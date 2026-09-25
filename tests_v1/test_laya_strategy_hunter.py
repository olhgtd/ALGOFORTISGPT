from __future__ import annotations

from engine.ai.laya.contracts import MarketRegime, ModelProvenance, StrategyCandidate, StrategyHuntRequest
from engine.ai.laya.strategy_hunter import LayaStrategyHuntError, StrategyHunter

import pytest


def _provenance() -> ModelProvenance:
    return ModelProvenance(
        model_id="laya-test",
        model_version="v1",
        model_hash="a" * 64,
        adapter_version="fake@v1",
        feature_schema_version="features@v1",
    )


def _request(*, max_candidates: int = 2) -> StrategyHuntRequest:
    return StrategyHuntRequest.create(
        dataset_refs=("nifty@v1",),
        feature_schema_version="features@v1",
        allowed_strategy_families=("ORB", "BREAKOUT"),
        max_candidates=max_candidates,
        seed=7,
    )


def _candidate(*, status: str = "RESEARCH_ONLY") -> StrategyCandidate:
    candidate = StrategyCandidate.create(
        entry_concept="breakout after compression",
        exit_requirements=("versioned protective policy",),
        parameter_names=("lookback",),
        target_regimes=(MarketRegime.UPTREND,),
        provenance=_provenance(),
    )
    if status != "RESEARCH_ONLY":
        object.__setattr__(candidate, "status", status)
    return candidate


class StubRouter:
    def __init__(self, results):
        self.results = tuple(results)
        self.calls = []

    def route_strategy_hunt(self, request):
        self.calls.append(request.fingerprint)
        return self.results


def test_strategy_hunter_returns_research_only_candidates_unchanged():
    request = _request(max_candidates=2)
    candidate = _candidate()
    router = StubRouter((candidate,))
    results = StrategyHunter(router).hunt(request)
    assert results == (candidate,)
    assert all(item.status == "RESEARCH_ONLY" for item in results)
    assert router.calls == [request.fingerprint]


def test_strategy_hunter_rejects_adapter_budget_overrun():
    request = _request(max_candidates=1)
    router = StubRouter((_candidate(), _candidate()))
    with pytest.raises(LayaStrategyHuntError, match="max_candidates"):
        StrategyHunter(router).hunt(request)


def test_strategy_hunter_rejects_non_research_candidate():
    request = _request(max_candidates=1)
    router = StubRouter((_candidate(status="ELIGIBLE_FOR_LIVE_EVIDENCE_ONLY"),))
    with pytest.raises(LayaStrategyHuntError, match="research-only"):
        StrategyHunter(router).hunt(request)


def test_strategy_hunter_requires_strategy_hunt_request():
    router = StubRouter(())
    with pytest.raises(TypeError, match="StrategyHuntRequest"):
        StrategyHunter(router).hunt(None)
    assert router.calls == []
