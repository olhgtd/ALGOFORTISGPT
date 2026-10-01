"""Typed S2 contracts with no trading or broker authority."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class DeviceSessionGateStatus(str, Enum):
    VALID = "VALID"
    REVOKED = "REVOKED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    DEVICE_UNTRUSTED = "DEVICE_UNTRUSTED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    AUTHORITY_UNAVAILABLE = "AUTHORITY_UNAVAILABLE"


class AccountRuntimeMode(str, Enum):
    NORMAL = "NORMAL"
    LOCAL_SAFETY_ONLY = "LOCAL_SAFETY_ONLY"


@dataclass(frozen=True, slots=True)
class DeviceSessionGateResult:
    schema_version: str
    user_id: UUID
    device_id: str
    session_family_id: str | None
    status: DeviceSessionGateStatus
    reasons: tuple[str, ...]
    authority_evidence_ref: str | None
    evaluated_at: datetime
    audit_ref: str | None


@dataclass(frozen=True, slots=True)
class UpdateSafeWindowPolicyRef:
    policy_id: str
    version: str


@dataclass(frozen=True, slots=True)
class EntitlementTimeEvidence:
    server_issued_at: datetime
    last_successful_server_check_in: datetime
    lease_expires_at: datetime
    monotonic_anchor: float | None
    monotonic_elapsed_seconds: float | None
    boot_session_id: str | None


@dataclass(frozen=True, slots=True)
class ProductionIdentityPolicy:
    rp_id: str
    origin: str
    environment: str
    production_migration_required: bool
