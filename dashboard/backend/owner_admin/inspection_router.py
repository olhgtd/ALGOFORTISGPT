"""Attach read-only per-user inspection routes to the product app."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from .user_inspection import OwnerUserInspectionService, OwnerUserInspectionUnavailable


def attach_owner_user_inspection(app: Any) -> Any:
    if getattr(app.state, "owner_user_inspection_attached", False):
        return app
    if getattr(app.state, "security_store", None) is None:
        app.state.owner_user_inspection_attached = False
        return app

    service = OwnerUserInspectionService(app)
    app.state.owner_user_inspection = service
    app.state.owner_user_inspection_attached = True

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

    router = APIRouter(prefix="/api/v1/owner/admin", tags=["owner-user-inspection"])

    @router.get("/users/{identifier}/inspection")
    def user_inspection(identifier: str, request: Request) -> dict[str, Any]:
        require_owner(request)
        try:
            return service.snapshot(identifier)
        except OwnerUserInspectionUnavailable as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="USER_INSPECTION_AUTHORITY_UNAVAILABLE") from exc

    app.include_router(router)
    return app
