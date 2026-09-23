from __future__ import annotations

from dataclasses import dataclass

import pytest

from engine.live.state_machine_v2 import (
    LiveState,
    LiveStateMachine,
    LiveStateTransitionError,
    TransitionReason,
)


class _AuditSink:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[tuple[str, dict[str, object]]] = []

    def write(self, event_type: str, payload: dict[str, object]) -> None:
        if self.fail:
            raise RuntimeError("audit unavailable")
        self.events.append((event_type, dict(payload)))


@dataclass(frozen=True, slots=True)
class _ArmAuthority:
    allowed: bool
    reference: str = "arm-ref"


def test_state_machine_starts_disabled_and_never_active() -> None:
    machine = LiveStateMachine(audit_sink=_AuditSink())

    assert machine.state is LiveState.DISABLED
    assert machine.is_active is False


def test_canonical_safe_progression_requires_explicit_steps() -> None:
    audit = _AuditSink()
    machine = LiveStateMachine(audit_sink=audit)

    machine.transition(LiveState.READY, reason=TransitionReason.OWNER_ENABLE)
    machine.transition(LiveState.CONNECTING, reason=TransitionReason.CONNECT_REQUEST)

    assert machine.state is LiveState.CONNECTING
    assert [event[0] for event in audit.events] == [
        "LIVE_STATE_TRANSITION",
        "LIVE_STATE_TRANSITION",
    ]


def test_active_transition_requires_explicit_arm_authority() -> None:
    machine = LiveStateMachine(audit_sink=_AuditSink())
    machine.transition(LiveState.READY, reason=TransitionReason.OWNER_ENABLE)
    machine.transition(LiveState.CONNECTING, reason=TransitionReason.CONNECT_REQUEST)

    with pytest.raises(LiveStateTransitionError, match="arm"):
        machine.transition(LiveState.ACTIVE, reason=TransitionReason.ARM_REQUEST)

    assert machine.state is LiveState.CONNECTING


def test_phase2_runtime_can_disable_arm_even_with_authority_object() -> None:
    machine = LiveStateMachine(audit_sink=_AuditSink(), arm_enabled=False)
    machine.transition(LiveState.READY, reason=TransitionReason.OWNER_ENABLE)
    machine.transition(LiveState.CONNECTING, reason=TransitionReason.CONNECT_REQUEST)

    with pytest.raises(LiveStateTransitionError, match="disabled"):
        machine.transition(
            LiveState.ACTIVE,
            reason=TransitionReason.ARM_REQUEST,
            arm_authority=_ArmAuthority(True),
        )

    assert machine.state is LiveState.CONNECTING


def test_restart_never_auto_arms_live() -> None:
    machine = LiveStateMachine.restore_after_restart(
        previous_state=LiveState.ACTIVE,
        audit_sink=_AuditSink(),
    )

    assert machine.state is LiveState.RECOVERY
    assert machine.is_active is False


def test_crash_recovery_never_auto_arms_live() -> None:
    machine = LiveStateMachine.restore_after_crash(
        previous_state=LiveState.ACTIVE,
        audit_sink=_AuditSink(),
    )

    assert machine.state is LiveState.RECOVERY
    assert machine.is_active is False


def test_reconnect_from_degraded_does_not_jump_to_active() -> None:
    machine = LiveStateMachine(audit_sink=_AuditSink())
    machine.transition(LiveState.READY, reason=TransitionReason.OWNER_ENABLE)
    machine.transition(LiveState.CONNECTING, reason=TransitionReason.CONNECT_REQUEST)
    machine.transition(LiveState.DEGRADED, reason=TransitionReason.CONNECTIVITY_DEGRADED)

    with pytest.raises(LiveStateTransitionError):
        machine.transition(LiveState.ACTIVE, reason=TransitionReason.RECONNECT)

    assert machine.state is LiveState.DEGRADED


def test_emergency_stop_cannot_transition_directly_to_active() -> None:
    machine = LiveStateMachine(audit_sink=_AuditSink())
    machine.transition(LiveState.READY, reason=TransitionReason.OWNER_ENABLE)
    machine.transition(LiveState.EMERGENCY_STOP, reason=TransitionReason.EMERGENCY_STOP)

    with pytest.raises(LiveStateTransitionError):
        machine.transition(LiveState.ACTIVE, reason=TransitionReason.ARM_REQUEST, arm_authority=_ArmAuthority(True))

    assert machine.state is LiveState.EMERGENCY_STOP


def test_audit_failure_blocks_state_mutation() -> None:
    machine = LiveStateMachine(audit_sink=_AuditSink(fail=True))

    with pytest.raises(LiveStateTransitionError, match="audit"):
        machine.transition(LiveState.READY, reason=TransitionReason.OWNER_ENABLE)

    assert machine.state is LiveState.DISABLED


def test_representative_illegal_transition_fails_closed() -> None:
    machine = LiveStateMachine(audit_sink=_AuditSink())

    with pytest.raises(LiveStateTransitionError):
        machine.transition(LiveState.PAUSED, reason=TransitionReason.PAUSE_REQUEST)

    assert machine.state is LiveState.DISABLED
