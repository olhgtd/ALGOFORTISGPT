"""Versioned, evidence-driven failure-storm policy for Phase-5 Paper.

No production trigger count/window is defined in this module. Callers must
supply a frozen policy; absence fails closed through MissingStormPolicyDecision.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.paper.contracts_v2 import PaperOperationalState


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


@dataclass(frozen=True, slots=True)
class FailureStormPolicy:
    policy_id: str
    version: str
    failure_class: str
    observation_window_ms: int
    trigger_count: int
    cooldown_ms: int
    escalation_action: str
    reset_rule: str
    test_only: bool = False

    def __post_init__(self) -> None:
        policy_id = _text(self.policy_id, "policy_id")
        version = _text(self.version, "version")
        failure_class = _text(self.failure_class, "failure_class").upper()
        escalation = _text(self.escalation_action, "escalation_action").upper()
        reset = _text(self.reset_rule, "reset_rule").upper()
        if not isinstance(self.test_only, bool):
            raise TypeError("test_only must be bool")
        if self.test_only and not policy_id.startswith("TEST_ONLY/"):
            raise ValueError("TEST_ONLY policy_id must start with TEST_ONLY/")
        if escalation != "HALT_ENTRIES":
            raise ValueError("Phase-5 storm escalation_action must be HALT_ENTRIES")
        if reset != "WINDOW_AND_COOLDOWN":
            raise ValueError("Phase-5 reset_rule must be WINDOW_AND_COOLDOWN")
        object.__setattr__(self, "policy_id", policy_id)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "failure_class", failure_class)
        object.__setattr__(self, "observation_window_ms", _positive_int(self.observation_window_ms, "observation_window_ms"))
        object.__setattr__(self, "trigger_count", _positive_int(self.trigger_count, "trigger_count"))
        object.__setattr__(self, "cooldown_ms", _non_negative_int(self.cooldown_ms, "cooldown_ms"))
        object.__setattr__(self, "escalation_action", escalation)
        object.__setattr__(self, "reset_rule", reset)

    @property
    def reference(self) -> str:
        return f"{self.policy_id}@{self.version}"


@dataclass(frozen=True, slots=True)
class StormDecision:
    failure_class: str
    observed_count: int
    halt: bool
    resulting_state: PaperOperationalState
    reason: str
    policy_ref: str


@dataclass(frozen=True, slots=True)
class MissingStormPolicyDecision:
    failure_class: str
    retry_unbounded: bool
    halt: bool
    resulting_state: PaperOperationalState
    reason: str

    @classmethod
    def for_failure(cls, failure_class: str) -> "MissingStormPolicyDecision":
        return cls(
            failure_class=_text(failure_class, "failure_class").upper(),
            retry_unbounded=False,
            halt=True,
            resulting_state=PaperOperationalState.HALTED,
            reason="MISSING_STORM_POLICY",
        )


class StormEvaluator:
    def __init__(self, policy: FailureStormPolicy) -> None:
        if not isinstance(policy, FailureStormPolicy):
            raise TypeError("policy must be FailureStormPolicy")
        self._policy = policy
        self._observations: list[int] = []
        self._last_observed_ms: int | None = None
        self._threshold_crossed_at_ms: int | None = None

    @property
    def policy_ref(self) -> str:
        return self._policy.reference

    def observe(self, failure_class: str, occurred_at_ms: int) -> StormDecision:
        failure_class = _text(failure_class, "failure_class").upper()
        if failure_class != self._policy.failure_class:
            raise ValueError("failure_class does not match policy")
        occurred_at_ms = _non_negative_int(occurred_at_ms, "occurred_at_ms")
        if self._last_observed_ms is not None and occurred_at_ms < self._last_observed_ms:
            raise ValueError("occurred_at_ms must be monotonic")
        self._last_observed_ms = occurred_at_ms

        lower_bound = occurred_at_ms - self._policy.observation_window_ms
        prior_observations = [
            timestamp for timestamp in self._observations if timestamp >= lower_bound
        ]

        if self._threshold_crossed_at_ms is not None:
            cooldown_elapsed = (
                occurred_at_ms - self._threshold_crossed_at_ms
                >= self._policy.cooldown_ms
            )
            quiet_window = not prior_observations
            if cooldown_elapsed and quiet_window:
                self._threshold_crossed_at_ms = None
                self._observations = []
            else:
                self._observations = prior_observations + [occurred_at_ms]
                return StormDecision(
                    failure_class=failure_class,
                    observed_count=len(self._observations),
                    halt=True,
                    resulting_state=PaperOperationalState.HALTED,
                    reason=(
                        "STORM_COOLDOWN_ACTIVE"
                        if not cooldown_elapsed
                        else "STORM_RESET_WAITING_FOR_QUIET_WINDOW"
                    ),
                    policy_ref=self._policy.reference,
                )

        self._observations = prior_observations + [occurred_at_ms]
        count = len(self._observations)
        halt = count >= self._policy.trigger_count
        if halt:
            self._threshold_crossed_at_ms = occurred_at_ms
        return StormDecision(
            failure_class=failure_class,
            observed_count=count,
            halt=halt,
            resulting_state=(
                PaperOperationalState.HALTED if halt else PaperOperationalState.DEGRADED
            ),
            reason="STORM_THRESHOLD_CROSSED" if halt else "BELOW_STORM_THRESHOLD",
            policy_ref=self._policy.reference,
        )


__all__ = [
    "FailureStormPolicy",
    "StormDecision",
    "MissingStormPolicyDecision",
    "StormEvaluator",
]
