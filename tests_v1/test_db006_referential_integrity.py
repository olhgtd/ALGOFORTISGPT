"""DB-006 Referential Integrity test suite; all databases and artifacts are isolated in temporary storage."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from dashboard.backend.security_store import SQLiteSecurityStore, SecurityStoreError
from dashboard.backend.governance_store import SQLiteGovernanceStore
from dashboard.backend.paper_service import (
    PaperService,
    GovernanceRejectionError,
    InvalidPaperParameterError,
)


class TestDB006ReferentialIntegrity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="db006_TEST_")
        self.root = Path(self.temp.name)
        self.sec_path = self.root / "security_TEST.sqlite3"
        self.gov_path = self.root / "governance_TEST.sqlite3"

        self.sec = SQLiteSecurityStore(self.sec_path, profile="test", seed_governance=True)
        self.gov = SQLiteGovernanceStore(self.gov_path, profile="test")
        self.paper = PaperService(self.sec)

        # Create active test user
        self.active_user_id = f"USR-{uuid4().hex[:8]}"
        with self.sec._transaction() as cur:
            cur.execute(
                """INSERT INTO users (
                    user_id, role, lifecycle, display_name, created_at_utc, security_state,
                    account_status, activation_status, service_status
                ) VALUES (?, 'USER', 'ACTIVE', 'Active User', '2026-09-15T00:00:00Z', 'CLEAR', 'ACTIVE', 'ACTIVE', 'ACTIVE')""",
                (self.active_user_id,),
            )

        # Create suspended test user
        self.suspended_user_id = f"USR-SUSP-{uuid4().hex[:8]}"
        with self.sec._transaction() as cur:
            cur.execute(
                """INSERT INTO users (
                    user_id, role, lifecycle, display_name, created_at_utc, security_state,
                    account_status, activation_status, service_status
                ) VALUES (?, 'USER', 'SUSPENDED', 'Suspended User', '2026-09-15T00:00:00Z', 'CLEAR', 'SUSPENDED', 'SUSPENDED', 'SUSPENDED')""",
                (self.suspended_user_id,),
            )

        # Create revoked test user
        self.revoked_user_id = f"USR-REV-{uuid4().hex[:8]}"
        with self.sec._transaction() as cur:
            cur.execute(
                """INSERT INTO users (
                    user_id, role, lifecycle, display_name, created_at_utc, security_state,
                    account_status, activation_status, service_status
                ) VALUES (?, 'USER', 'REVOKED', 'Revoked User', '2026-09-15T00:00:00Z', 'CLEAR', 'REVOKED', 'REVOKED', 'REVOKED')""",
                (self.revoked_user_id,),
            )

        # Get valid seeded strategy
        strats = self.sec.list_owner_strategies()
        self.valid_strategy_id = strats[0]["id"] if strats else "s1"
        self.valid_strategy = self.sec.get_owner_strategy(self.valid_strategy_id)
        self.valid_version = str(self.valid_strategy.get("version") or "1.0")

    def tearDown(self):
        self.sec.close()
        self.gov.close()
        self.temp.cleanup()

    # =========================================================================
    # PAPER SESSION TESTS (A - F)
    # =========================================================================

    def test_a_nonexistent_user_rejected_paper_service(self):
        """A. Nonexistent user rejected for new paper session."""
        with self.assertRaises(GovernanceRejectionError) as ctx:
            self.paper.create_session(
                user_id="FABRICATED_GHOST_USER_999",
                strategy_id=self.valid_strategy_id,
            )
        self.assertIn("does not exist", str(ctx.exception).lower())

    def test_b_suspended_or_revoked_user_rejected_paper_service(self):
        """B. Suspended/revoked user rejected for NEW paper session."""
        with self.assertRaises(GovernanceRejectionError) as ctx_susp:
            self.paper.create_session(
                user_id=self.suspended_user_id,
                strategy_id=self.valid_strategy_id,
            )
        self.assertIn("Active authenticated User required", str(ctx_susp.exception))

        with self.assertRaises(GovernanceRejectionError) as ctx_rev:
            self.paper.create_session(
                user_id=self.revoked_user_id,
                strategy_id=self.valid_strategy_id,
            )
        self.assertIn("Active authenticated User required", str(ctx_rev.exception))

    def test_c_nonexistent_strategy_rejected_paper_service(self):
        """C. Nonexistent strategy rejected for new paper session."""
        with self.assertRaises(InvalidPaperParameterError) as ctx:
            self.paper.create_session(
                user_id=self.active_user_id,
                strategy_id="NONEXISTENT_STRAT_999",
            )
        self.assertIn("not registered", str(ctx.exception).lower())

    def test_d_valid_active_user_and_valid_strategy_succeeds_paper(self):
        """D. Valid active user + valid strategy succeeds."""
        ses = self.paper.create_session(
            user_id=self.active_user_id,
            strategy_id=self.valid_strategy_id,
        )
        self.assertIsNotNone(ses)
        self.assertEqual(ses["status"], "INITIALIZED")
        self.assertEqual(ses["user_id"], self.active_user_id)
        self.assertEqual(ses["strategy_id"], self.valid_strategy_id)

    def test_e_direct_store_call_cannot_bypass_paper_checks(self):
        """E. Direct store call cannot bypass user and strategy checks."""
        # Nonexistent user
        with self.assertRaises(SecurityStoreError):
            self.sec.create_paper_session(
                session_id=f"SES-{uuid4().hex}",
                user_id="GHOST_USER",
                strategy_id=self.valid_strategy_id,
                strategy_name="Strat",
                strategy_version="1.0",
                instrument="NIFTY",
                timeframe="1m",
                initial_capital=50000.0,
                policy_snapshot="ATM",
            )

        # Suspended user
        with self.assertRaises(SecurityStoreError):
            self.sec.create_paper_session(
                session_id=f"SES-{uuid4().hex}",
                user_id=self.suspended_user_id,
                strategy_id=self.valid_strategy_id,
                strategy_name="Strat",
                strategy_version="1.0",
                instrument="NIFTY",
                timeframe="1m",
                initial_capital=50000.0,
                policy_snapshot="ATM",
            )

        # Nonexistent strategy
        with self.assertRaises(SecurityStoreError):
            self.sec.create_paper_session(
                session_id=f"SES-{uuid4().hex}",
                user_id=self.active_user_id,
                strategy_id="NONEXISTENT_STRAT_999",
                strategy_name="Strat",
                strategy_version="1.0",
                instrument="NIFTY",
                timeframe="1m",
                initial_capital=50000.0,
                policy_snapshot="ATM",
            )

    def test_f_failed_paper_validation_creates_zero_partial_rows(self):
        """F. Failed validation creates zero partial rows."""
        initial_count = self.sec._conn.execute("SELECT COUNT(*) as c FROM paper_sessions").fetchone()["c"]

        # Attempt multiple failures
        for bad_uid in ["GHOST_1", self.suspended_user_id, self.revoked_user_id]:
            try:
                self.paper.create_session(user_id=bad_uid, strategy_id=self.valid_strategy_id)
            except Exception:
                pass

        for bad_strat in ["BAD_STRAT_1", "BAD_STRAT_2"]:
            try:
                self.paper.create_session(user_id=self.active_user_id, strategy_id=bad_strat)
            except Exception:
                pass

        # Attempt direct store failures
        for _ in range(3):
            try:
                self.sec.create_paper_session(
                    session_id=f"SES-BAD-{uuid4().hex}",
                    user_id="GHOST_USER",
                    strategy_id="NONEXISTENT",
                    strategy_name="S",
                    strategy_version="1.0",
                    instrument="NIFTY",
                    timeframe="1m",
                    initial_capital=50000.0,
                    policy_snapshot="ATM",
                )
            except Exception:
                pass

        final_count = self.sec._conn.execute("SELECT COUNT(*) as c FROM paper_sessions").fetchone()["c"]
        self.assertEqual(initial_count, final_count)

    # =========================================================================
    # BACKTEST RUN TESTS (G - L)
    # =========================================================================

    def _sample_backtest_run(self, run_id: str, user_id: str, strategy_id: str) -> dict:
        return {
            "run_id": run_id,
            "user_id": user_id,
            "strategy_id": strategy_id,
            "strategy_name": "Test Strategy",
            "version": "1.0",
            "instrument": "NIFTY",
            "timeframe": "1m",
            "date_range": "2026-01-05/2026-01-10",
            "initial_capital": 500000.0,
            "net_profit": 12500.0,
            "net_profit_pct": 2.5,
            "win_rate": 62.5,
            "profit_factor": 1.6,
            "sharpe_ratio": 1.4,
            "max_drawdown": -3.2,
            "total_trades": 16,
            "winning_trades": 10,
            "losing_trades": 6,
            "avg_profit_trade": 781.25,
            "avg_win": 1800.0,
            "avg_loss": -916.67,
            "status": "COMPLETED",
            "quality_score": 78.5,
            "policy_snapshot": "ATM 0",
            "data_fingerprint": "mock_data_fp_123",
            "data_source_name": "nse-tick-primary",
            "created_at_utc": "2026-09-15T00:00:00Z",
            "completed_at_utc": "2026-09-15T00:05:00Z",
        }

    def test_g_fabricated_user_reference_rejected_backtest(self):
        """G. Fabricated/nonexistent user reference rejected."""
        run = self._sample_backtest_run(f"RUN-{uuid4().hex}", "NONEXISTENT_USER_999", self.valid_strategy_id)
        with self.assertRaises(SecurityStoreError) as ctx:
            self.sec.save_backtest_run(run)
        self.assertIn("not a registered user", str(ctx.exception))

    def test_h_fabricated_strategy_reference_rejected_backtest(self):
        """H. Fabricated/nonexistent strategy reference rejected."""
        run = self._sample_backtest_run(f"RUN-{uuid4().hex}", self.active_user_id, "NONEXISTENT_STRAT_999")
        with self.assertRaises(SecurityStoreError) as ctx:
            self.sec.save_backtest_run(run)
        self.assertIn("not a registered strategy", str(ctx.exception))

    def test_i_valid_user_and_valid_strategy_succeeds_backtest(self):
        """I. Valid user + valid strategy succeeds."""
        run_id = f"RUN-{uuid4().hex}"
        run = self._sample_backtest_run(run_id, self.active_user_id, self.valid_strategy_id)
        saved = self.sec.save_backtest_run(run)
        self.assertIsNotNone(saved)
        self.assertEqual(saved["run_id"], run_id)
        self.assertEqual(saved["user_id"], self.active_user_id)
        self.assertEqual(saved["strategy_id"], self.valid_strategy_id)

        # Retrieve and verify
        retrieved = self.sec.get_backtest_run(run_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["status"], "COMPLETED")
        self.assertEqual(retrieved["net_profit"], 12500.0)

    def test_j_direct_store_call_cannot_create_orphan_backtest(self):
        """J. Direct store call cannot create orphan."""
        initial_count = self.sec._conn.execute("SELECT COUNT(*) as c FROM backtest_runs").fetchone()["c"]

        # Attempt invalid user
        try:
            self.sec.save_backtest_run(
                self._sample_backtest_run(f"RUN-ORPH-{uuid4().hex}", "GHOST_USER", self.valid_strategy_id)
            )
        except SecurityStoreError:
            pass

        # Attempt invalid strategy
        try:
            self.sec.save_backtest_run(
                self._sample_backtest_run(f"RUN-ORPH-{uuid4().hex}", self.active_user_id, "GHOST_STRAT")
            )
        except SecurityStoreError:
            pass

        # Attempt both invalid
        try:
            self.sec.save_backtest_run(
                self._sample_backtest_run(f"RUN-ORPH-{uuid4().hex}", "GHOST_USER", "GHOST_STRAT")
            )
        except SecurityStoreError:
            pass

        final_count = self.sec._conn.execute("SELECT COUNT(*) as c FROM backtest_runs").fetchone()["c"]
        self.assertEqual(initial_count, final_count)

    def test_k_user_suspended_after_submission_historical_result_persistable(self):
        """K. User valid at submission but suspended before result persistence:
        historical result remains persistable."""
        # Create a new user that starts ACTIVE
        transient_user_id = f"USR-TRANSIENT-{uuid4().hex[:8]}"
        with self.sec._transaction() as cur:
            cur.execute(
                """INSERT INTO users (
                    user_id, role, lifecycle, display_name, created_at_utc, security_state,
                    account_status, activation_status, service_status
                ) VALUES (?, 'USER', 'ACTIVE', 'Transient User', '2026-09-15T00:00:00Z', 'CLEAR', 'ACTIVE', 'ACTIVE', 'ACTIVE')""",
                (transient_user_id,),
            )

        # Simulate: job submitted while ACTIVE, then user suspended before asynchronous completion
        with self.sec._transaction() as cur:
            cur.execute(
                "UPDATE users SET lifecycle='SUSPENDED', account_status='SUSPENDED' WHERE user_id = ?",
                (transient_user_id,),
            )

        # Worker completes and persists the historical result
        run_id = f"RUN-HIST-{uuid4().hex}"
        run = self._sample_backtest_run(run_id, transient_user_id, self.valid_strategy_id)
        saved = self.sec.save_backtest_run(run)

        self.assertIsNotNone(saved)
        self.assertEqual(saved["run_id"], run_id)
        self.assertEqual(saved["user_id"], transient_user_id)
        self.assertEqual(saved["status"], "COMPLETED")

    def test_l_strategy_archived_after_submission_historical_result_persistable(self):
        """L. Strategy valid at submission but archived/lifecycle-changed before result persistence:
        historical result remains persistable."""
        # Create a registered strategy
        transient_strat_id = f"strat-{uuid4().hex[:6]}"
        with self.sec._transaction() as cur:
            cur.execute(
                """INSERT INTO owner_strategies (
                    strategy_id, id, name, version, stage, quality, evidence_attached, pnl, note, author,
                    conformance_status, admin_status, updated_at_utc
                ) VALUES (?, ?, 'Transient Strategy', '1.0', 'STAGING', 75.0, 1, '0.0%', '', 'OWNER-001',
                          'CONFORMANT', 'ACTIVE', '2026-09-15T00:00:00Z')""",
                (transient_strat_id, transient_strat_id),
            )

        # Simulate: job submitted, then strategy archived/suspended in governance
        with self.sec._transaction() as cur:
            cur.execute(
                """UPDATE owner_strategies SET
                    admin_status='SUSPENDED',
                    stage='ARCHIVED',
                    backtest_owner_allowance='HOLD',
                    backtest_owner_hold_reason='Strategy archived by Owner'
                WHERE strategy_id = ?""",
                (transient_strat_id,),
            )

        # Worker completes and persists the historical result
        run_id = f"RUN-HIST-STRAT-{uuid4().hex}"
        run = self._sample_backtest_run(run_id, self.active_user_id, transient_strat_id)
        saved = self.sec.save_backtest_run(run)

        self.assertIsNotNone(saved)
        self.assertEqual(saved["run_id"], run_id)
        self.assertEqual(saved["strategy_id"], transient_strat_id)
        self.assertEqual(saved["status"], "COMPLETED")


if __name__ == "__main__":
    unittest.main()
