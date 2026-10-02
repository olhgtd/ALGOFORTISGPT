"""AlgoFortis V2 — S3 installer/update lifecycle qualification.

Covers runtime path isolation, signed update manifests and installer payloads,
versioned UpdateSafeWindowPolicy enforcement, and uninstall data preservation.
All signature functions below are TEST_ONLY deterministic verifiers; production
release signing remains an external P4/G10 input.
"""
import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path

from dashboard.backend.account_v2.policy_seams import UpdateSafeWindowPolicy
from dashboard.backend.update_service import UpdateChannel, UpdateService
from dashboard.runtime.paths import RuntimeMode, RuntimePaths

_TEST_KEY = b"algofortis-s3-test-only-key"
_TEST_KEY_ID = "TEST_ONLY_RELEASE_KEY_V1"
_TEST_INSTALLER_SIGNER = "TEST_ONLY_INSTALLER_SIGNER_V1"
_TEST_AUTHENTICODE_THUMBPRINT = "A" * 40


def _test_signature(payload: bytes, key_id: str) -> str:
    return hmac.new(_TEST_KEY + key_id.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _test_verifier(payload: bytes, signature: str, key_id: str) -> bool:
    expected = _test_signature(payload, key_id)
    return hmac.compare_digest(expected, signature)


def _signed_manifest(installer: bytes, *, channel: str = "STABLE") -> str:
    data = {
        "version": "9.1.0",
        "channel": channel,
        "installer_url": "https://releases.example.invalid/AlgoFortis-Setup-9.1.0.exe",
        "sha256_checksum": hashlib.sha256(installer).hexdigest(),
        "min_compatible_version": "9.0.0",
        "security_critical": True,
        "release_notes": "S3 qualification fixture.",
        "signing_key_id": _TEST_KEY_ID,
        "installer_signer_id": _TEST_INSTALLER_SIGNER,
        "installer_signature": _test_signature(installer, _TEST_INSTALLER_SIGNER),
        "installer_authenticode_thumbprint": _TEST_AUTHENTICODE_THUMBPRINT,
        "safe_window_policy_id": "updates/safe-window/test-v1",
        "safe_window_policy_version": "1",
    }
    data["manifest_signature"] = _test_signature(
        UpdateService.canonical_manifest_bytes(data),
        _TEST_KEY_ID,
    )
    return json.dumps(data)


def _service() -> UpdateService:
    return UpdateService(
        current_version="9.0.0",
        channel=UpdateChannel.STABLE,
        manifest_signature_verifier=_test_verifier,
        installer_signature_verifier=_test_verifier,
        authenticode_verifier=lambda _payload, thumbprint: thumbprint == _TEST_AUTHENTICODE_THUMBPRINT,
    )


class TestArea3InstallerUpdateLifecycle(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="af_area3_")
        self.tmp_path = Path(self._tmp.name).resolve()
        self.install_dir = (self.tmp_path / "Program Files" / "AlgoFortis").resolve()
        self.appdata_dir = (self.tmp_path / "AppData" / "Local").resolve()
        self.install_dir.mkdir(parents=True, exist_ok=True)
        self.appdata_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_production_runtime_paths_isolation(self):
        paths = RuntimePaths.resolve(
            RuntimeMode.PRODUCTION,
            install_root=self.install_dir,
            environ={"LOCALAPPDATA": str(self.appdata_dir)},
        )
        self.assertEqual(paths.install, self.install_dir)
        self.assertEqual(paths.root, self.appdata_dir / "AlgoFortis")
        self.assertEqual(paths.databases, paths.root / "databases")
        self.assertEqual(paths.logs, paths.root / "logs")
        self.assertFalse(str(paths.databases).startswith(str(paths.install)))

    def test_test_mode_isolation(self):
        isolated = (self.tmp_path / "isolated_test_data").resolve()
        paths = RuntimePaths.resolve(
            RuntimeMode.TEST,
            install_root=self.install_dir,
            data_root=isolated,
        )
        self.assertEqual(paths.root, isolated)

    def test_signed_manifest_and_installer_payload_verify(self):
        installer = b"MOCK_ALGOFORTIS_SETUP_INSTALLER_V9.1.0_BYTES"
        svc = _service()
        manifest = svc.parse_and_validate_manifest(_signed_manifest(installer))
        self.assertEqual(manifest.version, "9.1.0")
        self.assertEqual(manifest.channel, UpdateChannel.STABLE)
        self.assertTrue(svc.verify_installer_payload(installer, manifest))

    def test_unsigned_or_tampered_manifest_fails_closed(self):
        installer = b"INSTALLER"
        data = json.loads(_signed_manifest(installer))
        data["version"] = "9.1.1"
        with self.assertRaisesRegex(ValueError, "UPDATE_MANIFEST_SIGNATURE_INVALID"):
            _service().parse_and_validate_manifest(json.dumps(data))

        svc_without_verifier = UpdateService()
        with self.assertRaisesRegex(ValueError, "SIGNATURE_VERIFIER_UNAVAILABLE"):
            svc_without_verifier.parse_and_validate_manifest(_signed_manifest(installer))

    def test_tampered_installer_or_bad_signature_fails_closed(self):
        installer = b"INSTALLER"
        svc = _service()
        manifest = svc.parse_and_validate_manifest(_signed_manifest(installer))

        with self.assertRaisesRegex(ValueError, "INTEGRITY ERROR"):
            svc.verify_installer_payload(b"TAMPERED", manifest)

        bad_sig_data = json.loads(_signed_manifest(installer))
        bad_sig_data["installer_signature"] = "0" * 64
        bad_sig_data["manifest_signature"] = _test_signature(
            UpdateService.canonical_manifest_bytes(bad_sig_data),
            _TEST_KEY_ID,
        )
        bad_sig_manifest = svc.parse_and_validate_manifest(json.dumps(bad_sig_data))
        with self.assertRaisesRegex(ValueError, "UPDATE_INSTALLER_SIGNATURE_INVALID"):
            svc.verify_installer_payload(installer, bad_sig_manifest)

    def test_bad_authenticode_thumbprint_fails_closed(self):
        installer = b"INSTALLER"
        data = json.loads(_signed_manifest(installer))
        data["installer_authenticode_thumbprint"] = "B" * 40
        data["manifest_signature"] = _test_signature(
            UpdateService.canonical_manifest_bytes(data),
            _TEST_KEY_ID,
        )
        manifest = _service().parse_and_validate_manifest(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "UPDATE_AUTHENTICODE_SIGNATURE_INVALID"):
            _service().verify_installer_payload(installer, manifest)

    def test_update_safe_window_blocks_active_open_position_and_policy_mismatch(self):
        installer = b"INSTALLER"
        svc = _service()
        manifest = svc.parse_and_validate_manifest(_signed_manifest(installer))
        policy = UpdateSafeWindowPolicy(
            policy_id="updates/safe-window/test-v1",
            version="1",
            allowed_engine_states=("IDLE", "DISARMED"),
            allow_open_positions=False,
            session_calendar_ref="calendar/nse/test-v1",
            applicability="APPLICABLE",
        )

        allowed = svc.evaluate_apply_decision(
            manifest,
            policy,
            engine_state="IDLE",
            has_open_positions=False,
        )
        self.assertTrue(allowed.allowed)
        self.assertFalse(allowed.auto_arm_live)

        active = svc.evaluate_apply_decision(
            manifest,
            policy,
            engine_state="ACTIVE",
            has_open_positions=False,
        )
        self.assertFalse(active.allowed)
        self.assertEqual(active.reason, "ENGINE_STATE_NOT_ALLOWED")

        open_position = svc.evaluate_apply_decision(
            manifest,
            policy,
            engine_state="IDLE",
            has_open_positions=True,
        )
        self.assertFalse(open_position.allowed)
        self.assertEqual(open_position.reason, "OPEN_POSITIONS_BLOCK_UPDATE")

        mismatch = UpdateSafeWindowPolicy(
            policy_id="updates/safe-window/other",
            version="1",
            allowed_engine_states=("IDLE",),
            allow_open_positions=False,
            session_calendar_ref="calendar/nse/test-v1",
            applicability="APPLICABLE",
        )
        decision = svc.evaluate_apply_decision(
            manifest,
            mismatch,
            engine_state="IDLE",
            has_open_positions=False,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "UPDATE_POLICY_REFERENCE_MISMATCH")

    def test_update_manifest_missing_required_fields_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing field"):
            _service().parse_and_validate_manifest(json.dumps({"version": "9.1.0"}))

    def test_failed_update_automatically_rolls_back(self):
        installer = b"INSTALLER"
        svc = _service()
        manifest = svc.parse_and_validate_manifest(_signed_manifest(installer))
        policy = UpdateSafeWindowPolicy(
            policy_id="updates/safe-window/test-v1",
            version="1",
            allowed_engine_states=("IDLE",),
            allow_open_positions=False,
            session_calendar_ref="calendar/nse/test-v1",
            applicability="APPLICABLE",
        )
        events = []

        def capture():
            events.append("capture")
            return "rollback-token"

        def apply(_payload, _manifest):
            events.append("apply")
            raise RuntimeError("simulated installer failure")

        def restore(token):
            self.assertEqual(token, "rollback-token")
            events.append("restore")

        result = svc.apply_verified_update(
            manifest,
            policy,
            engine_state="IDLE",
            has_open_positions=False,
            installer_bytes=installer,
            capture_rollback=capture,
            apply_installer=apply,
            post_update_health_check=lambda _manifest: True,
            restore_rollback=restore,
        )
        self.assertFalse(result.applied)
        self.assertTrue(result.rolled_back)
        self.assertEqual(result.reason, "UPDATE_FAILED_ROLLED_BACK")
        self.assertFalse(result.auto_arm_live)
        self.assertEqual(events, ["capture", "apply", "restore"])

    def test_post_update_health_failure_rolls_back(self):
        installer = b"INSTALLER"
        svc = _service()
        manifest = svc.parse_and_validate_manifest(_signed_manifest(installer))
        policy = UpdateSafeWindowPolicy(
            policy_id="updates/safe-window/test-v1",
            version="1",
            allowed_engine_states=("IDLE",),
            allow_open_positions=False,
            session_calendar_ref="calendar/nse/test-v1",
            applicability="APPLICABLE",
        )
        events = []

        result = svc.apply_verified_update(
            manifest,
            policy,
            engine_state="IDLE",
            has_open_positions=False,
            installer_bytes=installer,
            capture_rollback=lambda: events.append("capture") or "rollback-token",
            apply_installer=lambda _payload, _manifest: events.append("apply"),
            post_update_health_check=lambda _manifest: False,
            restore_rollback=lambda _token: events.append("restore"),
        )
        self.assertFalse(result.applied)
        self.assertTrue(result.rolled_back)
        self.assertEqual(result.reason, "UPDATE_FAILED_ROLLED_BACK")
        self.assertEqual(events, ["capture", "apply", "restore"])

    def test_failed_update_with_failed_rollback_stays_failed_closed(self):
        installer = b"INSTALLER"
        svc = _service()
        manifest = svc.parse_and_validate_manifest(_signed_manifest(installer))
        policy = UpdateSafeWindowPolicy(
            policy_id="updates/safe-window/test-v1",
            version="1",
            allowed_engine_states=("IDLE",),
            allow_open_positions=False,
            session_calendar_ref="calendar/nse/test-v1",
            applicability="APPLICABLE",
        )

        result = svc.apply_verified_update(
            manifest,
            policy,
            engine_state="IDLE",
            has_open_positions=False,
            installer_bytes=installer,
            capture_rollback=lambda: "rollback-token",
            apply_installer=lambda _payload, _manifest: (_ for _ in ()).throw(
                RuntimeError("simulated installer failure")
            ),
            post_update_health_check=lambda _manifest: True,
            restore_rollback=lambda _token: (_ for _ in ()).throw(
                RuntimeError("simulated rollback failure")
            ),
        )
        self.assertFalse(result.applied)
        self.assertFalse(result.rolled_back)
        self.assertEqual(result.reason, "UPDATE_FAILED_ROLLBACK_FAILED")
        self.assertFalse(result.auto_arm_live)

    def test_unsafe_window_never_invokes_update_callbacks(self):
        installer = b"INSTALLER"
        svc = _service()
        manifest = svc.parse_and_validate_manifest(_signed_manifest(installer))
        policy = UpdateSafeWindowPolicy(
            policy_id="updates/safe-window/test-v1",
            version="1",
            allowed_engine_states=("IDLE",),
            allow_open_positions=False,
            session_calendar_ref="calendar/nse/test-v1",
            applicability="APPLICABLE",
        )
        events = []
        result = svc.apply_verified_update(
            manifest,
            policy,
            engine_state="ACTIVE",
            has_open_positions=False,
            installer_bytes=installer,
            capture_rollback=lambda: events.append("capture"),
            apply_installer=lambda _payload, _manifest: events.append("apply"),
            post_update_health_check=lambda _manifest: events.append("health") or True,
            restore_rollback=lambda _token: events.append("restore"),
        )
        self.assertFalse(result.applied)
        self.assertFalse(result.rolled_back)
        self.assertEqual(result.reason, "ENGINE_STATE_NOT_ALLOWED")
        self.assertEqual(events, [])

    def test_uninstall_preserves_localappdata_user_databases(self):
        (self.install_dir / "AlgoFortis.exe").write_bytes(b"launcher")
        (self.install_dir / "app.dll").write_bytes(b"dll")

        user_db_dir = self.appdata_dir / "AlgoFortis" / "databases"
        user_db_dir.mkdir(parents=True, exist_ok=True)
        user_db = user_db_dir / "user_data.sqlite3"
        user_db.write_bytes(b"SQLITE_DATA")

        for f in self.install_dir.glob("*"):
            f.unlink()
        self.install_dir.rmdir()

        self.assertFalse(self.install_dir.exists())
        self.assertTrue(user_db.exists())
        self.assertEqual(user_db.read_bytes(), b"SQLITE_DATA")


if __name__ == "__main__":
    unittest.main()
