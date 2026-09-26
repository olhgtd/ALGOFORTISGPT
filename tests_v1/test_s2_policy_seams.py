from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dashboard.backend.account_v2.contracts import EntitlementTimeEvidence
from dashboard.backend.account_v2.policy_seams import (
    PolicyViolation,
    ProductionIdentityMigration,
    TelemetryPrivacyPolicy,
    UpdateSafeWindowPolicy,
    evaluate_entitlement_time,
    evaluate_update_safe_window,
)


def _time(hour: int) -> datetime:
    return datetime(2026, 9, 26, hour, 0, tzinfo=timezone.utc)


def test_update_safe_window_has_no_production_time_defaults_and_missing_policy_defers() -> None:
    decision = evaluate_update_safe_window(None, engine_state="IDLE", has_open_positions=False)
    assert decision.allowed is False
    assert decision.reason == "UPDATE_POLICY_UNAVAILABLE"

    with pytest.raises(TypeError):
        UpdateSafeWindowPolicy()  # type: ignore[call-arg]


def test_invalid_or_inapplicable_update_policy_defers_closed() -> None:
    invalid = UpdateSafeWindowPolicy(
        policy_id="",
        version="",
        allowed_engine_states=("IDLE",),
        allow_open_positions=False,
        session_calendar_ref="",
        applicability="APPLICABLE",
    )
    decision = evaluate_update_safe_window(invalid, engine_state="IDLE", has_open_positions=False)
    assert decision.allowed is False
    assert decision.reason == "UPDATE_POLICY_INVALID"

    inapplicable = UpdateSafeWindowPolicy(
        policy_id="updates/v1",
        version="1",
        allowed_engine_states=("IDLE",),
        allow_open_positions=False,
        session_calendar_ref="calendar/nse/v1",
        applicability="NOT_APPLICABLE",
    )
    decision = evaluate_update_safe_window(inapplicable, engine_state="IDLE", has_open_positions=False)
    assert decision.allowed is False
    assert decision.reason == "UPDATE_POLICY_NOT_APPLICABLE"


def test_wall_clock_rollback_cannot_extend_entitlement_lease() -> None:
    evidence = EntitlementTimeEvidence(
        server_issued_at=_time(10),
        last_successful_server_check_in=_time(10),
        lease_expires_at=_time(11),
        monotonic_anchor=100.0,
        monotonic_elapsed_seconds=7200.0,
        boot_session_id="boot-1",
    )

    decision = evaluate_entitlement_time(evidence, observed_wall_time=_time(9))

    assert decision.status == "ENTITLEMENT_TIME_UNCERTAIN"
    assert decision.entitlement_dependent_new_operation_allowed is False
    assert decision.protective_safety_allowed is True


def test_missing_monotonic_evidence_fails_closed_but_preserves_protective_safety() -> None:
    evidence = EntitlementTimeEvidence(
        server_issued_at=_time(10),
        last_successful_server_check_in=_time(10),
        lease_expires_at=_time(18),
        monotonic_anchor=None,
        monotonic_elapsed_seconds=None,
        boot_session_id=None,
    )

    decision = evaluate_entitlement_time(evidence, observed_wall_time=_time(12))

    assert decision.status == "ENTITLEMENT_TIME_UNCERTAIN"
    assert decision.entitlement_dependent_new_operation_allowed is False
    assert decision.protective_safety_allowed is True


def test_telemetry_policy_rejects_forbidden_data_classes() -> None:
    with pytest.raises(PolicyViolation):
        TelemetryPrivacyPolicy(
            policy_id="telemetry/privacy/v1",
            version="1",
            opt_in=True,
            allowed_data_classes=frozenset({"crash_metadata", "broker_credentials"}),
        )


def test_production_identity_migration_never_promotes_dev_credentials() -> None:
    migration = ProductionIdentityMigration(
        publisher="PENDING_EXTERNAL",
        production_domain="PENDING_EXTERNAL",
        production_rp_id="PENDING_EXTERNAL",
    )

    assert migration.can_promote_existing_webauthn(source_environment="development") is False
    assert migration.requires_fresh_production_webauthn is True
    assert migration.requires_device_reproof is True
