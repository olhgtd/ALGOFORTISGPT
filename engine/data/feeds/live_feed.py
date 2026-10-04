"""Phase 5 Slice 4A — Provider-neutral live quote feed contracts and protocol.

Defines:
- SubscriptionOwnerKey (immutable strategy-version ownership)
- FeedConnectionState (legacy provider-neutral connection health)
- LiveQuoteTransportMetadata (Phase-6 transport evidence carried with quotes)
- LiveQuoteEvent (normalized quote plus optional transport evidence)
- LiveMarketDataFeed (runtime checkable Protocol)
- Canonical quote fingerprinting helpers

Phase-6 note: reconnect/heartbeat/generation authority belongs to the shared
market-data transport runtime. ``FeedConnectionState`` remains only for legacy
feed-wrapper compatibility and is not the Phase-6 transport state machine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Protocol, Sequence, runtime_checkable

from engine.data.transports.sequence import SourceSequence
from engine.execution.quote import QuoteSnapshot
from engine.portfolio.model import InstrumentIdentity
from engine.reproducibility.codec import CanonicalCodec

__all__ = [
    "SubscriptionOwnerKey",
    "FeedConnectionState",
    "LiveQuoteTransportMetadata",
    "LiveQuoteEvent",
    "QuoteListener",
    "LiveMarketDataFeed",
    "quote_payload_fingerprint",
    "deterministic_live_quote_event_id",
]


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


class FeedConnectionState(str, Enum):
    """Legacy provider-neutral live feed connection state."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"


def _aware_datetime(value: object, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class LiveQuoteTransportMetadata:
    """Read-only Phase-6 transport evidence attached to a normalized quote.

    This carries no connection lifecycle or policy authority. It exists only so
    provider-native generation/token/sequence evidence survives normalization
    and can be consumed by the central Data-V2 bridge/FeedMonitor path.
    """

    connection_generation: int
    instrument_token: str
    receive_timestamp: datetime
    source_sequence: SourceSequence | None = None

    def __post_init__(self) -> None:
        generation = self.connection_generation
        if isinstance(generation, bool) or not isinstance(generation, int) or generation <= 0:
            raise ValueError("connection_generation must be a positive integer")
        if not isinstance(self.instrument_token, str) or not self.instrument_token.strip():
            raise ValueError("instrument_token must be a non-empty string")
        object.__setattr__(self, "instrument_token", self.instrument_token.strip())
        object.__setattr__(
            self,
            "receive_timestamp",
            _aware_datetime(self.receive_timestamp, "receive_timestamp"),
        )
        if self.source_sequence is not None and not isinstance(self.source_sequence, SourceSequence):
            raise TypeError("source_sequence must be SourceSequence or None")


@dataclass(frozen=True)
class LiveQuoteEvent:
    """Immutable normalized live quote with optional Phase-6 transport evidence."""

    event_id: str
    quote: QuoteSnapshot
    transport_metadata: LiveQuoteTransportMetadata | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, str) or not self.event_id.strip():
            raise ValueError("event_id must be a non-empty string")
        if not isinstance(self.quote, QuoteSnapshot):
            raise TypeError("quote must be a QuoteSnapshot")
        if self.transport_metadata is not None and not isinstance(
            self.transport_metadata, LiveQuoteTransportMetadata
        ):
            raise TypeError("transport_metadata must be LiveQuoteTransportMetadata or None")
        object.__setattr__(self, "event_id", self.event_id.strip())


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
        "algofortis-quote-payload/v1",
        _canonical_quote_fields(quote),
    )


def deterministic_live_quote_event_id(quote: QuoteSnapshot) -> str:
    """Fallback deterministic event_id when provider supplies no native sequence ID."""
    if not isinstance(quote, QuoteSnapshot):
        raise TypeError("quote must be a QuoteSnapshot")
    return CanonicalCodec.fingerprint(
        "algofortis-live-quote/v1",
        _canonical_quote_fields(quote),
    )


QuoteListener = Callable[[LiveQuoteEvent], None]


@runtime_checkable
class LiveMarketDataFeed(Protocol):
    """Provider-neutral legacy live market data feed boundary."""

    def subscribe(self, identity: InstrumentIdentity) -> None: ...

    def unsubscribe(self, identity: InstrumentIdentity) -> None: ...

    def active_subscriptions(self) -> frozenset[InstrumentIdentity]: ...

    @property
    def connection_state(self) -> FeedConnectionState: ...

    @property
    def is_connected(self) -> bool: ...

    def add_quote_listener(self, listener: QuoteListener) -> None: ...

    def remove_quote_listener(self, listener: QuoteListener) -> None: ...
