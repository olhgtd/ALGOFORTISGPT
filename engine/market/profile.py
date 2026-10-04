"""Immutable market-profile and regular-session boundaries for Slice 2."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _require_aware(timestamp: datetime) -> None:
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")


@dataclass(frozen=True)
class MarketProfile:
    """Value-like exchange settings consumed by market-aware engine boundaries."""

    market_id: str
    timezone_name: str
    regular_session_open: time
    regular_session_close: time
    calendar_id: str
    tick_size_policy_ref: str | None
    lot_size_policy_ref: str | None
    contract_multiplier_ref: str | None
    cost_profile_ref: str | None
    asset_metadata_ref: str | None = None
    expiry_metadata_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.market_id:
            raise ValueError("market_id must not be empty")
        if not self.calendar_id:
            raise ValueError("calendar_id must not be empty")
        try:
            ZoneInfo(self.timezone_name)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"unknown timezone: {self.timezone_name!r}") from error
        if self.regular_session_open >= self.regular_session_close:
            raise ValueError("regular session open must be before regular session close")

    @property
    def timezone(self) -> ZoneInfo:
        """Return this profile's exchange timezone."""
        return ZoneInfo(self.timezone_name)


@dataclass(frozen=True)
class WeekendCalendar:
    """Deterministic weekday calendar with injected full-day closures."""

    closed_dates: frozenset[date] = field(default_factory=frozenset)

    def is_tradable_date(self, session_date: date) -> bool:
        """Return whether the exchange-local date is open under this baseline."""
        return session_date.weekday() < 5 and session_date not in self.closed_dates


CALENDAR_CLOSURE_SNAPSHOT_SCHEMA_VERSION = "algofortis-calendar-closure-snapshot/v1"


@dataclass(frozen=True)
class CalendarClosureSnapshot:
    """Immutable, canonically fingerprinted exchange calendar closure snapshot (ADR §122 OD-X)."""

    calendar_id: str
    exchange: str = "NSE"
    timezone: str = "Asia/Kolkata"
    coverage_start: date = date(2026, 1, 1)
    coverage_end: date = date(2026, 12, 31)
    closed_dates: tuple[date, ...] = ()
    schema_version: str = CALENDAR_CLOSURE_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != "algofortis-calendar-closure-snapshot/v1":
            raise ValueError(f"unsupported schema_version: {self.schema_version}")
        if not self.calendar_id.strip():
            raise ValueError("calendar_id must not be empty")
        if self.exchange != "NSE":
            raise ValueError(f"exchange must be 'NSE', got {self.exchange!r}")
        if self.timezone != "Asia/Kolkata":
            raise ValueError(f"timezone must be 'Asia/Kolkata', got {self.timezone!r}")
        if self.coverage_start > self.coverage_end:
            raise ValueError(f"coverage_start ({self.coverage_start}) must be <= coverage_end ({self.coverage_end})")
        sorted_dates = tuple(sorted(set(self.closed_dates)))
        for d in sorted_dates:
            if not isinstance(d, date):
                raise TypeError(f"closed_dates item must be date, got {type(d)}")
        object.__setattr__(self, "closed_dates", sorted_dates)

    @property
    def calendar_fingerprint(self) -> str:
        from engine.reproducibility.codec import CanonicalCodec
        return CanonicalCodec.fingerprint(
            "algofortis-calendar-closure-snapshot/v1",
            (
                ("calendar_id", self.calendar_id),
                ("exchange", self.exchange),
                ("timezone", self.timezone),
                ("coverage_start", self.coverage_start.isoformat()),
                ("coverage_end", self.coverage_end.isoformat()),
                ("closed_dates", tuple(d.isoformat() for d in self.closed_dates)),
            ),
        )

    def is_covered(self, session_date: date) -> bool:
        return self.coverage_start <= session_date <= self.coverage_end

    def to_calendar(self) -> WeekendCalendar:
        return WeekendCalendar(closed_dates=frozenset(self.closed_dates))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "calendar_id": self.calendar_id,
            "exchange": self.exchange,
            "timezone": self.timezone,
            "coverage_start": self.coverage_start.isoformat(),
            "coverage_end": self.coverage_end.isoformat(),
            "closed_dates": [d.isoformat() for d in self.closed_dates],
            "calendar_fingerprint": self.calendar_fingerprint,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> CalendarClosureSnapshot:
        schema = str(data.get("schema_version", ""))
        if schema != "algofortis-calendar-closure-snapshot/v1":
            raise ValueError(f"unsupported calendar snapshot schema_version: {schema}")
        cov_start_val = data["coverage_start"]
        cov_end_val = data["coverage_end"]
        cov_start = date.fromisoformat(str(cov_start_val)) if isinstance(cov_start_val, str) else cov_start_val
        cov_end = date.fromisoformat(str(cov_end_val)) if isinstance(cov_end_val, str) else cov_end_val
        raw_closed = data.get("closed_dates", ())
        if not isinstance(raw_closed, (list, tuple, set, frozenset)):
            raise ValueError("closed_dates must be a sequence of date strings or dates")
        closed = tuple(date.fromisoformat(str(d)) if isinstance(d, str) else d for d in raw_closed)
        snap = cls(
            calendar_id=str(data["calendar_id"]),
            exchange=str(data.get("exchange", "NSE")),
            timezone=str(data.get("timezone", "Asia/Kolkata")),
            coverage_start=cov_start,  # type: ignore[arg-type]
            coverage_end=cov_end,      # type: ignore[arg-type]
            closed_dates=closed,       # type: ignore[arg-type]
            schema_version=schema,
        )
        if "calendar_fingerprint" in data and str(data["calendar_fingerprint"]) != snap.calendar_fingerprint:
            raise ValueError("calendar_fingerprint mismatch in serialized snapshot")
        return snap


