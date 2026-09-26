"""Versioned, durable, flow-isolated S2 rate limiting.

Production thresholds are supplied by policy. This module does not invent
production values; tests may use explicit TEST_ONLY policies.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Mapping
from uuid import UUID

from .repository import AccountAuthorityRepository


class RateLimitFlow(str, Enum):
    LOGIN = "LOGIN"
    DEVICE_PROOF = "DEVICE_PROOF"
    REFRESH_MISUSE = "REFRESH_MISUSE"
    RECOVERY = "RECOVERY"
    EXPENSIVE_OPERATION = "EXPENSIVE_OPERATION"


@dataclass(frozen=True, slots=True)
class RateLimitRule:
    max_failures: int
    cooldown_seconds: int

    def __post_init__(self) -> None:
        if self.max_failures < 1 or self.cooldown_seconds < 1:
            raise ValueError("rate-limit rule must be explicit and positive")


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    policy_id: str
    version: str
    test_only: bool
    rules: Mapping[RateLimitFlow, RateLimitRule]

    def rule_for(self, flow: RateLimitFlow) -> RateLimitRule:
        try:
            return self.rules[flow]
        except KeyError as exc:
            raise ValueError(f"rate-limit policy missing flow {flow.value}") from exc


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    locked: bool
    remaining_seconds: int
    failure_count: int


class DurableRateLimitService:
    def __init__(self, repository: AccountAuthorityRepository, policy: RateLimitPolicy) -> None:
        self._repository = repository
        self._policy = policy

    def is_locked(
        self,
        *,
        user_id: UUID,
        flow: RateLimitFlow,
        subject_key: str,
        now: datetime,
    ) -> RateLimitDecision:
        state = self._repository.get_rate_limit_state(
            user_id=user_id,
            flow=flow.value,
            subject_key=subject_key,
        )
        if state is None:
            return RateLimitDecision(False, 0, 0)
        if state.locked_until is not None and now < state.locked_until:
            remaining = max(1, int((state.locked_until - now).total_seconds()))
            return RateLimitDecision(True, remaining, state.failure_count)
        return RateLimitDecision(False, 0, state.failure_count)

    def record_failure(
        self,
        *,
        user_id: UUID,
        flow: RateLimitFlow,
        subject_key: str,
        now: datetime,
    ) -> RateLimitDecision:
        rule = self._policy.rule_for(flow)
        state = self._repository.record_rate_limit_failure(
            user_id=user_id,
            flow=flow.value,
            subject_key=subject_key,
            max_failures=rule.max_failures,
            cooldown_seconds=rule.cooldown_seconds,
            now=now,
        )
        if state.locked_until is None or now >= state.locked_until:
            return RateLimitDecision(False, 0, state.failure_count)
        remaining = max(1, int((state.locked_until - now).total_seconds()))
        return RateLimitDecision(True, remaining, state.failure_count)

    def record_success(
        self,
        *,
        user_id: UUID,
        flow: RateLimitFlow,
        subject_key: str,
    ) -> None:
        self._repository.clear_rate_limit_state(
            user_id=user_id,
            flow=flow.value,
            subject_key=subject_key,
        )
