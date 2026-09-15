"""DB-004 failure/restart evidence; every database and artifact is temporary."""
import hashlib
import sqlite3
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from dashboard.backend.domain import Lifecycle, Role, StrategyStage, UserIdentity
from dashboard.backend.governance_store import SQLiteGovernanceStore
from dashboard.backend.security_store import SQLiteSecurityStore
from dashboard.backend.services import StrategyService, StrategyVersion
from dashboard.backend.strategy_projection import StrategyProjectionPending


SOURCE = '''from engine.strategy.base import Signal, StrategySignalGenerator
class TestStrategy(StrategySignalGenerator):
    interface_version = "1.0"
    state_schema = {"count": 0}
    def generate_signal(self, data, state):
        return Signal("HOLD", 0.0, {})
'''


class TestDB004StrategyProjection(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="db004_TEST_")
        self.root = Path(self.temp.name)
        self.owner = UserIdentity(uuid4(), Role.OWNER, Lifecycle.ACTIVE, "DB004 Test")
        self.open_stores()
        self.sec.ensure_user(user_id=self.owner.user_id, role="OWNER", lifecycle="ACTIVE", display_name="DB004 Test")

    def open_stores(self):
        self.gov = SQLiteGovernanceStore(self.root / "governance_TEST.sqlite3", profile="test")
        self.sec = SQLiteSecurityStore(self.root / "security_TEST.sqlite3", profile="test", seed_governance=False)
        self.service = StrategyService(artifact_root=self.root / "artifacts", governance_store=self.gov, security_store=self.sec)

    def tearDown(self):
        self.gov.close()
        self.sec.close()
        self.temp.cleanup()

    def submit(self):
        return self.service.submit(owner=self.owner, source=SOURCE, protective_policy_identity=None)[0]

    def seed_version(self, *, strategy_id=None, stage=StrategyStage.BACKTEST_ELIGIBLE, archived=False):
        sid, vid = strategy_id or uuid4(), uuid4()
        artifact = self.root / "artifacts" / f"usr_{self.owner.user_id}" / "strategies" / str(sid) / f"{vid}.py"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(SOURCE.encode("utf-8"))
        version = StrategyVersion(sid, vid, self.owner.user_id, hashlib.sha256(SOURCE.encode()).hexdigest(), str(artifact), stage, archived)
        self.gov.save_version(dict(strategy_id=str(sid), version_id=str(vid), owner_id=str(self.owner.user_id),
                                   source_sha256=version.source_sha256, artifact_path=str(artifact), stage=stage.value,
                                   archived=int(archived), protective_policy_identity=None, created_at_utc="2026-01-01T00:00:00Z"))
        return version

    def snapshot(self):
        return tuple(tuple(tuple(r) for r in store._conn.execute(f"SELECT * FROM {table} ORDER BY 1"))
                     for store, table in ((self.gov, "strategy_versions"), (self.sec, "owner_strategies"), (self.sec, "user_strategy_assignments")))

    def assert_projected(self, version):
        self.assertEqual(self.sec.get_owner_strategy(str(version.strategy_id))["version"], str(version.version_id))
        self.assertEqual(self.sec.get_strategy_assignment(self.owner.user_id, str(version.strategy_id))["version_id"], str(version.version_id))

    def fail_inside_security_transaction(self):
        with self.sec._transaction() as cur:
            cur.execute("""CREATE TRIGGER db004_failure BEFORE INSERT ON user_strategy_assignments
                           BEGIN SELECT RAISE(ABORT, 'TEST ONLY failure after catalog write'); END""")

    def app(self):
        from dashboard.backend.api import create_app
        app = create_app(owner=self.owner, security_store=self.sec, governance_store=self.gov, artifact_root=self.root / "artifacts")
        return app

    def client(self, app, stack):
        from fastapi.testclient import TestClient
        for obj in (app.state.backtest_service.jobs, app.state.walkforward_service):
            if obj is not None:
                stack.enter_context(patch.object(obj, "start"))
                stack.enter_context(patch.object(obj, "shutdown"))
        return stack.enter_context(TestClient(app))

    def test_a_both_stores_commit(self):
        version = self.submit()
        self.assert_projected(version)
        self.assertEqual(self.gov.load_version(version.version_id)["stage"], "ADDED")

    def test_b_first_failure_repaired_once(self):
        real = self.sec.register_backtest_artifact
        calls = []
        def transient(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise sqlite3.OperationalError("TEST ONLY")
            return real(**kwargs)
        with patch.object(self.sec, "register_backtest_artifact", side_effect=transient):
            version = self.submit()
        self.assertEqual(len(calls), 2)
        self.assert_projected(version)

    def test_c_double_failure_retains_governance_and_rolls_back_security(self):
        self.fail_inside_security_transaction()
        with self.assertRaises(StrategyProjectionPending) as caught:
            self.submit()
        detail = caught.exception.detail
        self.assertTrue(detail["governance_persisted"])
        self.assertIsNotNone(self.gov.load_version(detail["version_id"]))
        self.assertIsNone(self.sec.get_owner_strategy(detail["strategy_id"]))
        self.assertEqual(self.sec._conn.execute("SELECT COUNT(*) FROM user_strategy_assignments").fetchone()[0], 0)
        self.assertEqual(self.gov._conn.execute("SELECT COUNT(*) FROM strategy_versions").fetchone()[0], 1)

    def test_d_real_application_startup_repairs_after_restart(self):
        with patch.object(self.sec, "register_backtest_artifact", side_effect=sqlite3.OperationalError("TEST ONLY")):
            with self.assertRaises(StrategyProjectionPending):
                self.submit()
        self.gov.close()
        self.sec.close()
        self.open_stores()
        app = self.app()
        with ExitStack() as stack:
            self.client(app, stack)
            self.assertEqual(self.sec._conn.execute("SELECT COUNT(*) FROM owner_strategies").fetchone()[0], 1)
            self.assertEqual(self.sec._conn.execute("SELECT COUNT(*) FROM user_strategy_assignments").fetchone()[0], 1)

    def test_e_second_reconciliation_is_exact_noop(self):
        self.seed_version()
        self.assertEqual(self.service._projection.reconcile_startup(), 1)
        before = self.snapshot()
        self.assertEqual(self.service._projection.reconcile_startup(), 0)
        self.assertEqual(before, self.snapshot())

    def test_f_stale_registry_repairs_to_sole_current_governance_version(self):
        current = self.seed_version()
        self.sec.register_backtest_artifact(strategy_id=str(current.strategy_id), version_id="stale", name="Existing", owner_id=str(self.owner.user_id))
        self.assertEqual(self.service._projection.reconcile_startup(), 1)
        self.assert_projected(current)

    def test_g_archived_history_never_becomes_current(self):
        old = self.seed_version(stage=StrategyStage.ARCHIVED, archived=True)
        current = self.seed_version(strategy_id=old.strategy_id)
        self.sec.register_backtest_artifact(strategy_id=str(old.strategy_id), version_id=str(old.version_id), name="Old", owner_id=str(self.owner.user_id))
        self.service._projection.reconcile_startup()
        self.assert_projected(current)
        self.assertEqual(self.gov.load_version(old.version_id)["archived"], 1)

    def test_g_archived_or_unsupported_stage_not_created(self):
        archived = self.seed_version(stage=StrategyStage.ARCHIVED, archived=True)
        ineligible = self.seed_version(stage=StrategyStage.VALIDATED)
        self.assertEqual(self.service._projection.reconcile_startup(), 0)
        self.assertIsNone(self.sec.get_owner_strategy(str(archived.strategy_id)))
        self.assertIsNone(self.sec.get_owner_strategy(str(ineligible.strategy_id)))
        self.service._persist(archived)
        self.assertIsNone(self.sec.get_owner_strategy(str(archived.strategy_id)))

    def test_g_valid_registry_reference_preserved_with_multiple_versions(self):
        current = self.seed_version()
        self.seed_version(strategy_id=current.strategy_id)
        self.sec.register_backtest_artifact(strategy_id=str(current.strategy_id), version_id=str(current.version_id), name="Current", owner_id=str(self.owner.user_id))
        before = self.snapshot()
        self.assertEqual(self.service._projection.reconcile_startup(), 0)
        self.assertEqual(before, self.snapshot())

    def test_g_ambiguous_current_fails_closed(self):
        first = self.seed_version()
        self.seed_version(strategy_id=first.strategy_id)
        with self.assertRaises(StrategyProjectionPending) as caught:
            self.service._projection.reconcile_startup()
        self.assertEqual(caught.exception.detail["reason"], "AMBIGUOUS_CURRENT_VERSION")
        self.assertIsNone(self.sec.get_owner_strategy(str(first.strategy_id)))

    def test_h_visibility_holds_and_revocation_survive_repair(self):
        version = self.seed_version()
        self.sec.register_backtest_artifact(strategy_id=str(version.strategy_id), version_id="stale", name="Owner name", owner_id=str(self.owner.user_id))
        with self.sec._transaction() as cur:
            cur.execute("UPDATE owner_strategies SET visibility='GLOBAL', admin_status='SUSPENDED', backtest_owner_allowance='HOLD', paper_owner_allowance='HOLD', live_owner_allowance='HOLD'")
        self.sec.revoke_strategy_assignment(user_id=self.owner.user_id, strategy_id=str(version.strategy_id))
        before = dict(self.sec._conn.execute("SELECT * FROM owner_strategies").fetchone())
        self.service._projection.reconcile_startup()
        after = dict(self.sec._conn.execute("SELECT * FROM owner_strategies").fetchone())
        for field in before.keys() - {"version", "updated_at_utc"}:
            self.assertEqual(before[field], after[field], field)
        self.assert_projected(version)
        self.assertEqual(self.sec.get_strategy_assignment(self.owner.user_id, str(version.strategy_id))["assignment_status"], "REVOKED")

    def test_i_listing_does_not_repair_or_write(self):
        self.seed_version()
        before = self.snapshot()
        changes = (self.gov._conn.total_changes, self.sec._conn.total_changes)
        self.service.list_user_strategies(self.owner.user_id, self.owner.role)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(changes, (self.gov._conn.total_changes, self.sec._conn.total_changes))

    def test_http_persistent_failure_is_safe_503(self):
        app = self.app()
        route = next(r for r in app.routes if getattr(r, "path", None) == "/api/v1/strategies" and "POST" in r.methods)
        app.dependency_overrides[route.dependant.dependencies[0].call] = lambda: SimpleNamespace(user=self.owner)
        with ExitStack() as stack:
            client = self.client(app, stack)
            stack.enter_context(patch.object(self.sec, "register_backtest_artifact", side_effect=sqlite3.OperationalError("SECRET source password")))
            with self.assertLogs("dashboard.backend.strategy_projection", level="WARNING") as logs:
                response = client.post("/api/v1/strategies", json={"source": SOURCE})
            self.assertEqual(response.status_code, 503, response.text)
            self.assertEqual(response.json()["detail"]["code"], "STRATEGY_PROJECTION_PENDING")
            self.assertNotIn("SECRET", response.text + str(logs.output))
            self.assertNotIn(SOURCE, response.text + str(logs.output))

    def test_startup_failure_precedes_workers(self):
        self.seed_version()
        app = self.app()
        from fastapi.testclient import TestClient
        with patch.object(self.sec, "register_backtest_artifact", side_effect=sqlite3.OperationalError("TEST ONLY")), patch.object(app.state.backtest_service.jobs, "start") as start:
            with self.assertRaises(StrategyProjectionPending):
                with TestClient(app):
                    self.fail("unresolved startup must not become ready")
            start.assert_not_called()

    def test_startup_is_bounded_without_partial_repair(self):
        self.seed_version()
        self.seed_version()
        with self.assertRaises(StrategyProjectionPending) as caught:
            self.service._projection.reconcile_startup(limit=1)
        self.assertEqual(caught.exception.detail["reason"], "STARTUP_LIMIT_EXCEEDED")
        self.assertEqual(self.sec._conn.execute("SELECT COUNT(*) FROM owner_strategies").fetchone()[0], 0)

    def test_missing_assignment_repaired_without_catalog_policy_loss(self):
        version = self.submit()
        with self.sec._transaction() as cur:
            cur.execute("DELETE FROM user_strategy_assignments")
        self.service._projection.reconcile_startup()
        self.assert_projected(version)

    def test_artifact_tamper_prevents_restart_repair(self):
        version = self.seed_version()
        Path(version.source_artifact).write_text("TAMPERED", encoding="utf-8")
        with self.assertRaises(StrategyProjectionPending):
            self.service._projection.reconcile_startup()
        self.assertIsNone(self.sec.get_owner_strategy(str(version.strategy_id)))

    def test_safety_and_schema_unchanged(self):
        self.seed_version()
        self.service._projection.reconcile_startup()
        self.assertEqual(self.sec._conn.execute("SELECT value FROM security_metadata WHERE key='live_global_hold'").fetchone()[0], "true")
        for store, metadata in ((self.gov, "governance_metadata"), (self.sec, "security_metadata")):
            self.assertEqual(store._conn.execute(f"SELECT value FROM {metadata} WHERE key='schema_version'").fetchone()[0], "2")
            self.assertEqual(store._conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(store._conn.execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main()
