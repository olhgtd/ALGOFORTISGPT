"""Shared Phase 1 timestamp normalization and OHLCV validation helpers."""

import pandas as pd


def normalize_timestamps(data: pd.DataFrame, timezone: str = "Asia/Kolkata") -> pd.DataFrame:
    """Normalize timestamps to a timezone-aware series in the supplied source timezone."""
    timestamps = pd.to_datetime(data["timestamp"])
    if timestamps.dt.tz is None:
        data["timestamp"] = timestamps.dt.tz_localize(timezone)
    else:
        data["timestamp"] = timestamps.dt.tz_convert(timezone)
    return data


def invalid_ohlcv_mask(data: pd.DataFrame) -> pd.Series:
    """Return True for rows that fail the Phase 1 OHLCV sanity rules."""
    return (
        (data["high"] < data["low"])
        | (data["high"] < data["open"])
        | (data["high"] < data["close"])
        | (data["open"] <= 0)
        | (data["high"] <= 0)
        | (data["low"] <= 0)
        | (data["close"] <= 0)
        | (data["volume"] < 0)
    )
