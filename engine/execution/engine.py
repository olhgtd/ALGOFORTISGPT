"""Deterministic next-bar OHLC execution without portfolio mutation."""

from datetime import datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from engine.backtest.engine import BarEvent, _timeframe_duration
from engine.execution.model import (ExecutableOrder, ExecutionOutcome, ExecutionResult,
                                    StopLimitActivationBasis, StopLimitActivationEvidence)
from engine.execution.slippage import SlippageModel, ZeroSlippage
from engine.market.profile import MarketProfile, MarketSessionBoundary, WeekendCalendar
from engine.core.numeric import as_decimal
from engine.orders import ConcreteCloseInstruction, OrderRequest, OrderType, TimeInForce


class ExecutionEngine:
    """Evaluate one order against one legally available market bar."""

    lower_timeframe_resolver_available = False

    def __init__(
        self,
        slippage_model: SlippageModel | None = None,
        *,
        calendars: Mapping[str, WeekendCalendar] | None = None,
    ) -> None:
        self._slippage_model = slippage_model or ZeroSlippage()
        if not isinstance(getattr(self._slippage_model, "model_id", None), str):
            raise TypeError("slippage_model must expose a string model_id")
        if calendars is not None:
            values = dict(calendars)
            if not values:
                raise ValueError("calendars must not be empty when supplied")
            if not all(
                isinstance(key, str) and key.strip() and isinstance(value, WeekendCalendar)
                for key, value in values.items()
            ):
                raise TypeError("calendars must map non-empty calendar_id strings to WeekendCalendar instances")
            self._calendars = MappingProxyType(values)
        else:
            self._calendars = None

    @property
    def calendars(self) -> Mapping[str, WeekendCalendar] | None:
        """Read-only calendar authority; None preserves the legacy default boundary."""
        return self._calendars

    def evaluate(
        self,
        order: ExecutableOrder,
        bar: BarEvent,
        market_profile: MarketProfile,
        *,
        stop_limit_activation: StopLimitActivationEvidence | None = None,
    ) -> ExecutionResult:
        """Evaluate one request without inspecting any future bar or account state.

        ``stop_limit_activation`` carries immutable STOP_LIMIT activation
        evidence produced by a prior authoritative trigger; when supplied the
        order is evaluated as an already-active LIMIT.  Existing callers
        without the argument remain valid (STOP_LIMIT then evaluates trigger
        detection from scratch, preserving prior frozen behavior for
        non-activated evaluation).
        """
        if not isinstance(order, (OrderRequest, ConcreteCloseInstruction)):
            raise TypeError("order must be an executable order")
        if stop_limit_activation is not None:
            if not isinstance(stop_limit_activation, StopLimitActivationEvidence):
                raise TypeError("stop_limit_activation must be StopLimitActivationEvidence or None")
            if order.order_type is not OrderType.STOP_LIMIT:
                raise ValueError("stop_limit_activation evidence is valid only for STOP_LIMIT orders")
        if not isinstance(bar, BarEvent):
            raise TypeError("bar must be a BarEvent")
        if not isinstance(market_profile, MarketProfile):
            raise TypeError("market_profile must be a MarketProfile")
        if bar.symbol.casefold() != order.symbol:
            return self._result(order, ExecutionOutcome.INELIGIBLE, bar.timestamp, reason="symbol_mismatch", stop_limit_activation=stop_limit_activation)
        if bar.timeframe != order.timeframe:
            return self._result(order, ExecutionOutcome.INELIGIBLE, bar.timestamp, reason="timeframe_mismatch", stop_limit_activation=stop_limit_activation)
        if bar.timestamp <= order.originating_timestamp:
            return self._result(order, ExecutionOutcome.INELIGIBLE, bar.timestamp, reason="originating_or_prior_bar", stop_limit_activation=stop_limit_activation)

        if self._calendars is not None:
            try:
                calendar = self._calendars[market_profile.calendar_id]
            except KeyError:
                raise ValueError(
                    f"no authoritative calendar for calendar_id {market_profile.calendar_id!r}"
                ) from None
            boundary = MarketSessionBoundary(market_profile, calendar=calendar)
        else:
            boundary = MarketSessionBoundary(market_profile)
        if (
            order.time_in_force is TimeInForce.DAY
            and boundary.session_date(bar.timestamp)
            > boundary.session_date(order.originating_timestamp)
        ):
            return self._result(order, ExecutionOutcome.EXPIRED, bar.timestamp, reason="day_order_expired", stop_limit_activation=stop_limit_activation)
        exchange_bar = boundary.exchange_timestamp(bar.timestamp)
        session_close = datetime.combine(
            boundary.session_date(bar.timestamp),
            market_profile.regular_session_close,
            tzinfo=market_profile.timezone,
        )
        final_day_interval = (
            order.time_in_force is TimeInForce.DAY
            and exchange_bar + timedelta(minutes=_timeframe_duration(bar.timeframe)) >= session_close
        )
        if not boundary.is_regular_session(bar.timestamp):
            return self._result(order, ExecutionOutcome.INELIGIBLE, bar.timestamp, reason="outside_regular_session", stop_limit_activation=stop_limit_activation)
        if bar.is_synthetic:
            if final_day_interval:
                return self._result(order, ExecutionOutcome.EXPIRED, bar.timestamp, reason="day_session_expired", stop_limit_activation=stop_limit_activation)
            return self._result(order, ExecutionOutcome.INELIGIBLE, bar.timestamp, reason="synthetic_bar", stop_limit_activation=stop_limit_activation)
        result = self._evaluate_real(order, bar, stop_limit_activation=stop_limit_activation)
        if final_day_interval and result.outcome is not ExecutionOutcome.FILLED:
            return self._result(order, ExecutionOutcome.EXPIRED, bar.timestamp, reason="day_session_expired", stop_limit_activation=result.stop_limit_activation)
        return result

    def end_of_data(
        self,
        order: ExecutableOrder,
        *,
        stop_limit_activation: StopLimitActivationEvidence | None = None,
    ) -> ExecutionResult:
        """Preserve a GTC order at dataset end; dataset exhaustion is not cancellation."""
        if not isinstance(order, (OrderRequest, ConcreteCloseInstruction)):
            raise TypeError("order must be an executable order")
        if stop_limit_activation is not None and order.order_type is not OrderType.STOP_LIMIT:
            raise ValueError("stop_limit_activation evidence is valid only for STOP_LIMIT orders")
        if order.time_in_force is TimeInForce.GTC:
            return self._result(order, ExecutionOutcome.OUTSTANDING, None, reason="dataset_exhausted", stop_limit_activation=stop_limit_activation)
        return self._result(order, ExecutionOutcome.UNFILLED, None, reason="day_requires_session_expiry_evaluation", stop_limit_activation=stop_limit_activation)

    def _evaluate_real(
        self,
        order: ExecutableOrder,
        bar: BarEvent,
        *,
        stop_limit_activation: StopLimitActivationEvidence | None = None,
    ) -> ExecutionResult:
        if order.action == "EXIT":
            return self._result(
                order,
                ExecutionOutcome.REQUIRES_PORTFOLIO_RESOLUTION,
                bar.timestamp,
                reason="exit_requires_position_side_and_quantity",
                stop_limit_activation=stop_limit_activation,
            )
        if order.order_type is OrderType.STOP_LIMIT:
            basis, activation = self._stop_limit_evaluation(order, bar, stop_limit_activation)
        else:
            if stop_limit_activation is not None:
                raise ValueError("stop_limit_activation evidence is valid only for STOP_LIMIT orders")
            basis = self._fill_basis(order, bar)
            activation = None
        if basis is None:
            return self._result(order, ExecutionOutcome.UNFILLED, bar.timestamp, reason="order_conditions_not_met", stop_limit_activation=activation)
        fill_price = self._slippage_model.apply(action=order.action, price=basis, bar=bar)
        fill_price = as_decimal(fill_price, "slippage fill_price")
        if fill_price <= 0:
            raise ValueError("slippage model must return a positive price")
        if order.order_type in {OrderType.LIMIT, OrderType.STOP_LIMIT}:
            fill_price = min(fill_price, order.limit_price) if order.action == "BUY" else max(fill_price, order.limit_price)
        return ExecutionResult(
            order=order,
            outcome=ExecutionOutcome.FILLED,
            execution_bar_timestamp=bar.timestamp,
            pre_slippage_price=basis,
            fill_price=fill_price,
            filled_quantity=order.quantity,
            reason=None,
            slippage_model_id=self._slippage_model.model_id,
            slippage_amount=fill_price - basis,
            metadata=order.source_intent.metadata,
            stop_limit_activation=activation,
        )

    @staticmethod
    def _fill_basis(order: ExecutableOrder, bar: BarEvent) -> Decimal | None:
        if order.order_type is OrderType.MARKET:
            return bar.open
        if order.order_type is OrderType.LIMIT:
            if order.action == "BUY":
                return bar.open if bar.open <= order.limit_price else (order.limit_price if bar.low <= order.limit_price else None)
            return bar.open if bar.open >= order.limit_price else (order.limit_price if bar.high >= order.limit_price else None)
        if order.order_type is OrderType.STOP:
            if order.action == "BUY":
                return bar.open if bar.open >= order.stop_price else (order.stop_price if bar.high >= order.stop_price else None)
            return bar.open if bar.open <= order.stop_price else (order.stop_price if bar.low <= order.stop_price else None)
        return ExecutionEngine._stop_limit_basis(order, bar)

    @staticmethod
    def _stop_limit_basis(order: ExecutableOrder, bar: BarEvent) -> Decimal | None:
        """Legacy stateless trigger-then-limit basis used by ``_fill_basis``.

        Kept for the not-yet-activated evaluation path; the activation-aware
        path is ``_stop_limit_evaluation`` which additionally produces
        immutable activation evidence so a triggered-but-unfilled order is
        later evaluated as an active LIMIT.
        """
        basis, _ = ExecutionEngine._stop_limit_evaluation(order, bar, None)
        return basis

    @staticmethod
    def _stop_limit_evaluation(
        order: ExecutableOrder,
        bar: BarEvent,
        prior_activation: StopLimitActivationEvidence | None,
    ) -> tuple[Decimal | None, StopLimitActivationEvidence | None]:
        """Return (fill basis, activation evidence) for one STOP_LIMIT evaluation.

        NOT_YET_ACTIVATED (prior_activation is None): the eligible real bar is
        inspected for an authoritative STOP trigger.  An OPEN/GAP trigger
        (``bar.open >= stop`` for BUY, ``bar.open <= stop`` for SELL) is
        authoritative and creates activation evidence with the existing OPEN
        trigger basis; an intrabar stop touch is authoritative and creates
        evidence with the stop price.  Same-bar FILL stays governed by the
        existing conservative STOP_LIMIT ambiguity rule: no assumed fill when
        the limit is not executable at the trigger, but activation evidence is
        retained so later bars evaluate the order as an active LIMIT.

        ALREADY-ACTIVATED (prior_activation is not None): the STOP trigger is
        NOT inspected again; the original LIMIT is evaluated with the existing
        LIMIT basis and the prior immutable activation evidence is preserved.
        """
        if order.action == "BUY":
            if prior_activation is not None:
                return ExecutionEngine._limit_basis("BUY", order.limit_price, bar), prior_activation
            if bar.open >= order.stop_price:
                activation = StopLimitActivationEvidence(
                    activation_bar_timestamp=bar.timestamp,
                    activation_price=bar.open,
                    activation_basis=StopLimitActivationBasis.OPEN,
                )
                return ExecutionEngine._limit_basis("BUY", order.limit_price, bar), activation
            if bar.high < order.stop_price:
                return None, None
            activation = StopLimitActivationEvidence(
                activation_bar_timestamp=bar.timestamp,
                activation_price=order.stop_price,
                activation_basis=StopLimitActivationBasis.INTRABAR_STOP_TOUCH,
            )
            # Intrabar activation is only unambiguous if the limit is eligible at trigger.
            return (order.stop_price if order.limit_price >= order.stop_price else None), activation
        if prior_activation is not None:
            return ExecutionEngine._limit_basis("SELL", order.limit_price, bar), prior_activation
        if bar.open <= order.stop_price:
            activation = StopLimitActivationEvidence(
                activation_bar_timestamp=bar.timestamp,
                activation_price=bar.open,
                activation_basis=StopLimitActivationBasis.OPEN,
            )
            return ExecutionEngine._limit_basis("SELL", order.limit_price, bar), activation
        if bar.low > order.stop_price:
            return None, None
        activation = StopLimitActivationEvidence(
            activation_bar_timestamp=bar.timestamp,
            activation_price=order.stop_price,
            activation_basis=StopLimitActivationBasis.INTRABAR_STOP_TOUCH,
        )
        return (order.stop_price if order.limit_price <= order.stop_price else None), activation

    @staticmethod
    def _limit_basis(action: str, limit_price: Decimal, bar: BarEvent) -> Decimal | None:
        if action == "BUY":
            return bar.open if bar.open <= limit_price else (limit_price if bar.low <= limit_price else None)
        return bar.open if bar.open >= limit_price else (limit_price if bar.high >= limit_price else None)

    def _result(
        self,
        order: ExecutableOrder,
        outcome: ExecutionOutcome,
        timestamp: datetime | None,
        *,
        reason: str,
        stop_limit_activation: StopLimitActivationEvidence | None = None,
    ) -> ExecutionResult:
        return ExecutionResult(
            order=order,
            outcome=outcome,
            execution_bar_timestamp=timestamp,
            pre_slippage_price=None,
            fill_price=None,
            filled_quantity=0,
            reason=reason,
            slippage_model_id=self._slippage_model.model_id,
            slippage_amount=Decimal("0"),
            metadata=order.source_intent.metadata,
            stop_limit_activation=stop_limit_activation,
        )
