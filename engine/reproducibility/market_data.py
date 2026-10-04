"""D3 canonical market-data stream and snapshot identities."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from engine.backtest.engine import BarEvent
from engine.market import StreamKey
from engine.reproducibility.codec import CanonicalCodec


def _instrument_fields(stream: StreamKey) -> tuple[tuple[str, object], ...]:
    identity = stream.identity
    return (
        ("market", identity.market), ("instrument", identity.instrument),
        ("segment", identity.segment), ("underlying", identity.underlying),
        ("expiry", identity.expiry), ("strike", identity.strike),
        ("option_type", identity.option_type), ("timeframe", stream.timeframe),
    )


@dataclass(frozen=True)
class MarketDataPolicy:
    version: str
    normalization_identity: str
    interpretation_identity: str

    def __post_init__(self) -> None:
        for name in ("version", "normalization_identity", "interpretation_identity"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be non-empty")
        object.__setattr__(
            self,
            "normalization_identity",
            self.normalization_identity
            if self.normalization_identity.endswith("|InstrumentIdentityCasePolicy/v1")
            else f"{self.normalization_identity}|InstrumentIdentityCasePolicy/v1",
        )

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-market-data-policy/v1",
            (("version", self.version), ("normalization", self.normalization_identity), ("interpretation", self.interpretation_identity)),
        )


@dataclass(frozen=True)
class MarketDataStream:
    stream: StreamKey
    bars: tuple[BarEvent, ...]
    policy: MarketDataPolicy

    def __post_init__(self) -> None:
        if not isinstance(self.stream, StreamKey) or not isinstance(self.policy, MarketDataPolicy):
            raise TypeError("stream and policy must be Slice 9/Slice 12 contracts")
        bars = tuple(self.bars)
        if not bars or not all(isinstance(bar, BarEvent) for bar in bars):
            raise ValueError("market stream requires completed BarEvent evidence")
        for bar in bars:
            if bar.timeframe != self.stream.timeframe or bar.symbol.upper() != self.stream.identity.instrument:
                raise ValueError("BarEvent does not match its authoritative stream")
        ordered = tuple(sorted(bars, key=lambda bar: (CanonicalCodec.timestamp_text(bar.timestamp), -1 if bar.source_sequence is None else bar.source_sequence)))
        if len({CanonicalCodec.timestamp_text(bar.timestamp) for bar in ordered}) != len(ordered):
            raise ValueError("ambiguous duplicate market bar timestamp")
        object.__setattr__(self, "bars", ordered)

    @property
    def fingerprint(self) -> str:
        bars = tuple(
            (
                CanonicalCodec.timestamp_text(bar.timestamp), bar.timeframe,
                Decimal(bar.open), Decimal(bar.high), Decimal(bar.low), Decimal(bar.close), Decimal(bar.volume),
                bar.is_synthetic,
            )
            for bar in self.bars
        )
        return CanonicalCodec.fingerprint(
            "algofortis-market-data-stream/v1",
            (("stream", tuple(value for _, value in _instrument_fields(self.stream))), ("policy", self.policy.fingerprint), ("bars", bars)),
        )


@dataclass(frozen=True)
class MarketDataSnapshot:
    policy: MarketDataPolicy
    streams: tuple[MarketDataStream, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.policy, MarketDataPolicy):
            raise TypeError("policy must be MarketDataPolicy")
        values = tuple(self.streams)
        if not values or not all(isinstance(item, MarketDataStream) for item in values):
            raise ValueError("snapshot requires market streams")
        if any(item.policy != self.policy for item in values):
            raise ValueError("all market streams must use the snapshot policy")
        ordered = tuple(sorted(values, key=lambda item: (tuple(value for _, value in _instrument_fields(item.stream)), item.fingerprint)))
        if len({tuple(value for _, value in _instrument_fields(item.stream)) for item in ordered}) != len(ordered):
            raise ValueError("duplicate snapshot stream is ambiguous")
        object.__setattr__(self, "streams", ordered)

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-market-data-snapshot/v1",
            (("policy", self.policy.fingerprint), ("streams", tuple(item.fingerprint for item in self.streams))),
        )
