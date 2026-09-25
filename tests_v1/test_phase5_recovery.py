from __future__ import annotations

from datetime import datetime, timezone

from engine.paper.contracts_v2 import PaperOperationalState, RecoveryCheckpoint
from engine.paper.recovery_coordinator_v2 import (
    ReconciliationVerdict,
    RecoveryCoordinator,
    RecoveryInput,
)

NOW = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)


def _checkpoint() -> RecoveryCheckpoint:
    return RecoveryCheckpoint(
        checkpoint_id="cp-r1",
        session_id="session-r1",
        persisted_at=NOW,
        last_event_sequence=12,
        open_order_refs=("intent-stale",),
        open_position_refs=("position-1",),
        recovery_required=True,
        reason="RESTART",
        fingerprint="b" * 64,
    )


class _Loader:
    def load_for_recovery(self, session_id: str) -> RecoveryInput:
        return RecoveryInput(checkpoint=_checkpoint())


class _Reconciler:
    def __init__(self, verdict: ReconciliationVerdict):
        self.verdict = verdict
        self.calls = 0

    def reconcile(self, recovery_input: RecoveryInput) -> ReconciliationVerdict:
        self.calls += 1
        return self.verdict


class _Check:
    def __init__(self, result: str):
        self.result = result
        self.calls = 0

    def check(self, recovery_input: RecoveryInput) -> str:
        self.calls += 1
        return self.result


class _Alerts:
    def __init__(self):
        self.events: list[str] = []

    def emit(self, code: str) -> str:
        self.events.append(code)
        return f"alert-{len(self.events)}"


def _coordinator(reconciliation: ReconciliationVerdict):
    protective = _Check("VALID")
    feed = _Check("HEALTHY")
    clock = _Check("HEALTHY")
    session = _Check("VALID")
    alerts = _Alerts()
    coordinator = RecoveryCoordinator(
        loader=_Loader(),
        reconciler=_Reconciler(reconciliation),
        protective=protective,
        feed=feed,
        clock=clock,
        session_validity=session,
        alerts=alerts,
        now=lambda: NOW,
        recovery_id=lambda trigger, session_id: f"recovery-{trigger.lower()}-{session_id}",
    )
    return coordinator, protective, feed, clock, session, alerts


def test_uncertain_reconciliation_halts_before_downstream_checks_or_retry_permission():
    coordinator, protective, feed, clock, session, alerts = _coordinator(
        ReconciliationVerdict(status="UNCERTAIN", discrepancies=("ack truth unresolved",))
    )
    report = coordinator.recover("ACK_UNCERTAIN", "session-r1")
    assert report.final_state is PaperOperationalState.HALTED
    assert report.manual_resume_required is True
    assert report.reconciliation_result == "UNCERTAIN"
    assert report.unresolved_discrepancies == ("ack truth unresolved",)
    assert protective.calls == 0
    assert feed.calls == 0
    assert clock.calls == 0
    assert session.calls == 0
    assert alerts.events == ["RECONCILIATION_UNCERTAIN"]


def test_mismatch_halts_and_never_replays_checkpoint_intents():
    coordinator, *_ = _coordinator(
        ReconciliationVerdict(status="MISMATCH", discrepancies=("order mismatch",))
    )
    report = coordinator.recover("RESTART", "session-r1")
    assert report.final_state is PaperOperationalState.HALTED
    assert report.restored_order_refs == ("intent-stale",)
    assert report.unresolved_discrepancies == ("order mismatch",)
    # Recovery reports refs only; coordinator exposes no submit/replay capability.
    assert not hasattr(coordinator, "submit")
    assert not hasattr(coordinator, "retry")


def test_clean_recovery_runs_checks_in_order_and_stops_at_ready_for_resume():
    coordinator, protective, feed, clock, session, alerts = _coordinator(
        ReconciliationVerdict(status="CLEAN", discrepancies=())
    )
    report = coordinator.recover("RESTART", "session-r1")
    assert protective.calls == 1
    assert feed.calls == 1
    assert clock.calls == 1
    assert session.calls == 1
    assert alerts.events == []
    assert report.protective_integrity_result == "VALID"
    assert report.feed_health == "HEALTHY"
    assert report.clock_health == "HEALTHY"
    assert report.session_expiry_validity == "VALID"
    assert report.final_state is PaperOperationalState.READY_FOR_RESUME
    assert report.manual_resume_required is True
