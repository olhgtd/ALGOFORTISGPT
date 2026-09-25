from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from engine.ai.laya.contracts import (
    DirectionalBias,
    LayaContractError,
    MarketInsight,
    MarketIntelligenceRequest,
    MarketRegime,
    ModelProvenance,
    OpportunityIntent,
    VolatilityState,
)
from engine.ai.laya.opportunity_engine import LayaOpportunityError, OpportunityEngine


def _provenance() -> ModelProvenance:
    return ModelProvenance(
        model_id="laya-test",
        model_version="v1",
        model_hash="a" * 64,
        adapter_version="fake@v1",
        feature_schema_version="features@v1",
    )


def _request() -> MarketIntelligenceRequest:
    return MarketIntelligenceRequest.create(
        symbol="NIFTY",
        timeframe="5m",
        event_timestamp=datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc),
        features={"atr": Decimal("42.1"), "rsi": Decimal("68.2")},
        data_lineage="dataset@v1",
        existing_strategy_signals=(),
    )


def _insight(request: MarketIntelligenceRequest, *, bias: DirectionalBias,
             tags: tuple[str, ...], confidence: str = "0.81",
             request_fingerprint: str | None = None) -> MarketInsight:
    return MarketInsight.create(
        request_fingerprint=request_fingerprint or request.fingerprint,
        regime=MarketRegime.UPTREND,
        bias=bias,
        volatility=VolatilityState.HIGH,
        event_tags=tags,
        confidence=Decimal(confidence),
        produced_at=request.event_timestamp,
        provenance=_provenance(),
    )


def test_bearish_reversal_emits_laya_only_pe_candidate_when_strategy_is_silent():
    request = _request()
    assert request.existing_strategy_signals == ()
    insight = _insight(
        request,
        bias=DirectionalBias.BEARISH,
        tags=("MOMENTUM_WEAKENING", "REVERSAL_CANDIDATE"),
    )
    candidate = OpportunityEngine(min_confidence=Decimal("0.70")).from_insight(
        request=request,
        insight=insight,
        validity_seconds=60,
    )
    assert candidate is not None
    assert candidate.source == "LAYA"
    assert candidate.intent is OpportunityIntent.PE_CANDIDATE
    assert candidate.setup_type == "REVERSAL"
    assert candidate.status == "CANDIDATE_ONLY"


def test_bullish_breakout_emits_ce_candidate():
    request = _request()
    insight = _insight(
        request,
        bias=DirectionalBias.BULLISH,
        tags=("BREAKOUT_CANDIDATE",),
    )
    candidate = OpportunityEngine(min_confidence=Decimal("0.70")).from_insight(
        request=request,
        insight=insight,
        validity_seconds=45,
    )
    assert candidate is not None
    assert candidate.intent is OpportunityIntent.CE_CANDIDATE
    assert candidate.setup_type == "BREAKOUT"


def test_low_confidence_neutral_or_irrelevant_insight_emits_no_candidate():
    request = _request()
    engine = OpportunityEngine(min_confidence=Decimal("0.70"))
    assert engine.from_insight(
        request=request,
        insight=_insight(request, bias=DirectionalBias.BEARISH,
                         tags=("REVERSAL_CANDIDATE",), confidence="0.69"),
        validity_seconds=60,
    ) is None
    assert engine.from_insight(
        request=request,
        insight=_insight(request, bias=DirectionalBias.NEUTRAL,
                         tags=("REVERSAL_CANDIDATE",)),
        validity_seconds=60,
    ) is None
    assert engine.from_insight(
        request=request,
        insight=_insight(request, bias=DirectionalBias.BEARISH, tags=("TREND",)),
        validity_seconds=60,
    ) is None


def test_opportunity_engine_rejects_unbound_insight_before_candidate_creation():
    request = _request()
    insight = _insight(
        request,
        bias=DirectionalBias.BEARISH,
        tags=("REVERSAL_CANDIDATE",),
        request_fingerprint="b" * 64,
    )
    with pytest.raises(LayaOpportunityError, match="bound"):
        OpportunityEngine(min_confidence=Decimal("0.70")).from_insight(
            request=request,
            insight=insight,
            validity_seconds=60,
        )


def test_opportunity_engine_rejects_invalid_threshold_and_validity():
    for threshold in (Decimal("NaN"), Decimal("-0.01"), Decimal("1.01")):
        with pytest.raises(LayaOpportunityError, match="min_confidence"):
            OpportunityEngine(min_confidence=threshold)

    request = _request()
    insight = _insight(
        request,
        bias=DirectionalBias.BEARISH,
        tags=("REVERSAL_CANDIDATE",),
    )
    with pytest.raises(LayaOpportunityError, match="validity_seconds"):
        OpportunityEngine(min_confidence=Decimal("0.70")).from_insight(
            request=request,
            insight=insight,
            validity_seconds=0,
        )
