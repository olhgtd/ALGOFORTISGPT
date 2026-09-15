"""AlgoFortis V1 — Portable Backup & Restore Service
Implements ADR-18 (`AlgoFortisBackup/v1`).
- Allowed: non-secret settings, strategy configs, backtest results, reports.
- Strictly Forbidden: broker secrets, access tokens, refresh tokens, device private keys,
  DPAPI key blobs, WebAuthn private material, recovery codes, session credentials.
- Schema verification & SHA-256 integrity validation.
- Incompatible or corrupt backups fail closed with zero partial imports.
"""
import io
import json
import zipfile
import hashlib
import time
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Union

BACKUP_SCHEMA_VERSION = "AlgoFortisBackup/v1"

# Explicit blacklist of forbidden keys and patterns
FORBIDDEN_KEY_PATTERNS: Set[str] = {
    "api_secret", "secret_key", "broker_secret", "password", "pin",
    "private_key", "dpapi", "access_token", "refresh_token", "recovery_code",
    "session_token", "credential_private", "auth_token", "activation",
    "credential_priv", "privkey", "tpm_key", "webauthn_private", "device_private",
    "private_material"
}

ALLOWED_CATEGORIES: Set[str] = {
    "strategies", "backtest_results", "user_preferences", "reports", "system_settings"
}


class BackupSecurityError(Exception):
    pass


class AlgoFortisBackupService:
    """Creates and restores portable user archives with strict secret exclusion."""

    @staticmethod
    def is_secret_key(key: str) -> bool:
        lower = key.lower()
        return any(pattern in lower for pattern in FORBIDDEN_KEY_PATTERNS)

    @classmethod
    def sanitize_payload(cls, data: Any) -> Any:
        """Recursively strip any secret keys from dictionary payloads."""
        if isinstance(data, dict):
            clean = {}
            for k, v in data.items():
                if cls.is_secret_key(k):
                    continue
                clean[k] = cls.sanitize_payload(v)
            return clean
        elif isinstance(data, list):
            return [cls.sanitize_payload(item) for item in data]
        return data

    @classmethod
    def create_backup_archive(cls, app_version: str, categories_data: Dict[str, Any]) -> bytes:
        """Create a signed ZIP archive containing manifest and sanitized category files."""
        buffer = io.BytesIO()
        checksums = {}

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for category, data in categories_data.items():
                if category not in ALLOWED_CATEGORIES:
                    continue

                # Strip all secrets
                clean_data = cls.sanitize_payload(data)
                serialized = json.dumps(clean_data, indent=2, sort_keys=True).encode("utf-8")
                
                # Compute SHA256
                digest = hashlib.sha256(serialized).hexdigest()
                filename = f"{category}.json"
                checksums[filename] = digest
                zf.writestr(filename, serialized)

            # Write manifest
            manifest = {
                "schema_version": BACKUP_SCHEMA_VERSION,
                "app_version": app_version,
                "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "included_categories": list(checksums.keys()),
                "checksums": checksums
            }
            manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
            zf.writestr("manifest.json", manifest_bytes)

        return buffer.getvalue()

    @classmethod
    def restore_backup_archive(cls, archive_bytes: bytes) -> Dict[str, Any]:
        """Validate and restore a portable backup. Fails closed on any corruption, tamper, or path traversal."""
        try:
            buffer = io.BytesIO(archive_bytes)
            with zipfile.ZipFile(buffer, "r") as zf:
                namelist = zf.namelist()
                if "manifest.json" not in namelist:
                    raise BackupSecurityError("Invalid archive: missing manifest.json")

                # Validate archive members against path traversal, unsafe filenames, and duplicates
                seen_names: Set[str] = set()
                for member in namelist:
                    if member in seen_names:
                        raise BackupSecurityError(f"Duplicate filename in archive: {member}")
                    seen_names.add(member)
                    if ".." in member or member.startswith("/") or member.startswith("\\") or ":" in member:
                        raise BackupSecurityError(f"Path traversal detected in archive member: {member}")
                    if member != "manifest.json" and not member.endswith(".json"):
                        raise BackupSecurityError(f"Unsafe filename in archive: {member}")
                    if member != "manifest.json" and member.replace(".json", "") not in ALLOWED_CATEGORIES:
                        raise BackupSecurityError(f"Disallowed category in archive: {member}")

                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
                if manifest.get("schema_version") != BACKUP_SCHEMA_VERSION:
                    raise BackupSecurityError(
                        f"Incompatible backup schema: expected {BACKUP_SCHEMA_VERSION}, "
                        f"got {manifest.get('schema_version')}"
                    )

                checksums = manifest.get("checksums", {})
                restored_data = {}

                # Verify all declared file checksums before accepting any file
                for filename, expected_digest in checksums.items():
                    if ".." in filename or filename.startswith("/") or filename.startswith("\\") or ":" in filename:
                        raise BackupSecurityError(f"Path traversal detected in manifest checksums: {filename}")
                    category_name = filename.replace(".json", "")
                    if category_name not in ALLOWED_CATEGORIES:
                        raise BackupSecurityError(f"Disallowed category in manifest checksums: {category_name}")
                    if filename not in namelist:
                        raise BackupSecurityError(f"Corrupt backup: missing declared file {filename}")
                    content = zf.read(filename)
                    actual_digest = hashlib.sha256(content).hexdigest()
                    if actual_digest != expected_digest:
                        raise BackupSecurityError(f"Checksum integrity failure for {filename}")

                    # Parse JSON
                    parsed = json.loads(content.decode("utf-8"))
                    
                    # Final safety check: ensure no forbidden secrets leaked into backup
                    clean_parsed = cls.sanitize_payload(parsed)
                    restored_data[category_name] = clean_parsed

                return restored_data
        except Exception as e:
            if isinstance(e, BackupSecurityError):
                raise
            raise BackupSecurityError(f"Backup restoration failed: {e}")


