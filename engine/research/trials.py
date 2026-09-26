"""Append-only deterministic research trials ledger for AlgoFortis V2."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
import re
from types import MappingProxyType
from typing import Mapping

from engine.reproducibility.codec import CanonicalCodec
from engine.research.experiments import ExperimentSpec


_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
_TRIAL_ID_SCHEMA = "algofortis-trial-id/v1"
_TRIAL_RECORD_SCHEMA = "algofortis-trial-record/v1"


class TrialError(ValueError):
    """Raised when trial evidence is structurally invalid."""


class TrialsLedgerError(ValueError):
    """Raised when an append would violate ledger authority or budget."""


class TrialStatus(str, Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    EARLY_STOPPED = "EARLY_STOPPED"


def _text(value: object, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise TrialError(f"{name} must be a string")
    normalized = value.strip()
    if not allow_empty and not normalized:
        raise TrialError(f"{name} must be non-empty")
    return normalized


def _result_fingerprint(value: object | None) -> str | None:
    if value is None:
        return None
    normalized = _text(value, "result_fingerprint")
    if not _FINGERPRINT_RE.fullmatch(normalized):
        raise TrialError("result_fingerprint must be lowercase 64-character hex")
    return normalized


def _freeze(value: object) -> object:
    if value is None or isinstance(value, (bool, int, str, Decimal)):
        if isinstance(value, Decimal) and not value.is_finite():
            raise TrialError("parameter Decimal values must be finite")
        return value
    if isinstance(value, float):
        raise TrialError("float parameters are not canonical; use Decimal")
    if isinstance(value, Mapping):
        frozen: dict[str, object] = {}
        for raw_key, raw_value in value.items():
            key = _text(raw_key, "parameter name")
            if key in frozen:
                raise TrialError("duplicate parameter name")
            frozen[key] = _freeze(raw_value)
        return MappingProxyType(dict(sorted(frozen.items())))
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        raise TrialError("unordered parameter collections are forbidden")
    raise TrialError(f"unsupported parameter type: {type(value).__name__}")


def _canonical(value: object) -> object:
    if isinstance(value, Mapping):
        return tuple((key, _canonical(item)) for key, item in sorted(value.items()))
    if isinstance(value, tuple):
        return tuple(_canonical(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class TrialRecord:
    trial_id: str
    experiment_id: str
    ordinal: int
    parameters: Mapping[str, object]
    parameter_fingerprint: str
    status: TrialStatus
    result_fingerprint: str | None
    reason: str
    fingerprint: str

    @classmethod
    def create(
        cls,
        *,
        experiment: ExperimentSpec,
        ordinal: int,
        parameters: Mapping[str, object],
        status: TrialStatus,
        result_fingerprint: str | None,
        reason: str,
    ) -> "TrialRecord":
        if not isinstance(experiment, ExperimentSpec):
            raise TrialError("experiment must be ExperimentSpec")
        if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal <= 0:
            raise TrialError("ordinal must be a positive integer")
        if not isinstance(parameters, Mapping):
            raise TrialError("parameters must be a mapping")
        frozen = _freeze(parameters)
        if not isinstance(frozen, Mapping):
            raise TrialError("parameters must freeze to a mapping")
        try:
            status = TrialStatus(status)
        except (TypeError, ValueError) as exc:
            raise TrialError("unsupported trial status") from exc
        result_fingerprint = _result_fingerprint(result_fingerprint)
        reason = _text(reason, "reason", allow_empty=True)
        if status is TrialStatus.COMPLETED:
            if result_fingerprint is None:
                raise TrialError("COMPLETED trial requires result_fingerprint")
        else:
            if not reason:
                raise TrialError("non-completed trial requires a reason")

        parameter_fingerprint = CanonicalCodec.fingerprint(
            "algofortis-trial-parameters/v1",
            (("parameters", _canonical(frozen)),),
        )
        trial_digest = CanonicalCodec.fingerprint(
            _TRIAL_ID_SCHEMA,
            (
                ("experiment_id", experiment.experiment_id),
                ("ordinal", ordinal),
                ("parameter_fingerprint", parameter_fingerprint),
            ),
        )
        trial_id = f"trial_{trial_digest}"
        fingerprint = CanonicalCodec.fingerprint(
            _TRIAL_RECORD_SCHEMA,
            (
                ("trial_id", trial_id),
                ("experiment_id", experiment.experiment_id),
                ("ordinal", ordinal),
                ("parameter_fingerprint", parameter_fingerprint),
                ("status", status),
                ("result_fingerprint", result_fingerprint),
                ("reason", reason),
            ),
        )
        return cls(
            trial_id=trial_id,
            experiment_id=experiment.experiment_id,
            ordinal=ordinal,
            parameters=frozen,
            parameter_fingerprint=parameter_fingerprint,
            status=status,
            result_fingerprint=result_fingerprint,
            reason=reason,
            fingerprint=fingerprint,
        )


class TrialsLedger:
    """In-memory append-only trial authority bound to one experiment budget."""

    def __init__(self, experiment: ExperimentSpec) -> None:
        if not isinstance(experiment, ExperimentSpec):
            raise TrialsLedgerError("experiment must be ExperimentSpec")
        self._experiment = experiment
        self._records: list[TrialRecord] = []
        self._trial_ids: set[str] = set()

    @property
    def experiment(self) -> ExperimentSpec:
        return self._experiment

    @property
    def trial_count(self) -> int:
        return len(self._records)

    @property
    def remaining_budget(self) -> int:
        return self._experiment.max_trials - len(self._records)

    def append(self, record: TrialRecord) -> TrialRecord:
        if not isinstance(record, TrialRecord):
            raise TrialsLedgerError("record must be TrialRecord")
        if record.experiment_id != self._experiment.experiment_id:
            raise TrialsLedgerError("trial belongs to a different experiment")
        if len(self._records) >= self._experiment.max_trials:
            raise TrialsLedgerError("experiment trial budget is exhausted")
        expected_ordinal = len(self._records) + 1
        if record.ordinal != expected_ordinal:
            raise TrialsLedgerError(
                f"trial ordinal must be contiguous; expected {expected_ordinal}"
            )
        if record.trial_id in self._trial_ids:
            raise TrialsLedgerError("trial is already recorded")
        self._records.append(record)
        self._trial_ids.add(record.trial_id)
        return record

    def records(self) -> tuple[TrialRecord, ...]:
        return tuple(self._records)


__all__ = [
    "TrialError",
    "TrialsLedgerError",
    "TrialStatus",
    "TrialRecord",
    "TrialsLedger",
]
