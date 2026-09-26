"""Narrow durable account-authority repository contracts for S2."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


class AccountAuthorityRecordUnavailable(LookupError):
    """Requested account-owned state is absent or outside the caller's scope."""


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
class SessionFamilyRecord:
    user_id: UUID
    family_id: str
    device_id: str
    current_refresh_hash: str
    state: str
    created_at: datetime
    updated_at: datetime
    revoked_at: datetime | None


class AccountAuthorityRepository(Protocol):
    def list_devices(self, *, user_id: UUID) -> tuple[DeviceRecord, ...]: ...
    def get_device(self, *, user_id: UUID, device_id: str) -> DeviceRecord | None: ...
    def register_device(self, *, user_id: UUID, device_id: str, public_key: bytes, fingerprint: str, created_at: datetime) -> DeviceRecord: ...
    def revoke_device(self, *, user_id: UUID, device_id: str, revoked_at: datetime) -> None: ...
    def get_session_family(self, *, user_id: UUID, family_id: str) -> SessionFamilyRecord | None: ...
    def save_session_family(self, *, user_id: UUID, family_id: str, device_id: str, current_refresh_hash: str, state: str, created_at: datetime, updated_at: datetime) -> SessionFamilyRecord: ...
    def revoke_session_family(self, *, user_id: UUID, family_id: str, revoked_at: datetime) -> None: ...
