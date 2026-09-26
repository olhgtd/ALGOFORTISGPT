"""S2 wrapper around the existing durable WebAuthn ceremony authority."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from dashboard.backend.security import WebAuthnCeremonyService, WebAuthnRelyingParty

from .contracts import ProductionIdentityPolicy
from .rate_limit import RateLimitFlow


class ProductionCredentialReenrollmentRequired(PermissionError):
    """A non-production credential cannot be promoted into production trust."""


def validate_relying_party_profile(*, rp_id: str, origin: str, development_only: bool) -> WebAuthnRelyingParty:
    profile = WebAuthnRelyingParty(rp_id=rp_id, origin=origin, development_only=development_only)
    profile.validate()
    return profile


class WebAuthnAuthority:
    def __init__(
        self,
        ceremonies: WebAuthnCeremonyService,
        *,
        rate_limiter=None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._ceremonies = ceremonies
        self._rate_limiter = rate_limiter
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def require_credential_compatible(*, source: ProductionIdentityPolicy, target: ProductionIdentityPolicy) -> None:
        if target.environment.lower() != "production":
            return
        same_identity = (
            source.environment.lower() == "production"
            and source.rp_id == target.rp_id
            and source.origin == target.origin
            and not target.production_migration_required
        )
        if not same_identity:
            raise ProductionCredentialReenrollmentRequired(
                "fresh production WebAuthn enrollment and device re-proof are required"
            )

    @staticmethod
    def _subject_user_id(kwargs: dict[str, Any]):
        user = kwargs.get("user")
        user_id = getattr(user, "user_id", None)
        if user_id is None:
            raise PermissionError("WebAuthn subject unavailable")
        return user_id

    def _require_login_available(self, *, user_id, now: datetime) -> str:
        limiter = self._rate_limiter
        if limiter is None:
            raise PermissionError("WebAuthn login rate-limit service unavailable")
        subject_key = str(user_id)
        decision = limiter.is_locked(
            user_id=user_id,
            flow=RateLimitFlow.LOGIN,
            subject_key=subject_key,
            now=now,
        )
        if decision.locked:
            raise PermissionError("WebAuthn login rate-limit active")
        return subject_key

    def issue_authentication(self, **kwargs: Any) -> dict[str, object]:
        user_id = self._subject_user_id(kwargs)
        now = self._clock()
        subject_key = self._require_login_available(user_id=user_id, now=now)
        try:
            return self._ceremonies.issue_authentication(**kwargs)
        except PermissionError:
            self._rate_limiter.record_failure(
                user_id=user_id,
                flow=RateLimitFlow.LOGIN,
                subject_key=subject_key,
                now=now,
            )
            raise

    def complete_authentication(self, **kwargs: Any) -> tuple[str, str]:
        user_id = self._subject_user_id(kwargs)
        now = self._clock()
        subject_key = self._require_login_available(user_id=user_id, now=now)
        try:
            result = self._ceremonies.complete_authentication(**kwargs)
        except PermissionError:
            self._rate_limiter.record_failure(
                user_id=user_id,
                flow=RateLimitFlow.LOGIN,
                subject_key=subject_key,
                now=now,
            )
            raise
        self._rate_limiter.record_success(
            user_id=user_id,
            flow=RateLimitFlow.LOGIN,
            subject_key=subject_key,
        )
        return result
