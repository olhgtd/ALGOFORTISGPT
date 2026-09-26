from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from dashboard.backend.account_v2.contracts import DeviceSessionGateStatus
from dashboard.backend.account_v2.gate import DeviceSessionGate


@dataclass
class _Account:
    lifecycle: str = "ACTIVE"
    account_status: str = "ACTIVE"
    activation_status: str = "REDEEMED"
    security_state: str = "ACTIVE"


@dataclass
class _Device:
    status: str = "ACTIVE"


@dataclass
class _Family:
    state: str = "ACTIVE"
    device_id: str = "dev-1"


@dataclass
class _Policy:
    absolute_expires_at: datetime
    idle_expires_at: datetime


class _Repository:
    def __init__(self, *, account=None, credential_ready=True, device=None, family=None, policy=None) -> None:
        self.account = account if account is not None else _Account()
        self.credential_ready = credential_ready
        self.device = device
        self.family = family
        self.policy = policy

    def get_account_state(self, **_kwargs):
        return self.account

    def has_enabled_webauthn_credential(self, **_kwargs):
        return self.credential_ready

    def get_device(self, **_kwargs):
        return self.device

    def get_session_family(self, **_kwargs):
        return self.family

    def get_session_policy(self, **_kwargs):
        return self.policy


def _now() -> datetime:
    return datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def _gate(repository: _Repository) -> DeviceSessionGate:
    return DeviceSessionGate(repository, authority_evidence_ref="acct-evidence")


def test_account_and_webauthn_state_are_mandatory_gate_prerequisites() -> None:
    user_id = uuid4()
    now = _now()
    fresh = _Policy(now + timedelta(days=30), now + timedelta(days=7))

    suspended = _Account(account_status="SUSPENDED")
    result = _gate(_Repository(account=suspended, device=_Device(), family=_Family(), policy=fresh)).evaluate(user_id, "dev-1", "fam-1", now)
    assert result.status is DeviceSessionGateStatus.REVOKED

    recovery = _Account(security_state="RECOVERY_REQUIRED")
    result = _gate(_Repository(account=recovery, device=_Device(), family=_Family(), policy=fresh)).evaluate(user_id, "dev-1", "fam-1", now)
    assert result.status is DeviceSessionGateStatus.RECOVERY_REQUIRED

    result = _gate(_Repository(credential_ready=False, device=_Device(), family=_Family(), policy=fresh)).evaluate(user_id, "dev-1", "fam-1", now)
    assert result.status is DeviceSessionGateStatus.RECOVERY_REQUIRED


def test_device_session_gate_maps_all_fail_closed_states() -> None:
    user_id = uuid4()
    now = _now()

    assert _gate(_Repository(device=_Device("REVOKED"))).evaluate(user_id, "dev-1", "fam-1", now).status is DeviceSessionGateStatus.REVOKED
    assert _gate(_Repository(device=None)).evaluate(user_id, "dev-1", "fam-1", now).status is DeviceSessionGateStatus.DEVICE_UNTRUSTED
    assert _gate(_Repository(device=_Device(), family=_Family("RECOVERY_REQUIRED"))).evaluate(user_id, "dev-1", "fam-1", now).status is DeviceSessionGateStatus.RECOVERY_REQUIRED
    assert _gate(_Repository(device=_Device(), family=_Family("REVOKED"))).evaluate(user_id, "dev-1", "fam-1", now).status is DeviceSessionGateStatus.REVOKED
    assert _gate(_Repository(device=_Device(), family=None)).evaluate(user_id, "dev-1", "fam-1", now).status is DeviceSessionGateStatus.SESSION_EXPIRED

    expired = _Policy(now - timedelta(seconds=1), now + timedelta(days=1))
    assert _gate(_Repository(device=_Device(), family=_Family(), policy=expired)).evaluate(user_id, "dev-1", "fam-1", now).status is DeviceSessionGateStatus.SESSION_EXPIRED


def test_device_session_gate_valid_requires_active_account_credential_device_family_and_fresh_policy() -> None:
    user_id = uuid4()
    now = _now()
    policy = _Policy(now + timedelta(days=30), now + timedelta(days=7))

    result = _gate(_Repository(device=_Device(), family=_Family(), policy=policy)).evaluate(user_id, "dev-1", "fam-1", now)

    assert result.status is DeviceSessionGateStatus.VALID
    assert result.reasons == ("ACCOUNT_DEVICE_SESSION_VALID",)
    assert result.authority_evidence_ref == "acct-evidence"
    assert not ({"arm", "place_order", "cancel_order", "modify_order"} & set(dir(result)))
