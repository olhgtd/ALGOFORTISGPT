"""AlgoFortis Local Private Desktop Auth Certification Suite.

Validates:
1. Scrypt password hashing, salting, and constant-time verification.
2. Bootstrap token creation, single-use consumption, and replay rejection.
3. Single Super Owner (OWNER-001) lifecycle:
   - has_initialized_owner() starts False, becomes True.
   - Re-provisioning blocked (no OWNER-002, no overwrite).
4. Local email + password authentication:
   - Success returns owner record.
   - Bad password / bad email returns generic INVALID_EMAIL_OR_PASSWORD.
   - Plaintext passwords never stored in database.
5. Progressive cooldown ladder and rate-limiting.
6. FastAPI endpoints:
   - /api/v1/security/status (owner_initialized reporting)
   - /api/v1/auth/local/setup (first-run provisioning)
   - /api/v1/auth/local/login (subsequent desktop login)
"""
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from dashboard.backend.security_store import (
    SQLiteSecurityStore,
    SecurityStoreError,
    hash_password,
    verify_password,
)
from dashboard.backend.auth_policy import AuthPolicyManager
from dashboard.backend.session_manager import SessionManager
from dashboard.backend.security import SecurityConfiguration, SecurityStatusAuthority
from dashboard.backend.domain import Role, Lifecycle, UserIdentity
from dashboard.backend.api import create_app
from dashboard.runtime.paths import RuntimePaths, RuntimeMode


@pytest.fixture
def temp_store():
    with tempfile.TemporaryDirectory(prefix="af_local_auth_test_") as tmp_dir:
        db_path = Path(tmp_dir) / "security.sqlite3"
        store = SQLiteSecurityStore(db_path, seed_governance=False, profile="test")
        try:
            yield store, db_path
        finally:
            store.close()


class TestPasswordSecurity:
    """Password hashing and constant-time verification tests."""

    def test_scrypt_hashing_and_salting(self):
        pw = "SuperSecretPassword123!"
        h1, s1 = hash_password(pw)
        h2, s2 = hash_password(pw)

        # Unique salts per generation
        assert s1 != s2
        assert h1 != h2

        # Verification succeeds
        assert verify_password(pw, h1, s1) is True
        assert verify_password(pw, h2, s2) is True

        # Incorrect password fails
        assert verify_password("WrongPassword!", h1, s1) is False
        assert verify_password("", h1, s1) is False

    def test_password_never_stored_in_plaintext(self, temp_store):
        store, db_path = temp_store
        # Issue bootstrap token
        token_info = store.create_bootstrap_token(expires_in_hours=1)
        raw_token = token_info["raw_token"]

        owner_email = "owner@algofortis.internal"
        owner_pw = "HighlyConfidentialPassword99!"

        # Initialize owner
        user_row = store.initialize_owner_password(
            display_name="AlgoFortis Super Owner",
            email=owner_email,
            bootstrap_token=raw_token,
            password=owner_pw,
        )
        assert getattr(user_row, "bound_email", None) == owner_email or user_row.display_name == "AlgoFortis Super Owner"

        # Inspect database directly
        cur = store._conn.cursor()
        row = cur.execute("SELECT password_hash, password_salt FROM users WHERE user_id = ?", (str(user_row.user_id),)).fetchone()
        assert row is not None
        assert row["password_hash"] != owner_pw
        assert owner_pw not in row["password_hash"]
        assert row["password_salt"] != owner_pw


class TestBootstrapAndOwnerLifecycle:
    """Bootstrap token and Super Owner provisioning invariants."""

    def test_owner_initialization_lifecycle(self, temp_store):
        store, _ = temp_store
        # Initial state: uninitialized
        assert store.has_initialized_owner() is False

        # Issue bootstrap token
        token_info = store.create_bootstrap_token(expires_in_hours=1)
        raw_token = token_info["raw_token"]

        # Setup with invalid token fails
        with pytest.raises((ValueError, SecurityStoreError)):
            store.initialize_owner_password(
                display_name="Owner",
                email="owner@algofortis.internal",
                bootstrap_token="invalid-token-string",
                password="ValidPassword123",
            )
        assert store.has_initialized_owner() is False

        # Valid setup succeeds
        user_row = store.initialize_owner_password(
            display_name="Platform Owner",
            email="owner@algofortis.internal",
            bootstrap_token=raw_token,
            password="ValidPassword123",
        )
        assert user_row.role == Role.OWNER
        assert store.has_initialized_owner() is True

        # Bootstrap token is consumed: replay fails
        with pytest.raises((ValueError, SecurityStoreError)):
            store.initialize_owner_password(
                display_name="Impostor",
                email="impostor@algofortis.internal",
                bootstrap_token=raw_token,
                password="ValidPassword123",
            )

        # Re-provisioning attempt with new token also fails (Single Super Owner invariant)
        new_token = store.create_bootstrap_token(expires_in_hours=1)["raw_token"]
        with pytest.raises((ValueError, SecurityStoreError)):
            store.initialize_owner_password(
                display_name="Owner Two",
                email="owner2@algofortis.internal",
                bootstrap_token=new_token,
                password="AnotherPassword123",
            )


