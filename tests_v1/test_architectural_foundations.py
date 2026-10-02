"""AlgoFortis V1 — Comprehensive Architectural Foundations Test Suite
Tests all 10 V1 foundation modules across Stages 2 through 15:
- EngineClient Boundary
- Deployment Profiles
- Device Identity Key & DPAPI Storage
- Dual-Token Session Manager & Family Reuse Detection
- Auth Policy, 3-Device Quota & High-Assurance Recovery
- Data Sovereignty & Secret Isolation
- AlgoFortisBackup/v1 & Checksums
- Auto-Update Manifests & Integrity
- Entitlement Lease Monotonicity & Offline Rules
- Telemetry Redaction & Privacy
"""
import unittest
import tempfile
import time
import sys
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

root_dir = Path(__file__).resolve().parents[1]
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from dashboard.backend.engine_client import LocalEngineClient, RemoteEngineClientPlaceholder
from dashboard.runtime.deployment_profiles import resolve_deployment_profile, DeploymentProfileType
from dashboard.backend.device_identity import (
    DeviceIdentityManager,
    DpapiSoftwareKeyProvider,
    WindowsCngTpmKeyProvider,
    get_preferred_device_key_provider
)
from dashboard.backend.session_manager import SessionManager, ACCESS_TOKEN_TTL_SEC
from dashboard.backend.auth_policy import AuthPolicyManager, RateLimitTracker
from dashboard.backend.data_sovereignty import assert_can_sync_to_cloud, DATA_AUTHORITY_MATRIX, StorageAuthority
from dashboard.backend.backup_service import AlgoFortisBackupService, BackupSecurityError
from dashboard.backend.update_service import UpdateService, UpdateChannel
from dashboard.backend.entitlement_service import EntitlementLeaseManager, EntitlementLease
from dashboard.backend.account_v2.contracts import EntitlementTimeEvidence
from dashboard.backend.telemetry_service import TelemetryService


class _ManifestVerifier:
    def verify(self, *, payload: bytes, signature: str, key_id: str) -> bool:
        return bool(payload) and signature == "VALID_SIGNATURE" and key_id == "test-release-key"


class _EntitlementVerifier:
    def verify(self, *, lease: EntitlementLease) -> bool:
        return (
            lease.signing_key_id == "entitlement-key-v1"
            and lease.lease_signature == "VALID_LEASE_SIGNATURE"
        )


