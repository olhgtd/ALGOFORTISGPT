"""Focused SQLite repository for Phase-5 recovery checkpoints/reports."""

from __future__ import annotations

from pathlib import Path
import re
import sqlite3

from engine.paper.contracts_v2 import RecoveryCheckpoint, RecoveryReport
from engine.persistence.paper_codec_v2 import dumps_record, loads_record

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class CheckpointIntegrityError(RuntimeError):
    """Stored recovery checkpoint is malformed or contradicts indexed columns."""


class PaperRecoveryStore:
    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)
        if not self.database_path.is_file():
            raise FileNotFoundError(self.database_path)

    def _open(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.database_path))
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def save_checkpoint(self, checkpoint: RecoveryCheckpoint) -> None:
        if not isinstance(checkpoint, RecoveryCheckpoint):
            raise TypeError("checkpoint must be RecoveryCheckpoint")
        with self._open() as connection:
            connection.execute(
                """
                INSERT INTO phase5_recovery_checkpoints(
                    checkpoint_id, session_id, persisted_at,
                    last_event_sequence, fingerprint, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint.checkpoint_id,
                    checkpoint.session_id,
                    checkpoint.persisted_at.isoformat(),
                    checkpoint.last_event_sequence,
                    checkpoint.fingerprint,
                    dumps_record(checkpoint),
                ),
            )

    def latest_checkpoint(self, session_id: str) -> RecoveryCheckpoint | None:
        with self._open() as connection:
            row = connection.execute(
                """
                SELECT checkpoint_id, session_id, persisted_at,
                       last_event_sequence, fingerprint, payload_json
                FROM phase5_recovery_checkpoints
                WHERE session_id = ?
                ORDER BY last_event_sequence DESC, persisted_at DESC, checkpoint_id DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        checkpoint_id, stored_session, persisted_at, sequence, fingerprint, payload_json = row
        if not isinstance(fingerprint, str) or not _HEX64.fullmatch(fingerprint):
            raise CheckpointIntegrityError("stored checkpoint fingerprint is invalid")
        try:
            checkpoint = loads_record(str(payload_json), RecoveryCheckpoint)
        except (TypeError, ValueError) as exc:
            raise CheckpointIntegrityError(f"stored checkpoint payload is invalid: {exc}") from exc
        indexed = (
            checkpoint.checkpoint_id,
            checkpoint.session_id,
            checkpoint.persisted_at.isoformat(),
            checkpoint.last_event_sequence,
            checkpoint.fingerprint,
        )
        if indexed != (checkpoint_id, stored_session, persisted_at, sequence, fingerprint):
            raise CheckpointIntegrityError("stored checkpoint indexed fields/fingerprint disagree with payload")
        return checkpoint

    def save_recovery_report(self, report: RecoveryReport) -> None:
        if not isinstance(report, RecoveryReport):
            raise TypeError("report must be RecoveryReport")
        with self._open() as connection:
            connection.execute(
                """
                INSERT INTO phase5_recovery_reports(recovery_id, produced_at, payload_json)
                VALUES (?, ?, ?)
                """,
                (report.recovery_id, report.produced_at.isoformat(), dumps_record(report)),
            )

    def load_recovery_report(self, recovery_id: str) -> RecoveryReport | None:
        with self._open() as connection:
            row = connection.execute(
                "SELECT payload_json FROM phase5_recovery_reports WHERE recovery_id = ?",
                (recovery_id,),
            ).fetchone()
        return None if row is None else loads_record(str(row[0]), RecoveryReport)


__all__ = ["CheckpointIntegrityError", "PaperRecoveryStore"]
