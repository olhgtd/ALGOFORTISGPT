from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from engine.core.runtime import DeterministicIdGenerator, DeterministicSeedSource, FixedClock
from engine.orders.contracts_v2 import OrderIntent, OrderSource, RunMode
from engine.orders.model import OrderType
from engine.paper.execution_adapter_v2 import PaperExecutionAdapterV2
from engine.paper.fill_simulator_v2 import FillSimulationPolicy, PaperFillSimulator, QuoteSnapshot
from engine.paper.warm_handoff_v2 import WarmPaperHandoff
from engine.portfolio.model import InstrumentIdentity
from engine.risk.gate_v2 import RiskEvaluation, RiskGateV2
from engine.risk.limits import HardLimitHierarchy, LimitDirection


class _Eval:
    def evaluate(self, intent):
        return RiskEvaluation.approved(
            approved_qty=intent.qty,
            risk_rule_version="risk-v1",
            limits_snapshot_id=_LIMITS.snapshot_id,
        )


class _Audit:
    def write(self, event_type, payload):
        return None


_LIMITS = HardLimitHierarchy(
    definitions={"max_order_qty": LimitDirection.MAXIMUM},
    platform={"max_order_qty": "10"},
).resolve()


def _approved():
    created = datetime(2026, 9, 30, 9, 15, tzinfo=timezone.utc)
    clock = FixedClock(created + timedelta(seconds=1), 1, object())
    instrument = InstrumentIdentity(
        "NSE", "NIFTY26OCT25000CE", "options",
        underlying="NIFTY", expiry=date(2026, 10, 29), strike="25000", option_type="CE",
    )
    intent = OrderIntent(
        intent_id="warm-intent-1", strategy_id="s", strategy_version="v1",
        run_mode=RunMode.PAPER, instrument_ref=instrument, side="BUY", qty="1",
        order_type=OrderType.MARKET, created_at=created,
        valid_until=created + timedelta(seconds=10), source=OrderSource.STRATEGY,
        provenance={"market_sequence": 1},
    )
    ids = DeterministicIdGenerator(clock, DeterministicSeedSource(1), "warm-test")
    return RiskGateV2(
        evaluator=_Eval(), clock=clock, id_generator=ids, audit_sink=_Audit(), hard_limits=_LIMITS
    ).evaluate_entry(intent)


def _policy() -> FillSimulationPolicy:
    return FillSimulationPolicy(
        policy_id="TEST_ONLY/fill", version="v1", tick_size=Decimal("0.05"),
        slippage_ticks=0, latency_ms=0, reject=False, disconnect=False,
        stale_after_ms=1000, test_only=True,
    )


def test_prepare_static_has_no_execution_side_effect() -> None:
    handoff = WarmPaperHandoff(PaperExecutionAdapterV2(PaperFillSimulator()))
    context = handoff.prepare_static(
        instrument_mapping_ref="instrument-map@1",
        serializer_ref="paper-serializer@1",
    )
    assert context.instrument_mapping_ref == "instrument-map@1"
    assert handoff.handoff_count == 0


def test_handoff_requires_real_paper_approved_order_and_is_single_use() -> None:
    handoff = WarmPaperHandoff(PaperExecutionAdapterV2(PaperFillSimulator()))
    context = handoff.prepare_static(
        instrument_mapping_ref="instrument-map@1",
        serializer_ref="paper-serializer@1",
    )
    approved = _approved()
    now = datetime(2026, 9, 30, 9, 15, 2, tzinfo=timezone.utc)
    quote = QuoteSnapshot(Decimal("224.90"), Decimal("225.10"), now, 10)
    result = handoff.handoff(approved, context, quote, _policy(), now=now)
    assert result.accepted is True
    assert handoff.handoff_count == 1
    with pytest.raises(ValueError, match="already handed off"):
        handoff.handoff(approved, context, quote, _policy(), now=now)


def test_handoff_rejects_fabricated_or_expired_capability() -> None:
    handoff = WarmPaperHandoff(PaperExecutionAdapterV2(PaperFillSimulator()))
    context = handoff.prepare_static(
        instrument_mapping_ref="instrument-map@1",
        serializer_ref="paper-serializer@1",
    )
    now = datetime(2026, 9, 30, 9, 15, 2, tzinfo=timezone.utc)
    quote = QuoteSnapshot(Decimal("224.90"), Decimal("225.10"), now, 10)
    with pytest.raises(TypeError):
        handoff.handoff(object(), context, quote, _policy(), now=now)
    approved = _approved()
    expired_now = approved.expires_at
    with pytest.raises(ValueError, match="expired"):
        handoff.handoff(approved, context, quote, _policy(), now=expired_now)
