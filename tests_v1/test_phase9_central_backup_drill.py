from datetime import datetime, timezone

from dashboard.backend.product_ops_v2.central_backup import (
    CentralBackupEvidence,
    CentralBackupRecord,
    CentralPrivacyBackupService,
)
from dashboard.backend.product_ops_v2.drills import central_backup_restore_drill

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def evidence(**overrides):
    values = dict(
        backup_ref="central-backup-1",
        retention_policy_ref="retention/account/v1",
        encryption_evidence_ref="kms-proof-1",
        access_control_evidence_ref="access-proof-1",
        expiry_policy_ref="expiry/account/v1",
    )
    values.update(overrides)
    return CentralBackupEvidence(**values)


def test_central_backup_requires_allowlist_and_platform_evidence_refs():
    service = CentralPrivacyBackupService(allowed_classes={"ACCOUNT_IDENTITY", "CONSENT_EVIDENCE"})
    records = (CentralBackupRecord("ACCOUNT_IDENTITY", "record-proof-1"),)
    assert service.validate(records).allowed
    assert service.validate_evidence(evidence()).allowed

    missing_encryption = service.validate_evidence(evidence(encryption_evidence_ref=""))
    assert not missing_encryption.allowed
    assert "ENCRYPTION_EVIDENCE_MISSING" in missing_encryption.reasons


def test_central_restore_drill_requires_isolation_and_complete_evidence():
    service = CentralPrivacyBackupService(allowed_classes={"ACCOUNT_IDENTITY"})
    decision = service.validate((CentralBackupRecord("ACCOUNT_IDENTITY", "proof"),))
    good = central_backup_restore_drill(
        backup_decision=decision,
        platform_evidence_decision=service.validate_evidence(evidence()),
        isolated_restore=True,
        started_at=NOW,
        ended_at=NOW,
    )
    assert good.passed
    assert good.runbook_version == "RUNBOOK_CENTRAL_PRIVACY_BACKUP_RESTORE/v1"

    not_isolated = central_backup_restore_drill(
        backup_decision=decision,
        platform_evidence_decision=service.validate_evidence(evidence()),
        isolated_restore=False,
        started_at=NOW,
        ended_at=NOW,
    )
    assert not not_isolated.passed
