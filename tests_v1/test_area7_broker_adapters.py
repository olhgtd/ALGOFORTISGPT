"""AlgoFortis V1 — Area 7: Common Broker Adapter Contract & Capability Model Tests
Verifies:
- BrokerCapability enumeration completeness across all 15 locked capabilities
- BrokerAdapter Protocol runtime check compliance
- BaseBrokerAdapter capability enforcement and fail-closed guards
- Standardized error hierarchy (UnsupportedCapabilityError, BrokerAuthError, BrokerRateLimitError, etc.)
- Canonical snapshots (BrokerFundsSnapshot, BrokerPositionSnapshot, BrokerModifyResult) with fingerprinting
- MockBrokerAdapter compliance with truthful capability declarations
"""
import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

root_dir = Path(__file__).resolve().parents[1]
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from engine.broker_adapters.contracts import (
    BaseBrokerAdapter,
    BrokerAdapter,
    BrokerAdapterError,
    BrokerAdapterUnavailableError,
    BrokerAuthError,
    BrokerCapability,
    BrokerConnectionState,
    BrokerFundsSnapshot,
    BrokerModifyResult,
    BrokerNetworkError,
    BrokerOrderRejectedError,
    BrokerPositionSnapshot,
    BrokerRateLimitError,
    UnsupportedCapabilityError,
)
from engine.broker_adapters.mock_broker import MockBrokerAdapter


class DummyAdapterWithCustomCaps(BaseBrokerAdapter):
    adapter_id = "test-dummy"

    def supported_capabilities(self) -> frozenset[BrokerCapability]:
        return frozenset({BrokerCapability.AUTH, BrokerCapability.FUNDS})

    def query_funds(self) -> BrokerFundsSnapshot | None:
        self._require_capability(BrokerCapability.FUNDS)
        return BrokerFundsSnapshot(
            available_balance=Decimal("50000.00"),
            used_margin=Decimal("12000.00"),
            total_equity=Decimal("62000.00"),
            observed_at=datetime.now(timezone.utc),
        )


