"""One-window, training-only walk-forward selection and OOS evidence boundary.

This module deliberately orchestrates existing authorities.  Candidate run
factories own fresh runtime construction; ``MetricsCalculator`` remains the
sole metric authority and ``CanonicalPrimaryOOS`` remains the sole promotion
OOS authority.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta
from decimal import Decimal, localcontext
from enum import Enum
from itertools import product
from typing import Callable, Iterable, Protocol

from engine.costs import CostAssessment
from engine.backtest.historical_run import HistoricalRunInput
from engine.market import BoundBarEvent, MarketDataCoordinator
from engine.backtest.metrics import MetricStatus, MetricSummary
from engine.portfolio.model import INTERNAL_DECIMAL_CONTEXT
from engine.reproducibility import CanonicalCodec, ReproducibilityManifest, StructuredFailureResult
from engine.trades import TradeRecord
from engine.backtest.validation import (
    CanonicalPrimaryOOS,
    OOSTradeEvidence,
    ParameterMode,
    ParameterPlan,
    ParameterSelectionEvidence,
    SelectedParameterConfiguration,
    SelectedTrainingBaselineEvidence,
    SensitivityEvidence,
    SensitivityParameterValue,
    SensitivityPoint,
    SensitivityPointEvidence,
    SensitivityPointStatus,
    SensitivityPolicy,
    SensitivityReason,
    SelectionPolicy,
    ValidationPurpose,
    ValidationRunEvidence,
    ValidationStatus,
    ValidationWindow,
    WalkForwardPlanner,
)


class WalkForwardFailureCode(str, Enum):
    WALK_FORWARD_NO_VALID_CANDIDATE = "WALK_FORWARD_NO_VALID_CANDIDATE"


class WalkForwardFailureStage(str, Enum):
    CANDIDATE_SELECTION = "CANDIDATE_SELECTION"


class CandidateIneligibilityReason(str, Enum):
    ZERO_COMPLETED_TRADES = "ZERO_COMPLETED_TRADES"
    PRIMARY_METRIC_UNDEFINED = "PRIMARY_METRIC_UNDEFINED"
    NON_FINITE_SELECTION_METRIC = "NON_FINITE_SELECTION_METRIC"
    MISSING_REQUIRED_TRAINING_EVIDENCE = "MISSING_REQUIRED_TRAINING_EVIDENCE"


class MultiWindowWalkForwardStatus(str, Enum):
    COMPLETE_ELIGIBLE_WINDOWS = "COMPLETE_ELIGIBLE_WINDOWS"
    MULTI_WINDOW_INSUFFICIENT_COMPLETE_WINDOWS = "MULTI_WINDOW_INSUFFICIENT_COMPLETE_WINDOWS"


class MultiWindowClassification(str, Enum):
    EVIDENCE_COMPLETE = "EVIDENCE_COMPLETE"
    INSUFFICIENT_DATA_NON_PROMOTABLE = "INSUFFICIENT_DATA_NON_PROMOTABLE"


class WalkForwardRun(Protocol):
    """Fresh configured runtime boundary created separately for every call."""

    def run(
        self,
        historical_input: HistoricalRunInput,
        events: tuple[BoundBarEvent, ...],
    ) -> "WalkForwardRunResult": ...


class ParameterizedRunFactory(Protocol):
    def __call__(self, configuration: SelectedParameterConfiguration) -> WalkForwardRun: ...


@dataclass(frozen=True)
class WalkForwardRunResult:
    """Upstream run evidence; metrics must already come from MetricsCalculator."""

    completed_trades: tuple[TradeRecord, ...]
    cost_assessments: tuple[CostAssessment, ...] = ()
    training_metrics: MetricSummary | None = None

    def __post_init__(self) -> None:
        trades = tuple(self.completed_trades)
        costs = tuple(self.cost_assessments)
        if not all(isinstance(value, TradeRecord) for value in trades):
            raise TypeError("completed_trades must contain TradeRecord values")
        if not all(isinstance(value, CostAssessment) for value in costs):
            raise TypeError("cost_assessments must contain CostAssessment values")
        if self.training_metrics is not None and not isinstance(self.training_metrics, MetricSummary):
            raise TypeError("training_metrics must be a MetricSummary")
        object.__setattr__(self, "completed_trades", tuple(sorted(trades, key=lambda value: value.trade_id)))
        object.__setattr__(self, "cost_assessments", tuple(sorted(costs, key=lambda value: value.assessment_id)))


@dataclass(frozen=True)
class WalkForwardCandidate:
    candidate_fingerprint: str
    create_run: Callable[[], WalkForwardRun]
    selected_parameter_configuration: SelectedParameterConfiguration | None = None
    parameterized_create_run: ParameterizedRunFactory | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_fingerprint, str) or not self.candidate_fingerprint.strip():
            raise ValueError("candidate_fingerprint must be non-empty")
        if not callable(self.create_run):
            raise TypeError("create_run must be callable")
        object.__setattr__(self, "candidate_fingerprint", self.candidate_fingerprint.strip())
        if self.selected_parameter_configuration is not None:
            if not isinstance(self.selected_parameter_configuration, SelectedParameterConfiguration):
                raise TypeError("selected_parameter_configuration must be SelectedParameterConfiguration")
            if self.selected_parameter_configuration.selected_candidate_fingerprint != self.candidate_fingerprint:
                raise ValueError("selected parameter configuration must bind candidate fingerprint")
        if self.parameterized_create_run is not None and not callable(self.parameterized_create_run):
            raise TypeError("parameterized_create_run must be callable")


@dataclass(frozen=True)
class WalkForwardWindowResult:
    window: ValidationWindow
    parameter_plan: ParameterPlan
    selection_evidence: ParameterSelectionEvidence
    validation_evidence: ValidationRunEvidence
    canonical_oos_trades: tuple[OOSTradeEvidence, ...]
    training_events: tuple[BoundBarEvent, ...]
    oos_events: tuple[BoundBarEvent, ...]
    selected_parameter_configuration: SelectedParameterConfiguration | None = None
    selected_training_baseline: SelectedTrainingBaselineEvidence | None = None
    parameterized_create_run: ParameterizedRunFactory | None = None

    @property
    def result_identity(self) -> str:
        """D4 identity for an already-computed successful single-window result."""
        return CanonicalCodec.fingerprint(
            "sentinelx-walk-forward-window-result/v1",
            (("window", WalkForwardWindowExecutor._window_identity(self.window)),
             ("parameter_plan", _parameter_plan_identity(self.parameter_plan)),
             ("selection", _selection_identity(self.selection_evidence)),
             ("validation", self.validation_evidence.validation_identity),
             ("canonical_oos", tuple(value.fingerprint for value in self.canonical_oos_trades))),
        )


@dataclass(frozen=True)
class MultiWindowSelectionEntry:
    """One successful window's existing selection authority, without flattening it."""

    window: ValidationWindow
    parameter_plan: ParameterPlan
    selection_evidence: ParameterSelectionEvidence
    training_evidence_identity: str
    validation_identity: str

    def __post_init__(self) -> None:
        if not isinstance(self.window, ValidationWindow) or not isinstance(self.parameter_plan, ParameterPlan):
            raise TypeError("window and parameter_plan are required")
        if not isinstance(self.selection_evidence, ParameterSelectionEvidence):
            raise TypeError("selection_evidence is required")
        if self.parameter_plan.selection_evidence != self.selection_evidence:
            raise ValueError("selection evidence must match its frozen parameter plan")
        if self.selection_evidence.candidate_fingerprint != self.parameter_plan.parameter_fingerprint:
            raise ValueError("selection evidence must bind the selected parameter fingerprint")
        for name in ("training_evidence_identity", "validation_identity"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")
            object.__setattr__(self, name, value.strip())
        if self.training_evidence_identity != self.selection_evidence.training_evidence_fingerprint:
            raise ValueError("training evidence identity must match selection provenance")

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "sentinelx-multi-window-selection-entry/v1",
            (("window", WalkForwardWindowExecutor._window_identity(self.window)),
             ("parameter_plan", _parameter_plan_identity(self.parameter_plan)),
             ("selection", _selection_identity(self.selection_evidence)),
             ("training_evidence", self.training_evidence_identity),
             ("validation", self.validation_identity)),
        )


