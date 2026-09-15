"""Phase 3A/3B owner-locked production risk policy, sizing, and pre-order risk gate.

The RiskPolicy is the explicit Tier-1 production risk identity required by
architecture decision §30.5.  It deliberately does NOT reuse the temporary
``sentinelx-slice14-integration-quantity-policy/v1`` fixture, which is
prohibited as production Risk Management sizing policy.

Phase 3A (corrected): ``sentinelx-risk-policy/v3`` (v1/v2 legacy families) with
multiplier-aware Q64 sizing and runtime PositionKey ownership verification for
the STOP_LOSS/TARGET protective contract (LONG / BUY-TO-OPEN only).

Phase 3B-1: the deterministic pre-order ``RiskGate`` — account-level
``RiskGateState`` (daily loss baseline, daily trade count, RiskDay identity),
daily-loss gate (authoritative net-equity drawdown), daily trade-count gate,
max-open-positions gate (exact PositionKey counting), aggregate portfolio-risk
gate (fail-closed on missing/invalid stop evidence), Q60 same-direction
same-instrument overlap rejection, and the deterministic Q62 confidence
ranking helper.  Normal risk rejection is a structured result and never invokes
``alert_and_halt()``; exits and protective exits are never gated.

Phase 3B-2D: candidate protective evidence reconciliation.  For a NEW BUY
candidate, the authoritative STOP/TARGET price evidence is the strategy-owned
``PreEntryProtectivePlan`` bound to the exact intended PositionKey — never a
``ProtectiveExitBook`` lookup, never ``Signal.metadata``, never a synthesized
ProtectiveExit.  For EXISTING open positions, the authoritative risk evidence
remains the ACTIVE exact PositionKey-bound ``ProtectiveExitBook`` STOP_LOSS
(unchanged).  The gate never materializes runtime protection (no
``materialize_protective_plan``, no book mutation); runtime STOP/TARGET
instances are created only after an accepted entry fill, using the frozen
approved plan prices and the RiskGate-approved quantity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, localcontext
from enum import Enum
from typing import Iterable

from engine.costs import CostAdjustedAccountProjection
from engine.core.numeric import as_decimal
from engine.portfolio import AccountSnapshot, InstrumentIdentity, InstrumentSpecification, PositionKey
from engine.portfolio.model import INTERNAL_DECIMAL_CONTEXT
from engine.protective.runtime import ProtectiveExit, ProtectiveExitBook, ProtectiveExitKind, ProtectiveExitState
from engine.protective.plan import PreEntryProtectivePlan
from engine.reproducibility import CanonicalCodec


RISK_POLICY_SCHEMA = "sentinelx-risk-policy/v3"
RISK_POLICY_SCHEMA_V4 = "sentinelx-risk-policy/v4"
LEGACY_RISK_POLICY_SCHEMAS = ("sentinelx-risk-policy/v1", "sentinelx-risk-policy/v2")
RISK_CAPITAL_BASIS_FIXED_IDENTITY = "FixedCapitalBasis/v1"
RISK_CAPITAL_BASIS_COST_ADJUSTED_EQUITY_IDENTITY = "CostAdjustedEquityCapitalBasis/v1"
# The ONLY active RiskPolicy.version values.  Unknown/future versions fail
# closed at construction; the historical sentinelx-risk-policy/v1 and /v2
# schema identities never authorize active policy objects.
RISK_POLICY_VERSION_V3 = "risk-policy/v3"
RISK_POLICY_VERSION_V4 = "risk-policy/v4"
SUPPORTED_RISK_POLICY_VERSIONS = (RISK_POLICY_VERSION_V3, RISK_POLICY_VERSION_V4)
QUANTITY_NORMALIZATION_IDENTITY = "InstrumentQuantityNormalization/v1"
STOP_SOURCE_POLICY = "PROTECTIVE_EXIT_STOP_LOSS"
CAPITAL_ALLOCATION_FIXED = "FIXED"
FAILURE_SEMANTICS_REJECT = "REJECT"
CORRELATION_POLICY_IDENTITY = "Q60SameDirectionSameInstrument/v1"
CORRELATION_ACTION_REJECT = "REJECT"
SIGNAL_PRIORITY_POLICY_IDENTITY = "Q62ConfidenceScore/v1"
SIGNAL_PRIORITY_STRATEGY_SCOPED_POLICY_IDENTITY = "Q62StrategyScopedConfidence/v2"
DAILY_LOSS_MEASURE_IDENTITY = "NetEquityDrawdownRiskDay/v1"
RISK_DAY_POLICY_IDENTITY = "MarketSessionRiskDay/v1"
DAILY_TRADE_COUNT_POLICY_IDENTITY = "FirstEntryFillRiskDay/v1"
MISSING_RISK_EVIDENCE_POLICY_REJECT = "REJECT"
RR_ENTRY_REFERENCE_POLICY_IDENTITY = "DecisionTimeReferencePrice/v1"


class PositionDirection(str, Enum):
    """Authoritative phase-3 direction contract; never inferred from prices.

    LONG (BUY-TO-OPEN) is the only activated direction.  SHORT
    (SELL-TO-OPEN) is not activated and fails closed with
    ``unsupported_direction``.
    """

    LONG = "LONG"
    SHORT = "SHORT"


class RiskOutcome(str, Enum):
    """Structured fail-closed risk outcome, mirroring existing outcome enums."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class RiskDecision:
    """Deterministic structured sizing result with an explicit machine-readable reason."""

    outcome: RiskOutcome
    reason: str | None
    risk_capital: Decimal | None
    stop_distance: Decimal | None
    quantity: Decimal | None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, RiskOutcome):
            raise TypeError("outcome must be a RiskOutcome")
        if self.outcome is RiskOutcome.APPROVED:
            if self.reason is not None:
                raise ValueError("approved decision excludes a reason")
            if self.risk_capital is None or self.stop_distance is None or self.quantity is None:
                raise ValueError("approved decision requires risk capital, stop distance, and quantity")
        else:
            if self.reason is None or self.quantity is not None:
                raise ValueError("rejected decision requires a reason and excludes a quantity")


def _safe_decimal(value: object, field_name: str) -> Decimal | None:
    """Normalize an input or fail closed as missing/invalid; never route through float."""
    try:
        return as_decimal(value, field_name)
    except (TypeError, ValueError):
        return None


def _reject(reason: str) -> RiskDecision:
    return RiskDecision(RiskOutcome.REJECTED, reason, None, None, None)


