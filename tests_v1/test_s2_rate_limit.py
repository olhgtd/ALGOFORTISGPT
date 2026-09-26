from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4


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

    def close(self) -> None:
        self._conn.close()


def _policy():
    from dashboard.backend.account_v2.rate_limit import RateLimitFlow, RateLimitPolicy, RateLimitRule

    return RateLimitPolicy(
        policy_id="TEST_ONLY/s2-rate",
        version="1",
        test_only=True,
        rules={flow: RateLimitRule(max_failures=2, cooldown_seconds=60) for flow in RateLimitFlow},
    )


def test_login_lockout_does_not_consume_recovery_flow(tmp_path: Path) -> None:
    from dashboard.backend.account_v2.rate_limit import DurableRateLimitService, RateLimitFlow
    from dashboard.backend.account_v2.v1_store_adapter import V1SecurityStoreAdapter

    store = FakeSecurityStore(tmp_path / "s.sqlite")
    user = uuid4()
    store.add_user(user)
    service = DurableRateLimitService(V1SecurityStoreAdapter(store), _policy())
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    service.record_failure(user_id=user, flow=RateLimitFlow.LOGIN, subject_key="acct", now=now)
    locked = service.record_failure(user_id=user, flow=RateLimitFlow.LOGIN, subject_key="acct", now=now)
    assert locked.locked is True
    assert service.is_locked(user_id=user, flow=RateLimitFlow.RECOVERY, subject_key="acct", now=now).locked is False


def test_rate_limit_state_survives_store_reopen(tmp_path: Path) -> None:
    from dashboard.backend.account_v2.rate_limit import DurableRateLimitService, RateLimitFlow
    from dashboard.backend.account_v2.v1_store_adapter import V1SecurityStoreAdapter

    db = tmp_path / "s.sqlite"
    user = uuid4()
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    store = FakeSecurityStore(db)
    store.add_user(user)
    service = DurableRateLimitService(V1SecurityStoreAdapter(store), _policy())
    service.record_failure(user_id=user, flow=RateLimitFlow.DEVICE_PROOF, subject_key="d", now=now)
    service.record_failure(user_id=user, flow=RateLimitFlow.DEVICE_PROOF, subject_key="d", now=now)
    store.close()

    reopened = FakeSecurityStore(db)
    service2 = DurableRateLimitService(V1SecurityStoreAdapter(reopened), _policy())
    assert service2.is_locked(user_id=user, flow=RateLimitFlow.DEVICE_PROOF, subject_key="d", now=now + timedelta(seconds=10)).locked is True
