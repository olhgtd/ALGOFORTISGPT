from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard.backend.account_v2.contracts import EntitlementTimeEvidence
from dashboard.backend.account_v2.policy_seams import TelemetryPrivacyPolicy, UpdateSafeWindowPolicy
from dashboard.backend.backup_service import AlgoFortisBackupService
from dashboard.backend.entitlement_service import EntitlementLease, EntitlementLeaseManager
from dashboard.backend.telemetry_service import TelemetryService
from dashboard.backend.update_service import UpdateService

KEY = b"algofortis-s3-probe-test-only"
KEY_ID = "TEST_ONLY_S3_PROBE_KEY"


def sign(payload: bytes, key_id: str) -> str:
    return hmac.new(KEY + key_id.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify(payload: bytes, signature: str, key_id: str) -> bool:
    return hmac.compare_digest(sign(payload, key_id), signature)


def verify_update() -> None:
    installer = b"S3_PROBE_INSTALLER"
    data = {
        "version": "9.1.0",
        "channel": "STABLE",
        "installer_url": "https://updates.example.invalid/AlgoFortis-Setup-9.1.0.exe",
        "sha256_checksum": hashlib.sha256(installer).hexdigest(),
        "min_compatible_version": "9.0.0",
        "signing_key_id": KEY_ID,
        "installer_signer_id": "TEST_ONLY_INSTALLER",
        "installer_signature": sign(installer, "TEST_ONLY_INSTALLER"),
        "safe_window_policy_id": "updates/safe-window/test-v1",
        "safe_window_policy_version": "1",
    }
    data["manifest_signature"] = sign(UpdateService.canonical_manifest_bytes(data), KEY_ID)
    service = UpdateService(
        manifest_signature_verifier=verify,
        installer_signature_verifier=verify,
    )
    manifest = service.parse_and_validate_manifest(json.dumps(data))
    assert service.verify_installer_payload(installer, manifest)

    policy = UpdateSafeWindowPolicy(
        policy_id="updates/safe-window/test-v1",
        version="1",
        allowed_engine_states=("IDLE", "DISARMED"),
        allow_open_positions=False,
        session_calendar_ref="calendar/nse/test-v1",
        applicability="APPLICABLE",
    )
    ok = service.evaluate_apply_decision(
        manifest, policy, engine_state="IDLE", has_open_positions=False
    )
    active = service.evaluate_apply_decision(
        manifest, policy, engine_state="ACTIVE", has_open_positions=False
    )
    open_position = service.evaluate_apply_decision(
        manifest, policy, engine_state="IDLE", has_open_positions=True
    )
    assert ok.allowed and not ok.auto_arm_live
    assert not active.allowed
    assert not open_position.allowed


def verify_entitlement() -> None:
    now = datetime(2026, 10, 2, 6, 0, tzinfo=timezone.utc)
    issued = now.timestamp() - 3600
    expires = now.timestamp() + 6 * 86400
    unsigned = EntitlementLease(
        lease_id="probe-lease",
        user_id="probe-user",
        device_id="probe-device",
        tier="TEST",
        capabilities=["BACKTEST", "PAPER"],
        issued_at=issued,
        expires_at=expires,
        max_observed_timestamp=now.timestamp(),
        signing_key_id=KEY_ID,
        signature="",
    )
    lease = replace(
        unsigned,
        signature=sign(EntitlementLeaseManager.canonical_lease_bytes(unsigned), KEY_ID),
    )
    manager = EntitlementLeaseManager(lease_signature_verifier=verify)
    evidence = EntitlementTimeEvidence(
        server_issued_at=datetime.fromtimestamp(issued, tz=timezone.utc),
        last_successful_server_check_in=datetime.fromtimestamp(issued, tz=timezone.utc),
        lease_expires_at=datetime.fromtimestamp(expires, tz=timezone.utc),
        monotonic_anchor=100.0,
        monotonic_elapsed_seconds=3600.0,
        boot_session_id="probe-boot",
    )
    valid = manager.validate_lease(
        lease,
        "probe-device",
        time_evidence=evidence,
        observed_wall_time=now,
    )
    assert valid["valid"]

    uncertain = replace(
        evidence,
        monotonic_anchor=None,
        monotonic_elapsed_seconds=None,
        boot_session_id=None,
    )
    denied = manager.validate_lease(
        lease,
        "probe-device",
        time_evidence=uncertain,
        observed_wall_time=now,
    )
    assert not denied["valid"]
    assert denied["reason"] == "ENTITLEMENT_TIME_UNCERTAIN"
    assert denied["protective_safety_allowed"]


def verify_telemetry() -> None:
    try:
        TelemetryService().build_operational_heartbeat("READY", 64.0)
    except PermissionError:
        pass
    else:
        raise AssertionError("telemetry without opt-in must fail closed")

    policy = TelemetryPrivacyPolicy(
        policy_id="telemetry/test-v1",
        version="1",
        opt_in=True,
        allowed_data_classes=frozenset({"operational_health"}),
    )
    heartbeat = TelemetryService(privacy_policy=policy).build_operational_heartbeat("READY", 64.0)
    assert heartbeat["policy_id"] == "telemetry/test-v1"


def verify_backup() -> None:
    archive = AlgoFortisBackupService.create_backup_archive(
        "9.0.0",
        {
            "strategies": {"orb": {"name": "ORB", "api_secret": "MUST_NOT_SURVIVE"}},
            "user_preferences": {"theme": "dark"},
        },
    )
    restored = AlgoFortisBackupService.restore_backup_archive(archive)
    assert restored["strategies"]["orb"]["name"] == "ORB"
    assert "api_secret" not in restored["strategies"]["orb"]


if __name__ == "__main__":
    verify_update()
    verify_entitlement()
    verify_telemetry()
    verify_backup()
    print("S3_SIGNED_UPDATE=PASS")
    print("S3_UPDATE_SAFE_WINDOW=PASS")
    print("S3_ENTITLEMENT_TIME=PASS")
    print("S3_TELEMETRY_OPT_IN=PASS")
    print("S3_BACKUP_RESTORE=PASS")
    print("LIVE_STATE=READ_ONLY/DISARMED")
    print("G10_REAL_MONEY_ENABLEMENT=NO")
