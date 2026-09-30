from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from dashboard.backend.account_v2.contracts import DeviceSessionGateResult, DeviceSessionGateStatus
from engine.broker_adapters.angelone_v2.protection_capability import (
    ProtectionCapabilityDecision,
    ProtectionCapabilityStatus,
)
from engine.live.state_machine_v2 import LiveState

try:
    from engine.live.live_eligibility_v2 import (
        LiveEligibilityResult,
        LiveEligibilityStatus,
        LiveEligibilityV2,
    )
except ModuleNotFoundError as exc:
    pytest.fail(f"Live eligibility composition is not implemented: {exc}", pytrace=False)


def _s2(status: DeviceSessionGateStatus = DeviceSessionGateStatus.VALID) -> DeviceSessionGateResult:
    return DeviceSessionGateResult(
        schema_version="s2-device-session-gate/v1",
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        device_id="device-a",
        session_family_id="session-a",
        status=status,
        reasons=(),
        authority_evidence_ref="s2-evidence-1",
        evaluated_at=datetime(2026, 9, 30, 9, 15, tzinfo=timezone.utc),
        audit_ref="audit-s2-1",
    )


def _protection(
    status: ProtectionCapabilityStatus = ProtectionCapabilityStatus.VERIFIED_SUPPORTED,
    *,
    disarmed_required: bool = True,
) -> ProtectionCapabilityDecision:
    return ProtectionCapabilityDecision(
        status=status,
        requirement_ref="protection-policy/v1",
        evidence_ref="protection-evidence@1",
        missing_capabilities=(),
        disarmed_required=disarmed_required,
        existing_protection_observed=False,
        existing_protection_adopted=False,
    )


def _evaluate(**overrides) -> LiveEligibilityResult:
    values = {
        "live_state": LiveState.READY,
        "s2_gate_result": _s2(),
        "exclusivity_ok": True,
        "reconciliation_clean": True,
        "protection_decision": _protection(),
        "broker_policy_ref": "angelone-policy/v1",
        "audit_ready": True,
    }
    values.update(overrides)
    return LiveEligibilityV2.evaluate(**values)


def test_complete_prerequisites_are_only_eligible_for_qualification() -> None:
    result = _evaluate()

    assert result.status is LiveEligibilityStatus.ELIGIBLE_FOR_QUALIFICATION
    assert result.reasons == ()
    assert "s2-evidence-1" in result.evidence_refs
    assert "protection-evidence@1" in result.evidence_refs
    assert "angelone-policy/v1" in result.evidence_refs
    assert not hasattr(LiveEligibilityStatus, "ACTIVE")
    assert not hasattr(LiveEligibilityStatus, "ARMED")


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"live_state": LiveState.DISABLED}, "live_state_not_ready"),
        ({"s2_gate_result": _s2(DeviceSessionGateStatus.REVOKED)}, "s2_gate_invalid"),
        ({"exclusivity_ok": False}, "live_account_exclusivity_unproven"),
        ({"reconciliation_clean": False}, "reconciliation_not_clean"),
        (
            {"protection_decision": _protection(ProtectionCapabilityStatus.UNVERIFIED)},
            "broker_resident_protection_unverified",
        ),
        (
            {"protection_decision": _protection(disarmed_required=False)},
            "protection_disarmed_requirement_missing",
        ),
        ({"broker_policy_ref": None}, "broker_policy_ref_missing"),
        ({"broker_policy_ref": "   "}, "broker_policy_ref_missing"),
        ({"audit_ready": False}, "audit_not_ready"),
    ],
)
def test_each_missing_prerequisite_fails_closed(override, reason: str) -> None:
    result = _evaluate(**override)

    assert result.status is LiveEligibilityStatus.BLOCKED
    assert reason in result.reasons


def test_wrong_contract_types_fail_closed_by_exception() -> None:
    with pytest.raises(TypeError):
        LiveEligibilityV2.evaluate(
            live_state="READY",
            s2_gate_result=_s2(),
            exclusivity_ok=True,
            reconciliation_clean=True,
            protection_decision=_protection(),
            broker_policy_ref="angelone-policy/v1",
            audit_ready=True,
        )

    with pytest.raises(TypeError):
        LiveEligibilityV2.evaluate(
            live_state=LiveState.READY,
            s2_gate_result=object(),
            exclusivity_ok=True,
            reconciliation_clean=True,
            protection_decision=_protection(),
            broker_policy_ref="angelone-policy/v1",
            audit_ready=True,
        )


def test_blocked_result_collects_relevant_evidence_without_authorizing() -> None:
    result = _evaluate(
        reconciliation_clean=False,
        protection_decision=_protection(ProtectionCapabilityStatus.UNSUPPORTED),
    )

    assert result.status is LiveEligibilityStatus.BLOCKED
    assert result.evidence_refs == (
        "s2-evidence-1",
        "protection-evidence@1",
        "protection-policy/v1",
        "angelone-policy/v1",
    )
