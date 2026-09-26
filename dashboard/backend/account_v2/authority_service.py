"""Self-scoped S2 account-authority facade.

Public mutation methods accept an authenticated principal rather than a free
target user id.  Required audit intent is persisted before each direct
security mutation.  The facade has no trading/broker/arming authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from .audit import RequiredAuditSink


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    user_id: UUID
    session_family_id: str | None


class S2AccountAuthorityService:
    def __init__(
        self,
        repository,
        device_service,
        recovery_service,
        audit_sink: RequiredAuditSink,
        rate_limiter=None,
    ) -> None:
        self._repository = repository
        self._device_service = device_service
        self._recovery_service = recovery_service
        self._audit_sink = audit_sink
        self._rate_limiter = rate_limiter

    def _required_intent(
        self,
        *,
        principal: AuthenticatedPrincipal,
        action: str,
        resource_ref: str | None,
        occurred_at: datetime,
    ) -> str:
        reference = self._audit_sink.record_required_intent(
            user_id=principal.user_id,
            action=action,
            resource_ref=resource_ref,
            occurred_at=occurred_at,
        )
        if not reference:
            raise RuntimeError("required security audit reference unavailable")
        return str(reference)

    def list_devices(self, *, principal: AuthenticatedPrincipal):
        return self._repository.list_devices(user_id=principal.user_id)

    def get_device(self, *, principal: AuthenticatedPrincipal, device_id: str):
        return self._repository.get_device(user_id=principal.user_id, device_id=device_id)

    def enroll_device(
        self,
        *,
        principal: AuthenticatedPrincipal,
        device_id: str,
        public_key: bytes,
        fingerprint: str,
        challenge: bytes,
        signature: bytes,
        created_at: datetime,
    ):
        self._required_intent(
            principal=principal,
            action="DEVICE_ENROLL",
            resource_ref=device_id,
            occurred_at=created_at,
        )
        return self._device_service.enroll(
            user_id=principal.user_id,
            device_id=device_id,
            public_key=public_key,
            fingerprint=fingerprint,
            challenge=challenge,
            signature=signature,
            created_at=created_at,
        )

    def revoke_device(
        self,
        *,
        principal: AuthenticatedPrincipal,
        device_id: str,
        revoked_at: datetime,
    ) -> None:
        self._required_intent(
            principal=principal,
            action="DEVICE_REVOKE",
            resource_ref=device_id,
            occurred_at=revoked_at,
        )
        self._device_service.revoke(
            user_id=principal.user_id,
            device_id=device_id,
            revoked_at=revoked_at,
        )

    def revoke_session_family(
        self,
        *,
        principal: AuthenticatedPrincipal,
        family_id: str,
        revoked_at: datetime,
    ) -> None:
        self._required_intent(
            principal=principal,
            action="SESSION_FAMILY_REVOKE",
            resource_ref=family_id,
            occurred_at=revoked_at,
        )
        self._repository.revoke_session_family(
            user_id=principal.user_id,
            family_id=family_id,
            revoked_at=revoked_at,
        )

    def recover(
        self,
        *,
        principal: AuthenticatedPrincipal,
        proof: object,
        now: datetime,
    ):
        if self._rate_limiter is None:
            raise PermissionError("recovery rate-limit service unavailable")
        # HighAssuranceRecoveryService owns its own required recovery audit
        # boundary.  The target is derived from the authenticated principal.
        return self._recovery_service.recover(
            principal_user_id=principal.user_id,
            target_user_id=principal.user_id,
            proof=proof,
            now=now,
        )