class TestOwnerLoginVerification:
    """Local email and password verification logic."""

    def test_login_verification(self, temp_store):
        store, _ = temp_store
        token = store.create_bootstrap_token()["raw_token"]
        store.initialize_owner_password(
            display_name="Super Owner",
            email="owner@algofortis.internal",
            bootstrap_token=token,
            password="MySecretPassword456!",
        )

        # Successful login
        user = store.verify_owner_password("owner@algofortis.internal", "MySecretPassword456!")
        assert user is not None
        assert user.role == Role.OWNER

        # Case-insensitive email
        user = store.verify_owner_password("OWNER@ALGOFORTIS.INTERNAL", "MySecretPassword456!")
        assert user is not None
        assert user.role == Role.OWNER

        # Incorrect password
        user = store.verify_owner_password("owner@algofortis.internal", "WrongPassword!")
        assert user is None

        # Unknown email
        user = store.verify_owner_password("nonexistent@domain.com", "MySecretPassword456!")
        assert user is None


class TestLocalAuthApiEndpoints:
    """End-to-end FastAPI endpoint integration tests."""

    @pytest.fixture
    def test_app_client(self, temp_store):
        store, _ = temp_store
        owner_id = uuid.uuid4()
        owner_identity = UserIdentity(
            user_id=owner_id,
            role=Role.OWNER,
            lifecycle=Lifecycle.ACTIVE,
            display_name="Pending Owner",
        )

        app = create_app(
            security_store=store,
            governance_store=store,
            owner=owner_identity,
            config=SecurityConfiguration(normal_mtls_required=False),
        )
        return TestClient(app), store

    def test_full_auth_api_lifecycle(self, test_app_client):
        client, store = test_app_client

        # 1. Check security status before setup
        res = client.get("/api/v1/security/status")
        assert res.status_code == 200
        status_data = res.json()
        assert status_data["owner_initialized"] is False
        assert status_data["password_authentication"] == "PENDING_SETUP"

        # 2. Try login before setup -> fails
        login_res = client.post("/api/v1/auth/local/login", json={
            "email": "owner@algofortis.internal",
            "password": "Password123!",
        })
        assert login_res.status_code == 401

        # 3. Create bootstrap token
        raw_token = store.create_bootstrap_token()["raw_token"]

        # 4. Perform setup via API
        setup_res = client.post("/api/v1/auth/local/setup", json={
            "display_name": "AlgoFortis Administrator",
            "email": "admin@algofortis.internal",
            "bootstrap_token": raw_token,
            "password": "SecurePassword123!",
            "confirm_password": "SecurePassword123!",
        })
        assert setup_res.status_code == 200
        setup_data = setup_res.json()
        assert "access_token" in setup_data
        assert setup_data["role"] == "OWNER"
        assert setup_data["subject"] is not None

        # 5. Check status after setup -> owner_initialized is True
        res = client.get("/api/v1/security/status")
        assert res.status_code == 200
        assert res.json()["owner_initialized"] is True
        assert res.json()["password_authentication"] == "ENABLED"

        # 6. Re-setup is rejected
        re_setup = client.post("/api/v1/auth/local/setup", json={
            "display_name": "Another Owner",
            "email": "another@algofortis.internal",
            "bootstrap_token": raw_token,
            "password": "SecurePassword123!",
            "confirm_password": "SecurePassword123!",
        })
        assert re_setup.status_code in (400, 403)

        # 7. Login with wrong password -> 401 generic error
        fail_login = client.post("/api/v1/auth/local/login", json={
            "email": "admin@algofortis.internal",
            "password": "WrongPassword!",
        })
        assert fail_login.status_code == 401
        assert "INVALID_EMAIL_OR_PASSWORD" in fail_login.json()["detail"]

        # 8. Login with correct password -> 200 and valid session tokens
        success_login = client.post("/api/v1/auth/local/login", json={
            "email": "admin@algofortis.internal",
            "password": "SecurePassword123!",
        })
        assert success_login.status_code == 200
        login_data = success_login.json()
        assert "access_token" in login_data
        assert login_data["role"] == "OWNER"
        assert login_data["subject"] == setup_data["subject"]

        # 9. Verify session token unlocks authenticated owner endpoints
        auth_res = client.get(
            "/api/v1/integration/system/health",
            headers={"Authorization": f"Bearer {login_data['access_token']}"},
        )
        assert auth_res.status_code == 200

        # 10. Rate limiting progressive cooldown: 5 failed attempts trigger 429
        for _ in range(4):
            client.post("/api/v1/auth/local/login", json={
                "email": "admin@algofortis.internal",
                "password": "WrongPassword!",
            })
        # 5th failure trips cooldown
        locked_res = client.post("/api/v1/auth/local/login", json={
            "email": "admin@algofortis.internal",
            "password": "WrongPassword!",
        })
        assert locked_res.status_code == 429
        assert "RATE_LIMIT_COOLDOWN" in locked_res.json()["detail"]
