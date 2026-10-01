from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from engine.core.runtime import DeterministicIdGenerator, DeterministicSeedSource, FixedClock
from engine.orders.contracts_v2 import ApprovedOrder, OrderIntent, OrderSource, RunMode
from engine.orders.model import OrderType
from engine.paper.execution_adapter_v2 import PaperExecutionAdapterV2
from engine.paper.fill_simulator_v2 import FillSimulationPolicy, PaperFillSimulator, QuoteSnapshot
from engine.portfolio.model import InstrumentIdentity
from engine.risk.gate_v2 import RiskEvaluation, RiskGateV2
from engine.risk.limits import HardLimitHierarchy, LimitDirection

UTC = timezone.utc
_NOW = datetime(2026, 9, 25, 9, 16, tzinfo=UTC)
_LIMITS = HardLimitHierarchy(
    definitions={"max_order_qty": LimitDirection.MAXIMUM},
    platform={"max_order_qty": "100"},
).resolve()


@dataclass
class _Evaluator:
    def evaluate(self, intent: OrderIntent) -> RiskEvaluation:
        return RiskEvaluation.approved(
            approved_qty=intent.qty,
            risk_rule_version="risk/phase5-test-v1",
            limits_snapshot_id=_LIMITS.snapshot_id,
        )


class _Audit:
    def write(self, event_type: str, payload: dict[str, object]) -> None:
        return None


def _approved(*, side: str = "BUY", segment: str = "equity") -> ApprovedOrder:
    clock = FixedClock(_NOW, 1, object())
    instrument = InstrumentIdentity("NSE", "TEST", segment)
    intent = OrderIntent(
        intent_id=f"intent-{side.lower()}",
        strategy_id="phase5-test",
        strategy_version="v1",
        run_mode=RunMode.PAPER,
        instrument_ref=instrument,
        side=side,
        qty=Decimal("2"),
        order_type=OrderType.MARKET,
        created_at=_NOW - timedelta(minutes=1),
        valid_until=_NOW + timedelta(minutes=5),
        source=OrderSource.STRATEGY,
        provenance={"fixture": "phase5"},
    )
    gate = RiskGateV2(
        evaluator=_Evaluator(),
        clock=clock,
        id_generator=DeterministicIdGenerator(clock, DeterministicSeedSource(11), "phase5-fill"),
        audit_sink=_Audit(),
        hard_limits=_LIMITS,
    )
    result = gate.evaluate_entry(intent)
    assert isinstance(result, ApprovedOrder)
    return result


def _policy(**overrides) -> FillSimulationPolicy:
    values = dict(
        policy_id="paper-fill/test",
        version="v1",
        tick_size=Decimal("0.05"),
        slippage_ticks=2,
        latency_ms=25,
        reject=False,
        disconnect=False,
        stale_after_ms=1_000,
        test_only=True,
    )
    values.update(overrides)
    return FillSimulationPolicy(**values)


def test_buy_uses_ask_and_sell_uses_bid_with_conservative_slippage():
    simulator = PaperFillSimulator()
    quote = QuoteSnapshot(
        bid=Decimal("100.00"),
        ask=Decimal("101.00"),
        observed_at=_NOW,
        sequence=7,
    )
    buy = simulator.simulate(_approved(side="BUY"), quote, _policy(), now=_NOW)
    sell = simulator.simulate(_approved(side="SELL"), quote, _policy(), now=_NOW)
    assert buy.accepted is True
    assert buy.fill_price == Decimal("101.10")
    assert sell.accepted is True
    assert sell.fill_price == Decimal("99.90")


def test_stale_quote_fails_closed_without_fabricating_fill():
    simulator = PaperFillSimulator()
    quote = QuoteSnapshot(
        bid=Decimal("100"),
        ask=Decimal("101"),
        observed_at=_NOW - timedelta(seconds=2),
        sequence=8,
    )
    result = simulator.simulate(_approved(), quote, _policy(stale_after_ms=500), now=_NOW)
    assert result.accepted is False
    assert result.reason == "STALE_QUOTE"
    assert result.fill_price is None


def test_disconnect_and_forced_rejection_are_deterministic_fail_closed_results():
    simulator = PaperFillSimulator()
    quote = QuoteSnapshot(Decimal("100"), Decimal("101"), _NOW, 9)
    disconnected = simulator.simulate(_approved(), quote, _policy(disconnect=True), now=_NOW)
    rejected = simulator.simulate(_approved(), quote, _policy(reject=True), now=_NOW)
    assert disconnected.reason == "DISCONNECTED"
    assert disconnected.accepted is False
    assert rejected.reason == "REJECTED_BY_POLICY"
    assert rejected.accepted is False


def test_same_inputs_produce_identical_simulated_execution():
    simulator = PaperFillSimulator()
    order = _approved()
    quote = QuoteSnapshot(Decimal("100"), Decimal("101"), _NOW, 10)
    policy = _policy()
    a = simulator.simulate(order, quote, policy, now=_NOW)
    b = simulator.simulate(order, quote, policy, now=_NOW)
    assert a == b


def test_paper_execution_adapter_rejects_raw_order_intent():
    adapter = PaperExecutionAdapterV2(PaperFillSimulator())
    approved = _approved()
    with pytest.raises(TypeError, match="ApprovedOrder"):
        adapter.execute(approved.intent, QuoteSnapshot(Decimal("100"), Decimal("101"), _NOW, 11), _policy(), now=_NOW)


def test_non_test_forced_failure_policy_is_rejected():
    with pytest.raises(ValueError, match="TEST_ONLY"):
        _policy(reject=True, test_only=False)
