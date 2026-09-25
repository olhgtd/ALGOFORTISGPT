from dataclasses import dataclass

import pytest

from engine.paper.contracts_v2 import PaperOperationalState
from engine.paper.operational_state_v2 import (
    PaperOperationalStateMachine,
    PaperStateTransitionError,
    PaperTransitionReason,
)


@dataclass(frozen=True)
class _Authority:
    allowed: bool
    reference: str


def test_continuity_failure_can_jump_healthy_directly_to_recovery():
    machine = PaperOperationalStateMachine()
    assert (
        machine.require_recovery(reason=PaperTransitionReason.PROCESS_CRASH)
        is PaperOperationalState.RECOVERY
    )


def test_halt_entries_is_action_that_produces_sticky_halted_state():
    machine = PaperOperationalStateMachine()
    assert (
        machine.halt_entries(reason=PaperTransitionReason.RECONCILIATION_MISMATCH)
        is PaperOperationalState.HALTED
    )
    with pytest.raises(PaperStateTransitionError, match="READY_FOR_RESUME"):
        machine.resume(
            authority=_Authority(True, "owner-1"),
            reason=PaperTransitionReason.MANUAL_RESUME,
        )
    assert machine.state is PaperOperationalState.HALTED


def test_recovery_must_be_marked_ready_before_manual_resume():
    machine = PaperOperationalStateMachine()
    machine.require_recovery(reason=PaperTransitionReason.RESTART_WITH_OPEN_STATE)
    machine.mark_ready_for_resume(reason=PaperTransitionReason.RECOVERY_CHECKS_CLEAN)
    assert machine.state is PaperOperationalState.READY_FOR_RESUME
    assert (
        machine.resume(
            authority=_Authority(True, "owner-resume-1"),
            reason=PaperTransitionReason.MANUAL_RESUME,
        )
        is PaperOperationalState.HEALTHY
    )


def test_denied_resume_authority_fails_closed_and_keeps_ready_state():
    machine = PaperOperationalStateMachine(
        initial_state=PaperOperationalState.READY_FOR_RESUME
    )
    with pytest.raises(PaperStateTransitionError, match="denied"):
        machine.resume(
            authority=_Authority(False, "owner-resume-denied"),
            reason=PaperTransitionReason.MANUAL_RESUME,
        )
    assert machine.state is PaperOperationalState.READY_FOR_RESUME


def test_blank_resume_authority_reference_is_rejected():
    machine = PaperOperationalStateMachine(
        initial_state=PaperOperationalState.READY_FOR_RESUME
    )
    with pytest.raises(PaperStateTransitionError, match="reference"):
        machine.resume(
            authority=_Authority(True, " "),
            reason=PaperTransitionReason.MANUAL_RESUME,
        )
    assert machine.state is PaperOperationalState.READY_FOR_RESUME


def test_transient_degradation_can_clear_only_when_no_sticky_halt_was_entered():
    machine = PaperOperationalStateMachine()
    machine.degrade(reason=PaperTransitionReason.TRANSIENT_FEED_LATENCY)
    assert (
        machine.clear_degradation(reason=PaperTransitionReason.DEGRADATION_CLEARED)
        is PaperOperationalState.HEALTHY
    )


def test_halted_can_escalate_to_recovery_without_auto_clear():
    machine = PaperOperationalStateMachine()
    machine.halt_entries(reason=PaperTransitionReason.CLOCK_UNHEALTHY)
    assert (
        machine.require_recovery(
            reason=PaperTransitionReason.STATE_CONTINUITY_UNCERTAIN
        )
        is PaperOperationalState.RECOVERY
    )


def test_failed_recovery_checks_can_return_recovery_to_halted():
    machine = PaperOperationalStateMachine(
        initial_state=PaperOperationalState.RECOVERY
    )
    assert (
        machine.halt_entries(reason=PaperTransitionReason.PROTECTIVE_INTEGRITY_FAILURE)
        is PaperOperationalState.HALTED
    )


def test_new_safety_failure_can_revoke_ready_for_resume():
    machine = PaperOperationalStateMachine(
        initial_state=PaperOperationalState.READY_FOR_RESUME
    )
    assert (
        machine.halt_entries(reason=PaperTransitionReason.STALE_FEED)
        is PaperOperationalState.HALTED
    )


def test_clear_degradation_is_illegal_from_halted():
    machine = PaperOperationalStateMachine(initial_state=PaperOperationalState.HALTED)
    with pytest.raises(PaperStateTransitionError, match="DEGRADED"):
        machine.clear_degradation(reason=PaperTransitionReason.DEGRADATION_CLEARED)
    assert machine.state is PaperOperationalState.HALTED


def test_resume_requires_manual_resume_reason():
    machine = PaperOperationalStateMachine(
        initial_state=PaperOperationalState.READY_FOR_RESUME
    )
    with pytest.raises(PaperStateTransitionError, match="MANUAL_RESUME"):
        machine.resume(
            authority=_Authority(True, "owner-resume-1"),
            reason=PaperTransitionReason.RECOVERY_CHECKS_CLEAN,
        )
    assert machine.state is PaperOperationalState.READY_FOR_RESUME
