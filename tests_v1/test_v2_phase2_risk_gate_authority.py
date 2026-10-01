from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from engine.core.runtime import DeterministicIdGenerator, DeterministicSeedSource, FixedClock
from engine.orders.contracts_v2 import ApprovedOrder, OrderIntent, OrderSource, RunMode
from engine.orders.model import OrderType
from engine.portfolio.model import InstrumentIdentity
from engine.risk.gate_v2 import RiskApprovalError, RiskEvaluation, RiskGateV2, RiskRejection
from engine.risk.latency_evidence_v2 import RiskGateLatencyRecord
from engine.risk.limits import HardLimitHierarchy, LimitDirection


_LIMITS = HardLimitHierarchy(
    definitions={"max_order_qty": LimitDirection.MAXIMUM},
    platform={"max_order_qty": "10"},
).resolve()


@dataclass
class _Evaluator:
    result: RiskEvaluation
    calls: int = 0

    def evaluate(self, intent: OrderIntent) -> RiskEvaluation:
        assert isinstance(intent, OrderIntent)
        self.calls += 1
        return self.result


class _AuditSink:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[tuple[str, dict[str, object]]] = []

    def write(self, event_type: str, payload: dict[str, object]) -> None:
        if self.fail:
            raise RuntimeError("audit unavailable")
        self.events.append((event_type, dict(payload)))


class _LatencySink:
    def __init__(self) -> None:
        self.records: list[RiskGateLatencyRecord] = []

    def record(self, record: RiskGateLatencyRecord) -> None:
        self.records.append(record)


class _BrokenLatencySink:
    def record(self, record: RiskGateLatencyRecord) -> None:
        raise RuntimeError("latency sink unavailable")


def _clock(*, minute: int = 16) -> FixedClock:
    return FixedClock(
        datetime(2026, 9, 21, 9, minute, tzinfo=timezone.utc),
        123,
        object(),
    )


def _ids(clock: FixedClock) -> DeterministicIdGenerator:
    return DeterministicIdGenerator(clock, DeterministicSeedSource(7), "phase2-test")


def _intent(*, valid_for_minutes: int = 5) -> OrderIntent:
    created = datetime(2026, 9, 21, 9, 15, tzinfo=timezone.utc)
    instrument = InstrumentIdentity(
        "NSE",
        "NIFTY26SEP22000CE",
        "options",
        underlying="NIFTY",
        expiry=date(2026, 9, 24),
        strike="22000",
        option_type="CE",
    )
    return OrderIntent(
        intent_id="intent-001",
        strategy_id="orb",
        strategy_version="orb/v1",
        run_mode=RunMode.PAPER,
        instrument_ref=instrument,
        side="BUY",
        qty=Decimal("2"),
        order_type=OrderType.MARKET,
        created_at=created,
        valid_until=created + timedelta(minutes=valid_for_minutes),
        source=OrderSource.STRATEGY,
        provenance={"dataset_version": "ds-v1", "config_snapshot_id": "cfg-v1"},
    )


def _approved_evaluation(*, quantity: str = "2") -> RiskEvaluation:
    return RiskEvaluation.approved(
        approved_qty=Decimal(quantity),
        risk_rule_version="risk-policy/v4",
        limits_snapshot_id=_LIMITS.snapshot_id,
    )


def _gate(evaluator: _Evaluator, audit: _AuditSink, *, clock: FixedClock | None = None) -> RiskGateV2:
    runtime_clock = clock or _clock()
    return RiskGateV2(
        evaluator=evaluator,
        clock=runtime_clock,
        id_generator=_ids(runtime_clock),
        audit_sink=audit,
        hard_limits=_LIMITS,
    )


def test_approved_order_cannot_be_constructed_outside_risk_gate() -> None:
    with pytest.raises(TypeError, match="RiskGateV2"):
        ApprovedOrder(
            client_order_id="forged-client-order",
            intent_id="forged-intent",
            risk_decision_ref="0" * 64,
            run_mode=RunMode.PAPER,
            expires_at=datetime(2026, 9, 21, 9, 20, tzinfo=timezone.utc),
        )


def test_gate_mints_canonical_capability_only_after_approved_risk_and_audit() -> None:
    evaluator = _Evaluator(_approved_evaluation())
    audit = _AuditSink()
    gate = _gate(evaluator, audit)
    intent = _intent()

    result = gate.evaluate_entry(intent)

    assert isinstance(result, ApprovedOrder)
    assert result.intent_id == intent.intent_id
    assert result.run_mode is RunMode.PAPER
    assert result.expires_at == intent.valid_until
    assert result.client_order_id.startswith("af2_co_")
    assert len(result.risk_decision_ref) == 64
    assert result.intent is intent
    assert evaluator.calls == 1
    assert len(audit.events) == 1
    event_type, payload = audit.events[0]
    assert event_type == "RISK_APPROVAL_GRANTED"
    assert payload["client_order_id"] == result.client_order_id
    assert payload["intent_id"] == intent.intent_id
    assert payload["risk_decision_ref"] == result.risk_decision_ref
    assert payload["risk_rule_version"] == "risk-policy/v4"
    assert payload["limits_snapshot_id"] == _LIMITS.snapshot_id


