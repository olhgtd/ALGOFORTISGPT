from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from engine.ai.laya.config import LayaConfig
from engine.ai.laya.contracts import (
    DirectionalBias,
    LayaRole,
    MarketInsight,
    MarketIntelligenceRequest,
    MarketRegime,
    ModelProvenance,
    VolatilityState,
)
from engine.ai.laya.market_intelligence import LayaMarketError, MarketIntelligenceService
from engine.ai.laya.model_registry import LayaModelRegistry, RegisteredLayaModel
from engine.ai.laya.router import LayaRouter


def _provenance() -> ModelProvenance:
    return ModelProvenance(
        model_id="laya-test",
        model_version="v1",
        model_hash="a" * 64,
        adapter_version="fake@v1",
        feature_schema_version="features@v1",
    )


def _request(event_timestamp: datetime) -> MarketIntelligenceRequest:
    return MarketIntelligenceRequest.create(
        symbol="NIFTY",
        timeframe="5m",
        event_timestamp=event_timestamp,
        features={"atr": Decimal("42.1"), "rsi": Decimal("68.2")},
        data_lineage="dataset@v1",
        existing_strategy_signals=(),
    )


class FakeMarketAdapter:
    adapter_version = "fake@v1"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def market_intelligence(self, request: MarketIntelligenceRequest) -> MarketInsight:
        self.calls.append(request.fingerprint)
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

    def strategy_hunt(self, request):
        raise AssertionError("market service must not call strategy_hunt")

    def fast_task(self, request):
        raise AssertionError("market service must not call fast_task")


def _service(*, max_age: int = 30) -> tuple[MarketIntelligenceService, FakeMarketAdapter]:
    fake = FakeMarketAdapter()
    config = LayaConfig(
        enabled=True,
        enabled_roles=(LayaRole.MARKET_INTELLIGENCE,),
        model_ref="laya-test@v1",
        max_input_age_seconds=max_age,
    )
    registry = LayaModelRegistry((RegisteredLayaModel(
        model_id="laya-test",
        model_version="v1",
        model_hash="a" * 64,
        adapter_version="fake@v1",
        feature_schema_version="features@v1",
        local_path="models/laya/laya-test-v1",
    ),))
    router = LayaRouter(config=config, registry=registry, adapter=fake)
    return MarketIntelligenceService(router=router, max_input_age_seconds=max_age), fake


def test_stale_market_input_is_rejected_before_adapter_call():
    service, fake = _service(max_age=30)
    request = _request(datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc))
    with pytest.raises(LayaMarketError, match="stale"):
        service.analyze(
            request,
            observed_at=datetime(2026, 1, 5, 9, 31, tzinfo=timezone.utc),
        )
    assert fake.calls == []


def test_future_skew_over_five_seconds_is_rejected_before_adapter_call():
    service, fake = _service(max_age=30)
    request = _request(datetime(2026, 1, 5, 9, 30, 6, tzinfo=timezone.utc))
    with pytest.raises(LayaMarketError, match="future"):
        service.analyze(
            request,
            observed_at=datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc),
        )
    assert fake.calls == []


def test_observed_at_must_be_timezone_aware():
    service, fake = _service(max_age=30)
    request = _request(datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc))
    with pytest.raises(LayaMarketError, match="timezone-aware"):
        service.analyze(request, observed_at=datetime(2026, 1, 5, 9, 30, 15))
    assert fake.calls == []


def test_fresh_market_input_routes_once_and_returns_request_bound_insight():
    service, fake = _service(max_age=30)
    request = _request(datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc))
    result = service.analyze(
        request,
        observed_at=datetime(2026, 1, 5, 9, 30, 15, tzinfo=timezone.utc),
    )
    assert result.request_fingerprint == request.fingerprint
    assert fake.calls == [request.fingerprint]


def test_market_service_rejects_nonpositive_freshness_window():
    config = LayaConfig(
        enabled=True,
        enabled_roles=(LayaRole.MARKET_INTELLIGENCE,),
        model_ref="laya-test@v1",
        max_input_age_seconds=30,
    )
    registry = LayaModelRegistry((RegisteredLayaModel(
        model_id="laya-test",
        model_version="v1",
        model_hash="a" * 64,
        adapter_version="fake@v1",
        feature_schema_version="features@v1",
        local_path="models/laya/laya-test-v1",
    ),))
    router = LayaRouter(config=config, registry=registry, adapter=FakeMarketAdapter())
    with pytest.raises(LayaMarketError, match="positive"):
        MarketIntelligenceService(router=router, max_input_age_seconds=0)
