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
from engine.persistence.migrations import PHASE5_V8_MIGRATION
from engine.persistence.paper_incident_store_v2 import PaperIncidentStore
from engine.persistence.paper_recovery_store_v2 import CheckpointIntegrityError, PaperRecoveryStore
from engine.persistence.paper_session_store_v2 import PaperSessionStore
from engine.persistence.schema import CREATE_TABLES_SQL, SCHEMA_VERSION

NOW = datetime(2026, 9, 25, 9, 30, tzinfo=timezone.utc)


def _database(tmp_path: Path) -> Path:
    path = tmp_path / "phase5.sqlite3"
    with sqlite3.connect(path) as connection:
        for statement in CREATE_TABLES_SQL:
            connection.execute(statement)
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        connection.commit()
    return path


def _session() -> PaperSession:
    return PaperSession(
        session_id="session-p5",
        mode=PaperMode.PAPER,
        started_at=NOW,
        trading_date="2026-09-25",
        session_state=PaperOperationalState.HEALTHY,
        config_snapshot_ref="cfg@p5",
        strategy_versions=("orb@v2",),
        risk_policy_version="risk@v2",
        instrument_master_version="im@v2",
        failure_policy_version="fail@v1",
    )


def _order() -> PaperOrderRecord:
    return PaperOrderRecord(
        logical_intent_id="order-1",
        approved_order_id="approved-1",
        instrument="NIFTY-2026-09-25-22000-CE",
        side="BUY",
        quantity=Decimal("25"),
        lifecycle_state="PARTIALLY_FILLED",
        cumulative_fill=Decimal("10"),
        submitted_at=NOW,
        last_observed_at=NOW,
        last_observation_sequence=41,
        terminal_reason=None,
    )


def _position() -> PaperPositionRecord:
    return PaperPositionRecord(
        position_id="position-1",
        instrument="NIFTY-2026-09-25-22000-CE",
        quantity=Decimal("10"),
        average_price=Decimal("125.50"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("12.25"),
        protective_policy_ref="protect@v1",
        protective_state="ACTIVE",
        expiry_metadata="2026-09-25",
        session_metadata="session-p5",
    )


def _checkpoint() -> RecoveryCheckpoint:
    return RecoveryCheckpoint(
        checkpoint_id="checkpoint-p5",
        session_id="session-p5",
        persisted_at=NOW,
        last_event_sequence=42,
        open_order_refs=("order-1",),
        open_position_refs=("position-1",),
        recovery_required=True,
        reason="PROCESS_CRASH",
        fingerprint="a" * 64,
    )


def _recovery_report() -> RecoveryReport:
    return RecoveryReport(
        recovery_id="recovery-p5",
        trigger="PROCESS_CRASH",
        previous_state=PaperOperationalState.RECOVERY,
        checkpoint_fingerprint="a" * 64,
        restored_order_refs=("order-1",),
        restored_position_refs=("position-1",),
        reconciliation_result="CLEAN",
        protective_integrity_result="CLEAN",
        feed_health="HEALTHY",
        clock_health="HEALTHY",
        session_expiry_validity="VALID",
        unresolved_discrepancies=(),
        alert_refs=("alert-p5",),
        final_state=PaperOperationalState.READY_FOR_RESUME,
        manual_resume_required=True,
        produced_at=NOW,
    )


def test_phase5_schema_advances_additively_from_v7_to_v8():
    assert SCHEMA_VERSION >= 8
    assert PHASE5_V8_MIGRATION.from_version == 7
    assert PHASE5_V8_MIGRATION.to_version == 8
    assert PHASE5_V8_MIGRATION.migration_id == "phase5-paper-recovery-v8"


def test_paper_session_round_trip_is_exact(tmp_path: Path):
    store = PaperSessionStore(_database(tmp_path))
    session = _session()
    store.save_session(session)
    assert store.load_session(session.session_id) == session


def test_order_and_position_round_trip_are_exact(tmp_path: Path):
    store = PaperSessionStore(_database(tmp_path))
    order = _order()
    position = _position()
    store.save_order(order)
    store.save_position(position)
    assert store.load_order(order.logical_intent_id) == order
    assert store.load_position(position.position_id) == position


def test_checkpoint_round_trip_preserves_fingerprint(tmp_path: Path):
    store = PaperRecoveryStore(_database(tmp_path))
    checkpoint = _checkpoint()
    store.save_checkpoint(checkpoint)
    loaded = store.latest_checkpoint(checkpoint.session_id)
    assert loaded == checkpoint
    assert loaded.fingerprint == checkpoint.fingerprint


def test_owned_state_round_trip_restores_checkpoint_references_exactly(tmp_path: Path):
    path = _database(tmp_path)
    session_store = PaperSessionStore(path)
    recovery_store = PaperRecoveryStore(path)
    session_store.save_session(_session())
    session_store.save_order(_order())
    session_store.save_position(_position())
    recovery_store.save_checkpoint(_checkpoint())
    owned = session_store.load_owned_state("session-p5")
    assert owned.session == _session()
    assert owned.orders == (_order(),)
    assert owned.positions == (_position(),)


def test_owned_state_missing_order_reference_fails_closed(tmp_path: Path):
    path = _database(tmp_path)
    session_store = PaperSessionStore(path)
    recovery_store = PaperRecoveryStore(path)
    session_store.save_session(_session())
    session_store.save_position(_position())
    recovery_store.save_checkpoint(_checkpoint())
    with pytest.raises(RuntimeError, match="missing.*order"):
        session_store.load_owned_state("session-p5")


def test_owned_state_missing_position_reference_fails_closed(tmp_path: Path):
    path = _database(tmp_path)
    session_store = PaperSessionStore(path)
    recovery_store = PaperRecoveryStore(path)
    session_store.save_session(_session())
    session_store.save_order(_order())
    recovery_store.save_checkpoint(_checkpoint())
    with pytest.raises(RuntimeError, match="missing.*position"):
        session_store.load_owned_state("session-p5")


def test_corrupt_checkpoint_fails_closed(tmp_path: Path):
    path = _database(tmp_path)
    store = PaperRecoveryStore(path)
    store.save_checkpoint(_checkpoint())
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE phase5_recovery_checkpoints SET fingerprint = ? WHERE checkpoint_id = ?",
            ("broken", "checkpoint-p5"),
        )
        connection.commit()
    with pytest.raises(CheckpointIntegrityError, match="fingerprint"):
        store.latest_checkpoint("session-p5")


