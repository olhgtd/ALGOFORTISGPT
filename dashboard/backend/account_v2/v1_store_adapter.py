"""Additive S2 state adapter over the existing durable V1 security database."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from .repository import (
    AccountAuthorityRecordUnavailable,
    DeviceRecord,
    SessionFamilyPolicyRecord,
    SessionFamilyRecord,
)


S2_ACCOUNT_SCHEMA_VERSION = 1


class V1SecurityStoreAdapter:
    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._store._transaction() as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS s2_account_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            row = cur.execute("SELECT value FROM s2_account_metadata WHERE key = 'schema_version'").fetchone()
            if row is None:
                cur.execute("INSERT INTO s2_account_metadata(key, value) VALUES ('schema_version', ?)", (str(S2_ACCOUNT_SCHEMA_VERSION),))
            elif str(row[0]) != str(S2_ACCOUNT_SCHEMA_VERSION):
                raise RuntimeError("incompatible S2 account schema")
            cur.execute("""CREATE TABLE IF NOT EXISTS s2_devices (
                device_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                public_key BLOB NOT NULL,
                fingerprint TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                revoked_at_utc TEXT
            )""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_s2_devices_user ON s2_devices(user_id)")
            cur.execute("""CREATE TABLE IF NOT EXISTS s2_session_families (
                family_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                current_refresh_hash TEXT NOT NULL,
                state TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                revoked_at_utc TEXT
            )""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_s2_families_user ON s2_session_families(user_id)")
            cur.execute("""CREATE TABLE IF NOT EXISTS s2_session_family_policy (
                family_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                absolute_expires_at_utc TEXT NOT NULL,
                idle_expires_at_utc TEXT NOT NULL
            )""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_s2_family_policy_user ON s2_session_family_policy(user_id)")
            cur.execute("""CREATE TABLE IF NOT EXISTS s2_consumed_refresh_tokens (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                family_id TEXT NOT NULL,
                consumed_at_utc TEXT NOT NULL
            )""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_s2_consumed_family ON s2_consumed_refresh_tokens(user_id, family_id)")

    def _require_user(self, user_id: UUID) -> None:
        if self._store.get_user(user_id) is None:
            raise AccountAuthorityRecordUnavailable("account-owned state unavailable")

    @staticmethod
    def _device(row: Any) -> DeviceRecord:
        return DeviceRecord(
            user_id=UUID(str(row["user_id"])),
            device_id=str(row["device_id"]),
            public_key=bytes(row["public_key"]),
            fingerprint=str(row["fingerprint"]),
            status=str(row["status"]),
            created_at=datetime.fromisoformat(str(row["created_at_utc"])),
            revoked_at=datetime.fromisoformat(str(row["revoked_at_utc"])) if row["revoked_at_utc"] else None,
        )

    @staticmethod
    def _family(row: Any) -> SessionFamilyRecord:
        return SessionFamilyRecord(
            user_id=UUID(str(row["user_id"])),
            family_id=str(row["family_id"]),
            device_id=str(row["device_id"]),
            current_refresh_hash=str(row["current_refresh_hash"]),
            state=str(row["state"]),
            created_at=datetime.fromisoformat(str(row["created_at_utc"])),
            updated_at=datetime.fromisoformat(str(row["updated_at_utc"])),
            revoked_at=datetime.fromisoformat(str(row["revoked_at_utc"])) if row["revoked_at_utc"] else None,
        )

    @staticmethod
    def _family_policy(row: Any) -> SessionFamilyPolicyRecord:
        return SessionFamilyPolicyRecord(
            user_id=UUID(str(row["user_id"])),
            family_id=str(row["family_id"]),
            absolute_expires_at=datetime.fromisoformat(str(row["absolute_expires_at_utc"])),
            idle_expires_at=datetime.fromisoformat(str(row["idle_expires_at_utc"])),
        )

    def list_devices(self, *, user_id: UUID) -> tuple[DeviceRecord, ...]:
        self._require_user(user_id)
        rows = self._store._conn.execute(
            "SELECT * FROM s2_devices WHERE user_id = ? ORDER BY created_at_utc, device_id",
            (str(user_id),),
        ).fetchall()
        return tuple(self._device(row) for row in rows)

    def get_device(self, *, user_id: UUID, device_id: str) -> DeviceRecord | None:
        self._require_user(user_id)
        row = self._store._conn.execute(
            "SELECT * FROM s2_devices WHERE user_id = ? AND device_id = ?",
            (str(user_id), device_id),
        ).fetchone()
        return self._device(row) if row is not None else None

    def register_device(self, *, user_id: UUID, device_id: str, public_key: bytes, fingerprint: str, created_at: datetime) -> DeviceRecord:
        self._require_user(user_id)
        with self._store._transaction() as cur:
            existing = cur.execute("SELECT user_id FROM s2_devices WHERE device_id = ?", (device_id,)).fetchone()
            if existing is not None:
                raise AccountAuthorityRecordUnavailable("account-owned state unavailable")
            cur.execute(
                "INSERT INTO s2_devices(device_id, user_id, public_key, fingerprint, status, created_at_utc, revoked_at_utc) VALUES (?, ?, ?, ?, 'ACTIVE', ?, NULL)",
                (device_id, str(user_id), public_key, fingerprint, created_at.isoformat()),
            )
        record = self.get_device(user_id=user_id, device_id=device_id)
        assert record is not None
        return record

    def revoke_device(self, *, user_id: UUID, device_id: str, revoked_at: datetime) -> None:
        self._require_user(user_id)
        with self._store._transaction() as cur:
            row = cur.execute("SELECT 1 FROM s2_devices WHERE user_id = ? AND device_id = ?", (str(user_id), device_id)).fetchone()
            if row is None:
                raise AccountAuthorityRecordUnavailable("account-owned state unavailable")
            cur.execute("UPDATE s2_devices SET status = 'REVOKED', revoked_at_utc = ? WHERE user_id = ? AND device_id = ?", (revoked_at.isoformat(), str(user_id), device_id))
            cur.execute("UPDATE s2_session_families SET state = 'REVOKED', revoked_at_utc = ?, updated_at_utc = ? WHERE user_id = ? AND device_id = ? AND revoked_at_utc IS NULL", (revoked_at.isoformat(), revoked_at.isoformat(), str(user_id), device_id))

    def get_session_family(self, *, user_id: UUID, family_id: str) -> SessionFamilyRecord | None:
        self._require_user(user_id)
        row = self._store._conn.execute(
            "SELECT * FROM s2_session_families WHERE user_id = ? AND family_id = ?",
            (str(user_id), family_id),
        ).fetchone()
        return self._family(row) if row is not None else None

    def save_session_family(self, *, user_id: UUID, family_id: str, device_id: str, current_refresh_hash: str, state: str, created_at: datetime, updated_at: datetime) -> SessionFamilyRecord:
        self._require_user(user_id)
        device = self.get_device(user_id=user_id, device_id=device_id)
        if device is None or device.status != "ACTIVE":
            raise AccountAuthorityRecordUnavailable("account-owned state unavailable")
        with self._store._transaction() as cur:
            existing = cur.execute("SELECT user_id FROM s2_session_families WHERE family_id = ?", (family_id,)).fetchone()
            if existing is not None:
                raise AccountAuthorityRecordUnavailable("account-owned state unavailable")
            cur.execute(
                "INSERT INTO s2_session_families(family_id, user_id, device_id, current_refresh_hash, state, created_at_utc, updated_at_utc, revoked_at_utc) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                (family_id, str(user_id), device_id, current_refresh_hash, state, created_at.isoformat(), updated_at.isoformat()),
            )
        record = self.get_session_family(user_id=user_id, family_id=family_id)
        assert record is not None
        return record

    def revoke_session_family(self, *, user_id: UUID, family_id: str, revoked_at: datetime) -> None:
        self._require_user(user_id)
        with self._store._transaction() as cur:
            row = cur.execute("SELECT 1 FROM s2_session_families WHERE user_id = ? AND family_id = ?", (str(user_id), family_id)).fetchone()
            if row is None:
                raise AccountAuthorityRecordUnavailable("account-owned state unavailable")
            cur.execute("UPDATE s2_session_families SET state = 'REVOKED', revoked_at_utc = ?, updated_at_utc = ? WHERE user_id = ? AND family_id = ?", (revoked_at.isoformat(), revoked_at.isoformat(), str(user_id), family_id))

    def save_session_policy(self, *, user_id: UUID, family_id: str, absolute_expires_at: datetime, idle_expires_at: datetime) -> SessionFamilyPolicyRecord:
        self._require_user(user_id)
        family = self.get_session_family(user_id=user_id, family_id=family_id)
        if family is None:
            raise AccountAuthorityRecordUnavailable("account-owned state unavailable")
        with self._store._transaction() as cur:
            cur.execute(
                "INSERT INTO s2_session_family_policy(family_id, user_id, absolute_expires_at_utc, idle_expires_at_utc) VALUES (?, ?, ?, ?)",
                (family_id, str(user_id), absolute_expires_at.isoformat(), idle_expires_at.isoformat()),
            )
        record = self.get_session_policy(user_id=user_id, family_id=family_id)
        assert record is not None
        return record

    def get_session_policy(self, *, user_id: UUID, family_id: str) -> SessionFamilyPolicyRecord | None:
        self._require_user(user_id)
        row = self._store._conn.execute(
            "SELECT * FROM s2_session_family_policy WHERE user_id = ? AND family_id = ?",
            (str(user_id), family_id),
        ).fetchone()
        return self._family_policy(row) if row is not None else None

    def is_consumed_refresh_hash(self, *, user_id: UUID, family_id: str, token_hash: str) -> bool:
        self._require_user(user_id)
        return self._store._conn.execute(
            "SELECT 1 FROM s2_consumed_refresh_tokens WHERE user_id = ? AND family_id = ? AND token_hash = ?",
            (str(user_id), family_id, token_hash),
        ).fetchone() is not None

    def rotate_refresh_hash(self, *, user_id: UUID, family_id: str, expected_current_hash: str, new_current_hash: str, consumed_hash: str, updated_at: datetime, idle_expires_at: datetime) -> None:
        self._require_user(user_id)
        with self._store._transaction() as cur:
            row = cur.execute(
                "SELECT current_refresh_hash, state FROM s2_session_families WHERE user_id = ? AND family_id = ?",
                (str(user_id), family_id),
            ).fetchone()
            if row is None or row["state"] != "ACTIVE" or row["current_refresh_hash"] != expected_current_hash:
                raise AccountAuthorityRecordUnavailable("account-owned state unavailable")
            cur.execute(
                "INSERT INTO s2_consumed_refresh_tokens(token_hash, user_id, family_id, consumed_at_utc) VALUES (?, ?, ?, ?)",
                (consumed_hash, str(user_id), family_id, updated_at.isoformat()),
            )
            cur.execute(
                "UPDATE s2_session_families SET current_refresh_hash = ?, updated_at_utc = ? WHERE user_id = ? AND family_id = ?",
                (new_current_hash, updated_at.isoformat(), str(user_id), family_id),
            )
            cur.execute(
                "UPDATE s2_session_family_policy SET idle_expires_at_utc = ? WHERE user_id = ? AND family_id = ?",
                (idle_expires_at.isoformat(), str(user_id), family_id),
            )