@dataclass(frozen=True)
class MultiWindowSelectionIdentity:
    """Versioned canonical collection of independent per-window selections."""

    entries: tuple[MultiWindowSelectionEntry, ...]
    version: str = "MultiWindowSelectionIdentity/v1"

    def __post_init__(self) -> None:
        if self.version != "MultiWindowSelectionIdentity/v1":
            raise ValueError("unsupported multi-window selection identity version")
        values = tuple(self.entries)
        if not all(isinstance(value, MultiWindowSelectionEntry) for value in values):
            raise TypeError("entries must contain MultiWindowSelectionEntry values")
        ordered = tuple(sorted(values, key=lambda value: (value.window.oos_start, value.window.window_id)))
        if len({value.window.window_id for value in ordered}) != len(ordered):
            raise ValueError("multi-window selection identity requires unique window IDs")
        object.__setattr__(self, "entries", ordered)

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "sentinelx-multi-window-selection-identity/v1",
            (("version", self.version), ("entries", tuple(value.fingerprint for value in self.entries))),
        )


@dataclass(frozen=True)
class FailedWalkForwardWindow:
    window: ValidationWindow
    failure: StructuredFailureResult

    def __post_init__(self) -> None:
        if not isinstance(self.window, ValidationWindow) or not isinstance(self.failure, StructuredFailureResult):
            raise TypeError("window and failure are required")


