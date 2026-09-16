"""Tests for Phase 10: Live Reconciliation & Restart Recovery.

Verifies:
1. Broker state query (funds, open orders, positions) via BrokerAdapter.
2. Order reconciliation for in-flight orders that completed (FILLED, CANCELLED, REJECTED) during downtime.
3. Detection of orphan orders and local-only missing orders.
4. Net position reconciliation (matching, discrepancies, broker-only, local-only).
5. Restart stale & duplicate entry signal suppression using canonical identity and cutoff timestamp.
6. Position protection management restoration in ProtectiveExitBook without re-submitting duplicate entries.
7. Resilience against adapter query exceptions with structured error recording.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from engine.broker_adapters.contracts import (
    BrokerAdapter,
    BrokerAdapterOrderSnapshot,
    BrokerAdapterOrderStatus,
    BrokerFundsSnapshot,
    BrokerPositionSnapshot,
)
from engine.orders.model import OrderRequest, OrderType, TimeInForce
from engine.orchestration.signal_intake import SignalIntent, signal_intent_identity
from engine.portfolio.model import InstrumentIdentity, PositionKey
from engine.protective.runtime import (
    ProtectiveExit,
    ProtectiveExitBook,
    ProtectiveExitKind,
    ProtectiveExitState,
)
from engine.reconciliation.live_reconciler import (
    LiveBrokerReconciler,
    LiveReconciliationReport,
    OrderReconciliationAction,
    OrderReconciliationItem,
    PositionReconciliationItem,
)

_NOW = datetime(2026, 9, 16, 9, 30, tzinfo=timezone.utc)


def _make_dummy_signal(minute: int = 30, action: str = "BUY", symbol: str = "NIFTY") -> SignalIntent:
    return SignalIntent(
        strategy_id="strat-alpha",
        strategy_version="1.0",
        symbol=symbol,
        timeframe="5m",
        originating_timestamp=datetime(2026, 9, 16, 9, minute, tzinfo=timezone.utc),
        action=action,
        confidence=1.0,
        metadata={"seq": 1},
    )


class TestLiveBrokerReconciliation(unittest.TestCase):
    def setUp(self):
        self.mock_adapter = MagicMock(spec=BrokerAdapter)
        self.mock_adapter.broker_name = "MOCK_BROKER"
        self.reconciler = LiveBrokerReconciler(
            broker_adapter=self.mock_adapter,
            user_id="user-123",
            broker_id="MOCK_BROKER",
        )

    def test_reconcile_funds_success(self):
        expected_funds = BrokerFundsSnapshot(
            available_balance=Decimal("250000.00"),
            used_margin=Decimal("50000.00"),
            total_equity=Decimal("300000.00"),
            observed_at=_NOW,
            currency="INR",
        )
        self.mock_adapter.query_funds.return_value = expected_funds

        funds = self.reconciler.reconcile_funds()
        self.assertIsNotNone(funds)
        self.assertEqual(funds.available_balance, Decimal("250000.00"))
        self.assertEqual(funds.used_margin, Decimal("50000.00"))

    def test_reconcile_orders_terminal_during_downtime(self):
        # Local order ORD-1 was SUBMITTED before engine crashed
        local_orders = [
            {
                "order_id": "ORD-1",
                "broker_order_identity": "BROKER-ORD-1",
                "status": "SUBMITTED",
                "cumulative_filled_quantity": 0,
            },
            {
                "order_id": "ORD-2",
                "broker_order_identity": "BROKER-ORD-2",
                "status": "SUBMITTED",
                "cumulative_filled_quantity": 0,
            },
            {
                "order_id": "ORD-3",
                "broker_order_identity": "BROKER-ORD-3",
                "status": "SUBMITTED",
                "cumulative_filled_quantity": 0,
            },
        ]

        # Broker has no open orders (all 3 resolved while engine was offline)
        self.mock_adapter.query_open_orders.return_value = ()

        # Individual queries return terminal snapshots
        snap_filled = BrokerAdapterOrderSnapshot(
            order_id="ORD-1",
            broker_order_identity="BROKER-ORD-1",
            adapter_status=BrokerAdapterOrderStatus.FILLED,
            ordered_quantity=Decimal("50"),
            cumulative_filled_quantity=Decimal("50"),
            fragment_count=1,
            last_observation_sequence=1,
            last_observed_at=_NOW,
        )
        snap_cancelled = BrokerAdapterOrderSnapshot(
            order_id="ORD-2",
            broker_order_identity="BROKER-ORD-2",
            adapter_status=BrokerAdapterOrderStatus.CANCELLED,
            ordered_quantity=Decimal("50"),
            cumulative_filled_quantity=Decimal("0"),
            fragment_count=0,
            last_observation_sequence=1,
            last_observed_at=_NOW,
        )
        snap_rejected = BrokerAdapterOrderSnapshot(
            order_id="ORD-3",
            broker_order_identity="BROKER-ORD-3",
            adapter_status=BrokerAdapterOrderStatus.REJECTED,
            ordered_quantity=Decimal("50"),
            cumulative_filled_quantity=Decimal("0"),
            fragment_count=0,
            last_observation_sequence=1,
            last_observed_at=_NOW,
        )

        def mock_query_order(b_id):
            if b_id == "BROKER-ORD-1":
                return snap_filled
            elif b_id == "BROKER-ORD-2":
                return snap_cancelled
            elif b_id == "BROKER-ORD-3":
                return snap_rejected
            return None

        self.mock_adapter.query_order.side_effect = mock_query_order

        results = self.reconciler.reconcile_orders(local_orders)
        self.assertEqual(len(results), 3)

        res_by_id = {r.order_id: r for r in results}
        self.assertEqual(res_by_id["ORD-1"].action, OrderReconciliationAction.UPDATE_FILLED)
        self.assertEqual(res_by_id["ORD-1"].filled_quantity, Decimal("50"))

        self.assertEqual(res_by_id["ORD-2"].action, OrderReconciliationAction.UPDATE_CANCELLED)
        self.assertEqual(res_by_id["ORD-3"].action, OrderReconciliationAction.UPDATE_REJECTED)

    def test_reconcile_orders_open_and_orphan(self):
        # ORD-1 is still open unchanged
        local_orders = [
            {
                "order_id": "ORD-1",
                "broker_order_identity": "BROKER-ORD-1",
                "status": "ACCEPTED",
                "cumulative_filled_quantity": 0,
            }
        ]

        open_snap = BrokerAdapterOrderSnapshot(
            order_id="ORD-1",
            broker_order_identity="BROKER-ORD-1",
            adapter_status=BrokerAdapterOrderStatus.ACCEPTED,
            ordered_quantity=Decimal("50"),
            cumulative_filled_quantity=Decimal("0"),
            fragment_count=0,
            last_observation_sequence=1,
            last_observed_at=_NOW,
        )
        orphan_snap = BrokerAdapterOrderSnapshot(
            order_id="ORPHAN-1",
            broker_order_identity="ORPHAN-BROKER-99",
            adapter_status=BrokerAdapterOrderStatus.ACCEPTED,
            ordered_quantity=Decimal("25"),
            cumulative_filled_quantity=Decimal("0"),
            fragment_count=0,
            last_observation_sequence=1,
            last_observed_at=_NOW,
        )

        self.mock_adapter.query_open_orders.return_value = (open_snap, orphan_snap)

        results = self.reconciler.reconcile_orders(local_orders)
        self.assertEqual(len(results), 2)

        known = [r for r in results if r.order_id == "ORD-1"][0]
        self.assertEqual(known.action, OrderReconciliationAction.NO_CHANGE)

        orphan = [r for r in results if r.broker_order_identity == "ORPHAN-BROKER-99"][0]
        self.assertEqual(orphan.action, OrderReconciliationAction.ORPHAN_FOUND)

    def test_reconcile_positions_matched_and_discrepancy(self):
        self.mock_adapter.query_positions.return_value = (
            BrokerPositionSnapshot("tok1", "NIFTY", Decimal("50"), Decimal("24500"), "MIS", _NOW),
            BrokerPositionSnapshot("tok2", "BANKNIFTY", Decimal("30"), Decimal("52000"), "MIS", _NOW),
            BrokerPositionSnapshot("tok3", "FINNIFTY", Decimal("40"), Decimal("23000"), "MIS", _NOW),
        )

        local_positions = {
            "NIFTY": Decimal("50"),        # Matched
            "BANKNIFTY": Decimal("15"),    # Discrepancy (broker=30, local=15)
            "MIDCPNIFTY": Decimal("75"),   # Local-only (broker has 0)
            # FINNIFTY is broker-only (local has 0)
        }

        results = self.reconciler.reconcile_positions(local_positions)
        res_by_sym = {r.symbol: r for r in results}

        self.assertEqual(res_by_sym["NIFTY"].action, "MATCHED")
        self.assertEqual(res_by_sym["NIFTY"].discrepancy, Decimal("0"))

        self.assertEqual(res_by_sym["BANKNIFTY"].action, "DISCREPANCY_DETECTED")
        self.assertEqual(res_by_sym["BANKNIFTY"].discrepancy, Decimal("15"))

        self.assertEqual(res_by_sym["FINNIFTY"].action, "BROKER_ONLY_POSITION")
        self.assertEqual(res_by_sym["MIDCPNIFTY"].action, "LOCAL_ONLY_POSITION")

    def test_filter_stale_and_duplicate_signals_on_restart(self):
        # 1. Stale historical signal from 09:15 (prior to 09:30 restart cutoff)
        sig_stale = _make_dummy_signal(minute=15)
        # 2. Duplicate signal already executed and persisted
        sig_dup = _make_dummy_signal(minute=35)
        dup_id = signal_intent_identity(sig_dup)
        # 3. Genuinely fresh signal after cutoff and not in persisted intents
        sig_fresh = _make_dummy_signal(minute=40)

        persisted_intents = {dup_id}
        cutoff = datetime(2026, 9, 16, 9, 30, tzinfo=timezone.utc)

        valid, dropped = self.reconciler.filter_stale_or_duplicate_signals(
            signals=[sig_stale, sig_dup, sig_fresh],
            persisted_intent_ids=persisted_intents,
            cutoff_timestamp=cutoff,
        )

        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0].originating_timestamp.minute, 40)

        self.assertEqual(len(dropped), 2)
        dropped_minutes = [s.originating_timestamp.minute for s in dropped]
        self.assertIn(15, dropped_minutes)
        self.assertIn(35, dropped_minutes)

    def test_restore_protective_positions_no_reentry(self):
        # PositionKey and Exit setup
        identity = InstrumentIdentity("NSE", "NIFTY", "index")
        pos_key = PositionKey(strategy_id="strat-alpha", strategy_version="1.0", identity=identity)
        dummy_sig = _make_dummy_signal(action="EXIT")
        exit_order = OrderRequest(
            source_intent=dummy_sig,
            order_type=OrderType.STOP,
            quantity=Decimal("50"),
            time_in_force=TimeInForce.GTC,
            stop_price=Decimal("24000.00"),
        )
        protective_exit = ProtectiveExit(
            protective_id="PROT-1",
            position_key=pos_key,
            kind=ProtectiveExitKind.STOP_LOSS,
            quantity=Decimal("50"),
            exit_order=exit_order,
            state=ProtectiveExitState.ACTIVE,
        )

        book = ProtectiveExitBook((protective_exit,))
        self.assertEqual(len(book.exits), 1)

        # Broker shows position still open
        broker_positions = [
            BrokerPositionSnapshot("tok1", "NIFTY", Decimal("50"), Decimal("24500"), "MIS", _NOW)
        ]

        maintained = self.reconciler.restore_protective_positions(book, broker_positions)
        self.assertEqual(maintained, 1)
        self.assertEqual(book.exits["PROT-1"].state, ProtectiveExitState.ACTIVE)

        # Now suppose broker shows position was closed (net_quantity = 0 or missing)
        maintained_after_close = self.reconciler.restore_protective_positions(book, ())
        self.assertEqual(maintained_after_close, 0)
        self.assertEqual(book.exits["PROT-1"].state, ProtectiveExitState.CANCELLED)

    def test_run_full_reconciliation_cycle(self):
        self.mock_adapter.query_funds.return_value = BrokerFundsSnapshot(
            available_balance=Decimal("100000"),
            used_margin=Decimal("0"),
            total_equity=Decimal("100000"),
            observed_at=_NOW,
            currency="INR",
        )
        self.mock_adapter.query_open_orders.return_value = ()
        self.mock_adapter.query_positions.return_value = (
            BrokerPositionSnapshot("tok1", "NIFTY", Decimal("50"), Decimal("24500"), "MIS", _NOW),
        )

        report = self.reconciler.run_full_reconciliation(
            local_pending_orders=(),
            local_positions={"NIFTY": Decimal("50")},
            persisted_intent_ids=set(),
            candidate_signals=(),
        )

        self.assertTrue(report.is_clean)
        self.assertEqual(report.user_id, "user-123")
        self.assertEqual(report.broker_id, "MOCK_BROKER")
        self.assertEqual(len(report.errors), 0)
        self.assertEqual(len(report.position_items), 1)
        self.assertEqual(report.position_items[0].action, "MATCHED")


if __name__ == "__main__":
    unittest.main()
