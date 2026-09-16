"""Dedicated durable Phase 9 security/identity store.

This is deliberately separate from the trading/paper SQLite store.  Its
schema version is an independent security contract and never changes the
engine's SCHEMA_VERSION (which remains 7).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from .sqlite_access import SerializedConnection
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Literal
from uuid import UUID, uuid4

from .domain import (
    compute_service_expiry,
    compute_strategy_effective_eligibility,
    compute_capability_effective,
    compute_dataset_effective_readiness,
)
from .sensitive_storage import (
    StorageProfile,
    WindowsAclValidator,
    harden_sensitive_sqlite_files,
    resolve_sensitive_sqlite_path,
)


SECURITY_STORE_SCHEMA_VERSION = 2


# F-18: server-setting keys that can never be mutated through the settings
# lifecycle (no live arming, hold release, broker mutation, or gate bypass).
_PROTECTED_SETTING_KEYS = frozenset({
    "arm_live_trading", "release_live_hold", "live_global_hold",
    "enable_broker_mutation", "broker_mutation", "broker_connected",
    "disable_risk_gate", "disable_audit", "bypass_audit", "bypass_auth",
    "bypass_dataset_governance", "disable_dataset_gate",
})


class SecurityStoreError(RuntimeError):
    """Raised on security invariant violations inside the store."""


class AmbiguousSessionRefError(SecurityStoreError):
    """Raised when a masked or short session reference matches multiple active sessions."""
    def __init__(self, ref: str, match_count: int):
        super().__init__(f"AMBIGUOUS_SESSION_REF: Reference '{ref}' matches {match_count} active sessions. Exact session ID required.")
        self.code = "AMBIGUOUS_SESSION_REF"
        self.ref = ref
        self.match_count = match_count


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_activation_code(code: str) -> str:
    """Standard salted one-way hash for activation code at rest (AUTH_ACCESS_CONTRACT_V1.md §2.2)."""
    return hashlib.sha256(f"sx-act-v1-salt:{code.strip().upper()}".encode("utf-8")).hexdigest()


def _generate_canonical_sx_id() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    part1 = "".join(secrets.choice(alphabet) for _ in range(4))
    part2 = "".join(secrets.choice(alphabet) for _ in range(4))
    return f"SX-U-{part1}-{part2}"


def generate_activation_code() -> str:
    """Generate a high-entropy 24h one-time activation code: SX-ACT-XXXX-XXXX-XXXX."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    part1 = "".join(secrets.choice(alphabet) for _ in range(4))
    part2 = "".join(secrets.choice(alphabet) for _ in range(4))
    part3 = "".join(secrets.choice(alphabet) for _ in range(4))
    return f"SX-ACT-{part1}-{part2}-{part3}"


_generate_canonical_activation_code = generate_activation_code

# DB-008: Configurable retention defaults for historical sessions and ephemeral challenges
SESSION_HISTORY_RETENTION_DAYS: int = 30
WEBAUTHN_CHALLENGE_RETENTION_HOURS: int = 48