@dataclass(frozen=True)
class MultiWindowWalkForwardResult:
    """Immutable Step-3B aggregate; it is not a promotion-gate result."""

    historical_data_fingerprint: str
    manifest_fingerprint: str
    schedule: tuple[ValidationWindow, ...]
    successful_windows: tuple[WalkForwardWindowResult, ...]
    failed_windows: tuple[FailedWalkForwardWindow, ...]
    selection_identity: MultiWindowSelectionIdentity
    canonical_oos_trades: tuple[OOSTradeEvidence, ...]
    required_complete_windows: int
    achieved_complete_windows: int
    status: MultiWindowWalkForwardStatus
    classification: MultiWindowClassification
    policy_identity: str

    def __post_init__(self) -> None:
        for name in ("historical_data_fingerprint", "manifest_fingerprint", "policy_identity"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")
            object.__setattr__(self, name, value.strip())
        schedule = tuple(self.schedule)
        if not schedule or not all(isinstance(value, ValidationWindow) for value in schedule):
            raise ValueError("schedule must contain ValidationWindow values")
        ordered_schedule = tuple(sorted(schedule, key=lambda value: (value.oos_start, value.window_id)))
        if schedule != ordered_schedule or len({value.window_id for value in schedule}) != len(schedule):
            raise ValueError("schedule must be canonically ordered with unique window IDs")
        successes = tuple(self.successful_windows)
        failures = tuple(self.failed_windows)
        if not all(isinstance(value, WalkForwardWindowResult) for value in successes) or not all(isinstance(value, FailedWalkForwardWindow) for value in failures):
            raise TypeError("window outcomes are invalid")
        ordered_successes = tuple(sorted(successes, key=lambda value: (value.window.oos_start, value.window.window_id)))
        ordered_failures = tuple(sorted(failures, key=lambda value: (value.window.oos_start, value.window.window_id)))
        outcome_ids = [value.window.window_id for value in ordered_successes] + [value.window.window_id for value in ordered_failures]
        if len(outcome_ids) != len(set(outcome_ids)) or set(outcome_ids) != {value.window_id for value in schedule}:
            raise ValueError("every scheduled window requires exactly one outcome")
        schedule_by_id = {value.window_id: value for value in schedule}
        if any(schedule_by_id[value.window.window_id] != value.window for value in (*ordered_successes, *ordered_failures)):
            raise ValueError("window outcome contradicts the authoritative schedule identity")
        if not isinstance(self.selection_identity, MultiWindowSelectionIdentity):
            raise TypeError("selection_identity must be MultiWindowSelectionIdentity")
        if tuple(entry.window.window_id for entry in self.selection_identity.entries) != tuple(value.window.window_id for value in ordered_successes):
            raise ValueError("selection identity must bind exactly the successful windows")
        values = tuple(self.canonical_oos_trades)
        if not all(isinstance(value, OOSTradeEvidence) for value in values):
            raise TypeError("canonical_oos_trades must contain OOSTradeEvidence")
        if not isinstance(self.required_complete_windows, int) or isinstance(self.required_complete_windows, bool) or self.required_complete_windows <= 0:
            raise ValueError("required_complete_windows must be a positive integer")
        if self.achieved_complete_windows != len(ordered_successes):
            raise ValueError("achieved complete window count must equal successful window count")
        status = MultiWindowWalkForwardStatus(self.status)
        classification = MultiWindowClassification(self.classification)
        expected_insufficient = self.achieved_complete_windows < self.required_complete_windows
        if expected_insufficient != (status is MultiWindowWalkForwardStatus.MULTI_WINDOW_INSUFFICIENT_COMPLETE_WINDOWS):
            raise ValueError("aggregate status conflicts with complete-window requirement")
        if expected_insufficient != (classification is MultiWindowClassification.INSUFFICIENT_DATA_NON_PROMOTABLE):
            raise ValueError("aggregate classification conflicts with complete-window requirement")
        object.__setattr__(self, "schedule", ordered_schedule)
        object.__setattr__(self, "successful_windows", ordered_successes)
        object.__setattr__(self, "failed_windows", ordered_failures)
        object.__setattr__(self, "canonical_oos_trades", values)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "classification", classification)

    @property
    def aggregate_identity(self) -> str:
        return CanonicalCodec.fingerprint(
            "sentinelx-multi-window-walk-forward-result/v1",
            (("historical_data", self.historical_data_fingerprint), ("manifest", self.manifest_fingerprint),
             ("schedule", tuple(WalkForwardWindowExecutor._window_identity(value) for value in self.schedule)),
             ("selection", self.selection_identity.fingerprint),
             ("successes", tuple(value.result_identity for value in self.successful_windows)),
             ("failures", tuple((value.window.window_id, value.failure.failure_result_fingerprint) for value in self.failed_windows)),
             ("canonical_oos", tuple(value.fingerprint for value in self.canonical_oos_trades)),
             ("required_complete_windows", self.required_complete_windows),
             ("achieved_complete_windows", self.achieved_complete_windows),
             ("status", self.status), ("classification", self.classification), ("policy", self.policy_identity)),
        )


@dataclass(frozen=True)
class _CandidateEvaluation:
    candidate: WalkForwardCandidate
    metrics: MetricSummary | None
    reason: CandidateIneligibilityReason | None
    expectancy: Decimal | None
    max_drawdown: Decimal | None


def _selection_identity(value: ParameterSelectionEvidence) -> str:
    return CanonicalCodec.fingerprint(
        "sentinelx-parameter-selection-evidence/v1",
        (("candidate", value.candidate_fingerprint),
         ("training_evidence", value.training_evidence_fingerprint),
         ("selected_before_oos", value.selected_before_oos)),
    )


def _parameter_plan_identity(value: ParameterPlan) -> str:
    return CanonicalCodec.fingerprint(
        "sentinelx-parameter-plan/v1",
        (("mode", value.mode), ("parameter", value.parameter_fingerprint),
         ("selection_policy", value.selection_policy),
         ("candidates", value.candidate_fingerprints),
         ("selection", None if value.selection_evidence is None else _selection_identity(value.selection_evidence))),
    )


