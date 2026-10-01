"""Required S2 security-audit contracts.

Security-critical mutations use an intent-first audit boundary.  A missing or
failed required audit write is a hard failure and the mutation must not start.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


class RequiredAuditSink(Protocol):
    def record_required_intent(self, **kwargs) -> str: ...


@dataclass(frozen=True, slots=True)
class SecurityAuditIntent:
    user_id: UUID
    action: str
    resource_ref: str | None
    occurred_at: datetime
