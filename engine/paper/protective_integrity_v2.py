"""Independent protective-integrity gate for Phase-5 recovery."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from engine.paper.contracts_v2 import PaperPositionRecord


class ProtectiveIntegrityVerdict(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    UNCERTAIN = "UNCERTAIN"


@dataclass(frozen=True, slots=True)
class ProtectiveIntegrityResult:
    verdict: ProtectiveIntegrityVerdict
    reason: str
    entry_eligible: bool
    action: str


class ProtectiveIntegrityChecker:
    def check(
        self,
        position: PaperPositionRecord,
        *,
        policy_ref: str | None,
        observed_state: str | None,
    ) -> ProtectiveIntegrityResult:
        if not isinstance(position, PaperPositionRecord):
            raise TypeError("position must be PaperPositionRecord")
        if policy_ref is None or not str(policy_ref).strip():
            return ProtectiveIntegrityResult(
                ProtectiveIntegrityVerdict.UNCERTAIN,
                "MISSING_PROTECTIVE_POLICY",
                False,
                "HALT_ENTRIES",
            )
        policy_ref = str(policy_ref).strip()
        if policy_ref != position.protective_policy_ref:
            return ProtectiveIntegrityResult(
                ProtectiveIntegrityVerdict.INVALID,
                "PROTECTIVE_POLICY_MISMATCH",
                False,
                "HALT_ENTRIES",
            )
        state = "" if observed_state is None else str(observed_state).strip().upper()
        if state != "VALID" or position.protective_state.strip().upper() != "VALID":
            return ProtectiveIntegrityResult(
                ProtectiveIntegrityVerdict.INVALID,
                "PROTECTIVE_STATE_INVALID",
                False,
                "HALT_ENTRIES",
            )
        return ProtectiveIntegrityResult(
            ProtectiveIntegrityVerdict.VALID,
            "PROTECTIVE_STATE_VALID",
            True,
            "NONE",
        )


__all__ = [
    "ProtectiveIntegrityVerdict",
    "ProtectiveIntegrityResult",
    "ProtectiveIntegrityChecker",
]
