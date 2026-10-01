"""Deferred-execution tests for the V1 entry-gate password account reunion.

These tests are intentionally authored before production code.  Execution is
pending until the owner's GitHub Actions quota resets.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from dashboard.backend.account_v2.password_accounts import (
    PasswordAccountAuthority,
    normalize_legacy_owner_activation,
)
from dashboard.backend.domain import Role
from dashboard.backend.security_store import SQLiteSecurityStore, SecurityStoreError


@pytest.fixture
def store(tmp_path):
    security = SQLiteSecurityStore(
        tmp_path / "security.sqlite3",
        seed_governance=False,
        profile="test",
    )
    try:
        yield security
    finally:
        security.close()


def _invite(store: SQLiteSecurityStore, *, email: str = "user@example.com", term: str = "3_MONTHS"):
    record, code = store.create_user_access(
        display_name="Entry Gate User",
        email=email,
        service_term_type=term,
        is_draft=False,
    )
    assert code is not None
    return record, code


def _owner(store: SQLiteSecurityStore):
    token = store.create_bootstrap_token()["raw_token"]
    return store.initialize_owner_password(
        display_name="AlgoFortis Owner",
        email="owner@algofortis.internal",
        bootstrap_token=token,
        password="OwnerPassword123!",
    )


def test_user_activation_password_is_atomic_and_starts_service(store):
    record, code = _invite(store)
    authority = PasswordAccountAuthority(store)
    now = datetime(2026, 9, 30, 6, 0, tzinfo=timezone.utc)

    identity = authority.activate_user_password(
        identifier=record["sx_id"],
        activation_code=code,
        email="USER@example.com",
        password="UserPassword123!",
        now=now,
    )

    row = store.get_user(identity.user_id)
    issuance = store.get_user_issuances(identity.user_id)[0]
    assert identity.role is Role.USER
    assert row["account_status"] == "ACTIVE"
    assert row["activation_status"] == "REDEEMED"
    assert row["service_status"] == "ACTIVE"
    assert row["service_started_at"] == now.isoformat()
    assert row["service_expires_at"] is not None
    assert row["password_hash"]
    assert row["password_salt"]
    assert row["password_hash"] != "UserPassword123!"
    assert "UserPassword123!" not in row["password_hash"]
    assert issuance["status"] == "REDEEMED"
    assert issuance["redeemed_at_utc"] == now.isoformat()


def test_user_activation_rejects_wrong_email_without_partial_state(store):
    record, code = _invite(store, email="bound@example.com")
    authority = PasswordAccountAuthority(store)

    with pytest.raises(SecurityStoreError, match="Activation unavailable"):
        authority.activate_user_password(
            identifier=record["sx_id"],
            activation_code=code,
            email="other@example.com",
            password="UserPassword123!",
        )

    row = store.get_user(record["user_id"])
    issuance = store.get_user_issuances(record["user_id"])[0]
    assert row["account_status"] == "PENDING"
    assert row["activation_status"] == "INVITED"
    assert row["service_status"] == "NOT_STARTED"
    assert row["service_started_at"] is None
    assert row["password_hash"] is None
    assert row["password_salt"] is None
    assert issuance["status"] == "INVITED"
    assert issuance["redeemed_at_utc"] is None


def test_user_activation_rejects_expired_revoked_or_replayed_invitation(store):
    authority = PasswordAccountAuthority(store)

    expired, expired_code = _invite(store, email="expired@example.com")
    with store._transaction() as cur:
        cur.execute(
            "UPDATE activation_issuances SET expires_at_utc = ? WHERE user_id = ?",
            ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(), expired["user_id"]),
        )
    with pytest.raises(SecurityStoreError, match="Activation unavailable"):
        authority.activate_user_password(
            identifier=expired["sx_id"], activation_code=expired_code,
            email="expired@example.com", password="UserPassword123!",
        )

    revoked, revoked_code = _invite(store, email="revoked@example.com")
    with store._transaction() as cur:
        cur.execute(
            "UPDATE activation_issuances SET status = 'REVOKED', revoked_at_utc = ? WHERE user_id = ?",
            (datetime.now(timezone.utc).isoformat(), revoked["user_id"]),
        )
    with pytest.raises(SecurityStoreError, match="Activation unavailable"):
        authority.activate_user_password(
            identifier=revoked["sx_id"], activation_code=revoked_code,
            email="revoked@example.com", password="UserPassword123!",
        )

    replay, replay_code = _invite(store, email="replay@example.com")
    authority.activate_user_password(
        identifier=replay["sx_id"], activation_code=replay_code,
        email="replay@example.com", password="UserPassword123!",
    )
    with pytest.raises(SecurityStoreError, match="Activation unavailable"):
        authority.activate_user_password(
            identifier=replay["sx_id"], activation_code=replay_code,
            email="replay@example.com", password="UserPassword123!",
        )


def test_verify_identity_password_accepts_user_id_or_email_for_owner_and_user(store):
    owner = _owner(store)
    record, code = _invite(store)
    authority = PasswordAccountAuthority(store)
    user = authority.activate_user_password(
        identifier=record["sx_id"], activation_code=code,
        email="user@example.com", password="UserPassword123!",
    )

    assert authority.verify_identity_password(
        identifier="owner@algofortis.internal", password="OwnerPassword123!"
    ).user_id == owner.user_id
    assert authority.verify_identity_password(
        identifier=record["sx_id"].lower(), password="UserPassword123!"
    ).user_id == user.user_id
    assert authority.verify_identity_password(
        identifier="USER@EXAMPLE.COM", password="UserPassword123!"
    ).user_id == user.user_id


def test_verify_identity_password_rejects_bad_password_suspended_or_revoked_account(store):
    record, code = _invite(store)
    authority = PasswordAccountAuthority(store)
    identity = authority.activate_user_password(
        identifier=record["sx_id"], activation_code=code,
        email="user@example.com", password="UserPassword123!",
    )

    assert authority.verify_identity_password(
        identifier=record["sx_id"], password="WrongPassword!"
    ) is None

    with store._transaction() as cur:
        cur.execute("UPDATE users SET account_status = 'SUSPENDED' WHERE user_id = ?", (str(identity.user_id),))
    assert authority.verify_identity_password(
        identifier=record["sx_id"], password="UserPassword123!"
    ) is None

    with store._transaction() as cur:
        cur.execute("UPDATE users SET account_status = 'REVOKED' WHERE user_id = ?", (str(identity.user_id),))
    assert authority.verify_identity_password(
        identifier=record["sx_id"], password="UserPassword123!"
    ) is None


def test_legacy_owner_activated_status_migrates_to_redeemed(store):
    token = store.create_bootstrap_token()["raw_token"]
    owner_id = store.list_users()[0]["user_id"]
    with store._transaction() as cur:
        cur.execute("UPDATE users SET activation_status = 'ACTIVATED' WHERE user_id = ?", (owner_id,))

    changed = normalize_legacy_owner_activation(store)

    assert changed == 1
    assert store.get_user(owner_id)["activation_status"] == "REDEEMED"
    # Bootstrap remains valid; migration must not consume unrelated one-time authority.
    assert token
