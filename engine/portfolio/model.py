"""Immutable value objects for the Slice 6 long-only accounting foundation."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from engine.orders import ConcreteCloseInstruction
from engine.core.numeric import as_decimal


INTERNAL_DECIMAL_CONTEXT = Context(prec=50, rounding=ROUND_HALF_EVEN)
INSTRUMENT_IDENTITY_CASE_POLICY = "InstrumentIdentityCasePolicy/v1"


def quantize_monetary(value: Decimal, monetary_quantum: Decimal) -> Decimal:
    """Apply the owner-approved monetary boundary deterministically."""
    with localcontext(INTERNAL_DECIMAL_CONTEXT):
        return value.quantize(monetary_quantum, rounding=ROUND_HALF_EVEN)


def is_price_aligned(value: Decimal, price_increment: Decimal) -> bool:
    """Return whether a supplied executable price is a tradable increment."""
    with localcontext(INTERNAL_DECIMAL_CONTEXT):
        return value % price_increment == 0


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


@dataclass(frozen=True)
class InstrumentIdentity:
    """Collision-safe identity for one concrete tradable instrument."""

    market: str
    instrument: str
    segment: str
    underlying: str | None = None
    expiry: date | None = None
    strike: Decimal | int | float | str | None = None
    option_type: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("market", "instrument", "segment"):
            _require_text(getattr(self, field_name), field_name)
        object.__setattr__(self, "market", self.market.lower())
        object.__setattr__(self, "instrument", self.instrument.upper())
        object.__setattr__(self, "segment", self.segment.lower())
        if self.segment == "options":
            if self.underlying is None or self.expiry is None or self.strike is None or self.option_type is None:
                raise ValueError("options identity requires underlying, expiry, strike, and option_type")
            _require_text(self.underlying, "underlying")
            object.__setattr__(self, "underlying", self.underlying.upper())
            if not isinstance(self.expiry, date):
                raise TypeError("expiry must be a date")
            strike = as_decimal(self.strike, "strike")
            if strike <= 0:
                raise ValueError("strike must be positive")
            _require_text(self.option_type, "option_type")
            object.__setattr__(self, "option_type", self.option_type.upper())
            if self.option_type not in {"CE", "PE"}:
                raise ValueError("option_type must be CE or PE")
            object.__setattr__(self, "strike", strike)
        elif self.segment == "futures":
            if self.expiry is None:
                raise ValueError("futures identity requires expiry")
            if not isinstance(self.expiry, date):
                raise TypeError("expiry must be a date")
            if self.strike is not None or self.option_type is not None:
                raise ValueError("futures identity cannot carry option attributes")
            if self.underlying is not None:
                _require_text(self.underlying, "underlying")
                object.__setattr__(self, "underlying", self.underlying.upper())
        elif any(value is not None for value in (self.underlying, self.expiry, self.strike, self.option_type)):
            raise ValueError("non-option identity cannot carry option attributes")


@dataclass(frozen=True)
class InstrumentSpecification:
    """Authoritative upstream instrument terms consumed by accounting."""

    identity: InstrumentIdentity
    effective_from: date
    contract_multiplier: Decimal | int | float | str
    minimum_quantity: Decimal | int | float | str
    quantity_step: Decimal | int | float | str
    currency: str
    price_increment: Decimal | int | float | str

    def __post_init__(self) -> None:
        if not isinstance(self.identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")
        if not isinstance(self.effective_from, date):
            raise TypeError("effective_from must be a date")
        _require_text(self.currency, "currency")
        for field_name in ("price_increment", "contract_multiplier", "minimum_quantity", "quantity_step"):
            value = as_decimal(getattr(self, field_name), field_name)
            if value <= 0:
                raise ValueError(f"{field_name} must be positive")
            object.__setattr__(self, field_name, value)
        if self.minimum_quantity % self.quantity_step != 0:
            raise ValueError("minimum_quantity must be compatible with quantity_step")


@dataclass(frozen=True)
class PositionKey:
    """Position ownership: strategy identifier, version, and concrete contract."""

    strategy_id: str
    strategy_version: str
    identity: InstrumentIdentity

    def __post_init__(self) -> None:
        _require_text(self.strategy_id, "strategy_id")
        _require_text(self.strategy_version, "strategy_version")
        if not isinstance(self.identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")


@dataclass(frozen=True)
class PositionSnapshot:
    """A marked, long-only position owned by one strategy version."""

    key: PositionKey
    quantity: Decimal | int | float | str
    average_entry_price: Decimal | int | float | str
    contract_multiplier: Decimal | int | float | str
    mark_price: Decimal | int | float | str
    mark_timestamp: datetime
    valuation_timeframe: str
    price_increment: Decimal | int | float | str
    monetary_quantum: Decimal | int | float | str

    def __post_init__(self) -> None:
        if not isinstance(self.key, PositionKey):
            raise TypeError("key must be a PositionKey")
        for field_name in ("quantity", "average_entry_price", "contract_multiplier", "price_increment", "monetary_quantum", "mark_price"):
            value = as_decimal(getattr(self, field_name), field_name)
            if value <= 0:
                raise ValueError(f"{field_name} must be positive")
            object.__setattr__(self, field_name, value)
        if self.mark_timestamp.tzinfo is None or self.mark_timestamp.utcoffset() is None:
            raise ValueError("mark_timestamp must be timezone-aware")
        _require_text(self.valuation_timeframe, "valuation_timeframe")

    @property
    def unrealized_pnl(self) -> Decimal:
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            value = (self.mark_price - self.average_entry_price) * self.quantity * self.contract_multiplier
        return quantize_monetary(value, self.monetary_quantum)

    @property
    def marked_value(self) -> Decimal:
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            return self.mark_price * self.quantity * self.contract_multiplier


@dataclass(frozen=True)
class AccountSnapshot:
    """The complete immutable account state after one accounting operation."""

    account_id: str
    currency: str
    starting_capital: Decimal | int | float | str
    cash: Decimal | int | float | str
    realized_pnl: Decimal | int | float | str
    positions: Mapping[PositionKey, PositionSnapshot]
    aggregate_exposure: Mapping[InstrumentIdentity, Decimal | int | float | str]
    as_of_timestamp: datetime | None
    monetary_quantum: Decimal | int | float | str

    def __post_init__(self) -> None:
        _require_text(self.account_id, "account_id")
        _require_text(self.currency, "currency")
        monetary_quantum = as_decimal(self.monetary_quantum, "monetary_quantum")
        if monetary_quantum <= 0:
            raise ValueError("monetary_quantum must be positive")
        object.__setattr__(self, "monetary_quantum", monetary_quantum)
        for field_name in ("starting_capital", "cash", "realized_pnl"):
            value = as_decimal(getattr(self, field_name), field_name)
            object.__setattr__(self, field_name, quantize_monetary(value, monetary_quantum))
        if self.as_of_timestamp is not None and (
            self.as_of_timestamp.tzinfo is None or self.as_of_timestamp.utcoffset() is None
        ):
            raise ValueError("as_of_timestamp must be timezone-aware")
        positions = dict(self.positions)
        if not all(isinstance(key, PositionKey) and isinstance(value, PositionSnapshot) for key, value in positions.items()):
            raise TypeError("positions must map PositionKey to PositionSnapshot")
        if any(position.monetary_quantum != monetary_quantum for position in positions.values()):
            raise ValueError("position monetary_quantum must match account monetary_quantum")
        exposure = {identity: as_decimal(value, "aggregate_exposure") for identity, value in dict(self.aggregate_exposure).items()}
        if not all(isinstance(identity, InstrumentIdentity) and value >= 0 for identity, value in exposure.items()):
            raise ValueError("aggregate_exposure must contain non-negative InstrumentIdentity values")
        object.__setattr__(self, "positions", MappingProxyType(positions))
        object.__setattr__(self, "aggregate_exposure", MappingProxyType(exposure))

    @property
    def unrealized_pnl(self) -> Decimal:
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            value = sum((position.unrealized_pnl for position in self.positions.values()), Decimal("0"))
        return quantize_monetary(value, self.monetary_quantum)

    @property
    def equity(self) -> Decimal:
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            value = self.cash + sum((position.marked_value for position in self.positions.values()), Decimal("0"))
        return quantize_monetary(value, self.monetary_quantum)


class AccountingOutcome(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED_INSUFFICIENT_CAPITAL = "REJECTED_INSUFFICIENT_CAPITAL"
    REJECTED_INVALID_POSITION = "REJECTED_INVALID_POSITION"
    REJECTED_INVALID_MARK = "REJECTED_INVALID_MARK"
    REJECTED_INSTRUMENT_SPECIFICATION = "REJECTED_INSTRUMENT_SPECIFICATION"
    REJECTED_CURRENCY_MISMATCH = "REJECTED_CURRENCY_MISMATCH"
    REJECTED_INVALID_EXECUTION = "REJECTED_INVALID_EXECUTION"


@dataclass(frozen=True)
class AccountingResult:
    """Auditable immutable output of each portfolio operation."""

    prior_snapshot: AccountSnapshot
    resulting_snapshot: AccountSnapshot
    outcome: AccountingOutcome
    reason: str | None
    source_evidence: Any
    provenance: Mapping[str, Any]
    close_instruction: ConcreteCloseInstruction | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.prior_snapshot, AccountSnapshot) or not isinstance(self.resulting_snapshot, AccountSnapshot):
            raise TypeError("accounting snapshots must be AccountSnapshot values")
        if not isinstance(self.outcome, AccountingOutcome):
            raise TypeError("outcome must be an AccountingOutcome")
        if not isinstance(self.provenance, Mapping):
            raise TypeError("provenance must be a mapping")
        if self.close_instruction is not None and not isinstance(self.close_instruction, ConcreteCloseInstruction):
            raise TypeError("close_instruction must be a ConcreteCloseInstruction")
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))
