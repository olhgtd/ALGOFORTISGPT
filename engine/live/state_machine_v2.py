"""AlgoFortis V2 live safety state machine.

This module is deliberately broker-neutral: it controls safety state only and
contains no broker adapter, credentials, order placement, or mutation path.
Phase 2 keeps arming disabled by default and never auto-arms after restart,
crash recovery, reconnect, or emergency stop.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol


class LiveState(str, Enum):
    DISABLED = "DISABLED"
    READY = "READY"
    CONNECTING = "CONNECTING"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    PAUSED = "PAUSED"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    RECOVERY = "RECOVERY"


class TransitionReason(str, Enum):
    OWNER_ENABLE = "owner_enable"
    OWNER_DISABLE = "owner_disable"
    CONNECT_REQUEST = "connect_request"
    ARM_REQUEST = "arm_request"
    CONNECTIVITY_DEGRADED = "connectivity_degraded"
    PAUSE_REQUEST = "pause_request"
    EMERGENCY_STOP = "emergency_stop"
    RECOVERY_COMPLETE = "recovery_complete"
    RECONNECT = "reconnect"
    RESTART_RECOVERY = "restart_recovery"
    CRASH_RECOVERY = "crash_recovery"


class LiveStateTransitionError(RuntimeError):
    """Raised when a requested state change cannot be proven safe."""


class _AuditSink(Protocol):
    def write(self, event_type: str, payload: dict[str, object]) -> None: ...


class _ArmAuthority(Protocol):
    allowed: bool
    reference: str


_ALLOWED: dict[LiveState, frozenset[LiveState]] = {
    LiveState.DISABLED: frozenset({LiveState.READY}),
    LiveState.READY: frozenset(
        {LiveState.DISABLED, LiveState.CONNECTING, LiveState.EMERGENCY_STOP}
    ),
    LiveState.CONNECTING: frozenset(
        {LiveState.READY, LiveState.ACTIVE, LiveState.DEGRADED, LiveState.EMERGENCY_STOP}
    ),
    LiveState.ACTIVE: frozenset(
        {LiveState.DEGRADED, LiveState.PAUSED, LiveState.EMERGENCY_STOP}
    ),
    LiveState.DEGRADED: frozenset(
        {LiveState.CONNECTING, LiveState.PAUSED, LiveState.EMERGENCY_STOP}
    ),
    LiveState.PAUSED: frozenset(
        {LiveState.READY, LiveState.RECOVERY, LiveState.EMERGENCY_STOP}
    ),
    LiveState.EMERGENCY_STOP: frozenset({LiveState.RECOVERY, LiveState.DISABLED}),
    LiveState.RECOVERY: frozenset({LiveState.READY, LiveState.DISABLED}),
}


class LiveStateMachine:
    """Audit-before-mutation authority for the Phase-2 live safety state."""

    def __init__(
        self,
        *,
        audit_sink: _AuditSink,
        arm_enabled: bool = False,
        initial_state: LiveState = LiveState.DISABLED,
    ) -> None:
        if not callable(getattr(audit_sink, "write", None)):
            raise TypeError("audit_sink must provide write(event_type, payload)")
        if not isinstance(arm_enabled, bool):
            raise TypeError("arm_enabled must be bool")
        if not isinstance(initial_state, LiveState):
            raise TypeError("initial_state must be LiveState")
        self._audit_sink = audit_sink
        self._arm_enabled = arm_enabled
        self._state = initial_state

    @property
    def state(self) -> LiveState:
        return self._state

    @property
    def is_active(self) -> bool:
        return self._state is LiveState.ACTIVE

    def transition(
        self,
        target: LiveState,
        *,
        reason: TransitionReason,
        arm_authority: _ArmAuthority | None = None,
    ) -> LiveState:
        if not isinstance(target, LiveState):
            raise TypeError("target must be LiveState")
        if not isinstance(reason, TransitionReason):
            raise TypeError("reason must be TransitionReason")
        if target is self._state:
            raise LiveStateTransitionError("self transition is not allowed")
        if target not in _ALLOWED[self._state]:
            raise LiveStateTransitionError(
                f"illegal live state transition: {self._state.value} -> {target.value}"
            )

        authority_reference: str | None = None
        if target is LiveState.ACTIVE:
            if reason is not TransitionReason.ARM_REQUEST:
                raise LiveStateTransitionError("ACTIVE requires explicit arm request")
            if not self._arm_enabled:
                raise LiveStateTransitionError("live arm is disabled in this runtime")
            if arm_authority is None:
                raise LiveStateTransitionError("explicit arm authority is required")
            if getattr(arm_authority, "allowed", None) is not True:
                raise LiveStateTransitionError("arm authority denied")
            authority_reference = getattr(arm_authority, "reference", None)
            if not isinstance(authority_reference, str) or not authority_reference.strip():
                raise LiveStateTransitionError("arm authority reference is required")

        payload: dict[str, object] = {
            "from_state": self._state.value,
            "to_state": target.value,
            "reason": reason.value,
            "arm_enabled": self._arm_enabled,
        }
        if authority_reference is not None:
            payload["arm_authority_ref"] = authority_reference.strip()

        self._write_audit(payload)
        self._state = target
        return self._state

    @classmethod
    def restore_after_restart(
        cls,
        *,
        previous_state: LiveState,
        audit_sink: _AuditSink,
    ) -> "LiveStateMachine":
        return cls._restore(
            previous_state=previous_state,
            audit_sink=audit_sink,
            reason=TransitionReason.RESTART_RECOVERY,
        )

    @classmethod
    def restore_after_crash(
        cls,
        *,
        previous_state: LiveState,
        audit_sink: _AuditSink,
    ) -> "LiveStateMachine":
        return cls._restore(
            previous_state=previous_state,
            audit_sink=audit_sink,
            reason=TransitionReason.CRASH_RECOVERY,
        )

    @classmethod
    def _restore(
        cls,
        *,
        previous_state: LiveState,
        audit_sink: _AuditSink,
        reason: TransitionReason,
    ) -> "LiveStateMachine":
        if not isinstance(previous_state, LiveState):
            raise TypeError("previous_state must be LiveState")
        machine = cls(
            audit_sink=audit_sink,
            arm_enabled=False,
            initial_state=LiveState.RECOVERY,
        )
        machine._write_audit(
            {
                "from_state": previous_state.value,
                "to_state": LiveState.RECOVERY.value,
                "reason": reason.value,
                "arm_enabled": False,
            }
        )
        return machine

    def _write_audit(self, payload: dict[str, object]) -> None:
        try:
            self._audit_sink.write("LIVE_STATE_TRANSITION", dict(payload))
        except Exception as error:
            raise LiveStateTransitionError(
                "audit write failed; live state mutation blocked"
            ) from error


__all__ = [
    "LiveState",
    "TransitionReason",
    "LiveStateTransitionError",
    "LiveStateMachine",
]
