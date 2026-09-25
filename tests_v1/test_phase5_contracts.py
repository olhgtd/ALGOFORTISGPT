from datetime import datetime, timezone
from decimal import Decimal

import pytest

from engine.paper.contracts_v2 import (
    AlertDeliveryRecord,
    FailureIncident,
    FailureInjectionResult,
    FailureSeverity,
    PaperMode,
    PaperOperationalState,
    PaperOrderRecord,
    PaperPositionRecord,
    PaperSession,
    RecoveryCheckpoint,
    RecoveryReport,
)


UTC_NOW = datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc)


def _session(**overrides):
    values = {
        "session_id": "session-1",
        "mode": PaperMode.PAPER,
        "started_at": UTC_NOW,
        "trading_date": "2026-01-05",
        "session_state": PaperOperationalState.HEALTHY,
        "config_snapshot_ref": "config@v1",
        "strategy_versions": ("orb@v2",),
        "risk_policy_version": "risk@v2",
        "instrument_master_version": "im@v1",
        "failure_policy_version": "failure@v1",
    }
    values.update(overrides)
    return PaperSession(**values)


def test_phase5_state_vocabulary_is_closed():
    assert tuple(state.value for state in PaperOperationalState) == (
        "HEALTHY",
        "DEGRADED",
        "HALTED",
        "RECOVERY",
        "READY_FOR_RESUME",
    )


def test_failure_incident_carries_traceability_fields():
    incident = FailureIncident(
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
    assert incident.previous_state is PaperOperationalState.HEALTHY
    assert incident.resulting_state is PaperOperationalState.RECOVERY
    assert incident.recovery_id == "recovery-1"
    assert incident.storm_policy_ref is None


def test_failure_incident_rejects_non_state_result():
    with pytest.raises(TypeError, match="resulting_state"):
        FailureIncident(
            incident_id="incident-1",
            failure_type="PROCESS_CRASH",
            severity=FailureSeverity.RECOVERY_REQUIRED,
            detected_at=UTC_NOW,
            source="paper-session",
            affected_scope="session-1",
            previous_state=PaperOperationalState.HEALTHY,
            resulting_state="RECOVERY",  # type: ignore[arg-type]
            transition_reason="PROCESS_CRASH",
            halt_latched=True,
            recovery_id="recovery-1",
            storm_policy_ref=None,
            resolved_at=None,
            resolution_evidence=None,
        )


def test_naive_timestamp_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        _session(started_at=datetime(2026, 1, 5, 9, 30))


def test_blank_ids_are_rejected():
    with pytest.raises(ValueError, match="session_id"):
        _session(session_id=" ")


def test_order_quantity_and_fill_are_decimal_and_bounded():
    with pytest.raises(ValueError, match="cumulative_fill"):
        PaperOrderRecord(
            logical_intent_id="intent-1",
            approved_order_id="approved-1",
            instrument="NIFTY26JAN25000CE",
            side="BUY",
            quantity=Decimal("50"),
            lifecycle_state="FILLED",
            cumulative_fill=Decimal("51"),
            submitted_at=UTC_NOW,
            last_observed_at=UTC_NOW,
            last_observation_sequence=1,
            terminal_reason=None,
        )


def test_order_rejects_non_decimal_quantity():
    with pytest.raises(TypeError, match="quantity"):
        PaperOrderRecord(
            logical_intent_id="intent-1",
            approved_order_id="approved-1",
            instrument="NIFTY26JAN25000CE",
            side="BUY",
            quantity=50,  # type: ignore[arg-type]
            lifecycle_state="QUEUED",
            cumulative_fill=Decimal("0"),
            submitted_at=UTC_NOW,
            last_observed_at=UTC_NOW,
            last_observation_sequence=1,
            terminal_reason=None,
        )


def test_position_requires_positive_quantity():
    with pytest.raises(ValueError, match="quantity"):
        PaperPositionRecord(
            position_id="position-1",
            instrument="NIFTY26JAN25000CE",
            quantity=Decimal("0"),
            average_price=Decimal("100.00"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            protective_policy_ref="orb-protective@test-v1",
            protective_state="VALID",
            expiry_metadata="2026-01-29",
            session_metadata="2026-01-05",
        )


def test_position_requires_protective_policy_reference():
    with pytest.raises(ValueError, match="protective_policy_ref"):
        PaperPositionRecord(
            position_id="position-1",
            instrument="NIFTY26JAN25000CE",
            quantity=Decimal("50"),
            average_price=Decimal("100.00"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            protective_policy_ref=" ",
            protective_state="VALID",
            expiry_metadata="2026-01-29",
            session_metadata="2026-01-05",
        )


def test_checkpoint_sequence_must_be_non_negative():
    with pytest.raises(ValueError, match="last_event_sequence"):
        RecoveryCheckpoint(
            checkpoint_id="checkpoint-1",
            session_id="session-1",
            persisted_at=UTC_NOW,
            last_event_sequence=-1,
            open_order_refs=(),
            open_position_refs=(),
            recovery_required=True,
            reason="PROCESS_CRASH",
            fingerprint="a" * 64,
        )


def test_alert_record_has_independent_channel_status():
    record = AlertDeliveryRecord(
        alert_id="alert-1",
        incident_id="incident-1",
        channel="telegram",
        attempt=1,
        delivery_status="FAILED",
        failure_reason="network",
        attempted_at=UTC_NOW,
        completed_at=UTC_NOW,
    )
    assert record.channel == "telegram"
    assert record.delivery_status == "FAILED"


def test_recovery_report_smoke():
    report = RecoveryReport(
        recovery_id="recovery-1",
        trigger="PROCESS_CRASH",
        previous_state=PaperOperationalState.HEALTHY,
        checkpoint_fingerprint="a" * 64,
        restored_order_refs=("order-1",),
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
    assert report.final_state is PaperOperationalState.READY_FOR_RESUME
    assert report.manual_resume_required is True


def test_failure_injection_result_smoke():
    result = FailureInjectionResult(
        fi_id="FI-01",
        fixture_version="phase5-fi@test-v1",
        starting_state=PaperOperationalState.HEALTHY,
        injected_event="PROCESS_KILL_AFTER_SUBMIT",
        expected_state=PaperOperationalState.RECOVERY,
        actual_state=PaperOperationalState.RECOVERY,
        duplicate_order_count=0,
        stale_replay_count=0,
        unresolved_mismatch_count=0,
        recovery_report_ref="recovery-1",
        alert_evidence_refs=("alert-1",),
        passed=True,
        observed_at=UTC_NOW,
    )
    assert result.passed is True
    assert result.duplicate_order_count == 0
