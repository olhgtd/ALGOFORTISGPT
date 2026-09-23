"""Versioned instrument-master contracts with deterministic as-of resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from engine.reproducibility.codec import CanonicalCodec


class InstrumentMasterError(ValueError):
    """Raised when instrument metadata is invalid or historically ambiguous."""


def _text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InstrumentMasterError(f"{name} must be non-empty")
    return value.strip()


def _decimal(name: str, value: Decimal | int | str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise InstrumentMasterError(f"{name} must use Decimal/int/string semantics, not float")
    try:
        normalized = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise InstrumentMasterError(f"{name} must be numeric") from exc
    if not normalized.is_finite() or normalized <= 0:
        raise InstrumentMasterError(f"{name} must be positive and finite")
    return normalized


def _date_in_range(day: date, start: date, end: date | None) -> bool:
    return day >= start and (end is None or day <= end)


def _ranges_overlap(
    left_start: date,
    left_end: date | None,
    right_start: date,
    right_end: date | None,
) -> bool:
    return (left_end is None or right_start <= left_end) and (
        right_end is None or left_start <= right_end
    )


def _optional_date(value: date | None) -> str:
    return "" if value is None else value.isoformat()


def _optional_decimal(value: Decimal | None) -> str:
    return "" if value is None else format(value, "f")


def _optional_text(value: str | None) -> str:
    return "" if value is None else value


@dataclass(frozen=True, slots=True)
class InstrumentTerms:
    """One effective-dated set of authoritative instrument terms."""

    instrument_id: str
    market: str
    symbol: str
    segment: str
    effective_from: date
    effective_to: date | None
    lot_size: Decimal | int | str
    tick_size: Decimal | int | str
    underlying: str | None = None
    expiry: date | None = None
    strike: Decimal | int | str | None = None
    option_type: str | None = None
    expiry_kind: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument_id", _text("instrument_id", self.instrument_id))
        object.__setattr__(self, "market", _text("market", self.market).upper())
        object.__setattr__(self, "symbol", _text("symbol", self.symbol).upper())
        object.__setattr__(self, "segment", _text("segment", self.segment).lower())
        if not isinstance(self.effective_from, date):
            raise InstrumentMasterError("effective_from must be a date")
        if self.effective_to is not None:
            if not isinstance(self.effective_to, date):
                raise InstrumentMasterError("effective_to must be a date or None")
            if self.effective_to < self.effective_from:
                raise InstrumentMasterError("effective_to cannot precede effective_from")
        object.__setattr__(self, "lot_size", _decimal("lot_size", self.lot_size))
        object.__setattr__(self, "tick_size", _decimal("tick_size", self.tick_size))

        option_fields = (self.underlying, self.expiry, self.strike, self.option_type, self.expiry_kind)
        if self.segment == "options":
            if any(value is None for value in option_fields):
                raise InstrumentMasterError(
                    "options terms require underlying, expiry, strike, option_type, and expiry_kind"
                )
            underlying = _text("underlying", self.underlying).upper()  # type: ignore[arg-type]
            if not isinstance(self.expiry, date):
                raise InstrumentMasterError("expiry must be a date")
            strike = _decimal("strike", self.strike)  # type: ignore[arg-type]
            option_type = _text("option_type", self.option_type).upper()  # type: ignore[arg-type]
            if option_type not in {"CE", "PE"}:
                raise InstrumentMasterError("option_type must be CE or PE")
            expiry_kind = _text("expiry_kind", self.expiry_kind).lower()  # type: ignore[arg-type]
            if expiry_kind not in {"weekly", "monthly"}:
                raise InstrumentMasterError("expiry_kind must be weekly or monthly")
            if not _date_in_range(self.expiry, self.effective_from, self.effective_to):
                raise InstrumentMasterError("option expiry must fall inside the effective range")
            object.__setattr__(self, "underlying", underlying)
            object.__setattr__(self, "strike", strike)
            object.__setattr__(self, "option_type", option_type)
            object.__setattr__(self, "expiry_kind", expiry_kind)
        elif any(value is not None for value in option_fields):
            raise InstrumentMasterError("non-option terms cannot carry option-only metadata")

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-instrument-terms/v1",
            (
                ("instrument_id", self.instrument_id),
                ("market", self.market),
                ("symbol", self.symbol),
                ("segment", self.segment),
                ("effective_from", self.effective_from.isoformat()),
                ("effective_to", _optional_date(self.effective_to)),
                ("lot_size", format(self.lot_size, "f")),
                ("tick_size", format(self.tick_size, "f")),
                ("underlying", _optional_text(self.underlying)),
                ("expiry", _optional_date(self.expiry)),
                ("strike", _optional_decimal(self.strike if isinstance(self.strike, Decimal) else None)),
                ("option_type", _optional_text(self.option_type)),
                ("expiry_kind", _optional_text(self.expiry_kind)),
            ),
        )


class InstrumentMaster:
    """Deterministic effective-dated instrument metadata authority."""

    def __init__(self, terms: tuple[InstrumentTerms, ...] = ()) -> None:
        self._terms: list[InstrumentTerms] = []
        for item in terms:
            self.register(item)

    def register(self, terms: InstrumentTerms) -> InstrumentTerms:
        if not isinstance(terms, InstrumentTerms):
            raise InstrumentMasterError("terms must be InstrumentTerms")
        for existing in self._terms:
            if existing == terms:
                return existing
            same_authority = existing.instrument_id == terms.instrument_id or (
                existing.market == terms.market and existing.symbol == terms.symbol
            )
            if same_authority and _ranges_overlap(
                existing.effective_from,
                existing.effective_to,
                terms.effective_from,
                terms.effective_to,
            ):
                raise InstrumentMasterError(
                    "effective ranges overlap for the same instrument authority"
                )
        self._terms.append(terms)
        return terms

    def resolve(self, symbol: str, as_of: date) -> InstrumentTerms:
        normalized_symbol = _text("symbol", symbol).upper()
        if not isinstance(as_of, date):
            raise InstrumentMasterError("as_of must be a date")
        matches = [
            terms
            for terms in self._terms
            if terms.symbol == normalized_symbol
            and _date_in_range(as_of, terms.effective_from, terms.effective_to)
        ]
        if not matches:
            raise InstrumentMasterError(
                f"no instrument terms for {normalized_symbol} as of {as_of.isoformat()}"
            )
        if len(matches) != 1:
            raise InstrumentMasterError(
                f"ambiguous instrument terms for {normalized_symbol} as of {as_of.isoformat()}"
            )
        return matches[0]

    @property
    def records(self) -> tuple[InstrumentTerms, ...]:
        return tuple(
            sorted(
                self._terms,
                key=lambda item: (
                    item.instrument_id,
                    item.market,
                    item.symbol,
                    item.effective_from,
                    item.effective_to or date.max,
                ),
            )
        )

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-instrument-master/v1",
            (("terms", tuple(item.fingerprint for item in self.records)),),
        )


__all__ = ["InstrumentMasterError", "InstrumentTerms", "InstrumentMaster"]
