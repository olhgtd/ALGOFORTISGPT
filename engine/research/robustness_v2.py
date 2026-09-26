"""Deterministic scenario evaluation and circular-block MC drawdown."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import random
from types import MappingProxyType
from typing import Mapping

from engine.reproducibility.codec import CanonicalCodec
STRESS_FAMILIES = frozenset(("bootstrap", "monte_carlo", "sensitivity", "regime",
                             "cost", "slippage", "delay", "missing_feed", "bad_feed"))


class RobustnessError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RobustnessReport:
    scores: Mapping[str, Decimal]
    mc_drawdown_p95: Decimal
    fingerprint: str
    version: str = "algofortis-robustness-circular-block/v1"


def _max_drawdown(returns: tuple[Decimal, ...]) -> Decimal:
    equity = peak = Decimal(0)
    maximum = Decimal(0)
    for value in returns:
        equity += value
        peak = max(peak, equity)
        maximum = max(maximum, peak - equity)
    return maximum


def evaluate_robustness(scenarios: Mapping[str, tuple[Decimal, ...]], *,
                        seed: int, draws: int, block_length: int) -> RobustnessReport:
    if not isinstance(scenarios, Mapping) or set(scenarios) != STRESS_FAMILIES:
        raise RobustnessError("all nine stress scenarios are required")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise RobustnessError("seed must be nonnegative int")
    if any(isinstance(x, bool) or not isinstance(x, int) or x <= 0 for x in (draws, block_length)) or draws < 100:
        raise RobustnessError("at least 100 draws and a positive block length required")
    normalized = {}
    for family in sorted(STRESS_FAMILIES):
        series = scenarios[family]
        if (not isinstance(series, tuple) or len(series) < 20 or
                any(not isinstance(x, Decimal) or not x.is_finite() for x in series)):
            raise RobustnessError(f"{family} needs at least 20 finite Decimal outcomes")
        if block_length > len(series):
            raise RobustnessError("block_length exceeds sample length")
        normalized[family] = series
    reference = normalized["monte_carlo"]
    rng = random.Random(seed)
    drawdowns = []
    for _ in range(draws):
        sample = []
        while len(sample) < len(reference):
            start = rng.randrange(len(reference))
            sample.extend(reference[(start + offset) % len(reference)] for offset in range(block_length))
        drawdowns.append(_max_drawdown(tuple(sample[:len(reference)])))
    drawdowns.sort()
    p95 = drawdowns[(95 * (draws - 1) + 99) // 100]
    scores = MappingProxyType({key: sum(value) / len(value) for key, value in normalized.items()})
    fingerprint = CanonicalCodec.fingerprint("algofortis-robustness-evidence/v1", (
        ("scenarios", tuple(normalized.items())), ("seed", seed), ("draws", draws),
        ("block_length", block_length), ("scores", tuple(scores.items())),
        ("mc_drawdown_p95", p95)))
    return RobustnessReport(scores, p95, fingerprint)
