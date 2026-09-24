"""Deterministic session-aware market-bar resampling for AlgoFortis Data V2."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum

from engine.data.calendar import CalendarError, ExchangeCalendar
from engine.data.quality import RawBar
from engine.reproducibility.codec import CanonicalCodec


class ResampleError(ValueError):
    """Raised when source data cannot be resampled unambiguously."""


class ResampleIssueCode(str, Enum):
    MISSING_INPUT = "MISSING_INPUT"
    INCOMPLETE_BUCKET = "INCOMPLETE_BUCKET"
    OFF_SESSION = "OFF_SESSION"


@dataclass(frozen=True, slots=True)
class ResampleIssue:
    code: ResampleIssueCode
    timestamp: datetime
    detail: str


@dataclass(frozen=True, slots=True)
class ResampledBar:
    symbol: str
    timestamp: datetime
    timeframe: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    source_count: int


@dataclass(frozen=True, slots=True)
class ResampleResult:
    bars: tuple[ResampledBar, ...]
    issues: tuple[ResampleIssue, ...]
    fingerprint: str


class DeterministicResampler:
    """Aggregate complete integer-minute buckets anchored to exchange sessions."""

    def __init__(self, *, target_minutes: int) -> None:
        if isinstance(target_minutes, bool) or not isinstance(target_minutes, int) or target_minutes <= 0:
            raise ResampleError("target_minutes must be a positive integer")
        self.target_minutes = target_minutes
        self._interval = timedelta(minutes=target_minutes)

    def resample(
        self,
        bars: tuple[RawBar, ...] | list[RawBar],
        *,
        calendar: ExchangeCalendar,
        market: str,
    ) -> ResampleResult:
        source = tuple(bars)
        if not isinstance(calendar, ExchangeCalendar):
            raise ResampleError("calendar must be ExchangeCalendar")
        if not isinstance(market, str) or not market.strip():
            raise ResampleError("market must be non-empty")
        if any(not isinstance(bar, RawBar) for bar in source):
            raise ResampleError("bars must contain RawBar values")

        seen: set[tuple[str, datetime]] = set()
        for bar in source:
            key = (bar.symbol, bar.timestamp)
            if key in seen:
                raise ResampleError("duplicate source timestamp is ambiguous")
            seen.add(key)

        grouped: dict[tuple[str, datetime], list[RawBar]] = defaultdict(list)
        issues: list[ResampleIssue] = []

        for bar in sorted(source, key=lambda item: (item.symbol, item.timestamp)):
            try:
                session_open, session_close = calendar.session_bounds(market, bar.timestamp.date())
            except CalendarError:
                issues.append(
                    ResampleIssue(
                        ResampleIssueCode.OFF_SESSION,
                        bar.timestamp,
                        "source bar falls on a closed market day",
                    )
                )
                continue

            local_timestamp = bar.timestamp.astimezone(session_open.tzinfo)
            if local_timestamp < session_open or local_timestamp > session_close:
                issues.append(
                    ResampleIssue(
                        ResampleIssueCode.OFF_SESSION,
                        local_timestamp,
                        "source bar falls outside the market session",
                    )
                )
                continue

            elapsed_seconds = int((local_timestamp - session_open).total_seconds())
            bucket_index = elapsed_seconds // int(self._interval.total_seconds())
            bucket_start = session_open + bucket_index * self._interval
            grouped[(bar.symbol, bucket_start)].append(
                RawBar(
                    symbol=bar.symbol,
                    timestamp=local_timestamp,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                )
            )

        output: list[ResampledBar] = []
        for (symbol, bucket_start), bucket in sorted(grouped.items(), key=lambda item: item[0]):
            session_open, session_close = calendar.session_bounds(market, bucket_start.date())
            bucket_end_exclusive = bucket_start + self._interval

            # A full bucket needs target_minutes minute-start observations. If the
            # bucket itself cannot fit within the session, never borrow from another
            # session/day to complete it.
            if bucket_end_exclusive - timedelta(minutes=1) > session_close:
                issues.append(
                    ResampleIssue(
                        ResampleIssueCode.INCOMPLETE_BUCKET,
                        bucket_start,
                        "target bucket extends beyond session boundary",
                    )
                )
                continue

            ordered = tuple(sorted(bucket, key=lambda item: item.timestamp))
            expected = tuple(bucket_start + timedelta(minutes=offset) for offset in range(self.target_minutes))
            actual = tuple(item.timestamp for item in ordered)
            if actual != expected:
                issues.append(
                    ResampleIssue(
                        ResampleIssueCode.MISSING_INPUT,
                        bucket_start,
                        "target bucket is missing one or more source minutes",
                    )
                )
                continue

            output.append(
                ResampledBar(
                    symbol=symbol,
                    timestamp=bucket_start,
                    timeframe=f"{self.target_minutes}m",
                    open=ordered[0].open,
                    high=max(item.high for item in ordered),
                    low=min(item.low for item in ordered),
                    close=ordered[-1].close,
                    volume=sum((item.volume for item in ordered), Decimal("0")),
                    source_count=len(ordered),
                )
            )

        bars_result = tuple(output)
        issues_result = tuple(
            sorted(issues, key=lambda item: (item.timestamp, item.code.value, item.detail))
        )
        fingerprint = CanonicalCodec.fingerprint(
            "algofortis-resample-result/v1",
            (
                ("market", market.strip().upper()),
                ("target_minutes", str(self.target_minutes)),
                (
                    "bars",
                    tuple(
                        (
                            bar.symbol,
                            bar.timestamp.isoformat(),
                            bar.timeframe,
                            str(bar.open),
                            str(bar.high),
                            str(bar.low),
                            str(bar.close),
                            str(bar.volume),
                            str(bar.source_count),
                        )
                        for bar in bars_result
                    ),
                ),
                (
                    "issues",
                    tuple(
                        (issue.code.value, issue.timestamp.isoformat(), issue.detail)
                        for issue in issues_result
                    ),
                ),
            ),
        )
        return ResampleResult(bars_result, issues_result, fingerprint)


__all__ = [
    "ResampleError",
    "ResampleIssueCode",
    "ResampleIssue",
    "ResampledBar",
    "ResampleResult",
    "DeterministicResampler",
]
