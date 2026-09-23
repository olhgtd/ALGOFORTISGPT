from __future__ import annotations

from hashlib import sha256
from importlib import import_module
from pathlib import Path
import sqlite3

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from engine.data.catalog import DatasetProvenance, DatasetRecord


def _store_api():
    try:
        return import_module("engine.data.store")
    except ModuleNotFoundError:
        pytest.fail("engine.data.store is missing", pytrace=False)


def _catalog_store_api():
    try:
        return import_module("engine.data.catalog_store")
    except ModuleNotFoundError:
        pytest.fail("engine.data.catalog_store is missing", pytrace=False)


def _table() -> pa.Table:
    return pa.table(
        {
            "timestamp_ns": pa.array([1_700_000_000_000_000_000, 1_700_000_060_000_000_000], type=pa.int64()),
            "open": ["22000.10", "22005.00"],
            "high": ["22010.50", "22020.00"],
            "low": ["21995.25", "22002.00"],
            "close": ["22005.00", "22015.00"],
            "volume": [1000, 1200],
        }
    )


def _parquet_bytes(table: pa.Table) -> bytes:
    sink = pa.BufferOutputStream()
    pq.write_table(
        table,
        sink,
        compression="NONE",
        use_dictionary=False,
        write_statistics=False,
        version="2.6",
    )
    return sink.getvalue().to_pybytes()


def _record(table: pa.Table | None = None) -> DatasetRecord:
    table = _table() if table is None else table
    content_sha256 = sha256(_parquet_bytes(table)).hexdigest()
    provenance = DatasetProvenance(
        source_id="licensed-feed-a",
        source_type="licensed",
        licence_id="lic-research-v1",
        permitted_use="research",
    )
    return DatasetRecord.build(
        namespace="market",
        logical_name="nifty-1m-bars",
        data_kind="bars",
        schema_version="ohlcv/v1",
        content_sha256=content_sha256,
        provenance=provenance,
        lineage=("raw:nifty-1m:2026-01",),
    )


def test_parquet_publish_is_content_addressed_atomic_and_idempotent(tmp_path: Path):
    api = _store_api()
    table = _table()
    record = _record(table)
    store = api.HistoricalDatasetStore(tmp_path / "historical")

    first = store.publish(record, table)
    second = store.publish(record, table)

    assert first == second
    assert first.is_file()
    assert first.name == "data.parquet"
    assert first.parent.name == record.version_id
    assert first.parent.parent.name == record.dataset_id
    assert sha256(first.read_bytes()).hexdigest() == record.content_sha256
    assert not tuple(first.parent.glob("*.part"))


def test_publish_refuses_checksum_mismatch_and_never_creates_final_artifact(tmp_path: Path):
    api = _store_api()
    table = _table()
    record = _record(table)
    bad = DatasetRecord.build(
        namespace=record.namespace,
        logical_name=record.logical_name,
        data_kind=record.data_kind,
        schema_version=record.schema_version,
        content_sha256="f" * 64,
        provenance=record.provenance,
        lineage=record.lineage,
    )
    store = api.HistoricalDatasetStore(tmp_path / "historical")

    with pytest.raises(api.HistoricalStoreError, match="checksum"):
        store.publish(bad, table)

    assert not store.path_for(bad).exists()


def test_read_detects_corruption_in_immutable_artifact(tmp_path: Path):
    api = _store_api()
    table = _table()
    record = _record(table)
    store = api.HistoricalDatasetStore(tmp_path / "historical")
    path = store.publish(record, table)
    path.write_bytes(path.read_bytes() + b"corruption")

    with pytest.raises(api.HistoricalStoreError, match="checksum"):
        store.read(record)


def test_publish_refuses_overwrite_when_existing_version_bytes_differ(tmp_path: Path):
    api = _store_api()
    table = _table()
    record = _record(table)
    store = api.HistoricalDatasetStore(tmp_path / "historical")
    path = store.publish(record, table)
    path.write_bytes(b"different-existing-bytes")

    with pytest.raises(api.HistoricalStoreError, match="immutable"):
        store.publish(record, table)

    assert path.read_bytes() == b"different-existing-bytes"


def test_sqlite_catalog_persists_records_and_reconstructs_catalog_after_restart(tmp_path: Path):
    api = _catalog_store_api()
    record = _record()
    database = tmp_path / "operational" / "datasets.sqlite3"

    first = api.SQLiteDatasetCatalogStore(database)
    first.save(record)
    first.close()

    reopened = api.SQLiteDatasetCatalogStore(database)
    catalog = reopened.load_catalog()
    assert catalog.get(record.dataset_id, record.version_id) == record
    reopened.close()


def test_sqlite_catalog_backup_and_verified_restore_round_trip(tmp_path: Path):
    api = _catalog_store_api()
    record = _record()
    database = tmp_path / "operational" / "datasets.sqlite3"
    backup = tmp_path / "backups" / "datasets.sqlite3"
    restored = tmp_path / "restored" / "datasets.sqlite3"

    store = api.SQLiteDatasetCatalogStore(database)
    store.save(record)
    backup_path = store.backup_to(backup)
    store.close()

    assert backup_path == backup.resolve()
    with sqlite3.connect(str(backup_path)) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    api.SQLiteDatasetCatalogStore.restore_verified(backup_path, restored)
    restored_store = api.SQLiteDatasetCatalogStore(restored)
    assert restored_store.load_catalog().get(record.dataset_id, record.version_id) == record
    restored_store.close()


def test_sqlite_catalog_save_is_idempotent_but_conflicting_version_row_fails_closed(tmp_path: Path):
    api = _catalog_store_api()
    record = _record()
    database = tmp_path / "datasets.sqlite3"
    store = api.SQLiteDatasetCatalogStore(database)
    store.save(record)
    store.save(record)

    with sqlite3.connect(str(database)) as connection:
        connection.execute(
            "UPDATE dataset_versions SET content_sha256 = ? WHERE dataset_id = ? AND version_id = ?",
            ("f" * 64, record.dataset_id, record.version_id),
        )
        connection.commit()

    with pytest.raises(api.CatalogStoreError, match="conflict"):
        store.save(record)
    store.close()
