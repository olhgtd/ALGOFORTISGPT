from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

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
from engine.ai.laya.model_registry import LayaModelRegistry, RegisteredLayaModel
from engine.ai.laya.router import LayaRouter, LayaRoutingError


def _registered_model() -> RegisteredLayaModel:
    return RegisteredLayaModel(
        model_id="laya-test",
        model_version="v1",
        model_hash="a" * 64,
        adapter_version="fake@v1",
        feature_schema_version="features@v1",
        local_path="models/laya/laya-test-v1",
    )


def _provenance(*, model_id: str = "laya-test", model_hash: str = "a" * 64) -> ModelProvenance:
    return ModelProvenance(
        model_id=model_id,
        model_version="v1",
        model_hash=model_hash,
        adapter_version="fake@v1",
        feature_schema_version="features@v1",
    )


def _market_request() -> MarketIntelligenceRequest:
    return MarketIntelligenceRequest.create(
        symbol="NIFTY",
        timeframe="5m",
        event_timestamp=datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc),
        features={"atr": Decimal("42.1"), "rsi": Decimal("68.2")},
        data_lineage="dataset@v1",
        existing_strategy_signals=(),
    )


def _hunt_request(*, max_candidates: int = 2) -> StrategyHuntRequest:
    return StrategyHuntRequest.create(
        dataset_refs=("nifty@v1",),
        feature_schema_version="features@v1",
        allowed_strategy_families=("BREAKOUT", "ORB"),
        max_candidates=max_candidates,
        seed=7,
    )


def _fast_request() -> FastTaskRequest:
    return FastTaskRequest.create(
        task_kind="FEATURE_SCORING",
        payload=(("symbol", "NIFTY"),),
        request_timestamp=datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc),
    )


class FakeAdapter:
    adapter_version = "fake@v1"

    def __init__(self, *, provenance: ModelProvenance | None = None) -> None:
        self.provenance = provenance or _provenance()
        self.calls: list[tuple[str, str]] = []
        self.market_request_override: str | None = None
        self.fast_request_override: str | None = None
        self.fast_kind_override: str | None = None
        self.strategy_count = 1

    def market_intelligence(self, request: MarketIntelligenceRequest) -> MarketInsight:
        self.calls.append(("market", request.fingerprint))
        return MarketInsight.create(
            request_fingerprint=self.market_request_override or request.fingerprint,
            regime=MarketRegime.UPTREND,
            bias=DirectionalBias.BULLISH,
            volatility=VolatilityState.NORMAL,
            event_tags=("TREND",),
            confidence=Decimal("0.75"),
            produced_at=request.event_timestamp,
            provenance=self.provenance,
        )

    def strategy_hunt(self, request: StrategyHuntRequest) -> tuple[StrategyCandidate, ...]:
        self.calls.append(("hunt", request.fingerprint))
        return tuple(
            StrategyCandidate.create(
                entry_concept=f"candidate {ordinal}",
                exit_requirements=("versioned protective policy",),
                parameter_names=("lookback",),
                target_regimes=(MarketRegime.UPTREND,),
                provenance=self.provenance,
            )
            for ordinal in range(self.strategy_count)
        )

    def fast_task(self, request: FastTaskRequest) -> FastTaskResult:
        self.calls.append(("fast", request.fingerprint))
        return FastTaskResult.create(
            task_kind=self.fast_kind_override or request.task_kind,
            request_fingerprint=self.fast_request_override or request.fingerprint,
            ranked_items=(("atr", Decimal("0.8")),),
            provenance=self.provenance,
        )


def _router(*, roles: tuple[LayaRole, ...], adapter: FakeAdapter | None = None,
            register: bool = True, model_ref: str = "laya-test@v1") -> tuple[LayaRouter, FakeAdapter]:
    fake = adapter or FakeAdapter()
    config = LayaConfig(
        enabled=True,
        enabled_roles=roles,
        model_ref=model_ref,
        max_input_age_seconds=30,
    )
    registry = LayaModelRegistry((_registered_model(),) if register else ())
    return LayaRouter(config=config, registry=registry, adapter=fake), fake


def test_disabled_role_is_rejected_before_adapter_call():
    router, fake = _router(roles=(LayaRole.FAST_TASKS,))
    with pytest.raises(LayaRoutingError, match="role is disabled"):
        router.route_market(_market_request())
    assert fake.calls == []


def test_unregistered_model_provenance_is_rejected_fail_closed():
    router, fake = _router(roles=(LayaRole.MARKET_INTELLIGENCE,), register=False)
    with pytest.raises(LayaRoutingError, match="provenance"):
        router.route_market(_market_request())
    assert len(fake.calls) == 1


def test_result_from_different_model_ref_is_rejected():
    fake = FakeAdapter(provenance=_provenance(model_id="laya-other", model_hash="b" * 64))
    router, _ = _router(roles=(LayaRole.MARKET_INTELLIGENCE,), adapter=fake)
    with pytest.raises(LayaRoutingError, match="provenance"):
        router.route_market(_market_request())


def test_registered_market_result_is_accepted_and_request_bound():
    router, fake = _router(roles=(LayaRole.MARKET_INTELLIGENCE,))
    request = _market_request()
    result = router.route_market(request)
    assert result.request_fingerprint == request.fingerprint
    assert fake.calls == [("market", request.fingerprint)]


def test_market_result_with_wrong_request_fingerprint_is_rejected():
    fake = FakeAdapter()
    fake.market_request_override = "b" * 64
    router, _ = _router(roles=(LayaRole.MARKET_INTELLIGENCE,), adapter=fake)
    with pytest.raises(LayaRoutingError, match="bound to request"):
        router.route_market(_market_request())


def test_fast_task_requires_matching_task_kind_and_request_identity():
    request = _fast_request()

    wrong_request = FakeAdapter()
    wrong_request.fast_request_override = "b" * 64
    router, _ = _router(roles=(LayaRole.FAST_TASKS,), adapter=wrong_request)
    with pytest.raises(LayaRoutingError, match="bound to request"):
        router.route_fast_task(request)

    wrong_kind = FakeAdapter()
    wrong_kind.fast_kind_override = "SIGNAL_FILTERING"
    router, _ = _router(roles=(LayaRole.FAST_TASKS,), adapter=wrong_kind)
    with pytest.raises(LayaRoutingError, match="task kind"):
        router.route_fast_task(request)


def test_strategy_hunt_rejects_adapter_budget_overrun():
    fake = FakeAdapter()
    fake.strategy_count = 2
    router, _ = _router(roles=(LayaRole.STRATEGY_HUNTING,), adapter=fake)
    with pytest.raises(LayaRoutingError, match="max_candidates"):
        router.route_strategy_hunt(_hunt_request(max_candidates=1))


def test_strategy_hunt_accepts_registered_provenance_within_budget():
    router, fake = _router(roles=(LayaRole.STRATEGY_HUNTING,))
    request = _hunt_request(max_candidates=2)
    results = router.route_strategy_hunt(request)
    assert len(results) == 1
    assert results[0].provenance == _provenance()
    assert fake.calls == [("hunt", request.fingerprint)]


def test_adapter_version_must_match_registered_runtime():
    class WrongVersionAdapter(FakeAdapter):
        adapter_version = "wrong@v1"

    fake = WrongVersionAdapter()
    router, _ = _router(roles=(LayaRole.MARKET_INTELLIGENCE,), adapter=fake)
    with pytest.raises(LayaRoutingError, match="adapter version"):
        router.route_market(_market_request())
