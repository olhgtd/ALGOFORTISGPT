"""Legacy feed wrappers plus pure broker quote normalizers.

Phase-6 architecture rule:
- pure normalizers translate broker payloads -> QuoteSnapshot only;
- shared ``engine.data.transports`` runtime owns reconnect, heartbeat,
  generation fencing, backpressure and subscription replay;
- legacy feed wrappers remain for compatibility and delegate parsing to the
  pure normalizers, but they are not the new Phase-6 transport authority.
"""

from __future__ import annotations

import logging
import threading
from abc import ABC
from datetime import datetime, timezone
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from engine.broker_adapters.contracts import UnsupportedCapabilityError
from engine.core.numeric import as_decimal
from engine.data.feeds.live_feed import (
    FeedConnectionState,
    LiveMarketDataFeed,
    LiveQuoteEvent,
    LiveQuoteTransportMetadata,
    QuoteListener,
    deterministic_live_quote_event_id,
)
from engine.execution.quote import QuoteSnapshot
from engine.portfolio.model import InstrumentIdentity

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc


def _exchange_timestamp(data: dict[str, Any], *keys: str) -> datetime:
    value: object | None = None
    for key in keys:
        if data.get(key) is not None:
            value = data.get(key)
            break
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
    elif isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    return parsed


class BrokerQuoteNormalizer(Protocol):
    """Pure provider-edge payload normalizer with no transport authority."""

    provider_name: str

    def normalize(self, data: dict[str, Any], identity: InstrumentIdentity) -> QuoteSnapshot: ...


class UpstoxQuoteNormalizer:
    provider_name = "UPSTOX"

    def normalize(self, data: dict[str, Any], identity: InstrumentIdentity) -> QuoteSnapshot:
        dt = _exchange_timestamp(data, "timestamp")
        bid = as_decimal(data["bid"], "bid_price") if data.get("bid") is not None else None
        ask = as_decimal(data["ask"], "ask_price") if data.get("ask") is not None else None
        last = as_decimal(data["last_price"], "last_price") if data.get("last_price") is not None else None
        return QuoteSnapshot(
            instrument_identity=identity,
            exchange_timestamp=dt,
            bid_price=bid,
            ask_price=ask,
            last_price=last,
            source=self.provider_name,
        )


class KiteQuoteNormalizer:
    provider_name = "ZERODHA_KITE"

    def normalize(self, data: dict[str, Any], identity: InstrumentIdentity) -> QuoteSnapshot:
        dt = _exchange_timestamp(data, "timestamp")
        bid = as_decimal(data["bid"], "bid_price") if data.get("bid") is not None else None
        ask = as_decimal(data["ask"], "ask_price") if data.get("ask") is not None else None
        last = as_decimal(data["last_price"], "last_price") if data.get("last_price") is not None else None
        return QuoteSnapshot(
            instrument_identity=identity,
            exchange_timestamp=dt,
            bid_price=bid,
            ask_price=ask,
            last_price=last,
            source=self.provider_name,
        )


class DhanQuoteNormalizer:
    provider_name = "DHAN"

    def normalize(self, data: dict[str, Any], identity: InstrumentIdentity) -> QuoteSnapshot:
        dt = _exchange_timestamp(data, "time", "timestamp")
        bid = as_decimal(data["bid"], "bid_price") if data.get("bid") is not None else None
        ask = as_decimal(data["ask"], "ask_price") if data.get("ask") is not None else None
        last_raw = data.get("LTP") if data.get("LTP") is not None else data.get("last_price")
        last = as_decimal(last_raw, "last_price") if last_raw is not None else None
        return QuoteSnapshot(
            instrument_identity=identity,
            exchange_timestamp=dt,
            bid_price=bid,
            ask_price=ask,
            last_price=last,
            source=self.provider_name,
        )


class AngelOneQuoteNormalizer:
    provider_name = "ANGEL_ONE"

    def normalize(self, data: dict[str, Any], identity: InstrumentIdentity) -> QuoteSnapshot:
        dt = _exchange_timestamp(data, "time", "timestamp")
        bid_raw = data.get("best_buy") if data.get("best_buy") is not None else data.get("bid")
        ask_raw = data.get("best_sell") if data.get("best_sell") is not None else data.get("ask")
        last_raw = data.get("last_traded_price") if data.get("last_traded_price") is not None else data.get("last_price")
        bid = as_decimal(bid_raw, "bid_price") if bid_raw is not None else None
        ask = as_decimal(ask_raw, "ask_price") if ask_raw is not None else None
        last = as_decimal(last_raw, "last_price") if last_raw is not None else None
        return QuoteSnapshot(
            instrument_identity=identity,
            exchange_timestamp=dt,
            bid_price=bid,
            ask_price=ask,
            last_price=last,
            source=self.provider_name,
        )


