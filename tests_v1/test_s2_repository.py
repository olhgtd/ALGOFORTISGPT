from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest


class FakeSecurityStore:
    def __init__(self, path: Path) -> None:
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY)")
        self._conn.commit()

    def add_user(self, user_id: UUID) -> None:
        self._conn.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (str(user_id),))
        self._conn.commit()

    def get_user(self, user_id: UUID | str):
        return self._conn.execute("SELECT * FROM users WHERE user_id = ?", (str(user_id),)).fetchone()

    @contextmanager
    def _transaction(self):
        cur = self._conn.cursor()
        try:
            cur.execute("BEGIN IMMEDIATE")
            yield cur
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cur.close()

    def close(self) -> None:
        self._conn.close()


def test_device_and_session_family_state_survive_reopen(tmp_path: Path) -> None:
    from dashboard.backend.account_v2.v1_store_adapter import V1SecurityStoreAdapter

    db = tmp_path / "security.sqlite3"
    user_id = uuid4()
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)

    store = FakeSecurityStore(db)
    store.add_user(user_id)
    adapter = V1SecurityStoreAdapter(store)
    adapter.register_device(
        user_id=user_id,
        device_id="device-1",
        public_key=b"public-key",
        fingerprint="fp-1",
        created_at=now,
    )
    adapter.save_session_family(
        user_id=user_id,
        family_id="family-1",
        device_id="device-1",
        current_refresh_hash="hash-1",
        state="ACTIVE",
        created_at=now,
        updated_at=now,
    )
    store.close()

    reopened = FakeSecurityStore(db)
    adapter2 = V1SecurityStoreAdapter(reopened)
    device = adapter2.get_device(user_id=user_id, device_id="device-1")
    family = adapter2.get_session_family(user_id=user_id, family_id="family-1")

    assert device is not None
    assert device.device_id == "device-1"
    assert device.public_key == b"public-key"
    assert family is not None
    assert family.family_id == "family-1"
    assert family.current_refresh_hash == "hash-1"
    reopened.close()


def test_cross_user_device_and_session_access_fails_closed(tmp_path: Path) -> None:
    from dashboard.backend.account_v2.repository import AccountAuthorityRecordUnavailable
    from dashboard.backend.account_v2.v1_store_adapter import V1SecurityStoreAdapter

    db = tmp_path / "security.sqlite3"
    user_a = uuid4()
    user_b = uuid4()
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    store = FakeSecurityStore(db)
    store.add_user(user_a)
    store.add_user(user_b)
    adapter = V1SecurityStoreAdapter(store)
    adapter.register_device(user_id=user_a, device_id="a-device", public_key=b"pk", fingerprint="a-fp", created_at=now)
    adapter.save_session_family(user_id=user_a, family_id="a-family", device_id="a-device", current_refresh_hash="h", state="ACTIVE", created_at=now, updated_at=now)

    assert adapter.get_device(user_id=user_b, device_id="a-device") is None
    assert adapter.get_session_family(user_id=user_b, family_id="a-family") is None
    assert adapter.list_devices(user_id=user_b) == ()

    with pytest.raises(AccountAuthorityRecordUnavailable):
        adapter.revoke_device(user_id=user_b, device_id="a-device", revoked_at=now)
    with pytest.raises(AccountAuthorityRecordUnavailable):
        adapter.revoke_session_family(user_id=user_b, family_id="a-family", revoked_at=now)

    assert adapter.get_device(user_id=user_a, device_id="a-device").status == "ACTIVE"
    assert adapter.get_session_family(user_id=user_a, family_id="a-family").state == "ACTIVE"
    store.close()


def test_unknown_user_cannot_create_s2_owned_state(tmp_path: Path) -> None:
    from dashboard.backend.account_v2.repository import AccountAuthorityRecordUnavailable
    from dashboard.backend.account_v2.v1_store_adapter import V1SecurityStoreAdapter

    db = tmp_path / "security.sqlite3"
    store = FakeSecurityStore(db)
    adapter = V1SecurityStoreAdapter(store)
    with pytest.raises(AccountAuthorityRecordUnavailable):
        adapter.register_device(user_id=uuid4(), device_id="ghost", public_key=b"pk", fingerprint="ghost", created_at=datetime(2026, 9, 26, tzinfo=timezone.utc))
    store.close()
