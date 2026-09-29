"""Prime-owned deterministic routing for research/shadow AI jobs."""
from __future__ import annotations

import json
from typing import Any, Mapping

from .contracts import AgentRole, AIAvailability, AIJobScope, RoutingDecision


class AIUnavailable(RuntimeError):
    pass


_JOB_ROLE = {
    "MARKET_INTELLIGENCE": AgentRole.LAYA,
    "STRATEGY_RESEARCH": AgentRole.RESEARCH,
    "EVIDENCE_RESEARCH": AgentRole.RESEARCH,
    "RISK_CHALLENGE": AgentRole.RISK_CHALLENGER,
    "ORCHESTRATE": AgentRole.PRIME,
}

_ROLE_AGENT_ID = {
    AgentRole.PRIME: "prime",
    AgentRole.LAYA: "laya",
    AgentRole.RESEARCH: "research",
    AgentRole.RISK_CHALLENGER: "risk-challenger",
}


class PrimeOrchestrator:
    """Routes jobs only when every required authority is explicitly AVAILABLE."""

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

    def route(self, *, job_type: str, scope: str) -> RoutingDecision:
        job_key = str(job_type).upper().strip()
        try:
            scope_enum = AIJobScope(str(scope).upper().strip())
        except ValueError as exc:
            raise AIUnavailable("AI jobs are restricted to RESEARCH or SHADOW") from exc

        role = _JOB_ROLE.get(job_key)
        if role is None:
            raise AIUnavailable("unsupported AI research job type")
        agent_id = _ROLE_AGENT_ID[role]

        agents = {row["agent_id"]: row for row in self._repository.list_agents()}
        agent = agents.get(agent_id)
        if not agent or not bool(agent.get("enabled")):
            raise AIUnavailable("required AI agent is disabled or unavailable")

        binding = self._repository.get_binding(agent_id)
        if binding is None:
            raise AIUnavailable("AI provider/model binding unavailable")

        providers = {row["provider_id"]: row for row in self._repository.list_providers()}
        models = {row["model_id"]: row for row in self._repository.list_models()}
        provider = providers.get(binding["provider_id"])
        model = models.get(binding["model_id"])

        if not provider or not bool(provider.get("enabled")) or self._state(provider) is not AIAvailability.AVAILABLE:
            raise AIUnavailable("AI provider authority is not AVAILABLE")
        if not model or not bool(model.get("enabled")) or self._state(model) is not AIAvailability.AVAILABLE:
            raise AIUnavailable("AI model authority is not AVAILABLE")
        if model.get("provider_id") != provider.get("provider_id"):
            raise AIUnavailable("AI model/provider binding mismatch")

        policy = {}
        try:
            policy = json.loads(binding.get("fallback_policy_json") or "{}")
        except Exception:
            policy = {}
        if str(policy.get("mode") or "FAIL_CLOSED").upper() != "FAIL_CLOSED":
            raise AIUnavailable("only FAIL_CLOSED provider fallback is qualified")

        return RoutingDecision(
            agent_id=agent_id,
            role=role,
            provider_id=str(provider["provider_id"]),
            model_id=str(model["model_id"]),
            scope=scope_enum,
            evidence={
                "routing_owner": "PRIME",
                "fallback_mode": "FAIL_CLOSED",
                "provider_state": provider.get("authority_state"),
                "model_state": model.get("authority_state"),
            },
        )