class TestArchitecturalFoundations(unittest.TestCase):

    def test_engine_client_boundary(self):
        client = LocalEngineClient()
        status = client.get_runtime_status()
        self.assertEqual(status["state"], "READY")
        self.assertTrue(status["read_only"])
        self.assertEqual(status["broker_mutation"], "ZERO")

        remote = RemoteEngineClientPlaceholder("https://engine.internal:8443")
        with self.assertRaises(NotImplementedError):
            remote.get_runtime_status()

    def test_deployment_profiles(self):
        desktop = resolve_deployment_profile("DESKTOP_LOCAL")
        self.assertEqual(desktop.profile, DeploymentProfileType.DESKTOP_LOCAL)
        self.assertTrue(desktop.requires_webview)
        self.assertTrue(desktop.read_only_mode)

        vps = resolve_deployment_profile("WINDOWS_VPS")
        self.assertEqual(vps.profile, DeploymentProfileType.WINDOWS_VPS)
        self.assertTrue(vps.is_headless)
        self.assertFalse(vps.requires_webview)

    def test_device_identity_cng_tpm_preferred_path(self):
        """A. CNG/TPM preferred path where available/mockable."""
        with tempfile.TemporaryDirectory() as td:
            tpm_provider = WindowsCngTpmKeyProvider(key_name="AlgoFortis_Unit_Test_TPM_Key")
            mgr = DeviceIdentityManager(storage_dir=Path(td), provider=tpm_provider)
            try:
                ident = mgr.get_or_create_identity()
                self.assertEqual(ident["provider"], "WINDOWS_CNG_TPM")
                self.assertTrue(ident["device_id"].startswith("dev_"))
                
                # Sign challenge
                sig = mgr.sign_device_challenge(b"test_tpm_challenge_123")
                self.assertTrue(len(sig) > 0)
            except RuntimeError as e:
                # If running on environment without TPM hardware, confirm error is cleanly surfaced
                self.assertIn("TPM_UNAVAILABLE", str(e))

    def test_device_identity_dpapi_fallback(self):
        """B. DPAPI fallback provider test."""
        with tempfile.TemporaryDirectory() as td:
            dpapi_provider = DpapiSoftwareKeyProvider()
            mgr = DeviceIdentityManager(storage_dir=Path(td), provider=dpapi_provider)
            ident = mgr.get_or_create_identity()
            self.assertEqual(ident["provider"], "WINDOWS_DPAPI_SOFTWARE")
            self.assertTrue(ident["device_id"].startswith("dev_"))
            
            sig = mgr.sign_device_challenge(b"test_dpapi_challenge_456")
            self.assertTrue(len(sig) > 0)

    def test_device_identity_fail_closed_corrupt_or_missing(self):
        """C. Fail-closed on corrupt or missing key material."""
        with tempfile.TemporaryDirectory() as td:
            storage = Path(td)
            dpapi_provider = DpapiSoftwareKeyProvider()
            mgr = DeviceIdentityManager(storage_dir=storage, provider=dpapi_provider)
            ident = mgr.get_or_create_identity()

            # Corrupt the metadata file
            meta_path = storage / "device_identity.json"
            meta_path.write_text("CORRUPT_JSON_DATA", encoding="utf-8")

            mgr_corrupt = DeviceIdentityManager(storage_dir=storage, provider=dpapi_provider)
            with self.assertRaises(RuntimeError):
                mgr_corrupt.get_or_create_identity()

            # Missing key file with valid metadata
            meta_path.write_text(json.dumps(ident), encoding="utf-8")
            key_file = storage / "device_key.dpapi"
            if key_file.exists():
                key_file.unlink()

            with self.assertRaises(Exception):
                mgr_corrupt.get_or_create_identity()

    def test_device_identity_reinstall_rediscovery(self):
        """D. Same-PC reinstallation rediscovery semantics."""
        with tempfile.TemporaryDirectory() as td:
            storage = Path(td)
            # First installation
            mgr1 = DeviceIdentityManager(storage_dir=storage, provider=DpapiSoftwareKeyProvider())
            ident1 = mgr1.get_or_create_identity()
            original_device_id = ident1["device_id"]
            original_fp = ident1["public_key_fingerprint"]

            # Simulate app uninstalled (binaries removed, but %LOCALAPPDATA% directory preserved)
            # Reinstalling app and initializing fresh manager instance on preserved directory:
            mgr_reinstall = DeviceIdentityManager(storage_dir=storage, provider=DpapiSoftwareKeyProvider())
            ident_reinstall = mgr_reinstall.get_or_create_identity()

            # Must rediscover exact same device_id and public key without creating duplicate device
            self.assertEqual(ident_reinstall["device_id"], original_device_id)
            self.assertEqual(ident_reinstall["public_key_fingerprint"], original_fp)

    def test_session_manager_and_reuse_revocation(self):
        sm = SessionManager()
        at, rt, info = sm.create_session("usr_001", "dev_001", "USER")
        
        # Valid access token
        payload = sm.validate_access_token(at)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["user_id"], "usr_001")

        # Rotating refresh token
        new_at, new_rt = sm.rotate_refresh_token(rt)
        self.assertNotEqual(at, new_at)
        self.assertNotEqual(rt, new_rt)

        # REPLAY ATTACK: Re-submitting old refresh token MUST revoke entire family!
        with self.assertRaises(PermissionError):
            sm.rotate_refresh_token(rt)

        # Confirm new access token is now rejected due to family revocation
        self.assertIsNone(sm.validate_access_token(new_at))

    def test_auth_policy_quotas_and_recovery(self):
        apm = AuthPolicyManager()
        
        # 1. 24h Activation Lifecycle
        code = apm.generate_activation_code("usr_002", "trader@algofortis.io")
        rec = apm.redeem_activation_code(code)
        self.assertEqual(rec["email"], "trader@algofortis.io")
        # Second redemption must fail
        with self.assertRaises(ValueError):
            apm.redeem_activation_code(code)

        # 2. Strict 3-Device Quota
        apm.register_device("usr_002", "dev_1")
        apm.register_device("usr_002", "dev_2")
        apm.register_device("usr_002", "dev_3")
        with self.assertRaises(PermissionError):
            apm.register_device("usr_002", "dev_4")

        # 3. High-Assurance Recovery
        codes = apm.generate_recovery_codes("usr_002")
        self.assertEqual(len(codes), 8)
        sm = SessionManager()
        sm.create_session("usr_002", "dev_1", "USER")
        
        success = apm.execute_high_assurance_recovery("usr_002", codes[0], session_manager=sm)
        self.assertTrue(success)
        # All devices purged
        self.assertEqual(len(apm._user_devices["usr_002"]), 0)

    def test_data_sovereignty(self):
        # Permitted server categories
        assert_can_sync_to_cloud("account_identity")
        assert_can_sync_to_cloud("entitlement_leases")

        # Forbidden local-only categories
        with self.assertRaises(PermissionError):
            assert_can_sync_to_cloud("broker_api_secrets")
        with self.assertRaises(PermissionError):
            assert_can_sync_to_cloud("strategy_source_code")

    def test_backup_service_secret_exclusion(self):
        dirty_data = {
            "strategies": {
                "strat_1": {"name": "Momentum", "api_secret": "LEAKED_SECRET_123"}
            },
            "user_preferences": {
                "theme": "dark",
                "password": "DO_NOT_STORE_PASSWORD"
            }
        }
        archive = AlgoFortisBackupService.create_backup_archive("9.0.0", dirty_data)
        restored = AlgoFortisBackupService.restore_backup_archive(archive)

        # Verify secrets were stripped
        self.assertEqual(restored["strategies"]["strat_1"]["name"], "Momentum")
        self.assertNotIn("api_secret", restored["strategies"]["strat_1"])
        self.assertEqual(restored["user_preferences"]["theme"], "dark")
        self.assertNotIn("password", restored["user_preferences"])

    def test_update_service_manifest_and_sha(self):
        svc = UpdateService(signature_verifier=_ManifestVerifier())
        manifest_json = """{
            "version": "9.1.0",
            "channel": "STABLE",
            "installer_url": "https://updates.algofortis.internal/AlgoFortis-Setup-9.1.0.exe",
            "sha256_checksum": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
            "min_compatible_version": "9.0.0",
            "signing_key_id": "test-release-key",
            "manifest_signature": "VALID_SIGNATURE"
        }"""
        m = svc.parse_and_validate_manifest(manifest_json)
        self.assertEqual(m.version, "9.1.0")

        dummy_payload = b"hello" # SHA256: 2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824
        self.assertTrue(svc.verify_installer_payload(dummy_payload, m))

        with self.assertRaises(ValueError):
            svc.verify_installer_payload(b"corrupt", m)

    def test_entitlement_lease_manager(self):
        issued = datetime(2026, 10, 2, 4, 0, tzinfo=timezone.utc)
        expires = issued + timedelta(days=7)
        lease = EntitlementLease(
            lease_id="lse_001",
            user_id="usr_001",
            device_id="dev_001",
            tier="ENTERPRISE",
            capabilities=["BACKTEST", "PAPER", "OPTIONS"],
            issued_at=issued.timestamp(),
            expires_at=expires.timestamp(),
            max_observed_timestamp=issued.timestamp(),
            signing_key_id="entitlement-key-v1",
            lease_signature="VALID_LEASE_SIGNATURE",
        )
        mgr = EntitlementLeaseManager(signature_verifier=_EntitlementVerifier())
        evidence = EntitlementTimeEvidence(
            server_issued_at=issued,
            last_successful_server_check_in=issued,
            lease_expires_at=expires,
            monotonic_anchor=100.0,
            monotonic_elapsed_seconds=3600.0,
            boot_session_id="boot-1",
        )
        res = mgr.validate_lease(
            lease,
            current_device_id="dev_001",
            time_evidence=evidence,
            observed_wall_time=issued + timedelta(hours=1),
        )
        self.assertTrue(res["valid"])
        self.assertTrue(res["can_execute_risk_management"])

        rollback = mgr.validate_lease(
            lease,
            current_device_id="dev_001",
            time_evidence=evidence,
            observed_wall_time=issued - timedelta(hours=1),
        )
        self.assertFalse(rollback["valid"])
        self.assertEqual(rollback["reason"], "ENTITLEMENT_TIME_UNCERTAIN")
        self.assertTrue(rollback["can_execute_risk_management"])

    def test_telemetry_redaction(self):
        svc = TelemetryService()
        raw_log = "Error on C:\\Users\\Administrator\\Desktop with Bearer eyJhbGciOiJIUzI1Ni from 192.168.1.50 and api_key: 'topsecret123'"
        clean = svc.sanitize_string(raw_log)
        self.assertNotIn("Administrator", clean)
        self.assertNotIn("eyJhbGciOiJIUzI1Ni", clean)
        self.assertNotIn("192.168.1.50", clean)
        self.assertNotIn("topsecret123", clean)
        self.assertIn("[REDACTED_USER]", clean)
        self.assertIn("[REDACTED_TOKEN]", clean)
        self.assertIn("[REDACTED_IP]", clean)


if __name__ == "__main__":
    unittest.main()
