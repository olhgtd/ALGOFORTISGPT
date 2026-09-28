from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import inspect

import pytest

from engine.ai.laya.config import LayaConfig
from engine.ai.laya.contracts import MarketIntelligenceRequest
from engine.ai.laya.market_intelligence import LayaMarketError, MarketIntelligenceService
from engine.ai.laya.runtime import DisabledLayaRuntime, LayaUnavailable, LocalLayaRuntime


class _FakeRuntime:
    def predict(self, state, questions):
        assert state["symbol"] == "nifty"
        assert "regime" in questions
        return {
            "answers": {
                "regime": {"choice": "UPTREND", "confidence": 0.91},
                "bias": {"choice": "BULLISH", "confidence": 0.83},
                "volatility": {"choice": "NORMAL", "confidence": 0.74},
                "opportunity": {"choice": "NO_TRADE", "confidence": 0.95},
            }
        }


def _request(ts: datetime) -> MarketIntelligenceRequest:
    return MarketIntelligenceRequest.create(
        symbol="NIFTY",
        timeframe="5m",
        event_timestamp=ts,
        features={
            "close": Decimal("25420.50"),
            "volume": Decimal("125000"),
            "atr_14": Decimal("48.25"),
        },
        data_lineage="market-data/v1:test",
        existing_strategy_signals=(),
    )


def test_default_local_workspace_is_project_relative_and_shadow_only() -> None:
    config = LayaConfig.local_default()
    assert config.source_dir == "third_party/laya/upstream"
    assert config.model_dir == "models/laya/original"
    assert config.shadow_only is True
    assert config.allow_broker_mutation is False
    assert config.allow_agent_routing is False


def test_disabled_runtime_fails_closed() -> None:
    with pytest.raises(LayaUnavailable, match="disabled"):
        DisabledLayaRuntime().predict({}, {})


def test_local_runtime_does_not_use_laya_router() -> None:
    source = inspect.getsource(LocalLayaRuntime)
    assert "Router(" not in source
    assert ".Router" not in source
    assert "laya.load" in source


def test_market_intelligence_is_shadow_only() -> None:
    now = datetime(2026, 9, 29, 9, 30, tzinfo=timezone.utc)
    service = MarketIntelligenceService(
        runtime=_FakeRuntime(),
        max_input_age_seconds=30,
        model_ref="convaiinnovations/laya@local",
        model_hash="891102d372688fc2a094dac56a384bc537b87c63f21f9f3dac0be2b7cbc8d86c",
    )

    result = service.analyze(_request(now - timedelta(seconds=5)), observed_at=now)

    assert result.source == "LAYA"
    assert result.status == "SHADOW_ONLY"
    assert result.regime.value == "UPTREND"
    assert result.bias.value == "BULLISH"
    assert result.volatility.value == "NORMAL"
    assert result.opportunity.value == "NO_TRADE"
    assert result.confidence == Decimal("0.74")


def test_market_intelligence_rejects_stale_input_before_inference() -> None:
    now = datetime(2026, 9, 29, 9, 30, tzinfo=timezone.utc)
    service = MarketIntelligenceService(
        runtime=_FakeRuntime(),
        max_input_age_seconds=30,
        model_ref="convaiinnovations/laya@local",
        model_hash="891102d372688fc2a094dac56a384bc537b87c63f21f9f3dac0be2b7cbc8d86c",
    )

    with pytest.raises(LayaMarketError, match="stale"):
        service.analyze(_request(now - timedelta(seconds=31)), observed_at=now)
