from datetime import datetime, timezone
from uuid import UUID

import pytest

from dashboard.backend.account_v2.contracts import DeviceSessionGateResult, DeviceSessionGateStatus
from dashboard.backend.product_ops_v2.rights import RightsRequestType, RightsState, RightsWorkflow

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)
UID = UUID("00000000-0000-0000-0000-000000000001")
OTHER = UUID("00000000-0000-0000-0000-000000000002")


class Gate:
    def __init__(self, status=DeviceSessionGateStatus.VALID, *, evidence="s2-evidence", audit_ref="s2-audit"):
        self.status = status
        self.evidence = evidence
        self.audit_ref = audit_ref

    def evaluate(self, user_id, device_id, session_family_id, now):
        return DeviceSessionGateResult(
            "s2-device-session-gate/v1",
            user_id,
            device_id,
            session_family_id,
            self.status,
            ("TEST",),
            self.evidence,
            now,
            self.audit_ref,
        )


class Audit:
    def __init__(self):
        self.events = []

    def record_required_intent(self, **kwargs):
        self.events.append(kwargs)
        return f"audit-{len(self.events)}"


class FailingAudit:
    def record_required_intent(self, **_kwargs):
        raise RuntimeError("audit unavailable")


def test_rights_request_preserves_received_then_identity_check_state():
    audit = Audit()
    workflow = RightsWorkflow(Gate(), audit)
    received = workflow.receive(
        request_id="r1",
        principal_user_id=UID,
        requested_user_id=UID,
        request_type=RightsRequestType.ACCESS,
        now=NOW,
    )
    assert received.state is RightsState.RECEIVED
    assert received.audit_ref == "audit-1"
    checking = workflow.begin_identity_check(received, now=NOW)
    assert checking.state is RightsState.IDENTITY_CHECK
    accepted = workflow.identity_check(checking, device_id="d1", session_family_id="s1", now=NOW)
    assert accepted.state is RightsState.ACCEPTED
    assert accepted.identity_authority == "S2_DEVICE_SESSION_GATE"


def test_cross_user_and_transition_skips_are_rejected():
    workflow = RightsWorkflow(Gate(), Audit())
    with pytest.raises(ValueError, match="CROSS_USER_REQUEST_DENIED"):
        workflow.receive(
            request_id="r2",
            principal_user_id=UID,
            requested_user_id=OTHER,
            request_type=RightsRequestType.ACCESS,
            now=NOW,
        )

    received = workflow.receive(
        request_id="r3",
        principal_user_id=UID,
        requested_user_id=UID,
        request_type=RightsRequestType.ERASURE,
        now=NOW,
    )
    with pytest.raises(ValueError, match="INVALID_RIGHTS_TRANSITION"):
        workflow.identity_check(received, device_id="d1", session_family_id="s1", now=NOW)
    with pytest.raises(ValueError, match="INVALID_RIGHTS_TRANSITION"):
        workflow.start(received, now=NOW)


def test_invalid_s2_and_missing_strong_evidence_fail_closed():
    workflow = RightsWorkflow(Gate(DeviceSessionGateStatus.REVOKED), Audit())
    received = workflow.receive(
        request_id="r4",
        principal_user_id=UID,
        requested_user_id=UID,
        request_type=RightsRequestType.ERASURE,
        now=NOW,
    )
    rejected = workflow.identity_check(
        workflow.begin_identity_check(received, now=NOW),
        device_id="d1",
        session_family_id="s1",
        now=NOW,
        require_strong_verification=True,
    )
    assert rejected.state is RightsState.REJECTED

    missing_evidence = RightsWorkflow(Gate(evidence=None, audit_ref=None), Audit())
    received2 = missing_evidence.receive(
        request_id="r5",
        principal_user_id=UID,
        requested_user_id=UID,
        request_type=RightsRequestType.ERASURE,
        now=NOW,
    )
    rejected2 = missing_evidence.identity_check(
        missing_evidence.begin_identity_check(received2, now=NOW),
        device_id="d1",
        session_family_id="s1",
        now=NOW,
        require_strong_verification=True,
    )
    assert rejected2.state is RightsState.REJECTED
    assert rejected2.reason == "S2_STRONG_EVIDENCE_REQUIRED"


def test_required_audit_failure_blocks_rights_state_creation_and_progression():
    workflow = RightsWorkflow(Gate(), FailingAudit())
    with pytest.raises(RuntimeError, match="audit unavailable"):
        workflow.receive(
            request_id="r6",
            principal_user_id=UID,
            requested_user_id=UID,
            request_type=RightsRequestType.GRIEVANCE,
            now=NOW,
        )

    audit = Audit()
    workflow2 = RightsWorkflow(Gate(), audit)
    received = workflow2.receive(
        request_id="r7",
        principal_user_id=UID,
        requested_user_id=UID,
        request_type=RightsRequestType.GRIEVANCE,
        now=NOW,
    )
    accepted = workflow2.identity_check(
        workflow2.begin_identity_check(received, now=NOW),
        device_id="d1",
        session_family_id="s1",
        now=NOW,
    )
    workflow2._audit_sink = FailingAudit()
    with pytest.raises(RuntimeError, match="audit unavailable"):
        workflow2.start(accepted, now=NOW)
    assert accepted.state is RightsState.ACCEPTED
