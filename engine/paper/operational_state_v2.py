"""Pure Phase-5 paper operational-state authority.

`HALT_ENTRIES` is represented by :meth:`halt_entries`; `HALTED` is the
resulting sticky state.  The machine has no broker, persistence, notifier,
Windows, or Live dependency and cannot arm Live.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol

from engine.paper.contracts_v2 import PaperOperationalState


class PaperTransitionReason(str, Enum):
    PROCESS_CRASH = "PROCESS_CRASH"
    RESTART_WITH_OPEN_STATE = "RESTART_WITH_OPEN_STATE"
    SLEEP_RESUME_DISCONTINUITY = "SLEEP_RESUME_DISCONTINUITY"
    UNCERTAIN_ACKNOWLEDGEMENT = "UNCERTAIN_ACKNOWLEDGEMENT"
    PARTIAL_STATE_UNCERTAINTY = "PARTIAL_STATE_UNCERTAINTY"
    STATE_CONTINUITY_UNCERTAIN = "STATE_CONTINUITY_UNCERTAIN"
    TRANSIENT_FEED_LATENCY = "TRANSIENT_FEED_LATENCY"
    DEGRADATION_CLEARED = "DEGRADATION_CLEARED"
    RECONCILIATION_MISMATCH = "RECONCILIATION_MISMATCH"
    PROTECTIVE_INTEGRITY_FAILURE = "PROTECTIVE_INTEGRITY_FAILURE"
    CLOCK_UNHEALTHY = "CLOCK_UNHEALTHY"
    STALE_FEED = "STALE_FEED"
    STORM_THRESHOLD_CROSSED = "STORM_THRESHOLD_CROSSED"
    RISK_SNAPSHOT_BUILDER_UNHEALTHY = "RISK_SNAPSHOT_BUILDER_UNHEALTHY"
    RISK_SNAPSHOT_STALE = "RISK_SNAPSHOT_STALE"
    RISK_SNAPSHOT_CONTINUITY_UNCERTAIN = "RISK_SNAPSHOT_CONTINUITY_UNCERTAIN"
    RECOVERY_CHECKS_CLEAN = "RECOVERY_CHECKS_CLEAN"
    MANUAL_RESUME = "MANUAL_RESUME"


class PaperStateTransitionError(RuntimeError):
    """Raised when a paper operational-state transition cannot be proven safe."""


class ManualResumeAuthority(Protocol):
    allowed: bool
    reference: str


class PaperOperationalStateMachine:
    """Closed, action-oriented Phase-5 paper safety state machine."""

    def __init__(
        self,
        *,
        initial_state: PaperOperationalState = PaperOperationalState.HEALTHY,
    ) -> None:
        if not isinstance(initial_state, PaperOperationalState):
            raise TypeError("initial_state must be PaperOperationalState")
        self._state = initial_state

    @property
    def state(self) -> PaperOperationalState:
        return self._state

    def degrade(self, *, reason: PaperTransitionReason) -> PaperOperationalState:
        self._require_reason(reason)
        if self._state is not PaperOperationalState.HEALTHY:
            raise PaperStateTransitionError("DEGRADED requires current state HEALTHY")
        return self._commit(PaperOperationalState.DEGRADED)

    def clear_degradation(
        self, *, reason: PaperTransitionReason
    ) -> PaperOperationalState:
        self._require_reason(reason)
        if reason is not PaperTransitionReason.DEGRADATION_CLEARED:
            raise PaperStateTransitionError(
                "clearing DEGRADED requires DEGRADATION_CLEARED reason"
            )
        if self._state is not PaperOperationalState.DEGRADED:
            raise PaperStateTransitionError(
                "DEGRADATION_CLEARED requires current state DEGRADED"
            )
        return self._commit(PaperOperationalState.HEALTHY)

    def halt_entries(self, *, reason: PaperTransitionReason) -> PaperOperationalState:
        self._require_reason(reason)
        allowed_from = {
            PaperOperationalState.HEALTHY,
            PaperOperationalState.DEGRADED,
            PaperOperationalState.RECOVERY,
            PaperOperationalState.READY_FOR_RESUME,
        }
        if self._state not in allowed_from:
            raise PaperStateTransitionError(
                f"HALT_ENTRIES is not allowed from {self._state.value}"
            )
        return self._commit(PaperOperationalState.HALTED)

    def require_recovery(
        self, *, reason: PaperTransitionReason
    ) -> PaperOperationalState:
        self._require_reason(reason)
        allowed_from = {
            PaperOperationalState.HEALTHY,
            PaperOperationalState.DEGRADED,
            PaperOperationalState.HALTED,
            PaperOperationalState.READY_FOR_RESUME,
        }
        if self._state not in allowed_from:
            raise PaperStateTransitionError(
                f"RECOVERY is not allowed from {self._state.value}"
            )
        return self._commit(PaperOperationalState.RECOVERY)

    def mark_ready_for_resume(
        self, *, reason: PaperTransitionReason
    ) -> PaperOperationalState:
        self._require_reason(reason)
        if reason is not PaperTransitionReason.RECOVERY_CHECKS_CLEAN:
            raise PaperStateTransitionError(
                "READY_FOR_RESUME requires RECOVERY_CHECKS_CLEAN reason"
            )
        if self._state not in {
            PaperOperationalState.RECOVERY,
            PaperOperationalState.HALTED,
        }:
            raise PaperStateTransitionError(
                "READY_FOR_RESUME requires current state RECOVERY or HALTED"
            )
        return self._commit(PaperOperationalState.READY_FOR_RESUME)

    def resume(
        self,
        *,
        authority: ManualResumeAuthority,
        reason: PaperTransitionReason,
    ) -> PaperOperationalState:
        self._require_reason(reason)
        if self._state is not PaperOperationalState.READY_FOR_RESUME:
            raise PaperStateTransitionError(
                "manual resume requires current state READY_FOR_RESUME"
            )
        if reason is not PaperTransitionReason.MANUAL_RESUME:
            raise PaperStateTransitionError(
                "resume requires MANUAL_RESUME transition reason"
            )
        if authority is None or getattr(authority, "allowed", None) is not True:
            raise PaperStateTransitionError("manual resume authority denied")
        reference = getattr(authority, "reference", None)
        if not isinstance(reference, str) or not reference.strip():
            raise PaperStateTransitionError(
                "manual resume authority reference is required"
            )
        return self._commit(PaperOperationalState.HEALTHY)

    @staticmethod
    def _require_reason(reason: PaperTransitionReason) -> None:
        if not isinstance(reason, PaperTransitionReason):
            raise TypeError("reason must be PaperTransitionReason")

    def _commit(self, target: PaperOperationalState) -> PaperOperationalState:
        self._state = target
        return self._state


__all__ = [
    "ManualResumeAuthority",
    "PaperOperationalStateMachine",
    "PaperStateTransitionError",
    "PaperTransitionReason",
]
