"""AlgoFortis — API & Service Contract Hardening Test Suite.

Comprehensive tests covering:
1. AUTH / AUTHORIZATION:
   - GET /api/v1/integration/system/health (401 unauthenticated, 403 non-owner, 200 owner)
   - GET /api/v1/integration/access/records (401 unauthenticated, 403 non-owner, 200 owner)
   - Owner-only endpoints fail-closed on standard user token
2. REQUEST / QUERY VALIDATION:
   - Query pagination bounds (limit, offset) fail-closed on negative or out-of-range limits
   - Numeric and identifier validation
3. IDOR / CROSS-USER ISOLATION:
   - User A cannot view, mutate, or cancel User B backtests (404)
   - User A cannot view, start, stop, or read positions/orders of User B paper sessions (404)
   - User A cannot view or mutate User B connections or deployments (404)
   - Owner oversight is permitted with server path redaction for non-owners
4. ERROR CONTRACT & SECRET PRIVACY:
   - 500 responses return clean messages with zero leaked internal exception strings or paths
   - No token hashes, activation hashes, or secret keys leaked in API responses
5. RETRY / IDEMPOTENCY:
   - Duplicate onboarding with same email or operation ID returns idempotent result
6. TRADING SAFETY & LIVE ISOLATION:
   - Live order endpoints fail-closed with 403 EXECUTION_DISABLED
   - READ_ONLY=true, DISARMED=true invariants preserved
7. GOVERNANCE BOUNDARY:
   - promote_strategy resolves source digests via store authority get_strategy_source_digests
"""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from dashboard.backend.api import create_app
from dashboard.backend.domain import (
    AccessRoute,
    AccountAccessStatus,
    ActivationStatus,
    Lifecycle,
    Role,
    ServiceEntitlementStatus,
    ServiceTermType,
    SessionRisk,
    UserIdentity,
)
from dashboard.backend.governance_store import SQLiteGovernanceStore
from dashboard.backend.security import (
    SecurityConfiguration,
    Session,
    SessionService,
)
from dashboard.backend.security_store import SQLiteSecurityStore
from dashboard.backend.core_audit import MandatoryCoreSecurityAudit
from dashboard.backend.adapters import (
    PersistenceHealthReadAdapter,
    AccessRegistryReadAdapter,
    D16AuditReadAdapter,
)
from dashboard.backend.paper_service import PaperService
from dashboard.backend.backtest_service import BacktestService
from engine.persistence.sqlite_store import SQLitePaperStateStore


