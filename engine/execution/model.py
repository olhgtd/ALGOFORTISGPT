"""Immutable, portfolio-neutral execution outcomes."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from engine.backtest.engine import BarEvent
from engine.core.numeric import as_decimal
from engine.orders import ConcreteCloseInstruction, ConcreteOpenInstruction, OrderRequest, OrderType


ExecutableOrder = OrderRequest | ConcreteCloseInstruction | ConcreteOpenInstruction


class StopLimitActivationBasis(str, Enum):
    """Deterministic basis evidence for the first authoritative STOP trigger."""

    OPEN = "OPEN"
    INTRABAR_STOP_TOUCH = "INTRABAR_STOP_TOUCH"


@dataclass(frozen=True)
class StopLimitActivationEvidence:
    """Immutable evidence that a STOP_LIMIT order has authoritatively activated.

    Activation is MONOTONIC execution substate: once an eligible real bar
    triggers the STOP, later bars evaluate the order as an active LIMIT
    without requiring the STOP again.  The original OrderRequest remains the
    immutable logical request; this evidence is execution-state evidence only
    and carries no random/UUID/duplicated entry identity.
    """

    activation_bar_timestamp: datetime
    activation_price: Decimal | int | float | str
    activation_basis: StopLimitActivationBasis

    def __post_init__(self) -> None:
        if self.activation_bar_timestamp.tzinfo is None or self.activation_bar_timestamp.utcoffset() is None:
            raise ValueError("activation_bar_timestamp must be timezone-aware")
        price = as_decimal(self.activation_price, "activation_price")
        if price <= 0:
            raise ValueError("activation_price must be positive")
        object.__setattr__(self, "activation_price", price)
        if not isinstance(self.activation_basis, StopLimitActivationBasis):
            raise TypeError("activation_basis must be a StopLimitActivationBasis")


class ExecutionOutcome(str, Enum):
    """Slice 5 outcomes without broker or portfolio lifecycle semantics."""

    FILLED = "FILLED"
    UNFILLED = "UNFILLED"
    INELIGIBLE = "INELIGIBLE"
    EXPIRED = "EXPIRED"
    OUTSTANDING = "OUTSTANDING"
    REQUIRES_PORTFOLIO_RESOLUTION = "REQUIRES_PORTFOLIO_RESOLUTION"


@dataclass(frozen=True)
class ExecutionResult:
    """One deterministic evaluation outcome for one request against one bar.

    A successful result is always a full fill. This record never stores broker
    IDs, costs, account state, realized P&L, or position state.
    """

    order: ExecutableOrder
    outcome: ExecutionOutcome
    execution_bar_timestamp: datetime | None
    pre_slippage_price: Decimal | int | float | str | None
    fill_price: Decimal | int | float | str | None
    filled_quantity: Decimal | int | float | str
    reason: str | None
    slippage_model_id: str
    slippage_amount: Decimal | int | float | str
    metadata: Mapping[str, Any]
    stop_limit_activation: StopLimitActivationEvidence | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.order, (OrderRequest, ConcreteCloseInstruction, ConcreteOpenInstruction)):
            raise TypeError("order must be an executable order")
        if self.stop_limit_activation is not None:
            if not isinstance(self.stop_limit_activation, StopLimitActivationEvidence):
                raise TypeError("stop_limit_activation must be StopLimitActivationEvidence or None")
            if self.order.order_type is not OrderType.STOP_LIMIT:
                raise ValueError("stop_limit_activation evidence is valid only for STOP_LIMIT orders")
        if not isinstance(self.outcome, ExecutionOutcome):
            raise TypeError("outcome must be an ExecutionOutcome")
        if self.execution_bar_timestamp is not None and (
            self.execution_bar_timestamp.tzinfo is None
            or self.execution_bar_timestamp.utcoffset() is None
        ):
            raise ValueError("execution_bar_timestamp must be timezone-aware")
        object.__setattr__(self, "filled_quantity", as_decimal(self.filled_quantity, "filled_quantity"))
        object.__setattr__(self, "slippage_amount", as_decimal(self.slippage_amount, "slippage_amount"))
        if self.pre_slippage_price is not None:
            object.__setattr__(self, "pre_slippage_price", as_decimal(self.pre_slippage_price, "pre_slippage_price"))
        if self.fill_price is not None:
            object.__setattr__(self, "fill_price", as_decimal(self.fill_price, "fill_price"))
        if self.outcome is ExecutionOutcome.FILLED:
            if self.fill_price is None or self.pre_slippage_price is None:
                raise ValueError("filled result requires fill prices")
            if self.filled_quantity != self.order.quantity:
                raise ValueError("Slice 5 supports only full requested-quantity fills")
        elif self.filled_quantity != 0:
            raise ValueError("non-filled results must have zero filled_quantity")
        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def action(self) -> str:
        return self.order.action

    @property
    def symbol(self) -> str:
        return self.order.symbol

    @property
    def timeframe(self) -> str:
        return self.order.timeframe

    @property
    def originating_timestamp(self) -> datetime:
        return self.order.originating_timestamp
