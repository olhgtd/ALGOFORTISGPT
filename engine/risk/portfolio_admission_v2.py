"""Reservation-aware admission wrapper around the existing central RiskGateV2."""
from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from engine.orders.contracts_v2 import OrderIntent
from engine.risk.gate_v2 import RiskGateV2, RiskRejection


@dataclass(frozen=True, slots=True)
class PortfolioAdmissionRejection:
    intent_id: str
    reason: str
    reservation_reason: str | None = None


class PortfolioAdmissionCoordinator:
    """Reserve/adopt capital, delegate to RiskGateV2, and own reservation lifecycle."""

    def __init__(self, risk_gate: RiskGateV2, context_provider, reservation_book) -> None:
        if not isinstance(risk_gate, RiskGateV2):
            raise TypeError("risk_gate must be RiskGateV2")
        if not callable(getattr(context_provider, "context_for", None)):
            raise TypeError("context_provider must provide context_for(intent)")
        if not callable(getattr(reservation_book, "reserve", None)) or not callable(
            getattr(reservation_book, "release", None)
        ):
            raise TypeError("reservation_book must provide reserve/release")
        self._gate = risk_gate
        self._contexts = context_provider
        self._reservations = reservation_book
        self._retained: dict[str, str] = {}
        self._lock = RLock()

    def evaluate_entry(self, intent: OrderIntent):
        if not isinstance(intent, OrderIntent):
            raise TypeError("intent must be OrderIntent")
        with self._lock:
            if intent.intent_id in self._retained:
                return PortfolioAdmissionRejection(
                    intent.intent_id,
                    "DUPLICATE_ACTIVE_ADMISSION",
                )

        try:
            context = self._contexts.context_for(intent)
        except Exception:
            return PortfolioAdmissionRejection(
                intent.intent_id,
                "PORTFOLIO_CONTEXT_UNAVAILABLE",
            )
        for attr in ("reservation_id", "required_capital", "evaluated_at"):
            if not hasattr(context, attr):
                return PortfolioAdmissionRejection(
                    intent.intent_id,
                    "PORTFOLIO_CONTEXT_UNAVAILABLE",
                )

        policy = getattr(self._reservations, "policy", None)
        user_id = getattr(policy, "user_id", None)
        if not isinstance(user_id, str) or not user_id:
            return PortfolioAdmissionRejection(
                intent.intent_id,
                "RESERVATION_POLICY_UNAVAILABLE",
            )

        # Candidate arbitration may have already reserved the exact capital in
        # this same Phase-7 reservation book.  Adopt that reservation instead
        # of reserving a second time.  This is a hand-off, not a parallel
        # accounting authority.
        existing = None
        get_active = getattr(self._reservations, "get_active", None)
        if callable(get_active):
            existing = get_active(context.reservation_id)

        if existing is not None:
            if (
                getattr(existing, "user_id", None) != user_id
                or getattr(existing, "strategy_id", None) != intent.strategy_id
                or getattr(existing, "amount", None) != context.required_capital
            ):
                return PortfolioAdmissionRejection(
                    intent.intent_id,
                    "PRE_RESERVED_CAPITAL_MISMATCH",
                )
        else:
            reservation = self._reservations.reserve(
                reservation_id=context.reservation_id,
                user_id=user_id,
                strategy_id=intent.strategy_id,
                amount=context.required_capital,
                created_at=context.evaluated_at,
            )
            if getattr(reservation, "accepted", False) is not True:
                return PortfolioAdmissionRejection(
                    intent.intent_id,
                    "CAPITAL_RESERVATION_REJECTED",
                    str(getattr(reservation, "reason", "UNKNOWN")),
                )

        try:
            result = self._gate.evaluate_entry(intent)
        except Exception:
            self._reservations.release(
                context.reservation_id,
                released_at=context.evaluated_at,
            )
            raise

        if isinstance(result, RiskRejection):
            self._reservations.release(
                context.reservation_id,
                released_at=context.evaluated_at,
            )
            return result

        if (
            getattr(result, "intent_id", None) != intent.intent_id
            or not getattr(result, "risk_decision_ref", None)
        ):
            self._reservations.release(
                context.reservation_id,
                released_at=context.evaluated_at,
            )
            return PortfolioAdmissionRejection(
                intent.intent_id,
                "RISK_GATE_INVALID_RESULT",
            )

        with self._lock:
            if intent.intent_id in self._retained:
                self._reservations.release(
                    context.reservation_id,
                    released_at=context.evaluated_at,
                )
                return PortfolioAdmissionRejection(
                    intent.intent_id,
                    "DUPLICATE_ACTIVE_ADMISSION",
                )
            self._retained[intent.intent_id] = context.reservation_id
        return result

    def release_terminal(self, intent_id: str, *, released_at) -> bool:
        if not isinstance(intent_id, str) or not intent_id.strip():
            raise ValueError("intent_id must be a non-empty string")
        with self._lock:
            reservation_id = self._retained.get(intent_id)
            if reservation_id is None:
                return False
            decision = self._reservations.release(
                reservation_id,
                released_at=released_at,
            )
            if getattr(decision, "accepted", False) is not True:
                return False
            del self._retained[intent_id]
            return True


__all__ = [
    "PortfolioAdmissionCoordinator",
    "PortfolioAdmissionRejection",
]
