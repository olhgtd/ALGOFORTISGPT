"""Provenance-bound dispatch for the AlgoFortis Laya integration."""

from __future__ import annotations

from engine.ai.laya.adapter import LayaAdapter
from engine.ai.laya.config import LayaConfig
from engine.ai.laya.contracts import (
    FastTaskRequest,
    FastTaskResult,
    LayaRole,
    MarketInsight,
    MarketIntelligenceRequest,
    ModelProvenance,
    StrategyCandidate,
    StrategyHuntRequest,
)
from engine.ai.laya.model_registry import LayaModelRegistry, LayaRegistryError


class LayaRoutingError(ValueError):
    """Raised when a Laya result cannot be accepted safely."""


class LayaRouter:
    def __init__(self, *, config: LayaConfig, registry: LayaModelRegistry, adapter: LayaAdapter) -> None:
        if not isinstance(config, LayaConfig):
            raise TypeError("config must be LayaConfig")
        if not isinstance(registry, LayaModelRegistry):
            raise TypeError("registry must be LayaModelRegistry")
        if not isinstance(adapter, LayaAdapter):
            raise TypeError("adapter must implement LayaAdapter")
        self._config = config
        self._registry = registry
        self._adapter = adapter

    def _require_enabled(self, role: LayaRole) -> None:
        if not self._config.enabled or role not in self._config.enabled_roles:
            raise LayaRoutingError("Laya role is disabled")
        if self._config.model_ref is None:
            raise LayaRoutingError("Laya model_ref is missing")

    def _verify_provenance(self, provenance: ModelProvenance) -> None:
        if not isinstance(provenance, ModelProvenance):
            raise LayaRoutingError("Laya result provenance is invalid")
        if self._config.model_ref is None:
            raise LayaRoutingError("Laya result provenance has no configured model")
        output_ref = f"{provenance.model_id}@{provenance.model_version}"
        if output_ref != self._config.model_ref:
            raise LayaRoutingError("Laya result provenance does not match configured model")
        try:
            registered = self._registry.resolve(self._config.model_ref)
        except LayaRegistryError as exc:
            raise LayaRoutingError("Laya result provenance is not registered") from exc
        if provenance.model_hash != registered.model_hash:
            raise LayaRoutingError("Laya result provenance model hash mismatch")
        if provenance.adapter_version != registered.adapter_version:
            raise LayaRoutingError("Laya result provenance adapter version mismatch")
        if provenance.feature_schema_version != registered.feature_schema_version:
            raise LayaRoutingError("Laya result provenance feature schema mismatch")
        if self._adapter.adapter_version != registered.adapter_version:
            raise LayaRoutingError("Laya adapter version does not match registered runtime")

    def route_market(self, request: MarketIntelligenceRequest) -> MarketInsight:
        self._require_enabled(LayaRole.MARKET_INTELLIGENCE)
        if not isinstance(request, MarketIntelligenceRequest):
            raise TypeError("request must be MarketIntelligenceRequest")
        result = self._adapter.market_intelligence(request)
        if not isinstance(result, MarketInsight):
            raise LayaRoutingError("market adapter returned invalid result type")
        self._verify_provenance(result.provenance)
        if result.request_fingerprint != request.fingerprint:
            raise LayaRoutingError("market result is not bound to request")
        return result

    def route_strategy_hunt(self, request: StrategyHuntRequest) -> tuple[StrategyCandidate, ...]:
        self._require_enabled(LayaRole.STRATEGY_HUNTING)
        if not isinstance(request, StrategyHuntRequest):
            raise TypeError("request must be StrategyHuntRequest")
        raw = self._adapter.strategy_hunt(request)
        if not isinstance(raw, (tuple, list)):
            raise LayaRoutingError("strategy adapter returned invalid result type")
        results = tuple(raw)
        if len(results) > request.max_candidates:
            raise LayaRoutingError("strategy adapter exceeded max_candidates")
        for result in results:
            if not isinstance(result, StrategyCandidate):
                raise LayaRoutingError("strategy adapter returned invalid candidate type")
            self._verify_provenance(result.provenance)
        return results

    def route_fast_task(self, request: FastTaskRequest) -> FastTaskResult:
        self._require_enabled(LayaRole.FAST_TASKS)
        if not isinstance(request, FastTaskRequest):
            raise TypeError("request must be FastTaskRequest")
        result = self._adapter.fast_task(request)
        if not isinstance(result, FastTaskResult):
            raise LayaRoutingError("fast-task adapter returned invalid result type")
        self._verify_provenance(result.provenance)
        if result.request_fingerprint != request.fingerprint:
            raise LayaRoutingError("fast-task result is not bound to request")
        if result.task_kind != request.task_kind:
            raise LayaRoutingError("fast-task result task kind mismatch")
        return result


__all__ = ["LayaRoutingError", "LayaRouter"]
