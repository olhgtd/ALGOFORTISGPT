import pytest

from dashboard.backend.product_ops_v2.read_models import build_health


def test_health_read_model_is_deterministic_minimized_and_includes_runbook_state():
    health = build_health(
        incidents=2,
        alert_health="DEGRADED",
        request_counts={"IN_PROGRESS": 1, "RECEIVED": 3},
        stale_policy_count=1,
        backup_status="PASS",
        restore_status="PASS",
        rollback_status="PASS",
        runbook_status="PASS",
        active_policy_versions=("privacy-notice/1.0.0", "retention/account/v1"),
    )
    assert health.privacy_requests == (("IN_PROGRESS", 1), ("RECEIVED", 3))
    assert health.active_policy_versions == ("privacy-notice/1.0.0", "retention/account/v1")
    assert health.runbook_status == "PASS"
    assert not hasattr(health, "user_id")
    assert not hasattr(health, "account_number")
    assert not hasattr(health, "raw_payload")


def test_health_read_model_rejects_negative_counts():
    with pytest.raises(ValueError, match="non-negative"):
        build_health(
            incidents=-1,
            alert_health="OK",
            request_counts={},
            stale_policy_count=0,
            backup_status="PASS",
            restore_status="PASS",
            rollback_status="PASS",
            runbook_status="PASS",
            active_policy_versions=(),
        )
