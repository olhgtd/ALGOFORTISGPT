"""Immutable local Parquet historical storage for AlgoFortis V2 Data V2."""

from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import tempfile

import pyarrow as pa
import pyarrow.parquet as pq

from engine.data.catalog import DatasetRecord


class HistoricalStoreError(RuntimeError):
    """Raised when a historical artifact cannot be safely published or read."""


def _canonical_parquet_bytes(table: pa.Table) -> bytes:
    if not isinstance(table, pa.Table):
        raise HistoricalStoreError("historical publish requires a pyarrow.Table")
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


def _sha256_bytes(payload: bytes) -> str:
    return sha256(payload).hexdigest()


class HistoricalDatasetStore:
    """Write-once, checksum-verified Parquet artifact store.

    Layout is content-identity scoped by dataset and version IDs::

        <root>/<dataset_id>/<version_id>/data.parquet

    A published version is never overwritten.  Re-publishing identical evidence
    is idempotent; any byte drift fails closed.
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()

    def path_for(self, record: DatasetRecord) -> Path:
        if not isinstance(record, DatasetRecord):
            raise HistoricalStoreError("record must be DatasetRecord")
        return self.root / record.dataset_id / record.version_id / "data.parquet"

    def publish(self, record: DatasetRecord, table: pa.Table) -> Path:
        if not isinstance(record, DatasetRecord):
            raise HistoricalStoreError("record must be DatasetRecord")

        payload = _canonical_parquet_bytes(table)
        actual = _sha256_bytes(payload)
        if actual != record.content_sha256:
            raise HistoricalStoreError(
                f"Parquet checksum mismatch: record={record.content_sha256} actual={actual}"
            )

        final_path = self.path_for(record)
        final_path.parent.mkdir(parents=True, exist_ok=True)

        if final_path.exists():
            existing = _sha256_bytes(final_path.read_bytes())
            if existing != record.content_sha256:
                raise HistoricalStoreError(
                    "immutable dataset version already exists with different bytes"
                )
            return final_path

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=str(final_path.parent),
                prefix="data.parquet.",
                suffix=".part",
                delete=False,
            ) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
                temporary_path = Path(handle.name)

            # Hard-link publication is atomic and refuses to replace an existing
            # immutable version on both NTFS and POSIX filesystems.
            try:
                os.link(str(temporary_path), str(final_path))
            except FileExistsError:
                existing = _sha256_bytes(final_path.read_bytes())
                if existing != record.content_sha256:
                    raise HistoricalStoreError(
                        "immutable dataset version was concurrently published with different bytes"
                    )
            except OSError as exc:
                raise HistoricalStoreError(f"atomic Parquet publish failed: {exc}") from exc

            if not final_path.is_file():
                raise HistoricalStoreError("atomic Parquet publish did not create final artifact")
            published = _sha256_bytes(final_path.read_bytes())
            if published != record.content_sha256:
                raise HistoricalStoreError("published Parquet checksum verification failed")
            return final_path
        finally:
            if temporary_path is not None and temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    pass

    def read(self, record: DatasetRecord) -> pa.Table:
        path = self.path_for(record)
        if not path.is_file():
            raise HistoricalStoreError(f"historical artifact is missing: {path}")
        payload = path.read_bytes()
        actual = _sha256_bytes(payload)
        if actual != record.content_sha256:
            raise HistoricalStoreError(
                f"historical artifact checksum mismatch: record={record.content_sha256} actual={actual}"
            )
        try:
            return pq.read_table(pa.BufferReader(payload))
        except Exception as exc:
            raise HistoricalStoreError(f"historical Parquet read failed: {exc}") from exc


__all__ = ["HistoricalStoreError", "HistoricalDatasetStore"]