@dataclass(frozen=True)
class RiskPolicy:
    """Owner-locked Phase 3A/3B production risk policy (backtest/paper trading).

    v3 binds the inherited Phase-3A sizing semantics plus all economically
    meaningful Phase-3B gate values and sub-policy identities.  ``v1`` and
    ``v2`` are legacy/non-comparable schema families and are never silently
    mutated or reused.

    v4 is the explicit next schema/version: it adds the
    ``risk_capital_basis_policy`` field, whose
    ``CostAdjustedEquityCapitalBasis/v1`` identity changes the Q55/Q59
    capital denominator from the fixed deployable capital to the
    authoritative cost-adjusted equity.  A v3-versioned policy is restricted
    to the fixed basis, so v3 economic semantics and fingerprints are
    preserved exactly.
    """

    version: str
    per_trade_risk_pct: Decimal | int | float | str = Decimal("0.005")
    max_daily_loss_pct: Decimal | int | float | str = Decimal("0.02")
    max_daily_trades: int = 10
    max_open_positions: int = 3
    max_portfolio_risk_pct: Decimal | int | float | str = Decimal("0.03")
    capital_allocation: str = CAPITAL_ALLOCATION_FIXED
    min_risk_reward: Decimal | int | float | str = Decimal("1.5")
    stop_source: str = STOP_SOURCE_POLICY
    failure_semantics: str = FAILURE_SEMANTICS_REJECT
    quantity_normalization: str = QUANTITY_NORMALIZATION_IDENTITY
    correlation_policy: str = CORRELATION_POLICY_IDENTITY
    correlation_action: str = CORRELATION_ACTION_REJECT
    signal_priority_policy: str = SIGNAL_PRIORITY_STRATEGY_SCOPED_POLICY_IDENTITY
    daily_loss_measure: str = DAILY_LOSS_MEASURE_IDENTITY
    risk_day_policy: str = RISK_DAY_POLICY_IDENTITY
    daily_trade_count_policy: str = DAILY_TRADE_COUNT_POLICY_IDENTITY
    missing_risk_evidence_policy: str = MISSING_RISK_EVIDENCE_POLICY_REJECT
    rr_entry_reference_policy: str = RR_ENTRY_REFERENCE_POLICY_IDENTITY
    risk_capital_basis_policy: str = RISK_CAPITAL_BASIS_FIXED_IDENTITY

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("version must be a non-empty string")
        object.__setattr__(self, "version", self.version.strip())
        if self.version not in SUPPORTED_RISK_POLICY_VERSIONS:
            raise ValueError("unsupported RiskPolicy version")
        per_trade = as_decimal(self.per_trade_risk_pct, "per_trade_risk_pct")
        if per_trade <= 0 or per_trade >= 1:
            raise ValueError("per_trade_risk_pct must be a fraction in (0, 1)")
        object.__setattr__(self, "per_trade_risk_pct", per_trade)
        daily_loss = as_decimal(self.max_daily_loss_pct, "max_daily_loss_pct")
        if daily_loss <= 0 or daily_loss >= 1:
            raise ValueError("max_daily_loss_pct must be a fraction in (0, 1)")
        object.__setattr__(self, "max_daily_loss_pct", daily_loss)
        portfolio_risk = as_decimal(self.max_portfolio_risk_pct, "max_portfolio_risk_pct")
        if portfolio_risk <= 0 or portfolio_risk >= 1:
            raise ValueError("max_portfolio_risk_pct must be a fraction in (0, 1)")
        object.__setattr__(self, "max_portfolio_risk_pct", portfolio_risk)
        if not isinstance(self.max_daily_trades, int) or isinstance(self.max_daily_trades, bool) or self.max_daily_trades < 1:
            raise ValueError("max_daily_trades must be a positive integer")
        if not isinstance(self.max_open_positions, int) or isinstance(self.max_open_positions, bool) or self.max_open_positions < 1:
            raise ValueError("max_open_positions must be a positive integer")
        min_reward = as_decimal(self.min_risk_reward, "min_risk_reward")
        if min_reward <= 0:
            raise ValueError("min_risk_reward must be positive")
        object.__setattr__(self, "min_risk_reward", min_reward)
        if self.capital_allocation != CAPITAL_ALLOCATION_FIXED:
            raise ValueError("Phase 3A supports only the owner-locked FIXED capital allocation")
        if self.stop_source != STOP_SOURCE_POLICY:
            raise ValueError("Phase 3A stop source must be the authoritative ProtectiveExit STOP_LOSS contract")
        if self.failure_semantics != FAILURE_SEMANTICS_REJECT:
            raise ValueError("Phase 3A failure semantics must be the owner-locked structured REJECT")
        if self.correlation_action != CORRELATION_ACTION_REJECT:
            raise ValueError("Q60 correlation action must be the owner-locked REJECT")
        if self.missing_risk_evidence_policy != MISSING_RISK_EVIDENCE_POLICY_REJECT:
            raise ValueError("missing-risk-evidence policy must be the owner-locked REJECT")
        if self.risk_capital_basis_policy not in (
            RISK_CAPITAL_BASIS_FIXED_IDENTITY,
            RISK_CAPITAL_BASIS_COST_ADJUSTED_EQUITY_IDENTITY,
        ):
            raise ValueError("risk_capital_basis_policy must be an explicit locked capital-basis identity")
        if self.version == RISK_POLICY_VERSION_V3 and self.risk_capital_basis_policy != RISK_CAPITAL_BASIS_FIXED_IDENTITY:
            raise ValueError("pre-v4 risk policies support only the fixed capital basis")
        for name in ("quantity_normalization", "correlation_policy", "signal_priority_policy",
                     "daily_loss_measure", "risk_day_policy", "daily_trade_count_policy",
                     "rr_entry_reference_policy", "risk_capital_basis_policy"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")

    @property
    def fingerprint(self) -> str:
        """Explicit Tier-1 risk policy identity, replay-comparable within its schema family.

        ``sentinelx-risk-policy/v1`` and ``/v2`` are legacy/non-comparable
        families; v3 adds the Phase-3B gate values; v4 adds the explicit
        risk-capital-basis policy (``CostAdjustedEquityCapitalBasis/v1``
        changes the Q55/Q59 capital denominator), so no cross-family
        comparison is valid.  A v3-versioned policy fingerprint is
        byte-identical to the pre-v4 identity: the capital-basis field
        participates in the fingerprint only under the v4 schema.
        """
        v4 = self.version == RISK_POLICY_VERSION_V4
        fields = (
            ("version", self.version),
            ("per_trade_risk_pct", self.per_trade_risk_pct),
            ("max_daily_loss_pct", self.max_daily_loss_pct),
            ("max_daily_trades", self.max_daily_trades),
            ("max_open_positions", self.max_open_positions),
            ("max_portfolio_risk_pct", self.max_portfolio_risk_pct),
            ("capital_allocation", self.capital_allocation),
            ("min_risk_reward", self.min_risk_reward),
            ("stop_source", self.stop_source),
            ("failure_semantics", self.failure_semantics),
            ("quantity_normalization", self.quantity_normalization),
            ("correlation_policy", self.correlation_policy),
            ("correlation_action", self.correlation_action),
            ("signal_priority_policy", self.signal_priority_policy),
            ("daily_loss_measure", self.daily_loss_measure),
            ("risk_day_policy", self.risk_day_policy),
            ("daily_trade_count_policy", self.daily_trade_count_policy),
            ("missing_risk_evidence_policy", self.missing_risk_evidence_policy),
            ("rr_entry_reference_policy", self.rr_entry_reference_policy),
        )
        if v4:
            fields = (*fields, ("risk_capital_basis_policy", self.risk_capital_basis_policy))
        return CanonicalCodec.fingerprint(RISK_POLICY_SCHEMA_V4 if v4 else RISK_POLICY_SCHEMA, fields)


class RiskManager:
    """Owner-locked Q64 fixed-fractional sizing; fail-closed by default.

    The sizing input carries an explicit authoritative intended ``PositionKey``
    and an explicit authoritative ``PositionDirection``.  PositionKey ownership
    is runtime-verified (never caller-trusted): the supplied STOP_LOSS (and,
    when the trade plan includes one, TARGET) ProtectiveExit must bind exactly
    the intended PositionKey, and that key's InstrumentIdentity must equal the
    authoritative ``InstrumentSpecification`` identity.
    """

    def __init__(self, policy: RiskPolicy) -> None:
        if not isinstance(policy, RiskPolicy):
            raise TypeError("policy must be a RiskPolicy")
        self._policy = policy

    @property
    def policy(self) -> RiskPolicy:
        return self._policy

    def size_position(
        self,
        *,
        direction: PositionDirection,
        intended_position_key: PositionKey,
        capital: object,
        entry_price: object,
        protective_stop: ProtectiveExit,
        specification: InstrumentSpecification,
        protective_target: ProtectiveExit | None = None,
        require_risk_reward: bool = False,
    ) -> RiskDecision:
        """Apply the frozen multiplier-aware Q64 formula with exact Decimal arithmetic.

        Authoritative LONG / BUY-TO-OPEN contract::

            risk_distance      = entry_price - stop_price          (stop < entry)
            risk_per_quantity  = risk_distance × contract_multiplier
            risk_capital       = capital × policy.per_trade_risk_pct
            raw_quantity       = risk_capital / risk_per_quantity
            normalized_quantity = floor(raw_quantity, quantity_step)

        The stop is consumed from the strategy-owned / PositionKey-bound
        STOP_LOSS ProtectiveExit contract; no stop is invented and no
        Signal.metadata/ATR/percentage fallback exists.  Invalid geometry is
        rejected BEFORE division; ``abs()`` is never used to repair an invalid
        directional placement.  Missing/invalid inputs fail closed with a
        structured REJECT.  The Q64 / R:R mathematics are shared with
        ``size_position_from_plan`` via ``_size_from_prices``.
        """
        if not isinstance(direction, PositionDirection):
            raise TypeError("direction must be a PositionDirection")
        if not isinstance(intended_position_key, PositionKey):
            raise TypeError("intended_position_key must be a PositionKey")
        if not isinstance(specification, InstrumentSpecification):
            raise TypeError("specification must be an InstrumentSpecification")
        if direction is PositionDirection.SHORT:
            return _reject("unsupported_direction")
        if not isinstance(protective_stop, ProtectiveExit) or protective_stop.kind is not ProtectiveExitKind.STOP_LOSS or protective_stop.state is not ProtectiveExitState.ACTIVE:
            return _reject("missing_authoritative_stop")
        if protective_stop.position_key != intended_position_key:
            return _reject("stop_position_key_mismatch")
        if protective_stop.position_key.identity != specification.identity:
            return _reject("stop_instrument_mismatch")

        capital_value = _safe_decimal(capital, "capital")
        if capital_value is None:
            return _reject("missing_or_invalid_capital")
        if capital_value <= 0:
            return _reject("non_positive_capital")
        entry_value = _safe_decimal(entry_price, "entry_price")
        if entry_value is None or entry_value <= 0:
            return _reject("missing_or_invalid_entry_price")
        stop_value = _safe_decimal(protective_stop.exit_order.stop_price, "stop_price")
        if stop_value is None or stop_value <= 0:
            return _reject("missing_authoritative_stop")

        if protective_target is not None:
            if not isinstance(protective_target, ProtectiveExit) or protective_target.kind is not ProtectiveExitKind.TARGET or protective_target.state is not ProtectiveExitState.ACTIVE:
                return _reject("missing_authoritative_target")
            if protective_target.position_key.identity != specification.identity:
                return _reject("target_instrument_mismatch")
            if protective_target.position_key != intended_position_key:
                return _reject("target_position_key_mismatch")
            target_value = _safe_decimal(protective_target.exit_order.limit_price, "target_price")
            if target_value is None or target_value <= 0:
                return _reject("missing_authoritative_target")
        else:
            target_value = None
        return self._size_from_prices(
            capital_value=capital_value,
            entry_value=entry_value,
            stop_value=stop_value,
            target_value=target_value,
            specification=specification,
            require_risk_reward=require_risk_reward,
        )

    def size_position_from_plan(
        self,
        *,
        direction: PositionDirection,
        intended_position_key: PositionKey,
        capital: object,
        entry_price: object,
        candidate_plan: PreEntryProtectivePlan,
        specification: InstrumentSpecification,
        require_risk_reward: bool = True,
    ) -> RiskDecision:
        """Phase 3B-2D candidate sizing from the strategy-owned pre-entry plan.

        The candidate STOP/TARGET prices come from the exact PositionKey-bound
        ``PreEntryProtectivePlan`` (never ``Signal.metadata``, never a
        synthesized ProtectiveExit, never a ``ProtectiveExitBook`` lookup, and
        the plan is never inserted into a book).        Fail-closed validation: the plan must be present, bind the exact
        intended PositionKey, match the authoritative specification identity,
        and carry a concrete positive STOP price (and, when present, a
        concrete positive TARGET price).  A targetless plan
        (``target_price=None``) is REPRESENTABLE but fails closed with
        ``missing_authoritative_target`` when R:R eligibility is required
        (``require_risk_reward=True``).  The frozen Q64 / R:R mathematics are
        shared with ``size_position`` via ``_size_from_prices``.
        """
        if not isinstance(direction, PositionDirection):
            raise TypeError("direction must be a PositionDirection")
        if not isinstance(intended_position_key, PositionKey):
            raise TypeError("intended_position_key must be a PositionKey")
        if not isinstance(specification, InstrumentSpecification):
            raise TypeError("specification must be an InstrumentSpecification")
        if direction is PositionDirection.SHORT:
            return _reject("unsupported_direction")
        if not isinstance(candidate_plan, PreEntryProtectivePlan):
            return _reject("missing_candidate_plan")
        if candidate_plan.intended_position_key != intended_position_key:
            return _reject("candidate_plan_position_key_mismatch")
        if candidate_plan.intended_position_key.identity != specification.identity:
            return _reject("candidate_plan_instrument_mismatch")

        capital_value = _safe_decimal(capital, "capital")
        if capital_value is None:
            return _reject("missing_or_invalid_capital")
        if capital_value <= 0:
            return _reject("non_positive_capital")
        entry_value = _safe_decimal(entry_price, "entry_price")
        if entry_value is None or entry_value <= 0:
            return _reject("missing_or_invalid_entry_price")
        stop_value = _safe_decimal(candidate_plan.stop_price, "stop_price")
        if stop_value is None or stop_value <= 0:
            return _reject("missing_authoritative_stop")
        target_value = _safe_decimal(candidate_plan.target_price, "target_price")
        if target_value is None or target_value <= 0:
            return _reject("missing_authoritative_target")
        return self._size_from_prices(
            capital_value=capital_value,
            entry_value=entry_value,
            stop_value=stop_value,
            target_value=target_value,
            specification=specification,
            require_risk_reward=require_risk_reward,
        )

    def _size_from_prices(
        self,
        *,
        capital_value: Decimal,
        entry_value: Decimal,
        stop_value: Decimal,
        target_value: Decimal | None,
        specification: InstrumentSpecification,
        require_risk_reward: bool,
    ) -> RiskDecision:
        """Shared frozen Q64 sizing and LONG R:R mathematics over concrete prices.

        LONG stop geometry is enforced directionally; ``abs()`` never repairs
        an invalid placement and division happens only after the invariants
        pass.  Floor-to-step normalization can never increase the risk budget.
        Returns the structured APPROVED sizing result or a deterministic REJECT.
        """
        if stop_value >= entry_value:
            return _reject("invalid_stop_placement")
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            risk_distance = entry_value - stop_value
            if not risk_distance.is_finite() or risk_distance <= 0:
                return _reject("invalid_stop_placement")
            risk_per_quantity = risk_distance * specification.contract_multiplier
            if not risk_per_quantity.is_finite() or risk_per_quantity <= 0:
                return _reject("invalid_risk_per_quantity")
            risk_capital = capital_value * self._policy.per_trade_risk_pct
            raw_quantity = risk_capital / risk_per_quantity
            # Floor to the authoritative quantity step; never round to nearest,
            # so normalization can never increase the risk budget.
            normalized = (raw_quantity // specification.quantity_step) * specification.quantity_step
        if normalized <= 0 or normalized < specification.minimum_quantity:
            return _reject("quantity_below_minimum_quantity")
        if target_value is not None:
            eligibility = self._risk_reward_from_prices(entry_value, risk_distance, target_value)
            if eligibility is not None:
                return eligibility
        elif require_risk_reward:
            return _reject("missing_authoritative_target")
        return RiskDecision(RiskOutcome.APPROVED, None, risk_capital, risk_distance, normalized)

    def _risk_reward_from_prices(
        self, entry_value: Decimal, risk_distance: Decimal, target_value: Decimal,
    ) -> RiskDecision | None:
        """LONG R:R eligibility over concrete prices (``stop < entry < target``).

        Returns ``None`` when eligible, otherwise a deterministic structured
        REJECT.  OCO membership is NOT required: PositionKey symmetry (already
        verified by the caller path) is the authoritative ownership proof.
        """
        if target_value <= entry_value:
            return _reject("invalid_target_placement")
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            reward_distance = target_value - entry_value
            if not reward_distance.is_finite() or reward_distance <= 0:
                return _reject("invalid_target_placement")
            risk_reward = reward_distance / risk_distance
        if risk_reward < self._policy.min_risk_reward:
            return _reject("risk_reward_below_minimum")
        return None


@dataclass(frozen=True)
class RiskDay:
    """Authoritative account-level risk-day identity from the deployment calendar.

    Derived from the deployment's authoritative market calendar, timezone, and
    regular trading session boundary (MarketProfile owns session/calendar
    interpretation).  Conflicting calendar identities across instruments fail
    closed as invalid risk configuration/evidence.  Local-machine midnight and
    UTC midnight are never the risk-day basis unless explicitly the deployment
    RiskDay.
    """

    calendar_identity: str
    session_date: date

    def __post_init__(self) -> None:
        if not isinstance(self.calendar_identity, str) or not self.calendar_identity.strip():
            raise ValueError("calendar_identity must be a non-empty string")
        if not isinstance(self.session_date, date) or isinstance(self.session_date, datetime):
            raise TypeError("session_date must be a plain date")
        object.__setattr__(self, "calendar_identity", self.calendar_identity.strip())


@dataclass(frozen=True)
class RiskGateState:
    """Immutable account-level daily risk state, derived from authoritative evidence.

    ``start_of_day_net_equity`` is the fixed daily-loss baseline for the
    RiskDay (never rebased intraday); ``current_net_equity`` is the latest
    authoritative net equity (realized + unrealized + already-recognized costs;
    slippage is already inside authoritative fill prices).  Daily trade count
    increments exactly once per logical entry order on its first non-zero entry
    fill; the same entry identity never increments again.
    """

    risk_day: RiskDay
    start_of_day_net_equity: Decimal | int | float | str
    current_net_equity: Decimal | int | float | str
    daily_trade_count: int
    _filled_entry_identities: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.risk_day, RiskDay):
            raise TypeError("risk_day must be a RiskDay")
        start = as_decimal(self.start_of_day_net_equity, "start_of_day_net_equity")
        current = as_decimal(self.current_net_equity, "current_net_equity")
        if start < 0 or current < 0:
            raise ValueError("net equity values cannot be negative")
        if not isinstance(self.daily_trade_count, int) or isinstance(self.daily_trade_count, bool) or self.daily_trade_count < 0:
            raise ValueError("daily_trade_count must be a non-negative integer")
        identities = frozenset(self._filled_entry_identities)
        if not all(isinstance(value, str) and value for value in identities):
            raise ValueError("filled entry identities must be non-empty strings")
        object.__setattr__(self, "start_of_day_net_equity", start)
        object.__setattr__(self, "current_net_equity", current)
        object.__setattr__(self, "_filled_entry_identities", identities)

    def record_entry_fill(self, entry_identity: str) -> "RiskGateState":
        """Count the first non-zero fill of one logical entry order exactly once."""
        if not isinstance(entry_identity, str) or not entry_identity:
            raise ValueError("entry_identity must be a non-empty string")
        if entry_identity in self._filled_entry_identities:
            return self
        return RiskGateState(
            self.risk_day, self.start_of_day_net_equity, self.current_net_equity,
            self.daily_trade_count + 1, self._filled_entry_identities | {entry_identity},
        )


@dataclass(frozen=True)
class RiskGateResult:
    """Deterministic risk-gate outcome with the evaluation state.

    ``quantity`` (approved sizing) and ``nominal_stop_risk`` (the gate-computed
    candidate risk ``approved_quantity × stop_distance × contract_multiplier``)
    are both present on APPROVED SIZING results and both None on
    authorization-only APPROVED results and on REJECTED results.  Callers
    never recompute nominal stop-risk; the gate remains its sole calculator.
    """

    outcome: RiskOutcome
    reason: str | None
    state: RiskGateState | None
    quantity: Decimal | None = None
    nominal_stop_risk: Decimal | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, RiskOutcome):
            raise TypeError("outcome must be a RiskOutcome")
        if self.state is not None and not isinstance(self.state, RiskGateState):
            raise TypeError("state must be a RiskGateState")
        if self.outcome is RiskOutcome.APPROVED:
            if self.reason is not None or self.state is None:
                raise ValueError("approved gate result requires state and excludes a reason")
            if (self.quantity is None) != (self.nominal_stop_risk is None):
                raise ValueError("approved gate result requires quantity and nominal_stop_risk together (sizing results) or neither (authorization-only results)")
        else:
            if self.reason is None or self.quantity is not None or self.nominal_stop_risk is not None:
                raise ValueError("rejected gate result requires a reason and excludes quantity and nominal_stop_risk")


