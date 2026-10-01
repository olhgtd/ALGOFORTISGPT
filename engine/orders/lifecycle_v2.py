"""AlgoFortis V2 broker-neutral order execution lifecycle.

This module models execution state only. It never calls a broker. In-doubt
resolution consumes explicit broker-truth evidence supplied by a higher layer,
and retry after NOT_FOUND requires a fresh Risk-Gate ApprovedOrder with the
same idempotent client-order identity and an unexpired TTL.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

from engine.orders.contracts_v2 import ApprovedOrder


class OrderLifecycleError(ValueError):
    """Raised when an execution lifecycle transition would violate safety."""


class OrderExecutionState(str, Enum):
    RISK_APPROVED = "RISK_APPROVED"
    SUBMITTING = "SUBMITTING"
    SENT_UNACKED = "SENT_UNACKED"
    IN_DOUBT = "IN_DOUBT"
    ACKED = "ACKED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    NOT_FOUND = "NOT_FOUND"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class BrokerTruth(str, Enum):
    ACKED = "ACKED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    NOT_FOUND = "NOT_FOUND"


_BROKER_ORDER_EXISTS_TRUTH = frozenset(
    {
        BrokerTruth.ACKED,
        BrokerTruth.PARTIALLY_FILLED,
        BrokerTruth.FILLED,
        BrokerTruth.CANCELLED,
    }
)


_ALLOWED_TRANSITIONS: dict[OrderExecutionState, frozenset[OrderExecutionState]] = {
    OrderExecutionState.RISK_APPROVED: frozenset(
        {OrderExecutionState.SUBMITTING, OrderExecutionState.EXPIRED}
    ),
    OrderExecutionState.SUBMITTING: frozenset({OrderExecutionState.SENT_UNACKED}),
    OrderExecutionState.SENT_UNACKED: frozenset(
        {OrderExecutionState.ACKED, OrderExecutionState.IN_DOUBT}
    ),
    OrderExecutionState.IN_DOUBT: frozenset(
        {
            OrderExecutionState.ACKED,
            OrderExecutionState.PARTIALLY_FILLED,
            OrderExecutionState.FILLED,
            OrderExecutionState.CANCELLED,
            OrderExecutionState.REJECTED,
            OrderExecutionState.NOT_FOUND,
        }
    ),
    OrderExecutionState.ACKED: frozenset(
        {
            OrderExecutionState.PARTIALLY_FILLED,
            OrderExecutionState.CANCEL_PENDING,
            OrderExecutionState.REJECTED,
        }
    ),
    OrderExecutionState.PARTIALLY_FILLED: frozenset(
        {OrderExecutionState.FILLED, OrderExecutionState.CANCEL_PENDING}
    ),
    OrderExecutionState.CANCEL_PENDING: frozenset({OrderExecutionState.CANCELLED}),
    OrderExecutionState.NOT_FOUND: frozenset({OrderExecutionState.SUBMITTING}),
    OrderExecutionState.FILLED: frozenset(),
    OrderExecutionState.CANCELLED: frozenset(),
    OrderExecutionState.REJECTED: frozenset(),
    OrderExecutionState.EXPIRED: frozenset(),
}


class _Clock(Protocol):
    def now_utc(self) -> datetime: ...


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OrderLifecycleError(f"{field_name} must be a non-empty string")
    return value.strip()


def _aware(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise OrderLifecycleError(f"{field_name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class OrderTransitionEvidence:
    client_order_id: str
    intent_id: str
    from_state: OrderExecutionState
    to_state: OrderExecutionState
    reason: str
    timestamp: datetime
    broker_truth: BrokerTruth | None = None
    broker_order_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "client_order_id", _text(self.client_order_id, "client_order_id"))
        object.__setattr__(self, "intent_id", _text(self.intent_id, "intent_id"))
        if not isinstance(self.from_state, OrderExecutionState):
            raise TypeError("from_state must be an OrderExecutionState")
        if not isinstance(self.to_state, OrderExecutionState):
            raise TypeError("to_state must be an OrderExecutionState")
        object.__setattr__(self, "reason", _text(self.reason, "reason"))
        object.__setattr__(self, "timestamp", _aware(self.timestamp, "timestamp"))
        if self.broker_truth is not None and not isinstance(self.broker_truth, BrokerTruth):
            raise TypeError("broker_truth must be BrokerTruth or None")
        if self.broker_order_id is not None:
            object.__setattr__(self, "broker_order_id", _text(self.broker_order_id, "broker_order_id"))
        if self.broker_truth in _BROKER_ORDER_EXISTS_TRUTH and self.broker_order_id is None:
            raise OrderLifecycleError(
                f"{self.broker_truth.value} broker truth requires broker_order_id"
            )


class OrderExecutionLifecycle:
    """Immutable state-machine record for one idempotent ApprovedOrder."""

    def __init__(
        self,
        approved_order: ApprovedOrder,
        *,
        clock: _Clock,
        _state: OrderExecutionState = OrderExecutionState.RISK_APPROVED,
        _history: tuple[OrderTransitionEvidence, ...] = (),
    ) -> None:
        if not isinstance(approved_order, ApprovedOrder):
            raise TypeError("approved_order must be an ApprovedOrder")
        if not callable(getattr(clock, "now_utc", None)):
            raise TypeError("clock must provide now_utc()")
        if not isinstance(_state, OrderExecutionState):
            raise TypeError("state must be an OrderExecutionState")
        if not isinstance(_history, tuple) or not all(
            isinstance(item, OrderTransitionEvidence) for item in _history
        ):
            raise TypeError("history must contain OrderTransitionEvidence values")
        self._approved_order = approved_order
        self._clock = clock
        self._state = _state
        self._history = _history

    @property
    def approved_order(self) -> ApprovedOrder:
        return self._approved_order

    @property
    def state(self) -> OrderExecutionState:
        return self._state

    @property
    def history(self) -> tuple[OrderTransitionEvidence, ...]:
        return self._history

    @property
    def last_transition(self) -> OrderTransitionEvidence | None:
        return self._history[-1] if self._history else None

    @staticmethod
    def allowed_transitions(state: OrderExecutionState) -> frozenset[OrderExecutionState]:
        if not isinstance(state, OrderExecutionState):
            raise TypeError("state must be an OrderExecutionState")
        return _ALLOWED_TRANSITIONS[state]

    def transition_to(
        self,
        state: OrderExecutionState,
        *,
        reason: str,
    ) -> "OrderExecutionLifecycle":
        if not isinstance(state, OrderExecutionState):
            raise TypeError("state must be an OrderExecutionState")
        normalized_reason = _text(reason, "reason")

        if self._state is OrderExecutionState.IN_DOUBT:
            raise OrderLifecycleError(
                "broker truth is required to resolve IN_DOUBT; blind retry or assumed state is forbidden"
            )
        if self._state is OrderExecutionState.NOT_FOUND:
            raise OrderLifecycleError(
                "NOT_FOUND retry requires a fresh Risk Gate approval and the same client_order_id"
            )
        if state not in _ALLOWED_TRANSITIONS[self._state]:
            raise OrderLifecycleError(
                f"invalid order lifecycle transition: {self._state.value} -> {state.value}"
            )

        now = self._now()
        if self._state is OrderExecutionState.RISK_APPROVED and state is OrderExecutionState.SUBMITTING:
            if now >= self._approved_order.expires_at:
                raise OrderLifecycleError("ApprovedOrder TTL expired before submission")
        if state is OrderExecutionState.EXPIRED and now < self._approved_order.expires_at:
            raise OrderLifecycleError("cannot enter EXPIRED before ApprovedOrder TTL passes")

        return self._spawn(state, reason=normalized_reason, timestamp=now)

    def mark_in_doubt(self, *, reason: str) -> "OrderExecutionLifecycle":
        if self._state is not OrderExecutionState.SENT_UNACKED:
            raise OrderLifecycleError("IN_DOUBT is valid only from SENT_UNACKED")
        return self._spawn(
            OrderExecutionState.IN_DOUBT,
            reason=_text(reason, "reason"),
            timestamp=self._now(),
        )

    def resolve_in_doubt(
        self,
        broker_truth: BrokerTruth,
        *,
        broker_order_id: str | None = None,
    ) -> "OrderExecutionLifecycle":
        if self._state is not OrderExecutionState.IN_DOUBT:
            raise OrderLifecycleError("broker truth resolution is valid only while IN_DOUBT")
        if not isinstance(broker_truth, BrokerTruth):
            raise TypeError("broker_truth must be BrokerTruth")

        target = {
            BrokerTruth.ACKED: OrderExecutionState.ACKED,
            BrokerTruth.PARTIALLY_FILLED: OrderExecutionState.PARTIALLY_FILLED,
            BrokerTruth.FILLED: OrderExecutionState.FILLED,
            BrokerTruth.CANCELLED: OrderExecutionState.CANCELLED,
            BrokerTruth.REJECTED: OrderExecutionState.REJECTED,
            BrokerTruth.NOT_FOUND: OrderExecutionState.NOT_FOUND,
        }[broker_truth]
        if broker_truth in _BROKER_ORDER_EXISTS_TRUTH:
            broker_order_id = _text(broker_order_id, "broker_order_id")
        elif broker_order_id is not None:
            broker_order_id = _text(broker_order_id, "broker_order_id")

        return self._spawn(
            target,
            reason=f"broker_truth_{broker_truth.value.lower()}",
            timestamp=self._now(),
            broker_truth=broker_truth,
            broker_order_id=broker_order_id,
        )

    def retry_not_found(self, reapproved_order: ApprovedOrder) -> "OrderExecutionLifecycle":
        if self._state is not OrderExecutionState.NOT_FOUND:
            raise OrderLifecycleError("retry is valid only after broker truth NOT_FOUND")
        if not isinstance(reapproved_order, ApprovedOrder):
            raise TypeError("reapproved_order must be an ApprovedOrder")
        if reapproved_order.client_order_id != self._approved_order.client_order_id:
            raise OrderLifecycleError("NOT_FOUND retry must use the same client_order_id")
        if reapproved_order.run_mode is not self._approved_order.run_mode:
            raise OrderLifecycleError("NOT_FOUND retry cannot change run_mode")
        now = self._now()
        if now >= reapproved_order.expires_at:
            raise OrderLifecycleError("fresh Risk Gate approval TTL has expired")
        if reapproved_order.risk_decision_ref == self._approved_order.risk_decision_ref:
            raise OrderLifecycleError("NOT_FOUND retry requires a fresh Risk Gate approval")

        evidence = OrderTransitionEvidence(
            client_order_id=self._approved_order.client_order_id,
            intent_id=self._approved_order.intent_id,
            from_state=self._state,
            to_state=OrderExecutionState.SUBMITTING,
            reason="broker_not_found_fresh_reapproval_retry",
            timestamp=now,
        )
        return OrderExecutionLifecycle(
            reapproved_order,
            clock=self._clock,
            _state=OrderExecutionState.SUBMITTING,
            _history=self._history + (evidence,),
        )

    def _spawn(
        self,
        state: OrderExecutionState,
        *,
        reason: str,
        timestamp: datetime,
        broker_truth: BrokerTruth | None = None,
        broker_order_id: str | None = None,
    ) -> "OrderExecutionLifecycle":
        evidence = OrderTransitionEvidence(
            client_order_id=self._approved_order.client_order_id,
            intent_id=self._approved_order.intent_id,
            from_state=self._state,
            to_state=state,
            reason=reason,
            timestamp=timestamp,
            broker_truth=broker_truth,
            broker_order_id=broker_order_id,
        )
        return OrderExecutionLifecycle(
            self._approved_order,
            clock=self._clock,
            _state=state,
            _history=self._history + (evidence,),
        )

    def _now(self) -> datetime:
        return _aware(self._clock.now_utc(), "clock value")


__all__ = [
    "BrokerTruth",
    "OrderExecutionState",
    "OrderLifecycleError",
    "OrderTransitionEvidence",
    "OrderExecutionLifecycle",
]
