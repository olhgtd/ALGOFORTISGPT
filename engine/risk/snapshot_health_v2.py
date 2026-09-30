"""Route RiskSnapshot builder health into the existing Phase-5 safety spine."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from engine.alerts.contracts import AlertEnvelope
from engine.core.runtime import Clock, IdGenerator
from engine.paper.contracts_v2 import FailureIncident, FailureSeverity, PaperOperationalState
from engine.paper.failure_policy_v2 import StormEvaluator
from engine.paper.operational_state_v2 import PaperOperationalStateMachine, PaperTransitionReason


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _aware(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware datetime")
    return value


def _non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be int")
    if value < 0:
        raise ValueError(f"{field} must be non-negative")
    return value


@dataclass(frozen=True, slots=True)
class SnapshotHealthEvent:
    failure_class: str
    severity: FailureSeverity
    occurred_at: datetime
    affected_scope: str
    health_generation: int
    safe_reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "failure_class", _text(self.failure_class, "failure_class").upper())
        if not isinstance(self.severity, FailureSeverity):
            raise TypeError("severity must be FailureSeverity")
        object.__setattr__(self, "occurred_at", _aware(self.occurred_at, "occurred_at"))
        object.__setattr__(self, "affected_scope", _text(self.affected_scope, "affected_scope"))
        object.__setattr__(self, "health_generation", _non_negative_int(self.health_generation, "health_generation"))
        object.__setattr__(self, "safe_reason", _text(self.safe_reason, "safe_reason"))


class RiskSnapshotHealthCoordinator:
    def __init__(
        self,
        *,
        state_machine: PaperOperationalStateMachine,
        incident_store,
        alert_dispatcher,
        id_generator: IdGenerator,
        clock: Clock,
        session_scope: str,
        storm_evaluator: StormEvaluator | None = None,
    ) -> None:
        if not isinstance(state_machine, PaperOperationalStateMachine):
            raise TypeError("state_machine must be PaperOperationalStateMachine")
        if not callable(getattr(incident_store, "save_incident", None)):
            raise TypeError("incident_store must provide save_incident")
        if not callable(getattr(alert_dispatcher, "dispatch_critical", None)):
            raise TypeError("alert_dispatcher must provide dispatch_critical")
        if not callable(getattr(id_generator, "new_id", None)):
            raise TypeError("id_generator must provide new_id")
        if not callable(getattr(clock, "now_utc", None)):
            raise TypeError("clock must provide now_utc")
        if not callable(getattr(clock, "monotonic_ns", None)):
            raise TypeError("clock must provide monotonic_ns")
        if storm_evaluator is not None and not isinstance(storm_evaluator, StormEvaluator):
            raise TypeError("storm_evaluator must be StormEvaluator")
        self._state_machine = state_machine
        self._incident_store = incident_store
        self._alert_dispatcher = alert_dispatcher
        self._id_generator = id_generator
        self._clock = clock
        self._session_scope = _text(session_scope, "session_scope")
        self._storm_evaluator = storm_evaluator

    def handle(self, event: SnapshotHealthEvent) -> PaperOperationalState:
        if not isinstance(event, SnapshotHealthEvent):
            raise TypeError("event must be SnapshotHealthEvent")
        previous = self._state_machine.state
        resulting = self._transition(event)
        incident_id = self._id_generator.new_id("failure_incident")
        incident = FailureIncident(
            incident_id=incident_id,
            failure_type=event.failure_class,
            severity=event.severity,
            detected_at=event.occurred_at,
            source="risk_snapshot_builder",
            affected_scope=event.affected_scope,
            previous_state=previous,
            resulting_state=resulting,
            transition_reason=event.safe_reason,
            halt_latched=resulting is PaperOperationalState.HALTED,
            recovery_id=None,
            storm_policy_ref=(
                self._storm_evaluator.policy_ref
                if self._storm_evaluator is not None
                else None
            ),
            resolved_at=None,
            resolution_evidence=None,
        )
        self._incident_store.save_incident(incident)

        if event.severity in {FailureSeverity.CRITICAL, FailureSeverity.RECOVERY_REQUIRED}:
            alert_id = self._id_generator.new_id("alert")
            envelope = AlertEnvelope(
                alert_id=alert_id,
                incident_id=incident_id,
                severity=event.severity,
                incident_type=event.failure_class,
                session_ref=self._session_scope,
                occurred_at=event.occurred_at,
                safety_state=resulting,
                required_action="RESTORE_RISK_SNAPSHOT_AUTHORITY",
                safe_detail=event.safe_reason,
            )
            try:
                records = self._alert_dispatcher.dispatch_critical(envelope)
            except Exception:
                records = ()
            save_delivery = getattr(self._incident_store, "save_alert_delivery", None)
            if callable(save_delivery):
                for record in records:
                    save_delivery(record)
        return resulting

    def _transition(self, event: SnapshotHealthEvent) -> PaperOperationalState:
        current = self._state_machine.state
        if event.severity is FailureSeverity.INFO:
            return current

        if event.severity is FailureSeverity.RECOVERY_REQUIRED:
            if current is PaperOperationalState.RECOVERY:
                return current
            return self._state_machine.require_recovery(
                reason=PaperTransitionReason.RISK_SNAPSHOT_CONTINUITY_UNCERTAIN
            )

        if event.severity is FailureSeverity.CRITICAL:
            if current is PaperOperationalState.HALTED:
                return current
            return self._state_machine.halt_entries(
                reason=PaperTransitionReason.RISK_SNAPSHOT_STALE
            )

        # WARNING: apply existing storm policy if one is injected; otherwise a
        # single trustworthy-state degradation is enough. Sticky HALTED/RECOVERY
        # never auto-clear from a builder-health event.
        if current in {
            PaperOperationalState.HALTED,
            PaperOperationalState.RECOVERY,
            PaperOperationalState.READY_FOR_RESUME,
        }:
            return current
        if self._storm_evaluator is not None:
            occurred_ms = self._clock.monotonic_ns() // 1_000_000
            decision = self._storm_evaluator.observe(event.failure_class, occurred_ms)
            if decision.halt:
                if current is PaperOperationalState.HALTED:
                    return current
                return self._state_machine.halt_entries(
                    reason=PaperTransitionReason.STORM_THRESHOLD_CROSSED
                )
        if current is PaperOperationalState.DEGRADED:
            return current
        return self._state_machine.degrade(
            reason=PaperTransitionReason.RISK_SNAPSHOT_BUILDER_UNHEALTHY
        )


__all__ = ["RiskSnapshotHealthCoordinator", "SnapshotHealthEvent"]
