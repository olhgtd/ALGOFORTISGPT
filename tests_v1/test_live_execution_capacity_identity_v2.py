from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import sqlite3

import pytest

from engine.persistence.live_execution_schema_v9 import LIVE_EXECUTION_CREATE_TABLES_SQL
from engine.persistence.live_execution_store_v2 import (
    LiveExecutionCapacityConflict,
    LiveExecutionCapacityReservation,
    LiveExecutionStoreV2,
)


def _database(path) -> None:
    connection = sqlite3.connect(str(path))
    try:
        for statement in LIVE_EXECUTION_CREATE_TABLES_SQL:
            connection.execute(statement)
        connection.execute("PRAGMA user_version = 9")
        connection.commit()
    finally:
        connection.close()


def _reservation(account: str) -> LiveExecutionCapacityReservation:
    return LiveExecutionCapacityReservation(
        broker_account_ref=account,
        client_order_id="af2_co_global-identity",
        instrument_scope="NIFTY",
        required_cash=Decimal("25"),
        funds_evidence_ref=f"funds-{account}",
        created_at_utc=datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc),
    )


def test_client_order_identity_cannot_be_reserved_for_two_accounts(tmp_path) -> None:
    database = tmp_path / "live.sqlite3"
    _database(database)
    store = LiveExecutionStoreV2(database)

    assert store.try_reserve_capacity(_reservation("acct-a"), available_cash=Decimal("100")) is True
    with pytest.raises(LiveExecutionCapacityConflict):
        store.try_reserve_capacity(_reservation("acct-b"), available_cash=Decimal("100"))


def test_capacity_can_be_released_by_global_client_identity(tmp_path) -> None:
    database = tmp_path / "live.sqlite3"
    _database(database)
    store = LiveExecutionStoreV2(database)
    reservation = _reservation("acct-a")
    assert store.try_reserve_capacity(reservation, available_cash=Decimal("100")) is True

    released = store.release_capacity_by_client(
        reservation.client_order_id,
        released_at_utc=datetime(2026, 9, 30, 12, 1, tzinfo=timezone.utc),
        reason="pre_submit_abort",
    )

    assert released is True
    assert store.active_reserved_cash("acct-a") == Decimal("0")
