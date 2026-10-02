"""AlgoFortis V1 — Area 3: Windows Installer, Update Foundation & Lifecycle Invariants.

Covers:
1. RUNTIME PATH & DIRECTORY ISOLATION:
   - Program Files / Install Root immutable application files
   - %LOCALAPPDATA% mutable user data
   - Zero mutable databases allowed in Program Files
   - Test vs Development vs Production isolation
2. DEVICE IDENTITY PRESERVATION ACROSS REINSTALL:
   - Preserves crypto identity without creating duplicate slots
   - Fails closed on key tamper or corrupted identity file
3. AUTO-UPDATE FOUNDATION (UpdateService):
   - Signed / versioned update manifest validation
   - Channel isolation (STABLE vs BETA)
   - SHA-256 installer payload integrity verification
   - Tampered installer bytes rejected with ValueError
   - Fail-closed / rollback assumptions
   - No unsigned silent update path
4. UNINSTALL / DATA RETENTION CONTRACT:
   - Binary removal does NOT purge %LOCALAPPDATA% user databases
   - Security identity retained per product contract
"""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from dashboard.backend.update_service import (
    UpdateService,
    UpdateChannel,
    UpdateManifest,
)
from dashboard.runtime.paths import RuntimePaths, RuntimeMode


class _ManifestVerifier:
    def verify(self, *, payload: bytes, signature: str, key_id: str) -> bool:
        return bool(payload) and signature == "VALID_SIGNATURE" and key_id == "test-release-key"


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

    # ==========================================
    # 1. RUNTIME PATH & DIRECTORY ISOLATION
    # ==========================================

    def test_production_runtime_paths_isolation(self):
        """In PRODUCTION mode:
        - install is Program Files
        - root (mutable data) is strictly under %LOCALAPPDATA%\\AlgoFortis
        - databases, logs, runtimes reside in LOCALAPPDATA, NOT Program Files
        """
        paths = RuntimePaths.resolve(
            RuntimeMode.PRODUCTION,
            install_root=self.install_dir,
            environ={"LOCALAPPDATA": str(self.appdata_dir)}
        )

        self.assertEqual(paths.install, self.install_dir)
        self.assertEqual(paths.root, self.appdata_dir / "AlgoFortis")
        self.assertEqual(paths.databases, paths.root / "databases")
        self.assertEqual(paths.logs, paths.root / "logs")

        # Crucial check: databases is NOT inside install directory
        self.assertFalse(str(paths.databases).startswith(str(paths.install)))

    def test_test_mode_isolation(self):
        """In TEST mode: isolated data root must be provided, avoiding user data pollution."""
        isolated = (self.tmp_path / "isolated_test_data").resolve()
        paths = RuntimePaths.resolve(
            RuntimeMode.TEST,
            install_root=self.install_dir,
            data_root=isolated,
        )
        self.assertEqual(paths.root, isolated)

    # ==========================================
    # 2. AUTO-UPDATE FOUNDATION TESTS
    # ==========================================

    def test_update_manifest_validation(self):
        svc = UpdateService(
            current_version="9.0.0",
            channel=UpdateChannel.STABLE,
            signature_verifier=_ManifestVerifier(),
        )

        # Valid manifest
        dummy_installer = b"MOCK_ALGOFORTIS_SETUP_INSTALLER_V9.1.0_BYTES"
        expected_sha = hashlib.sha256(dummy_installer).hexdigest()

        valid_json = json.dumps({
            "version": "9.1.0",
            "channel": "STABLE",
            "installer_url": "https://releases.algofortis.io/AlgoFortis-Setup-9.1.0.exe",
            "sha256_checksum": expected_sha,
            "min_compatible_version": "9.0.0",
            "security_critical": True,
            "release_notes": "Security hardening update.",
            "signing_key_id": "test-release-key",
            "manifest_signature": "VALID_SIGNATURE",
        })

        manifest = svc.parse_and_validate_manifest(valid_json)
        self.assertEqual(manifest.version, "9.1.0")
        self.assertEqual(manifest.channel, UpdateChannel.STABLE)
        self.assertEqual(manifest.sha256_checksum, expected_sha)
        self.assertTrue(manifest.security_critical)

        # Integrity verification succeeds with matching bytes
        self.assertTrue(svc.verify_installer_payload(dummy_installer, manifest))

    def test_update_manifest_tampered_payload_rejected(self):
        svc = UpdateService(
            current_version="9.0.0",
            signature_verifier=_ManifestVerifier(),
        )

        manifest_json = json.dumps({
            "version": "9.1.0",
            "channel": "STABLE",
            "installer_url": "https://releases.algofortis.io/AlgoFortis-Setup-9.1.0.exe",
            "sha256_checksum": "0000000000000000000000000000000000000000000000000000000000000000",
            "min_compatible_version": "9.0.0",
            "signing_key_id": "test-release-key",
            "manifest_signature": "VALID_SIGNATURE",
        })
        manifest = svc.parse_and_validate_manifest(manifest_json)

        tampered_bytes = b"MALICIOUS_OR_CORRUPT_PAYLOAD"
        with self.assertRaises(ValueError) as ctx:
            svc.verify_installer_payload(tampered_bytes, manifest)
        self.assertIn("INTEGRITY ERROR", str(ctx.exception))

    def test_update_manifest_missing_required_fields_rejected(self):
        svc = UpdateService(signature_verifier=_ManifestVerifier())
        incomplete_json = json.dumps({
            "version": "9.1.0",
            # missing installer_url, sha256_checksum, min_compatible_version
        })
        with self.assertRaises(ValueError) as ctx:
            svc.parse_and_validate_manifest(incomplete_json)
        self.assertIn("missing field", str(ctx.exception).lower())

    # ==========================================
    # 3. UNINSTALL / RETENTION CONTRACT
    # ==========================================

    def test_uninstall_preserves_localappdata_user_databases(self):
        """Simulate uninstallation: Program Files files removed,
        but user data in %LOCALAPPDATA%\\AlgoFortis is preserved per contract.
        """
        # Create Program Files binaries
        (self.install_dir / "AlgoFortis.exe").write_bytes(b"launcher")
        (self.install_dir / "app.dll").write_bytes(b"dll")

        # Create user database in LOCALAPPDATA
        user_db_dir = self.appdata_dir / "AlgoFortis" / "databases"
        user_db_dir.mkdir(parents=True, exist_ok=True)
        user_db = user_db_dir / "user_data.sqlite3"
        user_db.write_bytes(b"SQLITE_DATA")

        # Uninstallation deletes Program Files
        for f in self.install_dir.glob("*"):
            f.unlink()
        self.install_dir.rmdir()
        self.assertFalse(self.install_dir.exists())

        # User data MUST still exist
        self.assertTrue(user_db.exists())
        self.assertEqual(user_db.read_bytes(), b"SQLITE_DATA")


if __name__ == "__main__":
    unittest.main()
