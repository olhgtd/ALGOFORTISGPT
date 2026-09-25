from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from engine.ai.laya.contracts import (
    ALLOWED_FAST_TASKS,
    DirectionalBias,
    FastTaskRequest,
    FastTaskResult,
    LayaContractError,
    LayaRole,
    MarketInsight,
    MarketIntelligenceRequest,
    MarketRegime,
    ModelProvenance,
    OpportunityCandidate,
    OpportunityIntent,
    StrategyCandidate,
    StrategyHuntRequest,
    VolatilityState,
)


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
        features={"atr": Decimal("42.1"), "rsi": Decimal("61.2")},
        data_lineage="dataset@v1",
        existing_strategy_signals=(),
    )


def _insight(request: MarketIntelligenceRequest) -> MarketInsight:
    return MarketInsight.create(
        request_fingerprint=request.fingerprint,
        regime=MarketRegime.UPTREND,
        bias=DirectionalBias.BEARISH,
        volatility=VolatilityState.HIGH,
        event_tags=("REVERSAL_CANDIDATE",),
        confidence=Decimal("0.81"),
        produced_at=request.event_timestamp,
        provenance=_provenance(),
    )


def test_market_request_fingerprint_is_deterministic_across_feature_order_and_symbol_case():
    now = datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc)
    first = MarketIntelligenceRequest.create(
        symbol="NIFTY",
        timeframe="5m",
        event_timestamp=now,
        features={"rsi": Decimal("61.2"), "atr": Decimal("42.1")},
        data_lineage="dataset@v1",
        existing_strategy_signals=("orb@2.0.0",),
    )
    second = MarketIntelligenceRequest.create(
        symbol="nifty",
        timeframe="5m",
        event_timestamp=now,
        features={"atr": Decimal("42.1"), "rsi": Decimal("61.2")},
        data_lineage="dataset@v1",
        existing_strategy_signals=("orb@2.0.0",),
    )

    assert first.fingerprint == second.fingerprint
    assert first.symbol == second.symbol == "nifty"
    assert first.features == (("atr", Decimal("42.1")), ("rsi", Decimal("61.2")))


def test_market_request_rejects_naive_time_invalid_features_and_duplicate_strategy_signals():
    with pytest.raises(LayaContractError, match="timezone-aware"):
        MarketIntelligenceRequest.create(
            symbol="NIFTY",
            timeframe="5m",
            event_timestamp=datetime(2026, 1, 5, 9, 30),
            features={"atr": Decimal("42")},
            data_lineage="dataset@v1",
            existing_strategy_signals=(),
        )
    with pytest.raises(LayaContractError, match="finite Decimal"):
        MarketIntelligenceRequest.create(
            symbol="NIFTY",
            timeframe="5m",
            event_timestamp=datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc),
            features={"atr": Decimal("NaN")},
            data_lineage="dataset@v1",
            existing_strategy_signals=(),
        )
    with pytest.raises(LayaContractError, match="duplicates"):
        MarketIntelligenceRequest.create(
            symbol="NIFTY",
            timeframe="5m",
            event_timestamp=datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc),
            features={"atr": Decimal("42")},
            data_lineage="dataset@v1",
            existing_strategy_signals=("orb", "orb"),
        )


def test_model_provenance_rejects_invalid_hash_and_blank_versions():
    with pytest.raises(LayaContractError, match="model_hash"):
        ModelProvenance(
            model_id="laya-test",
            model_version="v1",
            model_hash="not-a-hash",
            adapter_version="fake@v1",
            feature_schema_version="features@v1",
        )
    with pytest.raises(LayaContractError, match="adapter_version"):
        ModelProvenance(
            model_id="laya-test",
            model_version="v1",
            model_hash="a" * 64,
            adapter_version=" ",
            feature_schema_version="features@v1",
        )


