"""Prime-owned provider/model registry read seam.

This module holds metadata/health/binding decisions only. It never stores or
returns plaintext provider secrets and has no broker/order authority.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from .contracts import AIAvailability


@dataclass(frozen=True, slots=True)
class ProviderBinding:
    agent_id: str
    provider_id: str
    model_id: str
    provider: Mapping[str, Any]
    model: Mapping[str, Any]
    fallback_mode: str


class ProviderRegistryUnavailable(RuntimeError):
    pass


class ProviderRegistryView:
    """Read-only deterministic view over the durable AI registry repository."""

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    @staticmethod
    def _state(row: Mapping[str, Any] | None) -> AIAvailability:
        if not row:
            return AIAvailability.UNAVAILABLE
        try:
            return AIAvailability(str(row.get("authority_state") or "UNKNOWN"))
        except ValueError:
            return AIAvailability.UNKNOWN

    def binding_for(self, agent_id: str) -> ProviderBinding:
        binding = self._repository.get_binding(agent_id)
        if binding is None:
            raise ProviderRegistryUnavailable("AI provider/model binding unavailable")

        providers = {row["provider_id"]: row for row in self._repository.list_providers()}
        models = {row["model_id"]: row for row in self._repository.list_models()}
        provider = providers.get(binding["provider_id"])
        model = models.get(binding["model_id"])
        if provider is None or model is None:
            raise ProviderRegistryUnavailable("AI provider/model authority unavailable")
        if model.get("provider_id") != provider.get("provider_id"):
            raise ProviderRegistryUnavailable("AI model/provider binding mismatch")
        if not bool(provider.get("enabled")) or self._state(provider) is not AIAvailability.AVAILABLE:
            raise ProviderRegistryUnavailable("AI provider authority is not AVAILABLE")
        if not bool(model.get("enabled")) or self._state(model) is not AIAvailability.AVAILABLE:
            raise ProviderRegistryUnavailable("AI model authority is not AVAILABLE")

        try:
            policy = json.loads(binding.get("fallback_policy_json") or "{}")
        except Exception:
            policy = {}
        fallback_mode = str(policy.get("mode") or "FAIL_CLOSED").upper()
        if fallback_mode != "FAIL_CLOSED":
            raise ProviderRegistryUnavailable("only FAIL_CLOSED provider fallback is qualified")

        return ProviderBinding(
            agent_id=agent_id,
            provider_id=str(provider["provider_id"]),
            model_id=str(model["model_id"]),
            provider=dict(provider),
            model=dict(model),
            fallback_mode=fallback_mode,
        )
