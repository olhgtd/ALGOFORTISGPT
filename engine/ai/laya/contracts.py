"""Deterministic, broker-neutral contracts for AlgoFortis Laya market intelligence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
import re
from typing import Mapping

from engine.reproducibility.codec import CanonicalCodec


_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class LayaContractError(ValueError):
    """Raised when Laya market-intelligence evidence is invalid."""


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


class OpportunityView(str, Enum):
    CE_CANDIDATE = "CE_CANDIDATE"
    PE_CANDIDATE = "PE_CANDIDATE"
    NO_TRADE = "NO_TRADE"


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


def _finite_decimal(value: object, name: str, *, bounded: bool = False) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise LayaContractError(f"{name} must be a finite Decimal")
    if bounded and not Decimal("0") <= value <= Decimal("1"):
        raise LayaContractError(f"{name} must be between 0 and 1")
    return value


def _hash(value: object, name: str) -> str:
    normalized = _text(value, name).lower()
    if not _HASH_RE.fullmatch(normalized):
        raise LayaContractError(f"{name} must be lowercase 64-character hex")
    return normalized


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
    def create(
        cls,
        *,
        symbol: str,
        timeframe: str,
        event_timestamp: datetime,
        features: Mapping[str, Decimal],
        data_lineage: str,
        existing_strategy_signals: tuple[str, ...] | list[str],
    ) -> "MarketIntelligenceRequest":
        normalized_symbol = _text(symbol, "symbol").casefold()
        normalized_timeframe = _text(timeframe, "timeframe")
        timestamp = _aware(event_timestamp, "event_timestamp")
        lineage = _text(data_lineage, "data_lineage")

        if not isinstance(features, Mapping) or not features:
            raise LayaContractError("features must be a non-empty mapping")
        normalized_features: list[tuple[str, Decimal]] = []
        seen: set[str] = set()
        for raw_name, raw_value in features.items():
            name = _text(raw_name, "feature name")
            if name in seen:
                raise LayaContractError("features must not contain duplicates")
            seen.add(name)
            normalized_features.append((name, _finite_decimal(raw_value, f"feature {name}")))
        feature_pairs = tuple(sorted(normalized_features))

        if not isinstance(existing_strategy_signals, (tuple, list)):
            raise LayaContractError("existing_strategy_signals must be a tuple/list")
        signals = tuple(sorted(_text(item, "strategy signal") for item in existing_strategy_signals))
        if len(signals) != len(set(signals)):
            raise LayaContractError("existing_strategy_signals must not contain duplicates")

        fingerprint = CanonicalCodec.fingerprint(
            "algofortis-laya-market-request/v2",
            (
                ("symbol", normalized_symbol),
                ("timeframe", normalized_timeframe),
                ("event_timestamp", timestamp),
                ("features", feature_pairs),
                ("data_lineage", lineage),
                ("existing_strategy_signals", signals),
            ),
        )
        return cls(
            normalized_symbol,
            normalized_timeframe,
            timestamp,
            feature_pairs,
            lineage,
            signals,
            fingerprint,
        )


@dataclass(frozen=True, slots=True)
class LayaMarketAssessment:
    source: str
    status: str
    request_fingerprint: str
    regime: MarketRegime
    bias: DirectionalBias
    volatility: VolatilityState
    opportunity: OpportunityView
    confidence: Decimal
    produced_at: datetime
    model_ref: str
    model_hash: str
    fingerprint: str

    @classmethod
    def create(
        cls,
        *,
        request_fingerprint: str,
        regime: MarketRegime,
        bias: DirectionalBias,
        volatility: VolatilityState,
        opportunity: OpportunityView,
        confidence: Decimal,
        produced_at: datetime,
        model_ref: str,
        model_hash: str,
    ) -> "LayaMarketAssessment":
        request_fingerprint = _hash(request_fingerprint, "request_fingerprint")
        try:
            regime = MarketRegime(regime)
            bias = DirectionalBias(bias)
            volatility = VolatilityState(volatility)
            opportunity = OpportunityView(opportunity)
        except (TypeError, ValueError) as exc:
            raise LayaContractError("unsupported Laya market assessment value") from exc

        confidence = _finite_decimal(confidence, "confidence", bounded=True)
        produced_at = _aware(produced_at, "produced_at")
        model_ref = _text(model_ref, "model_ref")
        model_hash = _hash(model_hash, "model_hash")
        source = "LAYA"
        status = "SHADOW_ONLY"
        fingerprint = CanonicalCodec.fingerprint(
            "algofortis-laya-market-assessment/v1",
            (
                ("source", source),
                ("status", status),
                ("request_fingerprint", request_fingerprint),
                ("regime", regime),
                ("bias", bias),
                ("volatility", volatility),
                ("opportunity", opportunity),
                ("confidence", confidence),
                ("produced_at", produced_at),
                ("model_ref", model_ref),
                ("model_hash", model_hash),
            ),
        )
        return cls(
            source,
            status,
            request_fingerprint,
            regime,
            bias,
            volatility,
            opportunity,
            confidence,
            produced_at,
            model_ref,
            model_hash,
            fingerprint,
        )


__all__ = [
    "DirectionalBias",
    "LayaContractError",
    "LayaMarketAssessment",
    "MarketIntelligenceRequest",
    "MarketRegime",
    "OpportunityView",
    "VolatilityState",
]
