"""Deterministic Phase-5 Paper-vs-Backtest drift reporting.

This module reports execution differences. It does not define production drift
thresholds and cannot promote a strategy or arm Live execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


def _aware(value: object, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value


def _decimal(value: object, field: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field} must be Decimal")
    if not value.is_finite():
        raise ValueError(f"{field} must be finite")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True, slots=True)
class DriftExecutionRecord:
    logical_intent_id: str
    entry_time: datetime
    entry_price: Decimal
    exit_time: datetime
    exit_price: Decimal
    quantity: Decimal
    costs: Decimal
    realized_pnl: Decimal
    lifecycle_result: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "logical_intent_id", _text(self.logical_intent_id, "logical_intent_id"))
        object.__setattr__(self, "entry_time", _aware(self.entry_time, "entry_time"))
        object.__setattr__(self, "entry_price", _decimal(self.entry_price, "entry_price"))
        object.__setattr__(self, "exit_time", _aware(self.exit_time, "exit_time"))
        object.__setattr__(self, "exit_price", _decimal(self.exit_price, "exit_price"))
        quantity = _decimal(self.quantity, "quantity")
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        object.__setattr__(self, "quantity", quantity)
        costs = _decimal(self.costs, "costs")
        if costs < 0:
            raise ValueError("costs must be non-negative")
        object.__setattr__(self, "costs", costs)
        object.__setattr__(self, "realized_pnl", _decimal(self.realized_pnl, "realized_pnl"))
        object.__setattr__(self, "lifecycle_result", _text(self.lifecycle_result, "lifecycle_result"))


@dataclass(frozen=True, slots=True)
class DriftReport:
    logical_intent_id: str
    policy_ref: str | None
    entry_time_delta_ms: int
    exit_time_delta_ms: int
    entry_price_delta: Decimal
    exit_price_delta: Decimal
    cost_delta: Decimal
    realized_pnl_delta: Decimal
    lifecycle_match: bool
    promotion_eligible: bool
    reason: str


class PaperDriftReporter:
    @staticmethod
    def compare(
        backtest_record: DriftExecutionRecord,
        paper_record: DriftExecutionRecord,
        *,
        policy_ref: str | None,
    ) -> DriftReport:
        if not isinstance(backtest_record, DriftExecutionRecord):
            raise TypeError("backtest_record must be DriftExecutionRecord")
        if not isinstance(paper_record, DriftExecutionRecord):
            raise TypeError("paper_record must be DriftExecutionRecord")
        if backtest_record.logical_intent_id != paper_record.logical_intent_id:
            raise ValueError("drift records must reference the same logical intent")
        if policy_ref is not None:
            policy_ref = _text(policy_ref, "policy_ref")

        entry_time_delta_ms = int(
            (paper_record.entry_time - backtest_record.entry_time).total_seconds() * 1000
        )
        exit_time_delta_ms = int(
            (paper_record.exit_time - backtest_record.exit_time).total_seconds() * 1000
        )
        reason = "MISSING_DRIFT_POLICY" if policy_ref is None else "POLICY_EVALUATION_DEFERRED"

        return DriftReport(
            logical_intent_id=backtest_record.logical_intent_id,
            policy_ref=policy_ref,
            entry_time_delta_ms=entry_time_delta_ms,
            exit_time_delta_ms=exit_time_delta_ms,
            entry_price_delta=paper_record.entry_price - backtest_record.entry_price,
            exit_price_delta=paper_record.exit_price - backtest_record.exit_price,
            cost_delta=paper_record.costs - backtest_record.costs,
            realized_pnl_delta=paper_record.realized_pnl - backtest_record.realized_pnl,
            lifecycle_match=paper_record.lifecycle_result == backtest_record.lifecycle_result,
            promotion_eligible=False,
            reason=reason,
        )


__all__ = ["DriftExecutionRecord", "DriftReport", "PaperDriftReporter"]
