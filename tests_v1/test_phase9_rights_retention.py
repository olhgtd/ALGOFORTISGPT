from datetime import datetime, timezone
from uuid import UUID
import pytest

from dashboard.backend.account_v2.contracts import DeviceSessionGateResult, DeviceSessionGateStatus
from dashboard.backend.product_ops_v2.rights import RightsRequestType, RightsWorkflow, RightsState
from dashboard.backend.product_ops_v2.retention import RetentionPolicy, ErasureEngine, ErasureOutcome

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)
UID = UUID("00000000-0000-0000-0000-000000000001")


class Gate:
    def __init__(self, status=DeviceSessionGateStatus.VALID):
        self.status = status

    def evaluate(self, user_id, device_id, session_family_id, now):
        return DeviceSessionGateResult(
            "s2-device-session-gate/v1",
            user_id,
            device_id,
            session_family_id,
            self.status,
            ("TEST",),
            "s2-evidence",
            now,
            "audit-s2",
        )


class Audit:
    def record_required_intent(self, **_kwargs):
        return "phase9-audit"


def test_rights_workflow_reuses_s2_and_blocks_cross_user():
    workflow = RightsWorkflow(Gate(), Audit())
    received = workflow.receive(
        request_id="r1",
        principal_user_id=UID,
        requested_user_id=UID,
        request_type=RightsRequestType.ACCESS,
        now=NOW,
    )
    assert received.state is RightsState.RECEIVED
    checking = workflow.begin_identity_check(received, now=NOW)
    checked = workflow.identity_check(checking, device_id="d1", session_family_id="s1", now=NOW)
    assert checked.state is RightsState.ACCEPTED
    assert checked.identity_authority == "S2_DEVICE_SESSION_GATE"

    with pytest.raises(ValueError):
        workflow.receive(
            request_id="r2",
            principal_user_id=UID,
            requested_user_id=UUID("00000000-0000-0000-0000-000000000002"),
            request_type=RightsRequestType.ACCESS,
            now=NOW,
        )


def test_rights_fail_closed_when_s2_not_valid():
    workflow = RightsWorkflow(Gate(DeviceSessionGateStatus.AUTHORITY_UNAVAILABLE), Audit())
    received = workflow.receive(
        request_id="r3",
        principal_user_id=UID,
        requested_user_id=UID,
        request_type=RightsRequestType.ERASURE,
        now=NOW,
    )
    checking = workflow.begin_identity_check(received, now=NOW)
    assert workflow.identity_check(checking, device_id="d1", session_family_id="s1", now=NOW).state is RightsState.REJECTED


def test_erasure_legal_hold_is_scoped_and_reasoned():
    engine = ErasureEngine()
    held = RetentionPolicy(
        "ret-held",
        "1.0.0",
        "ACCOUNT_IDENTITY",
        "ACCOUNT_CLOSED",
        "retention/account/v1",
        "DELETE",
        legal_hold_ref="hold-1",
        safety_retention_ref=None,
        backup_propagation=True,
    )
    free = RetentionPolicy(
        "ret-free",
        "1.0.0",
        "CONSENT_EVIDENCE",
        "CONSENT_WITHDRAWN",
        "retention/consent/v1",
        "DELETE",
        legal_hold_ref=None,
        safety_retention_ref=None,
        backup_propagation=True,
    )
    decisions = engine.decide((held, free), now=NOW)
    assert decisions["ACCOUNT_IDENTITY"].outcome is ErasureOutcome.RETAIN_LEGAL_HOLD
    assert decisions["CONSENT_EVIDENCE"].outcome is ErasureOutcome.DELETE_ALLOWED
    assert decisions["ACCOUNT_IDENTITY"].reason_ref == "hold-1"
