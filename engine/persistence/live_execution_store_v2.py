"""Focused SQLite store for V2 Live execution evidence and account capacity reservations."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sqlite3

from engine.orders.contracts_v2 import RunMode
from engine.orders.lifecycle_v2 import OrderExecutionState


class LiveExecutionStoreError(RuntimeError):
    pass


class LiveExecutionDuplicateError(LiveExecutionStoreError):
    pass


class LiveExecutionNotFoundError(LiveExecutionStoreError):
    pass


class LiveExecutionCapacityConflict(LiveExecutionStoreError):
    pass


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field)


def _aware(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


def _money(value: object, field: str, *, allow_zero: bool = False) -> Decimal:
    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be a finite decimal") from exc
    if not amount.is_finite() or amount < 0 or (amount == 0 and not allow_zero):
        comparator = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{field} must be {comparator}")
    return amount


@dataclass(frozen=True, slots=True)
class LiveExecutionRecord:
    client_order_id: str
    approved_order_ref: str
    run_mode: RunMode
    lifecycle_state: OrderExecutionState
    broker_order_identity: str | None
    submission_attempt_id: str
    created_at_utc: datetime
    updated_at_utc: datetime
    is_uncertain: bool
    adapter_id: str | None = None
    policy_ref: str | None = None
    audit_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "client_order_id", _text(self.client_order_id, "client_order_id"))
        object.__setattr__(self, "approved_order_ref", _text(self.approved_order_ref, "approved_order_ref"))
        if self.run_mode is not RunMode.LIVE:
            raise ValueError("LiveExecutionRecord requires RunMode.LIVE")
        if not isinstance(self.lifecycle_state, OrderExecutionState):
            raise TypeError("lifecycle_state must be OrderExecutionState")
        object.__setattr__(self, "broker_order_identity", _optional_text(self.broker_order_identity, "broker_order_identity"))
        object.__setattr__(self, "submission_attempt_id", _text(self.submission_attempt_id, "submission_attempt_id"))
        created = _aware(self.created_at_utc, "created_at_utc")
        updated = _aware(self.updated_at_utc, "updated_at_utc")
        if updated < created:
            raise ValueError("updated_at_utc cannot precede created_at_utc")
        if not isinstance(self.is_uncertain, bool):
            raise TypeError("is_uncertain must be bool")
        object.__setattr__(self, "adapter_id", _optional_text(self.adapter_id, "adapter_id"))
        object.__setattr__(self, "policy_ref", _optional_text(self.policy_ref, "policy_ref"))
        object.__setattr__(self, "audit_ref", _optional_text(self.audit_ref, "audit_ref"))


@dataclass(frozen=True, slots=True)
class LiveExecutionCapacityReservation:
    broker_account_ref: str
    client_order_id: str
    instrument_scope: str
    required_cash: Decimal
    funds_evidence_ref: str
    created_at_utc: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "broker_account_ref", _text(self.broker_account_ref, "broker_account_ref"))
        object.__setattr__(self, "client_order_id", _text(self.client_order_id, "client_order_id"))
        object.__setattr__(self, "instrument_scope", _text(self.instrument_scope, "instrument_scope"))
        object.__setattr__(self, "required_cash", _money(self.required_cash, "required_cash"))
        object.__setattr__(self, "funds_evidence_ref", _text(self.funds_evidence_ref, "funds_evidence_ref"))
        object.__setattr__(self, "created_at_utc", _aware(self.created_at_utc, "created_at_utc"))


class LiveExecutionStoreV2:
    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)
        if not self.database_path.is_file():
            raise FileNotFoundError(self.database_path)

    def _open(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.database_path), timeout=5.0)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def reserve(self, record: LiveExecutionRecord) -> LiveExecutionRecord:
        if not isinstance(record, LiveExecutionRecord):
            raise TypeError("record must be LiveExecutionRecord")
        try:
            with self._open() as connection:
                connection.execute(
                    """
                    INSERT INTO live_execution_records(
                        client_order_id, approved_order_ref, run_mode, lifecycle_state,
                        broker_order_identity, submission_attempt_id, created_at_utc,
                        updated_at_utc, is_uncertain, adapter_id, policy_ref, audit_ref
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.client_order_id,
                        record.approved_order_ref,
                        record.run_mode.value,
                        record.lifecycle_state.value,
                        record.broker_order_identity,
                        record.submission_attempt_id,
                        record.created_at_utc.isoformat(),
                        record.updated_at_utc.isoformat(),
                        int(record.is_uncertain),
                        record.adapter_id,
                        record.policy_ref,
                        record.audit_ref,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise LiveExecutionDuplicateError(f"duplicate client_order_id: {record.client_order_id}") from exc
        return record

    def get(self, client_order_id: str) -> LiveExecutionRecord | None:
        key = _text(client_order_id, "client_order_id")
        with self._open() as connection:
            row = connection.execute(
                """
                SELECT client_order_id, approved_order_ref, run_mode, lifecycle_state,
                       broker_order_identity, submission_attempt_id, created_at_utc,
                       updated_at_utc, is_uncertain, adapter_id, policy_ref, audit_ref
                FROM live_execution_records WHERE client_order_id = ?
                """,
                (key,),
            ).fetchone()
        return None if row is None else self._record_from_row(row)

    def transition(
        self,
        client_order_id: str,
        *,
        lifecycle_state: OrderExecutionState,
        broker_order_identity: str | None = None,
        is_uncertain: bool | None = None,
        audit_ref: str | None = None,
    ) -> LiveExecutionRecord:
        key = _text(client_order_id, "client_order_id")
        if not isinstance(lifecycle_state, OrderExecutionState):
            raise TypeError("lifecycle_state must be OrderExecutionState")
        current = self.get(key)
        if current is None:
            raise LiveExecutionNotFoundError(key)
        next_record = LiveExecutionRecord(
            client_order_id=current.client_order_id,
            approved_order_ref=current.approved_order_ref,
            run_mode=current.run_mode,
            lifecycle_state=lifecycle_state,
            broker_order_identity=(current.broker_order_identity if broker_order_identity is None else broker_order_identity),
            submission_attempt_id=current.submission_attempt_id,
            created_at_utc=current.created_at_utc,
            updated_at_utc=datetime.now(tz=current.updated_at_utc.tzinfo),
            is_uncertain=(current.is_uncertain if is_uncertain is None else is_uncertain),
            adapter_id=current.adapter_id,
            policy_ref=current.policy_ref,
            audit_ref=(current.audit_ref if audit_ref is None else audit_ref),
        )
        with self._open() as connection:
            connection.execute(
                """
                UPDATE live_execution_records
                SET lifecycle_state = ?, broker_order_identity = ?, updated_at_utc = ?,
                    is_uncertain = ?, audit_ref = ?
                WHERE client_order_id = ?
                """,
                (
                    next_record.lifecycle_state.value,
                    next_record.broker_order_identity,
                    next_record.updated_at_utc.isoformat(),
                    int(next_record.is_uncertain),
                    next_record.audit_ref,
                    key,
                ),
            )
        return next_record

    def list_uncertain(self) -> tuple[LiveExecutionRecord, ...]:
        with self._open() as connection:
            rows = connection.execute(
                """
                SELECT client_order_id, approved_order_ref, run_mode, lifecycle_state,
                       broker_order_identity, submission_attempt_id, created_at_utc,
                       updated_at_utc, is_uncertain, adapter_id, policy_ref, audit_ref
                FROM live_execution_records
                WHERE is_uncertain = 1
                ORDER BY updated_at_utc, client_order_id
                """
            ).fetchall()
        return tuple(self._record_from_row(row) for row in rows)

    def try_reserve_capacity(
        self,
        reservation: LiveExecutionCapacityReservation,
        *,
        available_cash: Decimal | int | str,
    ) -> bool:
        if not isinstance(reservation, LiveExecutionCapacityReservation):
            raise TypeError("reservation must be LiveExecutionCapacityReservation")
        cash = _money(available_cash, "available_cash", allow_zero=True)
        connection = self._open()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT broker_account_ref, instrument_scope, required_cash,
                       funds_evidence_ref, created_at_utc, status
                FROM live_execution_capacity_reservations
                WHERE client_order_id = ?
                """,
                (reservation.client_order_id,),
            ).fetchone()
            if existing is not None:
                same = (
                    str(existing[0]) == reservation.broker_account_ref
                    and str(existing[1]) == reservation.instrument_scope
                    and Decimal(str(existing[2])) == reservation.required_cash
                    and str(existing[3]) == reservation.funds_evidence_ref
                    and str(existing[4]) == reservation.created_at_utc.isoformat()
                    and str(existing[5]) == "ACTIVE"
                )
                if same:
                    connection.commit()
                    return True
                raise LiveExecutionCapacityConflict(
                    f"conflicting capacity reservation: {reservation.client_order_id}"
                )

            rows = connection.execute(
                """
                SELECT required_cash FROM live_execution_capacity_reservations
                WHERE broker_account_ref = ? AND status = 'ACTIVE'
                """,
                (reservation.broker_account_ref,),
            ).fetchall()
            reserved = sum((Decimal(str(row[0])) for row in rows), Decimal("0"))
            if reserved + reservation.required_cash > cash:
                connection.rollback()
                return False
            try:
                connection.execute(
                    """
                    INSERT INTO live_execution_capacity_reservations(
                        broker_account_ref, client_order_id, instrument_scope, required_cash,
                        funds_evidence_ref, created_at_utc, released_at_utc, release_reason, status
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, 'ACTIVE')
                    """,
                    (
                        reservation.broker_account_ref,
                        reservation.client_order_id,
                        reservation.instrument_scope,
                        str(reservation.required_cash),
                        reservation.funds_evidence_ref,
                        reservation.created_at_utc.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise LiveExecutionCapacityConflict(
                    f"capacity identity already reserved: {reservation.client_order_id}"
                ) from exc
            connection.commit()
            return True
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def active_reserved_cash(self, broker_account_ref: str) -> Decimal:
        account = _text(broker_account_ref, "broker_account_ref")
        with self._open() as connection:
            rows = connection.execute(
                "SELECT required_cash FROM live_execution_capacity_reservations WHERE broker_account_ref = ? AND status = 'ACTIVE'",
                (account,),
            ).fetchall()
        return sum((Decimal(str(row[0])) for row in rows), Decimal("0"))

    def list_active_capacity(self, broker_account_ref: str) -> tuple[LiveExecutionCapacityReservation, ...]:
        account = _text(broker_account_ref, "broker_account_ref")
        with self._open() as connection:
            rows = connection.execute(
                """
                SELECT broker_account_ref, client_order_id, instrument_scope, required_cash,
                       funds_evidence_ref, created_at_utc
                FROM live_execution_capacity_reservations
                WHERE broker_account_ref = ? AND status = 'ACTIVE'
                ORDER BY created_at_utc, client_order_id
                """,
                (account,),
            ).fetchall()
        return tuple(
            LiveExecutionCapacityReservation(
                broker_account_ref=str(row[0]),
                client_order_id=str(row[1]),
                instrument_scope=str(row[2]),
                required_cash=Decimal(str(row[3])),
                funds_evidence_ref=str(row[4]),
                created_at_utc=datetime.fromisoformat(str(row[5])),
            )
            for row in rows
        )

    def release_capacity(
        self,
        *,
        broker_account_ref: str,
        client_order_id: str,
        released_at_utc: datetime,
        reason: str,
    ) -> bool:
        account = _text(broker_account_ref, "broker_account_ref")
        client = _text(client_order_id, "client_order_id")
        released = _aware(released_at_utc, "released_at_utc")
        normalized_reason = _text(reason, "reason")
        with self._open() as connection:
            cursor = connection.execute(
                """
                UPDATE live_execution_capacity_reservations
                SET status = 'RELEASED', released_at_utc = ?, release_reason = ?
                WHERE broker_account_ref = ? AND client_order_id = ? AND status = 'ACTIVE'
                """,
                (released.isoformat(), normalized_reason, account, client),
            )
            return cursor.rowcount == 1

    def release_capacity_by_client(
        self,
        client_order_id: str,
        *,
        released_at_utc: datetime,
        reason: str,
    ) -> bool:
        client = _text(client_order_id, "client_order_id")
        released = _aware(released_at_utc, "released_at_utc")
        normalized_reason = _text(reason, "reason")
        with self._open() as connection:
            cursor = connection.execute(
                """
                UPDATE live_execution_capacity_reservations
                SET status = 'RELEASED', released_at_utc = ?, release_reason = ?
                WHERE client_order_id = ? AND status = 'ACTIVE'
                """,
                (released.isoformat(), normalized_reason, client),
            )
            return cursor.rowcount == 1

    @staticmethod
    def _record_from_row(row: tuple[object, ...]) -> LiveExecutionRecord:
        return LiveExecutionRecord(
            client_order_id=str(row[0]),
            approved_order_ref=str(row[1]),
            run_mode=RunMode(str(row[2])),
            lifecycle_state=OrderExecutionState(str(row[3])),
            broker_order_identity=(None if row[4] is None else str(row[4])),
            submission_attempt_id=str(row[5]),
            created_at_utc=datetime.fromisoformat(str(row[6])),
            updated_at_utc=datetime.fromisoformat(str(row[7])),
            is_uncertain=bool(row[8]),
            adapter_id=(None if row[9] is None else str(row[9])),
            policy_ref=(None if row[10] is None else str(row[10])),
            audit_ref=(None if row[11] is None else str(row[11])),
        )


__all__ = [
    "LiveExecutionCapacityConflict",
    "LiveExecutionCapacityReservation",
    "LiveExecutionDuplicateError",
    "LiveExecutionNotFoundError",
    "LiveExecutionRecord",
    "LiveExecutionStoreError",
    "LiveExecutionStoreV2",
]
