from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import re

from engine.paper.contracts_v2 import PaperOperationalState, RecoveryReport
from engine.paper.drift_report_v2 import DriftExecutionRecord, PaperDriftReporter
from engine.paper.evidence_v2 import EvidenceWriter

NOW = datetime(2026, 9, 26, 6, 20, tzinfo=timezone.utc)


def _recovery_report() -> RecoveryReport:
    return RecoveryReport(
        recovery_id="recovery-p5-09",
        trigger="PROCESS_RESTART",
        previous_state=PaperOperationalState.RECOVERY,
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
        produced_at=NOW,
    )


def _backtest() -> DriftExecutionRecord:
    return DriftExecutionRecord(
        logical_intent_id="intent-1",
        entry_time=NOW,
        entry_price=Decimal("100.00"),
        exit_time=NOW,
        exit_price=Decimal("110.00"),
        quantity=Decimal("2"),
        costs=Decimal("1.00"),
        realized_pnl=Decimal("19.00"),
        lifecycle_result="FILLED",
    )


def _paper() -> DriftExecutionRecord:
    return DriftExecutionRecord(
        logical_intent_id="intent-1",
        entry_time=NOW,
        entry_price=Decimal("100.50"),
        exit_time=NOW,
        exit_price=Decimal("109.50"),
        quantity=Decimal("2"),
        costs=Decimal("1.50"),
        realized_pnl=Decimal("16.50"),
        lifecycle_result="FILLED",
    )


def test_same_recovery_report_has_same_64_hex_fingerprint():
    a = EvidenceWriter.recovery_fingerprint(_recovery_report())
    b = EvidenceWriter.recovery_fingerprint(_recovery_report())

    assert a == b
    assert re.fullmatch(r"[0-9a-f]{64}", a)


def test_recovery_fingerprint_changes_when_material_report_content_changes():
    original = _recovery_report()
    changed = RecoveryReport(
        recovery_id=original.recovery_id,
        trigger=original.trigger,
        previous_state=original.previous_state,
        checkpoint_fingerprint=original.checkpoint_fingerprint,
        restored_order_refs=original.restored_order_refs,
        restored_position_refs=original.restored_position_refs,
        reconciliation_result="MISMATCH",
        protective_integrity_result=original.protective_integrity_result,
        feed_health=original.feed_health,
        clock_health=original.clock_health,
        session_expiry_validity=original.session_expiry_validity,
        unresolved_discrepancies=("position mismatch",),
        alert_refs=original.alert_refs,
        final_state=PaperOperationalState.HALTED,
        manual_resume_required=True,
        produced_at=original.produced_at,
    )

    assert EvidenceWriter.recovery_fingerprint(original) != EvidenceWriter.recovery_fingerprint(changed)


def test_missing_drift_policy_is_fail_closed_not_guessed():
    report = PaperDriftReporter.compare(_backtest(), _paper(), policy_ref=None)

    assert report.promotion_eligible is False
    assert report.reason == "MISSING_DRIFT_POLICY"
    assert report.policy_ref is None


def test_drift_report_explains_execution_and_pnl_deltas_without_profit_claims():
    report = PaperDriftReporter.compare(_backtest(), _paper(), policy_ref="TEST_ONLY/drift-fi-v1@1")

    assert report.entry_price_delta == Decimal("0.50")
    assert report.exit_price_delta == Decimal("-0.50")
    assert report.cost_delta == Decimal("0.50")
    assert report.realized_pnl_delta == Decimal("-2.50")
    assert report.lifecycle_match is True
    assert report.promotion_eligible is False
    assert report.reason == "POLICY_EVALUATION_DEFERRED"


def test_g5_manifest_is_deterministic_and_fail_closed_when_required_evidence_missing():
    first = EvidenceWriter.build_g5_manifest(
        commit_sha="a" * 40,
        config_fingerprint="b" * 64,
        data_fingerprint="c" * 64,
        fault_profile_ref="TEST_ONLY/fi-v1@1",
        recovery_fingerprints=("d" * 64,),
        failure_injection_refs=(),
        drift_report_ref=None,
        alert_evidence_refs=("alert-evidence-1",),
        host_evidence_refs=("host-evidence-1",),
        soak_started=False,
    )
    second = EvidenceWriter.build_g5_manifest(
        commit_sha="a" * 40,
        config_fingerprint="b" * 64,
        data_fingerprint="c" * 64,
        fault_profile_ref="TEST_ONLY/fi-v1@1",
        recovery_fingerprints=("d" * 64,),
        failure_injection_refs=(),
        drift_report_ref=None,
        alert_evidence_refs=("alert-evidence-1",),
        host_evidence_refs=("host-evidence-1",),
        soak_started=False,
    )

    assert first == second
    assert first["g5_eligible"] is False
    assert "MISSING_FAILURE_INJECTION_EVIDENCE" in first["blockers"]
    assert "MISSING_DRIFT_EVIDENCE" in first["blockers"]
    assert "SOAK_NOT_STARTED" in first["blockers"]
