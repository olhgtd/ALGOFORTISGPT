from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import importlib
import sqlite3
import threading

import pytest


def _api():
    try:
        schema = importlib.import_module("engine.persistence.live_execution_schema_v9")
        store_mod = importlib.import_module("engine.persistence.live_execution_store_v2")
        migrations = importlib.import_module("engine.persistence.migrations")
        contracts = importlib.import_module("engine.orders.contracts_v2")
        lifecycle = importlib.import_module("engine.orders.lifecycle_v2")
    except ModuleNotFoundError as exc:
        pytest.fail(f"V9 Live execution journal is not implemented: {exc}")
    return schema, store_mod, migrations, contracts, lifecycle


def _create_v9_database(path, create_sql: tuple[str, ...]) -> None:
    connection = sqlite3.connect(str(path))
    try:
        for statement in create_sql:
            connection.execute(statement)
        connection.execute("PRAGMA user_version = 9")
        connection.commit()
    finally:
        connection.close()


def _record(store_mod, contracts, lifecycle, client_order_id: str = "co-nifty-1"):
    now = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
    return store_mod.LiveExecutionRecord(
        client_order_id=client_order_id,
        approved_order_ref="risk-ref-1",
        run_mode=contracts.RunMode.LIVE,
        lifecycle_state=lifecycle.OrderExecutionState.RISK_APPROVED,
        broker_order_identity=None,
        submission_attempt_id=f"attempt-{client_order_id}",
        created_at_utc=now,
        updated_at_utc=now,
        is_uncertain=False,
        adapter_id="angelone-v2",
        policy_ref="policy-v1",
        audit_ref="audit-v1",
    )


def _capacity(store_mod, *, client_order_id: str, instrument_scope: str, required_cash: str):
    return store_mod.LiveExecutionCapacityReservation(
        broker_account_ref="acct-1",
        client_order_id=client_order_id,
        instrument_scope=instrument_scope,
        required_cash=Decimal(required_cash),
        funds_evidence_ref="funds-snapshot-1",
        created_at_utc=datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc),
    )


def test_v9_migration_is_additive_and_reversible(tmp_path) -> None:
    schema, _, migrations, _, _ = _api()
    migration = migrations.LIVE_EXECUTION_V9_MIGRATION
    assert (migration.from_version, migration.to_version) == (8, 9)

    database = tmp_path / "migration.sqlite3"
    connection = sqlite3.connect(str(database))
    try:
        connection.execute("PRAGMA user_version = 8")
        for statement in migration.apply_sql:
            connection.execute(statement)
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "live_execution_records" in names
        assert "live_execution_capacity_reservations" in names
        for statement in migration.rollback_sql:
            connection.execute(statement)
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "live_execution_records" not in names
        assert "live_execution_capacity_reservations" not in names
    finally:
        connection.close()


def test_execution_record_persists_across_store_reopen(tmp_path) -> None:
    schema, store_mod, _, contracts, lifecycle = _api()
    database = tmp_path / "live.sqlite3"
    _create_v9_database(database, schema.LIVE_EXECUTION_CREATE_TABLES_SQL)
    record = _record(store_mod, contracts, lifecycle)

    store_mod.LiveExecutionStoreV2(database).reserve(record)
    reopened = store_mod.LiveExecutionStoreV2(database)
    assert reopened.get(record.client_order_id) == record


def test_duplicate_client_order_id_is_blocked_before_mutation(tmp_path) -> None:
    schema, store_mod, _, contracts, lifecycle = _api()
    database = tmp_path / "live.sqlite3"
    _create_v9_database(database, schema.LIVE_EXECUTION_CREATE_TABLES_SQL)
    store = store_mod.LiveExecutionStoreV2(database)
    record = _record(store_mod, contracts, lifecycle)
    store.reserve(record)

    with pytest.raises(store_mod.LiveExecutionDuplicateError):
        store.reserve(record)


