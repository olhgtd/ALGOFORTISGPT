from datetime import date
from decimal import Decimal

import pytest

from engine.data.licensing import AcquisitionPermission, DataLicenceMetadata, DataLicencePolicy, DataUse
from engine.research.durable_ledger import DurableTrialsLedger
from engine.research.experiments import ExperimentSpec
from engine.research.overfitting import overfitting_evidence
from engine.research.trials import TrialRecord, TrialStatus
from engine.research.validation_v2 import SplitWindow, STRESS_FAMILIES, ValidationBundle
from engine.research.walk_forward_v2 import WalkForwardPlan, execute_walk_forward, evaluate_final_holdout
from engine.research.robustness_v2 import evaluate_robustness
from engine.strategy.promotion_v2 import PromotionError, PromotionEvidenceBundle, PromotionProfile, evaluate_promotion


def test_promotion_bundle_requires_closed_ledger_and_licensed_data(tmp_path):
    exp = ExperimentSpec.create(strategy_id="orb", strategy_version="2.0.0",
        code_fingerprint="a" * 64, dataset_versions=("nifty@v1",),
        config_snapshot_id="cfg", seed=7, environment_fingerprint="b" * 64,
        max_trials=2, tags=(), note="")
    ledger = DurableTrialsLedger(tmp_path / "ledger.sqlite", exp)
    for n in (1, 2):
        ledger.append(TrialRecord.create(experiment=exp, ordinal=n,
            parameters={"lookback": n * 10}, status=TrialStatus.COMPLETED,
            result_fingerprint="c" * 64, reason=""))
    wfo = execute_walk_forward(tuple(Decimal(i) for i in range(50)), WalkForwardPlan(8, 2, 2, 1, 13),
        select=lambda train, val: "params@v1", score=lambda params, test: sum(test) / len(test))
    final_oos = evaluate_final_holdout(tuple(Decimal(i) for i in range(50)),
        start=40, end=50, wfo=wfo, score=lambda params, test: sum(test) / len(test))
    series = tuple(Decimal(i % 5 - 2) for i in range(30))
    robustness = evaluate_robustness({key: series for key in STRESS_FAMILIES},
                                     seed=17, draws=100, block_length=3)
    validation = ValidationBundle.create(
        train=SplitWindow(0, 20), validation=SplitWindow(20, 40), test=SplitWindow(40, 50),
        dataset_ref="nifty@v1", wfo_scores=tuple(w.oos_score for w in wfo.windows),
        oos_score=final_oos.score, stress_scores=robustness.scores,
        wfo_evidence=wfo, final_oos=final_oos, robustness=robustness)
    overfit = overfitting_evidence((
        (Decimal("1"), Decimal("2"), Decimal("-1"), Decimal("3"),
         Decimal("2"), Decimal("-2"), Decimal("1"), Decimal("3")),
        (Decimal("2"), Decimal("-1"), Decimal("3"), Decimal("1"),
         Decimal("-1"), Decimal("2"), Decimal("2"), Decimal("1"))), ledger_trial_count=2)
    licence = DataLicencePolicy().evaluate(DataLicenceMetadata(
        "licensed", "contract@v1", AcquisitionPermission.ALLOWED,
        (DataUse.PROMOTION,)), market="NSE", requested_use=DataUse.PROMOTION,
        programmatic_acquisition=False)
    with pytest.raises(PromotionError):
        PromotionEvidenceBundle.from_authorities(ledger=ledger, validation=validation,
            overfitting=overfit, licence=licence, metrics={"trades": 200})
    ledger.mark_oos_viewed()
    bundle = PromotionEvidenceBundle.from_authorities(ledger=ledger, validation=validation,
        overfitting=overfit, licence=licence, metrics={"trades": 200})
    assert len(bundle.fingerprint) == 64
    assert evaluate_promotion(PromotionProfile.research_only(), bundle).status == "NON_PROMOTABLE"
