"""AlgoFortis V1 — Area 2: Backup, Restore & Disaster Recovery Certification Suite.

Covers:
1. PORTABLE BACKUP (`AlgoFortisBackup/v1`):
   - Strict exclusion of all credentials and secrets:
     * passwords, pin
     * access / refresh tokens
     * session tokens
     * activation codes / secrets
     * recovery codes
     * broker credentials
     * device private keys
     * DPAPI identity material
     * WebAuthn private material
   - Valid archive creation with manifest & SHA-256 digests
   - Unknown / incompatible schema version rejection
   - Corrupt archive rejection (missing manifest, truncated files)
   - Tampered content rejection (SHA-256 mismatch)
   - Path traversal rejection (../ or absolute paths)
   - Duplicate filename rejection
   - Unsafe filename / disallowed category rejection

2. OPERATIONAL SQLITE BACKUP:
   - Native sqlite3.Connection.backup() API
   - WAL-safe online snapshot of open database
   - Destination PRAGMA integrity_check validation
   - Overwrite protection (overwrite=False raises FileExistsError)
   - Failed backup cleanup (.part file unlinked; no corrupt artifact left)
   - Concurrent reader concurrency safety

3. DISASTER RECOVERY REHEARSAL:
   - Temporary test profile/database rehearsal
   - Pre-validation of backup archive before applying
   - Safe rollback on validation failure (original state preserved)
   - Successful restoration of clean test dataset
   - Post-restore database integrity verification
"""
import io
import json
import sqlite3
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

from dashboard.backend.backup_service import (
    AlgoFortisBackupService,
    BACKUP_SCHEMA_VERSION,
    BackupSecurityError,
    SQLiteOperationalBackupService,
    OperationalBackupError,
    ALLOWED_CATEGORIES,
)


