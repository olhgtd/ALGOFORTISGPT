from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from engine.core.runtime import DeterministicIdGenerator, DeterministicSeedSource, FixedClock
from engine.orders.contracts_v2 import ApprovedOrder, OrderIntent, OrderSource, RunMode
from engine.orders.lifecycle_v2 import (
    BrokerTruth,
    OrderExecutionLifecycle,
    OrderExecutionState,
    OrderLifecycleError,
)
from engine.orders.model import OrderType
from engine.portfolio.model import InstrumentIdentity
from engine.risk.gate_v2 import RiskEvaluation, RiskGateV2
from engine.risk.limits import HardLimitHierarchy, LimitDirection


@dataclass
class _Evaluator:
    result: RiskEvaluation

    def evaluate(self, intent: OrderIntent) -> RiskEvaluation:
        return self.result


class _AuditSink:
    def write(self, event_type: str, payload: dict[str, object]) -> None:
        return None


class _MutableClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def now_utc(self) -> datetime:
        return self.current


def _clock(*, minute: int = 16) -> FixedClock:
    return FixedClock(
        datetime(2026, 9, 21, 9, minute, tzinfo=timezone.utc),
        123,
        object(),
    )


def _limits():
    return HardLimitHierarchy(
        definitions={"max_order_qty": LimitDirection.MAXIMUM},
        platform={"max_order_qty": "10"},
    ).resolve()


def _intent(*, intent_id: str = "intent-lifecycle", valid_for_minutes: int = 10) -> OrderIntent:
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
        intent_id=intent_id,
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


def _approved_order(
    *,
    intent_id: str = "intent-lifecycle",
    valid_for_minutes: int = 10,
    id_namespace: str = "phase2-lifecycle-test",
) -> ApprovedOrder:
    intent = _intent(intent_id=intent_id, valid_for_minutes=valid_for_minutes)
    limits = _limits()
    runtime_clock = _clock()
    gate = RiskGateV2(
        evaluator=_Evaluator(
            RiskEvaluation.approved(
                approved_qty="2",
                risk_rule_version="risk-policy/v4",
                limits_snapshot_id=limits.snapshot_id,
            )
        ),
        clock=runtime_clock,
        id_generator=DeterministicIdGenerator(
            runtime_clock,
            DeterministicSeedSource(7),
            id_namespace,
        ),
        audit_sink=_AuditSink(),
        hard_limits=limits,
    )
    result = gate.evaluate_entry(intent)
    assert isinstance(result, ApprovedOrder)
    return result


def test_allowed_transition_table_matches_canonical_architecture() -> None:
    expected = {
        OrderExecutionState.RISK_APPROVED: frozenset({OrderExecutionState.SUBMITTING, OrderExecutionState.EXPIRED}),
        OrderExecutionState.SUBMITTING: frozenset({OrderExecutionState.SENT_UNACKED}),
        OrderExecutionState.SENT_UNACKED: frozenset({OrderExecutionState.ACKED, OrderExecutionState.IN_DOUBT}),
        OrderExecutionState.IN_DOUBT: frozenset({OrderExecutionState.ACKED, OrderExecutionState.REJECTED, OrderExecutionState.NOT_FOUND}),
        OrderExecutionState.ACKED: frozenset({OrderExecutionState.PARTIALLY_FILLED, OrderExecutionState.CANCEL_PENDING, OrderExecutionState.REJECTED}),
        OrderExecutionState.PARTIALLY_FILLED: frozenset({OrderExecutionState.FILLED, OrderExecutionState.CANCEL_PENDING}),
        OrderExecutionState.CANCEL_PENDING: frozenset({OrderExecutionState.CANCELLED}),
        OrderExecutionState.NOT_FOUND: frozenset({OrderExecutionState.SUBMITTING}),
        OrderExecutionState.FILLED: frozenset(),
        OrderExecutionState.CANCELLED: frozenset(),
        OrderExecutionState.REJECTED: frozenset(),
        OrderExecutionState.EXPIRED: frozenset(),
    }

    assert {
        state: OrderExecutionLifecycle.allowed_transitions(state)
        for state in OrderExecutionState
    } == expected


def test_canonical_happy_path_reaches_filled() -> None:
    lifecycle = OrderExecutionLifecycle(_approved_order(), clock=_clock())

    lifecycle = lifecycle.transition_to(OrderExecutionState.SUBMITTING, reason="router_submit")
    lifecycle = lifecycle.transition_to(OrderExecutionState.SENT_UNACKED, reason="transport_sent")
    lifecycle = lifecycle.transition_to(OrderExecutionState.ACKED, reason="broker_ack")
    lifecycle = lifecycle.transition_to(OrderExecutionState.PARTIALLY_FILLED, reason="partial_fill")
    lifecycle = lifecycle.transition_to(OrderExecutionState.FILLED, reason="fill_complete")

    assert lifecycle.state is OrderExecutionState.FILLED
    assert lifecycle.last_transition is not None
    assert lifecycle.last_transition.from_state is OrderExecutionState.PARTIALLY_FILLED
    assert lifecycle.last_transition.to_state is OrderExecutionState.FILLED
    assert lifecycle.last_transition.client_order_id == lifecycle.approved_order.client_order_id


