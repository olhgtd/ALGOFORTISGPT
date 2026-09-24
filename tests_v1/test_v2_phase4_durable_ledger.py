from engine.research.experiments import ExperimentSpec
from engine.research.durable_ledger import DurableTrialsLedger, DurableLedgerError
from engine.research.trials import TrialRecord, TrialStatus
from engine.research.search import SearchSession, SearchError
import sqlite3
import pytest


def _experiment():
    return ExperimentSpec.create(strategy_id="orb", strategy_version="2.0.0",
        code_fingerprint="a" * 64, dataset_versions=("nifty@v1",),
        config_snapshot_id="cfg", seed=7, environment_fingerprint="b" * 64,
        max_trials=2, tags=(), note="")


def test_durable_ledger_reopens_without_losing_trials_or_oos_latch(tmp_path):
    experiment = _experiment()
    path = tmp_path / "trials.sqlite"
    ledger = DurableTrialsLedger(path, experiment)
    ledger.append(TrialRecord.create(experiment=experiment, ordinal=1,
        parameters={"lookback": 20}, status=TrialStatus.FAILED,
        result_fingerprint=None, reason="invalid"))
    ledger.mark_oos_viewed()
    again = DurableTrialsLedger(path, experiment)
    assert again.trial_count == 1
    assert again.oos_viewed is True
    assert SearchSession(experiment=experiment, ledger=again).search_closed is True
    try:
        again.append(TrialRecord.create(experiment=experiment, ordinal=2,
            parameters={"lookback": 30}, status=TrialStatus.FAILED,
            result_fingerprint=None, reason="late"))
    except DurableLedgerError:
        pass
    else:
        raise AssertionError("search reopened after viewing OOS")


def test_durable_ledger_rejects_external_update_and_experiment_change(tmp_path):
    experiment = _experiment()
    path = tmp_path / "trials.sqlite"
    ledger = DurableTrialsLedger(path, experiment)
    ledger.append(TrialRecord.create(experiment=experiment, ordinal=1,
        parameters={"lookback": 20}, status=TrialStatus.FAILED,
        result_fingerprint=None, reason="invalid"))
    with sqlite3.connect(path) as db, pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE trials SET reason = 'changed' WHERE ordinal = 1")
    assert DurableTrialsLedger(path, experiment).records()[0].reason == "invalid"
