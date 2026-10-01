from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

try:
    from engine.ai.monitoring_scheduler_v2 import (
        MonitoringPolicyV2,
        MonitoringSchedulerV2,
        MonitoringTaskV2,
    )
    from engine.ai.provider_queue_v2 import (
        AIProviderQueueFull,
        ProviderJobQueueV2,
        ProviderQueuePolicyV2,
    )
except ModuleNotFoundError as exc:  # RED until AI queue implementation exists
    pytest.fail(f"AI monitoring scheduler/provider queue is not implemented: {exc}", pytrace=False)


NOW = datetime(2026, 10, 1, 9, 15, tzinfo=timezone.utc)


def _scheduler(*, provider_id: str = "provider-a") -> MonitoringSchedulerV2:
    return MonitoringSchedulerV2(
        MonitoringPolicyV2(
            policy_ref=f"monitoring/{provider_id}/v1",
            allowed_instruments=("NIFTY", "BANKNIFTY", "SENSEX"),
            frequency_seconds=60,
            task_ttl_seconds=30,
            provider_id=provider_id,
            model_id=f"model-{provider_id}",
        )
    )


def _task(
    task_id: str,
    *,
    scheduler: MonitoringSchedulerV2 | None = None,
    instrument: str = "NIFTY",
    scheduled_offset: int = 0,
    hard_eligible: bool = True,
    portfolio_priority: int = 10,
    strategy_priority: int = 10,
    edge_quality: str = "1.0",
    capital_efficiency: str = "1.0",
    signal_offset_ms: int = 0,
) -> MonitoringTaskV2:
    owner = scheduler or _scheduler()
    return owner.schedule(
        task_id=task_id,
        instrument=instrument,
        scheduled_for=NOW + timedelta(seconds=scheduled_offset),
        hard_eligible=hard_eligible,
        portfolio_priority=portfolio_priority,
        strategy_priority=strategy_priority,
        edge_quality=Decimal(edge_quality),
        capital_efficiency=Decimal(capital_efficiency),
        signal_at=NOW + timedelta(milliseconds=signal_offset_ms),
    )


def _queue(provider_id: str = "provider-a", *, max_concurrency: int = 2, max_queue_size: int = 8) -> ProviderJobQueueV2:
    return ProviderJobQueueV2(
        ProviderQueuePolicyV2(
            policy_ref=f"provider-queue/{provider_id}/v1",
            provider_id=provider_id,
            max_concurrency=max_concurrency,
            max_queue_size=max_queue_size,
            retry_after_seconds=5,
        )
    )


def test_scheduler_owns_scope_provider_model_frequency_and_ttl() -> None:
    scheduler = _scheduler()
    task = _task("job-1", scheduler=scheduler, instrument="BANKNIFTY")

    assert task.instrument == "BANKNIFTY"
    assert task.provider_id == "provider-a"
    assert task.model_id == "model-provider-a"
    assert task.expires_at == task.scheduled_for + timedelta(seconds=30)
    assert scheduler.next_run(NOW) == NOW + timedelta(seconds=60)

    with pytest.raises(FrozenInstanceError):
        task.instrument = "SENSEX"
    with pytest.raises(FrozenInstanceError):
        task.expires_at = task.expires_at + timedelta(hours=1)


def test_scheduler_rejects_symbol_outside_owner_assigned_scope() -> None:
    scheduler = _scheduler()
    with pytest.raises(ValueError, match="instrument"):
        _task("job-out-of-scope", scheduler=scheduler, instrument="MIDCPNIFTY")


def test_caller_cannot_override_provider_or_ttl_per_task() -> None:
    scheduler = _scheduler()
    with pytest.raises(TypeError):
        scheduler.schedule(
            task_id="job-bypass",
            instrument="NIFTY",
            scheduled_for=NOW,
            hard_eligible=True,
            portfolio_priority=1,
            strategy_priority=1,
            edge_quality=Decimal("1"),
            capital_efficiency=Decimal("1"),
            signal_at=NOW,
            provider_id="other-provider",
            task_ttl_seconds=9999,
        )


def test_quota_exhaustion_keeps_valid_job_queued_without_bypass() -> None:
    queue = _queue(max_concurrency=1)
    task = _task("job-1")
    queue.enqueue(task, now=NOW)

    assert queue.claim(now=NOW, provider_slots_available=0) == ()
    assert tuple(item.task_id for item in queue.queued(now=NOW)) == ("job-1",)


def test_same_jobs_have_same_deterministic_order_regardless_of_enqueue_order() -> None:
    scheduler = _scheduler()
    jobs = (
        _task("nifty", scheduler=scheduler, portfolio_priority=2, strategy_priority=1, edge_quality="4"),
        _task("banknifty", scheduler=scheduler, portfolio_priority=1, strategy_priority=5, edge_quality="2"),
        _task("sensex", scheduler=scheduler, portfolio_priority=1, strategy_priority=2, edge_quality="3"),
    )

    q1 = _queue(max_concurrency=3)
    q2 = _queue(max_concurrency=3)
    for item in jobs:
        q1.enqueue(item, now=NOW)
    for item in reversed(jobs):
        q2.enqueue(item, now=NOW)

    first = tuple(item.task_id for item in q1.claim(now=NOW, provider_slots_available=3))
    second = tuple(item.task_id for item in q2.claim(now=NOW, provider_slots_available=3))
    assert first == ("sensex", "banknifty", "nifty")
    assert second == first


def test_expired_queued_job_is_dropped_and_never_executed_late() -> None:
    queue = _queue(max_concurrency=1)
    task = _task("job-expired")
    queue.enqueue(task, now=NOW)

    later = NOW + timedelta(seconds=31)
    assert queue.claim(now=later, provider_slots_available=1) == ()
    assert queue.queued(now=later) == ()


def test_wrong_provider_is_rejected_instead_of_silent_fallback() -> None:
    provider_a = _scheduler(provider_id="provider-a")
    provider_b_queue = _queue(provider_id="provider-b")
    with pytest.raises(ValueError, match="provider"):
        provider_b_queue.enqueue(_task("job-a", scheduler=provider_a), now=NOW)


def test_different_provider_queues_are_independent_when_explicitly_assigned() -> None:
    a_scheduler = _scheduler(provider_id="provider-a")
    b_scheduler = _scheduler(provider_id="provider-b")
    a_queue = _queue(provider_id="provider-a", max_concurrency=1)
    b_queue = _queue(provider_id="provider-b", max_concurrency=1)
    a_queue.enqueue(_task("job-a", scheduler=a_scheduler), now=NOW)
    b_queue.enqueue(_task("job-b", scheduler=b_scheduler), now=NOW)

    assert tuple(item.task_id for item in a_queue.claim(now=NOW, provider_slots_available=1)) == ("job-a",)
    assert tuple(item.task_id for item in b_queue.claim(now=NOW, provider_slots_available=1)) == ("job-b",)


def test_bounded_queue_rejects_overflow_instead_of_spawning_parallel_bypass() -> None:
    queue = _queue(max_queue_size=1)
    queue.enqueue(_task("job-1"), now=NOW)
    with pytest.raises(AIProviderQueueFull):
        queue.enqueue(_task("job-2"), now=NOW)


def test_ai_queue_has_no_order_capital_live_arm_or_broker_mutation_surface() -> None:
    queue = _queue()
    for forbidden in ("place", "cancel", "reserve_capital", "arm_live", "mint_approved_order"):
        assert not hasattr(queue, forbidden)
