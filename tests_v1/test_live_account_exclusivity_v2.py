from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
import threading

import pytest

from engine.persistence.live_execution_schema_v9 import LIVE_EXECUTION_CREATE_TABLES_SQL

try:
    from engine.live.account_exclusivity_v2 import (
        LiveAccountExclusivityConflict,
        LiveAccountExclusivityV2,
        LiveAccountOwner,
    )
    from engine.persistence.live_account_exclusivity_store_v2 import (
        LiveAccountExclusivityStoreCorrupt,
        LiveAccountExclusivityStoreV2,
    )
except ModuleNotFoundError as exc:
    pytest.fail(f"Live account exclusivity is not implemented: {exc}", pytrace=False)


def _database(path) -> None:
    connection = sqlite3.connect(str(path))
    try:
        for statement in LIVE_EXECUTION_CREATE_TABLES_SQL:
            connection.execute(statement)
        connection.execute("PRAGMA user_version = 9")
        connection.commit()
    finally:
        connection.close()


def _owner(*, device: str = "device-a", session: str = "session-a", nonce: str = "nonce-a") -> LiveAccountOwner:
    return LiveAccountOwner(
        broker_id="ANGELONE",
        broker_account_ref="acct-1",
        device_id=device,
        session_family_id=session,
        ownership_nonce=nonce,
        acquired_at_utc=datetime(2026, 9, 30, 9, 15, tzinfo=timezone.utc),
    )


def test_same_owner_is_idempotent_and_verifiable(tmp_path) -> None:
    database = tmp_path / "live.sqlite3"
    _database(database)
    service = LiveAccountExclusivityV2(LiveAccountExclusivityStoreV2(database))
    owner = _owner()

    assert service.acquire(owner) == owner
    assert service.acquire(owner) == owner
    assert service.verify(owner) is True


def test_second_device_or_session_cannot_take_over_same_broker_account(tmp_path) -> None:
    database = tmp_path / "live.sqlite3"
    _database(database)
    service = LiveAccountExclusivityV2(LiveAccountExclusivityStoreV2(database))
    service.acquire(_owner())

    with pytest.raises(LiveAccountExclusivityConflict):
        service.acquire(_owner(device="device-b", nonce="nonce-b"))
    with pytest.raises(LiveAccountExclusivityConflict):
        service.acquire(_owner(session="session-b", nonce="nonce-c"))


def test_concurrent_acquire_allows_exactly_one_owner(tmp_path) -> None:
    database = tmp_path / "live.sqlite3"
    _database(database)
    candidates = (_owner(), _owner(device="device-b", session="session-b", nonce="nonce-b"))
    barrier = threading.Barrier(2)
    winners: list[LiveAccountOwner] = []
    conflicts: list[BaseException] = []
    lock = threading.Lock()

    def worker(candidate: LiveAccountOwner) -> None:
        service = LiveAccountExclusivityV2(LiveAccountExclusivityStoreV2(database))
        barrier.wait(timeout=5)
        try:
            result = service.acquire(candidate)
            with lock:
                winners.append(result)
        except BaseException as exc:
            with lock:
                conflicts.append(exc)

    threads = [threading.Thread(target=worker, args=(candidate,)) for candidate in candidates]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert len(winners) == 1
    assert len(conflicts) == 1
    assert isinstance(conflicts[0], LiveAccountExclusivityConflict)


def test_restart_clears_durable_ownership_and_never_auto_restores(tmp_path) -> None:
    database = tmp_path / "live.sqlite3"
    _database(database)
    store = LiveAccountExclusivityStoreV2(database)
    service = LiveAccountExclusivityV2(store)
    original = _owner()
    service.acquire(original)

    service.restore_after_restart(broker_id="ANGELONE", broker_account_ref="acct-1")

    assert service.verify(original) is False
    fresh = _owner(device="device-b", session="session-b", nonce="fresh-nonce")
    assert service.acquire(fresh) == fresh


def test_release_requires_matching_owner_nonce(tmp_path) -> None:
    database = tmp_path / "live.sqlite3"
    _database(database)
    service = LiveAccountExclusivityV2(LiveAccountExclusivityStoreV2(database))
    original = _owner()
    service.acquire(original)

    with pytest.raises(LiveAccountExclusivityConflict):
        service.release(_owner(nonce="wrong-nonce"))
    service.release(original)
    assert service.verify(original) is False


def test_corrupt_durable_owner_fails_closed(tmp_path) -> None:
    database = tmp_path / "live.sqlite3"
    _database(database)
    connection = sqlite3.connect(str(database))
    try:
        connection.execute(
            """
            INSERT INTO live_account_exclusivity(
                broker_id, broker_account_ref, device_id, session_family_id,
                ownership_nonce, acquired_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("ANGELONE", "acct-1", "", "session-a", "nonce-a", "not-a-datetime"),
        )
        connection.commit()
    finally:
        connection.close()

    store = LiveAccountExclusivityStoreV2(database)
    with pytest.raises(LiveAccountExclusivityStoreCorrupt):
        store.load("ANGELONE", "acct-1")