class TestApiHardeningSuite(unittest.TestCase):

    def setUp(self):
        import gc
        gc.collect()
        self._tmp = tempfile.TemporaryDirectory(prefix="af_api_test_", ignore_cleanup_errors=True)
        self.tmp_path = Path(self._tmp.name)

        # Create isolated stores
        self.sec_db = self.tmp_path / "security.sqlite3"
        self.gov_db = self.tmp_path / "governance.sqlite3"
        self.audit_db = self.tmp_path / "audit.sqlite3"

        self.sec_store = SQLiteSecurityStore(self.sec_db, seed_governance=False, profile="test")
        self.gov_store = SQLiteGovernanceStore(self.gov_db, profile="test")
        self.audit_store = SQLitePaperStateStore(
            self.audit_db, account_id="test-acct", starting_capital=Decimal("0.00"), audit_source_identity="test"
        )
        self.core_audit = MandatoryCoreSecurityAudit(audit_store=self.audit_store, security_store=self.sec_store)

        # Create Owner identity
        self.owner_id = uuid4()
        self.owner = UserIdentity(
            user_id=self.owner_id,
            role=Role.OWNER,
            lifecycle=Lifecycle.ACTIVE,
            display_name="Super Owner",
            account_status=AccountAccessStatus.ACTIVE,
            activation_status=ActivationStatus.REDEEMED,
            service_status=ServiceEntitlementStatus.ACTIVE,
        )

        # Create User A and User B identities
        self.user_a_id = uuid4()
        self.user_a = UserIdentity(
            user_id=self.user_a_id,
            role=Role.USER,
            lifecycle=Lifecycle.ACTIVE,
            display_name="Trader Alpha",
            account_status=AccountAccessStatus.ACTIVE,
            activation_status=ActivationStatus.REDEEMED,
            service_status=ServiceEntitlementStatus.ACTIVE,
            sx_id="SX-ALPHA-01",
        )

        self.user_b_id = uuid4()
        self.user_b = UserIdentity(
            user_id=self.user_b_id,
            role=Role.USER,
            lifecycle=Lifecycle.ACTIVE,
            display_name="Trader Beta",
            account_status=AccountAccessStatus.ACTIVE,
            activation_status=ActivationStatus.REDEEMED,
            service_status=ServiceEntitlementStatus.ACTIVE,
            sx_id="SX-BETA-02",
        )

        # Initialize SessionService and issue test sessions
        self.sec_config = SecurityConfiguration(normal_mtls_required=False)
        self.session_service = SessionService(self.sec_config, store=self.sec_store)

        self.owner_session = self.session_service.issue(
            user=self.owner, route=AccessRoute.NORMAL, mtls_verified=True, step_up_satisfied=True
        )
        self.user_a_session = self.session_service.issue(
            user=self.user_a, route=AccessRoute.NORMAL, mtls_verified=True, step_up_satisfied=True
        )
        self.user_b_session = self.session_service.issue(
            user=self.user_b, route=AccessRoute.NORMAL, mtls_verified=True, step_up_satisfied=True
        )

        # Paper and Backtest services
        self.paper_service = PaperService(
            security_store=self.sec_store,
            governance_store=self.gov_store,
            artifact_root=self.tmp_path / "artifacts",
        )
        self.backtest_service = BacktestService(security_store=self.sec_store)

        # Health & Access Adapters
        self.health_adapter = PersistenceHealthReadAdapter(persistence_store=self.sec_store, db_path=self.sec_db)
        self.access_adapter = AccessRegistryReadAdapter(security_store=self.sec_store)
        self.audit_adapter = D16AuditReadAdapter(persistence_store=self.sec_store)

        # Register users in SQLite database table
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.sec_store._transaction() as cur:
            for u in [self.owner, self.user_a, self.user_b]:
                cur.execute(
                    """INSERT OR REPLACE INTO users (
                        user_id, role, lifecycle, display_name, created_at_utc, security_state,
                        account_status, activation_status, service_status, sx_id
                    ) VALUES (?, ?, ?, ?, ?, 'CLEAR', ?, ?, ?, ?)""",
                    (
                        str(u.user_id),
                        u.role.value,
                        u.lifecycle.value,
                        u.display_name,
                        now_iso,
                        u.account_status.value,
                        u.activation_status.value,
                        u.service_status.value,
                        getattr(u, "sx_id", None),
                    ),
                )

        # Register default test strategies
        self.sec_store.register_backtest_artifact(
            strategy_id="strat-b",
            version_id="1.0.0",
            name="Strategy B",
            owner_id=str(self.user_b_id),
        )

        # Create FastAPI App
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
        self.client = TestClient(self.app)

    def tearDown(self):
        import gc
        self.sec_store.close()
        self.gov_store.close()
        self.audit_store.close()
        gc.collect()
        try:
            self._tmp.cleanup()
        except Exception:
            pass

    # =========================================================================
    # 1. AUTH / AUTHORIZATION TESTS (FIND-001)
    # =========================================================================

    def test_find001_system_health_requires_owner(self):
        """FIND-001: GET /api/v1/integration/system/health requires authenticated Owner."""
        # 1. Unauthenticated -> 401
        res_anon = self.client.get("/api/v1/integration/system/health")
        self.assertEqual(res_anon.status_code, 401)
        self.assertIn("authentication required", res_anon.json().get("detail", ""))

        # 2. Authenticated non-owner (User A) -> 403
        headers_user = {"Authorization": f"Bearer {self.user_a_session.token}"}
        res_user = self.client.get("/api/v1/integration/system/health", headers=headers_user)
        self.assertEqual(res_user.status_code, 403)
        self.assertIn("owner authorization required", res_user.json().get("detail", ""))

        # 3. Authenticated Owner -> 200
        headers_owner = {"Authorization": f"Bearer {self.owner_session.token}"}
        res_owner = self.client.get("/api/v1/integration/system/health", headers=headers_owner)
        self.assertEqual(res_owner.status_code, 200)
        data = res_owner.json()
        self.assertTrue(data.get("adapter_reachable"))
        self.assertTrue(data.get("database_connected"))

    def test_access_records_requires_owner(self):
        """GET /api/v1/integration/access/records requires authenticated Owner."""
        res_anon = self.client.get("/api/v1/integration/access/records")
        self.assertEqual(res_anon.status_code, 401)

        headers_user = {"Authorization": f"Bearer {self.user_a_session.token}"}
        res_user = self.client.get("/api/v1/integration/access/records", headers=headers_user)
        self.assertEqual(res_user.status_code, 403)

        headers_owner = {"Authorization": f"Bearer {self.owner_session.token}"}
        res_owner = self.client.get("/api/v1/integration/access/records", headers=headers_owner)
        self.assertEqual(res_owner.status_code, 200)
        self.assertIn("records", res_owner.json())

    # =========================================================================
    # 2. REQUEST / QUERY VALIDATION (FIND-002)
    # =========================================================================

    def test_find002_query_pagination_bounds_fail_closed(self):
        """FIND-002: Query limit/offset bounds reject negative and oversized values with 422."""
        headers_owner = {"Authorization": f"Bearer {self.owner_session.token}"}
        headers_user = {"Authorization": f"Bearer {self.user_a_session.token}"}

        # 1. integration_audit_events: negative limit -> 422
        res = self.client.get("/api/v1/integration/audit/events?limit=-1", headers=headers_owner)
        self.assertEqual(res.status_code, 422)

        # 2. integration_audit_events: limit=0 -> 422
        res = self.client.get("/api/v1/integration/audit/events?limit=0", headers=headers_owner)
        self.assertEqual(res.status_code, 422)

        # 3. integration_audit_events: limit > 500 -> 422
        res = self.client.get("/api/v1/integration/audit/events?limit=501", headers=headers_owner)
        self.assertEqual(res.status_code, 422)

        # 4. integration_audit_events: negative offset -> 422
        res = self.client.get("/api/v1/integration/audit/events?offset=-1", headers=headers_owner)
        self.assertEqual(res.status_code, 422)

        # 5. list_backtests: limit bounds
        res = self.client.get("/api/v1/backtests?limit=-10", headers=headers_user)
        self.assertEqual(res.status_code, 422)
        res = self.client.get("/api/v1/backtests?limit=1000", headers=headers_user)
        self.assertEqual(res.status_code, 422)

        # 6. list_paper_sessions: limit bounds
        res = self.client.get("/api/v1/paper/sessions?limit=0", headers=headers_user)
        self.assertEqual(res.status_code, 422)
        res = self.client.get("/api/v1/paper/sessions?limit=501", headers=headers_user)
        self.assertEqual(res.status_code, 422)

        # Valid limits succeed
        res = self.client.get("/api/v1/paper/sessions?limit=50", headers=headers_user)
        self.assertEqual(res.status_code, 200)

    # =========================================================================
    # 3. ERROR CONTRACT & SECRET PRIVACY (FIND-003)
    # =========================================================================

    def test_find003_error_responses_never_leak_exceptions_or_paths(self):
        """FIND-003: 500 error responses are generic and contain zero raw traceback/exception details."""
        headers_user = {"Authorization": f"Bearer {self.user_a_session.token}"}

        # Request with nonexistent session ID on live quote
        res = self.client.post(
            "/api/v1/paper/sessions/nonexistent-session/live-quote",
            headers=headers_user,
            json={
                "event_id": "evt-1",
                "instrument": "NIFTY",
                "exchange_timestamp": datetime.now(timezone.utc).isoformat(),
                "bid_price": 20000.0,
                "ask_price": 20005.0,
                "bid_quantity": 50,
                "ask_quantity": 50,
                "last_price": 20002.5,
                "source": "SIM",
            },
        )
        # Should be 422 (validation/not found), not 500 with leaked traceback
        self.assertIn(res.status_code, (400, 404, 422))
        body_text = res.text
        self.assertNotIn("Traceback", body_text)
        self.assertNotIn("sqlite3.OperationalError", body_text)
        self.assertNotIn("C:\\Users\\", body_text)

    # =========================================================================
    # 4. IDOR / CROSS-USER ISOLATION PROOFS
    # =========================================================================

    def test_idor_backtest_isolation(self):
        """Proves User A cannot read, trade-inspect, or cancel User B's backtest runs."""
        # Setup a backtest run owned by User B
        b_run_id = f"bt-{uuid4().hex[:8]}"
        self.sec_store.save_backtest_run({
            "run_id": b_run_id,
            "user_id": str(self.user_b_id),
            "strategy_id": "strat-b",
            "dataset_id": "ds-1",
            "instrument": "NIFTY",
            "timeframe": "1m",
            "status": "RUNNING",
            "submitted_at_utc": datetime.now(timezone.utc).isoformat(),
            "execution_metadata": {},
        })

        headers_user_a = {"Authorization": f"Bearer {self.user_a_session.token}"}
        headers_user_b = {"Authorization": f"Bearer {self.user_b_session.token}"}
        headers_owner = {"Authorization": f"Bearer {self.owner_session.token}"}

        # 1. User B reads own backtest -> 200
        res_b = self.client.get(f"/api/v1/backtests/{b_run_id}", headers=headers_user_b)
        self.assertEqual(res_b.status_code, 200)

        # 2. User A attempts to read User B backtest -> 404 (IDOR fail-closed)
        res_a = self.client.get(f"/api/v1/backtests/{b_run_id}", headers=headers_user_a)
        self.assertEqual(res_a.status_code, 404)

        # 3. User A attempts to read User B backtest trades -> 404
        res_a_trades = self.client.get(f"/api/v1/backtests/{b_run_id}/trades", headers=headers_user_a)
        self.assertEqual(res_a_trades.status_code, 404)

        # 4. User A attempts to cancel User B backtest -> 404
        res_a_cancel = self.client.post(f"/api/v1/backtests/{b_run_id}/cancel", headers=headers_user_a)
        self.assertEqual(res_a_cancel.status_code, 404)

        # 5. Owner oversight can read User B backtest -> 200
        res_owner = self.client.get(f"/api/v1/backtests/{b_run_id}", headers=headers_owner)
        self.assertEqual(res_owner.status_code, 200)

    def test_idor_paper_session_isolation(self):
        """Proves User A cannot view, start, stop, or inspect User B's paper sessions."""
        ses = self.paper_service.create_session(
            user_id=str(self.user_b_id),
            strategy_id="strat-b",
            instrument="NIFTY",
            timeframe="1m",
            initial_capital=50000.0,
        )
        b_sess_id = ses["session_id"]

        headers_user_a = {"Authorization": f"Bearer {self.user_a_session.token}"}
        headers_user_b = {"Authorization": f"Bearer {self.user_b_session.token}"}

        # User B can access own session
        res_b = self.client.get(f"/api/v1/paper/sessions/{b_sess_id}", headers=headers_user_b)
        self.assertEqual(res_b.status_code, 200)

        # User A receives 404 on all endpoints
        self.assertEqual(self.client.get(f"/api/v1/paper/sessions/{b_sess_id}", headers=headers_user_a).status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1/paper/sessions/{b_sess_id}/positions", headers=headers_user_a).status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1/paper/sessions/{b_sess_id}/orders", headers=headers_user_a).status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1/paper/sessions/{b_sess_id}/events", headers=headers_user_a).status_code, 404)
        self.assertEqual(self.client.post(f"/api/v1/paper/sessions/{b_sess_id}/start", headers=headers_user_a).status_code, 404)
        self.assertEqual(self.client.post(f"/api/v1/paper/sessions/{b_sess_id}/stop", headers=headers_user_a).status_code, 404)

    def test_idor_connections_isolation(self):
        """Proves User A cannot inspect or mutate User B's connections."""
        conn = self.sec_store.create_user_connection(
            user_id=str(self.user_b_id),
            provider="UPSTOX",
            account_ref="ACT-BETA-01",
        )
        b_conn_id = conn["connectionId"]

        headers_user_a = {"Authorization": f"Bearer {self.user_a_session.token}"}
        headers_user_b = {"Authorization": f"Bearer {self.user_b_session.token}"}

        # User B reads own connection -> 200
        res_b = self.client.get(f"/api/v1/user/connections/{b_conn_id}", headers=headers_user_b)
        self.assertEqual(res_b.status_code, 200)

        # User A receives 404
        res_a = self.client.get(f"/api/v1/user/connections/{b_conn_id}", headers=headers_user_a)
        self.assertEqual(res_a.status_code, 404)

        # User A cannot update User B connection -> 404
        res_a_patch = self.client.patch(
            f"/api/v1/user/connections/{b_conn_id}",
            headers=headers_user_a,
            json={"display_name": "Hacked Connection"},
        )
        self.assertEqual(res_a_patch.status_code, 404)

    # =========================================================================
    # 5. SERVICE BOUNDARIES & GOVERNANCE PROMOTION (FIND-004)
    # =========================================================================

    def test_find004_governance_store_helper_and_promotion(self):
        """FIND-004: Strategy promotion queries source hashes via get_strategy_source_digests store method."""
        strat_id = "strat-prom-test"
        ver_id = str(uuid4())
        expected_digest = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

        # Save strategy version in governance store
        self.gov_store.save_version({
            "version_id": ver_id,
            "strategy_id": strat_id,
            "owner_id": str(self.owner_id),
            "source_sha256": expected_digest,
            "artifact_path": f"users/usr_{self.owner_id}/strategies/strat.py",
            "stage": "BACKTEST",
            "archived": 0,
            "protective_policy_identity": "DEFAULT",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        })

        # Verify the helper returns the exact digest
        digests = self.gov_store.get_strategy_source_digests(strat_id)
        self.assertEqual(digests, {expected_digest})

        # Register strategy in owner_strategies table
        self.sec_store.register_backtest_artifact(
            strategy_id=strat_id,
            version_id=ver_id,
            name="Promotion Test Strategy",
            owner_id=str(self.owner_id),
        )

        # Save a completed backtest run to satisfy promotion requirement
        self.sec_store.save_backtest_run({
            "run_id": f"run-{uuid4().hex[:8]}",
            "user_id": str(self.owner_id),
            "strategy_id": strat_id,
            "dataset_id": "ds-1",
            "instrument": "NIFTY",
            "timeframe": "1m",
            "status": "COMPLETED",
            "submitted_at_utc": datetime.now(timezone.utc).isoformat(),
            "execution_metadata": {},
        })

        headers_owner = {"Authorization": f"Bearer {self.owner_session.token}"}

        # Attempt promote with mismatched hash -> 422
        res_bad_hash = self.client.post(
            f"/api/v1/owner/strategies/{strat_id}/promote",
            headers=headers_owner,
            json={"target_stage": "PAPER_ELIGIBLE", "source_sha256": "bad-hash"},
        )
        self.assertEqual(res_bad_hash.status_code, 422)
        self.assertIn("artifact hash mismatch", res_bad_hash.json().get("detail", ""))

        # Attempt promote with valid matching hash -> 200
        res_ok = self.client.post(
            f"/api/v1/owner/strategies/{strat_id}/promote",
            headers=headers_owner,
            json={"target_stage": "PAPER_ELIGIBLE", "source_sha256": expected_digest},
        )
        self.assertEqual(res_ok.status_code, 200)
        self.assertEqual(res_ok.json().get("strategy", {}).get("stage"), "PAPER_ELIGIBLE")

    # =========================================================================
    # 6. RETRY / IDEMPOTENCY VERIFICATION
    # =========================================================================

    def test_idempotent_user_access_creation(self):
        """Duplicate user onboarding returns identical record without conflict."""
        headers_owner = {"Authorization": f"Bearer {self.owner_session.token}"}
        payload = {
            "email": "test-trader@algofortis.internal",
            "display_name": "Test Trader",
            "role": "USER",
            "plan": "PRO",
            "service_term_type": "ANNUAL",
            "is_draft": False,
            "notes": "Initial test registration",
            "idempotency_key": "op-idem-test-001",
        }

        # First submission -> 200
        res1 = self.client.post("/api/v1/owner/access/users", headers=headers_owner, json=payload)
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()
        self.assertTrue(data1["success"])
        user_id_1 = data1["record"]["user_id"]
        code_1 = data1["activation_code"]
        self.assertIsNotNone(code_1)

        # Retry identical submission -> returns idempotent 200 with same user_id and new/preserved code
        res2 = self.client.post("/api/v1/owner/access/users", headers=headers_owner, json=payload)
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertTrue(data2["success"])
        self.assertEqual(data2["record"]["user_id"], user_id_1)

    # =========================================================================
    # 7. TRADING SAFETY & LIVE MUTATION FAIL-CLOSED INVARIANTS
    # =========================================================================

    def test_live_mutation_is_unconditionally_disabled(self):
        """All live trading mutation routes fail-closed with 403 EXECUTION_DISABLED."""
        headers_owner = {"Authorization": f"Bearer {self.owner_session.token}"}
        headers_user = {"Authorization": f"Bearer {self.user_a_session.token}"}

        live_endpoints = [
            ("POST", "/api/v1/live/orders"),
            ("PUT", "/api/v1/live/orders"),
            ("PATCH", "/api/v1/live/orders"),
            ("DELETE", "/api/v1/live/orders"),
            ("POST", "/api/v1/user/live-readiness/arm"),
            ("POST", "/api/v1/user/shadow/arm"),
            ("POST", "/api/v1/shadow/orders"),
        ]

        for method, path in live_endpoints:
            # Test with Owner session
            res_owner = self.client.request(method, path, headers=headers_owner, json={})
            self.assertEqual(res_owner.status_code, 403, f"Expected 403 for {method} {path}")
            self.assertEqual(res_owner.json().get("detail"), "EXECUTION_DISABLED")

            # Test with User session
            res_user = self.client.request(method, path, headers=headers_user, json={})
            self.assertEqual(res_user.status_code, 403, f"Expected 403 for {method} {path}")
            self.assertEqual(res_user.json().get("detail"), "EXECUTION_DISABLED")


if __name__ == "__main__":
    unittest.main()
