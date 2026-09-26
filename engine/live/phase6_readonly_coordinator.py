"""Phase-6 read-only composition over the existing Live reconciler.

This module reuses the Phase-5 FailureIncident/alert vocabulary. It cannot arm
Live or mutate broker orders; even a clean observation never grants entry.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol

from engine.alerts.contracts import AlertEnvelope
from engine.paper.contracts_v2 import FailureIncident, FailureSeverity, PaperOperationalState
from engine.reconciliation.live_reconciler import (
    LiveBrokerReconciler,
    LiveReconciliationReport,
    OrderReconciliationAction,
)


class IncidentSink(Protocol):
    def record_once(self, incident: FailureIncident) -> bool: ...


class CriticalAlertPort(Protocol):
    def dispatch_critical(self, envelope: AlertEnvelope) -> tuple[object, ...]: ...


class EntryHaltPort(Protocol):
    def halt_new_entries(self, *, reason: str, incident_id: str) -> None: ...


@dataclass(frozen=True, slots=True)
class Phase6ObservationResult:
    report: LiveReconciliationReport
    incidents: tuple[FailureIncident, ...]
    alert_records: tuple[object, ...]
    new_entry_eligible: bool = False


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _incident_id(session_ref: str, failure_type: str, affected_scope: str) -> str:
    raw = f"phase6|{session_ref}|{failure_type}|{affected_scope}".encode("utf-8")
    return "phase6:" + hashlib.sha256(raw).hexdigest()


class Phase6ReadonlyCoordinator:
    def __init__(
        self,
        *,
        reconciler: LiveBrokerReconciler,
        incident_sink: IncidentSink,
        alerts: CriticalAlertPort,
        halt_port: EntryHaltPort,
        now: Callable[[], datetime],
    ) -> None:
        if not isinstance(reconciler, LiveBrokerReconciler):
            raise TypeError("reconciler must be LiveBrokerReconciler")
        if not callable(getattr(incident_sink, "record_once", None)):
            raise TypeError("incident_sink must provide record_once")
        if not callable(getattr(alerts, "dispatch_critical", None)):
            raise TypeError("alerts must provide dispatch_critical")
        if not callable(getattr(halt_port, "halt_new_entries", None)):
            raise TypeError("halt_port must provide halt_new_entries")
        if not callable(now):
            raise TypeError("now must be callable")
        self._reconciler = reconciler
        self._incident_sink = incident_sink
        self._alerts = alerts
        self._halt_port = halt_port
        self._now = now

    def _build_incident(
        self,
        *,
        session_ref: str,
        failure_type: str,
        affected_scope: str,
        severity: FailureSeverity,
        transition_reason: str,
    ) -> FailureIncident:
        return FailureIncident(
            incident_id=_incident_id(session_ref, failure_type, affected_scope),
            failure_type=failure_type,
            severity=severity,
            detected_at=self._now(),
            source="PHASE6_LIVE_READONLY_RECONCILIATION",
            affected_scope=affected_scope,
            previous_state=PaperOperationalState.HEALTHY,
            resulting_state=PaperOperationalState.HALTED,
            transition_reason=transition_reason,
            halt_latched=True,
            recovery_id=None,
            storm_policy_ref=None,
            resolved_at=None,
            resolution_evidence=None,
        )

    @staticmethod
    def _safe_detail(failure_type: str) -> str:
        if failure_type == "FOREIGN_BROKER_ORDER":
            return "Foreign broker order detected; manual reconciliation review required"
        if failure_type == "FOREIGN_BROKER_POSITION":
            return "Foreign broker position detected; manual reconciliation review required"
        return "Broker truth unavailable or uncertain; manual reconciliation review required"

    def _record_and_alert(
        self,
        incident: FailureIncident,
        session_ref: str,
    ) -> tuple[object, ...]:
        created = self._incident_sink.record_once(incident)
        if not created:
            return ()
        self._halt_port.halt_new_entries(
            reason=incident.transition_reason,
            incident_id=incident.incident_id,
        )
        envelope = AlertEnvelope(
            alert_id=f"alert:{incident.incident_id}",
            incident_id=incident.incident_id,
            severity=incident.severity,
            incident_type=incident.failure_type,
            session_ref=session_ref,
            occurred_at=incident.detected_at,
            safety_state=incident.resulting_state,
            required_action="MANUAL_RECONCILIATION_REVIEW",
            safe_detail=self._safe_detail(incident.failure_type),
        )
        return tuple(self._alerts.dispatch_critical(envelope))

    def observe_and_reconcile(
        self,
        *,
        session_ref: str,
        **reconcile_kwargs: object,
    ) -> Phase6ObservationResult:
        session_ref = _text(session_ref, "session_ref")
        report = self._reconciler.run_full_reconciliation(**reconcile_kwargs)
        incidents: list[FailureIncident] = []

        for item in report.order_items:
            if item.action is OrderReconciliationAction.ORPHAN_FOUND:
                incidents.append(
                    self._build_incident(
                        session_ref=session_ref,
                        failure_type="FOREIGN_BROKER_ORDER",
                        affected_scope=f"broker-order:{item.broker_order_identity}",
                        severity=FailureSeverity.CRITICAL,
                        transition_reason="FOREIGN_BROKER_ORDER_DETECTED",
                    )
                )

        for item in report.position_items:
            if item.action == "BROKER_ONLY_POSITION":
                incidents.append(
                    self._build_incident(
                        session_ref=session_ref,
                        failure_type="FOREIGN_BROKER_POSITION",
                        affected_scope=f"broker-position:{item.symbol}",
                        severity=FailureSeverity.CRITICAL,
                        transition_reason="FOREIGN_BROKER_POSITION_DETECTED",
                    )
                )

        if report.errors or report.funds is None:
            incidents.append(
                self._build_incident(
                    session_ref=session_ref,
                    failure_type="BROKER_TRUTH_UNAVAILABLE",
                    affected_scope=f"broker:{report.broker_id}",
                    severity=FailureSeverity.RECOVERY_REQUIRED,
                    transition_reason="BROKER_TRUTH_UNCERTAIN",
                )
            )

        alert_records: list[object] = []
        for incident in incidents:
            alert_records.extend(self._record_and_alert(incident, session_ref))

        return Phase6ObservationResult(
            report=report,
            incidents=tuple(incidents),
            alert_records=tuple(alert_records),
            new_entry_eligible=False,
        )


__all__ = [
    "CriticalAlertPort",
    "EntryHaltPort",
    "IncidentSink",
    "Phase6ObservationResult",
    "Phase6ReadonlyCoordinator",
]
