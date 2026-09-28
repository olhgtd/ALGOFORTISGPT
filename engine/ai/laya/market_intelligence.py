"""Freshness-gated, shadow-only Laya market intelligence."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Mapping

from engine.ai.laya.contracts import (
    DirectionalBias,
    LayaMarketAssessment,
    MarketIntelligenceRequest,
    MarketRegime,
    OpportunityView,
    VolatilityState,
)
from engine.ai.laya.questions import market_questions
from engine.ai.laya.runtime import LayaRuntime


class LayaMarketError(ValueError):
    """Raised when market intelligence input/output is unsafe or malformed."""


def _choice_answer(
    answers: Mapping[str, object],
    key: str,
) -> tuple[str, Decimal]:
    raw = answers.get(key)
    if not isinstance(raw, Mapping):
        raise LayaMarketError(f"malformed Laya output: missing {key}")
    choice = raw.get("choice")
    confidence = raw.get("confidence")
    if not isinstance(choice, str) or not choice.strip():
        raise LayaMarketError(f"malformed Laya output: invalid {key} choice")
    try:
        confidence_decimal = Decimal(str(confidence))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise LayaMarketError(f"malformed Laya output: invalid {key} confidence") from exc
    if not confidence_decimal.is_finite() or not Decimal("0") <= confidence_decimal <= Decimal("1"):
        raise LayaMarketError(f"malformed Laya output: invalid {key} confidence")
    return choice.strip().upper(), confidence_decimal


class MarketIntelligenceService:
    """Validate freshness, invoke local Laya, and emit auditable shadow evidence."""

    def __init__(
        self,
        *,
        runtime: LayaRuntime,
        max_input_age_seconds: int,
        model_ref: str,
        model_hash: str,
    ) -> None:
        if not hasattr(runtime, "predict"):
            raise TypeError("runtime must provide predict(state, questions)")
        if (
            isinstance(max_input_age_seconds, bool)
            or not isinstance(max_input_age_seconds, int)
            or max_input_age_seconds <= 0
        ):
            raise LayaMarketError("max_input_age_seconds must be positive")
        if not isinstance(model_ref, str) or not model_ref.strip():
            raise LayaMarketError("model_ref must be non-empty")
        if not isinstance(model_hash, str) or len(model_hash) != 64:
            raise LayaMarketError("model_hash must be 64-character hex")
        self._runtime = runtime
        self._max_input_age = timedelta(seconds=max_input_age_seconds)
        self._model_ref = model_ref.strip()
        self._model_hash = model_hash.lower()

    def analyze(
        self,
        request: MarketIntelligenceRequest,
        *,
        observed_at: datetime,
    ) -> LayaMarketAssessment:
        if not isinstance(request, MarketIntelligenceRequest):
            raise TypeError("request must be MarketIntelligenceRequest")
        if not isinstance(observed_at, datetime):
            raise LayaMarketError("observed_at must be a datetime")
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise LayaMarketError("observed_at must be timezone-aware")

        future_skew = request.event_timestamp - observed_at
        if future_skew > timedelta(seconds=5):
            raise LayaMarketError("market input is from the future")
        if observed_at - request.event_timestamp > self._max_input_age:
            raise LayaMarketError("market input is stale")

        state = {
            "symbol": request.symbol,
            "timeframe": request.timeframe,
            "event_timestamp": request.event_timestamp.isoformat(),
            "features": {name: str(value) for name, value in request.features},
            "data_lineage": request.data_lineage,
            "existing_strategy_signals": list(request.existing_strategy_signals),
        }
        result = self._runtime.predict(state, market_questions())
        if not isinstance(result, Mapping):
            raise LayaMarketError("malformed Laya output")
        answers = result.get("answers")
        if not isinstance(answers, Mapping):
            raise LayaMarketError("malformed Laya output: answers missing")

        regime_raw, regime_conf = _choice_answer(answers, "regime")
        bias_raw, bias_conf = _choice_answer(answers, "bias")
        volatility_raw, volatility_conf = _choice_answer(answers, "volatility")
        opportunity_raw, opportunity_conf = _choice_answer(answers, "opportunity")
        confidence = min(regime_conf, bias_conf, volatility_conf, opportunity_conf)

        try:
            regime = MarketRegime(regime_raw)
            bias = DirectionalBias(bias_raw)
            volatility = VolatilityState(volatility_raw)
            opportunity = OpportunityView(opportunity_raw)
        except ValueError as exc:
            raise LayaMarketError("malformed Laya output: unsupported choice") from exc

        return LayaMarketAssessment.create(
            request_fingerprint=request.fingerprint,
            regime=regime,
            bias=bias,
            volatility=volatility,
            opportunity=opportunity,
            confidence=confidence,
            produced_at=observed_at,
            model_ref=self._model_ref,
            model_hash=self._model_hash,
        )


__all__ = ["LayaMarketError", "MarketIntelligenceService"]
