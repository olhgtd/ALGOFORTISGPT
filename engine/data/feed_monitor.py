"""Fail-closed live market-data health monitor for AlgoFortis Data V2.

The monitor is an EntryPolicy consumed by RiskGateV2. It does not connect to a
broker, subscribe to a feed, or execute/cancel orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from typing import Iterable

from engine.core.runtime import Clock
from engine.data.live_feed import LiveMarketEvent, MarketState
from engine.data.transports.contracts import TransportHealthState
from engine.data.transports.sequence import SequenceSemantics, SourceSequence


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
    TRANSPORT_DEGRADED = "TRANSPORT_DEGRADED"
    TRANSPORT_FAILED_CLOSED = "TRANSPORT_FAILED_CLOSED"


class _ConnectionState(str, Enum):
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    RESUBSCRIBE_REQUIRED = "RESUBSCRIBE_REQUIRED"


@dataclass(slots=True)
class _InstrumentState:
    last_event: LiveMarketEvent | None = None
    last_source_sequence: SourceSequence | None = None
    latched: set[FeedHealthReason] = field(default_factory=set)


def _token(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FeedMonitorError("instrument_token must be a non-empty string")
    return value.strip()


def _generation(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FeedMonitorError("connection_generation must be a positive integer")
    return value


class FeedMonitor:
    """Track feed health per generation/instrument and fail closed for entries."""

    def __init__(
        self,
        *,
        clock: Clock,
        stale_after: timedelta,
        max_clock_skew: timedelta,
        required_instruments: Iterable[str] | None = None,
    ) -> None:
        if not isinstance(stale_after, timedelta) or stale_after <= timedelta(0):
            raise FeedMonitorError("stale_after must be positive")
        if not isinstance(max_clock_skew, timedelta) or max_clock_skew < timedelta(0):
            raise FeedMonitorError("max_clock_skew must be non-negative")
        if not callable(getattr(clock, "now_utc", None)):
            raise FeedMonitorError("clock must provide now_utc")
        self._clock = clock
        self._stale_after = stale_after
        self._max_clock_skew = max_clock_skew
        self._states: dict[tuple[int, str], _InstrumentState] = {}
        self._active_generation_by_token: dict[str, int] = {}
        self._explicit_required = required_instruments is not None
        self._required_instruments: set[str] = set()
        if required_instruments is not None:
            for item in required_instruments:
                self._required_instruments.add(_token(item))
            if not self._required_instruments:
                raise FeedMonitorError("required_instruments must not be empty when provided")
        self._connection_state = _ConnectionState.CONNECTED
        self._transport_health_state = TransportHealthState.STOPPED

    def observe(
        self,
        event: LiveMarketEvent,
        *,
        connection_generation: int,
        instrument_token: str,
        source_sequence: SourceSequence | None,
    ) -> None:
        if not isinstance(event, LiveMarketEvent):
            raise FeedMonitorError("event must be LiveMarketEvent")
        generation = _generation(connection_generation)
        token = _token(instrument_token)
        if source_sequence is not None and not isinstance(source_sequence, SourceSequence):
            raise FeedMonitorError("source_sequence must be SourceSequence or None")
        if event.source_sequence is not None and source_sequence != event.source_sequence:
            raise FeedMonitorError("event source_sequence disagrees with monitor source_sequence")

        active_generation = self._active_generation_by_token.get(token)
        if active_generation is not None and generation < active_generation:
            raise FeedMonitorError("stale connection generation cannot update feed monitor")
        if active_generation is None or generation > active_generation:
            self._active_generation_by_token[token] = generation

        key = (generation, token)
        state = self._states.setdefault(key, _InstrumentState())
        previous = state.last_source_sequence
        current = source_sequence
        if current is not None and current.semantics is not SequenceSemantics.UNAVAILABLE:
            if previous is not None and previous.semantics is not SequenceSemantics.UNAVAILABLE:
                assert current.value is not None and previous.value is not None
                if current.value <= previous.value:
                    state.latched.add(FeedHealthReason.OUT_OF_ORDER)
                elif (
                    current.semantics is SequenceSemantics.STRICT_CONTIGUOUS
                    and previous.semantics is SequenceSemantics.STRICT_CONTIGUOUS
                    and current.value != previous.value + 1
                ):
                    state.latched.add(FeedHealthReason.SEQUENCE_GAP)
            state.last_source_sequence = current
        elif current is not None:
            state.last_source_sequence = current

        if abs(event.receive_timestamp - event.exchange_timestamp) > self._max_clock_skew:
            state.latched.add(FeedHealthReason.CLOCK_SKEW)

        state.last_event = event
        if not self._explicit_required:
            self._required_instruments.add(token)

    def observe_transport_health(self, state: TransportHealthState) -> None:
        """Consume transport evidence without becoming a second policy authority."""

        if not isinstance(state, TransportHealthState):
            raise FeedMonitorError("state must be TransportHealthState")
        self._transport_health_state = state

    def mark_disconnected(self) -> None:
        self._connection_state = _ConnectionState.RECONNECTING

    def mark_reconnected(self) -> None:
        self._connection_state = _ConnectionState.RESUBSCRIBE_REQUIRED

    def mark_resubscribed(self) -> None:
        self._connection_state = _ConnectionState.CONNECTED

    def reasons_for(self, instrument_token: str) -> tuple[FeedHealthReason, ...]:
        token = _token(instrument_token)
        reasons: set[FeedHealthReason] = set()
        generation = self._active_generation_by_token.get(token)
        if generation is None:
            reasons.add(FeedHealthReason.NO_DATA)
            return tuple(sorted(reasons, key=lambda item: item.value))

        state = self._states[(generation, token)]
        reasons.update(state.latched)
        event = state.last_event
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
    def reasons(self) -> tuple[FeedHealthReason, ...]:
        reasons: set[FeedHealthReason] = set()
        if self._connection_state is _ConnectionState.RECONNECTING:
            reasons.add(FeedHealthReason.RECONNECTING)
        elif self._connection_state is _ConnectionState.RESUBSCRIBE_REQUIRED:
            reasons.add(FeedHealthReason.RESUBSCRIBE_REQUIRED)
        if self._transport_health_state is TransportHealthState.DEGRADED:
            reasons.add(FeedHealthReason.TRANSPORT_DEGRADED)
        elif self._transport_health_state is TransportHealthState.FAILED_CLOSED:
            reasons.add(FeedHealthReason.TRANSPORT_FAILED_CLOSED)

        if not self._required_instruments:
            reasons.add(FeedHealthReason.NO_DATA)
        else:
            for token in self._required_instruments:
                reasons.update(self.reasons_for(token))
        return tuple(sorted(reasons, key=lambda item: item.value))

    @property
    def entries_allowed(self) -> bool:
        return not self.reasons

    @property
    def protective_exits_allowed(self) -> bool:
        # Feed uncertainty must never disable the separate protective-exit path.
        return True


__all__ = ["FeedMonitorError", "FeedHealthReason", "FeedMonitor"]
