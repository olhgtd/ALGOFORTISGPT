from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from engine.core.runtime import FixedClock
from engine.orders.contracts_v2 import ApprovedOrder, OrderIntent, OrderSource, RunMode
from engine.orders.lifecycle_v2 import BrokerTruth, OrderExecutionLifecycle, OrderExecutionState, OrderLifecycleError
from engine.orders.model import OrderType
from engine.portfolio.model import InstrumentIdentity
from engine.risk.gate_v2 import RiskEvaluation, RiskGateV2
from engine.risk.limits import HardLimitHierarchy, LimitDirection


class _Ids:
    def __init__(self) -> None:
        self.n = 0

    def new_id(self, kind: str) -> str:
        self.n += 1
        return f"{kind}-{self.n}"


class _Audit:
    def write(self, event_type: str, payload: dict[str, object]) -> None:
        return None


@dataclass
class _Evaluator:
    snapshot_id: str

    def evaluate(self, intent: OrderIntent) -> RiskEvaluation:
        return RiskEvaluation.approved(
            approved_qty=intent.qty,
            risk_rule_version="risk/v1",
            limits_snapshot_id=self.snapshot_id,
        )


def _approved() -> ApprovedOrder:
    now = datetime(2026, 9, 30, 9, 15, tzinfo=timezone.utc)
    identity = InstrumentIdentity(
        "NSE", "NIFTY26OCT22000CE", "options", underlying="NIFTY",
        expiry=date(2026, 10, 29), strike="22000", option_type="CE",
    )
    intent = OrderIntent(
        intent_id="intent-truth", strategy_id="orb", strategy_version="orb/v1",
        run_mode=RunMode.LIVE, instrument_ref=identity, side="BUY", qty=Decimal("1"),
        order_type=OrderType.MARKET, created_at=now, valid_until=now + timedelta(minutes=5),
        source=OrderSource.STRATEGY, provenance={"market_sequence": 1},
    )
    limits = HardLimitHierarchy(
        definitions={"max_order_qty": LimitDirection.MAXIMUM},
        platform={"max_order_qty": "10"},
    ).resolve()
    gate = RiskGateV2(
        evaluator=_Evaluator(limits.snapshot_id), clock=FixedClock(now, 1, object()),
        id_generator=_Ids(), audit_sink=_Audit(), hard_limits=limits,
    )
    result = gate.evaluate_entry(intent)
    assert isinstance(result, ApprovedOrder)
    return result


def _in_doubt() -> OrderExecutionLifecycle:
    clock = FixedClock(datetime(2026, 9, 30, 9, 16, tzinfo=timezone.utc), 2, object())
    lifecycle = OrderExecutionLifecycle(_approved(), clock=clock)
    lifecycle = lifecycle.transition_to(OrderExecutionState.SUBMITTING, reason="submit")
    lifecycle = lifecycle.transition_to(OrderExecutionState.SENT_UNACKED, reason="sent")
    return lifecycle.mark_in_doubt(reason="ack_timeout")


@pytest.mark.parametrize(
    ("truth", "expected"),
    [
        ("PARTIALLY_FILLED", OrderExecutionState.PARTIALLY_FILLED),
        ("FILLED", OrderExecutionState.FILLED),
        ("CANCELLED", OrderExecutionState.CANCELLED),
    ],
)
def test_in_doubt_resolves_to_explicit_broker_exposure_truth(truth: str, expected: OrderExecutionState) -> None:
    broker_truth = getattr(BrokerTruth, truth)
    resolved = _in_doubt().resolve_in_doubt(broker_truth, broker_order_id="broker-1")
    assert resolved.state is expected
    assert resolved.last_transition is not None
    assert resolved.last_transition.broker_truth is broker_truth
    assert resolved.last_transition.broker_order_id == "broker-1"


@pytest.mark.parametrize("truth", ["ACKED", "PARTIALLY_FILLED", "FILLED", "CANCELLED"])
def test_truth_that_proves_broker_order_exists_requires_broker_identity(truth: str) -> None:
    with pytest.raises(OrderLifecycleError, match="broker_order_id"):
        _in_doubt().resolve_in_doubt(getattr(BrokerTruth, truth))


def test_not_found_still_carries_no_broker_identity_and_requires_fresh_reapproval_for_retry() -> None:
    lifecycle = _in_doubt().resolve_in_doubt(BrokerTruth.NOT_FOUND)
    assert lifecycle.state is OrderExecutionState.NOT_FOUND
    with pytest.raises(OrderLifecycleError, match="fresh Risk Gate approval"):
        lifecycle.retry_not_found(lifecycle.approved_order)
