"""Prime-owned deterministic routing for research/shadow AI jobs."""
from __future__ import annotations

from typing import Any

from .contracts import AgentRole, AIJobScope, RoutingDecision
from .evidence import routing_evidence
from .provider_registry import ProviderRegistryUnavailable, ProviderRegistryView


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
        self._registry = ProviderRegistryView(repository)

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

        try:
            binding = self._registry.binding_for(agent_id)
        except ProviderRegistryUnavailable as exc:
            raise AIUnavailable(str(exc)) from exc

        evidence = routing_evidence(
            agent_id=agent_id,
            provider_id=binding.provider_id,
            model_id=binding.model_id,
            scope=scope_enum.value,
        )
        return RoutingDecision(
            agent_id=agent_id,
            role=role,
            provider_id=binding.provider_id,
            model_id=binding.model_id,
            scope=scope_enum,
            evidence={
                **dict(evidence.payload),
                "evidence_ref": evidence.evidence_ref,
                "provider_state": binding.provider.get("authority_state"),
                "model_state": binding.model.get("authority_state"),
            },
        )
