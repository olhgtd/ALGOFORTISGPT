"""Registry for market-data transport drivers only.

This registry is intentionally separate from execution/account broker adapter
registries and contains no cross-broker failover or order-routing behavior.
"""

from __future__ import annotations

from collections.abc import Callable

from engine.data.transports.brokers import (
    AngelOneTransportDriver,
    DhanTransportDriver,
    UpstoxTransportDriver,
    ZerodhaTransportDriver,
)
from engine.data.transports.contracts import BrokerId, BrokerRef, broker_ref_key


DriverFactory = Callable[..., object]


class MarketDataTransportRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, DriverFactory] = {}

    def register(self, broker_id: BrokerRef, factory: DriverFactory) -> None:
        key = broker_ref_key(broker_id)
        if not callable(factory):
            raise TypeError("factory must be callable")
        if key in self._factories:
            raise ValueError(f"market-data transport already registered for {key}")
        self._factories[key] = factory

    def resolve(self, broker_id: BrokerRef) -> DriverFactory:
        key = broker_ref_key(broker_id)
        try:
            return self._factories[key]
        except KeyError as exc:
            raise KeyError(f"no market-data transport registered for {key}") from exc

    @property
    def supported_keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))


def default_transport_registry() -> MarketDataTransportRegistry:
    registry = MarketDataTransportRegistry()
    registry.register(BrokerId.ANGELONE, AngelOneTransportDriver)
    registry.register(BrokerId.ZERODHA, ZerodhaTransportDriver)
    registry.register(BrokerId.DHAN, DhanTransportDriver)
    registry.register(BrokerId.UPSTOX, UpstoxTransportDriver)
    return registry


__all__ = ["DriverFactory", "MarketDataTransportRegistry", "default_transport_registry"]
