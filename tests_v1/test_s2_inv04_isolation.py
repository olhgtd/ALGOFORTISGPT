from __future__ import annotations

import inspect
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from dashboard.backend.account_v2.authority_service import AuthenticatedPrincipal, S2AccountAuthorityService


class _Audit:
    def record_required_intent(self, **_kwargs):
        return "audit-1"


class _Repository:
    def __init__(self) -> None:
        self.devices = {}

    def list_devices(self, *, user_id):
        return tuple(record for (owner, _), record in self.devices.items() if owner == user_id)

    def get_device(self, *, user_id, device_id):
        return self.devices.get((user_id, device_id))

    def revoke_session_family(self, *, user_id, family_id, revoked_at):
        return None


class _DeviceService:
    def enroll(self, **_kwargs):
        return "enrolled"

    def revoke(self, **_kwargs):
        return None


class _RecoveryService:
    def __init__(self) -> None:
        self.calls = []

    def recover(self, *, principal_user_id, target_user_id, proof, now):
        self.calls.append((principal_user_id, target_user_id))
        return "recovered"


def test_facade_has_no_free_target_user_id_and_recovery_is_self_scoped() -> None:
    repository = _Repository()
    recovery = _RecoveryService()
    service = S2AccountAuthorityService(repository, _DeviceService(), recovery, _Audit())
    user_id = uuid4()
    principal = AuthenticatedPrincipal(user_id, "fam-1")

    assert "target_user_id" not in inspect.signature(service.revoke_device).parameters
    assert "target_user_id" not in inspect.signature(service.revoke_session_family).parameters

    service.recover(
        principal=principal,
        proof="ok",
        now=datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc),
    )
    assert recovery.calls == [(user_id, user_id)]


def test_recovery_fails_closed_when_rate_limit_service_is_missing() -> None:
    repository = _Repository()
    recovery = _RecoveryService()
    service = S2AccountAuthorityService(repository, _DeviceService(), recovery, _Audit())
    principal = AuthenticatedPrincipal(uuid4(), "fam-1")

    with pytest.raises(PermissionError, match="rate-limit"):
        service.recover(
            principal=principal,
            proof="ok",
            now=datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc),
        )
    assert recovery.calls == []


def test_user_cannot_read_foreign_device_through_authority_facade() -> None:
    repository = _Repository()
    user_a = uuid4()
    user_b = uuid4()
    foreign_device = object()
    repository.devices[(user_b, "b-dev")] = foreign_device
    service = S2AccountAuthorityService(repository, _DeviceService(), _RecoveryService(), _Audit())

    assert service.get_device(
        principal=AuthenticatedPrincipal(user_a, "a-fam"),
        device_id="b-dev",
    ) is None
