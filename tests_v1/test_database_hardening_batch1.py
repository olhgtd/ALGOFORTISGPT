"""AlgoFortis V1 — Database Hardening Batch 1 Test Suite (DB-001, DB-002, DB-003)
Tests:
- DB-001: One-time visibility migration and restart immutability
- DB-002: Safe draft user deletion, dependent lifecycle cleanup, and fail-closed retention
- DB-003: Duplicate email and SX-ID prevention (case-insensitive, whitespace, race safety)
"""
import tempfile
import sqlite3
import unittest
from pathlib import Path
from uuid import uuid4

from dashboard.backend.security_store import SQLiteSecurityStore, SecurityStoreError
from dashboard.backend.sqlite_access import SerializedConnection


class TestDatabaseHardeningBatch1(unittest.TestCase):

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._temp_dir.name)

    def tearDown(self):
        self._temp_dir.cleanup()

    # ==================================================================
    # DB-001: STARTUP VISIBILITY MIGRATION TESTS
    # ==================================================================

    def test_db001_fresh_schema_migration_normalizes_visibility(self):
        """1. Fresh schema migration adds the column and performs intended one-time normalization."""
        db_path = self.tmp_dir / "fresh_migration.sqlite3"
        
        # Manually create pre-Phase-B owner_strategies table WITHOUT visibility column
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE security_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO security_metadata VALUES ('schema_version', '2')")
        conn.execute("INSERT INTO security_metadata VALUES ('live_global_hold', 'true')")
        conn.execute("""CREATE TABLE users (
            user_id TEXT PRIMARY KEY, role TEXT NOT NULL, lifecycle TEXT NOT NULL,
            display_name TEXT NOT NULL, created_at_utc TEXT NOT NULL, security_state TEXT NOT NULL
        )""")
        # Insert one OWNER and one USER
        conn.execute("INSERT INTO users VALUES ('owner-1', 'OWNER', 'ACTIVE', 'Admin', '2026-01-01T00:00:00Z', 'ACTIVE')")
        conn.execute("INSERT INTO users VALUES ('user-1', 'USER', 'ACTIVE', 'Client', '2026-01-01T00:00:00Z', 'ACTIVE')")

        # owner_strategies WITHOUT visibility column
        conn.execute("""CREATE TABLE owner_strategies (
            strategy_id TEXT PRIMARY KEY, id TEXT NOT NULL, name TEXT NOT NULL,
            version TEXT NOT NULL, stage TEXT NOT NULL, author TEXT NOT NULL, updated_at_utc TEXT NOT NULL
        )""")
        conn.execute("INSERT INTO owner_strategies VALUES ('s1', 's1', 'Owner Strat', '1.0', 'PAPER', 'owner-1', '2026-01-01T00:00:00Z')")
        conn.execute("INSERT INTO owner_strategies VALUES ('s2', 's2', 'User Strat', '1.0', 'PAPER', 'user-1', '2026-01-01T00:00:00Z')")
        conn.execute("INSERT INTO owner_strategies VALUES ('s3', 's3', 'Legacy Strat', '1.0', 'PAPER', 'unknown-author', '2026-01-01T00:00:00Z')")
        conn.commit()
        conn.close()

        # Open store -> triggers _bootstrap migration
        store = SQLiteSecurityStore(db_path, profile="test", seed_governance=False)
        try:
            rows = {r["strategy_id"]: r["visibility"] for r in store._conn.execute("SELECT strategy_id, visibility FROM owner_strategies").fetchall()}
            # Owner strategy defaults to OWNER_PRIVATE
            self.assertEqual(rows["s1"], "OWNER_PRIVATE")
            # User strategy normalized to PRIVATE
            self.assertEqual(rows["s2"], "PRIVATE")
            # Unlinked/legacy author normalized to GLOBAL
            self.assertEqual(rows["s3"], "GLOBAL")
        finally:
            store.close()

    def test_db001_existing_schema_preserves_custom_visibility_across_restart(self):
        """2. Existing schema with visibility already present preserves custom visibility values exactly across restart."""
        db_path = self.tmp_dir / "restart_preservation.sqlite3"
        store1 = SQLiteSecurityStore(db_path, profile="test", seed_governance=False)

        with store1._transaction() as cur:
            cur.execute("INSERT INTO users VALUES ('user-1', 'USER', 'ACTIVE', 'Client', '2026-01-01T00:00:00Z', 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'user@test.com', NULL, NULL, NULL, NULL)")
            cur.execute("""INSERT INTO owner_strategies (
                strategy_id, id, name, version, stage, author, visibility, updated_at_utc
            ) VALUES ('s-custom', 's-custom', 'Custom Visibility Strat', '1.0', 'PAPER', 'user-1', 'GLOBAL', '2026-01-01T00:00:00Z')""")

        # Confirm it is currently GLOBAL
        v_before = store1._conn.execute("SELECT visibility FROM owner_strategies WHERE strategy_id = 's-custom'").fetchone()[0]
        self.assertEqual(v_before, "GLOBAL")
        store1.close()

        # RESTART store 2 against the exact same database
        store2 = SQLiteSecurityStore(db_path, profile="test", seed_governance=False)
        try:
            v_after = store2._conn.execute("SELECT visibility FROM owner_strategies WHERE strategy_id = 's-custom'").fetchone()[0]
            # Must remain GLOBAL, NOT reset to PRIVATE!
            self.assertEqual(v_after, "GLOBAL")
        finally:
            store2.close()

    def test_db001_starting_store_twice_causes_no_mutations(self):
        """3. Starting SQLiteSecurityStore twice causes no additional visibility mutations."""
        db_path = self.tmp_dir / "double_start.sqlite3"
        store1 = SQLiteSecurityStore(db_path, profile="test", seed_governance=False)

        with store1._transaction() as cur:
            cur.execute("INSERT INTO users VALUES ('user-a', 'USER', 'ACTIVE', 'Alice', '2026-01-01T00:00:00Z', 'ACTIVE', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'alice@test.com', NULL, NULL, NULL, NULL)")
            cur.execute("""INSERT INTO owner_strategies (
                strategy_id, id, name, version, stage, author, visibility, updated_at_utc
            ) VALUES ('strat-a', 'strat-a', 'Alice Strat', '1.0', 'PAPER', 'user-a', 'GLOBAL', '2026-01-01T00:00:00Z')""")
        store1.close()

        # Re-open store multiple times
        for _ in range(3):
            st = SQLiteSecurityStore(db_path, profile="test", seed_governance=False)
            val = st._conn.execute("SELECT visibility FROM owner_strategies WHERE strategy_id = 'strat-a'").fetchone()[0]
            self.assertEqual(val, "GLOBAL")
            st.close()

    # ==================================================================
    # DB-002: SAFE DRAFT USER DELETE TESTS
    # ==================================================================

    def test_db002_empty_draft_user_delete_succeeds(self):
        """Empty draft user delete succeeds."""
        db_path = self.tmp_dir / "empty_draft.sqlite3"
        store = SQLiteSecurityStore(db_path, profile="test", seed_governance=False)
        try:
            u, _ = store.create_user_access(display_name="Draft User", email="draft@example.com", is_draft=True)
            uid = u["user_id"]
            self.assertIsNotNone(store.get_user(uid))

            deleted = store.delete_draft_user(uid)
            self.assertTrue(deleted)
            self.assertIsNone(store.get_user(uid))
        finally:
            store.close()

    def test_db002_draft_user_with_activation_issuance_delete_succeeds(self):
        """Draft user with unredeemed activation issuance deletes both user and issuances cleanly."""
        db_path = self.tmp_dir / "issuance_draft.sqlite3"
        store = SQLiteSecurityStore(db_path, profile="test", seed_governance=False)
        try:
            u, _ = store.create_user_access(display_name="Draft User", email="draft2@example.com", is_draft=True)
            uid = u["user_id"]
            # Reissue an activation code invitation
            store.reissue_activation_code(uid)
            issuances = store.get_user_issuances(uid)
            self.assertTrue(len(issuances) >= 1)

            # Delete draft user
            # Reset activation status to DRAFT for deletion test if reissue set to INVITED
            with store._transaction() as cur:
                cur.execute("UPDATE users SET activation_status = 'DRAFT' WHERE user_id = ?", (uid,))

            deleted = store.delete_draft_user(uid)
            self.assertTrue(deleted)
            self.assertIsNone(store.get_user(uid))
            # Verify issuances are also cleaned up
            remaining_iss = store.get_user_issuances(uid)
            self.assertEqual(len(remaining_iss), 0)
        finally:
            store.close()

    def test_db002_draft_user_with_strategy_assignment_delete_succeeds(self):
        """Draft user with strategy assignment deletes assignment and user cleanly."""
        db_path = self.tmp_dir / "assign_draft.sqlite3"
        store = SQLiteSecurityStore(db_path, profile="test", seed_governance=False)
        try:
            u, _ = store.create_user_access(display_name="Draft User", email="draft3@example.com", is_draft=True)
            uid = u["user_id"]
            with store._transaction() as cur:
                cur.execute("""INSERT INTO owner_strategies (
                    strategy_id, id, name, version, stage, author, updated_at_utc
                ) VALUES ('s-test', 's-test', 'Test Strat', '1.0', 'PAPER', 'OWNER-001', '2026-01-01T00:00:00Z')""")

            store.assign_strategy_to_user(user_id=uid, strategy_id="s-test", actor="OWNER-001")
            self.assertIsNotNone(store.get_strategy_assignment(uid, "s-test"))

            # Delete draft user
            deleted = store.delete_draft_user(uid)
            self.assertTrue(deleted)
            self.assertIsNone(store.get_user(uid))
            self.assertIsNone(store.get_strategy_assignment(uid, "s-test"))
        finally:
            store.close()

    def test_db002_non_draft_user_cannot_be_deleted(self):
        """Non-draft active or invited user cannot be deleted through delete_draft_user."""
        db_path = self.tmp_dir / "nondraft_delete.sqlite3"
        store = SQLiteSecurityStore(db_path, profile="test", seed_governance=False)
        try:
            u, _ = store.create_user_access(display_name="Invited User", email="invited@example.com", is_draft=False)
            uid = u["user_id"]
            self.assertEqual(u["activation_status"], "INVITED")

            with self.assertRaises(SecurityStoreError) as ctx:
                store.delete_draft_user(uid)
            self.assertIn("Only draft records can be deleted", str(ctx.exception))
            self.assertIsNotNone(store.get_user(uid))
        finally:
            store.close()

    def test_db002_fails_closed_and_rolls_back_on_audit_or_retained_dependency(self):
        """If user has immutable audit references, fail closed without deleting user."""
        db_path = self.tmp_dir / "audit_retention.sqlite3"
        store = SQLiteSecurityStore(db_path, profile="test", seed_governance=False)
        try:
            u, _ = store.create_user_access(display_name="Audited Draft", email="audited@example.com", is_draft=True)
            uid = u["user_id"]

            # Attach a security event reference
            store.save_audit_reference(event_id="evt-12345", user_id=uid, action="SECURITY_PROPOSAL")

            with self.assertRaises(SecurityStoreError) as ctx:
                store.delete_draft_user(uid)
            self.assertIn("immutable security audit references", str(ctx.exception))

            # User must still exist (rollback / untouched)
            self.assertIsNotNone(store.get_user(uid))
        finally:
            store.close()

    # ==================================================================
    # DB-003: DUPLICATE IDENTITY PREVENTION TESTS
    # ==================================================================

    def test_db003_exact_duplicate_email_rejected(self):
        """Exact duplicate email is rejected with SecurityStoreError."""
        db_path = self.tmp_dir / "dup_exact.sqlite3"
        store = SQLiteSecurityStore(db_path, profile="test", seed_governance=False)
        try:
            store.create_user_access(display_name="User 1", email="trader@example.com")
            with self.assertRaises(SecurityStoreError) as ctx:
                store.create_user_access(display_name="User 2", email="trader@example.com")
            self.assertIn("already exists", str(ctx.exception))
        finally:
            store.close()

    def test_db003_case_variant_email_rejected(self):
        """Email with different casing is rejected."""
        db_path = self.tmp_dir / "dup_case.sqlite3"
        store = SQLiteSecurityStore(db_path, profile="test", seed_governance=False)
        try:
            store.create_user_access(display_name="User 1", email="trader@example.com")
            with self.assertRaises(SecurityStoreError) as ctx:
                store.create_user_access(display_name="User 2", email="TRADER@EXAMPLE.COM")
            self.assertIn("already exists", str(ctx.exception))
        finally:
            store.close()

    def test_db003_whitespace_variant_email_rejected(self):
        """Email with leading/trailing whitespace is normalized and rejected."""
        db_path = self.tmp_dir / "dup_whitespace.sqlite3"
        store = SQLiteSecurityStore(db_path, profile="test", seed_governance=False)
        try:
            store.create_user_access(display_name="User 1", email="trader@example.com")
            with self.assertRaises(SecurityStoreError) as ctx:
                store.create_user_access(display_name="User 2", email="   trader@example.com   ")
            self.assertIn("already exists", str(ctx.exception))
        finally:
            store.close()

    def test_db003_two_distinct_emails_succeed(self):
        """Two distinct emails succeed cleanly."""
        db_path = self.tmp_dir / "distinct_emails.sqlite3"
        store = SQLiteSecurityStore(db_path, profile="test", seed_governance=False)
        try:
            u1, _ = store.create_user_access(display_name="User 1", email="trader1@example.com")
            u2, _ = store.create_user_access(display_name="User 2", email="trader2@example.com")
            self.assertNotEqual(u1["user_id"], u2["user_id"])
            self.assertNotEqual(u1["sx_id"], u2["sx_id"])
        finally:
            store.close()

    def test_db003_failed_duplicate_creates_no_partial_state(self):
        """Failed duplicate attempt creates no partial activation/user state."""
        db_path = self.tmp_dir / "no_partial_state.sqlite3"
        store = SQLiteSecurityStore(db_path, profile="test", seed_governance=False)
        try:
            store.create_user_access(display_name="User 1", email="trader@example.com")
            initial_user_count = len(store.list_users())
            initial_issuance_count = store._conn.execute("SELECT count(*) FROM activation_issuances").fetchone()[0]

            with self.assertRaises(SecurityStoreError):
                store.create_user_access(display_name="User 2", email="trader@example.com")

            # Counts must remain strictly identical
            self.assertEqual(len(store.list_users()), initial_user_count)
            self.assertEqual(store._conn.execute("SELECT count(*) FROM activation_issuances").fetchone()[0], initial_issuance_count)
        finally:
            store.close()

    def test_db003_duplicate_sx_id_rejected_by_database_index(self):
        """Direct insert of duplicate SX-ID is rejected by database index."""
        db_path = self.tmp_dir / "dup_sxid.sqlite3"
        store = SQLiteSecurityStore(db_path, profile="test", seed_governance=False)
        try:
            u1, _ = store.create_user_access(display_name="User 1", email="user1@example.com")
            sx_id = u1["sx_id"]

            # Try direct SQL insert with identical SX-ID (case-insensitive check)
            with self.assertRaises(sqlite3.IntegrityError):
                with store._transaction() as cur:
                    cur.execute("""INSERT INTO users (
                        user_id, role, lifecycle, display_name, created_at_utc, security_state,
                        sx_id, bound_email
                    ) VALUES ('uid-diff', 'USER', 'ACTIVE', 'User 2', '2026-01-01T00:00:00Z', 'ACTIVE', ?, 'other@example.com')""",
                    (sx_id.lower(),))
        finally:
            store.close()

    def test_db003_migration_preflight_fails_closed_if_duplicates_exist(self):
        """Migration preflight fails closed with clear error if pre-existing duplicate emails exist."""
        db_path = self.tmp_dir / "preflight_fail.sqlite3"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE security_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO security_metadata VALUES ('schema_version', '2')")
        conn.execute("INSERT INTO security_metadata VALUES ('live_global_hold', 'true')")
        conn.execute("""CREATE TABLE users (
            user_id TEXT PRIMARY KEY, role TEXT NOT NULL, lifecycle TEXT NOT NULL,
            display_name TEXT NOT NULL, created_at_utc TEXT NOT NULL, security_state TEXT NOT NULL,
            sx_id TEXT, bound_email TEXT
        )""")
        # Insert two duplicate emails
        conn.execute("INSERT INTO users VALUES ('u1', 'USER', 'ACTIVE', 'User 1', '2026-01-01', 'ACTIVE', 'SX-1', 'dup@test.com')")
        conn.execute("INSERT INTO users VALUES ('u2', 'USER', 'ACTIVE', 'User 2', '2026-01-01', 'ACTIVE', 'SX-2', 'DUP@TEST.COM')")
        conn.commit()
        conn.close()

        # Attempt to open store with existing duplicates
        with self.assertRaises(SecurityStoreError) as ctx:
            SQLiteSecurityStore(db_path, profile="test", seed_governance=False)
        self.assertIn("Migration safety check failed: detected 1 duplicate email group", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
