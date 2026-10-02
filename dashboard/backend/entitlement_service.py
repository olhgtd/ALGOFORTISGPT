"""AlgoFortis signed offline entitlement authority for Track-P S3.

OD-V2-21 rules:
- signed, device-bound lease;
- trusted server/check-in + monotonic time evidence;
- wall clock alone cannot extend entitlement;
- uncertain/expired entitlement blocks entitlement-dependent new operations;
- protective safety and read-only safety access remain available.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from dashboard.backend.account_v2.contracts import EntitlementTimeEvidence
from dashboard.backend.account_v2.policy_seams import evaluate_entitlement_time

OFFLINE_LEASE_VALIDITY_SEC = 7 * 86400


@dataclass(frozen=True)
class EntitlementLease:
    lease_id: str
    user_id: str
    device_id: str
    tier: str
    capabilities: list[str]
    issued_at: float
    expires_at: float
    max_observed_timestamp: float
    signing_key_id: str
    lease_signature: str


class EntitlementSignatureVerifier(Protocol):
    def verify(self, *, lease: EntitlementLease) -> bool: ...


class EntitlementLeaseManager:
    """Validates signed leases using the shared S2 time-evidence authority."""

    def __init__(
        self,
        last_known_timestamp: float | None = None,
        *,
        signature_verifier: EntitlementSignatureVerifier | None = None,
    ):
        # Kept only as legacy diagnostic state; it is not an entitlement clock.
        self._legacy_max_observed_time = last_known_timestamp
        self._signature_verifier = signature_verifier

    @staticmethod
    def _denied(reason: str) -> dict[str, Any]:
        return {
            "valid": False,
            "reason": reason,
            "entitlement_dependent_new_operation_allowed": False,
            "can_execute_risk_management": True,
            "can_read_safety_state": True,
            "can_export_data": True,
        }

    def validate_lease(
        self,
        lease: EntitlementLease,
        current_device_id: str,
        *,
        time_evidence: EntitlementTimeEvidence,
        observed_wall_time: datetime,
    ) -> dict[str, Any]:
        """Validate signature, device binding and trusted time evidence."""
        if self._signature_verifier is None:
            return self._denied("ENTITLEMENT_SIGNATURE_UNVERIFIED")
        if not self._signature_verifier.verify(lease=lease):
            return self._denied("ENTITLEMENT_SIGNATURE_INVALID")
        if lease.device_id != current_device_id:
            return self._denied("DEVICE_MISMATCH")

        issued = datetime.fromtimestamp(lease.issued_at, tz=timezone.utc)
        expires = datetime.fromtimestamp(lease.expires_at, tz=timezone.utc)
        if (
            time_evidence.server_issued_at != issued
            or time_evidence.lease_expires_at != expires
        ):
            return self._denied("ENTITLEMENT_TIME_EVIDENCE_MISMATCH")

        time_decision = evaluate_entitlement_time(
            time_evidence,
            observed_wall_time=observed_wall_time,
        )
        if not time_decision.entitlement_dependent_new_operation_allowed:
            return self._denied(time_decision.status)

        trusted_now = (
            time_evidence.last_successful_server_check_in.timestamp()
            + float(time_evidence.monotonic_elapsed_seconds or 0.0)
        )
        return {
            "valid": True,
            "reason": time_decision.status,
            "tier": lease.tier,
            "capabilities": list(lease.capabilities),
            "expires_in_hours": max(0.0, (lease.expires_at - trusted_now) / 3600.0),
            "entitlement_dependent_new_operation_allowed": True,
            "can_execute_risk_management": True,
            "can_read_safety_state": True,
            "can_export_data": True,
        }
