"""Deterministic, broker-neutral contracts for the AlgoFortis Laya integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
import re
from typing import Mapping

from engine.reproducibility.codec import CanonicalCodec


_HASH_RE = re.compile(r"^[0-9a-f]{64}$")

ALLOWED_FAST_TASKS = frozenset({
    "REGIME_CLASSIFICATION",
    "REVERSAL_CLASSIFICATION",
    "BREAKOUT_CLASSIFICATION",
    "STRATEGY_RANKING",
    "FEATURE_SCORING",
    "SIGNAL_FILTERING",
    "CANDIDATE_PRUNING",
    "TRADE_QUALITY_SCORING",
    "RESEARCH_PRIORITY_RANKING",
})


class LayaContractError(ValueError):
    """Raised when Laya evidence is invalid or ambiguous."""


class LayaRole(str, Enum):
    MARKET_INTELLIGENCE = "MARKET_INTELLIGENCE"
    STRATEGY_HUNTING = "STRATEGY_HUNTING"
    FAST_TASKS = "FAST_TASKS"


class MarketRegime(str, Enum):
    UPTREND = "UPTREND"
    DOWNTREND = "DOWNTREND"
    SIDEWAYS = "SIDEWAYS"
    UNCERTAIN = "UNCERTAIN"


class DirectionalBias(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    UNCERTAIN = "UNCERTAIN"


class VolatilityState(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    UNCERTAIN = "UNCERTAIN"


class OpportunityIntent(str, Enum):
    CE_CANDIDATE = "CE_CANDIDATE"
    PE_CANDIDATE = "PE_CANDIDATE"


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LayaContractError(f"{name} must be a non-empty string")
    return value.strip()


def _aware(value: object, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise LayaContractError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise LayaContractError(f"{name} must be timezone-aware")
    return value


def _hash(value: object, name: str) -> str:
    normalized = _text(value, name)
    if not _HASH_RE.fullmatch(normalized):
        raise LayaContractError(f"{name} must be lowercase 64-character hex")
    return normalized


def _decimal(value: object, name: str, *, bounded: bool = False) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise LayaContractError(f"{name} must be a finite Decimal")
    if bounded and not Decimal("0") <= value <= Decimal("1"):
        raise LayaContractError(f"{name} must be between 0 and 1")
    return value


def _sorted_unique_text(values: object, name: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)):
        raise LayaContractError(f"{name} must be a tuple/list")
    normalized = tuple(_text(value, name) for value in values)
    if not allow_empty and not normalized:
        raise LayaContractError(f"{name} must not be empty")
    if len(normalized) != len(set(normalized)):
        raise LayaContractError(f"{name} must not contain duplicates")
    return tuple(sorted(normalized))


def _provenance_fields(value: "ModelProvenance") -> tuple[tuple[str, str], ...]:
    return (
        ("model_id", value.model_id),
        ("model_version", value.model_version),
        ("model_hash", value.model_hash),
        ("adapter_version", value.adapter_version),
        ("feature_schema_version", value.feature_schema_version),
    )


@dataclass(frozen=True, slots=True)
class ModelProvenance:
    model_id: str
    model_version: str
    model_hash: str
    adapter_version: str
    feature_schema_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_id", _text(self.model_id, "model_id"))
        object.__setattr__(self, "model_version", _text(self.model_version, "model_version"))
        object.__setattr__(self, "model_hash", _hash(self.model_hash, "model_hash"))
        object.__setattr__(self, "adapter_version", _text(self.adapter_version, "adapter_version"))
        object.__setattr__(self, "feature_schema_version", _text(self.feature_schema_version, "feature_schema_version"))


@dataclass(frozen=True, slots=True)
class MarketIntelligenceRequest:
    symbol: str
    timeframe: str
    event_timestamp: datetime
    features: tuple[tuple[str, Decimal], ...]
    data_lineage: str
    existing_strategy_signals: tuple[str, ...]
    fingerprint: str

    @classmethod
    def create(cls, *, symbol: str, timeframe: str, event_timestamp: datetime,
               features: Mapping[str, Decimal], data_lineage: str,
               existing_strategy_signals: tuple[str, ...] | list[str]) -> "MarketIntelligenceRequest":
        symbol = _text(symbol, "symbol").casefold()
        timeframe = _text(timeframe, "timeframe")
        event_timestamp = _aware(event_timestamp, "event_timestamp")
        data_lineage = _text(data_lineage, "data_lineage")
        if not isinstance(features, Mapping) or not features:
            raise LayaContractError("features must be a non-empty mapping")
        normalized_features: list[tuple[str, Decimal]] = []
        seen: set[str] = set()
        for raw_name, raw_value in features.items():
            name = _text(raw_name, "feature name")
            if name in seen:
                raise LayaContractError("features must not contain duplicates")
            seen.add(name)
            normalized_features.append((name, _decimal(raw_value, f"feature {name}")))
        feature_pairs = tuple(sorted(normalized_features))
        signals = _sorted_unique_text(existing_strategy_signals, "existing_strategy_signals", allow_empty=True)
        fingerprint = CanonicalCodec.fingerprint(
            "algofortis-laya-market-request/v1",
            (("symbol", symbol), ("timeframe", timeframe), ("event_timestamp", event_timestamp),
             ("features", feature_pairs), ("data_lineage", data_lineage),
             ("existing_strategy_signals", signals)),
        )
        return cls(symbol, timeframe, event_timestamp, feature_pairs, data_lineage, signals, fingerprint)


@dataclass(frozen=True, slots=True)
class MarketInsight:
    request_fingerprint: str
    regime: MarketRegime
    bias: DirectionalBias
    volatility: VolatilityState
    event_tags: tuple[str, ...]
    confidence: Decimal
    produced_at: datetime
    provenance: ModelProvenance
    fingerprint: str

    @classmethod
    def create(cls, *, request_fingerprint: str, regime: MarketRegime, bias: DirectionalBias,
               volatility: VolatilityState, event_tags: tuple[str, ...] | list[str],
               confidence: Decimal, produced_at: datetime,
               provenance: ModelProvenance) -> "MarketInsight":
        request_fingerprint = _hash(request_fingerprint, "request_fingerprint")
        try:
            regime = MarketRegime(regime)
            bias = DirectionalBias(bias)
            volatility = VolatilityState(volatility)
        except (TypeError, ValueError) as exc:
            raise LayaContractError("unsupported market insight enum value") from exc
        tags = _sorted_unique_text(event_tags, "event_tags")
        confidence = _decimal(confidence, "confidence", bounded=True)
        produced_at = _aware(produced_at, "produced_at")
        if not isinstance(provenance, ModelProvenance):
            raise LayaContractError("provenance must be ModelProvenance")
        fingerprint = CanonicalCodec.fingerprint(
            "algofortis-laya-market-insight/v1",
            (("request_fingerprint", request_fingerprint), ("regime", regime), ("bias", bias),
             ("volatility", volatility), ("event_tags", tags), ("confidence", confidence),
             ("produced_at", produced_at), ("provenance", _provenance_fields(provenance))),
        )
        return cls(request_fingerprint, regime, bias, volatility, tags, confidence, produced_at, provenance, fingerprint)


@dataclass(frozen=True, slots=True)
class OpportunityCandidate:
    source: str
    request_fingerprint: str
    insight_fingerprint: str
    symbol: str
    timeframe: str
    intent: OpportunityIntent
    setup_type: str
    evidence_tags: tuple[str, ...]
    confidence: Decimal
    valid_until: datetime
    provenance: ModelProvenance
    status: str
    fingerprint: str

    @classmethod
    def create(cls, *, request: MarketIntelligenceRequest, insight: MarketInsight,
               intent: OpportunityIntent, setup_type: str,
               evidence_tags: tuple[str, ...] | list[str], valid_until: datetime) -> "OpportunityCandidate":
        if not isinstance(request, MarketIntelligenceRequest):
            raise LayaContractError("request must be MarketIntelligenceRequest")
        if not isinstance(insight, MarketInsight):
            raise LayaContractError("insight must be MarketInsight")
        if insight.request_fingerprint != request.fingerprint:
            raise LayaContractError("insight must be bound to request")
        try:
            intent = OpportunityIntent(intent)
        except (TypeError, ValueError) as exc:
            raise LayaContractError("unsupported opportunity intent") from exc
        setup_type = _text(setup_type, "setup_type")
        tags = _sorted_unique_text(evidence_tags, "evidence_tags")
        valid_until = _aware(valid_until, "valid_until")
        if valid_until <= insight.produced_at:
            raise LayaContractError("valid_until must be after insight produced_at")
        source = "LAYA"
        status = "CANDIDATE_ONLY"
        fingerprint = CanonicalCodec.fingerprint(
            "algofortis-laya-opportunity/v1",
            (("source", source), ("request_fingerprint", request.fingerprint),
             ("insight_fingerprint", insight.fingerprint), ("symbol", request.symbol),
             ("timeframe", request.timeframe), ("intent", intent), ("setup_type", setup_type),
             ("evidence_tags", tags), ("confidence", insight.confidence), ("valid_until", valid_until),
             ("provenance", _provenance_fields(insight.provenance)), ("status", status)),
        )
        return cls(source, request.fingerprint, insight.fingerprint, request.symbol, request.timeframe,
                   intent, setup_type, tags, insight.confidence, valid_until, insight.provenance, status, fingerprint)


@dataclass(frozen=True, slots=True)
class StrategyHuntRequest:
    dataset_refs: tuple[str, ...]
    feature_schema_version: str
    allowed_strategy_families: tuple[str, ...]
    max_candidates: int
    seed: int
    fingerprint: str

    @classmethod
    def create(cls, *, dataset_refs: tuple[str, ...] | list[str], feature_schema_version: str,
               allowed_strategy_families: tuple[str, ...] | list[str], max_candidates: int,
               seed: int) -> "StrategyHuntRequest":
        datasets = _sorted_unique_text(dataset_refs, "dataset_refs")
        schema = _text(feature_schema_version, "feature_schema_version")
        families = _sorted_unique_text(allowed_strategy_families, "allowed_strategy_families")
        if isinstance(max_candidates, bool) or not isinstance(max_candidates, int) or max_candidates <= 0:
            raise LayaContractError("max_candidates must be a positive integer")
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            raise LayaContractError("seed must be a non-negative integer")
        fingerprint = CanonicalCodec.fingerprint(
            "algofortis-laya-strategy-hunt/v1",
            (("dataset_refs", datasets), ("feature_schema_version", schema),
             ("allowed_strategy_families", families), ("max_candidates", max_candidates), ("seed", seed)),
        )
        return cls(datasets, schema, families, max_candidates, seed, fingerprint)


@dataclass(frozen=True, slots=True)
class StrategyCandidate:
    hypothesis_id: str
    entry_concept: str
    exit_requirements: tuple[str, ...]
    parameter_names: tuple[str, ...]
    target_regimes: tuple[MarketRegime, ...]
    provenance: ModelProvenance
    status: str
    fingerprint: str

    @classmethod
    def create(cls, *, entry_concept: str, exit_requirements: tuple[str, ...] | list[str],
               parameter_names: tuple[str, ...] | list[str],
               target_regimes: tuple[MarketRegime, ...] | list[MarketRegime],
               provenance: ModelProvenance) -> "StrategyCandidate":
        entry_concept = _text(entry_concept, "entry_concept")
        exits = _sorted_unique_text(exit_requirements, "exit_requirements")
        parameters = _sorted_unique_text(parameter_names, "parameter_names")
        if not isinstance(target_regimes, (tuple, list)) or not target_regimes:
            raise LayaContractError("target_regimes must not be empty")
        try:
            regimes = tuple(sorted((MarketRegime(item) for item in target_regimes), key=lambda item: item.value))
        except (TypeError, ValueError) as exc:
            raise LayaContractError("unsupported target regime") from exc
        if len(regimes) != len(set(regimes)):
            raise LayaContractError("target_regimes must not contain duplicates")
        if not isinstance(provenance, ModelProvenance):
            raise LayaContractError("provenance must be ModelProvenance")
        status = "RESEARCH_ONLY"
        fingerprint = CanonicalCodec.fingerprint(
            "algofortis-laya-strategy-candidate/v1",
            (("entry_concept", entry_concept), ("exit_requirements", exits), ("parameter_names", parameters),
             ("target_regimes", regimes), ("provenance", _provenance_fields(provenance)), ("status", status)),
        )
        return cls("laya_" + fingerprint, entry_concept, exits, parameters, regimes, provenance, status, fingerprint)


@dataclass(frozen=True, slots=True)
class FastTaskRequest:
    task_kind: str
    payload: tuple[tuple[str, str], ...]
    request_timestamp: datetime
    fingerprint: str

    @classmethod
    def create(cls, *, task_kind: str, payload: tuple[tuple[str, str], ...] | list[tuple[str, str]],
               request_timestamp: datetime) -> "FastTaskRequest":
        task_kind = _text(task_kind, "task_kind")
        if task_kind not in ALLOWED_FAST_TASKS:
            raise LayaContractError("task_kind is not supported")
        if not isinstance(payload, (tuple, list)) or not payload:
            raise LayaContractError("payload must be a non-empty tuple/list")
        pairs: list[tuple[str, str]] = []
        names: set[str] = set()
        for item in payload:
            if not isinstance(item, (tuple, list)) or len(item) != 2:
                raise LayaContractError("payload entries must be key/value pairs")
            name = _text(item[0], "payload key")
            value = _text(item[1], "payload value")
            if name in names:
                raise LayaContractError("payload must not contain duplicate keys")
            names.add(name)
            pairs.append((name, value))
        normalized_payload = tuple(sorted(pairs))
        request_timestamp = _aware(request_timestamp, "request_timestamp")
        fingerprint = CanonicalCodec.fingerprint(
            "algofortis-laya-fast-request/v1",
            (("task_kind", task_kind), ("payload", normalized_payload), ("request_timestamp", request_timestamp)),
        )
        return cls(task_kind, normalized_payload, request_timestamp, fingerprint)


@dataclass(frozen=True, slots=True)
class FastTaskResult:
    task_kind: str
    request_fingerprint: str
    ranked_items: tuple[tuple[str, Decimal], ...]
    provenance: ModelProvenance
    fingerprint: str

    @classmethod
    def create(cls, *, task_kind: str, request_fingerprint: str,
               ranked_items: tuple[tuple[str, Decimal], ...] | list[tuple[str, Decimal]],
               provenance: ModelProvenance) -> "FastTaskResult":
        task_kind = _text(task_kind, "task_kind")
        if task_kind not in ALLOWED_FAST_TASKS:
            raise LayaContractError("task_kind is not supported")
        request_fingerprint = _hash(request_fingerprint, "request_fingerprint")
        if not isinstance(ranked_items, (tuple, list)) or not ranked_items:
            raise LayaContractError("ranked_items must be a non-empty tuple/list")
        normalized: list[tuple[str, Decimal]] = []
        names: set[str] = set()
        for item in ranked_items:
            if not isinstance(item, (tuple, list)) or len(item) != 2:
                raise LayaContractError("ranked_items entries must be name/score pairs")
            name = _text(item[0], "ranked item")
            if name in names:
                raise LayaContractError("ranked_items must not contain duplicate items")
            names.add(name)
            score = _decimal(item[1], "score", bounded=True)
            normalized.append((name, score))
        if not isinstance(provenance, ModelProvenance):
            raise LayaContractError("provenance must be ModelProvenance")
        ranked_tuple = tuple(normalized)
        fingerprint = CanonicalCodec.fingerprint(
            "algofortis-laya-fast-result/v1",
            (("task_kind", task_kind), ("request_fingerprint", request_fingerprint),
             ("ranked_items", ranked_tuple), ("provenance", _provenance_fields(provenance))),
        )
        return cls(task_kind, request_fingerprint, ranked_tuple, provenance, fingerprint)


__all__ = [
    "ALLOWED_FAST_TASKS", "LayaContractError", "LayaRole", "MarketRegime",
    "DirectionalBias", "VolatilityState", "OpportunityIntent", "ModelProvenance",
    "MarketIntelligenceRequest", "MarketInsight", "OpportunityCandidate",
    "StrategyHuntRequest", "StrategyCandidate", "FastTaskRequest", "FastTaskResult",
]
