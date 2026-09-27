from __future__ import annotations

import pytest

from engine.data.transports.brokers import (
    AngelOneTransportDriver,
    DhanTransportDriver,
    UpstoxTransportDriver,
    ZerodhaTransportDriver,
)
from engine.data.transports.contracts import BrokerId
from engine.data.transports.registry import MarketDataTransportRegistry, default_transport_registry


def test_default_registry_contains_exact_initial_four_market_data_drivers() -> None:
    registry = default_transport_registry()

    assert registry.supported_keys == ("ANGELONE", "DHAN", "UPSTOX", "ZERODHA")
    assert registry.resolve(BrokerId.ANGELONE) is AngelOneTransportDriver
    assert registry.resolve(BrokerId.ZERODHA) is ZerodhaTransportDriver
    assert registry.resolve(BrokerId.DHAN) is DhanTransportDriver
    assert registry.resolve(BrokerId.UPSTOX) is UpstoxTransportDriver


def test_registry_is_deny_duplicate_by_default() -> None:
    registry = MarketDataTransportRegistry()
    registry.register(BrokerId.ANGELONE, AngelOneTransportDriver)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(BrokerId.ANGELONE, AngelOneTransportDriver)


def test_registry_has_no_cross_broker_failover_or_execution_routing_surface() -> None:
    names = set(MarketDataTransportRegistry.__dict__)
    assert not ({"failover", "route_order", "submit_order", "select_execution_broker"} & names)
