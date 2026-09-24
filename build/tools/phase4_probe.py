"""Deterministic cross-run ORB reference and Backtest V2 probe."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from tempfile import TemporaryDirectory
from pathlib import Path

from engine.backtest.v2.contracts import Bar, ExecutionModel, OrderIntent
from engine.backtest.v2.execution import simulate
from engine.backtest.v2.orb_reference import run_orb_option_backtest
from engine.backtest.v2.options import OptionModel
from engine.data.instruments import InstrumentTerms
from engine.strategy.protective_policy_v2 import ProtectivePolicyV2
from strategies.orb.orb_v2 import ORBReferenceStrategyV2, ORBSignalSnapshot
from engine.data.licensing import AcquisitionPermission, DataLicenceMetadata, DataLicencePolicy, DataUse
from engine.research.durable_ledger import DurableTrialsLedger
from engine.research.experiments import ExperimentSpec
from engine.research.overfitting import overfitting_evidence
from engine.research.trials import TrialRecord, TrialStatus
from engine.research.validation_v2 import SplitWindow, STRESS_FAMILIES, ValidationBundle
from engine.strategy.promotion_v2 import PromotionEvidenceBundle, PromotionAttemptBundle
from engine.strategy.promotion_v2 import PromotionError


def run() -> tuple[str, str]:
    now = datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc)
    signal = ORBReferenceStrategyV2().generate_signal(ORBSignalSnapshot(
        "NIFTY", now, Decimal("22011"), Decimal("22010"), Decimal("21990")))
    bars = (Bar(now, Decimal("22000"), Decimal("22012"), Decimal("21999"), Decimal("22011"), Decimal("100")),
            Bar(now + timedelta(minutes=5), Decimal("22015"), Decimal("22020"), Decimal("22010"), Decimal("22018"), Decimal("100")))
    result = simulate(bars, (OrderIntent(0, "BUY", Decimal("1")),),
                      ExecutionModel("research-execution@v1", latency_bars=1,
                                     spread=Decimal("0.2"), slippage=Decimal("0.1")))
    return signal.fingerprint, result.fingerprint


def orb_option_probe() -> str:
    now = datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc)
    snapshot = ORBSignalSnapshot("NIFTY", now, Decimal("22011"),
                                  Decimal("22010"), Decimal("21990"))
    terms = InstrumentTerms("ce", "NSE", "NIFTY-CE", "options",
        date(2026, 1, 1), date(2026, 1, 29), 65, Decimal("0.05"),
        "NIFTY", date(2026, 1, 29), 22000, "CE", "monthly")
    bars = (Bar(now + timedelta(minutes=5), Decimal("100"), Decimal("101"), Decimal("99"), Decimal("100"), Decimal("100")),
            Bar(now + timedelta(minutes=10), Decimal("100"), Decimal("125"), Decimal("99"), Decimal("120"), Decimal("100")))
    policy = ProtectivePolicyV2("TEST_ONLY/orb@v1", Decimal("10"), Decimal("20"),
                                 Decimal("5"), True, Decimal("0.05"), "ROUND_HALF_UP")
    model = OptionModel("options@v1", Decimal(0), Decimal(0), Decimal(0), Decimal(0))
    result = run_orb_option_backtest(snapshot, terms=terms, option_bars=bars,
                                     policy=policy, option_model=model)
    if result.promotion_eligible:
        raise AssertionError("TEST_ONLY ORB option fixture became promotable")
    return result.fingerprint


def promotion_probe() -> tuple[str, str]:
    """Generate linked test-only authorities; built-in policy must reject."""
    experiment = ExperimentSpec.create(strategy_id="orb", strategy_version="2.0.0",
        code_fingerprint="a" * 64, dataset_versions=("fixture@v1",),
        config_snapshot_id="fixture", seed=7, environment_fingerprint="b" * 64,
        max_trials=2, tags=("TEST_ONLY",), note="cross-Windows probe")
    with TemporaryDirectory() as directory:
        ledger = DurableTrialsLedger(Path(directory) / "ledger.sqlite", experiment)
        for ordinal in (1, 2):
            ledger.append(TrialRecord.create(experiment=experiment, ordinal=ordinal,
                parameters={"lookback": ordinal * 10}, status=TrialStatus.COMPLETED,
                result_fingerprint="c" * 64, reason=""))
        ledger.mark_oos_viewed()
        validation = ValidationBundle.create(
            train=SplitWindow(0, 10), validation=SplitWindow(10, 12), test=SplitWindow(12, 15),
            dataset_ref="fixture@v1", wfo_scores=(Decimal("1"),), oos_score=Decimal("1"),
            stress_scores={name: Decimal("0") for name in STRESS_FAMILIES})
        overfit = overfitting_evidence((
            (Decimal("1"), Decimal("2"), Decimal("-1"), Decimal("3"), Decimal("2"), Decimal("-2"), Decimal("1"), Decimal("3")),
            (Decimal("2"), Decimal("-1"), Decimal("3"), Decimal("1"), Decimal("-1"), Decimal("2"), Decimal("2"), Decimal("1"))),
            ledger_trial_count=2)
        metadata = DataLicenceMetadata(
            "fixture", "fixture@v1", AcquisitionPermission.ALLOWED, (DataUse.RESEARCH, DataUse.PROMOTION), synthetic=True)
        licence = DataLicencePolicy().evaluate(metadata,
            market="NSE", requested_use=DataUse.PROMOTION, programmatic_acquisition=False)
        try:
            PromotionEvidenceBundle.from_authorities(
                ledger=ledger, validation=validation, overfitting=overfit,
                licence_metadata=metadata, market="NSE",
                metrics={"trades": 2})
        except PromotionError:
            attempt = PromotionAttemptBundle.test_only(
                validation_fingerprint=validation.fingerprint,
                overfitting_fingerprint=overfit.fingerprint, licence=licence)
            return attempt.fingerprint, attempt.status
        raise AssertionError("synthetic TEST_ONLY fixture was accepted for promotion")


if __name__ == "__main__":
    signal, run_fingerprint = run()
    print("ORB_SIGNAL=" + signal)
    print("BACKTEST_RUN=" + run_fingerprint)
    print("TEST_ONLY_ORB_OPTION_RUN=" + orb_option_probe())
    bundle, status = promotion_probe()
    print("TEST_ONLY_PROMOTION_ATTEMPT=" + bundle)
    print("DEFAULT_PROMOTION_STATUS=" + status)
