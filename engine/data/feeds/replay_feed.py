"""Historical replay feed for Phase 5 paper trading.

Implements the DataFeed contract (engine.data.feeds.base.DataFeed) by replaying
historical OHLCV data from a source DataFrame through a controlled
replay cursor.  The replay cursor uses authoritative historical timestamps;
wall-clock time is never used to define market time.

Frozen contracts:
  - §80 (D1): DataFeed live compatibility boundary.
  - §82 (D3): calendar/event-time-based completed bars.
  - §83 (D3a): no synthetic bars for missing intervals.

No wall-clock sleeping or real-time pacing is required for this slice.
Deterministic replay correctness is the priority.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional, Sequence

import pandas as pd

from engine.data.feeds.base import DataFeed
from engine.data.feeds.data_cleaning import invalid_ohlcv_mask, normalize_timestamps
from engine.data.feeds.live_feed import (
    FeedConnectionState,
    LiveMarketDataFeed,
    LiveQuoteEvent,
    QuoteListener,
)
from engine.portfolio.model import InstrumentIdentity

logger = logging.getLogger(__name__)

OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


class HistoricalReplayFeed(DataFeed):
    """DataFeed implementation that replays historical data through a cursor.

    The feed is initialized with a source DataFrame for one instrument/
    timeframe combination.  The cursor tracks how much of the source data
    has been "emitted" so far.  Each call to ``fetch`` returns only the
    bars that have been advanced past the cursor, preserving authoritative
    source timestamps.

    Replay semantics:
      - The cursor starts at position 0 (no data emitted).
      - ``advance_to(index)`` moves the cursor to the given 0-based
        position in the sorted source data.  Bars up to (but not
        including) that position become available via ``fetch``.
      - ``fetch(instrument, timeframe)`` returns all bars from the
        beginning of the source up to the current cursor position.
        This matches the HistoricalDataFeed contract: ``fetch`` returns
        the complete legally-available history as of the replay point.
      - The source data is sorted by timestamp once at initialization.
        Bars cannot be reordered.
      - No synthetic bars are created for missing intervals.
      - No look-ahead: bars beyond the cursor are unavailable.
      - Identical source data + identical advance sequence produces
        identical fetch output (deterministic replay).
    """

    def __init__(self, source: pd.DataFrame) -> None:
        """Initialize the replay feed from a source DataFrame.

        Parameters
        ----------
        source : DataFrame
            Historical OHLCV data.  Must contain at minimum the six
            OHLCV columns.  Timestamps may be naive (will be normalized)
            or timezone-aware.  The source is deep-copied; mutations to
            the original after construction have no effect.
        """
        if not isinstance(source, pd.DataFrame):
            raise TypeError("source must be a pandas DataFrame")

        df = source.copy(deep=True)

        for col in OHLCV_COLUMNS:
            if col not in df.columns:
                raise ValueError(f"source DataFrame missing required column: {col!r}")

        # Normalize timestamps to timezone-aware (same as HistoricalDataFeed).
        normalize_timestamps(df)

        # Sort by timestamp to guarantee deterministic ordering.
        df = df.sort_values("timestamp").reset_index(drop=True)

        # Reject invalid OHLCV rows (same cleaning as HistoricalDataFeed).
        invalid = invalid_ohlcv_mask(df)
        if invalid.any():
            logger.info(
                "HistoricalReplayFeed: rejected %d invalid OHLCV row(s).",
                invalid.sum(),
            )
            df = df.loc[~invalid].reset_index(drop=True)

        self._source: pd.DataFrame = df[OHLCV_COLUMNS]
        self._cursor: int = 0

    @property
    def total_bars(self) -> int:
        """Total number of valid bars in the source data."""
        return len(self._source)

    @property
    def cursor(self) -> int:
        """Current replay cursor position (number of bars available)."""
        return self._cursor

    def advance_to(self, index: int) -> None:
        """Move the replay cursor to the given 0-based position.

        After this call, ``fetch`` will return bars at positions
        ``[0, index)`` — i.e., the first *index* bars from the sorted
        source data.

        Parameters
        ----------
        index : int
            Target cursor position.  Must be non-negative.  Values
            exceeding ``total_bars`` are clamped to ``total_bars``.
            Values equal to the current cursor are a no-op.
            Values less than the current cursor are a programming
            error (replay does not move backward in market time).

        Raises
        ------
        ValueError
            If *index* is less than the current cursor (backward
            replay is not permitted).
        """
        if not isinstance(index, int) or isinstance(index, bool):
            raise TypeError("index must be an integer")
        if index < 0:
            raise ValueError("index must be non-negative")
        if index < self._cursor:
            raise ValueError(
                f"cannot advance cursor backward: "
                f"current={self._cursor}, requested={index}"
            )
        clamped = min(index, self.total_bars)
        if clamped != self._cursor:
            self._cursor = clamped

    def fetch(self, instrument: str, timeframe: str) -> pd.DataFrame:
        """Fetch all legally-available bars up to the current cursor.

        This returns the same OHLCV columns and DataFrame shape as
        ``HistoricalDataFeed.fetch`` — the DataFeed contract boundary.
        The ``instrument`` and ``timeframe`` parameters are accepted
        for contract compatibility but the replay feed serves whatever
        data it was initialized with (single-stream, matching the
        HistoricalDataFeed model).

        Returns an empty DataFrame (with correct columns) if the cursor
        is at position 0.
        """
        if self._cursor == 0:
            return pd.DataFrame(columns=OHLCV_COLUMNS)
        return self._source.iloc[: self._cursor].copy()

    def available_bars(self) -> int:
        """Number of bars currently available via fetch."""
        return self._cursor

    def remaining_bars(self) -> int:
        """Number of bars not yet emitted."""
        return self.total_bars - self._cursor

    def latest_timestamp(self) -> Optional[pd.Timestamp]:
        """Authoritative market timestamp of the most recently emitted bar.

        Returns None if no bars have been emitted (cursor == 0).
        """
        if self._cursor == 0:
            return None
        return self._source.iloc[self._cursor - 1]["timestamp"]

    def __repr__(self) -> str:
        return (
            f"HistoricalReplayFeed(bars={self.total_bars}, "
            f"cursor={self._cursor}, remaining={self.total_bars - self._cursor})"
        )


# ======================================================================
# ReplayLiveMarketFeed — Synchronous LiveMarketDataFeed for Full Pipeline Replay
# ======================================================================

StateListener = Callable[[FeedConnectionState], None]


class ReplayLiveMarketFeed(LiveMarketDataFeed):
    """Synchronous deterministic implementation of LiveMarketDataFeed for replay.

    Enforces:
    - Zero network calls / zero external I/O.
    - Synchronous deterministic quote dispatching to registered listeners.
    - Subscription causality: quotes are dispatched ONLY for actively subscribed instruments.
    - Connection state tracking and notification to state listeners.
    """

    def __init__(
        self,
        initial_state: FeedConnectionState = FeedConnectionState.CONNECTED,
    ) -> None:
        if not isinstance(initial_state, FeedConnectionState):
            raise TypeError("initial_state must be a FeedConnectionState")
        self._state: FeedConnectionState = initial_state
        self._subscriptions: set[InstrumentIdentity] = set()
        self._quote_listeners: list[QuoteListener] = []
        self._state_listeners: list[StateListener] = []

    @property
    def connection_state(self) -> FeedConnectionState:
        """Return canonical connection state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Return True if and only if connection state is CONNECTED."""
        return self._state == FeedConnectionState.CONNECTED

    def subscribe(self, identity: InstrumentIdentity) -> None:
        """Subscribe to live market data / quotes for an instrument."""
        if not isinstance(identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")
        self._subscriptions.add(identity)

    def unsubscribe(self, identity: InstrumentIdentity) -> None:
        """Unsubscribe from live market data / quotes for an instrument."""
        if not isinstance(identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")
        self._subscriptions.discard(identity)

    def active_subscriptions(self) -> frozenset[InstrumentIdentity]:
        """Return immutable set of active subscribed instruments."""
        return frozenset(self._subscriptions)

    def is_subscribed(self, identity: InstrumentIdentity) -> bool:
        """Check if an instrument identity is currently subscribed."""
        if not isinstance(identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")
        return identity in self._subscriptions

    def add_quote_listener(self, listener: QuoteListener) -> None:
        """Register a synchronous listener to receive incoming LiveQuoteEvents."""
        if not callable(listener):
            raise TypeError("listener must be callable")
        if listener not in self._quote_listeners:
            self._quote_listeners.append(listener)

    def remove_quote_listener(self, listener: QuoteListener) -> None:
        """Unregister a quote listener."""
        if listener in self._quote_listeners:
            self._quote_listeners.remove(listener)

    def add_state_listener(self, listener: StateListener) -> None:
        """Register a synchronous listener to receive FeedConnectionState changes."""
        if not callable(listener):
            raise TypeError("listener must be callable")
        if listener not in self._state_listeners:
            self._state_listeners.append(listener)

    def remove_state_listener(self, listener: StateListener) -> None:
        """Unregister a state listener."""
        if listener in self._state_listeners:
            self._state_listeners.remove(listener)

    def set_connection_state(self, state: FeedConnectionState) -> None:
        """Transition feed connection state and notify registered state listeners."""
        if not isinstance(state, FeedConnectionState):
            raise TypeError("state must be a FeedConnectionState")
        self._state = state
        for listener in list(self._state_listeners):
            listener(state)

    def dispatch_quote(self, event: LiveQuoteEvent) -> bool:
        """Dispatch a LiveQuoteEvent to registered listeners if instrument is subscribed.

        Returns True if the quote was dispatched to listeners, False if suppressed
        because the instrument is not currently subscribed (enforcing causality).
        """
        if not isinstance(event, LiveQuoteEvent):
            raise TypeError("event must be a LiveQuoteEvent")
        ident = event.quote.instrument_identity
        if ident not in self._subscriptions:
            return False
        for listener in list(self._quote_listeners):
            listener(event)
        return True

