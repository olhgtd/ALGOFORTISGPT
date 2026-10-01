"""Operational Phase-5 Paper safety wrapper.

Wraps the existing paper runner without rewriting its legacy execution core.
This boundary owns Phase-5 host preflight, recovery/manual-resume gating and
critical alert fan-out. It has no Live arming or order-submission capability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Protocol

from engine.alerts.contracts import AlertEnvelope
from engine.paper.contracts_v2 import FailureSeverity, PaperOperationalState
from engine.paper.operational_state_v2 import (
    PaperOperationalStateMachine,
    PaperTransitionReason,
)


class Phase5RuntimeSafetyError(RuntimeError):
    """Raised whenever the operational Paper wrapper must fail closed."""


class PaperRunnerDelegate(Protocol):
    def initialize(self) -> None: ...

    def run(self, **kwargs: Any) -> Any: ...

    def shutdown(self) -> None: ...


class InstanceLockPort(Protocol):
    def acquire(self) -> bool: ...

    def release(self) -> None: ...


class PowerSessionPort(Protocol):
    def begin_session(self) -> None: ...

    def end_session(self) -> None: ...

    def resume_detected(self) -> bool: ...


class ClockHealthPort(Protocol):
    def check(self, policy_ref: str | None) -> Any: ...


class CriticalAlertPort(Protocol):
    def dispatch_critical(self, envelope: AlertEnvelope) -> tuple[Any, ...]: ...


class RecoveryPort(Protocol):
    def recover(self, trigger: str, session_id: str) -> Any: ...


@dataclass(frozen=True, slots=True)
class _ManualResumeGrant:
    allowed: bool
    reference: str


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


class Phase5PaperRuntime:
    """Fail-closed operational wrapper around a Paper-only runner delegate."""

    def __init__(
        self,
        *,
        delegate: PaperRunnerDelegate,
        session_id: str,
        instance_lock: InstanceLockPort,
        power_session: PowerSessionPort,
        clock_health: ClockHealthPort,
        clock_policy_ref: str | None,
        alerts: CriticalAlertPort,
        recovery: RecoveryPort,
        now: Callable[[], datetime],
    ) -> None:
        for value, name in (
            (delegate, "delegate"),
            (instance_lock, "instance_lock"),
            (power_session, "power_session"),
            (clock_health, "clock_health"),
            (alerts, "alerts"),
            (recovery, "recovery"),
        ):
            if value is None:
                raise TypeError(f"{name} is required")
        if not callable(now):
            raise TypeError("now must be callable")

        self._delegate = delegate
        self._session_id = _text(session_id, "session_id")
        self._instance_lock = instance_lock
        self._power_session = power_session
        self._clock_health = clock_health
        self._clock_policy_ref = (
            None if clock_policy_ref is None else _text(clock_policy_ref, "clock_policy_ref")
        )
        self._alerts = alerts
        self._recovery = recovery
        self._now = now
        self._state = PaperOperationalStateMachine()
        self._initialized = False
        self._ownership_acquired = False
        self._power_active = False

    @property
    def state(self) -> PaperOperationalState:
        return self._state.state

    def _alert(self, code: str, detail: str, *, recovery_required: bool = False) -> None:
        severity = (
            FailureSeverity.RECOVERY_REQUIRED
            if recovery_required
            else FailureSeverity.CRITICAL
        )
        envelope = AlertEnvelope(
            alert_id=f"phase5:{self._session_id}:{code}",
            incident_id=f"phase5:{self._session_id}:{code}",
            severity=severity,
            incident_type=code,
            session_ref=self._session_id,
            occurred_at=self._now(),
            safety_state=self.state,
            required_action=(
                "RECOVERY_AND_MANUAL_RESUME"
                if recovery_required
                else "MANUAL_REVIEW"
            ),
            safe_detail=detail,
        )
        self._alerts.dispatch_critical(envelope)

    def _release_host_ownership(self) -> None:
        if self._power_active:
            try:
                self._power_session.end_session()
            finally:
                self._power_active = False
        if self._ownership_acquired:
            try:
                self._instance_lock.release()
            finally:
                self._ownership_acquired = False

    def initialize(self) -> None:
        if self._initialized:
            return

        if self._instance_lock.acquire() is not True:
            self._state.halt_entries(reason=PaperTransitionReason.STATE_CONTINUITY_UNCERTAIN)
            self._alert("SECOND_INSTANCE_REJECTED", "Another Paper runtime owns this session context")
            raise Phase5RuntimeSafetyError("SECOND_INSTANCE_REJECTED")
        self._ownership_acquired = True

        try:
            clock = self._clock_health.check(self._clock_policy_ref)
            if getattr(clock, "entry_eligible", False) is not True:
                self._state.halt_entries(reason=PaperTransitionReason.CLOCK_UNHEALTHY)
                reason = str(getattr(clock, "reason", "CLOCK_UNHEALTHY"))
                self._alert(reason, "Clock health does not permit new Paper entries")
                raise Phase5RuntimeSafetyError(reason)

            self._power_session.begin_session()
            self._power_active = True

            if self._power_session.resume_detected():
                self._enter_resume_recovery()
                raise Phase5RuntimeSafetyError("MANUAL_RESUME_REQUIRED")

            self._delegate.initialize()
            self._initialized = True
        except Exception:
            if not self._initialized:
                self._release_host_ownership()
            raise

    def _enter_resume_recovery(self) -> None:
        if self.state is not PaperOperationalState.RECOVERY:
            self._state.require_recovery(
                reason=PaperTransitionReason.SLEEP_RESUME_DISCONTINUITY
            )
        report = self._recovery.recover("SLEEP_RESUME", self._session_id)
        final_state = getattr(report, "final_state", None)
        if final_state is PaperOperationalState.READY_FOR_RESUME:
            self._state.mark_ready_for_resume(
                reason=PaperTransitionReason.RECOVERY_CHECKS_CLEAN
            )
            self._alert(
                "RECOVERY_READY_MANUAL_RESUME_REQUIRED",
                "Recovery checks are clean; explicit manual resume is still required",
                recovery_required=True,
            )
            return

        if self.state is PaperOperationalState.RECOVERY:
            self._state.halt_entries(
                reason=PaperTransitionReason.RECONCILIATION_MISMATCH
            )
        self._alert(
            "RECOVERY_NOT_CLEAN",
            "Recovery did not reach READY_FOR_RESUME; Paper entries remain halted",
            recovery_required=True,
        )
        raise Phase5RuntimeSafetyError("RECOVERY_NOT_CLEAN")

    def manual_resume(self) -> None:
        self._state.resume(
            authority=_ManualResumeGrant(
                allowed=True,
                reference=f"manual-resume:{self._session_id}",
            ),
            reason=PaperTransitionReason.MANUAL_RESUME,
        )

    def run(self, **kwargs: Any) -> Any:
        self.initialize()
        if self._power_session.resume_detected():
            self._enter_resume_recovery()
            raise Phase5RuntimeSafetyError("MANUAL_RESUME_REQUIRED")
        if self.state is not PaperOperationalState.HEALTHY:
            raise Phase5RuntimeSafetyError(
                f"PAPER_RUNTIME_NOT_HEALTHY:{self.state.value}"
            )
        return self._delegate.run(**kwargs)

    def shutdown(self) -> None:
        delegate_error: BaseException | None = None
        try:
            if self._initialized:
                try:
                    self._delegate.shutdown()
                except BaseException as error:  # cleanup must still release host ownership
                    delegate_error = error
        finally:
            self._initialized = False
            self._release_host_ownership()
        if delegate_error is not None:
            raise delegate_error


__all__ = [
    "Phase5PaperRuntime",
    "Phase5RuntimeSafetyError",
    "PaperRunnerDelegate",
]
