"""Fail-closed access and session primitives for Phase 9.

The actual WebAuthn ceremony is performed by a deployment supplied verifier.
This module never offers a password fallback and never grants safety authority.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Protocol
from urllib.parse import urlparse
from uuid import UUID, uuid4

from fido2.server import Fido2Server
from fido2.webauthn import (
    AttestedCredentialData,
    AuthenticationResponse,
    PublicKeyCredentialRpEntity,
    PublicKeyCredentialUserEntity,
)

from .domain import (
    AccessRoute,
    AccountAccessStatus,
    ActivationStatus,
    Lifecycle,
    Role,
    ServiceEntitlementStatus,
    ServiceTermType,
    SessionRisk,
    UserIdentity,
    utc_now,
)
from .security_store import SQLiteSecurityStore, SecurityStoreError


class SecurityError(PermissionError):
    pass


class SecurityStatus(str, Enum):
    """Deployment truth exposed to the control center.

    ``REQUIRED`` is policy, not evidence that an integration is deployed.
    The UI must only render CONFIGURED after this authority has verified the
    relevant configuration and enrollment prerequisites.
    """

    CONFIGURED = "CONFIGURED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNKNOWN = "UNKNOWN"
    NEEDS_ROTATION = "NEEDS_ROTATION"


@dataclass(frozen=True)
class WebAuthnRelyingParty:
    """An explicit RP/origin pair; no implicit deployment defaults exist."""

    rp_id: str
    origin: str
    development_only: bool = False

    def validate(self) -> None:
        parsed = urlparse(self.origin)
        if not self.rp_id or not parsed.scheme or not parsed.netloc:
            raise SecurityError("WebAuthn RP ID and origin must be explicit and valid")
        if self.development_only:
            if self.rp_id != "localhost" or parsed.scheme != "http" or parsed.hostname != "localhost" or parsed.port is None:
                raise SecurityError("development WebAuthn profile must be explicit localhost HTTP with a port")
        else:
            # Production strict invariant validation
            if parsed.scheme != "https":
                raise SecurityError("production WebAuthn origin must use HTTPS")
            origin_host = parsed.hostname or ""
            if not origin_host:
                raise SecurityError("production WebAuthn origin host is invalid")
            if origin_host != self.rp_id and not origin_host.endswith("." + self.rp_id):
                raise SecurityError(f"origin {self.origin} does not match WebAuthn RP ID {self.rp_id}")
            if self.rp_id.lower() in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
                raise SecurityError("production WebAuthn RP ID cannot be loopback")
            if any(char in self.rp_id for char in " :/?#[]@!$&'()*+,;="):
                raise SecurityError("production WebAuthn RP ID contains invalid characters")

    @property
    def route(self) -> AccessRoute:
        return AccessRoute.BREAK_GLASS if "recovery" in self.rp_id.lower() else AccessRoute.NORMAL


class WebAuthnCeremonyService:
    """Real server-side FIDO2 ceremony authority backed by durable state."""

    CHALLENGE_TTL = timedelta(minutes=5)

    def __init__(self, *, store: SQLiteSecurityStore, normal_rp: WebAuthnRelyingParty | None,
                 recovery_rp: WebAuthnRelyingParty | None = None) -> None:
        self._store = store
        self._normal_rp = normal_rp
        self._recovery_rp = recovery_rp
        self._profiles = {profile.rp_id: profile for profile in (normal_rp, recovery_rp) if profile is not None}
        for profile in self._profiles.values():
            profile.validate()

    @property
    def configured(self) -> bool:
        if not self._profiles:
            return False
        return any(profile.development_only for profile in self._profiles.values()) or (
            self._normal_rp is not None and not self._normal_rp.development_only
        )

    def _server(self, rp_id: str) -> tuple[Fido2Server, WebAuthnRelyingParty]:
        profile = self._profiles.get(rp_id)
        if profile is None:
            raise SecurityError("WebAuthn RP is not configured")
        return Fido2Server(PublicKeyCredentialRpEntity(id=profile.rp_id, name="AlgoFortis"), verify_origin=lambda origin: origin == profile.origin), profile

    def normal_rp_id(self) -> str:
        if self._normal_rp is not None:
            return self._normal_rp.rp_id
        development = [profile.rp_id for profile in self._profiles.values() if profile.development_only]
        if len(development) == 1:
            return development[0]
        if self._profiles:
            return next(iter(self._profiles.keys()))
        raise SecurityError("no configured normal WebAuthn profile")

    @staticmethod
    def _options(value: object) -> dict[str, object]:
        # fido2's Mapping conversion performs required base64url encoding.
        return dict(value)  # type: ignore[arg-type]

    def issue_registration(self, *, user: UserIdentity, rp_id: str, label: str,
                           is_backup_hardware: bool) -> dict[str, object]:
        server, profile = self._server(rp_id)
        existing = self._store.get_user(user.user_id)
        if existing is None and user.role is Role.OWNER:
            self._store.ensure_user(user_id=user.user_id, role=user.role.value, lifecycle=user.lifecycle.value, display_name=user.display_name)
        else:
            self._active_identity(existing)
        credentials = [AttestedCredentialData(bytes(row["credential_data"])) for row in self._store.credentials_for(user_id=user.user_id, rp_id=rp_id)]
        options, state = server.register_begin(
            PublicKeyCredentialUserEntity(id=user.user_id.bytes, name=f"usr_{user.user_id}", display_name=user.display_name),
            credentials=credentials,
        )
        challenge_id = str(uuid4())
        self._store.save_challenge(challenge_id=challenge_id, user_id=user.user_id, purpose="REGISTRATION", rp_id=rp_id, origin=profile.origin, ceremony_state=json.dumps(state), expires_at=utc_now() + self.CHALLENGE_TTL)
        return {"challenge_id": challenge_id, "publicKey": self._options(options.public_key), "rp_id": rp_id, "label": label, "is_backup_hardware": is_backup_hardware}

    def issue_bootstrap_registration(self, *, user: UserIdentity, bootstrap_token: str,
                                     rp_id: str) -> dict[str, object]:
        if rp_id != self.normal_rp_id():
            raise SecurityError("bootstrap only authorizes the configured normal WebAuthn RP")
        self._store.validate_owner_bootstrap(token=bootstrap_token, user_id=user.user_id)
        issued = self.issue_registration(user=user, rp_id=rp_id, label="First owner authenticator", is_backup_hardware=False)
        issued["bootstrap_token"] = bootstrap_token
        return issued

    def complete_registration(self, *, user: UserIdentity, challenge_id: str, label: str,
                              is_backup_hardware: bool, response: dict[str, object]) -> str:
        self._active_identity(self._store.get_user(user.user_id))
        row = self._store.consume_challenge(challenge_id=challenge_id, user_id=user.user_id, purpose="REGISTRATION")
        server, _ = self._server(row["rp_id"])
        auth_data = server.register_complete(json.loads(row["ceremony_state"]), response)
        credential = auth_data.credential_data
        if credential is None:
            raise SecurityError("WebAuthn registration did not provide credential data")
        self._store.add_credential(credential_id=credential.credential_id, user_id=user.user_id, rp_id=row["rp_id"], credential_data=bytes(credential), sign_count=auth_data.counter, label=label, is_backup_hardware=is_backup_hardware)
        return credential.credential_id.hex()

    def complete_bootstrap_registration(self, *, user: UserIdentity, bootstrap_token: str,
                                        challenge_id: str, label: str, response: dict[str, object]) -> str:
        self._store.validate_owner_bootstrap(token=bootstrap_token, user_id=user.user_id)
        self._store.consume_owner_bootstrap(token=bootstrap_token, user_id=user.user_id)
        return self.complete_registration(user=user, challenge_id=challenge_id, label=label, is_backup_hardware=False, response=response)

    @staticmethod
    def _active_identity(row) -> UserIdentity:
        from .identity import persisted_identity
        user = persisted_identity(row)
        if (user.lifecycle is not Lifecycle.ACTIVE or user.account_status is not AccountAccessStatus.ACTIVE
                or user.activation_status is not ActivationStatus.REDEEMED):
            raise SecurityError("Identity unavailable")
        return user

    def authentication_identity(self, identifier: str | None, owner: UserIdentity) -> UserIdentity:
        if not identifier:
            return self._active_identity(self._store.get_user(owner.user_id))
        rows = self._store._conn.execute(
            "SELECT * FROM users WHERE UPPER(sx_id) = UPPER(?) OR LOWER(bound_email) = LOWER(?)",
            (identifier.strip(), identifier.strip()),
        ).fetchall()
        if len(rows) != 1:
            raise SecurityError("Identity unavailable")
        return self._active_identity(rows[0])

    def assertion_identity(self, response: dict[str, object]) -> UserIdentity:
        try:
            assertion = AuthenticationResponse.from_dict(response)
        except (ValueError, TypeError, KeyError):
            raise SecurityError("Invalid assertion") from None
        user = self._active_identity(self._store.credential_subject(assertion.raw_id))
        handle = assertion.response.user_handle
        if handle is not None and handle != user.user_id.bytes:
            raise SecurityError("Credential subject mismatch")
        return user

    def redeem_user_activation(self, *, identifier: str, code: str) -> dict[str, object]:
        from .identity import persisted_identity
        user = persisted_identity(self._store.activation_subject(identifier, code))
        rp_id = self.normal_rp_id()
        server, profile = self._server(rp_id)
        options, state = server.register_begin(
            PublicKeyCredentialUserEntity(id=user.user_id.bytes, name=user.sx_id, display_name=user.display_name),
            credentials=[],
        )
        challenge_id = str(uuid4())
        self._store.redeem_activation(user_id=user.user_id, code=code, challenge_id=challenge_id,
                                     rp_id=rp_id, origin=profile.origin, ceremony_state=json.dumps(state),
                                     expires_at=utc_now() + self.CHALLENGE_TTL)
        return {"challenge_id": challenge_id, "publicKey": self._options(options.public_key), "enrollment": "PENDING"}

    def complete_user_enrollment(self, *, challenge_id: str, label: str, response: dict[str, object]) -> str:
        subject = self._store.challenge_subject(challenge_id, "USER_ENROLLMENT")
        user_id = UUID(subject["user_id"])
        row = self._store.consume_challenge(challenge_id=challenge_id, user_id=user_id, purpose="USER_ENROLLMENT")
        server, _ = self._server(row["rp_id"])
        auth_data = server.register_complete(json.loads(row["ceremony_state"]), response)
        credential = auth_data.credential_data
        if credential is None:
            raise SecurityError("Credential unavailable")
        self._store.complete_user_enrollment(user_id=user_id, challenge_id=challenge_id, credential_id=credential.credential_id,
                                            rp_id=row["rp_id"], credential_data=bytes(credential),
                                            sign_count=auth_data.counter, label=label)
        return credential.credential_id.hex()

    def issue_authentication(self, *, user: UserIdentity, rp_id: str) -> dict[str, object]:
        self._active_identity(self._store.get_user(user.user_id))
        server, profile = self._server(rp_id)
        credentials = [AttestedCredentialData(bytes(row["credential_data"])) for row in self._store.credentials_for(user_id=user.user_id, rp_id=rp_id)]
        if not credentials:
            raise SecurityError("no enabled WebAuthn credentials for this RP")
        options, state = server.authenticate_begin(credentials=credentials)
        challenge_id = str(uuid4())
        self._store.save_challenge(challenge_id=challenge_id, user_id=user.user_id, purpose="AUTHENTICATION", rp_id=rp_id, origin=profile.origin, ceremony_state=json.dumps(state), expires_at=utc_now() + self.CHALLENGE_TTL)
        return {"challenge_id": challenge_id, "publicKey": self._options(options.public_key), "rp_id": rp_id}

    def complete_authentication(self, *, user: UserIdentity, challenge_id: str,
                                response: dict[str, object]) -> tuple[str, str]:
        resolved = self.assertion_identity(response)
        if resolved.user_id != user.user_id:
            raise SecurityError("Credential subject mismatch")
        row = self._store.consume_challenge(challenge_id=challenge_id, user_id=user.user_id, purpose="AUTHENTICATION")
        server, _ = self._server(row["rp_id"])
        records = self._store.credentials_for(user_id=user.user_id, rp_id=row["rp_id"])
        credential = server.authenticate_complete(json.loads(row["ceremony_state"]), [AttestedCredentialData(bytes(record["credential_data"])) for record in records], response)
        assertion = AuthenticationResponse.from_dict(response)
        current_counter = assertion.response.authenticator_data.counter
        previous_counter = next(record["sign_count"] for record in records if bytes(record["credential_id"]) == credential.credential_id)
        self._store.update_sign_count(credential_id=credential.credential_id, previous=previous_counter, current=current_counter)
        return credential.credential_id.hex(), str(row["rp_id"])


@dataclass(frozen=True)
class Authenticator:
    credential_id: str
    label: str
    is_backup_hardware: bool
    enabled: bool = True


class AuthenticatorRegistry:
    """Enrollment invariant: OWNER has a primary plus backup hardware key."""
    def __init__(self) -> None:
        self._entries: dict[UUID, tuple[Authenticator, ...]] = {}

    def replace(self, user_id: UUID, authenticators: tuple[Authenticator, ...]) -> None:
        ids = [entry.credential_id for entry in authenticators if entry.enabled]
        if len(ids) < 2 or len(ids) != len(set(ids)):
            raise SecurityError("at least two distinct enabled WebAuthn authenticators are required")
        if not any(entry.enabled and entry.is_backup_hardware for entry in authenticators):
            raise SecurityError("an enabled backup hardware authenticator is required")
        self._entries[user_id] = authenticators

    def ready(self, user_id: UUID) -> bool:
        entries = self._entries.get(user_id, ())
        return len([entry for entry in entries if entry.enabled]) >= 2 and any(
            entry.enabled and entry.is_backup_hardware for entry in entries
        )

    def status(self, user_id: UUID) -> SecurityStatus:
        """Report enrollment truth without disclosing credential material."""
        entries = self._entries.get(user_id, ())
        if not entries:
            return SecurityStatus.NOT_CONFIGURED
        return SecurityStatus.CONFIGURED if self.ready(user_id) else SecurityStatus.NEEDS_ROTATION


class WebAuthnVerifier(Protocol):
    """Deployment adapter; implementations use python-fido2 server ceremonies."""
    configured: bool

    def verify(self, *, user_id: UUID, assertion: dict[str, object], challenge: str) -> str: ...


class MtlsAuthority(Protocol):
    """Deployment-provided source of verified client-certificate state.

    Implementations must derive assurance from a trusted server/TLS boundary,
    never from caller-controlled request headers alone.
    """

    def verified(self, request: object) -> bool: ...


class RejectingMtlsAuthority:
    """Fail closed when no authoritative mTLS integration is configured."""

    def verified(self, request: object) -> bool:
        return False


class RejectingWebAuthnVerifier:
    configured = False

    def verify(self, *, user_id: UUID, assertion: dict[str, object], challenge: str) -> str:
        raise SecurityError("WebAuthn verifier is not configured")


@dataclass(frozen=True)
class SecurityConfiguration:
    normal_mtls_required: bool = True
    normal_mtls_configured: bool = False
    break_glass_enabled: bool = False
    break_glass_origin: str | None = None
    normal_origin: str | None = None
    break_glass_independence_verified: bool = False

    def validate(self) -> None:
        if self.break_glass_enabled and not self.break_glass_origin:
            raise SecurityError("break-glass requires an independently configured origin")
        if self.break_glass_enabled and self.break_glass_origin == self.normal_origin:
            raise SecurityError("break-glass origin cannot share the normal access origin")

    def mtls_status(self) -> SecurityStatus:
        if not self.normal_mtls_required:
            return SecurityStatus.NOT_CONFIGURED
        return SecurityStatus.CONFIGURED if self.normal_mtls_configured else SecurityStatus.UNKNOWN

    def break_glass_status(self) -> SecurityStatus:
        if not self.break_glass_enabled:
            return SecurityStatus.NOT_CONFIGURED
        if not self.break_glass_origin:
            return SecurityStatus.UNKNOWN
        return (
            SecurityStatus.CONFIGURED
            if self.break_glass_independence_verified
            else SecurityStatus.UNKNOWN
        )


class SecurityStatusAuthority:
    """Single fail-closed projection of deployment and enrollment evidence."""

    def __init__(self, *, config: SecurityConfiguration, registry: AuthenticatorRegistry,
                 verifier: WebAuthnVerifier | object,
                 enrollment_status_reader: Callable[[UUID], SecurityStatus] | None = None,
                 owner_initialized_reader: Callable[[], bool] | None = None) -> None:
        self._config = config
        self._registry = registry
        self._verifier = verifier
        self._enrollment_status_reader = enrollment_status_reader
        self._owner_initialized_reader = owner_initialized_reader

    def public_status(self, user_id: UUID) -> dict[str, object]:
        enrollment = self._enrollment_status_reader(user_id) if self._enrollment_status_reader else self._registry.status(user_id)
        verifier_configured = bool(getattr(self._verifier, "configured", False))
        if not verifier_configured:
            webauthn = SecurityStatus.NOT_CONFIGURED
        elif enrollment is SecurityStatus.CONFIGURED:
            webauthn = SecurityStatus.CONFIGURED
        else:
            # A ceremony provider without the mandatory owner enrollment is
            # not production-ready, but distinguishes empty enrollment from a
            # degraded/disabled registered set.
            webauthn = enrollment
        owner_init = self._owner_initialized_reader() if self._owner_initialized_reader else False
        return {
            "password_authentication": "ENABLED" if owner_init else "PENDING_SETUP",
            "owner_initialized": owner_init,
            "webauthn": webauthn.value,
            "webauthn_enrollment": enrollment.value,
            "normal_mtls": self._config.mtls_status().value,
            "break_glass": self._config.break_glass_status().value,
            "owner_authenticators_ready": enrollment is SecurityStatus.CONFIGURED,
            "normal_mtls_required": self._config.normal_mtls_required,
        }


@dataclass(frozen=True)
class Session:
    token: str
    user: UserIdentity
    route: AccessRoute
    risk: SessionRisk
    expires_at: datetime
    step_up_satisfied: bool


class SessionService:
    """Opaque in-memory sessions; production may replace this storage adapter."""
    def __init__(self, config: SecurityConfiguration, ttl: timedelta = timedelta(minutes=15), store: SQLiteSecurityStore | None = None) -> None:
        config.validate()
        self._config = config
        self._ttl = ttl
        self._sessions: dict[str, Session] = {}
        self._store = store

    @staticmethod
    def determine_risk(*, route: AccessRoute, mtls_verified: bool, repeated_failures: int = 0) -> SessionRisk:
        if repeated_failures >= 3:
            return SessionRisk.DENY_OR_REVIEW
        if route is AccessRoute.BREAK_GLASS or not mtls_verified:
            return SessionRisk.STEP_UP_REQUIRED
        return SessionRisk.NORMAL

    def issue(
        self, *, user: UserIdentity, route: AccessRoute, mtls_verified: bool,
        repeated_failures: int = 0, step_up_satisfied: bool = False, credential_id: bytes | None = None,
    ) -> Session:
        if user.lifecycle is not Lifecycle.ACTIVE or user.account_status is AccountAccessStatus.SUSPENDED or user.account_status is AccountAccessStatus.REVOKED:
            raise SecurityError("inactive user cannot receive a session")
        if route is AccessRoute.NORMAL and self._config.normal_mtls_required and not mtls_verified:
            raise SecurityError("normal access requires verified mTLS")
        if route is AccessRoute.BREAK_GLASS and not self._config.break_glass_enabled:
            raise SecurityError("break-glass access is disabled")
        risk = self.determine_risk(route=route, mtls_verified=mtls_verified, repeated_failures=repeated_failures)
        if risk is SessionRisk.DENY_OR_REVIEW:
            raise SecurityError("session denied pending security review")
        token = secrets.token_urlsafe(48)
        session = Session(token, user, route, risk, utc_now() + self._ttl, step_up_satisfied)
        if self._store is not None:
            if self._store.get_user(user.user_id) is None:
                self._store.ensure_user(
                    user_id=user.user_id,
                    role=user.role.value,
                    lifecycle=user.lifecycle.value,
                    display_name=user.display_name,
                    sx_id=user.sx_id,
                    account_status=user.account_status.value,
                    activation_status=user.activation_status.value,
                    service_status=user.service_status.value,
                    service_started_at=user.service_started_at,
                    service_expires_at=user.service_expires_at,
                    service_term_type=user.service_term_type,
                    custom_term_value=user.custom_term_value,
                )
            user = WebAuthnCeremonyService._active_identity(self._store.get_user(user.user_id))
            session = Session(token, user, route, risk, session.expires_at, step_up_satisfied)
            self._store.save_session(token=token, user_id=user.user_id, route=route.value, risk=risk.value, expires_at=session.expires_at, step_up_satisfied=step_up_satisfied, credential_id=credential_id)
        else:
            self._sessions[token] = session
        return session

    def require(self, token: str | None, *, mutable: bool = False) -> Session:
        if not token:
            raise SecurityError("missing session")
        session = self._sessions.get(token)
        if self._store is not None:
            row = self._store.load_session(token)
            if row is None or row["revoked_at_utc"] is not None:
                raise SecurityError("invalid or expired session")
            
            from .identity import persisted_identity
            try:
                user = persisted_identity(row)
            except (ValueError, TypeError, KeyError):
                raise SecurityError("Invalid persisted identity") from None
            session = Session(token, user, AccessRoute(row["route"]), SessionRisk(row["risk"]), datetime.fromisoformat(row["expires_at_utc"]), bool(row["step_up_satisfied"]))
        if session is None or session.expires_at <= utc_now():
            self._sessions.pop(token or "", None)
            raise SecurityError("invalid or expired session")
        if (session.user.lifecycle is not Lifecycle.ACTIVE or session.user.account_status is not AccountAccessStatus.ACTIVE
                or session.user.activation_status is not ActivationStatus.REDEEMED):
            self._sessions.pop(token, None)
            raise SecurityError("user is no longer active")
        if mutable and session.risk is not SessionRisk.NORMAL and not session.step_up_satisfied:
            raise SecurityError("step-up WebAuthn verification is required")
        return session

    def revoke_user(self, user_id: UUID) -> None:
        self._sessions = {token: value for token, value in self._sessions.items() if value.user.user_id != user_id}
        if self._store is not None:
            self._store.revoke_user_sessions(user_id)


def signed_challenge(secret: bytes, user_id: UUID, challenge: str) -> str:
    """Bind a short-lived challenge to a user without storing a plaintext secret."""
    return hmac.new(secret, f"{user_id}:{challenge}".encode(), hashlib.sha256).hexdigest()
