"""Additive SQLite V8 objects for Phase-5 Paper recovery evidence."""

from __future__ import annotations

PHASE5_CREATE_TABLES_SQL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS phase5_paper_sessions (
        session_id TEXT PRIMARY KEY,
        payload_json TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS phase5_paper_orders (
        logical_intent_id TEXT PRIMARY KEY,
        payload_json TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS phase5_paper_positions (
        position_id TEXT PRIMARY KEY,
        payload_json TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS phase5_recovery_checkpoints (
        checkpoint_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        persisted_at TEXT NOT NULL,
        last_event_sequence INTEGER NOT NULL CHECK(last_event_sequence >= 0),
        fingerprint TEXT NOT NULL,
        payload_json TEXT NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_phase5_checkpoint_session
        ON phase5_recovery_checkpoints (session_id, last_event_sequence DESC, persisted_at DESC);
    """,
    """
    CREATE TABLE IF NOT EXISTS phase5_recovery_reports (
        recovery_id TEXT PRIMARY KEY,
        produced_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS phase5_failure_incidents (
        incident_id TEXT PRIMARY KEY,
        affected_scope TEXT NOT NULL,
        detected_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_phase5_incident_scope
        ON phase5_failure_incidents (affected_scope, detected_at, incident_id);
    """,
    """
    CREATE TABLE IF NOT EXISTS phase5_alert_deliveries (
        alert_id TEXT NOT NULL,
        incident_id TEXT NOT NULL,
        channel TEXT NOT NULL,
        attempt INTEGER NOT NULL CHECK(attempt > 0),
        attempted_at TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        PRIMARY KEY (alert_id, channel, attempt),
        FOREIGN KEY (incident_id) REFERENCES phase5_failure_incidents (incident_id)
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_phase5_alert_incident
        ON phase5_alert_deliveries (incident_id, attempted_at, alert_id, channel, attempt);
    """,
)

PHASE5_DROP_TABLES_SQL: tuple[str, ...] = (
    "DROP INDEX IF EXISTS idx_phase5_alert_incident;",
    "DROP TABLE IF EXISTS phase5_alert_deliveries;",
    "DROP INDEX IF EXISTS idx_phase5_incident_scope;",
    "DROP TABLE IF EXISTS phase5_failure_incidents;",
    "DROP TABLE IF EXISTS phase5_recovery_reports;",
    "DROP INDEX IF EXISTS idx_phase5_checkpoint_session;",
    "DROP TABLE IF EXISTS phase5_recovery_checkpoints;",
    "DROP TABLE IF EXISTS phase5_paper_positions;",
    "DROP TABLE IF EXISTS phase5_paper_orders;",
    "DROP TABLE IF EXISTS phase5_paper_sessions;",
)

__all__ = ["PHASE5_CREATE_TABLES_SQL", "PHASE5_DROP_TABLES_SQL"]