@dataclass(frozen=True)
class PendingRiskCommitment:
    """Risk-layer reservation for a gate-approved but not-yet-filled BUY entry.

    This is NOT an economic position: it never enters ``AccountSnapshot``
    positions, cash, realized/unrealized P&L, ``TradeLedger``, daily trade
    count, or ``ProtectiveExitBook``.  It exists only so the RiskGate can
    reserve max-position slots, aggregate nominal stop-risk, and Q60 identity
    overlap while the OrderRequest remains pending.  ``nominal_stop_risk`` is
    the gate-computed candidate risk at approval and is never recomputed by
    callers; ``entry_identity`` is the deterministic
    ``sentinelx-entry-intent/v1`` logical entry identity.
    """

    entry_identity: str
    intended_position_key: PositionKey
    approved_quantity: Decimal | int | float | str
    nominal_stop_risk: Decimal | int | float | str

    def __post_init__(self) -> None:
        if not isinstance(self.entry_identity, str) or not self.entry_identity.strip():
            raise ValueError("entry_identity must be a non-empty string")
        if not isinstance(self.intended_position_key, PositionKey):
            raise TypeError("intended_position_key must be a PositionKey")
        quantity = as_decimal(self.approved_quantity, "approved_quantity")
        if quantity <= 0:
            raise ValueError("approved_quantity must be positive")
        object.__setattr__(self, "approved_quantity", quantity)
        risk = as_decimal(self.nominal_stop_risk, "nominal_stop_risk")
        if risk <= 0:
            raise ValueError("nominal_stop_risk must be positive")
        object.__setattr__(self, "nominal_stop_risk", risk)


