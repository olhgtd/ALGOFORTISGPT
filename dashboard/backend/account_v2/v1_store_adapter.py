"""Additive S2 state adapter over the existing durable V1 security database."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from .repository import (
    AccountAuthorityRecordUnavailable,
    AccountStateRecord,
    DeviceProofChallengeRecord,
    DeviceQuotaAuthorityExceeded,
    DeviceRecord,
    RateLimitStateRecord,
    RefreshTokenReplayDetected,
    SessionFamilyPolicyRecord,
    SessionFamilyRecord,
)


S2_ACCOUNT_SCHEMA_VERSION = 2


class V1SecurityStoreAdapter:
    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._store._transaction() as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS s2_account_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            row = cur.execute("SELECT value FROM s2_account_metadata WHERE key = 'schema_version'").fetchone()
            if row is None:
                previous_version = None
                cur.execute("INSERT INTO s2_account_metadata(key, value) VALUES ('schema_version', ?)", (str(S2_ACCOUNT_SCHEMA_VERSION),))
            else:
                previous_version = int(row[0])
                if previous_version not in (1, S2_ACCOUNT_SCHEMA_VERSION):
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
            cur.execute("""CREATE TABLE IF NOT EXISTS s2_device_challenges (
                challenge_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                purpose TEXT NOT NULL,
                issued_at_utc TEXT NOT NULL,
                expires_at_utc TEXT NOT NULL,
                consumed_at_utc TEXT
            )""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_s2_device_challenge_scope ON s2_device_challenges(user_id, device_id, purpose)")
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
            cur.execute("""CREATE TABLE IF NOT EXISTS s2_rate_limit_state (
                user_id TEXT NOT NULL,
                flow TEXT NOT NULL,
                subject_key TEXT NOT NULL,
                failure_count INTEGER NOT NULL,
                locked_until_utc TEXT,
                updated_at_utc TEXT NOT NULL,
                PRIMARY KEY (user_id, flow, subject_key)
            )""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_s2_rate_limit_user ON s2_rate_limit_state(user_id)")
            if previous_version == 1:
                cur.execute(
                    "UPDATE s2_account_metadata SET value = ? WHERE key = 'schema_version'",
                    (str(S2_ACCOUNT_SCHEMA_VERSION),),
                )

    def _require_user(self, user_id: UUID) -> None:
        if self._store.get_user(user_id) is None:
            raise AccountAuthorityRecordUnavailable("account-owned state unavailable")

    @staticmethod
    def _account(row: Any) -> AccountStateRecord:
        keys = set(row.keys()) if hasattr(row, "keys") else set()

        def value(name: str, default: str) -> str:
            if name not in keys or row[name] is None:
                return default
            return str(row[name])

        return AccountStateRecord(
            user_id=UUID(str(row["user_id"])),
            lifecycle=value("lifecycle", "UNKNOWN"),
            account_status=value("account_status", "UNKNOWN"),
            activation_status=value("activation_status", "UNKNOWN"),
            security_state=value("security_state", "UNKNOWN"),
        )

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
    def _challenge(row: Any) -> DeviceProofChallengeRecord:
        return DeviceProofChallengeRecord(
            user_id=UUID(str(row["user_id"])),
            device_id=str(row["device_id"]),
            purpose=str(row["purpose"]),
            challenge_hash=str(row["challenge_hash"]),
            issued_at=datetime.fromisoformat(str(row["issued_at_utc"])),
            expires_at=datetime.fromisoformat(str(row["expires_at_utc"])),
            consumed_at=datetime.fromisoformat(str(row["consumed_at_utc"])) if row["consumed_at_utc"] else None,
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

    @staticmethod
    def _rate_limit(row: Any) -> RateLimitStateRecord:
        return RateLimitStateRecord(
            user_id=UUID(str(row["user_id"])),
            flow=str(row["flow"]),
            subject_key=str(row["subject_key"]),
            failure_count=int(row["failure_count"]),
            locked_until=datetime.fromisoformat(str(row["locked_until_utc"])) if row["locked_until_utc"] else None,
            updated_at=datetime.fromisoformat(str(row["updated_at_utc"])),
        )

    def get_account_state(self, *, user_id: UUID) -> AccountStateRecord | None:
        row = self._store.get_user(user_id)
        return self._account(row) if row is not None else None

    def has_enabled_webauthn_credential(self, *, user_id: UUID, rp_id: str | None = None) -> bool:
        self._require_user(user_id)
        table = self._store._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'webauthn_credentials'"
        ).fetchone()
        if table is None:
            return False
        if rp_id is None:
            row = self._store._conn.execute(
                "SELECT 1 FROM webauthn_credentials WHERE user_id = ? AND enabled = 1 AND revoked = 0 LIMIT 1",
                (str(user_id),),
            ).fetchone()
        else:
            row = self._store._conn.execute(
                "SELECT 1 FROM webauthn_credentials WHERE user_id = ? AND rp_id = ? AND enabled = 1 AND revoked = 0 LIMIT 1",
                (str(user_id), rp_id),
            ).fetchone()
        return row is not None

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

    def register_device(self, *, user_id: UUID, device_id: str, public_key: bytes, fingerprint: str, created_at: datetime, max_active_devices: int = 3) -> DeviceRecord:
        self._require_user(user_id)
        if max_active_devices < 1:
            raise ValueError("max_active_devices must be positive")
        with self._store._transaction() as cur:
            existing = cur.execute("SELECT user_id FROM s2_devices WHERE device_id = ?", (device_id,)).fetchone()
            if existing is not None:
                raise AccountAuthorityRecordUnavailable("account-owned state unavailable")
            active_count = cur.execute(
                "SELECT COUNT(*) AS count FROM s2_devices WHERE user_id = ? AND status = 'ACTIVE'",
                (str(user_id),),
            ).fetchone()["count"]
            if int(active_count) >= max_active_devices:
                raise DeviceQuotaAuthorityExceeded("active device quota reached")
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

    def save_device_challenge(self, *, user_id: UUID, device_id: str, purpose: str, challenge_hash: str, issued_at: datetime, expires_at: datetime) -> DeviceProofChallengeRecord:
        self._require_user(user_id)
        if not device_id or not purpose or not challenge_hash:
            raise ValueError("device challenge scope is required")
        if expires_at <= issued_at:
            raise ValueError("device challenge expiry must follow issue time")
        with self._store._transaction() as cur:
            existing = cur.execute(
                "SELECT 1 FROM s2_device_challenges WHERE challenge_hash = ?",
                (challenge_hash,),
            ).fetchone()
            if existing is not None:
                raise AccountAuthorityRecordUnavailable("device challenge unavailable")
            cur.execute(
                "INSERT INTO s2_device_challenges(challenge_hash, user_id, device_id, purpose, issued_at_utc, expires_at_utc, consumed_at_utc) VALUES (?, ?, ?, ?, ?, ?, NULL)",
                (challenge_hash, str(user_id), device_id, purpose, issued_at.isoformat(), expires_at.isoformat()),
            )
            row = cur.execute(
                "SELECT * FROM s2_device_challenges WHERE challenge_hash = ?",
                (challenge_hash,),
            ).fetchone()
            assert row is not None
            return self._challenge(row)

    def consume_device_challenge(self, *, user_id: UUID, device_id: str, purpose: str, challenge_hash: str, consumed_at: datetime) -> DeviceProofChallengeRecord:
        self._require_user(user_id)
        with self._store._transaction() as cur:
            row = cur.execute(
                "SELECT * FROM s2_device_challenges WHERE challenge_hash = ? AND user_id = ? AND device_id = ? AND purpose = ?",
                (challenge_hash, str(user_id), device_id, purpose),
            ).fetchone()
            if row is None or row["consumed_at_utc"] is not None:
                raise AccountAuthorityRecordUnavailable("device challenge unavailable")
            issued_at = datetime.fromisoformat(str(row["issued_at_utc"]))
            expires_at = datetime.fromisoformat(str(row["expires_at_utc"]))
            if consumed_at < issued_at or consumed_at > expires_at:
                raise AccountAuthorityRecordUnavailable("device challenge expired or not yet valid")
            cur.execute(
                "UPDATE s2_device_challenges SET consumed_at_utc = ? WHERE challenge_hash = ? AND consumed_at_utc IS NULL",
                (consumed_at.isoformat(), challenge_hash),
            )
            if cur.rowcount != 1:
                raise AccountAuthorityRecordUnavailable("device challenge unavailable")
            updated = cur.execute(
                "SELECT * FROM s2_device_challenges WHERE challenge_hash = ?",
                (challenge_hash,),
            ).fetchone()
            assert updated is not None
            return self._challenge(updated)

    def get_session_family(self, *, user_id: UUID, family_id: str) -> SessionFamilyRecord | None:
        self._require_user(user_id)
        row = self._store._conn.execute(
            "SELECT * FROM s2_session_families WHERE user_id = ? AND family_id = ?",
            (str(user_id), family_id),
        ).fetchone()
        return self._family(row) if row is not None else None

    def list_session_families(self, *, user_id: UUID) -> tuple[SessionFamilyRecord, ...]:
        self._require_user(user_id)
        rows = self._store._conn.execute(
            "SELECT * FROM s2_session_families WHERE user_id = ? ORDER BY created_at_utc, family_id",
            (str(user_id),),
        ).fetchall()
        return tuple(self._family(row) for row in rows)

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

    def revoke_all_access_for_recovery(self, *, user_id: UUID, revoked_at: datetime) -> None:
        self._require_user(user_id)
        stamp = revoked_at.isoformat()
        with self._store._transaction() as cur:
            cur.execute(
                "UPDATE s2_session_families SET state = 'REVOKED', revoked_at_utc = ?, updated_at_utc = ? WHERE user_id = ? AND state != 'REVOKED'",
                (stamp, stamp, str(user_id)),
            )
            cur.execute(
                "UPDATE s2_devices SET status = 'REVOKED', revoked_at_utc = ? WHERE user_id = ? AND status != 'REVOKED'",
                (stamp, str(user_id)),
            )

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
        replay_detected = False
        with self._store._transaction() as cur:
            family = cur.execute(
                "SELECT current_refresh_hash, state FROM s2_session_families WHERE user_id = ? AND family_id = ?",
                (str(user_id), family_id),
            ).fetchone()
            if family is None:
                raise AccountAuthorityRecordUnavailable("account-owned state unavailable")

            consumed = cur.execute(
                "SELECT 1 FROM s2_consumed_refresh_tokens WHERE user_id = ? AND family_id = ? AND token_hash = ?",
                (str(user_id), family_id, consumed_hash),
            ).fetchone()
            if consumed is not None:
                stamp = updated_at.isoformat()
                cur.execute(
                    "UPDATE s2_session_families SET state = 'REVOKED', revoked_at_utc = ?, updated_at_utc = ? WHERE user_id = ? AND family_id = ?",
                    (stamp, stamp, str(user_id), family_id),
                )
                replay_detected = True
            else:
                if family["state"] != "ACTIVE" or family["current_refresh_hash"] != expected_current_hash:
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
        if replay_detected:
            raise RefreshTokenReplayDetected("consumed refresh token replay detected; family revoked")

    def get_rate_limit_state(self, *, user_id: UUID, flow: str, subject_key: str) -> RateLimitStateRecord | None:
        self._require_user(user_id)
        row = self._store._conn.execute(
            "SELECT * FROM s2_rate_limit_state WHERE user_id = ? AND flow = ? AND subject_key = ?",
            (str(user_id), flow, subject_key),
        ).fetchone()
        return self._rate_limit(row) if row is not None else None

    def save_rate_limit_state(self, *, user_id: UUID, flow: str, subject_key: str, failure_count: int, locked_until: datetime | None, updated_at: datetime) -> RateLimitStateRecord:
        self._require_user(user_id)
        with self._store._transaction() as cur:
            cur.execute(
                """INSERT INTO s2_rate_limit_state(user_id, flow, subject_key, failure_count, locked_until_utc, updated_at_utc)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(user_id, flow, subject_key) DO UPDATE SET
                     failure_count = excluded.failure_count,
                     locked_until_utc = excluded.locked_until_utc,
                     updated_at_utc = excluded.updated_at_utc""",
                (
                    str(user_id), flow, subject_key, failure_count,
                    locked_until.isoformat() if locked_until else None,
                    updated_at.isoformat(),
                ),
            )
        record = self.get_rate_limit_state(user_id=user_id, flow=flow, subject_key=subject_key)
        assert record is not None
        return record

    def record_rate_limit_failure(self, *, user_id: UUID, flow: str, subject_key: str, max_failures: int, cooldown_seconds: int, now: datetime) -> RateLimitStateRecord:
        self._require_user(user_id)
        if max_failures < 1 or cooldown_seconds < 1:
            raise ValueError("rate-limit policy values must be positive")
        with self._store._transaction() as cur:
            row = cur.execute(
                "SELECT * FROM s2_rate_limit_state WHERE user_id = ? AND flow = ? AND subject_key = ?",
                (str(user_id), flow, subject_key),
            ).fetchone()
            if row is not None and row["locked_until_utc"]:
                locked_until = datetime.fromisoformat(str(row["locked_until_utc"]))
                if now < locked_until:
                    return self._rate_limit(row)
            failure_count = (int(row["failure_count"]) if row is not None else 0) + 1
            locked_until = now + timedelta(seconds=cooldown_seconds) if failure_count >= max_failures else None
            cur.execute(
                """INSERT INTO s2_rate_limit_state(user_id, flow, subject_key, failure_count, locked_until_utc, updated_at_utc)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(user_id, flow, subject_key) DO UPDATE SET
                     failure_count = excluded.failure_count,
                     locked_until_utc = excluded.locked_until_utc,
                     updated_at_utc = excluded.updated_at_utc""",
                (
                    str(user_id), flow, subject_key, failure_count,
                    locked_until.isoformat() if locked_until else None,
                    now.isoformat(),
                ),
            )
            stored = cur.execute(
                "SELECT * FROM s2_rate_limit_state WHERE user_id = ? AND flow = ? AND subject_key = ?",
                (str(user_id), flow, subject_key),
            ).fetchone()
            assert stored is not None
            return self._rate_limit(stored)

    def clear_rate_limit_state(self, *, user_id: UUID, flow: str, subject_key: str) -> None:
        self._require_user(user_id)
        with self._store._transaction() as cur:
            cur.execute(
                "DELETE FROM s2_rate_limit_state WHERE user_id = ? AND flow = ? AND subject_key = ?",
                (str(user_id), flow, subject_key),
            )
