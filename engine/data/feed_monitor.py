"""Fail-closed live market-data health monitor for AlgoFortis Data V2.

The monitor is an EntryPolicy consumed by RiskGateV2. It does not connect to a
broker, subscribe to a feed, or execute/cancel orders.
"""

from __future__ import annotations

from datetime import timedelta
from enum import Enum

from engine.core.runtime import Clock
from engine.data.live_feed import LiveMarketEvent, MarketState


class FeedMonitorError(ValueError):
    """Raised when monitor configuration or input is invalid."""


class FeedHealthReason(str, Enum):
    NO_DATA = "NO_DATA"
    STALE = "STALE"
    SEQUENCE_GAP = "SEQUENCE_GAP"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    CLOCK_SKEW = "CLOCK_SKEW"
    MARKET_CLOSED = "MARKET_CLOSED"
    MARKET_HALTED = "MARKET_HALTED"
    RECONNECTING = "RECONNECTING"
    RESUBSCRIBE_REQUIRED = "RESUBSCRIBE_REQUIRED"


class _ConnectionState(str, Enum):
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    RESUBSCRIBE_REQUIRED = "RESUBSCRIBE_REQUIRED"


class FeedMonitor:
    """Track feed health and expose a narrow fail-closed entry-policy seam."""

    def __init__(self, *, clock: Clock, stale_after: timedelta, max_clock_skew: timedelta) -> None:
        if not isinstance(stale_after, timedelta) or stale_after <= timedelta(0):
            raise FeedMonitorError("stale_after must be positive")
        if not isinstance(max_clock_skew, timedelta) or max_clock_skew < timedelta(0):
            raise FeedMonitorError("max_clock_skew must be non-negative")
        if not callable(getattr(clock, "now_utc", None)):
            raise FeedMonitorError("clock must provide now_utc")
        self._clock = clock
        self._stale_after = stale_after
        self._max_clock_skew = max_clock_skew
        self._last_event: LiveMarketEvent | None = None
        self._last_sequence: int | None = None
        self._latched: set[FeedHealthReason] = set()
        self._connection_state = _ConnectionState.CONNECTED

    def observe(self, event: LiveMarketEvent) -> None:
        if not isinstance(event, LiveMarketEvent):
            raise FeedMonitorError("event must be LiveMarketEvent")

        if self._last_sequence is not None:
            if event.sequence <= self._last_sequence:
                self._latched.add(FeedHealthReason.OUT_OF_ORDER)
            elif event.sequence != self._last_sequence + 1:
                self._latched.add(FeedHealthReason.SEQUENCE_GAP)

        if abs(event.receive_timestamp - event.exchange_timestamp) > self._max_clock_skew:
            self._latched.add(FeedHealthReason.CLOCK_SKEW)

        self._last_sequence = event.sequence
        self._last_event = event

    def mark_disconnected(self) -> None:
        self._connection_state = _ConnectionState.RECONNECTING

    def mark_reconnected(self) -> None:
        self._connection_state = _ConnectionState.RESUBSCRIBE_REQUIRED

    def mark_resubscribed(self) -> None:
        self._connection_state = _ConnectionState.CONNECTED
        # A completed resubscription is the explicit recovery point for transport
        # uncertainty. Persistent data-integrity faults remain latched.

    @property
    def reasons(self) -> tuple[FeedHealthReason, ...]:
        reasons = set(self._latched)

        if self._connection_state is _ConnectionState.RECONNECTING:
            reasons.add(FeedHealthReason.RECONNECTING)
        elif self._connection_state is _ConnectionState.RESUBSCRIBE_REQUIRED:
            reasons.add(FeedHealthReason.RESUBSCRIBE_REQUIRED)

        event = self._last_event
        if event is None:
            reasons.add(FeedHealthReason.NO_DATA)
        else:
            now = self._clock.now_utc()
            if now - event.receive_timestamp > self._stale_after:
                reasons.add(FeedHealthReason.STALE)
            if event.market_state is MarketState.CLOSED:
                reasons.add(FeedHealthReason.MARKET_CLOSED)
            elif event.market_state is MarketState.HALTED:
                reasons.add(FeedHealthReason.MARKET_HALTED)

        return tuple(sorted(reasons, key=lambda item: item.value))

    @property
    def entries_allowed(self) -> bool:
        return not self.reasons

    @property
    def protective_exits_allowed(self) -> bool:
        # Feed uncertainty must never disable the separate protective-exit path.
        return True


__all__ = ["FeedMonitorError", "FeedHealthReason", "FeedMonitor"]
