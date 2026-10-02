"""Phase 10 S3 entitlement and telemetry qualification tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from dashboard.backend.account_v2.contracts import EntitlementTimeEvidence
from dashboard.backend.account_v2.policy_seams import TelemetryPrivacyPolicy
from dashboard.backend.entitlement_service import EntitlementLease, EntitlementLeaseManager
from dashboard.backend.telemetry_service import TelemetryService


class _LeaseSignatureVerifier:
    def verify(self, *, lease: EntitlementLease) -> bool:
        return (
            lease.signing_key_id == "entitlement-key-v1"
            and lease.lease_signature == "VALID_LEASE_SIGNATURE"
        )


def _lease(*, device_id: str = "dev-1") -> EntitlementLease:
    issued = datetime(2026, 10, 2, 4, 0, tzinfo=timezone.utc)
    expires = issued + timedelta(days=7)
    return EntitlementLease(
        lease_id="lease-1",
        user_id="user-1",
        device_id=device_id,
        tier="RESEARCH",
        capabilities=["BACKTEST", "PAPER"],
        issued_at=issued.timestamp(),
        expires_at=expires.timestamp(),
        max_observed_timestamp=issued.timestamp(),
        signing_key_id="entitlement-key-v1",
        lease_signature="VALID_LEASE_SIGNATURE",
    )


def _evidence(
    *,
    elapsed_seconds: float | None = 3600.0,
    boot_session_id: str | None = "boot-1",
    check_in_hour: int = 4,
) -> EntitlementTimeEvidence:
    issued = datetime(2026, 10, 2, 4, 0, tzinfo=timezone.utc)
    return EntitlementTimeEvidence(
        server_issued_at=issued,
        last_successful_server_check_in=datetime(
            2026, 10, 2, check_in_hour, 0, tzinfo=timezone.utc
        ),
        lease_expires_at=issued + timedelta(days=7),
        monotonic_anchor=100.0 if elapsed_seconds is not None else None,
        monotonic_elapsed_seconds=elapsed_seconds,
        boot_session_id=boot_session_id,
    )


def test_entitlement_requires_signature_verifier_and_time_evidence() -> None:
    lease = _lease()

    no_verifier = EntitlementLeaseManager()
    denied = no_verifier.validate_lease(
        lease,
        current_device_id="dev-1",
        time_evidence=_evidence(),
        observed_wall_time=datetime(2026, 10, 2, 5, 0, tzinfo=timezone.utc),
    )
    assert denied["valid"] is False
    assert denied["reason"] == "ENTITLEMENT_SIGNATURE_UNVERIFIED"
    assert denied["can_execute_risk_management"] is True
    assert denied["can_read_safety_state"] is True

    verifier = EntitlementLeaseManager(signature_verifier=_LeaseSignatureVerifier())
    with pytest.raises(TypeError):
        verifier.validate_lease(lease, current_device_id="dev-1")


def test_uncertain_time_fails_closed_for_new_operations_but_preserves_safety() -> None:
    manager = EntitlementLeaseManager(signature_verifier=_LeaseSignatureVerifier())
    decision = manager.validate_lease(
        _lease(),
        current_device_id="dev-1",
        time_evidence=_evidence(elapsed_seconds=None, boot_session_id=None),
        observed_wall_time=datetime(2026, 10, 2, 5, 0, tzinfo=timezone.utc),
    )

    assert decision["valid"] is False
    assert decision["reason"] == "ENTITLEMENT_TIME_UNCERTAIN"
    assert decision["entitlement_dependent_new_operation_allowed"] is False
    assert decision["can_execute_risk_management"] is True
    assert decision["can_read_safety_state"] is True


def test_device_mismatch_fails_closed_even_with_valid_time_and_signature() -> None:
    manager = EntitlementLeaseManager(signature_verifier=_LeaseSignatureVerifier())
    decision = manager.validate_lease(
        _lease(device_id="dev-expected"),
        current_device_id="dev-other",
        time_evidence=_evidence(),
        observed_wall_time=datetime(2026, 10, 2, 5, 0, tzinfo=timezone.utc),
    )

    assert decision["valid"] is False
    assert decision["reason"] == "DEVICE_MISMATCH"
    assert decision["can_execute_risk_management"] is True


def test_valid_signed_lease_uses_monotonic_server_time_evidence() -> None:
    manager = EntitlementLeaseManager(signature_verifier=_LeaseSignatureVerifier())
    decision = manager.validate_lease(
        _lease(),
        current_device_id="dev-1",
        time_evidence=_evidence(elapsed_seconds=3600.0),
        observed_wall_time=datetime(2026, 10, 2, 5, 0, tzinfo=timezone.utc),
    )

    assert decision["valid"] is True
    assert decision["reason"] == "ENTITLEMENT_TIME_VALID"
    assert decision["entitlement_dependent_new_operation_allowed"] is True
    assert decision["can_execute_risk_management"] is True


def test_telemetry_is_silent_without_explicit_opt_in_policy() -> None:
    service = TelemetryService(app_version="2.0.0")
    assert service.build_operational_heartbeat("READY", 128.0) is None

    opted_out = TelemetryService(
        app_version="2.0.0",
        privacy_policy=TelemetryPrivacyPolicy(
            policy_id="telemetry/privacy/v1",
            version="1",
            opt_in=False,
            allowed_data_classes=frozenset({"operational_health"}),
        ),
    )
    assert opted_out.build_operational_heartbeat("READY", 128.0) is None


def test_telemetry_requires_allowed_data_class_when_opted_in() -> None:
    policy = TelemetryPrivacyPolicy(
        policy_id="telemetry/privacy/v1",
        version="1",
        opt_in=True,
        allowed_data_classes=frozenset({"crash_metadata"}),
    )
    service = TelemetryService(app_version="2.0.0", privacy_policy=policy)
    assert service.build_operational_heartbeat("READY", 128.0) is None

    allowed = TelemetryService(
        app_version="2.0.0",
        privacy_policy=TelemetryPrivacyPolicy(
            policy_id="telemetry/privacy/v1",
            version="1",
            opt_in=True,
            allowed_data_classes=frozenset({"operational_health"}),
        ),
    )
    heartbeat = allowed.build_operational_heartbeat("READY", 128.0)
    assert heartbeat is not None
    assert heartbeat["app_version"] == "2.0.0"
    assert heartbeat["runtime_state"] == "READY"
    assert "strategy" not in heartbeat
    assert "orders" not in heartbeat


def test_support_bundle_remains_explicit_export_and_redacted() -> None:
    service = TelemetryService(app_version="2.0.0")
    bundle = service.generate_support_bundle(
        ["Bearer SECRET_TOKEN from 192.168.1.50"],
        {"path": r"C:\Users\Alice\AlgoFortis"},
    )

    serialized = str(bundle)
    assert "SECRET_TOKEN" not in serialized
    assert "192.168.1.50" not in serialized
    assert "Alice" not in serialized
    assert bundle["manifest"]["redaction_applied"] is True
