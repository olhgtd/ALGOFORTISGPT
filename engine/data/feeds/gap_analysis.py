"""§129.17 - reusable session-gap analysis over canonical OHLCV data.

This module owns NO calendar/session semantics of its own.  Every date
classification is delegated to the single authoritative
``engine.market.calendar.MarketCalendarAuthority``.  The analyzer is pure:
it never reads or writes storage, never mutates its inputs, and never
fabricates rows.  It is reusable by historical ingestion, gap analysis,
replay/backtest, and future validation layers.

Frozen rules honored here (§129.17):
- weekends and exchange holidays are NEVER missing-data errors;
- contract not-listed / expired / no-trading / source-unavailable absences
  are distinguished only where authoritative evidence exists;
- dates without authoritative calendar coverage are CALENDAR_UNAVAILABLE
  and force review-required status (fail closed) instead of guesses;
- actual missing scheduled-session evidence is reported explicitly as
  ``missing_session_evidence`` CANDIDATES for human review.

Analysis range is the analyzed date range of one canonical target: by
default the observed canonical range ``[first_date, last_date]``; callers
holding authoritative contract-window evidence may extend it explicitly via
``assessment_window`` so evidenced pre-listing / post-expiry absences become
distinguishable instead of silently unscanned.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from engine.market.calendar import (
    DEFAULT_NSE_CALENDAR_ID,
    KNOWN_CLOSED_CLASSIFICATIONS,
    REVIEW_REQUIRED_CLASSIFICATIONS,
    ContractLifecycleEvidence,
    MarketCalendarAuthority,
    SessionClassification,
    SessionEvaluation,
)

#: Deterministic offline calendar-id wiring per market tag.  Only the
#: owner-approved India/NSE mapping exists; any other market yields NO
#: automatic authority (fail-closed review), never a guessed calendar.
DEFAULT_OFFLINE_CALENDAR_BY_MARKET = {
    "india": DEFAULT_NSE_CALENDAR_ID,
}

GAPS_STATUS_CLEAN = "clean"
GAPS_STATUS_MISSING_CANDIDATES = "missing_candidates"
GAPS_STATUS_CALENDAR_REVIEW_REQUIRED = "calendar_review_required"

MAX_GAP_SAMPLES = 20


@dataclass(frozen=True)
class TargetGapReport:
    """Deterministic gap-evidence result for one canonical target."""

    observed_start: date | None
    observed_end: date | None
    counts: Mapping[str, int]
    samples: tuple[str, ...]

    @property
    def missing_candidate_count(self) -> int:
        return self.counts.get(SessionClassification.MISSING_SESSION_EVIDENCE.value, 0)

    @property
    def known_closed_count(self) -> int:
        return sum(
            count
            for classification_value, count in self.counts.items()
            if SessionClassification(classification_value) in KNOWN_CLOSED_CLASSIFICATIONS
        )

    @property
    def review_required(self) -> bool:
        return any(
            SessionClassification(value) in REVIEW_REQUIRED_CLASSIFICATIONS
            for value in self.counts
        )

    @property
    def status(self) -> str:
        if self.review_required:
            return GAPS_STATUS_CALENDAR_REVIEW_REQUIRED
        if self.missing_candidate_count:
            return GAPS_STATUS_MISSING_CANDIDATES
        return GAPS_STATUS_CLEAN


def _canonical_dates(timestamps: pd.Series, *, timezone_name: str) -> list[date]:
    """Reduce canonical timestamps to unique exchange-local session dates.

    Mirrors the established ingestion convention: naive timestamps are
    localized to the market timezone without shifting clock times.
    """
    if not isinstance(timestamps, pd.Series):
        timestamps = pd.Series(list(timestamps))
    parsed = pd.to_datetime(timestamps, errors="coerce").dropna()
    if parsed.dt.tz is None:
        parsed = parsed.dt.tz_localize(timezone_name)
    else:
        parsed = parsed.dt.tz_convert(timezone_name)
    unique_dates = sorted({stamp.date() for stamp in parsed})
    return unique_dates


def _iter_dates(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def analyze_target_gaps(
    timestamps: pd.Series,
    *,
    authority: MarketCalendarAuthority | None,
    lifecycle: ContractLifecycleEvidence | None = None,
    max_samples: int = MAX_GAP_SAMPLES,
    assessment_window: tuple[date, date] | None = None,
) -> TargetGapReport:
    """Classify every exchange-local date in the analyzed range of one target.

    Default analyzed range is the observed canonical range
    ``[first_date, last_date]``.  Callers holding an explicit, authoritative
    assessment window (e.g. a verified contract lifetime) may pass
    ``assessment_window=(start, end)`` to extend the scanned range beyond
    observed rows; this is how evidenced pre-listing / post-expiry absences
    become distinguishable instead of silently unscanned.  An inverted or
    non-date window fails closed.

    ``authority=None`` means no authoritative calendar evidence was available:
    every analyzed date fails closed to CALENDAR_UNAVAILABLE.
    """
    timezone_name = authority.timezone_name if authority is not None else "Asia/Kolkata"
    unique_dates = _canonical_dates(timestamps, timezone_name=timezone_name)
    if assessment_window is not None:
        window_start, window_end = assessment_window
        if not isinstance(window_start, date) or not isinstance(window_end, date):
            raise ValueError("assessment_window bounds must be datetime.date values")
        if window_start > window_end:
            raise ValueError("assessment_window start must not be after end")
    if not unique_dates:
        if assessment_window is None:
            return TargetGapReport(
                observed_start=None,
                observed_end=None,
                counts={},
                samples=(),
            )
        unique_dates = [assessment_window[0]]
    observed_dates = set(unique_dates)
    analysis_start = unique_dates[0]
    analysis_end = unique_dates[-1]
    if assessment_window is not None:
        analysis_start = min(analysis_start, assessment_window[0])
        analysis_end = max(analysis_end, assessment_window[1])
    counter: Counter[str] = Counter()
    samples: list[str] = []
    for day in _iter_dates(analysis_start, analysis_end):
        if authority is not None:
            evaluation = authority.evaluate_observation(
                day,
                rows_observed=day in observed_dates,
                lifecycle=lifecycle,
            )
        else:
            evaluation = SessionEvaluation(
                session_date=day,
                intrinsic_state=SessionClassification.CALENDAR_UNAVAILABLE,
                classification=SessionClassification.CALENDAR_UNAVAILABLE,
                detail="no authoritative calendar evidence loaded",
            )
        value = evaluation.classification.value
        counter[value] += 1
        if evaluation.classification is not SessionClassification.SCHEDULED_SESSION:
            sample = f"{day.isoformat()}|{value}"
            if len(samples) < max_samples:
                samples.append(sample)
    samples.sort()
    return TargetGapReport(
        observed_start=analysis_start,
        observed_end=analysis_end,
        counts=dict(sorted(counter.items())),
        samples=tuple(samples),
    )


class _UnavailableEvaluation:
    """Local stand-in used only when no authority exists (fail closed)."""

    def __init__(self, session_date: date) -> None:
        self.session_date = session_date
        self.classification = SessionClassification.CALENDAR_UNAVAILABLE
        self.intrinsic_state = SessionClassification.CALENDAR_UNAVAILABLE
        self.detail = "no authoritative calendar evidence loaded"


_unavailable_evaluation = _UnavailableEvaluation


@dataclass(frozen=True)
class AggregateGapEvidence:
    """Aggregated manifest-facing gap evidence across one source file's targets."""

    gaps_status: str
    missing_candidate_count: int
    known_closed_count: int
    calendar_unavailable: bool
    samples: tuple[str, ...]


