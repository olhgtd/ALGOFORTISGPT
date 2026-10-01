"""Paper/Shadow-only RiskGate fast-path benchmark harness.

The harness imports no real broker adapter. All latency ceilings and probe
parameters are supplied by an explicit TEST_ONLY/CALIBRATION fixture. Warm and
cold probes are reported separately by rebuilding the local Paper/Shadow
runtime for every cold sample; neither mode authorizes Live or real-broker I/O.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
from time import perf_counter_ns

from engine.orders.contracts_v2 import OrderIntent, OrderSource, RunMode
from engine.orders.model import OrderType
from engine.paper.execution_adapter_v2 import PaperExecutionAdapterV2
from engine.paper.fill_simulator_v2 import FillSimulationPolicy, PaperFillSimulator, QuoteSnapshot
from engine.paper.warm_handoff_v2 import WarmPaperContext, WarmPaperHandoff
from engine.portfolio.model import InstrumentIdentity
from engine.risk.fast_path_v2 import CurrentQuoteEvidence, FastPathRiskEvaluator
from engine.risk.gate_v2 import RiskGateV2
from engine.risk.latency_benchmark_v2 import build_benchmark_evidence
from engine.risk.latency_evidence_v2 import RiskGateLatencyRecord, RiskLatencyStage
from engine.risk.latency_policy_v2 import LatencyPolicyStatus, LatencyStagePolicy, RiskGateLatencyPolicy
from engine.risk.limits import HardLimitHierarchy, LimitDirection
from engine.risk.snapshot_contracts_v2 import RiskSnapshot
from engine.risk.snapshot_publication_v2 import RiskSnapshotPublication


class _Clock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now_utc(self) -> datetime:
        return self._now

    def monotonic_ns(self) -> int:
        return perf_counter_ns()

    def session_calendar(self) -> object:
        return object()


class _Ids:
    def __init__(self) -> None:
        self._counter = 0

    def new_id(self, kind: str) -> str:
        self._counter += 1
        return f"bench-{kind}-{self._counter}"


class _Audit:
    def write(self, event_type: str, payload: dict[str, object]) -> None:
        # Deliberately bounded in-memory audit sink for benchmark isolation.
        _ = (event_type, payload)


class _LatencySink:
    def __init__(self) -> None:
        self.records: list[RiskGateLatencyRecord] = []

    def record(self, record: RiskGateLatencyRecord) -> None:
        self.records.append(record)


class _QuoteProvider:
    def __init__(self, quote: CurrentQuoteEvidence) -> None:
        self.quote = quote

    def current(self, instrument_ref: InstrumentIdentity) -> CurrentQuoteEvidence:
        return self.quote


class _ReplayGuard:
    def __init__(self) -> None:
        self.claimed: set[str] = set()

    def claim(self, intent_id: str, snapshot_id: str, market_sequence: int) -> bool:
        key = f"{intent_id}:{snapshot_id}:{market_sequence}"
        if key in self.claimed:
            return False
        self.claimed.add(key)
        return True


class _Freshness:
    reference = "TEST_ONLY/benchmark-freshness@v1"

    def is_fresh(self, snapshot: RiskSnapshot, now: datetime) -> bool:
        return True


class _PricePolicy:
    reference = "TEST_ONLY/benchmark-price@v1"

    def allows(self, intent: OrderIntent, quote: CurrentQuoteEvidence) -> bool:
        return True


class _EntryPolicy:
    reference = "TEST_ONLY/benchmark-entry@v1"

    def entries_allowed(self, snapshot: RiskSnapshot) -> bool:
        return snapshot.operational_state == "HEALTHY"


@dataclass(slots=True)
class _ProbeRuntime:
    gate: RiskGateV2
    latency_sink: _LatencySink
    handoff: WarmPaperHandoff
    context: WarmPaperContext
    quote: QuoteSnapshot
    fill_policy: FillSimulationPolicy


def _load_fixture(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("fixture must be a JSON object")
    return data


def _policy(data: dict[str, object]) -> RiskGateLatencyPolicy:
    policy = data["latency_policy"]
    if not isinstance(policy, dict):
        raise ValueError("latency_policy must be an object")
    stages = tuple(
        LatencyStagePolicy(
            stage_name=item["stage_name"],
            percentile_target=item["percentile_target"],
            ceiling_ns=int(item["ceiling_ns"]),
            breach_action=item["breach_action"],
        )
        for item in policy["stages"]
    )
    return RiskGateLatencyPolicy(
        policy_id=policy["policy_id"],
        version=policy["version"],
        status=LatencyPolicyStatus(policy["status"]),
        environment_scope=policy["environment_scope"],
        hardware_profile_ref=policy["hardware_profile_ref"],
        runtime_profile_ref=policy["runtime_profile_ref"],
        sample_minimum_ref=policy["sample_minimum_ref"],
        stages=stages,
        evidence_bundle_ref=policy.get("evidence_bundle_ref"),
        approval_ref=policy.get("approval_ref"),
    )


def _count_breaches(samples: tuple[int, ...], ceiling: int) -> int:
    return sum(1 for value in samples if value > ceiling)


def _build_runtime(
    *,
    policy: RiskGateLatencyPolicy,
    probe: dict[str, object],
    now: datetime,
    instrument: InstrumentIdentity,
    market_sequence: int,
) -> _ProbeRuntime:
    hard_limits = HardLimitHierarchy(
        definitions={"max_order_qty": LimitDirection.MAXIMUM},
        platform={"max_order_qty": str(probe["hard_max_order_qty"])},
    ).resolve()
    publication = RiskSnapshotPublication()
    scope = instrument.underlying or instrument.instrument
    snapshot = RiskSnapshot(
        snapshot_id="benchmark-snapshot",
        schema_version="v1",
        generated_at_utc=now,
        input_fingerprint="a" * 64,
        risk_rule_version="benchmark-risk-v1",
        limits_snapshot_id=hard_limits.snapshot_id,
        account_authority_ref="benchmark-account",
        strategy_eligibility_ref="benchmark-strategy",
        portfolio_state_ref="benchmark-portfolio",
        entry_policy_ref="benchmark-entry",
        operational_state="HEALTHY",
        kill_switch_state="CLEAR",
        hold_state="CLEAR",
        allowed_instrument_scope=(scope,),
        allowed_side_scope=("BUY",),
        quantity_ceiling_by_scope={scope: Decimal(str(probe["quantity_ceiling"]))},
        risk_budget_evidence="benchmark-risk-budget",
        feed_health_ref="benchmark-feed",
        latest_market_sequence=market_sequence,
        source_versions=("benchmark@v1",),
        builder_health_generation=1,
    )
    publication.publish(snapshot)
    current_quote = CurrentQuoteEvidence(
        instrument_ref=instrument,
        observed_at=now,
        market_sequence=market_sequence,
        bid=Decimal(str(probe["bid"])),
        ask=Decimal(str(probe["ask"])),
        source_ref="benchmark-quote",
    )
    clock = _Clock(now)
    evaluator = FastPathRiskEvaluator(
        publication=publication,
        quote_provider=_QuoteProvider(current_quote),
        replay_guard=_ReplayGuard(),
        freshness_policy=_Freshness(),
        price_policy=_PricePolicy(),
        entry_state_policy=_EntryPolicy(),
        clock=clock,
        active_risk_rule_version=snapshot.risk_rule_version,
        active_limits_snapshot_id=hard_limits.snapshot_id,
        active_builder_health_generation=lambda: 1,
        latency_policy_ref=policy.reference,
    )
    latency_sink = _LatencySink()
    gate = RiskGateV2(
        evaluator=evaluator,
        clock=clock,
        id_generator=_Ids(),
        audit_sink=_Audit(),
        hard_limits=hard_limits,
        monotonic_ns=perf_counter_ns,
        latency_sink=latency_sink,
    )
    handoff = WarmPaperHandoff(PaperExecutionAdapterV2(PaperFillSimulator()))
    context = handoff.prepare_static(
        instrument_mapping_ref="benchmark-map@v1",
        serializer_ref="benchmark-serializer@v1",
    )
    fill_policy = FillSimulationPolicy(
        policy_id="TEST_ONLY/benchmark-fill",
        version="v1",
        tick_size=Decimal(str(probe["tick_size"])),
        slippage_ticks=int(probe["slippage_ticks"]),
        latency_ms=int(probe["simulated_latency_ms"]),
        reject=False,
        disconnect=False,
        stale_after_ms=int(probe["stale_after_ms"]),
        test_only=True,
    )
    quote = QuoteSnapshot(current_quote.bid, current_quote.ask, now, market_sequence)
    return _ProbeRuntime(gate, latency_sink, handoff, context, quote, fill_policy)


def _approved_intent(
    *, index: int, now: datetime, instrument: InstrumentIdentity, probe: dict[str, object], market_sequence: int
) -> OrderIntent:
    return OrderIntent(
        intent_id=f"bench-approved-{index}",
        strategy_id="benchmark",
        strategy_version="v1",
        run_mode=RunMode.PAPER,
        instrument_ref=instrument,
        side="BUY",
        qty=Decimal(str(probe["order_qty"])),
        order_type=OrderType.MARKET,
        created_at=now,
        valid_until=now + timedelta(seconds=int(probe["intent_ttl_seconds"])),
        source=OrderSource.STRATEGY,
        provenance={"market_sequence": market_sequence},
    )


def _rejected_intent(
    *, index: int, now: datetime, instrument: InstrumentIdentity, probe: dict[str, object], market_sequence: int
) -> OrderIntent:
    return OrderIntent(
        intent_id=f"bench-rejected-{index}",
        strategy_id="benchmark",
        strategy_version="v1",
        run_mode=RunMode.PAPER,
        instrument_ref=instrument,
        side="SELL",
        qty=Decimal(str(probe["order_qty"])),
        order_type=OrderType.MARKET,
        created_at=now,
        valid_until=now + timedelta(seconds=int(probe["intent_ttl_seconds"])),
        source=OrderSource.STRATEGY,
        provenance={"market_sequence": market_sequence},
    )


def run_probe(*, fixture: dict[str, object], code_sha: str, iterations: int, warm: bool):
    if iterations <= 0:
        raise ValueError("iterations must be positive")
    policy = _policy(fixture)
    probe = fixture["probe"]
    if not isinstance(probe, dict):
        raise ValueError("probe must be an object")
    now = datetime.fromisoformat(str(probe["now_utc"]))
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("probe.now_utc must be timezone-aware")
    instrument = InstrumentIdentity(
        market="NSE",
        instrument=str(probe["instrument"]),
        segment="options",
        underlying=str(probe["underlying"]),
        expiry=date.fromisoformat(str(probe["expiry"])),
        strike=Decimal(str(probe["strike"])),
        option_type=str(probe["option_type"]),
    )
    market_sequence = int(probe["market_sequence"])

    shared_runtime = (
        _build_runtime(policy=policy, probe=probe, now=now, instrument=instrument, market_sequence=market_sequence)
        if warm else None
    )
    all_latency_records: list[RiskGateLatencyRecord] = []
    handoff_samples: list[int] = []

    for index in range(iterations):
        start = perf_counter_ns()
        runtime = shared_runtime or _build_runtime(
            policy=policy,
            probe=probe,
            now=now,
            instrument=instrument,
            market_sequence=market_sequence,
        )
        approved = runtime.gate.evaluate_entry(
            _approved_intent(
                index=index,
                now=now,
                instrument=instrument,
                probe=probe,
                market_sequence=market_sequence,
            )
        )
        runtime.handoff.handoff(
            approved,
            runtime.context,
            runtime.quote,
            runtime.fill_policy,
            now=now,
        )
        handoff_samples.append(perf_counter_ns() - start)
        runtime.gate.evaluate_entry(
            _rejected_intent(
                index=index,
                now=now,
                instrument=instrument,
                probe=probe,
                market_sequence=market_sequence,
            )
        )
        if shared_runtime is None:
            all_latency_records.extend(runtime.latency_sink.records)

    if shared_runtime is not None:
        all_latency_records.extend(shared_runtime.latency_sink.records)

    approved_samples: list[int] = []
    rejected_samples: list[int] = []
    audit_samples: list[int] = []
    for record in all_latency_records:
        total = record.duration_ns(RiskLatencyStage.RISK_GATE_ENTER, RiskLatencyStage.DECISION_FINALIZED)
        if record.decision_kind == "APPROVED":
            approved_samples.append(total)
        else:
            rejected_samples.append(total)
        if RiskLatencyStage.AUDIT_APPEND_COMPLETE in record.stage_timestamps_ns:
            audit_samples.append(
                record.duration_ns(RiskLatencyStage.CHECKS_COMPLETE, RiskLatencyStage.AUDIT_APPEND_COMPLETE)
            )

    breach_counts: dict[str, int] = {}
    sample_map = {
        "riskgate_total": tuple(approved_samples),
        "candidate_to_transport_handoff": tuple(handoff_samples),
        "audit_append": tuple(audit_samples),
    }
    for stage in policy.stages:
        samples = sample_map.get(stage.stage_name, ())
        breach_counts[stage.stage_name] = _count_breaches(samples, stage.ceiling_ns) if samples else 0

    return build_benchmark_evidence(
        code_sha=code_sha,
        policy=policy,
        hardware_profile_ref=policy.hardware_profile_ref,
        runtime_profile_ref=policy.runtime_profile_ref,
        warm=warm,
        approved_samples=tuple(approved_samples),
        rejected_samples=tuple(rejected_samples),
        candidate_to_handoff_samples=tuple(handoff_samples),
        audit_samples=tuple(audit_samples),
        breach_counts=breach_counts,
        sample_method_ref=str(probe["sample_method_ref"]),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--iterations", type=int, required=True)
    parser.add_argument("--warm", choices=("true", "false"), required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    evidence = run_probe(
        fixture=_load_fixture(Path(args.fixture)),
        code_sha=args.code_sha,
        iterations=args.iterations,
        warm=args.warm == "true",
    )
    Path(args.output).write_text(evidence.to_json() + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
