"""Production historical-data lifecycle authority (Finding F-21).

Owns:
- Instrument & timeframe inventory
- Requested vs locally available range calculations
- Provider abstraction (local import vs external provider)
- Strict validation (monotonicity, duplicates, numeric sanity, bar intervals)
- Cache & gap-fill without duplicate bars or silent substitution
- Authoritative SHA-256 fingerprinting
- F-12 Owner governance registration
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol, Sequence, runtime_checkable
from uuid import uuid4
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from engine.data.feeds.gap_analysis import analyze_target_gaps, TargetGapReport
from engine.market.calendar import (
    DEFAULT_NSE_CALENDAR_ID,
    ClosedSession,
    MarketCalendarAuthority,
    MarketCalendarDataset,
)

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc

SUPPORTED_INSTRUMENTS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"}
SUPPORTED_TIMEFRAMES = {"1m", "5m", "15m", "30m", "1H", "1d"}
TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1H": 3600,
    "1d": 86400,
}


from dashboard.backend.backtest_datasets import DatasetUnavailable


class HistoricalDataError(Exception):
    """Base error for historical data lifecycle."""


class DataProviderNotConfiguredError(HistoricalDataError):
    """Raised when data provisioning is requested but no provider is configured."""


class DataValidationError(HistoricalDataError):
    """Raised when incoming or cached data violates integrity/monotone constraints."""


class DataUnavailableError(HistoricalDataError, DatasetUnavailable):
    """Raised when requested data is not present and cannot be provisioned."""


@dataclass(frozen=True)
class DateInterval:
    start: date
    end: date

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError(f"Invalid interval: start ({self.start}) > end ({self.end})")

    def overlaps_or_adjacent(self, other: "DateInterval") -> bool:
        return not (self.end < other.start - timedelta(days=1) or self.start > other.end + timedelta(days=1))

    def merge(self, other: "DateInterval") -> "DateInterval":
        if not self.overlaps_or_adjacent(other):
            raise ValueError("Intervals do not overlap or touch")
        return DateInterval(min(self.start, other.start), max(self.end, other.end))


@runtime_checkable
class MarketDataProvider(Protocol):
    """Provider interface for provisioning historical market data."""

    @property
    def provider_name(self) -> str:
        ...

    @property
    def is_configured(self) -> bool:
        ...

    def fetch_historical_range(
        self,
        *,
        instrument: str,
        timeframe: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Fetch raw market bars for the requested interval."""
        ...


