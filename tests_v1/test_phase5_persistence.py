from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sqlite3

import pytest

from engine.paper.contracts_v2 import (
    AlertDeliveryRecord,
    FailureIncident,
    FailureSeverity,
    PaperMode,
    PaperOperationalState,
    PaperOrderRecord,
    PaperPositionRecord,
    PaperSession,
    RecoveryCheckpoint,
    RecoveryReport,
)
from engine.persistence.migrations import (
    PHASE5_PAPER_RECOVERY_MIGRATION,
    SQLiteMigrationRunner,
)
from engine.persistence.paper_incident_store_v2 import PaperIncidentStore
from engine.persistence.paper_recovery_store_v2 import (
    CheckpointIntegrityError,
    PaperRecoveryStore,
)
from engine.persistence.paper_session_store_v2 import PaperSessionStore
from engine.persistence.schema import CREATE_TABLES_SQL, SCHEMA_VERSION


UTC_NOW = datetime(2026, 9, 25, 9, 30, tzinfo=timezone.utc)


def _initialize_current_database(path: Path) -> None:
    connection = sqlite3.connect(str(path))
    try:
        for statement in CREATE_TABLES_SQL:
            connection.execute(statement)
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        connection.commit()
    finally:
        connection.close()


def _session() -> PaperSession:
    return PaperSession(
        session_id="session-1",
        mode=PaperMode.PAPER,
        started_at=UTC_NOW,
        trading_date="2026-09-25",
        session_state=PaperOperationalState.RECOVERY,
        config_snapshot_ref="config@v1",
        strategy_versions=("orb@v2",),
        risk_policy_version="risk@v2",
        instrument_master_version="instrument-master@v1",
        failure_policy_version="failure-policy@v1",
    )


def _order() -> PaperOrderRecord:
    return PaperOrderRecord(
        logical_intent_id="intent-1",
        approved_order_id="approved-1",
        instrument="NIFTY26SEP25000CE",
        side="BUY",
        quantity=Decimal("50"),
        lifecycle_state="FILLED",
        cumulative_fill=Decimal("50"),
        submitted_at=UTC_NOW,
        last_observed_at=UTC_NOW,
        last_observation_sequence=7,
        terminal_reason=None,
    )


