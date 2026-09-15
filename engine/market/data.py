"""Immutable, deterministic Slice 9 multi-symbol/multi-timeframe data views."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import re
from types import MappingProxyType
from typing import Callable, Iterable, Mapping

from engine.backtest.engine import BarEvent
from engine.market.profile import MarketProfile
from engine.portfolio.model import InstrumentIdentity


_TIMEFRAME = re.compile(r"^(\d+)(m|h|d)$")


def _duration(timeframe: str) -> timedelta:
    if not isinstance(timeframe, str):
        raise TypeError("timeframe must be a string")
    match = _TIMEFRAME.fullmatch(timeframe)
    if match is None:
        raise ValueError("timeframe must use the canonical <positive integer><m|h|d> form")
    quantity, unit = match.groups()
    amount = int(quantity)
    if amount <= 0:
        raise ValueError("timeframe duration must be positive")
    return timedelta(minutes=amount * {"m": 1, "h": 60, "d": 1_440}[unit])


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class StreamKey:
    """One concrete instrument/timeframe stream; suitable for immutable map keys."""

    identity: InstrumentIdentity
    timeframe: str

    def __post_init__(self) -> None:
        if not isinstance(self.identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")
        _duration(self.timeframe)


@dataclass(frozen=True)
class BoundBarEvent:
    """One BarEvent bound to its authoritative Slice 9 stream identity."""

    bar: BarEvent
    stream: StreamKey

    def __post_init__(self) -> None:
        if not isinstance(self.bar, BarEvent) or not isinstance(self.stream, StreamKey):
            raise TypeError("bar and stream must be BarEvent and StreamKey")
        if self.bar.symbol.upper() != self.stream.identity.instrument:
            raise ValueError("BarEvent symbol does not match bound StreamKey identity")
        if self.bar.timeframe != self.stream.timeframe:
            raise ValueError("BarEvent timeframe does not match bound StreamKey")


@dataclass(frozen=True)
class DataSubscription:
    """One required stream and its explicit completed-history requirement."""

    stream: StreamKey
    minimum_history: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.stream, StreamKey):
            raise TypeError("stream must be a StreamKey")
        if not isinstance(self.minimum_history, int) or isinstance(self.minimum_history, bool):
            raise TypeError("minimum_history must be an integer")
        if self.minimum_history <= 0:
            raise ValueError("minimum_history must be positive")


@dataclass(frozen=True)
class StrategyDataRequirements:
    """Declared streams, trigger streams, and readiness for one strategy."""

    strategy_id: str
    strategy_version: str
    subscriptions: tuple[DataSubscription, ...]
    trigger_streams: frozenset[StreamKey]

    def __post_init__(self) -> None:
        _text(self.strategy_id, "strategy_id")
        _text(self.strategy_version, "strategy_version")
        subscriptions = tuple(self.subscriptions)
        if not subscriptions or not all(isinstance(item, DataSubscription) for item in subscriptions):
            raise ValueError("subscriptions must contain at least one DataSubscription")
        streams = tuple(item.stream for item in subscriptions)
        if len(streams) != len(set(streams)):
            raise ValueError("duplicate stream subscription is ambiguous")
        triggers = frozenset(self.trigger_streams)
        if not triggers or not all(isinstance(item, StreamKey) for item in triggers):
            raise ValueError("trigger_streams must contain at least one StreamKey")
        if not triggers <= set(streams):
            raise ValueError("trigger_streams must be a subset of subscribed streams")
        object.__setattr__(self, "subscriptions", subscriptions)
        object.__setattr__(self, "trigger_streams", triggers)

    @property
    def streams(self) -> frozenset[StreamKey]:
        return frozenset(item.stream for item in self.subscriptions)


@dataclass(frozen=True)
class StreamProfileMap:
    """Explicit deterministic stream-to-market-profile mapping with no fallback."""

    profiles: Mapping[StreamKey, MarketProfile]

    def __post_init__(self) -> None:
        values = dict(self.profiles)
        if not values:
            raise ValueError("profiles must not be empty")
        if not all(isinstance(key, StreamKey) and isinstance(value, MarketProfile) for key, value in values.items()):
            raise TypeError("profiles must map StreamKey to MarketProfile")
        object.__setattr__(self, "profiles", MappingProxyType(values))

    def resolve(self, stream: StreamKey) -> MarketProfile:
        if not isinstance(stream, StreamKey):
            raise TypeError("stream must be a StreamKey")
        try:
            return self.profiles[stream]
        except KeyError as error:
            raise ValueError("missing MarketProfile mapping for required stream") from error


@dataclass(frozen=True)
class AllocationPriorityConfig:
    """Validated configuration-only same-timestamp allocation rank foundation."""

    ranks: Mapping[str, int]

    def __post_init__(self) -> None:
        values = dict(self.ranks)
        if not values:
            raise ValueError("ranks must not be empty")
        normalized: dict[str, int] = {}
        for strategy_id, rank in values.items():
            strategy = _text(strategy_id, "strategy_id")
            if not isinstance(rank, int) or isinstance(rank, bool):
                raise TypeError("allocation rank must be an integer")
            if rank < 0:
                raise ValueError("allocation rank must be non-negative")
            normalized[strategy] = rank
        if len(set(normalized.values())) != len(normalized):
            raise ValueError("duplicate allocation rank is ambiguous")
        object.__setattr__(self, "ranks", MappingProxyType(normalized))

    def rank_for(self, strategy_id: str) -> int:
        try:
            return self.ranks[strategy_id]
        except KeyError as error:
            raise ValueError("missing allocation rank for strategy") from error


@dataclass(frozen=True)
class StreamEvidence:
    """Read-only completed history and current-batch freshness for one stream."""

    history: tuple[BarEvent, ...]
    updated_in_batch: bool

    def __post_init__(self) -> None:
        history = tuple(self.history)
        if not all(isinstance(value, BarEvent) for value in history):
            raise TypeError("history must contain BarEvent values")
        object.__setattr__(self, "history", history)

    @property
    def latest(self) -> BarEvent | None:
        return self.history[-1] if self.history else None


@dataclass(frozen=True)
class DataReadiness:
    """Explicit strategy readiness; unready strategies are not evaluated."""

    ready: bool
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        reasons = tuple(self.reasons)
        if self.ready and reasons:
            raise ValueError("ready DataReadiness cannot have reasons")
        if not self.ready and not reasons:
            raise ValueError("unready DataReadiness requires reasons")
        object.__setattr__(self, "reasons", reasons)


@dataclass(frozen=True)
class MarketDataView:
    """Immutable declared-stream-only as-of view for one strategy evaluation."""

    decision_time: datetime
    streams: Mapping[StreamKey, StreamEvidence]

    def __post_init__(self) -> None:
        if self.decision_time.tzinfo is None or self.decision_time.utcoffset() is None:
            raise ValueError("decision_time must be timezone-aware")
        values = dict(self.streams)
        if not all(isinstance(key, StreamKey) and isinstance(value, StreamEvidence) for key, value in values.items()):
            raise TypeError("streams must map StreamKey to StreamEvidence")
        object.__setattr__(self, "streams", MappingProxyType(values))

    def evidence(self, stream: StreamKey) -> StreamEvidence:
        try:
            return self.streams[stream]
        except KeyError as error:
            raise KeyError("undeclared stream is inaccessible") from error

    def history(self, stream: StreamKey) -> tuple[BarEvent, ...]:
        return self.evidence(stream).history

    def latest(self, stream: StreamKey) -> BarEvent | None:
        return self.evidence(stream).latest

    def was_updated(self, stream: StreamKey) -> bool:
        return self.evidence(stream).updated_in_batch


@dataclass(frozen=True)
class EvaluationRequest:
    """One eligible, atomic strategy evaluation opportunity; no signal/order side effects."""

    requirements: StrategyDataRequirements
    data: MarketDataView
    readiness: DataReadiness

    def __post_init__(self) -> None:
        if not isinstance(self.requirements, StrategyDataRequirements):
            raise TypeError("requirements must be StrategyDataRequirements")
        if not isinstance(self.data, MarketDataView) or not isinstance(self.readiness, DataReadiness):
            raise TypeError("data and readiness must be Slice 9 values")
        if not self.readiness.ready:
            raise ValueError("EvaluationRequest requires ready data")


class MarketDataCoordinator:
    """Merge start-labelled bars by completion time into atomic strategy views."""

    def __init__(
        self,
        requirements: Iterable[StrategyDataRequirements],
        profiles: StreamProfileMap,
        allocation_priorities: AllocationPriorityConfig | None = None,
    ) -> None:
        strategies = tuple(requirements)
        if not strategies or not all(isinstance(value, StrategyDataRequirements) for value in strategies):
            raise ValueError("requirements must contain at least one StrategyDataRequirements")
        owners = tuple((value.strategy_id, value.strategy_version) for value in strategies)
        if len(owners) != len(set(owners)):
            raise ValueError("strategy requirements must have unique semantic owner identities")
        if not isinstance(profiles, StreamProfileMap):
            raise TypeError("profiles must be a StreamProfileMap")
        for requirement in strategies:
            for stream in requirement.streams:
                profiles.resolve(stream)
        if allocation_priorities is not None:
            if not isinstance(allocation_priorities, AllocationPriorityConfig):
                raise TypeError("allocation_priorities must be AllocationPriorityConfig")
            for requirement in strategies:
                allocation_priorities.rank_for(requirement.strategy_id)
        self._requirements = tuple(
            sorted(strategies, key=lambda item: (item.strategy_id, item.strategy_version))
        )
        self._profiles = profiles
        self._allocation_priorities = allocation_priorities
        self._streams = frozenset(stream for item in strategies for stream in item.streams)

    @staticmethod
    def availability_time(event: BarEvent | BoundBarEvent) -> datetime:
        bar = event.bar if isinstance(event, BoundBarEvent) else event
        if not isinstance(bar, BarEvent):
            raise TypeError("event must be a BarEvent or BoundBarEvent")
        return bar.timestamp + _duration(bar.timeframe)

    def stream_for(self, event: BarEvent | BoundBarEvent) -> StreamKey:
        if isinstance(event, BoundBarEvent):
            if event.stream not in self._streams:
                raise ValueError("BoundBarEvent does not map to a declared stream")
            return event.stream
        bar = event
        if not isinstance(bar, BarEvent):
            raise TypeError("event must be a BarEvent or BoundBarEvent")
        if len({stream.identity for stream in self._streams}) != 1:
            raise ValueError("multi-instrument BarEvent requires authoritative StreamKey binding")
        matches = tuple(
            stream for stream in self._streams
            if stream.timeframe == bar.timeframe
            and stream.identity.instrument == bar.symbol.upper()
        )
        if not matches:
            raise ValueError("BarEvent does not map to a declared stream")
        if len(matches) != 1:
            raise ValueError("BarEvent maps ambiguously to declared streams")
        return matches[0]

    def process(
        self,
        events: Iterable[BarEvent | BoundBarEvent],
        consumer: Callable[[EvaluationRequest], None] | None = None,
    ) -> tuple[EvaluationRequest, ...]:
        """Process complete availability batches; call consumer once per eligible strategy/batch."""
        events = tuple(events)
        if not all(isinstance(event, (BarEvent, BoundBarEvent)) for event in events):
            raise TypeError("events must contain BarEvent or BoundBarEvent values")
        resolved = tuple(
            (self.availability_time(event), self.stream_for(event), event.bar if isinstance(event, BoundBarEvent) else event)
            for event in events
        )
        self._reject_ambiguous_stream_bars(resolved)
        ordered = tuple(sorted(resolved, key=self._event_key))
        histories: dict[StreamKey, list[BarEvent]] = {stream: [] for stream in self._streams}
        emitted: list[EvaluationRequest] = []
        index = 0
        while index < len(ordered):
            decision_time = ordered[index][0]
            batch_end = index
            while batch_end < len(ordered) and ordered[batch_end][0] == decision_time:
                batch_end += 1
            batch = ordered[index:batch_end]
            # Synthetic bars may remain visible in history for continuity, but
            # they are not legal strategy-decision triggers.  Keep the two
            # concepts separate: ``updated`` describes received history,
            # while ``signal_triggers`` describes real completed evidence.
            updated = frozenset(stream for _, stream, _ in batch)
            signal_triggers = frozenset(stream for _, stream, bar in batch if not bar.is_synthetic)
            for _, stream, bar in batch:
                histories[stream].append(bar)
            for requirement in self._requirements:
                if not requirement.trigger_streams & signal_triggers:
                    continue
                view = self._view(requirement, histories, updated, decision_time)
                readiness = self._readiness(requirement, view)
                if readiness.ready:
                    request = EvaluationRequest(requirement, view, readiness)
                    emitted.append(request)
                    if consumer is not None:
                        consumer(request)
            index = batch_end
        return tuple(emitted)

    @staticmethod
    def _event_key(value: tuple[datetime, StreamKey, BarEvent]) -> tuple:
        availability, stream, bar = value
        identity = stream.identity
        return (
            availability,
            _duration(stream.timeframe),
            identity.market,
            identity.instrument,
            identity.segment,
            repr(identity.underlying),
            repr(identity.expiry),
            repr(identity.strike),
            repr(identity.option_type),
            -1 if bar.source_sequence is None else bar.source_sequence,
        )

    @staticmethod
    def _reject_ambiguous_stream_bars(values: tuple[tuple[datetime, StreamKey, BarEvent], ...]) -> None:
        seen: set[tuple[StreamKey, datetime]] = set()
        for _, stream, bar in values:
            key = (stream, bar.timestamp)
            if key in seen:
                raise ValueError("ambiguous duplicate BarEvent for stream")
            seen.add(key)

    @staticmethod
    def _view(
        requirement: StrategyDataRequirements,
        histories: Mapping[StreamKey, list[BarEvent]],
        updated: frozenset[StreamKey],
        decision_time: datetime,
    ) -> MarketDataView:
        return MarketDataView(
            decision_time,
            {
                subscription.stream: StreamEvidence(tuple(histories[subscription.stream]), subscription.stream in updated)
                for subscription in requirement.subscriptions
            },
        )

    @staticmethod
    def _readiness(requirement: StrategyDataRequirements, view: MarketDataView) -> DataReadiness:
        reasons = tuple(
            f"minimum_history_not_met:{subscription.stream.identity.instrument}:{subscription.stream.timeframe}"
            for subscription in requirement.subscriptions
            if len(view.history(subscription.stream)) < subscription.minimum_history
        )
        return DataReadiness(not reasons, reasons)
