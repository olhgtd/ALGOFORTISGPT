"""Phase 6 Q92 / Q93 — deterministic paper summaries from canonical evidence.

ADR §123.11 items 1–2: the daily summary and monthly per-strategy report are
Phase-6 obligations that aggregate ONLY from canonical accounting, trade, leg
and cost records. `audit_events` is NEVER a reporting or accounting authority
(§114.1, §114.14) and is not read anywhere in this module.

Frozen field authority:
- Q92 "Daily summary" and Q93 "Monthly report — aggregated metrics per
  strategy" (requirements-freeze-125.md) do not enumerate extra metrics, so
  ONLY canonically derivable values are reported: completed trade count,
  gross realized P&L, canonical cost totals, net realized P&L (gross − costs).
- Strategy identity = `TradeRecord.position_key` (strategy_id, strategy_version)
  — the canonical owner; never free-form payloads.
- Business date/month authority = trade completion (`closed_at`) projected to
  the repository-wide IST calendar (Q9); wall-clock is never consulted.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence
from uuid import uuid4
from zoneinfo import ZoneInfo

from engine.trades.model import TradeRecord

IST_CALENDAR: ZoneInfo = ZoneInfo("Asia/Kolkata")
IST: ZoneInfo = IST_CALENDAR

_ZERO = Decimal("0")

Q93_MONTHLY_SCHEMA_VERSION = "sentinelx-q93-monthly/v1"

_SAFE_SESSION_TOKEN = re.compile(r"[^A-Za-z0-9_-]")


class Q93PublicationError(RuntimeError):
    """Raised when a Q93 monthly publication cannot be completed safely."""


def q93_publication_outcome_published() -> str:
    return "PUBLISHED"


def q93_publication_outcome_already_published() -> str:
    return "ALREADY_PUBLISHED"


def ist_business_date(moment: datetime) -> date:
    """Canonical business-date projection (fail-closed on naive datetimes)."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f"canonical timestamps must be timezone-aware, got {moment!r}")
    return moment.astimezone(IST).date()


