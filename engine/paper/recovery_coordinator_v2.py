"""Fail-closed Phase-5 Paper recovery sequencing.

The coordinator has deliberately no submit/retry/broker capability.  Its only
job is to re-establish owned truth and produce recovery evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol

from engine.paper.contracts_v2 import (
    PaperOperationalState,
    RecoveryCheckpoint,
    RecoveryReport,
)

_RECONCILIATION = frozenset({"CLEAN", "MISMATCH", "UNCERTAIN", "INCOMPLETE"})


@dataclass(frozen=True, slots=True)
class RecoveryInput:
    checkpoint: RecoveryCheckpoint
    previous_state: PaperOperationalState = PaperOperationalState.HEALTHY

    def __post_init__(self) -> None:
        if not isinstance(self.checkpoint, RecoveryCheckpoint):
            raise TypeError("checkpoint must be RecoveryCheckpoint")
        if not isinstance(self.previous_state, PaperOperationalState):
            raise TypeError("previous_state must be PaperOperationalState")


@dataclass(frozen=True, slots=True)
class ReconciliationVerdict:
    status: str
    discrepancies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        status = str(self.status).strip().upper()
        if status not in _RECONCILIATION:
            raise ValueError(f"unsupported reconciliation status: {self.status!r}")
        if not isinstance(self.discrepancies, tuple) or not all(
            isinstance(item, str) and item.strip() for item in self.discrepancies
        ):
            raise TypeError("discrepancies must be a tuple of non-empty strings")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "discrepancies", tuple(item.strip() for item in self.discrepancies))


class OwnedStateLoader(Protocol):
    def load_for_recovery(self, session_id: str) -> RecoveryInput: ...


class PaperReconcilerPort(Protocol):
    def reconcile(self, recovery_input: RecoveryInput) -> ReconciliationVerdict: ...


class ProtectiveIntegrityPort(Protocol):
    def check(self, recovery_input: RecoveryInput) -> str: ...


class FeedHealthPort(Protocol):
    def check(self, recovery_input: RecoveryInput) -> str: ...


class ClockHealthPort(Protocol):
    def check(self, recovery_input: RecoveryInput) -> str: ...


class SessionValidityPort(Protocol):
    def check(self, recovery_input: RecoveryInput) -> str: ...


class AlertPort(Protocol):
    def emit(self, code: str) -> str: ...


class RecoveryCoordinator:
    def __init__(
        self,
        *,
        loader: OwnedStateLoader,
        reconciler: PaperReconcilerPort,
        protective: ProtectiveIntegrityPort,
        feed: FeedHealthPort,
        clock: ClockHealthPort,
        session_validity: SessionValidityPort,
        alerts: AlertPort,
        now: Callable[[], datetime],
        recovery_id: Callable[[str, str], str],
    ) -> None:
        self._loader = loader
        self._reconciler = reconciler
        self._protective = protective
        self._feed = feed
        self._clock = clock
        self._session_validity = session_validity
        self._alerts = alerts
        self._now = now
        self._recovery_id = recovery_id

    def _report(
        self,
        *,
        trigger: str,
        session_id: str,
        recovery_input: RecoveryInput,
        reconciliation: ReconciliationVerdict,
        protective: str,
        feed: str,
        clock: str,
        session_validity: str,
        alerts: tuple[str, ...],
        final_state: PaperOperationalState,
    ) -> RecoveryReport:
        checkpoint = recovery_input.checkpoint
        return RecoveryReport(
            recovery_id=self._recovery_id(trigger, session_id),
            trigger=trigger,
            previous_state=recovery_input.previous_state,
            checkpoint_fingerprint=checkpoint.fingerprint,
            restored_order_refs=checkpoint.open_order_refs,
            restored_position_refs=checkpoint.open_position_refs,
            reconciliation_result=reconciliation.status,
            protective_integrity_result=protective,
            feed_health=feed,
            clock_health=clock,
            session_expiry_validity=session_validity,
            unresolved_discrepancies=reconciliation.discrepancies,
            alert_refs=alerts,
            final_state=final_state,
            manual_resume_required=True,
            produced_at=self._now(),
        )

    def recover(self, trigger: str, session_id: str) -> RecoveryReport:
        if not isinstance(trigger, str) or not trigger.strip():
            raise ValueError("trigger must be non-empty")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be non-empty")
        trigger = trigger.strip().upper()
        session_id = session_id.strip()
        recovery_input = self._loader.load_for_recovery(session_id)
        if recovery_input.checkpoint.session_id != session_id:
            raise ValueError("recovery checkpoint session_id mismatch")

        reconciliation = self._reconciler.reconcile(recovery_input)
        if reconciliation.status != "CLEAN":
            alert = self._alerts.emit(f"RECONCILIATION_{reconciliation.status}")
            return self._report(
                trigger=trigger,
                session_id=session_id,
                recovery_input=recovery_input,
                reconciliation=reconciliation,
                protective="NOT_CHECKED",
                feed="NOT_CHECKED",
                clock="NOT_CHECKED",
                session_validity="NOT_CHECKED",
                alerts=(alert,),
                final_state=PaperOperationalState.HALTED,
            )

        protective = str(self._protective.check(recovery_input)).strip().upper()
        if protective != "VALID":
            alert = self._alerts.emit(f"PROTECTIVE_{protective or 'UNKNOWN'}")
            return self._report(
                trigger=trigger,
                session_id=session_id,
                recovery_input=recovery_input,
                reconciliation=reconciliation,
                protective=protective or "UNKNOWN",
                feed="NOT_CHECKED",
                clock="NOT_CHECKED",
                session_validity="NOT_CHECKED",
                alerts=(alert,),
                final_state=PaperOperationalState.HALTED,
            )

        feed = str(self._feed.check(recovery_input)).strip().upper()
        if feed != "HEALTHY":
            alert = self._alerts.emit(f"FEED_{feed or 'UNKNOWN'}")
            return self._report(
                trigger=trigger, session_id=session_id, recovery_input=recovery_input,
                reconciliation=reconciliation, protective=protective, feed=feed or "UNKNOWN",
                clock="NOT_CHECKED", session_validity="NOT_CHECKED", alerts=(alert,),
                final_state=PaperOperationalState.HALTED,
            )

        clock = str(self._clock.check(recovery_input)).strip().upper()
        if clock != "HEALTHY":
            alert = self._alerts.emit(f"CLOCK_{clock or 'UNKNOWN'}")
            return self._report(
                trigger=trigger, session_id=session_id, recovery_input=recovery_input,
                reconciliation=reconciliation, protective=protective, feed=feed,
                clock=clock or "UNKNOWN", session_validity="NOT_CHECKED", alerts=(alert,),
                final_state=PaperOperationalState.HALTED,
            )

        validity = str(self._session_validity.check(recovery_input)).strip().upper()
        if validity != "VALID":
            alert = self._alerts.emit(f"SESSION_{validity or 'UNKNOWN'}")
            return self._report(
                trigger=trigger, session_id=session_id, recovery_input=recovery_input,
                reconciliation=reconciliation, protective=protective, feed=feed, clock=clock,
                session_validity=validity or "UNKNOWN", alerts=(alert,),
                final_state=PaperOperationalState.HALTED,
            )

        return self._report(
            trigger=trigger,
            session_id=session_id,
            recovery_input=recovery_input,
            reconciliation=reconciliation,
            protective=protective,
            feed=feed,
            clock=clock,
            session_validity=validity,
            alerts=(),
            final_state=PaperOperationalState.READY_FOR_RESUME,
        )


__all__ = [
    "RecoveryInput",
    "ReconciliationVerdict",
    "OwnedStateLoader",
    "PaperReconcilerPort",
    "ProtectiveIntegrityPort",
    "FeedHealthPort",
    "ClockHealthPort",
    "SessionValidityPort",
    "AlertPort",
    "RecoveryCoordinator",
]
