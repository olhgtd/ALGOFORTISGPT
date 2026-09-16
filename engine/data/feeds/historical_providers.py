"""AlgoFortis V1 — Four Broker Historical Data Provider Adapters (ADR §129 / Phase 3).

Implements provider adapters for:
1. Upstox Historical Data (V2 Historical Candle API)
2. Zerodha / Kite Historical Data (Kite Connect V3 Historical API)
3. Dhan Historical Data (DhanHQ V2 Charts Historical API)
4. Angel One Historical Data (SmartAPI Historical Candle API)

All adapters:
- Adhere to HistoricalDataService MarketDataProvider protocol
- Truthfully declare capabilities (NIFTY & BANKNIFTY current scope)
- Report UNSUPPORTED_CAPABILITY for unsupported operations
- Normalize provider-specific JSON outputs into canonical pandas OHLCV DataFrames
- Support mockable HTTP transport for deterministic automated testing
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, Optional, Set
from zoneinfo import ZoneInfo

import pandas as pd

from engine.broker_adapters.contracts import BrokerCapability, UnsupportedCapabilityError

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc

SUPPORTED_HISTORICAL_INSTRUMENTS: frozenset[str] = frozenset({"NIFTY", "BANKNIFTY"})
SUPPORTED_HISTORICAL_TIMEFRAMES: frozenset[str] = frozenset({"1m", "5m", "15m", "30m", "1H", "1d"})


class BaseHistoricalDataProvider(ABC):
    """Base historical data provider with truthful capability checks and canonical normalization."""

    def __init__(
        self,
        *,
        provider_name: str,
        provider_id: str,
        api_key: str = "",
        access_token: str = "",
        supported_instruments: set[str] | None = None,
        supported_timeframes: set[str] | None = None,
        http_transport: Callable[[str, str, dict[str, Any] | None, dict[str, Any] | None], Any] | None = None,
    ) -> None:
        self._provider_name = provider_name
        self._provider_id = provider_id
        self._api_key = api_key
        self._access_token = access_token
        self._supported_instruments = set(supported_instruments or SUPPORTED_HISTORICAL_INSTRUMENTS)
        self._supported_timeframes = set(supported_timeframes or SUPPORTED_HISTORICAL_TIMEFRAMES)
        self._http_transport = http_transport
        self._enabled = True

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def is_configured(self) -> bool:
        return bool(self._access_token or self._api_key or self._http_transport)

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    @property
    def supported_instruments(self) -> set[str]:
        return self._supported_instruments

    @property
    def supported_timeframes(self) -> set[str]:
        return self._supported_timeframes

    def get_status(self) -> dict[str, Any]:
        return {
            "provider_id": self._provider_id,
            "provider_name": self._provider_name,
            "is_configured": self.is_configured,
            "is_enabled": self._enabled,
            "supported_instruments": sorted(list(self._supported_instruments)),
            "supported_timeframes": sorted(list(self._supported_timeframes)),
        }

    def _validate_request(self, instrument: str, timeframe: str) -> tuple[str, str]:
        inst = instrument.upper().strip()
        tf = timeframe.strip()
        if inst not in self._supported_instruments:
            raise UnsupportedCapabilityError(
                f"Instrument '{inst}' is not supported for historical fetch by provider '{self._provider_name}'",
                self._provider_id,
            )
        if tf not in self._supported_timeframes:
            raise UnsupportedCapabilityError(
                f"Timeframe '{tf}' is not supported for historical fetch by provider '{self._provider_name}'",
                self._provider_id,
            )
        return inst, tf

    @abstractmethod
    def fetch_historical_range(
        self,
        *,
        instrument: str,
        timeframe: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Fetch and normalize historical bars into canonical DataFrame."""
        pass

    @staticmethod
    def _finalize_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
        """Ensure canonical sorting, deduplication, and column types."""
        if not rows:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        df = pd.DataFrame(rows)
        # Parse timestamp to aware datetime
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float)

        df = df.sort_values(by="timestamp").drop_duplicates(subset=["timestamp"]).reset_index(drop=True)
        return df


