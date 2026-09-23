"""AlgoFortis V2 kill-switch domain semantics.

This module defines and audits safety commands only.  It never calls a broker,
never cancels or closes a real order itself, and does not enable live mutation.
Phase 2 remains READ_ONLY/DISARMED.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from engine.live.state_machine_v2 import (
    LiveState,
    LiveStateTransitionError,
    TransitionReason,
)


class KillSwitchError(RuntimeError):
    """Raised when kill-switch evidence cannot be established safely."""


class KillSwitchAction(str, Enum):
    HALT_ENTRIES = "HALT_ENTRIES"
    CANCEL_PENDING = "CANCEL_PENDING"
    FLATTEN_ALL = "FLATTEN_ALL"


class KillSwitchScope(str, Enum):
    POSITION = "POSITION"
    STRATEGY = "STRATEGY"
    USER = "USER"
    PLATFORM = "PLATFORM"


class CancelPendingScope(str, Enum):
    ENTRY_ORDERS_ONLY = "ENTRY_ORDERS_ONLY"


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True, slots=True)
class KillSwitchEvidence:
    scope: KillSwitchScope
    reason: str
    actions: tuple[KillSwitchAction, ...]
    cancel_pending_scope: CancelPendingScope | None
    protective_exits_active: bool
    reconciliation_active: bool
    alert_required: bool
    recovery_required: bool

    def __post_init__(self) -> None:
        if not isinstance(self.scope, KillSwitchScope):
            raise TypeError("scope must be KillSwitchScope")
        object.__setattr__(self, "reason", _text(self.reason, "reason"))
        if not isinstance(self.actions, tuple) or not self.actions:
            raise ValueError("actions must be a non-empty tuple")
        if any(not isinstance(action, KillSwitchAction) for action in self.actions):
            raise TypeError("actions must contain KillSwitchAction values")
        if len(self.actions) != len(set(self.actions)):
            raise ValueError("actions cannot contain duplicates")
        if KillSwitchAction.CANCEL_PENDING in self.actions:
            if self.cancel_pending_scope is not CancelPendingScope.ENTRY_ORDERS_ONLY:
                raise ValueError("CANCEL_PENDING is restricted to pending entry orders")
        elif self.cancel_pending_scope is not None:
            raise ValueError("cancel_pending_scope requires CANCEL_PENDING")
        if KillSwitchAction.FLATTEN_ALL in self.actions:
            raise ValueError("FLATTEN_ALL requires a separate explicit action contract")


class EntryHaltLatch:
    """Monotonic Phase-2 latch used by the central Risk Gate to block entries."""

    def __init__(self) -> None:
        self._halted = False

    @property
    def halted(self) -> bool:
        return self._halted

    @property
    def entries_allowed(self) -> bool:
        return not self._halted

    def halt(self) -> None:
        self._halted = True


class _AuditSink(Protocol):
    def write(self, event_type: str, payload: dict[str, object]) -> None: ...


class _StateMachine(Protocol):
    @property
    def state(self) -> LiveState: ...

    def transition(
        self,
        target: LiveState,
        *,
        reason: TransitionReason,
        arm_authority: object | None = None,
    ) -> LiveState: ...


class EmergencyStopController:
    """Audit-before-mutation orchestration for ADR-010 semantics."""

    def __init__(
        self,
        *,
        audit_sink: _AuditSink,
        state_machine: _StateMachine,
        entry_halt: EntryHaltLatch,
    ) -> None:
        if not callable(getattr(audit_sink, "write", None)):
            raise TypeError("audit_sink must provide write(event_type, payload)")
        if not callable(getattr(state_machine, "transition", None)):
            raise TypeError("state_machine must provide transition(...)")
        if not isinstance(entry_halt, EntryHaltLatch):
            raise TypeError("entry_halt must be EntryHaltLatch")
        self._audit_sink = audit_sink
        self._state_machine = state_machine
        self._entry_halt = entry_halt

    def emergency_stop(
        self,
        *,
        scope: KillSwitchScope,
        reason: str,
    ) -> KillSwitchEvidence:
        scope = self._scope(scope)
        reason = _text(reason, "reason")
        actions = (
            KillSwitchAction.HALT_ENTRIES,
            KillSwitchAction.CANCEL_PENDING,
        )
        evidence = KillSwitchEvidence(
            scope=scope,
            reason=reason,
            actions=actions,
            cancel_pending_scope=CancelPendingScope.ENTRY_ORDERS_ONLY,
            protective_exits_active=True,
            reconciliation_active=True,
            alert_required=True,
            recovery_required=True,
        )

        self._write_audit(
            "EMERGENCY_STOP_REQUESTED",
            {
                "scope": scope.value,
                "reason": reason,
                "actions": tuple(action.value for action in actions),
                "cancel_pending_scope": CancelPendingScope.ENTRY_ORDERS_ONLY.value,
                "protective_exits_active": True,
                "reconciliation_active": True,
                "flatten_all": False,
            },
        )

        try:
            self._state_machine.transition(
                LiveState.EMERGENCY_STOP,
                reason=TransitionReason.EMERGENCY_STOP,
            )
        except LiveStateTransitionError as error:
            raise KillSwitchError(
                "live state transition failed; kill-switch mutation blocked"
            ) from error

        self._entry_halt.halt()
        return evidence

    def reconciliation_mismatch(
        self,
        *,
        scope: KillSwitchScope,
        reason: str,
    ) -> KillSwitchEvidence:
        scope = self._scope(scope)
        reason = _text(reason, "reason")
        evidence = KillSwitchEvidence(
            scope=scope,
            reason=reason,
            actions=(KillSwitchAction.HALT_ENTRIES,),
            cancel_pending_scope=None,
            protective_exits_active=True,
            reconciliation_active=True,
            alert_required=True,
            recovery_required=True,
        )

        self._write_audit(
            "RECONCILIATION_MISMATCH_HALT",
            {
                "scope": scope.value,
                "reason": reason,
                "actions": (KillSwitchAction.HALT_ENTRIES.value,),
                "alert_required": True,
                "recovery_required": True,
                "reconciliation_active": True,
                "flatten_all": False,
            },
        )
        self._entry_halt.halt()
        return evidence

    @staticmethod
    def _scope(value: KillSwitchScope) -> KillSwitchScope:
        if not isinstance(value, KillSwitchScope):
            raise TypeError("scope must be KillSwitchScope")
        return value

    def _write_audit(self, event_type: str, payload: dict[str, object]) -> None:
        try:
            self._audit_sink.write(event_type, dict(payload))
        except Exception as error:
            raise KillSwitchError(
                "audit write failed; kill-switch mutation blocked"
            ) from error


__all__ = [
    "KillSwitchError",
    "KillSwitchAction",
    "KillSwitchScope",
    "CancelPendingScope",
    "KillSwitchEvidence",
    "EntryHaltLatch",
    "EmergencyStopController",
]
