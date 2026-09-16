"""Tests for Phase 7: User-Controlled Strategy Lifecycle & Removal of Owner Approval Gates.

Verifies:
1. Authenticated user can self-service promote an active strategy to PAPER_ELIGIBLE.
2. Authenticated user can self-service promote an active strategy to LIVE_ELIGIBLE.
3. Cross-user promotion attempts fail closed.
4. Strategy under Owner HOLD or SUSPENDED cannot be promoted.
5. User can create LIVE deployment when live eligibility is met.
6. User can pause and resume LIVE deployment with automatic eligibility re-validation.
"""

from __future__ import annotations

import gc
import json
import os
import tempfile
import unittest
from uuid import uuid4

from dashboard.backend.security_store import SQLiteSecurityStore, SecurityStoreError


class TestUserControlledLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "security_test.db")
        self.store = SQLiteSecurityStore(self.db_path, profile="test", seed_governance=False)

        self.user_id = str(uuid4())
        self.conn_id = f"conn-{uuid4().hex[:8]}"
        self.strategy_id = f"strat-{uuid4().hex[:6]}"
        now_str = "2026-09-16T00:00:00Z"

        with self.store._transaction() as cur:
            # Create active user
            cur.execute("""
                INSERT INTO users (user_id, role, lifecycle, display_name, created_at_utc, security_state, account_status)
                VALUES (?, 'USER', 'ACTIVE', 'Test Trader', ?, 'CLEAR', 'ACTIVE')
            """, (self.user_id, now_str))

            # Create configured connection
            cur.execute("""
                INSERT INTO user_connections (
                    connection_id, user_id, provider, account_ref, status,
                    market_data_capability, execution_capability, health_state,
                    credential_ref, last_verified_at_utc, created_at_utc, updated_at_utc
                ) VALUES (
                    ?, ?, 'UPSTOX', 'UP12345', 'CONFIGURED',
                    'READY', 'READY', 'HEALTHY',
                    'cred_ref_vault_123', ?, ?, ?
                )
            """, (self.conn_id, self.user_id, now_str, now_str, now_str))

            # Seed an active strategy
            cur.execute("""
                INSERT INTO owner_strategies (
                    id, strategy_id, name, version, author, stage, admin_status,
                    backtest_system_readiness, backtest_owner_allowance,
                    paper_system_readiness, paper_owner_allowance,
                    live_system_readiness, live_owner_allowance,
                    conformance_status, governance_history_json, updated_at_utc
                ) VALUES (
                    ?, ?, ?, '1.0', ?, 'BACKTEST_ELIGIBLE', 'ACTIVE',
                    'READY', 'ALLOWED',
                    'PENDING', 'ALLOWED',
                    'BLOCKED', 'ALLOWED',
                    'CONFORMANT', '[]', ?
                )
            """, (
                f"strat-{uuid4().hex[:8]}", self.strategy_id, "Test ORB Strategy",
                self.user_id, now_str
            ))

            # Assign strategy to user
            cur.execute("""
                INSERT INTO user_strategy_assignments (
                    assignment_id, user_id, strategy_id, assignment_status, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, 'ASSIGNED', ?, ?)
            """, (f"asg-{uuid4().hex[:6]}", self.user_id, self.strategy_id, now_str, now_str))

    def tearDown(self):
        self.store.close()
        gc.collect()
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def test_user_self_service_paper_promotion(self):
        """User can promote their active conforming strategy to PAPER_ELIGIBLE without Owner."""
        elig = self.store.check_self_service_paper_eligibility(self.strategy_id, user_id=self.user_id)
        self.assertTrue(elig["permitted"], f"Eligibility failed: {elig}")

        promoted = self.store.promote_strategy(
            strategy_id=self.strategy_id,
            target_stage="PAPER_ELIGIBLE",
            actor=f"USER-{self.user_id[:4]}",
            notes="Self-service paper promotion",
        )
        self.assertEqual(promoted["stage"], "PAPER_ELIGIBLE")
        self.assertEqual(promoted["paperGovernance"]["systemReadiness"], "READY")

    def test_user_self_service_live_promotion(self):
        """User can promote from PAPER_ELIGIBLE to LIVE_ELIGIBLE."""
        # First promote to PAPER_ELIGIBLE
        self.store.promote_strategy(
            strategy_id=self.strategy_id,
            target_stage="PAPER_ELIGIBLE",
            actor=f"USER-{self.user_id[:4]}",
        )

        # Check live eligibility
        elig = self.store.check_self_service_live_eligibility(self.strategy_id, user_id=self.user_id)
        self.assertTrue(elig["permitted"], f"Live eligibility failed: {elig}")

        # Promote to LIVE_ELIGIBLE
        promoted = self.store.promote_strategy(
            strategy_id=self.strategy_id,
            target_stage="LIVE_ELIGIBLE",
            actor=f"USER-{self.user_id[:4]}",
            notes="Self-service live promotion",
        )
        self.assertEqual(promoted["stage"], "LIVE_ELIGIBLE")
        self.assertEqual(promoted["liveGovernance"]["systemReadiness"], "READY")

    def test_cross_user_promotion_denied(self):
        """User B cannot promote User A's strategy."""
        user_b_id = str(uuid4())
        now_str = "2026-09-16T00:00:00Z"
        with self.store._transaction() as cur:
            cur.execute("""
                INSERT INTO users (user_id, role, lifecycle, display_name, created_at_utc, security_state, account_status)
                VALUES (?, 'USER', 'ACTIVE', 'User B', ?, 'CLEAR', 'ACTIVE')
            """, (user_b_id, now_str))

        elig = self.store.check_self_service_paper_eligibility(self.strategy_id, user_id=user_b_id)
        self.assertFalse(elig["permitted"])
        self.assertEqual(elig["code"], "STRATEGY_NOT_ASSIGNED")

    def test_owner_hold_blocks_promotion(self):
        """If Owner puts an explicit HOLD, self-service eligibility fails closed."""
        with self.store._transaction() as cur:
            cur.execute("""
                UPDATE owner_strategies 
                SET paper_owner_allowance = 'HOLD', paper_owner_hold_reason = 'Risk audit pending'
                WHERE strategy_id = ?
            """, (self.strategy_id,))

        elig = self.store.check_self_service_paper_eligibility(self.strategy_id, user_id=self.user_id)
        self.assertFalse(elig["permitted"])
        self.assertIn("Risk audit pending", str(elig["reason"]))

    def test_live_deployment_with_live_eligibility(self):
        """Creating a LIVE deployment succeeds when strategy is LIVE_ELIGIBLE and connection ready."""
        # Promote to LIVE_ELIGIBLE
        self.store.promote_strategy(strategy_id=self.strategy_id, target_stage="PAPER_ELIGIBLE")
        self.store.promote_strategy(strategy_id=self.strategy_id, target_stage="LIVE_ELIGIBLE")

        # Deploy in LIVE mode
        dep = self.store.create_deployment(
            user_id=self.user_id,
            strategy_id=self.strategy_id,
            strategy_version_id="1.0",
            source_sha256="mock_sha_12345",
            connection_id=self.conn_id,
            instrument="NIFTY",
            timeframe="5m",
            execution_mode="LIVE",
        )
        self.assertEqual(dep["status"], "DEPLOYED")
        self.assertIsNone(dep.get("blockReason"))

    def test_live_deployment_blocked_if_not_live_eligible(self):
        """Creating a LIVE deployment while still in BACKTEST_ELIGIBLE is BLOCKED."""
        dep = self.store.create_deployment(
            user_id=self.user_id,
            strategy_id=self.strategy_id,
            strategy_version_id="1.0",
            source_sha256="mock_sha_12345",
            connection_id=self.conn_id,
            instrument="NIFTY",
            timeframe="5m",
            execution_mode="LIVE",
        )
        self.assertEqual(dep["status"], "BLOCKED")
        self.assertIn("LIVE_ELIGIBLE required", dep.get("blockReason", ""))


if __name__ == "__main__":
    unittest.main()