class BaseLiveMarketDataFeed(ABC):
    """Legacy compatibility wrapper around pure broker quote normalizers.

    This class predates the Phase-6 shared transport runtime. New Phase-6
    drivers must not use its reconnect/backoff methods as authoritative
    transport lifecycle; those responsibilities live in
    ``MarketDataTransportRuntime``.
    """

    normalizer: BrokerQuoteNormalizer

    def __init__(
        self,
        *,
        provider_name: str,
        normalizer: BrokerQuoteNormalizer,
        initial_subscriptions: set[InstrumentIdentity] | None = None,
        max_backoff_sec: float = 30.0,
        initial_backoff_sec: float = 1.0,
        backoff_multiplier: float = 2.0,
        stale_threshold_sec: float = 15.0,
    ) -> None:
        self._provider_name = provider_name
        self.normalizer = normalizer
        self._subscribed_identities: set[InstrumentIdentity] = set(initial_subscriptions or set())
        self._quote_listeners: list[QuoteListener] = []
        self._connection_state = FeedConnectionState.DISCONNECTED
        self._lock = threading.RLock()
        self._latest_timestamps: dict[InstrumentIdentity, datetime] = {}
        self._last_packet_time: datetime | None = None
        self._max_backoff_sec = max_backoff_sec
        self._initial_backoff_sec = initial_backoff_sec
        self._backoff_multiplier = backoff_multiplier
        self._current_backoff = initial_backoff_sec
        self._reconnect_attempts = 0
        self._stale_threshold_sec = stale_threshold_sec
        self.out_of_order_dropped = 0
        self.malformed_dropped = 0

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def connection_state(self) -> FeedConnectionState:
        with self._lock:
            return self._connection_state

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._connection_state == FeedConnectionState.CONNECTED

    @property
    def last_packet_time(self) -> datetime | None:
        with self._lock:
            return self._last_packet_time

    def is_stale(self, max_age_sec: float | None = None) -> bool:
        threshold = max_age_sec or self._stale_threshold_sec
        with self._lock:
            if not self.is_connected or self._last_packet_time is None:
                return True
            age = (datetime.now(timezone.utc) - self._last_packet_time).total_seconds()
            return age > threshold

    def subscribe(self, identity: InstrumentIdentity) -> None:
        if not isinstance(identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")
        with self._lock:
            self._subscribed_identities.add(identity)
            if self.is_connected:
                self._send_subscription(identity)

    def unsubscribe(self, identity: InstrumentIdentity) -> None:
        if not isinstance(identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")
        with self._lock:
            self._subscribed_identities.discard(identity)
            self._latest_timestamps.pop(identity, None)
            if self.is_connected:
                self._send_unsubscription(identity)

    def active_subscriptions(self) -> frozenset[InstrumentIdentity]:
        with self._lock:
            return frozenset(self._subscribed_identities)

    def add_quote_listener(self, listener: QuoteListener) -> None:
        if not callable(listener):
            raise TypeError("listener must be callable")
        with self._lock:
            if listener not in self._quote_listeners:
                self._quote_listeners.append(listener)

    def remove_quote_listener(self, listener: QuoteListener) -> None:
        with self._lock:
            if listener in self._quote_listeners:
                self._quote_listeners.remove(listener)

    def connect(self) -> None:
        with self._lock:
            self._connection_state = FeedConnectionState.CONNECTED
            self._reconnect_attempts = 0
            self._current_backoff = self._initial_backoff_sec
            self._last_packet_time = datetime.now(timezone.utc)
            for ident in self._subscribed_identities:
                self._send_subscription(ident)

    def disconnect(self, reason: str = "client_disconnect") -> None:
        with self._lock:
            self._connection_state = FeedConnectionState.DISCONNECTED
            logger.info("Feed %s disconnected: %s", self._provider_name, reason)

    def reconnect(self) -> float:
        """Legacy compatibility only; Phase-6 runtime owns real reconnect."""
        with self._lock:
            self._connection_state = FeedConnectionState.RECONNECTING
            self._reconnect_attempts += 1
            wait_time = min(self._current_backoff, self._max_backoff_sec)
            self._current_backoff = min(self._current_backoff * self._backoff_multiplier, self._max_backoff_sec)
            return wait_time

    def _send_subscription(self, identity: InstrumentIdentity) -> None:
        """Legacy no-op compatibility seam; Phase-6 driver encodes subscriptions."""

    def _send_unsubscription(self, identity: InstrumentIdentity) -> None:
        """Legacy no-op compatibility seam; Phase-6 driver encodes unsubscriptions."""

    def dispatch_quote(
        self,
        quote: QuoteSnapshot,
        event_id: str | None = None,
        *,
        transport_metadata: LiveQuoteTransportMetadata | None = None,
    ) -> None:
        with self._lock:
            if not self.is_connected:
                logger.warning("Dropped quote received while feed disconnected: %s", quote)
                return
            ident = quote.instrument_identity
            ts = quote.exchange_timestamp
            last_ts = self._latest_timestamps.get(ident)
            if last_ts is not None and ts < last_ts:
                self.out_of_order_dropped += 1
                return
            self._latest_timestamps[ident] = ts
            self._last_packet_time = datetime.now(timezone.utc)
            eid = event_id or deterministic_live_quote_event_id(quote)
            event = LiveQuoteEvent(
                event_id=eid,
                quote=quote,
                transport_metadata=transport_metadata,
            )
            listeners = list(self._quote_listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception as exc:
                logger.error("Error in quote listener: %s", exc, exc_info=True)

    def ingest_tick(
        self,
        data: dict[str, Any],
        identity: InstrumentIdentity,
        *,
        transport_metadata: LiveQuoteTransportMetadata | None = None,
    ) -> None:
        try:
            quote = self.normalizer.normalize(data, identity)
            self.dispatch_quote(
                quote,
                data.get("event_id"),
                transport_metadata=transport_metadata,
            )
        except Exception as exc:
            self.malformed_dropped += 1
            logger.warning("Malformed %s tick dropped: %s (%s)", self.provider_name, data, exc)


class UpstoxLiveMarketFeed(BaseLiveMarketDataFeed):
    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("provider_name", "UPSTOX")
        kwargs.setdefault("normalizer", UpstoxQuoteNormalizer())
        super().__init__(**kwargs)


class KiteLiveMarketFeed(BaseLiveMarketDataFeed):
    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("provider_name", "ZERODHA_KITE")
        kwargs.setdefault("normalizer", KiteQuoteNormalizer())
        super().__init__(**kwargs)


class DhanLiveMarketFeed(BaseLiveMarketDataFeed):
    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("provider_name", "DHAN")
        kwargs.setdefault("normalizer", DhanQuoteNormalizer())
        super().__init__(**kwargs)


class AngelOneLiveMarketFeed(BaseLiveMarketDataFeed):
    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("provider_name", "ANGEL_ONE")
        kwargs.setdefault("normalizer", AngelOneQuoteNormalizer())
        super().__init__(**kwargs)


def create_live_market_feed(provider_name: str, **kwargs: Any) -> BaseLiveMarketDataFeed:
    norm = provider_name.upper().strip()
    if norm == "UPSTOX":
        return UpstoxLiveMarketFeed(**kwargs)
    if norm in ("ZERODHA", "KITE", "ZERODHA_KITE"):
        return KiteLiveMarketFeed(**kwargs)
    if norm == "DHAN":
        return DhanLiveMarketFeed(**kwargs)
    if norm in ("ANGELONE", "ANGEL_ONE"):
        return AngelOneLiveMarketFeed(**kwargs)
    raise UnsupportedCapabilityError(
        f"Provider '{provider_name}' does not support live market feed streaming",
        provider_name,
    )


__all__ = [
    "BrokerQuoteNormalizer",
    "UpstoxQuoteNormalizer",
    "KiteQuoteNormalizer",
    "DhanQuoteNormalizer",
    "AngelOneQuoteNormalizer",
    "BaseLiveMarketDataFeed",
    "UpstoxLiveMarketFeed",
    "KiteLiveMarketFeed",
    "DhanLiveMarketFeed",
    "AngelOneLiveMarketFeed",
    "create_live_market_feed",
]
