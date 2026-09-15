"""Dedicated Phase 9 governance metadata store; never a trading/audit authority."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from .sqlite_access import SerializedConnection
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from .sensitive_storage import (
    StorageProfile,
    WindowsAclValidator,
    harden_sensitive_sqlite_files,
    resolve_sensitive_sqlite_path,
)

GOVERNANCE_STORE_SCHEMA_VERSION = 2


class GovernanceStoreError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteGovernanceStore:
    """Durable references/metadata only; evidence remains in core authorities."""

    def __init__(self, path: Path, *, profile: StorageProfile = "development",
                 data_root: Path | None = None, windows_acl_validator: WindowsAclValidator | None = None) -> None:
        self.path = resolve_sensitive_sqlite_path(
            path, store="governance", profile=profile, data_root=data_root,
            windows_acl_validator=windows_acl_validator,
        )
        self._profile = profile
        self._conn = sqlite3.connect(self.path, check_same_thread=False, factory=SerializedConnection)
        self._transaction_lock = self._conn.access_lock
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._bootstrap()
        harden_sensitive_sqlite_files(self.path, profile=profile)

    @contextmanager
    def _tx(self):
        self._transaction_lock.acquire()
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
            self._transaction_lock.release()

    def _bootstrap(self) -> None:
        with self._tx() as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS governance_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            row = cur.execute("SELECT value FROM governance_metadata WHERE key='schema_version'").fetchone()
            if row is None:
                self._create_v1_structures(cur)
                self._create_v2_outbox(cur)
                self._validate_structure(cur, include_outbox=True)
                cur.execute("INSERT INTO governance_metadata VALUES ('schema_version', ?)", (str(GOVERNANCE_STORE_SCHEMA_VERSION),))
            elif row["value"] == "1":
                # V2 is additive: valid V1 governance evidence remains untouched while
                # the Item 4 outbox/recovery table is added atomically.
                self._validate_structure(cur, include_outbox=False)
                self._create_v2_outbox(cur)
                self._validate_structure(cur, include_outbox=True)
                cur.execute("UPDATE governance_metadata SET value = ? WHERE key = 'schema_version'", (str(GOVERNANCE_STORE_SCHEMA_VERSION),))
            elif row["value"] == str(GOVERNANCE_STORE_SCHEMA_VERSION):
                self._validate_structure(cur, include_outbox=True)
            else:
                raise GovernanceStoreError("unknown governance-store schema version")

    @staticmethod
    def _create_v1_structures(cur: sqlite3.Cursor) -> None:
        cur.execute("CREATE TABLE IF NOT EXISTS strategies (strategy_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, archived INTEGER NOT NULL, created_at_utc TEXT NOT NULL)")
        cur.execute("""CREATE TABLE IF NOT EXISTS strategy_versions (
            version_id TEXT PRIMARY KEY, strategy_id TEXT NOT NULL, owner_id TEXT NOT NULL, source_sha256 TEXT NOT NULL,
            artifact_path TEXT NOT NULL, stage TEXT NOT NULL, archived INTEGER NOT NULL, protective_policy_identity TEXT,
            conformance_reference TEXT, backtest_reference TEXT, paper_reference TEXT, promotion_reference TEXT,
            quality_reference TEXT, audit_reference TEXT, created_at_utc TEXT NOT NULL,
            FOREIGN KEY(strategy_id) REFERENCES strategies(strategy_id))""")
        # DB-007: Performance index for version lookups by strategy
        cur.execute("CREATE INDEX IF NOT EXISTS idx_strategy_versions_strat ON strategy_versions (strategy_id)")

    @staticmethod
    def _create_v2_outbox(cur: sqlite3.Cursor) -> None:
        cur.execute("""CREATE TABLE IF NOT EXISTS governance_mutation_outbox (
            operation_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, action TEXT NOT NULL,
            resource_id TEXT, payload_json TEXT NOT NULL, stage_state TEXT NOT NULL,
            created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL,
            intent_event_id TEXT, applied_event_id TEXT, error_message TEXT
        )""")

    @staticmethod
    def _validate_structure(cur: sqlite3.Cursor, *, include_outbox: bool) -> None:
        expected = {
            "governance_metadata": ("key", "value"),
            "strategies": ("strategy_id", "owner_id", "archived", "created_at_utc"),
            "strategy_versions": (
                "version_id", "strategy_id", "owner_id", "source_sha256", "artifact_path", "stage", "archived",
                "protective_policy_identity", "conformance_reference", "backtest_reference", "paper_reference",
                "promotion_reference", "quality_reference", "audit_reference", "created_at_utc",
            ),
        }
        if include_outbox:
            expected["governance_mutation_outbox"] = (
                "operation_id", "owner_id", "action", "resource_id", "payload_json", "stage_state",
                "created_at_utc", "updated_at_utc", "intent_event_id", "applied_event_id", "error_message",
            )
        for table, columns in expected.items():
            actual = tuple(row[1] for row in cur.execute(f"PRAGMA table_info({table})"))
            if actual != columns:
                raise GovernanceStoreError(f"invalid governance-store structure: {table}")

    def save_version(self, record: dict[str, object]) -> None:
        with self._tx() as cur:
            existing = cur.execute("SELECT strategy_id,owner_id,source_sha256,artifact_path,created_at_utc FROM strategy_versions WHERE version_id=?", (record["version_id"],)).fetchone()
            if existing is not None:
                immutable = ("strategy_id", "owner_id", "source_sha256", "artifact_path")
                if any(str(existing[key]) != str(record[key]) for key in immutable):
                    raise GovernanceStoreError("immutable strategy version conflict")
            cur.execute("INSERT INTO strategies(strategy_id,owner_id,archived,created_at_utc) VALUES (?,?,?,?) ON CONFLICT(strategy_id) DO NOTHING", (record["strategy_id"], record["owner_id"], int(bool(record["archived"])), _now()))
            cur.execute("""INSERT INTO strategy_versions(version_id,strategy_id,owner_id,source_sha256,artifact_path,stage,archived,protective_policy_identity,conformance_reference,backtest_reference,paper_reference,promotion_reference,quality_reference,audit_reference,created_at_utc)
                VALUES (:version_id,:strategy_id,:owner_id,:source_sha256,:artifact_path,:stage,:archived,:protective_policy_identity,NULL,NULL,NULL,NULL,NULL,NULL,:created_at_utc)
                ON CONFLICT(version_id) DO UPDATE SET stage=excluded.stage,archived=excluded.archived,protective_policy_identity=excluded.protective_policy_identity""", record)

    def load_version(self, version_id: UUID) -> sqlite3.Row:
        row = self._conn.execute("SELECT * FROM strategy_versions WHERE version_id=?", (str(version_id),)).fetchone()
        if row is None:
            raise GovernanceStoreError("unknown strategy version")
        return row

    def versions_for(self, owner_id: UUID) -> tuple[sqlite3.Row, ...]:
        return tuple(self._conn.execute("SELECT * FROM strategy_versions WHERE owner_id=?", (str(owner_id),)).fetchall())

    def get_strategy_source_digests(self, strategy_id: str) -> set[str]:
        """Return all unique source SHA256 hashes registered for a strategy."""
        with self._tx() as cur:
            rows = cur.execute(
                "SELECT source_sha256 FROM strategy_versions WHERE strategy_id = ?",
                (str(strategy_id),),
            ).fetchall()
            return {str(r["source_sha256"]) for r in rows}

    def get_version(self, strategy_id: str, version_id: str) -> sqlite3.Row | None:
        """Return registered strategy version row or None."""
        with self._tx() as cur:
            return cur.execute(
                "SELECT * FROM strategy_versions WHERE strategy_id = ? AND version_id = ?",
                (str(strategy_id), str(version_id)),
            ).fetchone()

    def save_outbox_stage(
        self,
        operation_id: str,
        owner_id: UUID,
        action: str,
        resource_id: str | None,
        payload_json: str,
        stage_state: str,
        intent_event_id: str | None = None,
        applied_event_id: str | None = None,
        error_message: str | None = None,
    ) -> None:
        now = _now()
        with self._tx() as cur:
            cur.execute(
                """
                INSERT INTO governance_mutation_outbox (
                    operation_id, owner_id, action, resource_id, payload_json,
                    stage_state, created_at_utc, updated_at_utc,
                    intent_event_id, applied_event_id, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(operation_id) DO UPDATE SET
                    stage_state = excluded.stage_state,
                    updated_at_utc = excluded.updated_at_utc,
                    intent_event_id = coalesce(excluded.intent_event_id, governance_mutation_outbox.intent_event_id),
                    applied_event_id = coalesce(excluded.applied_event_id, governance_mutation_outbox.applied_event_id),
                    error_message = coalesce(excluded.error_message, governance_mutation_outbox.error_message)
                """,
                (
                    operation_id, str(owner_id), action, resource_id, payload_json,
                    stage_state, now, now, intent_event_id, applied_event_id, error_message
                ),
            )

    def update_outbox_state(
        self,
        operation_id: str,
        stage_state: str,
        applied_event_id: str | None = None,
        error_message: str | None = None,
    ) -> None:
        now = _now()
        with self._tx() as cur:
            cur.execute(
                """
                UPDATE governance_mutation_outbox SET
                    stage_state = ?,
                    updated_at_utc = ?,
                    applied_event_id = coalesce(?, applied_event_id),
                    error_message = coalesce(?, error_message)
                WHERE operation_id = ?
                """,
                (stage_state, now, applied_event_id, error_message, operation_id),
            )

    def get_outbox_record(self, operation_id: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM governance_mutation_outbox WHERE operation_id = ?", (operation_id,)
        ).fetchone()

    def get_pending_outbox_records(self) -> tuple[sqlite3.Row, ...]:
        return tuple(
            self._conn.execute(
                "SELECT * FROM governance_mutation_outbox WHERE stage_state = 'COMMITTED_PENDING_AUDIT' ORDER BY created_at_utc ASC"
            ).fetchall()
        )

    def worker_copy(self):
        """Independent read authority for a historical job; no bootstrap writes."""
        from copy import copy
        worker = copy(self)
        worker._conn = sqlite3.connect(self.path, timeout=30, factory=SerializedConnection)
        worker._transaction_lock = worker._conn.access_lock
        worker._conn.row_factory = sqlite3.Row
        worker._conn.execute("PRAGMA foreign_keys=ON")
        return worker

    def close(self) -> None:
        self._conn.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    @staticmethod
    def verify_artifact(*, artifact_root: Path, owner_id: UUID, artifact_path: str, digest: str) -> Path:
        root = (artifact_root / f"usr_{owner_id}" / "strategies").resolve()
        path = Path(artifact_path).resolve()
        if root not in path.parents or path.parent.parent != root or path.suffix != ".py" or not path.is_file():
            raise GovernanceStoreError("missing or cross-user strategy artifact")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise GovernanceStoreError("strategy artifact hash mismatch")
        return path
