"""Phase-5 paper session/expiry validity policy boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SessionValidityResult:
    allowed: bool
    reason: str
    action: str
    auto_flatten: bool


class SessionValidityEvaluator:
    """Validate boundary eligibility without executing any expiry action."""

    def evaluate(
        self,
        *,
        instrument: str,
        expiry_at: datetime | None,
        now: datetime,
        has_open_position: bool,
        request_new_entry: bool,
        expiry_policy_ref: str | None,
    ) -> SessionValidityResult:
        if not isinstance(instrument, str) or not instrument.strip():
            raise ValueError("instrument must be non-empty")
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        if expiry_at is not None and (
            not isinstance(expiry_at, datetime)
            or expiry_at.tzinfo is None
            or expiry_at.utcoffset() is None
        ):
            raise ValueError("expiry_at must be timezone-aware when supplied")
        if not isinstance(has_open_position, bool) or not isinstance(request_new_entry, bool):
            raise TypeError("position/entry flags must be bool")

        if expiry_at is None or now < expiry_at:
            return SessionValidityResult(True, "SESSION_VALID", "NONE", False)

        # An expired contract is never eligible for a fresh entry, regardless of
        # whether a versioned close/settlement policy exists.
        if request_new_entry:
            return SessionValidityResult(
                False,
                "EXPIRED_CONTRACT_NEW_ENTRY",
                "HALT_ENTRIES",
                False,
            )

        if has_open_position:
            if expiry_policy_ref is None or not str(expiry_policy_ref).strip():
                return SessionValidityResult(
                    False,
                    "MISSING_EXPIRY_POLICY",
                    "HALT_ENTRIES",
                    False,
                )
            # This evaluator only validates that an explicit versioned policy
            # exists. It never interprets that reference as permission to
            # silently carry or auto-flatten a position.
            return SessionValidityResult(
                True,
                "VERSIONED_EXPIRY_POLICY_REQUIRED",
                "APPLY_VERSIONED_EXPIRY_POLICY",
                False,
            )

        return SessionValidityResult(True, "SESSION_VALID", "NONE", False)


__all__ = ["SessionValidityResult", "SessionValidityEvaluator"]
