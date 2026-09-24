from decimal import Decimal

import pytest

from engine.research.validation_v2 import EvidenceError, SplitWindow, ValidationBundle


def test_validation_bundle_rejects_split_overlap_and_missing_evidence():
    with pytest.raises(EvidenceError):
        ValidationBundle.create(
            train=SplitWindow(0, 10), validation=SplitWindow(9, 12),
            test=SplitWindow(12, 15), dataset_ref="licensed@v1",
            wfo_scores=(Decimal("1"),), oos_score=Decimal("1"),
            stress_scores={"cost": Decimal("0")},
        )
    with pytest.raises(EvidenceError):
        ValidationBundle.create(
            train=SplitWindow(0, 10), validation=SplitWindow(10, 12),
            test=SplitWindow(12, 15), dataset_ref="licensed@v1",
            wfo_scores=(), oos_score=Decimal("1"), stress_scores={},
        )


def test_validation_bundle_is_deterministic_and_requires_stress_families():
    kwargs = dict(train=SplitWindow(0, 10), validation=SplitWindow(10, 12),
                  test=SplitWindow(12, 15), dataset_ref="licensed@v1",
                  wfo_scores=(Decimal("1.1"), Decimal("1.2")),
                  oos_score=Decimal("1.0"))
    families = ("bootstrap", "monte_carlo", "sensitivity", "regime",
                "cost", "slippage", "delay", "missing_feed", "bad_feed")
    first = ValidationBundle.create(**kwargs, stress_scores={x: Decimal("0.1") for x in families})
    second = ValidationBundle.create(**kwargs, stress_scores={x: Decimal("0.1") for x in reversed(families)})
    assert first.fingerprint == second.fingerprint
    with pytest.raises(EvidenceError):
        ValidationBundle.create(**kwargs, stress_scores={"cost": Decimal("0.1")})
