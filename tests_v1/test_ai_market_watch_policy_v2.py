from __future__ import annotations

from datetime import datetime, timezone

import pytest

from engine.ai.monitoring_scheduler_v2 import (
    MarketWatchPolicyV2,
    MonitoringSchedulerV2,
    MonitoringTaskClass,
    MonitoringTriggerType,
    ScopeExpansionRequest,
    ScopeExpansionType,
)
from engine.ai.provider_queue_v2 import ProviderQueuePolicyV2

NOW = datetime(2026, 10, 1, 9, 15, tzinfo=timezone.utc)


def _policy() -> MarketWatchPolicyV2:
    return MarketWatchPolicyV2(
        policy_ref="market-watch/index-intraday/v3",
        policy_version="3.0.0",
        allowed_instruments=("NIFTY", "BANKNIFTY", "SENSEX"),
        frequency_seconds=300,
        task_ttl_seconds=45,
        provider_id="provider-a",
        model_id="model-a",
        allowed_trigger_types=(
            MonitoringTriggerType.SCHEDULED,
            MonitoringTriggerType.EVENT,
            MonitoringTriggerType.OWNER,
        ),
        allowed_task_classes=(
            MonitoringTaskClass.ACTIVE_CANDIDATE_REVIEW,
            MonitoringTaskClass.REGIME_EVENT,
            MonitoringTaskClass.SCHEDULED_MONITORING,
            MonitoringTaskClass.STRATEGY_HUNTING,
        ),
        allowed_timeframes=("1m", "5m"),
        strategy_review_mode="PREFERRED",
        independent_candidate_scan=True,
    )


def test_market_watch_policy_is_versioned_and_scheduler_owned() -> None:
    policy = _policy()
    scheduler = MonitoringSchedulerV2(policy)
    task = scheduler.schedule(
        task_id="review-1",
        instrument="BANKNIFTY",
        scheduled_for=NOW,
        hard_eligible=True,
        portfolio_priority=0,
        strategy_priority=0,
        edge_quality="1",
        capital_efficiency="1",
        signal_at=NOW,
        trigger_type=MonitoringTriggerType.EVENT,
        task_class=MonitoringTaskClass.ACTIVE_CANDIDATE_REVIEW,
        timeframe="5m",
    )
    assert task.policy_ref == "market-watch/index-intraday/v3"
    assert task.policy_version == "3.0.0"
    assert task.trigger_type is MonitoringTriggerType.EVENT
    assert task.task_class is MonitoringTaskClass.ACTIVE_CANDIDATE_REVIEW
    assert task.timeframe == "5m"


def test_scheduler_rejects_trigger_task_class_and_timeframe_outside_policy() -> None:
    scheduler = MonitoringSchedulerV2(_policy())
    common = dict(
        task_id="bad",
        instrument="NIFTY",
        scheduled_for=NOW,
        hard_eligible=True,
        portfolio_priority=1,
        strategy_priority=1,
        edge_quality="1",
        capital_efficiency="1",
        signal_at=NOW,
    )
    with pytest.raises(ValueError, match="trigger"):
        scheduler.schedule(**common, trigger_type="SELF_DIRECTED")
    with pytest.raises(ValueError, match="task class"):
        scheduler.schedule(**common, task_class="UNBOUNDED_SCAN")
    with pytest.raises(ValueError, match="timeframe"):
        scheduler.schedule(**common, timeframe="1s")


def test_scope_expansion_request_is_pending_evidence_not_self_approval() -> None:
    request = ScopeExpansionRequest(
        request_id="scope-1",
        requested_by="laya",
        expansion_type=ScopeExpansionType.INSTRUMENT,
        requested_value="MIDCPNIFTY",
        reason_ref="evidence:scope-1",
        requested_at=NOW,
        policy_ref="market-watch/index-intraday/v3",
    )
    assert request.status == "PENDING_OWNER_REVIEW"
    assert not hasattr(request, "approve")
    assert not hasattr(request, "apply")


def test_provider_fallback_is_explicit_allowlist_not_automatic() -> None:
    policy = ProviderQueuePolicyV2(
        policy_ref="queue/provider-a/v2",
        provider_id="provider-a",
        max_concurrency=2,
        max_queue_size=10,
        retry_after_seconds=5,
        allowed_fallback_provider_ids=("provider-b",),
        max_requests_per_window=20,
        window_seconds=60,
    )
    assert policy.allows_fallback("provider-b") is True
    assert policy.allows_fallback("provider-c") is False
    assert policy.max_requests_per_window == 20
    assert policy.window_seconds == 60
