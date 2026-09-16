"""Broker adapter factory instantiating concrete adapters per provider.

Supports:
- UPSTOX -> UpstoxBrokerAdapter
- ZERODHA / KITE -> KiteBrokerAdapter
- DHAN -> DhanBrokerAdapter
- ANGELONE / ANGEL_ONE -> AngelOneBrokerAdapter
- MOCK / PAPER_INTERNAL -> MockBrokerAdapter
"""

from __future__ import annotations

from typing import Any

from engine.broker_adapters.angel_adapter import AngelOneBrokerAdapter
from engine.broker_adapters.contracts import BrokerAdapter
from engine.broker_adapters.dhan_adapter import DhanBrokerAdapter
from engine.broker_adapters.kite_adapter import KiteBrokerAdapter
from engine.broker_adapters.mock_broker import MockBrokerAdapter
from engine.broker_adapters.upstox_adapter import UpstoxBrokerAdapter


class BrokerAdapterFactory:
    """Factory creating concrete broker execution adapters."""

    @staticmethod
    def create_adapter(
        provider: str,
        credentials: Any = None,
        *,
        http_client: Any = None,
        **kwargs: Any,
    ) -> BrokerAdapter:
        """Instantiate the authoritative broker adapter for the given provider."""
        prov = str(provider or "").upper().strip()
        if prov == "UPSTOX":
            return UpstoxBrokerAdapter(credentials=credentials, http_client=http_client, **kwargs)
        elif prov in {"ZERODHA", "KITE"}:
            return KiteBrokerAdapter(credentials=credentials, http_client=http_client, **kwargs)
        elif prov == "DHAN":
            return DhanBrokerAdapter(credentials=credentials, http_client=http_client, **kwargs)
        elif prov in {"ANGELONE", "ANGEL_ONE"}:
            return AngelOneBrokerAdapter(credentials=credentials, http_client=http_client, **kwargs)
        elif prov in {"MOCK", "MOCK_INTERNAL", "PAPER_INTERNAL"}:
            return MockBrokerAdapter(**kwargs)
        else:
            raise ValueError(
                f"Unsupported broker provider: '{provider}'. "
                "Supported: UPSTOX, ZERODHA/KITE, DHAN, ANGELONE, MOCK"
            )
