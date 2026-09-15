"""Deterministic Slice 1 backtest run and market-event foundation."""

from abc import ABC
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import re
from typing import Callable, Iterable

from engine.core.numeric import as_decimal


_TIMEFRAME_PATTERN = re.compile(r"^(\d+)(m|h|d)$")


def _timeframe_duration(timeframe: str) -> int:
    """Return a supported timeframe duration in minutes for ordering only."""
    match = _TIMEFRAME_PATTERN.fullmatch(timeframe)
    if match is None:
        raise ValueError("timeframe must use the canonical <positive integer><m|h|d> form")

    quantity, unit = match.groups()
    if int(quantity) <= 0:
        raise ValueError("timeframe duration must be positive")
    multiplier = {"m": 1, "h": 60, "d": 1_440}[unit]
    return int(quantity) * multiplier


def _validate_aware(timestamp: datetime, field_name: str) -> None:
    """Reject naive timestamps at the event-engine boundary."""
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class BacktestRunContext:
    """Immutable metadata for one backtest run; never portfolio/account state."""

    run_id: str
    engine_version: str
    strategy_id: str
    strategy_version: str
    requested_symbols: tuple[str, ...]
    requested_timeframes: tuple[str, ...]
    start: datetime | None
    end: datetime | None
    execution_model_id: str
    cost_model_id: str
    reproducibility_seed: int
    market_profile_ref: str | None = None
    configuration_fingerprint: str | None = None
    data_fingerprints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate controlled run metadata without creating later subsystems."""
        if self.start is not None:
            _validate_aware(self.start, "start")
        if self.end is not None:
            _validate_aware(self.end, "end")
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("start must not be after end")
        for timeframe in self.requested_timeframes:
            _timeframe_duration(timeframe)


class MarketEvent(ABC):
    """Generic timezone-aware market-event boundary for future event types."""


@dataclass(frozen=True)
class BarEvent(MarketEvent):
    """One completed OHLCV bar delivered to the deterministic event loop."""

    symbol: str
    timestamp: datetime
    timeframe: str
    open: Decimal | int | float | str
    high: Decimal | int | float | str
    low: Decimal | int | float | str
    close: Decimal | int | float | str
    volume: Decimal | int | float | str
    is_synthetic: bool = False
    source_sequence: int | None = None

    def __post_init__(self) -> None:
        """Validate frozen OHLCV and timestamp requirements at event creation."""
        _validate_aware(self.timestamp, "timestamp")
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        _timeframe_duration(self.timeframe)
        for field_name in ("open", "high", "low", "close", "volume"):
            object.__setattr__(self, field_name, as_decimal(getattr(self, field_name), field_name))
        if self.high < self.low or self.high < self.open or self.high < self.close:
            raise ValueError("invalid OHLC relationship")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("OHLC prices must be positive")
        if self.volume < 0:
            raise ValueError("volume must be non-negative")
        if self.source_sequence is not None and self.source_sequence < 0:
            raise ValueError("source_sequence must be non-negative")

    @property
    def batch_key(self) -> datetime:
        """Return the timestamp that defines this event's logical batch."""
        return self.timestamp

    @property
    def canonical_order_key(self) -> tuple[datetime, int, str, int]:
        """Return the owner-approved deterministic processing key."""
        return (
            self.timestamp,
            _timeframe_duration(self.timeframe),
            self.symbol.casefold(),
            -1 if self.source_sequence is None else self.source_sequence,
        )


@dataclass(frozen=True)
class BacktestRunResult:
    """Minimal Slice 1 run status without portfolio or performance results."""

    run_id: str
    status: str
    processed_event_count: int
    start_timestamp: datetime | None
    end_timestamp: datetime | None


class DeterministicEventLoop:
    """Process complete timestamp batches without strategy/order behavior."""

    def run(
        self,
        context: BacktestRunContext,
        events: Iterable[MarketEvent],
        consumer: Callable[[tuple[MarketEvent, ...]], None] | None = None,
    ) -> BacktestRunResult:
        """Deliver sorted complete timestamp batches to an optional observer."""
        market_events = tuple(events)
        if not all(isinstance(event, BarEvent) for event in market_events):
            raise TypeError("Slice 1 currently supports BarEvent instances only")

        bar_events = tuple(market_events)
        self._reject_ambiguous_duplicates(bar_events)
        ordered_events = tuple(sorted(bar_events, key=lambda event: event.canonical_order_key))

        processed = 0
        start_timestamp = None
        end_timestamp = None
        index = 0
        while index < len(ordered_events):
            timestamp = ordered_events[index].timestamp
            batch_end = index
            while batch_end < len(ordered_events) and ordered_events[batch_end].timestamp == timestamp:
                batch_end += 1

            batch = ordered_events[index:batch_end]
            if consumer is not None:
                consumer(batch)
            processed += len(batch)
            start_timestamp = timestamp if start_timestamp is None else start_timestamp
            end_timestamp = timestamp
            index = batch_end

        return BacktestRunResult(
            run_id=context.run_id,
            status="completed",
            processed_event_count=processed,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
        )

    @staticmethod
    def _reject_ambiguous_duplicates(events: tuple[BarEvent, ...]) -> None:
        """Reject indistinguishable duplicate events instead of choosing one."""
        seen_keys: set[tuple[datetime, str, str, int | None]] = set()
        for event in events:
            key = (event.timestamp, event.timeframe, event.symbol.casefold(), event.source_sequence)
            if key in seen_keys:
                raise ValueError("ambiguous duplicate BarEvent")
            seen_keys.add(key)
