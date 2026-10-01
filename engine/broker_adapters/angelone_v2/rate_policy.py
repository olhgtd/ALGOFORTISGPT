"""Versioned broker-rate policy seam for Phase-6 read-only qualification.

No production rate values are defined here. Callers must inject an explicit,
versioned policy; absence or a missing class fails closed.
"""

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


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


class BrokerRateClass(str, Enum):
    AUTH_SESSION = "AUTH_SESSION"
    READ_ORDERS = "READ_ORDERS"
    READ_ACCOUNT = "READ_ACCOUNT"
    FUTURE_MUTATION = "FUTURE_MUTATION"


@dataclass(frozen=True, slots=True)
class BrokerRateRule:
    max_requests: int
    window_seconds: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_requests", _positive_int(self.max_requests, "max_requests"))
        object.__setattr__(self, "window_seconds", _positive_int(self.window_seconds, "window_seconds"))


@dataclass(frozen=True, slots=True)
class BrokerRatePolicy:
    policy_id: str
    version: str
    rules: Mapping[BrokerRateClass, BrokerRateRule]
    test_only: bool = False

    def __post_init__(self) -> None:
        policy_id = _text(self.policy_id, "policy_id")
        version = _text(self.version, "version")
        if not isinstance(self.test_only, bool):
            raise TypeError("test_only must be bool")
        if self.test_only and not policy_id.startswith("TEST_ONLY/"):
            raise ValueError("TEST_ONLY policy_id must start with TEST_ONLY/")
        if not self.test_only and policy_id.startswith("TEST_ONLY/"):
            raise ValueError("TEST_ONLY policy_id requires test_only=True")
        if not isinstance(self.rules, Mapping):
            raise TypeError("rules must be a mapping")
        normalized: dict[BrokerRateClass, BrokerRateRule] = {}
        for key, rule in self.rules.items():
            if not isinstance(key, BrokerRateClass):
                raise TypeError("rate policy keys must be BrokerRateClass")
            if not isinstance(rule, BrokerRateRule):
                raise TypeError("rate policy values must be BrokerRateRule")
            normalized[key] = rule
        object.__setattr__(self, "policy_id", policy_id)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "rules", MappingProxyType(normalized))

    @property
    def reference(self) -> str:
        return f"{self.policy_id}@{self.version}"


@dataclass(frozen=True, slots=True)
class BrokerRateDecision:
    rate_class: BrokerRateClass
    allowed: bool
    retry_unbounded: bool
    reason: str
    policy_ref: str | None
    observed_requests: int


def evaluate_rate(
    policy: BrokerRatePolicy | None,
    rate_class: BrokerRateClass,
    *,
    observed_requests: int,
) -> BrokerRateDecision:
    if not isinstance(rate_class, BrokerRateClass):
        raise TypeError("rate_class must be BrokerRateClass")
    observed = _non_negative_int(observed_requests, "observed_requests")
    if policy is None:
        return BrokerRateDecision(rate_class, False, False, "MISSING_RATE_POLICY", None, observed)
    if not isinstance(policy, BrokerRatePolicy):
        raise TypeError("policy must be BrokerRatePolicy or None")
    rule = policy.rules.get(rate_class)
    if rule is None:
        return BrokerRateDecision(
            rate_class, False, False, "MISSING_RATE_CLASS_RULE", policy.reference, observed
        )
    allowed = observed < rule.max_requests
    return BrokerRateDecision(
        rate_class=rate_class,
        allowed=allowed,
        retry_unbounded=False,
        reason="BELOW_RATE_LIMIT" if allowed else "RATE_LIMIT_REACHED",
        policy_ref=policy.reference,
        observed_requests=observed,
    )


__all__ = [
    "BrokerRateClass",
    "BrokerRateRule",
    "BrokerRatePolicy",
    "BrokerRateDecision",
    "evaluate_rate",
]