def test_in_doubt_is_durable_and_queryable(tmp_path) -> None:
    schema, store_mod, _, contracts, lifecycle = _api()
    database = tmp_path / "live.sqlite3"
    _create_v9_database(database, schema.LIVE_EXECUTION_CREATE_TABLES_SQL)
    store = store_mod.LiveExecutionStoreV2(database)
    record = _record(store_mod, contracts, lifecycle)
    store.reserve(record)

    updated = store.transition(
        record.client_order_id,
        lifecycle_state=lifecycle.OrderExecutionState.IN_DOUBT,
        is_uncertain=True,
        audit_ref="audit-in-doubt",
    )
    assert updated.lifecycle_state is lifecycle.OrderExecutionState.IN_DOUBT
    assert updated.is_uncertain is True
    assert store.list_uncertain() == (updated,)


def test_v9_tables_store_no_secret_or_token_columns(tmp_path) -> None:
    schema, _, _, _, _ = _api()
    database = tmp_path / "live.sqlite3"
    _create_v9_database(database, schema.LIVE_EXECUTION_CREATE_TABLES_SQL)
    connection = sqlite3.connect(str(database))
    try:
        for table in ("live_execution_records", "live_execution_capacity_reservations"):
            columns = {str(row[1]).lower() for row in connection.execute(f"PRAGMA table_info({table})")}
            assert not any("secret" in name or "token" in name or "credential" in name for name in columns)
    finally:
        connection.close()


def test_capacity_reservation_is_idempotent_conflict_safe_and_cash_bounded(tmp_path) -> None:
    schema, store_mod, _, _, _ = _api()
    database = tmp_path / "live.sqlite3"
    _create_v9_database(database, schema.LIVE_EXECUTION_CREATE_TABLES_SQL)
    store = store_mod.LiveExecutionStoreV2(database)
    nifty = _capacity(store_mod, client_order_id="co-nifty", instrument_scope="NIFTY", required_cash="40")

    assert store.try_reserve_capacity(nifty, available_cash=Decimal("100")) is True
    assert store.try_reserve_capacity(nifty, available_cash=Decimal("100")) is True
    assert store.active_reserved_cash("acct-1") == Decimal("40")

    conflicting = _capacity(store_mod, client_order_id="co-nifty", instrument_scope="NIFTY", required_cash="41")
    with pytest.raises(store_mod.LiveExecutionCapacityConflict):
        store.try_reserve_capacity(conflicting, available_cash=Decimal("100"))

    banknifty = _capacity(store_mod, client_order_id="co-banknifty", instrument_scope="BANKNIFTY", required_cash="70")
    assert store.try_reserve_capacity(banknifty, available_cash=Decimal("100")) is False
    assert store.active_reserved_cash("acct-1") == Decimal("40")


def test_simultaneous_multi_instrument_reservations_cannot_oversubscribe_cash(tmp_path) -> None:
    schema, store_mod, _, _, _ = _api()
    database = tmp_path / "live.sqlite3"
    _create_v9_database(database, schema.LIVE_EXECUTION_CREATE_TABLES_SQL)
    requests = (
        _capacity(store_mod, client_order_id="co-nifty", instrument_scope="NIFTY", required_cash="70"),
        _capacity(store_mod, client_order_id="co-banknifty", instrument_scope="BANKNIFTY", required_cash="70"),
    )
    barrier = threading.Barrier(2)
    results: list[bool] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker(reservation) -> None:
        try:
            store = store_mod.LiveExecutionStoreV2(database)
            barrier.wait(timeout=5)
            result = store.try_reserve_capacity(reservation, available_cash=Decimal("100"))
            with lock:
                results.append(result)
        except BaseException as exc:  # pragma: no cover - asserted below
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(reservation,)) for reservation in requests]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert errors == []
    assert sorted(results) == [False, True]
    store = store_mod.LiveExecutionStoreV2(database)
    assert store.active_reserved_cash("acct-1") == Decimal("70")
    assert len(store.list_active_capacity("acct-1")) == 1
