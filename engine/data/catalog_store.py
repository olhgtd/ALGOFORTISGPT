"""SQLite persistence and verified backup/restore for the Data V2 catalog."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3

from engine.data.catalog import (
    DatasetCatalog,
    DatasetCatalogError,
    DatasetProvenance,
    DatasetRecord,
)


class CatalogStoreError(RuntimeError):
    """Raised when persistent dataset-catalog evidence is unsafe or corrupt."""


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS dataset_versions (
    dataset_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    namespace TEXT NOT NULL,
    logical_name TEXT NOT NULL,
    data_kind TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    licence_id TEXT NOT NULL,
    permitted_use TEXT NOT NULL,
    synthetic INTEGER NOT NULL CHECK (synthetic IN (0, 1)),
    model_ref TEXT NOT NULL,
    lineage_json TEXT NOT NULL,
    PRIMARY KEY (dataset_id, version_id)
)
"""

_COLUMNS = (
    "dataset_id",
    "version_id",
    "namespace",
    "logical_name",
    "data_kind",
    "schema_version",
    "content_sha256",
    "source_id",
    "source_type",
    "licence_id",
    "permitted_use",
    "synthetic",
    "model_ref",
    "lineage_json",
)


def _record_row(record: DatasetRecord) -> tuple[object, ...]:
    return (
        record.dataset_id,
        record.version_id,
        record.namespace,
        record.logical_name,
        record.data_kind,
        record.schema_version,
        record.content_sha256,
        record.provenance.source_id,
        record.provenance.source_type,
        record.provenance.licence_id,
        record.provenance.permitted_use,
        1 if record.provenance.synthetic else 0,
        record.provenance.model_ref,
        json.dumps(record.lineage, separators=(",", ":"), ensure_ascii=True),
    )


def _integrity_ok(path: Path) -> None:
    if not path.is_file():
        raise CatalogStoreError(f"SQLite database is missing: {path}")
    connection = sqlite3.connect(str(path))
    try:
        rows = connection.execute("PRAGMA integrity_check").fetchall()
    finally:
        connection.close()
    if not rows or any(str(row[0]).casefold() != "ok" for row in rows):
        raise CatalogStoreError(f"SQLite integrity check failed for {path}: {rows!r}")


