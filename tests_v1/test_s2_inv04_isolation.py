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
    def __init__(self) -> None:
        self.enroll_calls = []
        self.reproof_calls = []

    def enroll(self, **kwargs):
        self.enroll_calls.append(kwargs)
        return "enrolled"

    def reprove_existing_device(self, **kwargs):
        self.reproof_calls.append(kwargs)
        return "reproved"

    def revoke(self, **_kwargs):
        return None


class _RecoveryService:
    def __init__(self, *, deny: bool = False) -> None:
        self.calls = []
        self.deny = deny

    def recover(self, *, principal_user_id, target_user_id, proof, now):
        self.calls.append((principal_user_id, target_user_id))
        if self.deny:
            raise PermissionError("proof rejected")
        return "recovered"


class _Decision:
    def __init__(self, locked: bool) -> None:
        self.locked = locked


class _RecoveryRateLimiter:
    def __init__(self, *, locked: bool = False) -> None:
        self.locked = locked
        self.events = []

    def is_locked(self, **kwargs):
        self.events.append(("check", kwargs))
        return _Decision(self.locked)

    def record_failure(self, **kwargs):
        self.events.append(("failure", kwargs))

    def record_success(self, **kwargs):
        self.events.append(("success", kwargs))


def _now():
    return datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def test_facade_has_no_free_target_user_id_and_recovery_is_self_scoped() -> None:
    repository = _Repository()
    recovery = _RecoveryService()
    limiter = _RecoveryRateLimiter()
    service = S2AccountAuthorityService(repository, _DeviceService(), recovery, _Audit(), rate_limiter=limiter)
    user_id = uuid4()
    principal = AuthenticatedPrincipal(user_id, "fam-1")

    assert "target_user_id" not in inspect.signature(service.revoke_device).parameters
    assert "target_user_id" not in inspect.signature(service.revoke_session_family).parameters

    service.recover(principal=principal, proof="ok", now=_now())
    assert recovery.calls == [(user_id, user_id)]
    assert [event for event, _ in limiter.events] == ["check", "success"]
    assert limiter.events[0][1]["flow"].value == "RECOVERY"
    assert limiter.events[0][1]["subject_key"] == str(user_id)


def test_recovery_fails_closed_when_rate_limit_service_is_missing() -> None:
    repository = _Repository()
    recovery = _RecoveryService()
    service = S2AccountAuthorityService(repository, _DeviceService(), recovery, _Audit())
    principal = AuthenticatedPrincipal(uuid4(), "fam-1")

    with pytest.raises(PermissionError, match="rate-limit"):
        service.recover(principal=principal, proof="ok", now=_now())
    assert recovery.calls == []


def test_locked_recovery_rate_limit_blocks_proof_verification() -> None:
    recovery = _RecoveryService()
    limiter = _RecoveryRateLimiter(locked=True)
    service = S2AccountAuthorityService(_Repository(), _DeviceService(), recovery, _Audit(), rate_limiter=limiter)
    principal = AuthenticatedPrincipal(uuid4(), "fam-1")

    with pytest.raises(PermissionError, match="rate-limit"):
        service.recover(principal=principal, proof="ok", now=_now())
    assert recovery.calls == []
    assert [event for event, _ in limiter.events] == ["check"]


def test_rejected_recovery_proof_records_only_recovery_flow_failure() -> None:
    recovery = _RecoveryService(deny=True)
    limiter = _RecoveryRateLimiter()
    service = S2AccountAuthorityService(_Repository(), _DeviceService(), recovery, _Audit(), rate_limiter=limiter)
    principal = AuthenticatedPrincipal(uuid4(), "fam-1")

    with pytest.raises(PermissionError, match="proof rejected"):
        service.recover(principal=principal, proof="bad", now=_now())
    assert [event for event, _ in limiter.events] == ["check", "failure"]
    assert limiter.events[1][1]["flow"].value == "RECOVERY"


def test_locked_device_proof_rate_limit_blocks_enrollment_before_device_service() -> None:
    devices = _DeviceService()
    limiter = _RecoveryRateLimiter(locked=True)
    service = S2AccountAuthorityService(_Repository(), devices, _RecoveryService(), _Audit(), rate_limiter=limiter)
    principal = AuthenticatedPrincipal(uuid4(), "fam-1")

    with pytest.raises(PermissionError, match="rate-limit"):
        service.enroll_device(
            principal=principal,
            device_id="dev-1",
            public_key=b"pk",
            fingerprint="fp",
            challenge=b"challenge",
            signature=b"sig",
            created_at=_now(),
        )
    assert devices.enroll_calls == []
    assert [event for event, _ in limiter.events] == ["check"]
    assert limiter.events[0][1]["flow"].value == "DEVICE_PROOF"


def test_locked_device_proof_rate_limit_blocks_reproof_before_device_service() -> None:
    devices = _DeviceService()
    limiter = _RecoveryRateLimiter(locked=True)
    service = S2AccountAuthorityService(_Repository(), devices, _RecoveryService(), _Audit(), rate_limiter=limiter)
    principal = AuthenticatedPrincipal(uuid4(), "fam-1")

    with pytest.raises(PermissionError, match="rate-limit"):
        service.reprove_device(
            principal=principal,
            device_id="dev-1",
            public_key=b"pk",
            fingerprint="fp",
            challenge=b"challenge",
            signature=b"sig",
            now=_now(),
        )
    assert devices.reproof_calls == []
    assert limiter.events[0][1]["flow"].value == "DEVICE_PROOF"


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
