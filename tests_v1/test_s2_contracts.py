from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone
from uuid import uuid4

import pytest


def test_device_session_gate_status_set_is_exact() -> None:
    from dashboard.backend.account_v2.contracts import DeviceSessionGateStatus

    assert {item.value for item in DeviceSessionGateStatus} == {
        "VALID",
        "REVOKED",
        "SESSION_EXPIRED",
        "DEVICE_UNTRUSTED",
        "RECOVERY_REQUIRED",
        "AUTHORITY_UNAVAILABLE",
    }


def test_local_safety_only_is_runtime_mode_not_gate_status() -> None:
    from dashboard.backend.account_v2.contracts import AccountRuntimeMode, DeviceSessionGateStatus

    assert AccountRuntimeMode.LOCAL_SAFETY_ONLY.value == "LOCAL_SAFETY_ONLY"
    assert "LOCAL_SAFETY_ONLY" not in {item.value for item in DeviceSessionGateStatus}


def test_device_session_gate_result_is_immutable_and_has_no_trading_authority() -> None:
    from dashboard.backend.account_v2.contracts import DeviceSessionGateResult, DeviceSessionGateStatus

    result = DeviceSessionGateResult(
        schema_version="s2-gate/v1",
        user_id=uuid4(),
        device_id="device-1",
        session_family_id="family-1",
        status=DeviceSessionGateStatus.VALID,
        reasons=("ACCOUNT_DEVICE_SESSION_VALID",),
        authority_evidence_ref="authority-evidence-1",
        evaluated_at=datetime(2026, 9, 26, tzinfo=timezone.utc),
        audit_ref="audit-1",
    )

    names = {field.name for field in fields(result)}
    forbidden = {
        "armed",
        "arm",
        "can_trade",
        "trade_allowed",
        "approved_order",
        "broker_order",
        "place_order",
        "submit_order",
        "cancel_order",
        "modify_order",
    }
    assert names.isdisjoint(forbidden)

    with pytest.raises(FrozenInstanceError):
        result.status = DeviceSessionGateStatus.REVOKED  # type: ignore[misc]


def test_policy_seam_contracts_require_explicit_identity_and_time_evidence() -> None:
    from dashboard.backend.account_v2.contracts import (
        EntitlementTimeEvidence,
        ProductionIdentityPolicy,
        UpdateSafeWindowPolicyRef,
    )

    assert {field.name for field in fields(UpdateSafeWindowPolicyRef)} == {
        "policy_id",
        "version",
    }
    assert {field.name for field in fields(EntitlementTimeEvidence)} == {
        "server_issued_at",
        "last_successful_server_check_in",
        "lease_expires_at",
        "monotonic_anchor",
        "monotonic_elapsed_seconds",
        "boot_session_id",
    }
    assert {field.name for field in fields(ProductionIdentityPolicy)} == {
        "rp_id",
        "origin",
        "environment",
        "production_migration_required",
    }
