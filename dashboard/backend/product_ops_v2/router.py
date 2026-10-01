"""Read-only Phase 9 Product Operations HTTP boundary.

This module exposes already-authorized read models only. It cannot place,
modify or cancel broker orders, mint ApprovedOrder, arm Live, or execute AI
trading actions.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from .service import ProductOpsService


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _session_user(app: Any, request: Request) -> Any:
    authorization = request.headers.get("authorization")
    token = authorization.removeprefix("Bearer ").strip() if authorization else None
    sessions = getattr(app.state, "sessions", None)
    if sessions is None:
        raise HTTPException(status_code=503, detail="SESSION_AUTHORITY_UNAVAILABLE")
    try:
        session = sessions.require(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="authentication required") from exc
    user = getattr(session, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    if _value(getattr(user, "account_status", "ACTIVE")) != "ACTIVE":
        raise HTTPException(status_code=403, detail="active account required")
    return user


def attach_product_ops_routes(app: Any) -> Any:
    """Attach ProductOps read-model routes once and return the same app."""
    if getattr(app.state, "product_ops_routes_attached", False):
        return app

    service = getattr(app.state, "product_ops_service", None)
    if service is None:
        service = ProductOpsService(repository=None)
        app.state.product_ops_service = service

    router = APIRouter(prefix="/api/v1/product-ops", tags=["product-ops"])

    @router.get("/owner/health")
    def owner_health(request: Request) -> dict[str, Any]:
        user = _session_user(app, request)
        if _value(getattr(user, "role", None)) != "OWNER":
            raise HTTPException(status_code=403, detail="active owner authority required")
        provider = getattr(app.state, "product_ops_owner_health_provider", None)
        if provider is None:
            raise HTTPException(status_code=503, detail="PRODUCT_OPS_READ_MODEL_UNAVAILABLE")
        try:
            model = service.owner_health(health=provider())
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail="PRODUCT_OPS_READ_MODEL_UNAVAILABLE") from exc
        payload = asdict(model)
        payload["live_state"] = "READ_ONLY/DISARMED"
        payload["ai_authority"] = "RESEARCH_SHADOW_ONLY"
        return payload

    @router.get("/privacy/current")
    def current_privacy(request: Request) -> dict[str, Any]:
        user = _session_user(app, request)
        principal_ref = str(getattr(user, "user_id", ""))
        if not principal_ref:
            raise HTTPException(status_code=401, detail="authentication required")
        provider = getattr(app.state, "product_ops_user_privacy_provider", None)
        if provider is None:
            raise HTTPException(status_code=503, detail="PRODUCT_OPS_READ_MODEL_UNAVAILABLE")
        try:
            model = provider(principal_ref)
            scoped = service.user_privacy(
                principal_ref=principal_ref,
                model=model,
                requested_principal_ref=principal_ref,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="CROSS_USER_READ_DENIED") from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail="PRODUCT_OPS_READ_MODEL_UNAVAILABLE") from exc
        return asdict(scoped)

    app.include_router(router)
    app.state.product_ops_routes_attached = True
    return app
