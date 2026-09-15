"""§129.17 / §122.5 OD-E - THE authoritative market-calendar/session abstraction.

This module is SentinelX's ONE reusable market-calendar and session-state
authority.  It is isolated from acquisition/importer modules (no pandas, no
IO except the explicit offline loader) and is reusable by historical
ingestion, gap analysis, replay/backtest, and future validation layers.

Frozen semantics implemented here:

- §122.5 OD-E: session identity is the exchange-local trading date in the
  market timezone; weekends and exchange holidays are never missing sessions.
- §129.17: weekends/holidays are NEVER missing-data errors.  For derivatives,
  contract not-yet-listed, contract expired, no-trading, and source-unavailable
  states are distinguished ONLY where authoritative lifecycle/closure evidence
  exists.  Actual missing scheduled-session evidence is reported explicitly.
- FAIL CLOSED: when authoritative calendar evidence does not cover a date,
  the classification is CALENDAR_UNAVAILABLE - never a guessed holiday or a
  guessed trading day.  Unknown/unclassifiable cases are UNKNOWN.
- No network access exists anywhere in this module.  Calendar evidence is
  deterministic OFFLINE versioned data loaded from the local data root.
- Provenance/version identity: every dataset carries an explicit schema
  version, dataset version, provenance block, and a CanonicalCodec fingerprint
  so future calendar revisions are auditable and reproducible.

Authority relationships (no competing authorities):
- ``engine.market.profile.MarketProfile`` remains the session-time/profile
  primitive (Slice 2).
- ``engine.market.profile.CalendarClosureSnapshot`` remains the frozen §122
  closure-snapshot primitive; this authority interoperates with it via
  ``MarketCalendarDataset.to_closure_snapshot()``.
- This module is the ONLY date-level session-classification authority.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import Enum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from engine.reproducibility.codec import CanonicalCodec

CALENDAR_DATA_SCHEMA_VERSION = "sentinelx-market-calendar/v1"

DEFAULT_NSE_CALENDAR_ID = "nse-equity"
NSE_EXCHANGE_ID = "NSE"
INDIA_TIMEZONE_NAME = "Asia/Kolkata"

WEEKEND_CALENDAR_BASELINE_REF = "engine.market.profile.WeekendCalendar"

CLOSED_SESSION_CATEGORIES = frozenset({"HOLIDAY", "NO_TRADING", "SOURCE_UNAVAILABLE"})

_NSE_DATE_PATTERN = re.compile(r"^(\d{1,2})-([A-Za-z]{3})-(\d{4})$")
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_SESSION_TIME_PATTERN = re.compile(r"^(\d{2}):(\d{2})$")


class CalendarAuthorityError(ValueError):
    """Fail-closed base error for invalid or unavailable calendar evidence."""


class CalendarDataError(CalendarAuthorityError):
    """Raised when supplied calendar/lifecycle evidence is invalid or contradictory."""


class CalendarDataUnavailable(CalendarAuthorityError):
    """Raised when requested offline calendar evidence does not exist locally."""


class CalendarDataCorrupt(CalendarDataError):
    """Raised when offline calendar evidence fails schema/fingerprint verification."""


def parse_calendar_date(text: str, *, field_name: str = "date") -> date:
    """Parse an approved explicit calendar date format only; never guess.

    Approved formats: ISO ``YYYY-MM-DD`` and NSE ``DD-MMM-YYYY``
    (e.g. ``25-Jul-2024``).  Anything else raises CalendarDataError.
    """
    if not isinstance(text, str) or not text.strip():
        raise CalendarDataError(f"{field_name} must be a non-empty date string")
    value = text.strip()
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    match = _NSE_DATE_PATTERN.match(value)
    if match:
        day, month_text, year = match.groups()
        month = _MONTHS.get(month_text.casefold())
        if month is not None:
            try:
                return date(int(year), month, int(day))
            except ValueError as error:
                raise CalendarDataError(f"{field_name} is not a valid date: {text!r}") from error
    raise CalendarDataError(
        f"{field_name} uses unsupported format {text!r}; "
        "approved formats are YYYY-MM-DD and DD-MMM-YYYY"
    )


def parse_session_time(text: str, *, field_name: str = "session time") -> time:
    """Parse an explicit HH:MM session boundary only."""
    if not isinstance(text, str):
        raise CalendarDataError(f"{field_name} must be a HH:MM string")
    match = _SESSION_TIME_PATTERN.match(text.strip())
    if not match:
        raise CalendarDataError(f"{field_name} must use 24-hour HH:MM format: {text!r}")
    hour, minute = int(match.group(1)), int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise CalendarDataError(f"{field_name} is not a valid clock time: {text!r}")
    return time(hour, minute)


class SessionClassification(str, Enum):
    """Explicit session-evidence states for one exchange-local trading date."""

    SCHEDULED_SESSION = "scheduled_session"
    NON_SESSION_WEEKEND = "non_session_weekend"
    EXCHANGE_HOLIDAY = "exchange_holiday"
    NO_TRADING_CLOSED = "no_trading_closed"
    SOURCE_UNAVAILABLE = "source_unavailable"
    CONTRACT_NOT_LISTED = "contract_not_listed"
    CONTRACT_EXPIRED = "contract_expired"
    MISSING_SESSION_EVIDENCE = "missing_session_evidence"
    CALENDAR_UNAVAILABLE = "calendar_unavailable"
    UNKNOWN = "unknown"


#: Classifications that confidently explain an absence of canonical rows and
#: must NEVER be reported as missing-data errors (§129.17 frozen rule).
KNOWN_CLOSED_CLASSIFICATIONS = frozenset(
    {
        SessionClassification.NON_SESSION_WEEKEND,
        SessionClassification.EXCHANGE_HOLIDAY,
        SessionClassification.NO_TRADING_CLOSED,
        SessionClassification.SOURCE_UNAVAILABLE,
        SessionClassification.CONTRACT_NOT_LISTED,
        SessionClassification.CONTRACT_EXPIRED,
    }
)

#: Classifications requiring human review before any completeness claim.
REVIEW_REQUIRED_CLASSIFICATIONS = frozenset(
    {
        SessionClassification.CALENDAR_UNAVAILABLE,
        SessionClassification.UNKNOWN,
    }
)


@dataclass(frozen=True)
class ClosedSession:
    """One authoritatively evidenced closed session."""

    session_date: date
    category: str
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.category not in CLOSED_SESSION_CATEGORIES:
            raise CalendarDataError(
                f"closed-session category must be one of {sorted(CLOSED_SESSION_CATEGORIES)}, "
                f"got {self.category!r}"
            )


@dataclass(frozen=True)
class ContractLifecycleEvidence:
    """Authoritative contract-lifecycle evidence for one tradable contract.

    Every participating field must come from verified evidence supplied by the
    caller (e.g. structured expiry identity or a verified contract master).
    When evidence for a boundary does not exist, leave the field as ``None``:
    the authority will simply not classify that boundary rather than guess.
    """

    instrument_key: str
    listed_from: date | None = None
    expiry: date | None = None
    provenance_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_key, str) or not self.instrument_key.strip():
            raise CalendarDataError("instrument_key must be a non-empty string")
        if self.listed_from is not None and self.expiry is not None and self.listed_from > self.expiry:
            raise CalendarDataError(
                f"contradictory lifecycle evidence for {self.instrument_key!r}: "
                f"listed_from {self.listed_from} is after expiry {self.expiry}"
            )

    @classmethod
    def from_identity_evidence(
        cls,
        *,
        instrument_key: str,
        expiry_text: str | None,
        provenance_ref: str | None = None,
    ) -> "ContractLifecycleEvidence":
        """Build evidence from structured identity expiry text (§129.15).

        Only the expiry boundary is claimed; listing evidence stays absent
        unless separately supplied, because absence of early rows is NOT
        proof of a pre-listing period.
        """
        expiry = parse_calendar_date(expiry_text, field_name="expiry") if expiry_text else None
        return cls(instrument_key=instrument_key, expiry=expiry, provenance_ref=provenance_ref)


@dataclass(frozen=True)
class MarketCalendarDataset:
    """Immutable, fingerprinted, versioned OFFLINE market-calendar evidence."""

    calendar_id: str
    exchange: str
    timezone_name: str
    coverage_start: date
    coverage_end: date
    dataset_version: str
    closed_sessions: tuple[ClosedSession, ...] = ()
    special_sessions: tuple[date, ...] = ()
    session_open: time | None = None
    session_close: time | None = None
    provenance: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.calendar_id, str) or not self.calendar_id.strip():
            raise CalendarDataError("calendar_id must be a non-empty string")
        if not isinstance(self.exchange, str) or not self.exchange.strip():
            raise CalendarDataError("exchange must be a non-empty string")
        if not isinstance(self.dataset_version, str) or not self.dataset_version.strip():
            raise CalendarDataError("dataset_version must be a non-empty string")
        try:
            ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, TypeError) as error:
            raise CalendarDataError(f"unknown calendar timezone: {self.timezone_name!r}") from error
        if self.coverage_start > self.coverage_end:
            raise CalendarDataError(
                f"coverage_start ({self.coverage_start}) is after coverage_end ({self.coverage_end})"
            )
        object.__setattr__(
            self,
            "closed_sessions",
            tuple(sorted(self.closed_sessions, key=lambda entry: entry.session_date)),
        )
        object.__setattr__(
            self,
            "special_sessions",
            tuple(sorted(set(self.special_sessions))),
        )
        object.__setattr__(
            self,
            "provenance",
            dict(sorted((str(k), str(v)) for k, v in dict(self.provenance).items())),
        )
        seen: set[date] = set()
        for entry in self.closed_sessions:
            if entry.session_date.weekday() >= 5:
                raise CalendarDataError(
                    f"closed-session evidence on weekend {entry.session_date} is contradictory "
                    "(weekends are already non-session under the frozen baseline)"
                )
            if entry.session_date in seen:
                raise CalendarDataError(f"duplicate calendar evidence for {entry.session_date}")
            seen.add(entry.session_date)
        for special in self.special_sessions:
            if special.weekday() < 5:
                raise CalendarDataError(
                    f"special-session override on weekday {special} is redundant; "
                    "weekday scheduling requires no override"
                )
            if special in seen:
                raise CalendarDataError(
                    f"contradictory calendar evidence for {special}: both closed and special"
                )
            seen.add(special)
        if self.session_open is not None and self.session_close is not None:
            if self.session_open >= self.session_close:
                raise CalendarDataError("session_open must be before session_close")

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    @property
    def calendar_fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            CALENDAR_DATA_SCHEMA_VERSION,
            (
                ("calendar_id", self.calendar_id),
                ("exchange", self.exchange),
                ("timezone", self.timezone_name),
                ("dataset_version", self.dataset_version),
                ("coverage_start", self.coverage_start.isoformat()),
                ("coverage_end", self.coverage_end.isoformat()),
                (
                    "closed_sessions",
                    tuple(
                        (e.session_date.isoformat(), e.category, e.reason or "")
                        for e in self.closed_sessions
                    ),
                ),
                ("special_sessions", tuple(d.isoformat() for d in self.special_sessions)),
                (
                    "session_open",
                    self.session_open.strftime("%H:%M") if self.session_open else "",
                ),
                (
                    "session_close",
                    self.session_close.strftime("%H:%M") if self.session_close else "",
                ),
                ("provenance", tuple(self.provenance.items())),
            ),
        )

    def covers(self, session_date: date) -> bool:
        return self.coverage_start <= session_date <= self.coverage_end

    def to_closure_snapshot(self):  # -> engine.market.profile.CalendarClosureSnapshot
        """Interoperate with the frozen §122 closure-snapshot primitive."""
        from engine.market.profile import CalendarClosureSnapshot

        return CalendarClosureSnapshot(
            calendar_id=self.calendar_id,
            exchange=self.exchange,
            timezone=self.timezone_name,
            coverage_start=self.coverage_start,
            coverage_end=self.coverage_end,
            closed_dates=tuple(e.session_date for e in self.closed_sessions),
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": CALENDAR_DATA_SCHEMA_VERSION,
            "calendar_id": self.calendar_id,
            "exchange": self.exchange,
            "timezone": self.timezone_name,
            "dataset_version": self.dataset_version,
            "coverage_start": self.coverage_start.isoformat(),
            "coverage_end": self.coverage_end.isoformat(),
            "closed_sessions": [
                {
                    "date": e.session_date.isoformat(),
                    "category": e.category,
                    "reason": e.reason or "",
                }
                for e in self.closed_sessions
            ],
            "special_sessions": [d.isoformat() for d in self.special_sessions],
            "session_open": self.session_open.strftime("%H:%M") if self.session_open else None,
            "session_close": self.session_close.strftime("%H:%M") if self.session_close else None,
            "provenance": dict(self.provenance),
            "calendar_fingerprint": self.calendar_fingerprint,
        }
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MarketCalendarDataset":
        if not isinstance(data, Mapping):
            raise CalendarDataError("calendar dataset payload must be a JSON object")
        schema = data.get("schema_version")
        if schema != CALENDAR_DATA_SCHEMA_VERSION:
            raise CalendarDataCorrupt(
                f"unsupported calendar schema_version: {schema!r}; "
                f"expected {CALENDAR_DATA_SCHEMA_VERSION!r}"
            )
        required = (
            "calendar_id", "exchange", "timezone", "dataset_version",
            "coverage_start", "coverage_end", "calendar_fingerprint",
        )
        missing = [name for name in required if name not in data]
        if missing:
            raise CalendarDataCorrupt(f"calendar dataset missing required fields: {missing}")

        closed_entries = []
        raw_closed = data.get("closed_sessions", [])
        if not isinstance(raw_closed, (list, tuple)):
            raise CalendarDataCorrupt("closed_sessions must be a list")
        for entry in raw_closed:
            if not isinstance(entry, Mapping) or "date" not in entry or "category" not in entry:
                raise CalendarDataCorrupt(f"invalid closed_sessions entry: {entry!r}")
            reason = entry.get("reason")
            closed_entries.append(
                ClosedSession(
                    session_date=parse_calendar_date(str(entry["date"]), field_name="closed_sessions.date"),
                    category=str(entry["category"]),
                    reason=str(reason) if reason else None,
                )
            )
        raw_special = data.get("special_sessions", [])
        if not isinstance(raw_special, (list, tuple)):
            raise CalendarDataCorrupt("special_sessions must be a list")
        special_dates = tuple(
            parse_calendar_date(str(value), field_name="special_sessions.date")
            for value in raw_special
        )
        session_open_raw = data.get("session_open")
        session_close_raw = data.get("session_close")

        provenance_raw = data.get("provenance", {})
        if not isinstance(provenance_raw, Mapping):
            raise CalendarDataCorrupt("provenance must be a JSON object")

        dataset = cls(
            calendar_id=str(data["calendar_id"]),
            exchange=str(data["exchange"]),
            timezone_name=str(data["timezone"]),
            dataset_version=str(data["dataset_version"]),
            coverage_start=parse_calendar_date(str(data["coverage_start"]), field_name="coverage_start"),
            coverage_end=parse_calendar_date(str(data["coverage_end"]), field_name="coverage_end"),
            closed_sessions=tuple(closed_entries),
            special_sessions=special_dates,
            session_open=(
                parse_session_time(str(session_open_raw), field_name="session_open")
                if session_open_raw else None
            ),
            session_close=(
                parse_session_time(str(session_close_raw), field_name="session_close")
                if session_close_raw else None
            ),
            provenance={str(k): str(v) for k, v in provenance_raw.items()},
        )
        recorded_fingerprint = str(data["calendar_fingerprint"])
        if recorded_fingerprint != dataset.calendar_fingerprint:
            raise CalendarDataCorrupt(
                "calendar_fingerprint mismatch: recorded evidence does not match content"
            )
        return dataset


@dataclass(frozen=True)
class SessionEvaluation:
    """Deterministic evaluation result for one exchange-local trading date."""

    session_date: date
    intrinsic_state: SessionClassification
    classification: SessionClassification
    detail: str = ""


class MarketCalendarAuthority:
    """The single fail-closed market-calendar/session classification authority.

    ``dataset=None`` means no authoritative calendar evidence is loaded: every
    non-weekend date evaluates to CALENDAR_UNAVAILABLE (fail closed) instead of
    a guessed holiday or a guessed trading day.
    """

    def __init__(self, dataset: MarketCalendarDataset | None) -> None:
        if dataset is not None and not isinstance(dataset, MarketCalendarDataset):
            raise TypeError("dataset must be a MarketCalendarDataset or None")
        self._dataset = dataset
        if dataset is not None:
            self._closed_by_date = {e.session_date: e for e in dataset.closed_sessions}
            self._special_dates = frozenset(dataset.special_sessions)
        else:
            self._closed_by_date = {}
            self._special_dates = frozenset()

    # ------------------------------------------------------------------
    # Offline loading (deterministic, versioned, no network anywhere)
    # ------------------------------------------------------------------

    @staticmethod
    def offline_calendar_path(calendar_id: str, *, data_root: Path | None = None) -> Path:
        """Resolve the deterministic offline path for one calendar dataset."""
        from engine.data.feeds.data_root import get_data_root
        from engine.data.feeds.path_safety import require_safe_component

        safe_id = require_safe_component(calendar_id, "calendar_id")
        root = data_root if data_root is not None else get_data_root()
        return root / "calendars" / f"{safe_id}.json"

    @classmethod
    def load_offline(cls, calendar_id: str, *, data_root: Path | None = None) -> "MarketCalendarAuthority":
        """Load and verify one offline calendar dataset; FAIL CLOSED when unusable."""
        path = cls.offline_calendar_path(calendar_id, data_root=data_root)
        if not path.is_file():
            raise CalendarDataUnavailable(
                f"authoritative calendar evidence not found locally: {path} "
                "(offline manual placement only; never fetched at runtime)"
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise CalendarDataCorrupt(f"calendar file is not valid JSON: {path}") from error
        try:
            dataset = MarketCalendarDataset.from_dict(payload)
        except CalendarDataCorrupt as error:
            raise CalendarDataCorrupt(f"calendar file rejected for {calendar_id!r}: {error}") from error
        if dataset.calendar_id != calendar_id:
            raise CalendarDataCorrupt(
                f"calendar_id mismatch: file declares {dataset.calendar_id!r}, "
                f"requested {calendar_id!r}"
            )
        return cls(dataset)

    @classmethod
    def try_load_offline(cls, calendar_id: str, *, data_root: Path | None = None) -> "MarketCalendarAuthority | None":
        """Load one offline dataset, returning None when it simply does not exist.

        Corruption or schema failure still raises (fail closed); only genuine
        local absence yields None, which callers must treat as
        CALENDAR_UNAVAILABLE for every non-weekend date.
        """
        path = cls.offline_calendar_path(calendar_id, data_root=data_root)
        if not path.is_file():
            return None
        return cls.load_offline(calendar_id, data_root=data_root)

    # ------------------------------------------------------------------
    # Classification API
    # ------------------------------------------------------------------

    @property
    def dataset(self) -> MarketCalendarDataset | None:
        return self._dataset

    @property
    def timezone_name(self) -> str:
        return self._dataset.timezone_name if self._dataset else INDIA_TIMEZONE_NAME

    def exchange_date(self, timestamp: datetime) -> date:
        """Exchange-local calendar date of an AWARE timestamp (fail closed on naive)."""
        if not isinstance(timestamp, datetime):
            raise TypeError("timestamp must be a datetime")
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise CalendarAuthorityError(
                "timestamp must be timezone-aware; naive timestamps cannot establish "
                "an exchange-local session date"
            )
        return timestamp.astimezone(ZoneInfo(self.timezone_name)).date()

    def classify_session(
        self,
        session_date: date,
        lifecycle: ContractLifecycleEvidence | None = None,
    ) -> SessionClassification:
        """Intrinsic calendar state of one exchange-local date.

        Weekends are structurally NON_SESSION_WEEKEND (frozen baseline,
        ``engine.market.profile.WeekendCalendar``).  Everything else requires
        authoritative coverage: uncovered dates are CALENDAR_UNAVAILABLE.
        Lifecycle boundaries refine only otherwise-scheduled sessions and
        only where explicit evidence exists.
        """
        if not isinstance(session_date, date):
            raise TypeError("session_date must be a datetime.date")
        if session_date.weekday() >= 5:
            if session_date in self._special_dates:
                pass  # evidenced special open session overrides the weekend baseline
            else:
                return SessionClassification.NON_SESSION_WEEKEND
        if self._dataset is None or not self._dataset.covers(session_date):
            return SessionClassification.CALENDAR_UNAVAILABLE
        closed = self._closed_by_date.get(session_date)
        if closed is not None:
            if closed.category == "HOLIDAY":
                return SessionClassification.EXCHANGE_HOLIDAY
            if closed.category == "NO_TRADING":
                return SessionClassification.NO_TRADING_CLOSED
            return SessionClassification.SOURCE_UNAVAILABLE
        if lifecycle is not None:
            if lifecycle.listed_from is not None and session_date < lifecycle.listed_from:
                return SessionClassification.CONTRACT_NOT_LISTED
            if lifecycle.expiry is not None and session_date > lifecycle.expiry:
                return SessionClassification.CONTRACT_EXPIRED
        return SessionClassification.SCHEDULED_SESSION

    def evaluate_absence(
        self,
        session_date: date,
        lifecycle: ContractLifecycleEvidence | None = None,
    ) -> SessionEvaluation:
        """Evaluate one date with NO canonical rows observed on it."""
        intrinsic = self.classify_session(session_date, lifecycle)
        if intrinsic is SessionClassification.SCHEDULED_SESSION:
            classification = SessionClassification.MISSING_SESSION_EVIDENCE
            detail = "scheduled session has no canonical row evidence"
        else:
            classification = intrinsic
            detail = ""
        return SessionEvaluation(
            session_date=session_date,
            intrinsic_state=intrinsic,
            classification=classification,
            detail=detail,
        )

    def evaluate_observation(
        self,
        session_date: date,
        *,
        rows_observed: bool,
        lifecycle: ContractLifecycleEvidence | None = None,
    ) -> SessionEvaluation:
        """Evaluate one date given whether canonical rows were observed.

        Rows on a confidently-evidenced non-session date (weekend, holiday,
        closed, or outside lifecycle boundaries) contradict the authoritative
        evidence and are surfaced as UNKNOWN for review - never silently
        accepted, never rewritten (fail-closed discipline).  Rows on dates
        without authoritative coverage remain CALENDAR_UNAVAILABLE.
        """
        intrinsic = self.classify_session(session_date, lifecycle)
        detail = ""
        if not rows_observed:
            evaluation = self.evaluate_absence(session_date, lifecycle)
            return evaluation
        if intrinsic is SessionClassification.SCHEDULED_SESSION:
            classification = SessionClassification.SCHEDULED_SESSION
        elif intrinsic is SessionClassification.CALENDAR_UNAVAILABLE:
            classification = SessionClassification.CALENDAR_UNAVAILABLE
            detail = "rows observed outside authoritative calendar coverage"
        else:
            classification = SessionClassification.UNKNOWN
            detail = f"canonical rows contradict {intrinsic.value} evidence"
        return SessionEvaluation(
            session_date=session_date,
            intrinsic_state=intrinsic,
            classification=classification,
            detail=detail,
        )

    def iter_coverage_gap(self, session_date: date) -> bool:
        """Return True when the date lies outside authoritative evidence coverage."""
        return self._dataset is None or not self._dataset.covers(session_date)


__all__ = [
    "CALENDAR_DATA_SCHEMA_VERSION",
    "CLOSED_SESSION_CATEGORIES",
    "DEFAULT_NSE_CALENDAR_ID",
    "CalendarAuthorityError",
    "CalendarDataCorrupt",
    "CalendarDataUnavailable",
    "ClosedSession",
    "ContractLifecycleEvidence",
    "KNOWN_CLOSED_CLASSIFICATIONS",
    "MarketCalendarAuthority",
    "MarketCalendarDataset",
    "REVIEW_REQUIRED_CLASSIFICATIONS",
    "SessionClassification",
    "SessionEvaluation",
    "parse_calendar_date",
    "parse_session_time",
]