class WalkForwardWindowExecutor:
    """Execute one validation window with isolated training and OOS runs."""

    POLICY_ID = "WalkForwardSelectionPolicy/v1:MAXIMIZE_TRAINING_METRIC"

    def execute(
        self,
        historical_input: HistoricalRunInput,
        window: ValidationWindow,
        candidates: tuple[WalkForwardCandidate, ...],
        manifest: ReproducibilityManifest,
        validation_evidence: ValidationRunEvidence,
        *,
        _used_runners: list[object] | None = None,
    ) -> WalkForwardWindowResult | StructuredFailureResult:
        if not isinstance(historical_input, HistoricalRunInput) or not isinstance(window, ValidationWindow):
            raise TypeError("historical_input and window are required")
        if not isinstance(manifest, ReproducibilityManifest) or not isinstance(validation_evidence, ValidationRunEvidence):
            raise TypeError("manifest and validation_evidence are required")
        values = tuple(candidates)
        if not values or not all(isinstance(value, WalkForwardCandidate) for value in values):
            raise ValueError("candidates must contain at least one WalkForwardCandidate")
        ordered = tuple(sorted(values, key=lambda value: value.candidate_fingerprint))
        if len({value.candidate_fingerprint for value in ordered}) != len(ordered):
            raise ValueError("duplicate candidate fingerprints are ambiguous")
        if validation_evidence.purpose is not ValidationPurpose.PROMOTION:
            raise ValueError("one-window executor requires PROMOTION validation evidence")

        training_events = self._events_for(historical_input, window.train_start, window.train_end)
        oos_events = self._events_for(historical_input, window.oos_start, window.oos_end)
        # The default retains the frozen Step-3A one-window behavior. Step 3B
        # supplies one private scope for the whole schedule to reject a factory
        # that attempts to reuse mutable state across independent windows.
        used_runners = [] if _used_runners is None else _used_runners
        if not isinstance(used_runners, list):
            raise TypeError("_used_runners must be a private mutable identity scope")
        evaluations = tuple(self._evaluate(candidate, historical_input, training_events, used_runners) for candidate in ordered)
        eligible = tuple(value for value in evaluations if value.reason is None)
        if not eligible:
            return self._failure(manifest, window, evaluations)
        winner = min(eligible, key=lambda value: (-value.expectancy, value.max_drawdown, value.candidate.candidate_fingerprint))
        training_identity = self._training_identity(window, evaluations)
        # This deterministic logical boundary is strictly before OOS, including
        # zero-embargo windows, and never comes from OOS execution.
        selection = ParameterSelectionEvidence(
            winner.candidate.candidate_fingerprint,
            training_identity,
            window.oos_start - timedelta(microseconds=1),
        )
        plan = ParameterPlan(
            ParameterMode.TRAIN_SELECT_THEN_OOS,
            winner.candidate.candidate_fingerprint,
            SelectionPolicy.MAXIMIZE_TRAINING_METRIC,
            tuple(value.candidate.candidate_fingerprint for value in evaluations),
            selection,
        )
        plan.assert_frozen_before(window.oos_start)
        frozen_evidence = replace(validation_evidence, parameter_plan=plan)
        selected_configuration = None
        selected_baseline = None
        if winner.candidate.selected_parameter_configuration is not None:
            selected_configuration = SelectedParameterConfiguration(
                winner.candidate.candidate_fingerprint,
                winner.candidate.selected_parameter_configuration.parameters,
                self._window_identity(window),
                _selection_identity(selection),
            )
            selected_baseline = self._selected_training_baseline(
                window, winner, selected_configuration, selection, training_identity,
            )
        oos_result = self._run(winner.candidate, historical_input, oos_events, used_runners)
        evidence = self._oos_evidence(oos_result, window, frozen_evidence, selection)
        canonical = CanonicalPrimaryOOS.build(
            ValidationPurpose.PROMOTION,
            evidence,
            windows=(window,),
            universe=frozen_evidence.universe,
            parameter_plan=plan,
            configuration_fingerprint=frozen_evidence.configuration_fingerprint,
            validation_identity=frozen_evidence.validation_identity,
        )
        return WalkForwardWindowResult(
            window, plan, selection, frozen_evidence, canonical, training_events, oos_events,
            selected_configuration, selected_baseline, winner.candidate.parameterized_create_run,
        )

    @staticmethod
    def _events_for(input_value: HistoricalRunInput, start, end) -> tuple[BoundBarEvent, ...]:
        return tuple(
            event for event in input_value.events
            if start <= MarketDataCoordinator.availability_time(event) < end
        )

    def _evaluate(self, candidate, input_value, training_events, used_runners) -> _CandidateEvaluation:
        result = self._run(candidate, input_value, training_events, used_runners)
        summary = result.training_metrics
        if summary is None:
            return _CandidateEvaluation(candidate, None, CandidateIneligibilityReason.MISSING_REQUIRED_TRAINING_EVIDENCE, None, None)
        count = summary.metrics.get("trade_count")
        if count is None or count.status is not MetricStatus.VALID or not isinstance(count.value, Decimal):
            return _CandidateEvaluation(candidate, summary, CandidateIneligibilityReason.MISSING_REQUIRED_TRAINING_EVIDENCE, None, None)
        if count.value == 0:
            return _CandidateEvaluation(candidate, summary, CandidateIneligibilityReason.ZERO_COMPLETED_TRADES, None, None)
        expectancy, drawdown = summary.metrics.get("expectancy"), summary.metrics.get("max_drawdown")
        if expectancy is None or drawdown is None or expectancy.status is not MetricStatus.VALID or drawdown.status is not MetricStatus.VALID:
            return _CandidateEvaluation(candidate, summary, CandidateIneligibilityReason.PRIMARY_METRIC_UNDEFINED, None, None)
        if not isinstance(expectancy.value, Decimal) or not isinstance(drawdown.value, Decimal):
            return _CandidateEvaluation(candidate, summary, CandidateIneligibilityReason.MISSING_REQUIRED_TRAINING_EVIDENCE, None, None)
        if not expectancy.value.is_finite() or not drawdown.value.is_finite():
            return _CandidateEvaluation(candidate, summary, CandidateIneligibilityReason.NON_FINITE_SELECTION_METRIC, None, None)
        return _CandidateEvaluation(candidate, summary, None, expectancy.value, drawdown.value)

    @staticmethod
    def _selected_training_baseline(window, winner, configuration, selection, training_identity) -> SelectedTrainingBaselineEvidence:
        summary = winner.metrics
        if summary is None or winner.expectancy is None or winner.max_drawdown is None:
            raise ValueError("selected candidate lacks authoritative training metrics")
        count = summary.metrics.get("trade_count")
        if count is None or count.status is not MetricStatus.VALID or not isinstance(count.value, Decimal):
            raise ValueError("selected candidate lacks authoritative training trade count")
        return SelectedTrainingBaselineEvidence(
            WalkForwardWindowExecutor._window_identity(window), winner.candidate.candidate_fingerprint,
            configuration.configuration_fingerprint, _selection_identity(selection), training_identity,
            summary, count.value, winner.expectancy, winner.max_drawdown,
        )

    @staticmethod
    def _run(candidate, input_value, events, used_runners) -> WalkForwardRunResult:
        runner = candidate.create_run()
        if not callable(getattr(runner, "run", None)):
            raise TypeError("candidate factory must create a fresh WalkForwardRun-compatible boundary")
        if any(runner is prior for prior in used_runners):
            raise ValueError("candidate factory reused mutable run state")
        used_runners.append(runner)
        result = runner.run(input_value, events)
        if not isinstance(result, WalkForwardRunResult):
            raise TypeError("candidate run must return WalkForwardRunResult")
        return result

    def _failure(self, manifest, window, evaluations) -> StructuredFailureResult:
        items = tuple(sorted((
            (value.candidate.candidate_fingerprint, value.reason.value, None if value.metrics is None else value.metrics.evidence_id)
            for value in evaluations
        ), key=lambda value: value[0]))
        evidence = CanonicalCodec.fingerprint(
            "sentinelx-walk-forward-candidate-selection-failure/v1",
            (("window", self._window_identity(window)),
             ("training_window", (window.train_start, window.train_end)),
             ("candidate_universe", tuple(value[0] for value in items)),
             ("ineligible", items), ("selection_policy", self.POLICY_ID)),
        )
        return StructuredFailureResult(
            "structured-failure/v1", manifest.manifest_fingerprint,
            WalkForwardFailureStage.CANDIDATE_SELECTION.value,
            WalkForwardFailureCode.WALK_FORWARD_NO_VALID_CANDIDATE,
            evidence, self.POLICY_ID,
        )

    @staticmethod
    def _training_identity(window, evaluations) -> str:
        return CanonicalCodec.fingerprint(
            "sentinelx-walk-forward-training-evidence/v1",
            (("window", WalkForwardWindowExecutor._window_identity(window)),
             ("candidates", tuple((value.candidate.candidate_fingerprint, None if value.metrics is None else value.metrics.evidence_id, None if value.reason is None else value.reason.value) for value in evaluations))),
        )

    @staticmethod
    def _window_identity(window: ValidationWindow) -> str:
        return CanonicalCodec.fingerprint(
            "sentinelx-validation-window/v1",
            (("window_id", window.window_id), ("train_start", window.train_start), ("train_end", window.train_end),
             ("embargo_start", window.embargo_start), ("embargo_end", window.embargo_end),
             ("oos_start", window.oos_start), ("oos_end", window.oos_end)),
        )

    @staticmethod
    def _oos_evidence(result, window, evidence, selection) -> tuple[OOSTradeEvidence, ...]:
        costs = {value.trade_id: value for value in result.cost_assessments}
        if len(costs) != len(result.cost_assessments):
            raise ValueError("duplicate completed cost assessment is ambiguous")
        converted = []
        for trade in result.completed_trades:
            assessment = costs.get(trade.trade_id)
            if assessment is None or assessment.trade_record != trade:
                raise ValueError("completed OOS trade requires authoritative completed cost evidence")
            converted.append(OOSTradeEvidence(
                trade.trade_id, trade.instrument_identity, window.window_id, trade.closed_at,
                assessment.net_realized_pnl, trade.currency, "PRIMARY_OOS", evidence.parameter_plan.parameter_fingerprint,
                selection.training_evidence_fingerprint, evidence.configuration_fingerprint,
                evidence.validation_identity, "PRIMARY_OOS", None,
                "OOSTradeEvidence/v2" if evidence.schema_version == "ValidationRunEvidence/v2" else "OOSTradeEvidence/v1",
                trade.opening_event_key if evidence.schema_version == "ValidationRunEvidence/v2" else None,
                trade.account_id if evidence.schema_version == "ValidationRunEvidence/v2" else None,
            ))
        return tuple(converted)


