"""Fail-closed broker eligibility evidence for Phase-6 read-only observation."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _aware(value: object, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value


def _refs(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not value:
        raise ValueError("source_refs must be a non-empty tuple")
    return tuple(_text(item, "source_refs") for item in value)


class BrokerEligibilityStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    ELIGIBLE_READ_ONLY = "ELIGIBLE_READ_ONLY"


@dataclass(frozen=True, slots=True)
class BrokerComplianceEvidence:
    evidence_id: str
    version: str
    reviewed_at: datetime
    valid_until: datetime
    static_ip_verified: bool
    rule_review_verified: bool
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _text(self.evidence_id, "evidence_id"))
        object.__setattr__(self, "version", _text(self.version, "version"))
        reviewed = _aware(self.reviewed_at, "reviewed_at")
        valid_until = _aware(self.valid_until, "valid_until")
        if valid_until < reviewed:
            raise ValueError("valid_until cannot precede reviewed_at")
        if not isinstance(self.static_ip_verified, bool):
            raise TypeError("static_ip_verified must be bool")
        if not isinstance(self.rule_review_verified, bool):
            raise TypeError("rule_review_verified must be bool")
        object.__setattr__(self, "reviewed_at", reviewed)
        object.__setattr__(self, "valid_until", valid_until)
        object.__setattr__(self, "source_refs", _refs(self.source_refs))

    @property
    def reference(self) -> str:
        return f"{self.evidence_id}@{self.version}"


@dataclass(frozen=True, slots=True)
class BrokerEligibilityDecision:
    status: BrokerEligibilityStatus
    eligible: bool
    reason: str
    evidence_ref: str | None


class BrokerComplianceGate:
    def evaluate(
        self,
        evidence: BrokerComplianceEvidence | None,
        *,
        now: datetime,
    ) -> BrokerEligibilityDecision:
        current = _aware(now, "now")
        if evidence is None:
            return BrokerEligibilityDecision(
                BrokerEligibilityStatus.UNVERIFIED,
                False,
                "MISSING_COMPLIANCE_EVIDENCE",
                None,
            )
        if not isinstance(evidence, BrokerComplianceEvidence):
            raise TypeError("evidence must be BrokerComplianceEvidence or None")
        if current > evidence.valid_until:
            return BrokerEligibilityDecision(
                BrokerEligibilityStatus.NOT_ELIGIBLE,
                False,
                "STALE_COMPLIANCE_EVIDENCE",
                evidence.reference,
            )
        if not evidence.static_ip_verified:
            return BrokerEligibilityDecision(
                BrokerEligibilityStatus.NOT_ELIGIBLE,
                False,
                "STATIC_IP_UNVERIFIED",
                evidence.reference,
            )
        if not evidence.rule_review_verified:
            return BrokerEligibilityDecision(
                BrokerEligibilityStatus.UNVERIFIED,
                False,
                "RULE_REVIEW_UNVERIFIED",
                evidence.reference,
            )
        return BrokerEligibilityDecision(
            BrokerEligibilityStatus.ELIGIBLE_READ_ONLY,
            True,
            "READ_ONLY_EVIDENCE_VERIFIED",
            evidence.reference,
        )


__all__ = [
    "BrokerComplianceEvidence",
    "BrokerEligibilityStatus",
    "BrokerEligibilityDecision",
    "BrokerComplianceGate",
]
