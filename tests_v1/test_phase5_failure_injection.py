from __future__ import annotations

import pytest

from engine.paper.contracts_v2 import PaperOperationalState
from engine.paper.failure_injection_v2 import REQUIRED_FI_IDS, run_failure_fixture

EXPECTED_FINAL_STATE = {
    "FI-01": PaperOperationalState.RECOVERY,
    "FI-02": PaperOperationalState.READY_FOR_RESUME,
    "FI-03": PaperOperationalState.HALTED,
    "FI-04": PaperOperationalState.HALTED,
    "FI-05": PaperOperationalState.READY_FOR_RESUME,
    "FI-06": PaperOperationalState.HALTED,
    "FI-07": PaperOperationalState.HALTED,
    "FI-08": PaperOperationalState.HALTED,
    "FI-09": PaperOperationalState.READY_FOR_RESUME,
    "FI-12": PaperOperationalState.HALTED,
    "FI-13": PaperOperationalState.RECOVERY,
    "FI-14": PaperOperationalState.HALTED,
    "FI-23": PaperOperationalState.READY_FOR_RESUME,
    "FI-24": PaperOperationalState.HALTED,
}


def test_required_failure_injection_catalog_is_exact():
    assert REQUIRED_FI_IDS == tuple(EXPECTED_FINAL_STATE)


@pytest.mark.parametrize("fi_id", tuple(EXPECTED_FINAL_STATE))
def test_required_phase5_failure_injection_case(fi_id: str):
    result = run_failure_fixture(fi_id)

    assert result.passed is True
    assert result.final_state is EXPECTED_FINAL_STATE[fi_id]
    assert result.duplicate_order_count == 0
    assert result.stale_replay_count == 0
    assert result.unresolved_mismatch_count == 0
    assert result.live_arm_allowed is False


def test_fi01_uncertain_submission_never_retries_before_recovery():
    result = run_failure_fixture("FI-01")
    assert result.recovery_required is True
    assert result.retry_allowed is False
    assert result.logical_submission_attempts == 1


def test_fi02_open_position_recovery_checks_protective_state_before_ready():
    result = run_failure_fixture("FI-02")
    assert result.reconciliation_result == "CLEAN"
    assert result.protective_integrity_result == "VALID"
    assert result.manual_resume_required is True


def test_fi05_reconnect_does_not_restore_entry_permission_without_clean_reconciliation():
    result = run_failure_fixture("FI-05")
    assert result.reconciliation_result == "CLEAN"
    assert result.reconnect_alone_resumed is False
    assert result.manual_resume_required is True


def test_fi09_partial_fill_disconnect_converges_without_duplicate_submission():
    result = run_failure_fixture("FI-09")
    assert result.reconciliation_result == "CLEAN"
    assert result.logical_submission_attempts == 1
    assert result.duplicate_order_count == 0


def test_fi23_rollover_invalidates_stale_entry_and_requires_manual_resume():
    result = run_failure_fixture("FI-23")
    assert result.invalidated_stale_intents == 1
    assert result.stale_replay_count == 0
    assert result.manual_resume_required is True


def test_fi24_one_notifier_failure_does_not_suppress_other_attempt():
    result = run_failure_fixture("FI-24")
    assert result.alert_attempts == ("windows_local", "telegram")
    assert result.alert_failures == ("telegram",)
    assert result.local_persistent_warning is True