class RiskGate:
    """Deterministic pre-order risk gate over the corrected Phase 3A contracts.

    **Phase 3B-1 is explicitly LONG / BUY-TO-OPEN ONLY.**  All R:R and
    portfolio-risk geometry is intentionally LONG-only (``STOP < ENTRY <
    TARGET`` with positive risk/reward distances).  SHORT / SELL-TO-OPEN is
    NOT active: an authoritative SHORT direction is a structured
    ``unsupported_direction`` REJECT — the gate never evaluates a short-side
    formula, never infers side from price ordering, never uses ``abs()``, and
    never auto-swaps STOP/TARGET.  Future short support requires a separately
    owner-approved policy/contract extension.

    The gate evaluates one NEW risk-bearing entry candidate and returns
    APPROVED with the sized quantity or REJECTED with an explicit machine-
    readable reason.  Normal risk rejection never invokes ``alert_and_halt()``
    (fatal engine/invariant failures remain under the separate halt contract).
    Exits / protective exits / position reductions are never evaluated by this
    entry gate and therefore remain permitted under any daily limit.

    Same-PositionKey interaction: a candidate targeting an already-open exact
    PositionKey does NOT consume an additional max-open-position slot (it is
    not a new PositionKey), but under the current LONG-only Q60 policy it
    still fails later with ``correlation_conflict`` (existing open LONG
    exposure on the exact same InstrumentIdentity).  The max-position
    exemption is NOT permission to pyramid / average in / scale in / add to
    existing LONG exposure.  The branch is reachable and explicit for semantic
    correctness and future versioned policy changes.
    """

    def __init__(self, policy: RiskPolicy) -> None:
        if not isinstance(policy, RiskPolicy):
            raise TypeError("policy must be a RiskPolicy")
        self._policy = policy
        self._manager = RiskManager(policy)

    @property
    def policy(self) -> RiskPolicy:
        return self._policy

    def evaluate_pre_order(
        self,
        *,
        direction: PositionDirection,
        intended_position_key: PositionKey,
        capital: object,
        entry_price: object,
        specification: InstrumentSpecification,
        snapshot: AccountSnapshot,
        book: ProtectiveExitBook,
        candidate_plan: PreEntryProtectivePlan | None = None,
        risk_day: RiskDay,
        current_net_equity: object,
        starting_capital: object,
        prior_state: RiskGateState | None = None,
        pending_commitments: tuple[PendingRiskCommitment, ...] = (),
        cost_projection: CostAdjustedAccountProjection | None = None,
    ) -> RiskGateResult:
        """Evaluate one new entry candidate through the frozen 15-step pipeline.

        Pipeline: direction → candidate STOP/TARGET evidence (the exact
        PositionKey-bound ``PreEntryProtectivePlan``) → LONG geometry → R:R →
        corrected Q64 sizing → candidate risk → daily-loss gate →
        daily-trade-count gate (actual fills + active pending-entry
        reservations) → max-open-positions gate → aggregate portfolio-risk
        gate → Q60 same-direction same-instrument conflict gate.

        Candidate evidence contract (Phase 3B-2D): for a NEW BUY candidate the
        authoritative STOP/TARGET prices come from ``candidate_plan`` — never a
        ``ProtectiveExitBook`` lookup, never ``Signal.metadata``, never a
        synthesized ProtectiveExit.  The plan is never inserted into ``book``
        and the gate never materializes runtime protection.  A candidate plan
        may legitimately carry ``target_price=None`` (target-optional
        representation); because the current RiskPolicy still requires minimum
        R:R 1.5, such a candidate fails closed at R:R policy eligibility with
        ``missing_authoritative_target`` — the gate never invents, synthesizes,
        or substitutes a target.  For EXISTING open positions, the
        authoritative risk evidence remains the ACTIVE exact PositionKey-bound
        ``ProtectiveExitBook`` STOP_LOSS (unchanged).  A REJECT leaves
        ``book``, ``PortfolioAccount``, execution, and orders unchanged.

        Capital for sizing and the portfolio-risk budget is the SAME
        authoritative deployable-capital input under the v3 fixed basis
        (``FixedCapitalBasis/v1``).  Under RiskPolicy v4's explicit
        ``CostAdjustedEquityCapitalBasis/v1``, the authoritative
        ``CostAdjustedAccountProjection.cost_adjusted_equity`` (recognized
        costs only — never candidate costs, so no sizing circularity) is the
        Q55/Q59 denominator; the gate consumes the projection as evidence and
        never computes costs itself.  Daily-loss evidence (``start_of_day_net_equity`` /
        ``current_net_equity``) is a separate contract and is never changed by
        the capital basis.
        """
        if not isinstance(direction, PositionDirection):
            raise TypeError("direction must be a PositionDirection")
        if not isinstance(intended_position_key, PositionKey):
            raise TypeError("intended_position_key must be a PositionKey")
        if not isinstance(specification, InstrumentSpecification):
            raise TypeError("specification must be an InstrumentSpecification")
        if not isinstance(snapshot, AccountSnapshot):
            raise TypeError("snapshot must be an AccountSnapshot")
        if not isinstance(book, ProtectiveExitBook):
            raise TypeError("book must be a ProtectiveExitBook")
        if not isinstance(risk_day, RiskDay):
            raise TypeError("risk_day must be a RiskDay")

        state = self._derive_state(prior_state, risk_day, current_net_equity, starting_capital)
        if state is None:
            return RiskGateResult(RiskOutcome.REJECTED, "invalid_risk_evidence", prior_state)

        commitments = tuple(pending_commitments)
        if not all(isinstance(value, PendingRiskCommitment) for value in commitments):
            return RiskGateResult(RiskOutcome.REJECTED, "invalid_pending_commitments", state)
        if len({value.entry_identity for value in commitments}) != len(commitments):
            return RiskGateResult(RiskOutcome.REJECTED, "duplicate_pending_commitment", state)

        if direction is PositionDirection.SHORT:
            return RiskGateResult(RiskOutcome.REJECTED, "unsupported_direction", state)
        if not isinstance(candidate_plan, PreEntryProtectivePlan):
            return RiskGateResult(RiskOutcome.REJECTED, "missing_candidate_plan", state)

        # Capital-basis dispatch (RiskPolicy v4): the v3 fixed basis sizes
        # Q55 and the Q59 portfolio budget against the authoritative
        # deployable-capital input unchanged; the v4
        # CostAdjustedEquityCapitalBasis/v1 policy sizes both against the
        # authoritative cost-adjusted equity evidence (recognized costs only).
        # The gate consumes the projection as evidence and never reproduces
        # cost math; a missing/invalid projection fails closed before sizing.
        cost_basis = self._policy.risk_capital_basis_policy == RISK_CAPITAL_BASIS_COST_ADJUSTED_EQUITY_IDENTITY
        if cost_basis:
            resolved_capital, basis_reason = self._cost_adjusted_capital(cost_projection)
            if resolved_capital is None:
                return RiskGateResult(RiskOutcome.REJECTED, basis_reason, state)

        sizing = self._manager.size_position_from_plan(
            direction=direction,
            intended_position_key=intended_position_key,
            capital=resolved_capital if cost_basis else capital,
            entry_price=entry_price,
            candidate_plan=candidate_plan,
            specification=specification,
            require_risk_reward=True,
        )
        if sizing.outcome is not RiskOutcome.APPROVED:
            return RiskGateResult(RiskOutcome.REJECTED, sizing.reason, state)

        if cost_basis:
            capital_value = resolved_capital
        else:
            capital_value = _safe_decimal(capital, "capital")
            if capital_value is None or capital_value <= 0:
                return RiskGateResult(RiskOutcome.REJECTED, "missing_or_invalid_capital", state)

        # 8. Daily-loss gate: authoritative net-equity drawdown against the
        # fixed RiskDay baseline (never rebased intraday).  Shared with the
        # pending-entry pre-execution authorization so the two Q56 paths
        # cannot drift (single formula, one owner).
        if self._daily_loss_breach(state):
            return RiskGateResult(RiskOutcome.REJECTED, "daily_loss_limit_exceeded", state)

        # 9. Daily trade-count gate: max_daily_trades is a HARD account-level
        # cap on first accepted logical entry fills per RiskDay.  Approval is
        # NOT a trade and PendingRiskCommitment values never increment
        # ``state.daily_trade_count``, but every active validated pending
        # commitment reserves exactly ONE future logical entry-fill slot, so
        # eligibility requires:
        #     state.daily_trade_count + pending_entry_reservations
        #     < policy.max_daily_trades
        # The candidate itself is not included until approved.  Reservations
        # persist across RiskDay boundaries (a new RiskDay resets the actual
        # daily count via _derive_state/advance_state but pending commitments
        # are not reset) until the commitment is terminally released (expiry,
        # rejection, or accepted fill converting the reservation into an
        # actual entry-fill count).  This closes the falsified bypass where
        # multiple pre-approved pending entries could all fill on one RiskDay
        # and exceed the configured cap.
        reserved_entry_slots = len(commitments)
        if state.daily_trade_count + reserved_entry_slots >= self._policy.max_daily_trades:
            return RiskGateResult(RiskOutcome.REJECTED, "daily_trade_count_exceeded", state)

        # 10. Max-open-positions gate: exact PositionKey counting.  A pending
        # approved commitment reserves its future slot: effective open keys are
        # actual snapshot positions plus unique pending-commitment keys.  A
        # candidate that creates neither a new real nor a new committed key
        # does not consume a slot.
        committed_keys = {value.intended_position_key for value in commitments}
        creates_new_position = intended_position_key not in snapshot.positions and intended_position_key not in committed_keys
        if creates_new_position and len(snapshot.positions) + len(committed_keys) >= self._policy.max_open_positions:
            return RiskGateResult(RiskOutcome.REJECTED, "max_open_positions_exceeded", state)

        # 11. Aggregate portfolio-risk gate.  Every open LONG position must
        # have exactly one valid ACTIVE PositionKey-bound STOP_LOSS; otherwise
        # aggregate risk cannot be proven and new entries fail closed.
        existing_open_risk, evidence_failure = self._existing_open_risk(snapshot, book)
        if evidence_failure is not None:
            return RiskGateResult(RiskOutcome.REJECTED, evidence_failure, state)
        # candidate_trade_risk is admitted to the aggregate ONLY from the
        # successful, directionally-valid RiskManager sizing result above
        # (LONG direction, STOP/TARGET ownership, STOP < ENTRY < TARGET,
        # positive risk_distance, R:R eligibility, multiplier-aware sizing).
        # A candidate that did not pass directional geometry validation never
        # reaches aggregate portfolio-risk computation; if pipeline order ever
        # changes, candidate geometry must be independently re-verified first.
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            pending_risk = sum((value.nominal_stop_risk for value in commitments), Decimal("0"))
            candidate_trade_risk = sizing.quantity * sizing.stop_distance * specification.contract_multiplier
            aggregate_post_trade_risk = existing_open_risk + pending_risk + candidate_trade_risk
            portfolio_budget = capital_value * self._policy.max_portfolio_risk_pct
        if aggregate_post_trade_risk > portfolio_budget:
            return RiskGateResult(RiskOutcome.REJECTED, "portfolio_risk_exceeded", state)

        # 12. Q60 same-direction same-instrument overlap (LONG-only scope):
        # any existing open position OR pending approved commitment on the
        # exact canonical InstrumentIdentity conflicts with a new LONG
        # candidate on that identity.
        if (
            any(key.identity == intended_position_key.identity for key in snapshot.positions)
            or any(value.intended_position_key.identity == intended_position_key.identity for value in commitments)
        ):
            return RiskGateResult(RiskOutcome.REJECTED, "correlation_conflict", state)

        # The gate never materializes runtime protection: no
        # materialize_protective_plan call, no book mutation, no OrderRequest,
        # no protective-lifecycle/PortfolioAccount change.  It returns its
        # normal APPROVED result with the gate-computed nominal stop-risk;
        # runtime STOP/TARGET instances are created only after an accepted
        # entry fill by later orchestration wiring.
        return RiskGateResult(RiskOutcome.APPROVED, None, state, sizing.quantity, nominal_stop_risk=candidate_trade_risk)

    def evaluate_pending_entry_pre_execution(
        self,
        *,
        risk_day: RiskDay,
        current_net_equity: object,
        starting_capital: object,
        prior_state: RiskGateState | None,
    ) -> RiskGateResult:
        """Dynamic Q56-only authorization for an already-approved pending BUY.

        Q56 is a DYNAMIC account-level hard entry permission: an approval made
        at T1 is NOT permanent authorization to create new risk.  If the
        account has subsequently reached the daily-loss threshold before the
        pending entry becomes executable, the entry must not create a new
        position.  Existing exits remain allowed and are never evaluated here.

        This performs NO sizing and NO other strategy/order calculations: the
        pending order already carries its approved quantity, frozen entry
        identity, PendingRiskCommitment, frozen protective plan, planned order
        terms, and Q55/Q57/Q58/Q59/Q60 reservations.  The ONLY question is
        whether Q56 still authorizes new risk right now, against the CURRENT
        authoritative cost-inclusive net equity supplied by the caller (the
        orchestrator computes it via ``CostAdjustedAccountProjection``; the
        accounting snapshot itself remains gross and recognized costs are
        applied exactly once).  Uses the shared ``_daily_loss_breach`` formula
        so this path can never drift from ``evaluate_pre_order``; returns the
        existing ``RiskGateResult`` semantics with the existing reason
        ``daily_loss_limit_exceeded``.
        """
        state = self._derive_state(prior_state, risk_day, current_net_equity, starting_capital)
        if state is None:
            return RiskGateResult(RiskOutcome.REJECTED, "invalid_risk_evidence", prior_state)
        if self._daily_loss_breach(state):
            return RiskGateResult(RiskOutcome.REJECTED, "daily_loss_limit_exceeded", state)
        return RiskGateResult(RiskOutcome.APPROVED, None, state)

    def _daily_loss_breach(self, state: RiskGateState) -> bool:
        """Shared locked Q56 daily-loss comparison (single formula).

        ``start_of_day_net_equity - current_net_equity >= threshold`` against
        the fixed RiskDay baseline (never rebased intraday).  Used by BOTH the
        normal pre-order pipeline and the pending-entry pre-execution
        authorization so the two Q56 evidence paths cannot drift.
        """
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            daily_loss_amount = state.start_of_day_net_equity - state.current_net_equity
            daily_loss_threshold = state.start_of_day_net_equity * self._policy.max_daily_loss_pct
        return daily_loss_amount >= daily_loss_threshold

    def advance_state(
        self,
        *,
        risk_day: RiskDay,
        current_net_equity: object,
        starting_capital: object,
        prior_state: RiskGateState | None,
    ) -> RiskGateState:
        """Public fill-time state advance reusing the locked ``_derive_state`` rules.

        First RiskDay: ``start_of_day_net_equity = starting_capital``.  Same
        RiskDay: retains the existing start-of-day baseline and trade-count
        identities.  New RiskDay: rebases ``start_of_day_net_equity`` to the
        prior closing / current pre-event net equity and resets the daily
        entry-fill identities and count.  Calendar-identity conflict or
        invalid evidence FAILS CLOSED (raises).  This is the ONLY public
        transition used to move ``RiskGateState`` to the FILL-TIME RiskDay
        before ``record_entry_fill``, so a GTC entry approved on RiskDay D1
        and accepted/filled on D2 increments D2's trade count, never D1's.
        """
        state = self._derive_state(prior_state, risk_day, current_net_equity, starting_capital)
        if state is None:
            raise ValueError("invalid risk evidence for fill-time state advance")
        return state

    def _derive_state(
        self,
        prior_state: RiskGateState | None,
        risk_day: RiskDay,
        current_net_equity: object,
        starting_capital: object,
    ) -> RiskGateState | None:
        """Advance the account-level risk state for this evaluation.

        A changed RiskDay resets the daily counters and rebases
        ``start_of_day_net_equity`` to the previous RiskDay's closing net
        equity exactly once; the first RiskDay uses the authoritative
        ``starting_capital``.  Conflicting calendar identities fail closed.
        """
        equity = _safe_decimal(current_net_equity, "current_net_equity")
        if equity is None or equity < 0:
            return None
        if prior_state is None:
            baseline = _safe_decimal(starting_capital, "starting_capital")
            if baseline is None or baseline < 0:
                return None
            return RiskGateState(risk_day, baseline, equity, 0)
        if prior_state.risk_day == risk_day:
            return RiskGateState(risk_day, prior_state.start_of_day_net_equity, equity, prior_state.daily_trade_count)
        if prior_state.risk_day.calendar_identity != risk_day.calendar_identity:
            return None
        return RiskGateState(risk_day, prior_state.current_net_equity, equity, 0)

    def _cost_adjusted_capital(
        self,
        cost_projection: CostAdjustedAccountProjection | None,
    ) -> tuple[Decimal | None, str | None]:
        """Resolve the authoritative v4 Q55/Q59 capital denominator; fail closed.

        The projection's ``cost_adjusted_equity`` already subtracts recognized
        costs exactly once (``snapshot.equity − recognized_cost``); the gate
        only validates it as positive, finite evidence.
        """
        if not isinstance(cost_projection, CostAdjustedAccountProjection):
            return None, "missing_cost_adjusted_equity_evidence"
        equity = _safe_decimal(cost_projection.cost_adjusted_equity, "cost_adjusted_equity")
        if equity is None or not equity.is_finite() or equity <= 0:
            return None, "invalid_cost_adjusted_equity"
        return equity, None

    def _existing_open_risk(
        self,
        snapshot: AccountSnapshot,
        book: ProtectiveExitBook,
    ) -> tuple[Decimal, str | None]:
        """Sum per-position risk at each position's active protective stop.

        Returns ``(aggregate, None)`` on success or ``(Decimal, reason)`` on
        fail-closed evidence failure.  Position risk is
        ``quantity × (average_entry_price − active_stop_price) ×
        contract_multiplier`` with directional geometry
        ``active_stop_price < average_entry_price``.
        """
        total = Decimal("0")
        for key in snapshot.positions:
            candidates = book.authoritative_exits(key, kind=ProtectiveExitKind.STOP_LOSS)
            if not candidates:
                return Decimal("0"), "invalid_risk_evidence"
            if len(candidates) > 1:
                return Decimal("0"), "ambiguous_duplicate_stop"
            stop_price = _safe_decimal(candidates[0].exit_order.stop_price, "stop_price")
            position = snapshot.positions[key]
            if stop_price is None or stop_price <= 0 or stop_price >= position.average_entry_price:
                return Decimal("0"), "invalid_risk_evidence"
            with localcontext(INTERNAL_DECIMAL_CONTEXT):
                total += position.quantity * (position.average_entry_price - stop_price) * position.contract_multiplier
        return total, None


