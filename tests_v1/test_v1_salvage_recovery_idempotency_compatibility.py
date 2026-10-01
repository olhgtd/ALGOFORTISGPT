"""Manual-V1 recovery/idempotency compatibility guards on V2 authorities."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3

import pytest

from engine.paper.contracts_v2 import RecoveryCheckpoint
from engine.persistence.paper_recovery_store_v2 import PaperRecoveryStore
from engine.persistence.schema import CREATE_TABLES_SQL, SCHEMA_VERSION


NOW = datetime(2026, 9, 29, 3, 45, tzinfo=timezone.utc)


def _database(tmp_path: Path) -> Path:
    path = tmp_path / "v1-salvage-recovery.sqlite3"
    with sqlite3.connect(path) as connection:
        for statement in CREATE_TABLES_SQL:
            connection.execute(statement)
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        connection.commit()
    return path


def _checkpoint(*, sequence: int = 42, fingerprint: str = "a" * 64) -> RecoveryCheckpoint:
    return RecoveryCheckpoint(
        checkpoint_id="checkpoint-v1-salvage",
        session_id="session-v1-salvage",
        persisted_at=NOW,
        last_event_sequence=sequence,
        open_order_refs=("order-1",),
        open_position_refs=("position-1",),
        recovery_required=True,
        reason="PROCESS_CRASH",
        fingerprint=fingerprint,
    )


def test_duplicate_checkpoint_identity_cannot_overwrite_recovery_evidence(tmp_path: Path) -> None:
    """A repeated checkpoint ID must fail closed instead of replacing evidence."""

    store = PaperRecoveryStore(_database(tmp_path))
    original = _checkpoint()
    conflicting_replay = _checkpoint(sequence=43, fingerprint="b" * 64)

    store.save_checkpoint(original)

    with pytest.raises(sqlite3.IntegrityError):
        store.save_checkpoint(conflicting_replay)

    assert store.latest_checkpoint(original.session_id) == original