def test_owned_state_uses_checkpoint_integrity_validation(tmp_path: Path):
    path = _database(tmp_path)
    session_store = PaperSessionStore(path)
    recovery_store = PaperRecoveryStore(path)
    session_store.save_session(_session())
    session_store.save_order(_order())
    session_store.save_position(_position())
    recovery_store.save_checkpoint(_checkpoint())
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE phase5_recovery_checkpoints SET fingerprint = ? WHERE checkpoint_id = ?",
            ("broken", "checkpoint-p5"),
        )
        connection.commit()
    with pytest.raises(CheckpointIntegrityError, match="fingerprint"):
        session_store.load_owned_state("session-p5")


def test_recovery_report_round_trip_is_exact(tmp_path: Path):
    store = PaperRecoveryStore(_database(tmp_path))
    report = _recovery_report()
    store.save_recovery_report(report)
    assert store.load_recovery_report(report.recovery_id) == report


def test_incident_and_alert_delivery_are_append_only_evidence(tmp_path: Path):
    store = PaperIncidentStore(_database(tmp_path))
    incident = FailureIncident(
        incident_id="incident-p5",
        failure_type="PROCESS_CRASH",
        severity=FailureSeverity.RECOVERY_REQUIRED,
        detected_at=NOW,
        source="paper-session",
        affected_scope="session-p5",
        previous_state=PaperOperationalState.HEALTHY,
        resulting_state=PaperOperationalState.RECOVERY,
        transition_reason="PROCESS_CRASH",
        halt_latched=True,
        recovery_id="recovery-p5",
        storm_policy_ref=None,
        resolved_at=None,
        resolution_evidence=None,
    )
    delivery = AlertDeliveryRecord(
        alert_id="alert-p5",
        incident_id="incident-p5",
        channel="telegram",
        attempt=1,
        delivery_status="FAILED",
        failure_reason="network",
        attempted_at=NOW,
        completed_at=NOW,
    )
    store.save_incident(incident)
    store.save_alert_delivery(delivery)
    assert store.list_incidents("session-p5") == (incident,)
    assert store.list_alert_deliveries("incident-p5") == (delivery,)
    with pytest.raises(Exception):
        store.save_incident(incident)
