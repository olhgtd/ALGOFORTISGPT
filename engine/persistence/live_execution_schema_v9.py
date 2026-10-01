"""Additive SQLite V9 objects for durable Live execution evidence and safety state."""
from __future__ import annotations

LIVE_EXECUTION_CREATE_TABLES_SQL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS live_execution_records (
        client_order_id TEXT PRIMARY KEY,
        approved_order_ref TEXT NOT NULL,
        run_mode TEXT NOT NULL CHECK(run_mode = 'LIVE'),
        lifecycle_state TEXT NOT NULL,
        broker_order_identity TEXT,
        submission_attempt_id TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        updated_at_utc TEXT NOT NULL,
        is_uncertain INTEGER NOT NULL CHECK(is_uncertain IN (0, 1)),
        adapter_id TEXT,
        policy_ref TEXT,
        audit_ref TEXT
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_live_execution_uncertain
        ON live_execution_records (is_uncertain, updated_at_utc, client_order_id);
    """,
    """
    CREATE TABLE IF NOT EXISTS live_execution_capacity_reservations (
        broker_id TEXT NOT NULL,
        broker_account_ref TEXT NOT NULL,
        client_order_id TEXT NOT NULL,
        instrument_scope TEXT NOT NULL,
        required_cash TEXT NOT NULL,
        funds_evidence_ref TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        released_at_utc TEXT,
        release_reason TEXT,
        status TEXT NOT NULL CHECK(status IN ('ACTIVE', 'RELEASED')),
        PRIMARY KEY (broker_id, broker_account_ref, client_order_id)
    );
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_live_capacity_client_order_identity
        ON live_execution_capacity_reservations (client_order_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_live_capacity_account_status
        ON live_execution_capacity_reservations (
            broker_id, broker_account_ref, status, created_at_utc, client_order_id
        );
    """,
    """
    CREATE TABLE IF NOT EXISTS live_account_exclusivity (
        broker_id TEXT NOT NULL,
        broker_account_ref TEXT NOT NULL,
        device_id TEXT NOT NULL,
        session_family_id TEXT NOT NULL,
        ownership_nonce TEXT NOT NULL,
        acquired_at_utc TEXT NOT NULL,
        PRIMARY KEY (broker_id, broker_account_ref)
    );
    """,
)

LIVE_EXECUTION_DROP_TABLES_SQL: tuple[str, ...] = (
    "DROP TABLE IF EXISTS live_account_exclusivity;",
    "DROP INDEX IF EXISTS idx_live_capacity_account_status;",
    "DROP INDEX IF EXISTS idx_live_capacity_client_order_identity;",
    "DROP TABLE IF EXISTS live_execution_capacity_reservations;",
    "DROP INDEX IF EXISTS idx_live_execution_uncertain;",
    "DROP TABLE IF EXISTS live_execution_records;",
)

__all__ = ["LIVE_EXECUTION_CREATE_TABLES_SQL", "LIVE_EXECUTION_DROP_TABLES_SQL"]
