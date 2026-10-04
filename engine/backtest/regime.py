"""Single-owner, completed-bar RegimePolicy/v1 evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from enum import Enum

from engine.backtest.engine import BarEvent
from engine.market import StreamKey
from engine.portfolio.model import INTERNAL_DECIMAL_CONTEXT
from engine.reproducibility.codec import CanonicalCodec
from engine.trades import LedgerEventKey


class Regime(str, Enum):
    TRENDING = "TRENDING"
    SIDEWAYS = "SIDEWAYS"
    VOLATILE = "VOLATILE"


class RegimeStatus(str, Enum):
    CLASSIFIED = "CLASSIFIED"
    UNCLASSIFIED_WARMUP = "UNCLASSIFIED_WARMUP"


REGIME_POLICY_ID = "RegimePolicy/v1"


@dataclass(frozen=True)
class RegimeEvidence:
    stream: StreamKey
    timestamp: datetime
    status: RegimeStatus
    regime: Regime | None
    adx: Decimal | None
    normalized_atr: Decimal | None
    volatility_threshold: Decimal | None
    eligible_real_observations: int

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("regime timestamp must be timezone-aware")
        if self.status is RegimeStatus.CLASSIFIED and self.regime is None:
            raise ValueError("classified evidence requires regime")
        if self.status is RegimeStatus.UNCLASSIFIED_WARMUP and self.regime is not None:
            raise ValueError("warm-up evidence has no taxonomy value")

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-regime-evidence/v2",
            (("policy", REGIME_POLICY_ID), *_stream_identity_fields(self.stream),
             ("timestamp", self.timestamp), ("status", self.status.value),
             ("regime", None if self.regime is None else self.regime.value),
             ("adx", self.adx), ("normalized_atr", self.normalized_atr),
             ("threshold", self.volatility_threshold),
             ("observations", self.eligible_real_observations)),
        )


@dataclass(frozen=True)
class EntryRegimeSnapshot:
    """Immutable entry-time binding to classifier-produced regime evidence."""

    entry_event_key: LedgerEventKey
    stream: StreamKey
    fill_timestamp: datetime
    policy_identity: str
    regime_status: RegimeStatus
    regime: Regime | None
    source_evidence_fingerprint: str
    schema_version: str = "EntryRegimeSnapshot/v1"
    account_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.entry_event_key, LedgerEventKey) or not isinstance(self.stream, StreamKey):
            raise TypeError("entry_event_key and stream are required")
        if self.fill_timestamp.tzinfo is None or self.fill_timestamp.utcoffset() is None:
            raise ValueError("fill_timestamp must be timezone-aware")
        if self.policy_identity != REGIME_POLICY_ID:
            raise ValueError("entry snapshot must bind RegimePolicy/v1")
        object.__setattr__(self, "regime_status", RegimeStatus(self.regime_status))
        if self.regime is not None:
            object.__setattr__(self, "regime", Regime(self.regime))
        if self.regime_status is RegimeStatus.CLASSIFIED and self.regime is None:
            raise ValueError("classified entry snapshot requires taxonomy value")
        if self.regime_status is RegimeStatus.UNCLASSIFIED_WARMUP and self.regime is not None:
            raise ValueError("warm-up entry snapshot cannot have taxonomy value")
        if not isinstance(self.source_evidence_fingerprint, str) or not self.source_evidence_fingerprint:
            raise ValueError("source_evidence_fingerprint must be non-empty")
        if self.schema_version not in {"EntryRegimeSnapshot/v1", "EntryRegimeSnapshot/v2"}:
            raise ValueError("entry snapshot schema_version is unsupported")
        if self.schema_version == "EntryRegimeSnapshot/v2":
            if not isinstance(self.account_id, str) or not self.account_id.strip():
                raise ValueError("v2 entry snapshot requires account_id")
            object.__setattr__(self, "account_id", self.account_id.strip())
        elif self.account_id is not None:
            raise ValueError("v1 entry snapshot cannot carry account_id")

    @property
    def fingerprint(self) -> str:
        if self.schema_version == "EntryRegimeSnapshot/v1":
            return CanonicalCodec.fingerprint(
                "algofortis-entry-regime-snapshot/v1",
                (("schema_version", self.schema_version),
                 ("entry_run_id", self.entry_event_key.run_id),
                 ("entry_sequence", self.entry_event_key.accounting_sequence),
                 *_stream_identity_fields(self.stream), ("fill", self.fill_timestamp),
                 ("policy", self.policy_identity), ("status", self.regime_status.value),
                 ("regime", None if self.regime is None else self.regime.value),
                 ("source", self.source_evidence_fingerprint)),
            )
        return CanonicalCodec.fingerprint(
            "algofortis-entry-regime-snapshot/v2",
            (("schema_version", self.schema_version),
             ("account_id", self.account_id),
             ("entry_run_id", self.entry_event_key.run_id),
             ("entry_sequence", self.entry_event_key.accounting_sequence),
             *_stream_identity_fields(self.stream), ("fill", self.fill_timestamp),
             ("policy", self.policy_identity), ("status", self.regime_status.value),
             ("regime", None if self.regime is None else self.regime.value),
             ("source", self.source_evidence_fingerprint)),
        )


def entry_regime_evidence_fingerprint(values: tuple[EntryRegimeSnapshot, ...] | list[EntryRegimeSnapshot]) -> str:
    """Canonical result-side identity for persisted entry regime evidence."""
    snapshots = tuple(values)
    if not all(isinstance(value, EntryRegimeSnapshot) for value in snapshots):
        raise TypeError("values must contain EntryRegimeSnapshot")
    if all(value.schema_version == "EntryRegimeSnapshot/v1" for value in snapshots):
        ordered_v1 = sorted(snapshots, key=lambda value: (value.entry_event_key.run_id, value.entry_event_key.accounting_sequence))
        if len({value.entry_event_key for value in ordered_v1}) != len(ordered_v1):
            raise ValueError("duplicate entry regime snapshot is ambiguous")
        return CanonicalCodec.fingerprint(
            "algofortis-entry-regime-evidence/v1",
            (("snapshots", tuple(value.fingerprint for value in ordered_v1)),),
        )
    ordered = sorted(snapshots, key=lambda value: (value.entry_event_key.run_id, value.entry_event_key.accounting_sequence, "" if value.account_id is None else value.account_id))
    if len({(value.entry_event_key, value.account_id) for value in ordered}) != len(ordered):
        raise ValueError("duplicate entry regime snapshot is ambiguous")
    return CanonicalCodec.fingerprint(
        "algofortis-entry-regime-evidence/v2",
        (("snapshots", tuple(value.fingerprint for value in ordered)),),
    )


def _stream_identity_fields(stream: StreamKey) -> tuple[tuple[str, object], ...]:
    """Use the stored canonical StreamKey identity without local recasing."""
    identity = stream.identity
    return (
        ("market", identity.market), ("instrument", identity.instrument),
        ("segment", identity.segment), ("underlying", identity.underlying),
        ("expiry", identity.expiry), ("strike", identity.strike),
        ("option_type", identity.option_type), ("timeframe", stream.timeframe),
    )


class RegimeClassifier:
    """Wilder ADX/ATR stream-local classifier; synthetic bars never update it."""

    def __init__(self) -> None:
        self._bars: dict[StreamKey, list[BarEvent]] = {}
        self._evidence: dict[StreamKey, list[RegimeEvidence]] = {}

    @staticmethod
    def nearest_rank(values: list[Decimal], percentile: int = 80) -> Decimal:
        if not values or not 0 < percentile <= 100:
            raise ValueError("nearest-rank requires non-empty values and valid percentile")
        ordered = sorted(values)
        rank = (len(ordered) * percentile + 99) // 100
        return ordered[rank - 1]

    def update(self, stream: StreamKey, bar: BarEvent) -> RegimeEvidence | None:
        if not isinstance(stream, StreamKey) or not isinstance(bar, BarEvent):
            raise TypeError("stream and completed bar are required")
        if bar.symbol.upper() != stream.identity.instrument or bar.timeframe != stream.timeframe:
            raise ValueError("bar does not match regime stream")
        if bar.is_synthetic:
            return None
        bars = self._bars.setdefault(stream, [])
        if bars and bar.timestamp <= bars[-1].timestamp:
            raise ValueError("regime bars must be strictly chronological")
        bars.append(bar)
        evidence = self._classify(stream, bars)
        self._evidence.setdefault(stream, []).append(evidence)
        return evidence

    def latest_before(self, stream: StreamKey, timestamp: datetime) -> RegimeEvidence | None:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("fill timestamp must be timezone-aware")
        values = self._evidence.get(stream, ())
        return next((value for value in reversed(values) if value.timestamp < timestamp), None)

    @property
    def evidence(self) -> tuple[RegimeEvidence, ...]:
        """Immutable, canonically ordered authoritative classifier output.

        The classifier is the only component that creates these records.
        Consumers receive this completed-bar evidence unchanged and must not
        reconstruct a regime from raw OHLCV data.
        """
        values = tuple(value for stream_values in self._evidence.values() for value in stream_values)
        return tuple(sorted(values, key=lambda value: (
            value.timestamp,
            value.stream.timeframe,
            value.stream.identity.market,
            value.stream.identity.instrument,
            value.stream.identity.segment,
            "" if value.stream.identity.underlying is None else value.stream.identity.underlying,
            "" if value.stream.identity.expiry is None else value.stream.identity.expiry.isoformat(),
            "" if value.stream.identity.strike is None else str(value.stream.identity.strike),
            "" if value.stream.identity.option_type is None else value.stream.identity.option_type,
        )))

    @property
    def evidence_fingerprint(self) -> str:
        """One deterministic result-side identity for all classified streams."""
        values = tuple(value.fingerprint for value in self.evidence)
        return CanonicalCodec.fingerprint("algofortis-regime-evidence-aggregate/v2", (("evidence", values),))

    def _classify(self, stream: StreamKey, bars: list[BarEvent]) -> RegimeEvidence:
        count = len(bars)
        if count < 100:
            return RegimeEvidence(stream, bars[-1].timestamp, RegimeStatus.UNCLASSIFIED_WARMUP, None, None, None, None, count)
        atrs, adx = self._wilder(bars)
        normalized = [atr / bar.close for atr, bar in zip(atrs, bars)]
        current_atr, current_adx = normalized[-1], adx[-1]
        if current_adx is None:
            return RegimeEvidence(stream, bars[-1].timestamp, RegimeStatus.UNCLASSIFIED_WARMUP, None, None, current_atr, None, count)
        threshold = self.nearest_rank(normalized[-100:])
        regime = Regime.VOLATILE if current_atr >= threshold else (Regime.TRENDING if current_adx >= Decimal("25") else Regime.SIDEWAYS)
        return RegimeEvidence(stream, bars[-1].timestamp, RegimeStatus.CLASSIFIED, regime, current_adx, current_atr, threshold, count)

    @staticmethod
    def _wilder(bars: list[BarEvent]) -> tuple[list[Decimal], list[Decimal | None]]:
        period = Decimal("14")
        trs: list[Decimal] = [bars[0].high - bars[0].low]
        plus: list[Decimal] = [Decimal("0")]; minus: list[Decimal] = [Decimal("0")]
        for prior, current in zip(bars, bars[1:]):
            trs.append(max(current.high - current.low, abs(current.high - prior.close), abs(current.low - prior.close)))
            up, down = current.high - prior.high, prior.low - current.low
            plus.append(up if up > down and up > 0 else Decimal("0")); minus.append(down if down > up and down > 0 else Decimal("0"))
        atrs: list[Decimal] = []; adx: list[Decimal | None] = []; atr = p = m = None; dxs: list[Decimal] = []; current_adx = None
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            for index, (tr, pdm, mdm) in enumerate(zip(trs, plus, minus)):
                if index < 13:
                    atrs.append(sum(trs[:index + 1]) / Decimal(index + 1)); adx.append(None); continue
                if index == 13:
                    atr, p, m = sum(trs[:14]) / period, sum(plus[:14]) / period, sum(minus[:14]) / period
                else:
                    atr = (atr * Decimal("13") + tr) / period; p = (p * Decimal("13") + pdm) / period; m = (m * Decimal("13") + mdm) / period
                atrs.append(atr)
                denominator = p + m
                dx = Decimal("0") if denominator == 0 else Decimal("100") * abs(p - m) / denominator
                dxs.append(dx)
                if len(dxs) == 14: current_adx = sum(dxs) / period
                elif len(dxs) > 14: current_adx = (current_adx * Decimal("13") + dx) / period
                adx.append(current_adx)
        return atrs, adx