class MultiWindowWalkForwardComposer:
    """Step-3B composition only; Step-3A remains the sole per-window owner."""

    POLICY_ID = "MultiWindowWalkForwardPolicy/v1"

    def __init__(self, executor: WalkForwardWindowExecutor | None = None) -> None:
        if executor is not None and not isinstance(executor, WalkForwardWindowExecutor):
            raise TypeError("executor must be WalkForwardWindowExecutor")
        self._executor = executor or WalkForwardWindowExecutor()

    def execute(
        self,
        historical_input: HistoricalRunInput,
        windows: Iterable[ValidationWindow],
        candidates: tuple[WalkForwardCandidate, ...],
        manifest: ReproducibilityManifest,
        validation_evidence: ValidationRunEvidence,
        *,
        required_complete_windows: int,
    ) -> MultiWindowWalkForwardResult:
        if not isinstance(historical_input, HistoricalRunInput):
            raise TypeError("historical_input must be HistoricalRunInput")
        if not isinstance(manifest, ReproducibilityManifest) or not isinstance(validation_evidence, ValidationRunEvidence):
            raise TypeError("manifest and validation_evidence are required")
        if validation_evidence.purpose is not ValidationPurpose.PROMOTION:
            raise ValueError("multi-window composer requires PROMOTION validation evidence")
        if not isinstance(required_complete_windows, int) or isinstance(required_complete_windows, bool) or required_complete_windows <= 0:
            raise ValueError("required_complete_windows must be a positive integer")
        schedule = self._schedule(windows)
        candidate_values = tuple(candidates)
        if not candidate_values or not all(isinstance(value, WalkForwardCandidate) for value in candidate_values):
            raise ValueError("candidates must contain WalkForwardCandidate values")

        successes: list[WalkForwardWindowResult] = []
        failures: list[FailedWalkForwardWindow] = []
        used_runners: list[object] = []
        for window in schedule:
            outcome = self._executor.execute(
                historical_input, window, candidate_values, manifest, validation_evidence,
                _used_runners=used_runners,
            )
            if isinstance(outcome, StructuredFailureResult):
                failures.append(FailedWalkForwardWindow(window, outcome))
            elif isinstance(outcome, WalkForwardWindowResult):
                if outcome.window != window:
                    raise ValueError("Step-3A result does not bind its requested validation window")
                successes.append(outcome)
            else:
                raise TypeError("Step-3A executor returned an unsupported window outcome")

        entries = tuple(
            MultiWindowSelectionEntry(
                value.window, value.parameter_plan, value.selection_evidence,
                value.selection_evidence.training_evidence_fingerprint,
                value.validation_evidence.validation_identity,
            )
            for value in successes
        )
        selection_identity = MultiWindowSelectionIdentity(entries)
        plans = {value.window.window_id: value.parameter_plan for value in successes}
        identities = {value.window.window_id: value.validation_evidence.validation_identity for value in successes}
        canonical = CanonicalPrimaryOOS.build(
            ValidationPurpose.PROMOTION,
            tuple(trade for value in successes for trade in value.canonical_oos_trades),
            windows=schedule,
            universe=validation_evidence.universe,
            parameter_plans_by_window=plans,
            configuration_fingerprint=validation_evidence.configuration_fingerprint,
            validation_identities_by_window=identities,
        )
        achieved = len(successes)
        insufficient = achieved < required_complete_windows
        return MultiWindowWalkForwardResult(
            historical_input.snapshot.fingerprint,
            manifest.manifest_fingerprint,
            schedule,
            tuple(successes),
            tuple(failures),
            selection_identity,
            canonical,
            required_complete_windows,
            achieved,
            (MultiWindowWalkForwardStatus.MULTI_WINDOW_INSUFFICIENT_COMPLETE_WINDOWS
             if insufficient else MultiWindowWalkForwardStatus.COMPLETE_ELIGIBLE_WINDOWS),
            (MultiWindowClassification.INSUFFICIENT_DATA_NON_PROMOTABLE
             if insufficient else MultiWindowClassification.EVIDENCE_COMPLETE),
            self.POLICY_ID,
        )

    @staticmethod
    def _schedule(windows: Iterable[ValidationWindow]) -> tuple[ValidationWindow, ...]:
        values = tuple(windows)
        if not values or not all(isinstance(value, ValidationWindow) for value in values):
            raise ValueError("windows must contain ValidationWindow values")
        if len({value.window_id for value in values}) != len(values):
            raise ValueError("duplicate validation window identity is invalid")
        # Existing authority rejects overlapping promotion OOS intervals.
        WalkForwardPlanner.validate_purpose(values, ValidationPurpose.PROMOTION)
        return tuple(sorted(values, key=lambda value: (value.oos_start, value.window_id)))


