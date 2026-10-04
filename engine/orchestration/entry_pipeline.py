"""Deterministic Slice 14 orchestration over existing AlgoFortis boundaries.

This module deliberately owns coordination only.  It does not recalculate
execution, accounting, costs, metrics, validation, reproducibility, or
reporting truth.  Those concerns remain in their established slice modules.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, replace as dc_replace
from datetime import datetime
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from engine.backtest.engine import BarEvent
from engine.costs import (
    CostAdjustedAccountProjection, CostAssessment, CostCalculator,
    CostLegAssessment, CostSchedule, cost_evidence_fingerprint,
)
from engine.execution import ExecutionEngine, ExecutionOutcome, ExecutionResult
from engine.execution.model import StopLimitActivationEvidence
from engine.market import (
    BoundBarEvent,
    EvaluationRequest,
    MarketDataCoordinator,
    MarketDataView,
    StrategyDataRequirements,
    StreamKey,
    StreamProfileMap,
)
from engine.market.profile import MarketProfile, MarketSessionBoundary, WeekendCalendar
from engine.core.numeric import as_decimal
from engine.orders import (
    ConcreteCloseInstruction, OrderLifecycle, OrderLifecycleState, OrderRequest, OrderType, TimeInForce,
)
from engine.orders.lifecycle import (
    OrderLifecycleCauseType, OrderLifecycleEvent, order_lifecycle_cause_reference,
)
from engine.orders.validity import (
    EntryValidityContext, EntryValidityResult, EntryValiditySpec, EntryValidityOutcome,
    PendingEntryValidityPolicy, entry_validity_binding_fingerprint,
)
from engine.portfolio import (
    AccountSnapshot,
    AccountingOutcome,
    AccountingResult,
    InstrumentIdentity,
    InstrumentSpecification,
    PortfolioAccount,
    PositionKey,
)
from engine.protective.plan import PreEntryProtectivePlan, ProtectivePlanPolicy, materialize_protective_plan
from engine.risk.risk_manager import (
    PendingRiskCommitment,
    PositionDirection,
    RiskDay,
    RiskGate,
    RiskGateResult,
    RiskGateState,
    RiskOutcome,
    SignalPriorityEvidence,
    entry_intent_identity,
    rank_candidates,
)
from engine.reproducibility import (
    CanonicalCodec,
    ReproducibilityManifest,
    ResultEvidence,
    ResultEvidenceFamily,
    StructuredFailureResult,
    SuccessfulResult,
    successful_result_v2,
)
from engine.reporting import SuccessPayload, success_payload_v2, success_payload_with_cost_evidence
from engine.orchestration.signal_intake import SignalIntake, SignalIntakeContext, SignalIntent
from engine.strategy.base import Signal, StrategySignalGenerator
from engine.strategy.exceptions import safe_generate_signal
from engine.trades import LedgerEventKey, TradeLedger, TradeRecord
from engine.protective.runtime import ProtectiveExitBook, ProtectiveExitKind, ProtectiveExitState
from engine.protective.live import LiveProtectiveEvaluator, TrailingRatchetEvidence
from engine.protective.runtime_policy import (
    RuntimeTrailingDecision,
    RuntimeTrailingEvidence,
    StrategyExitDecision,
    StrategyExitEvidence,
    TargetCandidate,
    TargetReplacementEvidence,
)
from engine.persistence.sqlite_store import StrategyStateTransition
from engine.backtest.regime import EntryRegimeSnapshot, REGIME_POLICY_ID, RegimeClassifier, RegimeEvidence, entry_regime_evidence_fingerprint


TEMPORARY_QUANTITY_POLICY_ID = "algofortis-slice14-integration-quantity-policy/v1"


class PriceSource(str, Enum):
    """Policy-owned construction for prices required by non-market orders."""

    NONE = "NONE"
    CONFIGURED = "CONFIGURED"
    SOURCE_OPEN = "SOURCE_OPEN"
    SOURCE_HIGH = "SOURCE_HIGH"
    SOURCE_LOW = "SOURCE_LOW"
    SOURCE_CLOSE = "SOURCE_CLOSE"


class OrchestrationFailureCode(str, Enum):
    """Stable post-manifest deterministic orchestration failures."""

    AMBIGUOUS_CONCURRENT_CAPITAL_COMPETITION = "AMBIGUOUS_CONCURRENT_CAPITAL_COMPETITION"


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _gate_entry_reference(planned_terms: PlannedOrderTerms, source_bar: BarEvent) -> Decimal:
    """Authoritative pre-order entry reference for gate-enabled BUY entries.

    MARKET: completed decision/source bar close.
    LIMIT: the authoritative planned limit price (never blindly ``source.close``).
    STOP: the authoritative planned stop price (Owner Decision O2).
    STOP_LIMIT: the authoritative planned limit price (Owner Decision O2;
    ``planned.stop_price`` is the activation/trigger level only).
    The SAME reference is passed to ``ProtectivePlanPolicy.plan_for(reference_price=...)``
    and to ``RiskGate.evaluate_pre_order(entry_price=...)``; fill prices never
    participate in pre-order R:R eligibility.
    """
    if planned_terms.order_type is OrderType.MARKET:
        return as_decimal(source_bar.close, "source close")
    if planned_terms.order_type is OrderType.LIMIT:
        if planned_terms.limit_price is None:
            raise ValueError("LIMIT planned terms require an authoritative limit price")
        return planned_terms.limit_price
    if planned_terms.order_type is OrderType.STOP:
        if planned_terms.stop_price is None:
            raise ValueError("STOP planned terms require an authoritative stop price")
        return planned_terms.stop_price
    if planned_terms.order_type is OrderType.STOP_LIMIT:
        if planned_terms.limit_price is None:
            raise ValueError("STOP_LIMIT planned terms require an authoritative limit price")
        return planned_terms.limit_price
    raise ValueError("gate-enabled BUY entry supports only MARKET, LIMIT, STOP, and STOP_LIMIT order types")


@dataclass(frozen=True)
class SignalToOrderRule:
    """One policy-owned, metadata-independent actionable translation rule."""

    action: str
    order_type: OrderType
    time_in_force: TimeInForce
    quantity: Decimal | int | float | str
    limit_price_source: PriceSource = PriceSource.NONE
    stop_price_source: PriceSource = PriceSource.NONE
    configured_limit_price: Decimal | int | float | str | None = None
    configured_stop_price: Decimal | int | float | str | None = None

    def __post_init__(self) -> None:
        if self.action not in {"BUY", "SELL", "EXIT"}:
            raise ValueError("rule action must be BUY, SELL, or EXIT")
        if not isinstance(self.order_type, OrderType) or not isinstance(self.time_in_force, TimeInForce):
            raise TypeError("order_type and time_in_force must be frozen order enums")
        quantity = as_decimal(self.quantity, "quantity")
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "limit_price_source", PriceSource(self.limit_price_source))
        object.__setattr__(self, "stop_price_source", PriceSource(self.stop_price_source))
        if self.configured_limit_price is not None:
            value = as_decimal(self.configured_limit_price, "configured_limit_price")
            if value <= 0:
                raise ValueError("configured_limit_price must be positive")
            object.__setattr__(self, "configured_limit_price", value)
        if self.configured_stop_price is not None:
            value = as_decimal(self.configured_stop_price, "configured_stop_price")
            if value <= 0:
                raise ValueError("configured_stop_price must be positive")
            object.__setattr__(self, "configured_stop_price", value)
        required_limit = self.order_type in {OrderType.LIMIT, OrderType.STOP_LIMIT}
        required_stop = self.order_type in {OrderType.STOP, OrderType.STOP_LIMIT}
        if required_limit != (self.limit_price_source is not PriceSource.NONE):
            raise ValueError("limit price source must exactly match order type")
        if required_stop != (self.stop_price_source is not PriceSource.NONE):
            raise ValueError("stop price source must exactly match order type")
        if self.limit_price_source is PriceSource.CONFIGURED and self.configured_limit_price is None:
            raise ValueError("configured limit source requires configured_limit_price")
        if self.stop_price_source is PriceSource.CONFIGURED and self.configured_stop_price is None:
            raise ValueError("configured stop source requires configured_stop_price")


@dataclass(frozen=True)
class PlannedOrderTerms:
    """Quantity-free, already-resolved order terms for pre-gate evaluation.

    Pricing/order terms are resolved EXACTLY ONCE by
    ``SignalToOrderPolicy.planned_terms`` from the authoritative
    ``SignalToOrderRule`` / ``PriceSource``; quantity is deliberately absent
    so the RiskGate-approved quantity remains the sole sizing authority.
    """

    order_type: OrderType
    time_in_force: TimeInForce
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None


@dataclass(frozen=True)
class SignalToOrderPolicy:
    """Versioned Tier-1 Slice 14 policy; Signal.metadata is never consulted."""

    policy_id: str
    version: str
    rules: tuple[SignalToOrderRule, ...]
    quantity_policy_identity: str = TEMPORARY_QUANTITY_POLICY_ID

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _text(self.policy_id, "policy_id"))
        object.__setattr__(self, "version", _text(self.version, "version"))
        if self.quantity_policy_identity != TEMPORARY_QUANTITY_POLICY_ID:
            raise ValueError("Slice 14 must use the locked temporary quantity policy identity")
        rules = tuple(self.rules)
        if not rules or not all(isinstance(rule, SignalToOrderRule) for rule in rules):
            raise ValueError("rules must contain SignalToOrderRule values")
        if len({rule.action for rule in rules}) != len(rules):
            raise ValueError("duplicate signal-to-order action rule is ambiguous")
        object.__setattr__(self, "rules", rules)

    @property
    def tier1_identity(self) -> str:
        """Identity bound to manifest execution semantics and D6 replay."""
        return CanonicalCodec.fingerprint(
            "algofortis-slice14-signal-to-order-policy/v1",
            (
                ("policy_id", self.policy_id),
                ("version", self.version),
                ("quantity_policy", self.quantity_policy_identity),
                ("rules", tuple(
                    (
                        rule.action, rule.order_type.value, rule.time_in_force.value,
                        str(rule.quantity), rule.limit_price_source.value,
                        rule.stop_price_source.value,
                        None if rule.configured_limit_price is None else str(rule.configured_limit_price),
                        None if rule.configured_stop_price is None else str(rule.configured_stop_price),
                    )
                    for rule in sorted(self.rules, key=lambda item: item.action)
                )),
            ),
        )

    def planned_terms(self, intent: SignalIntent, source_bar: BarEvent) -> PlannedOrderTerms:
        """Resolve quantity-free order terms exactly once from the rule authority."""
        if not isinstance(intent, SignalIntent) or not isinstance(source_bar, BarEvent):
            raise TypeError("intent and source_bar are required")
        if intent.symbol.casefold() != source_bar.symbol.casefold() or intent.timeframe != source_bar.timeframe:
            raise ValueError("signal source evidence does not match intent provenance")
        rule = next((item for item in self.rules if item.action == intent.action), None)
        if rule is None:
            raise ValueError("signal-to-order policy has no rule for actionable signal")
        return PlannedOrderTerms(
            order_type=rule.order_type,
            time_in_force=rule.time_in_force,
            limit_price=self._price(rule.limit_price_source, rule.configured_limit_price, source_bar),
            stop_price=self._price(rule.stop_price_source, rule.configured_stop_price, source_bar),
        )

    def order_for(
        self,
        intent: SignalIntent,
        source_bar: BarEvent,
        *,
        quantity: Decimal | int | float | str | None = None,
        planned_terms: PlannedOrderTerms | None = None,
    ) -> OrderRequest:
        """Build an OrderRequest without resolving prices twice.

        When ``planned_terms`` is supplied it is used as-is (the caller
        already resolved prices once for pre-gate evaluation); otherwise
        ``planned_terms`` resolves them here.  ``quantity`` overrides the
        rule quantity (gate-enabled path passes the RiskGate-approved
        quantity); when omitted the legacy ``rule.quantity`` behavior is
        preserved.
        """
        terms = planned_terms if planned_terms is not None else self.planned_terms(intent, source_bar)
        rule = next((item for item in self.rules if item.action == intent.action), None)
        if rule is None:
            raise ValueError("signal-to-order policy has no rule for actionable signal")
        effective_quantity = rule.quantity if quantity is None else as_decimal(quantity, "quantity")
        return OrderRequest.from_intent(
            intent, terms.order_type, effective_quantity, terms.time_in_force,
            limit_price=terms.limit_price,
            stop_price=terms.stop_price,
        )

    @staticmethod
    def _price(source: PriceSource, configured: Decimal | None, bar: BarEvent) -> Decimal | None:
        if source is PriceSource.NONE:
            return None
        if source is PriceSource.CONFIGURED:
            return configured
        return {
            PriceSource.SOURCE_OPEN: bar.open,
            PriceSource.SOURCE_HIGH: bar.high,
            PriceSource.SOURCE_LOW: bar.low,
            PriceSource.SOURCE_CLOSE: bar.close,
        }[source]


@dataclass(frozen=True)
class StrategyBinding:
    """One strategy, its explicit Slice 9 market-data requirements, and the
    optional strategy-owned pending-entry validity capability (Phase-4 Slice 1).

    ``entry_validity_policy=None`` (default) means NO strategy-semantic
    invalidation and NO additional ``EntryValiditySpec`` constraints: the
    pending entry proceeds exactly as before, subject to existing mechanical
    lifecycle (DAY/GTC) and RiskGate rules.  The capability is bound alongside
    the strategy -- ``StrategySignalGenerator/v1`` is never modified.
    """

    strategy: StrategySignalGenerator
    requirements: StrategyDataRequirements
    signal_source_stream: StreamKey | None = None
    entry_validity_policy: PendingEntryValidityPolicy | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.strategy, StrategySignalGenerator):
            raise TypeError("strategy must be a StrategySignalGenerator")
        if not isinstance(self.requirements, StrategyDataRequirements):
            raise TypeError("requirements must be StrategyDataRequirements")
        # ``StrategySignalGenerator.interface_version`` is the frozen
        # generator API contract.  ``StrategyDataRequirements.strategy_version``
        # is the independently versioned semantic owner identity used by live
        # subscriptions, positions, and paper protection.  They deliberately
        # are not required to match.
        if self.entry_validity_policy is not None and not isinstance(self.entry_validity_policy, PendingEntryValidityPolicy):
            raise TypeError("entry_validity_policy must be a PendingEntryValidityPolicy")
        source = self.signal_source_stream
        if source is None:
            triggers = tuple(self.requirements.trigger_streams)
            if len(triggers) != 1:
                raise ValueError("multi-trigger strategy requires explicit signal_source_stream")
            source = triggers[0]
            object.__setattr__(self, "signal_source_stream", source)
        if source not in self.requirements.trigger_streams:
            raise ValueError("signal_source_stream must be a trigger stream")
        strategy_id = getattr(self.strategy, "id", None)
        if strategy_id is not None and strategy_id != self.requirements.strategy_id:
            raise ValueError("strategy object id must match authoritative strategy requirements id")


@dataclass(frozen=True)
class _Rule7StrategyAdapter:
    """Bind the frozen Rule 7 audit identity to orchestration requirements."""

    strategy: StrategySignalGenerator
    id: str
    interface_version: str

    def generate_signal(self, data, state):
        return self.strategy.generate_signal(data, state)


@dataclass(frozen=True)
class PendingEntryAssociation:
    """Orchestration-owned immutable link between a gate-approved pending BUY
    order and its frozen protective plan + approved quantity.

    Created at approval time (before the order fills) and consumed exactly
    once at the accepted fill: the frozen plan is never recomputed after
    fill, and plan evidence never travels through ``Signal.metadata``.
    """

    entry_identity: str
    order: OrderRequest
    source_stream: StreamKey
    frozen_plan: PreEntryProtectivePlan
    approved_quantity: Decimal
    entry_reference: Decimal | None = None
    validity_spec: EntryValiditySpec | None = None
    validity_policy_identity: str | None = None


@dataclass(frozen=True)
class EntryRiskRejectionEvidence:
    """Orchestration-owned entry-scoped link to an authoritative RiskGate rejection.

    ``RiskGateResult`` is generic risk-engine output and deliberately carries
    no entry identity; ``entry_identity`` is owned by the orchestration layer,
    so the exact linkage is created HERE at the evidence layer.  Two distinct
    pending entries rejected with the same reason at the same decision time
    still produce distinct evidence identities because ``entry_identity``
    participates in the canonical fingerprint.  The Q56 lifecycle
    ``cause_reference`` points at this identity instead of a shared
    reason-only synthetic hash.
    """

    entry_identity: str
    decision_timestamp: datetime
    risk_result: RiskGateResult

    def __post_init__(self) -> None:
        if not isinstance(self.entry_identity, str) or not self.entry_identity.strip():
            raise ValueError("entry_identity must be a non-empty string")
        if self.decision_timestamp.tzinfo is None or self.decision_timestamp.utcoffset() is None:
            raise ValueError("decision_timestamp must be timezone-aware")
        if not isinstance(self.risk_result, RiskGateResult):
            raise TypeError("risk_result must be a RiskGateResult")
        if self.risk_result.outcome is RiskOutcome.APPROVED:
            raise ValueError("entry-scoped rejection evidence requires a rejected risk result")
        object.__setattr__(self, "entry_identity", self.entry_identity.strip())

    @property
    def evidence_identity(self) -> str:
        """Canonical deterministic identity binding entry + decision + rejection."""
        return CanonicalCodec.fingerprint(
            "algofortis-entry-risk-rejection/v1",
            (
                ("entry", self.entry_identity),
                ("decision_time", self.decision_timestamp),
                ("outcome", self.risk_result.outcome.value),
                ("reason", self.risk_result.reason),
            ),
        )


@dataclass(frozen=True)
class OrchestrationResult:
    """Immutable evidence produced by the coordinator, not a replacement report."""

    manifest: ReproducibilityManifest
    final_snapshot: AccountSnapshot
    requests: tuple[EvaluationRequest, ...]
    intents: tuple[SignalIntent, ...]
    orders: tuple[OrderRequest, ...]
    executions: tuple[ExecutionResult, ...]
    accounting: tuple[AccountingResult, ...]
    trades: tuple[TradeRecord, ...]
    costs: tuple[CostAssessment, ...]
    leg_costs: tuple[CostLegAssessment, ...] = ()
    regime_evidence: tuple[RegimeEvidence, ...] = ()
    entry_regimes: tuple[EntryRegimeSnapshot, ...] = ()
    regime_enabled: bool = True

    @property
    def regime_evidence_fingerprint(self) -> str:
        """Authoritative v2 result child from persisted entry evidence only."""
        return entry_regime_evidence_fingerprint(self.entry_regimes)

    @property
    def cost_evidence_fingerprint(self) -> str:
        """Canonical outcome-side P1-5 cost identity from produced evidence."""
        return cost_evidence_fingerprint(self.leg_costs, self.costs)

    def successful_result(self, economic_evidence: tuple[ResultEvidence, ...]) -> SuccessfulResult:
        """Legacy compatibility helper, not the authoritative final result route.

        ``BacktestFinalizer/v1`` owns production SUCCESS composition.  This
        retained helper must never be used to create the report/replay result
        because its caller supplies economic child evidence directly.
        """
        if not self.regime_enabled:
            values = tuple(economic_evidence)
            if self.leg_costs or self.costs:
                if any(item.family.value == "COST" for item in values):
                    raise ValueError("supplied COST evidence conflicts with produced cost evidence")
                values = (*values, ResultEvidence(ResultEvidenceFamily.COST, self.cost_evidence_fingerprint))
            return SuccessfulResult("result/v1", values)
        return successful_result_v2(
            economic_evidence,
            self.entry_regimes,
            cost_leg_assessments=self.leg_costs,
            completed_cost_assessments=self.costs,
            cost_evidence_required=bool(self.leg_costs or self.costs),
        )

    def report_payload_v2(self, payload: SuccessPayload, reconciliation: Mapping[str, int]) -> SuccessPayload:
        """Legacy report projection helper; BacktestFinalizer/v1 owns final assembly."""
        return success_payload_with_cost_evidence(
            success_payload_v2(payload, self.entry_regimes, reconciliation),
            self.leg_costs,
            self.costs,
        )
    failure: StructuredFailureResult | None = None
    risk_rejections: tuple[RiskGateResult, ...] = ()
    order_lifecycle: tuple[OrderLifecycleEvent, ...] = ()
    entry_risk_rejections: tuple[EntryRiskRejectionEvidence, ...] = ()
    # B3-R1: authoritative post-run protective state (the per-run runtime
    # book).  Exposes target-replacement/trailing/OCO end state for evidence
    # without leaking the mutable object into result composition semantics.
    protective_book: ProtectiveExitBook | None = None


class BacktestOrchestrator:
    """Minimal deterministic coordinator for the verified Slice 1–13 contracts."""

    def __init__(
        self,
        *,
        bindings: Iterable[StrategyBinding],
        profiles: StreamProfileMap,
        policies: Mapping[str, SignalToOrderPolicy],
        account: PortfolioAccount,
        specifications: Mapping[InstrumentIdentity, InstrumentSpecification],
        manifest: ReproducibilityManifest,
        execution: ExecutionEngine | None = None,
        cost_schedules: Iterable[CostSchedule] = (),
        protective_book: ProtectiveExitBook | None = None,
        regime_enabled: bool = True,
        risk_gate: RiskGate | None = None,
        calendars: Mapping[str, WeekendCalendar] | None = None,
        protective_plan_policies: Mapping[str, ProtectivePlanPolicy] | None = None,
        runtime_trailing_policies: Mapping[tuple[str, str], object] | None = None,
        runtime_target_replacement_policies: Mapping[tuple[str, str], object] | None = None,
        strategy_exit_policies: Mapping[tuple[str, str], object] | None = None,
    ) -> None:
        bindings = tuple(bindings)
        if not bindings or not all(isinstance(value, StrategyBinding) for value in bindings):
            raise ValueError("bindings must contain StrategyBinding values")
        if len({item.requirements.strategy_id for item in bindings}) != len(bindings):
            raise ValueError("duplicate strategy bindings are ambiguous")
        if not isinstance(profiles, StreamProfileMap) or not isinstance(account, PortfolioAccount):
            raise TypeError("profiles and account are required Slice contracts")
        if not isinstance(manifest, ReproducibilityManifest):
            raise TypeError("manifest must be a ReproducibilityManifest")
        policy_values = dict(policies)
        for binding in bindings:
            policy = policy_values.get(binding.requirements.strategy_id)
            if not isinstance(policy, SignalToOrderPolicy):
                raise ValueError("each strategy requires an explicit SignalToOrderPolicy")
            if policy.tier1_identity != manifest.execution_policy_identity:
                raise ValueError("manifest execution policy identity must bind the Signal-to-Order policy")
        specification_values = dict(specifications)
        if not all(isinstance(key, InstrumentIdentity) and isinstance(value, InstrumentSpecification)
                   for key, value in specification_values.items()):
            raise TypeError("specifications must map InstrumentIdentity to InstrumentSpecification")
        self._bindings = {item.requirements.strategy_id: item for item in bindings}
        # Phase-4 Slice-1: strategy-owned pending-entry validity capabilities
        # bound alongside the strategies (never on StrategySignalGenerator/v1).
        self._entry_validity_policies = {
            item.requirements.strategy_id: item.entry_validity_policy
            for item in bindings if item.entry_validity_policy is not None
        }
        self._coordinator = MarketDataCoordinator((item.requirements for item in bindings), profiles)
        self._profiles = profiles
        self._policies = MappingProxyType(policy_values)
        self._account = account
        self._specifications = MappingProxyType(specification_values)
        self._manifest = manifest
        self._cost_schedules = tuple(cost_schedules)
        if protective_book is not None and not isinstance(protective_book, ProtectiveExitBook):
            raise TypeError("protective_book must be a ProtectiveExitBook")
        # The supplied book is configuration/template state.  Each ``run``
        # receives a fresh mutable lifecycle book so neither normal nor failed
        # independent backtests can inherit cancellation/trailing/OCO state.
        self._protective_configuration = protective_book
        # B3: Runtime policy callbacks for backtest/paper/live parity.
        # Initialized unconditionally (before risk_gate check) so they are
        # always available regardless of gate-enabled or legacy mode.
        self._runtime_trailing_policies: dict[tuple[str, str], object] = {}
        if runtime_trailing_policies is not None:
            for owner, policy in runtime_trailing_policies.items():
                if (
                    not isinstance(owner, tuple)
                    or len(owner) != 2
                    or not all(isinstance(part, str) and part.strip() for part in owner)
                ):
                    raise TypeError("runtime_trailing_policies keys must be non-empty (strategy_id, strategy_version) tuples")
                if not callable(getattr(policy, "trailing_decision", None)):
                    raise TypeError("runtime trailing policy must provide trailing_decision(evidence)")
                self._runtime_trailing_policies[owner] = policy
        self._runtime_target_replacement_policies: dict[tuple[str, str], object] = {}
        if runtime_target_replacement_policies is not None:
            for owner, policy in runtime_target_replacement_policies.items():
                if (
                    not isinstance(owner, tuple)
                    or len(owner) != 2
                    or not all(isinstance(part, str) and part.strip() for part in owner)
                ):
                    raise TypeError("runtime_target_replacement_policies keys must be non-empty (strategy_id, strategy_version) tuples")
                if not callable(getattr(policy, "target_replacement_decision", None)):
                    raise TypeError("runtime target replacement policy must provide target_replacement_decision(evidence)")
                self._runtime_target_replacement_policies[owner] = policy
        self._strategy_exit_policies: dict[tuple[str, str], object] = {}
        if strategy_exit_policies is not None:
            for owner, policy in strategy_exit_policies.items():
                if (
                    not isinstance(owner, tuple)
                    or len(owner) != 2
                    or not all(isinstance(part, str) and part.strip() for part in owner)
                ):
                    raise TypeError("strategy_exit_policies keys must be non-empty (strategy_id, strategy_version) tuples")
                if not callable(getattr(policy, "strategy_exit_decision", None)):
                    raise TypeError("strategy exit policy must provide strategy_exit_decision(evidence)")
                self._strategy_exit_policies[owner] = policy
        if not isinstance(regime_enabled, bool):
            raise TypeError("regime_enabled must be bool")
        self._regime_enabled = regime_enabled
        if regime_enabled and (not manifest.version.endswith("/v2") or manifest.regime_policy_identity != REGIME_POLICY_ID):
            raise ValueError("regime-enabled orchestration requires ReproducibilityManifest/v2 bound to RegimePolicy/v1")
        self._risk_gate = risk_gate
        if risk_gate is not None:
            if not isinstance(risk_gate, RiskGate):
                raise TypeError("risk_gate must be a RiskGate")
            if protective_book is None:
                raise ValueError("gate-enabled orchestration requires a protective_book")
            if calendars is None:
                raise ValueError("gate-enabled orchestration requires an authoritative calendars mapping")
            calendar_values = dict(calendars)
            if not calendar_values:
                raise ValueError("gate-enabled orchestration requires a non-empty calendars mapping")
            if not all(
                isinstance(key, str) and key.strip() and isinstance(value, WeekendCalendar)
                for key, value in calendar_values.items()
            ):
                raise TypeError("calendars must map non-empty calendar_id strings to WeekendCalendar instances")
            self._calendars = MappingProxyType(calendar_values)
            # Every profile used by this run must resolve an authoritative calendar.
            for profile in self._profiles.profiles.values():
                if profile.calendar_id not in self._calendars:
                    raise ValueError(f"no authoritative calendar for calendar_id {profile.calendar_id!r}")
            plan_policy_values = dict(protective_plan_policies or {})
            for binding in bindings:
                if binding.requirements.strategy_id not in plan_policy_values:
                    raise ValueError("gate-enabled orchestration requires a ProtectivePlanPolicy for every strategy binding")
            if not all(
                isinstance(key, str) and isinstance(value, ProtectivePlanPolicy)
                for key, value in plan_policy_values.items()
            ):
                raise TypeError("protective_plan_policies must map strategy_id to ProtectivePlanPolicy")
            self._plan_policies = MappingProxyType(plan_policy_values)
            # Gate-enabled BUY entry is authorized for MARKET, LIMIT, STOP, and STOP_LIMIT
            # per Owner Decision O2 (BACKTEST_ENGINE_ARCHITECTURE_DECISIONS.md §73).
            for policy in policy_values.values():
                for rule in policy.rules:
                    if rule.action == "BUY" and rule.order_type not in {
                        OrderType.MARKET, OrderType.LIMIT, OrderType.STOP, OrderType.STOP_LIMIT
                    }:
                        raise ValueError("gate-enabled BUY entry supports only MARKET, LIMIT, STOP, and STOP_LIMIT order types")
            if execution is not None:
                engine_calendars = getattr(execution, "calendars", None)
                if engine_calendars is None:
                    raise ValueError("gate-enabled orchestration requires an ExecutionEngine with explicit calendar authority")
                for stream, profile in self._profiles.profiles.items():
                    resolved = engine_calendars.get(profile.calendar_id)
                    if resolved is None or resolved is not self._calendars[profile.calendar_id]:
                        raise ValueError("execution engine calendar authority must match the orchestrator calendars mapping")
                self._execution = execution
            else:
                self._execution = ExecutionEngine(calendars=self._calendars)
            # Reproducibility binding (approved OPTION A): a gate-enabled run
            # must carry the ACTIVE RiskPolicy fingerprint in
            # RuntimeConfigurationSnapshot.risk under the v2 runtime-config
            # schema.  A gate-enabled run never masquerades as risk-deferred;
            # mismatch fails closed and is never silently rewritten.
            #
            # Phase-4 Slice-1 (owner decision O1): a validity-enabled run
            # (any binding carries a PendingEntryValidityPolicy) must bind the
            # canonical RUN-LEVEL strategy-keyed validity evidence under
            # RuntimeConfigurationSnapshot/v3.  v2 historical replay identity
            # is untouched; runs without validity policies keep the existing
            # v2 requirement unchanged.
            validity_bindings = tuple(
                (item.requirements.strategy_id, item.entry_validity_policy.policy_identity if item.entry_validity_policy is not None else None)
                for item in bindings
            )
            if self._entry_validity_policies:
                if not manifest.configuration.version.endswith("/v3"):
                    raise ValueError("validity-enabled orchestration requires RuntimeConfigurationSnapshot/v3 entry-validity binding evidence")
                expected_binding = entry_validity_binding_fingerprint(validity_bindings)
                if manifest.configuration.entry_validity != expected_binding:
                    raise ValueError("manifest configuration.entry_validity must bind the active entry-validity policies")
            elif not manifest.configuration.version.endswith("/v2"):
                raise ValueError("gate-enabled orchestration requires RuntimeConfigurationSnapshot/v2 risk-binding evidence")
            if manifest.configuration.risk != risk_gate.policy.fingerprint:
                raise ValueError("manifest configuration.risk must bind the active RiskPolicy fingerprint")
        else:
            if manifest.configuration.risk != "risk-deferred":
                raise ValueError("non-gated legacy orchestration requires configuration.risk 'risk-deferred'")
            self._calendars = None
            self._plan_policies = None
            self._execution = execution or ExecutionEngine()

    def run(self, events: Iterable[BarEvent | BoundBarEvent]) -> OrchestrationResult:
        """Coordinate complete-bar strategy decisions and pending orders deterministically."""
        protective_book = (
            None if self._protective_configuration is None
            else self._protective_configuration.fresh_runtime_book()
        )
        input_events = tuple(events)
        requests = self._coordinator.process(input_events)
        bars = tuple(event.bar if isinstance(event, BoundBarEvent) else event for event in input_events)
        requests_by_time: dict[datetime, list[EvaluationRequest]] = defaultdict(list)
        for request in requests:
            requests_by_time[request.data.decision_time].append(request)
        bars_by_time: dict[datetime, list[tuple[StreamKey, BarEvent]]] = defaultdict(list)
        for event, bar in zip(input_events, bars):
            stream = self._coordinator.stream_for(event)
            bars_by_time[self._coordinator.availability_time(bar)].append((stream, bar))

        snapshot = self._account.initial_snapshot()
        ledger = TradeLedger()
        states = {strategy_id: binding.strategy.initial_state() for strategy_id, binding in self._bindings.items()}
        pending: list[tuple[OrderRequest | ConcreteCloseInstruction, StreamKey, str | None]] = []
        risk_rejections: list[RiskGateResult] = []
        entry_risk_rejections: list[EntryRiskRejectionEvidence] = []
        # Gate runtime state is per-run and reset on every invocation.
        self._risk_state: RiskGateState | None = None
        self._commitments: tuple[PendingRiskCommitment, ...] = ()
        self._entry_associations: dict[str, PendingEntryAssociation] = {}
        self._lifecycles: dict[str, OrderLifecycle] = {}
        self._lifecycle_events: list[OrderLifecycleEvent] = []
        # Phase-4 no-lookahead: the strategy's MOST-RECENT PRE-T decision view.
        # ``_evaluate_pending`` for opportunity T runs BEFORE ``generate_signal``
        # for T, so this map always holds a view bounded strictly before T.
        last_views: dict[str, MarketDataView] = {}
        intents: list[SignalIntent] = []
        orders: list[OrderRequest] = []
        executions: list[ExecutionResult] = []
        accounting: list[AccountingResult] = []
        trades: list[TradeRecord] = []
        assessments: list[CostAssessment] = []
        leg_assessments: list[CostLegAssessment] = []
        regimes = RegimeClassifier()
        entry_regimes: list[EntryRegimeSnapshot] = []
        sequence = 0

        for decision_time in sorted(set(bars_by_time) | set(requests_by_time)):
            current_bars = tuple(sorted(bars_by_time.get(decision_time, ()), key=lambda item: item[1].canonical_order_key))
            failure, snapshot, sequence = self._evaluate_pending(
                pending, current_bars, snapshot, ledger, sequence,
                executions, accounting, trades, assessments, leg_assessments, regimes, entry_regimes, protective_book, risk_rejections, entry_risk_rejections,
                decision_time, states, last_views,
            )
            if failure is not None:
                return self._result(snapshot, requests, intents, orders, executions, accounting, trades, assessments, failure, leg_assessments, regimes.evidence, entry_regimes, risk_rejections, tuple(self._lifecycle_events), entry_risk_rejections, protective_book)

            batch_intents: list[tuple[SignalIntent, BarEvent, StreamKey]] = []
            for request in sorted(requests_by_time.get(decision_time, ()), key=lambda item: item.requirements.strategy_id):
                binding = self._bindings[request.requirements.strategy_id]
                # Retain the strategy's as-of decision view (immutable
                # MarketDataView) for the NEXT pending execution opportunity.
                last_views[request.requirements.strategy_id] = request.data
                data = self._strategy_data(binding, request.data)
                signal = safe_generate_signal(
                    _Rule7StrategyAdapter(
                        binding.strategy,
                        binding.requirements.strategy_id,
                        binding.requirements.strategy_version,
                    ),
                    data,
                    states[binding.requirements.strategy_id],
                    "backtest",
                )
                if not isinstance(signal, Signal):
                    raise TypeError("strategy generate_signal must return Signal")
                source = request.data.latest(binding.signal_source_stream)
                if source is None:
                    raise ValueError("ready trigger stream has no source event")
                intent = SignalIntake().intake(signal, SignalIntakeContext(source, request.requirements.strategy_id, request.requirements.strategy_version))
                if intent is not None:
                    intents.append(intent)
                    batch_intents.append((intent, source, binding.signal_source_stream))

            ordered_batch: list[tuple[SignalIntent, BarEvent, StreamKey]] = batch_intents
            if self._risk_gate is not None:
                # Q62StrategyScopedConfidence/v2: canonical strategy/version
                # group ordering first, confidence descending only within the
                # same strategy/version, then the canonical tie-break.
                grouped: dict[SignalPriorityEvidence, list[tuple[SignalIntent, BarEvent, StreamKey]]] = defaultdict(list)
                for intent, source, source_stream in batch_intents:
                    grouped[SignalPriorityEvidence(
                        intent.confidence, intent.strategy_id, intent.strategy_version,
                        source_stream.identity, intent.timeframe, intent.originating_timestamp,
                    )].append((intent, source, source_stream))
                ordered_batch = []
                for evidence in rank_candidates(tuple(grouped)):
                    ordered_batch.extend(grouped[evidence])

            for intent, source, source_stream in ordered_batch:
                if self._risk_gate is not None and intent.action == "BUY":
                    entry_identity = entry_intent_identity(
                        strategy_id=intent.strategy_id,
                        strategy_version=intent.strategy_version,
                        identity=source_stream.identity,
                        timeframe=intent.timeframe,
                        originating_timestamp=intent.originating_timestamp,
                    )
                    if entry_identity in self._entry_associations:
                        raise ValueError("duplicate logical entry identity within the same run")
                    planned = self._policies[intent.strategy_id].planned_terms(intent, source)
                    entry_reference = _gate_entry_reference(planned, source)
                    intended_key = PositionKey(intent.strategy_id, intent.strategy_version, source_stream.identity)
                    plan = self._plan_policies[intent.strategy_id].plan_for(
                        intended_position_key=intended_key,
                        originating_timestamp=intent.originating_timestamp,
                        timeframe=intent.timeframe,
                        reference_price=entry_reference,
                    )
                    risk_day = self._risk_day_for(source_stream, intent.originating_timestamp)
                    # Phase-4 Slice-1: the bound PendingEntryValidityPolicy
                    # freezes the immutable mechanical EntryValiditySpec from
                    # the current logical entry context (planned terms + entry
                    # reference already resolved once above).  The spec never
                    # depends on approved quantity, RiskGate sizing, fill
                    # price, or future market evidence; only the policy
                    # creates it.  No policy bound -> no spec (default VALID).
                    validity_policy = self._entry_validity_policies.get(intent.strategy_id)
                    validity_spec = None
                    if validity_policy is not None:
                        validity_spec = validity_policy.freeze_spec(entry_context=EntryValidityContext(
                            strategy_id=intent.strategy_id,
                            strategy_version=intent.strategy_version,
                            identity=source_stream.identity,
                            timeframe=intent.timeframe,
                            originating_timestamp=intent.originating_timestamp,
                            entry_reference=entry_reference,
                            calendar_identity=risk_day.calendar_identity,
                            session_date=risk_day.session_date,
                        ))
                        if not isinstance(validity_spec, EntryValiditySpec):
                            raise TypeError("freeze_spec must return an EntryValiditySpec")
                    # Authoritative cost-inclusive net-equity evidence, built
                    # ONCE from the current snapshot and ONLY already-recognized
                    # leg costs (never candidate costs).  The SAME projection
                    # object supplies BOTH the Q56 current_net_equity and the
                    # RiskPolicy v4 Q55/Q59 capital-basis evidence, so
                    # recognized costs are applied exactly once.  v3 ignores
                    # the projection for Q55/Q59, but Q56 always receives the
                    # cost-inclusive net equity.
                    projection = CostAdjustedAccountProjection.from_evidence(snapshot, tuple(leg_assessments))
                    gate_result = self._risk_gate.evaluate_pre_order(
                        direction=PositionDirection.LONG,
                        intended_position_key=intended_key,
                        capital=snapshot.starting_capital,
                        entry_price=entry_reference,
                        specification=self._specification_for_stream(source_stream),
                        snapshot=snapshot,
                        book=protective_book,
                        candidate_plan=plan,
                        risk_day=risk_day,
                        current_net_equity=projection.cost_adjusted_equity,
                        starting_capital=snapshot.starting_capital,
                        prior_state=self._risk_state,
                        pending_commitments=self._commitments,
                        cost_projection=projection,
                    )
                    self._risk_state = gate_result.state if gate_result.state is not None else self._risk_state
                    if gate_result.outcome is not RiskOutcome.APPROVED:
                        risk_rejections.append(gate_result)
                        continue
                    approved_quantity = gate_result.quantity
                    order = self._policies[intent.strategy_id].order_for(
                        intent, source, quantity=approved_quantity, planned_terms=planned,
                    )
                    if order.quantity != approved_quantity:
                        raise ValueError("order quantity must equal the RiskGate-approved quantity")
                    self._commitments = (*self._commitments, PendingRiskCommitment(
                        entry_identity=entry_identity,
                        intended_position_key=intended_key,
                        approved_quantity=approved_quantity,
                        nominal_stop_risk=gate_result.nominal_stop_risk,
                    ))
                    self._entry_associations[entry_identity] = PendingEntryAssociation(
                        entry_identity=entry_identity,
                        order=order,
                        source_stream=source_stream,
                        frozen_plan=plan,
                        approved_quantity=approved_quantity,
                        entry_reference=entry_reference,
                        validity_spec=validity_spec,
                        validity_policy_identity=validity_policy.policy_identity if validity_policy is not None else None,
                    )
                    # Lifecycle chain per owner mapping: RiskGate APPROVED ->
                    # OrderRequest constructed -> CREATED -> structural/order
                    # lifecycle validation -> VALIDATED -> pending + commitment
                    # + association -> QUEUED.  Initial RiskGate rejection
                    # creates no OrderRequest and no lifecycle chain.
                    self._lifecycles[entry_identity] = (
                        OrderLifecycle(order)
                        .transition_to(OrderLifecycleState.VALIDATED)
                        .transition_to(OrderLifecycleState.QUEUED)
                    )
                    orders.append(order)
                    pending.append((order, source_stream, entry_identity, None))
                else:
                    order = self._policies[intent.strategy_id].order_for(intent, source)
                    orders.append(order)
                    if order.action == "EXIT":
                        specification = self._specification_for_stream(source_stream)
                        resolved = self._account.resolve_exit(snapshot, order, specification)
                        accounting.append(resolved)
                        if resolved.outcome is AccountingOutcome.ACCEPTED and resolved.close_instruction is not None:
                            pending.append((resolved.close_instruction, source_stream, None, None))
                    else:
                        pending.append((order, source_stream, None, None))
            # A complete real bar becomes eligible for regime classification
            # only after all same-timestamp execution decisions.  Thus a fill
            # cannot see its own incomplete bar's high/low/close.
            if self._regime_enabled:
                for stream, bar in current_bars:
                    regimes.update(stream, bar)

        # Dataset exhaustion is an explicit execution outcome, never an implicit fill/cancel.
        for order, _, entry_identity, activation in tuple(pending):
            executions.append(self._execution.end_of_data(order, stop_limit_activation=activation))
            if entry_identity is not None:
                self._release_commitment(entry_identity)
        return self._result(snapshot, requests, intents, orders, executions, accounting, trades, assessments, None, leg_assessments, regimes.evidence, entry_regimes, risk_rejections, tuple(self._lifecycle_events), entry_risk_rejections, protective_book)

    def _evaluate_pending(
        self,
        pending: list[tuple[OrderRequest | ConcreteCloseInstruction, StreamKey, str | None, StopLimitActivationEvidence | None]],
        current_bars: tuple[tuple[StreamKey, BarEvent], ...],
        snapshot: AccountSnapshot,
        ledger: TradeLedger,
        sequence: int,
        executions: list[ExecutionResult],
        accounting: list[AccountingResult],
        trades: list[TradeRecord],
        assessments: list[CostAssessment],
        leg_assessments: list[CostLegAssessment],
        regimes: RegimeClassifier,
        entry_regimes: list[EntryRegimeSnapshot],
        protective_book: ProtectiveExitBook | None,
        risk_rejections: list[RiskGateResult],
        entry_risk_rejections: list[EntryRiskRejectionEvidence],
        decision_time: datetime,
        states: Mapping[str, Mapping[str, Any]],
        last_views: Mapping[str, MarketDataView],
    ) -> tuple[StructuredFailureResult | None, AccountSnapshot, int]:
        # Protective state is evaluated first in stable id order.  Its existing
        # domain object owns OCO/gap/trailing semantics; this coordinator only
        # records the accepted execution/accounting evidence it returns.
        if protective_book is not None:
            for protective_id, protective in sorted(protective_book.exits.items()):
                if protective.state is not ProtectiveExitState.ACTIVE:
                    continue
                if protective.position_key not in snapshot.positions:
                    # A configured protection becomes evaluable only once its
                    # exact PositionKey exists; do not cancel it before entry.
                    continue
                matched = next((bar for stream, bar in current_bars
                                if stream.identity == protective.position_key.identity
                                and stream.timeframe == protective.exit_order.timeframe), None)
                if matched is None:
                    continue
                matched_stream = next(stream for stream, bar in current_bars if bar is matched)
                evaluation = protective_book.evaluate(
                    protective_id, snapshot, matched,
                    self._profiles.resolve(matched_stream), self._account,
                    self._specification_for_stream(matched_stream),
                    self._execution,
                )
                if evaluation.execution is not None:
                    executions.append(evaluation.execution)
                if evaluation.accounting is None:
                    continue
                accounting.append(evaluation.accounting)
                snapshot = evaluation.accounting.resulting_snapshot
                sequence = self._record_accepted_leg(
                    ledger, sequence, evaluation.accounting, snapshot, trades, assessments, leg_assessments, regimes, matched_stream, entry_regimes, protective_book,
                )
        # B3: Runtime policy callbacks — backtest parity with paper/live.
        # For each active trailing stop with a registered runtime policy,
        # construct bar-based RuntimeTrailingEvidence and invoke the SAME
        # strategy-owned callback used in live mode.  The callback decides
        # whether to activate/ratchet; the book applies the result.
        if protective_book is not None and self._runtime_trailing_policies:
            for protective_id, protective in sorted(protective_book.exits.items()):
                if (
                    protective.state is not ProtectiveExitState.ACTIVE
                    or protective.kind is not ProtectiveExitKind.TRAILING_STOP
                    or protective.trailing is None
                ):
                    continue
                if protective.position_key not in snapshot.positions:
                    continue
                owner_key = (protective.position_key.strategy_id, protective.position_key.strategy_version)
                runtime_policy = self._runtime_trailing_policies.get(owner_key)
                if runtime_policy is None:
                    continue
                matched = next((bar for stream, bar in current_bars
                                if stream.identity == protective.position_key.identity
                                and stream.timeframe == protective.exit_order.timeframe), None)
                if matched is None:
                    continue
                evidence = RuntimeTrailingEvidence(
                    position_key=protective.position_key,
                    protective=protective,
                    market_timestamp=matched.timestamp,
                    executable_bid=matched.close,
                )
                try:
                    decision = runtime_policy.trailing_decision(evidence)
                except Exception as error:
                    raise RuntimeError(
                        f"backtest runtime trailing decision failed for {owner_key}"
                    ) from error
                if decision is not None and not isinstance(decision, RuntimeTrailingDecision):
                    raise TypeError("strategy runtime trailing decision must return RuntimeTrailingDecision or None")
                if decision is not None:
                    if protective.trailing.activated:
                        if decision.activate:
                            raise ValueError("backtest runtime trailing decision cannot activate an active trailing stop")
                        protective_book.update_trailing(
                            protective_id,
                            reference_extreme=decision.reference_extreme,
                            next_stop=decision.next_stop,
                            effective_after=matched.timestamp,
                        )
                    else:
                        if not decision.activate:
                            raise ValueError("backtest runtime trailing decision must set activate for an inactive trailing stop")
                        protective_book.activate_trailing(
                            protective_id,
                            reference_extreme=decision.reference_extreme,
                            next_stop=decision.next_stop,
                            effective_after=matched.timestamp,
                        )
        # B3-R1: Runtime target-replacement callbacks — backtest parity with
        # paper/live.  For each held position whose authoritative TARGET has a
        # registered runtime policy, construct bar-based
        # ``TargetReplacementEvidence`` from COMPLETED event-T facts only
        # (authoritative book state + the completed decision bar) and invoke
        # the SAME strategy-owned ``target_replacement_decision`` callback used
        # by ``LiveProtectiveEvaluator.replace_target``.  The generic book
        # machinery owns the committed mutation; the replacement carries
        # ``effective_after = T`` so the frozen non-retroactivity rule in
        # ``ProtectiveExitBook.evaluate`` (strictly-later bar required) makes
        # the replaced target untriggerable on its own decision bar.
        if protective_book is not None and self._runtime_target_replacement_policies:
            for key, position in sorted(
                snapshot.positions.items(),
                key=lambda item: (item[0].strategy_id, item[0].strategy_version, item[0].identity.instrument),
            ):
                if position.quantity <= Decimal("0"):
                    continue
                owner_key = (key.strategy_id, key.strategy_version)
                target_policy = self._runtime_target_replacement_policies.get(owner_key)
                if target_policy is None:
                    continue
                # Exactly-one-or-skip: a replacement decision requires exactly
                # one authoritative TARGET for this exact position.
                authoritative_targets = protective_book.authoritative_exits(
                    key, kind=ProtectiveExitKind.TARGET,
                )
                if len(authoritative_targets) != 1:
                    continue
                current_target = authoritative_targets[0]
                matched = next((bar for stream, bar in current_bars
                                if stream.identity == key.identity
                                and stream.timeframe == current_target.exit_order.timeframe), None)
                if matched is None:
                    continue
                evidence = TargetReplacementEvidence(
                    position_key=key,
                    strategy_id=key.strategy_id,
                    strategy_version=key.strategy_version,
                    current_target=current_target,
                    current_limit_price=current_target.exit_order.limit_price,
                    market_timestamp=matched.timestamp,
                )
                try:
                    candidate = target_policy.target_replacement_decision(evidence)
                except Exception as error:
                    raise RuntimeError(
                        f"backtest target replacement decision failed for {owner_key}"
                    ) from error
                if candidate is not None and not isinstance(candidate, TargetCandidate):
                    raise TypeError("policy target_replacement_decision must return TargetCandidate or None")
                if candidate is None:
                    continue
                # Authoritative re-read + identity validation (parity with
                # LiveProtectiveEvaluator.replace_target phase 3).  Candidate
                # geometry/finiteness is owned by TargetCandidate.__post_init__;
                # identity/quantity/OCO preservation is owned by the generic
                # committed_mutation finalize below.  No strategy economics
                # exists in this engine code.
                targets_now = protective_book.authoritative_exits(
                    key, kind=ProtectiveExitKind.TARGET,
                )
                if len(targets_now) != 1 or targets_now[0] != current_target:
                    raise ValueError("stale authoritative TARGET — target replacement candidate rejected")
                if (
                    candidate.position_key != key
                    or candidate.strategy_id != key.strategy_id
                    or candidate.strategy_version != key.strategy_version
                    or candidate.current_target_protective_id != current_target.protective_id
                ):
                    raise ValueError("target replacement candidate owner/identity mismatch")
                if candidate.market_timestamp != matched.timestamp:
                    raise ValueError("target replacement candidate timestamp must be the historical decision event")
                replacement_intent = SignalIntent(
                    action=current_target.exit_order.source_intent.action,
                    confidence=current_target.exit_order.source_intent.confidence,
                    symbol=current_target.exit_order.source_intent.symbol,
                    timeframe=current_target.exit_order.source_intent.timeframe,
                    originating_timestamp=candidate.market_timestamp,
                    strategy_id=current_target.exit_order.source_intent.strategy_id,
                    strategy_version=current_target.exit_order.source_intent.strategy_version,
                    metadata=current_target.exit_order.source_intent.metadata,
                )
                replacement_order = OrderRequest(
                    source_intent=replacement_intent,
                    order_type=OrderType.LIMIT,
                    quantity=current_target.quantity,
                    time_in_force=current_target.exit_order.time_in_force,
                    limit_price=candidate.proposed_target_price,
                    stop_price=None,
                )
                replacement = dc_replace(
                    current_target,
                    exit_order=replacement_order,
                    effective_after=candidate.market_timestamp,
                )
                # One logical backtest decision: accepted replacement + its
                # optional coupled strategy-state transition apply together.
                # Owner validation happens BEFORE the book mutation so an
                # invalid transition can never half-apply a target change;
                # after the committed publish succeeds, the deterministic
                # in-memory state assignment cannot fail, so there is no
                # partial-application window.
                transition = candidate.state_transition
                if transition is not None and (
                    transition.strategy_id != key.strategy_id
                    or transition.strategy_version != key.strategy_version
                ):
                    raise ValueError("target replacement state transition owner mismatch")
                with protective_book.committed_mutation() as session:
                    proposal = session.finalize(current_target, replacement)
                    session.publish_committed(proposal)
                if transition is not None:
                    states[key.strategy_id] = dict(transition.state)
        # B3: Strategy exit policy callbacks — backtest parity with paper/live.
        # For each open position with a registered strategy exit policy,
        # construct bar-based StrategyExitEvidence and invoke the SAME
        # strategy-owned callback used in live mode.
        if self._strategy_exit_policies:
            exit_candidates: list[tuple[PositionKey, StrategyExitDecision, StreamKey, BarEvent]] = []
            for key, position in snapshot.positions.items():
                if position.quantity <= Decimal("0"):
                    continue
                owner_key = (key.strategy_id, key.strategy_version)
                exit_policy = self._strategy_exit_policies.get(owner_key)
                if exit_policy is None:
                    continue
                matched = next((bar for stream, bar in current_bars
                                if stream.identity == key.identity), None)
                if matched is None:
                    continue
                matched_stream = next(stream for stream, bar in current_bars if bar is matched)
                evidence = StrategyExitEvidence(
                    strategy_id=key.strategy_id,
                    strategy_version=key.strategy_version,
                    position_key=key,
                    instrument_identity=key.identity,
                    direction="LONG",
                    open_quantity=position.quantity,
                    market_timestamp=matched.timestamp,
                )
                try:
                    decision = exit_policy.strategy_exit_decision(evidence)
                except Exception as error:
                    raise RuntimeError(
                        f"backtest strategy exit decision failed for {owner_key}"
                    ) from error
                if decision is not None and not isinstance(decision, StrategyExitDecision):
                    raise TypeError("strategy exit decision must return StrategyExitDecision or None")
                if decision is not None:
                    exit_candidates.append((key, decision, matched_stream, matched))
            # Process strategy exit candidates through normal close path
            for key, exit_decision, exit_stream, exit_bar in exit_candidates:
                # Re-check position still exists (may have been closed by protective)
                if key not in snapshot.positions or snapshot.positions[key].quantity <= Decimal("0"):
                    continue
                specification = self._specification_for_stream(exit_stream)
                profile = self._profiles.resolve(exit_stream)
                order = OrderRequest.from_intent(
                    SignalIntent(
                        action="EXIT", confidence=1.0,
                        symbol=key.identity.instrument, timeframe=exit_stream.timeframe,
                        originating_timestamp=exit_bar.timestamp,
                        strategy_id=key.strategy_id, strategy_version=key.strategy_version,
                        metadata={},
                    ),
                    OrderType.MARKET,
                    snapshot.positions[key].quantity,
                    TimeInForce.DAY,
                )
                resolved = self._account.resolve_exit(snapshot, order, specification)
                accounting.append(resolved)
                if resolved.outcome is AccountingOutcome.ACCEPTED and resolved.close_instruction is not None:
                    pending.append((resolved.close_instruction, exit_stream, None, None))
        candidates: list[tuple[ExecutionResult, StreamKey, str | None]] = []
        survivors: list[tuple[OrderRequest | ConcreteCloseInstruction, StreamKey, str | None, StopLimitActivationEvidence | None]] = []
        for order, order_stream, entry_identity, activation in tuple(pending):
            matching = next((bar for stream, bar in current_bars if stream == order_stream), None)
            if matching is None:
                survivors.append((order, order_stream, entry_identity, activation))
                continue
            profile = self._profiles.resolve(order_stream)
            if entry_identity is not None and order.action == "BUY":
                # Phase-4 Slice-1 pre-execution ordering for a gate-enabled
                # pending BUY: (1) mechanical EntryValiditySpec, (2) strategy
                # semantic validity, (3) existing Q56 reauthorization, (4)
                # ExecutionEngine.evaluate.  Any failing check terminally
                # removes the pending entry WITHOUT an execution evaluation.
                association = self._entry_associations.get(entry_identity)
                pending_risk_day = self._risk_day_for(order_stream, matching.timestamp)
                if association is not None and association.validity_spec is not None:
                    mechanical_reason = self._mechanical_validity_reason(
                        association.validity_spec, decision_time, pending_risk_day,
                    )
                    if mechanical_reason is not None:
                        self._terminal_lifecycle(
                            entry_identity, OrderLifecycleState.EXPIRED,
                            OrderLifecycleCauseType.MECHANICAL_EXPIRY,
                            order_lifecycle_cause_reference(
                                OrderLifecycleCauseType.MECHANICAL_EXPIRY,
                                reference=association.validity_spec.spec_identity,
                                reason=mechanical_reason,
                            ),
                            decision_time,
                        )
                        self._release_commitment(entry_identity)
                        continue
                validity_policy = self._entry_validity_policies.get(order.strategy_id)
                if validity_policy is not None and association is not None:
                    # Strategy semantic validity: the core consumes the result
                    # blindly.  Evidence boundary (no look-ahead): the retained
                    # MOST-RECENT PRE-T MarketDataView (bars strictly before
                    # this execution opportunity) and the strategy state as of
                    # its last generate_signal decision.  The state passed to
                    # the evaluator is an isolated deep copy; any mutation is
                    # discarded and the authoritative state is never touched.
                    bounded_view = last_views.get(order.strategy_id)
                    if bounded_view is None:
                        raise ValueError("pending entry validity requires a retained pre-execution data view")
                    if association.entry_reference is None:
                        raise ValueError("pending entry validity requires the frozen entry reference")
                    try:
                        state_snapshot = deepcopy(states[order.strategy_id])
                    except Exception as error:
                        raise ValueError("validity evaluation requires copyable strategy state") from error
                    validity_context = EntryValidityContext(
                        strategy_id=order.strategy_id,
                        strategy_version=order.strategy_version,
                        identity=order_stream.identity,
                        timeframe=order.timeframe,
                        originating_timestamp=order.originating_timestamp,
                        entry_reference=association.entry_reference,
                        calendar_identity=association.validity_spec.calendar_identity if association.validity_spec is not None else None,
                        session_date=association.validity_spec.session_date if association.validity_spec is not None else None,
                    )
                    validity_result = validity_policy.evaluate(
                        entry_context=validity_context,
                        spec=association.validity_spec,
                        data_view=self._strategy_data(self._bindings[order.strategy_id], bounded_view),
                        state_snapshot=state_snapshot,
                    )
                    if not isinstance(validity_result, EntryValidityResult):
                        raise TypeError("entry-validity evaluate must return an EntryValidityResult")
                    # Provenance fail-closed (P2-A): the returned result must
                    # claim the SAME policy identity as the active bound policy
                    # AND the frozen approval-time association before its
                    # outcome is consumed.  A mismatched result is NOT
                    # authoritative evidence: a mismatched INVALID must not be
                    # classified as STRATEGY_INVALIDATION and a mismatched
                    # VALID must not proceed toward execution.  Orchestration
                    # invariant only -- never a RiskGate rule.
                    if validity_result.policy_identity != validity_policy.policy_identity:
                        raise ValueError(
                            f"entry-validity provenance mismatch: result claims policy "
                            f"{validity_result.policy_identity!r} but the bound policy is "
                            f"{validity_policy.policy_identity!r}"
                        )
                    if association.validity_policy_identity != validity_policy.policy_identity:
                        raise ValueError(
                            f"entry-validity association provenance mismatch: association binds "
                            f"{association.validity_policy_identity!r} but the bound policy is "
                            f"{validity_policy.policy_identity!r}"
                        )
                    if validity_result.outcome is not EntryValidityOutcome.VALID:
                        self._terminal_lifecycle(
                            entry_identity, OrderLifecycleState.CANCELLED,
                            OrderLifecycleCauseType.STRATEGY_INVALIDATION,
                            validity_result.evidence_identity,
                            decision_time,
                        )
                        self._release_commitment(entry_identity)
                        continue
                # Dynamic Q56-only pre-execution authorization for an
                # already-approved pending entry: Q56 is a DYNAMIC account-level
                # hard entry permission, so the T1 approval is not permanent
                # authorization to create new risk.  The pending order already
                # carries its approved quantity, frozen entry identity,
                # commitment, frozen plan, and Q55/Q57/Q58/Q59/Q60
                # reservations; this checks ONLY whether Q56 still authorizes
                # new risk against the CURRENT authoritative cost-inclusive
                # net equity.  Completed-bar evidence only: the mark loop for
                # this bar runs later, so no same-bar look-ahead can
                # manufacture the breach.
                pending_projection = CostAdjustedAccountProjection.from_evidence(snapshot, tuple(leg_assessments))
                authorization = self._risk_gate.evaluate_pending_entry_pre_execution(
                    risk_day=pending_risk_day,
                    current_net_equity=pending_projection.cost_adjusted_equity,
                    starting_capital=snapshot.starting_capital,
                    prior_state=self._risk_state,
                )
                self._risk_state = authorization.state if authorization.state is not None else self._risk_state
                if authorization.outcome is not RiskOutcome.APPROVED:
                    # Terminal risk invalidation: the entry never reaches
                    # execution evaluation, never produces a FILLED result,
                    # never calls apply_execution, never creates ownership,
                    # never increments the daily trade count, never
                    # materializes protection, and never recognizes an entry
                    # cost.  The commitment and its frozen association are
                    # released deterministically; the submitted OrderRequest
                    # remains in historical orders evidence only.  Q56 stays
                    # authoritative ONLY in risk_rejections; the lifecycle
                    # event references it and never recomputes the formula.
                    risk_rejections.append(authorization)
                    # Entry-scoped rejection evidence (P2-D): RiskGateResult is
                    # generic risk-engine output and stays unchanged; the
                    # orchestration layer owns entry_identity, so the exact
                    # linkage is created HERE.  Two distinct pending entries
                    # rejected with the same reason at the same decision time
                    # still produce distinct evidence identities because
                    # entry_identity participates in the canonical fingerprint.
                    rejection_evidence = EntryRiskRejectionEvidence(
                        entry_identity=entry_identity,
                        decision_timestamp=decision_time,
                        risk_result=authorization,
                    )
                    entry_risk_rejections.append(rejection_evidence)
                    self._terminal_lifecycle(
                        entry_identity, OrderLifecycleState.REJECTED,
                        OrderLifecycleCauseType.Q56_REJECTION,
                        rejection_evidence.evidence_identity,
                        decision_time,
                    )
                    self._release_commitment(entry_identity)
                    continue
            outcome = self._execution.evaluate(order, matching, profile, stop_limit_activation=activation)
            executions.append(outcome)
            if outcome.outcome in {ExecutionOutcome.UNFILLED, ExecutionOutcome.INELIGIBLE}:
                # A synthetic/out-of-session bar is not a cancellation policy and
                # must not erase an otherwise valid pending order.  The
                # ExecutionEngine result is the single activation authority:
                # on UNFILLED/INELIGIBLE the survivor carries the evidence it
                # returned (newly created on an authoritative trigger, or the
                # prior evidence preserved unchanged on an ineligible bar).
                survivors.append((order, order_stream, entry_identity, outcome.stop_limit_activation))
            elif outcome.outcome is ExecutionOutcome.REQUIRES_PORTFOLIO_RESOLUTION:
                raise ValueError("unresolved EXIT reached execution despite portfolio resolution boundary")
            elif outcome.outcome is ExecutionOutcome.FILLED:
                candidates.append((outcome, order_stream, entry_identity))
            elif entry_identity is not None:
                # EXPIRED (DAY expiry) is terminal: the order drops from
                # pending; release any gate commitment deterministically.  The
                # lifecycle EXPIRED event references the EXISTING
                # ExecutionResult evidence (reason), never recomputes it.
                self._terminal_lifecycle(
                    entry_identity, OrderLifecycleState.EXPIRED,
                    OrderLifecycleCauseType.DAY_EXPIRY,
                    order_lifecycle_cause_reference(
                        OrderLifecycleCauseType.DAY_EXPIRY, reason=outcome.reason,
                    ),
                    decision_time,
                )
                self._release_commitment(entry_identity)
        pending[:] = survivors

        failure = self._capital_competition(candidates, snapshot, leg_assessments)
        if failure is not None:
            return failure, snapshot, sequence
        for outcome, stream, entry_identity in candidates:
            specification = self._specification_for_stream(stream)
            if outcome.action == "BUY" and self._cost_schedules:
                required = outcome.fill_price * outcome.filled_quantity * specification.contract_multiplier
                projection = CostAdjustedAccountProjection.from_evidence(snapshot, leg_assessments)
                if not projection.permits_entry(required):
                    accounting.append(AccountingResult(
                        snapshot, snapshot, AccountingOutcome.REJECTED_INSUFFICIENT_CAPITAL,
                        "insufficient_cost_adjusted_buying_power", outcome,
                        {},
                    ))
                    if entry_identity is not None:
                        # Q65 stays the fill-time cost authority; the
                        # lifecycle REJECTED event references its AccountingResult
                        # reason.  An ExecutionResult.FILLED candidate is NOT
                        # lifecycle FILLED without accepted accounting.
                        self._terminal_lifecycle(
                            entry_identity, OrderLifecycleState.REJECTED,
                            OrderLifecycleCauseType.Q65_REJECTION,
                            order_lifecycle_cause_reference(
                                OrderLifecycleCauseType.Q65_REJECTION,
                                reason="insufficient_cost_adjusted_buying_power",
                            ),
                            decision_time,
                        )
                        self._release_commitment(entry_identity)
                    continue
            result = self._account.apply_execution(snapshot, outcome, specification)
            accounting.append(result)
            if result.outcome is not AccountingOutcome.ACCEPTED:
                if entry_identity is not None:
                    self._terminal_lifecycle(
                        entry_identity, OrderLifecycleState.REJECTED,
                        OrderLifecycleCauseType.ACCOUNTING_REJECTION,
                        order_lifecycle_cause_reference(
                            OrderLifecycleCauseType.ACCOUNTING_REJECTION, reason=result.reason,
                        ),
                        decision_time,
                    )
                    self._release_commitment(entry_identity)
                continue
            snapshot = result.resulting_snapshot
            if entry_identity is not None:
                # Gate-enabled accepted BUY: ownership now exists.  Release the
                # pending commitment, advance risk state to the FILL-TIME
                # RiskDay using PRE-FILL net equity, record the first entry
                # fill exactly once, then materialize the frozen protective
                # plan at the approved (full-fill) quantity.
                association = self._entry_associations.pop(entry_identity, None)
                if association is None:
                    raise ValueError("gate-enabled accepted fill missing pending entry association")
                # QUEUED -> FILLED ONLY after accepted accounting ownership
                # (an ExecutionResult.FILLED candidate alone is NOT lifecycle
                # FILLED -- Q65/accounting can reject it before ownership).
                # Recorded BEFORE the release so the lifecycle chain is still
                # present for the transition.
                self._terminal_lifecycle(
                    entry_identity, OrderLifecycleState.FILLED,
                    OrderLifecycleCauseType.FILL,
                    order_lifecycle_cause_reference(
                        OrderLifecycleCauseType.FILL,
                        reference=CanonicalCodec.fingerprint(
                            "algofortis-accepted-accounting/v1",
                            (("entry", entry_identity), ("outcome", AccountingOutcome.ACCEPTED.value)),
                        ),
                    ),
                    decision_time,
                )
                self._release_commitment(entry_identity)
                if outcome.filled_quantity != association.approved_quantity:
                    raise ValueError("accepted fill quantity must equal the RiskGate-approved quantity")
                fill_risk_day = self._risk_day_for(stream, outcome.execution_bar_timestamp)
                # Authoritative COST-INCLUSIVE PRE-FILL net equity: built from
                # the PRE-FILL snapshot and ONLY costs recognized before the
                # current fill.  The accepted leg's own cost is appended to
                # leg_assessments later, inside _record_accepted_leg, so it is
                # never part of this RiskDay baseline; it becomes visible to
                # later Q56 evaluations on the fill-time RiskDay instead.
                pre_fill_projection = CostAdjustedAccountProjection.from_evidence(result.prior_snapshot, tuple(leg_assessments))
                self._risk_state = self._risk_gate.advance_state(
                    risk_day=fill_risk_day,
                    current_net_equity=pre_fill_projection.cost_adjusted_equity,
                    starting_capital=snapshot.starting_capital,
                    prior_state=self._risk_state,
                )
                self._risk_state = self._risk_state.record_entry_fill(association.entry_identity)
                materialize_protective_plan(
                    association.frozen_plan,
                    run_identity=self._manifest.manifest_fingerprint,
                    quantity=association.approved_quantity,
                    book=protective_book,
                )
            sequence = self._record_accepted_leg(
                ledger, sequence, result, snapshot, trades, assessments, leg_assessments, regimes, stream, entry_regimes, protective_book,
            )
        for stream, bar in current_bars:
            identity = stream.identity
            if any(key.identity == identity for key in snapshot.positions):
                mark = self._account.mark_to_market(snapshot, identity, bar)
                accounting.append(mark)
                if mark.outcome is AccountingOutcome.ACCEPTED:
                    snapshot = mark.resulting_snapshot
        return None, snapshot, sequence

    def _capital_competition(
        self,
        candidates: list[tuple[ExecutionResult, StreamKey, str | None]],
        snapshot: AccountSnapshot,
        recognized_leg_assessments: list[CostLegAssessment],
    ) -> StructuredFailureResult | None:
        groups: dict[datetime, list[tuple[ExecutionResult, StreamKey]]] = defaultdict(list)
        for outcome, stream, _ in candidates:
            if outcome.action == "BUY":
                groups[outcome.order.originating_timestamp].append((outcome, stream))
        for origin, group in groups.items():
            if len(group) < 2:
                continue
            required = Decimal("0")
            for outcome, stream in group:
                spec = self._specification_for_stream(stream)
                required += outcome.fill_price * outcome.filled_quantity * spec.contract_multiplier  # type: ignore[operator]
            # Only already-recognized immutable costs affect this check.
            # Candidate costs do not yet exist and must never be fabricated to
            # decide an allocation.  Without an approved allocation policy,
            # a candidate set that cannot fit the current authoritative
            # buying-power projection is a deterministic Category-A failure.
            projection = CostAdjustedAccountProjection.from_evidence(
                snapshot, recognized_leg_assessments,
            )
            if required > projection.available_buying_power:
                def intent_sort_key(value: tuple[ExecutionResult, StreamKey]) -> tuple[object, ...]:
                    outcome, stream = value
                    identity = stream.identity
                    return (
                        outcome.order.strategy_id, outcome.order.strategy_version,
                        identity.market, identity.instrument, identity.segment,
                        identity.underlying or "",
                        "" if identity.expiry is None else identity.expiry.isoformat(),
                        "" if identity.strike is None else str(identity.strike),
                        identity.option_type or "", outcome.order.timeframe,
                        outcome.order.originating_timestamp, outcome.order.action,
                        str(outcome.order.quantity),
                    )

                evidence = tuple(
                    (
                        outcome.order.strategy_id, outcome.order.strategy_version,
                        stream.identity.market, stream.identity.instrument, stream.identity.segment,
                        stream.identity.underlying, stream.identity.expiry,
                        stream.identity.strike, stream.identity.option_type,
                        outcome.order.timeframe, outcome.order.originating_timestamp,
                        outcome.order.action, outcome.order.quantity,
                    )
                    for outcome, stream in sorted(group, key=intent_sort_key)
                )
                evidence_identity = CanonicalCodec.fingerprint("algofortis-slice14-capital-competition/v1", (("intents", evidence),))
                return StructuredFailureResult(
                    "algofortis-slice14-failure/v1", self._manifest.manifest_fingerprint,
                    "slice14.concurrent_capital_competition",
                    OrchestrationFailureCode.AMBIGUOUS_CONCURRENT_CAPITAL_COMPETITION,
                    evidence_identity, self._manifest.execution_policy_identity,
                )
        return None

    def _specification_for_stream(self, stream: StreamKey) -> InstrumentSpecification:
        try:
            return self._specifications[stream.identity]
        except KeyError as error:
            raise ValueError("declared stream has no instrument specification") from error


    @staticmethod
    def _strategy_data(binding: StrategyBinding, view: MarketDataView) -> Any:
        """Preserve the legacy shape only where a single instrument makes it unambiguous."""
        instruments = {stream.identity for stream in view.streams}
        if len(instruments) != 1:
            return view
        # The frozen legacy contract calls for timeframe-keyed DataFrames.
        import pandas as pd
        output = {}
        for stream, evidence in view.streams.items():
            output[stream.timeframe] = pd.DataFrame(
                [{"timestamp": bar.timestamp, "open": bar.open, "high": bar.high, "low": bar.low,
                  "close": bar.close, "volume": bar.volume, "is_synthetic": bar.is_synthetic}
                 for bar in evidence.history]
            )
        return output

    def _record_accepted_leg(self, ledger, sequence, result, snapshot, trades, assessments, leg_assessments, regimes, stream, entry_regimes, protective_book):
        """Record the single accepted economic leg and its P1-5 result evidence."""
        sequence += 1
        key = LedgerEventKey(self._manifest.manifest_fingerprint, sequence)
        record = ledger.record(key, result)
        leg = ledger.leg_for(key)
        if leg is None:
            raise ValueError("accepted accounting evidence did not yield an economic trade leg")
        if leg.role.value == "ENTRY" and self._regime_enabled:
            source = regimes.latest_before(stream, leg.execution_timestamp)
            if source is None:
                raise ValueError("accepted entry lacks legally available pre-fill regime evidence")
            entry_regimes.append(EntryRegimeSnapshot(
                key, stream, leg.execution_timestamp, REGIME_POLICY_ID,
                source.status, source.regime, source.fingerprint,
                "EntryRegimeSnapshot/v2", result.prior_snapshot.account_id,
            ))
        # The changed position key is authoritative even for a final exit,
        # where it no longer appears in the resulting snapshot.
        keys = set(result.prior_snapshot.positions) | set(result.resulting_snapshot.positions)
        changed = [item for item in keys if result.prior_snapshot.positions.get(item) != result.resulting_snapshot.positions.get(item)]
        if len(changed) != 1:
            raise ValueError("accepted economic evidence must affect one position key")
        if self._cost_schedules:
            identity = changed[0].identity
            spec = self._specifications[identity]
            assessment = CostCalculator().assess_leg(
                leg, account_id=result.prior_snapshot.account_id, currency=result.prior_snapshot.currency,
                instrument_identity=identity, contract_multiplier=spec.contract_multiplier,
                monetary_quantum=result.prior_snapshot.monetary_quantum, schedules=self._cost_schedules,
            )
            leg_assessments.append(assessment)
        # Portfolio's resulting snapshot is the sole authority for the
        # changed key.  The protective book may shrink/cancel protection from
        # that evidence, but never grows it or owns another position state.
        if protective_book is not None:
            protective_book.reconcile_position(changed[0], snapshot)
        if record is not None:
            trades.append(record)
            if self._cost_schedules:
                assessments.append(CostCalculator().compose_completed(
                    record, (item for item in leg_assessments
                             if item.leg_event_key in {leg.event_key for leg in (*record.entry_legs, *record.exit_legs)}),
                ))
        return sequence

    def _result(self, snapshot, requests, intents, orders, executions, accounting, trades, costs, failure, leg_costs=(), regime_evidence=(), entry_regimes=(), risk_rejections=(), order_lifecycle=(), entry_risk_rejections=(), protective_book=None):
        return OrchestrationResult(
            manifest=self._manifest,
            final_snapshot=snapshot, requests=tuple(requests), intents=tuple(intents), orders=tuple(orders),
            executions=tuple(executions), accounting=tuple(accounting), trades=tuple(trades),
            costs=tuple(costs), failure=failure, leg_costs=tuple(leg_costs),
            regime_evidence=tuple(regime_evidence),
            entry_regimes=tuple(entry_regimes),
            regime_enabled=self._regime_enabled,
            risk_rejections=tuple(risk_rejections),
            order_lifecycle=tuple(order_lifecycle),
            entry_risk_rejections=tuple(entry_risk_rejections),
            protective_book=protective_book,
        )

    def _calendar_for(self, profile: MarketProfile) -> WeekendCalendar:
        """Resolve the authoritative shared calendar for one profile; fail closed."""
        try:
            return self._calendars[profile.calendar_id]
        except KeyError:
            raise ValueError(f"no authoritative calendar for calendar_id {profile.calendar_id!r}") from None

    def _risk_day_for(self, stream: StreamKey, decision_time: datetime) -> RiskDay:
        """Account-level RiskDay from the authoritative MarketProfile calendar."""
        profile = self._profiles.resolve(stream)
        calendar = self._calendar_for(profile)
        boundary = MarketSessionBoundary(profile, calendar=calendar)
        return RiskDay(calendar_identity=profile.calendar_id, session_date=boundary.session_date(decision_time))

    def _release_commitment(self, entry_identity: str) -> None:
        """Release a pending risk commitment and its entry association."""
        self._commitments = tuple(value for value in self._commitments if value.entry_identity != entry_identity)
        self._entry_associations.pop(entry_identity, None)
        self._lifecycles.pop(entry_identity, None)

    @staticmethod
    def _mechanical_validity_reason(
        spec: EntryValiditySpec,
        decision_time: datetime,
        risk_day: RiskDay,
    ) -> str | None:
        """Engine-enforced mechanical EntryValiditySpec evaluation (Slice-1 fields).

        ``valid_until_timestamp``: opportunity time strictly before the
        boundary is valid; ``>=`` is mechanical expiry.  ``valid_through_session``:
        same authoritative calendar identity AND same session date required.
        The authoritative orchestration decision time and the existing
        MarketProfile/calendar/MarketSessionBoundary RiskDay authority are
        used -- never wall clock, never a UTC/local-midnight shortcut.
        Returns the deterministic mechanical reason or None when valid.
        """
        if spec.valid_until_timestamp is not None and decision_time >= spec.valid_until_timestamp:
            return "valid_until_reached"
        if spec.calendar_identity is not None and (
            risk_day.calendar_identity != spec.calendar_identity
            or risk_day.session_date != spec.session_date
        ):
            return "session_expired"
        return None

    def _terminal_lifecycle(
        self,
        entry_identity: str,
        state: OrderLifecycleState,
        cause_type: OrderLifecycleCauseType,
        cause_reference: str,
        decision_time: datetime,
    ) -> None:
        """Record one terminal lifecycle transition + its cause evidence.

        One authority per fact: the lifecycle layer mirrors the terminal state
        and references EXISTING authoritative evidence; it never recomputes
        reasons or formulas.  Only gate-approved pending entries have a
        lifecycle chain (initial RiskGate rejection creates no OrderRequest /
        no CREATED chain); a missing chain is skipped defensively.
        """
        lifecycle = self._lifecycles.get(entry_identity)
        if lifecycle is None:
            return
        if lifecycle.state is not OrderLifecycleState.QUEUED:
            raise ValueError(f"terminal lifecycle transition requires QUEUED, found {lifecycle.state.value}")
        self._lifecycles[entry_identity] = lifecycle.transition_to(state)
        self._lifecycle_events.append(OrderLifecycleEvent(
            entry_identity, state, cause_type, cause_reference, decision_time,
        ))
