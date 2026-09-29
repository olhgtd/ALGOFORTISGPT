"""V1 salvage regression: portable backup restore must be manifest-closed.

A syntactically allowed JSON member that is not declared in the manifest must
not be silently ignored. The V1 salvage contract is fail-closed: every archive
member other than manifest.json must be covered by the manifest checksum map.
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

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, sort_keys=True).encode("utf-8"))
        zf.writestr("strategies.json", strategies)
        # reports.json is an allowed category name, but it is intentionally not
        # declared in the manifest and therefore must cause fail-closed restore.
        zf.writestr("reports.json", reports)

    with pytest.raises(BackupSecurityError, match="Undeclared archive member"):
        AlgoFortisBackupService.restore_backup_archive(buf.getvalue())
