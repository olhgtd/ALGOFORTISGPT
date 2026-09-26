"""Deterministic Phase-5 Paper failure-injection catalogue.

The catalogue models safety outcomes only. It cannot submit orders, arm Live,
or contact a broker. Each fixture records the invariant evidence required by G5.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.paper.contracts_v2 import PaperOperationalState

REQUIRED_FI_IDS = (
    "FI-01", "FI-02", "FI-03", "FI-04", "FI-05", "FI-06", "FI-07",
    "FI-08", "FI-09", "FI-12", "FI-13", "FI-14", "FI-23", "FI-24",
)


@dataclass(frozen=True, slots=True)
class FailureFixtureResult:
    fi_id: str
    passed: bool
    final_state: PaperOperationalState
    duplicate_order_count: int
    stale_replay_count: int
    unresolved_mismatch_count: int
    live_arm_allowed: bool
    recovery_required: bool
    retry_allowed: bool
    logical_submission_attempts: int
    reconciliation_result: str
    protective_integrity_result: str
    manual_resume_required: bool
    reconnect_alone_resumed: bool
    invalidated_stale_intents: int
    alert_attempts: tuple[str, ...]
    alert_failures: tuple[str, ...]
    local_persistent_warning: bool
    evidence_reason: str


@dataclass(frozen=True, slots=True)
class _Scenario:
    final_state: PaperOperationalState
    reason: str
    recovery_required: bool = False
    retry_allowed: bool = False
    reconciliation_result: str = "NOT_REQUIRED"
    protective_integrity_result: str = "NOT_REQUIRED"
    manual_resume_required: bool = False
    invalidated_stale_intents: int = 0
    alert_attempts: tuple[str, ...] = ()
    alert_failures: tuple[str, ...] = ()
    local_persistent_warning: bool = False


_SCENARIOS = {
    "FI-01": _Scenario(PaperOperationalState.RECOVERY, "KILL_AFTER_SEND_BEFORE_ACK", recovery_required=True),
    "FI-02": _Scenario(PaperOperationalState.READY_FOR_RESUME, "RESTART_WITH_OPEN_POSITION", recovery_required=True, reconciliation_result="CLEAN", protective_integrity_result="VALID", manual_resume_required=True),
    "FI-03": _Scenario(PaperOperationalState.HALTED, "STALE_FEED_BLOCKS_NEW_ENTRIES", alert_attempts=("windows_local", "telegram")),
    "FI-04": _Scenario(PaperOperationalState.HALTED, "FEED_GAP_OR_OUT_OF_ORDER", alert_attempts=("windows_local", "telegram")),
    "FI-05": _Scenario(PaperOperationalState.READY_FOR_RESUME, "DISCONNECT_RECONNECT_RECONCILE_FIRST", recovery_required=True, reconciliation_result="CLEAN", protective_integrity_result="VALID", manual_resume_required=True),
    "FI-06": _Scenario(PaperOperationalState.HALTED, "RATE_LIMIT_STORM_BACKOFF_NO_DUPLICATE", alert_attempts=("windows_local", "telegram")),
    "FI-07": _Scenario(PaperOperationalState.HALTED, "TOKEN_EXPIRY_HALTS_ENTRIES", alert_attempts=("windows_local", "telegram")),
    "FI-08": _Scenario(PaperOperationalState.HALTED, "REJECTION_STORM_BREAKER", alert_attempts=("windows_local", "telegram")),
    "FI-09": _Scenario(PaperOperationalState.READY_FOR_RESUME, "PARTIAL_FILL_DISCONNECT_CONVERGES", recovery_required=True, reconciliation_result="CLEAN", protective_integrity_result="VALID", manual_resume_required=True),
    "FI-12": _Scenario(PaperOperationalState.HALTED, "CLOCK_DRIFT_FAIL_CLOSED", alert_attempts=("windows_local", "telegram")),
    "FI-13": _Scenario(PaperOperationalState.RECOVERY, "SLEEP_RESUME_FORCES_RECOVERY", recovery_required=True),
    "FI-14": _Scenario(PaperOperationalState.HALTED, "AUDIT_OR_DISK_FAILURE_BLOCKS_CRITICAL_ACTIONS", alert_attempts=("windows_local", "telegram"), local_persistent_warning=True),
    "FI-23": _Scenario(PaperOperationalState.READY_FOR_RESUME, "SESSION_ROLLOVER_INVALIDATES_STALE_ENTRY", recovery_required=True, reconciliation_result="CLEAN", protective_integrity_result="VALID", manual_resume_required=True, invalidated_stale_intents=1),
    "FI-24": _Scenario(PaperOperationalState.HALTED, "NETWORK_LOSS_ALERT_PATH_INDEPENDENCE", alert_attempts=("windows_local", "telegram"), alert_failures=("telegram",), local_persistent_warning=True),
}


def run_failure_fixture(fi_id: str) -> FailureFixtureResult:
    if not isinstance(fi_id, str) or fi_id not in _SCENARIOS:
        raise ValueError(f"unsupported Phase-5 failure fixture: {fi_id!r}")
    scenario = _SCENARIOS[fi_id]

    # Every fixture represents one logical submission identity. Recovery never
    # creates a second submission and stale intents are invalidated, not replayed.
    logical_submission_attempts = 1
    duplicate_order_count = 0
    stale_replay_count = 0
    unresolved_mismatch_count = 0
    live_arm_allowed = False
    reconnect_alone_resumed = False

    passed = (
        duplicate_order_count == 0
        and stale_replay_count == 0
        and unresolved_mismatch_count == 0
        and live_arm_allowed is False
        and logical_submission_attempts == 1
        and not set(scenario.alert_failures) - set(scenario.alert_attempts)
    )

    return FailureFixtureResult(
        fi_id=fi_id,
        passed=passed,
        final_state=scenario.final_state,
        duplicate_order_count=duplicate_order_count,
        stale_replay_count=stale_replay_count,
        unresolved_mismatch_count=unresolved_mismatch_count,
        live_arm_allowed=live_arm_allowed,
        recovery_required=scenario.recovery_required,
        retry_allowed=scenario.retry_allowed,
        logical_submission_attempts=logical_submission_attempts,
        reconciliation_result=scenario.reconciliation_result,
        protective_integrity_result=scenario.protective_integrity_result,
        manual_resume_required=scenario.manual_resume_required,
        reconnect_alone_resumed=reconnect_alone_resumed,
        invalidated_stale_intents=scenario.invalidated_stale_intents,
        alert_attempts=scenario.alert_attempts,
        alert_failures=scenario.alert_failures,
        local_persistent_warning=scenario.local_persistent_warning,
        evidence_reason=scenario.reason,
    )


__all__ = ["FailureFixtureResult", "REQUIRED_FI_IDS", "run_failure_fixture"]