def _require_finite_decimal(value: Decimal, label: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal, got {type(value).__name__}")
    if not value.is_finite():
        raise ValueError(f"{label} must be finite, got {value!r}")
    return value


@dataclass(frozen=True)
class StrategyContribution:
    """One strategy's realized contribution inside one Q92 daily summary."""

    strategy_id: str
    strategy_version: str
    completed_trade_count: int
    gross_realized_pnl: Decimal
    total_cost: Decimal
    net_realized_pnl: Decimal


@dataclass(frozen=True)
class DailySummary:
    """Q92 — deterministic single-day summary over completed canonical trades."""

    trading_date: date
    currency: str | None
    completed_trade_count: int
    gross_realized_pnl: Decimal
    total_cost: Decimal
    net_realized_pnl: Decimal
    strategies: tuple[StrategyContribution, ...]


@dataclass(frozen=True)
class MonthlyStrategySummary:
    """Q93 — one (month, strategy) aggregate over completed canonical trades."""

    year: int
    month: int
    strategy_id: str
    strategy_version: str
    completed_trade_count: int
    gross_realized_pnl: Decimal
    total_cost: Decimal
    net_realized_pnl: Decimal


def _validate_trade(trade: TradeRecord) -> None:
    _require_finite_decimal(trade.gross_realized_pnl, f"gross_realized_pnl[{trade.trade_id}]")
    if trade.status is not None and str(getattr(trade.status, "value", trade.status)) != "CLOSED":
        raise ValueError(
            f"Q92/Q93 aggregate completed trades only; {trade.trade_id!r} status={trade.status!r}"
        )
    for leg in (*trade.entry_legs, *trade.exit_legs):
        _require_finite_decimal(leg.realized_pnl_delta, f"leg_pnl[{trade.trade_id}]")


def build_daily_summary(
    trades: Sequence[TradeRecord],
    *,
    costs_by_trade_id: Mapping[str, Decimal],
    trading_date: date,
) -> DailySummary:
    """Aggregate every completed trade whose IST close date equals `trading_date`.

    Explicit empty-day semantics: zero trades produce an all-zero summary with
    `currency=None` and an empty strategy tuple.
    """
    if not isinstance(trading_date, date):
        raise TypeError("trading_date must be a datetime.date")

    included = [t for t in trades if ist_business_date(t.closed_at) == trading_date]
    for t in included:
        _validate_trade(t)

    currencies = {t.currency for t in included}
    if len(currencies) > 1:
        raise ValueError(f"mixed currencies in one summary: {sorted(currencies)!r}")

    by_strategy: dict[tuple[str, str], list[TradeRecord]] = {}
    for t in included:
        by_strategy.setdefault((t.position_key.strategy_id, t.position_key.strategy_version), []).append(t)

    contributions: list[StrategyContribution] = []
    for key in sorted(by_strategy):
        group = by_strategy[key]
        gross = sum((t.gross_realized_pnl for t in group), _ZERO)
        cost = sum(
            (costs_by_trade_id.get(t.trade_id, _ZERO) for t in group), _ZERO
        )
        _require_finite_decimal(cost, f"total_cost[{key[0]}]")
        contributions.append(
            StrategyContribution(
                strategy_id=key[0],
                strategy_version=key[1],
                completed_trade_count=len(group),
                gross_realized_pnl=gross,
                total_cost=cost,
                net_realized_pnl=gross - cost,
            )
        )

    total_gross = sum((c.gross_realized_pnl for c in contributions), _ZERO)
    total_cost = sum((c.total_cost for c in contributions), _ZERO)
    currency = next(iter(currencies)) if currencies else None
    return DailySummary(
        trading_date=trading_date,
        currency=currency,
        completed_trade_count=len(included),
        gross_realized_pnl=total_gross,
        total_cost=total_cost,
        net_realized_pnl=total_gross - total_cost,
        strategies=tuple(contributions),
    )


def build_monthly_strategy_summaries(
    trades: Sequence[TradeRecord],
    *,
    costs_by_trade_id: Mapping[str, Decimal],
) -> tuple[MonthlyStrategySummary, ...]:
    """Aggregate completed trades per (IST close month, canonical strategy).

    Deterministic ordering: (year, month, strategy_id, strategy_version).
    Strategies never share trades; each trade contributes to exactly one row.
    """
    buckets: dict[tuple[int, int, str, str], list[TradeRecord]] = {}
    currency_by_bucket: dict[tuple[int, int, str, str], str] = {}
    for t in trades:
        _validate_trade(t)
        close_local = ist_business_date(t.closed_at)
        key = (
            close_local.year,
            close_local.month,
            t.position_key.strategy_id,
            t.position_key.strategy_version,
        )
        previous_currency = currency_by_bucket.setdefault(key, t.currency)
        if previous_currency != t.currency:
            raise ValueError(
                f"mixed currencies within one monthly strategy bucket {key}: "
                f"{previous_currency!r} vs {t.currency!r}"
            )
        buckets.setdefault(key, []).append(t)

    summaries: list[MonthlyStrategySummary] = []
    for key in sorted(buckets):
        group = buckets[key]
        gross = sum((t.gross_realized_pnl for t in group), _ZERO)
        cost = sum((costs_by_trade_id.get(t.trade_id, _ZERO) for t in group), _ZERO)
        _require_finite_decimal(cost, f"monthly_total_cost[{key}]")
        summaries.append(
            MonthlyStrategySummary(
                year=key[0],
                month=key[1],
                strategy_id=key[2],
                strategy_version=key[3],
                completed_trade_count=len(group),
                gross_realized_pnl=gross,
                total_cost=cost,
                net_realized_pnl=gross - cost,
            )
        )
    return tuple(summaries)


# ----------------------------------------------------------------------
# §124 R7 — monthly ↔ daily reconciliation
# ----------------------------------------------------------------------


def monthly_reconciliation_contributions(
    trades: Sequence[TradeRecord],
    *,
    costs_by_trade_id: Mapping[str, Decimal],
    year: int,
    month: int,
) -> tuple[StrategyContribution, ...]:
    """Sum the per-strategy Q92 daily contributions across one calendar month.

    Owner ruling R7 (§124.7): these sums must equal the corresponding Q93
    `MonthlyStrategySummary` values with exact Decimal equality.
    """
    dates = sorted(
        {
            ist_business_date(t.closed_at)
            for t in trades
            if ist_business_date(t.closed_at).year == year and ist_business_date(t.closed_at).month == month
        }
    )
    totals: dict[tuple[str, str], list[Decimal]] = {}
    counts: dict[tuple[str, str], int] = {}
    for day in dates:
        summary = build_daily_summary(trades, costs_by_trade_id=costs_by_trade_id, trading_date=day)
        for c in summary.strategies:
            key = (c.strategy_id, c.strategy_version)
            agg = totals.setdefault(key, [Decimal("0"), Decimal("0"), Decimal("0")])
            agg[0] += c.gross_realized_pnl
            agg[1] += c.total_cost
            agg[2] += c.net_realized_pnl
            counts[key] = counts.get(key, 0) + c.completed_trade_count
    return tuple(
        StrategyContribution(
            strategy_id=key[0],
            strategy_version=key[1],
            completed_trade_count=counts[key],
            gross_realized_pnl=values[0],
            total_cost=values[1],
            net_realized_pnl=values[2],
        )
        for key, values in sorted(totals.items())
    )


# ----------------------------------------------------------------------
# §124 R3/R5 — durable exactly-once Q93 monthly publication
# ----------------------------------------------------------------------


def _q93_document_bytes(
    rows: Sequence[MonthlyStrategySummary],
    *,
    paper_session_id: str,
    year: int,
    month: int,
) -> bytes:
    document = {
        "schema_version": Q93_MONTHLY_SCHEMA_VERSION,
        "paper_session_id": paper_session_id,
        "year": year,
        "month": month,
        "strategy_rows": [
            {
                "strategy_id": r.strategy_id,
                "strategy_version": r.strategy_version,
                "completed_trade_count": r.completed_trade_count,
                "gross_realized_pnl": str(r.gross_realized_pnl),
                "total_cost": str(r.total_cost),
                "net_realized_pnl": str(r.net_realized_pnl),
            }
            for r in sorted(rows, key=lambda r: (r.strategy_id, r.strategy_version))
        ],
    }
    return json.dumps(document, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


def publish_q93_monthly_summary(
    rows: Sequence[MonthlyStrategySummary],
    *,
    paper_session_id: str,
    year: int,
    month: int,
    destination_dir: Path | str,
) -> str:
    """Atomically finalize ONE (paper_session_id, year, month) Q93 report.

    Conventions mirror the established canonical ReportWriter mechanics
    (§124.8): exclusive claim, staging + fsync + atomic replace, deterministic
    content identity, PUBLISHED / ALREADY_PUBLISHED outcomes, conflict fails
    closed on any content difference. No wall-clock enters file content; the
    zero-row artifact is a valid finalized month under rulings R3/R6.
    """
    if not isinstance(paper_session_id, str) or not paper_session_id.strip():
        raise ValueError("paper_session_id must be a non-empty string")
    if not isinstance(year, int) or year < 1970 or year > 9999:
        raise ValueError(f"year out of range: {year!r}")
    if not isinstance(month, int) or not 1 <= month <= 12:
        raise ValueError(f"month out of range: {month!r}")
    for row in rows:
        if (row.year, row.month) != (year, month):
            raise ValueError(
                f"row {(row.strategy_id, row.strategy_version)} is for "
                f"{row.year}-{row.month:02d}, not {year}-{month:02d}"
            )

    directory = Path(destination_dir)
    if not directory.exists() or not directory.is_dir():
        raise Q93PublicationError("Q93 publication destination directory does not exist")

    session_token = _SAFE_SESSION_TOKEN.sub("_", paper_session_id)[:80]
    target = directory / f"sentinelx-q93-{session_token}-{year:04d}-{month:02d}.json"
    desired_raw = _q93_document_bytes(rows, paper_session_id=paper_session_id, year=year, month=month)

    lock = directory / f".{target.name}.sentinelx-lock"
    for _attempt in range(500):
        try:
            handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            time.sleep(0.01)
            continue
        os.close(handle)
        break
    else:
        raise Q93PublicationError("Q93 publication destination remains locked")

    try:
        if target.exists():
            existing = target.read_bytes()
            if existing != desired_raw:
                raise Q93PublicationError(
                    f"Q93 monthly conflict for {paper_session_id!r} {year}-{month:02d}: "
                    "existing final report differs from recomputed content"
                )
            return q93_publication_outcome_already_published()
        staging = directory / f".{target.name}.sentinelx-staging-{uuid4().hex}"
        try:
            with staging.open("xb") as stream:
                stream.write(desired_raw)
                stream.flush()
                os.fsync(stream.fileno())
            if staging.read_bytes() != desired_raw:
                raise Q93PublicationError("staged Q93 content verification failed")
            os.replace(staging, target)
            return q93_publication_outcome_published()
        except OSError as error:
            if staging.exists():
                staging.unlink()
            raise Q93PublicationError("atomic Q93 publication failed") from error
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