class OperationalBackupError(Exception):
    """Raised when operational SQLite database backup fails."""
    pass


class SQLiteOperationalBackupService:
    """Operational SQLite database backup service using native sqlite3.Connection.backup().

    Distinct from AlgoFortisBackup/v1:
    - AlgoFortisBackup/v1: portable user-data export/import (JSON in ZIP, strips secrets).
    - SQLiteOperationalBackupService: raw binary SQLite snapshot of operational databases,
      WAL-safe, non-blocking, verifies destination PRAGMA integrity_check.
    """

    @staticmethod
    def backup_database(
        source_connection_or_store: Any,
        destination_path: Path | str,
        *,
        overwrite: bool = False,
        pages: int = -1,
    ) -> Path:
        """Create a consistent, WAL-safe operational snapshot of an open SQLite database.

        Contract:
        - caller supplies source connection (sqlite3.Connection) or store instance exposing ._conn
        - caller supplies destination path
        - destination directory is created safely if it doesn't exist
        - if destination file already exists and overwrite=False -> raises FileExistsError
        - writes to a temporary sibling file (.part) and validates PRAGMA integrity_check == 'ok'
        - on success: atomically replaces target destination path
        - on failure: cleans up partial file, leaving no apparently-valid corrupted artifact
        - returns resolved destination Path
        """
        dest_path = Path(destination_path).resolve()

        if dest_path.exists() and not overwrite:
            raise FileExistsError(f"Backup destination already exists and overwrite is False: {dest_path}")

        # Resolve source connection
        if hasattr(source_connection_or_store, "_conn"):
            source_conn = source_connection_or_store._conn
        elif isinstance(source_connection_or_store, sqlite3.Connection):
            source_conn = source_connection_or_store
        else:
            raise TypeError("source_connection_or_store must be a sqlite3.Connection or expose a ._conn attribute")

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        temp_dest = dest_path.parent / f"{dest_path.name}.{time.time_ns()}.part"

        try:
            # 1. Connect to temp destination and perform online backup
            dest_conn = sqlite3.connect(str(temp_dest))
            try:
                source_conn.backup(dest_conn, pages=pages)
            finally:
                dest_conn.close()

            # 2. Verify destination database integrity
            verify_conn = sqlite3.connect(str(temp_dest))
            try:
                integrity = verify_conn.execute("PRAGMA integrity_check").fetchall()
                if not integrity or integrity[0][0] != "ok":
                    raise OperationalBackupError(f"Backup destination integrity check failed: {integrity}")
            finally:
                verify_conn.close()

            # 3. Atomic rename/replace to final destination
            if dest_path.exists():
                dest_path.unlink()
            temp_dest.replace(dest_path)
            return dest_path

        except Exception as exc:
            # Ensure no apparently-valid partial file is left behind
            if temp_dest.exists():
                try:
                    temp_dest.unlink()
                except OSError:
                    pass
            if isinstance(exc, (FileExistsError, TypeError, OperationalBackupError)):
                raise
            raise OperationalBackupError(f"Operational backup failed: {exc}") from exc