def test_rejected_risk_never_mints_approved_order_and_is_audited() -> None:
    audit = _AuditSink()
    gate = _gate(
        _Evaluator(
            RiskEvaluation.rejected(
                "daily_loss_limit",
                risk_rule_version="risk-policy/v4",
                limits_snapshot_id=_LIMITS.snapshot_id,
            )
        ),
        audit,
    )

    result = gate.evaluate_entry(_intent())

    assert isinstance(result, RiskRejection)
    assert result.intent_id == "intent-001"
    assert result.reasons == ("daily_loss_limit",)
    assert audit.events == [
        (
            "RISK_APPROVAL_REJECTED",
            {
                "intent_id": "intent-001",
                "reasons": ("daily_loss_limit",),
                "risk_rule_version": "risk-policy/v4",
                "limits_snapshot_id": _LIMITS.snapshot_id,
            },
        )
    ]


def test_gate_fails_closed_when_approved_quantity_differs_from_intent_quantity() -> None:
    audit = _AuditSink()
    gate = _gate(_Evaluator(_approved_evaluation(quantity="1")), audit)

    result = gate.evaluate_entry(_intent())

    assert isinstance(result, RiskRejection)
    assert result.reasons == ("risk_quantity_mismatch",)
    assert audit.events[0][0] == "RISK_APPROVAL_REJECTED"
    assert audit.events[0][1]["reasons"] == ("risk_quantity_mismatch",)


def test_stale_intent_is_rejected_before_risk_evaluation() -> None:
    evaluator = _Evaluator(_approved_evaluation())
    audit = _AuditSink()
    gate = _gate(evaluator, audit, clock=_clock(minute=21))

    result = gate.evaluate_entry(_intent(valid_for_minutes=5))

    assert isinstance(result, RiskRejection)
    assert result.reasons == ("intent_expired",)
    assert evaluator.calls == 0
    assert audit.events[0][0] == "RISK_APPROVAL_REJECTED"
    assert audit.events[0][1]["reasons"] == ("intent_expired",)
    assert audit.events[0][1]["limits_snapshot_id"] == _LIMITS.snapshot_id


def test_audit_failure_blocks_approval_capability() -> None:
    gate = _gate(_Evaluator(_approved_evaluation()), _AuditSink(fail=True))

    with pytest.raises(RiskApprovalError, match="audit"):
        gate.evaluate_entry(_intent())


def test_client_order_id_is_deterministic_for_same_intent_across_replay() -> None:
    intent_a = _intent()
    intent_b = _intent()
    approved_a = _gate(_Evaluator(_approved_evaluation()), _AuditSink()).evaluate_entry(intent_a)
    approved_b = _gate(_Evaluator(_approved_evaluation()), _AuditSink()).evaluate_entry(intent_b)

    assert isinstance(approved_a, ApprovedOrder)
    assert isinstance(approved_b, ApprovedOrder)
    assert approved_a.client_order_id == approved_b.client_order_id
    assert approved_a.risk_decision_ref == approved_b.risk_decision_ref


def test_fast_path_evidence_is_written_to_audit_before_approval_and_latency_recorded() -> None:
    runtime_clock = _clock()
    evaluation = RiskEvaluation.approved(
        approved_qty=Decimal("2"),
        risk_rule_version="risk-policy/v4",
        limits_snapshot_id=_LIMITS.snapshot_id,
        risk_snapshot_id="snap-1",
        market_sequence_ref="7",
        latency_policy_ref="TEST_ONLY/latency@v1",
    )
    audit = _AuditSink()
    latency = _LatencySink()
    ticks = iter((10, 20, 30, 40, 50, 60))
    gate = RiskGateV2(
        evaluator=_Evaluator(evaluation),
        clock=runtime_clock,
        id_generator=_ids(runtime_clock),
        audit_sink=audit,
        hard_limits=_LIMITS,
        monotonic_ns=lambda: next(ticks),
        latency_sink=latency,
    )

    result = gate.evaluate_entry(_intent())

    assert isinstance(result, ApprovedOrder)
    assert audit.events[0][0] == "RISK_APPROVAL_GRANTED"
    assert audit.events[0][1]["risk_snapshot_id"] == "snap-1"
    assert audit.events[0][1]["market_sequence_ref"] == "7"
    assert audit.events[0][1]["latency_policy_ref"] == "TEST_ONLY/latency@v1"
    assert latency.records[-1].decision_kind == "APPROVED"
    assert latency.records[-1].audit_result == "WRITTEN"


def test_latency_telemetry_failure_cannot_block_audited_approval() -> None:
    runtime_clock = _clock()
    gate = RiskGateV2(
        evaluator=_Evaluator(_approved_evaluation()),
        clock=runtime_clock,
        id_generator=_ids(runtime_clock),
        audit_sink=_AuditSink(),
        hard_limits=_LIMITS,
        monotonic_ns=lambda: 100,
        latency_sink=_BrokenLatencySink(),
    )

    assert isinstance(gate.evaluate_entry(_intent()), ApprovedOrder)


def test_audit_failure_remains_primary_even_if_latency_sink_is_broken() -> None:
    runtime_clock = _clock()
    gate = RiskGateV2(
        evaluator=_Evaluator(_approved_evaluation()),
        clock=runtime_clock,
        id_generator=_ids(runtime_clock),
        audit_sink=_AuditSink(fail=True),
        hard_limits=_LIMITS,
        monotonic_ns=lambda: 100,
        latency_sink=_BrokenLatencySink(),
    )

    with pytest.raises(RiskApprovalError, match="audit"):
        gate.evaluate_entry(_intent())
