from __future__ import annotations

import pytest

from engine.risk.latency_evidence_v2 import RiskGateLatencyRecord, RiskLatencyStage


def test_latency_record_requires_monotonic_stage_order() -> None:
    record = RiskGateLatencyRecord(
        intent_id="intent-1",
        risk_snapshot_id="snap-1",
        latency_policy_ref="TEST_ONLY/latency@v1",
        stage_timestamps_ns={
            RiskLatencyStage.RISK_GATE_ENTER: 10,
            RiskLatencyStage.CHECKS_COMPLETE: 20,
            RiskLatencyStage.AUDIT_APPEND_COMPLETE: 30,
            RiskLatencyStage.DECISION_FINALIZED: 40,
        },
        decision_kind="APPROVED",
        audit_result="WRITTEN",
        rejection_reason=None,
    )
    assert record.duration_ns(
        RiskLatencyStage.RISK_GATE_ENTER,
        RiskLatencyStage.DECISION_FINALIZED,
    ) == 30


def test_latency_record_rejects_non_monotonic_timestamps() -> None:
    with pytest.raises(ValueError, match="monotonic"):
        RiskGateLatencyRecord(
            intent_id="intent-1",
            risk_snapshot_id=None,
            latency_policy_ref=None,
            stage_timestamps_ns={
                RiskLatencyStage.RISK_GATE_ENTER: 20,
                RiskLatencyStage.CHECKS_COMPLETE: 10,
            },
            decision_kind="REJECTED",
            audit_result="WRITTEN",
            rejection_reason="blocked",
        )


def test_latency_record_requires_rejection_reason_for_rejected_decision() -> None:
    with pytest.raises(ValueError, match="rejection_reason"):
        RiskGateLatencyRecord(
            intent_id="intent-1",
            risk_snapshot_id=None,
            latency_policy_ref=None,
            stage_timestamps_ns={RiskLatencyStage.RISK_GATE_ENTER: 1},
            decision_kind="REJECTED",
            audit_result="WRITTEN",
            rejection_reason=None,
        )
