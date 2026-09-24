"""Versioned, research-only split and robustness evidence contracts."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from engine.reproducibility.codec import CanonicalCodec


class EvidenceError(ValueError):
    pass


STRESS_FAMILIES = frozenset(("bootstrap", "monte_carlo", "sensitivity", "regime",
                             "cost", "slippage", "delay", "missing_feed", "bad_feed"))


def _finite(value: object) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise EvidenceError("score must be a finite Decimal")
    return value


@dataclass(frozen=True, slots=True)
class SplitWindow:
    start: int
    end: int

    def __post_init__(self) -> None:
        if any(isinstance(x, bool) or not isinstance(x, int) for x in (self.start, self.end)) or self.start < 0 or self.end <= self.start:
            raise EvidenceError("split requires nonnegative, increasing bar offsets")


@dataclass(frozen=True, slots=True)
class ValidationBundle:
    train: SplitWindow
    validation: SplitWindow
    test: SplitWindow
    dataset_ref: str
    wfo_scores: tuple[Decimal, ...]
    oos_score: Decimal
    stress_scores: Mapping[str, Decimal]
    fingerprint: str
    schema_version: str = "algofortis-validation-bundle/v1"

    @classmethod
    def create(cls, *, train: SplitWindow, validation: SplitWindow, test: SplitWindow,
               dataset_ref: str, wfo_scores: tuple[Decimal, ...], oos_score: Decimal,
               stress_scores: Mapping[str, Decimal]) -> "ValidationBundle":
        if not all(isinstance(x, SplitWindow) for x in (train, validation, test)):
            raise EvidenceError("all splits must be SplitWindow")
        if train.end > validation.start or validation.end > test.start:
            raise EvidenceError("train/validation/test splits overlap")
        if not isinstance(dataset_ref, str) or "@" not in dataset_ref or dataset_ref.startswith("synthetic/"):
            raise EvidenceError("licensed versioned dataset reference required")
        if not isinstance(wfo_scores, tuple) or not wfo_scores:
            raise EvidenceError("WFO evidence required")
        scores = tuple(_finite(x) for x in wfo_scores)
        oos = _finite(oos_score)
        if not isinstance(stress_scores, Mapping) or set(stress_scores) != STRESS_FAMILIES:
            raise EvidenceError("all robustness and feed-stress families required")
        stresses = MappingProxyType({key: _finite(stress_scores[key]) for key in sorted(STRESS_FAMILIES)})
        fingerprint = CanonicalCodec.fingerprint("algofortis-validation-bundle/v1", (
            ("train", (train.start, train.end)), ("validation", (validation.start, validation.end)),
            ("test", (test.start, test.end)), ("dataset_ref", dataset_ref),
            ("wfo_scores", scores), ("oos_score", oos),
            ("stress_scores", tuple(stresses.items())),
        ))
        return cls(train, validation, test, dataset_ref, scores, oos, stresses, fingerprint)
