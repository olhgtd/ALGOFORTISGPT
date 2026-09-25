"""Research-only strategy hunting service for Laya-generated hypotheses."""

from __future__ import annotations

from engine.ai.laya.contracts import StrategyCandidate, StrategyHuntRequest


class LayaStrategyHuntError(ValueError):
    """Raised when strategy-hunt output escapes its research-only boundary."""


class StrategyHunter:
    def __init__(self, router: object) -> None:
        if not hasattr(router, "route_strategy_hunt"):
            raise TypeError("router must provide route_strategy_hunt")
        self._router = router

    def hunt(self, request: StrategyHuntRequest) -> tuple[StrategyCandidate, ...]:
        if not isinstance(request, StrategyHuntRequest):
            raise TypeError("request must be StrategyHuntRequest")
        raw = self._router.route_strategy_hunt(request)
        if not isinstance(raw, (tuple, list)):
            raise LayaStrategyHuntError("strategy hunter result must be a tuple/list")
        results = tuple(raw)
        if len(results) > request.max_candidates:
            raise LayaStrategyHuntError("strategy hunter exceeded max_candidates")
        for candidate in results:
            if not isinstance(candidate, StrategyCandidate):
                raise LayaStrategyHuntError("strategy hunter returned invalid candidate type")
            if candidate.status != "RESEARCH_ONLY":
                raise LayaStrategyHuntError("strategy candidate escaped research-only state")
        return results


__all__ = ["LayaStrategyHuntError", "StrategyHunter"]
