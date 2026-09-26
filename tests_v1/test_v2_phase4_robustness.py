from decimal import Decimal

import pytest

from engine.research.robustness_v2 import RobustnessError, evaluate_robustness
from engine.research.validation_v2 import STRESS_FAMILIES


def test_robustness_is_seeded_and_requires_every_stress_family():
    series = tuple(Decimal(i % 5 - 2) for i in range(30))
    scenarios = {key: series for key in STRESS_FAMILIES}
    first = evaluate_robustness(scenarios, seed=19, draws=100, block_length=3)
    second = evaluate_robustness(dict(reversed(tuple(scenarios.items()))),
                                 seed=19, draws=100, block_length=3)
    assert first.fingerprint == second.fingerprint
    assert first.mc_drawdown_p95 >= 0
    with pytest.raises(RobustnessError):
        evaluate_robustness({"cost": series}, seed=19, draws=100, block_length=3)
