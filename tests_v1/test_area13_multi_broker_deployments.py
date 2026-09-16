"""Tests for Phase 9: Multi-Broker Strategy Deployments and Signal Routing.

Verifies:
1. A single strategy S1 can be simultaneously deployed across Upstox, Kite, Dhan, and Angel One.
2. Signal routing generates dedicated orders per deployment.
3. Deployment-aware signal deduplication prevents cross-deployment interference.
4. Independent risk limits per deployment account.
5. Strict failure isolation: failure on Broker A never blocks Broker B, C, or D.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from engine.broker_adapters import (
    AngelOneBrokerAdapter,
    BrokerAdapterFactory,
    BrokerNetworkError,
    DhanBrokerAdapter,
    KiteBrokerAdapter,
    UpstoxBrokerAdapter,
)
from engine.orchestration.deployment_executor import MultiBrokerDeploymentExecutor
from engine.orchestration.signal_intake import SignalIntent
from engine.portfolio.model import InstrumentIdentity, InstrumentSpecification


def _make_dummy_instrument():
    identity = InstrumentIdentity("NSE", "NIFTY", "index")
    spec = InstrumentSpecification(identity, datetime(2020, 1, 1).date(), 1, 50, 50, "INR", "0.05")
    return identity, spec


def _make_signal(minute: int = 30, sequence: int = 1):
    return SignalIntent(
        strategy_id="strat-alpha",
        strategy_version="1.0",
        symbol="NIFTY",
        timeframe="5m",
        originating_timestamp=datetime(2026, 9, 16, 9, minute, tzinfo=timezone.utc),
        action="BUY",
        confidence=1.0,
        metadata={"seq": sequence},
    )


class TestMultiBrokerDeployments(unittest.TestCase):
    def setUp(self):
        self.executor = MultiBrokerDeploymentExecutor()
        self.ident, self.spec = _make_dummy_instrument()

        # Set up 4 mock adapters for 4 brokers
        self.upstox_client = MagicMock()
        self.upstox_client.post.return_value = MagicMock(status_code=200, json=lambda: {"status": "success", "data": {"order_id": "UP-1"}})
        self.upstox_adapter = UpstoxBrokerAdapter({"access_token": "tok_up"}, http_client=self.upstox_client)

        self.kite_client = MagicMock()
        self.kite_client.post.return_value = MagicMock(status_code=200, json=lambda: {"status": "success", "data": {"order_id": "KT-1"}})
        self.kite_adapter = KiteBrokerAdapter({"access_token": "tok_kt", "api_key": "k"}, http_client=self.kite_client)

        self.dhan_client = MagicMock()
        self.dhan_client.post.return_value = MagicMock(status_code=200, json=lambda: {"status": "success", "orderId": "DH-1"})
        self.dhan_adapter = DhanBrokerAdapter({"access_token": "tok_dh", "client_id": "c"}, http_client=self.dhan_client)

        self.angel_client = MagicMock()
        self.angel_client.post.return_value = MagicMock(status_code=200, json=lambda: {"status": True, "data": {"orderid": "AO-1"}})
        self.angel_adapter = AngelOneBrokerAdapter({"jwt_token": "tok_ao", "api_key": "k"}, http_client=self.angel_client)

        # Register all 4 deployments for strat-alpha
        self.executor.register_deployment(
            deployment_id="dep-upstox",
            strategy_id="strat-alpha",
            strategy_version="1.0",
            connection_id="conn-upstox",
            provider="UPSTOX",
            broker_adapter=self.upstox_adapter,
            max_position_size=Decimal("100"),
        )
        self.executor.register_deployment(
            deployment_id="dep-kite",
            strategy_id="strat-alpha",
            strategy_version="1.0",
            connection_id="conn-kite",
            provider="KITE",
            broker_adapter=self.kite_adapter,
            max_position_size=Decimal("200"),
        )
        self.executor.register_deployment(
            deployment_id="dep-dhan",
            strategy_id="strat-alpha",
            strategy_version="1.0",
            connection_id="conn-dhan",
            provider="DHAN",
            broker_adapter=self.dhan_adapter,
            max_position_size=Decimal("200"),
        )
        self.executor.register_deployment(
            deployment_id="dep-angel",
            strategy_id="strat-alpha",
            strategy_version="1.0",
            connection_id="conn-angel",
            provider="ANGELONE",
            broker_adapter=self.angel_adapter,
            max_position_size=Decimal("200"),
        )

    def test_simultaneous_multi_broker_signal_routing(self):
        """Signal on strategy S1 executes on all 4 broker deployments simultaneously."""
        signal = _make_signal(sequence=1)
        results = self.executor.route_signal(
            signal,
            instrument_identity=self.ident,
            specification=self.spec,
            quantity=Decimal("50"),
            price=Decimal("25000.00"),
        )

        self.assertEqual(len(results), 4)
        for dep_id, res in results.items():
            self.assertTrue(res.accepted, f"Deployment {dep_id} did not accept: {res}")
            self.assertFalse(res.duplicate)
            self.assertIsNotNone(res.order_id)

    def test_deployment_aware_signal_deduplication(self):
        """Submitting duplicate signal on S1 produces duplicate rejection per deployment."""
        signal = _make_signal(sequence=2)

        # First pass -> accepted
        res1 = self.executor.route_signal(
            signal,
            instrument_identity=self.ident,
            specification=self.spec,
            quantity=Decimal("50"),
        )
        self.assertTrue(res1["dep-upstox"].accepted)

        # Second pass with same signal -> duplicate rejected on all deployments
        res2 = self.executor.route_signal(
            signal,
            instrument_identity=self.ident,
            specification=self.spec,
            quantity=Decimal("50"),
        )
        for dep_id, res in res2.items():
            self.assertFalse(res.accepted)
            self.assertTrue(res.duplicate)

    def test_independent_risk_limits(self):
        """If one deployment exceeds risk limit, other deployments execute normally."""
        # dep-upstox has max_position_size = 100
        # Signal 1 (qty 75)
        sig1 = _make_signal(minute=30)
        res1 = self.executor.route_signal(sig1, instrument_identity=self.ident, specification=self.spec, quantity=Decimal("75"))
        self.assertTrue(res1["dep-upstox"].accepted)
        self.assertTrue(res1["dep-kite"].accepted)

        # Signal 2 (qty 50): dep-upstox now exceeds 100 (75 + 50 = 125 > 100), but dep-kite limit is 200
        sig2 = _make_signal(minute=35)
        res2 = self.executor.route_signal(sig2, instrument_identity=self.ident, specification=self.spec, quantity=Decimal("50"))

        # Upstox rejected due to its account risk limit
        self.assertFalse(res2["dep-upstox"].accepted)
        self.assertIn("risk_limit_exceeded", res2["dep-upstox"].reason)

        # Other 3 deployments still accepted without interruption!
        self.assertTrue(res2["dep-kite"].accepted)
        self.assertTrue(res2["dep-dhan"].accepted)
        self.assertTrue(res2["dep-angel"].accepted)

    def test_isolated_failure_boundary(self):
        """Failure / exception on one broker never crashes or blocks other brokers."""
        # Cause upstox client to throw an unhandled network error
        self.upstox_client.post.side_effect = ConnectionResetError("Upstox connection reset")

        sig = _make_signal(sequence=20)
        results = self.executor.route_signal(sig, instrument_identity=self.ident, specification=self.spec, quantity=Decimal("50"))

        # Upstox failed closed gracefully
        self.assertFalse(results["dep-upstox"].accepted)
        self.assertIn("broker_adapter_exception", results["dep-upstox"].reason)

        # Other 3 brokers completed successfully!
        self.assertTrue(results["dep-kite"].accepted)
        self.assertTrue(results["dep-dhan"].accepted)
        self.assertTrue(results["dep-angel"].accepted)


if __name__ == "__main__":
    unittest.main()
