"""Stateless, deterministic paper fill evaluation (MARKET and LIMIT only).

PaperFillAdapter evaluates one order against one quote snapshot and returns
a deterministic ExecutionResult.  It owns fill economics only — no order state,
no lifecycle, no costs, no risk logic.

STOP / STOP_LIMIT trigger detection is broker-owned (Slice 3B).  After trigger,
the broker calls evaluate_market() or evaluate_limit() directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Protocol, runtime_checkable

from engine.execution.adapter import ExecutionAdapter
from engine.execution.model import (
    ExecutableOrder,
    ExecutionOutcome,
    ExecutionResult,
)
from engine.execution.quote import QuoteSnapshot
from engine.core.numeric import as_decimal
from engine.orders.model import ConcreteOpenInstruction, OrderRequest, OrderType


# ======================================================================
# PaperSlippageModel protocol
# ======================================================================


@runtime_checkable
class PaperSlippageModel(Protocol):
    """Protocol for adverse execution slippage in paper mode."""

    model_id: str

    def apply(self, *, action: str, price: Decimal) -> Decimal:
        """Return a non-negative slippage AMOUNT (not adjusted price).

        BUY: returned amount is added to base price (adverse for buyer).
        SELL: returned amount is subtracted from base price (adverse for seller).
        """
        ...


# ======================================================================
# FixedBasisPointsSlippage — deterministic V1 implementation
# ======================================================================


class FixedBasisPointsSlippage:
    """Deterministic fixed-basis-points adverse slippage model.

    ``bps`` is a non-negative Decimal.  Zero means zero slippage.
    No empirical calibration values are baked into this class.
    """

    def __init__(self, bps: Decimal | int | float | str) -> None:
        self._bps = as_decimal(bps, "bps")
        if self._bps < 0:
            raise ValueError("bps must be non-negative")

    @property
    def model_id(self) -> str:
        return f"paper-fixed-bps/{self._bps}"

    def apply(self, *, action: str, price: Decimal) -> Decimal:
        if not isinstance(price, Decimal):
            raise TypeError("price must be Decimal")
        if price <= 0:
            raise ValueError("price must be positive")
        # bps/10000 of price, always non-negative
        amount = price * self._bps / Decimal("10000")
        if amount < 0:
            raise ValueError("slippage amount must be non-negative")
        return amount


# ======================================================================
# PaperFillPolicy — static adapter configuration
# ======================================================================


@dataclass(frozen=True)
class PaperFillPolicy:
    """Static, reusable paper-fill configuration.  Shared across orders in a run."""

    slippage_model: PaperSlippageModel
    max_execution_tolerance_bps: Decimal
    max_slippage_bps: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_execution_tolerance_bps",
            as_decimal(self.max_execution_tolerance_bps, "max_execution_tolerance_bps"),
        )
        object.__setattr__(
            self,
            "max_slippage_bps",
            as_decimal(self.max_slippage_bps, "max_slippage_bps"),
        )
        if self.max_execution_tolerance_bps < 0:
            raise ValueError("max_execution_tolerance_bps must be >= 0")
        if self.max_slippage_bps < 0:
            raise ValueError("max_slippage_bps must be >= 0")


# ======================================================================
# ExecutionEvaluationContext — per-order execution context
# ======================================================================


@dataclass(frozen=True)
class ExecutionEvaluationContext:
    """Per-order execution context provided by the broker at each evaluation.

    ``reference_price`` has ONE exact meaning:

    * **BUY:** order-submission-time executable ASK-side reference
    * **SELL:** order-submission-time executable BID-side reference

    It is NOT limit_price, current execution quote, stop_price, or any
    arbitrary later quote.
    """

    price_increment: Decimal
    reference_price: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "price_increment", as_decimal(self.price_increment, "price_increment"),
        )
        object.__setattr__(
            self, "reference_price", as_decimal(self.reference_price, "reference_price"),
        )
        if self.price_increment <= 0:
            raise ValueError("price_increment must be > 0")
        if self.reference_price <= 0:
            raise ValueError("reference_price must be > 0")


# ======================================================================
# Tick-rounding helpers
# ======================================================================


def _ceil_to_tick(value: Decimal, tick: Decimal) -> Decimal:
    """Round UP to nearest tick increment (adverse for buyer)."""
    if tick <= 0:
        raise ValueError("tick must be positive")
    quotient = value / tick
    rounded = int(quotient.to_integral_value(rounding=ROUND_CEILING))
    return rounded * tick


def _floor_to_tick(value: Decimal, tick: Decimal) -> Decimal:
    """Round DOWN to nearest tick increment (adverse for seller)."""
    if tick <= 0:
        raise ValueError("tick must be positive")
    quotient = value / tick
    rounded = int(quotient.to_integral_value(rounding=ROUND_FLOOR))
    return rounded * tick


# ======================================================================
# PaperFillAdapter
# ======================================================================


class PaperFillAdapter:
    """Stateless, deterministic paper fill evaluation (MARKET and LIMIT only).

    Implements :class:`ExecutionAdapter`.  STOP / STOP_LIMIT trigger logic is
    broker-owned (Slice 3B).  After trigger, the broker calls
    :meth:`evaluate_market` or :meth:`evaluate_limit` directly.
    """

    _MODEL_VERSION = "paper-fill-v1"

    def __init__(self, policy: PaperFillPolicy) -> None:
        if not isinstance(policy, PaperFillPolicy):
            raise TypeError("policy must be a PaperFillPolicy")
        object.__setattr__(self, "_policy", policy)

    @property
    def policy(self) -> PaperFillPolicy:
        return self._policy

    @property
    def model_id(self) -> str:
        return f"{self._MODEL_VERSION}/{self._policy.slippage_model.model_id}"

    # ------------------------------------------------------------------
    # ExecutionAdapter protocol
    # ------------------------------------------------------------------

    def evaluate(
        self,
        order: ExecutableOrder,
        market_evidence: object,
        execution_context: object,
    ) -> ExecutionResult:
        """Dispatch to MARKET or LIMIT evaluation.

        Validates market_evidence is QuoteSnapshot and execution_context is
        ExecutionEvaluationContext.  STOP / STOP_LIMIT raises ValueError
        because trigger state is broker-owned.
        """
        if not isinstance(market_evidence, QuoteSnapshot):
            raise TypeError(
                "market_evidence must be a QuoteSnapshot; "
                f"got {type(market_evidence).__name__}"
            )
        if not isinstance(execution_context, ExecutionEvaluationContext):
            raise TypeError(
                "execution_context must be an ExecutionEvaluationContext; "
                f"got {type(execution_context).__name__}"
            )

        if isinstance(order, (OrderRequest, ConcreteOpenInstruction)):
            if order.order_type is OrderType.MARKET:
                return self.evaluate_market(order, market_evidence, execution_context)
            if order.order_type is OrderType.LIMIT:
                return self.evaluate_limit(order, market_evidence, execution_context)
            # STOP or STOP_LIMIT → contract misuse in Slice 3A
            raise ValueError(
                "PaperFillAdapter does not evaluate STOP or STOP_LIMIT "
                "orders directly; use evaluate_market() or evaluate_limit() "
                "after broker-side trigger detection"
            )
        raise TypeError(f"order must be an OrderRequest or ConcreteOpenInstruction; got {type(order).__name__}")

    # ------------------------------------------------------------------
    # MARKET primitive
    # ------------------------------------------------------------------

    def evaluate_market(
        self,
        order: OrderRequest,
        quote: QuoteSnapshot,
        context: ExecutionEvaluationContext,
    ) -> ExecutionResult:
        """MARKET fill evaluation.  Also used by broker for triggered STOPs.

        Accepts MARKET and already-triggered STOP orders.
        """
        if order.order_type not in {OrderType.MARKET, OrderType.STOP}:
            raise ValueError(
                f"evaluate_market accepts MARKET or triggered STOP; "
                f"got {order.order_type.value}"
            )
        return self._fill(order, quote, context, limit_price=None)

    # ------------------------------------------------------------------
    # LIMIT primitive
    # ------------------------------------------------------------------

    def evaluate_limit(
        self,
        order: OrderRequest,
        quote: QuoteSnapshot,
        context: ExecutionEvaluationContext,
    ) -> ExecutionResult:
        """LIMIT fill evaluation.  Also used by broker for triggered STOP_LIMITs.

        Accepts LIMIT and already-triggered STOP_LIMIT orders.
        """
        if order.order_type not in {OrderType.LIMIT, OrderType.STOP_LIMIT}:
            raise ValueError(
                f"evaluate_limit accepts LIMIT or triggered STOP_LIMIT; "
                f"got {order.order_type.value}"
            )
        limit = order.limit_price
        if limit is None:
            raise ValueError("LIMIT order requires a non-None limit_price")
        return self._fill(order, quote, context, limit_price=limit)

    # ------------------------------------------------------------------
    # Core fill pipeline (steps 1–11 of locked sequence)
    # ------------------------------------------------------------------

    def _fill(
        self,
        order: OrderRequest,
        quote: QuoteSnapshot,
        context: ExecutionEvaluationContext,
        limit_price: Decimal | None,
    ) -> ExecutionResult:
        """Unified MARKET/LIMIT fill pipeline per locked evaluation sequence."""
        policy = self._policy
        action = order.action

        # Step 2: Select executable side
        if action == "BUY":
            current_executable = quote.ask_price
            missing_reason = "no_executable_ask"
        else:
            current_executable = quote.bid_price
            missing_reason = "no_executable_bid"

        # Step 3: Reject missing/invalid executable evidence
        if current_executable is None:
            return self._unfilled(order, quote, missing_reason)

        # Step 3b: Crossed quote check
        if (
            quote.bid_price is not None
            and quote.ask_price is not None
            and quote.bid_price > quote.ask_price
        ):
            return self._unfilled(order, quote, "crossed_quote")

        # Step 4: Price-move tolerance (market movement ONLY, no slippage)
        tol_bps = policy.max_execution_tolerance_bps
        if tol_bps > 0:
            ref = context.reference_price
            if action == "BUY":
                move = current_executable - ref
            else:
                move = ref - current_executable
            max_allowed = ref * tol_bps / Decimal("10000")
            if move > max_allowed:
                return self._unfilled(order, quote, "price_move_exceeded")

        # Step 5: For LIMIT, verify current executable satisfies limit
        if limit_price is not None:
            if action == "BUY":
                if current_executable > limit_price:
                    return self._unfilled(order, quote, "limit_not_executable")
            else:
                if current_executable < limit_price:
                    return self._unfilled(order, quote, "limit_not_executable")

        # Step 6: Compute adverse slippage amount
        slippage_amount = policy.slippage_model.apply(
            action=action, price=current_executable,
        )
        if slippage_amount < 0:
            raise ValueError("slippage model must return non-negative amount")

        # Step 7: Apply adverse slippage
        if action == "BUY":
            raw_fill = current_executable + slippage_amount
        else:
            raw_fill = current_executable - slippage_amount

        if raw_fill <= 0:
            return self._unfilled(order, quote, "non_positive_after_slippage")

        # Step 8: Apply adverse tick rounding
        inc = context.price_increment
        if action == "BUY":
            rounded = _ceil_to_tick(raw_fill, inc)
        else:
            rounded = _floor_to_tick(raw_fill, inc)

        if rounded <= 0:
            return self._unfilled(order, quote, "non_positive_after_rounding")

        # Step 9: Max slippage check (effective slippage vs current executable)
        max_slp_bps = policy.max_slippage_bps
        if max_slp_bps > 0:
            if action == "BUY":
                effective = rounded - current_executable
                threshold = current_executable * max_slp_bps / Decimal("10000")
            else:
                effective = current_executable - rounded
                threshold = current_executable * max_slp_bps / Decimal("10000")
            if effective > threshold:
                return self._unfilled(order, quote, "max_slippage_exceeded")

        # Step 10: For LIMIT, hard boundary (post-slippage, post-rounding)
        if limit_price is not None:
            if action == "BUY":
                if rounded > limit_price:
                    return self._unfilled(
                        order, quote, "adverse_slippage_exceeds_limit",
                    )
            else:
                if rounded < limit_price:
                    return self._unfilled(
                        order, quote, "adverse_slippage_exceeds_limit",
                    )

        # Step 11: FILLED
        if action == "BUY":
            effective_slippage = rounded - current_executable
        else:
            effective_slippage = current_executable - rounded

        return ExecutionResult(
            order=order,
            outcome=ExecutionOutcome.FILLED,
            execution_bar_timestamp=quote.exchange_timestamp,
            pre_slippage_price=current_executable,
            fill_price=rounded,
            filled_quantity=order.quantity,
            reason=None,
            slippage_model_id=policy.slippage_model.model_id,
            slippage_amount=effective_slippage,
            metadata=order.source_intent.metadata,
        )

    @staticmethod
    def _unfilled(
        order: OrderRequest, quote: QuoteSnapshot, reason: str,
    ) -> ExecutionResult:
        return ExecutionResult(
            order=order,
            outcome=ExecutionOutcome.UNFILLED,
            execution_bar_timestamp=quote.exchange_timestamp,
            pre_slippage_price=None,
            fill_price=None,
            filled_quantity=Decimal("0"),
            reason=reason,
            slippage_model_id="none",
            slippage_amount=Decimal("0"),
            metadata=order.source_intent.metadata,
        )
