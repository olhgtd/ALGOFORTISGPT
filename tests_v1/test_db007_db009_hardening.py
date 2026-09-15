import unittest
import tempfile
import sqlite3
from pathlib import Path
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

from dashboard.backend.security_store import SQLiteSecurityStore, SecurityStoreError
from dashboard.backend.governance_store import SQLiteGovernanceStore
from engine.persistence.schema import CREATE_TABLES_SQL

class TestDB007DB009Hardening(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tpath = Path(self.temp_dir.name)
        self.sec_db = self.tpath / "security.sqlite3"
        self.gov_db = self.tpath / "governance.sqlite3"
        self.audit_db = self.tpath / "audit.sqlite3"

        self.sec = SQLiteSecurityStore(self.sec_db, profile="test", seed_governance=False)
        self.gov = SQLiteGovernanceStore(self.gov_db, profile="test")

        self.audit_conn = sqlite3.connect(str(self.audit_db))
        for stmt in CREATE_TABLES_SQL:
            self.audit_conn.executescript(stmt)

    def tearDown(self):
        self.sec.close()
        self.gov.close()
        self.audit_conn.close()
        self.temp_dir.cleanup()

    def test_db007_indexes_exist(self):
        # 1. Check Security Store indexes
        sec_indexes = {row[1] for row in self.sec._conn.execute("PRAGMA index_list(sessions)").fetchall()}
        self.assertIn("idx_sessions_user", sec_indexes)

        iss_indexes = {row[1] for row in self.sec._conn.execute("PRAGMA index_list(activation_issuances)").fetchall()}
        self.assertIn("idx_activation_issuances_user", iss_indexes)

        cred_indexes = {row[1] for row in self.sec._conn.execute("PRAGMA index_list(webauthn_credentials)").fetchall()}
        self.assertIn("idx_webauthn_credentials_user", cred_indexes)

        # 2. Check Governance Store indexes
        gov_indexes = {row[1] for row in self.gov._conn.execute("PRAGMA index_list(strategy_versions)").fetchall()}
        self.assertIn("idx_strategy_versions_strat", gov_indexes)

        # 3. Check Core Audit Store indexes
        audit_indexes = {row[1] for row in self.audit_conn.execute("PRAGMA index_list(trade_records)").fetchall()}
        self.assertIn("idx_trade_records_strat", audit_indexes)

    def _setup_active_user_and_connection(self):
        uid = uuid4()
        conn_id = f"conn-{uuid4().hex[:8]}"
        strat_id = f"strat-{uuid4().hex[:6]}"

        with self.sec._transaction() as cur:
            cur.execute("""INSERT INTO users (user_id, role, lifecycle, display_name, created_at_utc, security_state, account_status)
                           VALUES (?, 'OWNER', 'ACTIVE', 'Test Owner', '2026-09-15T00:00:00Z', 'CLEAR', 'ACTIVE')""", (str(uid),))
            cur.execute("""INSERT INTO owner_strategies (
                strategy_id, id, name, version, stage, admin_status, updated_at_utc
            ) VALUES (?, 'strat-1', 'Strat Alpha', '1.0', 'DEPLOYABLE', 'ACTIVE', '2026-09-15T00:00:00Z')""", (strat_id,))
            cur.execute("""INSERT INTO user_strategy_assignments (assignment_id, user_id, strategy_id, assignment_status, created_at_utc, updated_at_utc)
                           VALUES (?, ?, ?, 'ASSIGNED', '2026-09-15T00:00:00Z', '2026-09-15T00:00:00Z')""", (f"asg-{uuid4().hex[:6]}", str(uid), strat_id))
            cur.execute("""INSERT INTO user_connections (
                connection_id, user_id, provider, account_ref, status,
                market_data_capability, execution_capability, health_state,
                last_verified_at_utc, created_at_utc, updated_at_utc
            ) VALUES (?, ?, 'ZERODHA', 'ACC-01', 'CONFIGURED', 'READY', 'DISABLED_DISARMED', 'HEALTHY', '2026-09-15T00:00:00Z', '2026-09-15T00:00:00Z', '2026-09-15T00:00:00Z')""", (conn_id, str(uid)))

        return uid, strat_id, conn_id

    def test_db009_normal_deployment_and_duplicate_rejections(self):
        uid, strat_id, conn_id = self._setup_active_user_and_connection()

        # 1. Normal deployment succeeds
        dep1 = self.sec.create_deployment(
            user_id=uid, strategy_id=strat_id, strategy_version_id="1.0", source_sha256="sha256_mock",
            connection_id=conn_id, instrument="NIFTY", timeframe="5m", execution_mode="LIVE_PAPER"
        )
        self.assertIsNotNone(dep1["deploymentId"])
        self.assertEqual(dep1["status"], "DEPLOYED")

        # 2. Duplicate DEPLOYED is rejected with controlled SecurityStoreError
        with self.assertRaises(SecurityStoreError) as ctx:
            self.sec.create_deployment(
                user_id=uid, strategy_id=strat_id, strategy_version_id="1.0", source_sha256="sha256_mock",
                connection_id=conn_id, instrument="NIFTY", timeframe="5m", execution_mode="LIVE_PAPER"
            )
        self.assertIn("An active deployment already exists", str(ctx.exception))
        # Ensure no raw sqlite IntegrityError leaked
        self.assertNotIn("sqlite3.IntegrityError", str(ctx.exception))

        # 3. Transition to PAUSED; duplicate PAUSED is also rejected
        self.sec.transition_deployment(
            deployment_id=dep1["deploymentId"], user_id=uid, action="pause", reason="Pausing for test"
        )
        paused_dep = self.sec.get_deployment(dep1["deploymentId"], user_id=uid)
        self.assertEqual(paused_dep["status"], "PAUSED")

        with self.assertRaises(SecurityStoreError) as ctx:
            self.sec.create_deployment(
                user_id=uid, strategy_id=strat_id, strategy_version_id="1.0", source_sha256="sha256_mock",
                connection_id=conn_id, instrument="NIFTY", timeframe="5m", execution_mode="LIVE_PAPER"
            )
        self.assertIn("An active deployment already exists", str(ctx.exception))

        # 4. Transition to BLOCKED; duplicate BLOCKED is also rejected
        self.sec.transition_deployment(
            deployment_id=dep1["deploymentId"], user_id=None, action="block", reason="Blocking for test", actor="OWNER"
        )
        blocked_dep = self.sec.get_deployment(dep1["deploymentId"], user_id=uid)
        self.assertEqual(blocked_dep["status"], "BLOCKED")

        with self.assertRaises(SecurityStoreError) as ctx:
            self.sec.create_deployment(
                user_id=uid, strategy_id=strat_id, strategy_version_id="1.0", source_sha256="sha256_mock",
                connection_id=conn_id, instrument="NIFTY", timeframe="5m", execution_mode="LIVE_PAPER"
            )
        self.assertIn("An active deployment already exists", str(ctx.exception))

        # 5. Transition to STOPPED; historical row allows redeployment!
        self.sec.transition_deployment(
            deployment_id=dep1["deploymentId"], user_id=uid, action="stop", reason="Stopping for test"
        )
        stopped_dep = self.sec.get_deployment(dep1["deploymentId"], user_id=uid)
        self.assertEqual(stopped_dep["status"], "STOPPED")

        # Redeployment now succeeds!
        dep2 = self.sec.create_deployment(
            user_id=uid, strategy_id=strat_id, strategy_version_id="1.0", source_sha256="sha256_mock",
            connection_id=conn_id, instrument="NIFTY", timeframe="5m", execution_mode="LIVE_PAPER"
        )
        self.assertIsNotNone(dep2["deploymentId"])
        self.assertNotEqual(dep1["deploymentId"], dep2["deploymentId"])
        self.assertEqual(dep2["status"], "DEPLOYED")

    def test_db009_concurrent_duplicate_creation(self):
        uid, strat_id, conn_id = self._setup_active_user_and_connection()

        results = []
        errors = []

        def attempt_deployment(idx):
            # Create a separate connection handle per thread for SQLite thread safety
            t_sec = SQLiteSecurityStore(self.sec_db, profile="test", seed_governance=False)
            try:
                dep = t_sec.create_deployment(
                    user_id=uid, strategy_id=strat_id, strategy_version_id="1.0", source_sha256="sha256_mock",
                    connection_id=conn_id, instrument="BANKNIFTY", timeframe="15m", execution_mode="LIVE_PAPER"
                )
                results.append(dep)
            except Exception as e:
                errors.append(e)
            finally:
                t_sec.close()

        with ThreadPoolExecutor(max_workers=5) as executor:
            list(executor.map(attempt_deployment, range(5)))

        # Exactly ONE deployment succeeded
        self.assertEqual(len(results), 1, f"Expected exactly 1 success, got {len(results)}")
        self.assertEqual(len(errors), 4, f"Expected 4 rejections, got {len(errors)}")

        for err in errors:
            self.assertIsInstance(err, SecurityStoreError)
            self.assertIn("An active deployment already exists", str(err))

        # Check DB count
        active_count = self.sec._conn.execute(
            "SELECT COUNT(*) FROM strategy_deployments WHERE instrument='BANKNIFTY' AND status IN ('DEPLOYED', 'PAUSED', 'BLOCKED')"
        ).fetchone()[0]
        self.assertEqual(active_count, 1)

if __name__ == "__main__":
    unittest.main()