def _position() -> PaperPositionRecord:
    return PaperPositionRecord(
        position_id="position-1",
        instrument="NIFTY26SEP25000CE",
        quantity=Decimal("50"),
        average_price=Decimal("101.10"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("12.50"),
        protective_policy_ref="protective@test-v1",
        protective_state="VALID",
        expiry_metadata="2026-09-25",
        session_metadata="2026-09-25",
    )


def _checkpoint() -> RecoveryCheckpoint:
    return RecoveryCheckpoint(
        checkpoint_id="checkpoint-1",
        session_id="session-1",
        persisted_at=UTC_NOW,
        last_event_sequence=11,
        open_order_refs=("approved-1",),
        open_position_refs=("position-1",),
        recovery_required=True,
        reason="PROCESS_CRASH",
        fingerprint="a" * 64,
    )


def _incident() -> FailureIncident:
    return FailureIncident(
        incident_id="incident-1",
        failure_type="PROCESS_CRASH",
        severity=FailureSeverity.RECOVERY_REQUIRED,
        detected_at=UTC_NOW,
        source="paper-session",
        affected_scope="session-1",
        previous_state=PaperOperationalState.HEALTHY,
        resulting_state=PaperOperationalState.RECOVERY,
        transition_reason="PROCESS_CRASH",
        halt_latched=True,
        recovery_id="recovery-1",
        storm_policy_ref=None,
        resolved_at=None,
        resolution_evidence=None,
    )


def _alert() -> AlertDeliveryRecord:
    return AlertDeliveryRecord(
        alert_id="alert-1",
        incident_id="incident-1",
        channel="telegram",
        attempt=1,
        delivery_status="DELIVERED",
        failure_reason=None,
        attempted_at=UTC_NOW,
        completed_at=UTC_NOW,
    )


def _report() -> RecoveryReport:
    return RecoveryReport(
        recovery_id="recovery-1",
        trigger="PROCESS_CRASH",
        previous_state=PaperOperationalState.HEALTHY,
        checkpoint_fingerprint="a" * 64,
        restored_order_refs=("approved-1",),
        restored_position_refs=("position-1",),
        reconciliation_result="CLEAN",
        protective_integrity_result="VALID",
        feed_health="HEALTHY",
        clock_health="HEALTHY",
        session_expiry_validity="VALID",
        unresolved_discrepancies=(),
        alert_refs=("alert-1",),
        final_state=PaperOperationalState.READY_FOR_RESUME,
        manual_resume_required=True,
        produced_at=UTC_NOW,
    )


def test_session_order_position_round_trip_preserves_owned_state(tmp_path: Path):
    database = tmp_path / "phase5.sqlite3"
    _initialize_current_database(database)
    store = PaperSessionStore(database)

    store.save_session(_session())
    store.save_order("session-1", _order())
    store.save_position("session-1", _position())

    owned = store.load_owned_state("session-1")
    assert owned.session == _session()
    assert owned.orders == (_order(),)
    assert owned.positions == (_position(),)


def test_checkpoint_round_trip_preserves_declared_fingerprint(tmp_path: Path):
    database = tmp_path / "phase5.sqlite3"
    _initialize_current_database(database)
    store = PaperRecoveryStore(database)
    checkpoint = _checkpoint()

    store.save_checkpoint(checkpoint)
    loaded = store.latest_checkpoint(checkpoint.session_id)

    assert loaded == checkpoint
    assert loaded is not None
    assert loaded.fingerprint == checkpoint.fingerprint


def test_corrupt_checkpoint_is_not_treated_as_valid_state(tmp_path: Path):
    database = tmp_path / "phase5.sqlite3"
    _initialize_current_database(database)
    store = PaperRecoveryStore(database)
    store.save_checkpoint(_checkpoint())

    connection = sqlite3.connect(str(database))
    try:
        connection.execute(
            "UPDATE phase5_recovery_checkpoints SET payload_json = ? WHERE checkpoint_id = ?",
            ("{}", "checkpoint-1"),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(CheckpointIntegrityError, match="integrity"):
        store.latest_checkpoint("session-1")


def test_recovery_report_round_trip(tmp_path: Path):
    database = tmp_path / "phase5.sqlite3"
    _initialize_current_database(database)
    store = PaperRecoveryStore(database)
    report = _report()

    store.save_recovery_report(report)
    assert store.load_recovery_report(report.recovery_id) == report


def test_incident_and_alert_delivery_round_trip(tmp_path: Path):
    database = tmp_path / "phase5.sqlite3"
    _initialize_current_database(database)
    store = PaperIncidentStore(database)

    store.save_incident(_incident())
    store.save_alert_delivery(_alert())

    assert store.load_incident("incident-1") == _incident()
    assert store.alert_deliveries("incident-1") == (_alert(),)


def test_phase5_forward_migration_is_exactly_v7_to_v8(tmp_path: Path):
    assert PHASE5_PAPER_RECOVERY_MIGRATION.from_version == 7
    assert PHASE5_PAPER_RECOVERY_MIGRATION.to_version == 8
    assert SCHEMA_VERSION == 8

    database = tmp_path / "legacy-v7.sqlite3"
    connection = sqlite3.connect(str(database))
    try:
        connection.execute("CREATE TABLE legacy_marker (id INTEGER PRIMARY KEY)")
        connection.execute("PRAGMA user_version = 7")
        connection.commit()
    finally:
        connection.close()

    runner = SQLiteMigrationRunner(database, tmp_path / "backups")
    result = runner.migrate(
        (PHASE5_PAPER_RECOVERY_MIGRATION,),
        target_version=8,
    )

    assert result.from_version == 7
    assert result.to_version == 8
    assert result.backup_verified is True
    assert result.applied_migration_ids == (PHASE5_PAPER_RECOVERY_MIGRATION.migration_id,)

    connection = sqlite3.connect(str(database))
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    finally:
        connection.close()

    assert version == 8
    assert {
        "phase5_paper_sessions",
        "phase5_paper_orders",
        "phase5_paper_positions",
        "phase5_recovery_checkpoints",
        "phase5_recovery_reports",
        "phase5_failure_incidents",
        "phase5_alert_deliveries",
    } <= tables
