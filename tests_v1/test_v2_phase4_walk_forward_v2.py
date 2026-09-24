from decimal import Decimal

import pytest

from engine.research.walk_forward_v2 import WalkForwardError, WalkForwardPlan, execute_walk_forward


def test_wfo_uses_separate_train_validation_and_unseen_oos_windows():
    observations = tuple(Decimal(n) for n in range(1, 41))
    views = []
    def select(train, validation):
        views.append((train, validation))
        return "params@v1"
    def score(params, unseen):
        assert params == "params@v1"
        return sum(unseen) / len(unseen)
    result = execute_walk_forward(observations, WalkForwardPlan(
        train_bars=8, validation_bars=2, test_bars=2, embargo_bars=1, step_bars=13),
        select=select, score=score)
    assert len(result.windows) >= 2
    assert result.windows[0].train_end < result.windows[0].test_start
    assert len(views[0][0]) == 8
    assert len(views[0][1]) == 2
    assert result.fingerprint == execute_walk_forward(observations,
        WalkForwardPlan(8, 2, 2, 1, 13), select=select, score=score).fingerprint


def test_wfo_rejects_undersized_or_float_observations():
    with pytest.raises(WalkForwardError):
        execute_walk_forward((Decimal("1"),), WalkForwardPlan(8, 2, 2, 1, 3),
                             select=lambda a, b: "p@v1", score=lambda p, x: Decimal(1))
    with pytest.raises(WalkForwardError):
        execute_walk_forward(tuple([1.0] * 20), WalkForwardPlan(8, 2, 2, 1, 3),
                             select=lambda a, b: "p@v1", score=lambda p, x: Decimal(1))