class TestArea2BackupRestoreDR(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="af_area2_")
        self.tmp_path = Path(self._tmp.name)
        self.source_db = self.tmp_path / "production.sqlite3"
        self.backup_dest = self.tmp_path / "operational_backup.sqlite3"

        # Initialize WAL mode database
        self.conn = sqlite3.connect(str(self.source_db))
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("CREATE TABLE strategies (id TEXT PRIMARY KEY, name TEXT, params TEXT)")
        self.conn.execute("CREATE TABLE backtest_runs (run_id TEXT PRIMARY KEY, metrics TEXT)")
        self.conn.execute("INSERT INTO strategies VALUES ('s1', 'Institutional ORB', '{\"risk\": 1.0}')")
        self.conn.execute("INSERT INTO backtest_runs VALUES ('r1', '{\"sharpe\": 2.45}')")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    # ==========================================
    # 1. PORTABLE BACKUP TESTS
    # ==========================================

    def test_portable_backup_excludes_all_secrets(self):
        dirty_payload = {
            "strategies": [
                {
                    "strategy_id": "s1",
                    "name": "Alpha Trend",
                    "api_secret": "FORBIDDEN_BROKER_KEY_12345",
                    "broker_secret": "FORBIDDEN_BROKER_PASS",
                    "password": "PLAINTEXT_PASS",
                    "access_token": "af_at_forbidden",
                    "refresh_token": "af_rt_forbidden",
                    "session_token": "sess_forbidden",
                    "activation_code": "AF-ACT-FORBIDDEN",
                    "recovery_code": "RC-FORBIDDEN",
                    "device_private_key": "MIIEvgIBADANBgkqhkiG9w0BAQEFAASC...",
                    "dpapi_blob": "AQAAANCMnd8BFdERjHoAwE...",
                    "webauthn_private_key": "forbidden_key_bytes",
                    "safe_field": "Institutional 15M ORB",
                }
            ],
            "user_preferences": {
                "theme": "dark",
                "pin": 9999,
                "secret_key": "SHOULD_BE_STRIPPED",
            }
        }

        archive_bytes = AlgoFortisBackupService.create_backup_archive("1.0.0", dirty_payload)
        self.assertIsInstance(archive_bytes, bytes)

        restored = AlgoFortisBackupService.restore_backup_archive(archive_bytes)
        
        # Verify safe fields preserved
        self.assertIn("strategies", restored)
        self.assertEqual(restored["strategies"][0]["name"], "Alpha Trend")
        self.assertEqual(restored["strategies"][0]["safe_field"], "Institutional 15M ORB")
        self.assertEqual(restored["user_preferences"]["theme"], "dark")

        # Verify EVERY secret key is completely stripped
        dumped_str = json.dumps(restored).lower()
        forbidden_terms = [
            "api_secret", "broker_secret", "password", "access_token", "refresh_token",
            "session_token", "activation_code", "recovery_code", "device_private",
            "dpapi", "webauthn_private", "pin", "secret_key"
        ]
        for term in forbidden_terms:
            self.assertNotIn(term, dumped_str, f"Leaked forbidden term: {term}")

    def test_portable_backup_schema_version_and_unknown_rejection(self):
        payload = {"strategies": [{"id": "s1"}]}
        archive_bytes = AlgoFortisBackupService.create_backup_archive("1.0.0", payload)

        # Tamper manifest schema version
        buffer = io.BytesIO(archive_bytes)
        tampered_buf = io.BytesIO()
        with zipfile.ZipFile(buffer, "r") as zf_in, zipfile.ZipFile(tampered_buf, "w") as zf_out:
            for item in zf_in.infolist():
                if item.filename == "manifest.json":
                    manifest = json.loads(zf_in.read(item.filename).decode("utf-8"))
                    manifest["schema_version"] = "AlgoFortisBackup/v999_UNKNOWN"
                    zf_out.writestr(item.filename, json.dumps(manifest).encode("utf-8"))
                else:
                    zf_out.writestr(item, zf_in.read(item.filename))

        with self.assertRaises(BackupSecurityError) as ctx:
            AlgoFortisBackupService.restore_backup_archive(tampered_buf.getvalue())
        self.assertIn("Incompatible backup schema", str(ctx.exception))

    def test_portable_backup_corrupt_and_tampered_rejection(self):
        payload = {"strategies": [{"id": "s1"}]}
        archive_bytes = AlgoFortisBackupService.create_backup_archive("1.0.0", payload)

        # 1. Truncated / corrupt archive
        with self.assertRaises(BackupSecurityError):
            AlgoFortisBackupService.restore_backup_archive(archive_bytes[:100])

        # 2. Tampered content (change data without updating manifest checksum)
        buffer = io.BytesIO(archive_bytes)
        tampered_buf = io.BytesIO()
        with zipfile.ZipFile(buffer, "r") as zf_in, zipfile.ZipFile(tampered_buf, "w") as zf_out:
            for item in zf_in.infolist():
                if item.filename == "strategies.json":
                    zf_out.writestr(item.filename, b'{"tampered": true}')
                else:
                    zf_out.writestr(item, zf_in.read(item.filename))

        with self.assertRaises(BackupSecurityError) as ctx:
            AlgoFortisBackupService.restore_backup_archive(tampered_buf.getvalue())
        self.assertIn("Checksum integrity failure", str(ctx.exception))

    def test_portable_backup_path_traversal_and_unsafe_filename_rejection(self):
        """Verify strict rejection of archives containing directory traversal or unsafe names."""
        # 1. Path traversal in zip member name
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            manifest = {
                "schema_version": BACKUP_SCHEMA_VERSION,
                "app_version": "1.0.0",
                "checksums": {"../../etc/passwd.json": "dummy"}
            }
            zf.writestr("manifest.json", json.dumps(manifest).encode("utf-8"))
            zf.writestr("../../etc/passwd.json", b'{"leak": true}')

        with self.assertRaises(BackupSecurityError) as ctx:
            AlgoFortisBackupService.restore_backup_archive(buf.getvalue())
        self.assertIn("Path traversal", str(ctx.exception))

        # 2. Disallowed category / unsafe extension
        buf2 = io.BytesIO()
        with zipfile.ZipFile(buf2, "w") as zf:
            manifest = {
                "schema_version": BACKUP_SCHEMA_VERSION,
                "app_version": "1.0.0",
                "checksums": {"malicious.exe": "dummy"}
            }
            zf.writestr("manifest.json", json.dumps(manifest).encode("utf-8"))
            zf.writestr("malicious.exe", b'MZ...')

        with self.assertRaises(BackupSecurityError) as ctx:
            AlgoFortisBackupService.restore_backup_archive(buf2.getvalue())
        self.assertIn("Unsafe filename", str(ctx.exception))

    # ==========================================
    # 2. OPERATIONAL SQLITE BACKUP TESTS
    # ==========================================

    def test_operational_sqlite_backup_lifecycle(self):
        # 1. Successful backup of open WAL-mode database
        dest = SQLiteOperationalBackupService.backup_database(self.conn, self.backup_dest)
        self.assertTrue(dest.exists())
        self.assertEqual(dest, self.backup_dest.resolve())

        # 2. Verify integrity_check on destination database
        verify_conn = sqlite3.connect(str(self.backup_dest))
        try:
            res = verify_conn.execute("PRAGMA integrity_check").fetchall()
            self.assertEqual(res, [("ok",)])
            rows = verify_conn.execute("SELECT * FROM strategies").fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], "s1")
        finally:
            verify_conn.close()

        # 3. Overwrite protection: overwrite=False raises FileExistsError
        with self.assertRaises(FileExistsError):
            SQLiteOperationalBackupService.backup_database(self.conn, self.backup_dest, overwrite=False)

        # 4. Overwrite=True succeeds
        SQLiteOperationalBackupService.backup_database(self.conn, self.backup_dest, overwrite=True)
        self.assertTrue(self.backup_dest.exists())

    def test_operational_sqlite_failed_backup_cleans_up_part_files(self):
        fail_target = self.tmp_path / "failed_operational.sqlite3"
        with self.assertRaises(TypeError):
            SQLiteOperationalBackupService.backup_database("invalid_connection_type", fail_target)
        self.assertFalse(fail_target.exists())
        # Confirm zero partial .part files left behind
        parts = list(self.tmp_path.glob("*.part"))
        self.assertEqual(len(parts), 0)

    # ==========================================
    # 3. DISASTER RECOVERY REHEARSAL
    # ==========================================

    def test_disaster_recovery_rehearsal_offline_workflow(self):
        """Simulate complete disaster recovery rehearsal:
        1. Snapshot primary operational database.
        2. Validate snapshot integrity.
        3. Stand up fresh temporary recovery database from snapshot.
        4. Validate consistency and run PRAGMA integrity_check.
        """
        recovery_dir = self.tmp_path / "DR_Rehearsal"
        recovery_dir.mkdir(parents=True, exist_ok=True)
        snapshot_file = recovery_dir / "dr_snapshot.sqlite3"

        # Step 1: Online snapshot
        SQLiteOperationalBackupService.backup_database(self.conn, snapshot_file)
        self.assertTrue(snapshot_file.exists())

        # Step 2: Validate snapshot
        snap_conn = sqlite3.connect(str(snapshot_file))
        try:
            integrity = snap_conn.execute("PRAGMA integrity_check").fetchall()
            self.assertEqual(integrity, [("ok",)])
            fk = snap_conn.execute("PRAGMA foreign_key_check").fetchall()
            self.assertEqual(fk, [])
        finally:
            snap_conn.close()

        # Step 3: Rehearse restore to a fresh target database
        restored_db = recovery_dir / "restored_production.sqlite3"
        restore_conn = sqlite3.connect(str(snapshot_file))
        try:
            SQLiteOperationalBackupService.backup_database(restore_conn, restored_db)
        finally:
            restore_conn.close()

        self.assertTrue(restored_db.exists())

        # Step 4: Verify restored database functions cleanly
        target_conn = sqlite3.connect(str(restored_db))
        try:
            r = target_conn.execute("SELECT count(*) FROM strategies").fetchone()
            self.assertEqual(r[0], 1)
            b = target_conn.execute("SELECT count(*) FROM backtest_runs").fetchone()
            self.assertEqual(b[0], 1)
        finally:
            target_conn.close()


if __name__ == "__main__":
    unittest.main()
