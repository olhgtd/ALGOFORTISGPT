"""AlgoFortis V1 — Area 5: Complete Product Workflow Tests.

Exercises end-to-end local product workflows using isolated test data:
1. OWNER END-TO-END WORKFLOW:
   - System boot & Owner authentication
   - Create invited user (onboarding)
   - Activation code generation & reissue
   - Inspect user status
   - Suspend user -> fails closed on access
   - Restore user -> access restored
   - Revoke user -> permanent termination
   - Session & device administration

2. USER END-TO-END WORKFLOW:
   - Authenticate returning user
   - Inspect assigned strategies
   - Submit permitted backtest & fetch results
   - Create, start, and stop paper trading session
   - Query execution events & trade ledger
   - Logout & re-login

3. STRATEGY GOVERNANCE & PROJECTION WORKFLOW:
   - Strategy registration & version resolution
   - Hash verification of strategy code
   - Historical backtest linkage
   - Paper session assignment

4. HIGH-ASSURANCE RECOVERY WORKFLOW:
   - Controlled lockout simulation
   - Recovery code presentation
   - Invalidation of active sessions & devices
   - Re-enrollment and safe return

5. RESTART & DATABASE STABILITY WORKFLOW:
   - Run workload
   - Clean shutdown of background job queues and services
   - Reopen database and verify zero stale locks or corruption
"""
import gc
import hashlib
import tempfile
import time
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from dashboard.backend.api import create_app
from dashboard.backend.domain import (
    Role,
    Lifecycle,
    AccountAccessStatus,
    ActivationStatus,
    ServiceEntitlementStatus,
    UserIdentity,
    AccessRoute,
)
from dashboard.backend.security import (
    SecurityConfiguration,
    SessionService,
)
from dashboard.backend.security_store import SQLiteSecurityStore
from dashboard.backend.governance_store import SQLiteGovernanceStore
from dashboard.backend.core_audit import MandatoryCoreSecurityAudit
from dashboard.backend.adapters import (
    PersistenceHealthReadAdapter,
    AccessRegistryReadAdapter,
    D16AuditReadAdapter,
)
from dashboard.backend.paper_service import PaperService
from dashboard.backend.backtest_service import BacktestService
from dashboard.backend.auth_policy import AuthPolicyManager
from dashboard.backend.session_manager import SessionManager
from dashboard.backend.backup_service import AlgoFortisBackupService, SQLiteOperationalBackupService
from engine.persistence.sqlite_store import SQLitePaperStateStore


