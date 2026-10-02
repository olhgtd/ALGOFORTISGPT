"""AlgoFortis V2 — S3 offline entitlement lease validation.

The lease is an externally signed capability document. S3 deliberately has no
wall-clock-only fallback: entitlement-dependent new operations require verified
lease signature plus trusted EntitlementTimeEvidence from the S2 authority
contract. Protective exits, reconciliation, local position monitoring and user
data export remain available when entitlement validation fails closed.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, Any, List, Optional

from dashboard.backend.account_v2.contracts import EntitlementTimeEvidence
from dashboard.backend.account_v2.policy_seams import evaluate_entitlement_time

OFFLINE_LEASE_VALIDITY_SEC = 7 * 86400
LeaseSignatureVerifier = Callable[[bytes, str, str], bool]


@dataclass(frozen=True)
class EntitlementLease:
    lease_id: str
    user_id: str
    device_id: str
    tier: str
    capabilities: List[str]
    issued_at: float
    expires_at: float
    max_observed_timestamp: float
    signing_key_id: str
    signature: str


class EntitlementLeaseManager:
    """Validate signed leases without granting authority from local wall time."""

    def __init__(
        self,
        *,
        lease_signature_verifier: Optional[LeaseSignatureVerifier] = None,
    ):
        self._lease_signature_verifier = lease_signature_verifier

    @staticmethod
    def canonical_lease_bytes(lease: EntitlementLease) -> bytes:
        payload = {
            "lease_id": lease.lease_id,
            "user_id": lease.user_id,
            "device_id": lease.device_id,
            "tier": lease.tier,
            "capabilities": list(lease.capabilities),
            "issued_at": lease.issued_at,
            "expires_at": lease.expires_at,
            "max_observed_timestamp": lease.max_observed_timestamp,
            "signing_key_id": lease.signing_key_id,
        }
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    @staticmethod
    def _denied(reason: str) -> Dict[str, Any]:
        return {
            "valid": False,
            "reason": reason,
            "can_execute_risk_management": True,
            "can_export_data": True,
            "protective_safety_allowed": True,
        }

    def validate_lease(
        self,
        lease: EntitlementLease,
        current_device_id: str,
        *,
        time_evidence: Optional[EntitlementTimeEvidence],
        observed_wall_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Validate signature, binding, lease duration and trusted time evidence."""
        if self._lease_signature_verifier is None:
            return self._denied("LEASE_SIGNATURE_VERIFIER_UNAVAILABLE")
        if not lease.signing_key_id.strip() or not lease.signature.strip():
            return self._denied("LEASE_SIGNATURE_MISSING")

        try:
            signature_valid = bool(
                self._lease_signature_verifier(
                    self.canonical_lease_bytes(lease),
                    lease.signature,
                    lease.signing_key_id,
                )
            )
        except Exception:
            return self._denied("LEASE_SIGNATURE_INVALID")
        if not signature_valid:
            return self._denied("LEASE_SIGNATURE_INVALID")

        if lease.device_id != current_device_id:
            return self._denied("DEVICE_MISMATCH")

        validity_seconds = lease.expires_at - lease.issued_at
        if validity_seconds <= 0 or validity_seconds > OFFLINE_LEASE_VALIDITY_SEC:
            return self._denied("LEASE_VALIDITY_INVALID")

        if time_evidence is None:
            return self._denied("ENTITLEMENT_TIME_UNCERTAIN")

        lease_issued_at = datetime.fromtimestamp(lease.issued_at, tz=timezone.utc)
        lease_expires_at = datetime.fromtimestamp(lease.expires_at, tz=timezone.utc)
        tolerance_seconds = 1.0
        if abs((time_evidence.server_issued_at - lease_issued_at).total_seconds()) > tolerance_seconds:
            return self._denied("ENTITLEMENT_TIME_UNCERTAIN")
        if abs((time_evidence.lease_expires_at - lease_expires_at).total_seconds()) > tolerance_seconds:
            return self._denied("ENTITLEMENT_TIME_UNCERTAIN")

        wall_time = observed_wall_time or datetime.now(timezone.utc)
        if wall_time.tzinfo is None:
            wall_time = wall_time.replace(tzinfo=timezone.utc)

        decision = evaluate_entitlement_time(
            time_evidence,
            observed_wall_time=wall_time,
        )
        if not decision.entitlement_dependent_new_operation_allowed:
            return self._denied(decision.status)

        assert time_evidence.monotonic_elapsed_seconds is not None
        trusted_now = (
            time_evidence.last_successful_server_check_in.timestamp()
            + time_evidence.monotonic_elapsed_seconds
        )
        expires_in_hours = max(0.0, (lease.expires_at - trusted_now) / 3600.0)
        return {
            "valid": True,
            "tier": lease.tier,
            "capabilities": list(lease.capabilities),
            "expires_in_hours": expires_in_hours,
            "time_status": decision.status,
            "can_execute_risk_management": True,
            "can_export_data": True,
            "protective_safety_allowed": True,
        }
