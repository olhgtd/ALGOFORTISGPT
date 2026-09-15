import unittest
import tempfile
import sqlite3
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timedelta, timezone

from dashboard.backend.security_store import (
    SQLiteSecurityStore,
    SESSION_HISTORY_RETENTION_DAYS,
    WEBAUTHN_CHALLENGE_RETENTION_HOURS,
)
from engine.persistence.schema import CREATE_TABLES_SQL

class TestDB008Retention(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tpath = Path(self.temp_dir.name)
        self.sec_db = self.tpath / "security.sqlite3"
        self.audit_db = self.tpath / "audit.sqlite3"

        self.sec = SQLiteSecurityStore(self.sec_db, profile="test", seed_governance=False)
        self.audit_conn = sqlite3.connect(str(self.audit_db))
        for stmt in CREATE_TABLES_SQL:
            self.audit_conn.executescript(stmt)

        # Seed test user
        self.uid = uuid4()
        with self.sec._transaction() as cur:
            cur.execute("""INSERT INTO users (user_id, role, lifecycle, display_name, created_at_utc, security_state, account_status)
                           VALUES (?, 'USER', 'ACTIVE', 'Retention Test User', '2026-09-15T00:00:00Z', 'CLEAR', 'ACTIVE')""", (str(self.uid),))

    def tearDown(self):
        self.sec.close()
        self.audit_conn.close()
        self.temp_dir.cleanup()

    def test_configurable_defaults(self):
        self.assertEqual(SESSION_HISTORY_RETENTION_DAYS, 30)
        self.assertEqual(WEBAUTHN_CHALLENGE_RETENTION_HOURS, 48)
        self.assertEqual(SQLiteSecurityStore.SESSION_HISTORY_RETENTION_DAYS, 30)
        self.assertEqual(SQLiteSecurityStore.WEBAUTHN_CHALLENGE_RETENTION_HOURS, 48)

    def test_session_retention_rules(self):
        now = datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc)

        # 1. Active session (expires in future, revoked=NULL) -> MUST BE PRESERVED
        tok_active = "tok_active"
        exp_future = (now + timedelta(days=1)).isoformat()
        created_recent = (now - timedelta(hours=2)).isoformat()

        # 2. Recently revoked session (revoked 5 days ago, within 30d window) -> MUST BE PRESERVED
        tok_recent_rev = "tok_recent_rev"
        rev_recent = (now - timedelta(days=5)).isoformat()
        created_rev = (now - timedelta(days=6)).isoformat()

        # 3. Old revoked session (revoked 35 days ago, older than 30d) -> MUST BE REMOVED
        tok_old_rev = "tok_old_rev"
        rev_old = (now - timedelta(days=35)).isoformat()
        created_old_rev = (now - timedelta(days=40)).isoformat()

        # 4. Recently expired session (expired 10 days ago, unrevoked, within 30d window) -> MUST BE PRESERVED
        tok_recent_exp = "tok_recent_exp"
        exp_recent = (now - timedelta(days=10)).isoformat()
        created_recent_exp = (now - timedelta(days=11)).isoformat()

        # 5. Old expired session (expired 35 days ago, unrevoked, older than 30d) -> MUST BE REMOVED
        tok_old_exp = "tok_old_exp"
        exp_old = (now - timedelta(days=35)).isoformat()
        created_old_exp = (now - timedelta(days=36)).isoformat()

        with self.sec._transaction() as cur:
            cur.execute("INSERT INTO sessions VALUES (?, ?, 'WEB', 'LOW', ?, NULL, ?, 0)",
                        (tok_active, str(self.uid), exp_future, created_recent))
            cur.execute("INSERT INTO sessions VALUES (?, ?, 'WEB', 'LOW', ?, ?, ?, 0)",
                        (tok_recent_rev, str(self.uid), exp_future, rev_recent, created_rev))
            cur.execute("INSERT INTO sessions VALUES (?, ?, 'WEB', 'LOW', ?, ?, ?, 0)",
                        (tok_old_rev, str(self.uid), exp_future, rev_old, created_old_rev))
            cur.execute("INSERT INTO sessions VALUES (?, ?, 'WEB', 'LOW', ?, NULL, ?, 0)",
                        (tok_recent_exp, str(self.uid), exp_recent, created_recent_exp))
            cur.execute("INSERT INTO sessions VALUES (?, ?, 'WEB', 'LOW', ?, NULL, ?, 0)",
                        (tok_old_exp, str(self.uid), exp_old, created_old_exp))

        # Run maintenance
        res = self.sec.run_retention_maintenance(now=now)
        self.assertEqual(res["deleted_sessions"], 2)

        # Verify which sessions remain
        remaining = {r["token_hash"] for r in self.sec._conn.execute("SELECT token_hash FROM sessions").fetchall()}
        self.assertIn(tok_active, remaining)
        self.assertIn(tok_recent_rev, remaining)
        self.assertIn(tok_recent_exp, remaining)
        self.assertNotIn(tok_old_rev, remaining)
        self.assertNotIn(tok_old_exp, remaining)

    def test_challenge_retention_rules(self):
        now = datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc)

        # 1. Valid pending challenge (expires in future, unconsumed) -> MUST BE PRESERVED
        ch_valid = "ch_valid"
        ch_valid_exp = (now + timedelta(minutes=5)).isoformat()
        ch_valid_created = now.isoformat()

        # 2. Recently consumed challenge (consumed 2 hours ago, within 48h) -> MUST BE PRESERVED
        ch_recent_consumed = "ch_recent_consumed"
        ch_rec_c_exp = (now - timedelta(hours=2) + timedelta(minutes=5)).isoformat()
        ch_rec_c_consumed = (now - timedelta(hours=2)).isoformat()
        ch_rec_c_created = (now - timedelta(hours=2, minutes=1)).isoformat()

        # 3. Old consumed challenge (consumed 50 hours ago, older than 48h) -> MUST BE REMOVED
        ch_old_consumed = "ch_old_consumed"
        ch_old_c_exp = (now - timedelta(hours=50) + timedelta(minutes=5)).isoformat()
        ch_old_c_consumed = (now - timedelta(hours=50)).isoformat()
        ch_old_c_created = (now - timedelta(hours=50, minutes=1)).isoformat()

        # 4. Old expired unconsumed challenge (expired 50 hours ago, unconsumed) -> MUST BE REMOVED
        ch_old_expired = "ch_old_expired"
        ch_old_e_exp = (now - timedelta(hours=50)).isoformat()
        ch_old_e_created = (now - timedelta(hours=50, minutes=5)).isoformat()

        with self.sec._transaction() as cur:
            cur.execute("INSERT INTO webauthn_challenges VALUES (?, ?, 'AUTH', 'localhost', 'http', 'st', ?, NULL, ?)",
                        (ch_valid, str(self.uid), ch_valid_exp, ch_valid_created))
            cur.execute("INSERT INTO webauthn_challenges VALUES (?, ?, 'AUTH', 'localhost', 'http', 'st', ?, ?, ?)",
                        (ch_recent_consumed, str(self.uid), ch_rec_c_exp, ch_rec_c_consumed, ch_rec_c_created))
            cur.execute("INSERT INTO webauthn_challenges VALUES (?, ?, 'AUTH', 'localhost', 'http', 'st', ?, ?, ?)",
                        (ch_old_consumed, str(self.uid), ch_old_c_exp, ch_old_c_consumed, ch_old_c_created))
            cur.execute("INSERT INTO webauthn_challenges VALUES (?, ?, 'AUTH', 'localhost', 'http', 'st', ?, NULL, ?)",
                        (ch_old_expired, str(self.uid), ch_old_e_exp, ch_old_e_created))

        res = self.sec.run_retention_maintenance(now=now)
        self.assertEqual(res["deleted_challenges"], 2)

        remaining = {r["challenge_id"] for r in self.sec._conn.execute("SELECT challenge_id FROM webauthn_challenges").fetchall()}
        self.assertIn(ch_valid, remaining)
        self.assertIn(ch_recent_consumed, remaining)
        self.assertNotIn(ch_old_consumed, remaining)
        self.assertNotIn(ch_old_expired, remaining)

    def test_idempotence_and_core_audit_untouched(self):
        now = datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc)

        # Seed an audit event into audit store
        self.audit_conn.execute("""
            INSERT INTO audit_events (
                event_id, event_schema_version, event_family, event_type, aggregate_type, aggregate_identity,
                recorded_at_utc, transaction_event_ordinal, payload_version, payload_json,
                environment, run_id, canonical_configuration_fingerprint, source_identity,
                status, severity
            ) VALUES (
                'ev-1', '1.0', 'SECURITY', 'SECURITY_LOGIN', 'USER', 'usr-1',
                '2026-09-15T12:00:00Z', 1, '1.0', '{}',
                'PAPER', 'run-1', 'cfg-1', 'src-1',
                'CONFIRMED', 'INFO'
            )
        """)
        self.audit_conn.commit()

        # Run maintenance twice
        res1 = self.sec.run_retention_maintenance(now=now)
        res2 = self.sec.run_retention_maintenance(now=now)

        self.assertEqual(res2["deleted_sessions"], 0)
        self.assertEqual(res2["deleted_challenges"], 0)

        # Verify Core Audit row is untouched
        row = self.audit_conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
        self.assertEqual(row, 1)

if __name__ == "__main__":
    unittest.main()
