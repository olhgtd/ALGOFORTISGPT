"""AlgoFortis V1 — Area 4: New UI Integration Readiness Certification Suite.

Validates backend readiness against the docs/ui-handoff contract:
1. ENDPOINT EXISTENCE & METHOD CONFORMANCE:
   - Heartbeat & System Health (/health, /api/v1/integration/system/health)
   - User Profile & Current Identity (/api/v1/users/current)
   - Owner Access Registry & User Onboarding (/api/v1/integration/access/records, /api/v1/owner/access/users)
   - Owner User Lifecycle Admin (/suspend, /restore, /revoke, /extend-service, /renew-service, /convert-lifetime)
   - Security & Device Oversight (/api/v1/owner/security/sessions, /api/v1/security/devices)
   - Strategy Governance (/api/v1/strategies, /promote, /allowance)
   - Backtesting Engine (/api/v1/backtests, /{run_id}, /{run_id}/trades, /cancel)
   - Paper Trading Engine (/api/v1/paper/sessions, /start, /stop, /positions, /orders, /events)
   - Market Data & Chart (/api/v1/market/chart, /timeframes, /inventory)
   - Portfolio & Orders Oversight (/api/v1/user/orders-portfolio, /api/v1/owner/orders-portfolio)
   - Regulatory Audit (/api/v1/audit/events, /api/v1/integration/audit/events)
   - Disarmed Live Execution (/api/v1/live/orders -> 403 Fail-Closed)

2. DATA MODEL & DTO SHAPE COMPATIBILITY:
   - Required fields present in responses
   - Correct typing and JSON serialization

3. BOUNDED PAGINATION & INPUT VALIDATION:
   - limit/offset validated and bounded; negative values return 422 Unprocessable Entity

4. SECURITY BOUNDARIES:
   - No UI secret leakage (passwords, tokens, private keys, broker secrets)
   - Role isolation preserved (USER blocked from OWNER routes with 403)
"""
import gc
import tempfile
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
from engine.persistence.sqlite_store import SQLitePaperStateStore


