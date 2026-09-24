import pytest

from engine.strategy.lifecycle_v2 import LifecycleError, StrategyLifecycle


def test_transition_never_arms_live_and_rolls_back():
    state = StrategyLifecycle("orb", "2.0.0")
    with pytest.raises(LifecycleError):
        state.advance("PAPER", evidence_fingerprint="a" * 64)
    for stage in ("RESEARCH", "BACKTEST", "VALIDATION", "PAPER"):
        state = state.advance(stage, evidence_fingerprint="a" * 64)
    assert state.live_state == "READ_ONLY/DISARMED"
    assert state.rollback().stage == "VALIDATION"
    assert state.deactivate().stage == "DEACTIVATED"