def test_market_insight_is_deterministic_and_rejects_invalid_confidence():
    request = _request()
    first = MarketInsight.create(
        request_fingerprint=request.fingerprint,
        regime=MarketRegime.UPTREND,
        bias=DirectionalBias.BEARISH,
        volatility=VolatilityState.HIGH,
        event_tags=("REVERSAL_CANDIDATE", "MOMENTUM_WEAKENING"),
        confidence=Decimal("0.81"),
        produced_at=request.event_timestamp,
        provenance=_provenance(),
    )
    second = MarketInsight.create(
        request_fingerprint=request.fingerprint,
        regime=MarketRegime.UPTREND,
        bias=DirectionalBias.BEARISH,
        volatility=VolatilityState.HIGH,
        event_tags=("MOMENTUM_WEAKENING", "REVERSAL_CANDIDATE"),
        confidence=Decimal("0.81"),
        produced_at=request.event_timestamp,
        provenance=_provenance(),
    )
    assert first.fingerprint == second.fingerprint
    assert first.event_tags == ("MOMENTUM_WEAKENING", "REVERSAL_CANDIDATE")

    for value in (Decimal("NaN"), Decimal("Infinity"), Decimal("-0.01"), Decimal("1.01")):
        with pytest.raises(LayaContractError, match="confidence"):
            MarketInsight.create(
                request_fingerprint=request.fingerprint,
                regime=MarketRegime.UPTREND,
                bias=DirectionalBias.BULLISH,
                volatility=VolatilityState.NORMAL,
                event_tags=("TREND",),
                confidence=value,
                produced_at=request.event_timestamp,
                provenance=_provenance(),
            )


def test_opportunity_candidate_is_laya_candidate_only_and_has_no_execution_fields():
    request = _request()
    insight = _insight(request)
    candidate = OpportunityCandidate.create(
        request=request,
        insight=insight,
        intent=OpportunityIntent.PE_CANDIDATE,
        setup_type="REVERSAL",
        evidence_tags=("REVERSAL_CANDIDATE",),
        valid_until=insight.produced_at + timedelta(seconds=60),
    )

    assert candidate.source == "LAYA"
    assert candidate.status == "CANDIDATE_ONLY"
    assert candidate.request_fingerprint == request.fingerprint
    assert candidate.insight_fingerprint == insight.fingerprint
    assert candidate.confidence == insight.confidence
    assert candidate.provenance == insight.provenance
    forbidden_fields = {"broker", "broker_id", "quantity", "price", "order_type", "order_id"}
    assert forbidden_fields.isdisjoint(OpportunityCandidate.__dataclass_fields__)


def test_opportunity_candidate_rejects_unbound_insight_and_invalid_expiry():
    request = _request()
    insight = MarketInsight.create(
        request_fingerprint="b" * 64,
        regime=MarketRegime.UPTREND,
        bias=DirectionalBias.BEARISH,
        volatility=VolatilityState.HIGH,
        event_tags=("REVERSAL_CANDIDATE",),
        confidence=Decimal("0.81"),
        produced_at=request.event_timestamp,
        provenance=_provenance(),
    )
    with pytest.raises(LayaContractError, match="bound"):
        OpportunityCandidate.create(
            request=request,
            insight=insight,
            intent=OpportunityIntent.PE_CANDIDATE,
            setup_type="REVERSAL",
            evidence_tags=("REVERSAL_CANDIDATE",),
            valid_until=request.event_timestamp + timedelta(seconds=60),
        )

    bound = _insight(request)
    with pytest.raises(LayaContractError, match="valid_until"):
        OpportunityCandidate.create(
            request=request,
            insight=bound,
            intent=OpportunityIntent.PE_CANDIDATE,
            setup_type="REVERSAL",
            evidence_tags=("REVERSAL_CANDIDATE",),
            valid_until=bound.produced_at,
        )


def test_strategy_hunt_request_and_candidate_are_deterministic_and_research_only():
    first = StrategyHuntRequest.create(
        dataset_refs=("nifty@v2", "banknifty@v1"),
        feature_schema_version="features@v1",
        allowed_strategy_families=("ORB", "BREAKOUT"),
        max_candidates=3,
        seed=7,
    )
    second = StrategyHuntRequest.create(
        dataset_refs=("banknifty@v1", "nifty@v2"),
        feature_schema_version="features@v1",
        allowed_strategy_families=("BREAKOUT", "ORB"),
        max_candidates=3,
        seed=7,
    )
    assert first.fingerprint == second.fingerprint

    candidate = StrategyCandidate.create(
        entry_concept="breakout after range compression",
        exit_requirements=("versioned protective policy",),
        parameter_names=("lookback", "volume_multiplier"),
        target_regimes=(MarketRegime.UPTREND, MarketRegime.SIDEWAYS),
        provenance=_provenance(),
    )
    assert candidate.hypothesis_id.startswith("laya_")
    assert candidate.status == "RESEARCH_ONLY"


