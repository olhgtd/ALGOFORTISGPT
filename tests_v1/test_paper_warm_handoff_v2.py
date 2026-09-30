from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from engine.core.runtime import DeterministicIdGenerator, DeterministicSeedSource, FixedClock
from engine.orders.contracts_v2 import ApprovedOrder, OrderIntent, OrderSource, RunMode
from engine.orders.model import OrderType
from engine.paper.fill_simulator_v2 import FillSimulationPolicy, PaperFillSimulator, QuoteSnapshot
from engine.paper.warm_handoff_v2 import WarmPaperContext, WarmPaperHandoff
from engine.portfolio.model import InstrumentIdentity
from engine.risk.gate_v2 import RiskEvaluation, RiskGateV2
from engine.risk.limits import HardLimitHierarchy, LimitDirection


_LIMITS = HardLimitHierarchy(
    definitions={"max_order_qty": LimitDirection.MAXIMUM},
    platform={"max_order_qty": "10"},
).resolve()


@dataclass
class _Evaluator:
    def evaluate(self, intent: OrderIntent) -> RiskEvaluation:
        return RiskEvaluation.approved(
            approved_qty=intent.qty,
            risk_rule_version="risk-policy/test",
            limits_snapshot_id=_LIMITS.snapshot_id,
        )


class _Audit:
    def write(self, event_type: str, payload: dict[str, object]) -> None:
        return None


class _RecordingSimulator(PaperFillSimulator):
    def __init__(self) -> None:
        self.calls = []

    def simulate(self, approved_order, quote, policy, *, now):
        self.calls.append((approved_order, quote, policy, now))
        return "simulated"


def _clock() -> FixedClock:
    return FixedClock(datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc), 100, object())


def _intent() -> OrderIntent:
    created = datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)
    return OrderIntent(
        intent_id="paper-warm-1",
        strategy_id="orb",
        strategy_version="v1",
        run_mode=RunMode.PAPER,
        instrument_ref=InstrumentIdentity(
            "NSE", "NIFTY26SEP22000CE", "options",
            underlying="NIFTY", expiry=date(2026, 10, 1), strike="22000", option_type="CE",
        ),
        side="BUY",
        qty=Decimal("1"),
        order_type=OrderType.MARKET,
        created_at=created,
        valid_until=created + timedelta(minutes=5),
        source=OrderSource.STRATEGY,
        provenance={"dataset_version": "test"},
    )


def _approved_order() -> ApprovedOrder:
    clock = _clock()
    gate = RiskGateV2(
        evaluator=_Evaluator(),
        clock=clock,
        id_generator=DeterministicIdGenerator(clock, DeterministicSeedSource(11), "warm-paper-test"),
        audit_sink=_Audit(),
        hard_limits=_LIMITS,
    )
    result = gate.evaluate_entry(_intent())
    assert isinstance(result, ApprovedOrder)
    return result


def _policy() -> FillSimulationPolicy:
    return FillSimulationPolicy(
        policy_id="paper-fill/test",
        version="v1",
        tick_size=Decimal("0.05"),
        slippage_ticks=0,
        latency_ms=0,
        reject=False,
        disconnect=False,
        stale_after_ms=5_000,
        test_only=True,
    )


def _quote() -> QuoteSnapshot:
    return QuoteSnapshot(
        bid=Decimal("100.00"),
        ask=Decimal("100.05"),
        observed_at=datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc),
        sequence=7,
    )


def test_prepare_only_warms_static_non_authorizing_context() -> None:
    simulator = _RecordingSimulator()
    context = WarmPaperContext(
        fill_policy=_policy(),
        runtime_profile_ref="runtime:test",
        config_snapshot_ref="config:test",
    )
    handoff = WarmPaperHandoff(simulator=simulator, context=context)

    assert handoff.prepare() is context
    assert simulator.calls == []


def test_handoff_refuses_non_approved_order() -> None:
    handoff = WarmPaperHandoff(
        simulator=_RecordingSimulator(),
        context=WarmPaperContext(_policy(), "runtime:test", "config:test"),
    )
    with pytest.raises(TypeError, match="ApprovedOrder"):
        handoff.handoff(object(), _quote(), now=datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc))


def test_handoff_forwards_only_genuine_paper_approved_order_to_existing_simulator() -> None:
    simulator = _RecordingSimulator()
    context = WarmPaperContext(_policy(), "runtime:test", "config:test")
    handoff = WarmPaperHandoff(simulator=simulator, context=context)
    approved = _approved_order()
    quote = _quote()
    now = datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)

    assert handoff.handoff(approved, quote, now=now) == "simulated"
    assert simulator.calls == [(approved, quote, context.fill_policy, now)]