class UpstoxHistoricalDataProvider(BaseHistoricalDataProvider):
    """Upstox V2 Historical Candle Data Provider."""

    INSTRUMENT_KEYS = {
        "NIFTY": "NSE_INDEX|Nifty 50",
        "BANKNIFTY": "NSE_INDEX|Nifty Bank",
    }
    TIMEFRAME_MAP = {
        "1m": "1minute",
        "5m": "5minute",
        "15m": "15minute",
        "30m": "30minute",
        "1H": "60minute",
        "1d": "day",
    }

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("provider_name", "UPSTOX")
        kwargs.setdefault("provider_id", "upstox-historical-v2")
        super().__init__(**kwargs)

    def fetch_historical_range(
        self,
        *,
        instrument: str,
        timeframe: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        inst, tf = self._validate_request(instrument, timeframe)
        key = self.INSTRUMENT_KEYS[inst]
        interval = self.TIMEFRAME_MAP[tf]

        from_date_str = start_date.strftime("%Y-%m-%d")
        to_date_str = end_date.strftime("%Y-%m-%d")
        url = f"https://api.upstox.com/v2/historical-candle/{key}/{interval}/{to_date_str}/{from_date_str}"

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._access_token}",
        }

        if self._http_transport is not None:
            res = self._http_transport("GET", url, headers, None)
        else:
            raise UnsupportedCapabilityError("Live HTTP fetch without transport or live credentials", self._provider_id)

        return self.normalize_upstox_response(res)

    @classmethod
    def normalize_upstox_response(cls, response_data: Any) -> pd.DataFrame:
        if isinstance(response_data, str):
            response_data = json.loads(response_data)

        if response_data.get("status") != "success":
            raise ValueError(f"Upstox historical API error: {response_data}")

        candles = response_data.get("data", {}).get("candles", [])
        rows = []
        for c in candles:
            # Format: [timestamp, open, high, low, close, volume, open_interest]
            rows.append({
                "timestamp": c[0],
                "open": c[1],
                "high": c[2],
                "low": c[3],
                "close": c[4],
                "volume": c[5],
                "oi": c[6] if len(c) > 6 else 0,
            })
        return cls._finalize_dataframe(rows)


