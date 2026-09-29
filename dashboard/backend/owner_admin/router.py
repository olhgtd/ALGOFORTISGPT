"""Attach the authoritative Owner/Admin + AI control plane to a product app.

The legacy dashboard API remains the product substrate.  This module adds a
thin authoritative control layer plus a middleware gate that requires fresh,
action-bound WebAuthn step-up proof for destructive Owner routes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from dashboard.backend.ai_control import AIControlService

from .audit import OwnerAdminAudit
from .contracts import AuthorityState, authority_state_from_source
from .repository import OwnerAdminRepository
from .step_up import OwnerStepUpAuthority, classify_destructive_route


class StepUpOptionsBody(BaseModel):
    action_family: str = Field(min_length=1, max_length=80)
    resource_ref: str | None = Field(default=None, max_length=256)


class StepUpCompleteBody(StepUpOptionsBody):
    challenge_id: str = Field(min_length=1, max_length=256)
    response: dict[str, Any]


class AIProviderBody(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    provider_type: str = Field(min_length=1, max_length=80)
    credential_ref: str | None = Field(default=None, max_length=512)
    enabled: bool = True
    authority_state: str = Field(default="UNKNOWN", max_length=20)


class AIModelBody(BaseModel):
    provider_id: str = Field(min_length=1, max_length=120)
    display_name: str = Field(min_length=1, max_length=160)
    capability: str = Field(default="GENERAL", max_length=100)
    enabled: bool = True
    authority_state: str = Field(default="UNKNOWN", max_length=20)


class AIBindingBody(BaseModel):
    provider_id: str = Field(min_length=1, max_length=120)
    model_id: str = Field(min_length=1, max_length=160)
    fallback_policy: dict[str, Any] = Field(default_factory=lambda: {"mode": "FAIL_CLOSED"})


class AIAgentPolicyBody(BaseModel):
    enabled: bool


class AIJobBody(BaseModel):
    job_type: str = Field(min_length=1, max_length=80)
    scope: str = Field(default="RESEARCH", max_length=20)
    request: dict[str, Any] = Field(default_factory=dict)
    auto_submit: bool = False


def _state(payload: dict[str, Any] | None) -> str:
    if not payload:
        return AuthorityState.UNAVAILABLE.value
    return authority_state_from_source(
        source=str(payload.get("source") or "UNAVAILABLE"),
        trust=str(payload.get("trust") or "UNKNOWN"),
    ).value


def attach_owner_admin_control_plane(app: Any) -> Any:
    """Attach once; returns the same FastAPI app."""
    if getattr(app.state, "owner_admin_control_plane_attached", False):
        return app

    security_store = getattr(app.state, "security_store", None)
    if security_store is None:
        # Product runtime can still start fail-closed; no Owner mutation/AI
        # authority is fabricated without the durable security authority.
        app.state.owner_admin_control_plane_attached = False
        app.state.owner_admin_control_plane_error = "SECURITY_AUTHORITY_UNAVAILABLE"
        return app

    repository = OwnerAdminRepository(security_store)
    step_up = OwnerStepUpAuthority(
        repository=repository,
        ceremonies=getattr(app.state, "webauthn_ceremonies", None),
    )
    audit = OwnerAdminAudit(
        core_audit=getattr(app.state, "core_security_audit", None),
        repository=repository,
    )
    ai = AIControlService(repository=repository)

    app.state.owner_admin_repository = repository
    app.state.owner_step_up = step_up
    app.state.owner_admin_audit = audit
    app.state.ai_control = ai
    app.state.owner_admin_control_plane_attached = True

    def owner_session_from_request(request: Request):
        authorization = request.headers.get("authorization")
        token = authorization.removeprefix("Bearer ").strip() if authorization else None
        try:
            session = app.state.sessions.require(token)
        except Exception as exc:
            raise HTTPException(status_code=401, detail="authentication required") from exc
        role = getattr(getattr(session, "user", None), "role", None)
        role_value = getattr(role, "value", role)
        account_status = getattr(getattr(session, "user", None), "account_status", None)
        account_value = getattr(account_status, "value", account_status)
        if role_value != "OWNER" or account_value != "ACTIVE":
            raise HTTPException(status_code=403, detail="active owner authority required")
        return session

    # Middleware hardens legacy destructive Owner endpoints as well as new AI
    # governance endpoints without rewriting the proven monolithic API.
    @app.middleware("http")
    async def owner_admin_step_up_boundary(request: Request, call_next):
        classified = classify_destructive_route(request.method, request.url.path)
        if classified is None:
            return await call_next(request)

        action_family, resource_ref = classified
        try:
            session = owner_session_from_request(request)
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

        grant = request.headers.get("x-algofortis-step-up", "")
        try:
            step_ref = step_up.consume_grant(
                token=grant,
                user_id=session.user.user_id,
                action_family=action_family,
                resource_ref=resource_ref,
            )
            auth_ref = audit.require_authorization_event(
                actor_id=session.user.user_id,
                action_family=action_family,
                resource_ref=resource_ref,
                step_up_ref=step_ref,
                details={"path": request.url.path, "method": request.method},
            )
        except PermissionError as exc:
            try:
                audit.failure_incident(
                    actor_id=session.user.user_id,
                    action_family=action_family,
                    resource_ref=resource_ref,
                    reason_code="STEP_UP_REQUIRED_OR_INVALID",
                    status="REJECTED",
                    details={"path": request.url.path},
                )
            except Exception:
                return JSONResponse({"detail": "authoritative audit unavailable"}, status_code=503)
            return JSONResponse({"detail": "fresh WebAuthn step-up required"}, status_code=403)
        except Exception:
            return JSONResponse({"detail": "authoritative audit unavailable"}, status_code=503)

        response = await call_next(request)
        try:
            if response.status_code < 400:
                audit.record_outcome(
                    actor_id=session.user.user_id,
                    action_family=action_family,
                    resource_ref=resource_ref,
                    status="APPLIED",
                    reason_code="BACKEND_CONFIRMED",
                    details={"http_status": response.status_code},
                )
            else:
                audit.failure_incident(
                    actor_id=session.user.user_id,
                    action_family=action_family,
                    resource_ref=resource_ref,
                    reason_code=f"HTTP_{response.status_code}",
                    status="REJECTED" if response.status_code < 500 else "FAILED",
                )
            response.headers["X-AlgoFortis-Audit-Ref"] = auth_ref
        except Exception:
            # Authorization audit was durably recorded before mutation.  A
            # missing outcome is surfaced loudly rather than hidden as success.
            response.headers["X-AlgoFortis-Audit-Outcome"] = "PENDING"
        return response

    router = APIRouter(prefix="/api/v1/owner/admin", tags=["owner-admin-authority"])

    @router.get("/authority")
    def owner_authority(request: Request) -> dict[str, Any]:
        session = owner_session_from_request(request)

        def read(name: str, method: str) -> dict[str, Any]:
            adapter = getattr(app.state, name, None)
            if adapter is None or not hasattr(adapter, method):
                return {
                    "source": "UNAVAILABLE", "trust": "UNKNOWN",
                    "as_of_utc": datetime.now(timezone.utc).isoformat(),
                    "error": f"{name.upper()}_UNAVAILABLE",
                }
            try:
                return getattr(adapter, method)()
            except Exception:
                return {
                    "source": "UNAVAILABLE", "trust": "UNKNOWN",
                    "as_of_utc": datetime.now(timezone.utc).isoformat(),
                    "error": f"{name.upper()}_UNAVAILABLE",
                }

        health = read("health_adapter", "read_persistence_health")
        access = read("access_adapter", "read_access_records")
        strategies = read("strategies_adapter", "read_strategies")
        connections = read("connections_adapter", "read_connections")
        datasets = read("datasets_adapter", "read_datasets")
        try:
            security = app.state.security_status.public_status(session.user.user_id)
            security_state = "AVAILABLE"
        except Exception:
            security = {"error": "SECURITY_STATUS_UNAVAILABLE"}
            security_state = "UNAVAILABLE"
        ai_snapshot = ai.snapshot()
        return {
            "source": "BACKEND",
            "trust": "FRESH",
            "live_state": "READ_ONLY/DISARMED",
            "broker_mutation": "ABSENT_FROM_OWNER_AUTHORITY",
            "surfaces": {
                "health": {"authority_state": _state(health), **health},
                "access": {"authority_state": _state(access), **access},
                "strategies": {"authority_state": _state(strategies), **strategies},
                "connections": {"authority_state": _state(connections), **connections},
                "datasets": {"authority_state": _state(datasets), **datasets},
                "security": {"authority_state": security_state, **security},
                "ai": ai_snapshot,
            },
            "incidents": repository.list_incidents(limit=20),
        }

    @router.post("/step-up/options")
    def step_up_options(body: StepUpOptionsBody, request: Request) -> dict[str, Any]:
        session = owner_session_from_request(request)
        return step_up.issue_options(
            user=session.user,
            action_family=body.action_family,
            resource_ref=body.resource_ref,
        )

    @router.post("/step-up/complete")
    def step_up_complete(body: StepUpCompleteBody, request: Request) -> dict[str, Any]:
        session = owner_session_from_request(request)
        try:
            result = step_up.complete(
                user=session.user,
                challenge_id=body.challenge_id,
                action_family=body.action_family,
                resource_ref=body.resource_ref,
                response=body.response,
            )
            audit.record_outcome(
                actor_id=session.user.user_id,
                action_family=body.action_family,
                resource_ref=body.resource_ref,
                status="APPLIED",
                reason_code="WEBAUTHN_STEP_UP_VERIFIED",
            )
            return result
        except Exception as exc:
            try:
                audit.failure_incident(
                    actor_id=session.user.user_id,
                    action_family=body.action_family,
                    resource_ref=body.resource_ref,
                    reason_code="WEBAUTHN_STEP_UP_FAILED",
                    status="REJECTED",
                )
            except Exception:
                pass
            raise HTTPException(status_code=403, detail="WebAuthn step-up verification failed") from exc

    @router.get("/incidents")
    def incidents(request: Request, limit: int = 100) -> dict[str, Any]:
        owner_session_from_request(request)
        return {"source": "BACKEND", "trust": "FRESH", "incidents": repository.list_incidents(limit=limit)}

    @router.get("/ai")
    def ai_snapshot(request: Request) -> dict[str, Any]:
        owner_session_from_request(request)
        return ai.snapshot()

    @router.post("/ai/providers/{provider_id}")
    def ai_provider(provider_id: str, body: AIProviderBody, request: Request) -> dict[str, Any]:
        owner_session_from_request(request)
        return ai.configure_provider(provider_id=provider_id, **body.model_dump())

    @router.post("/ai/models/{model_id}")
    def ai_model(model_id: str, body: AIModelBody, request: Request) -> dict[str, Any]:
        owner_session_from_request(request)
        return ai.configure_model(model_id=model_id, **body.model_dump())

    @router.post("/ai/agents/{agent_id}/binding")
    def ai_binding(agent_id: str, body: AIBindingBody, request: Request) -> dict[str, Any]:
        owner_session_from_request(request)
        return ai.bind_agent(agent_id=agent_id, **body.model_dump())

    @router.post("/ai/agents/{agent_id}/policy")
    def ai_agent_policy(agent_id: str, body: AIAgentPolicyBody, request: Request) -> dict[str, Any]:
        owner_session_from_request(request)
        return ai.set_agent_policy(agent_id=agent_id, enabled=body.enabled)

    @router.post("/ai/jobs")
    def ai_job(body: AIJobBody, request: Request) -> dict[str, Any]:
        session = owner_session_from_request(request)
        result = ai.create_job(**body.model_dump())
        try:
            audit.record_outcome(
                actor_id=session.user.user_id,
                action_family="AI_JOB_CREATE",
                resource_ref=result.get("job_id"),
                status="APPLIED" if result.get("status") != "BLOCKED" else "REJECTED",
                reason_code=str(result.get("failure_reason") or "PRIME_ROUTING_RECORDED"),
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail="AI job audit unavailable") from exc
        return result

    @router.post("/ai/jobs/{job_id}/cancel")
    def ai_job_cancel(job_id: str, request: Request) -> dict[str, Any]:
        owner_session_from_request(request)
        return ai.cancel_job(job_id=job_id)

    app.include_router(router)
    return app
