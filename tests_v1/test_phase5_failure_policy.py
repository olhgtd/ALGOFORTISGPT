from __future__ import annotations

import pytest

from engine.paper.contracts_v2 import PaperOperationalState
from engine.paper.failure_policy_v2 import (
    FailureStormPolicy,
    MissingStormPolicyDecision,
    StormEvaluator,
)


def _policy() -> FailureStormPolicy:
    return FailureStormPolicy(
        policy_id="TEST_ONLY/storm-fi-v1",
        version="1",
        failure_class="ORDER_REJECTION",
        observation_window_ms=10_000,
        trigger_count=3,
        cooldown_ms=30_000,
        escalation_action="HALT_ENTRIES",
        reset_rule="WINDOW_AND_COOLDOWN",
        test_only=True,
    )


def test_test_only_rejection_policy_halts_exactly_at_threshold():
    evaluator = StormEvaluator(_policy())
    first = evaluator.observe("ORDER_REJECTION", 0)
    second = evaluator.observe("ORDER_REJECTION", 1_000)
    third = evaluator.observe("ORDER_REJECTION", 2_000)
    assert first.halt is False
    assert first.resulting_state is PaperOperationalState.DEGRADED
    assert second.halt is False
    assert third.halt is True
    assert third.resulting_state is PaperOperationalState.HALTED


def test_events_outside_window_do_not_count_toward_threshold():
    evaluator = StormEvaluator(_policy())
    evaluator.observe("ORDER_REJECTION", 0)
    evaluator.observe("ORDER_REJECTION", 1_000)
    decision = evaluator.observe("ORDER_REJECTION", 20_000)
    assert decision.observed_count == 1
    assert decision.halt is False


def test_out_of_order_observation_is_rejected():
    evaluator = StormEvaluator(_policy())
    evaluator.observe("ORDER_REJECTION", 2_000)
    with pytest.raises(ValueError, match="monotonic"):
        evaluator.observe("ORDER_REJECTION", 1_000)


def test_wrong_failure_class_is_rejected():
    evaluator = StormEvaluator(_policy())
    with pytest.raises(ValueError, match="failure_class"):
        evaluator.observe("RATE_LIMIT", 0)


def test_missing_required_policy_never_allows_unbounded_retry():
    decision = MissingStormPolicyDecision.for_failure("ORDER_REJECTION")
    assert decision.retry_unbounded is False
    assert decision.halt is True
    assert decision.resulting_state is PaperOperationalState.HALTED
    assert decision.reason == "MISSING_STORM_POLICY"


def test_forced_test_policy_cannot_masquerade_as_production_default():
    with pytest.raises(ValueError, match="TEST_ONLY"):
        FailureStormPolicy(
            policy_id="production/rejections",
            version="1",
            failure_class="ORDER_REJECTION",
            observation_window_ms=10_000,
            trigger_count=3,
            cooldown_ms=30_000,
            escalation_action="HALT_ENTRIES",
            reset_rule="WINDOW_AND_COOLDOWN",
            test_only=True,
        )
