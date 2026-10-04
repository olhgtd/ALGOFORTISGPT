"""Immutable, deterministic Slice 11 validation contracts and calculations.

This module consumes prior-slice evidence.  It deliberately does not run a
strategy, execute an order, mutate a portfolio, retrieve FX, or authorise
Paper/Live trading.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, localcontext
from enum import Enum
import random
from types import MappingProxyType
from itertools import product
from typing import Iterable, Mapping

from engine.portfolio.model import INTERNAL_DECIMAL_CONTEXT, InstrumentIdentity, as_decimal
from engine.backtest.metrics import MetricSummary, MetricStatus
from engine.backtest.regime import EntryRegimeSnapshot, entry_regime_evidence_fingerprint
from engine.reproducibility.codec import CanonicalCodec
from engine.reproducibility.model import ReproducibilityManifest, StructuredFailureResult
from engine.trades import LedgerEventKey


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty")
    return value.strip()


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _duration(value: timedelta, name: str) -> timedelta:
    if not isinstance(value, timedelta) or value <= timedelta(0):
        raise ValueError(f"{name} must be a positive timedelta")
    return value


def _duration_parts(value: timedelta) -> tuple[int, int, int]:
    """Schema-owned exact timedelta representation for D4 validation identities."""
    if not isinstance(value, timedelta):
        raise TypeError("duration value must be timedelta")
    return value.days, value.seconds, value.microseconds


def _embargo_identity_value(value: "EmbargoPolicy | None") -> object:
    """Ordered D4 value for an optional embargo policy; never JSON-serialize it."""
    if value is None:
        return None
    magnitude: int | tuple[int, int, int]
    magnitude = value.value if value.kind is EmbargoKind.BARS else _duration_parts(value.value)
    return value.kind, magnitude, value.version


def _instrument_sort_key(value: InstrumentIdentity) -> tuple[str, str, str, str, str, str, str]:
    """Stable explicit ordering for the frozen full instrument identity."""
    return (
        value.market,
        value.instrument,
        value.segment,
        value.underlying or "",
        "" if value.expiry is None else value.expiry.isoformat(),
        "" if value.strike is None else str(value.strike),
        value.option_type or "",
    )


def _instrument_fields(value: InstrumentIdentity) -> tuple[object, ...]:
    """Canonical D4 fields for one full InstrumentIdentity."""
    return (
        value.market,
        value.instrument,
        value.segment,
        value.underlying,
        value.expiry,
        value.strike,
        value.option_type,
    )


def derive_seed(root_seed: int, kind: "RandomizedAnalysisKind", identity: str) -> int:
    if not isinstance(root_seed, int) or isinstance(root_seed, bool) or root_seed < 0:
        raise ValueError("root_seed must be a non-negative integer")
    digest = CanonicalCodec.fingerprint(
        "algofortis-randomized-derived-seed/v2",
        (("root_seed", root_seed), ("analysis_kind", RandomizedAnalysisKind(kind)),
         ("stable_identity", _text(identity, "identity"))),
    )
    return int.from_bytes(bytes.fromhex(digest)[:8], "big")


class ValidationPurpose(str, Enum):
    PROMOTION = "PROMOTION"
    RESEARCH = "RESEARCH"


class ParameterMode(str, Enum):
    FIXED_PARAMETERS = "FIXED_PARAMETERS"
    TRAIN_SELECT_THEN_OOS = "TRAIN_SELECT_THEN_OOS"


class SelectionPolicy(str, Enum):
    MAXIMIZE_TRAINING_METRIC = "MAXIMIZE_TRAINING_METRIC"
    EXPLICIT_CANDIDATE = "EXPLICIT_CANDIDATE"


class WalkForwardModel(str, Enum):
    ROLLING = "ROLLING"
    EXPANDING = "EXPANDING"


class EmbargoKind(str, Enum):
    BARS = "BARS"
    ELAPSED_TIME = "ELAPSED_TIME"
    SESSION_AWARE_TIME = "SESSION_AWARE_TIME"


class RandomizedAnalysisKind(str, Enum):
    BOOTSTRAP = "BOOTSTRAP"
    MC1 = "MC1"
    MC2 = "MC2"


class BootstrapFailureCode(str, Enum):
    """Stable D7 code for a non-finite Step-4A observation."""

    BOOTSTRAP_NON_FINITE_EVIDENCE = "BOOTSTRAP_NON_FINITE_EVIDENCE"


class BootstrapFailureStage(str, Enum):
    """The locked Stage-4A deterministic-analysis boundary."""

    BOOTSTRAP_ANALYSIS = "BOOTSTRAP_ANALYSIS"


class MC1FailureCode(str, Enum):
    MC1_NON_FINITE_EVIDENCE = "MC1_NON_FINITE_EVIDENCE"


class MC1FailureStage(str, Enum):
    MC1_ANALYSIS = "MC1_ANALYSIS"


class MC2FailureCode(str, Enum):
    MC2_NON_FINITE_EVIDENCE = "MC2_NON_FINITE_EVIDENCE"


class MC2FailureStage(str, Enum):
    MC2_ANALYSIS = "MC2_ANALYSIS"


class AggregateBlockUnit(str, Enum):
    """The only approved aggregate MC-2 resampling unit."""

    EPISODES = "EPISODES"


class ValidationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID = "INVALID"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class SensitivityForm(str, Enum):
    COORDINATE = "COORDINATE"
    LOCAL_GRID = "LOCAL_GRID"
    EXPLICIT_CANDIDATE_SET = "EXPLICIT_CANDIDATE_SET"


class SensitivityScope(str, Enum):
    TRAINING = "TRAINING"
    OOS = "OOS"


class SensitivityParameterType(str, Enum):
    INTEGER = "INTEGER"
    DECIMAL = "DECIMAL"
    CATEGORICAL = "CATEGORICAL"


class SensitivityPointStatus(str, Enum):
    VALID = "VALID"
    INELIGIBLE = "INELIGIBLE"
    FAILED = "FAILED"
    INVALID = "INVALID"


class SensitivityReason(str, Enum):
    NO_APPLICABLE_PARAMETER_DOMAIN = "SENSITIVITY_NO_APPLICABLE_PARAMETER_DOMAIN"
    INVALID_PARAMETER_DOMAIN = "SENSITIVITY_INVALID_PARAMETER_DOMAIN"
    DUPLICATE_PARAMETER_NAME = "SENSITIVITY_DUPLICATE_PARAMETER_NAME"
    SELECTED_VALUE_OUTSIDE_DOMAIN = "SENSITIVITY_SELECTED_VALUE_OUTSIDE_DOMAIN"
    GRID_EXCEEDS_POLICY_LIMIT = "SENSITIVITY_GRID_EXCEEDS_POLICY_LIMIT"
    NO_VALID_NEIGHBORS = "SENSITIVITY_NO_VALID_NEIGHBORS"
    BASELINE_NON_POSITIVE = "SENSITIVITY_BASELINE_NON_POSITIVE"
    BASELINE_EVIDENCE_INVALID = "SENSITIVITY_BASELINE_EVIDENCE_INVALID"
    POINT_METRIC_INVALID = "SENSITIVITY_POINT_METRIC_INVALID"
    ZERO_COMPLETED_TRADES = "ZERO_COMPLETED_TRADES"
    NON_VALID = "NON_VALID"
    NO_APPLICABLE_WINDOWS = "SENSITIVITY_NO_APPLICABLE_WINDOWS"


@dataclass(frozen=True)
class EmbargoPolicy:
    kind: EmbargoKind
    value: int | timedelta
    version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", EmbargoKind(self.kind))
        object.__setattr__(self, "version", _text(self.version, "embargo version"))
        if self.kind is EmbargoKind.BARS:
            if not isinstance(self.value, int) or isinstance(self.value, bool) or self.value <= 0:
                raise ValueError("BARS embargo value must be a positive integer")
        elif not isinstance(self.value, timedelta) or self.value <= timedelta(0):
            raise ValueError("time embargo value must be a positive timedelta")


@dataclass(frozen=True)
class ResolvedEmbargoMap:
    version: str
    default: EmbargoPolicy | None = None
    overrides: Mapping[str, EmbargoPolicy] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "version", _text(self.version, "embargo map version"))
        overrides = dict(self.overrides or {})
        if self.default is None and not overrides:
            raise ValueError("an embargo default or override is required")
        if self.default is not None and not isinstance(self.default, EmbargoPolicy):
            raise TypeError("default must be EmbargoPolicy")
        if not all(isinstance(key, str) and key.strip() and isinstance(value, EmbargoPolicy) for key, value in overrides.items()):
            raise TypeError("overrides must map non-empty scope keys to EmbargoPolicy")
        object.__setattr__(self, "overrides", MappingProxyType(dict(sorted(overrides.items()))))

    def resolve(self, scope: str, *, unambiguous_bar_domain: bool = False) -> EmbargoPolicy:
        policy = self.overrides.get(scope, self.default)
        if policy is None:
            raise ValueError("missing resolved embargo policy for scope")
        if policy.kind is EmbargoKind.BARS and not unambiguous_bar_domain:
            raise ValueError("BARS embargo is invalid without one unambiguous bar domain")
        return policy

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-resolved-embargo-map/v2",
            (("version", self.version), ("default", _embargo_identity_value(self.default)),
             ("overrides", tuple((scope, _embargo_identity_value(policy)) for scope, policy in self.overrides.items()))),
        )


@dataclass(frozen=True)
class WalkForwardPolicy:
    model: WalkForwardModel
    training_length: timedelta
    test_length: timedelta
    step: timedelta
    embargo_map: ResolvedEmbargoMap
    boundary_version: str
    drop_incomplete_final_oos: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "model", WalkForwardModel(self.model))
        for name in ("training_length", "test_length", "step"):
            _duration(getattr(self, name), name)
        if not isinstance(self.embargo_map, ResolvedEmbargoMap):
            raise TypeError("embargo_map must be ResolvedEmbargoMap")
        object.__setattr__(self, "boundary_version", _text(self.boundary_version, "boundary_version"))
        if not self.drop_incomplete_final_oos:
            raise ValueError("Slice 11 always drops an incomplete final OOS window")

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-walk-forward-policy/v2",
            (("model", self.model), ("training_length", _duration_parts(self.training_length)),
             ("test_length", _duration_parts(self.test_length)), ("step", _duration_parts(self.step)),
             ("embargo_map", self.embargo_map.fingerprint),
             ("boundary_version", self.boundary_version),
             ("drop_incomplete_final_oos", self.drop_incomplete_final_oos)),
        )


@dataclass(frozen=True)
class ValidationWindow:
    window_id: str
    train_start: datetime
    train_end: datetime
    embargo_start: datetime
    embargo_end: datetime
    oos_start: datetime
    oos_end: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "window_id", _text(self.window_id, "window_id"))
        for name in ("train_start", "train_end", "embargo_start", "embargo_end", "oos_start", "oos_end"):
            _aware(getattr(self, name), name)
        if not (self.train_start < self.train_end <= self.embargo_start <= self.embargo_end <= self.oos_start < self.oos_end):
            raise ValueError("window boundaries must be TRAIN -> EMBARGO -> OOS")


class WalkForwardPlanner:
    """Creates calendar-boundary windows only; it never uses bar counts."""

    @staticmethod
    def build(start: datetime, end: datetime, policy: WalkForwardPolicy, embargo: timedelta) -> tuple[ValidationWindow, ...]:
        _aware(start, "start"); _aware(end, "end")
        if start >= end:
            raise ValueError("start must precede end")
        if not isinstance(policy, WalkForwardPolicy):
            raise TypeError("policy must be WalkForwardPolicy")
        _duration(embargo, "embargo")
        windows: list[ValidationWindow] = []
        cursor = start
        index = 0
        while True:
            train_start = start if policy.model is WalkForwardModel.EXPANDING else cursor
            train_end = cursor + policy.training_length
            embargo_start, embargo_end = train_end, train_end + embargo
            oos_start, oos_end = embargo_end, embargo_end + policy.test_length
            if oos_end > end:
                break
            windows.append(ValidationWindow(f"window-{index:04d}", train_start, train_end, embargo_start, embargo_end, oos_start, oos_end))
            cursor += policy.step
            index += 1
        return tuple(windows)

    @staticmethod
    def validate_purpose(windows: Iterable[ValidationWindow], purpose: ValidationPurpose) -> tuple[ValidationWindow, ...]:
        values = tuple(windows)
        if not all(isinstance(value, ValidationWindow) for value in values):
            raise TypeError("windows must contain ValidationWindow")
        if purpose is ValidationPurpose.PROMOTION:
            ordered = tuple(sorted(values, key=lambda value: (value.oos_start, value.window_id)))
            for left, right in zip(ordered, ordered[1:]):
                if right.oos_start < left.oos_end:
                    raise ValueError("PROMOTION OOS windows must not overlap")
        return values


@dataclass(frozen=True)
class ParameterSelectionEvidence:
    candidate_fingerprint: str
    training_evidence_fingerprint: str
    selected_before_oos: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_fingerprint", _text(self.candidate_fingerprint, "candidate_fingerprint"))
        object.__setattr__(self, "training_evidence_fingerprint", _text(self.training_evidence_fingerprint, "training_evidence_fingerprint"))
        _aware(self.selected_before_oos, "selected_before_oos")


@dataclass(frozen=True)
class ParameterPlan:
    mode: ParameterMode
    parameter_fingerprint: str
    selection_policy: SelectionPolicy | None = None
    candidate_fingerprints: tuple[str, ...] = ()
    selection_evidence: ParameterSelectionEvidence | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", ParameterMode(self.mode))
        object.__setattr__(self, "parameter_fingerprint", _text(self.parameter_fingerprint, "parameter_fingerprint"))
        candidates = tuple(sorted(_text(value, "candidate_fingerprint") for value in self.candidate_fingerprints))
        if len(set(candidates)) != len(candidates):
            raise ValueError("candidate fingerprints must be unique")
        object.__setattr__(self, "candidate_fingerprints", candidates)
        if self.mode is ParameterMode.FIXED_PARAMETERS:
            if self.selection_policy is not None or self.selection_evidence is not None or candidates:
                raise ValueError("fixed parameters cannot carry selection evidence")
        else:
            if self.selection_policy is None or self.selection_evidence is None or not candidates:
                raise ValueError("train-select mode requires explicit policy, candidates, and training evidence")
            object.__setattr__(self, "selection_policy", SelectionPolicy(self.selection_policy))
            if self.parameter_fingerprint not in candidates:
                raise ValueError("selected parameter fingerprint must be a declared candidate")
            if self.selection_evidence.candidate_fingerprint != self.parameter_fingerprint:
                raise ValueError("selection evidence candidate fingerprint must match the selected parameter fingerprint")

    def assert_frozen_before(self, oos_start: datetime) -> None:
        _aware(oos_start, "oos_start")
        if self.selection_evidence is not None and self.selection_evidence.selected_before_oos > oos_start:
            raise ValueError("parameter selection must freeze before OOS")


@dataclass(frozen=True)
class SensitivityParameterValue:
    """One D4-typed, immutable strategy configuration value."""

    parameter_name: str
    parameter_type: SensitivityParameterType
    value: int | Decimal | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameter_name", _text(self.parameter_name, "parameter_name"))
        kind = SensitivityParameterType(self.parameter_type)
        value = self.value
        if kind is SensitivityParameterType.INTEGER:
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError("INTEGER sensitivity values must be non-boolean int")
        elif kind is SensitivityParameterType.DECIMAL:
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError("DECIMAL sensitivity values must be finite Decimal")
        else:
            if not isinstance(value, str) or not value.strip():
                raise ValueError("CATEGORICAL sensitivity values must be non-empty strings")
            value = value.strip()
        object.__setattr__(self, "parameter_type", kind)
        object.__setattr__(self, "value", value)

    @property
    def canonical_tuple(self) -> tuple[str, str, int | Decimal | str]:
        return (self.parameter_name, self.parameter_type.value, self.value)


def _parameter_values(values: Iterable[SensitivityParameterValue], name: str) -> tuple[SensitivityParameterValue, ...]:
    items = tuple(values)
    if not all(isinstance(value, SensitivityParameterValue) for value in items):
        raise TypeError(f"{name} must contain SensitivityParameterValue")
    ordered = tuple(sorted(items, key=lambda value: value.parameter_name))
    if len({value.parameter_name for value in ordered}) != len(ordered):
        raise ValueError("SENSITIVITY_DUPLICATE_PARAMETER_NAME")
    return ordered


@dataclass(frozen=True)
class SelectedParameterConfiguration:
    """Immutable Step-5 selection capture; never inferred from a fingerprint."""

    selected_candidate_fingerprint: str
    parameters: tuple[SensitivityParameterValue, ...]
    window_identity: str
    selection_identity: str
    schema_version: str = "SelectedParameterConfiguration/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "SelectedParameterConfiguration/v1":
            raise ValueError("unsupported selected parameter configuration version")
        for name in ("selected_candidate_fingerprint", "window_identity", "selection_identity"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "parameters", _parameter_values(self.parameters, "parameters"))

    @property
    def configuration_fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-selected-parameter-configuration/v1",
            (("schema", self.schema_version), ("candidate", self.selected_candidate_fingerprint),
             ("parameters", tuple(value.canonical_tuple for value in self.parameters)),
             ("window", self.window_identity), ("selection", self.selection_identity)),
        )


@dataclass(frozen=True)
class SensitivityParameterDomain:
    parameter_name: str
    parameter_type: SensitivityParameterType
    values: tuple[int | Decimal | str, ...]
    provenance: str
    schema_version: str = "SensitivityParameterDomain/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "SensitivityParameterDomain/v1":
            raise ValueError("unsupported sensitivity parameter domain version")
        name = _text(self.parameter_name, "parameter_name")
        kind = SensitivityParameterType(self.parameter_type)
        converted = tuple(SensitivityParameterValue(name, kind, value) for value in self.values)
        if not converted:
            raise ValueError("SENSITIVITY_INVALID_PARAMETER_DOMAIN")
        ordered = tuple(sorted(converted, key=lambda value: CanonicalCodec.encode_value(value.canonical_tuple)))
        if len({CanonicalCodec.encode_value(value.canonical_tuple) for value in ordered}) != len(ordered):
            raise ValueError("SENSITIVITY_INVALID_PARAMETER_DOMAIN")
        object.__setattr__(self, "parameter_name", name)
        object.__setattr__(self, "parameter_type", kind)
        object.__setattr__(self, "values", tuple(value.value for value in ordered))
        object.__setattr__(self, "provenance", _text(self.provenance, "domain provenance"))

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-sensitivity-parameter-domain/v1",
            (("schema", self.schema_version), ("name", self.parameter_name), ("type", self.parameter_type),
             ("values", self.values), ("provenance", self.provenance)),
        )


@dataclass(frozen=True)
class SensitivityPolicy:
    domains: tuple[SensitivityParameterDomain, ...]
    form: SensitivityForm
    max_evaluated_points: int
    method_identity: str = "SensitivityPolicy/v1:DETERMINISTIC_TRAINING_ONLY"
    schema_version: str = "SensitivityPolicy/v1"
    expectancy_ratio: Decimal = Decimal("0.50")
    drawdown_ratio: Decimal = Decimal("1.50")
    minimum_valid_neighbors: int = 2
    minimum_robust_ratio: Decimal = Decimal("0.60")

    def __post_init__(self) -> None:
        if self.schema_version != "SensitivityPolicy/v1":
            raise ValueError("unsupported sensitivity policy version")
        form = SensitivityForm(self.form)
        if form not in (SensitivityForm.COORDINATE, SensitivityForm.LOCAL_GRID):
            raise ValueError("Step-5 supports only COORDINATE or LOCAL_GRID")
        domains = tuple(self.domains)
        if not all(isinstance(value, SensitivityParameterDomain) for value in domains):
            raise TypeError("domains must contain SensitivityParameterDomain")
        ordered = tuple(sorted(domains, key=lambda value: value.parameter_name))
        if len({value.parameter_name for value in ordered}) != len(ordered):
            raise ValueError("SENSITIVITY_DUPLICATE_PARAMETER_NAME")
        if not isinstance(self.max_evaluated_points, int) or isinstance(self.max_evaluated_points, bool) or self.max_evaluated_points < 1:
            raise ValueError("max_evaluated_points must be a non-boolean integer >= 1")
        if (self.expectancy_ratio, self.drawdown_ratio, self.minimum_valid_neighbors, self.minimum_robust_ratio) != (Decimal("0.50"), Decimal("1.50"), 2, Decimal("0.60")):
            raise ValueError("SensitivityPolicy/v1 thresholds are fixed")
        object.__setattr__(self, "domains", ordered)
        object.__setattr__(self, "form", form)
        object.__setattr__(self, "method_identity", _text(self.method_identity, "method_identity"))

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-sensitivity-policy/v1",
            (("schema", self.schema_version), ("method", self.method_identity), ("form", self.form),
             ("domains", tuple(value.fingerprint for value in self.domains)),
             ("max_evaluated_points", self.max_evaluated_points), ("no_rng", True)),
        )


@dataclass(frozen=True)
class SelectedTrainingBaselineEvidence:
    window_identity: str
    selected_candidate_fingerprint: str
    selected_configuration_fingerprint: str
    selection_identity: str
    training_identity: str
    metrics: MetricSummary
    completed_trade_count: Decimal
    expectancy: Decimal
    max_drawdown: Decimal
    schema_version: str = "SelectedTrainingBaselineEvidence/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "SelectedTrainingBaselineEvidence/v1":
            raise ValueError("unsupported selected training baseline version")
        for name in ("window_identity", "selected_candidate_fingerprint", "selected_configuration_fingerprint", "selection_identity", "training_identity"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.metrics, MetricSummary) or not self.metrics.evidence_id:
            raise ValueError("SENSITIVITY_BASELINE_EVIDENCE_INVALID")
        for name in ("completed_trade_count", "expectancy", "max_drawdown"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError("SENSITIVITY_BASELINE_EVIDENCE_INVALID")
        if self.completed_trade_count < 0 or self.max_drawdown < 0:
            raise ValueError("SENSITIVITY_BASELINE_EVIDENCE_INVALID")

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-selected-training-baseline-evidence/v1",
            (("schema", self.schema_version), ("window", self.window_identity),
             ("candidate", self.selected_candidate_fingerprint), ("configuration", self.selected_configuration_fingerprint),
             ("selection", self.selection_identity), ("training", self.training_identity),
             ("metrics", self.metrics.evidence_id), ("trade_count", self.completed_trade_count),
             ("expectancy", self.expectancy), ("max_drawdown", self.max_drawdown)),
        )


@dataclass(frozen=True)
class SensitivityPoint:
    window_identity: str
    policy_fingerprint: str
    configuration: SelectedParameterConfiguration
    schema_version: str = "SensitivityPoint/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "SensitivityPoint/v1":
            raise ValueError("unsupported sensitivity point version")
        object.__setattr__(self, "window_identity", _text(self.window_identity, "window_identity"))
        object.__setattr__(self, "policy_fingerprint", _text(self.policy_fingerprint, "policy_fingerprint"))
        if not isinstance(self.configuration, SelectedParameterConfiguration):
            raise TypeError("configuration must be SelectedParameterConfiguration")
        if self.configuration.window_identity != self.window_identity:
            raise ValueError("point configuration must bind its window")

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-sensitivity-point/v1",
            (("schema", self.schema_version), ("window", self.window_identity), ("policy", self.policy_fingerprint),
             ("configuration", self.configuration.configuration_fingerprint), ("role", "NEIGHBOR")),
        )

    @property
    def ordering_key(self) -> bytes:
        return CanonicalCodec.encode_value(tuple(value.canonical_tuple for value in self.configuration.parameters))


@dataclass(frozen=True)
class SensitivityPointEvidence:
    point: SensitivityPoint
    status: SensitivityPointStatus
    reason: SensitivityReason | None = None
    metrics_evidence_id: str | None = None
    failure_fingerprint: str | None = None
    trade_count: Decimal | None = None
    expectancy: Decimal | None = None
    max_drawdown: Decimal | None = None
    robust: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.point, SensitivityPoint):
            raise TypeError("point must be SensitivityPoint")
        status = SensitivityPointStatus(self.status)
        reason = None if self.reason is None else SensitivityReason(self.reason)
        if self.metrics_evidence_id is not None:
            object.__setattr__(self, "metrics_evidence_id", _text(self.metrics_evidence_id, "metrics_evidence_id"))
        if self.failure_fingerprint is not None:
            object.__setattr__(self, "failure_fingerprint", _text(self.failure_fingerprint, "failure_fingerprint"))
        for name in ("trade_count", "expectancy", "max_drawdown"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, Decimal) or not value.is_finite()):
                raise ValueError("SENSITIVITY_POINT_METRIC_INVALID")
        if status is SensitivityPointStatus.VALID:
            if None in (self.metrics_evidence_id, self.trade_count, self.expectancy, self.max_drawdown, self.robust):
                raise ValueError("valid sensitivity point requires complete metric evidence")
        elif self.robust is not None:
            raise ValueError("only valid sensitivity points may carry robustness")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "reason", reason)

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-sensitivity-point-evidence/v1",
            (("point", self.point.fingerprint), ("status", self.status), ("reason", self.reason),
             ("metrics", self.metrics_evidence_id), ("failure", self.failure_fingerprint),
             ("trade_count", self.trade_count), ("expectancy", self.expectancy),
             ("max_drawdown", self.max_drawdown), ("robust", self.robust)),
        )


@dataclass(frozen=True)
class SensitivityEvidence:
    window: ValidationWindow
    parameter_plan_identity: str
    selection_identity: str
    selected_configuration_fingerprint: str | None
    training_identity: str
    policy_fingerprint: str
    baseline: SelectedTrainingBaselineEvidence | None
    points: tuple[SensitivityPointEvidence, ...]
    status: ValidationStatus
    reason: SensitivityReason | None
    valid_neighbor_count: int
    robust_neighbor_count: int
    robust_ratio: Decimal | None
    schema_version: str = "SensitivityEvidence/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "SensitivityEvidence/v1":
            raise ValueError("unsupported sensitivity evidence version")
        if not isinstance(self.window, ValidationWindow):
            raise TypeError("window must be ValidationWindow")
        for name in ("parameter_plan_identity", "selection_identity", "training_identity", "policy_fingerprint"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.selected_configuration_fingerprint is not None:
            object.__setattr__(self, "selected_configuration_fingerprint", _text(self.selected_configuration_fingerprint, "selected_configuration_fingerprint"))
        points = tuple(self.points)
        if not all(isinstance(value, SensitivityPointEvidence) for value in points):
            raise TypeError("points must contain SensitivityPointEvidence")
        ordered = tuple(sorted(points, key=lambda value: value.point.ordering_key))
        if len({value.point.fingerprint for value in ordered}) != len(ordered):
            raise ValueError("duplicate sensitivity points are ambiguous")
        if any(value.point.window_identity != self.window_identity for value in ordered):
            raise ValueError("point window contradicts sensitivity evidence")
        status = ValidationStatus(self.status)
        reason = None if self.reason is None else SensitivityReason(self.reason)
        if not isinstance(self.valid_neighbor_count, int) or isinstance(self.valid_neighbor_count, bool) or self.valid_neighbor_count < 0:
            raise ValueError("valid_neighbor_count must be non-negative integer")
        if not isinstance(self.robust_neighbor_count, int) or isinstance(self.robust_neighbor_count, bool) or not 0 <= self.robust_neighbor_count <= self.valid_neighbor_count:
            raise ValueError("robust_neighbor_count is invalid")
        if self.robust_ratio is not None and (not isinstance(self.robust_ratio, Decimal) or not self.robust_ratio.is_finite()):
            raise ValueError("robust_ratio must be finite Decimal")
        if status in (ValidationStatus.PASS, ValidationStatus.FAIL) and self.robust_ratio is None:
            raise ValueError("PASS/FAIL sensitivity evidence requires robust ratio")
        object.__setattr__(self, "points", ordered)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "reason", reason)

    @property
    def window_identity(self) -> str:
        return CanonicalCodec.fingerprint("algofortis-validation-window/v1", (("window_id", self.window.window_id), ("train_start", self.window.train_start), ("train_end", self.window.train_end), ("embargo_start", self.window.embargo_start), ("embargo_end", self.window.embargo_end), ("oos_start", self.window.oos_start), ("oos_end", self.window.oos_end)))

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-sensitivity-evidence/v1",
            (("schema", self.schema_version), ("window", self.window_identity), ("parameter_plan", self.parameter_plan_identity),
             ("selection", self.selection_identity), ("configuration", self.selected_configuration_fingerprint),
             ("training", self.training_identity), ("policy", self.policy_fingerprint),
             ("baseline", None if self.baseline is None else self.baseline.fingerprint),
             ("points", tuple(value.fingerprint for value in self.points)), ("status", self.status), ("reason", self.reason),
             ("valid", self.valid_neighbor_count), ("robust", self.robust_neighbor_count), ("ratio", self.robust_ratio)),
        )


@dataclass(frozen=True)
class AggregateSensitivityEvidence:
    required_windows: tuple[ValidationWindow, ...]
    evidence: tuple[SensitivityEvidence, ...]
    policy_fingerprint: str
    status: ValidationStatus
    reason: SensitivityReason | None
    schema_version: str = "AggregateSensitivityEvidence/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "AggregateSensitivityEvidence/v1":
            raise ValueError("unsupported aggregate sensitivity version")
        windows = tuple(sorted(self.required_windows, key=lambda value: (value.oos_start, value.window_id)))
        values = tuple(sorted(self.evidence, key=lambda value: (value.window.oos_start, value.window.window_id)))
        if not windows or len({value.window_id for value in windows}) != len(windows):
            raise ValueError("required sensitivity windows must be unique")
        if len(values) != len(windows) or {value.window.window_id for value in values} != {value.window_id for value in windows}:
            raise ValueError("every required sensitivity window requires exactly one result")
        object.__setattr__(self, "required_windows", windows)
        object.__setattr__(self, "evidence", values)
        object.__setattr__(self, "policy_fingerprint", _text(self.policy_fingerprint, "policy_fingerprint"))
        object.__setattr__(self, "status", ValidationStatus(self.status))
        object.__setattr__(self, "reason", None if self.reason is None else SensitivityReason(self.reason))

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint("algofortis-aggregate-sensitivity-evidence/v1", (("schema", self.schema_version), ("schedule", tuple(value.window_id for value in self.required_windows)), ("evidence", tuple(value.fingerprint for value in self.evidence)), ("policy", self.policy_fingerprint), ("status", self.status), ("reason", self.reason)))


@dataclass(frozen=True)
class OOSTradeEvidence:
    trade_id: str
    instrument: InstrumentIdentity
    window_id: str
    closed_at: datetime
    net_realized_pnl: Decimal | int | float | str
    currency: str
    source_kind: str
    parameter_fingerprint: str
    selection_provenance_fingerprint: str | None
    configuration_fingerprint: str
    validation_identity: str
    provenance_kind: str
    portfolio_observation_time: datetime | None = None
    schema_version: str = "OOSTradeEvidence/v1"
    opening_entry_event_key: LedgerEventKey | None = None
    account_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "trade_id", _text(self.trade_id, "trade_id"))
        if not isinstance(self.instrument, InstrumentIdentity):
            raise TypeError("instrument must be InstrumentIdentity")
        object.__setattr__(self, "window_id", _text(self.window_id, "window_id"))
        _aware(self.closed_at, "closed_at")
        object.__setattr__(self, "net_realized_pnl", as_decimal(self.net_realized_pnl, "net_realized_pnl"))
        object.__setattr__(self, "currency", _text(self.currency, "currency"))
        object.__setattr__(self, "source_kind", _text(self.source_kind, "source_kind"))
        object.__setattr__(self, "parameter_fingerprint", _text(self.parameter_fingerprint, "parameter_fingerprint"))
        if self.selection_provenance_fingerprint is not None:
            object.__setattr__(self, "selection_provenance_fingerprint", _text(self.selection_provenance_fingerprint, "selection_provenance_fingerprint"))
        object.__setattr__(self, "configuration_fingerprint", _text(self.configuration_fingerprint, "configuration_fingerprint"))
        object.__setattr__(self, "validation_identity", _text(self.validation_identity, "validation_identity"))
        object.__setattr__(self, "provenance_kind", _text(self.provenance_kind, "provenance_kind"))
        if self.portfolio_observation_time is not None:
            _aware(self.portfolio_observation_time, "portfolio_observation_time")
        if self.schema_version not in {"OOSTradeEvidence/v1", "OOSTradeEvidence/v2"}:
            raise ValueError("OOS trade evidence schema_version is unsupported")
        if self.schema_version == "OOSTradeEvidence/v2":
            if not isinstance(self.opening_entry_event_key, LedgerEventKey):
                raise TypeError("v2 OOS trade evidence requires opening_entry_event_key")
            object.__setattr__(self, "account_id", _text(self.account_id, "account_id"))
        elif self.opening_entry_event_key is not None or self.account_id is not None:
            raise ValueError("v1 OOS trade evidence cannot carry v2 provenance")

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-oos-trade-evidence/v2" if self.schema_version.endswith("/v2") else "algofortis-oos-trade-evidence/v1",
            (("schema_version", self.schema_version), ("trade_id", self.trade_id),
             ("market", self.instrument.market), ("instrument", self.instrument.instrument),
             ("segment", self.instrument.segment), ("underlying", self.instrument.underlying),
             ("expiry", self.instrument.expiry), ("strike", self.instrument.strike),
             ("option_type", self.instrument.option_type), ("window_id", self.window_id),
             ("closed_at", self.closed_at), ("net_realized_pnl", self.net_realized_pnl),
             ("currency", self.currency), ("source_kind", self.source_kind),
             ("parameter_fingerprint", self.parameter_fingerprint),
             ("selection_provenance_fingerprint", self.selection_provenance_fingerprint),
             ("configuration_fingerprint", self.configuration_fingerprint),
             ("validation_identity", self.validation_identity), ("provenance_kind", self.provenance_kind),
             ("portfolio_observation_time", self.portfolio_observation_time),
             ("opening_run_id", None if self.opening_entry_event_key is None else self.opening_entry_event_key.run_id),
             ("opening_sequence", None if self.opening_entry_event_key is None else self.opening_entry_event_key.accounting_sequence),
             ("account_id", self.account_id)),
        )


class CanonicalPrimaryOOS:
    """The single authority for promotion trade evidence and its sample count."""

    EXCLUDED_KINDS = frozenset({"TRAINING", "SELECTION", "WARMUP", "SENSITIVITY", "RESEARCH", "POST_OOS_RETUNE"})

    @classmethod
    def build(
        cls,
        purpose: ValidationPurpose,
        trades: Iterable[OOSTradeEvidence],
        *,
        windows: Iterable[ValidationWindow] = (),
        universe: Iterable["InstrumentValidationEvidence"] = (),
        parameter_plan: ParameterPlan | None = None,
        parameter_plans_by_window: Mapping[str, ParameterPlan] | None = None,
        configuration_fingerprint: str | None = None,
        validation_identity: str | None = None,
        validation_identities_by_window: Mapping[str, str] | None = None,
    ) -> tuple[OOSTradeEvidence, ...]:
        values = tuple(trades)
        if not all(isinstance(value, OOSTradeEvidence) for value in values):
            raise TypeError("trades must contain OOSTradeEvidence")
        if purpose is not ValidationPurpose.PROMOTION:
            return ()
        if parameter_plans_by_window is None:
            if not isinstance(parameter_plan, ParameterPlan):
                raise TypeError("PROMOTION canonical evidence requires ParameterPlan")
            plans_by_window: Mapping[str, ParameterPlan] | None = None
        else:
            if parameter_plan is not None:
                raise ValueError("canonical evidence cannot mix single and per-window parameter plans")
            plans_by_window = dict(parameter_plans_by_window)
            if not all(isinstance(key, str) and key.strip() and isinstance(value, ParameterPlan) for key, value in plans_by_window.items()):
                raise TypeError("per-window parameter plans must map window IDs to ParameterPlan")
        configuration_fingerprint = _text(configuration_fingerprint, "configuration_fingerprint")
        if validation_identities_by_window is None:
            validation_identity = _text(validation_identity, "validation_identity")
            identities_by_window: Mapping[str, str] | None = None
        else:
            if validation_identity is not None:
                raise ValueError("canonical evidence cannot mix single and per-window validation identities")
            identities_by_window = { _text(key, "window_id"): _text(value, "validation_identity") for key, value in dict(validation_identities_by_window).items() }
        window_values = tuple(windows)
        if not all(isinstance(value, ValidationWindow) for value in window_values):
            raise TypeError("windows must contain ValidationWindow")
        windows_by_id = {value.window_id: value for value in window_values}
        if len(windows_by_id) != len(window_values):
            raise ValueError("canonical evidence requires unique window IDs")
        if plans_by_window is not None and not set(plans_by_window) <= set(windows_by_id):
            raise ValueError("per-window parameter plan references an unknown validation window")
        if identities_by_window is not None and not set(identities_by_window) <= set(windows_by_id):
            raise ValueError("per-window validation identity references an unknown validation window")
        universe_values = tuple(universe)
        if not all(isinstance(value, InstrumentValidationEvidence) for value in universe_values):
            raise TypeError("universe must contain InstrumentValidationEvidence")
        eligible_by_instrument = {value.instrument: value for value in universe_values}
        if len(eligible_by_instrument) != len(universe_values):
            raise ValueError("canonical evidence requires a unique instrument universe")
        selected = tuple(value for value in values if value.source_kind == "PRIMARY_OOS")
        if any(value.source_kind in cls.EXCLUDED_KINDS for value in values if value.source_kind != "PRIMARY_OOS"):
            pass  # explicitly ignored, never silently merged
        for value in selected:
            window = windows_by_id.get(value.window_id)
            if window is None:
                raise ValueError("canonical trade references an unknown validation window")
            if not window.oos_start <= value.closed_at < window.oos_end:
                raise ValueError("canonical trade closed_at is outside its half-open OOS interval")
            instrument_evidence = eligible_by_instrument.get(value.instrument)
            if instrument_evidence is None or value.window_id not in instrument_evidence.eligible_windows:
                raise ValueError("canonical trade instrument is not eligible for its validation window")
            if value.currency != instrument_evidence.currency:
                raise ValueError("canonical trade currency does not match instrument validation evidence")
            current_plan = parameter_plan if plans_by_window is None else plans_by_window.get(value.window_id)
            if current_plan is None:
                raise ValueError("canonical trade lacks a frozen per-window parameter plan")
            expected_selection = None if current_plan.selection_evidence is None else current_plan.selection_evidence.training_evidence_fingerprint
            expected_validation = validation_identity if identities_by_window is None else identities_by_window.get(value.window_id)
            if expected_validation is None:
                raise ValueError("canonical trade lacks a frozen per-window validation identity")
            if value.parameter_fingerprint != current_plan.parameter_fingerprint:
                raise ValueError("canonical trade parameter fingerprint differs from the frozen plan")
            if value.selection_provenance_fingerprint != expected_selection:
                raise ValueError("canonical trade selection provenance differs from the frozen plan")
            if value.configuration_fingerprint != configuration_fingerprint or value.validation_identity != expected_validation:
                raise ValueError("canonical trade provenance differs from the frozen validation run")
            if value.provenance_kind != "PRIMARY_OOS":
                raise ValueError("non-primary provenance cannot be relabelled as PRIMARY_OOS")
        identities = [value.trade_id for value in selected]
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate canonical trade identity is invalid")
        return tuple(sorted(selected, key=lambda value: (value.closed_at, value.instrument.market.casefold(), value.instrument.instrument.casefold(), value.trade_id)))


@dataclass(frozen=True)
class BootstrapPolicy:
    method_version: str
    sample_count: int
    confidence_level: Decimal | int | float | str
    block_length: int
    root_seed: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "method_version", _text(self.method_version, "method_version"))
        if not isinstance(self.sample_count, int) or isinstance(self.sample_count, bool) or self.sample_count <= 0: raise ValueError("sample_count must be positive")
        if not isinstance(self.block_length, int) or isinstance(self.block_length, bool) or self.block_length <= 0: raise ValueError("block_length must be positive")
        confidence = as_decimal(self.confidence_level, "confidence_level")
        if not Decimal("0") < confidence < Decimal("1"): raise ValueError("confidence_level must be between zero and one")
        object.__setattr__(self, "confidence_level", confidence)
        if not isinstance(self.root_seed, int) or isinstance(self.root_seed, bool) or self.root_seed < 0: raise ValueError("root_seed must be non-negative")

    @property
    def fingerprint(self) -> str:
        """D4 identity for the complete explicit Bootstrap policy."""
        return CanonicalCodec.fingerprint(
            "algofortis-bootstrap-policy/v1",
            (("method_version", self.method_version), ("sample_count", self.sample_count),
             ("confidence_level", self.confidence_level), ("block_length", self.block_length),
             ("root_seed", self.root_seed)),
        )


@dataclass(frozen=True)
class MC1Policy:
    """Explicit §47 full-permutation sequence-risk policy."""

    trial_count: int
    root_seed: int
    requested_drawdown_quantiles: tuple[Decimal, ...] = ()
    method_identity: str = "MC1_FULL_PERMUTATION_ABSOLUTE_DRAWDOWN_V1"
    schema_version: str = "MC1Policy/v1"

    QUANTILE_METHOD = "MC1_EMPIRICAL_NEAREST_RANK_V1"

    def __post_init__(self) -> None:
        if self.schema_version != "MC1Policy/v1":
            raise ValueError("unsupported MC1 policy schema_version")
        if self.method_identity != "MC1_FULL_PERMUTATION_ABSOLUTE_DRAWDOWN_V1":
            raise ValueError("MC1_METHOD_IDENTITY_MISMATCH")
        if not isinstance(self.trial_count, int) or isinstance(self.trial_count, bool) or self.trial_count < 1:
            raise ValueError("MC1_INVALID_TRIAL_COUNT")
        if not isinstance(self.root_seed, int) or isinstance(self.root_seed, bool) or self.root_seed < 0:
            raise ValueError("root_seed must be a non-negative integer")
        quantiles: list[Decimal] = []
        for value in tuple(self.requested_drawdown_quantiles):
            if not isinstance(value, Decimal) or not value.is_finite() or not Decimal("0") < value <= Decimal("1"):
                raise ValueError("MC1_INVALID_QUANTILE")
            quantiles.append(value)
        object.__setattr__(self, "requested_drawdown_quantiles", tuple(sorted(set(quantiles))))

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            self.schema_version,
            (("method", self.method_identity), ("trial_count", self.trial_count),
             ("root_seed", self.root_seed), ("quantiles", self.requested_drawdown_quantiles)),
        )


@dataclass(frozen=True)
class MC2Policy:
    """Explicit §48 per-window circular-block MC-2 policy."""

    trial_count: int
    block_length: int
    root_seed: int
    requested_drawdown_quantiles: tuple[Decimal, ...] = ()
    method_identity: str = "MC2_PER_WINDOW_CIRCULAR_BLOCK_ABSOLUTE_DRAWDOWN_V1"
    schema_version: str = "MC2Policy/v1"

    QUANTILE_METHOD = "MC2_EMPIRICAL_NEAREST_RANK_V1"

    def __post_init__(self) -> None:
        if self.schema_version != "MC2Policy/v1":
            raise ValueError("unsupported MC2 policy schema_version")
        if self.method_identity != "MC2_PER_WINDOW_CIRCULAR_BLOCK_ABSOLUTE_DRAWDOWN_V1":
            raise ValueError("MC2_METHOD_IDENTITY_MISMATCH")
        if not isinstance(self.trial_count, int) or isinstance(self.trial_count, bool) or self.trial_count < 1:
            raise ValueError("MC2_INVALID_TRIAL_COUNT")
        if not isinstance(self.block_length, int) or isinstance(self.block_length, bool) or self.block_length < 1:
            raise ValueError("MC2_INVALID_BLOCK_LENGTH")
        if not isinstance(self.root_seed, int) or isinstance(self.root_seed, bool) or self.root_seed < 0:
            raise ValueError("root_seed must be a non-negative integer")
        quantiles: list[Decimal] = []
        for value in tuple(self.requested_drawdown_quantiles):
            if not isinstance(value, Decimal) or not value.is_finite() or not Decimal("0") < value <= Decimal("1"):
                raise ValueError("MC2_INVALID_QUANTILE")
            quantiles.append(value)
        object.__setattr__(self, "requested_drawdown_quantiles", tuple(sorted(set(quantiles))))

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            self.schema_version,
            (("method", self.method_identity), ("trial_count", self.trial_count),
             ("block_length", self.block_length), ("root_seed", self.root_seed),
             ("quantiles", self.requested_drawdown_quantiles)),
        )


@dataclass(frozen=True)
class AggregateMC2Policy:
    """Explicit aggregate MC-2 policy; blocks are never trade-count blocks."""

    block_length: int
    block_unit: AggregateBlockUnit

    def __post_init__(self) -> None:
        if not isinstance(self.block_length, int) or isinstance(self.block_length, bool) or self.block_length <= 0:
            raise ValueError("block_length must be a positive integer")
        object.__setattr__(self, "block_unit", AggregateBlockUnit(self.block_unit))
        if self.block_unit is not AggregateBlockUnit.EPISODES:
            raise ValueError("aggregate MC-2 block_unit must be EPISODES")


@dataclass(frozen=True)
class SynchronizedEconomicEpisode:
    """One atomic authoritative aggregate economic observation interval."""

    validation_run_id: str
    validation_identity: str
    window_id: str
    portfolio_observation_time: datetime
    members: tuple[OOSTradeEvidence, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "validation_run_id", _text(self.validation_run_id, "validation_run_id"))
        object.__setattr__(self, "validation_identity", _text(self.validation_identity, "validation_identity"))
        object.__setattr__(self, "window_id", _text(self.window_id, "window_id"))
        _aware(self.portfolio_observation_time, "portfolio_observation_time")
        members = tuple(self.members)
        if not members or not all(isinstance(value, OOSTradeEvidence) for value in members):
            raise ValueError("episode members must contain OOSTradeEvidence")
        if len({value.trade_id for value in members}) != len(members):
            raise ValueError("episode member evidence identity must be unique")
        for value in members:
            if value.window_id != self.window_id or value.validation_identity != self.validation_identity:
                raise ValueError("episode members must share frozen window and validation identity")
            if value.portfolio_observation_time != self.portfolio_observation_time:
                raise ValueError("episode members must share authoritative portfolio observation time")
        object.__setattr__(self, "members", tuple(sorted(
            members,
            key=lambda value: (_instrument_sort_key(value.instrument), value.closed_at, value.trade_id),
        )))

    @property
    def aggregate_net_outcome(self) -> Decimal:
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            return sum((value.net_realized_pnl for value in self.members), Decimal("0"))

    @property
    def identity(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-synchronized-economic-episode/v2",
            (("validation_run_id", self.validation_run_id),
             ("validation_identity", self.validation_identity), ("window_id", self.window_id),
             ("portfolio_observation_time", self.portfolio_observation_time),
             ("members", tuple(value.trade_id for value in self.members))),
        )


class SynchronizedEpisodeBuilder:
    """Build canonical aggregate MC units; no timestamp bucketing is permitted."""

    @staticmethod
    def build(evidence: "ValidationRunEvidence", windows: Iterable[ValidationWindow], trades: Iterable[OOSTradeEvidence]) -> tuple[SynchronizedEconomicEpisode, ...]:
        if not isinstance(evidence, ValidationRunEvidence):
            raise TypeError("evidence must be ValidationRunEvidence")
        window_values = tuple(windows)
        windows_by_id = {value.window_id: value for value in window_values}
        canonical = CanonicalPrimaryOOS.build(
            evidence.purpose,
            trades,
            windows=window_values,
            universe=evidence.universe,
            parameter_plan=evidence.parameter_plan,
            configuration_fingerprint=evidence.configuration_fingerprint,
            validation_identity=evidence.validation_identity,
        )
        grouped: dict[tuple[str, str, datetime], list[OOSTradeEvidence]] = {}
        for value in canonical:
            if value.portfolio_observation_time is None:
                raise ValueError("canonical aggregate evidence requires authoritative portfolio observation alignment")
            window = windows_by_id[value.window_id]
            if not window.oos_start <= value.portfolio_observation_time < window.oos_end:
                raise ValueError("authoritative portfolio observation is outside its half-open OOS interval")
            key = (value.validation_identity, value.window_id, value.portfolio_observation_time)
            grouped.setdefault(key, []).append(value)
        episodes = tuple(
            SynchronizedEconomicEpisode(evidence.source_run_id, validation_identity, window_id, observation_time, tuple(members))
            for (validation_identity, window_id, observation_time), members in grouped.items()
        )
        return tuple(sorted(episodes, key=lambda value: (value.portfolio_observation_time, value.window_id, value.identity)))


@dataclass(frozen=True)
class RandomizedResult:
    kind: RandomizedAnalysisKind
    status: ValidationStatus
    seed: int
    observed: Decimal | None
    lower_bound: Decimal | None = None
    upper_bound: Decimal | None = None
    reason: str | None = None


class _BootstrapNonFiniteReplicate(ValueError):
    """Private bridge from the existing sampler to the D7 producer."""

    def __init__(self, index: int, value: Decimal) -> None:
        self.index = index
        self.reason_code = _non_finite_reason(value)
        super().__init__(self.reason_code)


def _non_finite_reason(value: Decimal) -> str:
    if value.is_nan():
        return "NON_FINITE_NAN"
    return "NON_FINITE_NEGATIVE_INFINITY" if value.is_signed() else "NON_FINITE_POSITIVE_INFINITY"


def _bootstrap_observation_identity(value: OOSTradeEvidence) -> str:
    """Use the normal OOS identity, preserving a stable structural identity for D7 corruption evidence."""
    if value.net_realized_pnl.is_finite():
        return value.fingerprint
    return CanonicalCodec.fingerprint(
        "algofortis-bootstrap-non-finite-oos-observation/v1",
        (("trade_id", value.trade_id), ("instrument", _instrument_fields(value.instrument)),
         ("window_id", value.window_id), ("closed_at", value.closed_at),
         ("currency", value.currency), ("source_kind", value.source_kind),
         ("validation_identity", value.validation_identity)),
    )


@dataclass(frozen=True)
class BootstrapEvidence:
    """Immutable authoritative `BootstrapEvidence/v1` outcome evidence."""

    source_primary_oos_identity: str
    validation_scope_identity: str
    instrument: InstrumentIdentity
    instrument_scope_identity: str
    bootstrap_policy_fingerprint: str
    method_identity: str
    root_seed_identity: str
    derived_seed: int
    derived_seed_identity: str
    sample_count: int
    confidence_level: Decimal | int | float | str
    block_length: int
    completed_oos_trade_count: int
    point_expectancy: Decimal | int | float | str | None
    ci_lower: Decimal | int | float | str | None
    ci_upper: Decimal | int | float | str | None
    status: ValidationStatus
    reason_code: str | None = None
    schema_version: str = "BootstrapEvidence/v1"
    under_200_exception_eligible: bool = field(init=False)

    def __post_init__(self) -> None:
        if self.schema_version != "BootstrapEvidence/v1":
            raise ValueError("unsupported Bootstrap evidence schema_version")
        for name in (
            "source_primary_oos_identity", "validation_scope_identity", "instrument_scope_identity",
            "bootstrap_policy_fingerprint", "method_identity", "root_seed_identity", "derived_seed_identity",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.instrument, InstrumentIdentity):
            raise TypeError("instrument must be InstrumentIdentity")
        for name in ("derived_seed", "sample_count", "block_length", "completed_oos_trade_count"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.sample_count == 0 or self.block_length == 0:
            raise ValueError("sample_count and block_length must be positive")
        confidence = as_decimal(self.confidence_level, "confidence_level")
        if not Decimal("0") < confidence < Decimal("1"):
            raise ValueError("confidence_level must be between zero and one")
        object.__setattr__(self, "confidence_level", confidence)
        for name in ("point_expectancy", "ci_lower", "ci_upper"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, as_decimal(value, name))
        object.__setattr__(self, "status", ValidationStatus(self.status))
        if self.reason_code is not None:
            object.__setattr__(self, "reason_code", _text(self.reason_code, "reason_code"))
        eligible = (
            self.completed_oos_trade_count < 200
            and self.status is ValidationStatus.PASS
            and self.ci_lower is not None
            and self.ci_lower > 0
        )
        object.__setattr__(self, "under_200_exception_eligible", eligible)

    @property
    def result_fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-bootstrap-evidence/v1",
            (("schema_version", self.schema_version), ("source_primary_oos", self.source_primary_oos_identity),
             ("validation_scope", self.validation_scope_identity),
             ("instrument", _instrument_fields(self.instrument)), ("instrument_scope", self.instrument_scope_identity),
             ("policy", self.bootstrap_policy_fingerprint), ("method", self.method_identity),
             ("root_seed", self.root_seed_identity), ("derived_seed", self.derived_seed),
             ("derived_seed_identity", self.derived_seed_identity), ("sample_count", self.sample_count),
             ("confidence_level", self.confidence_level), ("block_length", self.block_length),
             ("trade_count", self.completed_oos_trade_count), ("point_expectancy", self.point_expectancy),
             ("ci_lower", self.ci_lower), ("ci_upper", self.ci_upper), ("status", self.status),
             ("reason_code", self.reason_code), ("under_200_exception_eligible", self.under_200_exception_eligible)),
        )


@dataclass(frozen=True)
class _PrimaryOOSInstrumentScope:
    """Shared additive canonical source projection; Bootstrap v1 stays unchanged."""

    aggregate_identity: str
    instrument: InstrumentIdentity
    trades: tuple[OOSTradeEvidence, ...]
    validation_scope_identity: str
    source_identity: str
    instrument_scope_identity: str


@dataclass(frozen=True)
class MC1Evidence:
    source_primary_oos_identity: str
    validation_scope_identity: str
    instrument: InstrumentIdentity
    instrument_scope_identity: str
    mc1_policy_fingerprint: str
    method_identity: str
    quantile_method_identity: str
    root_seed_identity: str
    derived_seed: int | None
    derived_seed_identity: str | None
    source_trade_count: int
    randomized_trial_count: int
    original_order_absolute_max_drawdown: Decimal | None
    requested_drawdown_quantiles: tuple[Decimal, ...]
    randomized_drawdown_quantiles: tuple[tuple[Decimal, Decimal], ...]
    worst_randomized_absolute_max_drawdown: Decimal | None
    randomized_trial_distribution_identity: str | None
    status: ValidationStatus
    reason_code: str | None = None
    schema_version: str = "MC1Evidence/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "MC1Evidence/v1":
            raise ValueError("unsupported MC1 evidence schema_version")
        for name in ("source_primary_oos_identity", "validation_scope_identity", "instrument_scope_identity",
                     "mc1_policy_fingerprint", "method_identity", "quantile_method_identity", "root_seed_identity"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.instrument, InstrumentIdentity):
            raise TypeError("instrument must be InstrumentIdentity")
        if self.derived_seed is not None and (not isinstance(self.derived_seed, int) or isinstance(self.derived_seed, bool) or self.derived_seed < 0):
            raise ValueError("derived_seed must be a non-negative integer or None")
        if self.derived_seed_identity is not None:
            object.__setattr__(self, "derived_seed_identity", _text(self.derived_seed_identity, "derived_seed_identity"))
        if self.randomized_trial_distribution_identity is not None:
            object.__setattr__(self, "randomized_trial_distribution_identity", _text(
                self.randomized_trial_distribution_identity, "randomized_trial_distribution_identity"))
        for name in ("source_trade_count", "randomized_trial_count"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        quantiles = tuple(self.requested_drawdown_quantiles)
        if tuple(sorted(set(quantiles))) != quantiles or not all(isinstance(value, Decimal) and value.is_finite() and Decimal("0") < value <= Decimal("1") for value in quantiles):
            raise ValueError("requested_drawdown_quantiles must be canonical finite Decimals")
        object.__setattr__(self, "requested_drawdown_quantiles", quantiles)
        results = tuple(self.randomized_drawdown_quantiles)
        if not all(isinstance(value, tuple) and len(value) == 2 and
                   all(isinstance(item, Decimal) and item.is_finite() for item in value) for value in results):
            raise ValueError("randomized_drawdown_quantiles must contain only finite Decimal pairs")
        object.__setattr__(self, "randomized_drawdown_quantiles", results)
        for name in ("original_order_absolute_max_drawdown", "worst_randomized_absolute_max_drawdown"):
            value = getattr(self, name)
            if value is not None:
                if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
                    raise ValueError(f"{name} must be a non-negative finite Decimal or None")
        object.__setattr__(self, "status", ValidationStatus(self.status))
        if self.reason_code is not None:
            object.__setattr__(self, "reason_code", _text(self.reason_code, "reason_code"))
        if self.status is ValidationStatus.PASS:
            if (tuple(value[0] for value in results) != quantiles
                    or self.source_trade_count < 2
                    or self.randomized_trial_count == 0
                    or any(value is None for value in (
                        self.derived_seed,
                        self.derived_seed_identity,
                        self.original_order_absolute_max_drawdown,
                        self.worst_randomized_absolute_max_drawdown,
                        self.randomized_trial_distribution_identity,
                    ))):
                raise ValueError("PASS MC1 evidence must bind complete randomized analysis evidence")
        elif self.status is ValidationStatus.INSUFFICIENT_DATA:
            if any(value is not None for value in (self.derived_seed, self.derived_seed_identity,
                                                   self.original_order_absolute_max_drawdown,
                                                   self.worst_randomized_absolute_max_drawdown,
                                                   self.randomized_trial_distribution_identity)) or results:
                raise ValueError("insufficient MC1 evidence must not fabricate randomized evidence")

    @property
    def result_fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-mc1-evidence/v1",
            (("schema_version", self.schema_version), ("source", self.source_primary_oos_identity),
             ("validation_scope", self.validation_scope_identity), ("instrument", _instrument_fields(self.instrument)),
             ("instrument_scope", self.instrument_scope_identity), ("policy", self.mc1_policy_fingerprint),
             ("method", self.method_identity), ("quantile_method", self.quantile_method_identity),
             ("root_seed", self.root_seed_identity), ("derived_seed", self.derived_seed),
             ("derived_seed_identity", self.derived_seed_identity), ("source_trade_count", self.source_trade_count),
             ("trial_count", self.randomized_trial_count), ("baseline_drawdown", self.original_order_absolute_max_drawdown),
             ("requested_quantiles", self.requested_drawdown_quantiles),
             ("quantile_results", self.randomized_drawdown_quantiles),
             ("worst_drawdown", self.worst_randomized_absolute_max_drawdown),
             ("distribution", self.randomized_trial_distribution_identity), ("status", self.status),
             ("reason_code", self.reason_code)),
        )


@dataclass(frozen=True)
class _MC2WindowScope:
    """One canonical Step-4C resampling domain, including zero-trade windows."""

    window_id: str
    validation_identity: str
    trades: tuple[OOSTradeEvidence, ...]
    source_identity: str

    @property
    def trade_count(self) -> int:
        return len(self.trades)


@dataclass(frozen=True)
class MC2Evidence:
    source_primary_oos_identity: str
    validation_scope_identity: str
    instrument: InstrumentIdentity
    instrument_scope_identity: str
    mc2_policy_fingerprint: str
    method_identity: str
    block_construction_identity: str
    quantile_method_identity: str
    root_seed_identity: str
    derived_seed: int | None
    derived_seed_identity: str | None
    source_trade_count: int
    per_window_sources: tuple[tuple[str, str, int, str], ...]
    randomized_trial_count: int
    block_length: int
    original_order_absolute_max_drawdown: Decimal | None
    requested_drawdown_quantiles: tuple[Decimal, ...]
    randomized_drawdown_quantiles: tuple[tuple[Decimal, Decimal], ...]
    worst_randomized_absolute_max_drawdown: Decimal | None
    randomized_trial_distribution_identity: str | None
    status: ValidationStatus
    reason_code: str | None = None
    schema_version: str = "MC2Evidence/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "MC2Evidence/v1":
            raise ValueError("unsupported MC2 evidence schema_version")
        for name in (
            "source_primary_oos_identity", "validation_scope_identity", "instrument_scope_identity",
            "mc2_policy_fingerprint", "method_identity", "block_construction_identity",
            "quantile_method_identity", "root_seed_identity",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.instrument, InstrumentIdentity):
            raise TypeError("instrument must be InstrumentIdentity")
        if self.derived_seed is not None and (not isinstance(self.derived_seed, int) or isinstance(self.derived_seed, bool) or self.derived_seed < 0):
            raise ValueError("derived_seed must be a non-negative integer or None")
        if self.derived_seed_identity is not None:
            object.__setattr__(self, "derived_seed_identity", _text(self.derived_seed_identity, "derived_seed_identity"))
        if self.randomized_trial_distribution_identity is not None:
            object.__setattr__(self, "randomized_trial_distribution_identity", _text(
                self.randomized_trial_distribution_identity, "randomized_trial_distribution_identity"))
        for name in ("source_trade_count", "randomized_trial_count", "block_length"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.block_length == 0:
            raise ValueError("block_length must be positive")
        windows = tuple(self.per_window_sources)
        if not all(
            isinstance(value, tuple) and len(value) == 4
            and isinstance(value[0], str) and value[0].strip()
            and isinstance(value[1], str) and value[1].strip()
            and isinstance(value[2], int) and not isinstance(value[2], bool) and value[2] >= 0
            and isinstance(value[3], str) and value[3].strip()
            for value in windows
        ):
            raise ValueError("per_window_sources must contain canonical window source identities")
        if len({value[0] for value in windows}) != len(windows) or sum(value[2] for value in windows) != self.source_trade_count:
            raise ValueError("per_window_sources must reconcile to the canonical source count")
        object.__setattr__(self, "per_window_sources", windows)
        quantiles = tuple(self.requested_drawdown_quantiles)
        if tuple(sorted(set(quantiles))) != quantiles or not all(
            isinstance(value, Decimal) and value.is_finite() and Decimal("0") < value <= Decimal("1")
            for value in quantiles
        ):
            raise ValueError("requested_drawdown_quantiles must be canonical finite Decimals")
        object.__setattr__(self, "requested_drawdown_quantiles", quantiles)
        results = tuple(self.randomized_drawdown_quantiles)
        if not all(
            isinstance(value, tuple) and len(value) == 2
            and all(isinstance(item, Decimal) and item.is_finite() for item in value)
            for value in results
        ):
            raise ValueError("randomized_drawdown_quantiles must contain only finite Decimal pairs")
        object.__setattr__(self, "randomized_drawdown_quantiles", results)
        for name in ("original_order_absolute_max_drawdown", "worst_randomized_absolute_max_drawdown"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, Decimal) or not value.is_finite() or value < 0):
                raise ValueError(f"{name} must be a non-negative finite Decimal or None")
        object.__setattr__(self, "status", ValidationStatus(self.status))
        if self.reason_code is not None:
            object.__setattr__(self, "reason_code", _text(self.reason_code, "reason_code"))
        if self.status is ValidationStatus.PASS:
            if (self.source_trade_count < 2 or self.randomized_trial_count == 0
                    or tuple(value[0] for value in results) != quantiles
                    or any(value is None for value in (
                        self.derived_seed, self.derived_seed_identity,
                        self.original_order_absolute_max_drawdown,
                        self.worst_randomized_absolute_max_drawdown,
                        self.randomized_trial_distribution_identity,
                    ))):
                raise ValueError("PASS MC2 evidence must bind complete randomized analysis evidence")
        elif self.status is ValidationStatus.INSUFFICIENT_DATA:
            if any(value is not None for value in (
                self.derived_seed, self.derived_seed_identity,
                self.original_order_absolute_max_drawdown,
                self.worst_randomized_absolute_max_drawdown,
                self.randomized_trial_distribution_identity,
            )) or results:
                raise ValueError("insufficient MC2 evidence must not fabricate randomized evidence")

    @property
    def result_fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-mc2-evidence/v1",
            (("schema_version", self.schema_version), ("source", self.source_primary_oos_identity),
             ("validation_scope", self.validation_scope_identity), ("instrument", _instrument_fields(self.instrument)),
             ("instrument_scope", self.instrument_scope_identity), ("policy", self.mc2_policy_fingerprint),
             ("method", self.method_identity), ("block_construction", self.block_construction_identity),
             ("quantile_method", self.quantile_method_identity), ("root_seed", self.root_seed_identity),
             ("derived_seed", self.derived_seed), ("derived_seed_identity", self.derived_seed_identity),
             ("source_trade_count", self.source_trade_count), ("per_window_sources", self.per_window_sources),
             ("trial_count", self.randomized_trial_count), ("block_length", self.block_length),
             ("baseline_drawdown", self.original_order_absolute_max_drawdown),
             ("requested_quantiles", self.requested_drawdown_quantiles),
             ("quantile_results", self.randomized_drawdown_quantiles),
             ("worst_drawdown", self.worst_randomized_absolute_max_drawdown),
             ("distribution", self.randomized_trial_distribution_identity), ("status", self.status),
             ("reason_code", self.reason_code)),
        )


class ValidationStatistics:
    @staticmethod
    def _bootstrap_percentile_indices(policy: BootstrapPolicy) -> tuple[int, int] | None:
        """The one locked §46 percentile-index implementation."""
        alpha = (Decimal("1") - policy.confidence_level) / Decimal("2")
        lower = int(alpha * policy.sample_count)
        upper = int((Decimal("1") - alpha) * policy.sample_count) - 1
        lower = min(policy.sample_count - 1, max(0, lower))
        upper = min(policy.sample_count - 1, max(0, upper))
        return None if lower > upper else (lower, upper)

    @staticmethod
    def _bootstrap_replicate_expectancies(
        outcomes: tuple[Decimal, ...], policy: BootstrapPolicy, seed: int,
    ) -> tuple[Decimal, ...]:
        """Existing circular-block sampler, factored only to surface D7 evidence."""
        rng = random.Random(seed)
        means: list[Decimal] = []
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            for replicate_index in range(policy.sample_count):
                sample: list[Decimal] = []
                while len(sample) < len(outcomes):
                    start = rng.randrange(len(outcomes))
                    sample.extend(outcomes[(start + offset) % len(outcomes)] for offset in range(policy.block_length))
                mean = sum(sample[:len(outcomes)], Decimal("0")) / Decimal(len(outcomes))
                if not mean.is_finite():
                    raise _BootstrapNonFiniteReplicate(replicate_index, mean)
                means.append(mean)
        return tuple(means)

    @staticmethod
    def primary_sample_status(
        trades: Iterable[OOSTradeEvidence], bootstrap: RandomizedResult | BootstrapEvidence | None = None,
    ) -> ValidationStatus:
        """Apply the frozen 200-trade baseline without treating low count as FAIL.

        The only under-200 exception is a valid Bootstrap result whose lower
        confidence bound is strictly positive.  Monte Carlo is intentionally
        not accepted here.
        """
        values = tuple(trades)
        if len(values) >= 200:
            return ValidationStatus.PASS
        if isinstance(bootstrap, BootstrapEvidence):
            return ValidationStatus.PASS if bootstrap.under_200_exception_eligible else ValidationStatus.INSUFFICIENT_DATA
        if (bootstrap is not None and bootstrap.kind is RandomizedAnalysisKind.BOOTSTRAP
                and bootstrap.status is ValidationStatus.PASS and bootstrap.lower_bound is not None
                and bootstrap.lower_bound > 0):
            return ValidationStatus.PASS
        return ValidationStatus.INSUFFICIENT_DATA

    @staticmethod
    def bootstrap_expectancy(trades: Iterable[OOSTradeEvidence], policy: BootstrapPolicy, identity: str) -> RandomizedResult:
        values = tuple(trades)
        if not all(isinstance(value, OOSTradeEvidence) for value in values): raise TypeError("trades must contain OOSTradeEvidence")
        seed = derive_seed(policy.root_seed, RandomizedAnalysisKind.BOOTSTRAP, identity)
        if len(values) < policy.block_length:
            return RandomizedResult(RandomizedAnalysisKind.BOOTSTRAP, ValidationStatus.INSUFFICIENT_DATA, seed, None, reason="evidence shorter than explicit block length")
        outcomes = tuple(value.net_realized_pnl for value in sorted(values, key=lambda value: (value.closed_at, value.trade_id)))
        if not all(value.is_finite() for value in outcomes):
            raise ValueError("bootstrap source outcome must be finite")
        indices = ValidationStatistics._bootstrap_percentile_indices(policy)
        if indices is None or indices[0] > indices[1]:
            return RandomizedResult(RandomizedAnalysisKind.BOOTSTRAP, ValidationStatus.INSUFFICIENT_DATA, seed, None, reason="BOOTSTRAP_INSUFFICIENT_SAMPLES_FOR_CI")
        means = list(ValidationStatistics._bootstrap_replicate_expectancies(outcomes, policy, seed))
        for replicate_index, mean in enumerate(means):
            if not mean.is_finite():
                raise _BootstrapNonFiniteReplicate(replicate_index, mean)
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            means.sort()
            lower = means[indices[0]]
            upper = means[indices[1]]
            observed = sum(outcomes, Decimal("0")) / Decimal(len(outcomes))
        return RandomizedResult(RandomizedAnalysisKind.BOOTSTRAP, ValidationStatus.PASS if lower > 0 else ValidationStatus.FAIL, seed, observed, lower, upper)


class BootstrapAnalyzer:
    """The sole authoritative Step-4A `CanonicalPrimaryOOS` Bootstrap boundary."""

    METHOD_VERSION = "CIRCULAR_BLOCK_PERCENTILE_V1"

    @classmethod
    def analyze(
        cls,
        aggregate: object,
        instrument: InstrumentIdentity,
        policy: BootstrapPolicy,
    ) -> BootstrapEvidence | StructuredFailureResult:
        # Import locally: walk_forward imports validation, while this boundary
        # needs the concrete aggregate contract only at execution time.
        from engine.backtest.walk_forward import MultiWindowWalkForwardResult

        if not isinstance(aggregate, MultiWindowWalkForwardResult):
            raise TypeError("aggregate must be MultiWindowWalkForwardResult")
        if not isinstance(instrument, InstrumentIdentity):
            raise TypeError("instrument must be InstrumentIdentity")
        if not isinstance(policy, BootstrapPolicy):
            raise TypeError("policy must be BootstrapPolicy")

        successful_pairs = tuple(
            (value.window.window_id, value.validation_evidence.validation_identity)
            for value in aggregate.successful_windows
        )
        try:
            aggregate_identity = aggregate.aggregate_identity
        except ValueError:
            # A deliberately corrupted non-finite observation cannot obtain a
            # normal D4 trade fingerprint.  Preserve deterministic D7 binding
            # without serializing the non-finite payload itself.
            aggregate_identity = CanonicalCodec.fingerprint(
                "algofortis-bootstrap-invalid-aggregate-source/v1",
                (("manifest", aggregate.manifest_fingerprint),
                 ("schedule", tuple(value.window_id for value in aggregate.schedule)),
                 ("selection", aggregate.selection_identity.fingerprint),
                 ("observations", tuple(_bootstrap_observation_identity(value) for value in aggregate.canonical_oos_trades))),
            )
        validation_scope_identity = CanonicalCodec.fingerprint(
            "algofortis-bootstrap-validation-scope/v1",
            (("successful_windows", successful_pairs),),
        )
        scoped = tuple(value for value in aggregate.canonical_oos_trades if value.instrument == instrument)
        source_identity = CanonicalCodec.fingerprint(
            "algofortis-bootstrap-primary-oos-source/v1",
            (("aggregate", aggregate_identity), ("instrument", _instrument_fields(instrument)),
             ("trades", tuple(_bootstrap_observation_identity(value) for value in scoped)),
             ("successful_windows", successful_pairs)),
        )
        instrument_scope_identity = CanonicalCodec.fingerprint(
            "algofortis-bootstrap-instrument-scope/v1",
            (("source", source_identity), ("instrument", _instrument_fields(instrument))),
        )
        method_identity = CanonicalCodec.fingerprint(
            "algofortis-bootstrap-method/v1", (("method_version", policy.method_version),),
        )
        root_seed_identity = CanonicalCodec.fingerprint(
            "algofortis-bootstrap-root-seed/v1", (("root_seed", policy.root_seed),),
        )
        derived_seed_identity = CanonicalCodec.fingerprint(
            "algofortis-bootstrap-derived-seed/v1",
            (("root_seed", root_seed_identity), ("kind", RandomizedAnalysisKind.BOOTSTRAP),
             ("source", source_identity), ("validation_scope", validation_scope_identity),
             ("policy", policy.fingerprint), ("method", method_identity)),
        )
        seed = derive_seed(policy.root_seed, RandomizedAnalysisKind.BOOTSTRAP, derived_seed_identity)

        if policy.method_version != cls.METHOD_VERSION:
            return cls._evidence(
                source_identity, validation_scope_identity, instrument, instrument_scope_identity, policy,
                method_identity, root_seed_identity, seed, derived_seed_identity, len(scoped),
                ValidationStatus.INVALID, "BOOTSTRAP_METHOD_IDENTITY_MISMATCH",
            )

        try:
            canonical = cls._validated_canonical_scope(aggregate, instrument)
        except (TypeError, ValueError):
            return cls._evidence(
                source_identity, validation_scope_identity, instrument, instrument_scope_identity, policy,
                method_identity, root_seed_identity, seed, derived_seed_identity, len(scoped),
                ValidationStatus.INVALID, "INVALID_CANONICAL_PRIMARY_OOS",
            )
        if canonical != scoped:
            return cls._evidence(
                source_identity, validation_scope_identity, instrument, instrument_scope_identity, policy,
                method_identity, root_seed_identity, seed, derived_seed_identity, len(scoped),
                ValidationStatus.INVALID, "CONTRADICTORY_CANONICAL_PRIMARY_OOS",
            )
        if not canonical:
            return cls._evidence(
                source_identity, validation_scope_identity, instrument, instrument_scope_identity, policy,
                method_identity, root_seed_identity, seed, derived_seed_identity, 0,
                ValidationStatus.INSUFFICIENT_DATA, "BOOTSTRAP_NO_CANONICAL_OOS_TRADES",
            )
        if len(canonical) < policy.block_length:
            return cls._evidence(
                source_identity, validation_scope_identity, instrument, instrument_scope_identity, policy,
                method_identity, root_seed_identity, seed, derived_seed_identity, len(canonical),
                ValidationStatus.INSUFFICIENT_DATA, "BOOTSTRAP_SOURCE_SHORTER_THAN_BLOCK_LENGTH",
            )
        for index, value in enumerate(canonical):
            if not value.net_realized_pnl.is_finite():
                failure_evidence = CanonicalCodec.fingerprint(
                    "algofortis-bootstrap-source-non-finite/v1",
                    (("source", source_identity), ("trade", _bootstrap_observation_identity(value)), ("source_index", index),
                     ("field", "net_realized_pnl"), ("reason", _non_finite_reason(value.net_realized_pnl))),
                )
                return StructuredFailureResult(
                    "structured-failure/v1", aggregate.manifest_fingerprint,
                    BootstrapFailureStage.BOOTSTRAP_ANALYSIS.value,
                    BootstrapFailureCode.BOOTSTRAP_NON_FINITE_EVIDENCE,
                    failure_evidence, policy.fingerprint,
                )
        try:
            outcome = ValidationStatistics.bootstrap_expectancy(canonical, policy, derived_seed_identity)
        except _BootstrapNonFiniteReplicate as error:
            failure_evidence = CanonicalCodec.fingerprint(
                "algofortis-bootstrap-replicate-non-finite/v1",
                (("source", source_identity), ("policy", policy.fingerprint), ("method", method_identity),
                 ("derived_seed", derived_seed_identity), ("replicate_index", error.index),
                 ("reason", error.reason_code)),
            )
            return StructuredFailureResult(
                "structured-failure/v1", aggregate.manifest_fingerprint,
                BootstrapFailureStage.BOOTSTRAP_ANALYSIS.value,
                BootstrapFailureCode.BOOTSTRAP_NON_FINITE_EVIDENCE,
                failure_evidence, policy.fingerprint,
            )
        return cls._evidence(
            source_identity, validation_scope_identity, instrument, instrument_scope_identity, policy,
            method_identity, root_seed_identity, outcome.seed, derived_seed_identity, len(canonical),
            outcome.status, outcome.reason, outcome.observed, outcome.lower_bound, outcome.upper_bound,
        )

    @staticmethod
    def _validated_canonical_scope(aggregate: object, instrument: InstrumentIdentity) -> tuple[OOSTradeEvidence, ...]:
        successes = tuple(aggregate.successful_windows)
        if not successes:
            return ()
        evidence = successes[0].validation_evidence
        if any(value.validation_evidence.universe != evidence.universe or
               value.validation_evidence.configuration_fingerprint != evidence.configuration_fingerprint
               for value in successes):
            raise ValueError("successful windows have contradictory validation provenance")
        canonical = CanonicalPrimaryOOS.build(
            ValidationPurpose.PROMOTION,
            tuple(trade for value in successes for trade in value.canonical_oos_trades),
            windows=aggregate.schedule,
            universe=evidence.universe,
            parameter_plans_by_window={value.window.window_id: value.parameter_plan for value in successes},
            configuration_fingerprint=evidence.configuration_fingerprint,
            validation_identities_by_window={
                value.window.window_id: value.validation_evidence.validation_identity for value in successes
            },
        )
        return tuple(value for value in canonical if value.instrument == instrument)

    @staticmethod
    def _evidence(
        source_identity: str, validation_scope_identity: str, instrument: InstrumentIdentity,
        instrument_scope_identity: str, policy: BootstrapPolicy, method_identity: str,
        root_seed_identity: str, seed: int, derived_seed_identity: str, trade_count: int,
        status: ValidationStatus, reason: str | None, point: Decimal | None = None,
        lower: Decimal | None = None, upper: Decimal | None = None,
    ) -> BootstrapEvidence:
        return BootstrapEvidence(
            source_identity, validation_scope_identity, instrument, instrument_scope_identity,
            policy.fingerprint, method_identity, root_seed_identity, seed, derived_seed_identity,
            policy.sample_count, policy.confidence_level, policy.block_length, trade_count,
            point, lower, upper, status, reason,
        )

    @staticmethod
    def monte_carlo_permutation(outcomes: Iterable[Decimal | int | float | str], root_seed: int, identity: str) -> RandomizedResult:
        values = tuple(as_decimal(value, "outcome") for value in outcomes)
        seed = derive_seed(root_seed, RandomizedAnalysisKind.MC1, identity)
        if not values: return RandomizedResult(RandomizedAnalysisKind.MC1, ValidationStatus.INSUFFICIENT_DATA, seed, None, reason="no outcomes")
        shuffled = list(values); random.Random(seed).shuffle(shuffled)
        with localcontext(INTERNAL_DECIMAL_CONTEXT): observed = min((sum(shuffled[:index], Decimal("0")) for index in range(1, len(shuffled)+1)), default=Decimal("0"))
        return RandomizedResult(RandomizedAnalysisKind.MC1, ValidationStatus.PASS, seed, observed)

    @staticmethod
    def monte_carlo_block_drawdown(outcomes: Iterable[Decimal | int | float | str], *, block_length: int, root_seed: int, identity: str, starting_equity: Decimal | int | float | str | None) -> RandomizedResult:
        values = tuple(as_decimal(value, "outcome") for value in outcomes)
        seed = derive_seed(root_seed, RandomizedAnalysisKind.MC2, identity)
        if starting_equity is None: return RandomizedResult(RandomizedAnalysisKind.MC2, ValidationStatus.INVALID, seed, None, reason="explicit starting equity is required")
        equity = as_decimal(starting_equity, "starting_equity")
        if equity <= 0 or block_length <= 0: return RandomizedResult(RandomizedAnalysisKind.MC2, ValidationStatus.INVALID, seed, None, reason="invalid policy")
        if len(values) < block_length: return RandomizedResult(RandomizedAnalysisKind.MC2, ValidationStatus.INSUFFICIENT_DATA, seed, None, reason="evidence shorter than explicit block length")
        rng = random.Random(seed); path: list[Decimal] = []
        while len(path) < len(values):
            start = rng.randrange(len(values)); path.extend(values[(start+i) % len(values)] for i in range(block_length))
        peak = equity; maximum_drawdown = Decimal("0")
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            for value in path[:len(values)]:
                equity += value; peak = max(peak, equity); maximum_drawdown = max(maximum_drawdown, peak-equity)
        return RandomizedResult(RandomizedAnalysisKind.MC2, ValidationStatus.PASS, seed, maximum_drawdown)

    @staticmethod
    def aggregate_monte_carlo_permutation(evidence: "ValidationRunEvidence", windows: Iterable[ValidationWindow], trades: Iterable[OOSTradeEvidence], *, root_seed: int, identity: str) -> RandomizedResult:
        """MC-1 whose indivisible units are canonical synchronized episodes."""
        seed = derive_seed(root_seed, RandomizedAnalysisKind.MC1, identity)
        try:
            values = SynchronizedEpisodeBuilder.build(evidence, windows, trades)
        except (TypeError, ValueError) as error:
            return RandomizedResult(RandomizedAnalysisKind.MC1, ValidationStatus.INVALID, seed, None, reason=str(error))
        values, reason = _canonical_aggregate_episodes(values)
        if reason is not None:
            return RandomizedResult(RandomizedAnalysisKind.MC1, ValidationStatus.INVALID, seed, None, reason=reason)
        if not values:
            return RandomizedResult(RandomizedAnalysisKind.MC1, ValidationStatus.INSUFFICIENT_DATA, seed, None, reason="no synchronized episodes")
        scoped_identity = CanonicalCodec.fingerprint(
            "algofortis-aggregate-mc1-scope/v2",
            (("scope_identity", _text(identity, "identity")),
             ("episodes", tuple(value.identity for value in values))),
        )
        return ValidationStatistics.monte_carlo_permutation(
            (value.aggregate_net_outcome for value in values), root_seed, scoped_identity
        )

    @staticmethod
    def aggregate_monte_carlo_block_drawdown(evidence: "ValidationRunEvidence", windows: Iterable[ValidationWindow], trades: Iterable[OOSTradeEvidence], *, policy: AggregateMC2Policy, root_seed: int, identity: str, starting_equity: Decimal | int | float | str | None) -> RandomizedResult:
        """MC-2 whose blocks are explicitly measured in ordered episode units."""
        seed = derive_seed(root_seed, RandomizedAnalysisKind.MC2, identity)
        if not isinstance(policy, AggregateMC2Policy):
            return RandomizedResult(RandomizedAnalysisKind.MC2, ValidationStatus.INVALID, seed, None, reason="aggregate MC-2 requires AggregateMC2Policy")
        try:
            values = SynchronizedEpisodeBuilder.build(evidence, windows, trades)
        except (TypeError, ValueError) as error:
            return RandomizedResult(RandomizedAnalysisKind.MC2, ValidationStatus.INVALID, seed, None, reason=str(error))
        values, reason = _canonical_aggregate_episodes(values)
        if reason is not None:
            return RandomizedResult(RandomizedAnalysisKind.MC2, ValidationStatus.INVALID, seed, None, reason=reason)
        scoped_identity = CanonicalCodec.fingerprint(
            "algofortis-aggregate-mc2-scope/v2",
            (("scope_identity", _text(identity, "identity")), ("block_unit", policy.block_unit),
             ("episodes", tuple(value.identity for value in values))),
        )
        return ValidationStatistics.monte_carlo_block_drawdown(
            (value.aggregate_net_outcome for value in values),
            block_length=policy.block_length,
            root_seed=root_seed,
            identity=scoped_identity,
            starting_equity=starting_equity,
        )


class MC1Analyzer:
    """The sole §47 authoritative per-instrument MC-1 producer."""

    METHOD_IDENTITY = "MC1_FULL_PERMUTATION_ABSOLUTE_DRAWDOWN_V1"
    QUANTILE_METHOD_IDENTITY = "MC1_EMPIRICAL_NEAREST_RANK_V1"

    @staticmethod
    def _observation_identity(value: OOSTradeEvidence) -> str:
        if value.net_realized_pnl.is_finite():
            return value.fingerprint
        return CanonicalCodec.fingerprint(
            "algofortis-mc1-non-finite-oos-observation/v1",
            (("trade_id", value.trade_id), ("instrument", _instrument_fields(value.instrument)),
             ("window_id", value.window_id), ("closed_at", value.closed_at),
             ("currency", value.currency), ("validation_identity", value.validation_identity)),
        )

    @classmethod
    def _scope(cls, aggregate: object, instrument: InstrumentIdentity) -> _PrimaryOOSInstrumentScope:
        from engine.backtest.walk_forward import MultiWindowWalkForwardResult
        if not isinstance(aggregate, MultiWindowWalkForwardResult):
            raise TypeError("aggregate must be MultiWindowWalkForwardResult")
        if not isinstance(instrument, InstrumentIdentity):
            raise TypeError("instrument must be InstrumentIdentity")
        successes = tuple(aggregate.successful_windows)
        successful_pairs = tuple((value.window.window_id, value.validation_evidence.validation_identity) for value in successes)
        if successes:
            evidence = successes[0].validation_evidence
            if any(value.validation_evidence.universe != evidence.universe or
                   value.validation_evidence.configuration_fingerprint != evidence.configuration_fingerprint
                   for value in successes):
                raise ValueError("successful windows have contradictory validation provenance")
            canonical = CanonicalPrimaryOOS.build(
                ValidationPurpose.PROMOTION,
                tuple(trade for value in successes for trade in value.canonical_oos_trades),
                windows=aggregate.schedule, universe=evidence.universe,
                parameter_plans_by_window={value.window.window_id: value.parameter_plan for value in successes},
                configuration_fingerprint=evidence.configuration_fingerprint,
                validation_identities_by_window={value.window.window_id: value.validation_evidence.validation_identity for value in successes},
            )
        else:
            canonical = ()
        scoped = tuple(value for value in canonical if value.instrument == instrument)
        aggregate_identity = CanonicalCodec.fingerprint(
            "algofortis-primary-oos-aggregate-source/v1",
            (("manifest", aggregate.manifest_fingerprint),
             ("schedule", tuple(value.window_id for value in aggregate.schedule)),
             ("selection", aggregate.selection_identity.fingerprint),
             ("successful_windows", successful_pairs),
             ("observations", tuple(cls._observation_identity(value) for value in canonical))),
        )
        validation_scope = CanonicalCodec.fingerprint(
            "algofortis-primary-oos-validation-scope/v1", (("successful_windows", successful_pairs),),
        )
        source = CanonicalCodec.fingerprint(
            "algofortis-primary-oos-instrument-source/v1",
            (("aggregate", aggregate_identity), ("instrument", _instrument_fields(instrument)),
             ("trades", tuple(cls._observation_identity(value) for value in scoped)),
             ("successful_windows", successful_pairs)),
        )
        instrument_scope = CanonicalCodec.fingerprint(
            "algofortis-primary-oos-instrument-scope/v1",
            (("source", source), ("instrument", _instrument_fields(instrument))),
        )
        return _PrimaryOOSInstrumentScope(aggregate_identity, instrument, scoped, validation_scope, source, instrument_scope)

    @staticmethod
    def _absolute_max_drawdown(outcomes: Iterable[Decimal], *, trial_index: int | None = None) -> Decimal:
        cumulative = Decimal("0"); peak = Decimal("0"); maximum = Decimal("0")
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            for position, value in enumerate(outcomes):
                cumulative += value
                if not cumulative.is_finite():
                    raise _MC1NonFinitePath(trial_index, position, "cumulative_pnl", cumulative)
                peak = max(peak, cumulative)
                drawdown = peak - cumulative
                if not drawdown.is_finite():
                    raise _MC1NonFinitePath(trial_index, position, "drawdown", drawdown)
                maximum = max(maximum, drawdown)
        return maximum

    @staticmethod
    def _quantile_index(value: Decimal, count: int) -> int:
        product = value * Decimal(count)
        ceiling = int(product.to_integral_value(rounding="ROUND_CEILING"))
        return min(count - 1, max(0, ceiling - 1))

    @classmethod
    def analyze(cls, aggregate: object, instrument: InstrumentIdentity, policy: MC1Policy) -> MC1Evidence | StructuredFailureResult:
        if not isinstance(policy, MC1Policy):
            raise TypeError("policy must be MC1Policy")
        scope = cls._scope(aggregate, instrument)
        root_seed_identity = CanonicalCodec.fingerprint(
            "algofortis-mc1-root-seed/v1", (("root_seed", policy.root_seed),),
        )
        if len(scope.trades) < 2:
            return cls._evidence(scope, policy, root_seed_identity, None, None, ValidationStatus.INSUFFICIENT_DATA,
                                 "MC1_INSUFFICIENT_SOURCE_TRADES")
        for index, trade in enumerate(scope.trades):
            if not trade.net_realized_pnl.is_finite():
                evidence = CanonicalCodec.fingerprint(
                    "algofortis-mc1-source-non-finite/v1",
                    (("source", scope.source_identity), ("trade", cls._observation_identity(trade)),
                     ("source_index", index), ("field", "net_realized_pnl"),
                     ("reason", _non_finite_reason(trade.net_realized_pnl))),
                )
                return StructuredFailureResult("structured-failure/v1", aggregate.manifest_fingerprint,
                                               MC1FailureStage.MC1_ANALYSIS.value,
                                               MC1FailureCode.MC1_NON_FINITE_EVIDENCE, evidence, policy.fingerprint)
        method_identity = CanonicalCodec.fingerprint("algofortis-mc1-method/v1", (("method", policy.method_identity),))
        derived_identity = CanonicalCodec.fingerprint(
            "algofortis-mc1-derived-seed/v1",
            (("root_seed", root_seed_identity), ("kind", RandomizedAnalysisKind.MC1),
             ("source", scope.source_identity), ("validation_scope", scope.validation_scope_identity),
             ("instrument_scope", scope.instrument_scope_identity), ("policy", policy.fingerprint),
             ("method", method_identity)),
        )
        seed = derive_seed(policy.root_seed, RandomizedAnalysisKind.MC1, derived_identity)
        values = tuple(value.net_realized_pnl for value in scope.trades)
        try:
            baseline = cls._absolute_max_drawdown(values)
            rng = random.Random(seed)
            trials: list[tuple[int, tuple[int, ...], Decimal]] = []
            for trial_index in range(policy.trial_count):
                indices = list(range(len(values))); rng.shuffle(indices)
                drawdown = cls._absolute_max_drawdown((values[index] for index in indices), trial_index=trial_index)
                trials.append((trial_index, tuple(indices), drawdown))
        except _MC1NonFinitePath as error:
            evidence = CanonicalCodec.fingerprint(
                "algofortis-mc1-generated-non-finite/v1",
                (("source", scope.source_identity), ("policy", policy.fingerprint), ("method", method_identity),
                 ("derived_seed", derived_identity), ("trial_index", error.trial_index),
                 ("path_index", error.position), ("field", error.field), ("reason", error.reason_code))),
            return StructuredFailureResult("structured-failure/v1", aggregate.manifest_fingerprint,
                                           MC1FailureStage.MC1_ANALYSIS.value,
                                           MC1FailureCode.MC1_NON_FINITE_EVIDENCE, evidence, policy.fingerprint)
        distribution = CanonicalCodec.fingerprint("algofortis-mc1-trial-distribution/v1", (("trials", tuple(trials)),))
        ordered = tuple(sorted(value[2] for value in trials))
        quantiles = tuple((value, ordered[cls._quantile_index(value, policy.trial_count)]) for value in policy.requested_drawdown_quantiles)
        return cls._evidence(scope, policy, root_seed_identity, seed, derived_identity, ValidationStatus.PASS, None,
                             baseline, quantiles, max(ordered), distribution)

    @classmethod
    def _evidence(cls, scope: _PrimaryOOSInstrumentScope, policy: MC1Policy, root_seed_identity: str,
                  seed: int | None, derived_identity: str | None, status: ValidationStatus, reason: str | None,
                  baseline: Decimal | None = None, quantiles: tuple[tuple[Decimal, Decimal], ...] = (),
                  worst: Decimal | None = None, distribution: str | None = None) -> MC1Evidence:
        return MC1Evidence(scope.source_identity, scope.validation_scope_identity, scope.instrument,
                           scope.instrument_scope_identity, policy.fingerprint, policy.method_identity,
                           cls.QUANTILE_METHOD_IDENTITY, root_seed_identity, seed, derived_identity,
                           len(scope.trades), policy.trial_count, baseline,
                           policy.requested_drawdown_quantiles, quantiles, worst, distribution, status, reason)


class MC2Analyzer:
    """The sole §48 authoritative per-instrument MC-2 producer."""

    METHOD_IDENTITY = "MC2_PER_WINDOW_CIRCULAR_BLOCK_ABSOLUTE_DRAWDOWN_V1"
    BLOCK_CONSTRUCTION_IDENTITY = "MC2_PER_WINDOW_CIRCULAR_BLOCKS_V1"
    QUANTILE_METHOD_IDENTITY = "MC2_EMPIRICAL_NEAREST_RANK_V1"

    @classmethod
    def _scope(cls, aggregate: object, instrument: InstrumentIdentity) -> tuple[_PrimaryOOSInstrumentScope, tuple[_MC2WindowScope, ...]]:
        scope = MC1Analyzer._scope(aggregate, instrument)
        successes = tuple(aggregate.successful_windows)
        groups: list[_MC2WindowScope] = []
        for window in successes:
            values = tuple(value for value in scope.trades if value.window_id == window.window.window_id)
            source = CanonicalCodec.fingerprint(
                "algofortis-mc2-window-source/v1",
                (("aggregate_source", scope.source_identity), ("window_id", window.window.window_id),
                 ("validation_identity", window.validation_evidence.validation_identity),
                 ("trades", tuple(MC1Analyzer._observation_identity(value) for value in values))),
            )
            groups.append(_MC2WindowScope(
                window.window.window_id, window.validation_evidence.validation_identity, values, source,
            ))
        return scope, tuple(groups)

    @staticmethod
    def _per_window_sources(windows: tuple[_MC2WindowScope, ...]) -> tuple[tuple[str, str, int, str], ...]:
        return tuple((value.window_id, value.validation_identity, value.trade_count, value.source_identity) for value in windows)

    @classmethod
    def _evidence(
        cls, scope: _PrimaryOOSInstrumentScope, windows: tuple[_MC2WindowScope, ...], policy: MC2Policy,
        root_seed_identity: str, seed: int | None, derived_identity: str | None, status: ValidationStatus,
        reason: str | None, baseline: Decimal | None = None,
        quantiles: tuple[tuple[Decimal, Decimal], ...] = (), worst: Decimal | None = None,
        distribution: str | None = None,
    ) -> MC2Evidence:
        return MC2Evidence(
            scope.source_identity, scope.validation_scope_identity, scope.instrument, scope.instrument_scope_identity,
            policy.fingerprint, policy.method_identity, cls.BLOCK_CONSTRUCTION_IDENTITY,
            cls.QUANTILE_METHOD_IDENTITY, root_seed_identity, seed, derived_identity, len(scope.trades),
            cls._per_window_sources(windows), policy.trial_count, policy.block_length, baseline,
            policy.requested_drawdown_quantiles, quantiles, worst, distribution, status, reason,
        )

    @staticmethod
    def _quantile_index(value: Decimal, count: int) -> int:
        ceiling = int((value * Decimal(count)).to_integral_value(rounding="ROUND_CEILING"))
        return min(count - 1, max(0, ceiling - 1))

    @staticmethod
    def _non_finite_source_failure(
        aggregate: object, scope: _PrimaryOOSInstrumentScope, policy: MC2Policy, window: _MC2WindowScope,
        trade: OOSTradeEvidence, global_index: int, local_index: int,
    ) -> StructuredFailureResult:
        evidence = CanonicalCodec.fingerprint(
            "algofortis-mc2-source-non-finite/v1",
            (("subtype", "SOURCE_OBSERVATION_NON_FINITE"), ("source", scope.source_identity),
             ("window_id", window.window_id), ("trade", MC1Analyzer._observation_identity(trade)),
             ("source_index", global_index), ("window_local_source_index", local_index),
             ("field", "net_realized_pnl"), ("reason", _non_finite_reason(trade.net_realized_pnl))),
        )
        return StructuredFailureResult(
            "structured-failure/v1", aggregate.manifest_fingerprint, MC2FailureStage.MC2_ANALYSIS.value,
            MC2FailureCode.MC2_NON_FINITE_EVIDENCE, evidence, policy.fingerprint,
        )

    @staticmethod
    def _non_finite_path_failure(
        aggregate: object, scope: _PrimaryOOSInstrumentScope, policy: MC2Policy, method_identity: str,
        derived_identity: str, error: "_MC1NonFinitePath", references: tuple[tuple[str, int, int, int, int], ...],
    ) -> StructuredFailureResult:
        window_id, block_ordinal, block_start, local_position, global_position = references[error.position]
        evidence = CanonicalCodec.fingerprint(
            "algofortis-mc2-generated-non-finite/v1",
            (("subtype", "GENERATED_PATH_NON_FINITE"), ("source", scope.source_identity),
             ("policy", policy.fingerprint), ("method", method_identity), ("derived_seed", derived_identity),
             ("trial_index", error.trial_index), ("window_id", window_id),
             ("sampled_block_ordinal", block_ordinal), ("sampled_block_start", block_start),
             ("window_local_position", local_position), ("path_position", global_position),
             ("field", error.field), ("reason", error.reason_code)),
        )
        return StructuredFailureResult(
            "structured-failure/v1", aggregate.manifest_fingerprint, MC2FailureStage.MC2_ANALYSIS.value,
            MC2FailureCode.MC2_NON_FINITE_EVIDENCE, evidence, policy.fingerprint,
        )

    @classmethod
    def analyze(cls, aggregate: object, instrument: InstrumentIdentity, policy: MC2Policy) -> MC2Evidence | StructuredFailureResult:
        if not isinstance(policy, MC2Policy):
            raise TypeError("policy must be MC2Policy")
        scope, windows = cls._scope(aggregate, instrument)
        root_seed_identity = CanonicalCodec.fingerprint(
            "algofortis-mc2-root-seed/v1", (("root_seed", policy.root_seed),),
        )
        if len(scope.trades) < 2:
            return cls._evidence(scope, windows, policy, root_seed_identity, None, None,
                                 ValidationStatus.INSUFFICIENT_DATA, "MC2_INSUFFICIENT_SOURCE_TRADES")
        if any(window.trade_count < policy.block_length for window in windows):
            return cls._evidence(scope, windows, policy, root_seed_identity, None, None,
                                 ValidationStatus.INSUFFICIENT_DATA, "MC2_INSUFFICIENT_WINDOW_TRADES_FOR_BLOCK")
        global_indices = {id(value): index for index, value in enumerate(scope.trades)}
        for window in windows:
            for local_index, trade in enumerate(window.trades):
                if not trade.net_realized_pnl.is_finite():
                    return cls._non_finite_source_failure(
                        aggregate, scope, policy, window, trade, global_indices[id(trade)], local_index,
                    )
        method_identity = CanonicalCodec.fingerprint(
            "algofortis-mc2-method/v1", (("method", policy.method_identity),),
        )
        derived_identity = CanonicalCodec.fingerprint(
            "algofortis-mc2-derived-seed/v1",
            (("root_seed", root_seed_identity), ("kind", RandomizedAnalysisKind.MC2),
             ("source", scope.source_identity), ("validation_scope", scope.validation_scope_identity),
             ("instrument_scope", scope.instrument_scope_identity), ("policy", policy.fingerprint),
             ("method", method_identity), ("block_construction", cls.BLOCK_CONSTRUCTION_IDENTITY)),
        )
        seed = derive_seed(policy.root_seed, RandomizedAnalysisKind.MC2, derived_identity)
        try:
            baseline = MC1Analyzer._absolute_max_drawdown(value.net_realized_pnl for value in scope.trades)
        except _MC1NonFinitePath as error:
            # Source values were checked above; retain a deterministic path fallback for tampering races.
            references = tuple((value.window_id, 0, 0, 0, index) for index, value in enumerate(scope.trades))
            return cls._non_finite_path_failure(aggregate, scope, policy, method_identity, derived_identity, error, references)
        rng = random.Random(seed)
        trials: list[tuple[object, ...]] = []
        for trial_index in range(policy.trial_count):
            path_values: list[Decimal] = []
            references: list[tuple[str, int, int, int, int]] = []
            window_records: list[tuple[object, ...]] = []
            for window in windows:
                starts: list[int] = []
                local_indices: list[int] = []
                block_ordinals: list[int] = []
                while len(local_indices) < window.trade_count:
                    start = rng.randrange(window.trade_count)
                    starts.append(start)
                    block_ordinal = len(starts) - 1
                    local_indices.extend((start + offset) % window.trade_count for offset in range(policy.block_length))
                    block_ordinals.extend([block_ordinal] * policy.block_length)
                local_indices = local_indices[:window.trade_count]
                block_ordinals = block_ordinals[:window.trade_count]
                trade_identities = tuple(MC1Analyzer._observation_identity(window.trades[index]) for index in local_indices)
                window_records.append((window.window_id, window.trade_count, tuple(starts), policy.block_length,
                                       tuple(local_indices), trade_identities))
                for position, local_index in enumerate(local_indices):
                    path_values.append(window.trades[local_index].net_realized_pnl)
                    references.append((window.window_id, block_ordinals[position], starts[block_ordinals[position]],
                                       position, len(path_values) - 1))
            try:
                drawdown = MC1Analyzer._absolute_max_drawdown(path_values, trial_index=trial_index)
            except _MC1NonFinitePath as error:
                return cls._non_finite_path_failure(
                    aggregate, scope, policy, method_identity, derived_identity, error, tuple(references),
                )
            path_identity = CanonicalCodec.fingerprint(
                "algofortis-mc2-trial-path/v1", (("trial_index", trial_index), ("windows", tuple(window_records))),
            )
            trials.append((trial_index, tuple(window_records), path_identity, drawdown))
        distribution = CanonicalCodec.fingerprint(
            "algofortis-mc2-trial-distribution/v1", (("trials", tuple(trials)),),
        )
        ordered = tuple(sorted(value[3] for value in trials))
        quantiles = tuple(
            (value, ordered[cls._quantile_index(value, policy.trial_count)])
            for value in policy.requested_drawdown_quantiles
        )
        return cls._evidence(scope, windows, policy, root_seed_identity, seed, derived_identity,
                             ValidationStatus.PASS, None, baseline, quantiles, max(ordered), distribution)


class _MC1NonFinitePath(ValueError):
    def __init__(self, trial_index: int | None, position: int, field: str, value: Decimal) -> None:
        self.trial_index = trial_index
        self.position = position
        self.field = field
        self.reason_code = _non_finite_reason(value)
        super().__init__(self.reason_code)


def _canonical_aggregate_episodes(episodes: Iterable[SynchronizedEconomicEpisode]) -> tuple[tuple[SynchronizedEconomicEpisode, ...], str | None]:
    """Reject ambiguous provenance before any aggregate randomized analysis."""
    values = tuple(episodes)
    if not all(isinstance(value, SynchronizedEconomicEpisode) for value in values):
        return (), "aggregate analysis requires synchronized economic episodes"
    ordered = tuple(sorted(values, key=lambda value: (value.portfolio_observation_time, value.window_id, value.identity)))
    if len({value.identity for value in ordered}) != len(ordered):
        return (), "duplicate synchronized episode identity"
    if not ordered:
        return ordered, None
    run_ids = {value.validation_run_id for value in ordered}
    validation_identities = {value.validation_identity for value in ordered}
    if len(run_ids) != 1 or len(validation_identities) != 1:
        return (), "aggregate episodes must share one frozen validation run"
    member_ids = [member.trade_id for episode in ordered for member in episode.members]
    if len(member_ids) != len(set(member_ids)):
        return (), "canonical member evidence may appear in exactly one episode"
    return ordered, None


# `BootstrapAnalyzer` owns only the new Step-4A public boundary.  The
# pre-existing Monte-Carlo methods remain part of `ValidationStatistics`; they
# are assigned back after the extraction above to preserve their frozen public
# surface without changing their implementations.
ValidationStatistics.monte_carlo_permutation = staticmethod(BootstrapAnalyzer.monte_carlo_permutation)
ValidationStatistics.monte_carlo_block_drawdown = staticmethod(BootstrapAnalyzer.monte_carlo_block_drawdown)
ValidationStatistics.aggregate_monte_carlo_permutation = staticmethod(BootstrapAnalyzer.aggregate_monte_carlo_permutation)
ValidationStatistics.aggregate_monte_carlo_block_drawdown = staticmethod(BootstrapAnalyzer.aggregate_monte_carlo_block_drawdown)


@dataclass(frozen=True)
class SensitivityNeighborhood:
    form: SensitivityForm
    parameter_domain_fingerprint: str
    points: tuple[str, ...]
    categorical: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "form", SensitivityForm(self.form))
        object.__setattr__(self, "parameter_domain_fingerprint", _text(self.parameter_domain_fingerprint, "parameter_domain_fingerprint"))
        points = tuple(sorted(_text(value, "sensitivity point") for value in self.points))
        if not points or len(points) != len(set(points)): raise ValueError("sensitivity points must be non-empty and unique")
        object.__setattr__(self, "points", points)


@dataclass(frozen=True)
class SensitivityPointResult:
    point: str
    status: ValidationStatus
    evidence_fingerprint: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "point", _text(self.point, "point")); object.__setattr__(self, "status", ValidationStatus(self.status))
        if self.evidence_fingerprint is not None: object.__setattr__(self, "evidence_fingerprint", _text(self.evidence_fingerprint, "evidence_fingerprint"))


@dataclass(frozen=True)
class SensitivityResult:
    scope: SensitivityScope
    status: ValidationStatus
    requested_points: tuple[str, ...]
    results: tuple[SensitivityPointResult, ...]
    coverage_fraction: Decimal


class SensitivityEvaluator:
    @staticmethod
    def evaluate(neighborhood: SensitivityNeighborhood | None, scope: SensitivityScope, results: Iterable[SensitivityPointResult]) -> SensitivityResult:
        if neighborhood is None:
            return SensitivityResult(SensitivityScope(scope), ValidationStatus.NOT_APPLICABLE, (), (), Decimal("1"))
        values = tuple(results)
        by_point = {value.point: value for value in values}
        if len(by_point) != len(values) or not set(by_point) <= set(neighborhood.points): raise ValueError("sensitivity results must be unique declared points")
        valid = sum(value.status is ValidationStatus.PASS for value in values)
        coverage = Decimal(valid) / Decimal(len(neighborhood.points))
        statuses = [value.status for value in values]
        status = combine_statuses(statuses) if len(values) == len(neighborhood.points) else ValidationStatus.INSUFFICIENT_DATA
        return SensitivityResult(SensitivityScope(scope), status, neighborhood.points, tuple(sorted(values, key=lambda value: value.point)), coverage)


def combine_statuses(statuses: Iterable[ValidationStatus]) -> ValidationStatus:
    values = tuple(ValidationStatus(value) for value in statuses)
    applicable = tuple(value for value in values if value is not ValidationStatus.NOT_APPLICABLE)
    if not applicable: return ValidationStatus.NOT_APPLICABLE
    for status in (ValidationStatus.INVALID, ValidationStatus.INSUFFICIENT_DATA, ValidationStatus.FAIL, ValidationStatus.PASS):
        if status in applicable: return status
    return ValidationStatus.NOT_APPLICABLE


@dataclass(frozen=True)
class ValidationGateResult:
    gate_id: str
    status: ValidationStatus
    reason: str | None
    policy_version: str
    evidence_identity: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "gate_id", _text(self.gate_id, "gate_id")); object.__setattr__(self, "status", ValidationStatus(self.status))
        object.__setattr__(self, "policy_version", _text(self.policy_version, "policy_version")); object.__setattr__(self, "evidence_identity", _text(self.evidence_identity, "evidence_identity"))


@dataclass(frozen=True)
class InstrumentValidationEvidence:
    instrument: InstrumentIdentity
    market_profile_fingerprint: str
    eligible_windows: tuple[str, ...]
    primary_status: ValidationStatus
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, InstrumentIdentity): raise TypeError("instrument must be InstrumentIdentity")
        object.__setattr__(self, "market_profile_fingerprint", _text(self.market_profile_fingerprint, "market_profile_fingerprint"))
        object.__setattr__(self, "eligible_windows", tuple(sorted(_text(value, "window_id") for value in self.eligible_windows)))
        object.__setattr__(self, "primary_status", ValidationStatus(self.primary_status)); object.__setattr__(self, "currency", _text(self.currency, "currency"))


@dataclass(frozen=True)
class FXEvidence:
    """Validation-only FX provenance; this is not an FX engine or price feed."""

    policy_fingerprint: str
    status: ValidationStatus
    evidence_fingerprint: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_fingerprint", _text(self.policy_fingerprint, "policy_fingerprint"))
        object.__setattr__(self, "status", ValidationStatus(self.status))
        if self.evidence_fingerprint is not None:
            object.__setattr__(self, "evidence_fingerprint", _text(self.evidence_fingerprint, "evidence_fingerprint"))


@dataclass(frozen=True)
class RegimeValidationEvidence:
    """Validation-side provenance projection; it never classifies a regime."""

    snapshots: tuple[EntryRegimeSnapshot, ...]

    def __post_init__(self) -> None:
        values = tuple(self.snapshots)
        if not all(isinstance(value, EntryRegimeSnapshot) for value in values):
            raise TypeError("snapshots must contain EntryRegimeSnapshot values")
        object.__setattr__(self, "snapshots", tuple(sorted(values, key=lambda value: value.entry_event_key)))

    @property
    def evidence_fingerprint(self) -> str:
        return entry_regime_evidence_fingerprint(self.snapshots)


@dataclass(frozen=True)
class ScopedValidationResultIdentity:
    """Post-canonical v1 result identity; foreign raw snapshots never enter it."""

    canonical_trades: tuple[OOSTradeEvidence, ...]
    applicable_snapshots: tuple[EntryRegimeSnapshot, ...]
    gate_evidence: tuple[ValidationGateResult, ...]

    def __post_init__(self) -> None:
        if not all(isinstance(value, OOSTradeEvidence) for value in self.canonical_trades):
            raise TypeError("canonical_trades must contain OOSTradeEvidence")
        if not all(isinstance(value, EntryRegimeSnapshot) for value in self.applicable_snapshots):
            raise TypeError("applicable_snapshots must contain EntryRegimeSnapshot")
        if not all(isinstance(value, ValidationGateResult) for value in self.gate_evidence):
            raise TypeError("gate_evidence must contain ValidationGateResult")
        object.__setattr__(self, "canonical_trades", tuple(sorted(self.canonical_trades, key=lambda value: value.fingerprint)))
        object.__setattr__(self, "applicable_snapshots", tuple(sorted(self.applicable_snapshots, key=lambda value: value.fingerprint)))
        object.__setattr__(self, "gate_evidence", tuple(sorted(self.gate_evidence, key=lambda value: (value.gate_id, value.evidence_identity))))

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "ScopedValidationResultIdentity/v1",
            (("canonical_oos_trades", tuple(value.fingerprint for value in self.canonical_trades)),
             ("applicable_entry_regimes", tuple(value.fingerprint for value in self.applicable_snapshots)),
             ("gate_evidence", tuple((value.gate_id, value.status.value, value.policy_version, value.evidence_identity) for value in self.gate_evidence))),
        )


@dataclass(frozen=True)
class ValidationRunEvidence:
    purpose: ValidationPurpose
    source_run_id: str
    configuration_fingerprint: str
    source_data_fingerprint: str
    market_profile_fingerprint: str
    cost_policy_fingerprint: str
    metric_policy_fingerprint: str
    strategy_id: str
    strategy_version: str
    parameter_plan: ParameterPlan
    universe: tuple[InstrumentValidationEvidence, ...]
    window_policy: WalkForwardPolicy
    base_currency: str
    fx_policy_fingerprint: str | None
    statistical_policy_fingerprint: str
    seed_policy_fingerprint: str
    fx_evidence: FXEvidence | None = None
    regime_evidence: RegimeValidationEvidence | None = None
    regime_evidence_required: bool = False
    schema_version: str = "ValidationRunEvidence/v1"
    account_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "purpose", ValidationPurpose(self.purpose))
        for name in ("source_run_id", "configuration_fingerprint", "source_data_fingerprint", "market_profile_fingerprint", "cost_policy_fingerprint", "metric_policy_fingerprint", "strategy_id", "strategy_version", "base_currency", "statistical_policy_fingerprint", "seed_policy_fingerprint"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.fx_policy_fingerprint is not None: object.__setattr__(self, "fx_policy_fingerprint", _text(self.fx_policy_fingerprint, "fx_policy_fingerprint"))
        if self.fx_evidence is not None and not isinstance(self.fx_evidence, FXEvidence):
            raise TypeError("fx_evidence must be FXEvidence")
        if self.regime_evidence is not None and not isinstance(self.regime_evidence, RegimeValidationEvidence):
            raise TypeError("regime_evidence must be RegimeValidationEvidence")
        if not isinstance(self.regime_evidence_required, bool):
            raise TypeError("regime_evidence_required must be bool")
        if self.schema_version not in {"ValidationRunEvidence/v1", "ValidationRunEvidence/v2"}:
            raise ValueError("validation run evidence schema_version is unsupported")
        if self.schema_version == "ValidationRunEvidence/v2":
            object.__setattr__(self, "account_id", _text(self.account_id, "account_id"))
        elif self.account_id is not None:
            raise ValueError("v1 validation run evidence cannot carry account_id")
        if self.fx_evidence is not None and self.fx_policy_fingerprint != self.fx_evidence.policy_fingerprint:
            raise ValueError("FX evidence must use the declared FX policy")
        if not isinstance(self.parameter_plan, ParameterPlan) or not isinstance(self.window_policy, WalkForwardPolicy): raise TypeError("parameter_plan and window_policy are required contracts")
        universe = tuple(self.universe)
        if not universe or not all(isinstance(value, InstrumentValidationEvidence) for value in universe): raise ValueError("universe must contain instrument validation evidence")
        keys = [_instrument_sort_key(value.instrument) for value in universe]
        if len(keys) != len(set(keys)): raise ValueError("instrument universe must be unique")
        object.__setattr__(self, "universe", tuple(sorted(universe, key=lambda value: _instrument_sort_key(value.instrument))))

    @property
    def universe_fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-validation-universe/v1",
            (("instruments", tuple(_instrument_fields(value.instrument) for value in self.universe)),),
        )

    @property
    def validation_identity(self) -> str:
        fx_evidence = None if self.fx_evidence is None else (
            self.fx_evidence.status, self.fx_evidence.evidence_fingerprint,
        )
        # The historical v1 contract binds its run-level regime commitment.
        # Regime-aware v2 instead follows §36.3: raw snapshots are selected
        # only after canonical OOS construction and bind scoped result identity.
        run_regime_evidence = (
            None
            if self.schema_version == "ValidationRunEvidence/v2" or self.regime_evidence is None
            else self.regime_evidence.evidence_fingerprint
        )
        return CanonicalCodec.fingerprint(
            "algofortis-validation-run-evidence/v2",
            (("schema_version", self.schema_version), ("purpose", self.purpose),
             ("source_run_id", self.source_run_id), ("account_id", self.account_id),
             ("configuration_fingerprint", self.configuration_fingerprint),
             ("source_data_fingerprint", self.source_data_fingerprint),
             ("market_profile_fingerprint", self.market_profile_fingerprint),
             ("cost_policy_fingerprint", self.cost_policy_fingerprint),
             ("metric_policy_fingerprint", self.metric_policy_fingerprint),
             ("strategy_id", self.strategy_id), ("strategy_version", self.strategy_version),
             ("parameter_fingerprint", self.parameter_plan.parameter_fingerprint),
             ("universe_fingerprint", self.universe_fingerprint),
             ("window_policy_fingerprint", self.window_policy.fingerprint),
             ("embargo_map_fingerprint", self.window_policy.embargo_map.fingerprint),
             ("base_currency", self.base_currency), ("fx_policy_fingerprint", self.fx_policy_fingerprint),
             ("fx_evidence", fx_evidence),
             ("run_regime_evidence_fingerprint", run_regime_evidence),
             ("regime_evidence_required", self.regime_evidence_required),
             ("statistical_policy_fingerprint", self.statistical_policy_fingerprint),
             ("seed_policy_fingerprint", self.seed_policy_fingerprint)),
        )


class PromotionGateKind(str, Enum):
    """The fixed Step-6 gate order; caller/evaluation order is never evidence."""

    PROVENANCE_SCHEMA = "PROVENANCE_SCHEMA"
    COMPLETE_WINDOWS = "COMPLETE_WINDOWS"
    SAMPLE_SUFFICIENCY_BOOTSTRAP = "SAMPLE_SUFFICIENCY_BOOTSTRAP"
    MC1_SEQUENCE_RISK = "MC1_SEQUENCE_RISK"
    MC2_DEPENDENCE_RISK = "MC2_DEPENDENCE_RISK"
    PARAMETER_SENSITIVITY = "PARAMETER_SENSITIVITY"


_PROMOTION_GATE_ORDER = tuple(PromotionGateKind)


@dataclass(frozen=True)
class PromotionPolicy:
    """The owner-locked, non-tunable Step-6 promotion method."""

    minimum_complete_windows: int = 3
    normal_sample_trade_count: int = 200
    mc1_quantile: Decimal = Decimal("0.95")
    mc1_max_drawdown_limit_ratio: Decimal = Decimal("1.50")
    mc2_quantile: Decimal = Decimal("0.95")
    mc2_max_drawdown_limit_ratio: Decimal = Decimal("1.50")
    sensitivity_not_applicable_neutral: bool = True
    schema_version: str = "PromotionPolicy/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "PromotionPolicy/v1":
            raise ValueError("unsupported promotion policy schema_version")
        if self.minimum_complete_windows != 3 or self.normal_sample_trade_count != 200:
            raise ValueError("PromotionPolicy/v1 has no caller-controlled count thresholds")
        if self.mc1_quantile != Decimal("0.95") or self.mc2_quantile != Decimal("0.95"):
            raise ValueError("PromotionPolicy/v1 requires the locked q95 gates")
        if (self.mc1_max_drawdown_limit_ratio != Decimal("1.50")
                or self.mc2_max_drawdown_limit_ratio != Decimal("1.50")):
            raise ValueError("PromotionPolicy/v1 requires the locked 1.50 drawdown ratios")
        if self.sensitivity_not_applicable_neutral is not True:
            raise ValueError("PromotionPolicy/v1 requires neutral NOT_APPLICABLE sensitivity")

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-promotion-policy/v1",
            (("schema", self.schema_version), ("minimum_complete_windows", self.minimum_complete_windows),
             ("normal_sample_trade_count", self.normal_sample_trade_count),
             ("mc1_quantile", self.mc1_quantile), ("mc1_limit_ratio", self.mc1_max_drawdown_limit_ratio),
             ("mc2_quantile", self.mc2_quantile), ("mc2_limit_ratio", self.mc2_max_drawdown_limit_ratio),
             ("sensitivity_not_applicable_neutral", self.sensitivity_not_applicable_neutral),
             ("gate_order", tuple(value.value for value in _PROMOTION_GATE_ORDER))),
        )


@dataclass(frozen=True)
class PromotionGateResult:
    """One immutable Step-6 gate outcome, including non-Boolean status."""

    gate_kind: PromotionGateKind
    applicable: bool
    source_identities: tuple[str, ...]
    policy_identity: str
    status: ValidationStatus
    reason_codes: tuple[str, ...] = ()
    measurements: tuple[tuple[str, object], ...] = ()
    schema_version: str = "PromotionGateResult/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "PromotionGateResult/v1":
            raise ValueError("unsupported promotion gate result schema_version")
        object.__setattr__(self, "gate_kind", PromotionGateKind(self.gate_kind))
        if not isinstance(self.applicable, bool):
            raise TypeError("applicable must be bool")
        sources = tuple(_text(value, "source_identity") for value in self.source_identities)
        object.__setattr__(self, "source_identities", tuple(sorted(set(sources))))
        object.__setattr__(self, "policy_identity", _text(self.policy_identity, "policy_identity"))
        object.__setattr__(self, "status", ValidationStatus(self.status))
        reasons = tuple(sorted(set(_text(value, "reason_code") for value in self.reason_codes)))
        object.__setattr__(self, "reason_codes", reasons)
        values = tuple(self.measurements)
        if not all(isinstance(value, tuple) and len(value) == 2 for value in values):
            raise TypeError("measurements must contain key/value pairs")
        names = tuple(_text(value[0], "measurement name") for value in values)
        if len(set(names)) != len(names):
            raise ValueError("promotion measurements must have unique names")
        object.__setattr__(self, "measurements", tuple(sorted(values, key=lambda value: value[0])))
        if self.status is ValidationStatus.NOT_APPLICABLE and self.applicable:
            raise ValueError("NOT_APPLICABLE promotion gate cannot be applicable")

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-promotion-gate-result/v1",
            (("schema", self.schema_version), ("gate", self.gate_kind.value), ("applicable", self.applicable),
             ("sources", self.source_identities), ("policy", self.policy_identity), ("status", self.status),
             ("reasons", self.reason_codes), ("measurements", self.measurements)),
        )


@dataclass(frozen=True)
class PromotionDecisionEvidence:
    """The pure authoritative Step-6 promotion decision; it is not D7 output."""

    policy_fingerprint: str
    manifest_fingerprint: str
    validation_scope_identity: str
    instrument: InstrumentIdentity
    instrument_scope_identity: str
    aggregate_walk_forward_identity: str
    primary_oos_source_identity: str | None
    gate_results: tuple[PromotionGateResult, ...]
    blocker_reasons: tuple[str, ...]
    status: ValidationStatus
    promotable: bool
    schema_version: str = "PromotionDecisionEvidence/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "PromotionDecisionEvidence/v1":
            raise ValueError("unsupported promotion decision schema_version")
        for name in ("policy_fingerprint", "manifest_fingerprint", "validation_scope_identity",
                     "instrument_scope_identity", "aggregate_walk_forward_identity"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.primary_oos_source_identity is not None:
            object.__setattr__(self, "primary_oos_source_identity", _text(
                self.primary_oos_source_identity, "primary_oos_source_identity"))
        if not isinstance(self.instrument, InstrumentIdentity):
            raise TypeError("instrument must be InstrumentIdentity")
        gates = tuple(self.gate_results)
        if not all(isinstance(value, PromotionGateResult) for value in gates):
            raise TypeError("gate_results must contain PromotionGateResult")
        if tuple(value.gate_kind for value in gates) != _PROMOTION_GATE_ORDER:
            raise ValueError("promotion gate results must use the canonical complete gate order")
        object.__setattr__(self, "gate_results", gates)
        reasons = tuple(_text(value, "blocker_reason") for value in self.blocker_reasons)
        if len(reasons) != len(set(reasons)):
            raise ValueError("promotion blocker reasons must be unique")
        object.__setattr__(self, "blocker_reasons", reasons)
        object.__setattr__(self, "status", ValidationStatus(self.status))
        if not isinstance(self.promotable, bool) or self.promotable != (self.status is ValidationStatus.PASS):
            raise ValueError("promotion is true only for PASS")

    @property
    def result_fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-promotion-decision-evidence/v1",
            (("schema", self.schema_version), ("policy", self.policy_fingerprint),
             ("manifest", self.manifest_fingerprint), ("validation_scope", self.validation_scope_identity),
             ("instrument", _instrument_fields(self.instrument)), ("instrument_scope", self.instrument_scope_identity),
             ("aggregate", self.aggregate_walk_forward_identity), ("primary_oos", self.primary_oos_source_identity),
             ("gates", tuple(value.fingerprint for value in self.gate_results)),
             ("blockers", self.blocker_reasons), ("status", self.status), ("promotable", self.promotable)),
        )


class PromotionEvaluator:
    """Pure Step-6 consumer of already-produced validation evidence."""

    @staticmethod
    def _gate(kind: PromotionGateKind, status: ValidationStatus, reason: str | None, policy: PromotionPolicy,
              *sources: str, applicable: bool = True, measurements: tuple[tuple[str, object], ...] = ()) -> PromotionGateResult:
        return PromotionGateResult(kind, applicable, tuple(value for value in sources if value), policy.fingerprint,
                                   status, () if reason is None else (reason,), measurements)

    @staticmethod
    def _analysis_provenance(value: object, instrument: InstrumentIdentity, validation_scope: str,
                             source: str | None = None) -> str | None:
        if value is None:
            return "PROMOTION_REQUIRED_EVIDENCE_MISSING"
        if getattr(value, "instrument", None) != instrument:
            return "PROMOTION_FOREIGN_INSTRUMENT"
        if getattr(value, "validation_scope_identity", None) != validation_scope:
            return "PROMOTION_VALIDATION_SCOPE_MISMATCH"
        if source is not None and getattr(value, "source_primary_oos_identity", None) != source:
            return "PROMOTION_PRIMARY_OOS_SOURCE_MISMATCH"
        return None

    @staticmethod
    def _quantile(evidence: MC1Evidence | MC2Evidence, quantile: Decimal) -> Decimal | None:
        if quantile not in evidence.requested_drawdown_quantiles:
            return None
        matches = tuple(value for value in evidence.randomized_drawdown_quantiles if value[0] == quantile)
        return matches[0][1] if len(matches) == 1 else None

    @classmethod
    def evaluate(cls, aggregate_walk_forward: object, instrument: InstrumentIdentity, manifest: ReproducibilityManifest,
                 validation_evidence: ValidationRunEvidence, bootstrap_evidence: BootstrapEvidence | None,
                 mc1_evidence: MC1Evidence | None, mc2_evidence: MC2Evidence | None,
                 sensitivity_evidence: AggregateSensitivityEvidence | None, policy: PromotionPolicy) -> PromotionDecisionEvidence:
        """Evaluate evidence only: no runners, analyzers, RNG, or mutation are invoked."""
        if not isinstance(instrument, InstrumentIdentity) or not isinstance(manifest, ReproducibilityManifest):
            raise TypeError("instrument and manifest are required contracts")
        if not isinstance(validation_evidence, ValidationRunEvidence) or not isinstance(policy, PromotionPolicy):
            raise TypeError("validation_evidence and policy are required contracts")
        aggregate_identity = getattr(aggregate_walk_forward, "aggregate_identity", None)
        aggregate_manifest = getattr(aggregate_walk_forward, "manifest_fingerprint", None)
        schedule = tuple(getattr(aggregate_walk_forward, "schedule", ()))
        successful = tuple(getattr(aggregate_walk_forward, "successful_windows", ()))
        aggregate_trades = tuple(getattr(aggregate_walk_forward, "canonical_oos_trades", ()))
        canonical_trades = tuple(value for value in aggregate_trades if getattr(value, "instrument", None) == instrument)
        try:
            successful_pairs = tuple(
                (value.window.window_id, value.validation_evidence.validation_identity)
                for value in successful
            )
        except AttributeError:
            successful_pairs = ()
        primary_validation_scope = CanonicalCodec.fingerprint(
            "algofortis-primary-oos-validation-scope/v1", (("successful_windows", successful_pairs),),
        )
        bootstrap_validation_scope = CanonicalCodec.fingerprint(
            "algofortis-bootstrap-validation-scope/v1", (("successful_windows", successful_pairs),),
        )
        try:
            primary_aggregate_source = CanonicalCodec.fingerprint(
                "algofortis-primary-oos-aggregate-source/v1",
                (("manifest", aggregate_manifest), ("schedule", tuple(value.window_id for value in schedule)),
                 ("selection", aggregate_walk_forward.selection_identity.fingerprint),
                 ("successful_windows", successful_pairs),
                 ("observations", tuple(value.fingerprint for value in aggregate_trades))),
            )
            expected_primary_source = CanonicalCodec.fingerprint(
                "algofortis-primary-oos-instrument-source/v1",
                (("aggregate", primary_aggregate_source), ("instrument", _instrument_fields(instrument)),
                 ("trades", tuple(value.fingerprint for value in canonical_trades)),
                 ("successful_windows", successful_pairs)),
            )
        except (AttributeError, TypeError, ValueError):
            expected_primary_source = None
        provenance_reason: str | None = None
        if (not isinstance(aggregate_identity, str) or not aggregate_identity or aggregate_manifest != manifest.manifest_fingerprint
                or validation_evidence.purpose is not ValidationPurpose.PROMOTION):
            provenance_reason = "PROMOTION_AGGREGATE_OR_MANIFEST_PROVENANCE_MISMATCH"
        elif not all(isinstance(value, OOSTradeEvidence) for value in aggregate_trades):
            provenance_reason = "PROMOTION_CANONICAL_PRIMARY_OOS_INSTRUMENT_MISMATCH"
        elif any(value.validation_identity not in {pair[1] for pair in successful_pairs} for value in aggregate_trades):
            provenance_reason = "PROMOTION_CANONICAL_PRIMARY_OOS_VALIDATION_SCOPE_MISMATCH"
        source = None
        if mc1_evidence is not None:
            source = mc1_evidence.source_primary_oos_identity
            if expected_primary_source is None or source != expected_primary_source:
                provenance_reason = provenance_reason or "PROMOTION_PRIMARY_OOS_SOURCE_MISMATCH"
        if mc1_evidence is not None and mc2_evidence is not None and source != mc2_evidence.source_primary_oos_identity:
            provenance_reason = provenance_reason or "PROMOTION_PRIMARY_OOS_SOURCE_MISMATCH"
        provenance_sources = tuple(value for value in (
            aggregate_identity if isinstance(aggregate_identity, str) else "", source or "",
            "" if bootstrap_evidence is None else bootstrap_evidence.result_fingerprint,
            "" if mc1_evidence is None else mc1_evidence.result_fingerprint,
            "" if mc2_evidence is None else mc2_evidence.result_fingerprint,
            "" if sensitivity_evidence is None else sensitivity_evidence.fingerprint,
        ) if value)
        provenance = cls._gate(PromotionGateKind.PROVENANCE_SCHEMA,
                               ValidationStatus.INVALID if provenance_reason else ValidationStatus.PASS,
                               provenance_reason, policy, *provenance_sources)

        complete_reason = None
        achieved = getattr(aggregate_walk_forward, "achieved_complete_windows", None)
        required = getattr(aggregate_walk_forward, "required_complete_windows", None)
        if achieved != len(successful) or not isinstance(achieved, int) or not isinstance(required, int):
            complete_reason = "PROMOTION_COMPLETE_WINDOW_PROVENANCE_MISMATCH"
            complete_status = ValidationStatus.INVALID
        elif achieved < policy.minimum_complete_windows:
            complete_reason = "PROMOTION_INSUFFICIENT_COMPLETE_WINDOWS"
            complete_status = ValidationStatus.INSUFFICIENT_DATA
        else:
            complete_status = ValidationStatus.PASS
        complete = cls._gate(PromotionGateKind.COMPLETE_WINDOWS, complete_status, complete_reason, policy,
                             aggregate_identity if isinstance(aggregate_identity, str) else "",
                             measurements=(("achieved_complete_windows", achieved), ("required_complete_windows", required),
                                           ("promotion_minimum_complete_windows", policy.minimum_complete_windows)))

        count = len(canonical_trades)
        bootstrap_reason = cls._analysis_provenance(bootstrap_evidence, instrument, bootstrap_validation_scope) if bootstrap_evidence is not None else None
        if count >= policy.normal_sample_trade_count:
            sample_status, sample_reason = (ValidationStatus.INVALID, bootstrap_reason) if bootstrap_reason else (ValidationStatus.PASS, None)
        elif bootstrap_evidence is None:
            sample_status, sample_reason = ValidationStatus.INVALID, "PROMOTION_REQUIRED_BOOTSTRAP_MISSING"
        elif bootstrap_reason:
            sample_status, sample_reason = ValidationStatus.INVALID, bootstrap_reason
        elif bootstrap_evidence.status is ValidationStatus.INVALID:
            sample_status, sample_reason = ValidationStatus.INVALID, bootstrap_evidence.reason_code or "PROMOTION_BOOTSTRAP_INVALID"
        elif bootstrap_evidence.status is ValidationStatus.INSUFFICIENT_DATA:
            sample_status, sample_reason = ValidationStatus.INSUFFICIENT_DATA, bootstrap_evidence.reason_code or "PROMOTION_BOOTSTRAP_INSUFFICIENT_DATA"
        elif (bootstrap_evidence.status is ValidationStatus.PASS and bootstrap_evidence.under_200_exception_eligible
              and bootstrap_evidence.ci_lower is not None and bootstrap_evidence.ci_lower > 0):
            sample_status, sample_reason = ValidationStatus.PASS, None
        else:
            sample_status, sample_reason = ValidationStatus.FAIL, "PROMOTION_BOOTSTRAP_CI_LOWER_NOT_STRICTLY_POSITIVE"
        sample = cls._gate(PromotionGateKind.SAMPLE_SUFFICIENCY_BOOTSTRAP, sample_status, sample_reason, policy,
                           "" if bootstrap_evidence is None else bootstrap_evidence.result_fingerprint,
                           measurements=(("completed_oos_trade_count", count),))

        def risk_gate(kind: PromotionGateKind, evidence: MC1Evidence | MC2Evidence | None, quantile: Decimal,
                      ratio: Decimal, missing_reason: str) -> PromotionGateResult:
            mismatch = cls._analysis_provenance(evidence, instrument, primary_validation_scope, source)
            if evidence is None:
                return cls._gate(kind, ValidationStatus.INVALID, missing_reason, policy)
            if mismatch:
                return cls._gate(kind, ValidationStatus.INVALID, mismatch, policy, evidence.result_fingerprint)
            if evidence.status is ValidationStatus.INVALID:
                return cls._gate(kind, ValidationStatus.INVALID, evidence.reason_code or "PROMOTION_ANALYSIS_INVALID", policy, evidence.result_fingerprint)
            if evidence.status is ValidationStatus.INSUFFICIENT_DATA:
                return cls._gate(kind, ValidationStatus.INSUFFICIENT_DATA, evidence.reason_code or "PROMOTION_ANALYSIS_INSUFFICIENT_DATA", policy, evidence.result_fingerprint)
            risk = cls._quantile(evidence, quantile)
            baseline = evidence.original_order_absolute_max_drawdown
            if evidence.status is not ValidationStatus.PASS or risk is None or baseline is None:
                return cls._gate(kind, ValidationStatus.INVALID, missing_reason, policy, evidence.result_fingerprint)
            passed = risk == 0 if baseline == 0 else risk <= ratio * baseline
            return cls._gate(kind, ValidationStatus.PASS if passed else ValidationStatus.FAIL,
                             None if passed else "PROMOTION_MAX_DRAWDOWN_LIMIT_BREACH", policy,
                             evidence.result_fingerprint, measurements=(("q95", risk), ("baseline", baseline), ("limit_ratio", ratio)))

        mc1 = risk_gate(PromotionGateKind.MC1_SEQUENCE_RISK, mc1_evidence, policy.mc1_quantile,
                        policy.mc1_max_drawdown_limit_ratio, "PROMOTION_MC1_REQUIRED_QUANTILE_MISSING")
        mc2 = risk_gate(PromotionGateKind.MC2_DEPENDENCE_RISK, mc2_evidence, policy.mc2_quantile,
                        policy.mc2_max_drawdown_limit_ratio, "PROMOTION_MC2_REQUIRED_QUANTILE_MISSING")

        if sensitivity_evidence is None:
            sensitivity = cls._gate(PromotionGateKind.PARAMETER_SENSITIVITY, ValidationStatus.INVALID,
                                    "PROMOTION_REQUIRED_SENSITIVITY_MISSING", policy)
        elif sensitivity_evidence.schema_version != "AggregateSensitivityEvidence/v1":
            sensitivity = cls._gate(PromotionGateKind.PARAMETER_SENSITIVITY, ValidationStatus.INVALID,
                                    "PROMOTION_SENSITIVITY_SCHEMA_UNSUPPORTED", policy, sensitivity_evidence.fingerprint)
        else:
            status = sensitivity_evidence.status
            sensitivity = cls._gate(PromotionGateKind.PARAMETER_SENSITIVITY, status,
                                    None if status in (ValidationStatus.PASS, ValidationStatus.NOT_APPLICABLE) else
                                    (None if sensitivity_evidence.reason is None else sensitivity_evidence.reason.value),
                                    policy, sensitivity_evidence.fingerprint,
                                    applicable=status is not ValidationStatus.NOT_APPLICABLE)

        gates = (provenance, complete, sample, mc1, mc2, sensitivity)
        statuses = tuple(value.status for value in gates if value.applicable)
        if ValidationStatus.INVALID in statuses:
            overall = ValidationStatus.INVALID
        elif ValidationStatus.INSUFFICIENT_DATA in statuses:
            overall = ValidationStatus.INSUFFICIENT_DATA
        elif ValidationStatus.FAIL in statuses:
            overall = ValidationStatus.FAIL
        else:
            overall = ValidationStatus.PASS
        blockers = tuple(reason for gate in gates for reason in gate.reason_codes
                         if gate.status in (ValidationStatus.INVALID, ValidationStatus.INSUFFICIENT_DATA, ValidationStatus.FAIL))
        return PromotionDecisionEvidence(policy.fingerprint, manifest.manifest_fingerprint,
                                         primary_validation_scope, instrument,
                                         source or CanonicalCodec.fingerprint("algofortis-promotion-empty-instrument-scope/v1", (("instrument", _instrument_fields(instrument)),)),
                                         aggregate_identity if isinstance(aggregate_identity, str) and aggregate_identity else "PROMOTION_INVALID_AGGREGATE",
                                         source, gates, blockers, overall, overall is ValidationStatus.PASS)


class ValidationEngine:
    """Pure Slice 11 aggregator.  Prior slices remain evidence authorities."""

    @staticmethod
    def scoped_result_identity(
        evidence: ValidationRunEvidence,
        canonical_trades: Iterable[OOSTradeEvidence],
        gates: Iterable[ValidationGateResult] = (),
    ) -> ScopedValidationResultIdentity:
        """Select only exact v2 regime evidence after canonical OOS construction."""
        values = tuple(canonical_trades)
        gate_values = tuple(gates)
        if not evidence.regime_evidence_required:
            return ScopedValidationResultIdentity(values, (), gate_values)
        if evidence.schema_version != "ValidationRunEvidence/v2" or evidence.regime_evidence is None:
            return ScopedValidationResultIdentity(values, (), gate_values)
        selected: list[EntryRegimeSnapshot] = []
        for trade in values:
            if trade.schema_version != "OOSTradeEvidence/v2":
                raise ValueError("regime-aware canonical OOS trade requires v2 provenance")
            matches = tuple(snapshot for snapshot in evidence.regime_evidence.snapshots if (
                snapshot.schema_version == "EntryRegimeSnapshot/v2"
                and snapshot.entry_event_key == trade.opening_entry_event_key
                and snapshot.account_id == trade.account_id == evidence.account_id
                and snapshot.entry_event_key.run_id == evidence.source_run_id
            ))
            if len(matches) > 1:
                raise ValueError("ambiguous applicable entry regime snapshot")
            if len(matches) == 1:
                selected.append(matches[0])
        return ScopedValidationResultIdentity(values, tuple(selected), gate_values)

    @staticmethod
    def evaluate(evidence: ValidationRunEvidence, windows: Iterable[ValidationWindow], trades: Iterable[OOSTradeEvidence], gates: Iterable[ValidationGateResult], *, bootstrap: RandomizedResult | None = None) -> tuple[ValidationStatus, tuple[OOSTradeEvidence, ...], tuple[ValidationGateResult, ...]]:
        if not isinstance(evidence, ValidationRunEvidence): raise TypeError("evidence must be ValidationRunEvidence")
        planned = WalkForwardPlanner.validate_purpose(windows, evidence.purpose)
        for window in planned: evidence.parameter_plan.assert_frozen_before(window.oos_start)
        canonical = CanonicalPrimaryOOS.build(
            evidence.purpose,
            trades,
            windows=planned,
            universe=evidence.universe,
            parameter_plan=evidence.parameter_plan,
            configuration_fingerprint=evidence.configuration_fingerprint,
            validation_identity=evidence.validation_identity,
        )
        gate_values = tuple(gates)
        if not all(isinstance(value, ValidationGateResult) for value in gate_values): raise TypeError("gates must contain ValidationGateResult")
        primary_statuses = [value.primary_status for value in evidence.universe]
        scoped = ValidationEngine.scoped_result_identity(evidence, canonical, gate_values)
        if evidence.regime_evidence_required:
            if evidence.regime_evidence is None or len(scoped.applicable_snapshots) != len(canonical):
                primary_statuses.append(ValidationStatus.INSUFFICIENT_DATA)
        if evidence.purpose is ValidationPurpose.PROMOTION:
            primary_statuses.append(ValidationStatistics.primary_sample_status(canonical, bootstrap))
        currencies = {value.currency for value in evidence.universe}
        if len(currencies) > 1:
            if evidence.fx_policy_fingerprint is None or evidence.fx_evidence is None:
                primary_statuses.append(ValidationStatus.INSUFFICIENT_DATA)
            else:
                primary_statuses.append(evidence.fx_evidence.status)
        return combine_statuses((*primary_statuses, *(value.status for value in gate_values))), canonical, gate_values