@dataclass(frozen=True)
class SignalPriorityEvidence:
    """One new-entry candidate's authoritative Q62 ranking evidence."""

    confidence: Decimal | int | float | str | None
    strategy_id: str
    strategy_version: str
    identity: InstrumentIdentity
    timeframe: str
    originating_timestamp: datetime

    def __post_init__(self) -> None:
        for name in ("strategy_id", "strategy_version", "timeframe"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")
        if self.originating_timestamp.tzinfo is None or self.originating_timestamp.utcoffset() is None:
            raise ValueError("originating_timestamp must be timezone-aware")
        if self.confidence is not None:
            confidence = _safe_decimal(self.confidence, "confidence")
            if confidence is None:
                raise ValueError("confidence must be numeric")
            object.__setattr__(self, "confidence", confidence)


def rank_candidates(
    candidates: Iterable[SignalPriorityEvidence],
    *,
    policy_identity: str = SIGNAL_PRIORITY_STRATEGY_SCOPED_POLICY_IDENTITY,
) -> tuple[SignalPriorityEvidence, ...]:
    """Versioned deterministic Q62 signal-priority ranking.

    ``Q62ConfidenceScore/v1`` (LEGACY, preserved for replay of legacy runs):
    highest raw ``confidence_score`` first globally, then the explicit
    canonical tie-break.  Raw confidence from different strategy_id /
    strategy_version pairs is directly comparable ONLY under this legacy
    identity.

    ``Q62StrategyScopedConfidence/v2`` (ACTIVE): raw confidence emitted by
    DIFFERENT ``strategy_id`` / ``strategy_version`` pairs is NOT inherently
    comparable, so candidates are ordered FIRST by canonical strategy identity
    (``strategy_id``, then ``strategy_version``).  Within the SAME
    strategy/version group, confidence sorts descending (``None`` sorts behind
    numeric confidence deterministically), then the existing canonical
    candidate tie-break applies using existing canonical field encodings.

    Any other ``policy_identity`` fails closed.  No Python ``hash()``, no
    insertion order, no caller order, no mixing of capital-allocation priority
    into signal priority.
    """
    if policy_identity not in (SIGNAL_PRIORITY_POLICY_IDENTITY, SIGNAL_PRIORITY_STRATEGY_SCOPED_POLICY_IDENTITY):
        raise ValueError(f"unknown Q62 signal-priority policy identity: {policy_identity!r}")

    def confidence_component(candidate: SignalPriorityEvidence) -> Decimal:
        confidence = _safe_decimal(candidate.confidence, "confidence")
        return Decimal("Infinity") if confidence is None else -confidence

    def canonical_tie_break(candidate: SignalPriorityEvidence) -> tuple[object, ...]:
        identity = candidate.identity
        return (
            identity.market,
            identity.instrument,
            identity.segment,
            identity.underlying or "",
            "" if identity.expiry is None else identity.expiry.isoformat(),
            "" if identity.strike is None else str(identity.strike),
            identity.option_type or "",
            candidate.timeframe,
            CanonicalCodec.timestamp_text(candidate.originating_timestamp),
        )

    def sort_key(candidate: SignalPriorityEvidence) -> tuple[object, ...]:
        if policy_identity == SIGNAL_PRIORITY_POLICY_IDENTITY:
            return (
                confidence_component(candidate),
                candidate.strategy_id,
                candidate.strategy_version,
                *canonical_tie_break(candidate),
            )
        return (
            candidate.strategy_id,
            candidate.strategy_version,
            confidence_component(candidate),
            *canonical_tie_break(candidate),
        )

    return tuple(sorted(candidates, key=sort_key))


def entry_intent_identity(
    *,
    strategy_id: str,
    strategy_version: str,
    identity: InstrumentIdentity,
    timeframe: str,
    originating_timestamp: datetime,
) -> str:
    """Deterministic pre-fill logical entry identity (``sentinelx-entry-intent/v1``).

    CanonicalCodec only, exact semantic field order: strategy_id,
    strategy_version, full InstrumentIdentity (established 7-field order),
    timeframe, originating_timestamp (CanonicalCodec UTC/nanosecond rules).
    Quantity, protective plan prices, confidence, and fill prices are
    EXCLUDED.  No delimiter concatenation, no JSON-SHA parallel identity, no
    repr(), no pickle, no Python hash().  The identity is stable from gate
    evaluation through pending commitment, pending order, first accepted
    entry fill (``RiskGateState.record_entry_fill`` dedup), and commitment
    release; a later entry cycle on the same PositionKey (later timestamp)
    produces a fresh identity.
    """
    if not isinstance(strategy_id, str) or not strategy_id.strip():
        raise ValueError("strategy_id must be a non-empty string")
    if not isinstance(strategy_version, str) or not strategy_version.strip():
        raise ValueError("strategy_version must be a non-empty string")
    if not isinstance(identity, InstrumentIdentity):
        raise TypeError("identity must be an InstrumentIdentity")
    if not isinstance(timeframe, str) or not timeframe.strip():
        raise ValueError("timeframe must be a non-empty string")
    if originating_timestamp.tzinfo is None or originating_timestamp.utcoffset() is None:
        raise ValueError("originating_timestamp must be timezone-aware")
    return CanonicalCodec.fingerprint(
        "sentinelx-entry-intent/v1",
        (
            ("strategy_id", strategy_id),
            ("strategy_version", strategy_version),
            ("identity", (
                identity.market,
                identity.instrument,
                identity.segment,
                identity.underlying,
                identity.expiry,
                identity.strike,
                identity.option_type,
            )),
            ("timeframe", timeframe),
            ("originating_timestamp", originating_timestamp),
        ),
    )