def test_strategy_hunt_request_rejects_invalid_budget_and_seed():
    with pytest.raises(LayaContractError, match="max_candidates"):
        StrategyHuntRequest.create(
            dataset_refs=("nifty@v2",),
            feature_schema_version="features@v1",
            allowed_strategy_families=("ORB",),
            max_candidates=0,
            seed=7,
        )
    with pytest.raises(LayaContractError, match="seed"):
        StrategyHuntRequest.create(
            dataset_refs=("nifty@v2",),
            feature_schema_version="features@v1",
            allowed_strategy_families=("ORB",),
            max_candidates=1,
            seed=-1,
        )


def test_fast_task_contracts_are_bounded_deterministic_and_request_bound():
    assert "PLACE_ORDER" not in ALLOWED_FAST_TASKS
    assert set(ALLOWED_FAST_TASKS) == {
        "REGIME_CLASSIFICATION",
        "REVERSAL_CLASSIFICATION",
        "BREAKOUT_CLASSIFICATION",
        "STRATEGY_RANKING",
        "FEATURE_SCORING",
        "SIGNAL_FILTERING",
        "CANDIDATE_PRUNING",
        "TRADE_QUALITY_SCORING",
        "RESEARCH_PRIORITY_RANKING",
    }
    now = datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc)
    first = FastTaskRequest.create(
        task_kind="FEATURE_SCORING",
        payload=(("b", "2"), ("a", "1")),
        request_timestamp=now,
    )
    second = FastTaskRequest.create(
        task_kind="FEATURE_SCORING",
        payload=(("a", "1"), ("b", "2")),
        request_timestamp=now,
    )
    assert first.fingerprint == second.fingerprint

    result = FastTaskResult.create(
        task_kind=first.task_kind,
        request_fingerprint=first.fingerprint,
        ranked_items=(("atr", Decimal("0.8")), ("rsi", Decimal("0.7"))),
        provenance=_provenance(),
    )
    assert result.request_fingerprint == first.fingerprint
    assert result.ranked_items == (("atr", Decimal("0.8")), ("rsi", Decimal("0.7")))


def test_fast_task_request_rejects_unknown_kind_and_nonaware_time():
    with pytest.raises(LayaContractError, match="task_kind"):
        FastTaskRequest.create(
            task_kind="PLACE_ORDER",
            payload=(("symbol", "NIFTY"),),
            request_timestamp=datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc),
        )
    with pytest.raises(LayaContractError, match="timezone-aware"):
        FastTaskRequest.create(
            task_kind="FEATURE_SCORING",
            payload=(("symbol", "NIFTY"),),
            request_timestamp=datetime(2026, 1, 5, 9, 30),
        )


def test_fast_task_result_rejects_duplicate_items_and_out_of_range_scores():
    request = FastTaskRequest.create(
        task_kind="FEATURE_SCORING",
        payload=(("symbol", "NIFTY"),),
        request_timestamp=datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc),
    )
    with pytest.raises(LayaContractError, match="duplicate"):
        FastTaskResult.create(
            task_kind=request.task_kind,
            request_fingerprint=request.fingerprint,
            ranked_items=(("atr", Decimal("0.8")), ("atr", Decimal("0.7"))),
            provenance=_provenance(),
        )
    with pytest.raises(LayaContractError, match="score"):
        FastTaskResult.create(
            task_kind=request.task_kind,
            request_fingerprint=request.fingerprint,
            ranked_items=(("atr", Decimal("1.1")),),
            provenance=_provenance(),
        )


def test_role_and_enum_values_are_explicit_and_stable():
    assert tuple(role.value for role in LayaRole) == (
        "MARKET_INTELLIGENCE",
        "STRATEGY_HUNTING",
        "FAST_TASKS",
    )
    assert tuple(regime.value for regime in MarketRegime) == (
        "UPTREND",
        "DOWNTREND",
        "SIDEWAYS",
        "UNCERTAIN",
    )
