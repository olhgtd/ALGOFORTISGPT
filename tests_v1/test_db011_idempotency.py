import unittest
import tempfile
import sqlite3
import json
import secrets
from pathlib import Path
from uuid import UUID, uuid4
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from dashboard.backend.security_store import (
    SQLiteSecurityStore,
    SecurityStoreError,
)
from dashboard.backend.core_audit import (
    MandatoryCoreSecurityAudit,
    OutboxStageState,
    AuditEvent,
    AuditEventFamily,
    AuditEventType,
    derive_audit_event_id,
    canonical_json_dumps,
    recorded_at_utc_now,
)
from dashboard.backend.domain import (
    UserIdentity,
    Role,
    Lifecycle,
    AccountAccessStatus,
    AccessRoute,
)
from dashboard.backend.api import create_app


class InMemoryAuditAuthority:
    def __init__(self):
        self.events = []
        self.should_fail = False

    def append_audit_events(self, events):
        if self.should_fail:
            raise RuntimeError("Simulated Core Audit write failure (authoritative append rejected)")
        self.events.extend(events)
        return tuple(events)


class TestDB011Idempotency(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tpath = Path(self.temp_dir.name)
        self.sec_db = self.tpath / "security.sqlite3"

        self.sec = SQLiteSecurityStore(self.sec_db, profile="test", seed_governance=False)
        self.audit_auth = InMemoryAuditAuthority()
        self.core_audit = MandatoryCoreSecurityAudit(audit_store=self.audit_auth, security_store=self.sec)

        # Create Owner
        self.owner_id = uuid4()
        self.owner = UserIdentity(
            user_id=self.owner_id,
            role=Role.OWNER,
            lifecycle=Lifecycle.ACTIVE,
            display_name="Test Owner",
            account_status=AccountAccessStatus.ACTIVE,
        )
        self.sec.ensure_user(
            user_id=self.owner_id,
            role="OWNER",
            lifecycle="ACTIVE",
            display_name="Test Owner",
            account_status="ACTIVE",
        )

        # Create App & TestClient
        self.app = create_app(
            owner=self.owner,
            security_store=self.sec,
            governance_store=None,
            core_security_audit=self.core_audit,
            artifact_root=self.tpath / "artifacts",
        )

        # Issue active session for Owner
        session = self.app.state.sessions.issue(
            user=self.owner,
            route=AccessRoute.NORMAL,
            mtls_verified=True,
            step_up_satisfied=True,
        )
        self.auth_headers = {"Authorization": f"Bearer {session.token}"}
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.sec.close()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_a_security_commit_and_audit_success(self):
        """A. Security commit + audit success -> 200, one-time code delivered, outbox VERIFIED_APPLIED."""
        payload = {
            "display_name": "Trader Alpha",
            "email": "alpha@example.com",
            "role": "USER",
            "plan": "Quant Professional",
            "service_term_type": "3_MONTHS",
        }
        res = self.client.post("/api/v1/owner/access/users", json=payload, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertTrue(data["activation_code"].startswith("SX-ACT-"))
        self.assertEqual(data["record"]["email"], "alpha@example.com")

        # Verify DB records
        row = self.sec._conn.execute("SELECT * FROM users WHERE bound_email = 'alpha@example.com'").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["account_status"], "PENDING")
        self.assertEqual(row["activation_status"], "INVITED")

        # Verify outbox state
        op_id = f"user-create-alpha@example.com"
        outbox = self.sec.get_outbox_record(op_id)
        self.assertIsNotNone(outbox)
        self.assertEqual(outbox["stage_state"], "VERIFIED_APPLIED")
        self.assertIsNotNone(outbox["applied_event_id"])

        # Verify Core Audit recorded event
        self.assertTrue(any(json.loads(e.payload_json).get("action") == "USER_ACCESS_CREATED" for e in self.audit_auth.events))

    def test_b_and_k_security_commit_audit_failure_no_false_200(self):
        """B & K. Security commit + audit failure -> HTTP 503, outbox COMMITTED_PENDING_AUDIT, no false 200."""
        self.audit_auth.should_fail = True

        payload = {
            "display_name": "Trader Beta",
            "email": "beta@example.com",
            "role": "USER",
        }
        res = self.client.post("/api/v1/owner/access/users", json=payload, headers=self.auth_headers)
        # Invariant K: no false 200 success when mandatory audit state is unresolved
        self.assertEqual(res.status_code, 503)
        self.assertIn("Mandatory security audit recording failed", res.json()["detail"])

        # Security user was committed
        row = self.sec._conn.execute("SELECT * FROM users WHERE bound_email = 'beta@example.com'").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["account_status"], "PENDING")
        self.assertEqual(row["activation_status"], "INVITED")

        # Outbox remains in COMMITTED_PENDING_AUDIT
        op_id = f"user-create-beta@example.com"
        outbox = self.sec.get_outbox_record(op_id)
        self.assertIsNotNone(outbox)
        self.assertEqual(outbox["stage_state"], "COMMITTED_PENDING_AUDIT")

    def test_c_d_e_f_retry_after_audit_failure(self):
        """C, D, E, F: Retry after B succeeds, same logical user, usable onboarding code, audit recorded."""
        # 1. First attempt fails on audit
        self.audit_auth.should_fail = True
        payload = {
            "display_name": "Trader Gamma",
            "email": "gamma@example.com",
            "role": "USER",
        }
        res1 = self.client.post("/api/v1/owner/access/users", json=payload, headers=self.auth_headers)
        self.assertEqual(res1.status_code, 503)

        first_user = self.sec._conn.execute("SELECT * FROM users WHERE bound_email = 'gamma@example.com'").fetchone()
        first_uid = first_user["user_id"]
        first_sx_id = first_user["sx_id"]

        # Check first issuance
        first_iss = self.sec._conn.execute("SELECT * FROM activation_issuances WHERE user_id = ?", (first_uid,)).fetchall()
        self.assertEqual(len(first_iss), 1)
        self.assertEqual(first_iss[0]["status"], "INVITED")

        # 2. Audit recovery: Core audit write authority restored
        self.audit_auth.should_fail = False

        # 3. Retry with same payload (C: retry after B)
        res2 = self.client.post("/api/v1/owner/access/users", json=payload, headers=self.auth_headers)
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        fresh_code = data2["activation_code"]
        self.assertTrue(fresh_code.startswith("SX-ACT-"))

        # D: same logical user remains one user
        user_count = self.sec._conn.execute("SELECT COUNT(*) as c FROM users WHERE bound_email = 'gamma@example.com'").fetchone()["c"]
        self.assertEqual(user_count, 1)
        current_user = self.sec._conn.execute("SELECT * FROM users WHERE bound_email = 'gamma@example.com'").fetchone()
        self.assertEqual(current_user["user_id"], first_uid)
        self.assertEqual(current_user["sx_id"], first_sx_id)

        # Verify old issuance marked EXPIRED and exactly one active INVITED issuance exists
        all_iss = self.sec._conn.execute("SELECT * FROM activation_issuances WHERE user_id = ? ORDER BY issued_at_utc ASC", (first_uid,)).fetchall()
        self.assertEqual(len(all_iss), 2)
        self.assertEqual(all_iss[0]["status"], "EXPIRED")
        self.assertEqual(all_iss[1]["status"], "INVITED")

        # E: Retry obtains a usable onboarding path (fresh code can be redeemed)
        now = datetime.now(timezone.utc)
        self.sec.redeem_activation(
            user_id=UUID(first_uid),
            code=fresh_code,
            challenge_id="ch-test-001",
            rp_id="localhost",
            origin="https://localhost",
            ceremony_state="{}",
            expires_at=now + timedelta(minutes=5),
        )
        redeemed_user = self.sec._conn.execute("SELECT * FROM users WHERE user_id = ?", (first_uid,)).fetchone()
        self.assertEqual(redeemed_user["activation_status"], "REDEEMED")

        # F: missing audit is recorded and outbox verified applied
        op_id = f"user-create-gamma@example.com"
        outbox = self.sec.get_outbox_record(op_id)
        self.assertEqual(outbox["stage_state"], "VERIFIED_APPLIED")
        self.assertTrue(any(json.loads(e.payload_json).get("action") == "USER_ACCESS_CREATED" for e in self.audit_auth.events))

    def test_g_repeated_identical_retry_remains_idempotent(self):
        """G. Repeated identical retries while pending remain idempotent with one user row."""
        payload = {"display_name": "Trader Delta", "email": "delta@example.com", "role": "USER"}

        # Attempt 1 (audit fails)
        self.audit_auth.should_fail = True
        r1 = self.client.post("/api/v1/owner/access/users", json=payload, headers=self.auth_headers)
        self.assertEqual(r1.status_code, 503)

        # Attempt 2 (audit succeeds)
        self.audit_auth.should_fail = False
        r2 = self.client.post("/api/v1/owner/access/users", json=payload, headers=self.auth_headers)
        self.assertEqual(r2.status_code, 200)
        code2 = r2.json()["activation_code"]

        # Attempt 3 (repeated retry while still pending)
        r3 = self.client.post("/api/v1/owner/access/users", json=payload, headers=self.auth_headers)
        self.assertEqual(r3.status_code, 200)
        code3 = r3.json()["activation_code"]

        # Confirm exactly 1 user row
        user_rows = self.sec._conn.execute("SELECT * FROM users WHERE bound_email = 'delta@example.com'").fetchall()
        self.assertEqual(len(user_rows), 1)

        # Confirm exactly 1 active (INVITED) issuance
        active_issuances = self.sec._conn.execute(
            "SELECT * FROM activation_issuances WHERE user_id = ? AND status = 'INVITED'",
            (user_rows[0]["user_id"],),
        ).fetchall()
        self.assertEqual(len(active_issuances), 1)

    def test_h_concurrent_duplicate_requests_create_one_identity(self):
        """H. Concurrent duplicate requests converge to create exactly one identity."""
        email = "concurrent@example.com"
        results = []

        def create_user():
            try:
                rec, code = self.sec.create_user_access(
                    display_name="Concurrent User",
                    email=email,
                    role="USER",
                    allow_idempotent_onboarding=True,
                )
                return ("OK", rec["user_id"])
            except Exception as e:
                return ("ERR", str(e))

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(create_user) for _ in range(8)]
            results = [f.result() for f in futures]

        # Verify all converged to OK
        success_uids = {uid for status, uid in results if status == "OK"}
        self.assertEqual(len(success_uids), 1, f"Expected 1 unique user_id, got: {success_uids}")

        # Verify in DB: exactly 1 user
        count = self.sec._conn.execute("SELECT COUNT(*) as c FROM users WHERE bound_email = ?", (email,)).fetchone()["c"]
        self.assertEqual(count, 1)

        # Verify exactly 1 active issuance
        user_id = list(success_uids)[0]
        active_count = self.sec._conn.execute(
            "SELECT COUNT(*) as c FROM activation_issuances WHERE user_id = ? AND status = 'INVITED'",
            (user_id,),
        ).fetchone()["c"]
        self.assertEqual(active_count, 1)

    def test_i_activation_code_security_storage_remains_one_way(self):
        """I. Plaintext activation code is NEVER stored in database tables."""
        payload = {"display_name": "Trader Epsilon", "email": "epsilon@example.com", "role": "USER"}
        res = self.client.post("/api/v1/owner/access/users", json=payload, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        plain_code = res.json()["activation_code"]

        # Check activation_issuances table
        rows = self.sec._conn.execute("SELECT * FROM activation_issuances").fetchall()
        for r in rows:
            self.assertNotEqual(r["code_hash"], plain_code)
            self.assertEqual(len(r["code_hash"]), 64)  # SHA256 hex digest length

        # Check all tables for plaintext code leakage
        tables = ["users", "activation_issuances", "security_mutation_outbox"]
        for tbl in tables:
            rows = self.sec._conn.execute(f"SELECT * FROM {tbl}").fetchall()
            for row in rows:
                for val in dict(row).values():
                    if isinstance(val, str):
                        self.assertNotIn(plain_code, val, f"Plaintext code leaked in table {tbl} column value {val}")

    def test_j_db003_uniqueness_protections_remain_active_for_registered_user(self):
        """J. DB-003 uniqueness protections remain active: once user is ACTIVE, creation returns 422."""
        # 1. Create user
        payload = {"display_name": "Trader Zeta", "email": "zeta@example.com", "role": "USER"}
        res = self.client.post("/api/v1/owner/access/users", json=payload, headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        uid = res.json()["record"]["user_id"]

        # 2. Simulate user becoming ACTIVE (onboarding completed, credential added)
        with self.sec._transaction() as cur:
            cur.execute("UPDATE users SET account_status = 'ACTIVE', activation_status = 'REDEEMED' WHERE user_id = ?", (uid,))
            cur.execute("""INSERT INTO webauthn_credentials (credential_id, user_id, rp_id, credential_data, sign_count, label, is_backup_hardware, enabled, revoked, created_at_utc)
                           VALUES (?, ?, 'localhost', x'1234', 1, 'Key', 0, 1, 0, '2026-09-15T00:00:00Z')""", (b"cred-1234", uid))

        # 3. Attempt to call create_user_access again for the active user
        res2 = self.client.post("/api/v1/owner/access/users", json=payload, headers=self.auth_headers)
        self.assertEqual(res2.status_code, 422)
        self.assertIn("already exists", res2.json()["detail"])

        # Verify direct call to security_store also raises
        with self.assertRaises(SecurityStoreError) as ctx:
            self.sec.create_user_access(
                display_name="Trader Zeta",
                email="zeta@example.com",
                role="USER",
                allow_idempotent_onboarding=True,
            )
        self.assertIn("already exists", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
