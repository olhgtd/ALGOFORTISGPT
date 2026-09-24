"""Deterministic, budgeted research-search primitives for AlgoFortis V2.

Search is strictly research-only.  The experiment's max_trials value is immutable,
and viewing OOS evidence permanently closes further search for that session.
"""

from __future__ import annotations

from hashlib import sha256
from itertools import product
from types import MappingProxyType
from typing import Mapping

from engine.reproducibility.codec import CanonicalCodec, CanonicalEncodingError
from engine.research.experiments import ExperimentSpec
from engine.research.trials import (
    TrialRecord,
    TrialStatus,
    TrialsLedger,
    TrialsLedgerError,
)


class SearchError(ValueError):
    """Raised when a research search violates its deterministic budget contract."""


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SearchError(f"{name} must be a positive integer")
    return value


def _canonical_value_key(value: object) -> bytes:
    try:
        return CanonicalCodec.encode_value(value)
    except CanonicalEncodingError as exc:
        raise SearchError(f"parameter-space value is not canonical: {type(value).__name__}") from exc


def _normalize_space(
    parameter_space: Mapping[str, tuple[object, ...] | list[object]],
) -> tuple[tuple[str, tuple[object, ...]], ...]:
    if not isinstance(parameter_space, Mapping) or not parameter_space:
        raise SearchError("parameter_space must be a non-empty mapping")
    normalized: list[tuple[str, tuple[object, ...]]] = []
    for raw_name, raw_values in parameter_space.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise SearchError("parameter names must be non-empty strings")
        name = raw_name.strip()
        if not isinstance(raw_values, (tuple, list)) or not raw_values:
            raise SearchError(f"parameter {name} must have at least one candidate")
        keyed: list[tuple[bytes, object]] = []
        seen: set[bytes] = set()
        for value in raw_values:
            key = _canonical_value_key(value)
            if key in seen:
                raise SearchError(f"parameter {name} contains duplicate candidates")
            seen.add(key)
            keyed.append((key, value))
        values = tuple(value for _, value in sorted(keyed, key=lambda item: item[0]))
        normalized.append((name, values))
    names = [name for name, _ in normalized]
    if len(names) != len(set(names)):
        raise SearchError("parameter names must be unique")
    return tuple(sorted(normalized, key=lambda item: item[0]))


def _all_candidates(
    parameter_space: Mapping[str, tuple[object, ...] | list[object]],
) -> tuple[Mapping[str, object], ...]:
    normalized = _normalize_space(parameter_space)
    names = tuple(name for name, _ in normalized)
    value_sets = tuple(values for _, values in normalized)
    return tuple(
        MappingProxyType(dict(zip(names, values, strict=True)))
        for values in product(*value_sets)
    )


def grid_candidates(
    parameter_space: Mapping[str, tuple[object, ...] | list[object]],
    *,
    max_trials: int,
) -> tuple[Mapping[str, object], ...]:
    """Return the first deterministic grid candidates up to the hard budget."""

    budget = _positive_int(max_trials, "max_trials")
    candidates = _all_candidates(parameter_space)
    return candidates[:budget]


def _candidate_fingerprint(candidate: Mapping[str, object]) -> str:
    fields = tuple((name, value) for name, value in sorted(candidate.items()))
    return CanonicalCodec.fingerprint("algofortis-search-candidate/v1", fields)


def random_candidates(
    parameter_space: Mapping[str, tuple[object, ...] | list[object]],
    *,
    seed: int,
    max_trials: int,
) -> tuple[Mapping[str, object], ...]:
    """Return a seed-ranked deterministic sample without replacement.

    Ranking uses SHA-256(seed, candidate fingerprint) rather than process-global
    randomness, so the same seed and parameter space replay identically.
    """

    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise SearchError("seed must be a non-negative integer")
    budget = _positive_int(max_trials, "max_trials")
    candidates = _all_candidates(parameter_space)
    if budget > len(candidates):
        raise SearchError("max_trials exceeds the unique parameter-space size")

    def rank(candidate: Mapping[str, object]) -> tuple[bytes, str]:
        fingerprint = _candidate_fingerprint(candidate)
        payload = b"\0".join(
            (
                b"algofortis-seeded-random-search/v1",
                str(seed).encode("ascii"),
                fingerprint.encode("ascii"),
            )
        )
        return sha256(payload).digest(), fingerprint

    return tuple(sorted(candidates, key=rank)[:budget])


class SearchSession:
    """One frozen-budget search session backed by the append-only trials ledger."""

    def __init__(self, *, experiment: ExperimentSpec, ledger: TrialsLedger) -> None:
        if not isinstance(experiment, ExperimentSpec):
            raise SearchError("experiment must be ExperimentSpec")
        if not isinstance(ledger, TrialsLedger):
            raise SearchError("ledger must be TrialsLedger")
        if ledger.experiment.experiment_id != experiment.experiment_id:
            raise SearchError("ledger is bound to a different experiment")
        self._experiment = experiment
        self._ledger = ledger
        self._oos_viewed = False
        self._search_closed = False

    @property
    def remaining_budget(self) -> int:
        return self._ledger.remaining_budget

    @property
    def oos_viewed(self) -> bool:
        return self._oos_viewed

    @property
    def search_closed(self) -> bool:
        return self._search_closed

    def mark_oos_viewed(self) -> None:
        """Permanently close parameter search after OOS evidence is viewed."""

        self._oos_viewed = True
        self._search_closed = True

    def reopen_search(self) -> None:
        raise SearchError("a frozen experiment search cannot be reopened")

    def record(
        self,
        *,
        parameters: Mapping[str, object],
        status: TrialStatus,
        result_fingerprint: str | None,
        reason: str,
    ) -> TrialRecord:
        if self._search_closed:
            raise SearchError("search is closed; OOS evidence has already been viewed")
        record = TrialRecord.create(
            experiment=self._experiment,
            ordinal=self._ledger.trial_count + 1,
            parameters=parameters,
            status=status,
            result_fingerprint=result_fingerprint,
            reason=reason,
        )
        try:
            return self._ledger.append(record)
        except TrialsLedgerError as exc:
            raise SearchError(str(exc)) from exc

    def record_early_stopped(
        self,
        *,
        parameters: Mapping[str, object],
        reason: str,
    ) -> TrialRecord:
        return self.record(
            parameters=parameters,
            status=TrialStatus.EARLY_STOPPED,
            result_fingerprint=None,
            reason=reason,
        )


__all__ = [
    "SearchError",
    "grid_candidates",
    "random_candidates",
    "SearchSession",
]
