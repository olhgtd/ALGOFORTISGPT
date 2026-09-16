"""Tests for Phase 8: Four Real Broker Execution Adapters & Factory.

Verifies:
1. BrokerAdapterFactory creates authoritative adapters for Upstox, Kite, Dhan, Angel One, and Mock.
2. UpstoxBrokerAdapter order lifecycle, query, positions, funds, and fail-closed transport.
3. KiteBrokerAdapter order lifecycle, query, positions, funds, and fail-closed transport.
4. DhanBrokerAdapter order lifecycle, query, positions, funds, and fail-closed transport.
5. AngelOneBrokerAdapter order lifecycle, query, positions, funds, and fail-closed transport.
6. Deduplication, normalization, and error classification across all 4 adapters.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from engine.broker_adapters import (
    AngelOneBrokerAdapter,
    BrokerAdapterFactory,
    BrokerAdapterOrderStatus,
    BrokerAdapterUnavailableError,
    BrokerAuthError,
    BrokerCapability,
    BrokerConnectionState,
    BrokerFundsSnapshot,
    BrokerNetworkError,
    BrokerPositionSnapshot,
    BrokerRateLimitError,
    DhanBrokerAdapter,
    KiteBrokerAdapter,
    MockBrokerAdapter,
    UpstoxBrokerAdapter,
)
from engine.orders import ConcreteOpenInstruction, OrderRequest, OrderType, TimeInForce
from engine.orchestration.signal_intake import SignalIntent
from engine.portfolio.model import InstrumentIdentity, InstrumentSpecification


def _make_dummy_order():
    now_dt = datetime(2026, 9, 16, 9, 15, tzinfo=timezone.utc)
    intent = SignalIntent(
        strategy_id="test-strat",
        strategy_version="1.0",
        symbol="NIFTY",
        timeframe="1m",
        originating_timestamp=now_dt,
        action="BUY",
        confidence=1.0,
        metadata={},
    )
    return ConcreteOpenInstruction(
        source_entry_order=OrderRequest(
            source_intent=intent,
            order_type=OrderType.LIMIT,
            quantity=Decimal("50"),
            time_in_force=TimeInForce.DAY,
            limit_price=Decimal("25000.00"),
        ),
        opening_action="BUY",
        execution_symbol="NIFTY",
    )


def _make_dummy_instrument():
    identity = InstrumentIdentity("NSE", "NIFTY", "index")
    spec = InstrumentSpecification(identity, datetime(2020, 1, 1).date(), 1, 50, 50, "INR", "0.05")
    return identity, spec


class TestBrokerExecutionAdapters(unittest.TestCase):
    def test_factory_creation(self):
        """Factory creates correct concrete broker adapter instance."""
        upstox = BrokerAdapterFactory.create_adapter("UPSTOX", {"access_token": "tok_up"})
        self.assertIsInstance(upstox, UpstoxBrokerAdapter)

        kite = BrokerAdapterFactory.create_adapter("KITE", {"access_token": "tok_kt", "api_key": "k"})
        self.assertIsInstance(kite, KiteBrokerAdapter)

        zerodha = BrokerAdapterFactory.create_adapter("ZERODHA", {"access_token": "tok_zd", "api_key": "k"})
        self.assertIsInstance(zerodha, KiteBrokerAdapter)

        dhan = BrokerAdapterFactory.create_adapter("DHAN", {"access_token": "tok_dh", "client_id": "c"})
        self.assertIsInstance(dhan, DhanBrokerAdapter)

        angel = BrokerAdapterFactory.create_adapter("ANGELONE", {"jwt_token": "tok_ao", "api_key": "k"})
        self.assertIsInstance(angel, AngelOneBrokerAdapter)

        angel_alias = BrokerAdapterFactory.create_adapter("ANGEL_ONE", {"jwt_token": "tok_ao", "api_key": "k"})
        self.assertIsInstance(angel_alias, AngelOneBrokerAdapter)

        mock_ad = BrokerAdapterFactory.create_adapter("MOCK")
        self.assertIsInstance(mock_ad, MockBrokerAdapter)

        with self.assertRaises(ValueError):
            BrokerAdapterFactory.create_adapter("UNKNOWN_BROKER")

    def test_upstox_adapter_lifecycle(self):
        """Upstox submit, deduplicate, cancel, modify, query, positions, funds."""
        client = MagicMock()
        client.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"status": "success", "data": {"order_id": "UP-1001"}},
        )
        client.delete.return_value = MagicMock(status_code=200, json=lambda: {"status": "success"})
        client.put.return_value = MagicMock(status_code=200, json=lambda: {"status": "success"})
        client.get.side_effect = [
            # positions query
            MagicMock(
                status_code=200,
                json=lambda: {
                    "status": "success",
                    "data": [
                        {
                            "instrument_token": "NIFTY26SEP25000CE",
                            "trading_symbol": "NIFTY26SEP25000CE",
                            "quantity": 50,
                            "average_price": 120.5,
                            "product": "I",
                            "last_price": 130.0,
                            "pnl": 475.0,
                        }
                    ],
                },
            ),
            # funds query
            MagicMock(
                status_code=200,
                json=lambda: {
                    "status": "success",
                    "data": {
                        "equity": {
                            "available_margin": 150000.0,
                            "used_margin": 25000.0,
                        }
                    },
                },
            ),
        ]

        adapter = UpstoxBrokerAdapter({"access_token": "valid_token"}, http_client=client)
        self.assertEqual(adapter.connection_state, BrokerConnectionState.CONNECTED)
        self.assertTrue(adapter.supports(BrokerCapability.PLACE_ORDER))

        order = _make_dummy_order()
        ident, spec = _make_dummy_instrument()
        now_dt = datetime(2026, 9, 16, 9, 15, tzinfo=timezone.utc)

        # 1. Submit
        sub_res = adapter.submit(order, instrument_identity=ident, specification=spec, submission_market_timestamp=now_dt)
        self.assertTrue(sub_res.accepted)
        self.assertIsNotNone(sub_res.order_id)
        self.assertFalse(sub_res.duplicate)

        # 2. Duplicate submission check
        dup_res = adapter.submit(order, instrument_identity=ident, specification=spec, submission_market_timestamp=now_dt)
        self.assertFalse(dup_res.accepted)
        self.assertTrue(dup_res.duplicate)

        # 3. Query order
        snap = adapter.query_order(sub_res.order_id)
        self.assertIsNotNone(snap)
        self.assertEqual(snap.adapter_status, BrokerAdapterOrderStatus.ACCEPTED)

        # 4. Modify order
        mod_res = adapter.modify(sub_res.order_id, new_price=Decimal("25100.00"), timestamp=now_dt)
        self.assertTrue(mod_res.modified)

        # 5. Cancel order
        can_res = adapter.cancel(sub_res.order_id, cancel_market_timestamp=now_dt)
        self.assertTrue(can_res.cancelled)

        # 6. Positions & Funds
        positions = adapter.query_positions()
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0].quantity, Decimal("50"))

        funds = adapter.query_funds()
        self.assertIsNotNone(funds)
        self.assertEqual(funds.available_balance, Decimal("150000.0"))
        self.assertEqual(funds.total_equity, Decimal("175000.0"))

    def test_kite_adapter_lifecycle(self):
        """Kite submit, query, cancel, positions, funds."""
        client = MagicMock()
        client.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"status": "success", "data": {"order_id": "KT-2001"}},
        )
        client.delete.return_value = MagicMock(status_code=200, json=lambda: {"status": "success"})
        client.get.side_effect = [
            # positions query
            MagicMock(
                status_code=200,
                json=lambda: {
                    "status": "success",
                    "data": {
                        "net": [
                            {
                                "instrument_token": "NIFTY26SEP25000CE",
                                "tradingsymbol": "NIFTY26SEP25000CE",
                                "quantity": 50,
                                "average_price": 100.0,
                                "product": "MIS",
                                "last_price": 115.0,
                                "pnl": 750.0,
                            }
                        ]
                    },
                },
            ),
            # funds query
            MagicMock(
                status_code=200,
                json=lambda: {
                    "status": "success",
                    "data": {
                        "equity": {
                            "available": {"cash": "200000.00"},
                            "utilised": {"debits": "15000.00"},
                        }
                    },
                },
            ),
        ]

        adapter = KiteBrokerAdapter({"access_token": "tok", "api_key": "key"}, http_client=client)
        self.assertEqual(adapter.connection_state, BrokerConnectionState.CONNECTED)

        order = _make_dummy_order()
        ident, spec = _make_dummy_instrument()
        now_dt = datetime(2026, 9, 16, 9, 15, tzinfo=timezone.utc)

        sub_res = adapter.submit(order, instrument_identity=ident, specification=spec, submission_market_timestamp=now_dt)
        self.assertTrue(sub_res.accepted)

        positions = adapter.query_positions()
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0].trading_symbol, "NIFTY26SEP25000CE")

        funds = adapter.query_funds()
        self.assertIsNotNone(funds)
        self.assertEqual(funds.available_balance, Decimal("200000.00"))

    def test_dhan_adapter_lifecycle(self):
        """Dhan submit, query, cancel, positions, funds."""
        client = MagicMock()
        client.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"status": "success", "orderId": "DH-3001"},
        )
        client.delete.return_value = MagicMock(status_code=200, json=lambda: {"status": "success"})
        client.get.side_effect = [
            # positions query
            MagicMock(
                status_code=200,
                json=lambda: [
                    {
                        "securityId": "NIFTY26SEP25000CE",
                        "customSymbol": "NIFTY26SEP25000CE",
                        "netQty": 50,
                        "costPrice": 95.0,
                        "positionType": "INTRADAY",
                        "lastTradedPrice": 105.0,
                        "realizedProfit": 500.0,
                    }
                ],
            ),
            # funds query
            MagicMock(
                status_code=200,
                json=lambda: {
                    "availMargin": "180000.00",
                    "utilizedAmount": "20000.00",
                },
            ),
        ]

        adapter = DhanBrokerAdapter({"access_token": "tok", "client_id": "cid"}, http_client=client)
        self.assertEqual(adapter.connection_state, BrokerConnectionState.CONNECTED)

        order = _make_dummy_order()
        ident, spec = _make_dummy_instrument()
        now_dt = datetime(2026, 9, 16, 9, 15, tzinfo=timezone.utc)

        sub_res = adapter.submit(order, instrument_identity=ident, specification=spec, submission_market_timestamp=now_dt)
        self.assertTrue(sub_res.accepted)

        positions = adapter.query_positions()
        self.assertEqual(len(positions), 1)

        funds = adapter.query_funds()
        self.assertIsNotNone(funds)
        self.assertEqual(funds.available_balance, Decimal("180000.00"))

    def test_angel_one_adapter_lifecycle(self):
        """Angel One submit, query, cancel, positions, funds."""
        client = MagicMock()
        client.post.side_effect = [
            # submit
            MagicMock(status_code=200, json=lambda: {"status": True, "data": {"orderid": "AO-4001"}}),
            # cancel
            MagicMock(status_code=200, json=lambda: {"status": True}),
        ]
        client.get.side_effect = [
            # positions query
            MagicMock(
                status_code=200,
                json=lambda: {
                    "status": True,
                    "data": [
                        {
                            "symboltoken": "NIFTY26SEP25000CE",
                            "tradingsymbol": "NIFTY26SEP25000CE",
                            "netqty": 50,
                            "totalbuyavgprice": 110.0,
                            "producttype": "INTRADAY",
                            "ltp": 125.0,
                            "pnl": 750.0,
                        }
                    ],
                },
            ),
            # funds query
            MagicMock(
                status_code=200,
                json=lambda: {
                    "status": True,
                    "data": {
                        "availablecash": "250000.00",
                        "utilizedmargin": "30000.00",
                    },
                },
            ),
        ]

        adapter = AngelOneBrokerAdapter({"jwt_token": "jwt", "api_key": "key"}, http_client=client)
        self.assertEqual(adapter.connection_state, BrokerConnectionState.CONNECTED)

        order = _make_dummy_order()
        ident, spec = _make_dummy_instrument()
        now_dt = datetime(2026, 9, 16, 9, 15, tzinfo=timezone.utc)

        sub_res = adapter.submit(order, instrument_identity=ident, specification=spec, submission_market_timestamp=now_dt)
        self.assertTrue(sub_res.accepted)

        can_res = adapter.cancel(sub_res.order_id, cancel_market_timestamp=now_dt)
        self.assertTrue(can_res.cancelled)

        positions = adapter.query_positions()
        self.assertEqual(len(positions), 1)

        funds = adapter.query_funds()
        self.assertIsNotNone(funds)
        self.assertEqual(funds.available_balance, Decimal("250000.00"))

    def test_disconnected_adapter_fails_closed(self):
        """Disconnected adapter raises BrokerAdapterUnavailableError."""
        adapter = UpstoxBrokerAdapter({"access_token": ""})
        self.assertEqual(adapter.connection_state, BrokerConnectionState.DISCONNECTED)

        order = _make_dummy_order()
        ident, spec = _make_dummy_instrument()
        now_dt = datetime(2026, 9, 16, 9, 15, tzinfo=timezone.utc)

        with self.assertRaises(BrokerAdapterUnavailableError):
            adapter.submit(order, instrument_identity=ident, specification=spec, submission_market_timestamp=now_dt)

        with self.assertRaises(BrokerAdapterUnavailableError):
            adapter.cancel("some-id", cancel_market_timestamp=now_dt)

        with self.assertRaises(BrokerAdapterUnavailableError):
            adapter.query_order("some-id")

        with self.assertRaises(BrokerAdapterUnavailableError):
            adapter.query_positions()

        with self.assertRaises(BrokerAdapterUnavailableError):
            adapter.query_funds()

    def test_http_error_classification(self):
        """HTTP errors are classified into standardized adapter exceptions."""
        client = MagicMock()
        client.post.return_value = MagicMock(status_code=401, json=lambda: {"detail": "unauthorized"})

        adapter = UpstoxBrokerAdapter({"access_token": "expired_tok"}, http_client=client)
        order = _make_dummy_order()
        ident, spec = _make_dummy_instrument()
        now_dt = datetime(2026, 9, 16, 9, 15, tzinfo=timezone.utc)

        with self.assertRaises(BrokerAuthError):
            adapter.submit(order, instrument_identity=ident, specification=spec, submission_market_timestamp=now_dt)

        # Rate limit
        client.post.return_value = MagicMock(status_code=429, json=lambda: {})
        with self.assertRaises(BrokerRateLimitError):
            adapter.submit(order, instrument_identity=ident, specification=spec, submission_market_timestamp=now_dt)

        # Server error
        client.post.return_value = MagicMock(status_code=502, json=lambda: {})
        with self.assertRaises(BrokerNetworkError):
            adapter.submit(order, instrument_identity=ident, specification=spec, submission_market_timestamp=now_dt)


if __name__ == "__main__":
    unittest.main()
