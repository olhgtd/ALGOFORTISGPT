"""Authoritative Owner AI control service.

The service owns registry/configuration and research/shadow job evidence only.
It never invokes broker mutation, Live arm, RiskGate approval, or account/billing
mutation. Actual model execution is an injected adapter and is unavailable by
default. Provider/model availability can only be asserted by that backend
adapter; Owner input cannot self-certify AVAILABLE truth.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Protocol

from engine.ai.contracts import AIAvailability, AIJobStatus
from engine.ai.orchestrator import AIUnavailable, PrimeOrchestrator

from .owner_admin.repository import OwnerAdminRepository


class AIExecutionAdapter(Protocol):
    def health(self, *, provider: Mapping[str, Any], model: Mapping[str, Any] | None = None) -> Mapping[str, Any]: ...
    def submit(self, *, job: Mapping[str, Any], provider: Mapping[str, Any], model: Mapping[str, Any]) -> Mapping[str, Any]: ...


class UnavailableAIExecutionAdapter:
    def health(self, *, provider: Mapping[str, Any], model: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        return {
            "provider_state": AIAvailability.UNAVAILABLE.value,
            "model_state": AIAvailability.UNAVAILABLE.value if model is not None else None,
            "reason": "qualified AI model execution adapter is unavailable",
        }

    def submit(self, *, job: Mapping[str, Any], provider: Mapping[str, Any], model: Mapping[str, Any]) -> Mapping[str, Any]:
        raise AIUnavailable("qualified AI model execution adapter is unavailable")


_ALLOWED_STATES = {item.value for item in AIAvailability}
_ALLOWED_JOB_TYPES = {"MARKET_INTELLIGENCE", "STRATEGY_REVIEW", "INDEPENDENT_CANDIDATE", "STRATEGY_HUNTING", "STRATEGY_RESEARCH", "EVIDENCE_RESEARCH", "RISK_CHALLENGE", "ORCHESTRATE"}


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
    def _public_provider(row: Mapping[str, Any]) -> dict[str, Any]:
        result = dict(row)
        credential_ref = result.pop("credential_ref", None)
        result["credential_configured"] = bool(credential_ref)
        return result

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
        raw_providers = self._repository.list_providers()
        models = self._repository.list_models()
        bindings = self._repository.list_bindings()
        jobs = [self._public_job(row) for row in self._repository.list_jobs(limit=50)]
        candidates = self._candidate_board(jobs)

        provider_map = {row["provider_id"]: row for row in raw_providers}
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
                "provider": self._public_provider(provider) if provider else None,
                "model": model,
            })

        overall = "AVAILABLE" if projected_agents and all(a["authority_state"] == "AVAILABLE" for a in projected_agents) else (
            "STALE" if any(a["authority_state"] == "STALE" for a in projected_agents) else "UNAVAILABLE"
        )
        return {
            "source": "BACKEND",
            "trust": "FRESH",
            "candidates": candidates,
            "authority_state": overall,
            "live_state": "READ_ONLY/DISARMED",
            "broker_mutation": "ABSENT",
            "routing_owner": "PRIME",
            "agents": projected_agents,
            "providers": [self._public_provider(row) for row in raw_providers],
            "models": models,
            "bindings": bindings,
            "jobs": jobs,
        }

    @staticmethod
    def _candidate_board(jobs: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """Project only persisted independent-candidate evidence into the UI board.

        A queued/blocked job is never presented as an approved order or trade.
        If a model adapter returns a structured candidate payload, that payload is
        preserved; otherwise the board exposes the job envelope with an explicit
        candidate_job status so the UI cannot imply execution authority.
        """
        rows: list[dict[str, Any]] = []
        for job in jobs:
            if str(job.get("job_type") or "").upper() != "INDEPENDENT_CANDIDATE":
                continue
            output = job.get("output") if isinstance(job.get("output"), Mapping) else None
            raw_candidates = output.get("candidates") if output else None
            if raw_candidates is None and output and isinstance(output.get("candidate"), Mapping):
                raw_candidates = [output["candidate"]]
            if isinstance(raw_candidates, list) and raw_candidates:
                for candidate in raw_candidates:
                    if not isinstance(candidate, Mapping):
                        continue
                    rows.append({
                        "candidate_id": str(candidate.get("candidate_id") or job.get("job_id")),
                        "source": str(candidate.get("source") or candidate.get("agent_id") or job.get("agent_id") or "UNKNOWN"),
                        "direction": str(candidate.get("direction") or candidate.get("action") or "UNAVAILABLE"),
                        "strategy": str(candidate.get("strategy") or candidate.get("strategy_id") or "AI/LAYA"),
                        "provider": str(candidate.get("provider") or job.get("provider_id") or "UNAVAILABLE"),
                        "model": str(candidate.get("model") or job.get("model_id") or "UNAVAILABLE"),
                        "evidence": str(candidate.get("evidence_ref") or job.get("evidence_ref") or "UNAVAILABLE"),
                        "status": str(candidate.get("status") or job.get("status") or "UNAVAILABLE"),
                        "execution_scope": str(candidate.get("execution_scope") or "RISK_GATED_CANDIDATE"),
                    })
            else:
                request = job.get("request") if isinstance(job.get("request"), Mapping) else {}
                rows.append({
                    "candidate_id": str(job.get("job_id") or "UNAVAILABLE"),
                    "source": str(job.get("agent_id") or "UNKNOWN"),
                    "direction": str(request.get("direction") or request.get("action") or "UNAVAILABLE"),
                    "strategy": str(request.get("strategy_id") or "AI/LAYA"),
                    "provider": str(job.get("provider_id") or "UNAVAILABLE"),
                    "model": str(job.get("model_id") or "UNAVAILABLE"),
                    "evidence": str(job.get("evidence_ref") or "UNAVAILABLE"),
                    "status": f"CANDIDATE_JOB_{job.get('status') or 'UNKNOWN'}",
                    "execution_scope": "RISK_GATED_CANDIDATE",
                })
        return rows

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
        # Owner configuration cannot self-certify health. A newly configured or
        # changed provider is UNKNOWN until verify_provider asks the backend adapter.
        requested_state = self._state(authority_state)
        if requested_state == AIAvailability.AVAILABLE.value:
            requested_state = AIAvailability.UNKNOWN.value
        row = self._repository.upsert_provider(
            provider_id=provider_id,
            display_name=display_name,
            provider_type=provider_type,
            credential_ref=credential_ref,
            enabled=enabled,
            authority_state=requested_state,
        )
        return self._public_provider(row)

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
        requested_state = self._state(authority_state)
        if requested_state == AIAvailability.AVAILABLE.value:
            requested_state = AIAvailability.UNKNOWN.value
        return self._repository.upsert_model(
            model_id=model_id,
            provider_id=provider_id,
            display_name=display_name,
            capability=capability,
            enabled=enabled,
            authority_state=requested_state,
        )

    def verify_provider(self, *, provider_id: str, model_id: str | None = None) -> dict[str, Any]:
        providers = {row["provider_id"]: row for row in self._repository.list_providers()}
        models = {row["model_id"]: row for row in self._repository.list_models()}
        provider = providers.get(provider_id)
        if provider is None:
            raise ValueError("AI provider unavailable")
        model = models.get(model_id) if model_id else None
        if model_id and (model is None or model.get("provider_id") != provider_id):
            raise ValueError("AI model/provider binding mismatch")

        result = dict(self._execution.health(provider=provider, model=model))
        provider_state = self._state(str(result.get("provider_state") or "UNKNOWN"))
        updated_provider = self._repository.upsert_provider(
            provider_id=provider_id,
            display_name=str(provider["display_name"]),
            provider_type=str(provider["provider_type"]),
            credential_ref=provider.get("credential_ref"),
            enabled=bool(provider.get("enabled")),
            authority_state=provider_state,
        )
        updated_model = None
        if model is not None:
            model_state = self._state(str(result.get("model_state") or "UNKNOWN"))
            updated_model = self._repository.upsert_model(
                model_id=str(model["model_id"]),
                provider_id=provider_id,
                display_name=str(model["display_name"]),
                capability=str(model["capability"]),
                enabled=bool(model.get("enabled")),
                authority_state=model_state,
            )
        return {
            "source": "BACKEND",
            "trust": "FRESH",
            "provider": self._public_provider(updated_provider),
            "model": updated_model,
            "reason": str(result.get("reason") or "BACKEND_ADAPTER_HEALTH_CHECK"),
        }

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
                    "STRATEGY_REVIEW": "research",
                    "INDEPENDENT_CANDIDATE": "research",
                    "STRATEGY_HUNTING": "research",
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

        route_ref = str(decision.evidence.get("evidence_ref") or "")
        queued = self._repository.create_job(
            agent_id=decision.agent_id,
            job_type=kind,
            scope=decision.scope.value,
            request=payload,
            status=AIJobStatus.QUEUED.value,
            provider_id=decision.provider_id,
            model_id=decision.model_id,
            evidence_ref=route_ref,
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
