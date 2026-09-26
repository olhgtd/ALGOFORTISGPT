from decimal import Decimal

import pytest

from engine.research.validation_v2 import EvidenceError, SplitWindow, ValidationBundle
from engine.research.walk_forward_v2 import WalkForwardPlan, execute_walk_forward
from engine.research.walk_forward_v2 import evaluate_final_holdout


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


def test_executed_wfo_evidence_is_bound_to_validation_bundle():
    observations = tuple(Decimal(i) for i in range(50))
    wfo = execute_walk_forward(observations, WalkForwardPlan(8, 2, 2, 1, 13),
        select=lambda train, val: "params@v1",
        score=lambda params, test: sum(test) / len(test))
    bundle = ValidationBundle.create(
        train=SplitWindow(0, 20), validation=SplitWindow(20, 40), test=SplitWindow(40, 50),
        dataset_ref="licensed@v1", wfo_scores=tuple(w.oos_score for w in wfo.windows),
        oos_score=Decimal("1"), stress_scores={name: Decimal(0) for name in
            ("bootstrap", "monte_carlo", "sensitivity", "regime", "cost", "slippage",
             "delay", "missing_feed", "bad_feed")}, wfo_evidence=wfo)
    assert bundle.wfo_evidence.fingerprint == wfo.fingerprint


def test_final_holdout_executes_with_frozen_wfo_selection_only():
    observations = tuple(Decimal(i) for i in range(50))
    wfo = execute_walk_forward(observations, WalkForwardPlan(8, 2, 2, 1, 13),
        select=lambda train, val: "params@v1", score=lambda params, test: sum(test) / len(test))
    result = evaluate_final_holdout(observations, start=40, end=50, wfo=wfo,
                                    score=lambda params, unseen: sum(unseen) / len(unseen))
    assert result.score == Decimal("44.5")
    assert result.parameters == "params@v1"
