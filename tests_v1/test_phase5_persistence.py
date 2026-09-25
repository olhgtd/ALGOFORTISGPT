from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3

import pytest

from engine.paper.contracts_v2 import (
    AlertDeliveryRecord,
    FailureIncident,
    FailureSeverity,
    PaperMode,
    PaperOperationalState,
    PaperSession,
    RecoveryCheckpoint,
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


def test_phase5_schema_advances_additively_from_v7_to_v8():
    assert SCHEMA_VERSION == 8
    assert PHASE5_V8_MIGRATION.from_version == 7
    assert PHASE5_V8_MIGRATION.to_version == 8
    assert PHASE5_V8_MIGRATION.migration_id == "phase5-paper-recovery-v8"


def test_paper_session_round_trip_is_exact(tmp_path: Path):
    store = PaperSessionStore(_database(tmp_path))
    session = _session()
    store.save_session(session)
    assert store.load_session(session.session_id) == session


def test_checkpoint_round_trip_preserves_fingerprint(tmp_path: Path):
    store = PaperRecoveryStore(_database(tmp_path))
    checkpoint = _checkpoint()
    store.save_checkpoint(checkpoint)
    loaded = store.latest_checkpoint(checkpoint.session_id)
    assert loaded == checkpoint
    assert loaded.fingerprint == checkpoint.fingerprint


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
