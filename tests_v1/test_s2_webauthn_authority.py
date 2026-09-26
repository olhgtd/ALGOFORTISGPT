from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest


def test_development_profile_requires_explicit_localhost_http_port() -> None:
    from dashboard.backend.account_v2.webauthn_authority import validate_relying_party_profile

    valid = validate_relying_party_profile(rp_id="localhost", origin="http://localhost:5173", development_only=True)
    assert valid.rp_id == "localhost"
    with pytest.raises(Exception):
        validate_relying_party_profile(rp_id="localhost", origin="https://localhost", development_only=True)


def test_production_profile_rejects_http_and_origin_mismatch() -> None:
    from dashboard.backend.account_v2.webauthn_authority import validate_relying_party_profile

    with pytest.raises(Exception):
        validate_relying_party_profile(rp_id="algofortis.example", origin="http://algofortis.example", development_only=False)
    with pytest.raises(Exception):
        validate_relying_party_profile(rp_id="algofortis.example", origin="https://evil.example", development_only=False)


def test_dev_credential_cannot_be_silently_promoted_to_production() -> None:
    from dashboard.backend.account_v2.contracts import ProductionIdentityPolicy
    from dashboard.backend.account_v2.webauthn_authority import ProductionCredentialReenrollmentRequired, WebAuthnAuthority

    source = ProductionIdentityPolicy(rp_id="localhost", origin="http://localhost:5173", environment="development", production_migration_required=False)
    target = ProductionIdentityPolicy(rp_id="algofortis.example", origin="https://algofortis.example", environment="production", production_migration_required=True)

    with pytest.raises(ProductionCredentialReenrollmentRequired):
        WebAuthnAuthority.require_credential_compatible(source=source, target=target)


def test_same_production_identity_does_not_require_migration() -> None:
    from dashboard.backend.account_v2.contracts import ProductionIdentityPolicy
    from dashboard.backend.account_v2.webauthn_authority import WebAuthnAuthority

    policy = ProductionIdentityPolicy(rp_id="algofortis.example", origin="https://algofortis.example", environment="production", production_migration_required=False)
    WebAuthnAuthority.require_credential_compatible(source=policy, target=policy)


class _User:
    def __init__(self):
        self.user_id = uuid4()


class _Decision:
    def __init__(self, locked: bool):
        self.locked = locked


class _Limiter:
    def __init__(self, *, locked: bool = False):
        self.locked = locked
        self.events = []

    def is_locked(self, **kwargs):
        self.events.append(("check", kwargs))
        return _Decision(self.locked)

    def record_failure(self, **kwargs):
        self.events.append(("failure", kwargs))

    def record_success(self, **kwargs):
        self.events.append(("success", kwargs))


class _Ceremonies:
    def __init__(self):
        self.issued = 0
        self.completed = 0

    def issue_authentication(self, **kwargs):
        self.issued += 1
        return {"challenge_id": "c1"}

    def complete_authentication(self, **kwargs):
        self.completed += 1
        return ("cred", "rp")


def _clock():
    return datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def test_webauthn_authentication_fails_closed_without_login_limiter() -> None:
    from dashboard.backend.account_v2.webauthn_authority import WebAuthnAuthority

    ceremonies = _Ceremonies()
    authority = WebAuthnAuthority(ceremonies)
    with pytest.raises(PermissionError, match="rate-limit"):
        authority.issue_authentication(user=_User(), rp_id="example")
    assert ceremonies.issued == 0


def test_locked_login_flow_blocks_webauthn_before_ceremony() -> None:
    from dashboard.backend.account_v2.webauthn_authority import WebAuthnAuthority

    ceremonies = _Ceremonies()
    limiter = _Limiter(locked=True)
    user = _User()
    authority = WebAuthnAuthority(ceremonies, rate_limiter=limiter, clock=_clock)
    with pytest.raises(PermissionError, match="rate-limit"):
        authority.issue_authentication(user=user, rp_id="example")
    assert ceremonies.issued == 0
    assert limiter.events[0][1]["flow"].value == "LOGIN"


def test_successful_webauthn_completion_resets_login_flow() -> None:
    from dashboard.backend.account_v2.webauthn_authority import WebAuthnAuthority

    ceremonies = _Ceremonies()
    limiter = _Limiter()
    user = _User()
    authority = WebAuthnAuthority(ceremonies, rate_limiter=limiter, clock=_clock)
    assert authority.complete_authentication(user=user, challenge_id="c1", response={}) == ("cred", "rp")
    assert [event for event, _ in limiter.events] == ["check", "success"]
