from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from engine.ai.laya.adapter import DisabledLayaAdapter, LayaAdapter, LayaUnavailable
from engine.ai.laya.config import LayaConfig
from engine.ai.laya.contracts import LayaRole, MarketIntelligenceRequest
from engine.ai.laya.model_registry import (
    LayaModelRegistry,
    LayaRegistryError,
    RegisteredLayaModel,
)


def _model(**overrides):
    values = dict(
        model_id="laya-test",
        model_version="v1",
        model_hash="a" * 64,
        adapter_version="fake@v1",
        feature_schema_version="features@v1",
        local_path="models/laya/laya-test-v1",
    )
    values.update(overrides)
    return RegisteredLayaModel(**values)


def _request():
    return MarketIntelligenceRequest.create(
        symbol="NIFTY",
        timeframe="5m",
        event_timestamp=datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc),
        features={"atr": Decimal("42")},
        data_lineage="dataset@v1",
        existing_strategy_signals=(),
    )


def test_config_is_disabled_by_default_and_fail_closed():
    config = LayaConfig.disabled()
    assert config.enabled is False
    assert config.enabled_roles == ()
    assert config.model_ref is None
    assert config.max_input_age_seconds == 0


def test_enabled_config_requires_model_roles_and_positive_freshness():
    config = LayaConfig(
        enabled=True,
        enabled_roles=(LayaRole.MARKET_INTELLIGENCE,),
        model_ref="laya-test@v1",
        max_input_age_seconds=30,
    )
    assert config.enabled_roles == (LayaRole.MARKET_INTELLIGENCE,)

    with pytest.raises(ValueError):
        LayaConfig(True, (), "laya-test@v1", 30)
    with pytest.raises(ValueError):
        LayaConfig(True, (LayaRole.MARKET_INTELLIGENCE,), None, 30)
    with pytest.raises(ValueError):
        LayaConfig(True, (LayaRole.MARKET_INTELLIGENCE,), "laya-test@v1", 0)


def test_registry_resolves_only_explicit_known_model_and_is_deterministic():
    first = _model()
    second = _model(model_id="laya-alt", model_hash="b" * 64)
    registry = LayaModelRegistry((second, first))
    assert registry.resolve("laya-test@v1") == first
    assert tuple(model.ref for model in registry.list_models()) == ("laya-alt@v1", "laya-test@v1")
    with pytest.raises(LayaRegistryError, match="not registered"):
        registry.resolve("missing@v1")


def test_registry_rejects_duplicate_ref_and_unsafe_model_paths():
    with pytest.raises(LayaRegistryError, match="duplicate"):
        LayaModelRegistry((_model(), _model()))
    for path in ("/tmp/model", r"C:\models\laya", r"\\server\share\model", "https://example/model"):
        with pytest.raises(LayaRegistryError, match="relative"):
            _model(local_path=path)


def test_registered_model_rejects_invalid_hash():
    with pytest.raises(LayaRegistryError, match="model_hash"):
        _model(model_hash="bad")


def test_disabled_adapter_implements_protocol_and_fails_closed_without_fallback():
    adapter = DisabledLayaAdapter()
    assert isinstance(adapter, LayaAdapter)
    assert adapter.adapter_version == "disabled@v1"
    with pytest.raises(LayaUnavailable, match="disabled"):
        adapter.market_intelligence(_request())
    with pytest.raises(LayaUnavailable, match="disabled"):
        adapter.strategy_hunt(None)
    with pytest.raises(LayaUnavailable, match="disabled"):
        adapter.fast_task(None)
