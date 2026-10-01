"""Narrow durable account-authority repository contracts for S2."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


class AccountAuthorityRecordUnavailable(LookupError):
    """Requested account-owned state is absent or outside the caller's scope."""


class AccountAuthorityUnavailable(RuntimeError):
    """Central account authority cannot be reached or its result cannot be verified."""


class RefreshTokenReplayDetected(PermissionError):
    """A consumed refresh token reached the atomic rotation boundary."""


class DeviceQuotaAuthorityExceeded(PermissionError):
    """Authoritative active-device quota was reached inside the durable boundary."""


@dataclass(frozen=True, slots=True)
class AccountStateRecord:
    user_id: UUID
    lifecycle: str
    account_status: str
    activation_status: str
    security_state: str


@dataclass(frozen=True, slots=True)
class DeviceRecord:
    user_id: UUID
    device_id: str
    public_key: bytes
    fingerprint: str
    status: str
    created_at: datetime
    revoked_at: datetime | None


@dataclass(frozen=True, slots=True)
class DeviceProofChallengeRecord:
    user_id: UUID
    device_id: str
    purpose: str
    challenge_hash: str
    issued_at: datetime
    expires_at: datetime
    consumed_at: datetime | None


@dataclass(frozen=True, slots=True)
class SessionFamilyRecord:
    user_id: UUID
    family_id: str
    device_id: str
    current_refresh_hash: str
    state: str
    created_at: datetime
    updated_at: datetime
    revoked_at: datetime | None


@dataclass(frozen=True, slots=True)
class SessionFamilyPolicyRecord:
    user_id: UUID
    family_id: str
    absolute_expires_at: datetime
    idle_expires_at: datetime


@dataclass(frozen=True, slots=True)
class RateLimitStateRecord:
    user_id: UUID
    flow: str
    subject_key: str
    failure_count: int
    locked_until: datetime | None
    updated_at: datetime


class AccountAuthorityRepository(Protocol):
    def get_account_state(self, *, user_id: UUID) -> AccountStateRecord | None: ...
    def has_enabled_webauthn_credential(self, *, user_id: UUID, rp_id: str | None = None) -> bool: ...
    def list_devices(self, *, user_id: UUID) -> tuple[DeviceRecord, ...]: ...
    def get_device(self, *, user_id: UUID, device_id: str) -> DeviceRecord | None: ...
    def register_device(self, *, user_id: UUID, device_id: str, public_key: bytes, fingerprint: str, created_at: datetime, max_active_devices: int = 3) -> DeviceRecord: ...
    def revoke_device(self, *, user_id: UUID, device_id: str, revoked_at: datetime) -> None: ...
    def save_device_challenge(self, *, user_id: UUID, device_id: str, purpose: str, challenge_hash: str, issued_at: datetime, expires_at: datetime) -> DeviceProofChallengeRecord: ...
    def consume_device_challenge(self, *, user_id: UUID, device_id: str, purpose: str, challenge_hash: str, consumed_at: datetime) -> DeviceProofChallengeRecord: ...
    def get_session_family(self, *, user_id: UUID, family_id: str) -> SessionFamilyRecord | None: ...
    def list_session_families(self, *, user_id: UUID) -> tuple[SessionFamilyRecord, ...]: ...
    def save_session_family(self, *, user_id: UUID, family_id: str, device_id: str, current_refresh_hash: str, state: str, created_at: datetime, updated_at: datetime) -> SessionFamilyRecord: ...
    def revoke_session_family(self, *, user_id: UUID, family_id: str, revoked_at: datetime) -> None: ...
    def revoke_all_access_for_recovery(self, *, user_id: UUID, revoked_at: datetime) -> None: ...
    def save_session_policy(self, *, user_id: UUID, family_id: str, absolute_expires_at: datetime, idle_expires_at: datetime) -> SessionFamilyPolicyRecord: ...
    def get_session_policy(self, *, user_id: UUID, family_id: str) -> SessionFamilyPolicyRecord | None: ...
    def is_consumed_refresh_hash(self, *, user_id: UUID, family_id: str, token_hash: str) -> bool: ...
    def rotate_refresh_hash(self, *, user_id: UUID, family_id: str, expected_current_hash: str, new_current_hash: str, consumed_hash: str, updated_at: datetime, idle_expires_at: datetime) -> None: ...
    def get_rate_limit_state(self, *, user_id: UUID, flow: str, subject_key: str) -> RateLimitStateRecord | None: ...
    def save_rate_limit_state(self, *, user_id: UUID, flow: str, subject_key: str, failure_count: int, locked_until: datetime | None, updated_at: datetime) -> RateLimitStateRecord: ...
    def record_rate_limit_failure(self, *, user_id: UUID, flow: str, subject_key: str, max_failures: int, cooldown_seconds: int, now: datetime) -> RateLimitStateRecord: ...
    def clear_rate_limit_state(self, *, user_id: UUID, flow: str, subject_key: str) -> None: ...