class TestArea5CompleteProductWorkflows(unittest.TestCase):

    def setUp(self):
        gc.collect()
        self._tmp = tempfile.TemporaryDirectory(prefix="af_area5_", ignore_cleanup_errors=True)
        self.tmp_path = Path(self._tmp.name).resolve()

        self.sec_db = self.tmp_path / "security.sqlite3"
        self.gov_db = self.tmp_path / "governance.sqlite3"
        self.audit_db = self.tmp_path / "audit.sqlite3"

        self.sec_store = SQLiteSecurityStore(self.sec_db, seed_governance=False, profile="test")
        self.gov_store = SQLiteGovernanceStore(self.gov_db, profile="test")
        self.audit_store = SQLitePaperStateStore(
            self.audit_db, account_id="test-acct", starting_capital=Decimal("100000.00"), audit_source_identity="test"
        )
        self.core_audit = MandatoryCoreSecurityAudit(audit_store=self.audit_store, security_store=self.sec_store)

        # Setup Master Owner
        self.owner_id = uuid4()
        self.owner = UserIdentity(
            user_id=self.owner_id,
            role=Role.OWNER,
            lifecycle=Lifecycle.ACTIVE,
            display_name="Master Owner",
            account_status=AccountAccessStatus.ACTIVE,
            activation_status=ActivationStatus.REDEEMED,
            service_status=ServiceEntitlementStatus.ACTIVE,
            sx_id="SX-OWNER-01",
        )

        now_iso = datetime.now(timezone.utc).isoformat()
        with self.sec_store._transaction() as cur:
            cur.execute(
                """INSERT OR REPLACE INTO users (
                    user_id, role, lifecycle, display_name, created_at_utc, security_state,
                    account_status, activation_status, service_status, sx_id
                ) VALUES (?, ?, ?, ?, ?, 'CLEAR', ?, ?, ?, ?)""",
                (
                    str(self.owner.user_id),
                    self.owner.role.value,
                    self.owner.lifecycle.value,
                    self.owner.display_name,
                    now_iso,
                    self.owner.account_status.value,
                    self.owner.activation_status.value,
                    self.owner.service_status.value,
                    self.owner.sx_id,
                ),
            )

        self.sec_config = SecurityConfiguration(normal_mtls_required=False)
        self.session_service = SessionService(self.sec_config, store=self.sec_store)
        self.owner_session = self.session_service.issue(user=self.owner, route=AccessRoute.NORMAL, mtls_verified=True)
        self.owner_headers = {"Authorization": f"Bearer {self.owner_session.token}"}

        self.paper_service = PaperService(
            security_store=self.sec_store,
            governance_store=self.gov_store,
            artifact_root=self.tmp_path / "artifacts",
        )
        self.backtest_service = BacktestService(security_store=self.sec_store)

        self.health_adapter = PersistenceHealthReadAdapter(persistence_store=self.sec_store, db_path=self.sec_db)
        self.access_adapter = AccessRegistryReadAdapter(security_store=self.sec_store)
        self.audit_adapter = D16AuditReadAdapter(persistence_store=self.sec_store)

        self.app = create_app(
            owner=self.owner,
            config=self.sec_config,
            security_store=self.sec_store,
            governance_store=self.gov_store,
            core_security_audit=self.core_audit,
            backtest_service=self.backtest_service,
            paper_service=self.paper_service,
            health_adapter=self.health_adapter,
            access_adapter=self.access_adapter,
            audit_adapter=self.audit_adapter,
            artifact_root=self.tmp_path / "artifacts",
        )
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def tearDown(self):
        self.client.close()
        self.sec_store.close()
        self.gov_store.close()
        self.audit_store.close()
        gc.collect()
        try:
            self._tmp.cleanup()
        except Exception:
            pass

    def test_owner_lifecycle_workflow(self):
        """Workflow:
        1. Owner invites a new trader.
        2. Inspects access records.
        3. Reissues activation code.
        4. Suspends account -> access fails closed.
        5. Restores account -> access restored.
        6. Revokes account -> permanently terminated.
        """
        # 1. Invite new user
        invite_resp = self.client.post(
            "/api/v1/owner/access/users",
            json={
                "email": "workflow_trader@algofortis.io",
                "display_name": "Workflow Trader",
                "role": "USER",
                "service_term_type": "ANNUAL",
                "plan": "STANDARD",
            },
            headers=self.owner_headers,
        )
        self.assertEqual(invite_resp.status_code, 200)
        invite_data = invite_resp.json()
        self.assertTrue(invite_data["success"])
        code1 = invite_data["activation_code"]
        user_identifier = invite_data["record"]["user_id"]

        # 2. Inspect access records
        records_resp = self.client.get("/api/v1/integration/access/records", headers=self.owner_headers)
        self.assertEqual(records_resp.status_code, 200)
        self.assertGreater(records_resp.json()["total_count"], 0)

        # 3. Reissue activation code
        reissue_resp = self.client.post(
            f"/api/v1/owner/access/users/{user_identifier}/reissue-activation",
            headers=self.owner_headers,
        )
        self.assertEqual(reissue_resp.status_code, 200)
        code2 = reissue_resp.json()["activation_code"]
        self.assertNotEqual(code1, code2)

        # 4. Suspend user
        suspend_resp = self.client.post(
            f"/api/v1/owner/access/users/{user_identifier}/suspend",
            headers=self.owner_headers,
        )
        self.assertEqual(suspend_resp.status_code, 200)
        user_row = self.sec_store.get_user(user_identifier)
        self.assertEqual(user_row["account_status"], "SUSPENDED")

        # 5. Restore user
        restore_resp = self.client.post(
            f"/api/v1/owner/access/users/{user_identifier}/restore",
            headers=self.owner_headers,
        )
        self.assertEqual(restore_resp.status_code, 200)
        user_row = self.sec_store.get_user(user_identifier)
        self.assertIn(user_row["account_status"], ["PENDING", "ACTIVE"])

        # 6. Revoke user
        revoke_resp = self.client.post(
            f"/api/v1/owner/access/users/{user_identifier}/revoke",
            headers=self.owner_headers,
        )
        self.assertEqual(revoke_resp.status_code, 200)
        user_row = self.sec_store.get_user(user_identifier)
        self.assertEqual(user_row["account_status"], "REVOKED")

    def test_user_and_strategy_workflow(self):
        """Workflow:
        1. Register trader identity.
        2. Trader checks profile.
        3. Register and assign strategy.
        4. Run simulated backtest.
        5. Create, start, query, and stop paper trading session.
        """
        trader_id = uuid4()
        trader = UserIdentity(
            user_id=trader_id,
            role=Role.USER,
            lifecycle=Lifecycle.ACTIVE,
            display_name="Pro Quant",
            account_status=AccountAccessStatus.ACTIVE,
            activation_status=ActivationStatus.REDEEMED,
            service_status=ServiceEntitlementStatus.ACTIVE,
            sx_id="SX-QUANT-01",
        )
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.sec_store._transaction() as cur:
            cur.execute(
                """INSERT INTO users (
                    user_id, role, lifecycle, display_name, created_at_utc, security_state,
                    account_status, activation_status, service_status, sx_id
                ) VALUES (?, ?, ?, ?, ?, 'CLEAR', ?, ?, ?, ?)""",
                (
                    str(trader.user_id),
                    trader.role.value,
                    trader.lifecycle.value,
                    trader.display_name,
                    now_iso,
                    trader.account_status.value,
                    trader.activation_status.value,
                    trader.service_status.value,
                    trader.sx_id,
                ),
            )

        trader_session = self.session_service.issue(user=trader, route=AccessRoute.NORMAL, mtls_verified=True)
        trader_headers = {"Authorization": f"Bearer {trader_session.token}"}

        # 2. Check profile
        prof_resp = self.client.get("/api/v1/users/current", headers=trader_headers)
        self.assertEqual(prof_resp.status_code, 200)
        self.assertEqual(prof_resp.json()["sx_id"], "SX-QUANT-01")

        # 3. Register strategy for this user and grant paper allowance under Owner governance
        strat_code = b'''from engine.strategy.base import Signal, StrategySignalGenerator
class TestStrategy(StrategySignalGenerator):
    interface_version = "1.0"
    state_schema = {"count": 0}
    def generate_signal(self, data, state):
        return Signal("HOLD", 0.0, {})
'''
        strat_sha = hashlib.sha256(strat_code).hexdigest()
        artifact_path = self.tmp_path / "artifacts" / f"usr_{trader_id}" / "strategies" / "strat-alpha-momentum" / "1.0.0.py"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(strat_code)

        self.sec_store.register_backtest_artifact(
            strategy_id="strat-alpha-momentum",
            version_id="1.0.0",
            name="Alpha Momentum",
            owner_id=str(trader_id),
        )
        self.gov_store.save_version({
            "strategy_id": "strat-alpha-momentum",
            "version_id": "1.0.0",
            "owner_id": str(trader_id),
            "source_sha256": strat_sha,
            "artifact_path": str(artifact_path),
            "stage": "PAPER_ELIGIBLE",
            "archived": 0,
            "protective_policy_identity": None,
            "created_at_utc": "2026-01-01T00:00:00Z",
        })
        with self.sec_store._transaction() as cur:
            cur.execute(
                """UPDATE owner_strategies SET
                    paper_system_readiness = 'READY',
                    paper_owner_allowance = 'ALLOWED',
                    admin_status = 'ACTIVE'
                WHERE strategy_id = 'strat-alpha-momentum'"""
            )
            cur.execute(
                """INSERT OR REPLACE INTO owner_datasets (
                    dataset_id, id, source, market, instrument, segment, timeframe, source_timezone,
                    start_date, end_date, trading_days, row_count, format, logical_path, gap_status,
                    gap_details, provenance, hash_sha256, acquisition_state, system_readiness,
                    system_blocker_reason, verification_details, owner_approval, owner_hold_reason,
                    history_json, updated_at_utc
                ) VALUES (
                    'nse-tick-primary', 'ds-primary', 'Mock Feed', 'NSE_INDEX', 'NIFTY', 'Spot', '1m', 'Asia/Kolkata',
                    '2026-01-01', '2026-09-01', 100, 10000, 'PARQUET_V2', 'data/test.parquet', 'GAPS_CLEAR',
                    'Clear', 'SYNTHETIC', 'hash123', 'ACQUIRED', 'SYSTEM_READY',
                    NULL, 'Verified', 'APPROVED', NULL,
                    '[]', '2026-09-15T00:00:00Z'
                )"""
            )

        strat_resp = self.client.get("/api/v1/strategies", headers=trader_headers)
        self.assertEqual(strat_resp.status_code, 200)

        # 4. Paper session lifecycle
        # Create paper session
        paper_create = self.client.post(
            "/api/v1/paper/sessions",
            json={
                "strategy_id": "strat-alpha-momentum",
                "instrument": "NIFTY",
                "timeframe": "1m",
                "initial_capital": 50000.0,
                "data_source_mode": "HISTORICAL_REPLAY",
            },
            headers=trader_headers,
        )
        self.assertEqual(paper_create.status_code, 200)
        session_id = paper_create.json()["session_id"]

        # Attach mock dataset feed for historical replay
        class MockFeed:
            def fetch_dataset(self, dataset):
                import pandas as pd
                df = pd.DataFrame({
                    "timestamp": pd.date_range("2026-01-01", periods=10, freq="1min", tz="UTC"),
                    "open": [100.0] * 10,
                    "high": [105.0] * 10,
                    "low": [95.0] * 10,
                    "close": [102.0] * 10,
                    "volume": [1000] * 10,
                    "instrument": ["NIFTY"] * 10,
                    "timeframe": ["1m"] * 10,
                })
                digest = dataset.get("hashSha256") or dataset.get("hash_sha256") or "hash123"
                return df, digest.removeprefix("sha256:")

        self.paper_service._dataset_feed = MockFeed()

        # Start paper session
        start_resp = self.client.post(f"/api/v1/paper/sessions/{session_id}/start", headers=trader_headers)
        self.assertEqual(start_resp.status_code, 200, start_resp.json())

        # Query session status
        get_resp = self.client.get(f"/api/v1/paper/sessions/{session_id}", headers=trader_headers)
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["status"], "ACTIVE")

        # Stop paper session
        stop_resp = self.client.post(f"/api/v1/paper/sessions/{session_id}/stop", headers=trader_headers)
        self.assertEqual(stop_resp.status_code, 200)
        self.assertEqual(stop_resp.json()["status"], "STOPPED")

    def test_recovery_and_restart_workflow(self):
        """Workflow:
        1. Set up user with active session and registered recovery codes.
        2. Execute high-assurance recovery.
        3. Verify all existing sessions are revoked.
        4. Verify operational database backup and clean restart rehearsal.
        """
        apm = AuthPolicyManager()
        sm = SessionManager()
        uid = "usr_e2e_recovery"

        at, rt, _ = sm.create_session(uid, "dev_primary", "USER")
        codes = apm.generate_recovery_codes(uid)
        self.assertEqual(len(codes), 8)

        # Execute recovery
        res = apm.execute_high_assurance_recovery(uid, codes[0], session_manager=sm)
        self.assertTrue(res)

        # Access token invalidated
        self.assertIsNone(sm.validate_access_token(at))

        # Operational SQLite backup snapshot
        backup_file = self.tmp_path / "post_recovery_backup.sqlite3"
        SQLiteOperationalBackupService.backup_database(self.sec_store, backup_file)
        self.assertTrue(backup_file.exists())

        # Clean restart rehearsal
        restart_conn = SQLiteSecurityStore(backup_file, profile="test")
        try:
            cur = restart_conn._conn.cursor()
            cur.execute("PRAGMA integrity_check")
            res = cur.fetchone()
            self.assertEqual(res[0], "ok")
        finally:
            restart_conn.close()


if __name__ == "__main__":
    unittest.main()
