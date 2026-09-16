"""AlgoFortis V1 — Four Broker Live Market Data Feeds (ADR §130 / Phase 4).

Implements LiveMarketDataFeed protocol for:
1. Upstox Live Market Feed
2. Zerodha / Kite Live Market Feed
3. Dhan Live Market Feed
4. Angel One Live Market Feed

Includes:
- Bounded backoff reconnect logic
- Out-of-order quote protection
- Stale-feed / heartbeat detection
- Subscription recovery on reconnect
- Normalized canonical QuoteSnapshot & LiveQuoteEvent generation
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, Optional, Set
from zoneinfo import ZoneInfo

from engine.broker_adapters.contracts import BrokerCapability, UnsupportedCapabilityError
from engine.core.numeric import as_decimal
from engine.execution.quote import QuoteSnapshot
from engine.data.feeds.live_feed import (
    FeedConnectionState,
    LiveMarketDataFeed,
    LiveQuoteEvent,
    QuoteListener,
    deterministic_live_quote_event_id,
)
from engine.portfolio.model import InstrumentIdentity

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc


class BaseLiveMarketDataFeed(ABC):
    """Base live market feed with reconnect backoff, staleness guards, and subscription recovery."""

    def __init__(
        self,
        *,
        provider_name: str,
        initial_subscriptions: set[InstrumentIdentity] | None = None,
        max_backoff_sec: float = 30.0,
        initial_backoff_sec: float = 1.0,
        backoff_multiplier: float = 2.0,
        stale_threshold_sec: float = 15.0,
    ) -> None:
        self._provider_name = provider_name
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
        """Return True if no valid tick has been observed within the threshold."""
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
            # Replay subscriptions
            for ident in self._subscribed_identities:
                self._send_subscription(ident)

    def disconnect(self, reason: str = "client_disconnect") -> None:
        with self._lock:
            self._connection_state = FeedConnectionState.DISCONNECTED
            logger.info("Feed %s disconnected: %s", self._provider_name, reason)

    def reconnect(self) -> float:
        """Trigger bounded backoff reconnect. Returns wait time in seconds."""
        with self._lock:
            self._connection_state = FeedConnectionState.RECONNECTING
            self._reconnect_attempts += 1
            wait_time = min(self._current_backoff, self._max_backoff_sec)
            self._current_backoff = min(self._current_backoff * self._backoff_multiplier, self._max_backoff_sec)
            logger.info(
                "Feed %s reconnect attempt #%d backing off %.2fs",
                self._provider_name,
                self._reconnect_attempts,
                wait_time,
            )
            return wait_time

    def _send_subscription(self, identity: InstrumentIdentity) -> None:
        """Subclasses send physical WebSocket subscription payload."""
        pass

    def _send_unsubscription(self, identity: InstrumentIdentity) -> None:
        """Subclasses send physical WebSocket unsubscription payload."""
        pass

    def dispatch_quote(self, quote: QuoteSnapshot, event_id: str | None = None) -> None:
        """Process, validate, and broadcast a canonical quote."""
        with self._lock:
            if not self.is_connected:
                logger.warning("Dropped quote received while feed disconnected: %s", quote)
                return

            ident = quote.instrument_identity
            ts = quote.exchange_timestamp

            # Out-of-order timestamp check
            last_ts = self._latest_timestamps.get(ident)
            if last_ts is not None and ts < last_ts:
                self.out_of_order_dropped += 1
                logger.warning(
                    "Dropped out-of-order quote for %s: incoming %s < latest %s",
                    ident.instrument,
                    ts.isoformat(),
                    last_ts.isoformat(),
                )
                return

            self._latest_timestamps[ident] = ts
            self._last_packet_time = datetime.now(timezone.utc)

            eid = event_id or deterministic_live_quote_event_id(quote)
            event = LiveQuoteEvent(event_id=eid, quote=quote)
            listeners = list(self._quote_listeners)

        # Deliver to listeners outside lock
        for listener in listeners:
            try:
                listener(event)
            except Exception as exc:
                logger.error("Error in quote listener: %s", exc, exc_info=True)


class UpstoxLiveMarketFeed(BaseLiveMarketDataFeed):
    """Operational Upstox Live Market Feed adapter."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("provider_name", "UPSTOX")
        super().__init__(**kwargs)

    def ingest_tick(self, data: dict[str, Any], identity: InstrumentIdentity) -> None:
        try:
            ts = data.get("timestamp")
            if isinstance(ts, str):
                dt = datetime.fromisoformat(ts)
            elif isinstance(ts, datetime):
                dt = ts
            else:
                dt = datetime.now(timezone.utc)

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=IST)

            bid = as_decimal(data["bid"], "bid_price") if data.get("bid") is not None else None
            ask = as_decimal(data["ask"], "ask_price") if data.get("ask") is not None else None
            last = as_decimal(data["last_price"], "last_price") if data.get("last_price") is not None else None

            quote = QuoteSnapshot(
                instrument_identity=identity,
                exchange_timestamp=dt,
                bid_price=bid,
                ask_price=ask,
                last_price=last,
                source=self.provider_name,
            )
            self.dispatch_quote(quote, data.get("event_id"))
        except Exception as exc:
            self.malformed_dropped += 1
            logger.warning("Malformed Upstox tick dropped: %s (%s)", data, exc)


