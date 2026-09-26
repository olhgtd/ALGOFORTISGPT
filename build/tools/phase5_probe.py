"""Deterministic cross-Windows Phase-5 Paper recovery fingerprint probe."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib

from engine.paper.contracts_v2 import (
    PaperMode,
    PaperOperationalState,
    PaperSession,
    RecoveryCheckpoint,
    RecoveryReport,
)
from engine.paper.evidence_v2 import EvidenceWriter
from engine.persistence.paper_codec_v2 import dumps_record

NOW = datetime(2026, 9, 25, 9, 30, tzinfo=timezone.utc)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_probe_lines() -> tuple[str, ...]:
    session = PaperSession(
        session_id="phase5-probe-session",
        mode=PaperMode.PAPER,
        started_at=NOW,
        trading_date="2026-09-25",
        session_state=PaperOperationalState.RECOVERY,
        config_snapshot_ref="phase5-probe-config/v1",
        strategy_versions=("phase5-probe-strategy/v1",),
        risk_policy_version="phase5-probe-risk/v1",
        instrument_master_version="phase5-probe-instruments/v1",
        failure_policy_version="TEST_ONLY/phase5-probe-failure/v1",
    )
    session_fingerprint = _sha256_text(dumps_record(session))
    checkpoint_fingerprint = _sha256_text("algofortis.phase5.probe.checkpoint/v1")
    checkpoint = RecoveryCheckpoint(
        checkpoint_id="phase5-probe-checkpoint",
        session_id=session.session_id,
        persisted_at=NOW,
        last_event_sequence=42,
        open_order_refs=("order-probe-1",),
        open_position_refs=("position-probe-1",),
        recovery_required=True,
        reason="PROCESS_RESTART",
        fingerprint=checkpoint_fingerprint,
    )
    report = RecoveryReport(
        recovery_id="phase5-probe-recovery",
        trigger="PROCESS_RESTART",
        previous_state=PaperOperationalState.RECOVERY,
        checkpoint_fingerprint=checkpoint.fingerprint,
        restored_order_refs=checkpoint.open_order_refs,
        restored_position_refs=checkpoint.open_position_refs,
        reconciliation_result="CLEAN",
        protective_integrity_result="VALID",
        feed_health="HEALTHY",
        clock_health="HEALTHY",
        session_expiry_validity="VALID",
        unresolved_discrepancies=(),
        alert_refs=(),
        final_state=PaperOperationalState.READY_FOR_RESUME,
        manual_resume_required=True,
        produced_at=NOW,
    )
    recovery_fingerprint = EvidenceWriter.recovery_fingerprint(report)

    return (
        f"SESSION_FINGERPRINT={session_fingerprint}",
        f"CHECKPOINT_FINGERPRINT={checkpoint.fingerprint}",
        f"RECOVERY_REPORT={recovery_fingerprint}",
        "FINAL_STATE=READY_FOR_RESUME",
        "MANUAL_RESUME_REQUIRED=true",
        "DUPLICATE_ORDER_COUNT=0",
        "STALE_REPLAY_COUNT=0",
        "DEFAULT_LIVE_STATE=READ_ONLY/DISARMED",
    )


def main() -> int:
    for line in build_probe_lines():
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
