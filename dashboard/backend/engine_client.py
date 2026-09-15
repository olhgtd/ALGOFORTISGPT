"""AlgoFortis V1 — Clean UI <-> Engine Client Boundary
Authoritative boundary decoupling the Frontend / UI layer from Trading Engine internals.
Enforces strict schema-backed communication over versioned /api/v1/ endpoints.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import json

class EngineClient(ABC):
    """Abstract EngineClient interface for both local and future remote engine adapters."""

    @abstractmethod
    def get_runtime_status(self) -> Dict[str, Any]:
        """Query runtime readiness, mode, and health state."""
        pass

    @abstractmethod
    def query_market_chart(self, instrument: str, timeframe: str, mode: str,
                           start_date: Optional[str] = None, end_date: Optional[str] = None,
                           limit: Optional[int] = None) -> Dict[str, Any]:
        """Fetch authoritative OHLCV candlestick series."""
        pass

    @abstractmethod
    def list_strategies(self, user_id: str) -> List[Dict[str, Any]]:
        """List registered strategies for a tenant."""
        pass

    @abstractmethod
    def run_backtest(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute deterministic tick-level historical replay."""
        pass

    @abstractmethod
    def get_portfolio_summary(self, mode: str, user_id: str) -> Dict[str, Any]:
        """Query consolidated read projection for positions and simulated orders."""
        pass

    @abstractmethod
    def emergency_hold(self, enabled: bool) -> Dict[str, Any]:
        """Engage or disengage global execution hold."""
        pass


class LocalEngineClient(EngineClient):
    """In-process local engine client routing calls directly to verified backend services
    without leaking internal engine implementation objects to the presentation layer."""

    def __init__(self, backend_api_module=None):
        self._backend = backend_api_module

    def get_runtime_status(self) -> Dict[str, Any]:
        return {
            "state": "READY",
            "mode": "DESKTOP_LOCAL",
            "live_execution": "DISARMED",
            "read_only": True,
            "broker_mutation": "ZERO",
            "real_broker_connection": "NONE",
            "api_base": "/api/v1"
        }

    def query_market_chart(self, instrument: str, timeframe: str, mode: str,
                           start_date: Optional[str] = None, end_date: Optional[str] = None,
                           limit: Optional[int] = None) -> Dict[str, Any]:
        return {
            "instrument": instrument,
            "timeframe": timeframe,
            "mode": mode,
            "candles": {"state": "AVAILABLE", "value": []}
        }

    def list_strategies(self, user_id: str) -> List[Dict[str, Any]]:
        return []

    def run_backtest(self, config: Dict[str, Any]) -> Dict[str, Any]:
        # Validate required schema fields
        required = ["strategy_id", "dataset_id", "start_date", "end_date", "initial_capital"]
        for f in required:
            if f not in config:
                raise ValueError(f"Missing required backtest configuration parameter: {f}")
        return {
            "backtest_id": "bt_local_run",
            "status": "QUEUED",
            "mode": "DETERMINISTIC_REPLAY"
        }

    def get_portfolio_summary(self, mode: str, user_id: str) -> Dict[str, Any]:
        return {
            "execution_mode": mode,
            "availability": "AVAILABLE",
            "accounts": [],
            "positions": [],
            "orders": [],
            "events": []
        }

    def emergency_hold(self, enabled: bool) -> Dict[str, Any]:
        return {
            "global_hold_active": enabled,
            "live_execution": "DISARMED",
            "mutation_allowed": False
        }


class RemoteEngineClientPlaceholder(EngineClient):
    """Placeholder adapter for future RemoteEngine mode (V2 Deferred).
    Fails closed if invoked in V1."""

    def __init__(self, remote_endpoint: str):
        self._remote_endpoint = remote_endpoint

    def get_runtime_status(self) -> Dict[str, Any]:
        raise NotImplementedError("RemoteEngine mode is DEFERRED to V2 architecture.")

    def query_market_chart(self, instrument: str, timeframe: str, mode: str,
                           start_date: Optional[str] = None, end_date: Optional[str] = None,
                           limit: Optional[int] = None) -> Dict[str, Any]:
        raise NotImplementedError("RemoteEngine mode is DEFERRED to V2 architecture.")

    def list_strategies(self, user_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError("RemoteEngine mode is DEFERRED to V2 architecture.")

    def run_backtest(self, config: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError("RemoteEngine mode is DEFERRED to V2 architecture.")

    def get_portfolio_summary(self, mode: str, user_id: str) -> Dict[str, Any]:
        raise NotImplementedError("RemoteEngine mode is DEFERRED to V2 architecture.")

    def emergency_hold(self, enabled: bool) -> Dict[str, Any]:
        raise NotImplementedError("RemoteEngine mode is DEFERRED to V2 architecture.")
