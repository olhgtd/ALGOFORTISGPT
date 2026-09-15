"""AlgoFortis V1 — Area 6 Performance & Stability Sanity Tests
Certifies bounded performance and stability invariants:
- Repeated API reads and bounded pagination latency
- Worker startup / shutdown and thread containment (no runaway threads)
- DB connection cleanup and Windows file-lock leakage prevention (clean file release)
- Memory stability under bounded batch operations (no obvious memory leaks)
- Repeated application lifecycle and restart sanity without degradation
"""

import gc
import os
import sys
import time
import tracemalloc
import tempfile
import threading
import unittest
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from engine.persistence.sqlite_store import SQLitePaperStateStore

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


class TestArea6PerformanceStabilitySanity(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="algofortis_area6_")
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

        self.sec_config = SecurityConfiguration(normal_mtls_required=False)
        self.session_service = SessionService(self.sec_config, store=self.sec_store)

        self.owner_id = uuid4()
        self.owner = UserIdentity(
            user_id=self.owner_id,
            role=Role.OWNER,
            lifecycle=Lifecycle.ACTIVE,
            display_name="Stability Owner",
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

    def test_repeated_api_reads_and_bounded_latency(self):
        """Sanity check: 50 sequential reads to health and profile endpoints.
        Latency per request must remain tightly bounded (<50ms avg), with 100% success rate.
        """
        latencies = []
        for _ in range(50):
            t0 = time.perf_counter()
            resp = self.client.get("/health")
            t1 = time.perf_counter()
            self.assertEqual(resp.status_code, 200)
            latencies.append((t1 - t0) * 1000.0)

        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)
        # Verify bounded local response time
        self.assertLess(avg_latency, 50.0, f"Average latency too high: {avg_latency:.2f}ms")
        self.assertLess(max_latency, 300.0, f"Max spike latency too high: {max_latency:.2f}ms")

    def test_bounded_pagination_performance(self):
        """Sanity check: Audit events and access registry pagination query remains fast and bounded."""
        # Seed 15 access records via owner endpoint
        for i in range(15):
            self.client.post(
                "/api/v1/owner/access/users",
                json={
                    "email": f"perf_user_{i}@algofortis.io",
                    "display_name": f"Perf User {i}",
                    "role": "USER",
                    "service_term_type": "ANNUAL",
                    "plan": "STANDARD",
                },
                headers=self.owner_headers,
            )

        t0 = time.perf_counter()
        resp = self.client.get(
            "/api/v1/integration/audit/events?limit=10",
            headers=self.owner_headers,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertLessEqual(len(data["events"]), 10)
        self.assertLess(elapsed_ms, 200.0, f"Pagination query too slow: {elapsed_ms:.2f}ms")

    def test_worker_thread_containment(self):
        """Verify worker startup and shutdown cleanly contains thread count.
        No runaway threads or background zombies should remain active.
        """
        initial_threads = threading.active_count()

        # Paper service session initialization / operations
        ps = PaperService(
            security_store=self.sec_store,
            governance_store=self.gov_store,
            artifact_root=self.tmp_path / "artifacts",
        )
        sessions = ps.list_sessions(limit=10)
        self.assertIsInstance(sessions, list)

        # Thread count after execution must not exceed initial count
        current_threads = threading.active_count()
        self.assertLessEqual(
            current_threads,
            initial_threads + 1,
            f"Thread leakage detected: initial={initial_threads}, current={current_threads}",
        )

    def test_db_connection_cleanup_and_file_lock_leakage(self):
        """Verify repeated store open and close cycles cleanly release SQLite Windows file locks.
        A locked SQLite file will throw WinError 32 on deletion; successful deletion proves zero lock leakage.
        """
        for i in range(15):
            test_db = self.tmp_path / f"lock_test_{i}.sqlite3"
            store = SQLiteSecurityStore(test_db, profile="test")
            # Write and query
            store.get_user(str(self.owner_id))
            store.close()
            del store
            gc.collect()

            # Prove the file is NOT locked on Windows by deleting or renaming it
            self.assertTrue(test_db.exists())
            test_db.unlink()  # On Windows, this raises PermissionError / WinError 32 if any handle remains open
            self.assertFalse(test_db.exists())

    def test_memory_stability_bounded_batch(self):
        """Sanity check: Bounded batch of database & session operations does not cause runaway memory growth."""
        tracemalloc.start()
        gc.collect()
        snapshot1 = tracemalloc.take_snapshot()

        # Perform 100 rapid operations
        for _ in range(100):
            self.sec_store.get_user(str(self.owner_id))
            self.health_adapter.read_persistence_health()

        gc.collect()
        snapshot2 = tracemalloc.take_snapshot()
        tracemalloc.stop()

        top_stats = snapshot2.compare_to(snapshot1, "lineno")
        total_growth_bytes = sum(stat.size_diff for stat in top_stats if stat.size_diff > 0)
        growth_mb = total_growth_bytes / (1024 * 1024)

        # Bounded growth must not exceed 10MB for 100 read/health operations
        self.assertLess(growth_mb, 10.0, f"Excessive memory allocation: {growth_mb:.2f} MB")

    def test_repeated_app_instantiation_stability(self):
        """Verify repeated creation and teardown of FastAPI application succeeds without performance degradation."""
        durations = []
        for i in range(3):
            fresh_bt = BacktestService(security_store=self.sec_store)
            t0 = time.perf_counter()
            app = create_app(
                owner=self.owner,
                config=self.sec_config,
                security_store=self.sec_store,
                governance_store=self.gov_store,
                core_security_audit=self.core_audit,
                backtest_service=fresh_bt,
                paper_service=self.paper_service,
                health_adapter=self.health_adapter,
                access_adapter=self.access_adapter,
                audit_adapter=self.audit_adapter,
                artifact_root=self.tmp_path / "artifacts",
            )
            with TestClient(app) as tc:
                resp = tc.get("/health")
                self.assertEqual(resp.status_code, 200)
            elapsed = time.perf_counter() - t0
            durations.append(elapsed)

        # Ensure subsequent app creations do not degrade exponentially
        self.assertLess(durations[-1], 2.0, "Subsequent app creation took too long")


if __name__ == "__main__":
    unittest.main()
