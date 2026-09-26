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

    def get_user(self, user_id):
        return self._conn.execute("SELECT * FROM users WHERE user_id = ?", (str(user_id),)).fetchone()

    @contextmanager
    def _transaction(self):
        cur = self._conn.cursor()
        cur.execute("BEGIN IMMEDIATE")
        try:
            yield cur
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cur.close()

    def close(self):
        self._conn.close()


def _setup(tmp_path: Path):
    from dashboard.backend.account_v2.v1_store_adapter import V1SecurityStoreAdapter
    from dashboard.backend.account_v2.session_service import DurableSessionService

    store = FakeSecurityStore(tmp_path / "security.sqlite3")
    user = uuid4()
    store.add_user(user)
    repo = V1SecurityStoreAdapter(store)
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    repo.register_device(user_id=user, device_id="device-1", public_key=b"pk", fingerprint="fp", created_at=now)
    return store, repo, DurableSessionService(repo), user, now


def test_normal_rotation_consumes_old_token_and_persists_new_hash(tmp_path: Path) -> None:
    store, repo, service, user, now = _setup(tmp_path)
    issued = service.create_session(user_id=user, device_id="device-1", now=now)
    rotated = service.rotate_refresh_token(user_id=user, device_id="device-1", family_id=issued.family_id, presented_refresh_token=issued.refresh_token, now=now)
    family = repo.get_session_family(user_id=user, family_id=issued.family_id)
    assert family is not None
    assert family.current_refresh_hash == service.hash_token(rotated.refresh_token)
    assert repo.is_consumed_refresh_hash(user_id=user, family_id=issued.family_id, token_hash=service.hash_token(issued.refresh_token))
    assert rotated.access_expires_at > now
    store.close()


def test_replaying_consumed_refresh_token_revokes_family(tmp_path: Path) -> None:
    from dashboard.backend.account_v2.session_service import RefreshTokenReuseDetected

    store, repo, service, user, now = _setup(tmp_path)
    issued = service.create_session(user_id=user, device_id="device-1", now=now)
    service.rotate_refresh_token(user_id=user, device_id="device-1", family_id=issued.family_id, presented_refresh_token=issued.refresh_token, now=now)
    with pytest.raises(RefreshTokenReuseDetected):
        service.rotate_refresh_token(user_id=user, device_id="device-1", family_id=issued.family_id, presented_refresh_token=issued.refresh_token, now=now)
    assert repo.get_session_family(user_id=user, family_id=issued.family_id).state == "REVOKED"
    store.close()


def test_repository_atomically_revokes_if_consumed_token_reaches_rotate_after_precheck(tmp_path: Path) -> None:
    from dashboard.backend.account_v2.repository import RefreshTokenReplayDetected

    store, repo, service, user, now = _setup(tmp_path)
    issued = service.create_session(user_id=user, device_id="device-1", now=now)
    service.rotate_refresh_token(user_id=user, device_id="device-1", family_id=issued.family_id, presented_refresh_token=issued.refresh_token, now=now)
    consumed = service.hash_token(issued.refresh_token)

    with pytest.raises(RefreshTokenReplayDetected):
        repo.rotate_refresh_hash(
            user_id=user,
            family_id=issued.family_id,
            expected_current_hash=consumed,
            new_current_hash="unused-new-hash",
            consumed_hash=consumed,
            updated_at=now,
            idle_expires_at=now,
        )

    assert repo.get_session_family(user_id=user, family_id=issued.family_id).state == "REVOKED"
    store.close()


def test_consumed_refresh_history_survives_store_reopen(tmp_path: Path) -> None:
    from dashboard.backend.account_v2.session_service import DurableSessionService, RefreshTokenReuseDetected
    from dashboard.backend.account_v2.v1_store_adapter import V1SecurityStoreAdapter

    db = tmp_path / "security.sqlite3"
    store, repo, service, user, now = _setup(tmp_path)
    issued = service.create_session(user_id=user, device_id="device-1", now=now)
    service.rotate_refresh_token(user_id=user, device_id="device-1", family_id=issued.family_id, presented_refresh_token=issued.refresh_token, now=now)
    store.close()

    reopened = FakeSecurityStore(db)
    repo2 = V1SecurityStoreAdapter(reopened)
    service2 = DurableSessionService(repo2)
    with pytest.raises(RefreshTokenReuseDetected):
        service2.rotate_refresh_token(user_id=user, device_id="device-1", family_id=issued.family_id, presented_refresh_token=issued.refresh_token, now=now)
    assert repo2.get_session_family(user_id=user, family_id=issued.family_id).state == "REVOKED"
    reopened.close()


def test_revoked_or_foreign_device_cannot_rotate(tmp_path: Path) -> None:
    from dashboard.backend.account_v2.session_service import SessionUnavailable

    store, repo, service, user, now = _setup(tmp_path)
    issued = service.create_session(user_id=user, device_id="device-1", now=now)
    repo.revoke_device(user_id=user, device_id="device-1", revoked_at=now)
    with pytest.raises(SessionUnavailable):
        service.rotate_refresh_token(user_id=user, device_id="device-1", family_id=issued.family_id, presented_refresh_token=issued.refresh_token, now=now)

    other = uuid4()
    store.add_user(other)
    with pytest.raises(SessionUnavailable):
        service.rotate_refresh_token(user_id=other, device_id="device-1", family_id=issued.family_id, presented_refresh_token=issued.refresh_token, now=now)
    store.close()


def test_plaintext_refresh_tokens_are_never_persisted(tmp_path: Path) -> None:
    store, repo, service, user, now = _setup(tmp_path)
    issued = service.create_session(user_id=user, device_id="device-1", now=now)
    family = repo.get_session_family(user_id=user, family_id=issued.family_id)
    values = [family.current_refresh_hash]
    rows = store._conn.execute("SELECT token_hash FROM s2_consumed_refresh_tokens").fetchall()
    values.extend(row[0] for row in rows)
    assert issued.refresh_token not in values
    assert family.current_refresh_hash == service.hash_token(issued.refresh_token)
    store.close()
