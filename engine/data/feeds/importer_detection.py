"""Deterministic metadata detection for the historical-data importer."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from engine.data.feeds.importer_identity import (
    CanonicalIdentity,
    IdentityResolutionError,
    resolve_source_timezone,
)


# ── §129.14 Source-format version concepts ──
SOURCE_FORMAT_UDIFF_V1 = "FO_UDIFF_V1"
SOURCE_FORMAT_BHAVCOPY_LEGACY = "FO_BHAVCOPY_LEGACY"
SOURCE_FORMAT_GENERIC = "GENERIC"
SOURCE_FORMAT_UNKNOWN = "UNKNOWN"

# §129.14 UDiFF V1 FinInstrmTp → segment mapping
UDIFF_INSTRUMENT_TYPE_MAP: dict[str, str] = {
    "OPTIDX": "options",
    "FUTIDX": "futures",
    "IDO": "index",
    "FUTSTK": "futures",
    "OPTSTK": "options",
    "FUTCOM": "futures",
    "OPTCOM": "options",
}


IDENTITY_FIELDS = (
    "market",
    "instrument",
    "segment",
    "timeframe",
    "source_timezone",
    "underlying",
    "expiry",
    "strike",
    "option_type",
)
COMMON_FIELDS = ("market", "instrument", "segment", "timeframe", "source_timezone")
CONTRACT_FIELDS = {
    "futures": ("expiry",),
    "options": ("underlying", "expiry", "strike", "option_type"),
}
FIELD_ALIASES = {
    "timestamp": ("timestamp", "datetime", "date_time", "date"),
    "open": ("open", "o"), "high": ("high", "h"), "low": ("low", "l"),
    "close": ("close", "c"), "volume": ("volume", "vol"),
    # §129.14 — UDiFF V1 + Legacy Bhavcopy aliases merged into frozen set
    "instrument": ("instrument", "symbol", "underlying", "tckrsymb"),
    "underlying": ("underlying", "instrument", "symbol", "tckrsymb"),
    "expiry": ("expiry", "expiry_date", "expiry_dt", "xprydt"),
    "strike": ("strike", "strike_price", "strkpric", "strike_pr"),
    "option_type": ("option_type", "type", "cp_type", "optntp", "option_typ"),
    "timeframe": ("timeframe", "interval"),
    "market": ("market",), "segment": ("segment",), "source_timezone": ("source_timezone",),
}
TIMEFRAME_TOKENS = {"1m", "3m", "5m", "15m", "30m", "1h", "1d"}
TIMEFRAME_DELTAS = {
    "1m": pd.Timedelta(minutes=1), "3m": pd.Timedelta(minutes=3),
    "5m": pd.Timedelta(minutes=5), "15m": pd.Timedelta(minutes=15),
    "30m": pd.Timedelta(minutes=30), "1h": pd.Timedelta(hours=1),
    "1d": pd.Timedelta(days=1),
}
INDIAN_SYMBOLS = {"NIFTY", "BANKNIFTY", "SENSEX"}
OPTION_TYPE_VALUES = {"CE": "CE", "CALL": "CE", "C": "CE", "PE": "PE", "PUT": "PE", "P": "PE"}


def infer_timeframe(data: pd.DataFrame) -> str | None:
    """Infer one supported base interval only when observed timestamp spacing proves it."""
    timestamps = pd.to_datetime(data["timestamp"], errors="coerce").dropna().drop_duplicates().sort_values()
    if len(timestamps) < 3:
        return None
    differences = timestamps.diff().dropna()
    differences = differences[differences > pd.Timedelta(0)]
    supported = sorted(TIMEFRAME_DELTAS.values(), reverse=True)
    candidates = [
        interval for interval in supported
        if all(difference % interval == pd.Timedelta(0) for difference in differences)
        and interval in set(differences)
    ]
    return next((token for token, delta in TIMEFRAME_DELTAS.items() if delta == candidates[0]), None) if candidates else None


def resolve_timeframe(data: pd.DataFrame, filename_metadata: Mapping[str, str]) -> str:
    """Apply approved explicit, filename, then timestamp-derived timeframe resolution."""
    content_timeframe = _resolve_field(data, filename_metadata, "timeframe")
    inferred = infer_timeframe(data)
    if content_timeframe:
        if inferred and content_timeframe != inferred:
            raise IdentityResolutionError("Explicit/filename timeframe contradicts timestamp spacing.")
        return content_timeframe
    if inferred:
        return inferred
    raise IdentityResolutionError("Unable to deterministically resolve timeframe from metadata or timestamps.")


def parse_filename_metadata(source_file: Path) -> dict[str, str]:
    """Parse only approved underscore-delimited filename tokens; never infer unknown values."""
    tokens = {token.upper() for token in source_file.stem.split("_")}
    metadata = {}
    symbols = tokens & INDIAN_SYMBOLS
    if len(symbols) == 1:
        metadata["instrument"] = symbols.pop()
        metadata["market"] = "india"
    if "OPTIONS" in tokens:
        metadata["segment"] = "options"
    elif "FUTURES" in tokens:
        metadata["segment"] = "futures"
    elif "instrument" in metadata:
        metadata["segment"] = "index"
    timeframes = {token.casefold() for token in tokens} & TIMEFRAME_TOKENS
    if len(timeframes) == 1:
        metadata["timeframe"] = timeframes.pop()
    return metadata


def normalize_column_aliases(data: pd.DataFrame) -> pd.DataFrame:
    """Rename explicit, unambiguous source aliases needed by shared Phase 1 cleaning."""
    renamed = data.copy()
    for field in ("timestamp", "open", "high", "low", "close", "volume", "expiry", "strike", "option_type", "timeframe"):
        matches = [column for column in renamed.columns if column.casefold() in FIELD_ALIASES[field]]
        if field in renamed.columns:
            matches = [column for column in matches if column != field]
        if len(matches) > 1:
            raise IdentityResolutionError(f"Ambiguous column aliases for {field!r}.")
        # Skip rename when canonical column already exists (§129.14 UDiFF compat)
        if matches and field not in renamed.columns:
            renamed = renamed.rename(columns={matches[0]: field})
    return renamed


def _column_value(data: pd.DataFrame, field: str) -> str | None:
    matching_columns = [column for column in data.columns if column.casefold() in FIELD_ALIASES[field]]
    if not matching_columns:
        return None
    values = {str(value) for column in matching_columns for value in data[column].dropna().unique()}
    if len(values) > 1:
        raise IdentityResolutionError(f"Ambiguous {field!r} values in file contents.")
    return next(iter(values), None)


def _resolve_field(
    data: pd.DataFrame, filename_metadata: Mapping[str, str], field: str
) -> str | None:
    content_value = _column_value(data, field)
    filename_value = filename_metadata.get(field)
    if field == "option_type":
        content_value = OPTION_TYPE_VALUES.get(content_value.upper(), content_value) if content_value else None
        filename_value = OPTION_TYPE_VALUES.get(str(filename_value).upper(), str(filename_value)) if filename_value else None
    if field == "segment":
        content_value = content_value.casefold() if content_value else None
        filename_value = str(filename_value).casefold() if filename_value else None
    if field in {"instrument", "underlying"}:
        content_value = content_value.upper() if content_value else None
        filename_value = str(filename_value).upper() if filename_value else None
    if field == "market":
        content_value = content_value.casefold() if content_value else None
        filename_value = str(filename_value).casefold() if filename_value else None
    if content_value and filename_value and content_value != filename_value:
        raise IdentityResolutionError(
            f"Filename metadata contradicts file contents for {field!r}."
        )
    return content_value or (str(filename_value) if filename_value is not None else None)


def detect_source_format(data: pd.DataFrame) -> str:
    """§129.14 — detect source format concept by schema/header validation.

    Returns one of the frozen format concepts:
    - FO_UDIFF_V1: NSE UDiFF F&O bhavcopy (post 08-Jul-2024)
    - FO_BHAVCOPY_LEGACY: NSE legacy F&O bhavcopy
    - GENERIC: generic CSV with standard AlgoFortis metadata columns
    - UNKNOWN: unrecognized header schema (quarantine candidate)
    """
    columns = {col.casefold() for col in data.columns}
    # §129.14 — UDiFF V1 signature: TckrSymb + FinInstrmTp
    if "tckrsymb" in columns and "fininstrmtp" in columns:
        return SOURCE_FORMAT_UDIFF_V1
    # §129.14 — Legacy Bhavcopy signature: SYMBOL + INSTRUMENT (uppercase)
    original_columns = {col for col in data.columns}
    if "SYMBOL" in original_columns and "INSTRUMENT" in original_columns:
        return SOURCE_FORMAT_BHAVCOPY_LEGACY
    # Generic: has standard AlgoFortis metadata columns
    if "instrument" in columns or "market" in columns:
        return SOURCE_FORMAT_GENERIC
    return SOURCE_FORMAT_UNKNOWN


def _apply_udiff_segment_mapping(data: pd.DataFrame) -> pd.DataFrame:
    """§129.14 — map UDiFF FinInstrmTp to segment field if present."""
    fininstrmtp_col = next(
        (col for col in data.columns if col.casefold() == "fininstrmtp"), None
    )
    if fininstrmtp_col is None:
        return data
    result = data.copy()
    if "segment" not in result.columns:
        result["segment"] = result[fininstrmtp_col].map(UDIFF_INSTRUMENT_TYPE_MAP)
    return result


def detect_identity(
    data: pd.DataFrame, filename_metadata: Mapping[str, str] | None = None
) -> CanonicalIdentity:
    """Detect a consistent identity from row/column metadata and parsed filename metadata."""
    metadata = filename_metadata or {}
    values = {field: _resolve_field(data, metadata, field) for field in COMMON_FIELDS}
    required_common = ("market", "instrument", "segment", "timeframe")
    missing = [field for field in required_common if not values[field]]
    if missing:
        raise IdentityResolutionError(f"Missing required identity metadata: {missing}.")

    values["source_timezone"] = resolve_source_timezone(
        values["market"], values["source_timezone"]
    )
    for field in CONTRACT_FIELDS.get(values["segment"], ()):
        values[field] = _resolve_field(data, metadata, field)
    return CanonicalIdentity(**values)


def detect_contract_identities(
    data: pd.DataFrame, filename_metadata: Mapping[str, str] | None = None
) -> list[tuple[CanonicalIdentity, pd.DataFrame]]:
    """Split futures/options by contract metadata and detect one identity per output group."""
    metadata = filename_metadata or {}
    # §129.14 — apply UDiFF V1 segment mapping before identity detection
    mapped_data = _apply_udiff_segment_mapping(data)
    segment = _resolve_field(mapped_data, metadata, "segment")
    if not segment:
        raise IdentityResolutionError("Missing required identity metadata: ['segment'].")
    contract_fields = CONTRACT_FIELDS.get(segment, ())
    grouping_fields = [field for field in contract_fields if any(
        column.casefold() == field for column in mapped_data.columns
    )]
    if not grouping_fields:
        return [(detect_identity(mapped_data, metadata), mapped_data)]
    return [
        (detect_identity(group, metadata), group.copy())
        for _, group in mapped_data.groupby(grouping_fields, dropna=False, sort=False)
    ]
