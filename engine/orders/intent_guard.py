"""AlgoFortis V2 duplicate/stale approved-intent suppression.

This guard is broker-neutral.  It consumes an already-approved order identity at
most once, rejects stale capabilities, and can restore previously-consumed
identities after restart so replay cannot create a second executable order.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Protocol

from engine.orders.contracts_v2 import ApprovedOrder


class IntentGuardReason(str, Enum):
    DUPLICATE_INTENT_ID = "duplicate_intent_id"
    DUPLICATE_CLIENT_ORDER_ID = "duplicate_client_order_id"
    STALE_INTENT = "stale_intent"


def _identity(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _identity_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    normalized = tuple(_identity(value, field_name) for value in values)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_name} cannot contain duplicates")
    return tuple(sorted(normalized))


@dataclass(frozen=True, slots=True)
class IntentGuardState:
    consumed_intent_ids: tuple[str, ...]
    consumed_client_order_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "consumed_intent_ids",
            _identity_tuple(self.consumed_intent_ids, "consumed_intent_ids"),
        )
        object.__setattr__(
            self,
            "consumed_client_order_ids",
            _identity_tuple(self.consumed_client_order_ids, "consumed_client_order_ids"),
        )


@dataclass(frozen=True, slots=True)
class IntentGuardResult:
    accepted: bool
    intent_id: str
    client_order_id: str
    reason: IntentGuardReason | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "intent_id", _identity(self.intent_id, "intent_id"))
        object.__setattr__(
            self,
            "client_order_id",
            _identity(self.client_order_id, "client_order_id"),
        )
        if self.accepted:
            if self.reason is not None:
                raise ValueError("accepted guard result cannot carry a rejection reason")
        elif not isinstance(self.reason, IntentGuardReason):
            raise ValueError("rejected guard result requires an IntentGuardReason")


class _Clock(Protocol):
    def now_utc(self): ...


class IntentGuard:
    """Atomically consume each approved intent/client-order identity once."""

    def __init__(
        self,
        *,
        clock: _Clock,
        restored_state: IntentGuardState | None = None,
    ) -> None:
        if not callable(getattr(clock, "now_utc", None)):
            raise TypeError("clock must provide now_utc()")
        if restored_state is not None and not isinstance(restored_state, IntentGuardState):
            raise TypeError("restored_state must be an IntentGuardState")
        state = restored_state or IntentGuardState((), ())
        self._clock = clock
        self._consumed_intent_ids = set(state.consumed_intent_ids)
        self._consumed_client_order_ids = set(state.consumed_client_order_ids)
        self._lock = Lock()

    def consume(self, order: ApprovedOrder) -> IntentGuardResult:
        if not isinstance(order, ApprovedOrder):
            raise TypeError("order must be an ApprovedOrder")

        now = self._clock.now_utc()
        if getattr(now, "tzinfo", None) is None or now.utcoffset() is None:
            raise RuntimeError("clock returned a non-timezone-aware value")

        with self._lock:
            if now >= order.expires_at:
                return self._rejected(order, IntentGuardReason.STALE_INTENT)
            if order.intent_id in self._consumed_intent_ids:
                return self._rejected(order, IntentGuardReason.DUPLICATE_INTENT_ID)
            if order.client_order_id in self._consumed_client_order_ids:
                return self._rejected(order, IntentGuardReason.DUPLICATE_CLIENT_ORDER_ID)

            self._consumed_intent_ids.add(order.intent_id)
            self._consumed_client_order_ids.add(order.client_order_id)
            return IntentGuardResult(
                accepted=True,
                intent_id=order.intent_id,
                client_order_id=order.client_order_id,
            )

    def snapshot(self) -> IntentGuardState:
        with self._lock:
            return IntentGuardState(
                tuple(sorted(self._consumed_intent_ids)),
                tuple(sorted(self._consumed_client_order_ids)),
            )

    @staticmethod
    def _rejected(order: ApprovedOrder, reason: IntentGuardReason) -> IntentGuardResult:
        return IntentGuardResult(
            accepted=False,
            intent_id=order.intent_id,
            client_order_id=order.client_order_id,
            reason=reason,
        )


__all__ = [
    "IntentGuardReason",
    "IntentGuardState",
    "IntentGuardResult",
    "IntentGuard",
]
