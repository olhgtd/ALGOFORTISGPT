"""Effective-dated exchange calendar and session authority for Data V2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from engine.reproducibility.codec import CanonicalCodec


class CalendarError(ValueError):
    """Raised when market-calendar evidence is invalid or ambiguous."""


def _text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CalendarError(f"{name} must be non-empty")
    return value.strip()


def _ranges_overlap(
    left_start: date,
    left_end: date | None,
    right_start: date,
    right_end: date | None,
) -> bool:
    return (left_end is None or right_start <= left_end) and (
        right_end is None or left_start <= right_end
    )


def _date_in_range(day: date, start: date, end: date | None) -> bool:
    return day >= start and (end is None or day <= end)


@dataclass(frozen=True, slots=True)
class TradingCalendarRule:
    """One effective-dated market-session calendar rule."""

    market: str
    timezone_name: str
    effective_from: date
    effective_to: date | None
    weekdays: tuple[int, ...]
    session_open: time
    session_close: time
    holidays: tuple[date, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "market", _text("market", self.market).upper())
        timezone_name = _text("timezone_name", self.timezone_name)
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise CalendarError(f"unknown timezone_name: {timezone_name}") from exc
        object.__setattr__(self, "timezone_name", timezone_name)

        if not isinstance(self.effective_from, date):
            raise CalendarError("effective_from must be a date")
        if self.effective_to is not None:
            if not isinstance(self.effective_to, date):
                raise CalendarError("effective_to must be a date or None")
            if self.effective_to < self.effective_from:
                raise CalendarError("effective_to cannot precede effective_from")

        if not isinstance(self.session_open, time) or not isinstance(self.session_close, time):
            raise CalendarError("session_open/session_close must be time values")
        if self.session_open.tzinfo is not None or self.session_close.tzinfo is not None:
            raise CalendarError("session times must be naive local wall times")
        if self.session_close <= self.session_open:
            raise CalendarError("session_close must be after session_open")

        weekdays = tuple(self.weekdays)
        if not weekdays or any(isinstance(day, bool) or not isinstance(day, int) or day < 0 or day > 6 for day in weekdays):
            raise CalendarError("weekdays must contain integers 0..6")
        if len(weekdays) != len(set(weekdays)):
            raise CalendarError("weekdays must be unique")
        object.__setattr__(self, "weekdays", tuple(sorted(weekdays)))

        holidays = tuple(self.holidays)
        if any(not isinstance(day, date) for day in holidays):
            raise CalendarError("holidays must contain date values")
        if len(holidays) != len(set(holidays)):
            raise CalendarError("holidays must be unique")
        object.__setattr__(self, "holidays", tuple(sorted(holidays)))

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-calendar-rule/v1",
            (
                ("market", self.market),
                ("timezone_name", self.timezone_name),
                ("effective_from", self.effective_from.isoformat()),
                ("effective_to", "" if self.effective_to is None else self.effective_to.isoformat()),
                ("weekdays", tuple(str(day) for day in self.weekdays)),
                ("session_open", self.session_open.isoformat()),
                ("session_close", self.session_close.isoformat()),
                ("holidays", tuple(day.isoformat() for day in self.holidays)),
            ),
        )


class ExchangeCalendar:
    """Deterministic as-of market calendar authority."""

    def __init__(self, rules: tuple[TradingCalendarRule, ...] = ()) -> None:
        self._rules: list[TradingCalendarRule] = []
        for rule in rules:
            self.register(rule)

    def register(self, rule: TradingCalendarRule) -> TradingCalendarRule:
        if not isinstance(rule, TradingCalendarRule):
            raise CalendarError("rule must be TradingCalendarRule")
        for existing in self._rules:
            if existing == rule:
                return existing
            if existing.market == rule.market and _ranges_overlap(
                existing.effective_from,
                existing.effective_to,
                rule.effective_from,
                rule.effective_to,
            ):
                raise CalendarError("calendar effective ranges overlap for the same market")
        self._rules.append(rule)
        return rule

    def _resolve_rule(self, market: str, as_of: date) -> TradingCalendarRule:
        normalized_market = _text("market", market).upper()
        if not isinstance(as_of, date):
            raise CalendarError("as_of must be a date")
        matches = [
            rule
            for rule in self._rules
            if rule.market == normalized_market
            and _date_in_range(as_of, rule.effective_from, rule.effective_to)
        ]
        if not matches:
            raise CalendarError(
                f"no calendar rule for {normalized_market} as of {as_of.isoformat()}"
            )
        if len(matches) != 1:
            raise CalendarError(
                f"ambiguous calendar rule for {normalized_market} as of {as_of.isoformat()}"
            )
        return matches[0]

    def is_trading_day(self, market: str, day: date) -> bool:
        rule = self._resolve_rule(market, day)
        return day.weekday() in rule.weekdays and day not in rule.holidays

    def session_bounds(self, market: str, day: date) -> tuple[datetime, datetime]:
        rule = self._resolve_rule(market, day)
        if day.weekday() not in rule.weekdays or day in rule.holidays:
            raise CalendarError(f"{market} is not open on {day.isoformat()}")
        zone = ZoneInfo(rule.timezone_name)
        return (
            datetime.combine(day, rule.session_open, tzinfo=zone),
            datetime.combine(day, rule.session_close, tzinfo=zone),
        )

    @property
    def rules(self) -> tuple[TradingCalendarRule, ...]:
        return tuple(
            sorted(
                self._rules,
                key=lambda item: (
                    item.market,
                    item.effective_from,
                    item.effective_to or date.max,
                ),
            )
        )

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-exchange-calendar/v1",
            (("rules", tuple(rule.fingerprint for rule in self.rules)),),
        )


__all__ = ["CalendarError", "TradingCalendarRule", "ExchangeCalendar"]
