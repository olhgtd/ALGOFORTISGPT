"""Research-only DSR approximation and CSCV PBO v1.

Returns are dimensionless Decimal observations. Analytics use binary float
with 1e-9 tolerance; money and order arithmetic never enters this module.
DSR uses Bailey/Lopez de Prado's skew/kurtosis adjusted probabilistic Sharpe
ratio against the expected maximum under N ledgered trials. PBO uses four
contiguous blocks and six combinatorial train/test splits. This evidence is
diagnostic, never sufficient for promotion by itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations
from math import erf, isfinite, log, sqrt
from statistics import NormalDist, mean, pstdev

from engine.reproducibility.codec import CanonicalCodec


class OverfittingError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OverfittingEvidence:
    trial_count: int
    dsr: Decimal
    pbo: Decimal
    fingerprint: str
    formula_version: str = "dsr-cscv-four-block/v1"
    analytic_tolerance: Decimal = Decimal("0.000000001")


def _sharpe(values: tuple[float, ...]) -> float:
    deviation = pstdev(values)
    if deviation <= 1e-12:
        raise OverfittingError("degenerate zero-variance return sample")
    return mean(values) / deviation


def overfitting_evidence(returns_by_candidate: tuple[tuple[Decimal, ...], ...], *,
                         ledger_trial_count: int, seed: int = 0) -> OverfittingEvidence:
    if isinstance(ledger_trial_count, bool) or not isinstance(ledger_trial_count, int) or ledger_trial_count < 2:
        raise OverfittingError("at least two ledgered attempts required")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise OverfittingError("seed must be a nonnegative integer")
    if not isinstance(returns_by_candidate, tuple) or len(returns_by_candidate) < 2 or len(returns_by_candidate) > ledger_trial_count:
        raise OverfittingError("candidate count cannot exceed ledger attempts")
    width = len(returns_by_candidate[0])
    if width < 8 or width % 4:
        raise OverfittingError("at least eight observations divisible into four blocks required")
    rows: list[tuple[float, ...]] = []
    for candidate in returns_by_candidate:
        if not isinstance(candidate, tuple) or len(candidate) != width or any(not isinstance(x, Decimal) or not x.is_finite() for x in candidate):
            raise OverfittingError("candidate observations must be aligned finite Decimals")
        row = tuple(float(x) for x in candidate)
        if not all(isfinite(x) for x in row):
            raise OverfittingError("overflow in analytic conversion")
        _sharpe(row)
        rows.append(row)
    best = max(rows, key=_sharpe)
    sr = _sharpe(best)
    n = len(best)
    avg = mean(best)
    sd = pstdev(best)
    skew = mean(((x - avg) / sd) ** 3 for x in best)
    kurt = mean(((x - avg) / sd) ** 4 for x in best)
    denominator = 1 - skew * sr + ((kurt - 1) / 4) * sr * sr
    if denominator <= 0:
        raise OverfittingError("DSR variance correction is nonpositive")
    normal = NormalDist()
    expected_max = ((1 - 0.5772156649) * normal.inv_cdf(1 - 1 / ledger_trial_count)
                    + 0.5772156649 * normal.inv_cdf(1 - 1 / (ledger_trial_count * 2.718281828)))
    threshold = max(0.0, expected_max / sqrt(n))
    z = (sr - threshold) * sqrt(n - 1) / sqrt(denominator)
    dsr = (1 + erf(z / sqrt(2))) / 2
    block = width // 4
    losses = 0
    splits = 0
    for train_blocks in combinations(range(4), 2):
        test_blocks = tuple(i for i in range(4) if i not in train_blocks)
        def sample(row: tuple[float, ...], blocks: tuple[int, ...]) -> tuple[float, ...]:
            return tuple(row[i] for b in blocks for i in range(b * block, (b + 1) * block))
        selected = max(range(len(rows)), key=lambda i: (_sharpe(sample(rows[i], train_blocks)), -i))
        oos = [_sharpe(sample(row, test_blocks)) for row in rows]
        rank = sum(value < oos[selected] for value in oos) + 0.5 * sum(value == oos[selected] for value in oos)
        if rank / len(rows) <= 0.5:
            losses += 1
        splits += 1
    pbo = losses / splits
    dsr_d, pbo_d = Decimal(str(dsr)), Decimal(str(pbo))
    fingerprint = CanonicalCodec.fingerprint("algofortis-overfitting-evidence/v1", (
        ("returns", returns_by_candidate), ("ledger_trial_count", ledger_trial_count),
        ("seed", seed), ("dsr", dsr_d), ("pbo", pbo_d)))
    return OverfittingEvidence(ledger_trial_count, dsr_d, pbo_d, fingerprint)
