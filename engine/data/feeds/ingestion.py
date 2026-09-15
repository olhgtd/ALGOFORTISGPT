import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd

from engine.data.feeds.data_cleaning import invalid_ohlcv_mask, normalize_timestamps
from engine.data.feeds.path_safety import assert_within_root, path_within_root, require_safe_component


logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def clean_ohlcv(
    data: pd.DataFrame,
    duplicate_columns: list[str],
    timezone: str,
    instrument: str,
    timeframe: str,
) -> tuple[pd.DataFrame, int, int]:
    """Reuse Phase 1 timestamp, deduplication, and validation behavior for one contract."""
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in data.columns]
    if missing_columns:
        raise ValueError(f"Raw OHLCV data is missing required columns: {missing_columns}")

    cleaned_data = data.copy()
    normalize_timestamps(cleaned_data, timezone)

    duplicate_rows = cleaned_data.duplicated(subset=duplicate_columns)
    duplicate_count = duplicate_rows.sum()
    if duplicate_count:
        cleaned_data = cleaned_data.loc[~duplicate_rows]
        logger.info(
            "Removed %d duplicate row(s) for instrument=%r, timeframe=%r.",
            duplicate_count,
            instrument,
            timeframe,
        )

    invalid_rows = invalid_ohlcv_mask(cleaned_data)
    invalid_count = invalid_rows.sum()
    if invalid_count:
        cleaned_data = cleaned_data.loc[~invalid_rows]
        logger.info(
            "Rejected %d invalid OHLCV row(s) for instrument=%r, timeframe=%r.",
            invalid_count,
            instrument,
            timeframe,
        )

    return cleaned_data[REQUIRED_COLUMNS], int(duplicate_count), int(invalid_count)


def write_ohlcv_parquet(
    data: pd.DataFrame,
    output_path: Path,
    *,
    authorized_root: Path | None = None,
) -> Path:
    """Atomically write cleaned OHLCV data to a caller-resolved Parquet path."""
    if authorized_root is not None:
        assert_within_root(output_path, authorized_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if authorized_root is not None:
        assert_within_root(output_path, authorized_root)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            dir=output_path.parent,
            suffix=".parquet",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

        data[REQUIRED_COLUMNS].to_parquet(temporary_path, index=False)
        if authorized_root is not None:
            assert_within_root(output_path, authorized_root)
        os.replace(temporary_path, output_path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
    return output_path


def ingest_ohlcv(data: pd.DataFrame, instrument: str, timeframe: str) -> Path:
    """Clean raw OHLCV data and write it to the original Phase 1 Parquet store."""
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in data.columns]
    if missing_columns:
        raise ValueError(f"Raw OHLCV data is missing required columns: {missing_columns}")

    data_for_deduplication = data[REQUIRED_COLUMNS].copy()
    data_for_deduplication["instrument"] = instrument
    cleaned_data, _, _ = clean_ohlcv(
        data_for_deduplication,
        duplicate_columns=["timestamp", "instrument"],
        timezone="Asia/Kolkata",
        instrument=instrument,
        timeframe=timeframe,
    )

    instrument = require_safe_component(instrument, "instrument")
    timeframe = require_safe_component(timeframe, "timeframe")
    from engine.data.feeds.data_root import data_path
    root = data_path("parquet")
    output_path = path_within_root(root, f"{instrument}_{timeframe}.parquet")
    return write_ohlcv_parquet(cleaned_data, output_path, authorized_root=root)