class KiteHistoricalDataProvider(BaseHistoricalDataProvider):
    """Zerodha / Kite Connect V3 Historical Candle Data Provider."""

    INSTRUMENT_TOKENS = {
        "NIFTY": "256265",
        "BANKNIFTY": "260105",
    }
    TIMEFRAME_MAP = {
        "1m": "minute",
        "5m": "5minute",
        "15m": "15minute",
        "30m": "30minute",
        "1H": "60minute",
        "1d": "day",
    }

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("provider_name", "ZERODHA_KITE")
        kwargs.setdefault("provider_id", "kite-historical-v3")
        super().__init__(**kwargs)

    def fetch_historical_range(
        self,
        *,
        instrument: str,
        timeframe: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        inst, tf = self._validate_request(instrument, timeframe)
        token = self.INSTRUMENT_TOKENS[inst]
        interval = self.TIMEFRAME_MAP[tf]

        from_date_str = start_date.strftime("%Y-%m-%d")
        to_date_str = end_date.strftime("%Y-%m-%d")
        url = f"https://api.kite.trade/instruments/historical/{token}/{interval}?from={from_date_str}&to={to_date_str}"

        headers = {
            "X-Kite-Version": "3",
            "Authorization": f"token {self._api_key}:{self._access_token}",
        }

        if self._http_transport is not None:
            res = self._http_transport("GET", url, headers, None)
        else:
            raise UnsupportedCapabilityError("Live HTTP fetch without transport or live credentials", self._provider_id)

        return self.normalize_kite_response(res)

    @classmethod
    def normalize_kite_response(cls, response_data: Any) -> pd.DataFrame:
        if isinstance(response_data, str):
            response_data = json.loads(response_data)

        if response_data.get("status") != "success":
            raise ValueError(f"Kite historical API error: {response_data}")

        candles = response_data.get("data", {}).get("candles", [])
        rows = []
        for c in candles:
            # Format: [timestamp, open, high, low, close, volume, oi]
            rows.append({
                "timestamp": c[0],
                "open": c[1],
                "high": c[2],
                "low": c[3],
                "close": c[4],
                "volume": c[5],
                "oi": c[6] if len(c) > 6 else 0,
            })
        return cls._finalize_dataframe(rows)


class DhanHistoricalDataProvider(BaseHistoricalDataProvider):
    """DhanHQ V2 Historical Charts Data Provider."""

    SECURITY_IDS = {
        "NIFTY": "13",
        "BANKNIFTY": "25",
    }

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("provider_name", "DHAN")
        kwargs.setdefault("provider_id", "dhan-historical-v2")
        super().__init__(**kwargs)

    def fetch_historical_range(
        self,
        *,
        instrument: str,
        timeframe: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        inst, tf = self._validate_request(instrument, timeframe)
        sec_id = self.SECURITY_IDS[inst]

        url = "https://api.dhan.co/v2/charts/historical"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "access-token": self._access_token,
        }
        payload = {
            "securityId": sec_id,
            "exchangeSegment": "IDX_I",
            "instrument": "INDEX",
            "expiryCode": 0,
            "fromDate": start_date.strftime("%Y-%m-%d"),
            "toDate": end_date.strftime("%Y-%m-%d"),
        }

        if self._http_transport is not None:
            res = self._http_transport("POST", url, headers, payload)
        else:
            raise UnsupportedCapabilityError("Live HTTP fetch without transport or live credentials", self._provider_id)

        return self.normalize_dhan_response(res)

    @classmethod
    def normalize_dhan_response(cls, response_data: Any) -> pd.DataFrame:
        if isinstance(response_data, str):
            response_data = json.loads(response_data)

        # Dhan returns arrays: {"open": [...], "high": [...], "low": [...], "close": [...], "volume": [...], "start_Time": [...]}
        times = response_data.get("start_Time", [])
        opens = response_data.get("open", [])
        highs = response_data.get("high", [])
        lows = response_data.get("low", [])
        closes = response_data.get("close", [])
        volumes = response_data.get("volume", [0] * len(times))

        rows = []
        for i in range(len(times)):
            rows.append({
                "timestamp": times[i],
                "open": opens[i],
                "high": highs[i],
                "low": lows[i],
                "close": closes[i],
                "volume": volumes[i] if i < len(volumes) else 0,
            })
        return cls._finalize_dataframe(rows)


class AngelOneHistoricalDataProvider(BaseHistoricalDataProvider):
    """Angel One SmartAPI Historical Candle Data Provider."""

    SYMBOL_TOKENS = {
        "NIFTY": "99926000",
        "BANKNIFTY": "99926009",
    }
    TIMEFRAME_MAP = {
        "1m": "ONE_MINUTE",
        "5m": "FIVE_MINUTE",
        "15m": "FIFTEEN_MINUTE",
        "30m": "THIRTY_MINUTE",
        "1H": "ONE_HOUR",
        "1d": "ONE_DAY",
    }

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("provider_name", "ANGEL_ONE")
        kwargs.setdefault("provider_id", "angelone-historical-v1")
        super().__init__(**kwargs)

    def fetch_historical_range(
        self,
        *,
        instrument: str,
        timeframe: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        inst, tf = self._validate_request(instrument, timeframe)
        token = self.SYMBOL_TOKENS[inst]
        interval = self.TIMEFRAME_MAP[tf]

        url = "https://apiconnect.angelone.in/rest/secure/angelbroking/historical/v1/getCandleData"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "127.0.0.1",
            "X-MACAddress": "00:00:00:00:00:00",
            "X-PrivateKey": self._api_key,
            "Authorization": f"Bearer {self._access_token}",
        }
        payload = {
            "exchange": "NSE",
            "symboltoken": token,
            "interval": interval,
            "fromdate": f"{start_date.strftime('%Y-%m-%d')} 09:15",
            "todate": f"{end_date.strftime('%Y-%m-%d')} 15:30",
        }

        if self._http_transport is not None:
            res = self._http_transport("POST", url, headers, payload)
        else:
            raise UnsupportedCapabilityError("Live HTTP fetch without transport or live credentials", self._provider_id)

        return self.normalize_angelone_response(res)

    @classmethod
    def normalize_angelone_response(cls, response_data: Any) -> pd.DataFrame:
        if isinstance(response_data, str):
            response_data = json.loads(response_data)

        if not response_data.get("status"):
            raise ValueError(f"Angel One historical API error: {response_data}")

        candles = response_data.get("data", [])
        rows = []
        for c in candles:
            # Format: [timestamp, open, high, low, close, volume]
            rows.append({
                "timestamp": c[0],
                "open": c[1],
                "high": c[2],
                "low": c[3],
                "close": c[4],
                "volume": c[5],
            })
        return cls._finalize_dataframe(rows)


def create_historical_provider(
    provider_name: str,
    *,
    api_key: str = "",
    access_token: str = "",
    http_transport: Any = None,
) -> BaseHistoricalDataProvider:
    """Factory creating the appropriate historical provider adapter."""
    norm_name = provider_name.upper().strip()
    if norm_name == "UPSTOX":
        return UpstoxHistoricalDataProvider(
            api_key=api_key,
            access_token=access_token,
            http_transport=http_transport,
        )
    elif norm_name in ("ZERODHA", "KITE", "ZERODHA_KITE"):
        return KiteHistoricalDataProvider(
            api_key=api_key,
            access_token=access_token,
            http_transport=http_transport,
        )
    elif norm_name == "DHAN":
        return DhanHistoricalDataProvider(
            api_key=api_key,
            access_token=access_token,
            http_transport=http_transport,
        )
    elif norm_name in ("ANGELONE", "ANGEL_ONE"):
        return AngelOneHistoricalDataProvider(
            api_key=api_key,
            access_token=access_token,
            http_transport=http_transport,
        )
    else:
        raise UnsupportedCapabilityError(
            f"Provider '{provider_name}' is not recognized for historical market data",
            provider_name,
        )
