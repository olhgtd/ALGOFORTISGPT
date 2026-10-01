"""V1 salvage regressions for a fail-closed portable backup manifest.

The restore boundary must be closed over the manifest: every payload member is
checksummed and the human-readable included_categories list must agree with the
checksum map. Allowed-but-undeclared or internally inconsistent archives are
rejected rather than silently normalized.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest

from dashboard.backend.backup_service import (
    AlgoFortisBackupService,
    BACKUP_SCHEMA_VERSION,
    BackupSecurityError,
)


def _archive(manifest: dict[str, object], members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, sort_keys=True).encode("utf-8"))
        for name, content in members.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_restore_rejects_allowed_but_undeclared_archive_member() -> None:
    strategies = json.dumps({"strategy_id": "s1"}, sort_keys=True).encode("utf-8")
    reports = json.dumps({"report_id": "r1"}, sort_keys=True).encode("utf-8")

    manifest = {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "app_version": "salvage-test",
        "created_at_utc": "2026-09-29T00:00:00Z",
        "included_categories": ["strategies.json"],
        "checksums": {
            "strategies.json": hashlib.sha256(strategies).hexdigest(),
        },
    }

    archive = _archive(
        manifest,
        {
            "strategies.json": strategies,
            # Allowed category name, intentionally absent from checksums.
            "reports.json": reports,
        },
    )

    with pytest.raises(BackupSecurityError, match="Undeclared archive member"):
        AlgoFortisBackupService.restore_backup_archive(archive)


def test_restore_rejects_included_categories_checksum_mismatch() -> None:
    strategies = json.dumps({"strategy_id": "s1"}, sort_keys=True).encode("utf-8")

    manifest = {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "app_version": "salvage-test",
        "created_at_utc": "2026-09-29T00:00:00Z",
        # The manifest claims reports.json is included, while checksums and the
        # archive payload contain only strategies.json.
        "included_categories": ["reports.json"],
        "checksums": {
            "strategies.json": hashlib.sha256(strategies).hexdigest(),
        },
    }

    archive = _archive(manifest, {"strategies.json": strategies})

    with pytest.raises(BackupSecurityError, match="included_categories mismatch"):
        AlgoFortisBackupService.restore_backup_archive(archive)
