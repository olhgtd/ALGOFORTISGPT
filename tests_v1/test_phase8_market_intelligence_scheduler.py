from __future__ import annotations

from datetime import datetime, timedelta, timezone
from importlib import import_module

import pytest


def _api():
    try:
        return import_module("engine.ai.v2.scheduler")
    except ModuleNotFoundError:
        pytest.fail("engine.ai.v2.scheduler is missing", pytrace=False)


class Clock:
    def __init__(self, now): self.now_value = now
    def now(self): return self.now_value


class Budget:
    def __init__(self, ok=True): self.ok = ok
    def allows(self, job): return self.ok


def _job(api, now, *, kind=None, ttl_minutes=5):
    return api.ResearchJob(
        job_id="job-1",
        kind=kind or api.ResearchJobKind.RESEARCH,
        created_at=now,
        input_valid_until=now + timedelta(minutes=ttl_minutes),
        payload_ref="dataset:snapshot-1",
        provider_policy_ref="provider-policy/v1",
        tool_policy_ref="tool-policy/v1",
    )


def test_scheduler_uses_injected_clock_and_rejects_stale_input_before_dispatch():
    api = _api(); now = datetime(2026, 9, 27, 5, 0, tzinfo=timezone.utc)
    calls = []
    scheduler = api.MarketIntelligenceScheduler(
        clock=Clock(now), policy=api.SchedulerPolicy("sched/v1", max_queue=2, max_concurrency=1),
        provider_budget=Budget(True), tool_budget=Budget(True), dispatch=lambda j: calls.append(j.job_id),
    )
    stale = _job(api, now, ttl_minutes=-1)
    decision = scheduler.submit(stale)
    assert decision.accepted is False
    assert decision.reason == api.SchedulerRejectReason.STALE_INPUT
    assert calls == []


def test_budget_exhaustion_rejects_without_expanding_budget_or_dispatching():
    api = _api(); now = datetime(2026, 9, 27, 5, 0, tzinfo=timezone.utc)
    calls=[]; provider = Budget(False); tools = Budget(True)
    scheduler = api.MarketIntelligenceScheduler(
        clock=Clock(now), policy=api.SchedulerPolicy("sched/v1", 2, 1),
        provider_budget=provider, tool_budget=tools, dispatch=lambda j: calls.append(j.job_id),
    )
    decision = scheduler.submit(_job(api, now))
    assert decision.accepted is False
    assert decision.reason == api.SchedulerRejectReason.PROVIDER_BUDGET_EXHAUSTED
    assert provider.ok is False
    assert calls == []


def test_queue_and_concurrency_are_bounded():
    api = _api(); now = datetime(2026, 9, 27, 5, 0, tzinfo=timezone.utc)
    scheduler = api.MarketIntelligenceScheduler(
        clock=Clock(now), policy=api.SchedulerPolicy("sched/v1", max_queue=1, max_concurrency=1),
        provider_budget=Budget(True), tool_budget=Budget(True), dispatch=lambda j: None,
    )
    assert scheduler.submit(_job(api, now)).accepted is True
    second = api.ResearchJob("job-2", api.ResearchJobKind.INTELLIGENCE, now, now+timedelta(minutes=5), "p", "pp", "tp")
    decision = scheduler.submit(second)
    assert decision.accepted is False
    assert decision.reason == api.SchedulerRejectReason.QUEUE_FULL


def test_only_research_and_shadow_job_kinds_exist():
    api = _api()
    assert {k.value for k in api.ResearchJobKind} == {"RESEARCH", "SHADOW"}
    assert all("ORDER" not in k.value and "BROKER" not in k.value for k in api.ResearchJobKind)


def test_run_next_respects_concurrency_and_dispatches_accepted_job():
    api = _api(); now = datetime(2026, 9, 27, 5, 0, tzinfo=timezone.utc); calls=[]
    scheduler = api.MarketIntelligenceScheduler(
        clock=Clock(now), policy=api.SchedulerPolicy("sched/v1", 2, 1),
        provider_budget=Budget(True), tool_budget=Budget(True), dispatch=lambda j: calls.append(j.job_id),
    )
    assert scheduler.submit(_job(api, now)).accepted is True
    result = scheduler.run_next()
    assert result.dispatched is True
    assert result.job_id == "job-1"
    assert calls == ["job-1"]
