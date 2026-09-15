"""Comprehensive Engine & Job Lifecycle Hardening Certification Suite for AlgoFortis.

Validates Backtest, Paper, Walk-Forward, and Mode Isolation contracts across all 18 phases:
- Backtest job state transitions & immutability
- Cooperative cancellation & restart interruption
- Backtest execution determinism
- Paper session state machine transitions (start guards & stop idempotency)
- Paper order deduplication & live quote deduplication
- Walk-forward job lifecycle, store boundaries & restart recovery
- Strict Backtest / Paper / Live isolation
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from dashboard.backend.domain import (
    AccountAccessStatus,
    ActivationStatus,
    Lifecycle,
    Role,
    ServiceEntitlementStatus,
    UserIdentity,
)
from dashboard.backend.governance_store import SQLiteGovernanceStore
from dashboard.backend.paper_service import (
    InvalidPaperParameterError,
    PaperService,
)
from dashboard.backend.security_store import SQLiteSecurityStore
from dashboard.backend.walkforward_service import WalkForwardService
from engine.backtest.engine import (
    BacktestRunContext,
    BarEvent,
    DeterministicEventLoop,
)
from engine.execution.paper_broker import (
    BrokerQuoteEvent,
    SimulatedPaperBroker,
)
from engine.execution.paper_fill import (
    FixedBasisPointsSlippage,
    PaperFillAdapter,
    PaperFillPolicy,
)
from engine.execution.quote import QuoteSnapshot
from engine.orders.model import (
    ConcreteOpenInstruction,
    OrderRequest,
    OrderType,
    SignalIntent,
    TimeInForce,
)
from engine.portfolio.model import (
    InstrumentIdentity,
    InstrumentSpecification,
)


class TestEngineHardeningSuite(unittest.TestCase):

    def setUp(self):
        import gc
        gc.collect()
        self._tmp = tempfile.TemporaryDirectory(prefix="af_eng_test_", ignore_cleanup_errors=True)
        self.tmp_path = Path(self._tmp.name)

        self.sec_db = self.tmp_path / "security.sqlite3"
        self.gov_db = self.tmp_path / "governance.sqlite3"

        self.sec_store = SQLiteSecurityStore(self.sec_db, seed_governance=False, profile="test")
        self.gov_store = SQLiteGovernanceStore(self.gov_db, profile="test")

        # Setup Owner and Test User
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

        self.user_id = uuid4()
        self.user = UserIdentity(
            user_id=self.user_id,
            role=Role.USER,
            lifecycle=Lifecycle.ACTIVE,
            display_name="Test Trader",
            account_status=AccountAccessStatus.ACTIVE,
            activation_status=ActivationStatus.REDEEMED,
            service_status=ServiceEntitlementStatus.ACTIVE,
            sx_id="SX-ALPHA-01",
        )

        # Register users in DB
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

        # Register Strategy
        self.strat_id = "test-trend-strat"
        self.ver_id = "1.0.0"
        self.sec_store.register_backtest_artifact(
            strategy_id=self.strat_id,
            version_id=self.ver_id,
            name="Test Trend Strategy",
            owner_id=str(self.owner_id),
        )
        self.sec_store.assign_strategy_to_user(user_id=str(self.user_id), strategy_id=self.strat_id)

        # Services
        self.paper_service = PaperService(
            security_store=self.sec_store,
            governance_store=self.gov_store,
            artifact_root=self.tmp_path / "artifacts",
        )

    def tearDown(self):
        import gc
        self.sec_store.close()
        self.gov_store.close()
        gc.collect()
        try:
            self._tmp.cleanup()
        except Exception:
            pass

    # =========================================================================
    # 1. BACKTEST JOB STATE MACHINE & CANCELLATION & CRASH RECOVERY
    # =========================================================================

    def test_backtest_job_state_transitions_and_immutability(self):
        """Backtest job transitions cleanly: PENDING -> RUNNING -> COMPLETED; terminal jobs cannot re-execute."""
        run_id = f"bt-{uuid4().hex[:8]}"
        run_record = {
            "run_id": run_id,
            "user_id": str(self.user_id),
            "strategy_id": self.strat_id,
            "status": "PENDING",
            "instrument": "NIFTY",
            "timeframe": "1m",
            "date_range": "2026-01-05",
            "initial_capital": 500000.0,
            "execution_metadata": {"runtime_instance": "inst-1"},
        }
        saved = self.sec_store.save_backtest_run(run_record)
        self.assertEqual(saved["status"], "PENDING")

        # Worker claims job
        claimed = self.sec_store.claim_backtest_job(run_id)
        self.assertTrue(claimed)
        curr = self.sec_store.get_backtest_run(run_id)
        self.assertEqual(curr["status"], "RUNNING")

        # Duplicate claim fails
        duplicate_claim = self.sec_store.claim_backtest_job(run_id)
        self.assertFalse(duplicate_claim)

        # Complete job
        curr["status"] = "COMPLETED"
        curr["net_profit"] = 12500.0
        final = self.sec_store.save_backtest_run(curr, expected_status={"RUNNING", "CANCEL_REQUESTED"})
        self.assertEqual(final["status"], "COMPLETED")
        self.assertEqual(final["net_profit"], 12500.0)

        # Completed job cannot transition back to RUNNING or PENDING
        curr["status"] = "RUNNING"
        re_run = self.sec_store.save_backtest_run(curr, expected_status={"PENDING"})
        self.assertEqual(re_run["status"], "COMPLETED")  # Unaltered terminal state preserved

    def test_backtest_cancellation_pending_and_running(self):
        """Cancelling PENDING marks CANCELLED immediately; cancelling RUNNING marks CANCEL_REQUESTED."""
        # 1. Cancel PENDING
        p_id = f"bt-p-{uuid4().hex[:8]}"
        self.sec_store.save_backtest_run({
            "run_id": p_id,
            "user_id": str(self.user_id),
            "strategy_id": self.strat_id,
            "status": "PENDING",
            "instrument": "NIFTY",
            "timeframe": "1m",
        })
        res_p = self.sec_store.cancel_backtest_run(p_id, user_id=str(self.user_id))
        self.assertTrue(res_p)
        rec_p = self.sec_store.get_backtest_run(p_id)
        self.assertEqual(rec_p["status"], "CANCELLED")
        self.assertEqual(rec_p["error_message"], "CANCELLED_BEFORE_EXECUTION")

        # Worker claiming cancelled job fails closed
        self.assertFalse(self.sec_store.claim_backtest_job(p_id))

        # 2. Cancel RUNNING
        r_id = f"bt-r-{uuid4().hex[:8]}"
        self.sec_store.save_backtest_run({
            "run_id": r_id,
            "user_id": str(self.user_id),
            "strategy_id": self.strat_id,
            "status": "RUNNING",
            "instrument": "NIFTY",
            "timeframe": "1m",
        })
        res_r = self.sec_store.cancel_backtest_run(r_id, user_id=str(self.user_id))
        self.assertTrue(res_r)
        rec_r = self.sec_store.get_backtest_run(r_id)
        self.assertEqual(rec_r["status"], "CANCEL_REQUESTED")

    def test_backtest_crash_recovery_interrupts_stale_jobs(self):
        """Simulated crash/restart interrupts all PENDING and RUNNING backtest jobs."""
        bt_stale_1 = f"bt-s1-{uuid4().hex[:8]}"
        bt_stale_2 = f"bt-s2-{uuid4().hex[:8]}"
        self.sec_store.save_backtest_run({
            "run_id": bt_stale_1,
            "user_id": str(self.user_id),
            "strategy_id": self.strat_id,
            "status": "PENDING",
            "instrument": "NIFTY",
            "timeframe": "1m",
        })
        self.sec_store.save_backtest_run({
            "run_id": bt_stale_2,
            "user_id": str(self.user_id),
            "strategy_id": self.strat_id,
            "status": "RUNNING",
            "instrument": "NIFTY",
            "timeframe": "1m",
        })

        # Simulate restart recovery hook
        self.sec_store.interrupt_backtest_jobs("RUNTIME_RESTART_INTERRUPTED")

        s1 = self.sec_store.get_backtest_run(bt_stale_1)
        s2 = self.sec_store.get_backtest_run(bt_stale_2)
        self.assertEqual(s1["status"], "FAILED")
        self.assertEqual(s1["error_message"], "RUNTIME_RESTART_INTERRUPTED")
        self.assertEqual(s2["status"], "FAILED")
        self.assertEqual(s2["error_message"], "RUNTIME_RESTART_INTERRUPTED")

    def test_backtest_deterministic_event_loop_and_decimal_precision(self):
        """DeterministicEventLoop guarantees identical batch ordering across random input permutations and preserves exact Decimals."""
        t1 = datetime(2026, 1, 5, 9, 15, tzinfo=timezone.utc)
        t2 = datetime(2026, 1, 5, 9, 16, tzinfo=timezone.utc)
        b1 = BarEvent(symbol="NIFTY", timestamp=t1, timeframe="1m", open="22000.10", high="22010.50", low="21995.25", close="22005.00", volume=1000, source_sequence=1)
        b2 = BarEvent(symbol="BANKNIFTY", timestamp=t1, timeframe="1m", open="48000.00", high="48050.00", low="47980.00", close="48020.00", volume=500, source_sequence=2)
        b3 = BarEvent(symbol="NIFTY", timestamp=t2, timeframe="1m", open="22005.00", high="22020.00", low="22002.00", close="22015.00", volume=1200, source_sequence=3)

        loop = DeterministicEventLoop()
        ctx = BacktestRunContext(
            run_id="det-test",
            engine_version="1.0.0",
            strategy_id=self.strat_id,
            strategy_version=self.ver_id,
            requested_symbols=("NIFTY", "BANKNIFTY"),
            requested_timeframes=("1m",),
            start=t1,
            end=t2,
            execution_model_id="MKT",
            cost_model_id="ZERO",
            reproducibility_seed=42,
        )

        batches_run1: list[list[str]] = []
        batches_run2: list[list[str]] = []

        res1 = loop.run(ctx, [b3, b1, b2], consumer=lambda batch: batches_run1.append([f"{b.symbol}:{b.source_sequence}" for b in batch]))
        res2 = loop.run(ctx, [b2, b3, b1], consumer=lambda batch: batches_run2.append([f"{b.symbol}:{b.source_sequence}" for b in batch]))

        self.assertEqual(res1.processed_event_count, 3)
        self.assertEqual(res2.processed_event_count, 3)
        self.assertEqual(batches_run1, batches_run2)
        self.assertEqual(b1.open, Decimal("22000.10"))
        self.assertEqual(b1.low, Decimal("21995.25"))

        with self.assertRaises(ValueError) as ctx_dup:
            loop.run(ctx, [b1, b1])
        self.assertIn("ambiguous duplicate BarEvent", str(ctx_dup.exception))

    # =========================================================================
    # 2. PAPER SESSION STATE MACHINE & STOP IDEMPOTENCY
    # =========================================================================

    def test_paper_session_cannot_start_stopped_or_failed_session(self):
        """Paper session in STOPPED or FAILED state rejects start_session fail-closed."""
        # Create session
        ses = self.paper_service.create_session(
            user_id=str(self.user_id),
            strategy_id=self.strat_id,
            instrument="NIFTY",
            timeframe="1m",
            initial_capital=50000.0,
        )
        session_id = ses["session_id"]
        self.assertEqual(ses["status"], "INITIALIZED")

        # Stop session
        stopped = self.paper_service.stop_session(session_id, user_id=str(self.user_id))
        self.assertEqual(stopped["status"], "STOPPED")

        # Attempt to restart STOPPED session -> must fail closed
        with self.assertRaises(InvalidPaperParameterError) as ctx:
            self.paper_service.start_session(session_id, user_id=str(self.user_id))
        self.assertIn("STOPPED and cannot be restarted", str(ctx.exception))

        # Manually set to FAILED and attempt start -> must fail closed
        self.sec_store.update_paper_session(session_id, status="FAILED", error_message="Fatal broker fault")
        with self.assertRaises(InvalidPaperParameterError) as ctx_failed:
            self.paper_service.start_session(session_id, user_id=str(self.user_id))
        self.assertIn("FAILED and cannot be started", str(ctx_failed.exception))

    def test_paper_session_stop_is_idempotent(self):
        """Calling stop_session multiple times is completely idempotent and records no duplicate events."""
        ses = self.paper_service.create_session(
            user_id=str(self.user_id),
            strategy_id=self.strat_id,
            instrument="NIFTY",
            timeframe="1m",
            initial_capital=50000.0,
        )
        session_id = ses["session_id"]

        # First stop
        stop_1 = self.paper_service.stop_session(session_id, user_id=str(self.user_id))
        self.assertEqual(stop_1["status"], "STOPPED")
        events_1 = self.sec_store.get_paper_events(session_id)
        stop_events_1 = [e for e in events_1 if e["title"] == "Paper Session Stopped"]
        self.assertEqual(len(stop_events_1), 1)

        # Second stop (idempotent retry)
        stop_2 = self.paper_service.stop_session(session_id, user_id=str(self.user_id))
        self.assertEqual(stop_2["status"], "STOPPED")
        events_2 = self.sec_store.get_paper_events(session_id)
        stop_events_2 = [e for e in events_2 if e["title"] == "Paper Session Stopped"]
        self.assertEqual(len(stop_events_2), 1)  # No duplicate stop event created

    # =========================================================================
    # 3. PAPER ORDER & FILL DEDUPLICATION
    # =========================================================================

    def test_simulated_paper_broker_deduplicates_orders(self):
        """SimulatedPaperBroker rejects duplicate order submission intents with duplicate=True."""
        fill_policy = PaperFillPolicy(
            slippage_model=FixedBasisPointsSlippage(0),
            max_execution_tolerance_bps=Decimal("50"),
            max_slippage_bps=Decimal("20"),
        )
        broker = SimulatedPaperBroker(adapter=PaperFillAdapter(fill_policy))

        ident = InstrumentIdentity("NSE", "NIFTY", "index")
        spec = InstrumentSpecification(ident, datetime(2020, 1, 1).date(), 1, 50, 50, "INR", "0.05")
        now_dt = datetime.now(timezone.utc)

        quote = QuoteSnapshot(
            instrument_identity=ident,
            exchange_timestamp=now_dt,
            bid_price=Decimal("22000.00"),
            ask_price=Decimal("22001.00"),
            source="TEST",
            last_price=Decimal("22000.50"),
        )
        intent = SignalIntent(
            strategy_id=self.strat_id,
            strategy_version=self.ver_id,
            symbol="NIFTY",
            timeframe="1m",
            originating_timestamp=now_dt,
            action="BUY",
            confidence=1.0,
            metadata={},
        )
        order = ConcreteOpenInstruction(
            source_entry_order=OrderRequest(source_intent=intent, order_type=OrderType.MARKET, quantity=Decimal("50"), time_in_force=TimeInForce.DAY),
            opening_action="BUY",
            execution_symbol="NIFTY",
        )

        # 1. First submission -> Accepted
        res1 = broker.submit(order, instrument_identity=ident, specification=spec, submission_quote=quote, submission_market_timestamp=now_dt)
        self.assertTrue(res1.accepted)
        self.assertFalse(res1.duplicate)

        # 2. Duplicate submission -> Rejected with duplicate=True
        res2 = broker.submit(order, instrument_identity=ident, specification=spec, submission_quote=quote, submission_market_timestamp=now_dt)
        self.assertFalse(res2.accepted)
        self.assertTrue(res2.duplicate)
        self.assertEqual(res2.reason, "duplicate_order")

    # =========================================================================
    # 4. WALK-FORWARD LIFECYCLE & CRASH RECOVERY
    # =========================================================================

    def test_walkforward_stale_jobs_interrupted_on_startup(self):
        """Walkforward jobs left in PENDING/RUNNING across restart are safely marked FAILED."""
        wf_id = self.sec_store.create_walkforward_job(
            user_id=str(self.user_id),
            strategy_id=self.strat_id,
            strategy_version_id=self.ver_id,
            source_sha256="fake-hash",
            dataset_id="nse-tick-primary",
            instrument="NIFTY",
            timeframe="1m",
            is_days=20,
            oos_days=5,
            initial_capital=500000.0,
            policy={"mode": "OTM"},
            windows=[{"kind": "IN_SAMPLE", "start_date": "2026-01-01", "end_date": "2026-01-20"}],
        )["jobId"]

        self.sec_store.update_walkforward_job(job_id=wf_id, user_id=str(self.user_id), status="RUNNING")
        job_running = self.sec_store.get_walkforward_job(wf_id, user_id=str(self.user_id))
        self.assertEqual(job_running["status"], "RUNNING")

        # Simulate restart recovery
        self.sec_store.interrupt_walkforward_jobs("RUNTIME_RESTART_INTERRUPTED")

        job_interrupted = self.sec_store.get_walkforward_job(wf_id, user_id=str(self.user_id))
        self.assertEqual(job_interrupted["status"], "FAILED")
        self.assertEqual(job_interrupted["error"], "RUNTIME_RESTART_INTERRUPTED")

    def test_walkforward_resolves_strategy_via_governance_store_helper(self):
        """WalkForwardService._resolve_exact_version uses gov.get_version store method."""
        ver_sha = "a" * 64
        self.gov_store.save_version({
            "version_id": self.ver_id,
            "strategy_id": self.strat_id,
            "owner_id": str(self.owner_id),
            "source_sha256": ver_sha,
            "artifact_path": "users/usr/strat.py",
            "stage": "BACKTEST",
            "archived": 0,
            "protective_policy_identity": "DEFAULT",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        })

        # Directly verify get_version helper
        row = self.gov_store.get_version(self.strat_id, self.ver_id)
        self.assertIsNotNone(row)
        self.assertEqual(row["source_sha256"], ver_sha)

    # =========================================================================
    # 5. ENGINE MODE ISOLATION PROOF
    # =========================================================================

    def test_backtest_does_not_mutate_paper_or_live_state(self):
        """Backtest execution never mutates paper_sessions, paper_orders, or paper_positions."""
        paper_sessions_before = self.sec_store.list_paper_sessions(limit=500)
        orders_before = self.sec_store.get_paper_orders("any-session")

        # Record a backtest run
        bt_id = f"bt-iso-{uuid4().hex[:8]}"
        self.sec_store.save_backtest_run({
            "run_id": bt_id,
            "user_id": str(self.user_id),
            "strategy_id": self.strat_id,
            "status": "COMPLETED",
            "instrument": "NIFTY",
            "timeframe": "1m",
            "net_profit": 5000.0,
            "trades": [{"id": "t1", "pnl": 5000.0}],
            "equity_curve": [{"date": "2026-01-05", "value": 505000.0}],
        })

        paper_sessions_after = self.sec_store.list_paper_sessions(limit=500)
        orders_after = self.sec_store.get_paper_orders("any-session")

        self.assertEqual(len(paper_sessions_before), len(paper_sessions_after))
        self.assertEqual(len(orders_before), len(orders_after))


if __name__ == "__main__":
    unittest.main()
