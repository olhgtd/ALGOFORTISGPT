from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from uuid import UUID

from dashboard.backend.account_v2.audit import RequiredAuditSink
from .identity import S2IdentityAuthorizer


class RightsRequestType(str, Enum):
    ACCESS = "ACCESS"
    CORRECTION_UPDATE = "CORRECTION_UPDATE"
    ERASURE = "ERASURE"
    GRIEVANCE = "GRIEVANCE"
    NOMINATION = "NOMINATION"


class RightsState(str, Enum):
    RECEIVED = "RECEIVED"
    IDENTITY_CHECK = "IDENTITY_CHECK"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


@dataclass(frozen=True, slots=True)
class RightsRequest:
    request_id: str
    principal_user_id: UUID
    request_type: RightsRequestType
    state: RightsState
    created_at: datetime
    identity_authority: str | None = None
    reason: str | None = None
    audit_ref: str | None = None


class RightsWorkflow:
    """Privacy-rights state machine scoped by the existing S2 authority.

    This class never implements credentials or identity proof. It consumes the
    Phase-9 S2IdentityAuthorizer wrapper and a required audit sink; failure of
    either authority blocks state progression.
    """

    def __init__(self, s2_gate_or_authorizer, audit_sink: RequiredAuditSink):
        self._identity = (
            s2_gate_or_authorizer
            if hasattr(s2_gate_or_authorizer, "authorize")
            else S2IdentityAuthorizer(s2_gate_or_authorizer)
        )
        self._audit_sink = audit_sink

    def _audit(self, *, user_id: UUID, request_id: str, action: str, now: datetime) -> str:
        audit_ref = self._audit_sink.record_required_intent(
            user_id=user_id,
            action=action,
            resource_ref=request_id,
            occurred_at=now,
        )
        if not audit_ref:
            raise RuntimeError("AUDIT_EVIDENCE_REQUIRED")
        return str(audit_ref)

    def receive(
        self,
        *,
        request_id: str,
        principal_user_id: UUID,
        requested_user_id: UUID,
        request_type: RightsRequestType,
        now: datetime,
    ) -> RightsRequest:
        if requested_user_id != principal_user_id:
            raise ValueError("CROSS_USER_REQUEST_DENIED")
        if not request_id.strip():
            raise ValueError("RIGHTS_REQUEST_ID_REQUIRED")
        audit_ref = self._audit(
            user_id=principal_user_id,
            request_id=request_id,
            action=f"PRIVACY_RIGHTS_RECEIVE:{request_type.value}",
            now=now,
        )
        return RightsRequest(
            request_id=request_id,
            principal_user_id=principal_user_id,
            request_type=request_type,
            state=RightsState.RECEIVED,
            created_at=now,
            audit_ref=audit_ref,
        )

    def begin_identity_check(self, request: RightsRequest, *, now: datetime) -> RightsRequest:
        if request.state is not RightsState.RECEIVED:
            raise ValueError("INVALID_RIGHTS_TRANSITION")
        audit_ref = self._audit(
            user_id=request.principal_user_id,
            request_id=request.request_id,
            action="PRIVACY_RIGHTS_IDENTITY_CHECK_BEGIN",
            now=now,
        )
        return replace(request, state=RightsState.IDENTITY_CHECK, audit_ref=audit_ref)

    def identity_check(
        self,
        request: RightsRequest,
        *,
        device_id: str,
        session_family_id: str | None,
        now: datetime,
        require_strong_verification: bool = False,
    ) -> RightsRequest:
        if request.state is not RightsState.IDENTITY_CHECK:
            raise ValueError("INVALID_RIGHTS_TRANSITION")
        audit_ref = self._audit(
            user_id=request.principal_user_id,
            request_id=request.request_id,
            action="PRIVACY_RIGHTS_IDENTITY_CHECK_EVALUATE",
            now=now,
        )
        allowed, result = self._identity.authorize(
            request.principal_user_id,
            device_id,
            session_family_id,
            now,
        )
        if not allowed:
            return replace(
                request,
                state=RightsState.REJECTED,
                identity_authority="S2_DEVICE_SESSION_GATE",
                reason=result.status.value,
                audit_ref=audit_ref,
            )
        if require_strong_verification and not (result.authority_evidence_ref and result.audit_ref):
            return replace(
                request,
                state=RightsState.REJECTED,
                identity_authority="S2_DEVICE_SESSION_GATE",
                reason="S2_STRONG_EVIDENCE_REQUIRED",
                audit_ref=audit_ref,
            )
        return replace(
            request,
            state=RightsState.ACCEPTED,
            identity_authority="S2_DEVICE_SESSION_GATE",
            reason=result.reasons[0] if result.reasons else None,
            audit_ref=audit_ref,
        )

    def start(self, request: RightsRequest, *, now: datetime) -> RightsRequest:
        if request.state is not RightsState.ACCEPTED:
            raise ValueError("INVALID_RIGHTS_TRANSITION")
        audit_ref = self._audit(
            user_id=request.principal_user_id,
            request_id=request.request_id,
            action="PRIVACY_RIGHTS_START",
            now=now,
        )
        return replace(request, state=RightsState.IN_PROGRESS, audit_ref=audit_ref)

    def complete(self, request: RightsRequest, *, now: datetime) -> RightsRequest:
        if request.state is not RightsState.IN_PROGRESS:
            raise ValueError("INVALID_RIGHTS_TRANSITION")
        audit_ref = self._audit(
            user_id=request.principal_user_id,
            request_id=request.request_id,
            action="PRIVACY_RIGHTS_COMPLETE",
            now=now,
        )
        return replace(request, state=RightsState.COMPLETED, audit_ref=audit_ref)
