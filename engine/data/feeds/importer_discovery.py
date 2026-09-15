"""Supported incoming-file discovery for the historical-data importer."""

from pathlib import Path


SUPPORTED_INPUT_SUFFIXES = {".csv", ".xlsx", ".xls", ".parquet"}


def discover_incoming_files(incoming_directory: Path | None = None) -> list[Path]:
    """Return supported files without modifying the incoming directory or its files."""
    if incoming_directory is None:
        from engine.data.feeds.data_root import data_path
        incoming_directory = data_path("incoming")
    if not incoming_directory.exists():
        return []
    return sorted(
        path
        for path in incoming_directory.iterdir()
        if path.is_file() and path.suffix.casefold() in SUPPORTED_INPUT_SUFFIXES
    )
