"""Focused durable store for Live broker-account ownership evidence.

The durable row is only a local exclusivity backstop. It never arms Live and it
is deliberately cleared during restart recovery before a new owner may be
established.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.live.account_exclusivity_v2 import LiveAccountOwner


class LiveAccountExclusivityStoreError(RuntimeError):
    pass


class LiveAccountExclusivityStoreConflict(LiveAccountExclusivityStoreError):
    pass


class LiveAccountExclusivityStoreCorrupt(LiveAccountExclusivityStoreError):
    pass


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LiveAccountExclusivityStoreCorrupt(f"{field} must be a non-empty string")
    return value.strip()


def _aware_text(value: object, field: str) -> datetime:
    text = _text(value, field)
    try:
        result = datetime.fromisoformat(text)
    except ValueError as exc:
        raise LiveAccountExclusivityStoreCorrupt(f"{field} is not an ISO datetime") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise LiveAccountExclusivityStoreCorrupt(f"{field} must be timezone-aware")
    return result


class LiveAccountExclusivityStoreV2:
    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)
        if not self.database_path.is_file():
            raise FileNotFoundError(self.database_path)

    def _open(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.database_path), timeout=5.0)
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def load(self, broker_id: str, broker_account_ref: str) -> "LiveAccountOwner | None":
        broker = _text(broker_id, "broker_id")
        account = _text(broker_account_ref, "broker_account_ref")
        with self._open() as connection:
            row = connection.execute(
                """
                SELECT broker_id, broker_account_ref, device_id, session_family_id,
                       ownership_nonce, acquired_at_utc
                FROM live_account_exclusivity
                WHERE broker_id = ? AND broker_account_ref = ?
                """,
                (broker, account),
            ).fetchone()
        if row is None:
            return None

        from engine.live.account_exclusivity_v2 import LiveAccountOwner

        try:
            return LiveAccountOwner(
                broker_id=_text(row[0], "broker_id"),
                broker_account_ref=_text(row[1], "broker_account_ref"),
                device_id=_text(row[2], "device_id"),
                session_family_id=_text(row[3], "session_family_id"),
                ownership_nonce=_text(row[4], "ownership_nonce"),
                acquired_at_utc=_aware_text(row[5], "acquired_at_utc"),
            )
        except LiveAccountExclusivityStoreCorrupt:
            raise
        except Exception as exc:
            raise LiveAccountExclusivityStoreCorrupt("durable owner row is invalid") from exc

    def save(self, owner: "LiveAccountOwner") -> "LiveAccountOwner":
        from engine.live.account_exclusivity_v2 import LiveAccountOwner

        if not isinstance(owner, LiveAccountOwner):
            raise TypeError("owner must be LiveAccountOwner")
        connection = self._open()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT device_id, session_family_id, ownership_nonce, acquired_at_utc
                FROM live_account_exclusivity
                WHERE broker_id = ? AND broker_account_ref = ?
                """,
                (owner.broker_id, owner.broker_account_ref),
            ).fetchone()
            if row is not None:
                same = (
                    str(row[0]) == owner.device_id
                    and str(row[1]) == owner.session_family_id
                    and str(row[2]) == owner.ownership_nonce
                    and str(row[3]) == owner.acquired_at_utc.isoformat()
                )
                if same:
                    connection.commit()
                    return owner
                raise LiveAccountExclusivityStoreConflict(
                    f"broker account already owned: {owner.broker_id}/{owner.broker_account_ref}"
                )
            try:
                connection.execute(
                    """
                    INSERT INTO live_account_exclusivity(
                        broker_id, broker_account_ref, device_id, session_family_id,
                        ownership_nonce, acquired_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        owner.broker_id,
                        owner.broker_account_ref,
                        owner.device_id,
                        owner.session_family_id,
                        owner.ownership_nonce,
                        owner.acquired_at_utc.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise LiveAccountExclusivityStoreConflict(
                    f"broker account ownership conflict: {owner.broker_id}/{owner.broker_account_ref}"
                ) from exc
            connection.commit()
            return owner
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def clear(self, broker_id: str, broker_account_ref: str, ownership_nonce: str) -> bool:
        broker = _text(broker_id, "broker_id")
        account = _text(broker_account_ref, "broker_account_ref")
        nonce = _text(ownership_nonce, "ownership_nonce")
        with self._open() as connection:
            cursor = connection.execute(
                """
                DELETE FROM live_account_exclusivity
                WHERE broker_id = ? AND broker_account_ref = ? AND ownership_nonce = ?
                """,
                (broker, account, nonce),
            )
            return cursor.rowcount == 1


__all__ = [
    "LiveAccountExclusivityStoreConflict",
    "LiveAccountExclusivityStoreCorrupt",
    "LiveAccountExclusivityStoreError",
    "LiveAccountExclusivityStoreV2",
]
