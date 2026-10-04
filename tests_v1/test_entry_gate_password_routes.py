"""Deferred-execution route tests for the canonical Owner/User password gate."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from dashboard.backend.account_v2.password_router import attach_password_account_routes
from dashboard.backend.domain import Lifecycle, Role, UserIdentity
from dashboard.backend.identity import persisted_identity
from dashboard.backend.api import create_app
from dashboard.backend.security import SecurityConfiguration
from dashboard.backend.security_store import SQLiteSecurityStore


class RecordingAudit:
    def __init__(self):
        self.events = []

    def record(self, **kwargs):
        self.events.append(kwargs)
        return f"audit-{len(self.events)}"


@pytest.fixture
def app_client(tmp_path):
    store = SQLiteSecurityStore(
        tmp_path / "security.sqlite3",
        seed_governance=False,
        profile="test",
    )
    bootstrap = store.create_bootstrap_token()["raw_token"]
    owner = store.initialize_owner_password(
        display_name="AlgoFortis Owner",
        email="owner@algofortis.internal",
        bootstrap_token=bootstrap,
        password="OwnerPassword123!",
    )
    audit = RecordingAudit()
    app = create_app(
        security_store=store,
        governance_store=store,
        owner=owner,
        config=SecurityConfiguration(normal_mtls_required=False),
        core_security_audit=audit,
    )
    attach_password_account_routes(app)
    try:
        yield TestClient(app), store, audit
    finally:
        store.close()


def _invite(store, *, email="user@example.com"):
    record, code = store.create_user_access(
        display_name="Password User",
        email=email,
        service_term_type="3_MONTHS",
        is_draft=False,
    )
    assert code
    return record, code


def _activate(client, record, code, *, email="user@example.com", password="UserPassword123!"):
    return client.post(
        "/api/v1/auth/password/activate",
        json={
            "identifier": record["sx_id"],
            "activation_code": code,
            "email": email,
            "password": password,
            "confirm_password": password,
        },
    )


def test_activation_requires_matching_passwords_without_mutation(app_client):
    client, store, _ = app_client
    record, code = _invite(store)
    res = client.post(
        "/api/v1/auth/password/activate",
        json={
            "identifier": record["sx_id"],
            "activation_code": code,
            "email": "user@example.com",
            "password": "UserPassword123!",
            "confirm_password": "DifferentPassword123!",
        },
    )
    assert res.status_code == 422
    row = store.get_user(record["user_id"])
    assert row["account_status"] == "PENDING"
    assert row["activation_status"] == "INVITED"
    assert row["password_hash"] is None


def test_successful_activation_returns_no_secrets_and_requires_sign_in(app_client):
    client, store, audit = app_client
    record, code = _invite(store)
    secret = "UserPassword123!"
    res = _activate(client, record, code, password=secret)
    assert res.status_code == 200
    assert res.json() == {"activated": True, "authentication_required": True}
    serialized = res.text.lower()
    assert "password" not in serialized
    assert "hash" not in serialized
    assert "salt" not in serialized
    assert all(secret not in str(event) for event in audit.events)
    assert all("password_hash" not in str(event).lower() for event in audit.events)
    assert all("salt" not in str(event).lower() for event in audit.events)
    assert all(code not in str(event) for event in audit.events)


def test_owner_and_user_login_share_endpoint_and_backend_role(app_client):
    client, store, _ = app_client
    record, code = _invite(store)
    assert _activate(client, record, code).status_code == 200

    owner_res = client.post(
        "/api/v1/auth/password/login",
        json={"identifier": "owner@algofortis.internal", "password": "OwnerPassword123!"},
    )
    user_res = client.post(
        "/api/v1/auth/password/login",
        json={"identifier": record["sx_id"], "password": "UserPassword123!"},
    )

    assert owner_res.status_code == 200
    assert owner_res.json()["role"] == "OWNER"
    assert owner_res.json()["workspace_eligibility"]["owner"] is True
    assert user_res.status_code == 200
    assert user_res.json()["role"] == "USER"
    assert user_res.json()["workspace_eligibility"]["user"] is True


def test_wrong_identifier_and_password_are_generic(app_client):
    client, _, _ = app_client
    bad_id = client.post(
        "/api/v1/auth/password/login",
        json={"identifier": "nobody@example.com", "password": "WrongPassword123!"},
    )
    bad_password = client.post(
        "/api/v1/auth/password/login",
        json={"identifier": "owner@algofortis.internal", "password": "WrongPassword123!"},
    )
    assert bad_id.status_code == 401
    assert bad_password.status_code == 401
    assert bad_id.json()["detail"] == "INVALID_ID_OR_PASSWORD"
    assert bad_password.json()["detail"] == "INVALID_ID_OR_PASSWORD"


def test_login_cooldown_tracks_ip_and_identifier(app_client):
    client, _, _ = app_client
    last = None
    for _ in range(5):
        last = client.post(
            "/api/v1/auth/password/login",
            json={"identifier": "owner@algofortis.internal", "password": "WrongPassword123!"},
        )
    assert last is not None
    assert last.status_code == 429
    assert "RATE_LIMIT_COOLDOWN" in last.json()["detail"]


def test_expired_user_entitlement_receives_no_workspace_session(app_client):
    client, store, _ = app_client
    record, code = _invite(store)
    assert _activate(client, record, code).status_code == 200
    with store._transaction() as cur:
        cur.execute(
            "UPDATE users SET service_status='EXPIRED', service_expires_at=? WHERE user_id=?",
            ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), record["user_id"]),
        )

    res = client.post(
        "/api/v1/auth/password/login",
        json={"identifier": record["sx_id"], "password": "UserPassword123!"},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "ACCOUNT_ACCESS_UNAVAILABLE"


def test_password_login_session_never_satisfies_fresh_step_up(app_client):
    client, store, _ = app_client
    res = client.post(
        "/api/v1/auth/password/login",
        json={"identifier": "owner@algofortis.internal", "password": "OwnerPassword123!"},
    )
    assert res.status_code == 200
    token = res.json()["access_token"]
    session_row = store.load_session(token)
    assert session_row is not None
    assert session_row["step_up_satisfied"] == 0
    assert res.json()["role"] == "OWNER"


def test_password_login_falls_back_to_configured_roaming_owner_authority(app_client):
    client, store, _ = app_client
    owner_row = store.find_user_by_identifier("OWNER-001")
    remote_owner = persisted_identity(owner_row)

    class FakeRoamingOwner:
        configured = True

        def authenticate_password(self, *, identifier: str, password: str):
            if identifier == "remote-owner@example.com" and password == "OwnerPassword123!":
                return remote_owner
            return None

    client.app.state.roaming_identity = FakeRoamingOwner()
    res = client.post(
        "/api/v1/auth/password/login",
        json={"identifier": "remote-owner@example.com", "password": "OwnerPassword123!"},
    )
    assert res.status_code == 200
    assert res.json()["role"] == "OWNER"
    assert res.json()["sx_id"] == "OWNER-001"


def test_remote_login_is_not_used_when_local_credentials_are_valid(app_client):
    client, _, _ = app_client

    class ExplodingRoaming:
        configured = True

        def authenticate_password(self, **_kwargs):
            raise AssertionError("remote authority must not run for valid local login")

    client.app.state.roaming_identity = ExplodingRoaming()
    res = client.post(
        "/api/v1/auth/password/login",
        json={"identifier": "OWNER-001", "password": "OwnerPassword123!"},
    )
    assert res.status_code == 200
    assert res.json()["role"] == "OWNER"
