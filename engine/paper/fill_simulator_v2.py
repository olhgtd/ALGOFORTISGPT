"""Deterministic conservative Paper fill simulation for AlgoFortis V2 Phase 5.

The simulator accepts only the canonical RiskGate-minted ``ApprovedOrder``
capability.  It never imports a broker adapter and never performs I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from engine.orders.contracts_v2 import ApprovedOrder, RunMode


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _aware(value: object, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value


def _decimal(value: object, field: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field} must be a Decimal")
    if not value.is_finite():
        raise ValueError(f"{field} must be finite")
    if positive and value <= 0:
        raise ValueError(f"{field} must be positive")
    return value


def _non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be an int")
    if value < 0:
        raise ValueError(f"{field} must be non-negative")
    return value


@dataclass(frozen=True, slots=True)
class QuoteSnapshot:
    bid: Decimal
    ask: Decimal
    observed_at: datetime
    sequence: int

    def __post_init__(self) -> None:
        bid = _decimal(self.bid, "bid", positive=True)
        ask = _decimal(self.ask, "ask", positive=True)
        if bid > ask:
            raise ValueError("bid must not exceed ask")
        object.__setattr__(self, "bid", bid)
        object.__setattr__(self, "ask", ask)
        object.__setattr__(self, "observed_at", _aware(self.observed_at, "observed_at"))
        object.__setattr__(self, "sequence", _non_negative_int(self.sequence, "sequence"))


@dataclass(frozen=True, slots=True)
class FillSimulationPolicy:
    policy_id: str
    version: str
    tick_size: Decimal
    slippage_ticks: int
    latency_ms: int
    reject: bool
    disconnect: bool
    stale_after_ms: int
    test_only: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _text(self.policy_id, "policy_id"))
        object.__setattr__(self, "version", _text(self.version, "version"))
        object.__setattr__(self, "tick_size", _decimal(self.tick_size, "tick_size", positive=True))
        object.__setattr__(self, "slippage_ticks", _non_negative_int(self.slippage_ticks, "slippage_ticks"))
        object.__setattr__(self, "latency_ms", _non_negative_int(self.latency_ms, "latency_ms"))
        object.__setattr__(self, "stale_after_ms", _non_negative_int(self.stale_after_ms, "stale_after_ms"))
        if not isinstance(self.reject, bool):
            raise TypeError("reject must be bool")
        if not isinstance(self.disconnect, bool):
            raise TypeError("disconnect must be bool")
        if not isinstance(self.test_only, bool):
            raise TypeError("test_only must be bool")
        if (self.reject or self.disconnect) and not self.test_only:
            raise ValueError("forced rejection/disconnect flags are TEST_ONLY only")

    @property
    def reference(self) -> str:
        return f"{self.policy_id}@{self.version}"


@dataclass(frozen=True, slots=True)
class SimulatedExecutionResult:
    accepted: bool
    reason: str
    client_order_id: str
    intent_id: str
    side: str
    quantity: Decimal
    fill_price: Decimal | None
    quote_sequence: int
    simulated_latency_ms: int
    policy_ref: str

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise TypeError("accepted must be bool")
        object.__setattr__(self, "reason", _text(self.reason, "reason"))
        object.__setattr__(self, "client_order_id", _text(self.client_order_id, "client_order_id"))
        object.__setattr__(self, "intent_id", _text(self.intent_id, "intent_id"))
        side = _text(self.side, "side")
        if side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "quantity", _decimal(self.quantity, "quantity", positive=True))
        if self.fill_price is not None:
            object.__setattr__(self, "fill_price", _decimal(self.fill_price, "fill_price", positive=True))
        object.__setattr__(self, "quote_sequence", _non_negative_int(self.quote_sequence, "quote_sequence"))
        object.__setattr__(self, "simulated_latency_ms", _non_negative_int(self.simulated_latency_ms, "simulated_latency_ms"))
        object.__setattr__(self, "policy_ref", _text(self.policy_ref, "policy_ref"))
        if self.accepted and self.fill_price is None:
            raise ValueError("accepted execution requires fill_price")
        if not self.accepted and self.fill_price is not None:
            raise ValueError("rejected execution must not carry fill_price")


class PaperFillSimulator:
    """Pure deterministic Paper fill engine; no randomness or external I/O."""

    @staticmethod
    def buy_base_price(quote: QuoteSnapshot) -> Decimal:
        if not isinstance(quote, QuoteSnapshot):
            raise TypeError("quote must be QuoteSnapshot")
        return quote.ask

    @staticmethod
    def sell_base_price(quote: QuoteSnapshot) -> Decimal:
        if not isinstance(quote, QuoteSnapshot):
            raise TypeError("quote must be QuoteSnapshot")
        return quote.bid

    def simulate(
        self,
        approved_order: ApprovedOrder,
        quote: QuoteSnapshot,
        policy: FillSimulationPolicy,
        *,
        now: datetime,
    ) -> SimulatedExecutionResult:
        if not isinstance(approved_order, ApprovedOrder):
            raise TypeError("approved_order must be an ApprovedOrder")
        if approved_order.run_mode is not RunMode.PAPER:
            raise ValueError("ApprovedOrder must be PAPER mode")
        if not isinstance(quote, QuoteSnapshot):
            raise TypeError("quote must be QuoteSnapshot")
        if not isinstance(policy, FillSimulationPolicy):
            raise TypeError("policy must be FillSimulationPolicy")
        current = _aware(now, "now")
        intent = approved_order.intent

        def rejected(reason: str) -> SimulatedExecutionResult:
            return SimulatedExecutionResult(
                accepted=False,
                reason=reason,
                client_order_id=approved_order.client_order_id,
                intent_id=approved_order.intent_id,
                side=intent.side,
                quantity=intent.qty,
                fill_price=None,
                quote_sequence=quote.sequence,
                simulated_latency_ms=policy.latency_ms,
                policy_ref=policy.reference,
            )

        if current >= approved_order.expires_at:
            return rejected("ORDER_EXPIRED")
        if quote.observed_at > current:
            return rejected("QUOTE_TIME_INVALID")
        if current - quote.observed_at > timedelta(milliseconds=policy.stale_after_ms):
            return rejected("STALE_QUOTE")
        if policy.disconnect:
            return rejected("DISCONNECTED")
        if policy.reject:
            return rejected("REJECTED_BY_POLICY")

        slip = policy.tick_size * policy.slippage_ticks
        if intent.side == "BUY":
            fill_price = quote.ask + slip
        elif intent.side == "SELL":
            fill_price = quote.bid - slip
        else:  # OrderIntent itself closes this vocabulary; retain fail-closed guard.
            return rejected("UNSUPPORTED_SIDE")
        if fill_price <= 0:
            return rejected("INVALID_FILL_PRICE")

        return SimulatedExecutionResult(
            accepted=True,
            reason="FILLED",
            client_order_id=approved_order.client_order_id,
            intent_id=approved_order.intent_id,
            side=intent.side,
            quantity=intent.qty,
            fill_price=fill_price,
            quote_sequence=quote.sequence,
            simulated_latency_ms=policy.latency_ms,
            policy_ref=policy.reference,
        )


__all__ = [
    "QuoteSnapshot",
    "FillSimulationPolicy",
    "SimulatedExecutionResult",
    "PaperFillSimulator",
]
