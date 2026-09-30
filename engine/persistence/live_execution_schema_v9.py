"""Additive SQLite V9 objects for durable Live execution evidence and capacity reservations."""
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
        broker_account_ref TEXT NOT NULL,
        client_order_id TEXT NOT NULL,
        instrument_scope TEXT NOT NULL,
        required_cash TEXT NOT NULL,
        funds_evidence_ref TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        released_at_utc TEXT,
        release_reason TEXT,
        status TEXT NOT NULL CHECK(status IN ('ACTIVE', 'RELEASED')),
        PRIMARY KEY (broker_account_ref, client_order_id)
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_live_capacity_account_status
        ON live_execution_capacity_reservations (broker_account_ref, status, created_at_utc, client_order_id);
    """,
)

LIVE_EXECUTION_DROP_TABLES_SQL: tuple[str, ...] = (
    "DROP INDEX IF EXISTS idx_live_capacity_account_status;",
    "DROP TABLE IF EXISTS live_execution_capacity_reservations;",
    "DROP INDEX IF EXISTS idx_live_execution_uncertain;",
    "DROP TABLE IF EXISTS live_execution_records;",
)

__all__ = ["LIVE_EXECUTION_CREATE_TABLES_SQL", "LIVE_EXECUTION_DROP_TABLES_SQL"]
