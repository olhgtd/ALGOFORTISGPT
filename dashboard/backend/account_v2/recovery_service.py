"""High-assurance S2 account recovery.

Recovery is self-scoped, requires an external high-assurance proof, writes a
required audit intent before mutation, and atomically revokes the target
user's S2 devices and session families.  It never grants trading authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from .repository import AccountAuthorityRepository


class RecoveryDenied(PermissionError):
    pass


class RecoveryProofVerifier(Protocol):
    def verify(self, *, user_id: UUID, proof: object) -> bool: ...


class RequiredAuditSink(Protocol):
    def record_required_intent(self, **kwargs) -> str: ...


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    user_id: UUID
    audit_ref: str
    reenrollment_required: bool = True


class HighAssuranceRecoveryService:
    def __init__(
        self,
        repository: AccountAuthorityRepository,
        proof_verifier: RecoveryProofVerifier,
        audit_sink: RequiredAuditSink,
    ) -> None:
        self._repository = repository
        self._proof_verifier = proof_verifier
        self._audit_sink = audit_sink

    def recover(
        self,
        *,
        principal_user_id: UUID,
        target_user_id: UUID,
        proof: object,
        now: datetime,
    ) -> RecoveryResult:
        if principal_user_id != target_user_id:
            raise RecoveryDenied("cross-user recovery is not permitted")
        if not self._proof_verifier.verify(user_id=principal_user_id, proof=proof):
            raise RecoveryDenied("high-assurance recovery proof rejected")

        # Audit is required evidence.  If this write fails, mutation never starts.
        audit_ref = self._audit_sink.record_required_intent(
            user_id=principal_user_id,
            action="HIGH_ASSURANCE_RECOVERY",
            occurred_at=now,
            consequences=("REVOKE_ALL_S2_SESSIONS", "REVOKE_ALL_S2_DEVICES"),
        )
        if not audit_ref:
            raise RuntimeError("required recovery audit reference unavailable")

        self._repository.revoke_all_access_for_recovery(
            user_id=principal_user_id,
            revoked_at=now,
        )
        return RecoveryResult(
            user_id=principal_user_id,
            audit_ref=str(audit_ref),
            reenrollment_required=True,
        )