class SensitivityAnalyzer:
    """Step-5 training-only neighbor executor; it never selects or executes OOS."""

    def analyze_window(
        self,
        historical_input: HistoricalRunInput,
        window_result: WalkForwardWindowResult,
        policy: SensitivityPolicy,
        parameterized_create_run: ParameterizedRunFactory | None = None,
        *,
        _used_runners: list[object] | None = None,
    ) -> SensitivityEvidence:
        if not isinstance(historical_input, HistoricalRunInput) or not isinstance(window_result, WalkForwardWindowResult):
            raise TypeError("historical_input and window_result are required")
        if not isinstance(policy, SensitivityPolicy):
            raise TypeError("policy must be SensitivityPolicy")
        used = [] if _used_runners is None else _used_runners
        plan_identity = _parameter_plan_identity(window_result.parameter_plan)
        selection_identity = _selection_identity(window_result.selection_evidence)
        base = window_result.selected_training_baseline
        config = window_result.selected_parameter_configuration
        factory = parameterized_create_run or window_result.parameterized_create_run
        common = dict(window=window_result.window, parameter_plan_identity=plan_identity,
                      selection_identity=selection_identity,
                      selected_configuration_fingerprint=None if config is None else config.configuration_fingerprint,
                      training_identity=window_result.selection_evidence.training_evidence_fingerprint,
                      policy_fingerprint=policy.fingerprint)
        if not policy.domains:
            return SensitivityEvidence(**common, baseline=base, points=(), status=ValidationStatus.NOT_APPLICABLE,
                                       reason=SensitivityReason.NO_APPLICABLE_PARAMETER_DOMAIN,
                                       valid_neighbor_count=0, robust_neighbor_count=0, robust_ratio=None)
        if config is None or base is None or factory is None:
            return SensitivityEvidence(**common, baseline=base, points=(), status=ValidationStatus.INVALID,
                                       reason=SensitivityReason.BASELINE_EVIDENCE_INVALID,
                                       valid_neighbor_count=0, robust_neighbor_count=0, robust_ratio=None)
        if base.window_identity != WalkForwardWindowExecutor._window_identity(window_result.window) or base.selection_identity != selection_identity or base.selected_configuration_fingerprint != config.configuration_fingerprint:
            return SensitivityEvidence(**common, baseline=base, points=(), status=ValidationStatus.INVALID,
                                       reason=SensitivityReason.BASELINE_EVIDENCE_INVALID,
                                       valid_neighbor_count=0, robust_neighbor_count=0, robust_ratio=None)
        if base.expectancy <= 0:
            return SensitivityEvidence(**common, baseline=base, points=(), status=ValidationStatus.NOT_APPLICABLE,
                                       reason=SensitivityReason.BASELINE_NON_POSITIVE,
                                       valid_neighbor_count=0, robust_neighbor_count=0, robust_ratio=None)
        configurations, failure = self._neighbors(config, policy)
        if failure is not None:
            return SensitivityEvidence(**common, baseline=base, points=(), status=ValidationStatus.INVALID,
                                       reason=failure, valid_neighbor_count=0, robust_neighbor_count=0, robust_ratio=None)
        if not configurations:
            return SensitivityEvidence(**common, baseline=base, points=(), status=ValidationStatus.INSUFFICIENT_DATA,
                                       reason=SensitivityReason.NO_VALID_NEIGHBORS,
                                       valid_neighbor_count=0, robust_neighbor_count=0, robust_ratio=None)
        if policy.form.value == "LOCAL_GRID" and len(configurations) > policy.max_evaluated_points:
            return SensitivityEvidence(**common, baseline=base, points=(), status=ValidationStatus.INVALID,
                                       reason=SensitivityReason.GRID_EXCEEDS_POLICY_LIMIT,
                                       valid_neighbor_count=0, robust_neighbor_count=0, robust_ratio=None)
        training = WalkForwardWindowExecutor._events_for(historical_input, window_result.window.train_start, window_result.window.train_end)
        points = tuple(self._point(historical_input, training, window_result.window, policy, configuration, factory, used, base) for configuration in configurations)
        valid = tuple(point for point in points if point.status is SensitivityPointStatus.VALID)
        robust = sum(bool(point.robust) for point in valid)
        if len(valid) < policy.minimum_valid_neighbors:
            return SensitivityEvidence(**common, baseline=base, points=points, status=ValidationStatus.INSUFFICIENT_DATA,
                                       reason=SensitivityReason.NO_VALID_NEIGHBORS, valid_neighbor_count=len(valid), robust_neighbor_count=robust, robust_ratio=None)
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            ratio = Decimal(robust) / Decimal(len(valid))
        status = ValidationStatus.PASS if ratio >= policy.minimum_robust_ratio else ValidationStatus.FAIL
        return SensitivityEvidence(**common, baseline=base, points=points, status=status, reason=None,
                                   valid_neighbor_count=len(valid), robust_neighbor_count=robust, robust_ratio=ratio)

    @staticmethod
    def _neighbors(base: SelectedParameterConfiguration, policy: SensitivityPolicy):
        base_by_name = {value.parameter_name: value for value in base.parameters}
        if set(base_by_name) != {domain.parameter_name for domain in policy.domains}:
            return (), SensitivityReason.SELECTED_VALUE_OUTSIDE_DOMAIN
        for domain in policy.domains:
            selected = base_by_name[domain.parameter_name]
            if selected.parameter_type is not domain.parameter_type or selected.value not in domain.values:
                return (), SensitivityReason.SELECTED_VALUE_OUTSIDE_DOMAIN
        generated = []
        if policy.form.value == "COORDINATE":
            for domain in policy.domains:
                for value in domain.values:
                    generated.append(tuple(SensitivityParameterValue(item.parameter_name, item.parameter_type, value if item.parameter_name == domain.parameter_name else item.value) for item in base.parameters))
        else:
            for values in product(*(domain.values for domain in policy.domains)):
                by_name = dict(zip((domain.parameter_name for domain in policy.domains), values))
                generated.append(tuple(SensitivityParameterValue(item.parameter_name, item.parameter_type, by_name[item.parameter_name]) for item in base.parameters))
        configs = {}
        for values in generated:
            candidate = SelectedParameterConfiguration(base.selected_candidate_fingerprint, values, base.window_identity, base.selection_identity)
            if candidate.configuration_fingerprint != base.configuration_fingerprint:
                configs[candidate.configuration_fingerprint] = candidate
        return tuple(sorted(configs.values(), key=lambda value: CanonicalCodec.encode_value(tuple(item.canonical_tuple for item in value.parameters)))), None

    @staticmethod
    def _point(historical_input, training, window, policy, configuration, factory, used, base) -> SensitivityPointEvidence:
        point = SensitivityPoint(WalkForwardWindowExecutor._window_identity(window), policy.fingerprint, configuration)
        runner = factory(configuration)
        if not callable(getattr(runner, "run", None)):
            raise TypeError("parameterized factory must create WalkForwardRun-compatible runner")
        if any(runner is prior for prior in used):
            raise ValueError("parameterized factory reused mutable run state")
        used.append(runner)
        result = runner.run(historical_input, training)
        if isinstance(result, StructuredFailureResult):
            return SensitivityPointEvidence(point, SensitivityPointStatus.FAILED, SensitivityReason.NON_VALID, failure_fingerprint=result.failure_result_fingerprint)
        if not isinstance(result, WalkForwardRunResult) or result.training_metrics is None:
            return SensitivityPointEvidence(point, SensitivityPointStatus.INVALID, SensitivityReason.POINT_METRIC_INVALID)
        summary = result.training_metrics
        count, expectancy, drawdown = (summary.metrics.get(name) for name in ("trade_count", "expectancy", "max_drawdown"))
        if any(value is None or value.status is not MetricStatus.VALID or not isinstance(value.value, Decimal) or not value.value.is_finite() for value in (count, expectancy, drawdown)):
            return SensitivityPointEvidence(point, SensitivityPointStatus.INVALID, SensitivityReason.POINT_METRIC_INVALID)
        if count.value == 0:
            return SensitivityPointEvidence(point, SensitivityPointStatus.INELIGIBLE, SensitivityReason.ZERO_COMPLETED_TRADES, metrics_evidence_id=summary.evidence_id, trade_count=count.value, expectancy=expectancy.value, max_drawdown=drawdown.value)
        robust = expectancy.value > 0 and expectancy.value >= policy.expectancy_ratio * base.expectancy and drawdown.value <= policy.drawdown_ratio * base.max_drawdown
        return SensitivityPointEvidence(point, SensitivityPointStatus.VALID, metrics_evidence_id=summary.evidence_id, trade_count=count.value, expectancy=expectancy.value, max_drawdown=drawdown.value, robust=robust)