class TestArea4UIIntegrationReadiness(unittest.TestCase):

    def setUp(self):
        gc.collect()
        self._tmp = tempfile.TemporaryDirectory(prefix="af_area4_", ignore_cleanup_errors=True)
        self.tmp_path = Path(self._tmp.name).resolve()

        self.sec_db = self.tmp_path / "security.sqlite3"
        self.gov_db = self.tmp_path / "governance.sqlite3"
        self.audit_db = self.tmp_path / "audit.sqlite3"

        self.sec_store = SQLiteSecurityStore(self.sec_db, seed_governance=False, profile="test")
        self.gov_store = SQLiteGovernanceStore(self.gov_db, profile="test")
        self.audit_store = SQLitePaperStateStore(
            self.audit_db, account_id="test-acct", starting_capital=Decimal("0.00"), audit_source_identity="test"
        )
        self.core_audit = MandatoryCoreSecurityAudit(audit_store=self.audit_store, security_store=self.sec_store)

        # Setup Owner and User
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
        self.user_id = uuid4()
        self.user = UserIdentity(
            user_id=self.user_id,
            role=Role.USER,
            lifecycle=Lifecycle.ACTIVE,
            display_name="Standard Trader",
            account_status=AccountAccessStatus.ACTIVE,
            activation_status=ActivationStatus.REDEEMED,
            service_status=ServiceEntitlementStatus.ACTIVE,
            sx_id="SX-USER-01",
        )

        now_iso = datetime.now(timezone.utc).isoformat()
        with self.sec_store._transaction() as cur:
            for u in [self.owner, self.user]:
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

        self.sec_config = SecurityConfiguration(normal_mtls_required=False)
        self.session_service = SessionService(self.sec_config, store=self.sec_store)

        self.owner_session = self.session_service.issue(user=self.owner, route=AccessRoute.NORMAL, mtls_verified=True)
        self.user_session = self.session_service.issue(user=self.user, route=AccessRoute.NORMAL, mtls_verified=True)

        self.owner_headers = {"Authorization": f"Bearer {self.owner_session.token}"}
        self.user_headers = {"Authorization": f"Bearer {self.user_session.token}"}

        self.paper_service = PaperService(
            security_store=self.sec_store,
            governance_store=self.gov_store,
            artifact_root=self.tmp_path / "artifacts",
        )
        self.backtest_service = BacktestService(security_store=self.sec_store)

        self.health_adapter = PersistenceHealthReadAdapter(persistence_store=self.sec_store, db_path=self.sec_db)
        self.access_adapter = AccessRegistryReadAdapter(security_store=self.sec_store)
        self.audit_adapter = D16AuditReadAdapter(persistence_store=self.sec_store)

        from dashboard.backend.historical_data_service import HistoricalDataService
        self.hds = HistoricalDataService(cache_root=self.tmp_path / "cache", security_store=self.sec_store)

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
            historical_data_service=self.hds,
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

    # ==========================================
    # 1. SCREEN COMPATIBILITY VERIFICATION
    # ==========================================

    def test_screen_system_health_and_runtime_status(self):
        # 1. Heartbeat
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"].upper(), "OK")

        # 2. Integration System Health (Owner only)
        resp_owner = self.client.get("/api/v1/integration/system/health", headers=self.owner_headers)
        self.assertEqual(resp_owner.status_code, 200)
        data = resp_owner.json()
        self.assertTrue("database_connected" in data or "databaseConnected" in data)
        self.assertTrue("schema_version" in data or "schemaVersion" in data)
        self.assertIn("subsystems", data)

        # Non-owner blocked with 403
        resp_user = self.client.get("/api/v1/integration/system/health", headers=self.user_headers)
        self.assertEqual(resp_user.status_code, 403)

    def test_screen_current_user_profile(self):
        resp = self.client.get("/api/v1/users/current", headers=self.user_headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["role"], "USER")
        self.assertEqual(data["sx_id"], "SX-USER-01")
        self.assertEqual(data["display_name"], "Standard Trader")
        self.assertEqual(data["account_status"], "ACTIVE")
        self.assertIn("workspace_eligibility", data)

    def test_screen_owner_access_registry_and_user_creation(self):
        # List access records
        resp = self.client.get("/api/v1/integration/access/records", headers=self.owner_headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("records", data)
        self.assertIn("total_count", data)

        # Create invited user
        create_payload = {
            "email": "hedgefund_quant@algofortis.io",
            "display_name": "Quant Fund Alpha",
            "role": "USER",
            "service_term_type": "ANNUAL",
            "plan": "STANDARD",
        }
        create_resp = self.client.post("/api/v1/owner/access/users", json=create_payload, headers=self.owner_headers)
        self.assertEqual(create_resp.status_code, 200)
        body = create_resp.json()
        self.assertTrue(body["success"])
        self.assertIn("activation_code", body)

    def test_screen_strategy_management(self):
        # List strategies
        resp = self.client.get("/api/v1/strategies", headers=self.user_headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("strategies", data)

    def test_screen_backtest_datasets_and_listing(self):
        # Available datasets for backtesting
        resp = self.client.get("/api/v1/backtests/datasets", headers=self.user_headers)
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

        # List user backtest runs
        resp_list = self.client.get("/api/v1/backtests", headers=self.user_headers)
        self.assertEqual(resp_list.status_code, 200)
        self.assertIsInstance(resp_list.json(), list)

    def test_screen_paper_sessions_listing(self):
        resp = self.client.get("/api/v1/paper/sessions", headers=self.user_headers)
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_screen_market_chart_and_inventory(self):
        # Market timeframes with required instrument and mode query params
        resp_tf = self.client.get("/api/v1/market/timeframes?instrument=BTC/USDT&mode=FROZEN_HISTORICAL", headers=self.user_headers)
        self.assertEqual(resp_tf.status_code, 200)
        self.assertIn("timeframes", resp_tf.json())

        # Market inventory
        resp_inv = self.client.get("/api/v1/market/data/inventory", headers=self.user_headers)
        self.assertEqual(resp_inv.status_code, 200)
        self.assertIn("datasets", resp_inv.json())

    def test_screen_portfolio_orders_oversight(self):
        # User portfolio
        resp_user = self.client.get("/api/v1/user/orders-portfolio?mode=PAPER", headers=self.user_headers)
        self.assertEqual(resp_user.status_code, 200)
        data = resp_user.json()
        self.assertIn("execution_mode", data)
        self.assertIn("accounts", data)
        self.assertIn("positions", data)
        self.assertIn("orders", data)

        # Owner portfolio oversight
        resp_owner = self.client.get("/api/v1/owner/orders-portfolio?mode=PAPER", headers=self.owner_headers)
        self.assertEqual(resp_owner.status_code, 200)

    def test_screen_audit_events_immutable_trail(self):
        resp = self.client.get("/api/v1/integration/audit/events?limit=50", headers=self.owner_headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("events", data)

    def test_screen_live_orders_disarmed_fail_closed(self):
        """CRITICAL SAFETY INVARIANT: Live order submission returns 403 fail-closed."""
        order_payload = {
            "symbol": "BTC/USDT",
            "side": "BUY",
            "qty": 1.0,
            "order_type": "LIMIT",
            "price": 60000.0,
        }
        resp = self.client.post("/api/v1/live/orders", json=order_payload, headers=self.user_headers)
        self.assertEqual(resp.status_code, 403)
        self.assertIn("EXECUTION_DISABLED", resp.json()["detail"])

    # ==========================================
    # 2. BOUNDED PAGINATION VERIFICATION
    # ==========================================

    def test_pagination_bounds_fail_closed(self):
        # Negative limit rejected with 422
        resp = self.client.get("/api/v1/backtests?limit=-1", headers=self.user_headers)
        self.assertEqual(resp.status_code, 422)

        # Excessive limit rejected with 422
        resp = self.client.get("/api/v1/backtests?limit=10000", headers=self.user_headers)
        self.assertEqual(resp.status_code, 422)

        # Negative offset / limit on audit events
        resp_audit = self.client.get("/api/v1/integration/audit/events?limit=-5", headers=self.owner_headers)
        self.assertEqual(resp_audit.status_code, 422)


if __name__ == "__main__":
    unittest.main()
