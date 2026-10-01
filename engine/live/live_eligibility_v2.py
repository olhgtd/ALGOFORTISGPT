"""Pure fail-closed composition of Package-1 Live qualification prerequisites.

Eligibility produced here is evidence that qualification may proceed while the
runtime remains disarmed. It is never an arm token and never transitions the
Live state machine.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from dashboard.backend.account_v2.contracts import (
    DeviceSessionGateResult,
    DeviceSessionGateStatus,
)
from engine.broker_adapters.angelone_v2.protection_capability import (
    ProtectionCapabilityDecision,
    ProtectionCapabilityStatus,
)
from engine.live.state_machine_v2 import LiveState


class LiveEligibilityStatus(str, Enum):
    ELIGIBLE_FOR_QUALIFICATION = "ELIGIBLE_FOR_QUALIFICATION"
    BLOCKED = "BLOCKED"


def _refs(values: tuple[str | None, ...]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if isinstance(value, str) and value.strip():
            normalized = value.strip()
            if normalized not in result:
                result.append(normalized)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class LiveEligibilityResult:
    status: LiveEligibilityStatus
    reasons: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.status, LiveEligibilityStatus):
            raise TypeError("status must be LiveEligibilityStatus")
        if not isinstance(self.reasons, tuple) or not all(
            isinstance(item, str) and item.strip() for item in self.reasons
        ):
            raise TypeError("reasons must be a tuple of non-empty strings")
        if not isinstance(self.evidence_refs, tuple) or not all(
            isinstance(item, str) and item.strip() for item in self.evidence_refs
        ):
            raise TypeError("evidence_refs must be a tuple of non-empty strings")
        if self.status is LiveEligibilityStatus.ELIGIBLE_FOR_QUALIFICATION and self.reasons:
            raise ValueError("eligible result cannot contain blocking reasons")
        if self.status is LiveEligibilityStatus.BLOCKED and not self.reasons:
            raise ValueError("blocked result requires at least one reason")


class LiveEligibilityV2:
    @staticmethod
    def evaluate(
        *,
        live_state: LiveState,
        s2_gate_result: DeviceSessionGateResult,
        exclusivity_ok: bool,
        reconciliation_clean: bool,
        protection_decision: ProtectionCapabilityDecision,
        broker_policy_ref: str | None,
        audit_ready: bool,
    ) -> LiveEligibilityResult:
        if not isinstance(live_state, LiveState):
            raise TypeError("live_state must be LiveState")
        if not isinstance(s2_gate_result, DeviceSessionGateResult):
            raise TypeError("s2_gate_result must be DeviceSessionGateResult")
        if not isinstance(exclusivity_ok, bool):
            raise TypeError("exclusivity_ok must be bool")
        if not isinstance(reconciliation_clean, bool):
            raise TypeError("reconciliation_clean must be bool")
        if not isinstance(protection_decision, ProtectionCapabilityDecision):
            raise TypeError("protection_decision must be ProtectionCapabilityDecision")
        if broker_policy_ref is not None and not isinstance(broker_policy_ref, str):
            raise TypeError("broker_policy_ref must be str or None")
        if not isinstance(audit_ready, bool):
            raise TypeError("audit_ready must be bool")

        reasons: list[str] = []
        if live_state is not LiveState.READY:
            reasons.append("live_state_not_ready")
        if s2_gate_result.status is not DeviceSessionGateStatus.VALID:
            reasons.append("s2_gate_invalid")
        if not s2_gate_result.authority_evidence_ref:
            reasons.append("s2_authority_evidence_missing")
        if exclusivity_ok is not True:
            reasons.append("live_account_exclusivity_unproven")
        if reconciliation_clean is not True:
            reasons.append("reconciliation_not_clean")
        if protection_decision.status is not ProtectionCapabilityStatus.VERIFIED_SUPPORTED:
            reasons.append("broker_resident_protection_unverified")
        if protection_decision.disarmed_required is not True:
            reasons.append("protection_disarmed_requirement_missing")
        normalized_policy = broker_policy_ref.strip() if isinstance(broker_policy_ref, str) else ""
        if not normalized_policy:
            reasons.append("broker_policy_ref_missing")
        if audit_ready is not True:
            reasons.append("audit_not_ready")

        evidence_refs = _refs(
            (
                s2_gate_result.authority_evidence_ref,
                protection_decision.evidence_ref,
                protection_decision.requirement_ref,
                normalized_policy or None,
            )
        )
        if reasons:
            return LiveEligibilityResult(
                status=LiveEligibilityStatus.BLOCKED,
                reasons=tuple(reasons),
                evidence_refs=evidence_refs,
            )
        return LiveEligibilityResult(
            status=LiveEligibilityStatus.ELIGIBLE_FOR_QUALIFICATION,
            reasons=(),
            evidence_refs=evidence_refs,
        )


__all__ = [
    "LiveEligibilityResult",
    "LiveEligibilityStatus",
    "LiveEligibilityV2",
]
