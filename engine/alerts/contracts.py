"""Pure Phase-5 alert contracts.

This module carries only redacted alert metadata and adapter Protocols. It has
no broker, live-arm, network, persistence, or OS dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from engine.paper.contracts_v2 import (
    AlertDeliveryRecord,
    FailureSeverity,
    PaperOperationalState,
)


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


@dataclass(frozen=True, slots=True)
class AlertEnvelope:
    alert_id: str
    incident_id: str
    severity: FailureSeverity
    incident_type: str
    session_ref: str
    occurred_at: datetime
    safety_state: PaperOperationalState
    required_action: str
    safe_detail: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "alert_id", _text(self.alert_id, "alert_id"))
        object.__setattr__(self, "incident_id", _text(self.incident_id, "incident_id"))
        if not isinstance(self.severity, FailureSeverity):
            raise TypeError("severity must be FailureSeverity")
        object.__setattr__(self, "incident_type", _text(self.incident_type, "incident_type"))
        object.__setattr__(self, "session_ref", _text(self.session_ref, "session_ref"))
        object.__setattr__(self, "occurred_at", _aware(self.occurred_at, "occurred_at"))
        if not isinstance(self.safety_state, PaperOperationalState):
            raise TypeError("safety_state must be PaperOperationalState")
        object.__setattr__(self, "required_action", _text(self.required_action, "required_action"))
        object.__setattr__(self, "safe_detail", _text(self.safe_detail, "safe_detail"))


class AlertAdapter(Protocol):
    channel: str

    def deliver(self, envelope: AlertEnvelope) -> AlertDeliveryRecord:
        """Attempt one delivery and return auditable evidence."""


__all__ = ["AlertAdapter", "AlertDeliveryRecord", "AlertEnvelope"]
