"""Immutable contracts for the Phase-6 Angel One read-only boundary.

These types carry configuration/evidence only. They intentionally define no
arming, order approval, or broker mutation capability.
"""

from dataclasses import dataclass
from datetime import datetime


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


def _text_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not value:
        raise ValueError(f"{field} must be a non-empty tuple")
    return tuple(_text(item, field) for item in value)


@dataclass(frozen=True, slots=True)
class AngelOneBrokerProfile:
    profile_id: str
    version: str
    api_base_url: str
    documentation_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile_id", _text(self.profile_id, "profile_id"))
        object.__setattr__(self, "version", _text(self.version, "version"))
        base = _text(self.api_base_url, "api_base_url")
        if not base.startswith("https://"):
            raise ValueError("api_base_url must use https")
        object.__setattr__(self, "api_base_url", base.rstrip("/"))
        object.__setattr__(self, "documentation_ref", _text(self.documentation_ref, "documentation_ref"))

    @property
    def reference(self) -> str:
        return f"{self.profile_id}@{self.version}"


@dataclass(frozen=True, slots=True)
class AngelOneCredentialRef:
    secret_ref: str
    account_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "secret_ref", _text(self.secret_ref, "secret_ref"))
        object.__setattr__(self, "account_ref", _text(self.account_ref, "account_ref"))


@dataclass(frozen=True, slots=True)
class AngelOneReadOnlyCapability:
    capability_id: str
    evidence_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "capability_id", _text(self.capability_id, "capability_id"))
        object.__setattr__(self, "evidence_ref", _text(self.evidence_ref, "evidence_ref"))


@dataclass(frozen=True, slots=True)
class BrokerRuleEvidenceRef:
    evidence_id: str
    version: str
    reviewed_at: datetime
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _text(self.evidence_id, "evidence_id"))
        object.__setattr__(self, "version", _text(self.version, "version"))
        object.__setattr__(self, "reviewed_at", _aware(self.reviewed_at, "reviewed_at"))
        object.__setattr__(self, "source_refs", _text_tuple(self.source_refs, "source_refs"))

    @property
    def reference(self) -> str:
        return f"{self.evidence_id}@{self.version}"


@dataclass(frozen=True, slots=True)
class AngelOneReadOnlyHealth:
    session_state: str
    broker_truth_available: bool
    profile_ref: str
    rule_evidence_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_state", _text(self.session_state, "session_state"))
        if not isinstance(self.broker_truth_available, bool):
            raise TypeError("broker_truth_available must be bool")
        object.__setattr__(self, "profile_ref", _text(self.profile_ref, "profile_ref"))
        object.__setattr__(self, "rule_evidence_ref", _text(self.rule_evidence_ref, "rule_evidence_ref"))


__all__ = [
    "AngelOneBrokerProfile",
    "AngelOneCredentialRef",
    "AngelOneReadOnlyCapability",
    "BrokerRuleEvidenceRef",
    "AngelOneReadOnlyHealth",
]