def aggregate_gap_evidence(
    reports: Iterable[TargetGapReport],
    *,
    max_samples: int = MAX_GAP_SAMPLES,
) -> AggregateGapEvidence:
    """Deterministically combine per-target reports into manifest fields."""
    total_counter: Counter[str] = Counter()
    all_samples: set[str] = set()
    review_required = False
    missing_candidates = 0
    known_closed = 0
    empty = True
    for report in reports:
        empty = False
        total_counter.update(report.counts)
        all_samples.update(report.samples)
        missing_candidates += report.missing_candidate_count
        known_closed += report.known_closed_count
        review_required = review_required or report.review_required
    if empty:
        return AggregateGapEvidence(
            gaps_status=GAPS_STATUS_CLEAN,
            missing_candidate_count=0,
            known_closed_count=0,
            calendar_unavailable=False,
            samples=(),
        )
    ordered_samples = tuple(sorted(all_samples)[:max_samples])
    if review_required:
        status: str = GAPS_STATUS_CALENDAR_REVIEW_REQUIRED
    elif missing_candidates:
        status = GAPS_STATUS_MISSING_CANDIDATES
    else:
        status = GAPS_STATUS_CLEAN
    return AggregateGapEvidence(
        gaps_status=status,
        missing_candidate_count=missing_candidates,
        known_closed_count=known_closed,
        calendar_unavailable=total_counter.get(SessionClassification.CALENDAR_UNAVAILABLE.value, 0) > 0,
        samples=ordered_samples,
    )


__all__ = [
    "AggregateGapEvidence",
    "DEFAULT_OFFLINE_CALENDAR_BY_MARKET",
    "GAPS_STATUS_CALENDAR_REVIEW_REQUIRED",
    "GAPS_STATUS_CLEAN",
    "GAPS_STATUS_MISSING_CANDIDATES",
    "MAX_GAP_SAMPLES",
    "TargetGapReport",
    "aggregate_gap_evidence",
    "analyze_target_gaps",
]
