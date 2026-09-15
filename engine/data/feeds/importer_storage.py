"""One market-qualified StorageLayout/v2 resolver for historical datasets."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from engine.data.feeds.importer_identity import CanonicalIdentity
from engine.data.feeds.path_safety import path_within_root
from engine.data.feeds.data_root import data_path

if TYPE_CHECKING:
    from engine.market import StreamKey

CANONICAL_STORAGE_ROOT = data_path("parquet")


def _date_text(value: date | str | None, field_name: str) -> str:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"{field_name} is required for StorageLayout/v2")


def _strike_text(value: Decimal | int | float | str | None) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (str, int, float)) and str(value):
        return str(value)
    raise ValueError("strike is required for StorageLayout/v2 options")


def _resolve_v2_path(
    *,
    market: str,
    instrument: str,
    segment: str,
    timeframe: str,
    underlying: str | None = None,
    expiry: date | str | None = None,
    strike: Decimal | int | float | str | None = None,
    option_type: str | None = None,
) -> Path:
    """Resolve one complete identity through the only StorageLayout/v2 rule."""
    root = CANONICAL_STORAGE_ROOT
    if segment == "futures":
        return path_within_root(
            root, market, instrument, segment, _date_text(expiry, "expiry"), timeframe, "data.parquet"
        )
    if segment == "options":
        if not underlying or not option_type:
            raise ValueError("options identity is incomplete for StorageLayout/v2")
        return path_within_root(
            root,
            market,
            instrument,
            segment,
            underlying,
            _date_text(expiry, "expiry"),
            _strike_text(strike),
            option_type,
            timeframe,
            "data.parquet",
        )
    return path_within_root(root, market, instrument, segment, timeframe, "data.parquet")


def resolve_storage_path(identity: CanonicalIdentity) -> Path:
    """Return the StorageLayout/v2 path for a validated importer identity."""
    if not isinstance(identity, CanonicalIdentity):
        raise TypeError("identity must be a CanonicalIdentity")
    return _resolve_v2_path(
        market=identity.market,
        instrument=identity.instrument,
        segment=identity.segment,
        timeframe=identity.timeframe,
        underlying=identity.underlying,
        expiry=identity.expiry,
        strike=identity.strike,
        option_type=identity.option_type,
    )


def resolve_stream_storage_path(stream: "StreamKey") -> Path:
    """Resolve an exact StreamKey through the same StorageLayout/v2 rule."""
    from engine.market import StreamKey

    if not isinstance(stream, StreamKey):
        raise TypeError("stream must be a StreamKey")
    identity = stream.identity
    return _resolve_v2_path(
        market=identity.market,
        instrument=identity.instrument,
        segment=identity.segment,
        timeframe=stream.timeframe,
        underlying=identity.underlying,
        expiry=identity.expiry,
        strike=identity.strike,
        option_type=identity.option_type,
    )
