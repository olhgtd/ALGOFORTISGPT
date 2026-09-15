"""Phase 5 Slice 4A — Provider-neutral live quote feed contracts and protocol.

Defines:
- SubscriptionOwnerKey (immutable strategy-version ownership)
- FeedConnectionState (provider-neutral connection health)
- LiveQuoteEvent (transport envelope binding event_id to QuoteSnapshot)
- LiveMarketDataFeed (runtime checkable Protocol)
- Canonical quote fingerprinting helpers
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol, Sequence, runtime_checkable

from engine.execution.quote import QuoteSnapshot
from engine.portfolio.model import InstrumentIdentity
from engine.reproducibility.codec import CanonicalCodec

__all__ = [
    "SubscriptionOwnerKey",
    "FeedConnectionState",
    "LiveQuoteEvent",
    "QuoteListener",
    "LiveMarketDataFeed",
    "quote_payload_fingerprint",
    "deterministic_live_quote_event_id",
]


# ======================================================================
# 1. SubscriptionOwnerKey
# ======================================================================


@dataclass(frozen=True)
class SubscriptionOwnerKey:
    """Immutable strategy identity owning a quote subscription."""

    strategy_id: str
    strategy_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.strategy_id, str) or not self.strategy_id.strip():
            raise ValueError("strategy_id must be a non-empty string")
        if not isinstance(self.strategy_version, str) or not self.strategy_version.strip():
            raise ValueError("strategy_version must be a non-empty string")
        object.__setattr__(self, "strategy_id", self.strategy_id.strip())
        object.__setattr__(self, "strategy_version", self.strategy_version.strip())


# ======================================================================
# 2. FeedConnectionState
# ======================================================================


class FeedConnectionState(str, Enum):
    """Provider-neutral live feed connection state."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"


# ======================================================================
# 3. LiveQuoteEvent
# ======================================================================


@dataclass(frozen=True)
class LiveQuoteEvent:
    """Immutable live quote transport envelope (Layer 1 feed boundary)."""

    event_id: str
    quote: QuoteSnapshot

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, str) or not self.event_id.strip():
            raise ValueError("event_id must be a non-empty string")
        if not isinstance(self.quote, QuoteSnapshot):
            raise TypeError("quote must be a QuoteSnapshot")
        object.__setattr__(self, "event_id", self.event_id.strip())


# ======================================================================
# 4. Canonical Fingerprinting Helpers
# ======================================================================


def _canonical_quote_fields(quote: QuoteSnapshot) -> Sequence[tuple[str, object]]:
    ident = quote.instrument_identity
    return (
        ("market", ident.market),
        ("instrument", ident.instrument),
        ("segment", ident.segment),
        ("underlying", ident.underlying),
        ("expiry", ident.expiry),
        ("strike", ident.strike),
        ("option_type", ident.option_type),
        ("exchange_timestamp", quote.exchange_timestamp),
        ("bid_price", quote.bid_price),
        ("ask_price", quote.ask_price),
        ("bid_quantity", quote.bid_quantity),
        ("ask_quantity", quote.ask_quantity),
        ("last_price", quote.last_price),
        ("source", quote.source),
    )


def quote_payload_fingerprint(quote: QuoteSnapshot) -> str:
    """Deterministic canonical fingerprint of normalized QuoteSnapshot evidence."""
    if not isinstance(quote, QuoteSnapshot):
        raise TypeError("quote must be a QuoteSnapshot")
    return CanonicalCodec.fingerprint(
        "sentinelx-quote-payload/v1",
        _canonical_quote_fields(quote),
    )


def deterministic_live_quote_event_id(quote: QuoteSnapshot) -> str:
    """Fallback deterministic event_id when provider supplies no native sequence ID."""
    if not isinstance(quote, QuoteSnapshot):
        raise TypeError("quote must be a QuoteSnapshot")
    return CanonicalCodec.fingerprint(
        "sentinelx-live-quote/v1",
        _canonical_quote_fields(quote),
    )


# ======================================================================
# 5. LiveMarketDataFeed Protocol
# ======================================================================


QuoteListener = Callable[[LiveQuoteEvent], None]


@runtime_checkable
class LiveMarketDataFeed(Protocol):
    """Provider-neutral live market data feed boundary."""

    def subscribe(self, identity: InstrumentIdentity) -> None:
        """Request live market data / quote subscription for an instrument."""
        ...

    def unsubscribe(self, identity: InstrumentIdentity) -> None:
        """Release live market data / quote subscription for an instrument."""
        ...

    def active_subscriptions(self) -> frozenset[InstrumentIdentity]:
        """Return all currently active subscribed instruments."""
        ...

    @property
    def connection_state(self) -> FeedConnectionState:
        """Return canonical live connection state."""
        ...

    @property
    def is_connected(self) -> bool:
        """Return True if live connection is active and operational."""
        ...

    def add_quote_listener(self, listener: QuoteListener) -> None:
        """Register a synchronous listener to receive incoming LiveQuoteEvents."""
        ...

    def remove_quote_listener(self, listener: QuoteListener) -> None:
        """Unregister a previously registered quote listener."""
        ...
