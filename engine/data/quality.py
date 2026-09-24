"""Deterministic market-data quality analysis for AlgoFortis Data V2."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_EVEN
from enum import Enum

from engine.core.numeric import as_decimal
from engine.data.calendar import CalendarError, ExchangeCalendar
from engine.reproducibility.codec import CanonicalCodec


class DataQualityError(ValueError):
    """Raised when quality-pipeline inputs are invalid."""


class QualityIssueCode(str, Enum):
    OUT_OF_ORDER = "OUT_OF_ORDER"
    DUPLICATE = "DUPLICATE"
    GAP = "GAP"
    INVALID_OHLC = "INVALID_OHLC"
    NEGATIVE_VOLUME = "NEGATIVE_VOLUME"
    OFF_SESSION = "OFF_SESSION"
    OUTLIER = "OUTLIER"


@dataclass(frozen=True, slots=True)
class RawBar:
    """Raw source bar. Validation is intentionally deferred to QualityPipeline."""

    symbol: str
    timestamp: datetime
    open: Decimal | int | float | str
    high: Decimal | int | float | str
    low: Decimal | int | float | str
    close: Decimal | int | float | str
    volume: Decimal | int | float | str

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise DataQualityError("symbol must be non-empty")
        object.__setattr__(self, "symbol", self.symbol.strip().upper())
        if not isinstance(self.timestamp, datetime) or self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise DataQualityError("timestamp must be timezone-aware")
        for field_name in ("open", "high", "low", "close", "volume"):
            object.__setattr__(self, field_name, as_decimal(getattr(self, field_name), field_name))


@dataclass(frozen=True, slots=True)
class QualityIssue:
    code: QualityIssueCode
    timestamp: datetime | None
    detail: str


@dataclass(frozen=True, slots=True)
class QualityScorecard:
    dataset_id: str
    version_id: str
    quality_score: Decimal
    coverage_ratio: Decimal
    issue_count: int
    accepted_count: int
    quarantined_count: int
    fingerprint: str


@dataclass(frozen=True, slots=True)
class QualityReport:
    accepted: tuple[RawBar, ...]
    quarantined: tuple[RawBar, ...]
    issues: tuple[QualityIssue, ...]
    scorecard: QualityScorecard


class QualityPipeline:
    """Fail-closed quality checks without silently rewriting source bars."""

    def __init__(
        self,
        *,
        expected_interval: timedelta,
        outlier_return_threshold: Decimal | int | float | str,
    ) -> None:
        if not isinstance(expected_interval, timedelta) or expected_interval <= timedelta(0):
            raise DataQualityError("expected_interval must be positive")
        threshold = as_decimal(outlier_return_threshold, "outlier_return_threshold")
        if threshold <= 0:
            raise DataQualityError("outlier_return_threshold must be positive")
        self.expected_interval = expected_interval
        self.outlier_return_threshold = threshold

    def analyze(
        self,
        bars: tuple[RawBar, ...] | list[RawBar],
        *,
        calendar: ExchangeCalendar,
        market: str,
        dataset_id: str = "",
        version_id: str = "",
    ) -> QualityReport:
        source = tuple(bars)
        if not isinstance(calendar, ExchangeCalendar):
            raise DataQualityError("calendar must be ExchangeCalendar")
        if not isinstance(market, str) or not market.strip():
            raise DataQualityError("market must be non-empty")
        if any(not isinstance(bar, RawBar) for bar in source):
            raise DataQualityError("bars must contain RawBar values")

        issues: list[QualityIssue] = []
        quarantined_indexes: set[int] = set()

        # Preserve source order evidence before deterministic sorting.
        for previous, current in zip(source, source[1:]):
            if current.timestamp < previous.timestamp:
                issues.append(
                    QualityIssue(
                        QualityIssueCode.OUT_OF_ORDER,
                        current.timestamp,
                        "source timestamps are not monotonic",
                    )
                )

        timestamp_counts = Counter(bar.timestamp for bar in source)
        duplicate_timestamps = {stamp for stamp, count in timestamp_counts.items() if count > 1}
        for stamp in sorted(duplicate_timestamps):
            issues.append(QualityIssue(QualityIssueCode.DUPLICATE, stamp, "duplicate timestamp is ambiguous"))
        for index, bar in enumerate(source):
            if bar.timestamp in duplicate_timestamps:
                quarantined_indexes.add(index)

        # Gap detection uses unique chronological raw observations so duplicate quarantine
        # does not hide missing expected intervals.
        unique_timestamps = sorted(timestamp_counts)
        for previous, current in zip(unique_timestamps, unique_timestamps[1:]):
            if current - previous > self.expected_interval:
                missing = int((current - previous) / self.expected_interval) - 1
                issues.append(
                    QualityIssue(
                        QualityIssueCode.GAP,
                        current,
                        f"missing {missing} expected interval(s)",
                    )
                )

        for index, bar in enumerate(source):
            invalid_ohlc = (
                bar.open <= 0
                or bar.high <= 0
                or bar.low <= 0
                or bar.close <= 0
                or bar.high < bar.low
                or bar.high < bar.open
                or bar.high < bar.close
                or bar.low > bar.open
                or bar.low > bar.close
            )
            if invalid_ohlc:
                issues.append(QualityIssue(QualityIssueCode.INVALID_OHLC, bar.timestamp, "invalid OHLC relationship"))
                quarantined_indexes.add(index)
            if bar.volume < 0:
                issues.append(QualityIssue(QualityIssueCode.NEGATIVE_VOLUME, bar.timestamp, "volume is negative"))
                quarantined_indexes.add(index)

            try:
                session_open, session_close = calendar.session_bounds(market, bar.timestamp.date())
                in_session = session_open <= bar.timestamp <= session_close
            except CalendarError:
                in_session = False
            if not in_session:
                issues.append(QualityIssue(QualityIssueCode.OFF_SESSION, bar.timestamp, "bar is outside market session"))
                quarantined_indexes.add(index)

        # Outlier detection is advisory only: source bars stay unchanged and accepted.
        chronological = sorted(
            ((index, bar) for index, bar in enumerate(source) if index not in quarantined_indexes),
            key=lambda item: (item[1].timestamp, item[0]),
        )
        for (_, previous), (_, current) in zip(chronological, chronological[1:]):
            if previous.close > 0:
                absolute_return = abs((current.close - previous.close) / previous.close)
                if absolute_return > self.outlier_return_threshold:
                    issues.append(
                        QualityIssue(
                            QualityIssueCode.OUTLIER,
                            current.timestamp,
                            "close-to-close return exceeds configured threshold",
                        )
                    )

        accepted = tuple(bar for index, bar in enumerate(source) if index not in quarantined_indexes)
        quarantined = tuple(bar for index, bar in enumerate(source) if index in quarantined_indexes)

        coverage_ratio = self._coverage_ratio(unique_timestamps)
        issue_count = len(issues)
        penalty = Decimal(issue_count * 10)
        quality_score = max(Decimal("0"), Decimal("100") - penalty).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN)

        normalized_dataset_id = dataset_id.strip() if isinstance(dataset_id, str) else ""
        normalized_version_id = version_id.strip() if isinstance(version_id, str) else ""
        fingerprint = CanonicalCodec.fingerprint(
            "algofortis-data-quality-scorecard/v1",
            (
                ("dataset_id", normalized_dataset_id),
                ("version_id", normalized_version_id),
                ("quality_score", str(quality_score)),
                ("coverage_ratio", str(coverage_ratio)),
                ("accepted_count", len(accepted)),
                ("quarantined_count", len(quarantined)),
                (
                    "issues",
                    tuple(
                        (
                            issue.code.value,
                            "" if issue.timestamp is None else issue.timestamp.isoformat(),
                            issue.detail,
                        )
                        for issue in issues
                    ),
                ),
            ),
        )
        scorecard = QualityScorecard(
            dataset_id=normalized_dataset_id,
            version_id=normalized_version_id,
            quality_score=quality_score,
            coverage_ratio=coverage_ratio,
            issue_count=issue_count,
            accepted_count=len(accepted),
            quarantined_count=len(quarantined),
            fingerprint=fingerprint,
        )
        return QualityReport(accepted=accepted, quarantined=quarantined, issues=tuple(issues), scorecard=scorecard)

    def _coverage_ratio(self, timestamps: list[datetime]) -> Decimal:
        if not timestamps:
            return Decimal("0.0000")
        if len(timestamps) == 1:
            return Decimal("1.0000")
        expected_slots = int((timestamps[-1] - timestamps[0]) / self.expected_interval) + 1
        if expected_slots <= 0:
            return Decimal("0.0000")
        ratio = Decimal(len(timestamps)) / Decimal(expected_slots)
        return min(Decimal("1"), ratio).quantize(Decimal("0.0000"), rounding=ROUND_HALF_EVEN)


__all__ = [
    "DataQualityError",
    "QualityIssueCode",
    "RawBar",
    "QualityIssue",
    "QualityScorecard",
    "QualityReport",
    "QualityPipeline",
]
