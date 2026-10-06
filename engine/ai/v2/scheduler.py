"""Bounded intelligence scheduler for AI/Laya market monitoring and research.

The scheduler has no broker mutation or execution authority.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Protocol


class SchedulerError(ValueError):
    pass


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchedulerError(f"{name} must be a non-empty string")
    return value.strip()


def _aware(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise SchedulerError(f"{name} must be timezone-aware datetime")
    return value


class ResearchJobKind(str, Enum):
    RESEARCH = "RESEARCH"
    INTELLIGENCE = "INTELLIGENCE"


class SchedulerRejectReason(str, Enum):
    STALE_INPUT = "STALE_INPUT"
    PROVIDER_BUDGET_EXHAUSTED = "PROVIDER_BUDGET_EXHAUSTED"
    TOOL_BUDGET_EXHAUSTED = "TOOL_BUDGET_EXHAUSTED"
    QUEUE_FULL = "QUEUE_FULL"
    CONCURRENCY_FULL = "CONCURRENCY_FULL"


@dataclass(frozen=True, slots=True)
class SchedulerPolicy:
    policy_ref: str
    max_queue: int
    max_concurrency: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_ref", _text(self.policy_ref, "policy_ref"))
        for name in ("max_queue", "max_concurrency"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise SchedulerError(f"{name} must be positive integer")


@dataclass(frozen=True, slots=True)
class ResearchJob:
    job_id: str
    kind: ResearchJobKind
    created_at: datetime
    input_valid_until: datetime
    payload_ref: str
    provider_policy_ref: str
    tool_policy_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "job_id", _text(self.job_id, "job_id"))
        if not isinstance(self.kind, ResearchJobKind):
            raise SchedulerError("kind must be ResearchJobKind")
        object.__setattr__(self, "created_at", _aware(self.created_at, "created_at"))
        object.__setattr__(self, "input_valid_until", _aware(self.input_valid_until, "input_valid_until"))
        object.__setattr__(self, "payload_ref", _text(self.payload_ref, "payload_ref"))
        object.__setattr__(self, "provider_policy_ref", _text(self.provider_policy_ref, "provider_policy_ref"))
        object.__setattr__(self, "tool_policy_ref", _text(self.tool_policy_ref, "tool_policy_ref"))


@dataclass(frozen=True, slots=True)
class SubmitDecision:
    accepted: bool
    reason: SchedulerRejectReason | None


@dataclass(frozen=True, slots=True)
class DispatchResult:
    dispatched: bool
    job_id: str | None
    reason: SchedulerRejectReason | None = None


class Clock(Protocol):
    def now(self) -> datetime: ...


class BudgetGate(Protocol):
    def allows(self, job: ResearchJob) -> bool: ...


class MarketIntelligenceScheduler:
    def __init__(self, *, clock: Clock, policy: SchedulerPolicy, provider_budget: BudgetGate, tool_budget: BudgetGate, dispatch: Callable[[ResearchJob], object]) -> None:
        if not isinstance(policy, SchedulerPolicy):
            raise SchedulerError("policy must be SchedulerPolicy")
        if not callable(getattr(clock, "now", None)):
            raise SchedulerError("clock must provide now()")
        if not callable(getattr(provider_budget, "allows", None)):
            raise SchedulerError("provider_budget must provide allows(job)")
        if not callable(getattr(tool_budget, "allows", None)):
            raise SchedulerError("tool_budget must provide allows(job)")
        if not callable(dispatch):
            raise SchedulerError("dispatch must be callable")
        self._clock = clock
        self._policy = policy
        self._provider_budget = provider_budget
        self._tool_budget = tool_budget
        self._dispatch = dispatch
        self._queue: deque[ResearchJob] = deque()
        self._in_flight = 0

    def submit(self, job: ResearchJob) -> SubmitDecision:
        if not isinstance(job, ResearchJob):
            raise SchedulerError("job must be ResearchJob")
        now = _aware(self._clock.now(), "clock.now()")
        if now >= job.input_valid_until:
            return SubmitDecision(False, SchedulerRejectReason.STALE_INPUT)
        if not bool(self._provider_budget.allows(job)):
            return SubmitDecision(False, SchedulerRejectReason.PROVIDER_BUDGET_EXHAUSTED)
        if not bool(self._tool_budget.allows(job)):
            return SubmitDecision(False, SchedulerRejectReason.TOOL_BUDGET_EXHAUSTED)
        if len(self._queue) >= self._policy.max_queue:
            return SubmitDecision(False, SchedulerRejectReason.QUEUE_FULL)
        self._queue.append(job)
        return SubmitDecision(True, None)

    def run_next(self) -> DispatchResult:
        if self._in_flight >= self._policy.max_concurrency:
            return DispatchResult(False, None, SchedulerRejectReason.CONCURRENCY_FULL)
        if not self._queue:
            return DispatchResult(False, None, None)
        job = self._queue.popleft()
        now = _aware(self._clock.now(), "clock.now()")
        if now >= job.input_valid_until:
            return DispatchResult(False, job.job_id, SchedulerRejectReason.STALE_INPUT)
        if not bool(self._provider_budget.allows(job)):
            return DispatchResult(False, job.job_id, SchedulerRejectReason.PROVIDER_BUDGET_EXHAUSTED)
        if not bool(self._tool_budget.allows(job)):
            return DispatchResult(False, job.job_id, SchedulerRejectReason.TOOL_BUDGET_EXHAUSTED)
        self._in_flight += 1
        try:
            self._dispatch(job)
        finally:
            self._in_flight -= 1
        return DispatchResult(True, job.job_id, None)


__all__ = [
    "SchedulerError", "ResearchJobKind", "SchedulerRejectReason", "SchedulerPolicy",
    "ResearchJob", "SubmitDecision", "DispatchResult", "MarketIntelligenceScheduler",
]
