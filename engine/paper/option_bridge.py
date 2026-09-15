"""Phase 5 Slice B — Market-only option entry bridge.

Bridges semantic strategy signals to concrete option-market execution:

    SignalIntent (BUY/SELL)
    -> OptionSelector (select CE/PE contract)
    -> QuoteSnapshot (option premium)
    -> worst_permitted_fill (conservative RiskGate reference)
    -> ProtectivePlanPolicy (premium-domain stop/target)
    -> RiskGate (sizing + risk authorization)
    -> ConcreteOpenInstruction (executable BUY on option contract)
    -> SimulatedPaperBroker.submit()

FROZEN OWNER LOCKS:
- Long-options only: BUY->CE, SELL->PE, all executable as BUY.
- MARKET entry only. LIMIT/STOP/STOP_LIMIT rejected at init.
- Option-premium price domain only. Underlying prices never used.
- Safety bounds: max_execution_tolerance_bps > 0 AND max_slippage_bps > 0.
- Single QuoteSnapshot authority: same quote for gate + broker.
- ProtectivePlanPolicy required. No production fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from engine.execution.paper_fill import PaperFillPolicy
from engine.execution.quote import QuoteSnapshot
from engine.data.feeds.live_feed import SubscriptionOwnerKey
from engine.core.numeric import as_decimal
from engine.options.catalog import InstrumentCatalog
from engine.options.policy import OptionSelectionPolicy
from engine.options.selector import (
    OptionSelector,
    OptionSelectionRejection,
    ResolvedOptionEntry,
)
from engine.orders.model import ConcreteOpenInstruction, OrderRequest, OrderType, TimeInForce
from engine.portfolio.model import InstrumentSpecification, PositionKey
from engine.protective.runtime import ProtectiveExitBook
from engine.protective.plan import PreEntryProtectivePlan, ProtectivePlanPolicy
from engine.risk.risk_manager import (
    PositionDirection,
    RiskDay,
    RiskGate,
    RiskGateResult,
    RiskOutcome,
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OptionEntryRejection:
    """Structured rejection when option entry cannot proceed."""

    reason: str
    strategy_id: str
    strategy_version: str
    action: str


@dataclass(frozen=True)
class OptionEntryResult:
    """Successful option entry: everything needed for broker submission.

    Contains the executable instruction, the frozen protective plan,
    the RiskGate result, and the authoritative quote used for submission.
    """

    instruction: ConcreteOpenInstruction
    plan: PreEntryProtectivePlan
    gate_result: RiskGateResult
    submission_quote: QuoteSnapshot
    selected_entry: ResolvedOptionEntry
    worst_permitted_fill: Decimal


# ---------------------------------------------------------------------------
# Conservative MARKET fill bound
# ---------------------------------------------------------------------------


def compute_worst_permitted_fill(
    reference_ask: Decimal,
    max_execution_tolerance_bps: Decimal,
    max_slippage_bps: Decimal,
) -> Decimal:
    """Deterministic upper bound on accepted MARKET BUY fill.

    From the 11-step PaperFillAdapter pipeline:
      - Step 4 bounds current_executable <= ref * (1 + tol/10000)
      - Step 9 bounds rounded <= current_executable * (1 + max_slp/10000)
      - Combined: fill <= ref * (1 + tol/10000) * (1 + max_slp/10000)

    This holds for every PaperSlippageModel because step 9 applies
    AFTER tick rounding, independent of the model output.

    Parameters must be strictly positive (bridge validates at init).
    """
    tol_factor = Decimal("1") + max_execution_tolerance_bps / Decimal("10000")
    slp_factor = Decimal("1") + max_slippage_bps / Decimal("10000")
    return reference_ask * tol_factor * slp_factor


# ---------------------------------------------------------------------------
# Bridge initialization validation
# ---------------------------------------------------------------------------


class OptionEntryBridge:
    """Market-only option entry bridge for paper trading.

    Validates construction-time safety invariants and provides
    ``build_option_entry()`` for one signal-intent-to-broker-submission
    pipeline invocation.
    """

    def __init__(
        self,
        *,
        catalog: InstrumentCatalog,
        paper_fill_policy: PaperFillPolicy,
        risk_gate: RiskGate,
        protective_plan_policies: Mapping[SubscriptionOwnerKey, ProtectivePlanPolicy],
        allow_empty_protective_policies: bool = False,
        option_signal_to_order_type: OrderType = OrderType.MARKET,
        option_time_in_force: TimeInForce = TimeInForce.DAY,
    ) -> None:
        # --- Safety bound validation (owner lock #5) ---
        tol = paper_fill_policy.max_execution_tolerance_bps
        slp = paper_fill_policy.max_slippage_bps
        if tol <= 0:
            raise ValueError(
                "option MARKET entry requires max_execution_tolerance_bps > 0; "
                f"got {tol}"
            )
        if slp <= 0:
            raise ValueError(
                "option MARKET entry requires max_slippage_bps > 0; "
                f"got {slp}"
            )

        # --- MARKET-only validation (owner lock #2) ---
        if option_signal_to_order_type is not OrderType.MARKET:
            raise ValueError(
                f"option-mode entry only supports MARKET in V1; "
                f"got {option_signal_to_order_type.value}"
            )

        # --- ProtectivePlanPolicy presence validation (owner lock #8) ---
        if not protective_plan_policies and not allow_empty_protective_policies:
            raise ValueError(
                "option entry requires at least one ProtectivePlanPolicy"
            )
        for owner, policy in protective_plan_policies.items():
            if not isinstance(owner, SubscriptionOwnerKey):
                raise TypeError(
                    "protective_plan_policies must use exact SubscriptionOwnerKey keys"
                )
            if (
                not isinstance(getattr(policy, "policy_identity", None), str)
                or not getattr(policy, "policy_identity").strip()
                or not callable(getattr(policy, "plan_for", None))
            ):
                raise TypeError(
                    "protective_plan_policies values must provide ProtectivePlanPolicy behaviour"
                )

        self._catalog = catalog
        self._paper_fill_policy = paper_fill_policy
        self._risk_gate = risk_gate
        self._protective_plan_policies = dict(protective_plan_policies)
        self._option_time_in_force = option_time_in_force

    @property
    def catalog(self) -> InstrumentCatalog:
        return self._catalog

    @property
    def paper_fill_policy(self) -> PaperFillPolicy:
        return self._paper_fill_policy

    @property
    def risk_gate(self) -> RiskGate:
        return self._risk_gate

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def build_option_entry(
        self,
        *,
        intent,  # SignalIntent
        policy,  # OptionSelectionPolicy
        underlying_price: Decimal | int | float | str,
        selection_timestamp,  # datetime (tz-aware)
        option_quote,  # QuoteSnapshot
        specification,  # InstrumentSpecification
        risk_day,  # RiskDay
        snapshot,  # AccountSnapshot
        protective_book,  # ProtectiveExitBook (current live state)
        current_net_equity: Decimal | int | float | str,
        starting_capital: Decimal | int | float | str,
        prior_risk_state=None,  # RiskGateState | None
        pending_commitments=(),  # tuple[PendingRiskCommitment, ...]
        cost_projection=None,  # CostAdjustedAccountProjection | None
    ) -> OptionEntryResult | OptionSelectionRejection | OptionEntryRejection:
        """Full pipeline: select -> plan -> gate -> instruction.

        Returns OptionEntryResult on success, or a rejection on failure.
        Never returns None.
        """
        # --- 1. Option selection ---
        selector = OptionSelector(self._catalog)
        selection = selector.select(
            intent=intent,
            policy=policy,
            underlying_price=underlying_price,
            selection_timestamp=selection_timestamp,
        )
        if isinstance(selection, OptionSelectionRejection):
            return selection

        selected = selection  # ResolvedOptionEntry

        # --- 2. Quote identity validation (owner lock #7) ---
        if option_quote.instrument_identity != selected.selected_identity:
            return OptionEntryRejection(
                reason="quote_instrument_mismatch",
                strategy_id=intent.strategy_id,
                strategy_version=intent.strategy_version,
                action=intent.action,
            )
        if specification.identity != selected.selected_identity:
            return OptionEntryRejection(
                reason="specification_instrument_mismatch",
                strategy_id=intent.strategy_id,
                strategy_version=intent.strategy_version,
                action=intent.action,
            )

        # --- 3. Quote validation (must have ask for BUY) ---
        if option_quote.ask_price is None:
            return OptionEntryRejection(
                reason="no_executable_ask_in_quote",
                strategy_id=intent.strategy_id,
                strategy_version=intent.strategy_version,
                action=intent.action,
            )

        reference_ask = option_quote.ask_price

        # --- 4. Compute worst-permitted fill (owner lock #6) ---
        worst_permitted_fill = compute_worst_permitted_fill(
            reference_ask,
            self._paper_fill_policy.max_execution_tolerance_bps,
            self._paper_fill_policy.max_slippage_bps,
        )

        # --- 5. ProtectivePlanPolicy (owner lock #8) ---
        owner = SubscriptionOwnerKey(intent.strategy_id, intent.strategy_version)
        plan_policy = self._protective_plan_policies.get(owner)
        if plan_policy is None:
            return OptionEntryRejection(
                reason="missing_protective_plan_policy",
                strategy_id=intent.strategy_id,
                strategy_version=intent.strategy_version,
                action=intent.action,
            )

        intended_key = PositionKey(
            intent.strategy_id, intent.strategy_version, selected.selected_identity
        )

        plan = plan_policy.plan_for(
            intended_position_key=intended_key,
            originating_timestamp=intent.originating_timestamp,
            timeframe=intent.timeframe,
            reference_price=worst_permitted_fill,
        )

        # --- 6. RiskGate evaluation ---
        gate_result = self._risk_gate.evaluate_pre_order(
            direction=PositionDirection.LONG,
            intended_position_key=intended_key,
            capital=snapshot.starting_capital,
            entry_price=worst_permitted_fill,
            specification=specification,
            snapshot=snapshot,
            book=protective_book,
            candidate_plan=plan,
            risk_day=risk_day,
            current_net_equity=current_net_equity,
            starting_capital=starting_capital,
            prior_state=prior_risk_state,
            pending_commitments=pending_commitments,
            cost_projection=cost_projection,
        )

        if gate_result.outcome is not RiskOutcome.APPROVED:
            return OptionEntryRejection(
                reason=f"risk_gate_rejected_{gate_result.reason}",
                strategy_id=intent.strategy_id,
                strategy_version=intent.strategy_version,
                action=intent.action,
            )

        approved_quantity = gate_result.quantity

        # --- 7. Build source OrderRequest (option-premium domain) ---
        # The source intent carries semantic action (BUY or SELL) and
        # underlying symbol for provenance. The OrderRequest's symbol
        # is set to the concrete option instrument for accounting.
        source_order = OrderRequest.from_intent(
            intent,
            OrderType.MARKET,
            approved_quantity,
            self._option_time_in_force,
        )

        # --- 8. ConcreteOpenInstruction (owner lock #1) ---
        # For SELL -> PE -> executable BUY PE:
        #   opening_action = "BUY" (overriding semantic SELL)
        #   execution_symbol = concrete option instrument
        #   source_entry_order.source_intent.action = "SELL" (provenance)
        instruction = ConcreteOpenInstruction(
            source_entry_order=source_order,
            opening_action="BUY",
            execution_symbol=selected.selected_identity.instrument,
        )

        # --- 9. Validate instruction properties ---
        assert instruction.action == "BUY"
        assert instruction.order_type is OrderType.MARKET
        assert instruction.limit_price is None
        assert instruction.stop_price is None
        assert instruction.quantity == approved_quantity
        assert instruction.symbol == selected.selected_identity.instrument

        return OptionEntryResult(
            instruction=instruction,
            plan=plan,
            gate_result=gate_result,
            submission_quote=option_quote,
            selected_entry=selected,
            worst_permitted_fill=worst_permitted_fill,
        )