@dataclass(frozen=True)
class MarketSessionBoundary:
    """Interpret aware timestamps using one profile and one calendar boundary."""

    profile: MarketProfile
    calendar: WeekendCalendar = field(default_factory=WeekendCalendar)
    calendar_snapshot: CalendarClosureSnapshot | None = None

    def __post_init__(self) -> None:
        if self.calendar_snapshot is not None and self.calendar == WeekendCalendar():
            object.__setattr__(self, "calendar", self.calendar_snapshot.to_calendar())

    def exchange_timestamp(self, timestamp: datetime) -> datetime:
        """Convert an aware timestamp to the profile's exchange timezone."""
        _require_aware(timestamp)
        return timestamp.astimezone(self.profile.timezone)

    def session_date(self, timestamp: datetime) -> date:
        """Return the exchange-local date associated with an aware timestamp."""
        return self.exchange_timestamp(timestamp).date()

    def is_regular_session(self, timestamp: datetime) -> bool:
        """Return whether an aware timestamp is within an open regular session.

        Both configured session endpoints are included. Exceptional sessions and
        intraday holiday schedules are intentionally outside Slice 2 scope.
        """
        exchange_timestamp = self.exchange_timestamp(timestamp)
        return (
            self.calendar.is_tradable_date(exchange_timestamp.date())
            and self.profile.regular_session_open
            <= exchange_timestamp.timetz().replace(tzinfo=None)
            <= self.profile.regular_session_close
        )



def india_market_profile() -> MarketProfile:
    """Return the owner-approved India regular-session baseline."""
    return MarketProfile(
        market_id="india-equities",
        timezone_name="Asia/Kolkata",
        regular_session_open=time(9, 15),
        regular_session_close=time(15, 30),
        calendar_id="weekend-and-injected-closures",
        tick_size_policy_ref="india-default",
        lot_size_policy_ref="india-default",
        contract_multiplier_ref="india-default",
        cost_profile_ref="india-default",
    )


def us_equities_market_profile() -> MarketProfile:
    """Return the owner-approved representative US regular-session baseline."""
    return MarketProfile(
        market_id="us-equities",
        timezone_name="America/New_York",
        regular_session_open=time(9, 30),
        regular_session_close=time(16, 0),
        calendar_id="weekend-and-injected-closures",
        tick_size_policy_ref="us-default",
        lot_size_policy_ref="us-default",
        contract_multiplier_ref="us-default",
        cost_profile_ref="us-default",
    )
