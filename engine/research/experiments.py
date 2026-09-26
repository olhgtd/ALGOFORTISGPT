"""Immutable deterministic experiment identity and registry for AlgoFortis V2."""

from __future__ import annotations

from dataclasses import dataclass
import re

from engine.reproducibility.codec import CanonicalCodec


_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
_EXPERIMENT_SCHEMA = "algofortis-experiment-spec/v1"


class ExperimentError(ValueError):
    """Raised when experiment evidence is invalid, ambiguous or mutable."""


def _text(value: object, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ExperimentError(f"{name} must be a string")
    normalized = value.strip()
    if not allow_empty and not normalized:
        raise ExperimentError(f"{name} must be non-empty")
    return normalized


def _fingerprint(value: object, name: str) -> str:
    normalized = _text(value, name)
    if not _FINGERPRINT_RE.fullmatch(normalized):
        raise ExperimentError(f"{name} must be lowercase 64-character hex")
    return normalized


def _sorted_unique(values: object, name: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)):
        raise ExperimentError(f"{name} must be a tuple/list")
    normalized = tuple(_text(item, name) for item in values)
    if not allow_empty and not normalized:
        raise ExperimentError(f"{name} must not be empty")
    if len(normalized) != len(set(normalized)):
        raise ExperimentError(f"{name} must contain unique values")
    return tuple(sorted(normalized))


@dataclass(frozen=True, slots=True)
class ExperimentSpec:
    experiment_id: str
    fingerprint: str
    strategy_id: str
    strategy_version: str
    code_fingerprint: str
    dataset_versions: tuple[str, ...]
    config_snapshot_id: str
    seed: int
    environment_fingerprint: str
    max_trials: int
    parent_experiment_id: str | None
    tags: tuple[str, ...]
    note: str
    schema_version: str = _EXPERIMENT_SCHEMA

    @classmethod
    def create(
        cls,
        *,
        strategy_id: str,
        strategy_version: str,
        code_fingerprint: str,
        dataset_versions: tuple[str, ...] | list[str],
        config_snapshot_id: str,
        seed: int,
        environment_fingerprint: str,
        max_trials: int,
        parent_experiment_id: str | None = None,
        tags: tuple[str, ...] | list[str] = (),
        note: str = "",
    ) -> "ExperimentSpec":
        strategy_id = _text(strategy_id, "strategy_id")
        strategy_version = _text(strategy_version, "strategy_version")
        code_fingerprint = _fingerprint(code_fingerprint, "code_fingerprint")
        dataset_versions = _sorted_unique(dataset_versions, "dataset_versions")
        config_snapshot_id = _text(config_snapshot_id, "config_snapshot_id")
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            raise ExperimentError("seed must be a non-negative integer")
        environment_fingerprint = _fingerprint(
            environment_fingerprint, "environment_fingerprint"
        )
        if isinstance(max_trials, bool) or not isinstance(max_trials, int) or max_trials <= 0:
            raise ExperimentError("max_trials must be a positive integer")
        if parent_experiment_id is not None:
            parent_experiment_id = _text(parent_experiment_id, "parent_experiment_id")
        tags = _sorted_unique(tags, "tags", allow_empty=True)
        note = _text(note, "note", allow_empty=True)

        fingerprint = CanonicalCodec.fingerprint(
            _EXPERIMENT_SCHEMA,
            (
                ("strategy_id", strategy_id),
                ("strategy_version", strategy_version),
                ("code_fingerprint", code_fingerprint),
                ("dataset_versions", dataset_versions),
                ("config_snapshot_id", config_snapshot_id),
                ("seed", seed),
                ("environment_fingerprint", environment_fingerprint),
                ("max_trials", max_trials),
                ("parent_experiment_id", parent_experiment_id),
                ("tags", tags),
                ("note", note),
            ),
        )
        return cls(
            experiment_id=f"exp_{fingerprint}",
            fingerprint=fingerprint,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            code_fingerprint=code_fingerprint,
            dataset_versions=dataset_versions,
            config_snapshot_id=config_snapshot_id,
            seed=seed,
            environment_fingerprint=environment_fingerprint,
            max_trials=max_trials,
            parent_experiment_id=parent_experiment_id,
            tags=tags,
            note=note,
        )


class ExperimentRegistry:
    """Append-only in-memory authority for immutable experiment specifications."""

    def __init__(self) -> None:
        self._experiments: dict[str, ExperimentSpec] = {}

    def register(self, experiment: ExperimentSpec) -> ExperimentSpec:
        if not isinstance(experiment, ExperimentSpec):
            raise ExperimentError("experiment must be ExperimentSpec")
        if experiment.experiment_id in self._experiments:
            raise ExperimentError("experiment is already registered")
        self._experiments[experiment.experiment_id] = experiment
        return experiment

    def get(self, experiment_id: str) -> ExperimentSpec:
        experiment_id = _text(experiment_id, "experiment_id")
        try:
            return self._experiments[experiment_id]
        except KeyError as exc:
            raise ExperimentError("experiment is not registered") from exc

    def list_experiments(self) -> tuple[ExperimentSpec, ...]:
        return tuple(
            sorted(self._experiments.values(), key=lambda item: item.experiment_id)
        )


__all__ = ["ExperimentError", "ExperimentSpec", "ExperimentRegistry"]
