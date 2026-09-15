import logging
from pathlib import Path

import pandas as pd

from engine.data.feeds.base import DataFeed
from engine.data.feeds.data_cleaning import invalid_ohlcv_mask, normalize_timestamps
from engine.data.feeds.importer_storage import resolve_stream_storage_path
from engine.market import StreamKey


logger = logging.getLogger(__name__)


class HistoricalDataFeed(DataFeed):
    """Serves from Parquet store, respects walk-forward train/test boundaries."""

    def fetch(self, instrument: str, timeframe: str) -> pd.DataFrame:
        """Fetch through the frozen marketless legacy read surface."""
        from engine.data.feeds.data_root import data_path
        canonical_path = (
            data_path("parquet", instrument, timeframe, "data.parquet")
        )
        legacy_path = data_path("parquet", f"{instrument}_{timeframe}.parquet")
        parquet_path = canonical_path if canonical_path.exists() else legacy_path

        if not parquet_path.exists():
            raise FileNotFoundError(
                f"Historical Parquet file not found for instrument={instrument!r}, "
                f"timeframe={timeframe!r}: {canonical_path} or {legacy_path}"
            )

        return self._read_ohlcv(parquet_path, instrument=instrument, timeframe=timeframe)

    def fetch_stream(self, stream: StreamKey) -> pd.DataFrame:
        """Fetch one exact market-qualified StorageLayout/v2 stream only."""
        if not isinstance(stream, StreamKey):
            raise TypeError("stream must be a StreamKey")
        parquet_path = resolve_stream_storage_path(stream)
        if not parquet_path.exists():
            raise FileNotFoundError(
                "Historical exact-stream Parquet file not found for "
                f"stream={stream!r}: {parquet_path}"
            )
        return self._read_ohlcv(
            parquet_path,
            instrument=stream.identity.instrument,
            timeframe=stream.timeframe,
        )

    @staticmethod
    def _read_ohlcv(parquet_path: Path, *, instrument: str, timeframe: str) -> pd.DataFrame:
        """Read and preserve the established defensive feed-cleaning behavior."""
        data = pd.read_parquet(parquet_path)

        # Keep the first row for each timestamp and remove later duplicates.
        duplicate_count = data.duplicated(subset=["timestamp"]).sum()
        if duplicate_count:
            data = data.drop_duplicates(subset=["timestamp"], keep="first")
            logger.info(
                "Removed %d duplicate row(s) for instrument=%r, timeframe=%r.",
                duplicate_count,
                instrument,
                timeframe,
            )

        # Normalize timestamps to the IST timezone without changing naive clock times.
        normalize_timestamps(data)

        # Reject rows that fail the required OHLC and volume sanity checks.
        invalid_rows = invalid_ohlcv_mask(data)
        invalid_count = invalid_rows.sum()
        if invalid_count:
            data = data.loc[~invalid_rows]
            logger.info(
                "Rejected %d invalid OHLCV row(s) for instrument=%r, timeframe=%r.",
                invalid_count,
                instrument,
                timeframe,
            )

        return data[["timestamp", "open", "high", "low", "close", "volume"]]