class TestCommonBrokerContract(unittest.TestCase):

    def test_broker_capabilities_enumeration(self):
        expected_capabilities = {
            "AUTH",
            "ACCOUNT_PROFILE",
            "FUNDS",
            "HISTORICAL_DATA",
            "LIVE_QUOTES",
            "WEBSOCKET",
            "OPTION_CHAIN",
            "PLACE_ORDER",
            "MODIFY_ORDER",
            "CANCEL_ORDER",
            "ORDER_STATUS",
            "TRADES_FILLS",
            "POSITIONS",
            "RECONNECT",
            "RECONCILIATION",
        }
        declared_capabilities = {c.value for c in BrokerCapability}
        self.assertEqual(expected_capabilities, declared_capabilities)

    def test_unsupported_capability_error_attributes(self):
        err = UnsupportedCapabilityError(BrokerCapability.MODIFY_ORDER, "test_adapter")
        self.assertIsInstance(err, BrokerAdapterError)
        self.assertEqual(err.capability, BrokerCapability.MODIFY_ORDER)
        self.assertEqual(err.adapter_id, "test_adapter")
        self.assertIn("MODIFY_ORDER", str(err))
        self.assertIn("test_adapter", str(err))

    def test_error_hierarchy(self):
        auth_err = BrokerAuthError("token expired")
        self.assertIsInstance(auth_err, BrokerAdapterError)

        net_err = BrokerNetworkError("connection timeout")
        self.assertIsInstance(net_err, BrokerAdapterError)

        rate_err = BrokerRateLimitError("429 too many requests", retry_after_seconds=2.5)
        self.assertIsInstance(rate_err, BrokerAdapterError)
        self.assertEqual(rate_err.retry_after_seconds, 2.5)

        rej_err = BrokerOrderRejectedError("insufficient funds", rejection_code="RMS_MARGIN_FAIL")
        self.assertIsInstance(rej_err, BrokerAdapterError)
        self.assertEqual(rej_err.rejection_code, "RMS_MARGIN_FAIL")

    def test_base_broker_adapter_capability_enforcement(self):
        adapter = DummyAdapterWithCustomCaps()
        self.assertTrue(adapter.supports(BrokerCapability.AUTH))
        self.assertTrue(adapter.supports(BrokerCapability.FUNDS))
        self.assertFalse(adapter.supports(BrokerCapability.PLACE_ORDER))
        self.assertFalse(adapter.supports(BrokerCapability.MODIFY_ORDER))

        # Querying funds works
        funds = adapter.query_funds()
        self.assertIsNotNone(funds)
        self.assertEqual(funds.available_balance, Decimal("50000.00"))

        # Querying positions or modify raises UnsupportedCapabilityError
        with self.assertRaises(UnsupportedCapabilityError) as ctx:
            adapter.query_positions()
        self.assertEqual(ctx.exception.capability, BrokerCapability.POSITIONS)

        with self.assertRaises(UnsupportedCapabilityError) as ctx:
            adapter.modify(
                "ord-1",
                timestamp=datetime.now(timezone.utc),
            )
        self.assertEqual(ctx.exception.capability, BrokerCapability.MODIFY_ORDER)

    def test_funds_snapshot_validation_and_fingerprinting(self):
        now = datetime.now(timezone.utc)
        funds = BrokerFundsSnapshot(
            available_balance=Decimal("150000.50"),
            used_margin=Decimal("25000.00"),
            total_equity=Decimal("175000.50"),
            observed_at=now,
            currency="INR",
        )
        self.assertEqual(funds.available_balance, Decimal("150000.50"))
        self.assertEqual(funds.currency, "INR")
        self.assertTrue(isinstance(funds.snapshot_identity, str) and len(funds.snapshot_identity) > 0)

        # Naive datetime fails
        with self.assertRaises(ValueError):
            BrokerFundsSnapshot(
                available_balance=Decimal("100"),
                used_margin=Decimal("0"),
                total_equity=Decimal("100"),
                observed_at=datetime.now(),  # naive
            )

    def test_position_snapshot_validation_and_fingerprinting(self):
        now = datetime.now(timezone.utc)
        pos = BrokerPositionSnapshot(
            instrument_token="NSE_FO|54321",
            trading_symbol="NIFTY26SEP24500CE",
            quantity=Decimal("75"),
            average_price=Decimal("120.50"),
            product_type="MIS",
            observed_at=now,
            current_price=Decimal("135.00"),
            pnl=Decimal("1087.50"),
        )
        self.assertEqual(pos.quantity, Decimal("75"))
        self.assertEqual(pos.current_price, Decimal("135.00"))
        self.assertTrue(isinstance(pos.position_identity, str) and len(pos.position_identity) > 0)

        # Empty trading symbol fails
        with self.assertRaises(ValueError):
            BrokerPositionSnapshot(
                instrument_token="TOK",
                trading_symbol="   ",
                quantity=Decimal("10"),
                average_price=Decimal("10"),
                product_type="MIS",
                observed_at=now,
            )

    def test_modify_result_validation_and_fingerprinting(self):
        now = datetime.now(timezone.utc)
        res = BrokerModifyResult(
            order_id="ord-123",
            broker_order_identity="boid-456",
            modified=True,
            timestamp=now,
        )
        self.assertTrue(res.modified)
        self.assertIsNone(res.rejection_reason)
        self.assertTrue(isinstance(res.modify_identity, str) and len(res.modify_identity) > 0)

    def test_mock_broker_adapter_protocol_and_capabilities(self):
        mock = MockBrokerAdapter()
        self.assertTrue(isinstance(mock, BrokerAdapter))
        self.assertTrue(mock.supports(BrokerCapability.PLACE_ORDER))
        self.assertTrue(mock.supports(BrokerCapability.CANCEL_ORDER))
        self.assertTrue(mock.supports(BrokerCapability.ORDER_STATUS))
        self.assertTrue(mock.supports(BrokerCapability.TRADES_FILLS))
        self.assertTrue(mock.supports(BrokerCapability.RECONNECT))
        self.assertTrue(mock.supports(BrokerCapability.RECONCILIATION))
        self.assertFalse(mock.supports(BrokerCapability.MODIFY_ORDER))

        # Modify raises UnsupportedCapabilityError
        with self.assertRaises(UnsupportedCapabilityError):
            mock.modify("ord-1", timestamp=datetime.now(timezone.utc))

        # Query while connected
        positions = mock.query_positions()
        self.assertEqual(positions, ())

        # Disconnect and verify fail-closed
        mock.disconnect("test_disconnect")
        self.assertEqual(mock.connection_state, BrokerConnectionState.DISCONNECTED)
        with self.assertRaises(BrokerAdapterUnavailableError):
            mock.query_positions()
        with self.assertRaises(BrokerAdapterUnavailableError):
            mock.query_funds()

        # Reconnect
        mock.reconnect()
        self.assertEqual(mock.connection_state, BrokerConnectionState.CONNECTED)
        self.assertEqual(mock.query_positions(), ())


if __name__ == "__main__":
    unittest.main()