def test_representative_illegal_transition_is_rejected() -> None:
    lifecycle = OrderExecutionLifecycle(_approved_order(), clock=_clock())

    with pytest.raises(OrderLifecycleError, match="invalid"):
        lifecycle.transition_to(OrderExecutionState.FILLED, reason="skip_states")


def test_sent_without_ack_enters_in_doubt() -> None:
    lifecycle = OrderExecutionLifecycle(_approved_order(), clock=_clock())
    lifecycle = lifecycle.transition_to(OrderExecutionState.SUBMITTING, reason="router_submit")
    lifecycle = lifecycle.transition_to(OrderExecutionState.SENT_UNACKED, reason="transport_sent")

    lifecycle = lifecycle.mark_in_doubt(reason="ack_timeout")

    assert lifecycle.state is OrderExecutionState.IN_DOUBT
    assert lifecycle.last_transition is not None
    assert lifecycle.last_transition.reason == "ack_timeout"


def test_in_doubt_cannot_be_blindly_retried_or_directly_acked() -> None:
    lifecycle = OrderExecutionLifecycle(_approved_order(), clock=_clock())
    lifecycle = lifecycle.transition_to(OrderExecutionState.SUBMITTING, reason="router_submit")
    lifecycle = lifecycle.transition_to(OrderExecutionState.SENT_UNACKED, reason="transport_sent")
    lifecycle = lifecycle.mark_in_doubt(reason="ack_timeout")

    with pytest.raises(OrderLifecycleError, match="broker truth"):
        lifecycle.transition_to(OrderExecutionState.SUBMITTING, reason="blind_retry")
    with pytest.raises(OrderLifecycleError, match="broker truth"):
        lifecycle.transition_to(OrderExecutionState.ACKED, reason="assume_ack")


def test_in_doubt_resolves_only_through_explicit_broker_truth() -> None:
    lifecycle = OrderExecutionLifecycle(_approved_order(), clock=_clock())
    lifecycle = lifecycle.transition_to(OrderExecutionState.SUBMITTING, reason="router_submit")
    lifecycle = lifecycle.transition_to(OrderExecutionState.SENT_UNACKED, reason="transport_sent")
    lifecycle = lifecycle.mark_in_doubt(reason="ack_timeout")

    acked = lifecycle.resolve_in_doubt(BrokerTruth.ACKED, broker_order_id="broker-123")

    assert acked.state is OrderExecutionState.ACKED
    assert acked.last_transition is not None
    assert acked.last_transition.broker_truth is BrokerTruth.ACKED
    assert acked.last_transition.broker_order_id == "broker-123"


def test_not_found_retry_requires_fresh_approval_same_client_id_and_valid_ttl() -> None:
    original = _approved_order(id_namespace="initial-approval")
    lifecycle = OrderExecutionLifecycle(original, clock=_clock())
    lifecycle = lifecycle.transition_to(OrderExecutionState.SUBMITTING, reason="router_submit")
    lifecycle = lifecycle.transition_to(OrderExecutionState.SENT_UNACKED, reason="transport_sent")
    lifecycle = lifecycle.mark_in_doubt(reason="ack_timeout")
    lifecycle = lifecycle.resolve_in_doubt(BrokerTruth.NOT_FOUND)
    assert lifecycle.state is OrderExecutionState.NOT_FOUND

    reapproved = _approved_order(id_namespace="fresh-reapproval")
    retried = lifecycle.retry_not_found(reapproved)

    assert retried.state is OrderExecutionState.SUBMITTING
    assert retried.approved_order.client_order_id == original.client_order_id
    assert retried.approved_order.risk_decision_ref != original.risk_decision_ref


def test_not_found_retry_rejects_different_client_identity_and_expired_reapproval() -> None:
    original = _approved_order(intent_id="intent-original", valid_for_minutes=20)
    clock = _MutableClock(datetime(2026, 9, 21, 9, 16, tzinfo=timezone.utc))
    lifecycle = OrderExecutionLifecycle(original, clock=clock)
    lifecycle = lifecycle.transition_to(OrderExecutionState.SUBMITTING, reason="router_submit")
    lifecycle = lifecycle.transition_to(OrderExecutionState.SENT_UNACKED, reason="transport_sent")
    lifecycle = lifecycle.mark_in_doubt(reason="ack_timeout")
    lifecycle = lifecycle.resolve_in_doubt(BrokerTruth.NOT_FOUND)

    different = _approved_order(intent_id="intent-different")
    with pytest.raises(OrderLifecycleError, match="same client_order_id"):
        lifecycle.retry_not_found(different)

    expired = _approved_order(intent_id="intent-original", valid_for_minutes=5, id_namespace="expired-reapproval")
    clock.current = datetime(2026, 9, 21, 9, 26, tzinfo=timezone.utc)
    with pytest.raises(OrderLifecycleError, match="TTL"):
        lifecycle.retry_not_found(expired)
