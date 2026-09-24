from __future__ import annotations

from decimal import Decimal
from importlib import import_module

import pytest

from engine.research.experiments import ExperimentSpec
from engine.research.trials import TrialStatus, TrialsLedger


def _search():
    try:
        return import_module("engine.research.search")
    except ModuleNotFoundError:
        pytest.fail("engine.research.search is missing", pytrace=False)


def _stability():
    try:
        return import_module("engine.research.stability")
    except ModuleNotFoundError:
        pytest.fail("engine.research.stability is missing", pytrace=False)


def _experiment(*, max_trials: int = 4, seed: int = 17) -> ExperimentSpec:
    return ExperimentSpec.create(
        strategy_id="orb",
        strategy_version="2.0.0",
        code_fingerprint="a" * 64,
        dataset_versions=("nifty-bars@v2",),
        config_snapshot_id="cfg-search",
        seed=seed,
        environment_fingerprint="b" * 64,
        max_trials=max_trials,
        tags=("phase4",),
        note="search contract",
    )


def test_grid_candidates_are_deterministic_and_mapping_order_independent():
    api = _search()
    first = api.grid_candidates(
        {"lookback": (20, 30), "volume": (Decimal("1.0"), Decimal("1.2"))},
        max_trials=4,
    )
    second = api.grid_candidates(
        {"volume": (Decimal("1.2"), Decimal("1.0")), "lookback": (30, 20)},
        max_trials=4,
    )

    assert tuple(dict(item) for item in first) == tuple(dict(item) for item in second)
    assert len(first) == 4
    assert tuple(first[0]) == ("lookback", "volume")


def test_seeded_random_candidates_repeat_and_respect_hard_budget():
    api = _search()
    space = {
        "lookback": (10, 20, 30, 40),
        "volume": (Decimal("0.8"), Decimal("1.0"), Decimal("1.2")),
    }
    first = api.random_candidates(space, seed=123, max_trials=5)
    second = api.random_candidates(space, seed=123, max_trials=5)
    changed = api.random_candidates(space, seed=124, max_trials=5)

    assert tuple(dict(item) for item in first) == tuple(dict(item) for item in second)
    assert tuple(dict(item) for item in first) != tuple(dict(item) for item in changed)
    assert len(first) == 5
    assert len({tuple(item.items()) for item in first}) == 5


def test_search_session_records_early_stop_and_cannot_exceed_experiment_budget():
    api = _search()
    experiment = _experiment(max_trials=2)
    ledger = TrialsLedger(experiment)
    session = api.SearchSession(experiment=experiment, ledger=ledger)

    first = session.record(
        parameters={"lookback": 20},
        status=TrialStatus.COMPLETED,
        result_fingerprint="c" * 64,
        reason="",
    )
    second = session.record_early_stopped(
        parameters={"lookback": 30}, reason="no_improvement"
    )

    assert first.ordinal == 1
    assert second.ordinal == 2
    assert second.status is TrialStatus.EARLY_STOPPED
    assert ledger.trial_count == 2
    assert session.remaining_budget == 0

    with pytest.raises(Exception):
        session.record_early_stopped(parameters={"lookback": 40}, reason="overflow")


def test_oos_view_latches_search_closed_without_reopening_unused_budget():
    api = _search()
    experiment = _experiment(max_trials=3)
    ledger = TrialsLedger(experiment)
    session = api.SearchSession(experiment=experiment, ledger=ledger)

    session.record_early_stopped(parameters={"lookback": 20}, reason="screened")
    assert session.remaining_budget == 2
    session.mark_oos_viewed()
    assert session.oos_viewed is True
    assert session.search_closed is True
    assert session.remaining_budget == 2

    with pytest.raises(api.SearchError):
        session.record_early_stopped(parameters={"lookback": 30}, reason="late_search")
    with pytest.raises(api.SearchError):
        session.reopen_search()


def test_parameter_stability_report_is_order_independent_and_top_band_explicit():
    api = _stability()
    observations = (
        api.ParameterObservation(
            parameters={"lookback": 20, "volume": Decimal("1.0")},
            score=Decimal("1.50"),
        ),
        api.ParameterObservation(
            parameters={"lookback": 20, "volume": Decimal("1.2")},
            score=Decimal("1.45"),
        ),
        api.ParameterObservation(
            parameters={"lookback": 30, "volume": Decimal("1.0")},
            score=Decimal("1.10"),
        ),
    )
    first = api.ParameterStabilityReport.create(observations, top_n=2)
    second = api.ParameterStabilityReport.create(tuple(reversed(observations)), top_n=2)

    assert first.fingerprint == second.fingerprint
    assert first.observation_count == 3
    assert first.top_n == 2
    assert first.consensus["lookback"] == 20
    assert first.consensus["volume"] is None


def test_parameter_stability_rejects_float_scores_and_invalid_top_n():
    api = _stability()
    with pytest.raises(api.StabilityError):
        api.ParameterObservation(parameters={"x": 1}, score=1.2)

    observation = api.ParameterObservation(parameters={"x": 1}, score=Decimal("1"))
    with pytest.raises(api.StabilityError):
        api.ParameterStabilityReport.create((observation,), top_n=0)
    with pytest.raises(api.StabilityError):
        api.ParameterStabilityReport.create((observation,), top_n=2)
