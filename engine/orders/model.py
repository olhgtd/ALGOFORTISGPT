"""Immutable structural order requests translated from signal intents."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Literal

from engine.core.numeric import as_decimal
from engine.orchestration.signal_intake import SignalIntent


class OrderType(str, Enum):
    """Order structures supported before execution behavior exists."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class TimeInForce(str, Enum):
    """Explicit lifetime for a pending order."""

    DAY = "DAY"
    GTC = "GTC"


def _require_positive_price(value: Decimal | int | float | str | None, field_name: str) -> Decimal:
    if value is None:
        raise ValueError(f"{field_name} must be a positive price")
    result = as_decimal(value, field_name)
    if result <= 0:
        raise ValueError(f"{field_name} must be a positive price")
    return result


@dataclass(frozen=True)
class OrderRequest:
    """A validated, non-executable request for a future order subsystem.

    Quantity is supplied by the caller. This class validates it but never
    calculates sizing, inspects market prices, or changes account state.
    """

    source_intent: SignalIntent
    order_type: OrderType
    quantity: Decimal | int | float | str
    time_in_force: TimeInForce
    limit_price: Decimal | int | float | str | None = None
    stop_price: Decimal | int | float | str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_intent, SignalIntent):
            raise TypeError("source_intent must be a SignalIntent")
        if not isinstance(self.order_type, OrderType):
            raise TypeError("order_type must be an OrderType")
        if not isinstance(self.time_in_force, TimeInForce):
            raise TypeError("time_in_force must be a TimeInForce")
        quantity = as_decimal(self.quantity, "quantity")
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        object.__setattr__(self, "quantity", quantity)
        timestamp = self.source_intent.originating_timestamp
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("originating signal timestamp must be timezone-aware")

        if self.order_type is OrderType.MARKET:
            if self.limit_price is not None or self.stop_price is not None:
                raise ValueError("MARKET orders cannot carry limit or stop prices")
        elif self.order_type is OrderType.LIMIT:
            object.__setattr__(self, "limit_price", _require_positive_price(self.limit_price, "limit_price"))
            if self.stop_price is not None:
                raise ValueError("LIMIT orders cannot carry a stop price")
        elif self.order_type is OrderType.STOP:
            object.__setattr__(self, "stop_price", _require_positive_price(self.stop_price, "stop_price"))
            if self.limit_price is not None:
                raise ValueError("STOP orders cannot carry a limit price")
        else:
            object.__setattr__(self, "limit_price", _require_positive_price(self.limit_price, "limit_price"))
            object.__setattr__(self, "stop_price", _require_positive_price(self.stop_price, "stop_price"))

    @classmethod
    def from_intent(
        cls,
        intent: SignalIntent,
        order_type: OrderType,
        quantity: Decimal | int | float | str,
        time_in_force: TimeInForce,
        *,
        limit_price: Decimal | int | float | str | None = None,
        stop_price: Decimal | int | float | str | None = None,
    ) -> "OrderRequest":
        """Translate an actionable intent without choosing execution behavior."""
        return cls(intent, order_type, quantity, time_in_force, limit_price, stop_price)

    @property
    def action(self) -> Literal["BUY", "SELL", "EXIT"]:
        """Preserve the strategy action without inferring broker-side semantics."""
        return self.source_intent.action

    @property
    def symbol(self) -> str:
        return self.source_intent.symbol

    @property
    def timeframe(self) -> str:
        return self.source_intent.timeframe

    @property
    def originating_timestamp(self):
        return self.source_intent.originating_timestamp

    @property
    def strategy_id(self) -> str:
        return self.source_intent.strategy_id

    @property
    def strategy_version(self) -> str:
        return self.source_intent.strategy_version


