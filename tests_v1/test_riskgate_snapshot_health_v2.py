from __future__ import annotations

from datetime import datetime, timezone

from engine.alerts.contracts import AlertDeliveryRecord
from engine.core.runtime import FixedClock
from engine.paper.contracts_v2 import FailureSeverity, PaperOperationalState
from engine.paper.failure_policy_v2 import FailureStormPolicy, StormEvaluator
from engine.paper.operational_state_v2 import PaperOperationalStateMachine
from engine.risk.snapshot_health_v2 import RiskSnapshotHealthCoordinator, SnapshotHealthEvent


class _Ids:
    def __init__(self) -> None:
        self.value = 0

    def new_id(self, kind: str) -> str:
        self.value += 1
        return f"{kind}-{self.value}"


class _IncidentStore:
    def __init__(self) -> None:
        self.incidents = []
        self.deliveries = []

    def save_incident(self, incident) -> None:
        self.incidents.append(incident)

    def save_alert_delivery(self, record) -> None:
        self.deliveries.append(record)


class _Dispatcher:
    def __init__(self, records=()) -> None:
        self.records = tuple(records)
        self.envelopes = []

    def dispatch_critical(self, envelope):
        self.envelopes.append(envelope)
        return self.records


def _clock() -> FixedClock:
    return FixedClock(
        datetime(2026, 9, 30, tzinfo=timezone.utc),
        1,
        object(),
    )


def _event(severity: FailureSeverity, failure_class: str = "RISK_SNAPSHOT_STALE") -> SnapshotHealthEvent:
    return SnapshotHealthEvent(
        failure_class=failure_class,
        severity=severity,
        occurred_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
        affected_scope="paper-session-1",
        health_generation=7,
        safe_reason="snapshot authority unavailable",
    )


def _coordinator(state=PaperOperationalState.HEALTHY, dispatcher=None, storm_evaluator=None):
    machine = PaperOperationalStateMachine(initial_state=state)
    store = _IncidentStore()
    return (
        RiskSnapshotHealthCoordinator(
            state_machine=machine,
            incident_store=store,
            alert_dispatcher=dispatcher or _Dispatcher(),
            id_generator=_Ids(),
            clock=_clock(),
            session_scope="paper-session-1",
            storm_evaluator=storm_evaluator,
        ),
        machine,
        store,
    )


def test_warning_builder_failure_degrades_without_new_state_model() -> None:
    coordinator, machine, store = _coordinator()
    result = coordinator.handle(_event(FailureSeverity.WARNING, "RISK_SNAPSHOT_BUILDER_UNHEALTHY"))
    assert result is PaperOperationalState.DEGRADED
    assert machine.state is PaperOperationalState.DEGRADED
    assert store.incidents[-1].resulting_state is PaperOperationalState.DEGRADED


def test_stale_or_unavailable_snapshot_halts_new_entries() -> None:
    coordinator, machine, store = _coordinator()
    result = coordinator.handle(_event(FailureSeverity.CRITICAL))
    assert result is PaperOperationalState.HALTED
    assert machine.state is PaperOperationalState.HALTED
    assert store.incidents[-1].halt_latched is True


def test_continuity_uncertainty_enters_recovery() -> None:
    coordinator, machine, store = _coordinator()
    result = coordinator.handle(
        _event(FailureSeverity.RECOVERY_REQUIRED, "RISK_SNAPSHOT_CONTINUITY_UNCERTAIN")
    )
    assert result is PaperOperationalState.RECOVERY
    assert machine.state is PaperOperationalState.RECOVERY
    assert store.incidents[-1].severity is FailureSeverity.RECOVERY_REQUIRED


def test_critical_alert_delivery_records_are_saved_independently() -> None:
    now = datetime(2026, 9, 30, tzinfo=timezone.utc)
    records = (
        AlertDeliveryRecord("alert-1", "incident-1", "windows", 1, "DELIVERED", None, now, now),
        AlertDeliveryRecord("alert-1", "incident-1", "telegram", 1, "FAILED", "offline", now, now),
    )
    dispatcher = _Dispatcher(records)
    coordinator, machine, store = _coordinator(dispatcher=dispatcher)
    coordinator.handle(_event(FailureSeverity.CRITICAL))
    assert machine.state is PaperOperationalState.HALTED
    assert len(dispatcher.envelopes) == 1
    assert len(store.deliveries) == 2
    assert {record.delivery_status for record in store.deliveries} == {"DELIVERED", "FAILED"}


def test_sticky_halted_state_does_not_auto_clear_on_health_event() -> None:
    coordinator, machine, _ = _coordinator(state=PaperOperationalState.HALTED)
    result = coordinator.handle(_event(FailureSeverity.WARNING, "RISK_SNAPSHOT_BUILDER_UNHEALTHY"))
    assert result is PaperOperationalState.HALTED
    assert machine.state is PaperOperationalState.HALTED


def test_mismatched_storm_policy_fails_closed_to_halted() -> None:
    policy = FailureStormPolicy(
        policy_id="TEST_ONLY/other-failure",
        version="v1",
        failure_class="OTHER_FAILURE",
        observation_window_ms=1000,
        trigger_count=2,
        cooldown_ms=0,
        escalation_action="HALT_ENTRIES",
        reset_rule="WINDOW_AND_COOLDOWN",
        test_only=True,
    )
    coordinator, machine, store = _coordinator(storm_evaluator=StormEvaluator(policy))
    result = coordinator.handle(
        _event(FailureSeverity.WARNING, "RISK_SNAPSHOT_BUILDER_UNHEALTHY")
    )
    assert result is PaperOperationalState.HALTED
    assert machine.state is PaperOperationalState.HALTED
    assert store.incidents[-1].halt_latched is True
