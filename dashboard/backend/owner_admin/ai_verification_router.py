"""Backend-owned AI provider configuration, credential, and health routes.

All trust-changing routes are protected by the global Owner step-up middleware.
Provider secrets are stored only through the existing Windows DPAPI vault and
are never returned by this API. Owner input may request a health check, but only
the configured backend execution adapter may assert provider/model availability.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, SecretStr

from .ai_credentials import LocalDPAPIAICredentialStore


class AIProviderVerifyBody(BaseModel):
    model_id: str | None = Field(default=None, max_length=160)


class AIProviderMetadataBody(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    provider_type: str = Field(min_length=1, max_length=80)
    enabled: bool = True


class AIProviderCredentialBody(BaseModel):
    token: SecretStr = Field(min_length=1, max_length=8192)


def _public_provider(row: dict[str, Any]) -> dict[str, Any]:
    public = dict(row)
    credential_ref = public.pop("credential_ref", None)
    public["credential_configured"] = bool(credential_ref)
    return public


def attach_ai_verification_routes(app: Any) -> Any:
    if getattr(app.state, "owner_ai_verification_attached", False):
        return app
    ai = getattr(app.state, "ai_control", None)
    repository = getattr(app.state, "owner_admin_repository", None)
    if ai is None or repository is None:
        app.state.owner_ai_verification_attached = False
        return app

    credential_store = LocalDPAPIAICredentialStore()

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

    def provider_or_404(provider_id: str) -> dict[str, Any]:
        provider = next(
            (row for row in repository.list_providers() if row.get("provider_id") == provider_id),
            None,
        )
        if provider is None:
            raise HTTPException(status_code=404, detail="AI provider unavailable")
        return provider

    router = APIRouter(prefix="/api/v1/owner/admin/ai", tags=["owner-ai-verification"])

    @router.post("/providers/{provider_id}/metadata")
    def configure_provider_metadata(
        provider_id: str,
        body: AIProviderMetadataBody,
        request: Request,
    ) -> dict[str, Any]:
        require_owner(request)
        existing = next(
            (row for row in repository.list_providers() if row.get("provider_id") == provider_id),
            None,
        )
        try:
            row = repository.upsert_provider(
                provider_id=provider_id,
                display_name=body.display_name,
                provider_type=body.provider_type,
                credential_ref=existing.get("credential_ref") if existing else None,
                enabled=body.enabled,
                authority_state="UNKNOWN",
            )
        except Exception as exc:
            raise HTTPException(status_code=422, detail="AI_PROVIDER_METADATA_REJECTED") from exc
        return {"source": "BACKEND", "trust": "FRESH", "provider": _public_provider(row)}

    @router.post("/providers/{provider_id}/credential")
    def store_provider_credential(
        provider_id: str,
        body: AIProviderCredentialBody,
        request: Request,
    ) -> dict[str, Any]:
        session = require_owner(request)
        provider = provider_or_404(provider_id)
        credential_ref: str | None = None
        try:
            credential_ref = credential_store.store_token(
                user_id=str(session.user.user_id),
                provider_id=provider_id,
                token=body.token.get_secret_value(),
            )
            row = repository.upsert_provider(
                provider_id=provider_id,
                display_name=str(provider["display_name"]),
                provider_type=str(provider["provider_type"]),
                credential_ref=credential_ref,
                enabled=bool(provider.get("enabled")),
                authority_state="UNKNOWN",
            )
        except Exception as exc:
            if credential_ref:
                try:
                    credential_store.delete_token(
                        user_id=str(session.user.user_id),
                        credential_ref=credential_ref,
                    )
                except Exception:
                    pass
            raise HTTPException(status_code=503, detail="AI_PROVIDER_CREDENTIAL_STORE_UNAVAILABLE") from exc
        return {
            "source": "BACKEND",
            "trust": "FRESH",
            "provider": _public_provider(row),
            "credential_stored": True,
        }

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
