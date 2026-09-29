"""Backend-owned AI provider/model health verification routes.

The route is protected by the global Owner step-up middleware. Owner input may
request a check, but only the configured backend execution adapter may assert
AVAILABLE/STALE/UNKNOWN/UNAVAILABLE health.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field


class AIProviderVerifyBody(BaseModel):
    model_id: str | None = Field(default=None, max_length=160)


def attach_ai_verification_routes(app: Any) -> Any:
    if getattr(app.state, "owner_ai_verification_attached", False):
        return app
    ai = getattr(app.state, "ai_control", None)
    if ai is None:
        app.state.owner_ai_verification_attached = False
        return app

    def require_owner(request: Request):
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

    router = APIRouter(prefix="/api/v1/owner/admin/ai", tags=["owner-ai-verification"])

    @router.post("/providers/{provider_id}/verify")
    def verify_provider(provider_id: str, body: AIProviderVerifyBody, request: Request) -> dict[str, Any]:
        require_owner(request)
        try:
            return ai.verify_provider(provider_id=provider_id, model_id=body.model_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="AI_PROVIDER_VERIFICATION_UNAVAILABLE") from exc

    app.include_router(router)
    app.state.owner_ai_verification_attached = True
    return app
