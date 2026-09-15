"""Phase 5 Slice 4C-2 — Provider-neutral live market events, market-time advancement,
and deterministic tick-to-bar / provider-bar aggregation.

Defines:
- IngestionMode
- LiveTradeTick
- LiveProviderBar
- MarketTimeEvent
- DataGapEvidence
- LiveBarBuilderResult
- LiveBarBuilder
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from typing import Mapping
import re

from engine.backtest.engine import BarEvent
from engine.market.data import BoundBarEvent, StreamKey
from engine.market.profile import MarketSessionBoundary
from engine.core.numeric import as_decimal
from engine.portfolio.model import InstrumentIdentity

__all__ = [
    "IngestionMode",
    "LiveTradeTick",
    "LiveProviderBar",
    "MarketTimeEvent",
    "StreamIngestionModeMismatchError",
    "AmbiguousSameTimestampTickError",
    "DataGapEvidence",
    "LiveBarBuilderResult",
    "LiveBarBuilder",
]


# ======================================================================
# Helpers
# ======================================================================

_TIMEFRAME_RE = re.compile(r"^(\d+)(m|h|d)$")

# Timeframes whose minute-granularity evenly divides into 60 are safe for
# epoch-aligned floor because they also align to any session-open on a
# minute boundary. Others (e.g. 30m) may NOT align to session open and
# require session-relative alignment.
_EPOCH_SAFE_MINUTES = frozenset({1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 60})


def _timeframe_duration(timeframe: str) -> timedelta:
    match = _TIMEFRAME_RE.fullmatch(timeframe)
    if match is None:
        raise ValueError(f"invalid timeframe: {timeframe!r}")
    quantity, unit = match.groups()
    amount = int(quantity)
    if amount <= 0:
        raise ValueError("timeframe duration must be positive")
    return timedelta(minutes=amount * {"m": 1, "h": 60, "d": 1_440}[unit])


def _timeframe_minutes(timeframe: str) -> int:
    return int(_timeframe_duration(timeframe).total_seconds() / 60)


def _is_epoch_safe(timeframe: str) -> bool:
    """Return True if epoch-aligned floor produces correct session-relative intervals."""
    minutes = _timeframe_minutes(timeframe)
    return minutes in _EPOCH_SAFE_MINUTES


def _require_aware(ts: datetime, name: str) -> None:
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


# ======================================================================
# 1. IngestionMode
# ======================================================================


class IngestionMode(str, Enum):
    """Each declared underlying stream uses exactly one ingestion mode."""
    TICK = "TICK"
    PROVIDER_BAR = "PROVIDER_BAR"


# ======================================================================
# 2. StreamIngestionModeMismatchError
# ======================================================================


class StreamIngestionModeMismatchError(Exception):
    """Raised when the wrong event type is ingested into a stream with a different mode."""


# ======================================================================
# 2b. AmbiguousSameTimestampTickError
# ======================================================================


class AmbiguousSameTimestampTickError(Exception):
    """Raised when conflicting tick payloads share the same exchange_timestamp with no tick_id."""


# ======================================================================
# 3. LiveTradeTick
# ======================================================================


@dataclass(frozen=True)
class LiveTradeTick:
    """Atomic underlying exchange trade-price evidence (not a QuoteSnapshot).

    Forbidden for option identities; option quotes use LiveQuoteEvent.
    """

    identity: InstrumentIdentity
    exchange_timestamp: datetime
    price: Decimal
    quantity: Decimal
    tick_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")
        if self.identity.segment == "options":
            raise ValueError(
                "LiveTradeTick does not accept option identities; "
                "use LiveQuoteEvent for option contract quotes"
            )
        _require_aware(self.exchange_timestamp, "exchange_timestamp")

        price = as_decimal(self.price, "price")
        if price <= 0:
            raise ValueError("price must be positive")
        quantity = as_decimal(self.quantity, "quantity")
        if quantity <= 0:
            raise ValueError("quantity must be positive")

        if self.tick_id is not None:
            if not isinstance(self.tick_id, str) or not self.tick_id.strip():
                raise ValueError("tick_id when provided must be a non-empty string")
            object.__setattr__(self, "tick_id", self.tick_id.strip())

        object.__setattr__(self, "price", price)
        object.__setattr__(self, "quantity", quantity)


# ======================================================================
# 4. LiveProviderBar
# ======================================================================


@dataclass(frozen=True)
class LiveProviderBar:
    """Authoritative provider-completed 1m base candle (already aggregated evidence).

    Represents the closed interval [start_timestamp, start_timestamp + 1 minute).
    NEVER decomposed into synthetic ticks.
    Forbidden for option identities.
    """

    identity: InstrumentIdentity
    timeframe: str
    start_timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    exchange_timestamp: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")
        if self.identity.segment == "options":
            raise ValueError(
                "LiveProviderBar does not accept option identities"
            )
        if self.timeframe != "1m":
            raise ValueError(
                "LiveProviderBar only accepts completed base-interval timeframe='1m'"
            )
        _require_aware(self.start_timestamp, "start_timestamp")
        _require_aware(self.exchange_timestamp, "exchange_timestamp")

        for name in ("open", "high", "low", "close", "volume"):
            val = as_decimal(getattr(self, name), name)
            object.__setattr__(self, name, val)

        if self.open <= 0 or self.high <= 0 or self.low <= 0 or self.close <= 0:
            raise ValueError("OHLC prices must be positive")
        if self.volume < 0:
            raise ValueError("volume must be non-negative")
        # Structural OHLC validity
        if self.high < self.low:
            raise ValueError("high must be >= low")
        if self.high < self.open or self.high < self.close:
            raise ValueError("high must be >= open and close")
        if self.low > self.open or self.low > self.close:
            raise ValueError("low must be <= open and close")

        # exchange_timestamp must prove that the 1m interval is complete
        interval_end = self.start_timestamp + timedelta(minutes=1)
        if self.exchange_timestamp < interval_end:
            raise ValueError(
                "exchange_timestamp must be >= start_timestamp + 1m to prove interval completion"
            )


# ======================================================================
# 5. MarketTimeEvent
# ======================================================================


@dataclass(frozen=True)
class MarketTimeEvent:
    """Explicit market-time advancement pulse.

    Carries ZERO price/OHLC/volume authority.
    Its sole purpose is deterministic time advancement for interval closure
    and D3a gap detection.
    """

    market_timestamp: datetime
    source: str = "transport_heartbeat"

    def __post_init__(self) -> None:
        _require_aware(self.market_timestamp, "market_timestamp")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must be a non-empty string")
        object.__setattr__(self, "source", self.source.strip())


# ======================================================================
# 6. DataGapEvidence
# ======================================================================


@dataclass(frozen=True)
class DataGapEvidence:
    """Immutable evidence of a zero-observation expected interval.

    D3a: A genuinely empty interval must produce gap evidence, never a synthetic bar.
    """

    stream: StreamKey
    interval_start: datetime
    interval_end: datetime
    reason: str = "zero_observations_in_interval"

    def __post_init__(self) -> None:
        if not isinstance(self.stream, StreamKey):
            raise TypeError("stream must be a StreamKey")
        _require_aware(self.interval_start, "interval_start")
        _require_aware(self.interval_end, "interval_end")
        if self.interval_end <= self.interval_start:
            raise ValueError("interval_end must be strictly after interval_start")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("reason must be a non-empty string")
        object.__setattr__(self, "reason", self.reason.strip())


# ======================================================================
# 7. LiveBarBuilderResult
# ======================================================================


@dataclass(frozen=True)
class LiveBarBuilderResult:
    """Immutable output from one ingestion or market-time advancement step."""

    completed_events: tuple[BoundBarEvent, ...]
    gaps: tuple[DataGapEvidence, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.completed_events, tuple) or not all(
            isinstance(e, BoundBarEvent) for e in self.completed_events
        ):
            raise TypeError("completed_events must be a tuple of BoundBarEvent")
        if not isinstance(self.gaps, tuple) or not all(
            isinstance(g, DataGapEvidence) for g in self.gaps
        ):
            raise TypeError("gaps must be a tuple of DataGapEvidence")


_EMPTY_RESULT = LiveBarBuilderResult(completed_events=(), gaps=())


# ======================================================================
# Tick fingerprint for full-payload idempotence
# ======================================================================

def _tick_fingerprint(tick: LiveTradeTick) -> tuple:
    """Return an immutable canonical fingerprint for full-payload duplicate detection.

    Includes identity, exchange_timestamp, price, quantity, and tick_id.
    """
    ident = tick.identity
    return (
        ident.market,
        ident.instrument,
        ident.segment,
        tick.exchange_timestamp,
        tick.price,
        tick.quantity,
        tick.tick_id,
    )


# ======================================================================
# 8. Internal per-stream state
# ======================================================================


class _TickAccumulator:
    """Mutable in-progress bar evidence for TICK-mode streams."""

    def __init__(self) -> None:
        self.bar_start: datetime | None = None
        self.open: Decimal | None = None
        self.high: Decimal | None = None
        self.low: Decimal | None = None
        self.close: Decimal | None = None
        self.volume: Decimal = Decimal("0")
        # Latest consumed exchange_timestamp for monotonic order enforcement
        self.last_exchange_timestamp: datetime | None = None
        # timestamp -> fingerprint for same-timestamp/no-tick-id ambiguity
        self.seen_no_id_timestamps: dict[datetime, tuple] = {}

    def has_observations(self) -> bool:
        return self.open is not None

    def add_tick(self, price: Decimal, quantity: Decimal) -> None:
        if self.open is None:
            self.open = price
            self.high = price
            self.low = price
        else:
            if price > self.high:  # type: ignore[operator]
                self.high = price
            if price < self.low:  # type: ignore[operator]
                self.low = price
        self.close = price
        self.volume += quantity

    def reset(self) -> None:
        self.bar_start = None
        self.open = None
        self.high = None
        self.low = None
        self.close = None
        self.volume = Decimal("0")
        self.seen_no_id_timestamps = {}


class _ProviderBarAccumulator:
    """Mutable in-progress 1m base-bar aggregation state for PROVIDER_BAR streams."""

    def __init__(self) -> None:
        # Tracks accepted 1m bars by start_timestamp
        self.bars: dict[datetime, LiveProviderBar] = {}
        # Latest accepted start_timestamp for monotonic order enforcement
        self.last_accepted_start: datetime | None = None


# ======================================================================
# 9. LiveBarBuilder
# ======================================================================


class LiveBarBuilder:
    """Provider-neutral deterministic tick-to-bar and provider-bar aggregator.

    Each declared StreamKey operates in exactly one IngestionMode.
    Mixing TICK and PROVIDER_BAR inputs for the same stream fails closed.
    """

    def __init__(
        self,
        *,
        declared_streams: Mapping[StreamKey, IngestionMode],
        session_boundary: MarketSessionBoundary,
    ) -> None:
        if not isinstance(declared_streams, Mapping):
            raise TypeError("declared_streams must be a Mapping[StreamKey, IngestionMode]")
        if not isinstance(session_boundary, MarketSessionBoundary):
            raise TypeError("session_boundary must be a MarketSessionBoundary")

        streams: dict[StreamKey, IngestionMode] = {}
        for key, mode in declared_streams.items():
            if not isinstance(key, StreamKey):
                raise TypeError(f"declared_streams key must be StreamKey, got {type(key).__name__}")
            if not isinstance(mode, IngestionMode):
                raise TypeError(f"declared_streams value must be IngestionMode, got {type(mode).__name__}")
            streams[key] = mode

        self._streams: dict[StreamKey, IngestionMode] = streams
        self._session_boundary = session_boundary

        # Identity -> sorted list of StreamKeys (for fan-out)
        self._identity_to_streams: dict[InstrumentIdentity, list[StreamKey]] = {}
        for key in streams:
            ident = key.identity
            if ident not in self._identity_to_streams:
                self._identity_to_streams[ident] = []
            self._identity_to_streams[ident].append(key)
        # Sort each identity's streams by duration ascending (1m -> 5m -> 15m)
        for ident in self._identity_to_streams:
            self._identity_to_streams[ident].sort(
                key=lambda k: _timeframe_duration(k.timeframe)
            )

        # Per-stream state
        self._tick_accum: dict[StreamKey, _TickAccumulator] = {}
        self._provider_bar_accum: dict[StreamKey, _ProviderBarAccumulator] = {}
        self._last_closed_boundary: dict[StreamKey, datetime | None] = {}
        # Track per-stream session-start for D3a initial gap detection
        self._stream_session_start: dict[StreamKey, datetime | None] = {}
        # Track the latest gap-emitted boundary per stream
        self._last_gap_boundary: dict[StreamKey, datetime | None] = {}
        # Track completed bar timestamps per stream to avoid duplicate gap generation and enforce mutual exclusion
        self._emitted_bar_starts: dict[StreamKey, set[datetime]] = {}
        self._emitted_gap_starts: dict[StreamKey, set[datetime]] = {}

        # Authoritative monotonic market-time watermark across all streams
        self._last_market_timestamp: datetime | None = None

        # Identity-scoped tick_id registry for duplicate/conflict detection
        # Key is (InstrumentIdentity, tick_id)
        self._seen_tick_ids: dict[tuple[InstrumentIdentity, str], tuple] = {}

        for key, mode in streams.items():
            if mode == IngestionMode.TICK:
                self._tick_accum[key] = _TickAccumulator()
            else:
                self._provider_bar_accum[key] = _ProviderBarAccumulator()
            self._last_closed_boundary[key] = None
            self._stream_session_start[key] = None
            self._last_gap_boundary[key] = None
            self._emitted_bar_starts[key] = set()
            self._emitted_gap_starts[key] = set()

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    def _session_open_dt(self, ref_ts: datetime) -> datetime:
        """Return the session-open datetime for the trading date containing ref_ts."""
        profile = self._session_boundary.profile
        exch_ts = self._session_boundary.exchange_timestamp(ref_ts)
        session_date = exch_ts.date()
        return datetime.combine(session_date, profile.regular_session_open, tzinfo=profile.timezone)

    def _session_close_dt(self, ref_ts: datetime) -> datetime:
        """Return the session-close datetime for the trading date containing ref_ts."""
        profile = self._session_boundary.profile
        exch_ts = self._session_boundary.exchange_timestamp(ref_ts)
        session_date = exch_ts.date()
        return datetime.combine(session_date, profile.regular_session_close, tzinfo=profile.timezone)

    def _is_in_regular_session(self, ts: datetime) -> bool:
        """Return whether ts falls within regular trading session.

        Note: An interval starting at session_close (e.g. 15:30) is post-session.
        Valid session interval starts must be strictly before session_close.
        """
        if not self._session_boundary.is_regular_session(ts):
            return False
        # If timestamp time equals session close time, it's the post-session boundary
        close_time = self._session_boundary.profile.regular_session_close
        ts_time = self._session_boundary.exchange_timestamp(ts).timetz().replace(tzinfo=None)
        return ts_time < close_time

    def _ensure_session_start(self, stream: StreamKey, ts: datetime) -> None:
        """Set the session start for a stream if not already set, using session boundary."""
        if self._stream_session_start[stream] is None:
            session_open = self._session_open_dt(ts)
            self._stream_session_start[stream] = session_open
            self._last_gap_boundary[stream] = session_open

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest_trade_tick(self, tick: LiveTradeTick) -> LiveBarBuilderResult:
        """Accumulate one trade tick and return any newly completed bars / gap evidence."""
        if not isinstance(tick, LiveTradeTick):
            raise TypeError("expected LiveTradeTick")

        matching_streams = self._resolve_identity(tick.identity)
        ts = tick.exchange_timestamp

        for stream in matching_streams:
            mode = self._streams[stream]
            if mode != IngestionMode.TICK:
                raise StreamIngestionModeMismatchError(
                    f"stream {stream!r} is configured for {mode.value} mode; "
                    f"cannot ingest LiveTradeTick"
                )

            # Finality Check: Late tick after interval finalization
            interval_start = self._interval_start_for(ts, stream)
            duration = _timeframe_duration(stream.timeframe)
            interval_end = interval_start + duration

            if (
                interval_start in self._emitted_gap_starts[stream]
                or interval_start in self._emitted_bar_starts[stream]
                or (self._last_market_timestamp is not None and self._last_market_timestamp >= interval_end)
            ):
                raise ValueError(
                    f"late tick at exchange_timestamp {ts} for stream {stream!r} "
                    f"arrives after interval {interval_start} has been finalized"
                )

        # Identity-scoped tick_id duplicate and conflict check
        fingerprint = _tick_fingerprint(tick)
        if tick.tick_id is not None:
            key = (tick.identity, tick.tick_id)
            if key in self._seen_tick_ids:
                existing_fp = self._seen_tick_ids[key]
                if existing_fp == fingerprint:
                    # Exact full-payload duplicate — idempotent across matching streams
                    return _EMPTY_RESULT
                else:
                    raise ValueError(
                        f"reused tick_id {tick.tick_id!r} for identity {tick.identity!r} "
                        f"with conflicting payload (existing fingerprint={existing_fp}, new={fingerprint})"
                    )
            self._seen_tick_ids[key] = fingerprint

        completed: list[BoundBarEvent] = []
        gaps: list[DataGapEvidence] = []

        for stream in matching_streams:
            c, g = self._process_tick_for_stream(stream, tick, fingerprint)
            completed.extend(c)
            gaps.extend(g)

        return self._ordered_result(completed, gaps)

    def ingest_provider_bar(self, bar: LiveProviderBar) -> LiveBarBuilderResult:
        """Accept a completed 1m provider bar and roll up higher timeframes."""
        if not isinstance(bar, LiveProviderBar):
            raise TypeError("expected LiveProviderBar")

        matching_streams = self._resolve_identity(bar.identity)
        base_start = bar.start_timestamp
        base_end = base_start + timedelta(minutes=1)

        for stream in matching_streams:
            mode = self._streams[stream]
            if mode != IngestionMode.PROVIDER_BAR:
                raise StreamIngestionModeMismatchError(
                    f"stream {stream!r} is configured for {mode.value} mode; "
                    f"cannot ingest LiveProviderBar"
                )

            accum = self._provider_bar_accum[stream]
            # Duplicate / conflict check for same start_timestamp
            if base_start in accum.bars:
                existing = accum.bars[base_start]
                if (existing.open != bar.open or existing.high != bar.high
                        or existing.low != bar.low or existing.close != bar.close
                        or existing.volume != bar.volume):
                    raise ValueError(
                        f"conflicting provider bar for start_timestamp {base_start}: "
                        f"existing={existing!r}, new={bar!r}"
                    )

            # Finality Check: Late provider bar after interval finalization
            interval_start = self._interval_start_for(base_start, stream)
            if base_start not in accum.bars:
                if (
                    interval_start in self._emitted_gap_starts[stream]
                    or interval_start in self._emitted_bar_starts[stream]
                    or base_start in self._emitted_gap_starts[stream]
                    or base_start in self._emitted_bar_starts[stream]
                    or (self._last_market_timestamp is not None and self._last_market_timestamp >= base_end)
                ):
                    raise ValueError(
                        f"late provider bar at start_timestamp {base_start} for stream {stream!r} "
                        f"arrives after interval has been finalized"
                    )

        completed: list[BoundBarEvent] = []
        gaps: list[DataGapEvidence] = []

        for stream in matching_streams:
            c, g = self._process_provider_bar_for_stream(stream, bar)
            completed.extend(c)
            gaps.extend(g)

        return self._ordered_result(completed, gaps)

    def advance_market_time(self, event: MarketTimeEvent) -> LiveBarBuilderResult:
        """Advance market time, close completed intervals, emit D3a gap evidence."""
        if not isinstance(event, MarketTimeEvent):
            raise TypeError("expected MarketTimeEvent")

        ts = event.market_timestamp

        # Monotonic MarketTimeEvent advancement check
        if self._last_market_timestamp is not None:
            if ts < self._last_market_timestamp:
                raise ValueError(
                    f"MarketTimeEvent market_timestamp {ts} cannot move backwards "
                    f"from already-advanced market time {self._last_market_timestamp}"
                )
            if ts == self._last_market_timestamp:
                # Exact duplicate MarketTimeEvent is idempotent
                return _EMPTY_RESULT

        self._last_market_timestamp = ts

        completed: list[BoundBarEvent] = []
        gaps: list[DataGapEvidence] = []

        # Process each stream deterministically (sorted by stream key for determinism)
        for stream in self._sorted_streams():
            mode = self._streams[stream]
            if mode == IngestionMode.TICK:
                c, g = self._advance_tick_stream(stream, ts)
                completed.extend(c)
                gaps.extend(g)
            else:
                c, g = self._advance_provider_bar_stream(stream, ts)
                completed.extend(c)
                gaps.extend(g)

        return self._ordered_result(completed, gaps)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_identity(self, identity: InstrumentIdentity) -> list[StreamKey]:
        """Return the declared streams for a given identity, fail closed if unknown."""
        if identity not in self._identity_to_streams:
            raise KeyError(
                f"identity {identity!r} is not registered in any declared stream"
            )
        return self._identity_to_streams[identity]

    def _sorted_streams(self) -> list[StreamKey]:
        """Return all declared streams in canonical deterministic order."""
        return sorted(
            self._streams.keys(),
            key=lambda k: (
                k.identity.instrument,
                _timeframe_duration(k.timeframe),
            ),
        )

    def _interval_start_for(self, ts: datetime, stream: StreamKey) -> datetime:
        """Compute the interval start of the bar that contains the given timestamp.

        For epoch-safe timeframes (1m, 5m, 15m, etc.), uses epoch-aligned floor.
        For non-epoch-safe timeframes (30m, etc.), uses session-relative alignment
        derived from MarketSessionBoundary to ensure intervals start from session open.
        """
        duration = _timeframe_duration(stream.timeframe)

        if _is_epoch_safe(stream.timeframe):
            # Epoch-aligned floor
            epoch = datetime(1970, 1, 1, tzinfo=ts.tzinfo)
            elapsed = ts - epoch
            slots = int(elapsed.total_seconds() / duration.total_seconds())
            return epoch + slots * duration
        else:
            # Session-relative alignment: intervals start from session open
            session_open = self._session_open_dt(ts)
            if ts < session_open:
                session_open = self._session_open_dt(ts - timedelta(days=1))
            elapsed = ts - session_open
            elapsed_seconds = elapsed.total_seconds()
            if elapsed_seconds < 0:
                elapsed_seconds = 0
            duration_seconds = duration.total_seconds()
            slots = int(elapsed_seconds / duration_seconds)
            return session_open + timedelta(seconds=slots * duration_seconds)

    def _process_tick_for_stream(
        self,
        stream: StreamKey,
        tick: LiveTradeTick,
        fingerprint: tuple,
    ) -> tuple[list[BoundBarEvent], list[DataGapEvidence]]:
        """Handle a tick for one TICK-mode stream."""
        accum = self._tick_accum[stream]
        ts = tick.exchange_timestamp

        # Monotonic order enforcement
        if accum.last_exchange_timestamp is not None:
            if ts < accum.last_exchange_timestamp:
                raise ValueError(
                    f"tick exchange_timestamp {ts} is older than already-accepted "
                    f"{accum.last_exchange_timestamp} for stream {stream!r}"
                )

        # No tick_id: same-timestamp ambiguity detection
        if tick.tick_id is None:
            if ts in accum.seen_no_id_timestamps:
                existing_fp = accum.seen_no_id_timestamps[ts]
                if existing_fp == fingerprint:
                    # Exact same payload — idempotent
                    return [], []
                else:
                    raise AmbiguousSameTimestampTickError(
                        f"conflicting tick payload at exchange_timestamp={ts} "
                        f"without tick_id discriminator; cannot determine OHLC authority "
                        f"(existing={existing_fp}, new={fingerprint})"
                    )
            accum.seen_no_id_timestamps[ts] = fingerprint

        accum.last_exchange_timestamp = ts

        # Initialize session tracking for D3a gap detection
        if self._is_in_regular_session(ts):
            self._ensure_session_start(stream, ts)

        # Compute current interval start
        interval_start = self._interval_start_for(ts, stream)
        duration = _timeframe_duration(stream.timeframe)
        interval_end = interval_start + duration

        completed: list[BoundBarEvent] = []
        gaps: list[DataGapEvidence] = []

        if accum.bar_start is None:
            # Starting fresh — emit gaps for any missing intervals since session start
            if self._stream_session_start[stream] is not None:
                gap_from = self._last_gap_boundary[stream] or self._stream_session_start[stream]
                fill_start = self._interval_start_for(gap_from, stream)
                while fill_start < interval_start:
                    fill_end = fill_start + duration
                    if self._is_in_regular_session(fill_start) and fill_start not in self._emitted_gap_starts[stream] and fill_start not in self._emitted_bar_starts[stream]:
                        gaps.append(DataGapEvidence(
                            stream=stream,
                            interval_start=fill_start,
                            interval_end=fill_end,
                        ))
                        self._emitted_gap_starts[stream].add(fill_start)
                    fill_start = fill_end
                self._last_gap_boundary[stream] = interval_end
            accum.bar_start = interval_start
        elif interval_start > accum.bar_start:
            # We have moved into a new interval — close and emit prior bar
            prior_end = accum.bar_start + duration
            c, g = self._close_tick_bar(stream, accum)
            completed.extend(c)
            gaps.extend(g)
            # Fill any completely skipped intervals between prior and new
            fill_start = prior_end
            while fill_start < interval_start:
                fill_end = fill_start + duration
                if self._is_in_regular_session(fill_start) and fill_start not in self._emitted_gap_starts[stream] and fill_start not in self._emitted_bar_starts[stream]:
                    gaps.append(DataGapEvidence(
                        stream=stream,
                        interval_start=fill_start,
                        interval_end=fill_end,
                    ))
                    self._emitted_gap_starts[stream].add(fill_start)
                fill_start = fill_end
            accum.bar_start = interval_start
            accum.seen_no_id_timestamps = {}
            if tick.tick_id is None:
                accum.seen_no_id_timestamps[ts] = fingerprint
            self._last_gap_boundary[stream] = interval_end

        # Add tick to current interval
        accum.add_tick(tick.price, tick.quantity)
        self._last_closed_boundary[stream] = interval_end

        return completed, gaps

    def _close_tick_bar(
        self,
        stream: StreamKey,
        accum: _TickAccumulator,
    ) -> tuple[list[BoundBarEvent], list[DataGapEvidence]]:
        """Finalize a tick-mode bar interval and return completed BoundBarEvent if observations exist."""
        if not accum.has_observations() or accum.bar_start is None:
            return [], []
        bar_start = accum.bar_start
        bar = BarEvent(
            symbol=stream.identity.instrument,
            timestamp=bar_start,
            timeframe=stream.timeframe,
            open=accum.open,
            high=accum.high,
            low=accum.low,
            close=accum.close,
            volume=accum.volume,
            is_synthetic=False,
        )
        bound = BoundBarEvent(bar=bar, stream=stream)
        self._emitted_bar_starts[stream].add(bar_start)
        accum.reset()
        return [bound], []

    def _advance_tick_stream(
        self,
        stream: StreamKey,
        market_ts: datetime,
    ) -> tuple[list[BoundBarEvent], list[DataGapEvidence]]:
        """On market-time advancement, close any completed tick intervals.

        D3a: If session has started but no observation set bar_start, derive
        expected interval boundaries from session open and emit gap evidence.
        """
        accum = self._tick_accum[stream]
        duration = _timeframe_duration(stream.timeframe)

        # D3a: Handle initial zero-observation intervals
        if accum.bar_start is None:
            if self._is_in_regular_session(market_ts):
                self._ensure_session_start(stream, market_ts)

            if self._stream_session_start[stream] is not None:
                gaps: list[DataGapEvidence] = []
                gap_from = self._last_gap_boundary[stream] or self._stream_session_start[stream]
                fill_start = self._interval_start_for(gap_from, stream)

                while fill_start + duration <= market_ts:
                    fill_end = fill_start + duration
                    if self._is_in_regular_session(fill_start) and fill_start not in self._emitted_bar_starts[stream] and fill_start not in self._emitted_gap_starts[stream]:
                        gaps.append(DataGapEvidence(
                            stream=stream,
                            interval_start=fill_start,
                            interval_end=fill_end,
                        ))
                        self._emitted_gap_starts[stream].add(fill_start)
                    fill_start = fill_end
                if gaps:
                    self._last_gap_boundary[stream] = gaps[-1].interval_end
                return [], gaps

            return [], []

        interval_end = accum.bar_start + duration

        if market_ts < interval_end:
            return [], []

        completed: list[BoundBarEvent] = []
        gaps: list[DataGapEvidence] = []

        # Close current (possibly observed) bar
        prior_bar_start = accum.bar_start
        c, g = self._close_tick_bar(stream, accum)
        completed.extend(c)
        # Note: _close_tick_bar resets accum (bar_start=None)
        # If no observations, produce gap evidence for that interval
        if not c and prior_bar_start not in self._emitted_gap_starts[stream] and prior_bar_start not in self._emitted_bar_starts[stream]:
            gaps.append(DataGapEvidence(
                stream=stream,
                interval_start=prior_bar_start,
                interval_end=interval_end,
            ))
            self._emitted_gap_starts[stream].add(prior_bar_start)

        # Fill completely skipped intervals between closed interval_end and market_ts
        fill_start = interval_end
        while fill_start + duration <= market_ts:
            fill_end = fill_start + duration
            if self._is_in_regular_session(fill_start) and fill_start not in self._emitted_bar_starts[stream] and fill_start not in self._emitted_gap_starts[stream]:
                gaps.append(DataGapEvidence(
                    stream=stream,
                    interval_start=fill_start,
                    interval_end=fill_end,
                ))
                self._emitted_gap_starts[stream].add(fill_start)
            fill_start = fill_end

        if gaps:
            self._last_gap_boundary[stream] = gaps[-1].interval_end

        return completed, gaps

    def _process_provider_bar_for_stream(
        self,
        stream: StreamKey,
        bar: LiveProviderBar,
    ) -> tuple[list[BoundBarEvent], list[DataGapEvidence]]:
        """Accept a 1m provider bar for one PROVIDER_BAR stream and roll up into declared timeframe."""
        accum = self._provider_bar_accum[stream]
        base_start = bar.start_timestamp
        base_end = base_start + timedelta(minutes=1)

        # Initialize session tracking for D3a
        if self._is_in_regular_session(base_start):
            self._ensure_session_start(stream, base_start)

        # Monotonic order enforcement
        if accum.last_accepted_start is not None:
            if base_start < accum.last_accepted_start:
                raise ValueError(
                    f"provider bar start_timestamp {base_start} is older than accepted "
                    f"{accum.last_accepted_start} for stream {stream!r}"
                )

        # Duplicate / conflict check
        if base_start in accum.bars:
            existing = accum.bars[base_start]
            if (existing.open != bar.open or existing.high != bar.high
                    or existing.low != bar.low or existing.close != bar.close
                    or existing.volume != bar.volume):
                raise ValueError(
                    f"conflicting provider bar for start_timestamp {base_start}: "
                    f"existing={existing!r}, new={bar!r}"
                )
            # Exact duplicate — idempotent
            return [], []

        accum.bars[base_start] = bar
        accum.last_accepted_start = base_start

        # Only the base 1m stream emits immediately; larger timeframes roll up
        if stream.timeframe == "1m":
            bar_event = BarEvent(
                symbol=stream.identity.instrument,
                timestamp=base_start,
                timeframe="1m",
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                is_synthetic=False,
            )
            bound = BoundBarEvent(bar=bar_event, stream=stream)
            self._emitted_bar_starts[stream].add(base_start)
            return [bound], []

        # Higher timeframe: check if we have a complete set
        duration = _timeframe_duration(stream.timeframe)
        # Find the interval start for this bar
        interval_start = self._interval_start_for(base_start, stream)
        interval_end = interval_start + duration
        n_base_bars = int(duration.total_seconds() / 60)

        # Collect all expected 1m starts for this interval
        expected_starts = set()
        t = interval_start
        for _ in range(n_base_bars):
            expected_starts.add(t)
            t += timedelta(minutes=1)

        # Check if we have all of them in accum
        available = {s: accum.bars[s] for s in expected_starts if s in accum.bars}
        if len(available) < n_base_bars:
            # Incomplete — do not fabricate
            return [], []

        # Aggregate
        sorted_bases = sorted(available.values(), key=lambda b: b.start_timestamp)
        agg_open = sorted_bases[0].open
        agg_high = max(b.high for b in sorted_bases)
        agg_low = min(b.low for b in sorted_bases)
        agg_close = sorted_bases[-1].close
        agg_volume = sum((b.volume for b in sorted_bases), Decimal("0"))

        bar_event = BarEvent(
            symbol=stream.identity.instrument,
            timestamp=interval_start,
            timeframe=stream.timeframe,
            open=agg_open,
            high=agg_high,
            low=agg_low,
            close=agg_close,
            volume=agg_volume,
            is_synthetic=False,
        )
        bound = BoundBarEvent(bar=bar_event, stream=stream)
        self._emitted_bar_starts[stream].add(interval_start)
        return [bound], []

    def _advance_provider_bar_stream(
        self,
        stream: StreamKey,
        market_ts: datetime,
    ) -> tuple[list[BoundBarEvent], list[DataGapEvidence]]:
        """Market-time advancement for PROVIDER_BAR mode (gap detection).

        D3a: Emit gaps for expected declared stream intervals that have not produced a bar.
        """
        if self._is_in_regular_session(market_ts):
            self._ensure_session_start(stream, market_ts)

        if self._stream_session_start[stream] is None:
            return [], []

        gaps: list[DataGapEvidence] = []
        duration = _timeframe_duration(stream.timeframe)
        gap_from = self._last_gap_boundary[stream] or self._stream_session_start[stream]
        fill_start = self._interval_start_for(gap_from, stream)

        while fill_start + duration <= market_ts:
            fill_end = fill_start + duration
            if self._is_in_regular_session(fill_start) and fill_start not in self._emitted_bar_starts[stream] and fill_start not in self._emitted_gap_starts[stream]:
                gaps.append(DataGapEvidence(
                    stream=stream,
                    interval_start=fill_start,
                    interval_end=fill_end,
                ))
                self._emitted_gap_starts[stream].add(fill_start)
            fill_start = fill_end

        if gaps:
            self._last_gap_boundary[stream] = gaps[-1].interval_end

        return [], gaps

    def _ordered_result(
        self,
        completed: list[BoundBarEvent],
        gaps: list[DataGapEvidence],
    ) -> LiveBarBuilderResult:
        """Return an immutable canonically ordered result."""
        # Sort completed events by (instrument, timeframe_duration, bar_timestamp)
        sorted_completed = tuple(sorted(
            completed,
            key=lambda e: (
                e.stream.identity.instrument,
                _timeframe_duration(e.stream.timeframe),
                e.bar.timestamp,
            ),
        ))
        # Sort gaps by (instrument, timeframe_duration, interval_start)
        sorted_gaps = tuple(sorted(
            gaps,
            key=lambda g: (
                g.stream.identity.instrument,
                _timeframe_duration(g.stream.timeframe),
                g.interval_start,
            ),
        ))
        return LiveBarBuilderResult(
            completed_events=sorted_completed,
            gaps=sorted_gaps,
        )
