"""Atomic in-process capital reservation book for Phase 7."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from threading import RLock

from .contracts import (
    CapitalReservation,
    PortfolioBudgetPolicy,
    ReservationSnapshot,
    _aware,
    _decimal,
    _text,
)


@dataclass(frozen=True, slots=True)
class ReservationDecision:
    accepted: bool
    reason: str
    reservation: CapitalReservation | None
    snapshot: ReservationSnapshot


class CapitalReservationBook:
    def __init__(self, policy: PortfolioBudgetPolicy) -> None:
        if not isinstance(policy, PortfolioBudgetPolicy):
            raise TypeError("policy must be PortfolioBudgetPolicy")
        self._policy = policy
        self._active: dict[str, CapitalReservation] = {}
        self._released: dict[str, CapitalReservation] = {}
        self._lock = RLock()

    @property
    def policy(self) -> PortfolioBudgetPolicy:
        return self._policy

    def _snapshot_unlocked(self) -> ReservationSnapshot:
        reserved_by_strategy: dict[str, Decimal] = {}
        total = Decimal("0")
        for reservation in self._active.values():
            total += reservation.amount
            reserved_by_strategy[reservation.strategy_id] = (
                reserved_by_strategy.get(reservation.strategy_id, Decimal("0"))
                + reservation.amount
            )
        return ReservationSnapshot(
            self._policy.reference,
            self._active,
            self._released,
            total,
            reserved_by_strategy,
        )

    def snapshot(self) -> ReservationSnapshot:
        with self._lock:
            return self._snapshot_unlocked()

    def get_active(self, reservation_id: str) -> CapitalReservation | None:
        identity = _text(reservation_id, "reservation_id")
        with self._lock:
            return self._active.get(identity)

    def reserve(
        self,
        *,
        reservation_id: str,
        user_id: str,
        strategy_id: str,
        amount: Decimal,
        created_at: datetime,
    ) -> ReservationDecision:
        identity = _text(reservation_id, "reservation_id")
        user = _text(user_id, "user_id")
        strategy = _text(strategy_id, "strategy_id")
        capital = _decimal(amount, "amount", positive=True)
        when = _aware(created_at, "created_at")

        with self._lock:
            if identity in self._active:
                return ReservationDecision(
                    False,
                    "DUPLICATE_ACTIVE_RESERVATION",
                    self._active[identity],
                    self._snapshot_unlocked(),
                )
            if identity in self._released:
                return ReservationDecision(
                    False,
                    "RESERVATION_ID_ALREADY_USED",
                    self._released[identity],
                    self._snapshot_unlocked(),
                )
            if user != self._policy.user_id:
                return ReservationDecision(False, "USER_MISMATCH", None, self._snapshot_unlocked())

            strategy_cap = self._policy.strategy_budget(strategy)
            if strategy_cap is None:
                return ReservationDecision(
                    False,
                    "STRATEGY_BUDGET_UNAVAILABLE",
                    None,
                    self._snapshot_unlocked(),
                )

            snapshot = self._snapshot_unlocked()
            strategy_reserved = snapshot.reserved_by_strategy.get(strategy, Decimal("0"))
            if strategy_reserved + capital > strategy_cap:
                return ReservationDecision(False, "STRATEGY_BUDGET_EXCEEDED", None, snapshot)
            if snapshot.total_reserved + capital > self._policy.user_budget:
                return ReservationDecision(False, "USER_BUDGET_EXCEEDED", None, snapshot)

            reservation = CapitalReservation(
                identity,
                user,
                strategy,
                capital,
                when,
                self._policy.reference,
            )
            self._active[identity] = reservation
            return ReservationDecision(True, "RESERVED", reservation, self._snapshot_unlocked())

    def release(self, reservation_id: str, *, released_at: datetime) -> ReservationDecision:
        identity = _text(reservation_id, "reservation_id")
        when = _aware(released_at, "released_at")
        with self._lock:
            if identity in self._released:
                return ReservationDecision(
                    False,
                    "ALREADY_RELEASED",
                    self._released[identity],
                    self._snapshot_unlocked(),
                )
            current = self._active.get(identity)
            if current is None:
                return ReservationDecision(
                    False,
                    "RESERVATION_NOT_FOUND",
                    None,
                    self._snapshot_unlocked(),
                )
            released = replace(current, released_at=when)
            del self._active[identity]
            self._released[identity] = released
            return ReservationDecision(True, "RELEASED", released, self._snapshot_unlocked())


__all__ = ["CapitalReservationBook", "ReservationDecision"]
