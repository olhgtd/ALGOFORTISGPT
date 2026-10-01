from datetime import datetime, timezone

from dashboard.backend.backup_service import AlgoFortisBackupService, BACKUP_SCHEMA_VERSION
from dashboard.backend.product_ops_v2.drills import local_backup_restore_drill

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def test_local_drill_uses_real_portable_backup_contract_and_strips_secrets():
    archive = AlgoFortisBackupService.create_backup_archive(
        "2.0.0",
        {
            "user_preferences": {
                "theme": "dark",
                "api_secret": "must-not-survive",
            },
            "strategies": {"display_name": "research-only"},
        },
    )
    restored = AlgoFortisBackupService.restore_backup_archive(archive)
    assert restored["user_preferences"] == {"theme": "dark"}
    assert "api_secret" not in restored["user_preferences"]

    isolated_target = dict(restored)
    result = local_backup_restore_drill(
        schema_version=BACKUP_SCHEMA_VERSION,
        isolated_restore=isolated_target is not restored,
        secrets_excluded="api_secret" not in restored["user_preferences"],
        started_at=NOW,
        ended_at=NOW,
    )
    assert result.passed
    assert result.runbook_version == "RUNBOOK_LOCAL_BACKUP_RESTORE/v1"
