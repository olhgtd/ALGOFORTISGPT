from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib
from pathlib import Path

import pytest

from engine.broker_adapters.angelone_v2.contracts import AngelOneBrokerProfile, AngelOneCredentialRef

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "engine" / "broker_adapters" / "angelone_v2" / "session.py"


def _load():
    assert MODULE.is_file(), "Phase-6 Angel One session module is missing"
    return importlib.import_module("engine.broker_adapters.angelone_v2.session")


def _profile():
    return AngelOneBrokerProfile(
        "ANGELONE/SMARTAPI/READ_ONLY",
        "2026-09-27",
        "https://apiconnect.angelone.in",
        "docs-v1",
    )


def _credentials():
    return AngelOneCredentialRef("secret://angelone/test", "acct-ref")


def _now():
    return datetime(2026, 9, 27, 4, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self, now):
        self.value = now

    def now(self):
        return self.value


class Transport:
    def __init__(self, *, fail_auth=False, fail_refresh=False):
        self.fail_auth = fail_auth
        self.fail_refresh = fail_refresh

    def authenticate(self, *, profile, credential_ref):
        if self.fail_auth:
            raise RuntimeError("auth failed for super-secret-token")
        return {
            "access_token": "super-secret-token",
            "refresh_token": "refresh-secret-token",
            "expires_at": _now() + timedelta(minutes=15),
            "daily_valid_until": _now() + timedelta(hours=8),
        }

    def refresh(self, *, profile, credential_ref, refresh_token):
        if self.fail_refresh:
            raise RuntimeError("refresh failed with refresh-secret-token")
        assert refresh_token == "refresh-secret-token"
        return {
            "access_token": "new-secret-token",
            "refresh_token": "new-refresh-secret",
            "expires_at": _now() + timedelta(minutes=30),
            "daily_valid_until": _now() + timedelta(hours=8),
        }


def test_missing_profile_credentials_transport_or_clock_fail_closed() -> None:
    m = _load()
    AngelOneSessionAuthority = m.AngelOneSessionAuthority

    with pytest.raises((TypeError, ValueError)):
        AngelOneSessionAuthority(profile=None, credential_ref=_credentials(), transport=Transport(), clock=Clock(_now()))
    with pytest.raises((TypeError, ValueError)):
        AngelOneSessionAuthority(profile=_profile(), credential_ref=None, transport=Transport(), clock=Clock(_now()))
    with pytest.raises((TypeError, ValueError)):
        AngelOneSessionAuthority(profile=_profile(), credential_ref=_credentials(), transport=None, clock=Clock(_now()))
    with pytest.raises((TypeError, ValueError)):
        AngelOneSessionAuthority(profile=_profile(), credential_ref=_credentials(), transport=Transport(), clock=None)


def test_authentication_evidence_and_repr_never_expose_tokens() -> None:
    m = _load()
    AngelOneSessionAuthority, AngelOneSessionState = m.AngelOneSessionAuthority, m.AngelOneSessionState

    authority = AngelOneSessionAuthority(
        profile=_profile(), credential_ref=_credentials(), transport=Transport(), clock=Clock(_now())
    )
    evidence = authority.authenticate()
    assert evidence.state is AngelOneSessionState.AUTHENTICATED
    rendered = repr(evidence) + repr(authority)
    assert "super-secret-token" not in rendered
    assert "refresh-secret-token" not in rendered
    assert not hasattr(evidence, "access_token")
    assert not hasattr(evidence, "refresh_token")
    assert not hasattr(evidence, "arm_enabled")


def test_auth_error_is_redacted_and_fails_closed() -> None:
    m = _load()
    AngelOneSessionAuthority, AngelOneSessionUnavailable = m.AngelOneSessionAuthority, m.AngelOneSessionUnavailable

    authority = AngelOneSessionAuthority(
        profile=_profile(), credential_ref=_credentials(), transport=Transport(fail_auth=True), clock=Clock(_now())
    )
    with pytest.raises(AngelOneSessionUnavailable) as exc:
        authority.authenticate()
    assert "super-secret-token" not in str(exc.value)
    assert "authentication unavailable" in str(exc.value)


def test_expiry_daily_boundary_and_refresh_failure_never_create_arm_permission() -> None:
    m = _load()
    AngelOneSessionAuthority = m.AngelOneSessionAuthority
    AngelOneSessionState = m.AngelOneSessionState
    AngelOneSessionUnavailable = m.AngelOneSessionUnavailable

    clock = Clock(_now())
    authority = AngelOneSessionAuthority(
        profile=_profile(), credential_ref=_credentials(), transport=Transport(), clock=clock
    )
    authority.authenticate()
    clock.value = _now() + timedelta(minutes=16)
    expired = authority.health()
    assert expired.state is AngelOneSessionState.EXPIRED
    assert expired.observation_available is False
    assert not hasattr(expired, "arm")

    authority = AngelOneSessionAuthority(
        profile=_profile(), credential_ref=_credentials(), transport=Transport(fail_refresh=True), clock=Clock(_now())
    )
    authority.authenticate()
    with pytest.raises(AngelOneSessionUnavailable):
        authority.refresh()
    assert authority.health().observation_available is False

    clock2 = Clock(_now())
    authority2 = AngelOneSessionAuthority(
        profile=_profile(), credential_ref=_credentials(), transport=Transport(), clock=clock2
    )
    authority2.authenticate()
    clock2.value = _now() + timedelta(hours=9)
    assert authority2.health().state is AngelOneSessionState.DAILY_BOUNDARY_EXPIRED
    assert authority2.health().observation_available is False
