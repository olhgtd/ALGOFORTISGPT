"""Immutable, broker-agnostic Slice 8 transaction-cost contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from enum import Enum
from typing import Iterable

from engine.portfolio.model import INTERNAL_DECIMAL_CONTEXT, InstrumentIdentity, as_decimal
from engine.reproducibility.codec import CanonicalCodec
from engine.trades import LedgerEventKey, TradeLeg, TradeRecord


class CostUnavailableError(ValueError):
    """Raised when no configured schedule applies to required evidence."""


class CostScheduleAmbiguityError(ValueError):
    """Raised when more than one competing schedule applies."""


class CostBasis(str, Enum):
    FIXED = "FIXED"
    PER_UNIT = "PER_UNIT"
    NOTIONAL = "NOTIONAL"
    DEPENDENCY = "DEPENDENCY"


class CostSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    BOTH = "BOTH"


class NetTradeClassification(str, Enum):
    """Read-only net outcome classification; gross trade evidence is unchanged."""

    WIN = "WIN"
    LOSS = "LOSS"
    BREAK_EVEN = "BREAK_EVEN"


_ROUNDING_MODES = {"ROUND_HALF_EVEN": ROUND_HALF_EVEN}


def _identity_fields(value: InstrumentIdentity) -> tuple[object, ...]:
    """Canonical D4 fields for one full InstrumentIdentity, established order."""
    return (
        value.market,
        value.instrument,
        value.segment,
        value.underlying,
        value.expiry,
        value.strike,
        value.option_type,
    )


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _enum(value, enum_type, name: str):
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid {name}") from error


@dataclass(frozen=True)
class CostComponentRule:
    component_id: str
    basis: CostBasis
    rate: Decimal | int | float | str
    side: CostSide = CostSide.BOTH
    minimum: Decimal | int | float | str | None = None
    maximum: Decimal | int | float | str | None = None
    rounding_quantum: Decimal | int | float | str | None = None
    rounding_mode: str = "ROUND_HALF_EVEN"
    dependency_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_id", _text(self.component_id, "component_id"))
        object.__setattr__(self, "basis", _enum(self.basis, CostBasis, "basis"))
        object.__setattr__(self, "side", _enum(self.side, CostSide, "side"))
        rate = as_decimal(self.rate, "rate")
        if rate < 0:
            raise ValueError("rate cannot be negative")
        object.__setattr__(self, "rate", rate)
        if self.rounding_quantum is None:
            raise ValueError("rounding_quantum must be explicitly supplied")
        quantum = as_decimal(self.rounding_quantum, "rounding_quantum")
        if quantum <= 0:
            raise ValueError("rounding_quantum must be positive")
        object.__setattr__(self, "rounding_quantum", quantum)
        if self.rounding_mode not in _ROUNDING_MODES:
            raise ValueError("unsupported rounding_mode")
        minimum = None if self.minimum is None else as_decimal(self.minimum, "minimum")
        maximum = None if self.maximum is None else as_decimal(self.maximum, "maximum")
        if minimum is not None and minimum < 0:
            raise ValueError("minimum cannot be negative")
        if maximum is not None and maximum < 0:
            raise ValueError("maximum cannot be negative")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("minimum cannot exceed maximum")
        object.__setattr__(self, "minimum", minimum)
        object.__setattr__(self, "maximum", maximum)
        dependencies = tuple(_text(value, "dependency_id") for value in self.dependency_ids)
        if len(set(dependencies)) != len(dependencies):
            raise ValueError("dependency_ids must be unique")
        if self.component_id in dependencies:
            raise ValueError("component cannot depend on itself")
        if self.basis is CostBasis.DEPENDENCY and not dependencies:
            raise ValueError("dependency basis requires dependency_ids")
        if self.basis is not CostBasis.DEPENDENCY and dependencies:
            raise ValueError("dependency_ids require dependency basis")
        object.__setattr__(self, "dependency_ids", dependencies)


@dataclass(frozen=True)
class CostSchedule:
    schedule_id: str
    version: str
    currency: str
    effective_from: datetime
    effective_to: datetime | None
    component_rules: tuple[CostComponentRule, ...]
    market: str | None = None
    instrument: str | None = None
    segment: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "schedule_id", _text(self.schedule_id, "schedule_id"))
        object.__setattr__(self, "version", _text(self.version, "version"))
        object.__setattr__(self, "currency", _text(self.currency, "currency"))
        _aware(self.effective_from, "effective_from")
        if self.effective_to is not None:
            _aware(self.effective_to, "effective_to")
            if self.effective_to < self.effective_from:
                raise ValueError("effective_to cannot precede effective_from")
        rules = tuple(self.component_rules)
        if not all(isinstance(rule, CostComponentRule) for rule in rules):
            raise TypeError("component_rules must contain CostComponentRule values")
        ids = [rule.component_id for rule in rules]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate component identity is ambiguous")
        for field_name, canonicalize in (
            ("market", str.lower),
            ("instrument", str.upper),
            ("segment", str.lower),
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, canonicalize(_text(value, field_name)))
        object.__setattr__(self, "component_rules", rules)

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "sentinelx-cost-schedule/v2",
            (
                ("schedule_id", self.schedule_id),
                ("version", self.version),
                ("currency", self.currency),
                ("effective_from", self.effective_from),
                ("effective_to", self.effective_to),
                ("market", self.market),
                ("instrument", self.instrument),
                ("segment", self.segment),
                ("rules", tuple(
                    (
                        ("component_id", rule.component_id),
                        ("basis", rule.basis),
                        ("rate", rule.rate),
                        ("side", rule.side),
                        ("minimum", rule.minimum),
                        ("maximum", rule.maximum),
                        ("rounding_quantum", rule.rounding_quantum),
                        ("rounding_mode", rule.rounding_mode),
                        ("dependency_ids", rule.dependency_ids),
                    )
                    for rule in self.component_rules
                )),
            ),
        )

    @property
    def reference(self) -> "ScheduleReference":
        return ScheduleReference(self.schedule_id, self.version, self.fingerprint)

    def applies_to(self, trade: TradeRecord, timestamp: datetime) -> bool:
        _aware(timestamp, "execution_timestamp")
        identity = trade.instrument_identity
        return (
            self.effective_from <= timestamp
            and (self.effective_to is None or timestamp <= self.effective_to)
            and (self.market is None or self.market == identity.market)
            and (self.instrument is None or self.instrument == identity.instrument)
            and (self.segment is None or self.segment == identity.segment)
        )


@dataclass(frozen=True, order=True)
class ScheduleReference:
    """Minimal immutable assessment-level schedule provenance."""

    schedule_id: str
    version: str
    fingerprint: str

    def __post_init__(self) -> None:
        for field_name in ("schedule_id", "version", "fingerprint"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))


def trade_evidence_fingerprint(trade: TradeRecord) -> str:
    """Hash only immutable, cost-relevant completed-trade evidence."""
    if not isinstance(trade, TradeRecord):
        raise TypeError("trade must be a TradeRecord")

    def identity(value):
        return _identity_fields(value)

    def leg(value: TradeLeg):
        return (
            ("event_key", (value.event_key.run_id, value.event_key.accounting_sequence)),
            ("role", value.role),
            ("execution_timestamp", value.execution_timestamp),
            ("execution_price", value.execution_price),
            ("execution_quantity", value.execution_quantity),
            ("realized_pnl_delta", value.realized_pnl_delta),
        )

    return CanonicalCodec.fingerprint(
        "sentinelx-trade-evidence/v2",
        (
            ("trade_id", trade.trade_id),
            ("account_id", trade.account_id),
            ("currency", trade.currency),
            ("monetary_quantum", trade.monetary_quantum),
            ("instrument_identity", identity(trade.instrument_identity)),
            ("position_key", (
                ("strategy_id", trade.position_key.strategy_id),
                ("strategy_version", trade.position_key.strategy_version),
                ("identity", identity(trade.position_key.identity)),
            )),
            ("contract_multiplier", trade.contract_multiplier),
            ("gross_realized_pnl", trade.gross_realized_pnl),
            ("entry_legs", tuple(leg(value) for value in trade.entry_legs)),
            ("exit_legs", tuple(leg(value) for value in trade.exit_legs)),
        ),
    )


def assessment_identity(trade_fingerprint: str, references: tuple[ScheduleReference, ...]) -> str:
    """Derive a collision-safe assessment identity from canonical provenance."""
    return CanonicalCodec.fingerprint(
        "sentinelx-cost-assessment/v2",
        (
            ("trade_evidence_fingerprint", _text(trade_fingerprint, "trade_evidence_fingerprint")),
            ("schedules", tuple(
                (value.schedule_id, value.version, value.fingerprint)
                for value in references
            )),
        ),
    )


def leg_assessment_identity(leg_event_key: LedgerEventKey, schedule: ScheduleReference, evidence_fingerprint: str) -> str:
    """Canonical v2 identity for one accepted execution-backed economic leg."""
    return CanonicalCodec.fingerprint(
        "sentinelx-cost-leg-assessment/v2",
        (
            ("run_id", leg_event_key.run_id),
            ("accounting_sequence", leg_event_key.accounting_sequence),
            ("schedule", (schedule.schedule_id, schedule.version, schedule.fingerprint)),
            ("evidence", _text(evidence_fingerprint, "evidence_fingerprint")),
        ),
    )


def leg_evidence_fingerprint(leg: TradeLeg, account_id: str, currency: str, identity: InstrumentIdentity, multiplier: Decimal) -> str:
    """Canonical cost-relevant accepted-leg evidence, independent of trade closure."""
    return CanonicalCodec.fingerprint(
        "sentinelx-cost-leg-evidence/v2",
        (
            ("event_key", (leg.event_key.run_id, leg.event_key.accounting_sequence)),
            ("account_id", _text(account_id, "account_id")),
            ("currency", _text(currency, "currency")),
            ("identity", _identity_fields(identity)),
            ("role", leg.role),
            ("timestamp", leg.execution_timestamp),
            ("price", leg.execution_price),
            ("quantity", leg.execution_quantity),
            ("multiplier", multiplier),
        ),
    )


def cost_evidence_fingerprint(
    leg_assessments: Iterable["CostLegAssessment"],
    completed_assessments: Iterable["CostAssessment"],
) -> str:
    """Canonical result-side cost evidence; policy remains manifest-side input."""
    legs = tuple(leg_assessments)
    completed = tuple(completed_assessments)
    if not all(isinstance(value, CostLegAssessment) for value in legs):
        raise TypeError("leg_assessments must contain CostLegAssessment values")
    if not all(isinstance(value, CostAssessment) for value in completed):
        raise TypeError("completed_assessments must contain CostAssessment values")
    if len({value.assessment_id for value in legs}) != len(legs):
        raise ValueError("duplicate CostLegAssessment identity is ambiguous")
    if len({value.assessment_id for value in completed}) != len(completed):
        raise ValueError("duplicate CostAssessment identity is ambiguous")
    return CanonicalCodec.fingerprint(
        "sentinelx-cost-result-evidence/v2",
        (
            ("leg_assessments", tuple(sorted(
                (
                    value.assessment_id,
                    value.evidence_fingerprint,
                    value.total_cost,
                    tuple(
                        (
                            component.component_id,
                            component.basis,
                            component.schedule_id,
                            component.schedule_version,
                            component.schedule_fingerprint,
                            component.input_amount,
                            component.rate,
                            component.unrounded_amount,
                            component.amount,
                        )
                        for component in value.component_results
                    ),
                )
                for value in legs
            ))),
            ("completed_assessments", tuple(sorted(
                (
                    value.assessment_id,
                    value.trade_evidence_fingerprint,
                    value.total_cost,
                    value.net_realized_pnl,
                    tuple(
                        (
                            component.component_id,
                            component.leg_event_key.run_id,
                            component.leg_event_key.accounting_sequence,
                            component.basis,
                            component.schedule_id,
                            component.schedule_version,
                            component.schedule_fingerprint,
                            component.input_amount,
                            component.rate,
                            component.unrounded_amount,
                            component.amount,
                        )
                        for component in value.component_results
                    ),
                )
                for value in completed
            ))),
        ),
    )


@dataclass(frozen=True)
class CostComponentResult:
    component_id: str
    leg_event_key: LedgerEventKey
    basis: CostBasis
    schedule_id: str
    schedule_version: str
    schedule_fingerprint: str
    input_amount: Decimal
    rate: Decimal
    unrounded_amount: Decimal
    amount: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_id", _text(self.component_id, "component_id"))
        if not isinstance(self.leg_event_key, LedgerEventKey):
            raise TypeError("leg_event_key must be a LedgerEventKey")
        object.__setattr__(self, "basis", _enum(self.basis, CostBasis, "basis"))
        for field_name in ("schedule_id", "schedule_version", "schedule_fingerprint"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        for field_name in ("input_amount", "rate", "unrounded_amount", "amount"):
            value = as_decimal(getattr(self, field_name), field_name)
            if field_name == "amount" and value < 0:
                raise ValueError("amount cannot be negative")
            object.__setattr__(self, field_name, value)


@dataclass(frozen=True)
class CostLegAssessment:
    """Immutable pre-closure cost evidence for one accepted economic leg."""

    version: str
    assessment_id: str
    leg_event_key: LedgerEventKey
    account_id: str
    currency: str
    instrument_identity: InstrumentIdentity
    side: CostSide
    execution_timestamp: datetime
    execution_price: Decimal
    execution_quantity: Decimal
    contract_multiplier: Decimal
    monetary_quantum: Decimal
    schedule_reference: ScheduleReference
    component_results: tuple[CostComponentResult, ...]
    total_cost: Decimal
    evidence_fingerprint: str

    def __post_init__(self) -> None:
        if self.version != "sentinelx-cost-leg-assessment/v2":
            raise ValueError("unknown CostLegAssessment schema version")
        if (not isinstance(self.leg_event_key, LedgerEventKey)
                or not isinstance(self.schedule_reference, ScheduleReference)
                or not isinstance(self.instrument_identity, InstrumentIdentity)):
            raise TypeError("leg_event_key, schedule_reference, and instrument_identity are required")
        _text(self.account_id, "account_id"); _text(self.currency, "currency")
        _aware(self.execution_timestamp, "execution_timestamp")
        object.__setattr__(self, "side", _enum(self.side, CostSide, "side"))
        for name in ("execution_price", "execution_quantity", "contract_multiplier", "monetary_quantum", "total_cost"):
            value = as_decimal(getattr(self, name), name)
            if name != "total_cost" and value <= 0:
                raise ValueError(f"{name} must be positive")
            if name == "total_cost" and value < 0:
                raise ValueError("total_cost cannot be negative")
            object.__setattr__(self, name, value)
        results = tuple(self.component_results)
        if not all(isinstance(value, CostComponentResult) for value in results):
            raise TypeError("component_results must contain CostComponentResult values")
        if any(value.leg_event_key != self.leg_event_key for value in results):
            raise ValueError("component result must bind the assessed leg")
        object.__setattr__(self, "component_results", tuple(sorted(results, key=lambda value: value.component_id)))
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            total = sum((value.amount for value in results), Decimal("0")).quantize(self.monetary_quantum, rounding=ROUND_HALF_EVEN)
        if self.total_cost != total:
            raise ValueError("total_cost must equal component results")
        evidence = _text(self.evidence_fingerprint, "evidence_fingerprint")
        object.__setattr__(self, "evidence_fingerprint", evidence)
        expected = leg_assessment_identity(self.leg_event_key, self.schedule_reference, evidence)
        if self.assessment_id != expected:
            raise ValueError("CostLegAssessment identity does not match evidence")


@dataclass(frozen=True)
class CostAssessment:
    assessment_id: str
    trade_evidence_fingerprint: str
    trade_id: str
    account_id: str
    currency: str
    schedule_references: tuple[ScheduleReference, ...]
    component_results: tuple[CostComponentResult, ...]
    total_cost: Decimal
    gross_realized_pnl: Decimal
    net_realized_pnl: Decimal
    trade_record: TradeRecord

    def __post_init__(self) -> None:
        _text(self.assessment_id, "assessment_id")
        object.__setattr__(self, "trade_evidence_fingerprint", _text(self.trade_evidence_fingerprint, "trade_evidence_fingerprint"))
        _text(self.trade_id, "trade_id")
        _text(self.account_id, "account_id")
        _text(self.currency, "currency")
        if not isinstance(self.trade_record, TradeRecord):
            raise TypeError("trade_record must be a TradeRecord")
        if self.trade_record.trade_id != self.trade_id or self.trade_record.account_id != self.account_id:
            raise ValueError("assessment provenance does not match trade")
        results = tuple(self.component_results)
        if not all(isinstance(result, CostComponentResult) for result in results):
            raise TypeError("component_results must contain CostComponentResult values")
        object.__setattr__(self, "component_results", results)
        references = tuple(self.schedule_references)
        if not references or not all(isinstance(value, ScheduleReference) for value in references):
            raise ValueError("schedule_references must be non-empty ScheduleReference values")
        if len(set(references)) != len(references):
            raise ValueError("schedule_references must be unique")
        object.__setattr__(self, "schedule_references", tuple(sorted(references)))
        for field_name in ("total_cost", "gross_realized_pnl", "net_realized_pnl"):
            value = as_decimal(getattr(self, field_name), field_name)
            object.__setattr__(self, field_name, value)
        if self.currency != self.trade_record.currency:
            raise ValueError("assessment currency does not match trade")
        if self.gross_realized_pnl != self.trade_record.gross_realized_pnl:
            raise ValueError("assessment gross P&L does not match trade")
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            total_from_components = sum((result.amount for result in results), Decimal("0"))
            expected_total = total_from_components.quantize(
                self.trade_record.monetary_quantum, rounding=ROUND_HALF_EVEN
            )
            expected_net = self.gross_realized_pnl - self.total_cost
        if self.total_cost != expected_total:
            raise ValueError("assessment total cost does not match component results")
        if self.net_realized_pnl != expected_net:
            raise ValueError("assessment net P&L must equal gross P&L minus total cost")
        if self.trade_evidence_fingerprint != trade_evidence_fingerprint(self.trade_record):
            raise ValueError("assessment trade evidence fingerprint does not match trade")
        if self.assessment_id != assessment_identity(self.trade_evidence_fingerprint, self.schedule_references):
            raise ValueError("assessment identity does not match immutable provenance")

    @property
    def schedule_fingerprints(self) -> tuple[str, ...]:
        """Compatibility view of the immutable schedule references."""
        return tuple(value.fingerprint for value in self.schedule_references)

    @property
    def net_classification(self) -> NetTradeClassification:
        if self.net_realized_pnl > 0:
            return NetTradeClassification.WIN
        if self.net_realized_pnl < 0:
            return NetTradeClassification.LOSS
        return NetTradeClassification.BREAK_EVEN
