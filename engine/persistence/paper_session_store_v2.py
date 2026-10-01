"""Focused SQLite repository for Phase-5 paper-owned session state."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from engine.paper.contracts_v2 import PaperOrderRecord, PaperPositionRecord, PaperSession
from engine.persistence.paper_codec_v2 import dumps_record, loads_record
from engine.persistence.paper_recovery_store_v2 import PaperRecoveryStore


class OwnedStateIntegrityError(RuntimeError):
    """Persisted owned-state references cannot be reconstructed exactly."""


@dataclass(frozen=True, slots=True)
class OwnedPaperState:
    session: PaperSession
    orders: tuple[PaperOrderRecord, ...]
    positions: tuple[PaperPositionRecord, ...]


class PaperSessionStore:
    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)
        if not self.database_path.is_file():
            raise FileNotFoundError(self.database_path)

    def _open(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.database_path))
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def save_session(self, session: PaperSession) -> None:
        if not isinstance(session, PaperSession):
            raise TypeError("session must be PaperSession")
        with self._open() as connection:
            connection.execute(
                """
                INSERT INTO phase5_paper_sessions(session_id, payload_json)
                VALUES (?, ?)
                ON CONFLICT(session_id) DO UPDATE SET payload_json=excluded.payload_json
                """,
                (session.session_id, dumps_record(session)),
            )

    def load_session(self, session_id: str) -> PaperSession | None:
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be non-empty")
        with self._open() as connection:
            row = connection.execute(
                "SELECT payload_json FROM phase5_paper_sessions WHERE session_id = ?",
                (session_id.strip(),),
            ).fetchone()
        if row is None:
            return None
        return loads_record(str(row[0]), PaperSession)

    def save_order(self, record: PaperOrderRecord) -> None:
        if not isinstance(record, PaperOrderRecord):
            raise TypeError("record must be PaperOrderRecord")
        with self._open() as connection:
            connection.execute(
                """
                INSERT INTO phase5_paper_orders(logical_intent_id, payload_json)
                VALUES (?, ?)
                ON CONFLICT(logical_intent_id) DO UPDATE SET payload_json=excluded.payload_json
                """,
                (record.logical_intent_id, dumps_record(record)),
            )

    def load_order(self, logical_intent_id: str) -> PaperOrderRecord | None:
        with self._open() as connection:
            row = connection.execute(
                "SELECT payload_json FROM phase5_paper_orders WHERE logical_intent_id = ?",
                (logical_intent_id,),
            ).fetchone()
        return None if row is None else loads_record(str(row[0]), PaperOrderRecord)

    def save_position(self, record: PaperPositionRecord) -> None:
        if not isinstance(record, PaperPositionRecord):
            raise TypeError("record must be PaperPositionRecord")
        with self._open() as connection:
            connection.execute(
                """
                INSERT INTO phase5_paper_positions(position_id, payload_json)
                VALUES (?, ?)
                ON CONFLICT(position_id) DO UPDATE SET payload_json=excluded.payload_json
                """,
                (record.position_id, dumps_record(record)),
            )

    def load_position(self, position_id: str) -> PaperPositionRecord | None:
        with self._open() as connection:
            row = connection.execute(
                "SELECT payload_json FROM phase5_paper_positions WHERE position_id = ?",
                (position_id,),
            ).fetchone()
        return None if row is None else loads_record(str(row[0]), PaperPositionRecord)

    def load_owned_state(self, session_id: str) -> OwnedPaperState:
        session = self.load_session(session_id)
        if session is None:
            raise KeyError(f"unknown paper session: {session_id}")

        checkpoint = PaperRecoveryStore(self.database_path).latest_checkpoint(session_id)
        if checkpoint is None:
            return OwnedPaperState(session=session, orders=(), positions=())

        orders: list[PaperOrderRecord] = []
        for ref in checkpoint.open_order_refs:
            record = self.load_order(ref)
            if record is None:
                raise OwnedStateIntegrityError(f"missing referenced paper order: {ref}")
            orders.append(record)

        positions: list[PaperPositionRecord] = []
        for ref in checkpoint.open_position_refs:
            record = self.load_position(ref)
            if record is None:
                raise OwnedStateIntegrityError(f"missing referenced paper position: {ref}")
            positions.append(record)

        return OwnedPaperState(
            session=session,
            orders=tuple(orders),
            positions=tuple(positions),
        )


__all__ = ["OwnedStateIntegrityError", "OwnedPaperState", "PaperSessionStore"]
