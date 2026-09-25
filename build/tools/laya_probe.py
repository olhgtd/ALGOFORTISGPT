"""Deterministic, non-executable Laya integration qualification probe."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from engine.ai.laya.config import LayaConfig
from engine.ai.laya.contracts import (
    DirectionalBias,
    FastTaskRequest,
    FastTaskResult,
    LayaRole,
    MarketInsight,
    MarketIntelligenceRequest,
    MarketRegime,
    ModelProvenance,
    StrategyCandidate,
    StrategyHuntRequest,
    VolatilityState,
)
from engine.ai.laya.market_intelligence import MarketIntelligenceService
from engine.ai.laya.model_registry import LayaModelRegistry, RegisteredLayaModel
from engine.ai.laya.opportunity_engine import OpportunityEngine
from engine.ai.laya.router import LayaRouter


_EVENT_AT = datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc)
_OBSERVED_AT = _EVENT_AT + timedelta(seconds=15)
_PROVENANCE = ModelProvenance(
    model_id="laya-test",
    model_version="v1",
    model_hash="a" * 64,
    adapter_version="fake@v1",
    feature_schema_version="features@v1",
)


class _DeterministicFakeAdapter:
    """Fixed test-only adapter. It performs no model, network, broker, or Live work."""

    adapter_version = "fake@v1"

    def market_intelligence(self, request: MarketIntelligenceRequest) -> MarketInsight:
        return MarketInsight.create(
            request_fingerprint=request.fingerprint,
            regime=MarketRegime.UPTREND,
            bias=DirectionalBias.BEARISH,
            volatility=VolatilityState.HIGH,
            event_tags=("REVERSAL_CANDIDATE",),
            confidence=Decimal("0.81"),
            produced_at=_EVENT_AT,
            provenance=_PROVENANCE,
        )

    def strategy_hunt(self, request: StrategyHuntRequest) -> tuple[StrategyCandidate, ...]:
        return ()

    def fast_task(self, request: FastTaskRequest) -> FastTaskResult:
        raise AssertionError("qualification probe must not invoke fast-task inference")


def run() -> dict[str, str]:
    """Run one fixed market-intelligence path and return deterministic evidence."""

    request = MarketIntelligenceRequest.create(
        symbol="NIFTY",
        timeframe="5m",
        event_timestamp=_EVENT_AT,
        features={"atr": Decimal("42.1"), "rsi": Decimal("68.2")},
        data_lineage="dataset@v1",
        existing_strategy_signals=(),
    )
    model = RegisteredLayaModel(
        model_id="laya-test",
        model_version="v1",
        model_hash="a" * 64,
        adapter_version="fake@v1",
        feature_schema_version="features@v1",
        local_path="models/laya/laya-test-v1",
    )
    router = LayaRouter(
        config=LayaConfig(
            enabled=True,
            enabled_roles=(LayaRole.MARKET_INTELLIGENCE,),
            model_ref="laya-test@v1",
            max_input_age_seconds=30,
        ),
        registry=LayaModelRegistry((model,)),
        adapter=_DeterministicFakeAdapter(),
    )
    insight = MarketIntelligenceService(
        router=router,
        max_input_age_seconds=30,
    ).analyze(request, observed_at=_OBSERVED_AT)
    opportunity = OpportunityEngine(min_confidence=Decimal("0.70")).from_insight(
        request=request,
        insight=insight,
        validity_seconds=60,
    )
    if opportunity is None:
        raise AssertionError("qualification probe expected a candidate-only opportunity")

    return {
        "MARKET_REQUEST": request.fingerprint,
        "MARKET_INSIGHT": insight.fingerprint,
        "LAYA_OPPORTUNITY": opportunity.fingerprint,
        "OPPORTUNITY_STATUS": opportunity.status,
        "STRATEGY_SIGNAL_COUNT": str(len(request.existing_strategy_signals)),
        "DEFAULT_LIVE_STATE": "READ_ONLY/DISARMED",
    }


def main() -> None:
    evidence = run()
    for key in (
        "MARKET_REQUEST",
        "MARKET_INSIGHT",
        "LAYA_OPPORTUNITY",
        "OPPORTUNITY_STATUS",
        "STRATEGY_SIGNAL_COUNT",
        "DEFAULT_LIVE_STATE",
    ):
        print(f"{key}={evidence[key]}")


if __name__ == "__main__":
    main()