@dataclass(frozen=True)
class ConcreteCloseInstruction:
    """Position-resolved full-close instruction evaluated by the execution layer.

    This is a nonbreaking extension for an explicit EXIT request.  It retains
    the original EXIT order as provenance while exposing the concrete closing
    side and quantity needed for normal execution evaluation.
    """

    source_exit_order: OrderRequest
    closing_action: Literal["BUY", "SELL"]
    quantity: Decimal | int | float | str

    def __post_init__(self) -> None:
        if not isinstance(self.source_exit_order, OrderRequest):
            raise TypeError("source_exit_order must be an OrderRequest")
        if self.source_exit_order.action != "EXIT":
            raise ValueError("source_exit_order must preserve an EXIT action")
        if self.closing_action not in {"BUY", "SELL"}:
            raise ValueError("closing_action must be BUY or SELL")
        quantity = as_decimal(self.quantity, "quantity")
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        object.__setattr__(self, "quantity", quantity)

    @property
    def action(self) -> Literal["BUY", "SELL"]:
        return self.closing_action

    @property
    def source_intent(self) -> SignalIntent:
        return self.source_exit_order.source_intent

    @property
    def order_type(self) -> OrderType:
        return self.source_exit_order.order_type

    @property
    def time_in_force(self) -> TimeInForce:
        return self.source_exit_order.time_in_force

    @property
    def limit_price(self) -> Decimal | None:
        return self.source_exit_order.limit_price

    @property
    def stop_price(self) -> Decimal | None:
        return self.source_exit_order.stop_price

    @property
    def symbol(self) -> str:
        return self.source_exit_order.symbol

    @property
    def timeframe(self) -> str:
        return self.source_exit_order.timeframe

    @property
    def originating_timestamp(self):
        return self.source_exit_order.originating_timestamp

    @property
    def strategy_id(self) -> str:
        return self.source_exit_order.strategy_id

    @property
    def strategy_version(self) -> str:
        return self.source_exit_order.strategy_version


@dataclass(frozen=True)
class ConcreteOpenInstruction:
    """Option-entry open instruction evaluated by the execution layer.

    This is a nonbreaking extension for option entry in paper/live modes.
    It retains the original semantic entry order as provenance while
    exposing the concrete opening side, quantity, and execution symbol
    needed for normal execution evaluation.

    For semantic SELL (bearish) -> PE selection -> executable BUY PE:
      - source_entry_order.source_intent.action == "SELL" (provenance)
      - source_entry_order.source_intent.symbol == underlying (provenance)
      - opening_action == "BUY" (executable side)
      - execution_symbol == concrete option contract instrument
    """

    source_entry_order: OrderRequest
    opening_action: Literal["BUY", "SELL"]
    execution_symbol: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_entry_order, OrderRequest):
            raise TypeError("source_entry_order must be an OrderRequest")
        if self.source_entry_order.action not in ("BUY", "SELL"):
            raise ValueError("source_entry_order must preserve a BUY or SELL action")
        if self.opening_action not in ("BUY", "SELL"):
            raise ValueError("opening_action must be BUY or SELL")
        if not isinstance(self.execution_symbol, str) or not self.execution_symbol.strip():
            raise ValueError("execution_symbol must be a non-empty string")
        object.__setattr__(self, "execution_symbol", self.execution_symbol.strip())

    @property
    def action(self) -> Literal["BUY", "SELL"]:
        return self.opening_action

    @property
    def source_intent(self) -> SignalIntent:
        return self.source_entry_order.source_intent

    @property
    def order_type(self) -> OrderType:
        return self.source_entry_order.order_type

    @property
    def time_in_force(self) -> TimeInForce:
        return self.source_entry_order.time_in_force

    @property
    def limit_price(self) -> Decimal | None:
        return self.source_entry_order.limit_price

    @property
    def stop_price(self) -> Decimal | None:
        return self.source_entry_order.stop_price

    @property
    def symbol(self) -> str:
        """Concrete option contract instrument (not the underlying)."""
        return self.execution_symbol

    @property
    def timeframe(self) -> str:
        return self.source_entry_order.timeframe

    @property
    def originating_timestamp(self):
        return self.source_entry_order.originating_timestamp

    @property
    def strategy_id(self) -> str:
        return self.source_entry_order.strategy_id

    @property
    def strategy_version(self) -> str:
        return self.source_entry_order.strategy_version

    @property
    def quantity(self) -> Decimal:
        """Single authority: delegates to source_entry_order.quantity."""
        return self.source_entry_order.quantity