class SQLiteSecurityStore:
    """Small transactional store for WebAuthn state, never bearer secrets."""

    SESSION_HISTORY_RETENTION_DAYS = SESSION_HISTORY_RETENTION_DAYS
    WEBAUTHN_CHALLENGE_RETENTION_HOURS = WEBAUTHN_CHALLENGE_RETENTION_HOURS

    def __init__(self, path: Path, *, profile: StorageProfile = "development",
                 data_root: Path | None = None, windows_acl_validator: WindowsAclValidator | None = None,
                 seed_governance: bool | None = None) -> None:
        self.path = resolve_sensitive_sqlite_path(
            path, store="security", profile=profile, data_root=data_root,
            windows_acl_validator=windows_acl_validator,
        )
        self._profile = profile
        self._seed_governance = seed_governance
        self._transaction_lock = RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, factory=SerializedConnection)
        self._closed = False
        self._transaction_lock = self._conn.access_lock
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._bootstrap()
        try:
            self.run_retention_maintenance()
        except Exception:
            # Retention cleanup failure must not fail startup or corrupt auth state
            pass
        harden_sensitive_sqlite_files(self.path, profile=profile)

    def _should_seed_governance(self) -> bool:
        # Production is an explicit security boundary, even with test flags set.
        if self._profile == "production":
            return False
        # 1. Explicit caller parameter takes highest precedence
        if self._seed_governance is True:
            return True
        if self._seed_governance is False:
            return False

        # 2. Explicit environment mode configuration boundaries
        if os.environ.get("SENTINELX_AUTO_SEED") == "0":
            return False
        if os.environ.get("SENTINELX_APP_MODE", "").lower() in {"production", "release_candidate", "live"}:
            return False

        path_str = str(self.path).replace("\\", "/").lower()
        # 3. Canonical authoritative runtime stores are permanently forbidden from auto-seeding
        if "sentinelx_security.sqlite3" in path_str and ".sentinelx-dev-data" in path_str and "test" not in path_str:
            return False

        # 4. Explicit test configuration or isolated test fixtures
        if os.environ.get("SENTINELX_AUTO_SEED") == "1":
            return True
        if os.environ.get("SENTINELX_TEST_MODE") == "1" or "pytest" in sys.modules:
            return True

        # 5. Default: Fail closed (zero auto-seeding in normal runtime)
        return False

    def _bootstrap(self) -> None:
        with self._transaction() as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS security_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            cur.execute("""CREATE TABLE IF NOT EXISTS live_readiness_observations (
                user_id TEXT NOT NULL, observation_key TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (user_id, observation_key)
            )""")
            cur.execute("INSERT OR IGNORE INTO security_metadata VALUES ('live_global_hold', 'true')")
            existing = cur.execute("SELECT value FROM security_metadata WHERE key = 'schema_version'").fetchone()
            if existing is None:
                cur.execute("INSERT INTO security_metadata(key, value) VALUES ('schema_version', ?)", (str(SECURITY_STORE_SCHEMA_VERSION),))
            elif existing["value"] == "1":
                # Clean migration from V1 to V2
                cur.execute("UPDATE security_metadata SET value = ? WHERE key = 'schema_version'", (str(SECURITY_STORE_SCHEMA_VERSION),))
            elif existing["value"] != str(SECURITY_STORE_SCHEMA_VERSION):
                raise SecurityStoreError("incompatible dedicated security-store schema")

            cur.execute("""CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY, role TEXT NOT NULL, lifecycle TEXT NOT NULL,
                display_name TEXT NOT NULL, created_at_utc TEXT NOT NULL, security_state TEXT NOT NULL,
                sx_id TEXT, account_status TEXT, activation_status TEXT, service_status TEXT,
                service_started_at TEXT, service_expires_at TEXT, service_term_type TEXT,
                custom_term_value INTEGER, custom_term_unit TEXT,
                bound_email TEXT, bound_phone TEXT, notes TEXT, plan TEXT, created_by TEXT
            )""")
            # Non-destructive additive migration for existing security-store tables
            user_cols = {row["name"] for row in cur.execute("PRAGMA table_info(users)").fetchall()}
            for col_name, col_type in [
                ("sx_id", "TEXT"),
                ("account_status", "TEXT"),
                ("activation_status", "TEXT"),
                ("service_status", "TEXT"),
                ("service_started_at", "TEXT"),
                ("service_expires_at", "TEXT"),
                ("service_term_type", "TEXT"),
                ("custom_term_value", "INTEGER"),
                ("custom_term_unit", "TEXT"),
                ("bound_email", "TEXT"),
                ("bound_phone", "TEXT"),
                ("notes", "TEXT"),
                ("plan", "TEXT"),
                ("created_by", "TEXT"),
            ]:
                if col_name not in user_cols:
                    cur.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")

            # DB-003: Preflight duplicate check before creating unique indexes
            dup_emails = cur.execute("""
                SELECT LOWER(TRIM(bound_email)) as email_val, COUNT(*) as c
                FROM users
                WHERE bound_email IS NOT NULL AND TRIM(bound_email) != ''
                GROUP BY LOWER(TRIM(bound_email))
                HAVING COUNT(*) > 1
            """).fetchall()
            if dup_emails:
                raise SecurityStoreError(
                    f"Migration safety check failed: detected {len(dup_emails)} duplicate email group(s) in users table. Pre-existing duplicates must be resolved before applying unique constraint."
                )

            dup_sxids = cur.execute("""
                SELECT UPPER(TRIM(sx_id)) as sx_val, COUNT(*) as c
                FROM users
                WHERE sx_id IS NOT NULL AND TRIM(sx_id) != ''
                GROUP BY UPPER(TRIM(sx_id))
                HAVING COUNT(*) > 1
            """).fetchall()
            if dup_sxids:
                raise SecurityStoreError(
                    f"Migration safety check failed: detected {len(dup_sxids)} duplicate SX-ID group(s) in users table. Pre-existing duplicates must be resolved before applying unique constraint."
                )

            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_users_bound_email_unique
                ON users(LOWER(TRIM(bound_email)))
                WHERE bound_email IS NOT NULL AND TRIM(bound_email) != ''
            """)
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_users_sx_id_unique
                ON users(UPPER(TRIM(sx_id)))
                WHERE sx_id IS NOT NULL AND TRIM(sx_id) != ''
            """)

            cur.execute("""CREATE TABLE IF NOT EXISTS activation_issuances (
                issuance_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                issued_at_utc TEXT NOT NULL,
                expires_at_utc TEXT NOT NULL,
                redeemed_at_utc TEXT,
                revoked_at_utc TEXT,
                actor TEXT NOT NULL,
                notes TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )""")

            cur.execute("""CREATE TABLE IF NOT EXISTS webauthn_credentials (
                credential_id BLOB PRIMARY KEY, user_id TEXT NOT NULL, rp_id TEXT NOT NULL,
                credential_data BLOB NOT NULL, sign_count INTEGER NOT NULL, label TEXT NOT NULL,
                is_backup_hardware INTEGER NOT NULL, enabled INTEGER NOT NULL, revoked INTEGER NOT NULL,
                created_at_utc TEXT NOT NULL, last_used_at_utc TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )""")
            credential_columns = {row[1] for row in cur.execute("PRAGMA table_info(webauthn_credentials)")}
            if "revoked_at_utc" not in credential_columns:
                cur.execute("ALTER TABLE webauthn_credentials ADD COLUMN revoked_at_utc TEXT")
            cur.execute("""CREATE TABLE IF NOT EXISTS webauthn_challenges (
                challenge_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, purpose TEXT NOT NULL,
                rp_id TEXT NOT NULL, origin TEXT NOT NULL, ceremony_state TEXT NOT NULL,
                expires_at_utc TEXT NOT NULL, consumed_at_utc TEXT, created_at_utc TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )""")
            cur.execute("""CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, route TEXT NOT NULL,
                risk TEXT NOT NULL, expires_at_utc TEXT NOT NULL, revoked_at_utc TEXT,
                created_at_utc TEXT NOT NULL, step_up_satisfied INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )""")
            # DB-007: Performance indexes for high-frequency security lookups
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_activation_issuances_user ON activation_issuances(user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_webauthn_credentials_user ON webauthn_credentials(user_id)")
            cur.execute("""CREATE TABLE IF NOT EXISTS security_event_references (
                event_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, action TEXT NOT NULL,
                core_audit_reference TEXT NOT NULL, recorded_at_utc TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )""")
            cur.execute("""CREATE TABLE IF NOT EXISTS bootstrap_authorizations (
                token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at_utc TEXT NOT NULL,
                consumed_at_utc TEXT, created_at_utc TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )""")
            cur.execute("""CREATE TABLE IF NOT EXISTS security_mutation_outbox (
                operation_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, action TEXT NOT NULL,
                resource_id TEXT, payload_json TEXT NOT NULL, stage_state TEXT NOT NULL,
                created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL,
                intent_event_id TEXT, applied_event_id TEXT, error_message TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )""")

            cur.execute("""CREATE TABLE IF NOT EXISTS owner_strategies (
                strategy_id TEXT PRIMARY KEY,
                id TEXT NOT NULL,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                interface_version TEXT NOT NULL DEFAULT '1.0',
                stage TEXT NOT NULL,
                category TEXT,
                instruments_json TEXT NOT NULL DEFAULT '[]',
                timeframes_json TEXT NOT NULL DEFAULT '[]',
                quality REAL NOT NULL DEFAULT 70.0,
                evidence_attached INTEGER NOT NULL DEFAULT 1,
                pnl TEXT NOT NULL DEFAULT '0.0%',
                is_profit INTEGER NOT NULL DEFAULT 1,
                note TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                author TEXT NOT NULL DEFAULT '',
                author_sx_id TEXT NOT NULL DEFAULT '',
                conformance_status TEXT NOT NULL DEFAULT 'CONFORMANT',
                admin_status TEXT NOT NULL DEFAULT 'ACTIVE',
                backtest_system_readiness TEXT NOT NULL DEFAULT 'READY',
                backtest_system_blocker TEXT,
                backtest_owner_allowance TEXT NOT NULL DEFAULT 'ALLOWED',
                backtest_owner_hold_reason TEXT,
                paper_system_readiness TEXT NOT NULL DEFAULT 'READY',
                paper_system_blocker TEXT,
                paper_owner_allowance TEXT NOT NULL DEFAULT 'ALLOWED',
                paper_owner_hold_reason TEXT,
                live_system_readiness TEXT NOT NULL DEFAULT 'BLOCKED',
                live_system_blocker TEXT,
                live_owner_allowance TEXT NOT NULL DEFAULT 'ALLOWED',
                live_owner_hold_reason TEXT,
                win_rate REAL NOT NULL DEFAULT 60.0,
                max_drawdown REAL NOT NULL DEFAULT -5.0,
                profit_factor REAL NOT NULL DEFAULT 1.5,
                sharpe_ratio REAL NOT NULL DEFAULT 1.5,
                total_trades INTEGER NOT NULL DEFAULT 100,
                active_positions INTEGER NOT NULL DEFAULT 0,
                governance_history_json TEXT NOT NULL DEFAULT '[]',
                updated_at_utc TEXT NOT NULL
            )""")

            cur.execute("""CREATE TABLE IF NOT EXISTS user_strategy_assignments (
                assignment_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                version_id TEXT,
                tenant TEXT NOT NULL DEFAULT 'default',
                assignment_status TEXT NOT NULL DEFAULT 'ASSIGNED',
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                UNIQUE(user_id, strategy_id),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_user_strategy_assignments_user ON user_strategy_assignments(user_id)")

            # Additive Phase B: explicit strategy visibility. PRIVATE (user
            # authored), OWNER_PRIVATE (owner authored, default), GLOBAL
            # (explicit privileged publish). Legacy rows backfill by author:
            # rows whose author is not a registered identity keep the prior
            # canonical-catalog behavior (GLOBAL); registered non-owner
            # authors become PRIVATE; registered owners stay OWNER_PRIVATE.
            strategy_columns = {row[1] for row in cur.execute("PRAGMA table_info(owner_strategies)")}
            if "visibility" not in strategy_columns:
                cur.execute("ALTER TABLE owner_strategies ADD COLUMN visibility TEXT NOT NULL DEFAULT 'OWNER_PRIVATE'")
                cur.execute("""UPDATE owner_strategies SET visibility = 'GLOBAL'
                               WHERE (author IS NULL OR TRIM(author) = ''
                                      OR author NOT IN (SELECT user_id FROM users))""")
                cur.execute("""UPDATE owner_strategies SET visibility = 'PRIVATE'
                               WHERE author IN (SELECT user_id FROM users WHERE role != 'OWNER')""")

            cur.execute("""CREATE TABLE IF NOT EXISTS owner_connections (
                connection_id TEXT PRIMARY KEY,
                id TEXT NOT NULL,
                name TEXT NOT NULL,
                provider TEXT NOT NULL,
                type TEXT NOT NULL,
                environment TEXT NOT NULL,
                account_alias TEXT NOT NULL,
                secret_ref TEXT NOT NULL,
                auth_state TEXT NOT NULL,
                health_state TEXT NOT NULL,
                latency_ms INTEGER NOT NULL DEFAULT 0,
                last_check TEXT NOT NULL,
                owner_allowance TEXT NOT NULL DEFAULT 'ALLOWED',
                owner_hold_reason TEXT,
                capabilities_json TEXT NOT NULL DEFAULT '[]',
                events_json TEXT NOT NULL DEFAULT '[]',
                updated_at_utc TEXT NOT NULL
            )""")

            cur.execute("""CREATE TABLE IF NOT EXISTS owner_datasets (
                dataset_id TEXT PRIMARY KEY,
                id TEXT NOT NULL,
                source TEXT NOT NULL,
                market TEXT NOT NULL,
                instrument TEXT NOT NULL,
                segment TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                source_timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                trading_days INTEGER NOT NULL DEFAULT 0,
                row_count INTEGER NOT NULL DEFAULT 0,
                format TEXT NOT NULL DEFAULT 'PARQUET_V2',
                logical_path TEXT NOT NULL,
                gap_status TEXT NOT NULL DEFAULT 'GAPS_CLEAR',
                gap_details TEXT,
                provenance TEXT NOT NULL DEFAULT 'KNOWN_HASH',
                hash_sha256 TEXT NOT NULL,
                acquisition_state TEXT NOT NULL DEFAULT 'ACQUIRED',
                system_readiness TEXT NOT NULL DEFAULT 'SYSTEM_READY',
                system_blocker_reason TEXT,
                verification_details TEXT NOT NULL DEFAULT '',
                owner_approval TEXT NOT NULL DEFAULT 'APPROVED',
                owner_hold_reason TEXT,
                history_json TEXT NOT NULL DEFAULT '[]',
                updated_at_utc TEXT NOT NULL
            )""")

            # Additive Phase I (R-05): walk-forward/OOS jobs. Manual runs
            # only; no scheduler constructs exist anywhere in this codebase.
            cur.execute("""CREATE TABLE IF NOT EXISTS walkforward_jobs (
                job_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                strategy_version_id TEXT,
                source_sha256 TEXT,
                dataset_id TEXT NOT NULL,
                instrument TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                is_days INTEGER NOT NULL,
                oos_days INTEGER NOT NULL,
                initial_capital REAL NOT NULL,
                policy_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'PENDING',
                cancel_requested INTEGER NOT NULL DEFAULT 0,
                overall_json TEXT NOT NULL DEFAULT '{}',
                error_message TEXT,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_walkforward_jobs_user ON walkforward_jobs(user_id)")
            cur.execute("""CREATE TABLE IF NOT EXISTS walkforward_windows (
                window_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                kind TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                backtest_run_id TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING',
                metrics_json TEXT NOT NULL DEFAULT '{}',
                error_message TEXT,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES walkforward_jobs(job_id)
            )""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_walkforward_windows_job ON walkforward_windows(job_id)")
            # Phase I pivot: windows execute as paper historical-replay sessions
            # (stable multi-day engine path) instead of backtest runs.
            window_columns = {row[1] for row in cur.execute("PRAGMA table_info(walkforward_windows)")}
            if "paper_session_id" not in window_columns:
                cur.execute("ALTER TABLE walkforward_windows ADD COLUMN paper_session_id TEXT")

            cur.execute("""CREATE TABLE IF NOT EXISTS backtest_runs (
                run_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                strategy_name TEXT NOT NULL,
                version TEXT NOT NULL,
                instrument TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                date_range TEXT NOT NULL,
                initial_capital REAL NOT NULL,
                net_profit REAL NOT NULL,
                net_profit_pct REAL NOT NULL,
                win_rate REAL NOT NULL,
                profit_factor REAL NOT NULL,
                sharpe_ratio REAL NOT NULL,
                max_drawdown REAL NOT NULL,
                total_trades INTEGER NOT NULL,
                winning_trades INTEGER NOT NULL,
                losing_trades INTEGER NOT NULL,
                avg_profit_trade REAL NOT NULL,
                avg_win REAL NOT NULL,
                avg_loss REAL NOT NULL,
                status TEXT NOT NULL,
                quality_score REAL NOT NULL,
                policy_snapshot TEXT NOT NULL,
                policy_details_json TEXT NOT NULL DEFAULT '{}',
                data_fingerprint TEXT NOT NULL,
                data_source_name TEXT NOT NULL,
                manifest_fingerprint TEXT,
                equity_curve_json TEXT NOT NULL DEFAULT '[]',
                trades_json TEXT NOT NULL DEFAULT '[]',
                created_at_utc TEXT NOT NULL,
                completed_at_utc TEXT,
                error_message TEXT
            )""")
            # F-2: unavailable evidence is SQL NULL. Rebuild only the old
            # NOT NULL run table transactionally, preserving every existing row.
            nullable = {"net_profit", "net_profit_pct", "win_rate", "profit_factor", "sharpe_ratio",
                        "max_drawdown", "avg_profit_trade", "avg_win", "avg_loss", "quality_score"}
            if any(row[1] in nullable and row[3] for row in cur.execute("PRAGMA table_info(backtest_runs)")):
                definition = cur.execute("SELECT sql FROM sqlite_master WHERE name = 'backtest_runs'").fetchone()[0]
                for column in nullable:
                    definition = definition.replace(column + " REAL NOT NULL", column + " REAL")
                definition = definition.replace("backtest_runs", "backtest_runs_p0", 1)
                cur.execute(definition)
                cur.execute("INSERT INTO backtest_runs_p0 SELECT * FROM backtest_runs")
                cur.execute("DROP TABLE backtest_runs")
                cur.execute("ALTER TABLE backtest_runs_p0 RENAME TO backtest_runs")
            if "execution_metadata_json" not in {r[1] for r in cur.execute("PRAGMA table_info(backtest_runs)")}:
                cur.execute("ALTER TABLE backtest_runs ADD COLUMN execution_metadata_json TEXT NOT NULL DEFAULT '{}'")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_bt_runs_user ON backtest_runs(user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_bt_runs_strat ON backtest_runs(strategy_id)")

            cur.execute("""CREATE TABLE IF NOT EXISTS paper_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                strategy_name TEXT NOT NULL,
                strategy_version TEXT NOT NULL,
                instrument TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                initial_capital REAL NOT NULL,
                current_equity REAL NOT NULL,
                available_cash REAL NOT NULL,
                used_capital REAL NOT NULL,
                realized_pnl REAL NOT NULL DEFAULT 0.0,
                unrealized_pnl REAL NOT NULL DEFAULT 0.0,
                day_pnl REAL NOT NULL DEFAULT 0.0,
                total_pnl REAL NOT NULL DEFAULT 0.0,
                return_pct REAL NOT NULL DEFAULT 0.0,
                trades_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'INITIALIZED',
                owner_allowance TEXT NOT NULL DEFAULT 'ALLOWED',
                owner_hold_reason TEXT,
                policy_snapshot TEXT NOT NULL,
                policy_details_json TEXT NOT NULL DEFAULT '{}',
                data_source_name TEXT NOT NULL DEFAULT 'HISTORICAL_REPLAY',
                data_source_mode TEXT NOT NULL DEFAULT 'HISTORICAL_REPLAY',
                feed_status TEXT NOT NULL DEFAULT 'DISCONNECTED',
                last_market_timestamp TEXT,
                last_quote_received_at TEXT,
                contract_identity TEXT,
                live_quote_count INTEGER NOT NULL DEFAULT 0,
                reconciliation_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                reconciliation_finding TEXT,
                market_data_readiness TEXT NOT NULL DEFAULT 'UNKNOWN',
                persistence_health TEXT NOT NULL DEFAULT 'UNKNOWN',
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                stopped_at_utc TEXT,
                error_message TEXT
            )""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_paper_sessions_user ON paper_sessions(user_id)")

            paper_session_cols = {row["name"] for row in cur.execute("PRAGMA table_info(paper_sessions)").fetchall()}
            for col_name, col_type in [
                ("data_source_mode", "TEXT NOT NULL DEFAULT 'HISTORICAL_REPLAY'"),
                ("feed_status", "TEXT NOT NULL DEFAULT 'DISCONNECTED'"),
                ("last_market_timestamp", "TEXT"),
                ("last_quote_received_at", "TEXT"),
                ("contract_identity", "TEXT"),
                ("live_quote_count", "INTEGER NOT NULL DEFAULT 0"),
                ("bars_consumed", "INTEGER"),
                ("first_consumed_timestamp", "TEXT"),
                ("last_consumed_timestamp", "TEXT"),
                ("requested_date_range", "TEXT"),
                ("effective_date_range_json", "TEXT"),
                ("price_provenance", "TEXT DEFAULT 'MODELED'"),
                ("date_range", "TEXT"),
                ("dataset_id", "TEXT"),
                ("risk_gate_status", "TEXT DEFAULT 'ACTIVE'"),
                # R-06: live market-data feed source truth. TEST_FEED =
                # explicitly registered test feed; MANUAL_INGEST = tenant-
                # scoped manual quote ingest; PROVIDER = provider-backed
                # streaming adapter (only with a wired credential provider).
                ("feed_source", "TEXT NOT NULL DEFAULT 'MANUAL_INGEST'"),
            ]:
                if col_name not in paper_session_cols:
                    cur.execute(f"ALTER TABLE paper_sessions ADD COLUMN {col_name} {col_type}")

            cur.execute("""CREATE TABLE IF NOT EXISTS paper_positions (
                position_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                resolved_contract TEXT NOT NULL,
                position_type TEXT NOT NULL,
                qty INTEGER NOT NULL,
                avg_price REAL NOT NULL,
                ltp REAL NOT NULL,
                entry_cost REAL NOT NULL,
                current_value REAL NOT NULL,
                unrealized_pnl REAL NOT NULL,
                return_pct REAL NOT NULL,
                strategy_source TEXT NOT NULL,
                policy_snapshot TEXT,
                opened_at_utc TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'OPEN',
                price_provenance TEXT DEFAULT 'MODELED',
                FOREIGN KEY(session_id) REFERENCES paper_sessions(session_id)
            )""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_paper_positions_session ON paper_positions(session_id)")

            paper_pos_cols = {row["name"] for row in cur.execute("PRAGMA table_info(paper_positions)").fetchall()}
            if "price_provenance" not in paper_pos_cols:
                cur.execute("ALTER TABLE paper_positions ADD COLUMN price_provenance TEXT DEFAULT 'MODELED'")

            cur.execute("""CREATE TABLE IF NOT EXISTS paper_orders (
                order_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                instrument TEXT NOT NULL,
                order_type TEXT NOT NULL,
                side TEXT NOT NULL,
                qty INTEGER NOT NULL,
                limit_price REAL,
                fill_price REAL,
                status TEXT NOT NULL,
                rejection_reason TEXT,
                created_at_utc TEXT NOT NULL,
                filled_at_utc TEXT,
                FOREIGN KEY(session_id) REFERENCES paper_sessions(session_id)
            )""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_paper_orders_session ON paper_orders(session_id)")

            # Broker fingerprints are canonical within a run, not globally unique
            # across tenants replaying identical inputs. Preserve existing evidence
            # while making the persistence identity (session_id, order_id).
            order_columns = cur.execute("PRAGMA table_info(paper_orders)").fetchall()
            if [c["name"] for c in order_columns if c["pk"]] == ["order_id"]:
                cur.execute("""CREATE TABLE paper_orders_scoped (
                    order_id TEXT NOT NULL, session_id TEXT NOT NULL,
                    instrument TEXT NOT NULL, order_type TEXT NOT NULL,
                    side TEXT NOT NULL, qty INTEGER NOT NULL, limit_price REAL,
                    fill_price REAL, status TEXT NOT NULL, rejection_reason TEXT,
                    created_at_utc TEXT NOT NULL, filled_at_utc TEXT,
                    PRIMARY KEY (session_id, order_id),
                    FOREIGN KEY(session_id) REFERENCES paper_sessions(session_id)
                )""")
                cur.execute("INSERT INTO paper_orders_scoped SELECT * FROM paper_orders")
                cur.execute("DROP TABLE paper_orders")
                cur.execute("ALTER TABLE paper_orders_scoped RENAME TO paper_orders")
                cur.execute("CREATE INDEX idx_paper_orders_session ON paper_orders(session_id)")

            cur.execute("""CREATE TABLE IF NOT EXISTS paper_events (
                event_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                event_time TEXT NOT NULL,
                title TEXT NOT NULL,
                detail TEXT NOT NULL,
                source TEXT NOT NULL,
                status TEXT NOT NULL,
                badge TEXT,
                created_at_utc TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES paper_sessions(session_id)
            )""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_paper_events_session ON paper_events(session_id)")

            # ── P1-A (R-02): per-user broker/API connection authority ──
            # Additive only. Raw secrets are never persisted here; credential_ref
            # is an opaque reference resolved server-side by future execution layers.
            cur.execute("""CREATE TABLE IF NOT EXISTS user_connections (
                connection_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                account_ref TEXT NOT NULL,
                credential_ref TEXT,
                status TEXT NOT NULL DEFAULT 'NOT_CONNECTED',
                market_data_capability TEXT NOT NULL DEFAULT 'UNAVAILABLE',
                execution_capability TEXT NOT NULL DEFAULT 'DISABLED_DISARMED',
                health_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                suspended INTEGER NOT NULL DEFAULT 0,
                suspend_reason TEXT,
                last_verified_at_utc TEXT,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_user_connections_user ON user_connections(user_id)")

            # ── P1-A (R-02): canonical strategy → connection/account mapping ──
            cur.execute("""CREATE TABLE IF NOT EXISTS strategy_connection_mappings (
                mapping_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                strategy_version_id TEXT,
                source_sha256 TEXT,
                connection_id TEXT NOT NULL,
                account_ref TEXT NOT NULL,
                execution_mode TEXT NOT NULL DEFAULT 'LIVE_PAPER',
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                UNIQUE(user_id, strategy_id, execution_mode),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_strategy_connection_mappings_user ON strategy_connection_mappings(user_id)")
            mapping_cols = {
                row["name"] for row in cur.execute(
                    "PRAGMA table_info(strategy_connection_mappings)"
                ).fetchall()
            }
            if "source_sha256" not in mapping_cols:
                cur.execute("ALTER TABLE strategy_connection_mappings ADD COLUMN source_sha256 TEXT")

            # ── P1-A (R-07): persistent multi-strategy deployment authority ──
            # Backend/database is authoritative; frontend state is never truth.
            cur.execute("""CREATE TABLE IF NOT EXISTS strategy_deployments (
                deployment_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                strategy_version_id TEXT,
                source_sha256 TEXT,
                connection_id TEXT,
                account_ref TEXT,
                instrument TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                execution_mode TEXT NOT NULL DEFAULT 'LIVE_PAPER',
                risk_ref TEXT,
                status TEXT NOT NULL DEFAULT 'DEPLOYED',
                block_reason TEXT,
                block_authority TEXT NOT NULL DEFAULT 'LEGACY',
                runtime_session_id TEXT,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                last_transition_at_utc TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_strategy_deployments_user ON strategy_deployments(user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_strategy_deployments_status ON strategy_deployments(status)")
            # DB-009: Active deployment uniqueness constraint (DEPLOYED, PAUSED, BLOCKED)
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_strategy_deployments_active_unique
                ON strategy_deployments(user_id, strategy_id, instrument, timeframe, execution_mode)
                WHERE status IN ('DEPLOYED', 'PAUSED', 'BLOCKED')
            """)
            deployment_cols = {
                row["name"] for row in cur.execute(
                    "PRAGMA table_info(strategy_deployments)"
                ).fetchall()
            }
            if "block_authority" not in deployment_cols:
                # Existing ambiguous BLOCKED records fail closed as LEGACY. New
                # records always persist an explicit authority below.
                cur.execute(
                    "ALTER TABLE strategy_deployments "
                    "ADD COLUMN block_authority TEXT NOT NULL DEFAULT 'LEGACY'"
                )

            if self._should_seed_governance():
                self._seed_owner_governance_if_empty(cur)

    @contextmanager
    def _transaction(self):
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

    def activation_subject(self, identifier: str, code: str):
        # The permanent SX ID identifies one record; email/display names are not authority.
        rows = self._conn.execute("SELECT * FROM users WHERE UPPER(sx_id) = UPPER(?)", (identifier.strip(),)).fetchall()
        if len(rows) != 1:
            raise SecurityStoreError("Activation unavailable")
        user = rows[0]
        self._validate_activation(self._conn, user, code, _utc_now())
        return user

    @staticmethod
    def _validate_activation(cur, user, code, now):
        if (user is None or user["role"] != "USER" or user["lifecycle"] != "ACTIVE"
                or user["account_status"] != "PENDING" or user["activation_status"] != "INVITED"
                or user["service_started_at"] is not None):
            raise SecurityStoreError("Activation unavailable")
        rows = cur.execute("SELECT * FROM activation_issuances WHERE user_id = ? AND status = 'INVITED'", (user["user_id"],)).fetchall()
        if len(rows) != 1:
            raise SecurityStoreError("Activation unavailable")
        row = rows[0]
        if (row["redeemed_at_utc"] is not None or row["revoked_at_utc"] is not None
                or datetime.fromisoformat(row["expires_at_utc"]) <= now
                or not hmac.compare_digest(row["code_hash"], _hash_activation_code(code))):
            raise SecurityStoreError("Activation unavailable")
        return row

    def redeem_activation(self, *, user_id: UUID, code: str, challenge_id: str,
                          rp_id: str, origin: str, ceremony_state: str, expires_at: datetime):
        now = _utc_now()
        with self._transaction() as cur:
            user = cur.execute("SELECT * FROM users WHERE user_id = ?", (str(user_id),)).fetchone()
            issuance = self._validate_activation(cur, user, code, now)
            cur.execute("UPDATE activation_issuances SET status = 'REDEEMED', redeemed_at_utc = ? WHERE issuance_id = ?", (now.isoformat(), issuance["issuance_id"]))
            cur.execute("UPDATE users SET activation_status = 'REDEEMED' WHERE user_id = ?", (str(user_id),))
            cur.execute("INSERT INTO webauthn_challenges VALUES (?, ?, 'USER_ENROLLMENT', ?, ?, ?, ?, NULL, ?)",
                        (challenge_id, str(user_id), rp_id, origin, ceremony_state, expires_at.isoformat(), now.isoformat()))

    def challenge_subject(self, challenge_id: str, purpose: str):
        row = self._conn.execute("SELECT u.* FROM users u JOIN webauthn_challenges c ON c.user_id = u.user_id WHERE c.challenge_id = ? AND c.purpose = ?", (challenge_id, purpose)).fetchone()
        if row is None:
            raise SecurityStoreError("Unknown ceremony")
        return row

    def credential_subject(self, credential_id: bytes):
        row = self._conn.execute("SELECT u.* FROM users u JOIN webauthn_credentials c ON c.user_id = u.user_id WHERE c.credential_id = ? AND c.enabled = 1 AND c.revoked = 0", (credential_id,)).fetchone()
        if row is None:
            raise SecurityStoreError("Credential unavailable")
        return row

    def complete_user_enrollment(self, *, user_id: UUID, challenge_id: str, credential_id: bytes, rp_id: str,
                                 credential_data: bytes, sign_count: int, label: str):
        now = _utc_now()
        with self._transaction() as cur:
            user = cur.execute("SELECT * FROM users WHERE user_id = ?", (str(user_id),)).fetchone()
            generation = cur.execute("SELECT 1 FROM webauthn_challenges c JOIN activation_issuances a ON a.user_id = c.user_id AND a.redeemed_at_utc = c.created_at_utc WHERE c.challenge_id = ? AND a.status = 'REDEEMED' AND NOT EXISTS (SELECT 1 FROM activation_issuances newer WHERE newer.user_id = a.user_id AND newer.issued_at_utc > a.issued_at_utc)", (challenge_id,)).fetchone()
            if (user is None or user["role"] != "USER" or user["lifecycle"] != "ACTIVE"
                    or user["account_status"] != "PENDING" or user["activation_status"] != "REDEEMED"
                    or user["service_started_at"] is not None or generation is None):
                raise SecurityStoreError("Enrollment unavailable")
            expiry = compute_service_expiry(now, user["service_term_type"], user["custom_term_value"], user["custom_term_unit"])
            cur.execute("INSERT INTO webauthn_credentials (credential_id, user_id, rp_id, credential_data, sign_count, label, is_backup_hardware, enabled, revoked, created_at_utc) VALUES (?, ?, ?, ?, ?, ?, 0, 1, 0, ?)",
                        (credential_id, str(user_id), rp_id, credential_data, sign_count, label, now.isoformat()))
            cur.execute("UPDATE users SET account_status = 'ACTIVE', service_status = 'ACTIVE', service_started_at = ?, service_expires_at = ? WHERE user_id = ?",
                        (now.isoformat(), expiry.isoformat() if expiry else None, str(user_id)))

    def ensure_user(
        self,
        *,
        user_id: UUID,
        role: str,
        lifecycle: str,
        display_name: str,
        sx_id: str | None = None,
        account_status: str | None = None,
        activation_status: str | None = None,
        service_status: str | None = None,
        service_started_at: datetime | str | None = None,
        service_expires_at: datetime | str | None = None,
        service_term_type: str | None = None,
        custom_term_value: int | None = None,
    ) -> None:
        now_str = _utc_now().isoformat()
        derived_sx_id = sx_id or f"SX-U-{str(user_id)[:4].upper()}-{str(user_id)[-4].upper()}"
        derived_account_status = account_status or ("ACTIVE" if lifecycle == "ACTIVE" else "SUSPENDED")
        derived_activation_status = activation_status or "REDEEMED"
        derived_service_status = service_status or ("ACTIVE" if role == "OWNER" else "ACTIVE")
        derived_service_started_at = (
            service_started_at.isoformat() if isinstance(service_started_at, datetime)
            else service_started_at if service_started_at
            else now_str
        )
        derived_service_expires_at = (
            service_expires_at.isoformat() if isinstance(service_expires_at, datetime)
            else service_expires_at
        )
        derived_service_term_type = service_term_type or "LIFETIME"
        with self._transaction() as cur:
            cur.execute(
                """INSERT INTO users(
                    user_id, role, lifecycle, display_name, created_at_utc, security_state,
                    sx_id, account_status, activation_status, service_status,
                    service_started_at, service_expires_at, service_term_type, custom_term_value
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    role = excluded.role,
                    lifecycle = excluded.lifecycle,
                    display_name = excluded.display_name,
                    sx_id = coalesce(users.sx_id, excluded.sx_id),
                    account_status = coalesce(excluded.account_status, users.account_status),
                    activation_status = coalesce(excluded.activation_status, users.activation_status),
                    service_status = coalesce(excluded.service_status, users.service_status),
                    service_started_at = coalesce(excluded.service_started_at, users.service_started_at),
                    service_expires_at = excluded.service_expires_at,
                    service_term_type = coalesce(excluded.service_term_type, users.service_term_type),
                    custom_term_value = coalesce(excluded.custom_term_value, users.custom_term_value)
                """,
                (
                    str(user_id), role, lifecycle, display_name, now_str, "ACTIVE",
                    derived_sx_id, derived_account_status, derived_activation_status, derived_service_status,
                    derived_service_started_at, derived_service_expires_at, derived_service_term_type, custom_term_value
                ),
            )

    def save_challenge(self, *, challenge_id: str, user_id: UUID, purpose: str, rp_id: str,
                       origin: str, ceremony_state: str, expires_at: datetime) -> None:
        with self._transaction() as cur:
            cur.execute(
                "INSERT INTO webauthn_challenges VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)",
                (challenge_id, str(user_id), purpose, rp_id, origin, ceremony_state,
                 expires_at.isoformat(), _utc_now().isoformat()),
            )

    def consume_challenge(self, *, challenge_id: str, user_id: UUID, purpose: str,
                          now: datetime | None = None) -> sqlite3.Row:
        now = now or _utc_now()
        with self._transaction() as cur:
            row = cur.execute("SELECT * FROM webauthn_challenges WHERE challenge_id = ?", (challenge_id,)).fetchone()
            if row is None or row["user_id"] != str(user_id) or row["purpose"] != purpose:
                raise SecurityStoreError("unknown or mismatched WebAuthn challenge")
            if row["consumed_at_utc"] is not None:
                raise SecurityStoreError("WebAuthn challenge replay detected")
            if datetime.fromisoformat(row["expires_at_utc"]) <= now:
                raise SecurityStoreError("WebAuthn challenge expired")
            if cur.execute("UPDATE webauthn_challenges SET consumed_at_utc = ? WHERE challenge_id = ? AND consumed_at_utc IS NULL", (now.isoformat(), challenge_id)).rowcount != 1:
                raise SecurityStoreError("WebAuthn challenge replay detected")
            return row

    def add_credential(self, *, credential_id: bytes, user_id: UUID, rp_id: str,
                       credential_data: bytes, sign_count: int, label: str,
                       is_backup_hardware: bool) -> None:
        with self._transaction() as cur:
            user = cur.execute("SELECT * FROM users WHERE user_id = ?", (str(user_id),)).fetchone()
            if user is None or user["lifecycle"] != "ACTIVE" or user["account_status"] != "ACTIVE":
                raise SecurityStoreError("Enrollment unavailable")
            active_count = cur.execute(
                "SELECT count(*) as c FROM webauthn_credentials WHERE user_id = ? AND enabled = 1 AND revoked = 0",
                (str(user_id),),
            ).fetchone()["c"]
            if active_count >= 3:
                raise SecurityStoreError("Maximum 3 active registered devices quota reached. Explicitly revoke an existing device to register a new one.")
            cur.execute(
                "INSERT INTO webauthn_credentials (credential_id, user_id, rp_id, credential_data, sign_count, label, is_backup_hardware, enabled, revoked, created_at_utc, last_used_at_utc) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, ?, NULL)",
                (credential_id, str(user_id), rp_id, credential_data, sign_count, label,
                 int(is_backup_hardware), _utc_now().isoformat()),
            )

    def credentials_for(self, *, user_id: UUID, rp_id: str) -> tuple[sqlite3.Row, ...]:
        return tuple(self._conn.execute("SELECT * FROM webauthn_credentials WHERE user_id = ? AND rp_id = ? AND enabled = 1 AND revoked = 0", (str(user_id), rp_id)).fetchall())

    def credential_count_ready(self, *, user_id: UUID, rp_id: str) -> bool:
        rows = self.credentials_for(user_id=user_id, rp_id=rp_id)
        return len(rows) >= 2 and any(row["is_backup_hardware"] for row in rows)

    def credential_status(self, *, user_id: UUID, rp_id: str) -> str:
        rows = self.credentials_for(user_id=user_id, rp_id=rp_id)
        if not rows:
            return "NOT_CONFIGURED"
        return "CONFIGURED" if self.credential_count_ready(user_id=user_id, rp_id=rp_id) else "NEEDS_ROTATION"

    def create_owner_bootstrap(self, *, user_id: UUID, expires_at: datetime) -> str:
        """Trusted-host helper: returns a one-time secret exactly once."""
        if self._conn.execute("SELECT 1 FROM webauthn_credentials WHERE user_id = ? AND enabled = 1 AND revoked = 0", (str(user_id),)).fetchone():
            raise SecurityStoreError("owner already has a credential; bootstrap forbidden")
        token = secrets.token_urlsafe(48)
        with self._transaction() as cur:
            cur.execute("INSERT INTO bootstrap_authorizations VALUES (?, ?, ?, NULL, ?)", (self.token_hash(token), str(user_id), expires_at.isoformat(), _utc_now().isoformat()))
        return token

    def consume_owner_bootstrap(self, *, token: str, user_id: UUID, now: datetime | None = None) -> None:
        now = now or _utc_now()
        with self._transaction() as cur:
            row = cur.execute("SELECT * FROM bootstrap_authorizations WHERE token_hash = ?", (self.token_hash(token),)).fetchone()
            if row is None or row["user_id"] != str(user_id):
                raise SecurityStoreError("invalid bootstrap authorization")
            if row["consumed_at_utc"] is not None:
                raise SecurityStoreError("bootstrap authorization replay detected")
            if datetime.fromisoformat(row["expires_at_utc"]) <= now:
                raise SecurityStoreError("bootstrap authorization expired")
            if cur.execute("SELECT 1 FROM webauthn_credentials WHERE user_id = ? AND enabled = 1 AND revoked = 0", (str(user_id),)).fetchone():
                raise SecurityStoreError("owner credential already established; bootstrap forbidden")
            if cur.execute("UPDATE bootstrap_authorizations SET consumed_at_utc = ? WHERE token_hash = ? AND consumed_at_utc IS NULL", (now.isoformat(), self.token_hash(token))).rowcount != 1:
                raise SecurityStoreError("bootstrap authorization replay detected")

    def validate_owner_bootstrap(self, *, token: str, user_id: UUID, now: datetime | None = None) -> None:
        """Validate without consuming; completion consumes in the same browser flow."""
        now = now or _utc_now()
        row = self._conn.execute("SELECT * FROM bootstrap_authorizations WHERE token_hash = ?", (self.token_hash(token),)).fetchone()
        if row is None or row["user_id"] != str(user_id) or row["consumed_at_utc"] is not None:
            raise SecurityStoreError("invalid or replayed bootstrap authorization")
        if datetime.fromisoformat(row["expires_at_utc"]) <= now or self._conn.execute("SELECT 1 FROM webauthn_credentials WHERE user_id = ? AND enabled = 1 AND revoked = 0", (str(user_id),)).fetchone():
            raise SecurityStoreError("expired or no-longer-eligible bootstrap authorization")

    def update_sign_count(self, *, credential_id: bytes, previous: int, current: int) -> None:
        if previous and current <= previous:
            raise SecurityStoreError("authenticator sign-count rollback detected")
        with self._transaction() as cur:
            if cur.execute("UPDATE webauthn_credentials SET sign_count = ?, last_used_at_utc = ? WHERE credential_id = ? AND sign_count = ? AND enabled = 1 AND revoked = 0", (current, _utc_now().isoformat(), credential_id, previous)).rowcount != 1:
                raise SecurityStoreError("unknown WebAuthn credential")

    def set_credential_state(self, *, credential_id: bytes, disabled: bool = False,
                             revoked: bool = False) -> bool:
        """Non-destructive lifecycle transition; revocation is terminal."""
        if disabled and revoked:
            raise SecurityStoreError("credential cannot be disabled and revoked together")
        with self._transaction() as cur:
            row = cur.execute("SELECT enabled, revoked, user_id FROM webauthn_credentials WHERE credential_id = ?", (credential_id,)).fetchone()
            if row is None:
                raise SecurityStoreError("unknown WebAuthn credential")
            if row["revoked"]:
                return False
            if revoked:
                cur.execute("UPDATE webauthn_credentials SET enabled = 0, revoked = 1, revoked_at_utc = ? WHERE credential_id = ?", (_utc_now().isoformat(), credential_id))
                cur.execute("UPDATE sessions SET revoked_at_utc = ? WHERE user_id = ? AND revoked_at_utc IS NULL", (_utc_now().isoformat(), row["user_id"]))
                return True
            if disabled:
                cur.execute("UPDATE sessions SET revoked_at_utc = ? WHERE user_id = ? AND revoked_at_utc IS NULL", (_utc_now().isoformat(), row["user_id"]))
            target = 0 if disabled else 1
            if row["enabled"] == target:
                return False
            cur.execute("UPDATE webauthn_credentials SET enabled = ? WHERE credential_id = ?", (target, credential_id))
            return True

    @staticmethod
    def token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def save_session(self, *, token: str, user_id: UUID, route: str, risk: str,
                     expires_at: datetime, step_up_satisfied: bool, credential_id: bytes | None = None) -> None:
        """Persist only a SHA-256 verifier; bearer plaintext never reaches disk."""
        with self._transaction() as cur:
            user = cur.execute("SELECT * FROM users WHERE user_id = ?", (str(user_id),)).fetchone()
            if (user is None or user["lifecycle"] != "ACTIVE" or user["account_status"] != "ACTIVE"
                    or user["activation_status"] != "REDEEMED"):
                raise SecurityStoreError("Session unavailable")
            if credential_id is not None and not cur.execute("SELECT 1 FROM webauthn_credentials WHERE credential_id = ? AND user_id = ? AND enabled = 1 AND revoked = 0", (credential_id, str(user_id))).fetchone():
                raise SecurityStoreError("Credential unavailable")
            cur.execute(
                "INSERT INTO sessions(token_hash, user_id, route, risk, expires_at_utc, revoked_at_utc, created_at_utc, step_up_satisfied) VALUES (?, ?, ?, ?, ?, NULL, ?, ?)",
                (self.token_hash(token), str(user_id), route, risk, expires_at.isoformat(), _utc_now().isoformat(), int(step_up_satisfied)),
            )

    def load_session(self, token: str) -> sqlite3.Row | None:
        return self._conn.execute(
            """SELECT s.*, u.role, u.lifecycle, u.display_name,
                      u.sx_id, u.account_status, u.activation_status,
                      u.service_status, u.service_started_at, u.service_expires_at,
                      u.service_term_type, u.custom_term_value, u.custom_term_unit,
                      u.bound_email, u.bound_phone, u.notes, u.plan, u.created_by
               FROM sessions s
               JOIN users u ON u.user_id = s.user_id
               WHERE s.token_hash = ?""",
            (self.token_hash(token),),
        ).fetchone()

    def get_user(self, user_id: UUID | str) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM users WHERE user_id = ?", (str(user_id),)).fetchone()

    def find_user_by_identifier(self, identifier: str | UUID) -> sqlite3.Row | None:
        ident_str = str(identifier).strip()
        return self._conn.execute(
            "SELECT * FROM users WHERE user_id = ? OR UPPER(sx_id) = UPPER(?) OR LOWER(bound_email) = LOWER(?)",
            (ident_str, ident_str, ident_str),
        ).fetchone()

    def get_user_issuances(self, user_id: str | UUID) -> tuple[sqlite3.Row, ...]:
        return tuple(
            self._conn.execute(
                "SELECT * FROM activation_issuances WHERE user_id = ? ORDER BY issued_at_utc ASC",
                (str(user_id),),
            ).fetchall()
        )

    def list_users(self) -> tuple[sqlite3.Row, ...]:
        return tuple(self._conn.execute("SELECT * FROM users ORDER BY created_at_utc ASC").fetchall())

    def create_user_access(
        self,
        *,
        user_id: UUID | None = None,
        display_name: str,
        email: str,
        phone: str = "",
        role: str = "USER",
        plan: str = "Quant Professional",
        service_term_type: str = "3_MONTHS",
        custom_term_value: int | None = None,
        custom_term_unit: str | None = None,
        is_draft: bool = False,
        actor: str = "OWNER-001",
        notes: str = "Owner-created access record",
        operation_id: str | None = None,
        allow_idempotent_onboarding: bool = False,
    ) -> tuple[dict, str | None]:
        uid = user_id or uuid4()
        clean_email = email.strip().lower() if email else ""
        sx_id = _generate_canonical_sx_id()
        now = _utc_now()
        now_str = now.isoformat()

        if is_draft:
            act_status = "DRAFT"
            acct_status = "PENDING"
            srv_status = "NOT_STARTED"
            code = None
            exp_str = None
        else:
            act_status = "INVITED"
            acct_status = "PENDING"
            srv_status = "NOT_STARTED"
            code = _generate_canonical_activation_code()
            code_hash = _hash_activation_code(code)
            exp_dt = now + timedelta(hours=24)
            exp_str = exp_dt.isoformat()

        effective_op_id = operation_id or (f"user-create-{clean_email}" if clean_email else f"user-create-{uid}")

        with self._transaction() as cur:
            # DB-003: Controlled domain pre-check for duplicate identity
            if clean_email:
                existing_row = cur.execute(
                    "SELECT * FROM users WHERE LOWER(TRIM(bound_email)) = ? LIMIT 1",
                    (clean_email,),
                ).fetchone()
                if existing_row is not None:
                    # Check if this pending unredeemed user can be recovered idempotently
                    cred_count = cur.execute(
                        "SELECT COUNT(*) as c FROM webauthn_credentials WHERE user_id = ? AND enabled = 1",
                        (existing_row["user_id"],),
                    ).fetchone()["c"]
                    if (
                        allow_idempotent_onboarding
                        and existing_row["account_status"] == "PENDING"
                        and existing_row["activation_status"] in ("INVITED", "DRAFT")
                        and cred_count == 0
                    ):
                        target_uid = existing_row["user_id"]
                        target_sx_id = existing_row["sx_id"]
                        # Invalidate prior unredeemed issuances
                        cur.execute(
                            "UPDATE activation_issuances SET status = 'EXPIRED' WHERE user_id = ? AND status = 'INVITED'",
                            (target_uid,),
                        )
                        fresh_code = None
                        fresh_exp_str = None
                        if not is_draft:
                            fresh_code = _generate_canonical_activation_code()
                            fresh_code_hash = _hash_activation_code(fresh_code)
                            fresh_exp_dt = now + timedelta(hours=24)
                            fresh_exp_str = fresh_exp_dt.isoformat()
                            iss_id = f"iss-{str(uuid4())[:8]}"
                            cur.execute(
                                """INSERT INTO activation_issuances(
                                    issuance_id, user_id, code_hash, status,
                                    issued_at_utc, expires_at_utc, redeemed_at_utc, revoked_at_utc,
                                    actor, notes
                                ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)""",
                                (iss_id, target_uid, fresh_code_hash, "INVITED", now_str, fresh_exp_str, actor, "Idempotent onboarding fresh 24h code"),
                            )
                            cur.execute("UPDATE users SET activation_status = 'INVITED' WHERE user_id = ?", (target_uid,))
                        # Update outbox record
                        cur.execute(
                            """
                            INSERT INTO security_mutation_outbox (
                                operation_id, user_id, action, resource_id, payload_json,
                                stage_state, created_at_utc, updated_at_utc
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(operation_id) DO UPDATE SET
                                stage_state = excluded.stage_state,
                                updated_at_utc = excluded.updated_at_utc
                            """,
                            (
                                effective_op_id, target_uid, "USER_ACCESS_CREATED", target_uid,
                                json.dumps({"user_id": target_uid, "sx_id": target_sx_id, "email": clean_email}),
                                "COMMITTED_PENDING_AUDIT", now_str, now_str
                            ),
                        )
                        record = {
                            "user_id": target_uid,
                            "sx_id": target_sx_id,
                            "display_name": existing_row["display_name"],
                            "email": existing_row["bound_email"],
                            "phone": existing_row["bound_phone"],
                            "role": existing_row["role"],
                            "plan": existing_row["plan"],
                            "activation_status": "INVITED" if not is_draft else existing_row["activation_status"],
                            "account_status": existing_row["account_status"],
                            "service_status": existing_row["service_status"],
                            "service_term_type": existing_row["service_term_type"],
                            "custom_term_value": existing_row["custom_term_value"],
                            "custom_term_unit": existing_row["custom_term_unit"],
                            "created_at_utc": existing_row["created_at_utc"],
                            "expires_at_utc": fresh_exp_str or existing_row.get("service_expires_at"),
                            "notes": existing_row["notes"],
                            "created_by": existing_row["created_by"],
                        }
                        return record, fresh_code
                    else:
                        raise SecurityStoreError(f"A user with email '{clean_email}' already exists")

            clean_sx_id = sx_id.strip().upper()
            for _ in range(5):
                existing_sx = cur.execute(
                    "SELECT user_id FROM users WHERE UPPER(TRIM(sx_id)) = ? LIMIT 1",
                    (clean_sx_id,),
                ).fetchone()
                if existing_sx is None:
                    break
                sx_id = _generate_canonical_sx_id()
                clean_sx_id = sx_id.strip().upper()
            else:
                raise SecurityStoreError("Failed to generate a unique SentinelX identifier")

            try:
                cur.execute(
                    """INSERT INTO users(
                        user_id, role, lifecycle, display_name, created_at_utc, security_state,
                        sx_id, account_status, activation_status, service_status,
                        service_started_at, service_expires_at, service_term_type,
                        custom_term_value, custom_term_unit, bound_email, bound_phone,
                        notes, plan, created_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(uid), role, "ACTIVE", display_name.strip(), now_str, "ACTIVE",
                        clean_sx_id, acct_status, act_status, srv_status,
                        None, None, service_term_type,
                        custom_term_value, custom_term_unit, clean_email, phone.strip(),
                        notes, plan, actor
                    ),
                )
            except sqlite3.IntegrityError as err:
                err_lower = str(err).lower()
                if "bound_email" in err_lower or "idx_users_bound_email" in err_lower:
                    if allow_idempotent_onboarding and clean_email:
                        conflicting = cur.execute(
                            "SELECT * FROM users WHERE LOWER(TRIM(bound_email)) = ? LIMIT 1",
                            (clean_email,),
                        ).fetchone()
                        if conflicting is not None:
                            cred_count = cur.execute(
                                "SELECT COUNT(*) as c FROM webauthn_credentials WHERE user_id = ? AND enabled = 1",
                                (conflicting["user_id"],),
                            ).fetchone()["c"]
                            if (
                                conflicting["account_status"] == "PENDING"
                                and conflicting["activation_status"] in ("INVITED", "DRAFT")
                                and cred_count == 0
                            ):
                                target_uid = conflicting["user_id"]
                                target_sx_id = conflicting["sx_id"]
                                cur.execute(
                                    "UPDATE activation_issuances SET status = 'EXPIRED' WHERE user_id = ? AND status = 'INVITED'",
                                    (target_uid,),
                                )
                                fresh_code = None
                                fresh_exp_str = None
                                if not is_draft:
                                    fresh_code = _generate_canonical_activation_code()
                                    fresh_code_hash = _hash_activation_code(fresh_code)
                                    fresh_exp_dt = now + timedelta(hours=24)
                                    fresh_exp_str = fresh_exp_dt.isoformat()
                                    iss_id = f"iss-{str(uuid4())[:8]}"
                                    cur.execute(
                                        """INSERT INTO activation_issuances(
                                            issuance_id, user_id, code_hash, status,
                                            issued_at_utc, expires_at_utc, redeemed_at_utc, revoked_at_utc,
                                            actor, notes
                                        ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)""",
                                        (iss_id, target_uid, fresh_code_hash, "INVITED", now_str, fresh_exp_str, actor, "Concurrent idempotent onboarding fresh 24h code"),
                                    )
                                    cur.execute("UPDATE users SET activation_status = 'INVITED' WHERE user_id = ?", (target_uid,))
                                cur.execute(
                                    """
                                    INSERT INTO security_mutation_outbox (
                                        operation_id, user_id, action, resource_id, payload_json,
                                        stage_state, created_at_utc, updated_at_utc
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                    ON CONFLICT(operation_id) DO UPDATE SET
                                        stage_state = excluded.stage_state,
                                        updated_at_utc = excluded.updated_at_utc
                                    """,
                                    (
                                        effective_op_id, target_uid, "USER_ACCESS_CREATED", target_uid,
                                        json.dumps({"user_id": target_uid, "sx_id": target_sx_id, "email": clean_email}),
                                        "COMMITTED_PENDING_AUDIT", now_str, now_str
                                    ),
                                )
                                record = {
                                    "user_id": target_uid,
                                    "sx_id": target_sx_id,
                                    "display_name": conflicting["display_name"],
                                    "email": conflicting["bound_email"],
                                    "phone": conflicting["bound_phone"],
                                    "role": conflicting["role"],
                                    "plan": conflicting["plan"],
                                    "activation_status": "INVITED" if not is_draft else conflicting["activation_status"],
                                    "account_status": conflicting["account_status"],
                                    "service_status": conflicting["service_status"],
                                    "service_term_type": conflicting["service_term_type"],
                                    "custom_term_value": conflicting["custom_term_value"],
                                    "custom_term_unit": conflicting["custom_term_unit"],
                                    "created_at_utc": conflicting["created_at_utc"],
                                    "expires_at_utc": fresh_exp_str or conflicting.get("service_expires_at"),
                                    "notes": conflicting["notes"],
                                    "created_by": conflicting["created_by"],
                                }
                                return record, fresh_code
                    raise SecurityStoreError(f"A user with email '{clean_email}' already exists") from err
                if "sx_id" in err_lower or "idx_users_sx_id" in err_lower:
                    raise SecurityStoreError(f"A user with SentinelX ID '{clean_sx_id}' already exists") from err
                raise SecurityStoreError(f"User identity constraint violation: {err}") from err

            if code is not None:
                iss_id = f"iss-{str(uuid4())[:8]}"
                cur.execute(
                    """INSERT INTO activation_issuances(
                        issuance_id, user_id, code_hash, status,
                        issued_at_utc, expires_at_utc, redeemed_at_utc, revoked_at_utc,
                        actor, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)""",
                    (iss_id, str(uid), code_hash, "INVITED", now_str, exp_str, actor, "Initial 24-hour activation code"),
                )

            # Record outbox stage for audit reconciliation
            if not is_draft and (operation_id or allow_idempotent_onboarding):
                cur.execute(
                    """
                    INSERT INTO security_mutation_outbox (
                        operation_id, user_id, action, resource_id, payload_json,
                        stage_state, created_at_utc, updated_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(operation_id) DO UPDATE SET
                        stage_state = excluded.stage_state,
                        updated_at_utc = excluded.updated_at_utc
                    """,
                    (
                        effective_op_id, str(uid), "USER_ACCESS_CREATED", str(uid),
                        json.dumps({"user_id": str(uid), "sx_id": sx_id, "email": clean_email}),
                        "COMMITTED_PENDING_AUDIT", now_str, now_str
                    ),
                )

        record = {
            "user_id": str(uid),
            "sx_id": sx_id,
            "display_name": display_name.strip(),
            "email": email.strip().lower(),
            "phone": phone.strip(),
            "role": role,
            "plan": plan,
            "activation_status": act_status,
            "account_status": acct_status,
            "service_status": srv_status,
            "service_term_type": service_term_type,
            "custom_term_value": custom_term_value,
            "custom_term_unit": custom_term_unit,
            "created_at_utc": now_str,
            "expires_at_utc": exp_str,
            "notes": notes,
            "created_by": actor,
        }
        return record, code

    def reissue_activation_code(
        self,
        identifier: str | UUID,
        *,
        actor: str = "OWNER-001",
        notes: str = "Reissued 24h activation code",
    ) -> tuple[dict, str]:
        user = self.find_user_by_identifier(identifier)
        if user is None:
            raise SecurityStoreError("User access record not found")

        if user["account_status"] == "REVOKED":
            raise SecurityStoreError("Cannot reissue activation for a revoked account")
        if user["account_status"] == "SUSPENDED":
            raise SecurityStoreError("Cannot reissue activation for a suspended account")

        now = _utc_now()
        now_str = now.isoformat()
        code = _generate_canonical_activation_code()
        code_hash = _hash_activation_code(code)
        exp_dt = now + timedelta(hours=24)
        exp_str = exp_dt.isoformat()

        with self._transaction() as cur:
            # Mark prior unredeemed invitations expired
            cur.execute(
                "UPDATE activation_issuances SET status = 'EXPIRED' WHERE user_id = ? AND status = 'INVITED'",
                (user["user_id"],),
            )
            iss_id = f"iss-{str(uuid4())[:8]}"
            cur.execute(
                """INSERT INTO activation_issuances(
                    issuance_id, user_id, code_hash, status,
                    issued_at_utc, expires_at_utc, redeemed_at_utc, revoked_at_utc,
                    actor, notes
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)""",
                (iss_id, user["user_id"], code_hash, "INVITED", now_str, exp_str, actor, notes),
            )
            cur.execute(
                "UPDATE users SET activation_status = 'INVITED' WHERE user_id = ?",
                (user["user_id"],),
            )

        return {
            "user_id": user["user_id"],
            "sx_id": user["sx_id"],
            "activation_status": "INVITED",
            "expires_at_utc": exp_str,
        }, code

    def revoke_activation_code(
        self,
        identifier: str | UUID,
        *,
        actor: str = "OWNER-001",
        notes: str = "Activation invitation revoked",
    ) -> bool:
        user = self.find_user_by_identifier(identifier)
        if user is None:
            raise SecurityStoreError("User access record not found")

        now_str = _utc_now().isoformat()
        with self._transaction() as cur:
            cur.execute(
                "UPDATE activation_issuances SET status = 'REVOKED', revoked_at_utc = ? WHERE user_id = ? AND status = 'INVITED'",
                (now_str, user["user_id"]),
            )
            cur.execute(
                "UPDATE users SET activation_status = 'REVOKED' WHERE user_id = ?",
                (user["user_id"],),
            )
        return True

    def suspend_user_account(
        self,
        identifier: str | UUID,
        *,
        actor: str = "OWNER-001",
        notes: str = "Account suspended",
    ) -> bool:
        user = self.find_user_by_identifier(identifier)
        if user is None:
            raise SecurityStoreError("User access record not found")
        if user["account_status"] == "REVOKED":
            raise SecurityStoreError("Cannot suspend a revoked account")

        now_str = _utc_now().isoformat()
        with self._transaction() as cur:
            cur.execute(
                "UPDATE users SET account_status = 'SUSPENDED', lifecycle = 'SUSPENDED' WHERE user_id = ?",
                (user["user_id"],),
            )
            cur.execute(
                "UPDATE sessions SET revoked_at_utc = ? WHERE user_id = ? AND revoked_at_utc IS NULL",
                (now_str, user["user_id"]),
            )
        return True

    def restore_user_account(
        self,
        identifier: str | UUID,
        *,
        actor: str = "OWNER-001",
        notes: str = "Account restored",
    ) -> dict:
        user = self.find_user_by_identifier(identifier)
        if user is None:
            raise SecurityStoreError("User access record not found")
        if user["account_status"] == "REVOKED":
            raise SecurityStoreError("Revoked account cannot be restored; revocation is terminal")

        is_redeemed = user["service_started_at"] is not None
        target_account_status = "ACTIVE" if is_redeemed else "PENDING"

        with self._transaction() as cur:
            cur.execute(
                "UPDATE users SET account_status = ?, lifecycle = 'ACTIVE' WHERE user_id = ?",
                (target_account_status, user["user_id"]),
            )
        return {"user_id": user["user_id"], "sx_id": user["sx_id"], "account_status": target_account_status}

    def revoke_user_account(
        self,
        identifier: str | UUID,
        *,
        actor: str = "OWNER-001",
        notes: str = "Account permanently revoked",
    ) -> bool:
        user = self.find_user_by_identifier(identifier)
        if user is None:
            raise SecurityStoreError("User access record not found")

        now_str = _utc_now().isoformat()
        with self._transaction() as cur:
            cur.execute(
                "UPDATE users SET account_status = 'REVOKED', lifecycle = 'CLOSED' WHERE user_id = ?",
                (user["user_id"],),
            )
            if user["activation_status"] == "INVITED":
                cur.execute(
                    "UPDATE users SET activation_status = 'REVOKED' WHERE user_id = ?",
                    (user["user_id"],),
                )
                cur.execute(
                    "UPDATE activation_issuances SET status = 'REVOKED', revoked_at_utc = ? WHERE user_id = ? AND status = 'INVITED'",
                    (now_str, user["user_id"]),
                )
            cur.execute(
                "UPDATE sessions SET revoked_at_utc = ? WHERE user_id = ? AND revoked_at_utc IS NULL",
                (now_str, user["user_id"]),
            )
        return True

    def extend_service_entitlement(
        self,
        identifier: str | UUID,
        *,
        term_type: str,
        custom_value: int | None = None,
        custom_unit: str | None = None,
        actor: str = "OWNER-001",
        notes: str = "Service entitlement extended",
    ) -> dict:
        user = self.find_user_by_identifier(identifier)
        if user is None:
            raise SecurityStoreError("User access record not found")

        if user["service_term_type"] == "LIFETIME":
            return {"user_id": user["user_id"], "service_expires_at": None, "service_term_type": "LIFETIME"}

        now = _utc_now()
        # If not started, update the configured term type
        if user["service_status"] == "NOT_STARTED" or user["service_expires_at"] is None:
            with self._transaction() as cur:
                cur.execute(
                    "UPDATE users SET service_term_type = ?, custom_term_value = ?, custom_term_unit = ? WHERE user_id = ?",
                    (term_type, custom_value, custom_unit, user["user_id"]),
                )
            return {"user_id": user["user_id"], "service_expires_at": None, "service_term_type": term_type}

        # Check if already expired
        current_exp = datetime.fromisoformat(user["service_expires_at"])
        if current_exp.tzinfo is None:
            current_exp = current_exp.replace(tzinfo=timezone.utc)

        if now >= current_exp:
            raise SecurityStoreError("Cannot extend expired service entitlement; use renewal instead")

        # Active: append to current_exp (OD-AUTH-21)
        new_exp = compute_service_expiry(current_exp, term_type, custom_value, custom_unit)
        new_exp_str = new_exp.isoformat() if new_exp else None

        with self._transaction() as cur:
            cur.execute(
                "UPDATE users SET service_expires_at = ? WHERE user_id = ?",
                (new_exp_str, user["user_id"]),
            )
        return {"user_id": user["user_id"], "service_expires_at": new_exp_str, "service_term_type": user["service_term_type"]}

    def renew_service_entitlement(
        self,
        identifier: str | UUID,
        *,
        term_type: str,
        custom_value: int | None = None,
        custom_unit: str | None = None,
        actor: str = "OWNER-001",
        notes: str = "Service entitlement renewed",
    ) -> dict:
        user = self.find_user_by_identifier(identifier)
        if user is None:
            raise SecurityStoreError("User access record not found")

        now = _utc_now()
        now_str = now.isoformat()
        new_exp = compute_service_expiry(now, term_type, custom_value, custom_unit)
        new_exp_str = new_exp.isoformat() if new_exp else None

        with self._transaction() as cur:
            cur.execute(
                """UPDATE users SET
                    service_started_at = ?,
                    service_expires_at = ?,
                    service_status = 'ACTIVE',
                    service_term_type = ?,
                    custom_term_value = ?,
                    custom_term_unit = ?
                WHERE user_id = ?""",
                (now_str, new_exp_str, term_type, custom_value, custom_unit, user["user_id"]),
            )
        return {
            "user_id": user["user_id"],
            "service_started_at": now_str,
            "service_expires_at": new_exp_str,
            "service_status": "ACTIVE",
            "service_term_type": term_type,
        }

    def convert_to_lifetime_entitlement(
        self,
        identifier: str | UUID,
        *,
        actor: str = "OWNER-001",
        notes: str = "Converted to Lifetime",
    ) -> dict:
        user = self.find_user_by_identifier(identifier)
        if user is None:
            raise SecurityStoreError("User access record not found")

        with self._transaction() as cur:
            cur.execute(
                "UPDATE users SET service_term_type = 'LIFETIME', service_expires_at = NULL WHERE user_id = ?",
                (user["user_id"],),
            )
        return {"user_id": user["user_id"], "service_term_type": "LIFETIME", "service_expires_at": None}

    def delete_draft_user(
        self,
        identifier: str | UUID,
        *,
        actor: str = "OWNER-001",
    ) -> bool:
        user = self.find_user_by_identifier(identifier)
        if user is None:
            raise SecurityStoreError("User access record not found")
        if user["activation_status"] != "DRAFT":
            raise SecurityStoreError("Only draft records can be deleted")

        uid = str(user["user_id"])
        with self._transaction() as cur:
            # 1. Audit / legal retention checks: fail closed if immutable or operational evidence exists
            has_audit = cur.execute(
                "SELECT 1 FROM security_event_references WHERE user_id = ? LIMIT 1", (uid,)
            ).fetchone()
            if has_audit:
                raise SecurityStoreError("Cannot delete draft user with immutable security audit references")

            has_outbox = cur.execute(
                "SELECT 1 FROM security_mutation_outbox WHERE user_id = ? LIMIT 1", (uid,)
            ).fetchone()
            if has_outbox:
                raise SecurityStoreError("Cannot delete draft user with recorded mutation outbox history")

            has_creds = cur.execute(
                "SELECT 1 FROM webauthn_credentials WHERE user_id = ? LIMIT 1", (uid,)
            ).fetchone()
            if has_creds:
                raise SecurityStoreError("Cannot delete draft user with enrolled WebAuthn credentials")

            has_conns = cur.execute(
                "SELECT 1 FROM user_connections WHERE user_id = ? LIMIT 1", (uid,)
            ).fetchone()
            if has_conns:
                raise SecurityStoreError("Cannot delete draft user with configured broker connections")

            has_deployments = cur.execute(
                "SELECT 1 FROM strategy_deployments WHERE user_id = ? LIMIT 1", (uid,)
            ).fetchone()
            if has_deployments:
                raise SecurityStoreError("Cannot delete draft user with strategy deployments")

            has_jobs = cur.execute(
                "SELECT 1 FROM walkforward_jobs WHERE user_id = ? LIMIT 1", (uid,)
            ).fetchone()
            if has_jobs:
                raise SecurityStoreError("Cannot delete draft user with walk-forward jobs")

            redeemed_issuance = cur.execute(
                "SELECT 1 FROM activation_issuances WHERE user_id = ? AND status = 'REDEEMED' LIMIT 1", (uid,)
            ).fetchone()
            if redeemed_issuance:
                raise SecurityStoreError("Cannot delete draft user with redeemed activation issuance")

            # 2. Delete safe draft-lifecycle dependent records inside the same transaction
            cur.execute("DELETE FROM user_strategy_assignments WHERE user_id = ?", (uid,))
            cur.execute("DELETE FROM strategy_connection_mappings WHERE user_id = ?", (uid,))
            cur.execute("DELETE FROM activation_issuances WHERE user_id = ?", (uid,))
            cur.execute("DELETE FROM webauthn_challenges WHERE user_id = ?", (uid,))
            cur.execute("DELETE FROM bootstrap_authorizations WHERE user_id = ?", (uid,))
            cur.execute("DELETE FROM sessions WHERE user_id = ?", (uid,))
            cur.execute("DELETE FROM live_readiness_observations WHERE user_id = ?", (uid,))

            # 3. Delete the user row
            try:
                cur.execute("DELETE FROM users WHERE user_id = ?", (uid,))
            except sqlite3.IntegrityError as err:
                raise SecurityStoreError(f"Cannot delete draft user due to integrity constraint: {err}") from err
        return True

    def run_retention_maintenance(
        self,
        *,
        session_retention_days: int = SESSION_HISTORY_RETENTION_DAYS,
        challenge_retention_hours: int = WEBAUTHN_CHALLENGE_RETENTION_HOURS,
        now: datetime | None = None,
    ) -> dict[str, int]:
        """Bounded maintenance: prunes defunct historical sessions and expired/consumed WebAuthn challenges.

        Deletes ONLY:
        1. Revoked sessions older than session_retention_days
        2. Expired non-active sessions older than session_retention_days
        3. Consumed WebAuthn challenges older than challenge_retention_hours
        4. Expired unconsumed WebAuthn challenges older than challenge_retention_hours

        NEVER deletes:
        - Active (non-revoked, unexpired) sessions
        - Active/unexpired WebAuthn challenges
        - Core Audit events or security audit references
        """
        ref_time = now or _utc_now()
        session_cutoff = (ref_time - timedelta(days=session_retention_days)).isoformat()
        challenge_cutoff = (ref_time - timedelta(hours=challenge_retention_hours)).isoformat()

        with self._transaction() as cur:
            # 1. Prune defunct sessions older than retention cutoff (revoked or expired)
            # Active sessions have revoked_at_utc IS NULL AND expires_at_utc > ref_time, so they are never touched.
            deleted_sessions = cur.execute(
                """
                DELETE FROM sessions
                WHERE (revoked_at_utc IS NOT NULL AND revoked_at_utc < ?)
                   OR (revoked_at_utc IS NULL AND expires_at_utc < ?)
                """,
                (session_cutoff, session_cutoff),
            ).rowcount

            # 2. Prune defunct challenges older than challenge cutoff (consumed or expired)
            # Pending valid challenges have consumed_at_utc IS NULL AND expires_at_utc >= ref_time, so they are never touched.
            deleted_challenges = cur.execute(
                """
                DELETE FROM webauthn_challenges
                WHERE (consumed_at_utc IS NOT NULL AND consumed_at_utc < ?)
                   OR (consumed_at_utc IS NULL AND expires_at_utc < ?)
                """,
                (challenge_cutoff, challenge_cutoff),
            ).rowcount

        return {
            "deleted_sessions": deleted_sessions,
            "deleted_challenges": deleted_challenges,
        }

    def revoke_session(self, token: str) -> bool:
        with self._transaction() as cur:
            return cur.execute("UPDATE sessions SET revoked_at_utc = ? WHERE token_hash = ? AND revoked_at_utc IS NULL", (_utc_now().isoformat(), self.token_hash(token))).rowcount == 1

    def resolve_candidate_sessions(self, session_ref: str) -> list[sqlite3.Row]:
        """Resolve active (unrevoked) session rows matching a reference or suffix."""
        clean_ref = session_ref.strip()
        if not clean_ref:
            return []

        # 1. Direct exact token_hash match
        rows = self._conn.execute(
            "SELECT token_hash, user_id FROM sessions WHERE token_hash = ? AND revoked_at_utc IS NULL",
            (clean_ref,),
        ).fetchall()
        if rows:
            return rows

        # 2. Stable session id format: ses-<prefix>
        if clean_ref.lower().startswith("ses-") and not ("****" in clean_ref):
            prefix = clean_ref[4:].lower()
            return self._conn.execute(
                "SELECT token_hash, user_id FROM sessions WHERE LOWER(token_hash) LIKE ? AND revoked_at_utc IS NULL",
                (f"{prefix}%",),
            ).fetchall()

        # 3. Legacy masked reference: SES-****-XXXX (match exact last 4 characters of token_hash)
        if clean_ref.upper().startswith("SES-****-") or ("SES-" in clean_ref.upper() and "****" in clean_ref):
            last_part = clean_ref.upper().split("-")[-1].strip().lower()
            return self._conn.execute(
                "SELECT token_hash, user_id FROM sessions WHERE LOWER(token_hash) LIKE ? AND revoked_at_utc IS NULL",
                (f"%{last_part}",),
            ).fetchall()

        # 4. Direct prefix match if length >= 8
        if len(clean_ref) >= 8:
            return self._conn.execute(
                "SELECT token_hash, user_id FROM sessions WHERE LOWER(token_hash) LIKE ? AND revoked_at_utc IS NULL",
                (f"{clean_ref.lower()}%",),
            ).fetchall()

        return []

    def revoke_session_by_ref(self, session_ref: str) -> dict[str, Any] | None:
        """Revoke a session by its reference.

        Must resolve to EXACTLY ONE active session.
        - 0 matches => returns None
        - 1 match => revokes that exact session and returns info dict
        - >1 matches => raises AmbiguousSessionRefError (fail-closed, 0 mutations)
        """
        candidates = self.resolve_candidate_sessions(session_ref)
        if not candidates:
            return None
        if len(candidates) > 1:
            raise AmbiguousSessionRefError(session_ref, len(candidates))

        target = candidates[0]
        exact_hash = target["token_hash"]
        now_str = _utc_now().isoformat()
        with self._transaction() as cur:
            res = cur.execute(
                "UPDATE sessions SET revoked_at_utc = ? WHERE token_hash = ? AND revoked_at_utc IS NULL",
                (now_str, exact_hash),
            )
            if res.rowcount != 1:
                return None
            return {
                "revoked": True,
                "token_hash": exact_hash,
                "exact_session_id": f"ses-{exact_hash[:8]}",
                "user_id": str(target["user_id"]),
            }

    def revoke_user_sessions(self, user_id: UUID | str) -> int:
        with self._transaction() as cur:
            res = cur.execute("UPDATE sessions SET revoked_at_utc = ? WHERE user_id = ? AND revoked_at_utc IS NULL", (_utc_now().isoformat(), str(user_id)))
            return res.rowcount

    def list_all_sessions(self, *, user_id: UUID | str | None = None, current_token_hash: str | None = None) -> list[dict]:
        """Safe projection of session records. Plaintext tokens and full hashes are NEVER exposed."""
        now = _utc_now()
        now_str = now.isoformat()
        query = """
            SELECT s.token_hash, s.user_id, s.route, s.risk, s.expires_at_utc, s.revoked_at_utc, s.created_at_utc, s.step_up_satisfied,
                   u.display_name, u.sx_id, u.role
            FROM sessions s
            JOIN users u ON u.user_id = s.user_id
        """
        params: list[str] = []
        if user_id is not None:
            query += " WHERE s.user_id = ?"
            params.append(str(user_id))
        query += " ORDER BY s.created_at_utc DESC"

        rows = self._conn.execute(query, params).fetchall()
        result = []
        for r in rows:
            th = r["token_hash"]
            exp_dt = datetime.fromisoformat(r["expires_at_utc"])
            is_revoked = r["revoked_at_utc"] is not None
            is_expired = not is_revoked and exp_dt <= now
            status = "REVOKED" if is_revoked else ("EXPIRED" if is_expired else "ACTIVE")
            short_id = th[:8]
            last_4 = th[-4:].upper()
            session_ref = f"SES-****-{last_4}"
            is_current = bool(current_token_hash and current_token_hash == th)

            result.append({
                "id": f"ses-{short_id}",
                "sessionRef": session_ref,
                "userId": str(r["user_id"]),
                "sxId": r["sx_id"] or f"SX-U-{str(r['user_id'])[:4].upper()}-{str(r['user_id'])[-4:].upper()}",
                "userName": r["display_name"],
                "role": r["role"],
                "deviceRef": "UNAVAILABLE",
                "deviceName": "Session device binding unavailable",
                "ipMasked": "UNAVAILABLE",
                "location": "UNAVAILABLE",
                "authMethod": "FIDO2_WEBAUTHN" if r["route"] == "NORMAL" else "RECOVERY_CEREMONY",
                "isCurrent": is_current,
                "status": status,
                "createdAt": r["created_at_utc"],
                "lastActive": None,
                "expiresAt": r["expires_at_utc"],
                "context": "RECOVERY_ASSURANCE_WINDOW" if r["route"] == "BREAK_GLASS" else "NORMAL",
                "clientType": "UNAVAILABLE",
            })
        return result

    def list_all_devices(self, *, user_id: UUID | str | None = None) -> list[dict]:
        """Safe projection of registered devices. Raw public/private key material is NEVER exposed."""
        query = """
            SELECT c.credential_id, c.user_id, c.rp_id, c.sign_count, c.label,
                   c.is_backup_hardware, c.enabled, c.revoked, c.created_at_utc, c.last_used_at_utc, c.revoked_at_utc,
                   u.display_name, u.sx_id, u.role
            FROM webauthn_credentials c
            JOIN users u ON u.user_id = c.user_id
        """
        params: list[str] = []
        if user_id is not None:
            query += " WHERE c.user_id = ?"
            params.append(str(user_id))
        query += " ORDER BY c.created_at_utc DESC"

        rows = self._conn.execute(query, params).fetchall()

        # Count active sessions per user for the activeSessionCount projection
        active_session_counts: dict[str, int] = {}
        sess_rows = self._conn.execute("SELECT user_id, count(*) as cnt FROM sessions WHERE revoked_at_utc IS NULL AND expires_at_utc > ? GROUP BY user_id", (_utc_now().isoformat(),)).fetchall()
        for s in sess_rows:
            active_session_counts[s["user_id"]] = s["cnt"]

        result = []
        for r in rows:
            cid_bytes: bytes = r["credential_id"]
            cid_hex = cid_bytes.hex() if isinstance(cid_bytes, bytes) else str(cid_bytes)
            short_id = cid_hex[:4].upper()
            last_4 = cid_hex[-4:].upper()
            device_id = f"DEV-{short_id}-{last_4}"
            is_revoked = bool(r["revoked"] or not r["enabled"])
            status = "REVOKED" if is_revoked else "TRUSTED_REGISTERED"
            auth_type = "FIDO2 Security Key (Hardware Backup)" if r["is_backup_hardware"] else "FIDO2 / WebAuthn Hardware Passkey"
            uid_str = str(r["user_id"])

            result.append({
                "id": cid_hex,
                "deviceId": device_id,
                "credentialIdMasked": f"cred-fido2-****-{last_4.lower()}",
                "userId": uid_str,
                "sxId": r["sx_id"] or f"SX-U-{uid_str[:4].upper()}-{uid_str[-4:].upper()}",
                "userName": r["display_name"],
                "deviceName": r["label"] or "Registered Authenticator",
                "platform": r["rp_id"],
                "authenticatorType": auth_type,
                "registeredAt": r["created_at_utc"],
                "lastSeen": r["last_used_at_utc"],
                "status": status,
                "activeSessionCount": active_session_counts.get(uid_str, 0) if status == "TRUSTED_REGISTERED" else 0,
                "sessionCountScope": "USER",
                "deviceAuthority": "WEBAUTHN_CREDENTIAL",
                "revokedAt": r["revoked_at_utc"],
                "revokedReason": "Revoked by Owner authority" if is_revoked else None,
            })
        return result

    def revoke_device(self, credential_id: bytes | str) -> bool:
        """Terminally revoke a registered device / WebAuthn credential."""
        cid = bytes.fromhex(credential_id) if isinstance(credential_id, str) else credential_id
        with self._transaction() as cur:
            row = cur.execute("SELECT enabled, revoked, user_id FROM webauthn_credentials WHERE credential_id = ?", (cid,)).fetchone()
            if row is None:
                raise SecurityStoreError("Device / credential not found")
            if row["revoked"]:
                return False
            cur.execute(
                "UPDATE webauthn_credentials SET enabled = 0, revoked = 1, revoked_at_utc = ? WHERE credential_id = ?",
                (_utc_now().isoformat(), cid),
            )
            # Until sessions carry a per-credential binding, revoke all of this
            # user's sessions atomically; never leave revoked-device authority live.
            cur.execute("UPDATE sessions SET revoked_at_utc = ? WHERE user_id = ? AND revoked_at_utc IS NULL", (_utc_now().isoformat(), row["user_id"]))
            return True

    def revoke_all_user_devices(self, user_id: UUID | str) -> int:
        """Terminally revoke all registered devices for a user."""
        with self._transaction() as cur:
            res = cur.execute(
                "UPDATE webauthn_credentials SET enabled = 0, revoked = 1, revoked_at_utc = ? WHERE user_id = ? AND revoked = 0",
                (_utc_now().isoformat(), str(user_id)),
            )
            count = res.rowcount
            cur.execute("UPDATE sessions SET revoked_at_utc = ? WHERE user_id = ? AND revoked_at_utc IS NULL", (_utc_now().isoformat(), str(user_id)))
            return count

    def save_audit_reference(self, *, event_id: str, user_id: UUID, action: str) -> None:
        with self._transaction() as cur:
            cur.execute("INSERT OR REPLACE INTO security_event_references VALUES (?, ?, ?, ?, ?)",
                        (event_id, str(user_id), action, event_id, _utc_now().isoformat()))

    def save_outbox_stage(
        self,
        operation_id: str,
        user_id: UUID,
        action: str,
        resource_id: str | None,
        payload_json: str,
        stage_state: str,
        intent_event_id: str | None = None,
        applied_event_id: str | None = None,
        error_message: str | None = None,
    ) -> None:
        now = _utc_now().isoformat()
        with self._transaction() as cur:
            cur.execute(
                """
                INSERT INTO security_mutation_outbox (
                    operation_id, user_id, action, resource_id, payload_json,
                    stage_state, created_at_utc, updated_at_utc,
                    intent_event_id, applied_event_id, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(operation_id) DO UPDATE SET
                    stage_state = excluded.stage_state,
                    updated_at_utc = excluded.updated_at_utc,
                    intent_event_id = coalesce(excluded.intent_event_id, security_mutation_outbox.intent_event_id),
                    applied_event_id = coalesce(excluded.applied_event_id, security_mutation_outbox.applied_event_id),
                    error_message = coalesce(excluded.error_message, security_mutation_outbox.error_message)
                """,
                (
                    operation_id, str(user_id), action, resource_id, payload_json,
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
        now = _utc_now().isoformat()
        with self._transaction() as cur:
            cur.execute(
                """
                UPDATE security_mutation_outbox SET
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
            "SELECT * FROM security_mutation_outbox WHERE operation_id = ?", (operation_id,)
        ).fetchone()

    def get_pending_outbox_records(self) -> tuple[sqlite3.Row, ...]:
        return tuple(
            self._conn.execute(
                "SELECT * FROM security_mutation_outbox WHERE stage_state = 'COMMITTED_PENDING_AUDIT' ORDER BY created_at_utc ASC"
            ).fetchall()
        )


    def _seed_owner_governance_if_empty(self, cur: sqlite3.Cursor) -> None:
        strat_count = cur.execute("SELECT COUNT(*) as c FROM owner_strategies").fetchone()["c"]
        if strat_count == 0:
            now_iso = _utc_now().isoformat()
            seeds = [
                (
                    "SX-STRAT-001", "s1", "NIFTY Momentum Reversion", "v2.3.1", "1.0", "PAPER", "Mean Reversion",
                    json.dumps(["NIFTY", "BANKNIFTY"]), json.dumps(["5m", "15m"]), 78.0, 1, "+2.1% sample", 1,
                    "Paper forward evaluation cycle 12 active",
                    "Multi-timeframe mean reversion on NIFTY index options anchored at ATM.",
                    "Alexander Vance", "SX-0009-ALPHA", "CONFORMANT", "ACTIVE",
                    "READY", None, "ALLOWED", None,
                    "READY", None, "ALLOWED", None,
                    "BLOCKED", "Paper forward evaluation in progress (Cycle 12/30; requires contiguous 30-day verified tracking report per ADR §122)", "ALLOWED", None,
                    68.4, -3.8, 2.14, 1.82, 142, 2,
                    json.dumps([
                        {"id": "gov-1", "timestamp": "2026-08-29 14:12 UTC", "actor": "OWNER-001", "action": "ELIGIBILITY_UPDATE", "note": "Approved for Paper forward evaluation following backtest verification (Sharpe 1.82)", "tone": "ok"},
                        {"id": "gov-2", "timestamp": "2026-08-20 10:00 UTC", "actor": "OWNER-001", "action": "CONFORMANCE_VERIFIED", "note": "Static AST scan passed interface_version 1.0 contract", "tone": "ok"},
                    ]),
                    now_iso,
                ),
                (
                    "SX-STRAT-002", "s2", "BankNifty Straddle Harvester", "v1.8.0", "1.0", "PAPER", "Volatility & Greeks",
                    json.dumps(["BANKNIFTY"]), json.dumps(["1m", "5m"]), 71.0, 1, "-0.4% sample", 0,
                    "Owner administrative hold · Regime review",
                    "Weekly delta-neutral automated volatility harvesting with stop-loss protection.",
                    "Alexander Vance", "SX-0009-ALPHA", "CONFORMANT", "ACTIVE",
                    "READY", None, "ALLOWED", None,
                    "READY", None, "HOLD", "Owner administrative hold · Regime review",
                    "BLOCKED", "Paper forward evaluation incomplete.", "ALLOWED", None,
                    52.1, -7.2, 1.42, 1.15, 88, 0,
                    json.dumps([
                        {"id": "gov-3", "timestamp": "2026-08-28 09:30 UTC", "actor": "OWNER-001", "action": "OWNER_HOLD_PLACED", "note": "Placed paper execution on hold pending volatility regime review", "tone": "warn"},
                    ]),
                    now_iso,
                ),
                (
                    "SX-STRAT-003", "s3", "Weekly Expiry Harvester", "v3.0.1", "1.0", "LIVE", "Expiry Scalping",
                    json.dumps(["NIFTY"]), json.dumps(["1m", "3m"]), 85.0, 1, "+4.8% sample", 1,
                    "Live production deployment active",
                    "Zero-DTE options premium decay capture with real-time portfolio stop guards.",
                    "Priya Sharma", "SX-0114-BETA", "CONFORMANT", "ACTIVE",
                    "READY", None, "ALLOWED", None,
                    "READY", None, "ALLOWED", None,
                    "READY", None, "ALLOWED", None,
                    74.2, -2.4, 2.65, 2.41, 210, 3,
                    json.dumps([
                        {"id": "gov-4", "timestamp": "2026-08-25 09:15 UTC", "actor": "OWNER-001", "action": "LIVE_PROMOTED", "note": "Promoted to LIVE after 30-day continuous paper evaluation pass", "tone": "ok"},
                    ]),
                    now_iso,
                ),
                (
                    "SX-STRAT-004", "s4", "ATM Volatility Scalper", "v1.2.0", "1.0", "BACKTEST_ELIGIBLE", "Scalping",
                    json.dumps(["NIFTY", "FINNIFTY"]), json.dumps(["1m"]), 62.0, 0, "-1.2% sample", 0,
                    "Suspended pending backtest calibration",
                    "High-frequency gamma scalping algorithm requiring ultra-low latency.",
                    "Alexander Vance", "SX-0009-ALPHA", "CONFORMANT", "SUSPENDED",
                    "READY", None, "ALLOWED", None,
                    "BLOCKED", "Backtest validation evidence unattached.", "HOLD", "Suspended pending backtest calibration",
                    "BLOCKED", "Backtest stage only.", "HOLD", "Awaiting live approval",
                    45.0, -11.5, 0.95, 0.82, 54, 0,
                    json.dumps([
                        {"id": "gov-5", "timestamp": "2026-08-22 11:00 UTC", "actor": "OWNER-001", "action": "ADMIN_SUSPENDED", "note": "Owner suspended strategy: Suspended pending backtest calibration", "tone": "neg"},
                    ]),
                    now_iso,
                ),
                (
                    "SX-STRAT-005", "s5", "Index Gamma Breakout", "v2.0.4", "1.0", "PAPER", "Breakout",
                    json.dumps(["BANKNIFTY"]), json.dumps(["15m", "30m"]), 74.0, 1, "+1.7% sample", 1,
                    "Paper forward simulation running",
                    "Momentum-based directional gamma breakout targeting morning volatility windows.",
                    "Vikram Malhotra", "SX-0131-BETA", "CONFORMANT", "ACTIVE",
                    "READY", None, "ALLOWED", None,
                    "READY", None, "ALLOWED", None,
                    "BLOCKED", "Paper evaluation cycle 18/30 in progress", "HOLD", "Awaiting live risk budget allocation",
                    61.8, -4.6, 1.88, 1.64, 96, 1,
                    json.dumps([
                        {"id": "gov-6", "timestamp": "2026-08-26 14:00 UTC", "actor": "OWNER-001", "action": "PAPER_APPROVED", "note": "Approved for paper trading simulation", "tone": "ok"},
                    ]),
                    now_iso,
                ),
            ]
            cur.executemany(
                """INSERT INTO owner_strategies (
                    strategy_id, id, name, version, interface_version, stage,
                    category, instruments_json, timeframes_json, quality,
                    evidence_attached, pnl, is_profit, note, description,
                    author, author_sx_id, conformance_status, admin_status,
                    backtest_system_readiness, backtest_system_blocker,
                    backtest_owner_allowance, backtest_owner_hold_reason,
                    paper_system_readiness, paper_system_blocker,
                    paper_owner_allowance, paper_owner_hold_reason,
                    live_system_readiness, live_system_blocker,
                    live_owner_allowance, live_owner_hold_reason,
                    win_rate, max_drawdown, profit_factor, sharpe_ratio,
                    total_trades, active_positions, governance_history_json,
                    updated_at_utc
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                seeds,
            )
            # Fresh seeds carry sample (non-registered) authors: they keep the
            # prior canonical-catalog behavior (GLOBAL) via the same rule as
            # the legacy backfill above.
            cur.execute("""UPDATE owner_strategies SET visibility = 'GLOBAL'
                           WHERE (author IS NULL OR TRIM(author) = ''
                                  OR author NOT IN (SELECT user_id FROM users))""")

        conn_count = cur.execute("SELECT COUNT(*) as c FROM owner_connections").fetchone()["c"]
        if conn_count == 0:
            now_iso = _utc_now().isoformat()
            conn_seeds = [
                (
                    "SX-CONN-ZERODHA-01", "conn-01", "Zerodha Kite Connect Primary", "Zerodha", "Broker", "Live", "ACC-KITE-8821", "ak •••• ••7f",
                    "CONFIGURED", "HEALTHY", 12, "14:02:11 UTC", "ALLOWED", None,
                    json.dumps([
                        {"capability": "HISTORICAL_DATA", "name": "Historical Data", "systemStatus": "READY", "authStatus": "AUTHORIZED", "ownerAllowance": "ALLOWED", "effectiveStatus": "AVAILABLE"},
                        {"capability": "LIVE_MARKET_DATA", "name": "Live Market Data", "systemStatus": "READY", "authStatus": "AUTHORIZED", "ownerAllowance": "ALLOWED", "effectiveStatus": "AVAILABLE"},
                        {"capability": "ORDER_EXECUTION", "name": "Order Execution", "systemStatus": "READY", "authStatus": "AUTHORIZED", "ownerAllowance": "ALLOWED", "effectiveStatus": "AVAILABLE"},
                        {"capability": "PORTFOLIO_READ", "name": "Portfolio Read", "systemStatus": "READY", "authStatus": "AUTHORIZED", "ownerAllowance": "ALLOWED", "effectiveStatus": "AVAILABLE"},
                    ]),
                    json.dumps([
                        {"time": "14:02:11 UTC", "text": "Heartbeat received · Latency 12ms", "tone": "ok"},
                        {"time": "09:15:00 UTC", "text": "Broker session established via TOTP", "tone": "ok"},
                    ]),
                    now_iso,
                ),
                (
                    "SX-CONN-ZERODHA-SBX", "conn-02", "Zerodha Paper Sandbox Bridge", "Zerodha", "Broker", "Paper / Sandbox", "ACC-SBX-1044", "ak •••• ••2a",
                    "CONFIGURED", "HEALTHY", 18, "14:00:00 UTC", "ALLOWED", None,
                    json.dumps([
                        {"capability": "PAPER_TRADING", "name": "Paper Trading", "systemStatus": "READY", "authStatus": "AUTHORIZED", "ownerAllowance": "ALLOWED", "effectiveStatus": "AVAILABLE"},
                        {"capability": "LIVE_MARKET_DATA", "name": "Live Market Data", "systemStatus": "READY", "authStatus": "AUTHORIZED", "ownerAllowance": "ALLOWED", "effectiveStatus": "AVAILABLE"},
                        {"capability": "PORTFOLIO_READ", "name": "Portfolio Read", "systemStatus": "READY", "authStatus": "AUTHORIZED", "ownerAllowance": "ALLOWED", "effectiveStatus": "AVAILABLE"},
                    ]),
                    json.dumps([
                        {"time": "14:00:00 UTC", "text": "Paper execution simulator active", "tone": "ok"},
                    ]),
                    now_iso,
                ),
                (
                    "SX-CONN-GROWW-01", "conn-03", "Groww Capital Connect", "Groww", "Broker", "Both", "ACC-GRW-4412", "gw •••• ••1c",
                    "EXPIRED", "DEGRADED", 145, "10:12:00 UTC", "HOLD", "Owner administrative hold pending daily auth renewal",
                    json.dumps([
                        {"capability": "HISTORICAL_DATA", "name": "Historical Data", "systemStatus": "READY", "authStatus": "AUTHORIZED", "ownerAllowance": "ALLOWED", "effectiveStatus": "BLOCKED", "blockerReason": "Connection placed on administrative hold by Owner."},
                        {"capability": "ORDER_EXECUTION", "name": "Order Execution", "systemStatus": "READY", "authStatus": "EXPIRED", "ownerAllowance": "ALLOWED", "effectiveStatus": "BLOCKED", "blockerReason": "Daily session token expired (401 Unauthorized)"},
                        {"capability": "PORTFOLIO_READ", "name": "Portfolio Read", "systemStatus": "READY", "authStatus": "EXPIRED", "ownerAllowance": "ALLOWED", "effectiveStatus": "BLOCKED", "blockerReason": "Daily session token expired (401 Unauthorized)"},
                    ]),
                    json.dumps([
                        {"time": "10:12:00 UTC", "text": "401 Unauthorized: Session token expired", "tone": "warn"},
                        {"time": "09:15:00 UTC", "text": "Initial session established", "tone": "ok"},
                    ]),
                    now_iso,
                ),
                (
                    "SX-CONN-TRUEDATA-01", "conn-04", "NSE Official TrueData Feed", "TrueData", "Market Data", "Live", "FEED-TD-NSE-09", "td •••• ••88",
                    "CONFIGURED", "HEALTHY", 8, "14:03:00 UTC", "ALLOWED", None,
                    json.dumps([
                        {"capability": "HISTORICAL_DATA", "name": "Historical Data", "systemStatus": "READY", "authStatus": "AUTHORIZED", "ownerAllowance": "ALLOWED", "effectiveStatus": "AVAILABLE"},
                        {"capability": "LIVE_MARKET_DATA", "name": "Live Market Data", "systemStatus": "READY", "authStatus": "AUTHORIZED", "ownerAllowance": "ALLOWED", "effectiveStatus": "AVAILABLE"},
                        {"capability": "ORDER_EXECUTION", "name": "Order Execution", "systemStatus": "UNSUPPORTED", "authStatus": "NOT_CONFIGURED", "ownerAllowance": "ALLOWED", "effectiveStatus": "BLOCKED", "blockerReason": "TrueData is an institutional market data provider; order execution is unsupported"},
                    ]),
                    json.dumps([
                        {"time": "14:03:00 UTC", "text": "Direct multicast feed nominal · Latency 8ms", "tone": "ok"},
                        {"time": "09:00:00 UTC", "text": "Daily historical tick cache synced", "tone": "ok"},
                    ]),
                    now_iso,
                ),
                (
                    "SX-CONN-UPSTOX-01", "conn-05", "Upstox Developer Sandbox", "Upstox", "Broker", "Paper / Sandbox", "ACC-SBX-9912", "ux •••• ••91",
                    "NOT_CONFIGURED", "OFFLINE", 0, "Yesterday 15:30 UTC", "HOLD", "Sandbox endpoint disconnected pending key provisioning",
                    json.dumps([
                        {"capability": "PAPER_TRADING", "name": "Paper Trading", "systemStatus": "OFFLINE", "authStatus": "NOT_CONFIGURED", "ownerAllowance": "HOLD", "effectiveStatus": "BLOCKED", "blockerReason": "Endpoint disconnected"},
                        {"capability": "LIVE_MARKET_DATA", "name": "Live Market Data", "systemStatus": "OFFLINE", "authStatus": "NOT_CONFIGURED", "ownerAllowance": "HOLD", "effectiveStatus": "BLOCKED", "blockerReason": "Endpoint disconnected"},
                    ]),
                    json.dumps([
                        {"time": "Yesterday 15:30 UTC", "text": "Session disconnected · Gateway offline", "tone": "dim"},
                    ]),
                    now_iso,
                ),
                (
                    "SX-CONN-TG-01", "conn-06", "Telegram Compliance Bot", "Telegram Bot API", "Notification", "Live", "BOT-SX-NOTIF-01", "tg •••• ••b3",
                    "CONFIGURED", "HEALTHY", 42, "13:50:00 UTC", "ALLOWED", None,
                    json.dumps([
                        {"capability": "NOTIFICATIONS", "name": "Notifications", "systemStatus": "READY", "authStatus": "AUTHORIZED", "ownerAllowance": "ALLOWED", "effectiveStatus": "AVAILABLE"},
                    ]),
                    json.dumps([
                        {"time": "13:50:00 UTC", "text": "TLS webhook endpoint responsive · 42ms", "tone": "ok"},
                    ]),
                    now_iso,
                ),
            ]
            cur.executemany(
                """INSERT INTO owner_connections VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                conn_seeds,
            )

        ds_count = cur.execute("SELECT COUNT(*) as c FROM owner_datasets").fetchone()["c"]
        if ds_count == 0:
            now_iso = _utc_now().isoformat()
            ds_seeds = [
                (
                    "DS-NIFTY-5M-2024-2026", "ds-01", "TrueData Historical API", "NSE_INDEX", "NIFTY", "Index Spot", "5m", "Asia/Kolkata",
                    "2024-01-01", "2026-08-25", 652, 48900, "PARQUET_V2", "data/parquet/nse/nifty/spot/5m/nifty_5m.parquet",
                    "GAPS_CLEAR", "0 missing candles against NSE Calendar Authority (652 trading sessions verified)", "SYNTHETIC_FIXTURE",
                    "97bc2654a31f24d297d4b79d654525d6cc5c9df100f8d6adcb4ab1c846190fd3", "ACQUIRED", "SYSTEM_READY", None,
                    "Parquet v2 format valid · SHA-256 sealed · Synthetic test fixture", "APPROVED", None,
                    json.dumps([{"time": "2026-08-26 18:00 UTC", "action": "INTEGRITY_SEALED", "actor": "PIPELINE", "note": "Dataset verification passed; SHA-256 sealed", "tone": "ok"}]),
                    now_iso,
                ),
                (
                    "DS-BANKNIFTY-1M-2025-2026", "ds-02", "TrueData Historical API", "NSE_INDEX", "BANKNIFTY", "Index Spot", "1m", "Asia/Kolkata",
                    "2025-01-01", "2026-08-25", 412, 154500, "PARQUET_V2", "data/parquet/nse/banknifty/spot/1m/banknifty_1m.parquet",
                    "GAPS_CLEAR", "0 missing candles against NSE Calendar Authority (412 trading sessions verified)", "SYNTHETIC_FIXTURE",
                    "c6141eff40eed34155234a5be69603982259927e5698be34447695cfc5522703", "ACQUIRED", "SYSTEM_READY", None,
                    "Parquet v2 format valid · SHA-256 sealed · Synthetic test fixture", "APPROVED", None,
                    json.dumps([{"time": "2026-08-26 18:15 UTC", "action": "INTEGRITY_SEALED", "actor": "PIPELINE", "note": "Dataset verification passed; SHA-256 sealed", "tone": "ok"}]),
                    now_iso,
                ),
                (
                    "DS-NIFTY-OPT-WEEKLY-2026", "ds-03", "Zerodha Historical API", "NSE_FO", "NIFTY", "Index Options", "1m", "Asia/Kolkata",
                    "2026-01-01", "2026-08-25", 164, 61500, "PARQUET_V2", "data/parquet/nse/nifty/options/weekly/1m/nifty_opt_1m.parquet",
                    "GAPS_DETECTED", "3 calendar gaps detected: 2026-04-14 (Holiday mismatch), 2026-06-18 (Tick drop), 2026-08-05 (Half-session)", "SYNTHETIC_FIXTURE",
                    "7bca928374827189a0e481b99201948572018491827481928471928471928471", "ACQUIRED", "BLOCKED",
                    "Trading calendar gap analysis detected 3 missing sessions. Unresolved gaps violate Rule 5 backtest contract.",
                    "GAPS DETECTED: 3 calendar sessions require repair/backfill", "HOLD", "Owner placed dataset on administrative hold pending gap backfill from TrueData",
                    json.dumps([{"time": "2026-08-27 10:00 UTC", "action": "GAP_DETECTED", "actor": "CALENDAR_SCANNER", "note": "3 calendar gaps detected", "tone": "warn"}]),
                    now_iso,
                ),
                (
                    "DS-FINNIFTY-5M-2025-2026", "ds-04", "TrueData Historical API", "NSE_INDEX", "FINNIFTY", "Index Spot", "5m", "Asia/Kolkata",
                    "2025-01-01", "2026-08-25", 248, 18600, "PARQUET_V2", "data/parquet/nse/finnifty/spot/5m/finnifty_5m.parquet",
                    "GAPS_CLEAR", "0 missing candles against NSE Calendar Authority (248 trading sessions verified)", "SYNTHETIC_FIXTURE",
                    "1982740192847192847192847192847192847192847192847192847192847192", "ACQUIRED", "SYSTEM_READY", None,
                    "Parquet v2 format valid · Synthetic demo fixture · Pending calendar gap verification", "APPROVED", None,
                    json.dumps([{"time": "2026-08-26 18:30 UTC", "action": "INTEGRITY_SEALED", "actor": "PIPELINE", "note": "Dataset verification passed; SHA-256 sealed", "tone": "ok"}]),
                    now_iso,
                ),
                (
                    "DS-SENSEX-TICK-RAW-2026", "ds-05", "BSE Direct Market Feed", "BSE_INDEX", "SENSEX", "Index Spot", "tick", "Asia/Kolkata",
                    "2026-08-01", "2026-08-25", 18, 4200000, "CSV_RAW", "data/raw/bse/sensex/ticks/2026/sensex_ticks.csv",
                    "GAPS_CLEAR", "Tick timestamps verified against BSE Trading Calendar", "SYNTHETIC_FIXTURE",
                    "9918273645102938475610293847561029384756102938475610293847561029", "PARTIAL", "BLOCKED",
                    "Format is CSV_RAW without SHA-256 seal; requires ingestion pipeline normalization to Parquet v2 before backtest eligibility.",
                    "UNVERIFIED RAW SOURCE: Ingestion normalization pipeline pending", "HOLD", "Raw tick capture awaiting pipeline normalization",
                    json.dumps([{"time": "2026-08-25 19:00 UTC", "action": "SOURCE_REGISTERED", "actor": "OPS", "note": "Raw tick feed registered; awaiting normalization", "tone": "dim"}]),
                    now_iso,
                ),
            ]
            cur.executemany(
                """INSERT INTO owner_datasets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ds_seeds,
            )

    # ── Slice 4: Strategies Governance & Execution-Hold Authority ──

    def _format_strategy_row(self, row: sqlite3.Row) -> dict[str, object]:
        b_eff, _ = compute_strategy_effective_eligibility(
            row["backtest_system_readiness"],
            row["backtest_owner_allowance"],
            row["admin_status"] == "SUSPENDED",
        )
        p_eff, _ = compute_strategy_effective_eligibility(
            row["paper_system_readiness"],
            row["paper_owner_allowance"],
            row["admin_status"] == "SUSPENDED",
        )
        l_eff, _ = compute_strategy_effective_eligibility(
            row["live_system_readiness"],
            row["live_owner_allowance"],
            row["admin_status"] == "SUSPENDED",
        )
        return {
            "id": row["id"],
            "strategyId": row["strategy_id"],
            "name": row["name"],
            "version": row["version"],
            "visibility": row["visibility"] if "visibility" in row.keys() else "OWNER_PRIVATE",
            "interfaceVersion": row["interface_version"],
            "language": "Python",
            "stage": row["stage"],
            "category": row["category"],
            "instruments": json.loads(row["instruments_json"]),
            "timeframes": json.loads(row["timeframes_json"]),
            "quality": row["quality"],
            "evidenceAttached": bool(row["evidence_attached"]),
            "pnl": row["pnl"],
            "isProfit": bool(row["is_profit"]),
            "note": row["note"],
            "description": row["description"],
            "author": row["author"],
            "authorSxId": row["author_sx_id"],
            "lastUpdated": row["updated_at_utc"],
            "scanStatus": "PASSED",
            "conformanceCheck": row["conformance_status"],
            "conformanceStatus": row["conformance_status"],
            "adminStatus": row["admin_status"],
            "governance": {
                "backtest": {
                    "systemReadiness": row["backtest_system_readiness"],
                    "systemBlockerReason": row["backtest_system_blocker"],
                    "ownerAllowance": row["backtest_owner_allowance"],
                    "ownerHoldReason": row["backtest_owner_hold_reason"],
                    "effectiveEligibility": b_eff,
                },
                "paper": {
                    "systemReadiness": row["paper_system_readiness"],
                    "systemBlockerReason": row["paper_system_blocker"],
                    "ownerAllowance": row["paper_owner_allowance"],
                    "ownerHoldReason": row["paper_owner_hold_reason"],
                    "effectiveEligibility": p_eff,
                },
                "live": {
                    "systemReadiness": row["live_system_readiness"],
                    "systemBlockerReason": row["live_system_blocker"],
                    "ownerAllowance": row["live_owner_allowance"],
                    "ownerHoldReason": row["live_owner_hold_reason"],
                    "effectiveEligibility": l_eff,
                },
            },
            "backtestGovernance": {
                "systemReadiness": row["backtest_system_readiness"],
                "systemBlockerReason": row["backtest_system_blocker"],
                "ownerAllowance": row["backtest_owner_allowance"],
                "ownerHoldReason": row["backtest_owner_hold_reason"],
                "effectiveEligibility": b_eff,
            },
            "paperGovernance": {
                "systemReadiness": row["paper_system_readiness"],
                "systemBlockerReason": row["paper_system_blocker"],
                "ownerAllowance": row["paper_owner_allowance"],
                "ownerHoldReason": row["paper_owner_hold_reason"],
                "effectiveEligibility": p_eff,
            },
            "liveGovernance": {
                "systemReadiness": row["live_system_readiness"],
                "systemBlockerReason": row["live_system_blocker"],
                "ownerAllowance": row["live_owner_allowance"],
                "ownerHoldReason": row["live_owner_hold_reason"],
                "effectiveEligibility": l_eff,
            },
            "backtestEligibility": b_eff,
            "paperEligibility": p_eff,
            "liveEligibility": l_eff,
            "governanceHistory": json.loads(row["governance_history_json"]),
            "winRate": row["win_rate"],
            "maxDrawdown": row["max_drawdown"],
            "profitFactor": row["profit_factor"],
            "sharpeRatio": row["sharpe_ratio"],
            "totalTrades": row["total_trades"],
            "activePositions": row["active_positions"],
        }

    def list_owner_strategies(self) -> list[dict[str, object]]:
        rows = self._conn.execute("SELECT * FROM owner_strategies ORDER BY strategy_id ASC").fetchall()
        return [self._format_strategy_row(r) for r in rows]

    def get_owner_strategy(self, strategy_id: str) -> dict[str, object] | None:
        row = self._conn.execute(
            "SELECT * FROM owner_strategies WHERE strategy_id = ? OR id = ?",
            (strategy_id, strategy_id),
        ).fetchone()
        return self._format_strategy_row(row) if row else None

    def register_backtest_artifact(self, *, strategy_id: str, version_id: str, name: str, owner_id: str,
                                   preserve_assignment_status: bool = False):
        """Register an actually conformant artifact; no Paper/Live readiness is granted."""
        with self._transaction() as cur:
            role_row = cur.execute(
                "SELECT role FROM users WHERE user_id = ?", (str(owner_id),)).fetchone()
            initial_visibility = "OWNER_PRIVATE" if (role_row and (role_row["role"] or "") == "OWNER") else "PRIVATE"
            cur.execute("""INSERT INTO owner_strategies (
                strategy_id,id,name,version,stage,quality,evidence_attached,pnl,note,author,visibility,
                backtest_system_readiness,backtest_owner_allowance,paper_system_readiness,
                paper_system_blocker,live_system_readiness,live_system_blocker,
                win_rate,max_drawdown,profit_factor,sharpe_ratio,total_trades,updated_at_utc
            ) VALUES (?, ?, ?, ?, 'BACKTEST_ELIGIBLE', 0, 0, 'UNAVAILABLE',
                'Registered artifact; performance evidence unavailable until a run completes', ?, ?,
                'READY', 'ALLOWED', 'BLOCKED', 'Paper conformance unavailable',
                'BLOCKED', 'Live execution DISARMED', 0, 0, 0, 0, 0, ?)
            ON CONFLICT(strategy_id) DO UPDATE SET
                version = excluded.version,
                author = excluded.author,
                updated_at_utc = excluded.updated_at_utc""",
                (strategy_id,strategy_id,name,version_id,owner_id,initial_visibility,_utc_now().isoformat()))

            # Automatically persist strategy assignment for authoring user (F-10)
            now_iso = _utc_now().isoformat()
            cur.execute("""INSERT INTO user_strategy_assignments (
                assignment_id, user_id, strategy_id, version_id, tenant,
                assignment_status, created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, 'default', 'ASSIGNED', ?, ?)
            ON CONFLICT(user_id, strategy_id) DO UPDATE SET
                assignment_status = CASE WHEN ? THEN user_strategy_assignments.assignment_status ELSE 'ASSIGNED' END,
                version_id = excluded.version_id,
                updated_at_utc = excluded.updated_at_utc""",
                (f"asgn-{uuid4().hex[:12]}", str(owner_id), strategy_id, version_id, now_iso, now_iso,
                 int(preserve_assignment_status)))

    def assign_strategy_to_user(
        self,
        *,
        user_id: str | UUID,
        strategy_id: str,
        version_id: str | None = None,
        tenant: str = "default",
        actor: str = "OWNER",
    ) -> dict[str, object]:
        """Assign an approved strategy to a user (F-10)."""
        uid = str(user_id)
        now_str = _utc_now().isoformat()
        assignment_id = f"asgn-{uuid4().hex[:12]}"
        with self._transaction() as cur:
            user = cur.execute(
                "SELECT user_id, lifecycle, account_status FROM users WHERE user_id = ?",
                (uid,)
            ).fetchone()
            if not user:
                raise SecurityStoreError(f"User {uid} not found")

            strat = cur.execute(
                "SELECT strategy_id, name, version FROM owner_strategies WHERE strategy_id = ?",
                (strategy_id,)
            ).fetchone()
            if not strat:
                raise SecurityStoreError(f"Strategy {strategy_id} not registered in owner strategies")

            v_id = version_id or strat["version"]
            cur.execute("""
                INSERT INTO user_strategy_assignments (
                    assignment_id, user_id, strategy_id, version_id, tenant,
                    assignment_status, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, 'ASSIGNED', ?, ?)
                ON CONFLICT(user_id, strategy_id) DO UPDATE SET
                    assignment_status = 'ASSIGNED',
                    version_id = excluded.version_id,
                    updated_at_utc = excluded.updated_at_utc
            """, (assignment_id, uid, strategy_id, v_id, tenant, now_str, now_str))

            row = cur.execute(
                "SELECT * FROM user_strategy_assignments WHERE user_id = ? AND strategy_id = ?",
                (uid, strategy_id)
            ).fetchone()
            return dict(row)

    def revoke_strategy_assignment(
        self,
        *,
        user_id: str | UUID,
        strategy_id: str,
        actor: str = "OWNER",
    ) -> bool:
        """Revoke a strategy assignment for a user (F-10)."""
        uid = str(user_id)
        now_str = _utc_now().isoformat()
        with self._transaction() as cur:
            res = cur.execute("""
                UPDATE user_strategy_assignments SET
                    assignment_status = 'REVOKED',
                    updated_at_utc = ?
                WHERE user_id = ? AND strategy_id = ?
            """, (now_str, uid, strategy_id))
            return res.rowcount > 0

    def list_user_strategy_assignments(
        self,
        user_id: str | UUID | None = None,
        strategy_id: str | None = None,
    ) -> list[dict[str, object]]:
        """List active strategy assignments for a user and/or strategy (F-10)."""
        clauses = ["assignment_status = 'ASSIGNED'"]
        params: list[object] = []
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(str(user_id))
        if strategy_id is not None:
            clauses.append("strategy_id = ?")
            params.append(str(strategy_id))

        query = f"SELECT * FROM user_strategy_assignments WHERE {' AND '.join(clauses)}"
        rows = self._conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_strategy_assignment(self, user_id: str | UUID, strategy_id: str) -> dict[str, object] | None:
        """Get strategy assignment record for a user."""
        uid = str(user_id)
        row = self._conn.execute(
            "SELECT * FROM user_strategy_assignments WHERE user_id = ? AND strategy_id = ?",
            (uid, strategy_id)
        ).fetchone()
        return dict(row) if row else None

    STRATEGY_VISIBILITIES = frozenset({"PRIVATE", "OWNER_PRIVATE", "GLOBAL"})

    def set_strategy_visibility(
        self,
        *,
        strategy_id: str,
        visibility: str,
        actor_user_id: str | UUID | None = None,
        actor: str = "OWNER",
    ) -> dict[str, object]:
        """Explicit privileged publish/unpublish (Phase B).

        Only Owner-authored (OWNER_PRIVATE) or system rows may become GLOBAL,
        and only the authoring Owner (or Owner oversight for system rows) may
        publish. User-authored PRIVATE strategies can NEVER be made GLOBAL
        through this path. Unpublish returns to OWNER_PRIVATE; historical
        runs/evidence are untouched (no deletion anywhere in this method).
        """
        vis = (visibility or "").upper().strip()
        if vis not in {"OWNER_PRIVATE", "GLOBAL"}:
            raise SecurityStoreError(f"Invalid strategy visibility '{visibility}'")
        with self._transaction() as cur:
            row = cur.execute(
                "SELECT * FROM owner_strategies WHERE strategy_id = ?", (strategy_id,)).fetchone()
            if row is None:
                raise SecurityStoreError("Strategy is not registered")
            current = (row["visibility"] if "visibility" in row.keys() else "OWNER_PRIVATE") or "OWNER_PRIVATE"
            if current == "PRIVATE":
                raise SecurityStoreError("User-private strategies cannot be published to the global catalog")
            author = str(row["author"] or "").strip()
            if author:
                author_user = cur.execute(
                    "SELECT role FROM users WHERE user_id = ?", (author,)).fetchone()
                if author_user is not None and (author_user["role"] or "") != "OWNER":
                    raise SecurityStoreError("User-private strategies cannot be published to the global catalog")
                if actor_user_id is not None and author != str(actor_user_id):
                    # Owner oversight (actor None) may publish system rows;
                    # a named non-author owner cannot publish another's row.
                    if author_user is not None:
                        raise SecurityStoreError("Only the authoring Owner may change catalog visibility")
            if current == vis:
                return self._format_strategy_row(row)
            cur.execute("""UPDATE owner_strategies SET visibility = ?, updated_at_utc = ?
                           WHERE strategy_id = ?""",
                        (vis, _utc_now().isoformat(), strategy_id))
        updated = self._conn.execute(
            "SELECT * FROM owner_strategies WHERE strategy_id = ?", (strategy_id,)).fetchone()
        return self._format_strategy_row(updated)

    def check_user_strategy_access(self, user_id: str | UUID, strategy_id: str) -> dict[str, object]:
        """Verify if a user has active, permitted access to a strategy (F-10)."""
        uid = str(user_id)
        user_row = self._conn.execute("SELECT role FROM users WHERE user_id = ?", (uid,)).fetchone()
        is_owner = user_row and user_row["role"] == "OWNER"

        strat = self.get_owner_strategy(strategy_id)
        if not strat:
            return {"permitted": False, "reason": "STRATEGY_NOT_REGISTERED"}

        admin_status = strat.get("adminStatus") or strat.get("admin_status") or "ACTIVE"
        if admin_status != "ACTIVE":
            return {"permitted": False, "reason": f"STRATEGY_{admin_status}", "strategy": strat}

        if is_owner:
            return {"permitted": True, "strategy": strat, "role": "OWNER"}

        # Check if user is author
        author = strat.get("author") or strat.get("authorSxId")
        if author == uid:
            return {"permitted": True, "strategy": strat, "role": "AUTHOR"}

        # Explicit per-user revocation fails closed even for catalog strategies.
        assignment = self.get_strategy_assignment(uid, strategy_id)
        if assignment and assignment.get("assignment_status") == "REVOKED":
            return {"permitted": False, "reason": "STRATEGY_ASSIGNMENT_REVOKED", "strategy": strat}

        # Explicit global catalog: discoverable/usable by active users under
        # normal governance controls. Execution/account/session state always
        # remains per-user (tenant isolation is enforced by callers).
        if (strat.get("visibility") or "OWNER_PRIVATE") == "GLOBAL":
            return {"permitted": True, "strategy": strat, "role": "GLOBAL_CATALOG_USER"}

        # Check assignment
        if assignment and assignment.get("assignment_status") == "ASSIGNED":
            return {"permitted": True, "strategy": strat, "assignment": assignment, "role": "ASSIGNED_USER"}

        # If author is a registered user identity and not assigned, deny access (tenant isolation)
        author_user = self.get_user(str(author or "")) if author else None
        if author_user is not None:
            return {"permitted": False, "reason": "STRATEGY_NOT_ASSIGNED", "strategy": strat}

        # Canonical / system catalog strategy published by Owner (author is not a registered user):
        # accessible to active platform users under normal administrative / governance controls.
        return {"permitted": True, "strategy": strat, "role": "CANONICAL_CATALOG_USER"}

    def update_strategy_allowance(
        self,
        strategy_id: str,
        sandbox: str,
        allowance: str,
        reason: str | None = None,
        actor: str = "OWNER-001",
    ) -> tuple[dict[str, object], str, str]:
        sb = sandbox.lower()
        if sb not in {"backtest", "paper", "live"}:
            raise SecurityStoreError(f"Invalid sandbox: {sandbox}")
        allw = allowance.upper()
        if allw not in {"ALLOWED", "HOLD"}:
            raise SecurityStoreError(f"Invalid allowance: {allowance}")

        with self._transaction() as cur:
            row = cur.execute(
                "SELECT * FROM owner_strategies WHERE strategy_id = ? OR id = ?",
                (strategy_id, strategy_id),
            ).fetchone()
            if row is None:
                raise SecurityStoreError("Strategy not found")

            history = json.loads(row["governance_history_json"])
            now_str = _utc_now().strftime("%Y-%m-%d %H:%M UTC")
            now_iso = _utc_now().isoformat()
            history.insert(0, {
                "id": f"gov-{int(_utc_now().timestamp()*1000)}",
                "timestamp": now_str,
                "actor": actor,
                "action": f"OWNER_ALLOWANCE_{sb.upper()}_{allw}",
                "note": f"Owner set {sb.upper()} allowance to {allw}" + (f": {reason}" if reason else ""),
                "tone": "ok" if allw == "ALLOWED" else "warn",
            })
            hold_reason = reason or f"Placed on hold by {actor}" if allw == "HOLD" else None

            if sb == "backtest":
                cur.execute(
                    "UPDATE owner_strategies SET backtest_owner_allowance = ?, backtest_owner_hold_reason = ?, governance_history_json = ?, updated_at_utc = ? WHERE strategy_id = ?",
                    (allw, hold_reason, json.dumps(history), now_iso, row["strategy_id"]),
                )
            elif sb == "paper":
                cur.execute(
                    "UPDATE owner_strategies SET paper_owner_allowance = ?, paper_owner_hold_reason = ?, governance_history_json = ?, updated_at_utc = ? WHERE strategy_id = ?",
                    (allw, hold_reason, json.dumps(history), now_iso, row["strategy_id"]),
                )
            else:
                cur.execute(
                    "UPDATE owner_strategies SET live_owner_allowance = ?, live_owner_hold_reason = ?, governance_history_json = ?, updated_at_utc = ? WHERE strategy_id = ?",
                    (allw, hold_reason, json.dumps(history), now_iso, row["strategy_id"]),
                )

        updated_row = self._conn.execute(
            "SELECT * FROM owner_strategies WHERE strategy_id = ?", (row["strategy_id"],)
        ).fetchone()
        formatted = self._format_strategy_row(updated_row)
        eff_status = formatted[f"{sb}Eligibility"]
        msg = f"Owner {sb.upper()} allowance set to {allw}."
        if allw == "ALLOWED" and eff_status == "BLOCKED":
            msg += " Effective eligibility remains BLOCKED by system readiness gate."
        return formatted, eff_status, msg

    def suspend_strategy(
        self,
        strategy_id: str,
        reason: str = "Owner administrative hold",
        actor: str = "OWNER-001",
    ) -> dict[str, object]:
        with self._transaction() as cur:
            row = cur.execute(
                "SELECT * FROM owner_strategies WHERE strategy_id = ? OR id = ?",
                (strategy_id, strategy_id),
            ).fetchone()
            if row is None:
                raise SecurityStoreError("Strategy not found")

            history = json.loads(row["governance_history_json"])
            now_str = _utc_now().strftime("%Y-%m-%d %H:%M UTC")
            now_iso = _utc_now().isoformat()
            history.insert(0, {
                "id": f"gov-{int(_utc_now().timestamp()*1000)}",
                "timestamp": now_str,
                "actor": actor,
                "action": "ADMIN_SUSPENDED",
                "note": f"Owner suspended strategy: {reason}",
                "tone": "neg",
            })
            cur.execute(
                "UPDATE owner_strategies SET admin_status = 'SUSPENDED', governance_history_json = ?, updated_at_utc = ? WHERE strategy_id = ?",
                (json.dumps(history), now_iso, row["strategy_id"]),
            )

        updated_row = self._conn.execute(
            "SELECT * FROM owner_strategies WHERE strategy_id = ?", (row["strategy_id"],)
        ).fetchone()
        return self._format_strategy_row(updated_row)

    def restore_strategy(
        self,
        strategy_id: str,
        actor: str = "OWNER-001",
    ) -> dict[str, object]:
        with self._transaction() as cur:
            row = cur.execute(
                "SELECT * FROM owner_strategies WHERE strategy_id = ? OR id = ?",
                (strategy_id, strategy_id),
            ).fetchone()
            if row is None:
                raise SecurityStoreError("Strategy not found")

            history = json.loads(row["governance_history_json"])
            now_str = _utc_now().strftime("%Y-%m-%d %H:%M UTC")
            now_iso = _utc_now().isoformat()
            history.insert(0, {
                "id": f"gov-{int(_utc_now().timestamp()*1000)}",
                "timestamp": now_str,
                "actor": actor,
                "action": "ADMIN_RESTORED",
                "note": "Owner restored strategy to ACTIVE governance status",
                "tone": "ok",
            })
            cur.execute(
                "UPDATE owner_strategies SET admin_status = 'ACTIVE', governance_history_json = ?, updated_at_utc = ? WHERE strategy_id = ?",
                (json.dumps(history), now_iso, row["strategy_id"]),
            )

        updated_row = self._conn.execute(
            "SELECT * FROM owner_strategies WHERE strategy_id = ?", (row["strategy_id"],)
        ).fetchone()
        return self._format_strategy_row(updated_row)

    def is_strategy_execution_held(
        self,
        strategy_id: str,
        sandbox: str = "live",
    ) -> tuple[bool, str]:
        strat = self.get_owner_strategy(strategy_id)
        if strat is None:
            return True, "Strategy not found"
        if strat["adminStatus"] == "SUSPENDED":
            return True, "Global strategy suspension is active (Owner administrative hold)."
        sb = sandbox.lower()
        if sb == "backtest":
            gov = strat["backtestGovernance"]
        elif sb == "paper":
            gov = strat["paperGovernance"]
        else:
            gov = strat["liveGovernance"]

        if gov["ownerAllowance"] == "HOLD":
            return True, gov.get("ownerHoldReason") or f"Owner hold active on {sb} sandbox."
        if gov["systemReadiness"] != "READY":
            return True, gov.get("systemBlockerReason") or f"System readiness unsatisfied on {sb} sandbox."
        return False, f"Strategy execution permitted on {sb} sandbox."

    # ── F-19: Strategy Promotion Authority ──

    def promote_strategy(
        self,
        strategy_id: str,
        target_stage: str,
        actor: str = "OWNER-001",
        notes: str = "",
    ) -> dict[str, object]:
        """F-19: Authoritative strategy lifecycle promotion.

        Allowed transitions:
        - BACKTEST_ELIGIBLE -> PAPER_ELIGIBLE
        - PAPER_ELIGIBLE -> LIVE_ELIGIBLE

        Requires:
        - Admin status must be ACTIVE (not SUSPENDED).
        - For PAPER_ELIGIBLE: at least one completed conforming backtest run or conformant status.
        - For LIVE_ELIGIBLE: paper forward evidence required; live execution remains BLOCKED.
        """
        valid_stages = {"BACKTEST_ELIGIBLE", "PAPER_ELIGIBLE", "LIVE_ELIGIBLE"}
        target_stage = target_stage.upper().strip()
        if target_stage not in valid_stages:
            raise SecurityStoreError(f"Invalid target stage '{target_stage}'. Valid: {sorted(valid_stages)}")

        with self._transaction() as cur:
            row = cur.execute(
                "SELECT * FROM owner_strategies WHERE strategy_id = ? OR id = ?",
                (strategy_id, strategy_id),
            ).fetchone()
            if row is None:
                raise SecurityStoreError("Strategy not found")

            if row["admin_status"] != "ACTIVE":
                raise SecurityStoreError(f"Cannot promote strategy '{strategy_id}': admin status is {row['admin_status']}")

            current_stage = row["stage"]
            allowed_transitions = {
                "ADDED": {"VALIDATED", "BACKTEST_ELIGIBLE"},
                "VALIDATED": {"BACKTEST_ELIGIBLE"},
                "BACKTEST_ELIGIBLE": {"PAPER_ELIGIBLE"},
                "PAPER_ELIGIBLE": {"LIVE_ELIGIBLE"},
            }
            if target_stage not in allowed_transitions.get(current_stage, set()):
                if current_stage == target_stage:
                    # Idempotent re-affirmation
                    pass
                else:
                    raise SecurityStoreError(
                        f"Invalid promotion transition from {current_stage} to {target_stage}. "
                        f"Allowed: {sorted(allowed_transitions.get(current_stage, set()))}"
                    )

            if target_stage == "PAPER_ELIGIBLE":
                runs = cur.execute(
                    "SELECT run_id, status FROM backtest_runs WHERE strategy_id = ? AND status = 'COMPLETED'",
                    (row["strategy_id"],),
                ).fetchall()
                if not runs and row["conformance_status"] != "CONFORMANT":
                    raise SecurityStoreError(
                        f"Cannot promote strategy '{strategy_id}' to PAPER_ELIGIBLE: no completed backtest runs found"
                    )

            history = json.loads(row["governance_history_json"])
            now_str = _utc_now().strftime("%Y-%m-%d %H:%M UTC")
            now_iso = _utc_now().isoformat()
            history.insert(0, {
                "id": f"gov-prom-{int(_utc_now().timestamp()*1000)}",
                "timestamp": now_str,
                "actor": actor,
                "action": f"PROMOTED_TO_{target_stage}",
                "note": notes or f"Owner promoted strategy from {current_stage} to {target_stage}",
                "tone": "ok",
            })

            paper_readiness = "READY" if target_stage in {"PAPER_ELIGIBLE", "LIVE_ELIGIBLE"} else row["paper_system_readiness"]
            live_readiness = "READY" if target_stage == "LIVE_ELIGIBLE" else row["live_system_readiness"]
            live_blocker = None if target_stage == "LIVE_ELIGIBLE" else row["live_system_blocker"]
            cur.execute(
                """UPDATE owner_strategies
                   SET stage = ?, paper_system_readiness = ?, live_system_readiness = ?, live_system_blocker = ?, governance_history_json = ?, updated_at_utc = ?
                   WHERE strategy_id = ?""",
                (target_stage, paper_readiness, live_readiness, live_blocker, json.dumps(history), now_iso, row["strategy_id"]),
            )

            # Clear pending promotion request if any
            cur.execute(
                "DELETE FROM security_metadata WHERE key = ?",
                (f"strat_prom_req:{row['strategy_id']}",),
            )

        updated_row = self._conn.execute(
            "SELECT * FROM owner_strategies WHERE strategy_id = ?", (row["strategy_id"],)
        ).fetchone()
        return self._format_strategy_row(updated_row)

    def request_strategy_promotion(
        self,
        strategy_id: str,
        user_id: str,
        target_stage: str = "PAPER_ELIGIBLE",
        run_id: str | None = None,
        notes: str = "",
        actor: str = "USER",
    ) -> dict[str, Any]:
        """F-19: User-initiated formal strategy promotion request."""
        target_stage = target_stage.upper().strip()
        strat = self.get_owner_strategy(strategy_id)
        if not strat:
            raise SecurityStoreError(f"Strategy '{strategy_id}' not found")
        if strat["adminStatus"] != "ACTIVE":
            raise SecurityStoreError(f"Strategy '{strategy_id}' is {strat['adminStatus']} under Owner governance")

        with self._transaction() as cur:
            if run_id:
                run = cur.execute(
                    "SELECT run_id, status FROM backtest_runs WHERE run_id = ? AND (? IS NULL OR user_id = ?)",
                    (run_id, user_id, user_id),
                ).fetchone()
                if not run:
                    raise SecurityStoreError(f"Backtest run '{run_id}' not found")
                if run["status"] != "COMPLETED":
                    raise SecurityStoreError(f"Backtest run '{run_id}' is not COMPLETED (status: {run['status']})")
            else:
                # F-19: a request without an explicit run must still cite real
                # completed eligible backtest evidence owned by the requester.
                evidence = cur.execute(
                    """SELECT run_id FROM backtest_runs
                       WHERE strategy_id = ? AND user_id = ? AND status = 'COMPLETED' LIMIT 1""",
                    (strat["strategyId"], user_id),
                ).fetchone()
                if not evidence:
                    raise SecurityStoreError(
                        f"No completed backtest evidence for strategy '{strategy_id}' by this user"
                    )
                run_id = evidence["run_id"]

            now_iso = _utc_now().isoformat()
            req_data = {
                "strategy_id": strat["strategyId"],
                "strategy_name": strat["name"],
                "version": strat["version"],
                "user_id": user_id,
                "current_stage": strat["stage"],
                "target_stage": target_stage,
                "run_id": run_id,
                "notes": notes,
                "status": "PENDING_OWNER_REVIEW",
                "requested_at_utc": now_iso,
            }
            cur.execute(
                "INSERT OR REPLACE INTO security_metadata (key, value) VALUES (?, ?)",
                (f"strat_prom_req:{strat['strategyId']}", json.dumps(req_data)),
            )

        return {
            "success": True,
            "strategy_id": strat["strategyId"],
            "target_stage": target_stage,
            "status": "PENDING_OWNER_REVIEW",
            "requested_at": now_iso,
        }

    def get_strategy_promotion_request(self, strategy_id: str) -> dict[str, Any] | None:
        """Retrieve pending promotion request for a strategy."""
        row = self._conn.execute(
            "SELECT value FROM security_metadata WHERE key = ?",
            (f"strat_prom_req:{strategy_id}",),
        ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["value"])
        except Exception:
            return None

    def list_pending_strategy_promotions(self) -> list[dict[str, Any]]:
        """List all pending strategy promotion requests."""
        rows = self._conn.execute(
            "SELECT value FROM security_metadata WHERE key LIKE 'strat_prom_req:%'"
        ).fetchall()
        results = []
        for r in rows:
            try:
                results.append(json.loads(r["value"]))
            except Exception:
                pass
        return results

    # ── F-18: Authoritative Server Settings (PROPOSE -> CONFIRM -> APPLY -> VERIFY) ──

    def get_server_setting(self, key: str, default: Any = None) -> Any:
        """Read a server-authoritative setting from security_metadata."""
        row = self._conn.execute(
            "SELECT value FROM security_metadata WHERE key = ?",
            (f"setting:{key}",),
        ).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except Exception:
            return row["value"]

    def list_server_settings(self) -> dict[str, Any]:
        """List all server-authoritative settings with defaults for unconfigured keys."""
        defaults = {
            "safe_mode": False,
            "stale_threshold_seconds": 30,
            "retention_policy_days": 365,
            "auto_archive_inactive_strategies": False,
            "live_global_hold": self.live_global_hold(),
        }
        rows = self._conn.execute(
            "SELECT key, value FROM security_metadata WHERE key LIKE 'setting:%'"
        ).fetchall()
        for r in rows:
            clean_key = r["key"].removeprefix("setting:")
            try:
                defaults[clean_key] = json.loads(r["value"])
            except Exception:
                defaults[clean_key] = r["value"]
        defaults["live_global_hold"] = self.live_global_hold()
        return defaults

    def stage_setting_proposal(
        self,
        proposal_id: str,
        key: str,
        current_value: Any,
        proposed_value: Any,
        actor: str,
        diff: str,
        expires_at_utc: str,
    ) -> dict[str, Any]:
        """Stage a proposed setting change awaiting explicit confirmation."""
        if key in _PROTECTED_SETTING_KEYS:
            raise SecurityStoreError(f"Modification of protected safety control '{key}' is architecturally forbidden")
        proposal = {
            "proposal_id": proposal_id,
            "key": key,
            "current_value": current_value,
            "proposed_value": proposed_value,
            "actor": actor,
            "diff": diff,
            "staged_at_utc": _utc_now().isoformat(),
            "expires_at_utc": expires_at_utc,
            "status": "AWAITING_CONFIRMATION",
        }
        with self._transaction() as cur:
            cur.execute(
                "INSERT OR REPLACE INTO security_metadata (key, value) VALUES (?, ?)",
                (f"setting_prop:{proposal_id}", json.dumps(proposal)),
            )
        return proposal

    def apply_setting_proposal(
        self,
        proposal_id: str,
        actor: str,
    ) -> tuple[str, Any, Any]:
        """Apply a staged setting proposal atomically, returning (key, verified_value, old_value)."""
        prop_row = self._conn.execute(
            "SELECT value FROM security_metadata WHERE key = ?",
            (f"setting_prop:{proposal_id}",),
        ).fetchone()
        if not prop_row:
            raise SecurityStoreError("Setting proposal not found or already consumed")

        proposal = json.loads(prop_row["value"])
        if proposal["status"] != "AWAITING_CONFIRMATION":
            raise SecurityStoreError(f"Proposal status is {proposal['status']}, cannot apply")

        now = _utc_now()
        exp = datetime.fromisoformat(proposal["expires_at_utc"])
        if now > exp:
            raise SecurityStoreError("Setting proposal has expired")

        key = proposal["key"]
        new_val = proposal["proposed_value"]
        old_val = proposal["current_value"]

        # F-18 mandatory safety: these controls can never be mutated through the
        # settings lifecycle. live_global_hold is read-only truth derived from
        # the dedicated security control, never a writable setting.
        if key in _PROTECTED_SETTING_KEYS:
            raise SecurityStoreError(f"Modification of protected safety control '{key}' is architecturally forbidden")

        with self._transaction() as cur:
            cur.execute("DELETE FROM security_metadata WHERE key = ?", (f"setting_prop:{proposal_id}",))
            cur.execute(
                "INSERT OR REPLACE INTO security_metadata (key, value) VALUES (?, ?)",
                (f"setting:{key}", json.dumps(new_val)),
            )

        verified = self.get_server_setting(key)
        if verified != new_val:
            raise SecurityStoreError(
                f"Setting verification failed: re-read value '{verified}' does not match proposed '{new_val}'"
            )

        return key, verified, old_val

    # ── Slice 4: Broker Connector Authority ──

    def _format_connection_row(self, row: sqlite3.Row) -> dict[str, object]:
        caps = json.loads(row["capabilities_json"])
        derived_caps = []
        for cap in caps:
            eff_status, blocker = compute_capability_effective(
                conn_health=row["health_state"],
                conn_allowance=row["owner_allowance"],
                cap_system_status=cap.get("systemStatus", "READY"),
                cap_auth_status=cap.get("authStatus", "AUTHORIZED"),
                cap_owner_allowance=cap.get("ownerAllowance", "ALLOWED"),
                blocker_reason=cap.get("blockerReason"),
            )
            c = dict(cap)
            c["effectiveStatus"] = eff_status
            if blocker:
                c["blockerReason"] = blocker
            derived_caps.append(c)

        return {
            "id": row["id"],
            "connectionId": row["connection_id"],
            "name": row["name"],
            "provider": row["provider"],
            "type": row["type"],
            "environment": row["environment"],
            "accountAlias": row["account_alias"],
            "secretRef": row["secret_ref"],  # MASKED! Never expose plaintext
            "authState": row["auth_state"],
            "healthState": row["health_state"],
            "latencyMs": row["latency_ms"],
            "lastCheck": row["last_check"],
            "ownerAllowance": row["owner_allowance"],
            "ownerHoldReason": row["owner_hold_reason"],
            "capabilities": derived_caps,
            "events": json.loads(row["events_json"]),
        }

    def list_owner_connections(self) -> list[dict[str, object]]:
        rows = self._conn.execute("SELECT * FROM owner_connections ORDER BY connection_id ASC").fetchall()
        return [self._format_connection_row(r) for r in rows]

    def get_owner_connection(self, connection_id: str) -> dict[str, object] | None:
        row = self._conn.execute(
            "SELECT * FROM owner_connections WHERE connection_id = ? OR id = ?",
            (connection_id, connection_id),
        ).fetchone()
        return self._format_connection_row(row) if row else None

    def update_connection_allowance(
        self,
        connection_id: str,
        allowance: str,
        reason: str | None = None,
        actor: str = "OWNER-001",
    ) -> dict[str, object]:
        allw = allowance.upper()
        if allw not in {"ALLOWED", "HOLD"}:
            raise SecurityStoreError(f"Invalid allowance: {allowance}")

        with self._transaction() as cur:
            row = cur.execute(
                "SELECT * FROM owner_connections WHERE connection_id = ? OR id = ?",
                (connection_id, connection_id),
            ).fetchone()
            if row is None:
                raise SecurityStoreError("Connection not found")

            events = json.loads(row["events_json"])
            now_str = _utc_now().strftime("%H:%M:%S UTC")
            now_iso = _utc_now().isoformat()
            events.insert(0, {
                "time": now_str,
                "text": f"Owner allowance set to {allw}" + (f": {reason}" if reason else ""),
                "tone": "ok" if allw == "ALLOWED" else "warn",
            })
            hold_reason = reason or f"Placed on hold by {actor}" if allw == "HOLD" else None

            cur.execute(
                "UPDATE owner_connections SET owner_allowance = ?, owner_hold_reason = ?, events_json = ?, updated_at_utc = ? WHERE connection_id = ?",
                (allw, hold_reason, json.dumps(events), now_iso, row["connection_id"]),
            )

        updated_row = self._conn.execute(
            "SELECT * FROM owner_connections WHERE connection_id = ?", (row["connection_id"],)
        ).fetchone()
        formatted = self._format_connection_row(updated_row)
        msg = f"Connection '{row['connection_id']}' allowance updated to {allw}."
        return formatted, msg

    def update_capability_allowance(
        self,
        connection_id: str,
        capability: str,
        allowance: str,
        reason: str | None = None,
        actor: str = "OWNER-001",
    ) -> tuple[dict[str, object], str, str]:
        allw = allowance.upper()
        if allw not in {"ALLOWED", "HOLD"}:
            raise SecurityStoreError(f"Invalid allowance: {allowance}")

        with self._transaction() as cur:
            row = cur.execute(
                "SELECT * FROM owner_connections WHERE connection_id = ? OR id = ?",
                (connection_id, connection_id),
            ).fetchone()
            if row is None:
                raise SecurityStoreError("Connection not found")

            caps = json.loads(row["capabilities_json"])
            found = False
            for cap in caps:
                if cap.get("capability") == capability:
                    cap["ownerAllowance"] = allw
                    if allw == "HOLD":
                        cap["blockerReason"] = reason or f"Capability placed on hold by {actor}"
                    elif "blockerReason" in cap and "placed on hold" in cap.get("blockerReason", ""):
                        del cap["blockerReason"]
                    found = True
                    break
            if not found:
                raise SecurityStoreError(f"Capability '{capability}' not found on connection")

            events = json.loads(row["events_json"])
            now_str = _utc_now().strftime("%H:%M:%S UTC")
            now_iso = _utc_now().isoformat()
            events.insert(0, {
                "time": now_str,
                "text": f"Capability '{capability}' allowance set to {allw}",
                "tone": "ok" if allw == "ALLOWED" else "warn",
            })

            cur.execute(
                "UPDATE owner_connections SET capabilities_json = ?, events_json = ?, updated_at_utc = ? WHERE connection_id = ?",
                (json.dumps(caps), json.dumps(events), now_iso, row["connection_id"]),
            )

        updated_row = self._conn.execute(
            "SELECT * FROM owner_connections WHERE connection_id = ?", (row["connection_id"],)
        ).fetchone()
        formatted = self._format_connection_row(updated_row)
        cap = next((c for c in formatted["capabilities"] if c["capability"] == capability), None)
        eff_status = cap["effectiveStatus"] if cap else "BLOCKED"
        msg = f"Capability '{capability}' allowance updated to {allw}."
        return formatted, eff_status, msg

    # ── P1-A (R-03): self-service paper/backtest eligibility ──
    # Locked policy: REGISTERED + VALIDATED + ACTIVE + ASSIGNED (or author /
    # canonical catalog) may Backtest and Paper-trade subject to automatic
    # safety checks. Owner stage promotion (PAPER_ELIGIBLE) is NO LONGER
    # required for ordinary paper workflows. Owner SUSPEND / HOLD / REVOKE,
    # archived versions, hash verification and LIVE real-money governance are
    # untouched and still fail closed elsewhere.

    def check_self_service_paper_eligibility(
        self, strategy_id: str, *, user_id: str | UUID | None = None,
    ) -> dict[str, object]:
        """Automatic paper-eligibility verdict without Owner promotion."""
        def deny(code, reason):
            return dict(permitted=False, code=code, reason=reason)
        strat = self.get_owner_strategy(strategy_id)
        if strat is None:
            return deny("STRATEGY_UNKNOWN", f"Strategy '{strategy_id}' not registered")
        admin_status = strat.get("adminStatus") or strat.get("admin_status") or "ACTIVE"
        if admin_status != "ACTIVE":
            return deny(f"STRATEGY_{admin_status}", f"Strategy '{strategy_id}' is {admin_status} under Owner governance")
        if user_id is not None:
            uid = str(user_id)
            user = self.get_user(uid)
            if user is None or user["lifecycle"] != "ACTIVE" or user["account_status"] != "ACTIVE":
                return deny("SUBJECT_INACTIVE", "Active authenticated User required")
            if (user["role"] or "") != "OWNER":
                access = self.check_user_strategy_access(uid, strategy_id)
                if not access.get("permitted"):
                    return deny(str(access.get("reason", "STRATEGY_NOT_ASSIGNED")), "Cross-user strategy execution denied")
        paper_allowance = (
            (strat.get("governance") or {}).get("paper", {}).get("ownerAllowance")
            if isinstance(strat.get("governance"), dict) else None
        ) or strat.get("paper_owner_allowance") or "ALLOWED"
        if paper_allowance != "ALLOWED":
            hold_reason = (
                ((strat.get("governance") or {}).get("paper", {}) or {}).get("ownerHoldReason")
                if isinstance(strat.get("governance"), dict) else None
            ) or strat.get("paper_owner_hold_reason") or "Owner execution hold active"
            return deny("PAPER_OWNER_HOLD", f"Strategy '{strategy_id}' paper execution is on hold: {hold_reason}")
        return dict(permitted=True, code="SELF_SERVICE_PAPER_OK",
                    reason="Registered, validated, active strategy with automatic safety checks satisfied; no Owner promotion required for paper.")

    def check_self_service_backtest_eligibility(
        self, strategy_id: str, *, user_id: str | UUID | None = None,
    ) -> dict[str, object]:
        """Automatic backtest-eligibility verdict without Owner promotion."""
        def deny(code, reason):
            return dict(permitted=False, code=code, reason=reason)
        strat = self.get_owner_strategy(strategy_id)
        if strat is None:
            return deny("STRATEGY_UNKNOWN", f"Strategy '{strategy_id}' not registered")
        admin_status = strat.get("adminStatus") or strat.get("admin_status") or "ACTIVE"
        if admin_status != "ACTIVE":
            return deny(f"STRATEGY_{admin_status}", f"Strategy '{strategy_id}' is {admin_status} under Owner governance")
        if user_id is not None:
            uid = str(user_id)
            user = self.get_user(uid)
            if user is None or user["lifecycle"] != "ACTIVE" or user["account_status"] != "ACTIVE":
                return deny("SUBJECT_INACTIVE", "Active authenticated User required")
            if (user["role"] or "") != "OWNER":
                access = self.check_user_strategy_access(uid, strategy_id)
                if not access.get("permitted"):
                    return deny(str(access.get("reason", "STRATEGY_NOT_ASSIGNED")), "Cross-user strategy execution denied")
        held, hold_reason = self.is_strategy_execution_held(strategy_id, "backtest")
        if held:
            return deny("STRATEGY_BLOCKED", f"Strategy backtest blocked: {hold_reason}")
        return dict(permitted=True, code="SELF_SERVICE_BACKTEST_OK",
                    reason="Registered, validated, active strategy with automatic safety checks satisfied; no Owner promotion required for backtest.")

    def check_self_service_live_eligibility(
        self, strategy_id: str, *, user_id: str | UUID | None = None,
    ) -> dict[str, object]:
        """Automatic live-eligibility verdict for authenticated active user without Owner approval."""
        def deny(code, reason):
            return dict(permitted=False, code=code, reason=reason)
        strat = self.get_owner_strategy(strategy_id)
        if strat is None:
            return deny("STRATEGY_UNKNOWN", f"Strategy '{strategy_id}' not registered")
        admin_status = strat.get("adminStatus") or strat.get("admin_status") or "ACTIVE"
        if admin_status != "ACTIVE":
            return deny(f"STRATEGY_{admin_status}", f"Strategy '{strategy_id}' is {admin_status} under Owner governance")
        if user_id is not None:
            uid = str(user_id)
            user = self.get_user(uid)
            if user is None or user["lifecycle"] != "ACTIVE" or user["account_status"] != "ACTIVE":
                return deny("SUBJECT_INACTIVE", "Active authenticated User required")
            if (user["role"] or "") != "OWNER":
                access = self.check_user_strategy_access(uid, strategy_id)
                if not access.get("permitted"):
                    return deny(str(access.get("reason", "STRATEGY_NOT_ASSIGNED")), "Cross-user strategy execution denied")
        stage = strat.get("stage")
        if stage not in {"PAPER_ELIGIBLE", "LIVE_ELIGIBLE"}:
            return deny("STAGE_INELIGIBLE", f"Strategy '{strategy_id}' stage is {stage}; PAPER_ELIGIBLE or LIVE_ELIGIBLE required for live eligibility")
        live_allowance = (
            (strat.get("governance") or {}).get("live", {}).get("ownerAllowance")
            if isinstance(strat.get("governance"), dict) else None
        ) or strat.get("live_owner_allowance") or "ALLOWED"
        if live_allowance != "ALLOWED":
            hold_reason = (
                ((strat.get("governance") or {}).get("live", {}) or {}).get("ownerHoldReason")
                if isinstance(strat.get("governance"), dict) else None
            ) or strat.get("live_owner_hold_reason") or "Owner execution hold active"
            return deny("LIVE_OWNER_HOLD", f"Strategy '{strategy_id}' live execution is on hold: {hold_reason}")
        return dict(
            permitted=True,
            code="SELF_SERVICE_LIVE_OK",
            reason="Registered, validated, active strategy with automatic safety checks satisfied; user controls live deployment.",
        )

    # ── P1-A (R-02): per-user broker/API connection authority ──

    USER_CONNECTION_PROVIDERS = frozenset(
        {"UPSTOX", "ZERODHA", "KITE", "DHAN", "ANGELONE", "ANGEL_ONE", "PAPER_INTERNAL"}
    )
    USER_CONNECTION_USER_STATUSES = frozenset({"NOT_CONNECTED", "CONFIGURED", "DISABLED"})
    USER_CONNECTION_ALL_STATUSES = frozenset({"NOT_CONNECTED", "CONFIGURED", "DISCONNECTED", "SUSPENDED", "ERROR", "DISABLED", "RETIRED"})
    STRATEGY_CONNECTION_MODES = frozenset({"LIVE_PAPER", "LIVE"})

    @staticmethod
    def _mask_account_ref(account_ref: str) -> str:
        """Backend-side account identifier masking (NF-R203-06). First two /
        last two characters retained for support correlation; the middle is
        never projected. Short references collapse to a fixed mask."""
        ref = str(account_ref or "")
        if len(ref) <= 4:
            return "••••"
        return f"{ref[:2]}••••{ref[-2:]}"

    def _format_user_connection_row(self, row: sqlite3.Row, *, mask_account_ref: bool = False) -> dict[str, object]:
        # credential_ref value is NEVER projected; only its presence bit.
        return {
            "connectionId": row["connection_id"],
            "userId": row["user_id"],
            "provider": row["provider"],
            "accountRef": self._mask_account_ref(row["account_ref"]) if mask_account_ref else row["account_ref"],
            "hasCredentialRef": bool(row["credential_ref"]),
            "status": row["status"],
            "marketDataCapability": row["market_data_capability"],
            "executionCapability": row["execution_capability"],
            "healthState": row["health_state"],
            "suspended": bool(row["suspended"]),
            "suspendReason": row["suspend_reason"],
            "lastVerifiedAtUtc": row["last_verified_at_utc"],
            "createdAtUtc": row["created_at_utc"],
            "updatedAtUtc": row["updated_at_utc"],
        }

    def _require_active_user(self, cur, uid: str) -> None:
        user = cur.execute(
            "SELECT user_id, lifecycle, account_status FROM users WHERE user_id = ?", (uid,)
        ).fetchone()
        if user is None or user["lifecycle"] != "ACTIVE" or user["account_status"] != "ACTIVE":
            raise SecurityStoreError(f"User {uid} is not an active platform user")

    def create_user_connection(
        self,
        *,
        user_id: str | UUID,
        provider: str,
        account_ref: str,
        credential_ref: str | None = None,
        actor: str = "USER",
    ) -> dict[str, object]:
        """Create an isolated per-user broker/API connection record.

        ARCHITECTURE ONLY: creating a record never connects to a broker, never
        verifies credentials, and never enables execution. New records start
        NOT_CONNECTED with honest UNAVAILABLE / DISABLED_DISARMED capabilities.
        """
        uid = str(user_id)
        prov = (provider or "").upper().strip()
        if prov not in self.USER_CONNECTION_PROVIDERS:
            raise SecurityStoreError(f"Unsupported broker provider '{provider}'")
        acct = (account_ref or "").strip()
        if not acct or len(acct) > 128:
            raise SecurityStoreError("A non-empty account reference (max 128 chars) is required")
        if credential_ref is not None and (not str(credential_ref).strip() or len(str(credential_ref)) > 256):
            raise SecurityStoreError("Invalid credential reference")
        now_iso = _utc_now().isoformat()
        connection_id = f"CONN-{uuid4().hex}"
        with self._transaction() as cur:
            self._require_active_user(cur, uid)
            cur.execute("""INSERT INTO user_connections (
                connection_id, user_id, provider, account_ref, credential_ref,
                status, market_data_capability, execution_capability, health_state,
                suspended, suspend_reason, last_verified_at_utc, created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, 'NOT_CONNECTED', 'UNAVAILABLE', 'DISABLED_DISARMED',
                      'UNKNOWN', 0, NULL, NULL, ?, ?)""",
                (connection_id, uid, prov, acct,
                 str(credential_ref).strip() if credential_ref else None, now_iso, now_iso))
        row = self._conn.execute(
            "SELECT * FROM user_connections WHERE connection_id = ?", (connection_id,)).fetchone()
        return self._format_user_connection_row(row)

    def get_user_connection(
        self, connection_id: str, user_id: str | UUID | None,
    ) -> dict[str, object] | None:
        """Tenant-scoped read. user_id=None is explicit Owner oversight (all users)."""
        row = self._conn.execute(
            "SELECT * FROM user_connections WHERE connection_id = ?", (connection_id,)).fetchone()
        if row is None:
            return None
        if user_id is not None and row["user_id"] != str(user_id):
            return None
        return self._format_user_connection_row(row)

    def list_user_connections(
        self, user_id: str | UUID | None, *, mask_account_ref: bool = False,
    ) -> list[dict[str, object]]:
        """Tenant-scoped list. user_id=None is explicit Owner oversight (all users).

        mask_account_ref=True projects backend-masked account identifiers
        (Owner bulk overview). The record owner's own reads stay exact.
        """
        if user_id is None:
            rows = self._conn.execute(
                "SELECT * FROM user_connections ORDER BY created_at_utc ASC").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM user_connections WHERE user_id = ? ORDER BY created_at_utc ASC",
                (str(user_id),)).fetchall()
        return [self._format_user_connection_row(r, mask_account_ref=mask_account_ref) for r in rows]

    def retire_user_connection(
        self, *, connection_id: str, user_id: str | UUID | None,
        reason: str | None = None, actor: str = "USER",
    ) -> dict[str, object]:
        """Explicit retirement contract (NF-R203-06). The record is preserved
        for deployments/audit/reports history, but operationally dead: status
        RETIRED (never CONFIGURED) and credential_ref cleared (no dangling
        secret reference). Retired records are immutable via the normal update
        path; only Owner/system status control may restore them. Suspended
        records are Owner-governed and cannot be retired by the user.
        Idempotent: retiring an already-RETIRED record returns it unchanged."""
        with self._transaction() as cur:
            row = cur.execute(
                "SELECT * FROM user_connections WHERE connection_id = ?", (connection_id,)).fetchone()
            if row is None:
                raise SecurityStoreError("Connection not found")
            if user_id is not None and row["user_id"] != str(user_id):
                raise SecurityStoreError("Connection not found")
            if row["status"] == "RETIRED":
                return self._format_user_connection_row(row)
            if row["suspended"]:
                raise SecurityStoreError("Connection is SUSPENDED by Owner; retirement requires Owner action")
            cur.execute("""UPDATE user_connections SET status = 'RETIRED', credential_ref = NULL,
                           suspend_reason = ?, updated_at_utc = ? WHERE connection_id = ?""",
                        (reason or "Retired by connection owner", _utc_now().isoformat(), connection_id))
        updated = self._conn.execute(
            "SELECT * FROM user_connections WHERE connection_id = ?", (connection_id,)).fetchone()
        return self._format_user_connection_row(updated)

    def get_operational_connection(
        self,
        user_id: str | UUID | None,
        provider: str | None = None,
        connection_id: str | None = None,
    ) -> dict[str, object] | None:
        """Resolve the canonical per-user operational connection (NF-R203-04).

        Ownership is enforced inside SQL (tenant-scoped predicate).
        When neither provider nor connection_id is specified, exactly one
        usable record is required; if multiple exist, raises ambiguous error.
        When provider or connection_id is specified, filters by that target.

        Usable = not suspended, status CONFIGURED, credential_ref present.
        """
        if user_id is None:
            raise SecurityStoreError("Operational connection requires an authenticated user")

        params: list[object] = [str(user_id)]
        where_clauses = [
            "user_id = ?",
            "(suspended IS NULL OR suspended = 0)",
            "status = 'CONFIGURED'",
            "credential_ref IS NOT NULL",
            "TRIM(credential_ref) != ''",
        ]
        if connection_id is not None:
            where_clauses.append("connection_id = ?")
            params.append(str(connection_id))
        if provider is not None:
            where_clauses.append("provider = ?")
            params.append(str(provider).upper().strip())

        query = f"""SELECT * FROM user_connections
                   WHERE {' AND '.join(where_clauses)}
                   ORDER BY created_at_utc ASC"""
        rows = self._conn.execute(query, tuple(params)).fetchall()
        if not rows:
            return None
        if len(rows) > 1 and connection_id is None:
            raise SecurityStoreError(
                "AMBIGUOUS_OPERATIONAL_CONNECTION: multiple usable connections; "
                "specify connection_id or retire extras before operational use"
            )
        row = rows[0]
        projected = self._format_user_connection_row(row)
        projected["credentialRef"] = row["credential_ref"]
        return projected

    def set_connection_credentials(
        self,
        *,
        connection_id: str,
        user_id: str | UUID,
        credentials: Any,
        vault: Any = None,
    ) -> str:
        """Encrypt broker credentials in LocalCredentialVault and associate with connection."""
        from dashboard.backend.credential_vault import LocalCredentialVault
        v = vault or LocalCredentialVault()
        cred_ref = v.store_credentials(str(user_id), connection_id, credentials)
        self.update_user_connection(
            connection_id=connection_id,
            user_id=user_id,
            credential_ref=cred_ref,
            status="CONFIGURED",
        )
        return cred_ref

    def get_connection_credentials(
        self,
        *,
        connection_id: str,
        user_id: str | UUID,
        vault: Any = None,
    ) -> Any:
        """Resolve and decrypt credentials from LocalCredentialVault."""
        from dashboard.backend.credential_vault import LocalCredentialVault
        conn = self.get_user_connection(connection_id, user_id)
        if not conn:
            raise SecurityStoreError(f"Connection '{connection_id}' not found for user")
        row = self._conn.execute(
            "SELECT credential_ref FROM user_connections WHERE connection_id = ? AND user_id = ?",
            (connection_id, str(user_id)),
        ).fetchone()
        if not row or not row["credential_ref"]:
            raise SecurityStoreError(f"No credential associated with connection '{connection_id}'")
        v = vault or LocalCredentialVault()
        return v.resolve_credentials(str(user_id), row["credential_ref"])

    def update_user_connection(
        self,
        *,
        connection_id: str,
        user_id: str | UUID | None,
        account_ref: str | None = None,
        credential_ref: str | None = None,
        clear_credential_ref: bool = False,
        status: str | None = None,
        actor: str = "USER",
    ) -> dict[str, object]:
        """Update own connection record. Cross-user update fails closed (not found).

        Users may move between NOT_CONNECTED / CONFIGURED / DISABLED only.
        SUSPENDED / ERROR are Owner/system states and cannot be set or cleared here.
        RETIRED records are immutable here (explicit retirement contract);
        only Owner/system status control may restore them.
        """
        with self._transaction() as cur:
            row = cur.execute(
                "SELECT * FROM user_connections WHERE connection_id = ?", (connection_id,)).fetchone()
            if row is None:
                raise SecurityStoreError("Connection not found")
            if user_id is not None and row["user_id"] != str(user_id):
                raise SecurityStoreError("Connection not found")
            if row["status"] == "RETIRED":
                raise SecurityStoreError("Connection is RETIRED and immutable; Owner may restore it")
            if row["suspended"] and status != "DISABLED":
                raise SecurityStoreError("Connection is SUSPENDED by Owner; only disable is permitted")
            updates: list[str] = []
            params: list[object] = []
            if account_ref is not None:
                acct = account_ref.strip()
                if not acct or len(acct) > 128:
                    raise SecurityStoreError("A non-empty account reference (max 128 chars) is required")
                updates.append("account_ref = ?")
                params.append(acct)
            if clear_credential_ref:
                updates.append("credential_ref = NULL")
            elif credential_ref is not None:
                cred = str(credential_ref).strip()
                if not cred or len(cred) > 256:
                    raise SecurityStoreError("Invalid credential reference")
                updates.append("credential_ref = ?")
                params.append(cred)
            if status is not None:
                st = status.upper().strip()
                if st not in self.USER_CONNECTION_USER_STATUSES:
                    raise SecurityStoreError(f"Status '{status}' cannot be set by the connection owner")
                updates.append("status = ?")
                params.append(st)
            if not updates:
                raise SecurityStoreError("No updatable connection fields supplied")
            updates.append("updated_at_utc = ?")
            params.append(_utc_now().isoformat())
            params.append(connection_id)
            cur.execute(f"UPDATE user_connections SET {', '.join(updates)} WHERE connection_id = ?", params)
        updated = self._conn.execute(
            "SELECT * FROM user_connections WHERE connection_id = ?", (connection_id,)).fetchone()
        return self._format_user_connection_row(updated)

    def set_user_connection_status(
        self,
        *,
        connection_id: str,
        status: str,
        reason: str | None = None,
        actor: str = "OWNER-001",
    ) -> dict[str, object]:
        """Owner/system connection status control (SUSPEND / RESTORE / ERROR)."""
        st = (status or "").upper().strip()
        if st not in self.USER_CONNECTION_ALL_STATUSES:
            raise SecurityStoreError(f"Invalid connection status '{status}'")
        now_iso = _utc_now().isoformat()
        with self._transaction() as cur:
            row = cur.execute(
                "SELECT * FROM user_connections WHERE connection_id = ?", (connection_id,)).fetchone()
            if row is None:
                raise SecurityStoreError("Connection not found")
            suspended = 1 if st == "SUSPENDED" else 0
            suspend_reason = reason if st == "SUSPENDED" else None
            cur.execute("""UPDATE user_connections SET status = ?, suspended = ?, suspend_reason = ?,
                           updated_at_utc = ? WHERE connection_id = ?""",
                        (st, suspended, suspend_reason, now_iso, connection_id))
        updated = self._conn.execute(
            "SELECT * FROM user_connections WHERE connection_id = ?", (connection_id,)).fetchone()
        return self._format_user_connection_row(updated)

    def map_strategy_connection(
        self,
        *,
        user_id: str | UUID,
        strategy_id: str,
        connection_id: str,
        execution_mode: str = "LIVE_PAPER",
        strategy_version_id: str | None = None,
        governance_store=None,
        actor: str = "USER",
    ) -> dict[str, object]:
        """Map a strategy's canonical current version to an owned connection.

        Mapping is preparation only: it never enables execution. LIVE mappings are
        recorded but remain non-executable while live execution is DISARMED.

        The mapping deliberately follows the canonical current strategy version.
        A client-supplied version is only an assertion and must match that version.
        """
        uid = str(user_id)
        mode = (execution_mode or "").upper().strip()
        if mode not in self.STRATEGY_CONNECTION_MODES:
            raise SecurityStoreError(f"Invalid execution mode '{execution_mode}'")
        if governance_store is None or not hasattr(governance_store, "_conn"):
            raise SecurityStoreError("Canonical strategy governance authority unavailable")

        registered = self.get_owner_strategy(strategy_id)
        if registered is None:
            raise SecurityStoreError("Strategy is not registered")
        canonical_version_id = str(registered.get("version") or "").strip()
        if not canonical_version_id:
            raise SecurityStoreError("Canonical strategy version is unavailable")
        if strategy_version_id is not None and str(strategy_version_id) != canonical_version_id:
            raise SecurityStoreError("Strategy version does not match the canonical current version")
        version_row = governance_store._conn.execute(
            "SELECT * FROM strategy_versions WHERE version_id = ?",
            (canonical_version_id,),
        ).fetchone()
        if version_row is None:
            raise SecurityStoreError("Canonical strategy version does not exist")
        if str(version_row["strategy_id"]) != str(strategy_id):
            raise SecurityStoreError("Strategy version belongs to an unrelated strategy")
        if bool(version_row["archived"]) or str(version_row["stage"]).upper() == "ARCHIVED":
            raise SecurityStoreError("Canonical strategy version is archived")
        registered_author = str(registered.get("author") or "").strip()
        if registered_author and str(version_row["owner_id"]) != registered_author:
            raise SecurityStoreError("Strategy version owner does not match strategy authority")
        canonical_source_sha256 = str(version_row["source_sha256"] or "").strip()
        if not canonical_source_sha256:
            raise SecurityStoreError("Canonical strategy artifact digest is unavailable")

        with self._transaction() as cur:
            self._require_active_user(cur, uid)
            conn = cur.execute(
                "SELECT * FROM user_connections WHERE connection_id = ?", (connection_id,)).fetchone()
            if conn is None or conn["user_id"] != uid:
                raise SecurityStoreError("Connection not found for this user")
            if conn["suspended"] or conn["status"] == "DISABLED":
                raise SecurityStoreError("Connection is not usable (suspended or disabled)")
            access = self.check_user_strategy_access(uid, strategy_id)
            if not access.get("permitted"):
                raise SecurityStoreError("Cross-user strategy mapping denied")
            current = cur.execute(
                "SELECT version FROM owner_strategies WHERE strategy_id = ?",
                (strategy_id,),
            ).fetchone()
            if current is None or str(current["version"]) != canonical_version_id:
                raise SecurityStoreError("Canonical strategy version changed during mapping")
            now_iso = _utc_now().isoformat()
            mapping_id = f"MAP-{uuid4().hex}"
            cur.execute("""INSERT INTO strategy_connection_mappings (
                mapping_id, user_id, strategy_id, strategy_version_id, source_sha256,
                connection_id, account_ref, execution_mode, created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, strategy_id, execution_mode) DO UPDATE SET
                strategy_version_id = excluded.strategy_version_id,
                source_sha256 = excluded.source_sha256,
                connection_id = excluded.connection_id,
                account_ref = excluded.account_ref,
                updated_at_utc = excluded.updated_at_utc""",
                (mapping_id, uid, strategy_id, canonical_version_id,
                 canonical_source_sha256, connection_id, conn["account_ref"],
                 mode, now_iso, now_iso))
            row = cur.execute(
                """SELECT * FROM strategy_connection_mappings
                   WHERE user_id = ? AND strategy_id = ? AND execution_mode = ?""",
                (uid, strategy_id, mode)).fetchone()
            return dict(row)

    def get_strategy_connection_mapping(
        self, user_id: str | UUID | None, strategy_id: str, execution_mode: str = "LIVE_PAPER",
    ) -> dict[str, object] | None:
        """Tenant-scoped mapping read. user_id=None is explicit Owner oversight."""
        mode = (execution_mode or "").upper().strip()
        if user_id is None:
            row = self._conn.execute(
                """SELECT * FROM strategy_connection_mappings WHERE strategy_id = ? AND execution_mode = ?""",
                (strategy_id, mode)).fetchone()
        else:
            row = self._conn.execute(
                """SELECT * FROM strategy_connection_mappings
                   WHERE user_id = ? AND strategy_id = ? AND execution_mode = ?""",
                (str(user_id), strategy_id, mode)).fetchone()
        return dict(row) if row else None

    # ── P1-A (R-07): persistent strategy deployment authority ──

    DEPLOYMENT_STATUSES = frozenset({"DEPLOYED", "PAUSED", "STOPPED", "BLOCKED"})
    DEPLOYMENT_TERMINAL_STATUSES = frozenset({"STOPPED"})
    DEPLOYMENT_BLOCK_AUTHORITIES = frozenset({"NONE", "POLICY", "OWNER", "SYSTEM", "LEGACY"})

    @staticmethod
    def _deployment_connection_readiness_from_row(row: sqlite3.Row) -> dict[str, object]:
        status = str(row["status"] or "NOT_CONNECTED").upper()
        if bool(row["suspended"]) or status != "CONFIGURED":
            return {"permitted": False, "reason": f"CONNECTION_STATUS_{status}: connection is not deployable"}
        if str(row["market_data_capability"] or "").upper() != "READY":
            return {
                "permitted": False,
                "reason": "MARKET_DATA_CAPABILITY_NOT_READY: positive market-data authority is required",
            }
        if str(row["health_state"] or "").upper() != "HEALTHY":
            return {"permitted": False, "reason": "CONNECTION_HEALTH_NOT_READY: connection is not healthy"}
        if not row["last_verified_at_utc"]:
            return {"permitted": False, "reason": "CONNECTION_UNVERIFIED: verification timestamp is required"}
        return {
            "permitted": True,
            "reason": None,
            "connectionId": row["connection_id"],
            "accountRef": row["account_ref"],
        }

    def check_user_connection_deployment_readiness(
        self,
        *,
        user_id: str | UUID,
        connection_id: str | None,
        execution_mode: str,
    ) -> dict[str, object]:
        """Return positively verified connection readiness for deployment.

        CONFIGURED is metadata only. LIVE_PAPER additionally requires a current
        positive market-data capability, healthy state, and verification time.
        No broker contact or credential resolution occurs here.
        """
        uid = str(user_id)
        mode = (execution_mode or "").upper().strip()
        if mode not in self.STRATEGY_CONNECTION_MODES:
            raise SecurityStoreError(f"Invalid execution mode '{execution_mode}'")
        if connection_id is None:
            return {"permitted": False, "reason": "CONNECTION_REQUIRED: deployment requires a canonical connection"}
        row = self._conn.execute(
            "SELECT * FROM user_connections WHERE connection_id = ?", (connection_id,)
        ).fetchone()
        if row is None or row["user_id"] != uid:
            raise SecurityStoreError("Connection not found for this user")
        return self._deployment_connection_readiness_from_row(row)

    def _format_deployment_row(self, row: sqlite3.Row) -> dict[str, object]:
        return {
            "deploymentId": row["deployment_id"],
            "userId": row["user_id"],
            "strategyId": row["strategy_id"],
            "strategyVersionId": row["strategy_version_id"],
            "sourceSha256": row["source_sha256"],
            "connectionId": row["connection_id"],
            "accountRef": row["account_ref"],
            "instrument": row["instrument"],
            "timeframe": row["timeframe"],
            "executionMode": row["execution_mode"],
            "riskRef": row["risk_ref"],
            "status": row["status"],
            "blockReason": row["block_reason"],
            "blockAuthority": row["block_authority"],
            "runtimeSessionId": row["runtime_session_id"],
            "createdAtUtc": row["created_at_utc"],
            "updatedAtUtc": row["updated_at_utc"],
            "lastTransitionAtUtc": row["last_transition_at_utc"],
        }

    def create_deployment(
        self,
        *,
        user_id: str | UUID,
        strategy_id: str,
        strategy_version_id: str | None = None,
        source_sha256: str | None = None,
        connection_id: str | None = None,
        account_ref: str | None = None,
        instrument: str,
        timeframe: str,
        execution_mode: str = "LIVE_PAPER",
        risk_ref: str | None = None,
        actor: str = "USER",
    ) -> dict[str, object]:
        """Persist a strategy deployment. State machine entry only — no execution.

        LIVE mode records are created BLOCKED while live execution is DISARMED
        (fail closed, honest record). Nothing here arms or mutates any broker.
        """
        uid = str(user_id)
        mode = (execution_mode or "").upper().strip()
        if mode not in self.STRATEGY_CONNECTION_MODES:
            raise SecurityStoreError(f"Invalid execution mode '{execution_mode}'")
        inst = (instrument or "").upper().strip()
        tf = (timeframe or "").strip()
        if not inst or not tf:
            raise SecurityStoreError("Deployment instrument and timeframe are required")
        now_iso = _utc_now().isoformat()
        deployment_id = f"DEP-{uuid4().hex}"
        with self._transaction() as cur:
            self._require_active_user(cur, uid)
            access = self.check_user_strategy_access(uid, strategy_id)
            if not access.get("permitted"):
                raise SecurityStoreError("Cross-user deployment denied")

            if connection_id is None:
                readiness = {
                    "permitted": False,
                    "reason": "CONNECTION_REQUIRED: deployment requires a canonical connection",
                }
                account_ref = None
            else:
                conn = cur.execute(
                    "SELECT * FROM user_connections WHERE connection_id = ?", (connection_id,)
                ).fetchone()
                if conn is None or conn["user_id"] != uid:
                    raise SecurityStoreError("Connection not found for this user")
                readiness = self._deployment_connection_readiness_from_row(conn)
                account_ref = conn["account_ref"]

            identity_complete = bool(strategy_version_id and source_sha256)
            if not identity_complete:
                status = "BLOCKED"
                block_reason = "DEPLOYMENT_IDENTITY_INCOMPLETE: exact strategy version and artifact digest are required"
                block_authority = "POLICY"
            elif not readiness.get("permitted"):
                status = "BLOCKED"
                block_reason = str(readiness.get("reason") or "CONNECTION_NOT_READY")
                block_authority = "POLICY"
            elif mode == "LIVE":
                strat_row = cur.execute("SELECT stage FROM owner_strategies WHERE strategy_id = ?", (strategy_id,)).fetchone()
                current_stage = strat_row["stage"] if strat_row else None
                if current_stage != "LIVE_ELIGIBLE":
                    status = "BLOCKED"
                    block_reason = f"Strategy '{strategy_id}' stage is {current_stage}; LIVE_ELIGIBLE required for live deployment"
                    block_authority = "POLICY"
                else:
                    live_elig = self.check_self_service_live_eligibility(strategy_id, user_id=uid)
                    if not live_elig.get("permitted"):
                        status = "BLOCKED"
                        block_reason = str(live_elig.get("reason") or "STRATEGY_NOT_LIVE_ELIGIBLE")
                        block_authority = "POLICY"
                    else:
                        status, block_reason, block_authority = "DEPLOYED", None, "NONE"
            else:
                status, block_reason, block_authority = "DEPLOYED", None, "NONE"

            # DB-009: Transaction-level preflight check for existing active deployment
            active_existing = cur.execute(
                """SELECT deployment_id FROM strategy_deployments
                   WHERE user_id = ? AND strategy_id = ? AND instrument = ? AND timeframe = ? AND execution_mode = ?
                     AND status IN ('DEPLOYED', 'PAUSED', 'BLOCKED')
                   LIMIT 1""",
                (uid, strategy_id, inst, tf, mode),
            ).fetchone()
            if active_existing is not None:
                raise SecurityStoreError(
                    f"An active deployment already exists for strategy '{strategy_id}', instrument '{inst}', timeframe '{tf}', and mode '{mode}'"
                )

            try:
                cur.execute("""INSERT INTO strategy_deployments (
                    deployment_id, user_id, strategy_id, strategy_version_id, source_sha256,
                    connection_id, account_ref, instrument, timeframe, execution_mode, risk_ref,
                    status, block_reason, block_authority, runtime_session_id,
                    created_at_utc, updated_at_utc, last_transition_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)""",
                    (deployment_id, uid, strategy_id, strategy_version_id, source_sha256,
                     connection_id, account_ref, inst, tf, mode, risk_ref,
                     status, block_reason, block_authority, now_iso, now_iso, now_iso))
            except sqlite3.IntegrityError as err:
                err_lower = str(err).lower()
                if "idx_strategy_deployments_active_unique" in err_lower or "unique constraint failed" in err_lower:
                    raise SecurityStoreError(
                        f"An active deployment already exists for strategy '{strategy_id}', instrument '{inst}', timeframe '{tf}', and mode '{mode}'"
                    ) from err
                raise
        row = self._conn.execute(
            "SELECT * FROM strategy_deployments WHERE deployment_id = ?", (deployment_id,)).fetchone()
        return self._format_deployment_row(row)

    def get_deployment(
        self, deployment_id: str, user_id: str | UUID | None,
    ) -> dict[str, object] | None:
        """Tenant-scoped read. user_id=None is explicit Owner oversight."""
        row = self._conn.execute(
            "SELECT * FROM strategy_deployments WHERE deployment_id = ?", (deployment_id,)).fetchone()
        if row is None:
            return None
        if user_id is not None and row["user_id"] != str(user_id):
            return None
        return self._format_deployment_row(row)

    def list_deployments(
        self, user_id: str | UUID | None, *, status: str | None = None,
    ) -> list[dict[str, object]]:
        """Tenant-scoped list. user_id=None is explicit Owner oversight."""
        clauses: list[str] = []
        params: list[object] = []
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(str(user_id))
        if status is not None:
            st = status.upper().strip()
            if st not in self.DEPLOYMENT_STATUSES:
                raise SecurityStoreError(f"Invalid deployment status '{status}'")
            clauses.append("status = ?")
            params.append(st)
        query = "SELECT * FROM strategy_deployments"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at_utc ASC"
        rows = self._conn.execute(query, params).fetchall()
        return [self._format_deployment_row(r) for r in rows]

    def transition_deployment(
        self,
        *,
        deployment_id: str,
        user_id: str | UUID | None,
        action: str,
        reason: str | None = None,
        actor: str = "USER",
        block_authority: str | None = None,
        runtime_session_id: str | None = None,
    ) -> dict[str, object]:
        """Authoritative deployment state machine. Terminal STOPPED never reactivates.

        Actions: pause (DEPLOYED→PAUSED), resume (PAUSED or policy-recoverable
        BLOCKED→DEPLOYED after caller re-validation), stop
        (DEPLOYED/PAUSED/BLOCKED→STOPPED), block (Owner/system: any→BLOCKED).
        Resume from BLOCKED re-checks strategy self-service eligibility and
        connection usability; LIVE mode always re-blocks while disarmed.
        """
        act = (action or "").lower().strip()
        if act not in {"pause", "resume", "stop", "block"}:
            raise SecurityStoreError(f"Invalid deployment action '{action}'")
        is_owner_scope = user_id is None
        with self._transaction() as cur:
            row = cur.execute(
                "SELECT * FROM strategy_deployments WHERE deployment_id = ?", (deployment_id,)).fetchone()
            if row is None:
                raise SecurityStoreError("Deployment not found")
            if not is_owner_scope and row["user_id"] != str(user_id):
                raise SecurityStoreError("Deployment not found")
            current = row["status"]
            if current in self.DEPLOYMENT_TERMINAL_STATUSES:
                raise SecurityStoreError(f"Deployment is {current} (terminal) and cannot transition")
            now_iso = _utc_now().isoformat()
            new_status = current
            block_reason = row["block_reason"]
            current_block_authority = str(row["block_authority"] or "LEGACY").upper()
            new_block_authority = current_block_authority
            if act == "pause":
                if current != "DEPLOYED":
                    raise SecurityStoreError(f"Only DEPLOYED deployments can be paused (current: {current})")
                new_status, block_reason, new_block_authority = "PAUSED", None, "NONE"
            elif act == "stop":
                new_status, block_reason, new_block_authority = "STOPPED", None, "NONE"
            elif act == "block":
                if not is_owner_scope and actor.upper() != "SYSTEM":
                    raise SecurityStoreError("Only Owner oversight or system safety may block a deployment")
                new_status = "BLOCKED"
                block_reason = reason or "Blocked by Owner oversight"
                actor_upper = actor.upper()
                if actor_upper == "SYSTEM":
                    requested_authority = (block_authority or "SYSTEM").upper().strip()
                    if requested_authority not in {"POLICY", "SYSTEM"}:
                        raise SecurityStoreError("System block authority must be POLICY or SYSTEM")
                    new_block_authority = requested_authority
                else:
                    new_block_authority = "OWNER"
            elif act == "resume":
                if current not in {"PAUSED", "BLOCKED"}:
                    raise SecurityStoreError(f"Only PAUSED or BLOCKED deployments can be resumed (current: {current})")
                if current == "BLOCKED" and current_block_authority != "POLICY":
                    raise SecurityStoreError(
                        f"{current_block_authority} blocked deployment cannot be resumed by the user"
                    )
                new_status, block_reason, new_block_authority = "DEPLOYED", None, "NONE"
            cur.execute("""UPDATE strategy_deployments SET status = ?, block_reason = ?, block_authority = ?,
                           runtime_session_id = COALESCE(?, runtime_session_id),
                           updated_at_utc = ?, last_transition_at_utc = ? WHERE deployment_id = ?""",
                        (new_status, block_reason, new_block_authority, runtime_session_id,
                         now_iso, now_iso, deployment_id))
        updated = self._conn.execute(
            "SELECT * FROM strategy_deployments WHERE deployment_id = ?", (deployment_id,)).fetchone()
        return self._format_deployment_row(updated)

    def set_deployment_runtime(
        self, *, deployment_id: str, user_id: str | UUID | None, runtime_session_id: str | None,
    ) -> dict[str, object]:
        """Link/unlink the runtime (paper session) reference. Tenant-scoped."""
        with self._transaction() as cur:
            row = cur.execute(
                "SELECT * FROM strategy_deployments WHERE deployment_id = ?", (deployment_id,)).fetchone()
            if row is None:
                raise SecurityStoreError("Deployment not found")
            if user_id is not None and row["user_id"] != str(user_id):
                raise SecurityStoreError("Deployment not found")
            cur.execute("""UPDATE strategy_deployments SET runtime_session_id = ?,
                           updated_at_utc = ? WHERE deployment_id = ?""",
                        (runtime_session_id, _utc_now().isoformat(), deployment_id))
        updated = self._conn.execute(
            "SELECT * FROM strategy_deployments WHERE deployment_id = ?", (deployment_id,)).fetchone()
        return self._format_deployment_row(updated)

    # ── Slice 4: Dataset Authority ──

    def _format_dataset_row(self, row: sqlite3.Row) -> dict[str, object]:
        eff_readiness, _ = compute_dataset_effective_readiness(
            system_readiness=row["system_readiness"],
            owner_approval=row["owner_approval"],
            system_blocker=row["system_blocker_reason"],
            provenance=row["provenance"],
            hash_sha256=row["hash_sha256"],
        )
        return {
            "id": row["id"],
            "datasetId": row["dataset_id"],
            "source": row["source"],
            "market": row["market"],
            "instrument": row["instrument"],
            "segment": row["segment"],
            "timeframe": row["timeframe"],
            "sourceTimezone": row["source_timezone"],
            "startDate": row["start_date"],
            "endDate": row["end_date"],
            "tradingDays": row["trading_days"],
            "rowCount": row["row_count"],
            "format": row["format"],
            "logicalPath": row["logical_path"],
            "gapStatus": row["gap_status"],
            "gapDetails": row["gap_details"],
            "provenance": row["provenance"],
            "hashSha256": row["hash_sha256"],
            "acquisitionState": row["acquisition_state"],
            "systemReadiness": row["system_readiness"],
            "systemBlockerReason": row["system_blocker_reason"],
            "verificationDetails": row["verification_details"],
            "ownerApproval": row["owner_approval"],
            "ownerHoldReason": row["owner_hold_reason"],
            "effectiveBacktestReadiness": eff_readiness,
            "lastUpdated": row["updated_at_utc"],
            "history": json.loads(row["history_json"]),
        }

    def list_owner_datasets(self) -> list[dict[str, object]]:
        rows = self._conn.execute("SELECT * FROM owner_datasets ORDER BY dataset_id ASC").fetchall()
        return [self._format_dataset_row(r) for r in rows]

    def get_owner_dataset(self, dataset_id: str) -> dict[str, object] | None:
        row = self._conn.execute(
            "SELECT * FROM owner_datasets WHERE dataset_id = ? OR id = ?",
            (dataset_id, dataset_id),
        ).fetchone()
        return self._format_dataset_row(row) if row else None

    def update_dataset_approval(
        self,
        dataset_id: str,
        approval: str,
        reason: str | None = None,
        actor: str = "OWNER-001",
    ) -> tuple[dict[str, object], str, str]:
        appr = approval.upper()
        if appr not in {"APPROVED", "HOLD", "REJECTED"}:
            raise SecurityStoreError(f"Invalid approval status: {approval}")

        with self._transaction() as cur:
            row = cur.execute(
                "SELECT * FROM owner_datasets WHERE dataset_id = ? OR id = ?",
                (dataset_id, dataset_id),
            ).fetchone()
            if row is None:
                raise SecurityStoreError("Dataset not found")

            history = json.loads(row["history_json"])
            now_str = _utc_now().strftime("%Y-%m-%d %H:%M UTC")
            now_iso = _utc_now().isoformat()
            history.insert(0, {
                "time": now_str,
                "action": f"OWNER_APPROVAL_{appr}",
                "actor": actor,
                "note": f"Owner set approval to {appr}" + (f": {reason}" if reason else ""),
                "tone": "ok" if appr == "APPROVED" else "warn",
            })
            hold_reason = reason or f"Placed on hold by {actor}" if appr == "HOLD" else (reason if appr == "REJECTED" else None)

            cur.execute(
                "UPDATE owner_datasets SET owner_approval = ?, owner_hold_reason = ?, history_json = ?, updated_at_utc = ? WHERE dataset_id = ?",
                (appr, hold_reason, json.dumps(history), now_iso, row["dataset_id"]),
            )

        updated_row = self._conn.execute(
            "SELECT * FROM owner_datasets WHERE dataset_id = ?", (row["dataset_id"],)
        ).fetchone()
        formatted = self._format_dataset_row(updated_row)
        eff_readiness = formatted["effectiveBacktestReadiness"]
        msg = f"Dataset '{row['dataset_id']}' Owner Approval set to {appr}."
        if appr == "APPROVED" and eff_readiness == "BLOCKED":
            msg += f" Effective readiness remains BLOCKED ({formatted.get('systemBlockerReason') or 'System gate unsatisfied'})."
        return formatted, eff_readiness, msg

    def check_backtest_gate(self, strategy_id: str, dataset_id: str, *, user_id=None,
                            instrument=None, timeframe=None) -> dict[str, object]:
        """One Owner governance policy, shared by preview and actual execution."""
        def deny(code, reason, strategy_status="BLOCKED", dataset_status="UNKNOWN"):
            return dict(permitted=False, code=code, reason=reason,
                        strategy_status=strategy_status, dataset_status=dataset_status)
        strat = self.get_owner_strategy(strategy_id)
        if strat is None:
            return deny("STRATEGY_UNKNOWN", f"Strategy '{strategy_id}' not found", "NOT_FOUND")
        if user_id is not None:
            user = self.get_user(user_id)
            if user is None or user["lifecycle"] != "ACTIVE" or user["account_status"] != "ACTIVE":
                return deny("SUBJECT_INACTIVE", "Active authenticated User required")
            if str(strat["author"]) != str(user_id):
                # F-10: persisted assignment confers execution eligibility
                # alongside authorship; unassigned users remain denied.
                # Phase B: explicit GLOBAL catalog strategies are executable
                # by active users without per-user assignment.
                assignment = self.get_strategy_assignment(str(user_id), strategy_id)
                if not assignment or assignment.get("assignment_status") != "ASSIGNED":
                    if (strat.get("visibility") or "OWNER_PRIVATE") != "GLOBAL":
                        return deny("STRATEGY_SUBJECT_MISMATCH", "Cross-user strategy execution denied")
        is_held, hold_reason = self.is_strategy_execution_held(strategy_id, "backtest")
        if is_held:
            return deny("STRATEGY_BLOCKED", f"Strategy backtest blocked: {hold_reason}")
        ds = self.get_owner_dataset(dataset_id)
        if ds is None:
            return deny("DATASET_UNKNOWN", f"Dataset '{dataset_id}' not found", "ELIGIBLE", "NOT_FOUND")
        if ds.get("hashSha256", "").removeprefix("sha256:").lower() == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855":
            return deny("DATASET_VACUOUS_HASH", "Dataset has empty-string sha256 digest and cannot be certified for execution", "ELIGIBLE", "BLOCKED")
        if ds["effectiveBacktestReadiness"] != "READY_FOR_BACKTEST":
            blocker = ds.get("systemBlockerReason") or ds.get("ownerHoldReason") or "Dataset not approved for backtest"
            return deny("DATASET_NOT_APPROVED", f"Dataset '{dataset_id}' not ready for backtest: {blocker}",
                        "ELIGIBLE", ds["effectiveBacktestReadiness"])
        if instrument is not None and ds["instrument"] != instrument:
            return deny("DATASET_INSTRUMENT_MISMATCH", "Requested instrument does not match approved dataset", "ELIGIBLE")
        if timeframe is not None and ds["timeframe"] != timeframe:
            return deny("DATASET_TIMEFRAME_MISMATCH", "Requested timeframe does not match approved dataset", "ELIGIBLE")
        return dict(permitted=True, code="GATE_PASS", reason="Strategy and Dataset verified eligible for backtest.",
                    strategy_status="ELIGIBLE", dataset_status="READY_FOR_BACKTEST", dataset=ds)

    def save_backtest_run(self, run: dict[str, object], *, expected_status=None) -> dict[str, object]:
        now_str = _utc_now().isoformat()
        with self._transaction() as cur:
            if expected_status is not None:
                current = cur.execute("SELECT status FROM backtest_runs WHERE run_id=?", (run["run_id"],)).fetchone()
                if current is None or current["status"] not in expected_status:
                    return self.get_backtest_run(str(run["run_id"]))
                if current["status"] == "CANCEL_REQUESTED":
                    # Cancellation won the transaction race. Discard all partial evidence.
                    run = self._cancelled_record(run)

            # DB-006: Verify referenced user identity exists
            # Historical retention rule: require user identity to exist, but do NOT require current ACTIVE status
            # to preserve validly submitted historical runs where user lifecycle changed after submission.
            uid = str(run.get("user_id") or "")
            if not uid:
                raise SecurityStoreError("Backtest run missing required user_id")
            user_row = cur.execute("SELECT user_id FROM users WHERE user_id = ?", (uid,)).fetchone()
            if user_row is None:
                raise SecurityStoreError(f"User '{uid}' is not a registered user")

            # DB-006: Verify referenced strategy identity is a known/registered strategy
            # Historical retention rule: require strategy identity to be known, but do NOT re-run eligibility/stage checks
            # so historical results are not rejected if the strategy was archived or transitioned after submission.
            strat_id = str(run.get("strategy_id") or "")
            if not strat_id:
                raise SecurityStoreError("Backtest run missing required strategy_id")
            strat_row = cur.execute(
                "SELECT strategy_id FROM owner_strategies WHERE strategy_id = ? OR id = ?",
                (strat_id, strat_id),
            ).fetchone()
            if strat_row is None:
                raise SecurityStoreError(f"Strategy '{strat_id}' is not a registered strategy")

            cur.execute(
                """INSERT OR REPLACE INTO backtest_runs (
                    run_id, user_id, strategy_id, strategy_name, version,
                    instrument, timeframe, date_range, initial_capital,
                    net_profit, net_profit_pct, win_rate, profit_factor,
                    sharpe_ratio, max_drawdown, total_trades, winning_trades,
                    losing_trades, avg_profit_trade, avg_win, avg_loss,
                    status, quality_score, policy_snapshot, policy_details_json,
                    data_fingerprint, data_source_name, manifest_fingerprint,
                    equity_curve_json, trades_json, created_at_utc, completed_at_utc,
                    error_message, execution_metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(run["run_id"]),
                    str(run["user_id"]),
                    str(run["strategy_id"]),
                    str(run.get("strategy_name", run["strategy_id"])),
                    str(run.get("version", "v1.0")),
                    str(run.get("instrument", "NIFTY")),
                    str(run.get("timeframe", "1m")),
                    str(run.get("date_range", "")),
                    float(run.get("initial_capital", 500000.0)),
                    float(run["net_profit"]) if run.get("net_profit") is not None else None,
                    float(run["net_profit_pct"]) if run.get("net_profit_pct") is not None else None,
                    float(run["win_rate"]) if run.get("win_rate") is not None else None,
                    float(run["profit_factor"]) if run.get("profit_factor") is not None else None,
                    float(run["sharpe_ratio"]) if run.get("sharpe_ratio") is not None else None,
                    float(run["max_drawdown"]) if run.get("max_drawdown") is not None else None,
                    int(run.get("total_trades", 0)),
                    int(run.get("winning_trades", 0)),
                    int(run.get("losing_trades", 0)),
                    float(run["avg_profit_trade"]) if run.get("avg_profit_trade") is not None else None,
                    float(run["avg_win"]) if run.get("avg_win") is not None else None,
                    float(run["avg_loss"]) if run.get("avg_loss") is not None else None,
                    str(run.get("status", "COMPLETED")),
                    float(run["quality_score"]) if run.get("quality_score") is not None else None,
                    str(run.get("policy_snapshot", "")),
                    json.dumps(run.get("policy_details", {}) if not isinstance(run.get("policy_details"), str) else json.loads(run["policy_details"])),
                    str(run.get("data_fingerprint", "")),
                    str(run.get("data_source_name", "")),
                    str(run.get("manifest_fingerprint", "")),
                    json.dumps(run.get("equity_curve", []) if not isinstance(run.get("equity_curve"), str) else json.loads(run["equity_curve"])),
                    json.dumps(run.get("trades", []) if not isinstance(run.get("trades"), str) else json.loads(run["trades"])),
                    str(run.get("created_at_utc", now_str)),
                    run.get("completed_at_utc"),
                    run.get("error_message"),
                    json.dumps(run.get("execution_metadata", {}), allow_nan=False),
                ),
            )
        ret = self.get_backtest_run(str(run["run_id"]))
        if ret is None:
            raise RuntimeError(f"Failed to persist backtest run {run['run_id']}")
        return ret

    def get_backtest_run(self, run_id: str, user_id: str | None = None) -> dict[str, object] | None:
        # R-09: ownership enforced inside SQL. user_id=None remains the
        # explicit Owner-oversight path.
        if user_id is not None:
            row = self._conn.execute(
                "SELECT * FROM backtest_runs WHERE run_id = ? AND user_id = ?",
                (run_id, user_id),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT * FROM backtest_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["execution_metadata"] = json.loads(d["execution_metadata_json"])
        try:
            d["policy_details"] = json.loads(d["policy_details_json"])
        except Exception:
            d["policy_details"] = {}
        try:
            d["equity_curve"] = json.loads(d["equity_curve_json"])
        except Exception:
            d["equity_curve"] = []
        try:
            d["trades"] = json.loads(d["trades_json"])
        except Exception:
            d["trades"] = []
        d.pop("execution_metadata_json", None)
        d.pop("policy_details_json", None)
        d.pop("equity_curve_json", None)
        d.pop("trades_json", None)
        return d

    def list_backtest_runs(self, user_id: str | None = None, limit: int = 50) -> list[dict[str, object]]:
        if user_id is not None:
            rows = self._conn.execute(
                "SELECT * FROM backtest_runs WHERE user_id = ? ORDER BY created_at_utc DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM backtest_runs ORDER BY created_at_utc DESC LIMIT ?",
                (limit,),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["execution_metadata"] = json.loads(d["execution_metadata_json"])
            try:
                d["policy_details"] = json.loads(d["policy_details_json"])
            except Exception:
                d["policy_details"] = {}
            try:
                d["equity_curve"] = json.loads(d["equity_curve_json"])
            except Exception:
                d["equity_curve"] = []
            d["trades_count"] = d["total_trades"]
            d.pop("execution_metadata_json", None)
            d.pop("policy_details_json", None)
            d.pop("equity_curve_json", None)
            d.pop("trades_json", None)
            result.append(d)
        return result

    def get_backtest_trades(self, run_id: str, user_id: str | None = None) -> list[dict[str, object]] | None:
        run = self.get_backtest_run(run_id, user_id=user_id)
        if run is None:
            return None
        return run.get("trades", [])

    # ── Phase I (R-05): walk-forward/OOS job authority ──

    WALKFORWARD_STATUSES = frozenset({"PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"})
    WALKFORWARD_TERMINAL_STATUSES = frozenset({"COMPLETED", "FAILED", "CANCELLED"})

    def create_walkforward_job(
        self, *, user_id: str | UUID, strategy_id: str, strategy_version_id: str | None,
        source_sha256: str | None, dataset_id: str, instrument: str, timeframe: str,
        is_days: int, oos_days: int, initial_capital: float, policy: dict[str, object] | None,
        windows: list[dict[str, object]],
    ) -> dict[str, object]:
        """Persist a manual walk-forward job (PENDING) with its IS/OOS windows."""
        uid = str(user_id)
        now_iso = _utc_now().isoformat()
        job_id = f"WF-{uuid4().hex}"
        with self._transaction() as cur:
            self._require_active_user(cur, uid)
            cur.execute("""INSERT INTO walkforward_jobs (
                job_id, user_id, strategy_id, strategy_version_id, source_sha256,
                dataset_id, instrument, timeframe, is_days, oos_days,
                initial_capital, policy_json, status, cancel_requested,
                overall_json, error_message, created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', 0, '{}', NULL, ?, ?)""",
                (job_id, uid, strategy_id, strategy_version_id, source_sha256,
                 dataset_id, instrument, timeframe, int(is_days), int(oos_days),
                 float(initial_capital), json.dumps(policy or {}), now_iso, now_iso))
            for seq, w in enumerate(windows):
                cur.execute("""INSERT INTO walkforward_windows (
                    window_id, job_id, user_id, seq, kind, start_date, end_date,
                    backtest_run_id, status, metrics_json, error_message,
                    created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 'PENDING', '{}', NULL, ?, ?)""",
                    (f"{job_id}-W{seq:02d}", job_id, uid, seq, w["kind"],
                     w["start_date"], w["end_date"], now_iso, now_iso))
        return self.get_walkforward_job(job_id, user_id=uid)

    def get_walkforward_job(
        self, job_id: str, user_id: str | UUID | None,
    ) -> dict[str, object] | None:
        """Tenant-scoped read with windows and progress. user_id=None is Owner oversight."""
        if user_id is not None:
            job = self._conn.execute(
                "SELECT * FROM walkforward_jobs WHERE job_id = ? AND user_id = ?",
                (job_id, str(user_id))).fetchone()
        else:
            job = self._conn.execute(
                "SELECT * FROM walkforward_jobs WHERE job_id = ?", (job_id,)).fetchone()
        if job is None:
            return None
        windows = self._conn.execute(
            "SELECT * FROM walkforward_windows WHERE job_id = ? ORDER BY seq ASC",
            (job_id,)).fetchall()
        return self._format_walkforward_job(job, windows)

    def list_walkforward_jobs(
        self, user_id: str | UUID | None, *, status: str | None = None,
    ) -> list[dict[str, object]]:
        """Tenant-scoped list (newest first). user_id=None is Owner oversight."""
        clauses: list[str] = []
        params: list[object] = []
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(str(user_id))
        if status is not None:
            st = status.upper().strip()
            if st not in self.WALKFORWARD_STATUSES:
                raise SecurityStoreError(f"Invalid walk-forward status '{status}'")
            clauses.append("status = ?")
            params.append(st)
        query = "SELECT * FROM walkforward_jobs"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at_utc DESC"
        jobs = self._conn.execute(query, params).fetchall()
        result = []
        for job in jobs:
            windows = self._conn.execute(
                "SELECT * FROM walkforward_windows WHERE job_id = ? ORDER BY seq ASC",
                (job["job_id"],)).fetchall()
            result.append(self._format_walkforward_job(job, windows))
        return result

    def _format_walkforward_job(self, job: sqlite3.Row, windows: list[sqlite3.Row]) -> dict[str, object]:
        window_dicts = []
        for w in windows:
            try:
                metrics = json.loads(w["metrics_json"] or "{}")
            except Exception:
                metrics = {}
            window_dicts.append({
                "windowId": w["window_id"], "seq": w["seq"], "kind": w["kind"],
                "startDate": w["start_date"], "endDate": w["end_date"],
                "backtestRunId": w["backtest_run_id"],
                "paperSessionId": w["paper_session_id"] if "paper_session_id" in w.keys() else None,
                "status": w["status"],
                "metrics": metrics, "error": w["error_message"],
            })
        try:
            overall = json.loads(job["overall_json"] or "{}")
        except Exception:
            overall = {}
        try:
            policy = json.loads(job["policy_json"] or "{}")
        except Exception:
            policy = {}
        done = sum(1 for w in window_dicts if w["status"] in ("COMPLETED", "FAILED", "CANCELLED"))
        return {
            "jobId": job["job_id"], "userId": job["user_id"],
            "strategyId": job["strategy_id"], "strategyVersionId": job["strategy_version_id"],
            "sourceSha256": job["source_sha256"], "datasetId": job["dataset_id"],
            "instrument": job["instrument"], "timeframe": job["timeframe"],
            "isDays": job["is_days"], "oosDays": job["oos_days"],
            "initialCapital": job["initial_capital"], "policy": policy,
            "status": job["status"], "cancelRequested": bool(job["cancel_requested"]),
            "overall": overall, "error": job["error_message"],
            "windows": window_dicts,
            "progress": {"done": done, "total": len(window_dicts)},
            "createdAtUtc": job["created_at_utc"], "updatedAtUtc": job["updated_at_utc"],
        }

    def update_walkforward_job(
        self, *, job_id: str, user_id: str | UUID | None = None,
        status: str | None = None, overall: dict[str, object] | None = None,
        error: str | None = None, cancel_requested: bool | None = None,
    ) -> dict[str, object] | None:
        """Worker/owner status updates. Terminal records are immutable except overall."""
        with self._transaction() as cur:
            if user_id is not None:
                row = cur.execute(
                    "SELECT * FROM walkforward_jobs WHERE job_id = ? AND user_id = ?",
                    (job_id, str(user_id))).fetchone()
            else:
                row = cur.execute(
                    "SELECT * FROM walkforward_jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                return None
            updates: list[str] = []
            params: list[object] = []
            if cancel_requested is not None:
                updates.append("cancel_requested = ?")
                params.append(1 if cancel_requested else 0)
            if status is not None:
                st = status.upper().strip()
                if st not in self.WALKFORWARD_STATUSES:
                    raise SecurityStoreError(f"Invalid walk-forward status '{status}'")
                if row["status"] in self.WALKFORWARD_TERMINAL_STATUSES and st != row["status"]:
                    raise SecurityStoreError(f"Walk-forward job is {row['status']} (terminal)")
                updates.append("status = ?")
                params.append(st)
            if overall is not None:
                updates.append("overall_json = ?")
                params.append(json.dumps(overall))
            if error is not None:
                updates.append("error_message = ?")
                params.append(error)
            if updates:
                updates.append("updated_at_utc = ?")
                params.append(_utc_now().isoformat())
                params.append(job_id)
                cur.execute(f"UPDATE walkforward_jobs SET {', '.join(updates)} WHERE job_id = ?", params)
        return self.get_walkforward_job(job_id, user_id=user_id)

    def update_walkforward_window(
        self, *, window_id: str, status: str | None = None,
        backtest_run_id: str | None = None, paper_session_id: str | None = None,
        metrics: dict[str, object] | None = None, error: str | None = None,
    ) -> None:
        updates: list[str] = []
        params: list[object] = []
        if status is not None:
            updates.append("status = ?")
            params.append(status.upper().strip())
        if backtest_run_id is not None:
            updates.append("backtest_run_id = ?")
            params.append(backtest_run_id)
        if paper_session_id is not None:
            updates.append("paper_session_id = ?")
            params.append(paper_session_id)
        if metrics is not None:
            updates.append("metrics_json = ?")
            params.append(json.dumps(metrics))
        if error is not None:
            updates.append("error_message = ?")
            params.append(error)
        if not updates:
            return
        updates.append("updated_at_utc = ?")
        params.append(_utc_now().isoformat())
        params.append(window_id)
        with self._transaction() as cur:
            cur.execute(f"UPDATE walkforward_windows SET {', '.join(updates)} WHERE window_id = ?", params)

    def request_walkforward_cancel(self, *, job_id: str, user_id: str | UUID | None) -> dict[str, object] | None:
        """Cooperative cancel: flags the job; the worker stops between windows."""
        with self._transaction() as cur:
            if user_id is not None:
                row = cur.execute(
                    "SELECT * FROM walkforward_jobs WHERE job_id = ? AND user_id = ?",
                    (job_id, str(user_id))).fetchone()
            else:
                row = cur.execute(
                    "SELECT * FROM walkforward_jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                return None
            if row["status"] in self.WALKFORWARD_TERMINAL_STATUSES:
                raise SecurityStoreError(f"Walk-forward job is {row['status']} (terminal)")
            cur.execute("UPDATE walkforward_jobs SET cancel_requested = 1, updated_at_utc = ? WHERE job_id = ?",
                        (_utc_now().isoformat(), job_id))
        return self.get_walkforward_job(job_id, user_id=user_id)

    @staticmethod
    def _cancelled_record(run):
        run = dict(run)
        run.update(status="CANCELLED", completed_at_utc=_utc_now().isoformat(),
                   error_message="CANCELLED_BY_OPERATOR", trades=[], equity_curve=[],
                   total_trades=0, winning_trades=0, losing_trades=0)
        for key in ("net_profit", "net_profit_pct", "win_rate", "profit_factor", "sharpe_ratio",
                    "max_drawdown", "avg_profit_trade", "avg_win", "avg_loss", "quality_score"):
            run[key] = None
        meta = dict(run["execution_metadata"])
        for key in ("signal_evidence", "metric_evidence_id", "financial_provenance"):
            meta.pop(key, None)
        meta["metric_status"] = "UNAVAILABLE_CANCELLED"
        meta["bars_consumed"] = None
        run["execution_metadata"] = meta
        return run

    def cancel_backtest_run(self, run_id: str, user_id: str | None = None) -> bool:
        with self._transaction() as cur:
            row = cur.execute("SELECT user_id,status FROM backtest_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None or user_id is not None and row["user_id"] != user_id:
                return False
            if row["status"] == "PENDING":
                cur.execute("UPDATE backtest_runs SET status='CANCELLED', error_message='CANCELLED_BEFORE_EXECUTION', completed_at_utc=? WHERE run_id=?",
                            (_utc_now().isoformat(),run_id))
            elif row["status"] == "RUNNING":
                cur.execute("UPDATE backtest_runs SET status='CANCEL_REQUESTED', error_message='CANCEL_REQUESTED_BY_OPERATOR' WHERE run_id=?", (run_id,))
            # Terminal history and an existing intention are immutable/idempotent.
            return True

    def claim_backtest_job(self, run_id):
        with self._transaction() as cur:
            cur.execute("UPDATE backtest_runs SET status='RUNNING' WHERE run_id=? AND status='PENDING'", (run_id,))
            return cur.rowcount == 1

    def interrupt_backtest_jobs(self, reason, *, run_id=None):
        with self._transaction() as cur:
            query = "UPDATE backtest_runs SET status='FAILED', error_message=?, completed_at_utc=? WHERE status IN ('PENDING','RUNNING','CANCEL_REQUESTED')"
            args = [reason, _utc_now().isoformat()]
            if run_id is not None:
                query += " AND run_id=?"
                args.append(run_id)
            cur.execute(query, args)

    def interrupt_walkforward_jobs(self, reason: str, *, job_id: str | None = None) -> None:
        """Mark interrupted PENDING or RUNNING walkforward jobs as FAILED across restart/failure."""
        now_iso = _utc_now().isoformat()
        with self._transaction() as cur:
            query = "UPDATE walkforward_jobs SET status = 'FAILED', error_message = ?, updated_at_utc = ? WHERE status IN ('PENDING', 'RUNNING')"
            args = [reason, now_iso]
            if job_id is not None:
                query += " AND job_id = ?"
                args.append(job_id)
            cur.execute(query, args)

    def worker_copy(self):
        """Open only an existing, already hardened database; no seeding/bootstrap."""
        from copy import copy
        worker = copy(self)
        worker._conn = sqlite3.connect(self.path, timeout=30, factory=SerializedConnection)
        worker._conn.row_factory = sqlite3.Row
        worker._conn.execute("PRAGMA foreign_keys=ON")
        worker._transaction_lock = worker._conn.access_lock
        return worker

    # ── BI-2 Slice 5: Paper Trading State & History ──

    def save_live_observation(self, user_id: str, key: str, payload: dict) -> None:
        """Sanitized read observations/intent receipts only; never broker credentials."""
        with self._transaction() as cur:
            cur.execute("""INSERT INTO live_readiness_observations VALUES (?, ?, ?)
                ON CONFLICT(user_id, observation_key) DO UPDATE SET payload_json=excluded.payload_json""",
                (user_id, key, json.dumps(payload, allow_nan=False)))

    def live_observations(self, user_id: str | None = None) -> list[dict]:
        rows = self._conn.execute(
            "SELECT user_id, observation_key, payload_json FROM live_readiness_observations WHERE (? IS NULL OR user_id = ?) ORDER BY user_id, observation_key",
            (user_id, user_id),
        ).fetchall()
        return [{"user_id": r["user_id"], "key": r["observation_key"], "data": json.loads(r["payload_json"])} for r in rows]

    def live_global_hold(self) -> bool:
        row = self._conn.execute("SELECT value FROM security_metadata WHERE key='live_global_hold'").fetchone()
        return row is None or row["value"] != "false"

    def set_live_global_hold(self, enabled: bool) -> None:
        with self._transaction() as cur:
            cur.execute("UPDATE security_metadata SET value=? WHERE key='live_global_hold'", ("true" if enabled else "false",))

    def create_paper_session(
        self,
        *,
        session_id: str,
        user_id: str,
        strategy_id: str,
        strategy_name: str,
        strategy_version: str,
        instrument: str,
        timeframe: str,
        initial_capital: float,
        policy_snapshot: str,
        policy_details: dict[str, Any] | None = None,
        data_source_name: str = "HISTORICAL_REPLAY",
        data_source_mode: str = "HISTORICAL_REPLAY",
        feed_status: str = "DISCONNECTED",
        contract_identity: str | None = None,
        date_range: str | None = None,
        dataset_id: str | None = None,
        price_provenance: str = "MODELED",
    ) -> dict[str, Any]:
        now_str = _utc_now().isoformat()
        with self._transaction() as cur:
            # DB-006: Enforce active user validation and registered strategy validation at store boundary
            self._require_active_user(cur, str(user_id))
            strat = cur.execute(
                "SELECT strategy_id FROM owner_strategies WHERE strategy_id = ? OR id = ?",
                (str(strategy_id), str(strategy_id)),
            ).fetchone()
            if strat is None:
                raise SecurityStoreError(f"Strategy '{strategy_id}' is not a registered strategy")
            cur.execute(
                """INSERT INTO paper_sessions (
                    session_id, user_id, strategy_id, strategy_name, strategy_version,
                    instrument, timeframe, initial_capital, current_equity, available_cash,
                    used_capital, realized_pnl, unrealized_pnl, day_pnl, total_pnl,
                    return_pct, trades_count, status, owner_allowance, owner_hold_reason,
                    policy_snapshot, policy_details_json, data_source_name, data_source_mode,
                    feed_status, last_market_timestamp, last_quote_received_at, contract_identity,
                    live_quote_count, reconciliation_state, market_data_readiness,
                    persistence_health, created_at_utc, updated_at_utc,
                    date_range, dataset_id, price_provenance
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 'INITIALIZED', 'ALLOWED', NULL, ?, ?, ?, ?, ?, NULL, NULL, ?, 0, 'UNKNOWN', 'UNKNOWN', 'UNKNOWN', ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    user_id,
                    strategy_id,
                    strategy_name,
                    strategy_version,
                    instrument,
                    timeframe,
                    initial_capital,
                    initial_capital,
                    initial_capital,
                    0.0,
                    policy_snapshot,
                    json.dumps(policy_details or {}),
                    data_source_name,
                    data_source_mode,
                    feed_status,
                    contract_identity,
                    now_str,
                    now_str,
                    date_range,
                    dataset_id,
                    price_provenance,
                ),
            )
        ses = self.get_paper_session(session_id)
        if ses is None:
            raise SecurityStoreError(f"Failed to retrieve created paper session '{session_id}'")
        return ses

    def update_paper_session(
        self,
        session_id: str,
        *,
        status: str | None = None,
        current_equity: float | None = None,
        available_cash: float | None = None,
        used_capital: float | None = None,
        realized_pnl: float | None = None,
        unrealized_pnl: float | None = None,
        day_pnl: float | None = None,
        total_pnl: float | None = None,
        return_pct: float | None = None,
        trades_count: int | None = None,
        stopped_at_utc: str | None = None,
        error_message: str | None = None,
        data_source_mode: str | None = None,
        feed_status: str | None = None,
        last_market_timestamp: str | None = None,
        last_quote_received_at: str | None = None,
        contract_identity: str | None = None,
        live_quote_count: int | None = None,
        bars_consumed: int | None = None,
        first_consumed_timestamp: str | None = None,
        last_consumed_timestamp: str | None = None,
        requested_date_range: str | None = None,
        effective_date_range_json: str | None = None,
        price_provenance: str | None = None,
        risk_gate_status: str | None = None,
        feed_source: str | None = None,
    ) -> dict[str, Any] | None:
        now_str = _utc_now().isoformat()
        fields = ["updated_at_utc = ?"]
        params: list[Any] = [now_str]
        if status is not None:
            fields.append("status = ?")
            params.append(status)
        if current_equity is not None:
            fields.append("current_equity = ?")
            params.append(current_equity)
        if available_cash is not None:
            fields.append("available_cash = ?")
            params.append(available_cash)
        if used_capital is not None:
            fields.append("used_capital = ?")
            params.append(used_capital)
        if realized_pnl is not None:
            fields.append("realized_pnl = ?")
            params.append(realized_pnl)
        if unrealized_pnl is not None:
            fields.append("unrealized_pnl = ?")
            params.append(unrealized_pnl)
        if day_pnl is not None:
            fields.append("day_pnl = ?")
            params.append(day_pnl)
        if total_pnl is not None:
            fields.append("total_pnl = ?")
            params.append(total_pnl)
        if return_pct is not None:
            fields.append("return_pct = ?")
            params.append(return_pct)
        if trades_count is not None:
            fields.append("trades_count = ?")
            params.append(trades_count)
        if stopped_at_utc is not None:
            fields.append("stopped_at_utc = ?")
            params.append(stopped_at_utc)
        if error_message is not None:
            fields.append("error_message = ?")
            params.append(error_message)
        if data_source_mode is not None:
            fields.append("data_source_mode = ?")
            params.append(data_source_mode)
        if feed_status is not None:
            fields.append("feed_status = ?")
            params.append(feed_status)
        if last_market_timestamp is not None:
            fields.append("last_market_timestamp = ?")
            params.append(last_market_timestamp)
        if last_quote_received_at is not None:
            fields.append("last_quote_received_at = ?")
            params.append(last_quote_received_at)
        if contract_identity is not None:
            fields.append("contract_identity = ?")
            params.append(contract_identity)
        if live_quote_count is not None:
            fields.append("live_quote_count = ?")
            params.append(live_quote_count)
        if bars_consumed is not None:
            fields.append("bars_consumed = ?")
            params.append(bars_consumed)
        if first_consumed_timestamp is not None:
            fields.append("first_consumed_timestamp = ?")
            params.append(first_consumed_timestamp)
        if last_consumed_timestamp is not None:
            fields.append("last_consumed_timestamp = ?")
            params.append(last_consumed_timestamp)
        if requested_date_range is not None:
            fields.append("requested_date_range = ?")
            params.append(requested_date_range)
        if effective_date_range_json is not None:
            fields.append("effective_date_range_json = ?")
            params.append(effective_date_range_json)
        if price_provenance is not None:
            fields.append("price_provenance = ?")
            params.append(price_provenance)
        if risk_gate_status is not None:
            fields.append("risk_gate_status = ?")
            params.append(risk_gate_status)
        if feed_source is not None:
            fields.append("feed_source = ?")
            params.append(feed_source)
        params.append(session_id)

        with self._transaction() as cur:
            cur.execute(f"UPDATE paper_sessions SET {', '.join(fields)} WHERE session_id = ?", params)
        return self.get_paper_session(session_id)

    def get_paper_session(self, session_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        if user_id is not None:
            row = self._conn.execute(
                "SELECT * FROM paper_sessions WHERE session_id = ? AND user_id = ?",
                (session_id, user_id),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT * FROM paper_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["policy_details"] = json.loads(d.get("policy_details_json") or "{}")
        except Exception:
            d["policy_details"] = {}
        pos_count = self._conn.execute(
            "SELECT COUNT(*) FROM paper_positions WHERE session_id = ? AND status = 'OPEN'",
            (session_id,),
        ).fetchone()[0]
        orders_count = self._conn.execute(
            "SELECT COUNT(*) FROM paper_orders WHERE session_id = ?",
            (session_id,),
        ).fetchone()[0]
        fills_count = self._conn.execute(
            "SELECT COUNT(*) FROM paper_orders WHERE session_id = ? AND status = 'FILLED'",
            (session_id,),
        ).fetchone()[0]
        d["active_positions"] = pos_count
        d["total_orders"] = orders_count
        d["total_fills"] = fills_count
        return d

    def list_paper_sessions(self, user_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if user_id is not None:
            rows = self._conn.execute(
                "SELECT * FROM paper_sessions WHERE user_id = ? ORDER BY created_at_utc DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM paper_sessions ORDER BY created_at_utc DESC LIMIT ?",
                (limit,),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if "execution_metadata_json" in d and d["execution_metadata_json"]:
                try:
                    d["execution_metadata"] = json.loads(d["execution_metadata_json"])
                except Exception:
                    d["execution_metadata"] = {}
            try:
                d["policy_details"] = json.loads(d.get("policy_details_json") or "{}")
            except Exception:
                d["policy_details"] = {}
            pos_count = self._conn.execute(
                "SELECT COUNT(*) FROM paper_positions WHERE session_id = ? AND status = 'OPEN'",
                (d["session_id"],),
            ).fetchone()[0]
            orders_count = self._conn.execute(
                "SELECT COUNT(*) FROM paper_orders WHERE session_id = ?",
                (d["session_id"],),
            ).fetchone()[0]
            fills_count = self._conn.execute(
                "SELECT COUNT(*) FROM paper_orders WHERE session_id = ? AND status = 'FILLED'",
                (d["session_id"],),
            ).fetchone()[0]
            d["active_positions"] = pos_count
            d["total_orders"] = orders_count
            d["total_fills"] = fills_count
            result.append(d)
        return result

    def record_paper_position(
        self,
        *,
        position_id: str,
        session_id: str,
        symbol: str,
        resolved_contract: str,
        position_type: str,
        qty: int,
        avg_price: float,
        ltp: float,
        entry_cost: float,
        current_value: float,
        unrealized_pnl: float,
        return_pct: float,
        strategy_source: str,
        policy_snapshot: str = "",
        status: str = "OPEN",
        price_provenance: str = "MODELED",
    ) -> None:
        now_str = _utc_now().isoformat()
        with self._transaction() as cur:
            cur.execute(
                """INSERT INTO paper_positions (
                    position_id, session_id, symbol, resolved_contract, position_type,
                    qty, avg_price, ltp, entry_cost, current_value, unrealized_pnl,
                    return_pct, strategy_source, policy_snapshot, opened_at_utc, status,
                    price_provenance
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(position_id) DO UPDATE SET
                    qty=excluded.qty, avg_price=excluded.avg_price, ltp=excluded.ltp,
                    entry_cost=excluded.entry_cost, current_value=excluded.current_value,
                    unrealized_pnl=excluded.unrealized_pnl, return_pct=excluded.return_pct,
                    status=excluded.status, price_provenance=excluded.price_provenance""",
                (
                    position_id,
                    session_id,
                    symbol,
                    resolved_contract,
                    position_type,
                    qty,
                    avg_price,
                    ltp,
                    entry_cost,
                    current_value,
                    unrealized_pnl,
                    return_pct,
                    strategy_source,
                    policy_snapshot,
                    now_str,
                    status,
                    price_provenance,
                ),
            )

    def get_paper_positions(self, session_id: str, user_id: str | None = None) -> list[dict[str, Any]]:
        # R-09: session ownership enforced inside SQL via the parent session.
        if user_id is not None:
            rows = self._conn.execute(
                """SELECT p.* FROM paper_positions p
                   JOIN paper_sessions s ON s.session_id = p.session_id
                   WHERE p.session_id = ? AND s.user_id = ?
                   ORDER BY p.opened_at_utc ASC""",
                (session_id, user_id),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM paper_positions WHERE session_id = ? ORDER BY opened_at_utc ASC",
                (session_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def record_paper_order(
        self,
        *,
        order_id: str,
        session_id: str,
        instrument: str,
        order_type: str,
        side: str,
        qty: int,
        limit_price: float | None = None,
        fill_price: float | None = None,
        status: str = "SUBMITTED",
        rejection_reason: str | None = None,
        filled_at_utc: str | None = None,
    ) -> None:
        now_str = _utc_now().isoformat()
        with self._transaction() as cur:
            cur.execute(
                """INSERT INTO paper_orders (
                    order_id, session_id, instrument, order_type, side,
                    qty, limit_price, fill_price, status, rejection_reason,
                    created_at_utc, filled_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, order_id) DO UPDATE SET
                    fill_price=excluded.fill_price, status=excluded.status,
                    rejection_reason=excluded.rejection_reason, filled_at_utc=excluded.filled_at_utc""",
                (
                    order_id,
                    session_id,
                    instrument,
                    order_type,
                    side,
                    qty,
                    limit_price,
                    fill_price,
                    status,
                    rejection_reason,
                    now_str,
                    filled_at_utc,
                ),
            )

    def get_paper_orders(self, session_id: str, user_id: str | None = None) -> list[dict[str, Any]]:
        # R-09: session ownership enforced inside SQL via the parent session.
        if user_id is not None:
            rows = self._conn.execute(
                """SELECT o.* FROM paper_orders o
                   JOIN paper_sessions s ON s.session_id = o.session_id
                   WHERE o.session_id = ? AND s.user_id = ?
                   ORDER BY o.created_at_utc ASC""",
                (session_id, user_id),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM paper_orders WHERE session_id = ? ORDER BY created_at_utc ASC",
                (session_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def record_paper_event(
        self,
        *,
        event_id: str,
        session_id: str,
        event_time: str,
        title: str,
        detail: str,
        source: str,
        status: str = "PASS",
        badge: str | None = None,
    ) -> None:
        now_str = _utc_now().isoformat()
        with self._transaction() as cur:
            cur.execute(
                """INSERT INTO paper_events (
                    event_id, session_id, event_time, title, detail, source, status, badge, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    title=excluded.title, detail=excluded.detail, status=excluded.status, badge=excluded.badge""",
                (
                    event_id,
                    session_id,
                    event_time,
                    title,
                    detail,
                    source,
                    status,
                    badge,
                    now_str,
                ),
            )

    def get_paper_events(self, session_id: str, user_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        # R-09: session ownership enforced inside SQL via the parent session.
        if user_id is not None:
            rows = self._conn.execute(
                """SELECT e.* FROM paper_events e
                   JOIN paper_sessions s ON s.session_id = e.session_id
                   WHERE e.session_id = ? AND s.user_id = ?
                   ORDER BY e.created_at_utc DESC LIMIT ?""",
                (session_id, user_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM paper_events WHERE session_id = ? ORDER BY created_at_utc DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def record_paper_quote_event_id(self, session_id: str, event_id: str, *, cap: int = 500) -> None:
        """Durably record a consumed live-quote event id (F-11 cross-restart dedup)."""
        key = f"paper_quote_ids:{session_id}"
        with self._transaction() as cur:
            row = cur.execute("SELECT value FROM security_metadata WHERE key = ?", (key,)).fetchone()
            try:
                known: list[str] = json.loads(row["value"]) if row else []
                if not isinstance(known, list):
                    known = []
            except Exception:
                known = []
            if event_id not in known:
                known.append(event_id)
            if len(known) > cap:
                known = known[-cap:]
            cur.execute("INSERT OR REPLACE INTO security_metadata (key, value) VALUES (?, ?)",
                        (key, json.dumps(known)))

    def get_paper_quote_event_ids(self, session_id: str) -> list[str]:
        """Return durably recorded live-quote event ids for a session."""
        row = self._conn.execute(
            "SELECT value FROM security_metadata WHERE key = ?",
            (f"paper_quote_ids:{session_id}",),
        ).fetchone()
        if not row:
            return []
        try:
            values = json.loads(row["value"])
        except Exception:
            return []
        return [str(v) for v in values] if isinstance(values, list) else []

    def set_paper_session_hold(self, session_id: str, hold: bool, reason: str | None = None) -> bool:
        now_str = _utc_now().isoformat()
        allowance = "HOLD" if hold else "ALLOWED"
        status = "HELD" if hold else "ACTIVE"
        with self._transaction() as cur:
            row = cur.execute("SELECT session_id FROM paper_sessions WHERE session_id = ?", (session_id,)).fetchone()
            if not row:
                return False
            cur.execute(
                "UPDATE paper_sessions SET owner_allowance = ?, owner_hold_reason = ?, status = ?, updated_at_utc = ? WHERE session_id = ?",
                (allowance, reason, status, now_str, session_id),
            )
            return True

    def close(self) -> None:
        if not self._closed:
            self._conn.close()
            self._closed = True

    def __enter__(self) -> "SQLiteSecurityStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
