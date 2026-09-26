from decimal import Decimal

import pytest

from engine.research.overfitting import OverfittingError, overfitting_evidence


def test_insufficient_trials_and_degenerate_samples_fail_closed():
    with pytest.raises(OverfittingError):
        overfitting_evidence(((Decimal("1"),),), ledger_trial_count=1)
    with pytest.raises(OverfittingError):
        overfitting_evidence(((Decimal("1"),) * 8, (Decimal("1"),) * 8), ledger_trial_count=2)


def test_seeded_overfitting_evidence_is_replayable_and_ledger_bound():
    observations = ((Decimal("1"), Decimal("2"), Decimal("-1"), Decimal("3"),
                     Decimal("2"), Decimal("-2"), Decimal("1"), Decimal("3")),
                    (Decimal("2"), Decimal("-1"), Decimal("3"), Decimal("1"),
                     Decimal("-1"), Decimal("2"), Decimal("2"), Decimal("1")))
    first = overfitting_evidence(observations, ledger_trial_count=3, seed=17)
    second = overfitting_evidence(observations, ledger_trial_count=3, seed=17)
    assert first.fingerprint == second.fingerprint
    assert Decimal(0) <= first.pbo <= Decimal(1)
    assert first.trial_count == 3
