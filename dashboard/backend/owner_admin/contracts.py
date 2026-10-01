"""Typed Owner/Admin authority-truth contracts.

These values describe evidence availability for governance presentation only.
They intentionally contain no trading, broker, order-approval, or Live-arm fields.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping


class AuthorityState(str, Enum):
    AVAILABLE = "AVAILABLE"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"


def authority_state_from_source(*, source: str, trust: str) -> AuthorityState:
    source_key = (source or "").upper()
    trust_key = (trust or "").upper()
    if source_key == "UNAVAILABLE":
        return AuthorityState.UNAVAILABLE
    if source_key != "BACKEND":
        return AuthorityState.UNKNOWN
    if trust_key == "FRESH":
        return AuthorityState.AVAILABLE
    if trust_key == "STALE":
        return AuthorityState.STALE
    return AuthorityState.UNKNOWN


@dataclass(frozen=True, slots=True)
class AuthorityEnvelope:
    state: AuthorityState
    source: str
    as_of: datetime
    payload: Mapping[str, Any]
    reason: str | None = None
    evidence_ref: str | None = None

    def authoritative_value(self, key: str) -> Any | None:
        """Return a value only when its source is explicitly AVAILABLE.

        This prevents missing/unavailable authority from being rendered as a
        valid numeric zero, empty-safe state, PASS, or healthy condition.
        """
        if self.state is not AuthorityState.AVAILABLE:
            return None
        return self.payload.get(key)
