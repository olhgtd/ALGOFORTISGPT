from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re

from engine.ai.v2.contracts import AIContractError, DataClass
from engine.data.licensing import DataLicenceMetadata

_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
STRATEGY_HUNTING_DATA_CLASS = DataClass.STRATEGY_RESEARCH


def _text(v: object, n: str) -> str:
    if not isinstance(v, str) or not v.strip():
        raise AIContractError(f"{n} must be non-empty")
    return v.strip()


def _aware(v: datetime, n: str) -> datetime:
    if not isinstance(v, datetime) or v.tzinfo is None or v.utcoffset() is None:
        raise AIContractError(f"{n} must be timezone-aware")
    return v


@dataclass(frozen=True, slots=True)
class ProviderDataPolicy:
    policy_id: str
    provider_id: str
    version: str
    allowed_data_classes: tuple[DataClass, ...]

    def __post_init__(self):
        object.__setattr__(self, "policy_id", _text(self.policy_id, "policy_id"))
        object.__setattr__(self, "provider_id", _text(self.provider_id, "provider_id"))
        version = _text(self.version, "version")
        if _SEMVER.fullmatch(version) is None:
            raise AIContractError("version must be semantic version")
        if (
            not isinstance(self.allowed_data_classes, tuple)
            or not self.allowed_data_classes
            or any(not isinstance(x, DataClass) for x in self.allowed_data_classes)
        ):
            raise AIContractError("allowed_data_classes must be non-empty DataClass tuple")
        if len(set(self.allowed_data_classes)) != len(self.allowed_data_classes):
            raise AIContractError("allowed_data_classes must be unique")

    def allows(self, data_class: DataClass) -> bool:
        return isinstance(data_class, DataClass) and data_class in self.allowed_data_classes


@dataclass(frozen=True, slots=True)
class DataProvenanceEvidence:
    evidence_ref: str
    metadata: DataLicenceMetadata
    observed_at: datetime
    valid_until: datetime
    ambiguous: bool = False

    def __post_init__(self):
        object.__setattr__(self, "evidence_ref", _text(self.evidence_ref, "evidence_ref"))
        if not isinstance(self.metadata, DataLicenceMetadata):
            raise AIContractError("metadata must be DataLicenceMetadata")
        observed = _aware(self.observed_at, "observed_at")
        valid = _aware(self.valid_until, "valid_until")
        if valid <= observed:
            raise AIContractError("valid_until must be after observed_at")
        if not isinstance(self.ambiguous, bool):
            raise AIContractError("ambiguous must be bool")


__all__ = [
    "DataProvenanceEvidence",
    "ProviderDataPolicy",
    "STRATEGY_HUNTING_DATA_CLASS",
]
