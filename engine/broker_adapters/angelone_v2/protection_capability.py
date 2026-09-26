"""Read-only broker-resident protection capability evidence for G6."""
from __future__ import annotations

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


def _caps(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not value:
        raise ValueError("capabilities must be a non-empty tuple")
    return tuple(sorted({_text(item, "capability").upper() for item in value}))


class ProtectionCapabilityStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    UNSUPPORTED = "UNSUPPORTED"
    VERIFIED_SUPPORTED = "VERIFIED_SUPPORTED"


@dataclass(frozen=True, slots=True)
class ProtectionCapabilityEvidence:
    evidence_id: str
    version: str
    observed_at: datetime
    supported_capabilities: tuple[str, ...]
    verified: bool
    source_ref: str
    ownership_verified: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _text(self.evidence_id, "evidence_id"))
        object.__setattr__(self, "version", _text(self.version, "version"))
        object.__setattr__(self, "observed_at", _aware(self.observed_at, "observed_at"))
        object.__setattr__(self, "supported_capabilities", _caps(self.supported_capabilities))
        if not isinstance(self.verified, bool):
            raise TypeError("verified must be bool")
        if not isinstance(self.ownership_verified, bool):
            raise TypeError("ownership_verified must be bool")
        object.__setattr__(self, "source_ref", _text(self.source_ref, "source_ref"))

    @property
    def reference(self) -> str:
        return f"{self.evidence_id}@{self.version}"


@dataclass(frozen=True, slots=True)
class ProtectionCapabilityDecision:
    status: ProtectionCapabilityStatus
    requirement_ref: str
    evidence_ref: str | None
    missing_capabilities: tuple[str, ...]
    disarmed_required: bool
    existing_protection_observed: bool
    existing_protection_adopted: bool


def evaluate_required_protection(
    *,
    requirement_ref: str,
    required_capabilities: tuple[str, ...],
    evidence: ProtectionCapabilityEvidence | None,
    existing_protection_observed: bool = False,
) -> ProtectionCapabilityDecision:
    requirement = _text(requirement_ref, "requirement_ref")
    required = _caps(required_capabilities)
    if not isinstance(existing_protection_observed, bool):
        raise TypeError("existing_protection_observed must be bool")

    if evidence is None or not isinstance(evidence, ProtectionCapabilityEvidence) or not evidence.verified:
        return ProtectionCapabilityDecision(
            status=ProtectionCapabilityStatus.UNVERIFIED,
            requirement_ref=requirement,
            evidence_ref=evidence.reference if isinstance(evidence, ProtectionCapabilityEvidence) else None,
            missing_capabilities=required,
            disarmed_required=True,
            existing_protection_observed=existing_protection_observed,
            existing_protection_adopted=False,
        )

    missing = tuple(item for item in required if item not in evidence.supported_capabilities)
    status = (
        ProtectionCapabilityStatus.UNSUPPORTED
        if missing
        else ProtectionCapabilityStatus.VERIFIED_SUPPORTED
    )
    return ProtectionCapabilityDecision(
        status=status,
        requirement_ref=requirement,
        evidence_ref=evidence.reference,
        missing_capabilities=missing,
        disarmed_required=True,
        existing_protection_observed=existing_protection_observed,
        existing_protection_adopted=(
            existing_protection_observed and evidence.ownership_verified
        ),
    )


__all__ = [
    "ProtectionCapabilityDecision",
    "ProtectionCapabilityEvidence",
    "ProtectionCapabilityStatus",
    "evaluate_required_protection",
]
