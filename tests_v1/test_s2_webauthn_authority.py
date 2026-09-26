from __future__ import annotations

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
