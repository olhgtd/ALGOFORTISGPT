import tempfile
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from dashboard.backend.account_v2.password_router import attach_password_account_routes
from dashboard.backend.api import create_app
from dashboard.backend.domain import Lifecycle, Role, UserIdentity
from dashboard.backend.security import SecurityConfiguration
from dashboard.backend.security_store import SQLiteSecurityStore


class RecordingAudit:
    def __init__(self):
        self.events = []

    def record(self, **kwargs):
        self.events.append(kwargs)
        return f"audit-{len(self.events)}"


def _client():
    temp = tempfile.TemporaryDirectory(prefix="af_owner_entry_recovery_")
    store = SQLiteSecurityStore(Path(temp.name) / "security.sqlite3", seed_governance=False, profile="test")
    owner = UserIdentity(
        user_id=uuid.uuid4(),
        role=Role.OWNER,
        lifecycle=Lifecycle.ACTIVE,
        display_name="Pending Owner",
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
    return temp, store, TestClient(app)


def test_first_owner_setup_returns_eight_single_use_recovery_codes_and_reset_works():
    temp, store, client = _client()
    try:
        bootstrap = store.create_bootstrap_token()["raw_token"]
        setup = client.post(
            "/api/v1/auth/local/setup",
            json={
                "display_name": "AlgoFortis Owner",
                "email": "owner@test.invalid",
                "bootstrap_token": bootstrap,
                "password": "OwnerPass123!",
                "confirm_password": "OwnerPass123!",
            },
        )
        assert setup.status_code == 200, setup.text
        body = setup.json()
        assert body["role"] == "OWNER"
        assert len(body["recovery_codes"]) == 8
        assert len(set(body["recovery_codes"])) == 8
        assert all(code.startswith("RC-") for code in body["recovery_codes"])

        stored = store._conn.execute(
            "SELECT code_hash, consumed_at_utc FROM recovery_codes WHERE user_id = ?",
            (body["subject"],),
        ).fetchall()
        assert len(stored) == 8
        assert all(row["consumed_at_utc"] is None for row in stored)
        assert all(code not in {row["code_hash"] for row in stored} for code in body["recovery_codes"])

        code = body["recovery_codes"][0]
        verify = client.post(
            "/api/v1/auth/local/recovery/verify",
            json={"email": "owner@test.invalid", "recovery_code": code},
        )
        assert verify.status_code == 200, verify.text
        assert verify.json() == {"valid": True}

        reset = client.post(
            "/api/v1/auth/local/recovery/reset",
            json={
                "email": "owner@test.invalid",
                "recovery_code": code,
                "new_password": "NewOwnerPass456!",
                "confirm_password": "NewOwnerPass456!",
            },
        )
        assert reset.status_code == 200, reset.text
        assert reset.json()["success"] is True

        replay = client.post(
            "/api/v1/auth/local/recovery/verify",
            json={"email": "owner@test.invalid", "recovery_code": code},
        )
        assert replay.status_code == 400

        old_login = client.post(
            "/api/v1/auth/local/login",
            json={"email": "owner@test.invalid", "password": "OwnerPass123!"},
        )
        assert old_login.status_code == 401

        new_login = client.post(
            "/api/v1/auth/local/login",
            json={"email": "owner@test.invalid", "password": "NewOwnerPass456!"},
        )
        assert new_login.status_code == 200, new_login.text
        assert new_login.json()["role"] == "OWNER"
    finally:
        store.close()
        temp.cleanup()
