"""P1-07 authoritative composition of completed backtest evidence.

This module deliberately validates and projects evidence; domain computation
remains with orchestration, metrics, validation, costs, and reporting.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Iterable, Mapping, TYPE_CHECKING

from engine.costs import cost_evidence_fingerprint
from engine.backtest.metrics import MetricSummary
from engine.reproducibility import (CanonicalCodec, InvalidFinalizedResult, RandomizedAnalysisCollection,
                                    ResultEvidence, ResultEvidenceFamily, SuccessfulResult,
                                    ValidationEvidenceCollection, successful_result_v2)
from engine.reporting import (INVALID_FINALIZED, RandomizedAnalysisCollectionEvidence, SUCCESS,
                              InvalidFinalizationPayload, ReportProvenance, StructuredBacktestResult,
                              SuccessPayload, success_payload_v2, success_payload_with_cost_evidence)
from engine.reporting.model import REPORT_SCHEMA_VERSION, REPORT_SCHEMA_VERSION_V2, REPORT_SCHEMA_VERSION_V3
from engine.backtest.validation import BootstrapEvidence, PromotionDecisionEvidence, ScopedValidationResultIdentity, ValidationStatus
from engine.backtest.regime import entry_regime_evidence_fingerprint

if TYPE_CHECKING:  # avoids making orchestration depend back on finalization.
    from engine.orchestration.entry_pipeline import OrchestrationResult


VALIDATION_OUTCOME_SCHEMA = "ValidationOutcomeIdentity/v1"
VALIDATION_NOT_APPLICABLE = "VALIDATION_NOT_APPLICABLE"
VALIDATION_APPLICABILITY_POLICY_SCHEMA = "ValidationApplicabilityPolicy/v1"
VALIDATION_APPLICABILITY_DECISION_SCHEMA = "ValidationApplicabilityDecision/v1"


class ValidationOutcomeStatus(str, Enum):
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ValidationApplicabilityMode(str, Enum):
    REQUIRED = "REQUIRED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


def _identity(value: str, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{field} must be a lowercase SHA-256 identity")
    return value


def _text(value: str | None, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty identity reference")
    return value.strip()


@dataclass(frozen=True)
class ValidationApplicabilityPolicy:
    """Explicit §41 Tier-1 semantics; never inferred from a manifest hash."""

    mode: ValidationApplicabilityMode
    schema_version: str = VALIDATION_APPLICABILITY_POLICY_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", ValidationApplicabilityMode(self.mode))
        if self.schema_version != VALIDATION_APPLICABILITY_POLICY_SCHEMA:
            raise ValueError("unsupported validation applicability policy schema")

    @property
    def fingerprint(self) -> str:
        values: tuple[tuple[str, str], ...] = (("mode", self.mode.value),)
        if self.mode is ValidationApplicabilityMode.NOT_APPLICABLE:
            values += (("reason_code", VALIDATION_NOT_APPLICABLE),)
        return CanonicalCodec.fingerprint(self.schema_version, values)


@dataclass(frozen=True)
class ValidationApplicabilityDecision:
    """Policy-produced §40 applicability evidence for one manifest scope."""

    status: ValidationApplicabilityMode
    run_scope_identity: str
    validation_policy_identity: str
    reason_code: str | None = None
    schema_version: str = VALIDATION_APPLICABILITY_DECISION_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", ValidationApplicabilityMode(self.status))
        if self.schema_version != VALIDATION_APPLICABILITY_DECISION_SCHEMA:
            raise ValueError("unsupported validation applicability decision schema")
        object.__setattr__(self, "run_scope_identity", _identity(self.run_scope_identity, "run_scope_identity"))
        object.__setattr__(self, "validation_policy_identity", _identity(
            self.validation_policy_identity, "validation_policy_identity"
        ))
        if self.status is ValidationApplicabilityMode.NOT_APPLICABLE:
            if self.reason_code != VALIDATION_NOT_APPLICABLE:
                raise ValueError("NOT_APPLICABLE decision requires the stable reason code")
        elif self.reason_code is not None:
            raise ValueError("REQUIRED decision cannot carry a not-applicable reason code")

    @property
    def fingerprint(self) -> str:
        values: tuple[tuple[str, str], ...] = (
            ("run_scope", self.run_scope_identity),
            ("validation_policy", self.validation_policy_identity),
            ("status", self.status.value),
        )
        if self.status is ValidationApplicabilityMode.NOT_APPLICABLE:
            values += (("reason_code", self.reason_code),)
        return CanonicalCodec.fingerprint(self.schema_version, values)


class ValidationApplicabilityPolicyProducer:
    """The sole owner of §41 policy-to-decision interpretation."""

    version = "ValidationApplicabilityPolicyProducer/v1"

    @classmethod
    def produce(cls, policy: ValidationApplicabilityPolicy, manifest: object) -> ValidationApplicabilityDecision:
        if not isinstance(policy, ValidationApplicabilityPolicy):
            raise TypeError("policy must be ValidationApplicabilityPolicy/v1")
        manifest_identity = getattr(manifest, "validation_policy_identity", None)
        manifest_scope = getattr(manifest, "manifest_fingerprint", None)
        if policy.fingerprint != manifest_identity:
            raise ValueError("validation applicability policy conflicts with manifest")
        return ValidationApplicabilityDecision(
            policy.mode,
            manifest_scope,
            policy.fingerprint,
            VALIDATION_NOT_APPLICABLE if policy.mode is ValidationApplicabilityMode.NOT_APPLICABLE else None,
        )


@dataclass(frozen=True)
class ValidationOutcomeIdentity:
    """Closed §39 VALIDATION-family outcome; it never computes validation."""

    status: ValidationOutcomeStatus
    scoped_result: ScopedValidationResultIdentity | None = None
    run_scope_identity: str | None = None
    applicability_policy_identity: str | None = None
    reason_code: str | None = None
    schema_version: str = VALIDATION_OUTCOME_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", ValidationOutcomeStatus(self.status))
        if self.schema_version != VALIDATION_OUTCOME_SCHEMA:
            raise ValueError("unsupported validation outcome schema")
        if self.status is ValidationOutcomeStatus.APPLICABLE:
            if not isinstance(self.scoped_result, ScopedValidationResultIdentity):
                raise TypeError("APPLICABLE validation outcome requires ScopedValidationResultIdentity")
            object.__setattr__(self, "run_scope_identity", _identity(self.run_scope_identity, "run_scope_identity"))
            if any(value is not None for value in (self.applicability_policy_identity, self.reason_code)):
                raise ValueError("APPLICABLE validation outcome cannot carry N/A fields")
        else:
            if self.scoped_result is not None:
                raise ValueError("NOT_APPLICABLE validation outcome cannot carry scoped validation evidence")
            object.__setattr__(self, "run_scope_identity", _identity(self.run_scope_identity, "run_scope_identity"))
            # A manifest policy reference is an authoritative policy identifier;
            # the frozen manifest contract does not require it to be a SHA value.
            object.__setattr__(self, "applicability_policy_identity", _text(self.applicability_policy_identity, "applicability_policy_identity"))
            if self.reason_code != VALIDATION_NOT_APPLICABLE:
                raise ValueError("NOT_APPLICABLE validation outcome requires the stable reason code")

    @property
    def fingerprint(self) -> str:
        if self.status is ValidationOutcomeStatus.APPLICABLE:
            return CanonicalCodec.fingerprint(
                VALIDATION_OUTCOME_SCHEMA,
                (("status", self.status.value), ("scoped_validation", self.scoped_result.fingerprint),
                 ("run_scope", self.run_scope_identity)),
            )
        return CanonicalCodec.fingerprint(
            VALIDATION_OUTCOME_SCHEMA,
            (("status", self.status.value), ("run_scope", self.run_scope_identity),
             ("applicability_policy", self.applicability_policy_identity), ("reason_code", self.reason_code)),
        )


@dataclass(frozen=True)
class FinalizationEvidenceBundle:
    """Immutable, typed, non-economic evidence accepted by BacktestFinalizer."""

    metric_summary: MetricSummary
    validation_outcome: ValidationOutcomeIdentity | None
    strategy_identity: Mapping[str, object]
    parameter_identity: str
    report_generated_at: datetime
    provenance: ReportProvenance = ReportProvenance()
    applicability_decision: ValidationApplicabilityDecision | None = None
    bootstrap_evidence: BootstrapEvidence | None = None
    randomized_analysis_collection: RandomizedAnalysisCollection | None = None
    validation_collection: ValidationEvidenceCollection | None = None
    promotion_decision: PromotionDecisionEvidence | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.metric_summary, MetricSummary):
            raise TypeError("metric_summary must be authoritative MetricSummary")
        if self.validation_outcome is not None and not isinstance(self.validation_outcome, ValidationOutcomeIdentity):
            raise TypeError("validation_outcome must be ValidationOutcomeIdentity")
        if (self.validation_outcome is None) == (self.validation_collection is None):
            raise ValueError("finalization requires exactly one legacy validation outcome or validation collection")
        if self.validation_collection is not None and not isinstance(self.validation_collection, ValidationEvidenceCollection):
            raise TypeError("validation_collection must be ValidationEvidenceCollection/v1")
        if self.validation_collection is None and self.promotion_decision is not None:
            raise ValueError("promotion_decision requires collection finalization mode")
        if self.validation_collection is not None and not isinstance(self.promotion_decision, PromotionDecisionEvidence):
            raise TypeError("collection finalization requires typed PromotionDecisionEvidence")
        if not isinstance(self.strategy_identity, Mapping):
            raise TypeError("strategy_identity must be a mapping")
        object.__setattr__(self, "strategy_identity", MappingProxyType(dict(self.strategy_identity)))
        object.__setattr__(self, "parameter_identity", _identity(self.parameter_identity, "parameter_identity"))
        if not isinstance(self.report_generated_at, datetime) or self.report_generated_at.tzinfo is None or self.report_generated_at.utcoffset() is None:
            raise ValueError("report_generated_at must be timezone-aware")
        if not isinstance(self.provenance, ReportProvenance):
            raise TypeError("provenance must be ReportProvenance")
        if self.applicability_decision is not None and not isinstance(
            self.applicability_decision, ValidationApplicabilityDecision
        ):
            raise TypeError("applicability_decision must be ValidationApplicabilityDecision")
        if self.bootstrap_evidence is not None and not isinstance(self.bootstrap_evidence, BootstrapEvidence):
            raise TypeError("bootstrap_evidence must be BootstrapEvidence")
        if self.randomized_analysis_collection is not None and not isinstance(
            self.randomized_analysis_collection, RandomizedAnalysisCollection
        ):
            raise TypeError("randomized_analysis_collection must be RandomizedAnalysisCollection")
        if self.bootstrap_evidence is not None and self.randomized_analysis_collection is not None:
            raise ValueError("direct Bootstrap evidence and randomized collection are contradictory")


EXECUTION_EVIDENCE_SCHEMA_V1 = "sentinelx-execution-evidence/v1"
EXECUTION_EVIDENCE_SCHEMA_V2 = "sentinelx-execution-evidence/v2"


def _execution_identity(result: "OrchestrationResult") -> str:
    values = tuple(sorted((
        (item.action, item.symbol, item.timeframe, item.originating_timestamp,
         item.outcome.value, item.execution_bar_timestamp, item.pre_slippage_price,
         item.fill_price, item.filled_quantity, item.slippage_model_id, item.slippage_amount)
        for item in result.executions
    ), key=lambda item: (CanonicalCodec.timestamp_text(item[3]), item[1], item[2], item[0])))
    return CanonicalCodec.fingerprint(EXECUTION_EVIDENCE_SCHEMA_V1, (("executions", values),))


def _execution_activation_component(item) -> tuple:
    """Explicit closed tagged shape: ('NONE',) or ('PRESENT', ts, price, basis)."""
    activation = getattr(item, "stop_limit_activation", None)
    if activation is None:
        return ("NONE",)
    return (
        "PRESENT",
        activation.activation_bar_timestamp,
        activation.activation_price,
        activation.activation_basis.value,
    )


def _execution_identity_v2(result: "OrchestrationResult") -> str:
    """sentinelx-execution-evidence/v2 — activation-aware binding.

    Preserves every v1-bound field in the same order and appends an explicit
    activation component for every execution.  Historical v1 fingerprints
    remain byte-stable because _execution_identity is untouched.
    """
    values = tuple(sorted((
        (item.action, item.symbol, item.timeframe, item.originating_timestamp,
         item.outcome.value, item.execution_bar_timestamp, item.pre_slippage_price,
         item.fill_price, item.filled_quantity, item.slippage_model_id, item.slippage_amount,
         _execution_activation_component(item))
        for item in result.executions
    ), key=lambda item: (CanonicalCodec.timestamp_text(item[3]), item[1], item[2], item[0])))
    return CanonicalCodec.fingerprint(EXECUTION_EVIDENCE_SCHEMA_V2, (("executions", values),))


def _execution_evidence_identity(result: "OrchestrationResult") -> str:
    """Owner-approved O5 collection-level schema router.

    Evidence-shape routing, NOT historical-run detection.
    ANY activation evidence in the collection → entire collection uses v2.
    ZERO activation evidence → collection uses v1 (frozen byte-stable).
    """
    if any(getattr(item, "stop_limit_activation", None) is not None for item in result.executions):
        return _execution_identity_v2(result)
    return _execution_identity(result)


def _accounting_identity(result: "OrchestrationResult") -> str:
    values = tuple(sorted((
        (item.outcome.value, item.prior_snapshot.account_id, item.prior_snapshot.currency,
         item.prior_snapshot.cash, item.prior_snapshot.equity,
         item.resulting_snapshot.cash, item.resulting_snapshot.equity)
        for item in result.accounting
    ), key=lambda item: (item[1], item[0], str(item[2]))))
    return CanonicalCodec.fingerprint("sentinelx-accounting-evidence/v1", (("accounting", values),))


def _trade_identity(result: "OrchestrationResult") -> str:
    values = tuple(sorted((item.trade_id, item.account_id, item.opening_event_key.run_id,
                           item.opening_event_key.accounting_sequence, item.closing_event_key.accounting_sequence)
                          for item in result.trades))
    return CanonicalCodec.fingerprint("sentinelx-trade-ledger-evidence/v1", (("trades", values),))


def _reconciliation(result: "OrchestrationResult") -> dict[str, int]:
    values = {"TRENDING": 0, "SIDEWAYS": 0, "VOLATILE": 0, "UNCLASSIFIED_WARMUP": 0}
    for item in result.entry_regimes:
        values[item.regime_status.value] += 1
    return values


def _validation_evidence_identity(
    outcome: ValidationOutcomeIdentity,
    decision: ValidationApplicabilityDecision | None,
) -> str:
    """Bind new §41 policy causality without changing the legacy outcome path."""
    if decision is None:
        return outcome.fingerprint
    return CanonicalCodec.fingerprint(
        "ValidationOutcomeApplicabilityBinding/v1",
        (("outcome", outcome.fingerprint), ("decision", decision.fingerprint)),
    )


def _promotion_gate_projection(decision: PromotionDecisionEvidence) -> tuple[dict[str, object], ...]:
    """Project already-established gate evidence; never evaluate a gate here."""
    return tuple({
        "gate_kind": gate.gate_kind.value,
        "status": gate.status.value,
        "reason": ",".join(gate.reason_codes) if gate.reason_codes else "NONE",
    } for gate in decision.gate_results)


class BacktestFinalizer:
    """The sole P1-07 authoritative SUCCESS result/report producer."""

    version = "BacktestFinalizer/v1"

    @classmethod
    def finalize(cls, result: "OrchestrationResult", bundle: FinalizationEvidenceBundle) -> tuple[SuccessfulResult | InvalidFinalizedResult, StructuredBacktestResult]:
        # Duck typing prevents an orchestration -> finalization import cycle while
        # retaining strict ownership of the actual produced result evidence.
        required = ("manifest", "executions", "accounting", "trades", "leg_costs", "costs", "entry_regimes", "regime_enabled", "final_snapshot")
        if any(not hasattr(result, name) for name in required):
            raise TypeError("result must be an authoritative OrchestrationResult")
        if not isinstance(bundle, FinalizationEvidenceBundle):
            raise TypeError("bundle must be FinalizationEvidenceBundle")
        manifest = result.manifest
        collection = bundle.validation_collection
        if collection is not None:
            outcome_entry, promotion_entry = collection.entries
            promotion = bundle.promotion_decision
            if promotion_entry.evidence_result_fingerprint != promotion.result_fingerprint:
                raise ValueError("collection promotion entry conflicts with supplied promotion decision")
            if promotion.manifest_fingerprint != manifest.manifest_fingerprint:
                raise ValueError("promotion decision belongs to a foreign manifest")
            if outcome_entry.scope_identity != manifest.manifest_fingerprint:
                raise ValueError("validation outcome collection scope conflicts with manifest")
            if promotion_entry.scope_identity != promotion.validation_scope_identity:
                raise ValueError("promotion collection scope conflicts with promotion decision")
            validation_identity = collection.fingerprint
        elif bundle.validation_outcome.run_scope_identity != manifest.manifest_fingerprint:
            raise ValueError("validation outcome belongs to a foreign run scope")
        decision = bundle.applicability_decision
        if collection is None and decision is None:
            # Frozen legacy callers remain explicit about their outcome and are
            # never silently assigned an applicability mode.
            if bundle.validation_outcome.status is ValidationOutcomeStatus.NOT_APPLICABLE:
                if bundle.validation_outcome.applicability_policy_identity != manifest.validation_policy_identity:
                    raise ValueError("N/A validation outcome policy conflicts with manifest")
        elif collection is None:
            if decision.run_scope_identity != manifest.manifest_fingerprint:
                raise ValueError("validation applicability decision belongs to a foreign run scope")
            if decision.validation_policy_identity != manifest.validation_policy_identity:
                raise ValueError("validation applicability decision policy conflicts with manifest")
            if decision.status is ValidationApplicabilityMode.REQUIRED:
                if bundle.validation_outcome.status is not ValidationOutcomeStatus.APPLICABLE:
                    raise ValueError("REQUIRED validation applicability requires APPLICABLE validation outcome")
            elif bundle.validation_outcome.status is not ValidationOutcomeStatus.NOT_APPLICABLE:
                raise ValueError("NOT_APPLICABLE validation applicability rejects APPLICABLE validation outcome")
            elif bundle.validation_outcome.applicability_policy_identity != decision.validation_policy_identity:
                raise ValueError("N/A validation outcome policy conflicts with applicability decision")
        if result.trades and (not result.executions or not result.accounting):
            raise ValueError("completed trades require execution and accounting evidence")
        if result.regime_enabled and not manifest.version.endswith("/v2"):
            raise ValueError("regime-enabled finalization requires manifest/v2")
        if result.regime_enabled and not result.entry_regimes and result.trades:
            raise ValueError("regime-enabled trade finalization requires entry regime evidence")
        if (result.leg_costs or result.costs) and not cost_evidence_fingerprint(result.leg_costs, result.costs):
            raise ValueError("cost evidence is malformed")

        if collection is None:
            validation_identity = _validation_evidence_identity(bundle.validation_outcome, decision)
        children = (
            ResultEvidence(ResultEvidenceFamily.EXECUTION, _execution_evidence_identity(result)),
            ResultEvidence(ResultEvidenceFamily.PORTFOLIO_ACCOUNTING, _accounting_identity(result)),
            ResultEvidence(ResultEvidenceFamily.TRADE_LEDGER, _trade_identity(result)),
            ResultEvidence(ResultEvidenceFamily.METRICS, bundle.metric_summary.evidence_id),
            ResultEvidence(ResultEvidenceFamily.VALIDATION, validation_identity),
        )
        randomized_collection = bundle.randomized_analysis_collection
        if randomized_collection is not None:
            children += (ResultEvidence(ResultEvidenceFamily.RANDOMIZED_ANALYSIS, randomized_collection.fingerprint),)
        elif bundle.bootstrap_evidence is not None:
            children += (ResultEvidence(
                ResultEvidenceFamily.RANDOMIZED_ANALYSIS,
                bundle.bootstrap_evidence.result_fingerprint,
            ),)
        if result.regime_enabled:
            finalized: SuccessfulResult | InvalidFinalizedResult = successful_result_v2(
                children,
                result.entry_regimes,
                cost_leg_assessments=result.leg_costs,
                completed_cost_assessments=result.costs,
                cost_evidence_required=bool(result.leg_costs or result.costs),
                randomized_analysis_collection=randomized_collection,
            )
        else:
            # Legacy compatibility remains a v1 result.  No regime-enabled
            # run can silently take this branch.
            cost_child = ()
            if result.leg_costs or result.costs:
                cost_child = (ResultEvidence(
                    ResultEvidenceFamily.COST,
                    cost_evidence_fingerprint(result.leg_costs, result.costs),
                ),)
            finalized = SuccessfulResult("result/v1", (*children, *cost_child),
                                         randomized_analysis_collection=randomized_collection)
        if collection is not None:
            finalized = replace(finalized, validation_collection=collection)
        if collection is not None and bundle.promotion_decision.status is ValidationStatus.INVALID:
            established = finalized.evidence
            finalized = InvalidFinalizedResult(
                manifest.manifest_fingerprint,
                collection.fingerprint,
                bundle.promotion_decision.result_fingerprint,
                bundle.promotion_decision.blocker_reasons,
                established,
                randomized_analysis_collection=randomized_collection,
                validation_collection=collection,
            )
            invalid_payload = InvalidFinalizationPayload(
                manifest.manifest_fingerprint,
                finalized.result_fingerprint,
                "INVALID",
                False,
                finalized.invalid_reason_identities,
                bundle.promotion_decision.result_fingerprint,
                collection.fingerprint,
                _promotion_gate_projection(bundle.promotion_decision),
            )
            return finalized, StructuredBacktestResult(
                REPORT_SCHEMA_VERSION_V3, INVALID_FINALIZED, bundle.report_generated_at,
                bundle.provenance, invalid_payload,
            )
        payload = SuccessPayload(
            manifest.manifest_fingerprint,
            finalized.result_fingerprint,
            bundle.strategy_identity,
            bundle.parameter_identity,
            manifest.market_data.fingerprint,
            manifest.configuration.fingerprint,
            validation_identity,
            tuple({"trade_id": item.trade_id, "account_id": item.account_id, "currency": item.currency,
                   "gross_realized_pnl": item.gross_realized_pnl} for item in result.trades),
            tuple({key: value for key, value in (
                ("action", item.action), ("symbol", item.symbol), ("timeframe", item.timeframe),
                ("outcome", item.outcome.value), ("execution_timestamp", item.execution_bar_timestamp),
                ("fill_price", item.fill_price), ("filled_quantity", item.filled_quantity),
            ) if value is not None} for item in result.executions),
            ({"account_id": result.final_snapshot.account_id, "currency": result.final_snapshot.currency,
              "gross_equity": result.final_snapshot.equity},),
            (),
            ({"identity": bundle.metric_summary.evidence_id, "net_basis": bundle.metric_summary.net_basis,
              "regime_reconciliation": dict(bundle.metric_summary.regime_buckets)},),
            {"validation_identity": validation_identity,
             "status": (bundle.validation_outcome.status.value if bundle.validation_outcome is not None else "COLLECTION")},
            {"runtime_identity": manifest.runtime.fingerprint},
        )
        if result.regime_enabled:
            payload = success_payload_v2(payload, result.entry_regimes, _reconciliation(result))
        payload = success_payload_with_cost_evidence(payload, result.leg_costs, result.costs)
        if randomized_collection is not None:
            payload = replace(payload, randomized_analysis=RandomizedAnalysisCollectionEvidence(
                randomized_collection.fingerprint,
                tuple({"analysis_kind": item.analysis_kind, "scope_identity": item.scope_identity,
                       "evidence_schema_version": item.evidence_schema_version,
                       "evidence_result_fingerprint": item.evidence_result_fingerprint}
                      for item in randomized_collection.entries),
            ))
        if collection is not None:
            payload = replace(
                payload,
                promotion_status=bundle.promotion_decision.status.value,
                promotable=bundle.promotion_decision.promotable,
                promotion_gates=_promotion_gate_projection(bundle.promotion_decision),
                promotion_evidence_fingerprint=bundle.promotion_decision.result_fingerprint,
                validation_collection_fingerprint=collection.fingerprint,
            )
        report = StructuredBacktestResult(
            REPORT_SCHEMA_VERSION_V3 if collection is not None else (REPORT_SCHEMA_VERSION_V2 if result.regime_enabled else REPORT_SCHEMA_VERSION),
            SUCCESS,
            bundle.report_generated_at,
            bundle.provenance,
            payload,
        )
        return finalized, report


@dataclass(frozen=True)
class FinalizedBacktestRun:
    """One application-level, serializer-ready completed backtest result."""

    orchestration_result: "OrchestrationResult"
    successful_result: SuccessfulResult | InvalidFinalizedResult
    structured_result: StructuredBacktestResult


class BacktestApplicationCoordinator:
    """The one application seam from an orchestrated run to final output.

    It coordinates pre-produced analysis evidence with the immutable result;
    metrics and validation remain external, authoritative producers.  Future
    CLI/UI/batch callers use this boundary instead of composing result/report
    identities themselves.
    """

    def __init__(
        self,
        orchestrator: object,
        validation_applicability_policy: ValidationApplicabilityPolicy | None = None,
    ) -> None:
        if not callable(getattr(orchestrator, "run", None)):
            raise TypeError("orchestrator must expose the BacktestOrchestrator.run boundary")
        if validation_applicability_policy is not None and not isinstance(
            validation_applicability_policy, ValidationApplicabilityPolicy
        ):
            raise TypeError("validation_applicability_policy must be ValidationApplicabilityPolicy/v1")
        self._orchestrator = orchestrator
        self._validation_applicability_policy = validation_applicability_policy

    def run(
        self,
        events: Iterable[object],
        bundle: FinalizationEvidenceBundle,
    ) -> FinalizedBacktestRun:
        result = self._orchestrator.run(events)
        if getattr(result, "failure", None) is not None:
            raise ValueError("a Category-A orchestration failure cannot become a successful final result")
        if self._validation_applicability_policy is None:
            if bundle.applicability_decision is not None:
                raise ValueError("legacy application coordination cannot accept caller applicability decisions")
        else:
            decision = ValidationApplicabilityPolicyProducer.produce(
                self._validation_applicability_policy, result.manifest
            )
            # The coordinator deliberately replaces, rather than trusts, any
            # caller-provided decision with the sole producer's evidence.
            bundle = replace(bundle, applicability_decision=decision)
        successful, structured = BacktestFinalizer.finalize(result, bundle)
        return FinalizedBacktestRun(result, successful, structured)
