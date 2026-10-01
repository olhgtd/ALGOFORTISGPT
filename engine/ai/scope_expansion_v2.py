from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ScopeExpansionType(str, Enum):
    INSTRUMENT = "INSTRUMENT"
    TIMEFRAME = "TIMEFRAME"
    FREQUENCY = "FREQUENCY"
    DATA_SOURCE = "DATA_SOURCE"
    TASK_CLASS = "TASK_CLASS"
    PROVIDER_USAGE = "PROVIDER_USAGE"


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _aware(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class ScopeExpansionRequest:
    """Pending evidence only; it cannot approve/apply its own scope expansion."""

    request_id: str
    requested_by: str
    expansion_type: ScopeExpansionType
    requested_value: str
    reason_ref: str
    requested_at: datetime
    policy_ref: str
    status: str = "PENDING_OWNER_REVIEW"

    def __post_init__(self) -> None:
        for field in ("request_id", "requested_by", "requested_value", "reason_ref", "policy_ref"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        if not isinstance(self.expansion_type, ScopeExpansionType):
            raise TypeError("expansion_type must be ScopeExpansionType")
        _aware(self.requested_at, "requested_at")
        if self.status != "PENDING_OWNER_REVIEW":
            raise ValueError("ScopeExpansionRequest status is fixed to PENDING_OWNER_REVIEW")


__all__ = ["ScopeExpansionRequest", "ScopeExpansionType"]
