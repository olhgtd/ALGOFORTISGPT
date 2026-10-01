"""Bounded deterministic queue for scheduler-authorized AI provider jobs.

Provider pressure may delay valid work, but it cannot create parallel bypass
calls, widen task scope, or silently fall back to another provider.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .monitoring_scheduler_v2 import MonitoringTaskV2


class AIProviderQueueFull(RuntimeError):
    """Raised when bounded provider queue capacity is exhausted."""


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _aware(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be int")
    if value <= 0:
        raise ValueError(f"{field} must be positive")
    return value


def _non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be int")
    if value < 0:
        raise ValueError(f"{field} must be non-negative")
    return value


@dataclass(frozen=True, slots=True)
class ProviderQueuePolicyV2:
    policy_ref: str
    provider_id: str
    max_concurrency: int
    max_queue_size: int
    retry_after_seconds: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_ref", _text(self.policy_ref, "policy_ref"))
        object.__setattr__(self, "provider_id", _text(self.provider_id, "provider_id"))
        object.__setattr__(self, "max_concurrency", _positive_int(self.max_concurrency, "max_concurrency"))
        object.__setattr__(self, "max_queue_size", _positive_int(self.max_queue_size, "max_queue_size"))
        object.__setattr__(self, "retry_after_seconds", _non_negative_int(self.retry_after_seconds, "retry_after_seconds"))


class ProviderJobQueueV2:
    """In-memory scheduling seam; no provider calls or trading authority live here."""

    def __init__(self, policy: ProviderQueuePolicyV2) -> None:
        if not isinstance(policy, ProviderQueuePolicyV2):
            raise TypeError("policy must be ProviderQueuePolicyV2")
        self._policy = policy
        self._queued_by_id: dict[str, MonitoringTaskV2] = {}

    @property
    def policy(self) -> ProviderQueuePolicyV2:
        return self._policy

    def enqueue(self, task: MonitoringTaskV2, *, now: datetime) -> None:
        current = _aware(now, "now")
        if not isinstance(task, MonitoringTaskV2):
            raise TypeError("task must be MonitoringTaskV2")
        if task.provider_id != self._policy.provider_id:
            raise ValueError("task provider does not match provider queue")
        if task.hard_eligible is not True:
            raise ValueError("task is not hard eligible")
        if current >= task.expires_at:
            raise ValueError("expired task cannot be queued")

        existing = self._queued_by_id.get(task.task_id)
        if existing is not None:
            if existing == task:
                return
            raise ValueError("conflicting duplicate task_id")
        if len(self._queued_by_id) >= self._policy.max_queue_size:
            raise AIProviderQueueFull("provider queue is full")
        self._queued_by_id[task.task_id] = task

    def queued(self, *, now: datetime) -> tuple[MonitoringTaskV2, ...]:
        current = _aware(now, "now")
        self._drop_expired(current)
        return tuple(sorted(self._queued_by_id.values(), key=self._sort_key))

    def claim(
        self,
        *,
        now: datetime,
        provider_slots_available: int,
    ) -> tuple[MonitoringTaskV2, ...]:
        current = _aware(now, "now")
        slots = _non_negative_int(provider_slots_available, "provider_slots_available")
        self._drop_expired(current)
        if slots == 0:
            return ()
        capacity = min(slots, self._policy.max_concurrency)
        due = sorted(
            (task for task in self._queued_by_id.values() if task.scheduled_for <= current),
            key=self._sort_key,
        )
        claimed = tuple(due[:capacity])
        for task in claimed:
            self._queued_by_id.pop(task.task_id, None)
        return claimed

    def _drop_expired(self, now: datetime) -> None:
        expired = [task_id for task_id, task in self._queued_by_id.items() if now >= task.expires_at]
        for task_id in expired:
            self._queued_by_id.pop(task_id, None)

    @staticmethod
    def _sort_key(task: MonitoringTaskV2) -> tuple[object, ...]:
        # Hard eligibility is enforced before enqueue. Remaining order mirrors the
        # deterministic pre-AI candidate priority stages from the approved plan.
        return (
            task.portfolio_priority,
            task.strategy_priority,
            -task.edge_quality,
            -task.capital_efficiency,
            task.signal_at,
            task.task_id,
        )


__all__ = ["AIProviderQueueFull", "ProviderJobQueueV2", "ProviderQueuePolicyV2"]
