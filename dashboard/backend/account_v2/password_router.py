"""Shared Owner/User password activation and login HTTP authority.

The router is additive: it composes the existing security store, session
service, auth policy, mTLS authority and Core Audit.  It never accepts a role
or workspace claim from the caller.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from dashboard.backend.domain import AccessRoute, Role
from dashboard.backend.security import SecurityError
from dashboard.backend.security_store import SecurityStoreError

from .password_accounts import PasswordAccountAuthority


class PasswordActivationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: str = Field(min_length=1, max_length=128)
    activation_code: str = Field(min_length=1, max_length=256)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=256)
    confirm_password: str = Field(min_length=8, max_length=256)


class PasswordLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=256)


def _client_key(request: Request) -> str:
    # Do not trust caller-controlled forwarding headers at the private runtime
    # boundary.  A deployment proxy may provide its own trusted-edge adapter in
    # the future; until then the socket peer is the only local evidence.
    host = request.client.host if request.client is not None else "unknown"
    return f"ip:{host}"


def attach_password_account_routes(app: Any) -> Any:
    """Attach the canonical password account router exactly once."""
    if getattr(app.state, "password_account_routes_attached", False):
        return app

    store = getattr(app.state, "security_store", None)
    sessions = getattr(app.state, "sessions", None)
    if store is None or sessions is None:
        app.state.password_account_routes_attached = False
        app.state.password_account_routes_error = "ACCOUNT_AUTHORITY_UNAVAILABLE"
        return app

    authority = PasswordAccountAuthority(store)
    app.state.password_accounts = authority
    app.state.password_account_routes_attached = True

    router = APIRouter(prefix="/api/v1/auth/password", tags=["password-account-authority"])

    def _limiter(name: str):
        policy = getattr(app.state, "auth_policy", None)
        return getattr(policy, name, None) if policy is not None else None

    @staticmethod
    def _locked(limiter, key: str) -> tuple[bool, int]:
        if limiter is None:
            return False, 0
        return limiter.is_locked_out(key)

    def _require_not_locked(limiter, *keys: str) -> None:
        remaining = 0
        for key in keys:
            locked, rem = _locked(limiter, key)
            if locked:
                remaining = max(remaining, rem)
        if remaining:
            raise HTTPException(
                status_code=429,
                detail=f"RATE_LIMIT_COOLDOWN: Cooldown active for {remaining}s",
                headers={"Retry-After": str(remaining)},
            )

    def _record_failure(limiter, *keys: str) -> None:
        if limiter is None:
            return
        remaining = 0
        locked_any = False
        for key in keys:
            locked, rem = limiter.record_failure(key)
            locked_any = locked_any or locked
            remaining = max(remaining, rem)
        if locked_any:
            raise HTTPException(
                status_code=429,
                detail=f"RATE_LIMIT_COOLDOWN: Cooldown active for {remaining}s",
                headers={"Retry-After": str(remaining)},
            )

    def _record_success(limiter, *keys: str) -> None:
        if limiter is None:
            return
        for key in keys:
            limiter.record_success(key)

    def _audit(*, actor_id: UUID, action: str, rejected: bool = False) -> str:
        audit = getattr(app.state, "core_security_audit", None)
        if audit is None or not hasattr(audit, "record"):
            raise HTTPException(status_code=503, detail="AUTHORITATIVE_AUDIT_UNAVAILABLE")
        try:
            return str(
                audit.record(
                    actor_id=actor_id,
                    action=action,
                    rejected=rejected,
                    payload={"channel": "PASSWORD_ENTRY_GATE"},
                    resource_id=str(actor_id),
                )
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail="AUTHORITATIVE_AUDIT_UNAVAILABLE") from exc

    def _normal_route_assurance(request: Request) -> bool:
        """Return the boolean SessionService expects for normal-route assurance.

        If deployment policy requires mTLS, only the process-wired mTLS
        authority may satisfy it.  If policy explicitly does not require mTLS
        (LOCAL_PRIVATE), normal transport assurance is already satisfied by
        policy; this does not claim that mTLS is configured.
        """
        config = sessions._config
        if not config.normal_mtls_required:
            return True
        mtls = getattr(app.state, "mtls_authority", None)
        try:
            return bool(mtls is not None and mtls.verified(request))
        except Exception:
            return False

    @router.post("/activate")
    def activate_password_account(body: PasswordActivationRequest, request: Request) -> dict[str, bool]:
        if body.password != body.confirm_password:
            raise HTTPException(status_code=422, detail="Passwords do not match")

        identifier = body.identifier.strip()
        activation_key = f"password_activation:{identifier.lower()}"
        ip_key = _client_key(request)
        limiter = _limiter("otp_limiter")
        _require_not_locked(limiter, ip_key, activation_key)

        try:
            # Resolve/validate the one-time invitation before writing audit
            # authorization evidence.  No activation code or password enters
            # the audit payload.
            subject = store.activation_subject(identifier, body.activation_code)
            authoritative_email = (subject["bound_email"] or "").strip().lower()
            if authoritative_email != body.email.strip().lower():
                raise SecurityStoreError("Activation unavailable")
            actor_id = UUID(subject["user_id"])
            _audit(actor_id=actor_id, action="USER_PASSWORD_ACTIVATION_AUTHORIZED")
            authority.activate_user_password(
                identifier=identifier,
                activation_code=body.activation_code,
                email=body.email,
                password=body.password,
            )
            _record_success(limiter, ip_key, activation_key)
            return {"activated": True, "authentication_required": True}
        except HTTPException:
            raise
        except (SecurityStoreError, ValueError, TypeError, KeyError):
            _record_failure(limiter, ip_key, activation_key)
            raise HTTPException(status_code=403, detail="Activation unavailable") from None

    @router.post("/login")
    def password_login(body: PasswordLoginRequest, request: Request) -> dict[str, Any]:
        identifier = body.identifier.strip()
        identifier_key = f"password_login:{identifier.lower()}"
        ip_key = _client_key(request)
        limiter = _limiter("login_limiter")
        _require_not_locked(limiter, ip_key, identifier_key)

        identity = authority.verify_identity_password(
            identifier=identifier,
            password=body.password,
        )
        if identity is None:
            _record_failure(limiter, ip_key, identifier_key)
            raise HTTPException(status_code=401, detail="INVALID_ID_OR_PASSWORD")

        workspace = "owner" if identity.role is Role.OWNER else "user"
        if not identity.is_workspace_eligible(workspace):
            # Valid credentials do not override lifecycle/service authority.
            _record_failure(limiter, ip_key, identifier_key)
            raise HTTPException(status_code=403, detail="ACCOUNT_ACCESS_UNAVAILABLE")

        # Audit verified identity before issuing a bearer session.  Password
        # authentication is never represented as fresh WebAuthn step-up.
        _audit(actor_id=identity.user_id, action="PASSWORD_LOGIN_VERIFIED")
        try:
            session = sessions.issue(
                user=identity,
                route=AccessRoute.NORMAL,
                mtls_verified=_normal_route_assurance(request),
                step_up_satisfied=False,
            )
        except SecurityError as exc:
            raise HTTPException(status_code=403, detail="ACCOUNT_ACCESS_UNAVAILABLE") from exc

        _record_success(limiter, ip_key, identifier_key)
        return {
            "access_token": session.token,
            "expires_at_utc": session.expires_at.isoformat(),
            "subject": str(session.user.user_id),
            "role": session.user.role.value,
            "sx_id": session.user.sx_id,
            "workspace_eligibility": {
                "owner": session.user.is_workspace_eligible("owner"),
                "user": session.user.is_workspace_eligible("user"),
            },
        }

    app.include_router(router)
    return app
