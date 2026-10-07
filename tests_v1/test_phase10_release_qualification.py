"""Phase 10 release qualification against the current V2 S3 contracts.

These tests preserve the valuable qualification intent from PR #31 without
replacing the stronger implementations already present on current main.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dashboard.backend.account_v2.contracts import EntitlementTimeEvidence
from dashboard.backend.account_v2.policy_seams import TelemetryPrivacyPolicy
from dashboard.backend.entitlement_service import EntitlementLease, EntitlementLeaseManager
from dashboard.backend.telemetry_service import TelemetryService
from dashboard.backend.update_service import UpdateChannel, UpdateService

ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "build" / "tools" / "build_installer.ps1"

_KEY = b"algofortis-phase10-test-only"
_KEY_ID = "PHASE10_TEST_RELEASE_KEY"
_INSTALLER_SIGNER = "PHASE10_TEST_INSTALLER_SIGNER"
_THUMBPRINT = "A" * 40


def _sign(payload: bytes, key_id: str) -> str:
    return hmac.new(_KEY + key_id.encode(), payload, hashlib.sha256).hexdigest()


def _verify(payload: bytes, signature: str, key_id: str) -> bool:
    return hmac.compare_digest(_sign(payload, key_id), signature)


def _manifest(installer: bytes) -> str:
    data = {
        "version": "9.1.0",
        "channel": "STABLE",
        "installer_url": "https://updates.example.invalid/AlgoFortis-Setup-9.1.0.exe",
        "sha256_checksum": hashlib.sha256(installer).hexdigest(),
        "min_compatible_version": "9.0.0",
        "security_critical": True,
        "release_notes": "Phase 10 qualification fixture.",
        "signing_key_id": _KEY_ID,
        "installer_signer_id": _INSTALLER_SIGNER,
        "installer_signature": _sign(installer, _INSTALLER_SIGNER),
        "installer_authenticode_thumbprint": _THUMBPRINT,
        "safe_window_policy_id": "updates/safe-window/test-v1",
        "safe_window_policy_version": "1",
    }
    data["manifest_signature"] = _sign(
        UpdateService.canonical_manifest_bytes(data), _KEY_ID
    )
    return json.dumps(data)


def _update_service() -> UpdateService:
    return UpdateService(
        current_version="9.0.0",
        channel=UpdateChannel.STABLE,
        manifest_signature_verifier=_verify,
        installer_signature_verifier=_verify,
        authenticode_verifier=lambda _payload, thumbprint: thumbprint == _THUMBPRINT,
    )


def _lease() -> EntitlementLease:
    issued = datetime(2026, 10, 2, 4, tzinfo=timezone.utc)
    return EntitlementLease(
        lease_id="phase10-lease",
        user_id="user-1",
        device_id="device-1",
        tier="RESEARCH",
        capabilities=["BACKTEST", "PAPER"],
        issued_at=issued.timestamp(),
        expires_at=(issued + timedelta(days=7)).timestamp(),
        max_observed_timestamp=issued.timestamp(),
        signing_key_id="PHASE10_ENTITLEMENT_KEY",
        signature="VALID",
    )


def _lease_verify(payload: bytes, signature: str, key_id: str) -> bool:
    return bool(payload) and key_id == "PHASE10_ENTITLEMENT_KEY" and signature == "VALID"


def _time_evidence() -> EntitlementTimeEvidence:
    issued = datetime(2026, 10, 2, 4, tzinfo=timezone.utc)
    return EntitlementTimeEvidence(
        server_issued_at=issued,
        last_successful_server_check_in=issued,
        lease_expires_at=issued + timedelta(days=7),
        monotonic_anchor=100.0,
        monotonic_elapsed_seconds=3600.0,
        boot_session_id="phase10-boot",
    )


def test_signed_update_and_installer_integrity_are_fail_closed() -> None:
    installer = b"PHASE10-INSTALLER"
    service = _update_service()
    manifest = service.parse_and_validate_manifest(_manifest(installer))

    assert service.verify_installer_payload(installer, manifest) is True

    with pytest.raises(ValueError, match="INTEGRITY ERROR"):
        service.verify_installer_payload(b"TAMPERED", manifest)

    tampered = json.loads(_manifest(installer))
    tampered["version"] = "9.1.1"
    with pytest.raises(ValueError, match="UPDATE_MANIFEST_SIGNATURE_INVALID"):
        service.parse_and_validate_manifest(json.dumps(tampered))


def test_entitlement_requires_trusted_signature_device_and_time_evidence() -> None:
    manager = EntitlementLeaseManager(lease_signature_verifier=_lease_verify)
    lease = _lease()

    valid = manager.validate_lease(
        lease,
        current_device_id="device-1",
        time_evidence=_time_evidence(),
        observed_wall_time=datetime(2026, 10, 2, 5, tzinfo=timezone.utc),
    )
    assert valid["valid"] is True

    mismatch = manager.validate_lease(
        lease,
        current_device_id="other-device",
        time_evidence=_time_evidence(),
        observed_wall_time=datetime(2026, 10, 2, 5, tzinfo=timezone.utc),
    )
    assert mismatch["valid"] is False
    assert mismatch["reason"] == "DEVICE_MISMATCH"
    assert mismatch["can_execute_risk_management"] is True

    uncertain = manager.validate_lease(
        lease,
        current_device_id="device-1",
        time_evidence=None,
        observed_wall_time=datetime(2026, 10, 2, 5, tzinfo=timezone.utc),
    )
    assert uncertain["valid"] is False
    assert uncertain["reason"] == "ENTITLEMENT_TIME_UNCERTAIN"
    assert uncertain["can_execute_risk_management"] is True


def test_telemetry_is_deny_by_default_and_allowlisted_when_opted_in() -> None:
    service = TelemetryService(app_version="9.0.0")
    with pytest.raises(PermissionError, match="TELEMETRY_OPT_IN_REQUIRED"):
        service.build_operational_heartbeat("READY", 128.0)

    policy = TelemetryPrivacyPolicy(
        policy_id="telemetry/privacy/v1",
        version="1",
        opt_in=True,
        allowed_data_classes=frozenset({"operational_health"}),
    )
    opted_in = TelemetryService(app_version="9.0.0", privacy_policy=policy)
    heartbeat = opted_in.build_operational_heartbeat("READY", 128.0)
    assert heartbeat["policy_id"] == "telemetry/privacy/v1"
    assert heartbeat["crash_reporting_enabled"] is False

    bundle = opted_in.generate_support_bundle(
        ["Bearer SECRET_TOKEN 10.20.30.40"],
        {"path": r"C:\Users\Alice\secret.log"},
    )
    assert "[REDACTED_TOKEN]" in bundle["sanitized_log_lines"][0]
    assert "[REDACTED_IP]" in bundle["sanitized_log_lines"][0]
    assert "[REDACTED_USER]" in bundle["system_diagnostics"]["path"]


def test_production_packaging_requires_explicit_release_identity_and_signing() -> None:
    source = BUILD_SCRIPT.read_text(encoding="utf-8")
    upper = source.upper()

    assert "$REQUIRESIGNATURE" in upper
    assert "SIGNED RELEASE" in upper
    assert "SIGNTOOL_CERT_PATH" in upper
    assert "SIGNTOOL_TIMESTAMP_URL" in upper
    assert "EXPECTEDPUBLISHERSUBJECT" in upper
    assert "PUBLISHERURL" in upper
    assert "REQUIREDSIGNATURE" not in upper
    assert "OD-V2-23 PRODUCTION IDENTITY CANNOT BE INFERRED" in upper
