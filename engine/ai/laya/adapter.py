"""Model-runtime boundary for the AlgoFortis Laya integration."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from engine.ai.laya.contracts import (
    FastTaskRequest,
    FastTaskResult,
    MarketInsight,
    MarketIntelligenceRequest,
    StrategyCandidate,
    StrategyHuntRequest,
)


class LayaUnavailable(RuntimeError):
    """Raised when a Laya adapter cannot provide inference."""


@runtime_checkable
class LayaAdapter(Protocol):
    adapter_version: str

    def market_intelligence(self, request: MarketIntelligenceRequest) -> MarketInsight:
        ...

    def strategy_hunt(self, request: StrategyHuntRequest) -> tuple[StrategyCandidate, ...]:
        ...

    def fast_task(self, request: FastTaskRequest) -> FastTaskResult:
        ...


class DisabledLayaAdapter:
    """Default adapter: always fail closed, with no fallback model."""

    adapter_version = "disabled@v1"

    def market_intelligence(self, request: MarketIntelligenceRequest) -> MarketInsight:
        raise LayaUnavailable("Laya is disabled")

    def strategy_hunt(self, request: StrategyHuntRequest) -> tuple[StrategyCandidate, ...]:
        raise LayaUnavailable("Laya is disabled")

    def fast_task(self, request: FastTaskRequest) -> FastTaskResult:
        raise LayaUnavailable("Laya is disabled")


__all__ = ["LayaAdapter", "LayaUnavailable", "DisabledLayaAdapter"]
