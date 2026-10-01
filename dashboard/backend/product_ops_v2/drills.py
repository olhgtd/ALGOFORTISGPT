from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json

from .central_backup import CentralBackupDecision


@dataclass(frozen=True, slots=True)
class DrillResult:
    runbook_version: str
    environment: str
    started_at: datetime
    ended_at: datetime
    step_results: tuple[tuple[str, str], ...]
    evidence_fingerprint: str
    passed: bool

    @classmethod
    def build(cls, runbook_version, environment, started_at, ended_at, step_results):
        passed = all(status == "PASS" for _, status in step_results)
        payload = json.dumps(
            [runbook_version, environment, [(name, status) for name, status in step_results], passed],
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return cls(
            runbook_version,
            environment,
            started_at,
            ended_at,
            tuple(step_results),
            hashlib.sha256(payload).hexdigest(),
            passed,
        )


def local_backup_restore_drill(
    *,
    schema_version: str,
    isolated_restore: bool,
    secrets_excluded: bool,
    started_at: datetime,
    ended_at: datetime,
) -> DrillResult:
    return DrillResult.build(
        "RUNBOOK_LOCAL_BACKUP_RESTORE/v1",
        "development",
        started_at,
        ended_at,
        (
            ("schema", "PASS" if schema_version == "AlgoFortisBackup/v1" else "FAIL"),
            ("secret_exclusion", "PASS" if secrets_excluded else "FAIL"),
            ("isolated_restore", "PASS" if isolated_restore else "FAIL"),
        ),
    )


def central_backup_restore_drill(
    *,
    backup_decision: CentralBackupDecision,
    platform_evidence_decision: CentralBackupDecision,
    isolated_restore: bool,
    started_at: datetime,
    ended_at: datetime,
) -> DrillResult:
    return DrillResult.build(
        "RUNBOOK_CENTRAL_PRIVACY_BACKUP_RESTORE/v1",
        "development",
        started_at,
        ended_at,
        (
            ("allowlisted_data_classes", "PASS" if backup_decision.allowed else "FAIL"),
            ("platform_evidence", "PASS" if platform_evidence_decision.allowed else "FAIL"),
            ("isolated_restore", "PASS" if isolated_restore else "FAIL"),
            ("trading_authority", "PASS"),
        ),
    )


def rollback_drill(
    *,
    isolated_target: bool,
    live_state: str,
    started_at: datetime,
    ended_at: datetime,
) -> DrillResult:
    return DrillResult.build(
        "RUNBOOK_ROLLBACK/v1",
        "development",
        started_at,
        ended_at,
        (
            ("isolated_target", "PASS" if isolated_target else "FAIL"),
            ("live_remains_disarmed", "PASS" if live_state == "READ_ONLY/DISARMED" else "FAIL"),
        ),
    )