class SQLiteDatasetCatalogStore:
    """Operational SQLite metadata store for immutable historical datasets."""

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path).resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self.database_path))
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        self._connection.execute(_SCHEMA_SQL)
        self._connection.commit()
        self._closed = False

    def _require_open(self) -> sqlite3.Connection:
        if self._closed:
            raise CatalogStoreError("dataset catalog store is closed")
        return self._connection

    def save(self, record: DatasetRecord) -> DatasetRecord:
        if not isinstance(record, DatasetRecord):
            raise CatalogStoreError("record must be DatasetRecord")
        connection = self._require_open()
        values = _record_row(record)
        existing = connection.execute(
            "SELECT " + ", ".join(_COLUMNS) + " FROM dataset_versions "
            "WHERE dataset_id = ? AND version_id = ?",
            (record.dataset_id, record.version_id),
        ).fetchone()
        if existing is not None:
            if tuple(existing) != values:
                raise CatalogStoreError(
                    "persistent dataset version conflict: immutable evidence differs from requested record"
                )
            return record

        try:
            connection.execute(
                "INSERT INTO dataset_versions (" + ", ".join(_COLUMNS) + ") "
                "VALUES (" + ",".join("?" for _ in _COLUMNS) + ")",
                values,
            )
            connection.commit()
        except Exception as exc:
            connection.rollback()
            raise CatalogStoreError(f"dataset catalog save failed: {exc}") from exc
        return record

    def load_catalog(self) -> DatasetCatalog:
        connection = self._require_open()
        rows = connection.execute(
            "SELECT " + ", ".join(_COLUMNS) + " FROM dataset_versions "
            "ORDER BY dataset_id, version_id"
        ).fetchall()
        catalog = DatasetCatalog()
        try:
            for row in rows:
                (
                    dataset_id,
                    version_id,
                    namespace,
                    logical_name,
                    data_kind,
                    schema_version,
                    content_sha256,
                    source_id,
                    source_type,
                    licence_id,
                    permitted_use,
                    synthetic,
                    model_ref,
                    lineage_json,
                ) = row
                decoded = json.loads(str(lineage_json))
                if not isinstance(decoded, list) or not all(isinstance(item, str) for item in decoded):
                    raise CatalogStoreError("stored lineage_json is invalid")
                provenance = DatasetProvenance(
                    source_id=str(source_id),
                    source_type=str(source_type),
                    licence_id=str(licence_id),
                    permitted_use=str(permitted_use),
                    synthetic=bool(synthetic),
                    model_ref=str(model_ref),
                )
                record = DatasetRecord.build(
                    namespace=str(namespace),
                    logical_name=str(logical_name),
                    data_kind=str(data_kind),
                    schema_version=str(schema_version),
                    content_sha256=str(content_sha256),
                    provenance=provenance,
                    lineage=tuple(decoded),
                )
                if record.dataset_id != dataset_id or record.version_id != version_id:
                    raise CatalogStoreError("stored dataset identity conflicts with deterministic evidence")
                catalog.register(record)
        except CatalogStoreError:
            raise
        except (DatasetCatalogError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise CatalogStoreError(f"stored dataset catalog is corrupt: {exc}") from exc
        return catalog

    def backup_to(self, destination: Path | str) -> Path:
        connection = self._require_open()
        destination_path = Path(destination).resolve()
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        if destination_path.exists():
            raise CatalogStoreError(f"backup destination already exists: {destination_path}")
        partial = destination_path.with_suffix(destination_path.suffix + ".part")
        if partial.exists():
            partial.unlink()

        try:
            target = sqlite3.connect(str(partial))
            try:
                connection.backup(target)
            finally:
                target.close()
            _integrity_ok(partial)
            os.link(str(partial), str(destination_path))
            _integrity_ok(destination_path)
            return destination_path
        except Exception as exc:
            if isinstance(exc, CatalogStoreError):
                raise
            raise CatalogStoreError(f"verified catalog backup failed: {exc}") from exc
        finally:
            if partial.exists():
                try:
                    partial.unlink()
                except OSError:
                    pass

    @staticmethod
    def restore_verified(source: Path | str, destination: Path | str) -> Path:
        source_path = Path(source).resolve()
        destination_path = Path(destination).resolve()
        _integrity_ok(source_path)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        if destination_path.exists():
            raise CatalogStoreError(f"restore destination already exists: {destination_path}")
        partial = destination_path.with_suffix(destination_path.suffix + ".part")
        if partial.exists():
            partial.unlink()

        source_connection = sqlite3.connect(str(source_path))
        try:
            target = sqlite3.connect(str(partial))
            try:
                source_connection.backup(target)
            finally:
                target.close()
        except Exception as exc:
            raise CatalogStoreError(f"catalog restore copy failed: {exc}") from exc
        finally:
            source_connection.close()

        try:
            _integrity_ok(partial)
            os.link(str(partial), str(destination_path))
            _integrity_ok(destination_path)
            return destination_path
        except Exception as exc:
            if destination_path.exists():
                try:
                    destination_path.unlink()
                except OSError:
                    pass
            if isinstance(exc, CatalogStoreError):
                raise
            raise CatalogStoreError(f"verified catalog restore failed: {exc}") from exc
        finally:
            if partial.exists():
                try:
                    partial.unlink()
                except OSError:
                    pass

    def close(self) -> None:
        if not self._closed:
            self._connection.close()
            self._closed = True

    def __enter__(self) -> "SQLiteDatasetCatalogStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


__all__ = ["CatalogStoreError", "SQLiteDatasetCatalogStore"]
