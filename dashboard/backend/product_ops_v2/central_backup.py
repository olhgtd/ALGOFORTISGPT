from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CentralBackupRecord:
    data_class: str
    evidence_ref: str


@dataclass(frozen=True, slots=True)
class CentralBackupEvidence:
    backup_ref: str
    retention_policy_ref: str
    encryption_evidence_ref: str
    access_control_evidence_ref: str
    expiry_policy_ref: str


@dataclass(frozen=True, slots=True)
class CentralBackupDecision:
    allowed: bool
    reasons: tuple[str, ...]


class CentralPrivacyBackupPort(Protocol):
    """Platform adapter boundary only; implementations live outside Phase 9 domain code."""

    def create_backup(self, records: tuple[CentralBackupRecord, ...]) -> CentralBackupEvidence: ...
    def restore_isolated(self, backup_ref: str) -> bool: ...


class CentralPrivacyBackupService:
    FORBIDDEN = {
        "BROKER_CREDENTIAL",
        "DEVICE_PRIVATE_KEY",
        "STRATEGY_CONTENT",
        "LIVE_POSITION",
        "BALANCE",
        "RAW_TRADE_LOG",
        "LOCAL_TRADING_STATE",
    }

    def __init__(self, *, allowed_classes: set[str]):
        self._allowed = set(allowed_classes)

    def validate(self, records: tuple[CentralBackupRecord, ...]) -> CentralBackupDecision:
        reasons: list[str] = []
        for record in records:
            if record.data_class in self.FORBIDDEN:
                reasons.append("LOCAL_OR_SECRET_CLASS_FORBIDDEN:" + record.data_class)
            elif record.data_class not in self._allowed:
                reasons.append("UNAPPROVED_CENTRAL_CLASS:" + record.data_class)
            if not record.evidence_ref:
                reasons.append("EVIDENCE_REF_MISSING:" + record.data_class)
        return CentralBackupDecision(not reasons, tuple(sorted(set(reasons))))

    def validate_evidence(self, evidence: CentralBackupEvidence) -> CentralBackupDecision:
        reasons: list[str] = []
        checks = (
            ("BACKUP_REF_MISSING", evidence.backup_ref),
            ("RETENTION_POLICY_REF_MISSING", evidence.retention_policy_ref),
            ("ENCRYPTION_EVIDENCE_MISSING", evidence.encryption_evidence_ref),
            ("ACCESS_CONTROL_EVIDENCE_MISSING", evidence.access_control_evidence_ref),
            ("EXPIRY_POLICY_REF_MISSING", evidence.expiry_policy_ref),
        )
        for code, value in checks:
            if not value.strip():
                reasons.append(code)
        return CentralBackupDecision(not reasons, tuple(reasons))
