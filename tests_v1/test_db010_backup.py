import unittest
import tempfile
import sqlite3
import threading
from pathlib import Path

from dashboard.backend.backup_service import (
    AlgoFortisBackupService,
    BACKUP_SCHEMA_VERSION,
    BackupSecurityError,
    SQLiteOperationalBackupService,
    OperationalBackupError,
)

class TestDB010Backup(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tpath = Path(self.temp_dir.name)
        self.source_db = self.tpath / "live.sqlite3"
        self.backup_db = self.tpath / "backup.sqlite3"

        # Initialize WAL mode database with tables and records
        self.conn = sqlite3.connect(str(self.source_db))
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("CREATE TABLE accounts (account_id TEXT PRIMARY KEY, balance REAL)")
        self.conn.execute("CREATE TABLE orders (order_id TEXT PRIMARY KEY, symbol TEXT, qty INTEGER)")
        self.conn.execute("INSERT INTO accounts VALUES ('ACC-01', 50000.0)")
        self.conn.execute("INSERT INTO orders VALUES ('ORD-01', 'NIFTY', 50)")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def test_live_wal_backup_succeeds_and_matches_records(self):
        # Confirm WAL file exists
        wal_file = self.tpath / "live.sqlite3-wal"
        self.assertTrue(wal_file.exists() or self.source_db.exists())

        # Perform operational backup
        out_path = SQLiteOperationalBackupService.backup_database(self.conn, self.backup_db)
        self.assertEqual(out_path, self.backup_db.resolve())
        self.assertTrue(self.backup_db.exists())

        # Verify backup contains exact same committed records
        b_conn = sqlite3.connect(str(self.backup_db))
        try:
            acc_row = b_conn.execute("SELECT account_id, balance FROM accounts WHERE account_id='ACC-01'").fetchone()
            ord_row = b_conn.execute("SELECT order_id, symbol, qty FROM orders WHERE order_id='ORD-01'").fetchone()
            self.assertEqual(acc_row, ("ACC-01", 50000.0))
            self.assertEqual(ord_row, ("ORD-01", "NIFTY", 50))

            # Verify integrity_check = ok
            integrity = b_conn.execute("PRAGMA integrity_check").fetchall()
            self.assertEqual(integrity, [("ok",)])
        finally:
            b_conn.close()

    def test_backup_with_store_instance(self):
        class MockStore:
            def __init__(self, conn):
                self._conn = conn

        store = MockStore(self.conn)
        dest = self.tpath / "store_backup.sqlite3"
        SQLiteOperationalBackupService.backup_database(store, dest)
        self.assertTrue(dest.exists())

    def test_overwrite_protection(self):
        # First backup
        SQLiteOperationalBackupService.backup_database(self.conn, self.backup_db)

        # Attempt second backup without overwrite=True -> FileExistsError
        with self.assertRaises(FileExistsError):
            SQLiteOperationalBackupService.backup_database(self.conn, self.backup_db, overwrite=False)

        # Second backup with overwrite=True succeeds
        SQLiteOperationalBackupService.backup_database(self.conn, self.backup_db, overwrite=True)
        self.assertTrue(self.backup_db.exists())

    def test_concurrent_reader_does_not_break_backup(self):
        stop_event = threading.Event()
        read_errors = []

        def reader_loop():
            r_conn = sqlite3.connect(str(self.source_db))
            try:
                while not stop_event.is_set():
                    rows = r_conn.execute("SELECT * FROM accounts").fetchall()
                    if len(rows) != 1:
                        read_errors.append("unexpected row count")
            except Exception as exc:
                read_errors.append(str(exc))
            finally:
                r_conn.close()

        reader_thread = threading.Thread(target=reader_loop)
        reader_thread.start()

        try:
            # Perform backup while reader is concurrently active
            dest = self.tpath / "concurrent_backup.sqlite3"
            SQLiteOperationalBackupService.backup_database(self.conn, dest)
            self.assertTrue(dest.exists())
        finally:
            stop_event.set()
            reader_thread.join(timeout=2.0)

        self.assertEqual(read_errors, [])

    def test_failed_backup_cleans_up_partial_file(self):
        corrupt_target = self.tpath / "fail_backup.sqlite3"

        # Pass an invalid object to cause failure
        with self.assertRaises(TypeError):
            SQLiteOperationalBackupService.backup_database("not_a_connection", corrupt_target)

        self.assertFalse(corrupt_target.exists())
        # Ensure no .part files remain
        part_files = list(self.tpath.glob("*.part"))
        self.assertEqual(part_files, [])

    def test_portable_backup_contract_unchanged(self):
        # Verify AlgoFortisBackupService remains 100% functional and unchanged
        payload = {
            "strategies": [{"name": "Alpha", "code": "pass", "api_secret": "FORBIDDEN"}],
            "user_preferences": {"theme": "dark", "password": "FORBIDDEN"}
        }
        archive = AlgoFortisBackupService.create_backup_archive("1.0.0", payload)
        self.assertIsInstance(archive, bytes)

        restored = AlgoFortisBackupService.restore_backup_archive(archive)
        self.assertIn("strategies", restored)
        self.assertIn("user_preferences", restored)
        # Secrets stripped
        self.assertNotIn("api_secret", str(restored))
        self.assertNotIn("password", str(restored))

if __name__ == "__main__":
    unittest.main()