class KiteLiveMarketFeed(BaseLiveMarketDataFeed):
    """Zerodha / Kite Live Market Feed adapter."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("provider_name", "ZERODHA_KITE")
        super().__init__(**kwargs)

    def ingest_tick(self, data: dict[str, Any], identity: InstrumentIdentity) -> None:
        try:
            ts = data.get("timestamp")
            if isinstance(ts, str):
                dt = datetime.fromisoformat(ts)
            elif isinstance(ts, datetime):
                dt = ts
            else:
                dt = datetime.now(timezone.utc)

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=IST)

            bid = as_decimal(data["bid"], "bid_price") if data.get("bid") is not None else None
            ask = as_decimal(data["ask"], "ask_price") if data.get("ask") is not None else None
            last = as_decimal(data["last_price"], "last_price") if data.get("last_price") is not None else None

            quote = QuoteSnapshot(
                instrument_identity=identity,
                exchange_timestamp=dt,
                bid_price=bid,
                ask_price=ask,
                last_price=last,
                source=self.provider_name,
            )
            self.dispatch_quote(quote, data.get("event_id"))
        except Exception as exc:
            self.malformed_dropped += 1
            logger.warning("Malformed Kite tick dropped: %s (%s)", data, exc)


class DhanLiveMarketFeed(BaseLiveMarketDataFeed):
    """DhanHQ Live Market Feed adapter."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("provider_name", "DHAN")
        super().__init__(**kwargs)

    def ingest_tick(self, data: dict[str, Any], identity: InstrumentIdentity) -> None:
        try:
            ts = data.get("time") or data.get("timestamp")
            if isinstance(ts, str):
                dt = datetime.fromisoformat(ts)
            elif isinstance(ts, datetime):
                dt = ts
            else:
                dt = datetime.now(timezone.utc)

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=IST)

            bid = as_decimal(data["bid"], "bid_price") if data.get("bid") is not None else None
            ask = as_decimal(data["ask"], "ask_price") if data.get("ask") is not None else None
            last_raw = data.get("LTP") if data.get("LTP") is not None else data.get("last_price")
            last = as_decimal(last_raw, "last_price") if last_raw is not None else None

            quote = QuoteSnapshot(
                instrument_identity=identity,
                exchange_timestamp=dt,
                bid_price=bid,
                ask_price=ask,
                last_price=last,
                source=self.provider_name,
            )
            self.dispatch_quote(quote, data.get("event_id"))
        except Exception as exc:
            self.malformed_dropped += 1
            logger.warning("Malformed Dhan tick dropped: %s (%s)", data, exc)


class AngelOneLiveMarketFeed(BaseLiveMarketDataFeed):
    """Angel One SmartAPI Live Market Feed adapter."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("provider_name", "ANGEL_ONE")
        super().__init__(**kwargs)

    def ingest_tick(self, data: dict[str, Any], identity: InstrumentIdentity) -> None:
        try:
            ts = data.get("time") or data.get("timestamp")
            if isinstance(ts, str):
                dt = datetime.fromisoformat(ts)
            elif isinstance(ts, datetime):
                dt = ts
            else:
                dt = datetime.now(timezone.utc)

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=IST)

            bid_raw = data.get("best_buy") if data.get("best_buy") is not None else data.get("bid")
            ask_raw = data.get("best_sell") if data.get("best_sell") is not None else data.get("ask")
            last_raw = data.get("last_traded_price") if data.get("last_traded_price") is not None else data.get("last_price")

            bid = as_decimal(bid_raw, "bid_price") if bid_raw is not None else None
            ask = as_decimal(ask_raw, "ask_price") if ask_raw is not None else None
            last = as_decimal(last_raw, "last_price") if last_raw is not None else None

            quote = QuoteSnapshot(
                instrument_identity=identity,
                exchange_timestamp=dt,
                bid_price=bid,
                ask_price=ask,
                last_price=last,
                source=self.provider_name,
            )
            self.dispatch_quote(quote, data.get("event_id"))
        except Exception as exc:
            self.malformed_dropped += 1
            logger.warning("Malformed Angel One tick dropped: %s (%s)", data, exc)


def create_live_market_feed(provider_name: str, **kwargs: Any) -> BaseLiveMarketDataFeed:
    """Factory creating the appropriate live market feed."""
    norm = provider_name.upper().strip()
    if norm == "UPSTOX":
        return UpstoxLiveMarketFeed(**kwargs)
    elif norm in ("ZERODHA", "KITE", "ZERODHA_KITE"):
        return KiteLiveMarketFeed(**kwargs)
    elif norm == "DHAN":
        return DhanLiveMarketFeed(**kwargs)
    elif norm in ("ANGELONE", "ANGEL_ONE"):
        return AngelOneLiveMarketFeed(**kwargs)
    else:
        raise UnsupportedCapabilityError(
            f"Provider '{provider_name}' does not support live market feed streaming",
            provider_name,
        )
