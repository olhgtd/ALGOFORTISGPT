"""Candidate arbitration over the existing Phase-7 reservation authority.

This module does not own accounting truth and cannot mint ApprovedOrder.  It
coordinates existing CapitalReservationBook instances keyed by broker/account
and applies one aggregate owner cap before survivors continue to the existing
PortfolioAdmissionCoordinator -> RiskGateV2 path.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from threading import RLock
from typing import Mapping

from engine.portfolio.v2.reservations import CapitalReservationBook, ReservationDecision


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _aware(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(f"{field} must be Decimal-compatible without float")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)  # type: ignore[arg-type]
    except Exception as exc:
        raise TypeError(f"{field} must be Decimal-compatible") from exc
    if not result.is_finite() or result <= 0:
        raise ValueError(f"{field} must be positive and finite")
    return result


@dataclass(frozen=True, slots=True, order=True)
class BrokerAccountKey:
    broker_id: str
    account_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "broker_id", _text(self.broker_id, "broker_id"))
        object.__setattr__(self, "account_id", _text(self.account_id, "account_id"))

    @property
    def reference(self) -> str:
        return f"{self.broker_id}:{self.account_id}"


@dataclass(frozen=True, slots=True)
class CandidateReservationRequest:
    candidate_id: str
    broker_account: BrokerAccountKey
    strategy_id: str
    required_capital: Decimal
    created_at: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _text(self.candidate_id, "candidate_id"))
        if not isinstance(self.broker_account, BrokerAccountKey):
            raise TypeError("broker_account must be BrokerAccountKey")
        object.__setattr__(self, "strategy_id", _text(self.strategy_id, "strategy_id"))
        object.__setattr__(self, "required_capital", _decimal(self.required_capital, "required_capital"))
        created = _aware(self.created_at, "created_at")
        valid_until = _aware(self.valid_until, "valid_until")
        if valid_until <= created:
            raise ValueError("valid_until must be after created_at")


@dataclass(frozen=True, slots=True)
class CandidateArbitrationDecision:
    accepted: bool
    reason: str
    candidate_id: str
    broker_account: BrokerAccountKey
    reservation_id: str | None
    account_reserved: Decimal
    aggregate_reserved: Decimal
    portfolio_admission_required: bool = True
    approved_order_authority: str = "RiskGateV2"


@dataclass(frozen=True, slots=True)
class _ActiveCandidateReservation:
    request: CandidateReservationRequest
    reservation_id: str


class PortfolioCandidateArbitrator:
    """Atomic broker/account arbitration over existing reservation books."""

    def __init__(
        self,
        reservation_books: Mapping[BrokerAccountKey, CapitalReservationBook],
        *,
        aggregate_capital_limit: Decimal,
    ) -> None:
        if not isinstance(reservation_books, Mapping) or not reservation_books:
            raise ValueError("reservation_books must be a non-empty mapping")
        books = dict(reservation_books)
        if any(not isinstance(k, BrokerAccountKey) or not isinstance(v, CapitalReservationBook) for k, v in books.items()):
            raise TypeError("reservation_books must map BrokerAccountKey to CapitalReservationBook")
        self._books = books
        self._aggregate_limit = _decimal(aggregate_capital_limit, "aggregate_capital_limit")
        self._active: dict[str, _ActiveCandidateReservation] = {}
        self._lock = RLock()

    @property
    def total_reserved(self) -> Decimal:
        with self._lock:
            return sum((book.snapshot().total_reserved for book in self._books.values()), Decimal("0"))

    def _cleanup_expired(self, now: datetime) -> None:
        expired = [
            candidate_id
            for candidate_id, active in self._active.items()
            if now >= active.request.valid_until
        ]
        for candidate_id in expired:
            active = self._active[candidate_id]
            book = self._books[active.request.broker_account]
            decision = book.release(active.reservation_id, released_at=now)
            if decision.accepted:
                del self._active[candidate_id]

    def reserve(self, request: CandidateReservationRequest) -> CandidateArbitrationDecision:
        if not isinstance(request, CandidateReservationRequest):
            raise TypeError("request must be CandidateReservationRequest")
        with self._lock:
            self._cleanup_expired(request.created_at)
            book = self._books.get(request.broker_account)
            if book is None:
                return CandidateArbitrationDecision(
                    False,
                    "BROKER_ACCOUNT_POOL_UNAVAILABLE",
                    request.candidate_id,
                    request.broker_account,
                    None,
                    Decimal("0"),
                    self.total_reserved,
                )
            if request.candidate_id in self._active:
                snap = book.snapshot()
                return CandidateArbitrationDecision(
                    False,
                    "DUPLICATE_ACTIVE_CANDIDATE",
                    request.candidate_id,
                    request.broker_account,
                    self._active[request.candidate_id].reservation_id,
                    snap.total_reserved,
                    self.total_reserved,
                )

            aggregate_before = self.total_reserved
            if aggregate_before + request.required_capital > self._aggregate_limit:
                return CandidateArbitrationDecision(
                    False,
                    "AGGREGATE_CAPITAL_EXCEEDED",
                    request.candidate_id,
                    request.broker_account,
                    None,
                    book.snapshot().total_reserved,
                    aggregate_before,
                )

            reservation_id = f"candidate:{request.candidate_id}"
            decision: ReservationDecision = book.reserve(
                reservation_id=reservation_id,
                user_id=book.policy.user_id,
                strategy_id=request.strategy_id,
                amount=request.required_capital,
                created_at=request.created_at,
            )
            if not decision.accepted:
                return CandidateArbitrationDecision(
                    False,
                    decision.reason,
                    request.candidate_id,
                    request.broker_account,
                    None,
                    decision.snapshot.total_reserved,
                    self.total_reserved,
                )

            self._active[request.candidate_id] = _ActiveCandidateReservation(request, reservation_id)
            return CandidateArbitrationDecision(
                True,
                "RESERVED_FOR_PORTFOLIO_ADMISSION",
                request.candidate_id,
                request.broker_account,
                reservation_id,
                decision.snapshot.total_reserved,
                self.total_reserved,
            )

    def release(self, candidate_id: str, *, released_at: datetime) -> bool:
        identity = _text(candidate_id, "candidate_id")
        when = _aware(released_at, "released_at")
        with self._lock:
            active = self._active.get(identity)
            if active is None:
                return False
            book = self._books[active.request.broker_account]
            decision = book.release(active.reservation_id, released_at=when)
            if not decision.accepted:
                return False
            del self._active[identity]
            return True


__all__ = [
    "BrokerAccountKey",
    "CandidateArbitrationDecision",
    "CandidateReservationRequest",
    "PortfolioCandidateArbitrator",
]
