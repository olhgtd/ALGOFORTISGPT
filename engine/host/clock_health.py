"""Injectable, versioned clock-health policy for Phase-5 host safety.

No production drift threshold is defined here. Callers must supply an explicit
versioned policy; missing or unknown policy references fail closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


@dataclass(frozen=True, slots=True)
class ClockHealthPolicy:
    policy_id: str
    version: str
    max_abs_drift_ms: int
    test_only: bool = False

    def __post_init__(self) -> None:
        policy_id = _require_text(self.policy_id, "policy_id")
        version = _require_text(self.version, "version")
        if not isinstance(self.test_only, bool):
            raise TypeError("test_only must be bool")
        if self.test_only and not policy_id.startswith("TEST_ONLY/"):
            raise ValueError("TEST_ONLY policy_id must start with TEST_ONLY/")
        object.__setattr__(self, "policy_id", policy_id)
        object.__setattr__(self, "version", version)
        object.__setattr__(
            self,
            "max_abs_drift_ms",
            _non_negative_int(self.max_abs_drift_ms, "max_abs_drift_ms"),
        )

    @property
    def reference(self) -> str:
        return f"{self.policy_id}@{self.version}"


@dataclass(frozen=True, slots=True)
class ClockHealthResult:
    healthy: bool
    entry_eligible: bool
    reason: str
    policy_ref: str | None
    observed_drift_ms: int | None


class ClockDriftSource(Protocol):
    def observed_drift_ms(self) -> int: ...


class ClockHealthProvider:
    """Evaluates injected drift evidence against an injected versioned policy."""

    def __init__(
        self,
        *,
        policies: Mapping[str, ClockHealthPolicy],
        drift_source: ClockDriftSource,
    ) -> None:
        if drift_source is None:
            raise TypeError("drift_source is required")
        normalized: dict[str, ClockHealthPolicy] = {}
        for reference, policy in dict(policies).items():
            if not isinstance(policy, ClockHealthPolicy):
                raise TypeError("clock policies must be ClockHealthPolicy")
            if reference != policy.reference:
                raise ValueError("clock policy mapping key must equal policy.reference")
            normalized[reference] = policy
        self._policies = normalized
        self._drift_source = drift_source

    def check(self, policy_ref: str | None) -> ClockHealthResult:
        if policy_ref is None or not isinstance(policy_ref, str) or not policy_ref.strip():
            return ClockHealthResult(
                healthy=False,
                entry_eligible=False,
                reason="MISSING_CLOCK_POLICY",
                policy_ref=None,
                observed_drift_ms=None,
            )
        reference = policy_ref.strip()
        policy = self._policies.get(reference)
        if policy is None:
            return ClockHealthResult(
                healthy=False,
                entry_eligible=False,
                reason="UNKNOWN_CLOCK_POLICY",
                policy_ref=reference,
                observed_drift_ms=None,
            )
        drift = self._drift_source.observed_drift_ms()
        if isinstance(drift, bool) or not isinstance(drift, int):
            return ClockHealthResult(
                healthy=False,
                entry_eligible=False,
                reason="INVALID_CLOCK_OBSERVATION",
                policy_ref=reference,
                observed_drift_ms=None,
            )
        healthy = abs(drift) <= policy.max_abs_drift_ms
        return ClockHealthResult(
            healthy=healthy,
            entry_eligible=healthy,
            reason="CLOCK_HEALTHY" if healthy else "CLOCK_DRIFT_EXCEEDED",
            policy_ref=reference,
            observed_drift_ms=drift,
        )


__all__ = [
    "ClockDriftSource",
    "ClockHealthPolicy",
    "ClockHealthProvider",
    "ClockHealthResult",
]
