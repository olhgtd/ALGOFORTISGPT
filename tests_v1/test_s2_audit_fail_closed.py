from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from dashboard.backend.account_v2.authority_service import AuthenticatedPrincipal, S2AccountAuthorityService


class _FailingAudit:
    def record_required_intent(self, **_kwargs):
        raise RuntimeError("audit unavailable")


class _Repository:
    def __init__(self) -> None:
        self.revoked_families = []

    def list_devices(self, *, user_id):
        return ()

    def get_device(self, *, user_id, device_id):
        return None

    def revoke_session_family(self, *, user_id, family_id, revoked_at):
        self.revoked_families.append((user_id, family_id))


class _DeviceService:
    def __init__(self) -> None:
        self.enrolled = []
        self.revoked = []

    def enroll(self, *, user_id, **_kwargs):
        self.enrolled.append(user_id)
        return "enrolled"

    def revoke(self, *, user_id, device_id, revoked_at):
        self.revoked.append((user_id, device_id))


class _RecoveryService:
    def __init__(self) -> None:
        self.calls = []

    def recover(self, **kwargs):
        self.calls.append(kwargs)
        return "recovered"


def test_required_audit_failure_prevents_device_and_session_mutation() -> None:
    repository = _Repository()
    devices = _DeviceService()
    service = S2AccountAuthorityService(repository, devices, _RecoveryService(), _FailingAudit())
    principal = AuthenticatedPrincipal(uuid4(), "fam-1")
    now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(RuntimeError):
        service.revoke_device(principal=principal, device_id="dev-1", revoked_at=now)
    with pytest.raises(RuntimeError):
        service.revoke_session_family(principal=principal, family_id="fam-1", revoked_at=now)

    assert devices.revoked == []
    assert repository.revoked_families == []
