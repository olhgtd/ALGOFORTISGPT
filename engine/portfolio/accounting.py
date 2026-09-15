"""Deterministic long-only, single-currency portfolio accounting."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from types import MappingProxyType

from engine.backtest.engine import BarEvent
from engine.execution.model import ExecutionOutcome, ExecutionResult
from engine.orders import ConcreteCloseInstruction, OrderRequest
from engine.reproducibility.codec import CanonicalCodec
from engine.portfolio.model import (
    AccountSnapshot,
    AccountingOutcome,
    AccountingResult,
    InstrumentIdentity,
    InstrumentSpecification,
    PositionKey,
    PositionSnapshot,
    INTERNAL_DECIMAL_CONTEXT,
    as_decimal,
    is_price_aligned,
    quantize_monetary,
)


def _text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


@dataclass(frozen=True)
class PortfolioAccount:
    """A stateless transformer from immutable snapshots to immutable results."""

    account_id: str
    currency: str
    starting_capital: Decimal | int | float | str
    monetary_quantum: Decimal | int | float | str

    def __post_init__(self) -> None:
        _text(self.account_id, "account_id")
        _text(self.currency, "currency")
        monetary_quantum = as_decimal(self.monetary_quantum, "monetary_quantum")
        if monetary_quantum <= 0:
            raise ValueError("monetary_quantum must be positive")
        object.__setattr__(self, "monetary_quantum", monetary_quantum)
        capital = as_decimal(self.starting_capital, "starting_capital")
        if capital < 0:
            raise ValueError("starting_capital cannot be negative")
        object.__setattr__(self, "starting_capital", quantize_monetary(capital, monetary_quantum))

    def initial_snapshot(self) -> AccountSnapshot:
        return AccountSnapshot(
            account_id=self.account_id,
            currency=self.currency,
            monetary_quantum=self.monetary_quantum,
            starting_capital=self.starting_capital,
            cash=self.starting_capital,
            realized_pnl=Decimal("0"),
            positions=MappingProxyType({}),
            aggregate_exposure=MappingProxyType({}),
            as_of_timestamp=None,
        )

    def apply_execution(
        self,
        snapshot: AccountSnapshot,
        execution: ExecutionResult,
        specification: InstrumentSpecification | None,
    ) -> AccountingResult:
        """Apply one filled concrete BUY/SELL execution; never mutate inputs."""
        self._validate_snapshot(snapshot)
        if not isinstance(execution, ExecutionResult) or execution.outcome is not ExecutionOutcome.FILLED:
            return self._reject(snapshot, AccountingOutcome.REJECTED_INVALID_EXECUTION, "execution_must_be_filled", execution)
        if execution.fill_price is None or execution.execution_bar_timestamp is None:
            return self._reject(snapshot, AccountingOutcome.REJECTED_INVALID_EXECUTION, "filled_execution_missing_evidence", execution)
        if not isinstance(specification, InstrumentSpecification):
            return self._reject(snapshot, AccountingOutcome.REJECTED_INSTRUMENT_SPECIFICATION, "missing_or_invalid_specification", execution)
        specification_failure = self._specification_failure(specification, execution)
        if specification_failure is not None:
            return self._reject(snapshot, AccountingOutcome.REJECTED_INSTRUMENT_SPECIFICATION, specification_failure, execution)
        if specification.currency != self.currency:
            return self._reject(snapshot, AccountingOutcome.REJECTED_CURRENCY_MISMATCH, "instrument_currency_mismatch", execution)

        quantity = as_decimal(execution.filled_quantity, "filled_quantity")
        fill_price = as_decimal(execution.fill_price, "fill_price")
        key = PositionKey(execution.order.strategy_id, execution.order.strategy_version, specification.identity)
        provenance = self._provenance(execution.order)
        if execution.action == "BUY":
            with localcontext(INTERNAL_DECIMAL_CONTEXT):
                required_cash = quantize_monetary(quantity * fill_price * specification.contract_multiplier, self.monetary_quantum)
            if snapshot.cash < required_cash:
                return self._reject(snapshot, AccountingOutcome.REJECTED_INSUFFICIENT_CAPITAL, "insufficient_cash", execution, provenance)
            positions = dict(snapshot.positions)
            existing = positions.get(key)
            if existing is not None and (
                existing.contract_multiplier != specification.contract_multiplier
                or existing.valuation_timeframe != execution.timeframe
            ):
                return self._reject(snapshot, AccountingOutcome.REJECTED_INVALID_POSITION, "incompatible_existing_position", execution, provenance)
            if existing is None:
                positions[key] = PositionSnapshot(key, quantity, fill_price, specification.contract_multiplier, fill_price, execution.execution_bar_timestamp, execution.timeframe, specification.price_increment, self.monetary_quantum)
            else:
                total_quantity = existing.quantity + quantity
                with localcontext(INTERNAL_DECIMAL_CONTEXT):
                    average = ((existing.average_entry_price * existing.quantity) + (fill_price * quantity)) / total_quantity
                positions[key] = PositionSnapshot(key, total_quantity, average, existing.contract_multiplier, fill_price, execution.execution_bar_timestamp, existing.valuation_timeframe, existing.price_increment, existing.monetary_quantum)
            with localcontext(INTERNAL_DECIMAL_CONTEXT):
                cash = quantize_monetary(snapshot.cash - required_cash, self.monetary_quantum)
            result = self._snapshot(snapshot, cash=cash, realized_pnl=snapshot.realized_pnl, positions=positions, timestamp=execution.execution_bar_timestamp)
            return AccountingResult(snapshot, result, AccountingOutcome.ACCEPTED, None, execution, provenance)

        if execution.action != "SELL":
            return self._reject(snapshot, AccountingOutcome.REJECTED_INVALID_EXECUTION, "unresolved_exit_cannot_be_accounted", execution, provenance)
        existing = snapshot.positions.get(key)
        if existing is None or existing.quantity < quantity:
            return self._reject(snapshot, AccountingOutcome.REJECTED_INVALID_POSITION, "insufficient_owned_long_quantity", execution, provenance)
        positions = dict(snapshot.positions)
        remaining = existing.quantity - quantity
        if remaining == 0:
            del positions[key]
        else:
            positions[key] = PositionSnapshot(key, remaining, existing.average_entry_price, existing.contract_multiplier, existing.mark_price, existing.mark_timestamp, existing.valuation_timeframe, existing.price_increment, existing.monetary_quantum)
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            proceeds = quantize_monetary(quantity * fill_price * existing.contract_multiplier, self.monetary_quantum)
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            realized_change = (fill_price - existing.average_entry_price) * quantity * existing.contract_multiplier
        realized = quantize_monetary(snapshot.realized_pnl + realized_change, self.monetary_quantum)
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            cash = quantize_monetary(snapshot.cash + proceeds, self.monetary_quantum)
        result = self._snapshot(snapshot, cash=cash, realized_pnl=realized, positions=positions, timestamp=execution.execution_bar_timestamp)
        return AccountingResult(snapshot, result, AccountingOutcome.ACCEPTED, None, execution, provenance)

    def resolve_exit(
        self,
        snapshot: AccountSnapshot,
        exit_order: OrderRequest,
        specification: InstrumentSpecification | None,
        *,
        quantity: Decimal | int | float | str | None = None,
    ) -> AccountingResult:
        """Resolve an explicit EXIT to an owned close instruction, never a fill.

        Omitting ``quantity`` preserves the original full-close behavior.
        Protective exits may supply an explicit quantity, which is rejected if
        it exceeds the currently owned aggregate position.
        """
        self._validate_snapshot(snapshot)
        if not isinstance(exit_order, OrderRequest) or exit_order.action != "EXIT":
            return self._reject(snapshot, AccountingOutcome.REJECTED_INVALID_POSITION, "exit_order_required", exit_order)
        if not isinstance(specification, InstrumentSpecification):
            return self._reject(snapshot, AccountingOutcome.REJECTED_INSTRUMENT_SPECIFICATION, "missing_or_invalid_specification", exit_order)
        if specification.identity.instrument != exit_order.symbol.upper():
            return self._reject(snapshot, AccountingOutcome.REJECTED_INSTRUMENT_SPECIFICATION, "specification_symbol_mismatch", exit_order)
        if specification.currency != self.currency:
            return self._reject(snapshot, AccountingOutcome.REJECTED_CURRENCY_MISMATCH, "instrument_currency_mismatch", exit_order)
        key = PositionKey(exit_order.strategy_id, exit_order.strategy_version, specification.identity)
        position = snapshot.positions.get(key)
        if position is None:
            return self._reject(snapshot, AccountingOutcome.REJECTED_INVALID_POSITION, "no_owned_position_for_exit", exit_order)
        closable_quantity = position.quantity if quantity is None else as_decimal(quantity, "quantity")
        if closable_quantity <= 0 or closable_quantity > position.quantity:
            return self._reject(snapshot, AccountingOutcome.REJECTED_INVALID_POSITION, "invalid_or_excess_exit_quantity", exit_order)
        instruction = ConcreteCloseInstruction(exit_order, "SELL", closable_quantity)
        reason = "exit_resolved_full_close" if closable_quantity == position.quantity else "exit_resolved_partial_close"
        return AccountingResult(snapshot, snapshot, AccountingOutcome.ACCEPTED, reason, exit_order, self._provenance(exit_order), instruction)

    def mark_to_market(self, snapshot: AccountSnapshot, identity: InstrumentIdentity, bar: BarEvent) -> AccountingResult:
        """Mark matching owned positions from one eligible real bar close."""
        self._validate_snapshot(snapshot)
        if not isinstance(identity, InstrumentIdentity) or not isinstance(bar, BarEvent):
            return self._reject(snapshot, AccountingOutcome.REJECTED_INVALID_MARK, "malformed_mark_evidence", bar)
        if bar.is_synthetic:
            return self._reject(snapshot, AccountingOutcome.REJECTED_INVALID_MARK, "synthetic_mark_evidence", bar)
        if bar.symbol.upper() != identity.instrument:
            return self._reject(snapshot, AccountingOutcome.REJECTED_INVALID_MARK, "mark_instrument_mismatch", bar)
        if snapshot.as_of_timestamp is not None and bar.timestamp < snapshot.as_of_timestamp:
            return self._reject(snapshot, AccountingOutcome.REJECTED_INVALID_MARK, "mark_precedes_account_state", bar)
        matching = [position for key, position in snapshot.positions.items() if key.identity == identity]
        if not matching:
            return self._reject(snapshot, AccountingOutcome.REJECTED_INVALID_MARK, "no_open_position_for_instrument", bar)
        if any(position.valuation_timeframe != bar.timeframe for position in matching):
            return self._reject(snapshot, AccountingOutcome.REJECTED_INVALID_MARK, "valuation_timeframe_mismatch", bar)
        if any(not is_price_aligned(as_decimal(bar.close, "mark_price"), position.price_increment) for position in matching):
            return self._reject(snapshot, AccountingOutcome.REJECTED_INVALID_MARK, "mark_price_incompatible_with_specification", bar)
        positions = dict(snapshot.positions)
        for key, position in snapshot.positions.items():
            if key.identity == identity:
                positions[key] = PositionSnapshot(key, position.quantity, position.average_entry_price, position.contract_multiplier, bar.close, bar.timestamp, position.valuation_timeframe, position.price_increment, position.monetary_quantum)
        result = self._snapshot(snapshot, cash=snapshot.cash, realized_pnl=snapshot.realized_pnl, positions=positions, timestamp=bar.timestamp)
        return AccountingResult(snapshot, result, AccountingOutcome.ACCEPTED, None, bar, {"identity": identity.instrument, "mark_timestamp": CanonicalCodec.timestamp_text(bar.timestamp)})

    def _validate_snapshot(self, snapshot: AccountSnapshot) -> None:
        if not isinstance(snapshot, AccountSnapshot):
            raise TypeError("snapshot must be an AccountSnapshot")
        if snapshot.account_id != self.account_id or snapshot.currency != self.currency or snapshot.starting_capital != self.starting_capital:
            raise ValueError("snapshot does not belong to this account")

    @staticmethod
    def _specification_failure(specification: InstrumentSpecification, execution: ExecutionResult) -> str | None:
        if specification.identity.instrument != execution.symbol.upper():
            return "specification_symbol_mismatch"
        if execution.execution_bar_timestamp is None or specification.effective_from > execution.execution_bar_timestamp.date():
            return "specification_not_effective"
        quantity = as_decimal(execution.filled_quantity, "filled_quantity")
        if quantity < specification.minimum_quantity or quantity % specification.quantity_step != 0:
            return "quantity_incompatible_with_specification"
        if execution.fill_price is None or not is_price_aligned(as_decimal(execution.fill_price, "fill_price"), specification.price_increment):
            return "fill_price_incompatible_with_specification"
        return None

    @staticmethod
    def _provenance(order: OrderRequest | ConcreteCloseInstruction) -> dict[str, str]:
        provenance = {
            "strategy_id": order.strategy_id,
            "strategy_version": order.strategy_version,
            "symbol": order.symbol,
            "timeframe": order.timeframe,
            "originating_timestamp": CanonicalCodec.timestamp_text(order.originating_timestamp),
            "action": order.action,
        }
        if isinstance(order, ConcreteCloseInstruction):
            provenance["source_exit_action"] = "EXIT"
        return provenance

    def _snapshot(self, prior: AccountSnapshot, *, cash: Decimal, realized_pnl: Decimal, positions: dict[PositionKey, PositionSnapshot], timestamp: datetime) -> AccountSnapshot:
        exposure: dict[InstrumentIdentity, Decimal] = {}
        for position in positions.values():
            identity = position.key.identity
            exposure[identity] = exposure.get(identity, Decimal("0")) + position.quantity
        return AccountSnapshot(prior.account_id, prior.currency, prior.starting_capital, cash, realized_pnl, positions, exposure, timestamp, prior.monetary_quantum)

    @staticmethod
    def _reject(snapshot: AccountSnapshot, outcome: AccountingOutcome, reason: str, evidence, provenance=None) -> AccountingResult:
        return AccountingResult(snapshot, snapshot, outcome, reason, evidence, provenance or {})