class AggregateSensitivityComposer:
    """Pure Step-5 aggregate; no point execution or selection authority."""

    def compose(self, windows: Iterable[ValidationWindow], evidence: Iterable[SensitivityEvidence], policy: SensitivityPolicy):
        from engine.backtest.validation import AggregateSensitivityEvidence
        schedule = tuple(sorted(windows, key=lambda value: (value.oos_start, value.window_id)))
        values = tuple(sorted(evidence, key=lambda value: (value.window.oos_start, value.window.window_id)))
        if any(value.policy_fingerprint != policy.fingerprint for value in values):
            raise ValueError("sensitivity evidence policy mismatch")
        statuses = tuple(value.status for value in values)
        if ValidationStatus.INVALID in statuses:
            status, reason = ValidationStatus.INVALID, None
        elif ValidationStatus.INSUFFICIENT_DATA in statuses:
            status, reason = ValidationStatus.INSUFFICIENT_DATA, None
        else:
            applicable = tuple(value for value in statuses if value is not ValidationStatus.NOT_APPLICABLE)
            if not applicable:
                status, reason = ValidationStatus.NOT_APPLICABLE, SensitivityReason.NO_APPLICABLE_WINDOWS
            elif ValidationStatus.FAIL in applicable:
                status, reason = ValidationStatus.FAIL, None
            else:
                status, reason = ValidationStatus.PASS, None
        return AggregateSensitivityEvidence(schedule, values, policy.fingerprint, status, reason)
