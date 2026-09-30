"""Shared Owner/User password activation and login HTTP authority.

The router is additive: it composes the existing security store, session
service, auth policy, mTLS authority and Core Audit.  It never accepts a role
or workspace claim from the caller.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

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


class PasswordOwnerBootstrapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=160)
    email: str = Field(min_length=3, max_length=320)
    bootstrap_token: str = Field(min_length=1, max_length=512)
    password: str = Field(min_length=8, max_length=256)
    confirm_password: str = Field(min_length=8, max_length=256)


def _client_key(request: Request) -> str:
    # Do not trust caller-controlled forwarding headers at the private runtime
    # boundary. A trusted-edge deployment can supply its own adapter later.
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
        """Return the normal-route assurance input expected by SessionService.

        If mTLS is policy-required, only the process-wired mTLS authority may
        satisfy it. LOCAL_PRIVATE explicitly does not require mTLS, so normal
        route assurance is satisfied by that policy without claiming mTLS is
        configured.
        """
        config = sessions._config
        if not config.normal_mtls_required:
            return True
        mtls = getattr(app.state, "mtls_authority", None)
        try:
            return bool(mtls is not None and mtls.verified(request))
        except Exception:
            return False

    def _session_payload(session) -> dict[str, Any]:
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

    def _issue_password_session(identity, request: Request):
        try:
            return sessions.issue(
                user=identity,
                route=AccessRoute.NORMAL,
                mtls_verified=_normal_route_assurance(request),
                step_up_satisfied=False,
            )
        except SecurityError as exc:
            raise HTTPException(status_code=403, detail="ACCOUNT_ACCESS_UNAVAILABLE") from exc

    def _login(body: PasswordLoginRequest, request: Request) -> dict[str, Any]:
        identifier = body.identifier.strip()
        identifier_key = f"password_login:{identifier.lower()}"
        ip_key = _client_key(request)
        limiter = _limiter("login_limiter")
        _require_not_locked(limiter, ip_key, identifier_key)

        identity = authority.verify_identity_password(identifier=identifier, password=body.password)
        if identity is None:
            _record_failure(limiter, ip_key, identifier_key)
            raise HTTPException(status_code=401, detail="INVALID_ID_OR_PASSWORD")

        workspace = "owner" if identity.role is Role.OWNER else "user"
        if not identity.is_workspace_eligible(workspace):
            _record_failure(limiter, ip_key, identifier_key)
            raise HTTPException(status_code=403, detail="ACCOUNT_ACCESS_UNAVAILABLE")

        _audit(actor_id=identity.user_id, action="PASSWORD_LOGIN_VERIFIED")
        session = _issue_password_session(identity, request)
        _record_success(limiter, ip_key, identifier_key)
        return _session_payload(session)

    def _bootstrap_owner(body: PasswordOwnerBootstrapRequest, request: Request) -> dict[str, Any]:
        if body.password != body.confirm_password:
            raise HTTPException(status_code=422, detail="Passwords do not match")
        decision_reader = getattr(app.state, "owner_bootstrap_decision", None)
        if callable(decision_reader):
            decision = decision_reader()
            if not bool(getattr(decision, "setup_allowed", False)):
                raise HTTPException(status_code=403, detail="OWNER_SETUP_NOT_AUTHORIZED")
        if store.has_initialized_owner():
            raise HTTPException(status_code=403, detail="OWNER_SETUP_NOT_AUTHORIZED")

        ip_key = _client_key(request)
        limiter = _limiter("login_limiter")
        _require_not_locked(limiter, ip_key)
        try:
            owner_rows = [row for row in store.list_users() if row["role"] == "OWNER"]
            if len(owner_rows) == 1:
                actor_id = UUID(owner_rows[0]["user_id"])
            elif len(owner_rows) == 0:
                auth_row = store._conn.execute(
                    "SELECT user_id FROM bootstrap_authorizations WHERE token_hash = ?",
                    (store.token_hash(body.bootstrap_token.strip()),),
                ).fetchone()
                if auth_row is None:
                    raise SecurityStoreError("invalid bootstrap authorization")
                actor_id = UUID(auth_row["user_id"])
            else:
                raise SecurityStoreError("Ambiguous local Owner authority")

            _audit(actor_id=actor_id, action="LOCAL_OWNER_PROVISIONING_AUTHORIZED")
            identity = store.initialize_owner_password(
                token=body.bootstrap_token.strip(),
                display_name=body.display_name.strip(),
                email=body.email.strip(),
                password=body.password,
            )
            session = _issue_password_session(identity, request)
            _record_success(limiter, ip_key)
            return _session_payload(session)
        except HTTPException:
            raise
        except (SecurityStoreError, ValueError, TypeError, KeyError) as exc:
            _record_failure(limiter, ip_key)
            raise HTTPException(status_code=400, detail="OWNER_SETUP_REJECTED") from exc

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
        return _login(body, request)

    @router.post("/owner-bootstrap")
    def password_owner_bootstrap(body: PasswordOwnerBootstrapRequest, request: Request) -> dict[str, Any]:
        return _bootstrap_owner(body, request)

    app.include_router(router)

    # Legacy packaged clients continue to function, but their password-created
    # sessions are now delegated to the canonical authority and never receive a
    # synthetic fresh-WebAuthn step-up bit.
    @app.middleware("http")
    async def legacy_local_password_bridge(request: Request, call_next):
        if request.method.upper() != "POST":
            return await call_next(request)
        if request.url.path not in {"/api/v1/auth/local/login", "/api/v1/auth/local/setup"}:
            return await call_next(request)
        try:
            payload = await request.json()
            if request.url.path.endswith("/login"):
                body = PasswordLoginRequest(
                    identifier=str(payload.get("email") or payload.get("identifier") or ""),
                    password=str(payload.get("password") or ""),
                )
                result = _login(body, request)
            else:
                body = PasswordOwnerBootstrapRequest.model_validate(payload)
                result = _bootstrap_owner(body, request)
            return JSONResponse(result, status_code=200)
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
        except ValidationError:
            return JSONResponse({"detail": "INVALID_AUTH_REQUEST"}, status_code=422)
        except Exception:
            return JSONResponse({"detail": "AUTHENTICATION_UNAVAILABLE"}, status_code=503)

    return app
