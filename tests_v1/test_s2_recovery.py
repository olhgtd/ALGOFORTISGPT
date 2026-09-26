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
        self._conn.execute("INSERT OR IGNORE INTO users VALUES (?)", (str(user_id),))
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


class AcceptProof:
    def verify(self, *, user_id, proof):
        return proof == "ok"


class FailingAudit:
    def record_required_intent(self, **kwargs):
        raise RuntimeError("audit down")


class MemoryAudit:
    def __init__(self):
        self.events = []

    def record_required_intent(self, **kwargs):
        self.events.append(kwargs)
        return "audit-1"


def _setup(tmp_path: Path):
    from dashboard.backend.account_v2.v1_store_adapter import V1SecurityStoreAdapter

    store = FakeSecurityStore(tmp_path / "s.sqlite")
    user_a, user_b = uuid4(), uuid4()
    store.add_user(user_a)
    store.add_user(user_b)
    repo = V1SecurityStoreAdapter(store)
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    for user, prefix in ((user_a, "a"), (user_b, "b")):
        repo.register_device(user_id=user, device_id=f"{prefix}-d1", public_key=b"pk", fingerprint=f"{prefix}-fp", created_at=now)
        repo.save_session_family(user_id=user, family_id=f"{prefix}-f1", device_id=f"{prefix}-d1", current_refresh_hash=f"{prefix}-h", state="ACTIVE", created_at=now, updated_at=now)
    return store, repo, user_a, user_b, now


def test_high_assurance_recovery_revokes_all_target_sessions_and_devices_only(tmp_path: Path) -> None:
    from dashboard.backend.account_v2.recovery_service import HighAssuranceRecoveryService

    _, repo, user_a, user_b, now = _setup(tmp_path)
    service = HighAssuranceRecoveryService(repo, AcceptProof(), MemoryAudit())
    result = service.recover(principal_user_id=user_a, target_user_id=user_a, proof="ok", now=now)
    assert result.reenrollment_required is True
    assert all(device.status == "REVOKED" for device in repo.list_devices(user_id=user_a))
    assert all(family.state == "REVOKED" for family in repo.list_session_families(user_id=user_a))
    assert all(device.status == "ACTIVE" for device in repo.list_devices(user_id=user_b))
    assert all(family.state == "ACTIVE" for family in repo.list_session_families(user_id=user_b))


def test_cross_user_recovery_is_denied(tmp_path: Path) -> None:
    from dashboard.backend.account_v2.recovery_service import HighAssuranceRecoveryService, RecoveryDenied

    _, repo, user_a, user_b, now = _setup(tmp_path)
    service = HighAssuranceRecoveryService(repo, AcceptProof(), MemoryAudit())
    with pytest.raises(RecoveryDenied):
        service.recover(principal_user_id=user_a, target_user_id=user_b, proof="ok", now=now)
    assert all(device.status == "ACTIVE" for device in repo.list_devices(user_id=user_b))


def test_required_audit_failure_prevents_recovery_mutation(tmp_path: Path) -> None:
    from dashboard.backend.account_v2.recovery_service import HighAssuranceRecoveryService

    _, repo, user_a, _, now = _setup(tmp_path)
    service = HighAssuranceRecoveryService(repo, AcceptProof(), FailingAudit())
    with pytest.raises(RuntimeError):
        service.recover(principal_user_id=user_a, target_user_id=user_a, proof="ok", now=now)
    assert all(device.status == "ACTIVE" for device in repo.list_devices(user_id=user_a))
    assert all(family.state == "ACTIVE" for family in repo.list_session_families(user_id=user_a))
