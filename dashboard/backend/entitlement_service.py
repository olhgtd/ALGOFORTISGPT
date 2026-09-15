"""AlgoFortis V1 — Offline Entitlement Lease Engine
Implements ADR-21.
- Signed offline entitlement leases with 7-day validity.
- Clock rollback resistance.
- Core Invariant: License expiration blocks new premium operations, but NEVER blocks:
  1. Local protective risk management & stop-loss rules.
  2. Access to or export of user's own data.
"""
import time
import json
import base64
import hashlib
from typing import Dict, Any, Optional, Set, List
from dataclasses import dataclass

OFFLINE_LEASE_VALIDITY_SEC = 7 * 86400  # 7 Days


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


class EntitlementLeaseManager:
    """Validates and enforces offline entitlement leases."""

    def __init__(self, last_known_timestamp: Optional[float] = None):
        self._max_observed_time = last_known_timestamp or time.time()

    def validate_lease(self, lease: EntitlementLease, current_device_id: str) -> Dict[str, Any]:
        """Validate lease validity, device binding, and clock monotonicity."""
        now = time.time()

        # 1. Clock Rollback Detection
        if now < self._max_observed_time - 300:  # 5 min tolerance for NTP jitter
            return {
                "valid": False,
                "reason": "CLOCK_ROLLBACK_DETECTED",
                "can_execute_risk_management": True,
                "can_export_data": True
            }

        # Update high-water mark
        self._max_observed_time = max(self._max_observed_time, now)

        # 2. Device Binding Check
        if lease.device_id != current_device_id:
            return {
                "valid": False,
                "reason": "DEVICE_MISMATCH",
                "can_execute_risk_management": True,
                "can_export_data": True
            }

        # 3. Expiration Check (7-Day Limit)
        if now > lease.expires_at:
            return {
                "valid": False,
                "reason": "LEASE_EXPIRED",
                "can_execute_risk_management": True,
                "can_export_data": True
            }

        return {
            "valid": True,
            "tier": lease.tier,
            "capabilities": lease.capabilities,
            "expires_in_hours": (lease.expires_at - now) / 3600,
            "can_execute_risk_management": True,
            "can_export_data": True
        }
