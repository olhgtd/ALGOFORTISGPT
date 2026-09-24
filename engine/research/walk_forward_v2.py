"""Versioned split-owned walk-forward execution of research observations."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from engine.reproducibility.codec import CanonicalCodec


class WalkForwardError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WalkForwardPlan:
    train_bars: int
    validation_bars: int
    test_bars: int
    embargo_bars: int
    step_bars: int
    allow_prior_oos_in_train: bool = False
    version: str = "algofortis-wfo-plan/v1"

    def __post_init__(self) -> None:
        for name in ("train_bars", "validation_bars", "test_bars", "embargo_bars", "step_bars"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < (0 if name == "embargo_bars" else 1):
                raise WalkForwardError(f"{name} invalid")
        if not isinstance(self.allow_prior_oos_in_train, bool):
            raise WalkForwardError("OOS reuse flag must be explicit bool")


@dataclass(frozen=True, slots=True)
class WalkForwardWindow:
    train_start: int
    train_end: int
    validation_start: int
    validation_end: int
    test_start: int
    test_end: int
    selected_parameters: str
    oos_score: Decimal


@dataclass(frozen=True, slots=True)
class WalkForwardEvidence:
    windows: tuple[WalkForwardWindow, ...]
    fingerprint: str
    plan: WalkForwardPlan


@dataclass(frozen=True, slots=True)
class FinalHoldoutEvidence:
    start: int
    end: int
    parameters: str
    score: Decimal
    wfo_fingerprint: str
    fingerprint: str


def evaluate_final_holdout(observations: tuple[Decimal, ...], *, start: int, end: int,
                           wfo: WalkForwardEvidence,
                           score: Callable[[str, tuple[Decimal, ...]], Decimal]) -> FinalHoldoutEvidence:
    if not isinstance(wfo, WalkForwardEvidence) or not wfo.windows or not callable(score):
        raise WalkForwardError("frozen WFO selection and scorer required")
    if (isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int)
            or not isinstance(end, int) or start < max(w.test_end for w in wfo.windows)
            or end <= start or not isinstance(observations, tuple) or end > len(observations)
            or any(not isinstance(x, Decimal) or not x.is_finite() for x in observations)):
        raise WalkForwardError("final OOS must follow all WFO windows without overlap")
    parameters = wfo.windows[-1].selected_parameters
    result = score(parameters, observations[start:end])
    if not isinstance(result, Decimal) or not result.is_finite():
        raise WalkForwardError("final OOS score must be finite Decimal")
    fingerprint = CanonicalCodec.fingerprint("algofortis-final-oos/v1", (
        ("observations", observations[start:end]), ("start", start), ("end", end),
        ("parameters", parameters), ("score", result), ("wfo", wfo.fingerprint)))
    return FinalHoldoutEvidence(start, end, parameters, result, wfo.fingerprint, fingerprint)


def execute_walk_forward(observations: tuple[Decimal, ...], plan: WalkForwardPlan, *,
                         select: Callable[[tuple[Decimal, ...], tuple[Decimal, ...]], str],
                         score: Callable[[str, tuple[Decimal, ...]], Decimal]) -> WalkForwardEvidence:
    if not isinstance(plan, WalkForwardPlan) or not isinstance(observations, tuple) or any(
        not isinstance(x, Decimal) or not x.is_finite() for x in observations):
        raise WalkForwardError("finite Decimal observation tuple and versioned plan required")
    if not callable(select) or not callable(score):
        raise WalkForwardError("selection and OOS scoring callbacks required")
    length = plan.train_bars + plan.validation_bars + plan.embargo_bars + plan.test_bars
    if len(observations) < length:
        raise WalkForwardError("insufficient observations for one WFO window")
    windows = []
    previous_tests: list[tuple[int, int]] = []
    for start in range(0, len(observations) - length + 1, plan.step_bars):
        train_end = start + plan.train_bars
        validation_end = train_end + plan.validation_bars
        test_start = validation_end + plan.embargo_bars
        test_end = test_start + plan.test_bars
        if not plan.allow_prior_oos_in_train and any(a < validation_end and b > start for a, b in previous_tests):
            break
        train = observations[start:train_end]
        validation = observations[train_end:validation_end]
        unseen = observations[test_start:test_end]
        params = select(train, validation)
        if not isinstance(params, str) or "@" not in params:
            raise WalkForwardError("selection must return versioned parameter reference")
        oos = score(params, unseen)
        if not isinstance(oos, Decimal) or not oos.is_finite():
            raise WalkForwardError("OOS scorer must return finite Decimal")
        windows.append(WalkForwardWindow(start, train_end, train_end, validation_end,
                                         test_start, test_end, params, oos))
        previous_tests.append((test_start, test_end))
    if not windows:
        raise WalkForwardError("no uncontaminated WFO windows")
    fingerprint = CanonicalCodec.fingerprint("algofortis-wfo-evidence/v1", (
        ("observations", observations), ("plan", (plan.train_bars, plan.validation_bars,
          plan.test_bars, plan.embargo_bars, plan.step_bars, plan.allow_prior_oos_in_train, plan.version)),
        ("windows", tuple((w.train_start, w.train_end, w.validation_start, w.validation_end,
                           w.test_start, w.test_end, w.selected_parameters, w.oos_score) for w in windows)),
    ))
    return WalkForwardEvidence(tuple(windows), fingerprint, plan)
