from __future__ import annotations

from decimal import Decimal
from importlib import import_module

import pytest


def _experiments():
    try:
        return import_module("engine.research.experiments")
    except ModuleNotFoundError:
        pytest.fail("engine.research.experiments is missing", pytrace=False)


def _trials():
    try:
        return import_module("engine.research.trials")
    except ModuleNotFoundError:
        pytest.fail("engine.research.trials is missing", pytrace=False)


def _spec(*, seed: int = 7, max_trials: int = 4, reverse: bool = False):
    api = _experiments()
    datasets = ("nifty-bars@v2", "nifty-options@v4")
    tags = ("orb", "phase4")
    if reverse:
        datasets = tuple(reversed(datasets))
        tags = tuple(reversed(tags))
    return api.ExperimentSpec.create(
        strategy_id="orb",
        strategy_version="2.0.0",
        code_fingerprint="a" * 64,
        dataset_versions=datasets,
        config_snapshot_id="cfg_001",
        seed=seed,
        environment_fingerprint="b" * 64,
        max_trials=max_trials,
        parent_experiment_id=None,
        tags=tags,
        note="reference ORB research",
    )


def test_experiment_identity_is_deterministic_and_binds_research_inputs():
    first = _spec(reverse=False)
    second = _spec(reverse=True)

    assert first.experiment_id == second.experiment_id
    assert first.fingerprint == second.fingerprint
    assert first.dataset_versions == ("nifty-bars@v2", "nifty-options@v4")
    assert first.tags == ("orb", "phase4")

    assert _spec(seed=8).experiment_id != first.experiment_id
    assert _spec(max_trials=5).experiment_id != first.experiment_id


def test_experiment_registry_is_immutable_and_deterministically_ordered():
    api = _experiments()
    registry = api.ExperimentRegistry()
    first = _spec(seed=7)
    second = _spec(seed=8)

    assert registry.register(second) == second
    assert registry.register(first) == first
    assert registry.list_experiments() == tuple(
        sorted((first, second), key=lambda item: item.experiment_id)
    )
    assert registry.get(first.experiment_id) == first

    with pytest.raises(api.ExperimentError):
        registry.register(first)


def test_trial_record_fingerprint_is_parameter_order_independent_and_status_bound():
    api = _trials()
    experiment = _spec()
    first = api.TrialRecord.create(
        experiment=experiment,
        ordinal=1,
        parameters={"lookback": 35, "volume_multiplier": Decimal("1.2")},
        status=api.TrialStatus.COMPLETED,
        result_fingerprint="c" * 64,
        reason="",
    )
    second = api.TrialRecord.create(
        experiment=experiment,
        ordinal=1,
        parameters={"volume_multiplier": Decimal("1.2"), "lookback": 35},
        status=api.TrialStatus.COMPLETED,
        result_fingerprint="c" * 64,
        reason="",
    )
    failed = api.TrialRecord.create(
        experiment=experiment,
        ordinal=1,
        parameters={"lookback": 35, "volume_multiplier": Decimal("1.2")},
        status=api.TrialStatus.FAILED,
        result_fingerprint=None,
        reason="simulation_error",
    )

    assert first.trial_id == second.trial_id
    assert first.fingerprint == second.fingerprint
    assert failed.fingerprint != first.fingerprint


def test_trials_ledger_records_failed_rejected_and_early_stopped_attempts_append_only():
    api = _trials()
    experiment = _spec(max_trials=4)
    ledger = api.TrialsLedger(experiment)

    statuses = (
        api.TrialStatus.COMPLETED,
        api.TrialStatus.FAILED,
        api.TrialStatus.REJECTED,
        api.TrialStatus.EARLY_STOPPED,
    )
    for ordinal, status in enumerate(statuses, start=1):
        record = api.TrialRecord.create(
            experiment=experiment,
            ordinal=ordinal,
            parameters={"lookback": 30 + ordinal},
            status=status,
            result_fingerprint=("d" * 64 if status is api.TrialStatus.COMPLETED else None),
            reason=("" if status is api.TrialStatus.COMPLETED else status.value.lower()),
        )
        ledger.append(record)

    assert ledger.trial_count == 4
    assert tuple(record.status for record in ledger.records()) == statuses
    assert ledger.remaining_budget == 0

    with pytest.raises(api.TrialsLedgerError):
        ledger.append(ledger.records()[0])


def test_trials_ledger_rejects_skipped_ordinals_foreign_experiments_and_budget_overflow():
    api = _trials()
    experiment = _spec(max_trials=2)
    ledger = api.TrialsLedger(experiment)

    skipped = api.TrialRecord.create(
        experiment=experiment,
        ordinal=2,
        parameters={"x": 1},
        status=api.TrialStatus.FAILED,
        result_fingerprint=None,
        reason="bad_input",
    )
    with pytest.raises(api.TrialsLedgerError):
        ledger.append(skipped)

    first = api.TrialRecord.create(
        experiment=experiment,
        ordinal=1,
        parameters={"x": 1},
        status=api.TrialStatus.COMPLETED,
        result_fingerprint="e" * 64,
        reason="",
    )
    ledger.append(first)

    foreign_experiment = _spec(seed=99, max_trials=2)
    foreign = api.TrialRecord.create(
        experiment=foreign_experiment,
        ordinal=2,
        parameters={"x": 2},
        status=api.TrialStatus.FAILED,
        result_fingerprint=None,
        reason="foreign",
    )
    with pytest.raises(api.TrialsLedgerError):
        ledger.append(foreign)

    second = api.TrialRecord.create(
        experiment=experiment,
        ordinal=2,
        parameters={"x": 2},
        status=api.TrialStatus.REJECTED,
        result_fingerprint=None,
        reason="policy_reject",
    )
    ledger.append(second)

    overflow = api.TrialRecord.create(
        experiment=experiment,
        ordinal=3,
        parameters={"x": 3},
        status=api.TrialStatus.EARLY_STOPPED,
        result_fingerprint=None,
        reason="budget",
    )
    with pytest.raises(api.TrialsLedgerError):
        ledger.append(overflow)