class UnconfiguredMarketDataProvider:
    """Default fail-closed provider when no external provider is set."""

    @property
    def provider_name(self) -> str:
        return "UNCONFIGURED_PROVIDER"

    @property
    def is_configured(self) -> bool:
        return False

    def get_status(self) -> dict[str, Any]:
        return {
            "provider_id": "UNCONFIGURED",
            "provider_name": self.provider_name,
            "is_configured": False,
            "is_enabled": False,
            "supported_instruments": [],
            "supported_timeframes": [],
        }

    def fetch_historical_range(
        self,
        *,
        instrument: str,
        timeframe: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        raise DataProviderNotConfiguredError(
            "DATA_PROVIDER_NOT_CONFIGURED: No external market data provider is configured. "
            "Configure a provider or import local data explicitly."
        )


class LocalImportDataProvider:
    """Provider that loads from pre-supplied local files or dataframes."""

    def __init__(self, source_path: Path | None = None, source_df: pd.DataFrame | None = None) -> None:
        self._source_path = source_path
        self._source_df = source_df

    @property
    def provider_name(self) -> str:
        return "LOCAL_IMPORT"

    @property
    def is_configured(self) -> bool:
        return self._source_path is not None or self._source_df is not None

    def get_status(self) -> dict[str, Any]:
        return {
            "provider_id": "LOCAL_IMPORT",
            "provider_name": self.provider_name,
            "is_configured": self.is_configured,
            "is_enabled": True,
            "supported_instruments": sorted(list(SUPPORTED_INSTRUMENTS)),
            "supported_timeframes": sorted(list(SUPPORTED_TIMEFRAMES)),
        }

    def fetch_historical_range(
        self,
        *,
        instrument: str,
        timeframe: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        if self._source_df is not None:
            df = self._source_df.copy()
        elif self._source_path is not None and self._source_path.exists():
            if self._source_path.suffix in (".parquet", ".pq"):
                df = pd.read_parquet(self._source_path)
            elif self._source_path.suffix in (".csv", ".txt"):
                df = pd.read_csv(self._source_path)
            else:
                raise DataValidationError(f"Unsupported import format: {self._source_path.suffix}")
        else:
            raise DataUnavailableError("Local import source not available or file not found")
        return df


class TestHistoricalDataProvider:
    """Deterministic offline market data provider for automated tests and validation."""

    __test__ = False

    def __init__(
        self,
        *,
        provider_name: str = "TEST_PROVIDER",
        provider_id: str = "test-provider-01",
        base_price: float = 24000.0,
        supported_instruments: set[str] | None = None,
        supported_timeframes: set[str] | None = None,
        enabled: bool = True,
        gap_dates: set[date] | None = None,
        error_to_raise: Exception | None = None,
        malformed: bool = False,
    ) -> None:
        self._provider_name = provider_name
        self._provider_id = provider_id
        self._base_price = base_price
        self._supported_instruments = supported_instruments or {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"}
        self._supported_timeframes = supported_timeframes or {"1m", "5m", "15m", "30m", "1H", "1d"}
        self._enabled = enabled
        self._gap_dates = gap_dates or set()
        self._error_to_raise = error_to_raise
        self._malformed = malformed
        self.fetch_calls: list[dict[str, Any]] = []

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def is_configured(self) -> bool:
        return True

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

    @property
    def is_synthetic(self) -> bool:
        return True

    @property
    def provider_type(self) -> str:
        return "SYNTHETIC_TEST"

    def get_status(self) -> dict[str, Any]:
        return {
            "provider_id": self._provider_id,
            "provider_name": self._provider_name,
            "is_configured": self.is_configured,
            "is_enabled": self._enabled,
            "is_synthetic": True,
            "provider_type": "SYNTHETIC_TEST",
            "supported_instruments": sorted(list(self._supported_instruments)),
            "supported_timeframes": sorted(list(self._supported_timeframes)),
        }

    def fetch_historical_range(
        self,
        *,
        instrument: str,
        timeframe: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        self.fetch_calls.append({
            "instrument": instrument,
            "timeframe": timeframe,
            "start_date": start_date,
            "end_date": end_date,
        })
        if not self._enabled:
            raise DataProviderNotConfiguredError(f"DATA_PROVIDER_NOT_CONFIGURED: Provider '{self._provider_name}' is disabled")
        if self._error_to_raise is not None:
            raise self._error_to_raise

        inst = instrument.upper().strip()
        tf = timeframe.strip()
        if inst not in self._supported_instruments:
            raise DataValidationError(f"Instrument '{inst}' not supported by provider")
        if tf not in self._supported_timeframes:
            raise DataValidationError(f"Timeframe '{tf}' not supported by provider")

        rows = []
        current = start_date
        step_minutes = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1H": 60, "1d": 375}.get(tf, 1)

        while current <= end_date:
            # Weekday check: 0-4 are Mon-Fri
            if current.weekday() < 5 and current not in self._gap_dates:
                day_start = datetime(current.year, current.month, current.day, 9, 15, tzinfo=IST)
                day_end = datetime(current.year, current.month, current.day, 15, 30, tzinfo=IST)
                cur_dt = day_start
                bar_idx = 0
                while cur_dt < day_end:
                    day_offset = (current - start_date).days
                    o = self._base_price + (day_offset * 10.0) + (bar_idx * 0.5)
                    h = o + 5.0
                    l = o - 5.0
                    c = o + 1.0
                    v = 1000.0 + bar_idx * 10.0
                    if self._malformed:
                        h = l - 10.0  # malformed price: high < low
                    rows.append({
                        "timestamp": cur_dt,
                        "open": o,
                        "high": h,
                        "low": l,
                        "close": c,
                        "volume": v,
                        "instrument": inst,
                        "timeframe": tf,
                    })
                    cur_dt += timedelta(minutes=step_minutes)
                    bar_idx += 1
                    if tf == "1d":
                        break
            current += timedelta(days=1)

        if not rows:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume", "instrument", "timeframe"])
        return pd.DataFrame(rows)


@dataclass
class GapInterval:
    start: date
    end: date
    timeframe: str = "1m"
    missing_sessions: int = 1
    status: str = "MISSING_SESSION_EVIDENCE"


class GapAnalysisResult(list):
    def __init__(self, gaps: list[GapInterval], **metadata):
        super().__init__(gaps)
        self.metadata = metadata
        self.__dict__.update(metadata)

    def __getitem__(self, item):
        if isinstance(item, str):
            return self.metadata[item]
        return super().__getitem__(item)

    def get(self, key, default=None):
        return self.metadata.get(key, default)

    def __getattr__(self, name):
        if name in self.metadata:
            return self.metadata[name]
        raise AttributeError(f"'GapAnalysisResult' object has no attribute '{name}'")


class GapRepairReport(dict):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.__dict__ = self


class SyncJobRecord(dict):
    def __init__(
        self,
        job_id: str,
        job_type: str,
        provider_id: str,
        instrument: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        status: str,
        rows_fetched: int = 0,
        error_message: str | None = None,
        created_at_utc: str | None = None,
        completed_at_utc: str | None = None,
        details: str | None = None,
        already_up_to_date: bool = False,
        dataset: Any | None = None,
        **kwargs,
    ):
        data = {
            "job_id": job_id,
            "job_type": job_type,
            "provider_id": provider_id,
            "instrument": instrument,
            "timeframe": timeframe,
            "start_date": start_date,
            "end_date": end_date,
            "status": status,
            "rows_fetched": rows_fetched,
            "error_message": error_message,
            "created_at_utc": created_at_utc or datetime.now(UTC).isoformat(),
            "completed_at_utc": completed_at_utc,
            "details": details or error_message or ("ALREADY_SYNCED" if already_up_to_date else ""),
            "already_up_to_date": already_up_to_date,
            "dataset": dataset,
        }
        data.update(kwargs)
        super().__init__(data)
        self.__dict__ = self


class ScheduledSyncConfig(dict):
    def __init__(
        self,
        instrument: str = "NIFTY",
        timeframe: str = "1m",
        frequency: str = "DAILY",
        lookback_days: int = 5,
        provider_id: str | None = None,
        is_enabled: bool = True,
        last_run_utc: str | None = None,
        **kwargs,
    ):
        en = kwargs.pop("enabled", is_enabled)
        data = {
            "instrument": instrument,
            "timeframe": timeframe,
            "frequency": frequency,
            "lookback_days": lookback_days,
            "provider_id": provider_id,
            "is_enabled": en,
            "enabled": en,
            "last_run_utc": last_run_utc,
        }
        data.update(kwargs)
        super().__init__(data)
        self.__dict__ = self


@dataclass
class DatasetInventoryItem:
    instrument: str
    timeframe: str
    start_date: str
    end_date: str
    row_count: int
    trading_days: int
    file_sha256: str
    logical_path: str
    gap_status: str
    updated_at_utc: str
    is_complete: bool = True


class HistoricalDataService:
    """Canonical Historical Data Authority for SentinelX.

    Manages local cache, checks availability, provisions missing intervals via
    provider, strictly validates OHLC data, maintains SHA-256 fingerprints,
    and coordinates with F-12 Owner governance.
    """

    def __init__(
        self,
        cache_root: Path,
        *,
        provider: MarketDataProvider | None = None,
        security_store: Any | None = None,
        imports_root: Path | None = None,
    ) -> None:
        self._cache_root = Path(cache_root).resolve()
        self._cache_root.mkdir(parents=True, exist_ok=True)
        self._provider = provider or UnconfiguredMarketDataProvider()
        self._security_store = security_store
        self._imports_root = Path(imports_root).resolve() if imports_root else self._cache_root
        self._imports_root.mkdir(parents=True, exist_ok=True)
        self._meta_file = self._cache_root / "inventory_manifest.json"
        self._providers_file = self._cache_root / "providers_manifest.json"
        self._providers: dict[str, MarketDataProvider] = {}
        if self._provider:
            p_id = getattr(self._provider, "provider_id", self._provider.provider_name)
            self._providers[p_id] = self._provider
        self._load_providers_manifest()

    @property
    def cache_root(self) -> Path:
        return self._cache_root

    @property
    def imports_root(self) -> Path:
        return self._imports_root

    @property
    def provider(self) -> MarketDataProvider:
        return self._provider

    def set_provider(self, provider: MarketDataProvider) -> None:
        """Inject or update the active market data provider."""
        self._provider = provider
        p_id = getattr(provider, "provider_id", provider.provider_name)
        self._providers[p_id] = provider

    def register_provider(
        self,
        provider: MarketDataProvider | None = None,
        *,
        provider_id: str | None = None,
        name: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        supported_instruments: list[str] | None = None,
        supported_timeframes: list[str] | None = None,
        is_enabled: bool = True,
        provider_type: str | None = None,
        is_test: bool = False,
    ) -> MarketDataProvider:
        """Register a market data provider into the service fleet."""
        if provider is None:
            p_id = provider_id or f"prov-{uuid4().hex[:8]}"
            p_name = name or p_id

            # External provider configuration without an implemented transport adapter must fail closed
            is_explicit_test = is_test or provider_type == "SYNTHETIC_TEST" or (
                p_id.lower().startswith("test-") and p_name.upper().startswith("TEST")
            )
            has_external_creds = bool(base_url or api_key)

            if not is_explicit_test or has_external_creds:
                raise DataProviderNotConfiguredError(
                    f"EXTERNAL_PROVIDER_UNSUPPORTED: External provider '{p_name}' has no implemented transport adapter. "
                    "External provider configuration fails closed rather than fabricating synthetic data."
                )

            insts = set(supported_instruments) if supported_instruments else None
            tfs = set(supported_timeframes) if supported_timeframes else None
            provider = TestHistoricalDataProvider(
                provider_id=p_id,
                provider_name=p_name,
                supported_instruments=insts,
                supported_timeframes=tfs,
                enabled=is_enabled,
            )
        p_id = getattr(provider, "provider_id", provider.provider_name)
        self._providers[p_id] = provider
        if isinstance(self._provider, UnconfiguredMarketDataProvider):
            self._provider = provider
        self._save_providers_manifest()
        return provider

    def get_provider(self, provider_id: str) -> MarketDataProvider | None:
        """Fetch provider by provider_id or provider_name."""
        if provider_id in self._providers:
            return self._providers[provider_id]
        for p in self._providers.values():
            if getattr(p, "provider_id", None) == provider_id or p.provider_name == provider_id:
                return p
        return None

    def list_providers(self) -> list[dict[str, Any]]:
        """List all configured providers with sanitized/masked configuration."""
        items = []
        for p_id, p in self._providers.items():
            is_active = (self._provider == p)
            is_synthetic = getattr(p, "is_synthetic", False)
            p_type = getattr(p, "provider_type", "SYNTHETIC_TEST" if is_synthetic else "EXTERNAL")
            items.append({
                "provider_id": getattr(p, "provider_id", p_id),
                "provider_name": p.provider_name,
                "is_configured": p.is_configured,
                "is_enabled": getattr(p, "is_enabled", True),
                "is_active": is_active,
                "is_synthetic": is_synthetic,
                "provider_type": p_type,
                "supported_instruments": sorted(list(getattr(p, "supported_instruments", SUPPORTED_INSTRUMENTS))),
                "supported_timeframes": sorted(list(getattr(p, "supported_timeframes", SUPPORTED_TIMEFRAMES))),
            })
        return items

    def toggle_provider(self, provider_id: str, enabled: bool) -> dict[str, Any]:
        """Enable or disable a configured provider."""
        p = self.get_provider(provider_id)
        if not p:
            raise DataProviderNotConfiguredError(f"Provider '{provider_id}' not found")
        if hasattr(p, "set_enabled"):
            p.set_enabled(enabled)
        self._save_providers_manifest()
        return {
            "provider_id": getattr(p, "provider_id", provider_id),
            "provider_name": p.provider_name,
            "is_enabled": getattr(p, "is_enabled", enabled),
        }

    def _save_providers_manifest(self) -> None:
        records = []
        for p in self._providers.values():
            records.append({
                "provider_id": getattr(p, "provider_id", p.provider_name),
                "provider_name": p.provider_name,
                "is_enabled": getattr(p, "is_enabled", True),
            })
        tmp = self._providers_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(records, indent=2), encoding="utf-8")
        tmp.replace(self._providers_file)

    def _load_providers_manifest(self) -> None:
        if not self._providers_file.exists():
            return
        try:
            records = json.loads(self._providers_file.read_text(encoding="utf-8"))
            for r in records:
                p_id = r.get("provider_id")
                if p_id in self._providers and hasattr(self._providers[p_id], "set_enabled"):
                    self._providers[p_id].set_enabled(r.get("is_enabled", True))
        except Exception as exc:
            logger.warning("Error reading providers manifest: %s", exc)

    # ─────────────────────────────────────────────────────────────
    # Path & Storage Mapping
    # ─────────────────────────────────────────────────────────────

    def _get_parquet_path(self, instrument: str, timeframe: str) -> Path:
        inst = instrument.upper().strip()
        tf = timeframe.strip()
        target_dir = self._cache_root / inst / tf
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / "data.parquet"

    def _read_metadata(self) -> dict[str, Any]:
        if not self._meta_file.exists():
            return {}
        try:
            return json.loads(self._meta_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_metadata(self, meta: dict[str, Any]) -> None:
        tmp = self._meta_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        tmp.replace(self._meta_file)

    # ─────────────────────────────────────────────────────────────
    # Inventory & Range Checking
    # ─────────────────────────────────────────────────────────────

    def check_inventory(self, instrument: str, timeframe: str) -> DatasetInventoryItem | None:
        """Check local authoritative cache for instrument and timeframe."""
        inst = instrument.upper().strip()
        tf = timeframe.strip()
        pq_path = self._get_parquet_path(inst, tf)
        if not pq_path.exists() or pq_path.stat().st_size == 0:
            return None

        meta = self._read_metadata()
        key = f"{inst}:{tf}"
        if key in meta:
            item_dict = meta[key]
            # Verify file digest still matches
            current_digest = self._hash_file(pq_path)
            if item_dict.get("file_sha256") == current_digest:
                return DatasetInventoryItem(**item_dict)

        # Re-index if metadata missing or stale
        try:
            df = pd.read_parquet(pq_path)
            valid_df = self.validate_ohlcv(df, instrument=inst, timeframe=tf)
            item = self._index_dataframe(valid_df, inst, tf, pq_path)
            meta[key] = item.__dict__
            self._write_metadata(meta)
            return item
        except Exception as exc:
            logger.warning("Corrupt or invalid cached data for %s %s: %s", inst, tf, exc)
            return None

    def list_inventory(self) -> list[DatasetInventoryItem]:
        """List all locally available datasets in the authoritative cache."""
        items: list[DatasetInventoryItem] = []
        for inst in SUPPORTED_INSTRUMENTS:
            for tf in SUPPORTED_TIMEFRAMES:
                item = self.check_inventory(inst, tf)
                if item is not None:
                    items.append(item)
        return items

    def available_timeframes(self, instrument: str) -> tuple[str, ...]:
        """Return timeframes available locally for the instrument."""
        inst = instrument.upper().strip()
        available = []
        for tf in sorted(SUPPORTED_TIMEFRAMES, key=lambda t: TIMEFRAME_SECONDS.get(t, 0)):
            if self.check_inventory(inst, tf) is not None:
                available.append(tf)
        return tuple(available)

    def read_cached_dataframe(self, instrument: str, timeframe: str) -> pd.DataFrame | None:
        """Read cached pandas DataFrame directly from parquet."""
        pq = self._get_parquet_path(instrument, timeframe)
        if not pq.exists():
            return None
        return pd.read_parquet(pq)

    def calculate_missing_intervals(
        self,
        instrument: str,
        timeframe: str,
        requested_start: date,
        requested_end: date,
    ) -> list[DateInterval]:
        """Determine exactly which date ranges are missing from the local cache."""
        if requested_start > requested_end:
            raise ValueError(f"requested_start ({requested_start}) > requested_end ({requested_end})")

        inv = self.check_inventory(instrument, timeframe)
        if inv is None:
            return [DateInterval(requested_start, requested_end)]

        cached_start = date.fromisoformat(inv.start_date)
        cached_end = date.fromisoformat(inv.end_date)

        # Case 1: Requested is completely before cached range
        if requested_end < cached_start:
            return [DateInterval(requested_start, requested_end)]

        # Case 2: Requested is completely after cached range
        if requested_start > cached_end:
            return [DateInterval(requested_start, requested_end)]

        missing: list[DateInterval] = []
        # Case 3: Missing head (start before cached_start)
        if requested_start < cached_start:
            missing.append(DateInterval(requested_start, cached_start - timedelta(days=1)))

        # Case 4: Missing tail (end after cached_end)
        if requested_end > cached_end:
            missing.append(DateInterval(cached_end + timedelta(days=1), requested_end))

        return missing

    # ─────────────────────────────────────────────────────────────
    # Data Validation
    # ─────────────────────────────────────────────────────────────

    def validate_ohlcv(
        self,
        df: pd.DataFrame,
        *,
        instrument: str,
        timeframe: str,
    ) -> pd.DataFrame:
        """Strict validation of historical OHLCV data.

        Enforces:
        - Required columns: timestamp, open, high, low, close, volume
        - Numeric validity: non-NaN, positive prices, volume >= 0
        - Price consistency: low <= min(open, close), high >= max(open, close)
        - Timezone normalization: IST-aware timestamps
        - Duplicate timestamps rejected/deduplicated cleanly
        - Monotonic increasing timestamps
        - Timeframe bar interval sanity
        """
        inst = instrument.upper().strip()
        tf = timeframe.strip()

        if df is None or df.empty:
            raise DataValidationError("DataFrame is empty or None")

        # Column normalization
        cols = {c.lower(): c for c in df.columns}
        required = ["timestamp", "open", "high", "low", "close"]
        for req in required:
            if req not in cols:
                raise DataValidationError(f"Missing required column: {req}")

        df = df.rename(columns={
            cols["timestamp"]: "timestamp",
            cols["open"]: "open",
            cols["high"]: "high",
            cols["low"]: "low",
            cols["close"]: "close",
            cols.get("volume", "volume"): "volume",
        }).copy()

        if "volume" not in df.columns:
            df["volume"] = 0.0

        # Timestamp normalization
        if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
            try:
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            except Exception as exc:
                raise DataValidationError(f"Cannot parse timestamp column: {exc}") from exc

        ts = pd.to_datetime(df["timestamp"], utc=True)
        if ts.isna().any():
            raise DataValidationError("Timestamps contain null/NaN values")

        # Convert to IST
        df["timestamp"] = ts.dt.tz_convert(IST)

        # Check instrument identity if present
        if "instrument" in cols:
            inst_series = df[cols["instrument"]].astype(str).str.upper().str.strip()
            if not (inst_series == inst).all():
                raise DataValidationError(
                    f"DATASET_INSTRUMENT_MISMATCH: Data contains rows for instrument other than {inst}"
                )

        # Numeric conversions
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            if df[col].isna().any():
                raise DataValidationError(f"Non-numeric values in column {col}")

        # Price sanity: positive numbers
        for col in ["open", "high", "low", "close"]:
            if (df[col] <= 0).any():
                raise DataValidationError(f"Zero or negative prices detected in column {col}")

        if (df["volume"] < 0).any():
            raise DataValidationError("Negative volume detected")

        # Price consistency: low <= min(open, close) and high >= max(open, close)
        min_oc = np.minimum(df["open"].to_numpy(), df["close"].to_numpy())
        max_oc = np.maximum(df["open"].to_numpy(), df["close"].to_numpy())

        # Allow slight float precision epsilon
        if (df["low"].to_numpy() > min_oc + 1e-6).any():
            raise DataValidationError("Invalid bar: low > min(open, close)")

        if (df["high"].to_numpy() < max_oc - 1e-6).any():
            raise DataValidationError("Invalid bar: high < max(open, close)")

        # Handle duplicates and sort
        dup_count = df.duplicated(subset=["timestamp"]).sum()
        if dup_count > 0:
            logger.info("Dropping %d duplicate timestamp(s) for %s %s", dup_count, inst, tf)
            df = df.drop_duplicates(subset=["timestamp"], keep="first")

        df = df.sort_values(by="timestamp").reset_index(drop=True)

        if not df["timestamp"].is_monotonic_increasing:
            raise DataValidationError("Timestamps are not monotonically increasing after sort")

        # Bar interval check
        interval_secs = TIMEFRAME_SECONDS.get(tf, 60)
        deltas = df["timestamp"].diff().dropna().dt.total_seconds()
        if (deltas < interval_secs - 1e-3).any():
            raise DataValidationError(
                f"DATASET_BAR_INTERVAL_INVALID: Bars found with interval less than timeframe {tf} ({interval_secs}s)"
            )

        df["instrument"] = inst
        df["timeframe"] = tf
        return df[["timestamp", "open", "high", "low", "close", "volume", "instrument", "timeframe"]]

    # ─────────────────────────────────────────────────────────────
    # Data Request & Provisioning Flow
    # ─────────────────────────────────────────────────────────────

    def request_data(
        self,
        instrument: str,
        timeframe: str,
        start_date: date,
        end_date: date,
        auto_provision: bool = True,
        allow_fetch: bool | None = None,
    ) -> tuple[pd.DataFrame, DatasetInventoryItem]:
        """Request historical data for an instrument and date range.

        Checks local cache:
        - If complete: returns validated data immediately.
        - If missing intervals:
          - If provider configured and auto_provision: provisions only the missing
            intervals, merges safely, recalculates hash, and registers dataset.
          - If provider not configured: fails closed with DATA_PROVIDER_NOT_CONFIGURED.
        """
        inst = instrument.upper().strip()
        tf = timeframe.strip()

        if inst not in SUPPORTED_INSTRUMENTS:
            raise DataValidationError(f"Unsupported instrument: {inst}")
        if tf not in SUPPORTED_TIMEFRAMES:
            raise DataValidationError(f"Unsupported timeframe: {tf}")
        if start_date > end_date:
            raise DataValidationError(f"Invalid date range: {start_date} > {end_date}")

        missing = self.calculate_missing_intervals(
            instrument=inst, timeframe=tf, requested_start=start_date, requested_end=end_date
        )

        if missing:
            if not auto_provision or not self._provider.is_configured:
                raise DataProviderNotConfiguredError(
                    f"DATA_PROVIDER_NOT_CONFIGURED: Missing {len(missing)} interval(s) "
                    f"for {inst} {tf} ({start_date} to {end_date}), but no external data provider is configured."
                )

            # Provision missing intervals
            for interval in missing:
                logger.info(
                    "Provisioning missing interval for %s %s: %s to %s via %s",
                    inst, tf, interval.start, interval.end, self._provider.provider_name
                )
                raw_df = self._provider.fetch_historical_range(
                    instrument=inst, timeframe=tf, start_date=interval.start, end_date=interval.end
                )
                self.import_dataframe(
                    raw_df,
                    instrument=inst,
                    timeframe=tf,
                    source_name=self._provider.provider_name,
                )

        # Read back from authoritative cache
        pq_path = self._get_parquet_path(inst, tf)
        if not pq_path.exists():
            raise DataUnavailableError(f"DATA_UNAVAILABLE: No data available for {inst} {tf}")

        df = pd.read_parquet(pq_path)
        valid_df = self.validate_ohlcv(df, instrument=inst, timeframe=tf)

        # Filter to requested range
        dates = valid_df["timestamp"].dt.date
        sliced_df = valid_df.loc[(dates >= start_date) & (dates <= end_date)].copy()
        if sliced_df.empty:
            raise DataUnavailableError(f"DATA_UNAVAILABLE: No bars found between {start_date} and {end_date}")

        inv = self.check_inventory(inst, tf)
        if inv is None:
            inv = self._index_dataframe(valid_df, inst, tf, pq_path)

        return sliced_df, inv

    def import_dataframe(
        self,
        new_df: pd.DataFrame,
        *,
        instrument: str,
        timeframe: str,
        source_name: str = "LOCAL_IMPORT",
        require_owner_approval: bool = True,
    ) -> DatasetInventoryItem:
        """Validate, merge, cache, and register a DataFrame into the canonical inventory."""
        inst = instrument.upper().strip()
        tf = timeframe.strip()
        validated_new = self.validate_ohlcv(new_df, instrument=inst, timeframe=tf)

        pq_path = self._get_parquet_path(inst, tf)
        if pq_path.exists() and pq_path.stat().st_size > 0:
            existing_df = pd.read_parquet(pq_path)
            validated_existing = self.validate_ohlcv(existing_df, instrument=inst, timeframe=tf)
            # Merge without duplicates
            combined = pd.concat([validated_existing, validated_new], ignore_index=True)
            combined = combined.drop_duplicates(subset=["timestamp"], keep="last")
            combined = combined.sort_values(by="timestamp").reset_index(drop=True)
            final_df = self.validate_ohlcv(combined, instrument=inst, timeframe=tf)
        else:
            final_df = validated_new

        # Write Parquet atomically
        tmp_pq = pq_path.with_suffix(".tmp.parquet")
        final_df.to_parquet(tmp_pq, engine="pyarrow", index=False)
        tmp_pq.replace(pq_path)

        # Compute fingerprint and index
        item = self._index_dataframe(final_df, inst, tf, pq_path, source_name=source_name)

        # Update manifest
        meta = self._read_metadata()
        meta[f"{inst}:{tf}"] = item.__dict__
        self._write_metadata(meta)

        # Coordinate with F-12 governance store if present
        if self._security_store is not None:
            self._register_with_governance(item, source_name=source_name, pending_approval=require_owner_approval)

        return item

    def _index_dataframe(
        self,
        df: pd.DataFrame,
        instrument: str,
        timeframe: str,
        pq_path: Path,
        source_name: str = "CANONICAL_CACHE",
    ) -> DatasetInventoryItem:
        file_hash = self._hash_file(pq_path)
        dates = df["timestamp"].dt.date
        start_d = dates.min().isoformat()
        end_d = dates.max().isoformat()
        unique_days = int(dates.nunique())
        row_count = int(len(df))
        logical = str(pq_path.relative_to(self._cache_root)).replace("\\", "/")

        return DatasetInventoryItem(
            instrument=instrument,
            timeframe=timeframe,
            start_date=start_d,
            end_date=end_d,
            row_count=row_count,
            trading_days=unique_days,
            file_sha256=file_hash,
            logical_path=logical,
            gap_status="GAPS_CLEAR",
            updated_at_utc=datetime.now(UTC).isoformat(),
            is_complete=True,
        )

    def _register_with_governance(
        self,
        item: DatasetInventoryItem,
        source_name: str,
        pending_approval: bool = True,
    ) -> None:
        """Register or update dataset in SQLiteSecurityStore owner_datasets table."""
        if not hasattr(self._security_store, "_transaction"):
            return

        dataset_id = f"{item.instrument.lower()}-{item.timeframe.lower()}-primary"
        now_str = datetime.now(UTC).isoformat()
        approval_status = "PENDING" if pending_approval else "APPROVED"

        prov_obj = self.get_provider(source_name) or self._provider
        if getattr(prov_obj, "is_synthetic", False) or isinstance(prov_obj, TestHistoricalDataProvider):
            provenance = "SYNTHETIC_TEST"
        elif getattr(prov_obj, "provider_name", "") == "LOCAL_IMPORT" or isinstance(prov_obj, LocalImportDataProvider):
            provenance = "LOCAL_IMPORT"
        else:
            provenance = "EXTERNAL_PRODUCTION"

        with self._security_store._transaction() as cur:
            # Check existing approval status
            existing = cur.execute(
                "SELECT owner_approval, history_json FROM owner_datasets WHERE dataset_id = ?",
                (dataset_id,)
            ).fetchone()

            if existing:
                # Retain existing owner approval if already approved
                approval = existing["owner_approval"] if existing["owner_approval"] == "APPROVED" else approval_status
                cur.execute(
                    """
                    UPDATE owner_datasets SET
                        start_date = ?, end_date = ?, trading_days = ?, row_count = ?,
                        logical_path = ?, hash_sha256 = ?, provenance = ?, acquisition_state = 'ACQUIRED',
                        system_readiness = 'SYSTEM_READY', updated_at_utc = ?
                    WHERE dataset_id = ?
                    """,
                    (
                        item.start_date, item.end_date, item.trading_days, item.row_count,
                        item.logical_path, item.file_sha256, provenance, now_str, dataset_id
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO owner_datasets (
                        dataset_id, id, source, market, instrument, segment, timeframe,
                        source_timezone, start_date, end_date, trading_days, row_count,
                        format, logical_path, gap_status, gap_details, provenance,
                        hash_sha256, acquisition_state, system_readiness, verification_details,
                        owner_approval, owner_hold_reason, history_json, updated_at_utc
                    ) VALUES (
                        ?, ?, ?, 'NSE', ?, 'EQUITY', ?,
                        'Asia/Kolkata', ?, ?, ?, ?,
                        'PARQUET_V2', ?, 'GAPS_CLEAR', '', ?,
                        ?, 'ACQUIRED', 'SYSTEM_READY', 'Validated by HistoricalDataService',
                        ?, NULL, '[]', ?
                    )
                    """,
                    (
                        dataset_id, dataset_id, source_name, item.instrument, item.timeframe,
                        item.start_date, item.end_date, item.trading_days, item.row_count,
                        item.logical_path, provenance, item.file_sha256, approval_status, now_str
                    ),
                )

    # ─────────────────────────────────────────────────────────────
    # Feed Compatibility Surface (HistoricalDataFeed bridge)
    # ─────────────────────────────────────────────────────────────

    def fetch(self, instrument: str, timeframe: str) -> pd.DataFrame:
        """Fetch through the DataFeed compatible surface."""
        inst = instrument.upper().strip()
        tf = timeframe.strip()
        pq_path = self._get_parquet_path(inst, tf)
        if not pq_path.exists():
            raise FileNotFoundError(f"Historical Parquet file not found for instrument={inst!r}, timeframe={tf!r}")
        df = pd.read_parquet(pq_path)
        return self.validate_ohlcv(df, instrument=inst, timeframe=tf)

    def fetch_dataset(self, dataset: dict[str, Any]) -> tuple[pd.DataFrame, str]:
        """Fetch exact approved dataset bytes, compatible with ApprovedDatasetFiles."""
        logical = Path(dataset["logicalPath"])
        if logical.is_absolute():
            raise DataUnavailableError("DATASET_PATH_OUTSIDE_ROOT")
        # Check cache root then imports root
        path = (self._cache_root / logical).resolve()
        cache_resolved = self._cache_root.resolve()
        if not path.is_relative_to(cache_resolved):
            raise DataUnavailableError("DATASET_PATH_OUTSIDE_ROOT")
        if not path.exists():
            path = (self._imports_root / logical).resolve()
            imports_resolved = self._imports_root.resolve()
            if not path.is_relative_to(imports_resolved):
                raise DataUnavailableError("DATASET_PATH_OUTSIDE_ROOT")
        if not path.exists():
            raise DataUnavailableError("DATASET_FILE_MISSING")

        try:
            payload = path.read_bytes()
        except OSError:
            raise DataUnavailableError("DATASET_FILE_MISSING") from None
        digest = hashlib.sha256(payload).hexdigest()
        expected = dataset["hashSha256"].removeprefix("sha256:")
        if digest != expected:
            raise DataUnavailableError("DATASET_HASH_MISMATCH")

        try:
            frame = pd.read_parquet(BytesIO(payload))
        except Exception:
            raise DataUnavailableError("DATASET_FORMAT_INVALID") from None
        return frame, digest

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    # ─────────────────────────────────────────────────────────────
    # Calendar & Gap Authority Integration
    # ─────────────────────────────────────────────────────────────

    def _get_calendar_authority(self) -> MarketCalendarAuthority:
        auth = MarketCalendarAuthority.try_load_offline(DEFAULT_NSE_CALENDAR_ID)
        if auth is not None:
            return auth
        # Fallback authoritative dataset for standard NSE hours and holidays
        closed_sessions = [
            ClosedSession(date(2026, 1, 26), "HOLIDAY", "Republic Day"),
            ClosedSession(date(2026, 3, 25), "HOLIDAY", "Holi"),
            ClosedSession(date(2026, 4, 14), "HOLIDAY", "Ambedkar Jayanti"),
            ClosedSession(date(2026, 10, 2), "HOLIDAY", "Gandhi Jayanti"),
            ClosedSession(date(2026, 12, 25), "HOLIDAY", "Christmas"),
        ]
        # Filter weekend days to enforce MarketCalendarDataset invariant
        filtered = tuple(cs for cs in closed_sessions if cs.session_date.weekday() < 5)
        ds = MarketCalendarDataset(
            calendar_id="nse-equity",
            exchange="NSE",
            timezone_name="Asia/Kolkata",
            coverage_start=date(2020, 1, 1),
            coverage_end=date(2035, 12, 31),
            dataset_version="2026.01-r1",
            closed_sessions=filtered,
            provenance={"source_description": "SentinelX Authoritative NSE Calendar"},
        )
        return MarketCalendarAuthority(ds)

    def detect_gaps(self, instrument: str, timeframe: str) -> GapAnalysisResult:
        """Detect missing session candidates in cached dataset using calendar authority."""
        inst = instrument.upper().strip()
        tf = timeframe.strip()
        df = self.read_cached_dataframe(inst, tf)
        if df is None or df.empty:
            return GapAnalysisResult(
                [],
                instrument=inst,
                timeframe=tf,
                status="DATA_UNAVAILABLE",
                missing_candidate_count=0,
                known_closed_count=0,
                review_required=False,
                samples=[],
                observed_start=None,
                observed_end=None,
            )

        authority = self._get_calendar_authority()
        report = analyze_target_gaps(df["timestamp"], authority=authority)
        status_str = "GAPS_CLEAR" if report.status == "clean" else "GAPS_DETECTED"

        gap_intervals: list[GapInterval] = []
        for s in report.samples:
            parts = s.split("|")
            d_str = parts[0]
            val = parts[1] if len(parts) > 1 else ""
            if val in ("missing_session_evidence", "missing_session_candidate") or not val:
                try:
                    d = date.fromisoformat(d_str)
                    gap_intervals.append(GapInterval(start=d, end=d, timeframe=tf))
                except Exception:
                    pass

        # Sync gapStatus with security_store if available
        ds_id = f"{inst.lower()}-{tf.lower()}-primary"
        if self._security_store and hasattr(self._security_store, "_transaction"):
            try:
                with self._security_store._transaction() as cur:
                    cur.execute(
                        "UPDATE owner_datasets SET gap_status = ?, updated_at_utc = ? WHERE dataset_id = ?",
                        (status_str, datetime.now(UTC).isoformat(), ds_id),
                    )
            except Exception:
                pass

        return GapAnalysisResult(
            gap_intervals,
            instrument=inst,
            timeframe=tf,
            status=status_str,
            raw_status=report.status,
            missing_candidate_count=len(gap_intervals) if gap_intervals else report.missing_candidate_count,
            known_closed_count=report.known_closed_count,
            review_required=report.review_required,
            samples=list(report.samples),
            observed_start=report.observed_start.isoformat() if report.observed_start else None,
            observed_end=report.observed_end.isoformat() if report.observed_end else None,
        )

    def repair_gaps(
        self,
        instrument: str,
        timeframe: str,
        dataset_id: str | None = None,
        provider_id: str | None = None,
        provider_name: str | None = None,
    ) -> GapRepairReport:
        """Fetch and merge missing session candidates identified by calendar authority."""
        inst = instrument.upper().strip()
        tf = timeframe.strip()
        resolved_prov = provider_id or provider_name
        gap_report = self.detect_gaps(inst, tf)
        if gap_report["status"] == "DATA_UNAVAILABLE":
            raise DataUnavailableError(f"DATA_UNAVAILABLE: No cached data available to repair for {inst} {tf}")

        missing_count = gap_report["missing_candidate_count"]
        ds_id = dataset_id or f"{inst.lower()}-{tf.lower()}-primary"

        if missing_count == 0:
            if self._security_store and hasattr(self._security_store, "_transaction"):
                with self._security_store._transaction() as cur:
                    cur.execute(
                        "UPDATE owner_datasets SET gap_status = 'GAPS_CLEAR', updated_at_utc = ? WHERE dataset_id = ?",
                        (datetime.now(UTC).isoformat(), ds_id)
                    )
            return GapRepairReport(
                instrument=inst,
                timeframe=tf,
                status="ALREADY_CLEAN",
                success=True,
                repaired_gaps=0,
                repaired_sessions=0,
                rows_fetched=0,
                message="No gap candidates detected by MarketCalendarAuthority.",
            )

        candidate_dates = [g.start for g in gap_report]
        rows_repaired = 0
        if candidate_dates:
            start_d = min(candidate_dates)
            end_d = max(candidate_dates)
            sync_res = self.sync_dataset(inst, tf, start_d, end_d, provider_id=resolved_prov, job_type="GAP_REPAIR")
            rows_repaired = sync_res.get("rows_fetched", 0)

        post_report = self.detect_gaps(inst, tf)
        final_gap_status = "GAPS_CLEAR" if len(post_report) == 0 else "GAPS_DETECTED"

        if self._security_store and hasattr(self._security_store, "_transaction"):
            with self._security_store._transaction() as cur:
                cur.execute(
                    "UPDATE owner_datasets SET gap_status = ?, updated_at_utc = ? WHERE dataset_id = ?",
                    (final_gap_status, datetime.now(UTC).isoformat(), ds_id)
                )

        return GapRepairReport(
            instrument=inst,
            timeframe=tf,
            status="REPAIRED" if final_gap_status == "GAPS_CLEAR" else "PARTIALLY_REPAIRED",
            gap_status=final_gap_status,
            success=final_gap_status == "GAPS_CLEAR",
            repaired_gaps=len(candidate_dates),
            repaired_sessions=len(candidate_dates),
            rows_fetched=rows_repaired,
            message=f"Gap repair processed {len(candidate_dates)} session candidate(s) for {inst} {tf}.",
        )

    # ─────────────────────────────────────────────────────────────
    # Manual & Incremental Sync Engine
    # ─────────────────────────────────────────────────────────────

    def sync_dataset(
        self,
        instrument: str,
        timeframe: str,
        start_date: date,
        end_date: date,
        *,
        provider_id: str | None = None,
        provider_name: str | None = None,
        force_refresh: bool = False,
        job_type: str = "MANUAL",
        actor: str = "OWNER",
    ) -> SyncJobRecord:
        """Perform manual, incremental, or scheduled synchronization of an instrument/timeframe range."""
        inst = instrument.upper().strip()
        tf = timeframe.strip()
        if inst not in SUPPORTED_INSTRUMENTS:
            raise DataValidationError(f"Unsupported instrument: {inst}")
        if tf not in SUPPORTED_TIMEFRAMES:
            raise DataValidationError(f"Unsupported timeframe: {tf}")
        if start_date > end_date:
            raise DataValidationError(f"Invalid date range: start_date ({start_date}) > end_date ({end_date})")

        resolved_prov = provider_id or provider_name
        provider = (self.get_provider(resolved_prov) if resolved_prov else None) or self._provider
        p_name = provider.provider_name if provider else "UNCONFIGURED"
        p_id = getattr(provider, "provider_id", p_name)

        job_id = f"job-{uuid4().hex[:12]}"
        job = SyncJobRecord(
            job_id=job_id,
            job_type=job_type,
            provider_id=p_id,
            instrument=inst,
            timeframe=tf,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            status="RUNNING",
        )
        self._record_job(job)

        if not provider or not provider.is_configured or not getattr(provider, "is_enabled", True):
            err_msg = f"DATA_PROVIDER_NOT_CONFIGURED: Provider '{p_name}' is not configured or disabled"
            job.status = "FAILED"
            job.error_message = err_msg
            job.details = err_msg
            job.completed_at_utc = datetime.now(UTC).isoformat()
            self._record_job(job)
            raise DataProviderNotConfiguredError(err_msg)

        if force_refresh or job_type == "GAP_REPAIR":
            missing_intervals = [DateInterval(start_date, end_date)]
        else:
            missing_intervals = self.calculate_missing_intervals(
                instrument=inst, timeframe=tf, requested_start=start_date, requested_end=end_date
            )

        if not missing_intervals:
            # Idempotency check: Already complete locally
            inv = self.check_inventory(inst, tf)
            job.status = "COMPLETED"
            job.rows_fetched = 0
            job.details = "ALREADY_SYNCED"
            job.already_up_to_date = True
            job.dataset = inv.__dict__ if inv else None
            job.completed_at_utc = datetime.now(UTC).isoformat()
            self._record_job(job)
            return job

        fetched_frames = []
        total_rows = 0
        try:
            for interval in missing_intervals:
                df = provider.fetch_historical_range(
                    instrument=inst,
                    timeframe=tf,
                    start_date=interval.start,
                    end_date=interval.end,
                )
                if df is not None and not df.empty:
                    valid_chunk = self.validate_ohlcv(df, instrument=inst, timeframe=tf)
                    fetched_frames.append(valid_chunk)
                    total_rows += len(valid_chunk)

            if fetched_frames:
                combined_new = pd.concat(fetched_frames, ignore_index=True)
                item = self.import_dataframe(
                    combined_new,
                    instrument=inst,
                    timeframe=tf,
                    source_name=p_name,
                    require_owner_approval=True,
                )
            else:
                inv = self.check_inventory(inst, tf)
                item = inv

            job.status = "COMPLETED"
            job.rows_fetched = total_rows
            job.details = f"Successfully synced {total_rows} rows"
            job.already_up_to_date = False
            job.dataset = item.__dict__ if item else None
            job.completed_at_utc = datetime.now(UTC).isoformat()
            self._record_job(job)
            return job
        except Exception as exc:
            job.status = "FAILED"
            job.error_message = str(exc)
            job.details = str(exc)
            job.completed_at_utc = datetime.now(UTC).isoformat()
            self._record_job(job)
            raise

    # ─────────────────────────────────────────────────────────────
    # Automated / Scheduled Sync Engine
    # ─────────────────────────────────────────────────────────────

    def get_schedule(
        self,
        instrument: str | None = None,
        timeframe: str | None = None,
    ) -> ScheduledSyncConfig:
        """Fetch current automated synchronization schedule configuration."""
        sched_file = self._cache_root / "schedule_manifest.json"
        manifest = {}
        if sched_file.exists():
            try:
                manifest = json.loads(sched_file.read_text(encoding="utf-8"))
            except Exception:
                manifest = {}

        inst = (instrument or "NIFTY").upper().strip()
        tf = (timeframe or "1m").strip()
        key = f"{inst}:{tf}"
        if key in manifest:
            return ScheduledSyncConfig(**manifest[key])
        if "default" in manifest:
            return ScheduledSyncConfig(instrument=inst, timeframe=tf, **manifest["default"])

        p_name = getattr(self._provider, "provider_id", getattr(self._provider, "provider_name", "TEST_FEED"))
        return ScheduledSyncConfig(
            instrument=inst,
            timeframe=tf,
            frequency="DAILY",
            lookback_days=5,
            provider_id=p_name,
            is_enabled=False,
        )

    def update_schedule(
        self,
        config: dict[str, Any] | None = None,
        *,
        instrument: str | None = None,
        timeframe: str | None = None,
        frequency: str = "DAILY",
        lookback_days: int = 5,
        provider_id: str | None = None,
        is_enabled: bool = True,
        **kwargs,
    ) -> ScheduledSyncConfig:
        """Update and persist automated synchronization schedule."""
        sched_file = self._cache_root / "schedule_manifest.json"
        manifest = {}
        if sched_file.exists():
            try:
                manifest = json.loads(sched_file.read_text(encoding="utf-8"))
            except Exception:
                manifest = {}

        if config and isinstance(config, dict):
            instrument = config.get("instrument", instrument)
            timeframe = config.get("timeframe", timeframe)
            frequency = config.get("frequency", frequency)
            lookback_days = config.get("lookback_days", lookback_days)
            provider_id = config.get("provider_id", provider_id)
            is_enabled = config.get("is_enabled", config.get("enabled", is_enabled))

        inst = (instrument or "NIFTY").upper().strip()
        tf = (timeframe or "1m").strip()
        key = f"{inst}:{tf}"
        p_id = provider_id or getattr(self._provider, "provider_id", getattr(self._provider, "provider_name", "TEST_FEED"))

        cfg_obj = ScheduledSyncConfig(
            instrument=inst,
            timeframe=tf,
            frequency=frequency,
            lookback_days=lookback_days,
            provider_id=p_id,
            is_enabled=is_enabled,
        )

        manifest[key] = dict(cfg_obj)
        manifest["default"] = dict(cfg_obj)

        tmp = sched_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        tmp.replace(sched_file)
        return cfg_obj

    def run_scheduled_sync(
        self,
        instrument: str | None = None,
        timeframe: str | None = None,
        force: bool = False,
    ) -> SyncJobRecord | list[SyncJobRecord]:
        """Run scheduled synchronization incrementally for configured instruments."""
        today = datetime.now(IST).date()
        if instrument and timeframe:
            inst = instrument.upper().strip()
            tf = timeframe.strip()
            cfg = self.get_schedule(inst, tf)
            if not cfg.is_enabled and not force:
                return SyncJobRecord(
                    job_id=f"job-skipped-{uuid4().hex[:8]}",
                    job_type="SCHEDULED",
                    provider_id=cfg.provider_id or "NONE",
                    instrument=inst,
                    timeframe=tf,
                    start_date=today.isoformat(),
                    end_date=today.isoformat(),
                    status="SKIPPED",
                    details="Schedule disabled",
                )
            lookback = cfg.lookback_days or 5
            inv = self.check_inventory(inst, tf)
            if inv:
                cached_end = date.fromisoformat(inv.end_date)
                start_d = cached_end + timedelta(days=1)
            else:
                start_d = today - timedelta(days=lookback)
            if start_d > today:
                start_d = today - timedelta(days=lookback)

            job = self.sync_dataset(
                instrument=inst,
                timeframe=tf,
                start_date=start_d,
                end_date=today,
                provider_id=cfg.provider_id,
                job_type="SCHEDULED",
            )
            return job

        # Iterate all manifest entries
        sched_file = self._cache_root / "schedule_manifest.json"
        manifest = {}
        if sched_file.exists():
            try:
                manifest = json.loads(sched_file.read_text(encoding="utf-8"))
            except Exception:
                manifest = {}

        results = []
        for k, v in manifest.items():
            if k == "default" or not isinstance(v, dict):
                continue
            inst = v.get("instrument")
            tf = v.get("timeframe")
            if not inst or not tf:
                continue
            cfg = ScheduledSyncConfig(**v)
            if not cfg.is_enabled and not force:
                continue
            lookback = cfg.lookback_days or 5
            inv = self.check_inventory(inst, tf)
            if inv:
                cached_end = date.fromisoformat(inv.end_date)
                start_d = cached_end + timedelta(days=1)
            else:
                start_d = today - timedelta(days=lookback)
            if start_d > today:
                start_d = today - timedelta(days=lookback)

            try:
                j = self.sync_dataset(
                    instrument=inst,
                    timeframe=tf,
                    start_date=start_d,
                    end_date=today,
                    provider_id=cfg.provider_id,
                    job_type="SCHEDULED",
                )
                results.append(j)
            except Exception as exc:
                results.append(SyncJobRecord(
                    job_id=f"job-failed-{uuid4().hex[:8]}",
                    job_type="SCHEDULED",
                    provider_id=cfg.provider_id or "NONE",
                    instrument=inst,
                    timeframe=tf,
                    start_date=start_d.isoformat(),
                    end_date=today.isoformat(),
                    status="FAILED",
                    error_message=str(exc),
                    details=str(exc),
                ))
        return results

    # ─────────────────────────────────────────────────────────────
    # Job History & Observability
    # ─────────────────────────────────────────────────────────────

    def _record_job(self, record: dict[str, Any] | SyncJobRecord) -> None:
        jobs_file = self._cache_root / "jobs_manifest.json"
        jobs = []
        if jobs_file.exists():
            try:
                jobs = json.loads(jobs_file.read_text(encoding="utf-8"))
            except Exception:
                jobs = []
        data = dict(record)
        updated = False
        for i, j in enumerate(jobs):
            if j.get("job_id") == data.get("job_id"):
                jobs[i] = data
                updated = True
                break
        if not updated:
            jobs.insert(0, data)
        jobs = jobs[:100]
        tmp = jobs_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(jobs, indent=2), encoding="utf-8")
        tmp.replace(jobs_file)

    def list_jobs(self, instrument: str | None = None, limit: int = 50) -> list[SyncJobRecord]:
        """List historical sync jobs in reverse chronological order."""
        jobs_file = self._cache_root / "jobs_manifest.json"
        if jobs_file.exists():
            try:
                raw_jobs = json.loads(jobs_file.read_text(encoding="utf-8"))
                records = [SyncJobRecord(**j) for j in raw_jobs]
                if instrument:
                    records = [r for r in records if r.instrument == instrument.upper().strip()]
                return records[:limit]
            except Exception:
                pass
        return []

    def get_job(self, job_id: str) -> SyncJobRecord | None:
        """Fetch details of a single sync job."""
        for j in self.list_jobs(limit=100):
            if j.job_id == job_id or j.get("job_id") == job_id:
                return j
        return None

    # ─────────────────────────────────────────────────────────────
    # Dataset Lifecycle: Retirement & Replacement
    # ─────────────────────────────────────────────────────────────

    def retire_dataset(self, dataset_id: str, reason: str, actor: str = "OWNER") -> dict[str, Any]:
        """Owner retires a central dataset, placing it on HOLD/RETIRED and blocking backtesting."""
        if not self._security_store or not hasattr(self._security_store, "_transaction"):
            raise HistoricalDataError("Security store unavailable")

        with self._security_store._transaction() as cur:
            row = cur.execute("SELECT * FROM owner_datasets WHERE dataset_id = ?", (dataset_id,)).fetchone()
            if not row:
                raise HistoricalDataError(f"Dataset '{dataset_id}' not found")
            history = json.loads(row["history_json"])
            now_iso = datetime.now(UTC).isoformat()
            history.insert(0, {
                "time": now_iso,
                "action": "OWNER_DATASET_RETIRED",
                "actor": actor,
                "note": f"Retired by {actor}: {reason}",
                "tone": "warn",
            })
            cur.execute(
                """
                UPDATE owner_datasets SET
                    owner_approval = 'HOLD',
                    system_readiness = 'BLOCKED',
                    owner_hold_reason = ?,
                    history_json = ?,
                    updated_at_utc = ?
                WHERE dataset_id = ?
                """,
                (reason, json.dumps(history), now_iso, dataset_id)
            )
        return {
            "dataset_id": dataset_id,
            "status": "RETIRED",
            "owner_approval": "HOLD",
            "system_readiness": "BLOCKED",
            "reason": reason,
        }

    def replace_dataset(
        self,
        dataset_id: str,
        new_df: pd.DataFrame | None = None,
        *,
        replacement_dataset_id: str | None = None,
        reason: str,
        actor: str = "OWNER",
    ) -> dict[str, Any]:
        """Owner replaces a central dataset's underlying data and resets approval to PENDING."""
        if not self._security_store or not hasattr(self._security_store, "_transaction"):
            raise HistoricalDataError("Security store unavailable")

        with self._security_store._transaction() as cur:
            row = cur.execute("SELECT * FROM owner_datasets WHERE dataset_id = ?", (dataset_id,)).fetchone()
            if not row:
                raise HistoricalDataError(f"Dataset '{dataset_id}' not found")
            inst = row["instrument"]
            tf = row["timeframe"]

        if new_df is None:
            if replacement_dataset_id:
                with self._security_store._transaction() as cur:
                    rep_row = cur.execute("SELECT * FROM owner_datasets WHERE dataset_id = ?", (replacement_dataset_id,)).fetchone()
                    if not rep_row:
                        raise HistoricalDataError(f"Replacement dataset '{replacement_dataset_id}' not found")
                    rep_inst = rep_row["instrument"]
                    rep_tf = rep_row["timeframe"]
                rep_pq = self._get_parquet_path(rep_inst, rep_tf)
                if not rep_pq.exists():
                    raise HistoricalDataError(f"Replacement dataset file not found: {rep_pq}")
                new_df = pd.read_parquet(rep_pq)
            else:
                raise HistoricalDataError("Either new_df or replacement_dataset_id must be provided")

        validated = self.validate_ohlcv(new_df, instrument=inst, timeframe=tf)
        pq_path = self._get_parquet_path(inst, tf)
        tmp_pq = pq_path.with_suffix(".tmp.parquet")
        validated.to_parquet(tmp_pq, engine="pyarrow", index=False)
        tmp_pq.replace(pq_path)

        item = self._index_dataframe(validated, inst, tf, pq_path, source_name=f"OWNER_REPLACE_{actor}")
        meta = self._read_metadata()
        meta[f"{inst}:{tf}"] = item.__dict__
        self._write_metadata(meta)

        # Authoritative calendar-aware gap analysis before readiness determination
        gap_res = self.detect_gaps(inst, tf)
        is_clean = (gap_res.status == "GAPS_CLEAR" and gap_res.missing_candidate_count == 0)
        if is_clean:
            system_readiness = "SYSTEM_READY"
            system_blocker = None
            gap_status = "GAPS_CLEAR"
            verification_details = "Validated by HistoricalDataService · Calendar & Gaps Verified Clean"
        else:
            system_readiness = "BLOCKED"
            system_blocker = f"Calendar-aware gap check failed: {gap_res.missing_candidate_count} missing session candidate(s) detected"
            gap_status = "GAPS_DETECTED"
            verification_details = f"Calendar verification failed with {gap_res.missing_candidate_count} gap(s)"

        with self._security_store._transaction() as cur:
            row = cur.execute("SELECT history_json FROM owner_datasets WHERE dataset_id = ?", (dataset_id,)).fetchone()
            history = json.loads(row["history_json"]) if row else []
            now_iso = datetime.now(UTC).isoformat()
            history.insert(0, {
                "time": now_iso,
                "action": "OWNER_DATASET_REPLACED",
                "actor": actor,
                "note": f"Dataset replaced by {actor}: {reason}. Readiness: {system_readiness} ({gap_status})",
                "tone": "ok" if is_clean else "warn",
            })
            cur.execute(
                """
                UPDATE owner_datasets SET
                    start_date = ?, end_date = ?, trading_days = ?, row_count = ?,
                    logical_path = ?, hash_sha256 = ?, owner_approval = 'PENDING',
                    system_readiness = ?, system_blocker_reason = ?, gap_status = ?,
                    verification_details = ?, owner_hold_reason = NULL,
                    history_json = ?, updated_at_utc = ?
                WHERE dataset_id = ?
                """,
                (
                    item.start_date, item.end_date, item.trading_days, item.row_count,
                    item.logical_path, item.file_sha256, system_readiness, system_blocker,
                    gap_status, verification_details, json.dumps(history), now_iso, dataset_id
                )
            )
        return {
            "dataset_id": dataset_id,
            "status": "REPLACED",
            "owner_approval": "PENDING",
            "system_readiness": system_readiness,
            "system_blocker_reason": system_blocker,
            "gap_status": gap_status,
            "row_count": item.row_count,
            "file_sha256": item.file_sha256,
        }

