"""Exact historical-dataset to authoritative engine-event run preparation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable

from engine.backtest.engine import BarEvent
from engine.data.feeds.historical_feed import HistoricalDataFeed
from engine.market import BoundBarEvent, StreamKey
from engine.reproducibility import CanonicalCodec, MarketDataPolicy, MarketDataSnapshot, MarketDataStream


def _event_key(event: BoundBarEvent) -> tuple[object, ...]:
    """Canonical full-stream ordering without symbol-only tie breaking."""
    bar, stream = event.bar, event.stream
    identity = stream.identity
    return (
        CanonicalCodec.timestamp_text(bar.timestamp), bar.canonical_order_key[1],
        identity.market, identity.instrument, identity.segment,
        identity.underlying or "", "" if identity.expiry is None else identity.expiry.isoformat(),
        "" if identity.strike is None else str(identity.strike), identity.option_type or "",
        -1 if bar.source_sequence is None else bar.source_sequence,
    )


@dataclass(frozen=True)
class HistoricalRunInput:
    """One immutable execution/evidence view over the same exact bar objects."""

    snapshot: MarketDataSnapshot
    events: tuple[BoundBarEvent, ...]

    def __post_init__(self) -> None:
        events = tuple(self.events)
        if not events or not all(isinstance(item, BoundBarEvent) for item in events):
            raise ValueError("historical run input requires BoundBarEvent values")
        snapshot_bars = {
            item.stream: item.bars for item in self.snapshot.streams
        }
        event_bars: dict[StreamKey, tuple[BarEvent, ...]] = {}
        for stream in snapshot_bars:
            event_bars[stream] = tuple(item.bar for item in events if item.stream == stream)
        if snapshot_bars != event_bars:
            raise ValueError("snapshot and executable historical events must be identical evidence")
        object.__setattr__(self, "events", tuple(sorted(events, key=_event_key)))


class HistoricalDatasetRunAdapter:
    """The single exact-feed -> snapshot -> bound-event adapter."""

    def __init__(self, feed: HistoricalDataFeed, market_data_policy: MarketDataPolicy) -> None:
        if not isinstance(feed, HistoricalDataFeed):
            raise TypeError("feed must be HistoricalDataFeed")
        if not isinstance(market_data_policy, MarketDataPolicy):
            raise TypeError("market_data_policy must be MarketDataPolicy")
        self._feed = feed
        self._policy = market_data_policy

    def prepare(self, streams: Iterable[StreamKey]) -> HistoricalRunInput:
        requested = tuple(streams)
        if not requested or not all(isinstance(item, StreamKey) for item in requested):
            raise ValueError("streams must contain exact StreamKey values")
        if len(requested) != len(set(requested)):
            raise ValueError("duplicate historical stream is ambiguous")
        market_streams: list[MarketDataStream] = []
        events: list[BoundBarEvent] = []
        for stream in requested:
            data = self._feed.fetch_stream(stream)
            data = data.sort_values("timestamp", kind="stable")
            bars = tuple(
                BarEvent(
                    stream.identity.instrument, row.timestamp, stream.timeframe,
                    row.open, row.high, row.low, row.close, row.volume,
                    False, sequence,
                )
                for sequence, row in enumerate(data.itertuples(index=False))
            )
            if not bars:
                raise ValueError("exact historical stream has no valid completed bars")
            market_stream = MarketDataStream(stream, bars, self._policy)
            market_streams.append(market_stream)
            events.extend(BoundBarEvent(bar, stream) for bar in market_stream.bars)
        return HistoricalRunInput(MarketDataSnapshot(self._policy, tuple(market_streams)), tuple(events))


class HistoricalBacktestRunService:
    """Run prepared exact historical evidence through a caller-configured app coordinator."""

    def __init__(
        self,
        adapter: HistoricalDatasetRunAdapter,
        coordinator_factory: Callable[[MarketDataSnapshot], object],
    ) -> None:
        if not isinstance(adapter, HistoricalDatasetRunAdapter) or not callable(coordinator_factory):
            raise TypeError("adapter and coordinator_factory are required")
        self._adapter = adapter
        self._coordinator_factory = coordinator_factory

    def run(self, streams: Iterable[StreamKey], bundle: object) -> object:
        prepared = self._adapter.prepare(streams)
        coordinator = self._coordinator_factory(prepared.snapshot)
        if not callable(getattr(coordinator, "run", None)):
            raise TypeError("coordinator factory must produce BacktestApplicationCoordinator-compatible boundary")
        return coordinator.run(prepared.events, bundle)
