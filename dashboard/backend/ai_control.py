"""Authoritative Owner AI control service.

The service owns registry/configuration and research/shadow job evidence only.
It never invokes broker mutation, Live arm, RiskGate approval, or account/billing
mutation.  Actual model execution is an injected adapter and is unavailable by
default.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Protocol

from engine.ai.contracts import AIAvailability, AIJobStatus
from engine.ai.orchestrator import AIUnavailable, PrimeOrchestrator

from .owner_admin.repository import OwnerAdminRepository


class AIExecutionAdapter(Protocol):
    def submit(self, *, job: Mapping[str, Any], provider: Mapping[str, Any], model: Mapping[str, Any]) -> Mapping[str, Any]: ...


class UnavailableAIExecutionAdapter:
    def submit(self, *, job: Mapping[str, Any], provider: Mapping[str, Any], model: Mapping[str, Any]) -> Mapping[str, Any]:
        raise AIUnavailable("qualified AI model execution adapter is unavailable")


_ALLOWED_STATES = {item.value for item in AIAvailability}
_ALLOWED_JOB_TYPES = {"MARKET_INTELLIGENCE", "STRATEGY_RESEARCH", "EVIDENCE_RESEARCH", "RISK_CHALLENGE", "ORCHESTRATE"}


class AIControlService:
    def __init__(
        self,
        *,
        repository: OwnerAdminRepository,
        execution_adapter: AIExecutionAdapter | None = None,
    ) -> None:
        self._repository = repository
        self._orchestrator = PrimeOrchestrator(repository)
        self._execution = execution_adapter or UnavailableAIExecutionAdapter()

    @staticmethod
    def _state(value: str) -> str:
        state = str(value or "UNKNOWN").upper()
        if state not in _ALLOWED_STATES:
            raise ValueError("invalid AI authority state")
        return state

    @staticmethod
    def _public_job(row: Mapping[str, Any]) -> dict[str, Any]:
        result = dict(row)
        for field in ("request_json", "output_json"):
            raw = result.pop(field, None)
            if raw:
                try:
                    result[field.removesuffix("_json")] = json.loads(raw)
                except Exception:
                    result[field.removesuffix("_json")] = None
        return result

    def snapshot(self) -> dict[str, Any]:
        agents = self._repository.list_agents()
        providers = self._repository.list_providers()
        models = self._repository.list_models()
        bindings = self._repository.list_bindings()
        jobs = [self._public_job(row) for row in self._repository.list_jobs(limit=50)]

        provider_map = {row["provider_id"]: row for row in providers}
        model_map = {row["model_id"]: row for row in models}
        binding_map = {row["agent_id"]: row for row in bindings}
        projected_agents: list[dict[str, Any]] = []
        for agent in agents:
            binding = binding_map.get(agent["agent_id"])
            provider = provider_map.get(binding["provider_id"]) if binding else None
            model = model_map.get(binding["model_id"]) if binding else None
            state = str(agent.get("authority_state") or "UNKNOWN")
            if not binding:
                state = "UNAVAILABLE"
            elif not provider or not model:
                state = "UNAVAILABLE"
            elif provider.get("authority_state") != "AVAILABLE" or model.get("authority_state") != "AVAILABLE":
                state = "STALE" if "STALE" in {provider.get("authority_state"), model.get("authority_state")} else "UNAVAILABLE"
            else:
                state = "AVAILABLE"
            projected_agents.append({
                **agent,
                "authority_state": state,
                "binding": binding,
                "provider": provider,
                "model": model,
            })

        overall = "AVAILABLE" if projected_agents and all(a["authority_state"] == "AVAILABLE" for a in projected_agents) else (
            "STALE" if any(a["authority_state"] == "STALE" for a in projected_agents) else "UNAVAILABLE"
        )
        return {
            "source": "BACKEND",
            "trust": "FRESH",
            "authority_state": overall,
            "live_state": "READ_ONLY/DISARMED",
            "broker_mutation": "ABSENT",
            "routing_owner": "PRIME",
            "agents": projected_agents,
            "providers": providers,
            "models": models,
            "bindings": bindings,
            "jobs": jobs,
        }

    def configure_provider(
        self,
        *,
        provider_id: str,
        display_name: str,
        provider_type: str,
        credential_ref: str | None,
        enabled: bool,
        authority_state: str,
    ) -> dict[str, Any]:
        if credential_ref and any(marker in credential_ref.lower() for marker in ("bearer ", "sk-", "api_key=", "password=")):
            raise ValueError("plaintext provider credentials are forbidden; use opaque credential_ref")
        return self._repository.upsert_provider(
            provider_id=provider_id,
            display_name=display_name,
            provider_type=provider_type,
            credential_ref=credential_ref,
            enabled=enabled,
            authority_state=self._state(authority_state),
        )

    def configure_model(
        self,
        *,
        model_id: str,
        provider_id: str,
        display_name: str,
        capability: str,
        enabled: bool,
        authority_state: str,
    ) -> dict[str, Any]:
        return self._repository.upsert_model(
            model_id=model_id,
            provider_id=provider_id,
            display_name=display_name,
            capability=capability,
            enabled=enabled,
            authority_state=self._state(authority_state),
        )

    def bind_agent(
        self,
        *,
        agent_id: str,
        provider_id: str,
        model_id: str,
        fallback_policy: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        policy = dict(fallback_policy or {"mode": "FAIL_CLOSED"})
        if str(policy.get("mode") or "").upper() != "FAIL_CLOSED":
            raise ValueError("only FAIL_CLOSED fallback policy is qualified")
        return self._repository.set_binding(
            agent_id=agent_id,
            provider_id=provider_id,
            model_id=model_id,
            fallback_policy=policy,
        )

    def set_agent_policy(self, *, agent_id: str, enabled: bool) -> dict[str, Any]:
        return self._repository.set_agent_enabled(agent_id=agent_id, enabled=enabled)

    def create_job(
        self,
        *,
        job_type: str,
        scope: str,
        request: Mapping[str, Any] | None = None,
        auto_submit: bool = False,
    ) -> dict[str, Any]:
        kind = str(job_type).upper().strip()
        if kind not in _ALLOWED_JOB_TYPES:
            raise ValueError("unsupported AI research job type")
        payload = dict(request or {})
        try:
            decision = self._orchestrator.route(job_type=kind, scope=scope)
        except AIUnavailable as exc:
            blocked = self._repository.create_job(
                agent_id={
                    "MARKET_INTELLIGENCE": "laya",
                    "STRATEGY_RESEARCH": "research",
                    "EVIDENCE_RESEARCH": "research",
                    "RISK_CHALLENGE": "risk-challenger",
                    "ORCHESTRATE": "prime",
                }[kind],
                job_type=kind,
                scope=str(scope).upper(),
                request=payload,
                status=AIJobStatus.BLOCKED.value,
                failure_reason=str(exc),
            )
            return self._public_job(blocked)

        queued = self._repository.create_job(
            agent_id=decision.agent_id,
            job_type=kind,
            scope=decision.scope.value,
            request=payload,
            status=AIJobStatus.QUEUED.value,
            provider_id=decision.provider_id,
            model_id=decision.model_id,
            evidence_ref=f"route:{decision.agent_id}:{decision.provider_id}:{decision.model_id}",
        )
        if not auto_submit:
            return self._public_job(queued)

        providers = {row["provider_id"]: row for row in self._repository.list_providers()}
        models = {row["model_id"]: row for row in self._repository.list_models()}
        try:
            output = self._execution.submit(
                job=queued,
                provider=providers[decision.provider_id],
                model=models[decision.model_id],
            )
        except Exception as exc:
            failed = self._repository.update_job(
                job_id=queued["job_id"],
                status=AIJobStatus.FAILED.value,
                failure_reason=str(exc),
            )
            return self._public_job(failed)
        completed = self._repository.update_job(
            job_id=queued["job_id"],
            status=AIJobStatus.COMPLETED.value,
            output=output,
            evidence_ref=str(output.get("evidence_ref") or queued.get("evidence_ref") or ""),
        )
        return self._public_job(completed)

    def cancel_job(self, *, job_id: str) -> dict[str, Any]:
        job = self._repository.get_job(job_id)
        if job is None:
            raise ValueError("AI job unavailable")
        if job["status"] not in {AIJobStatus.QUEUED.value, AIJobStatus.BLOCKED.value}:
            raise ValueError("AI job cannot be cancelled from current state")
        return self._public_job(self._repository.update_job(
            job_id=job_id,
            status=AIJobStatus.CANCELLED.value,
            failure_reason="OWNER_CANCELLED",
        ))
