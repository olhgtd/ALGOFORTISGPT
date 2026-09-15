"""Separate P1-5 cost-adjusted view; never mutates gross portfolio state."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Iterable

from engine.portfolio import AccountSnapshot
from engine.portfolio.model import INTERNAL_DECIMAL_CONTEXT, quantize_monetary
from .model import CostLegAssessment


@dataclass(frozen=True)
class CostAdjustedAccountProjection:
    account_id: str
    gross_snapshot: AccountSnapshot
    recognized_leg_assessments: tuple[CostLegAssessment, ...]
    recognized_cost: Decimal
    available_buying_power: Decimal
    cost_adjusted_equity: Decimal

    def __post_init__(self) -> None:
        if self.account_id != self.gross_snapshot.account_id:
            raise ValueError("projection account does not match gross snapshot")
        values = tuple(self.recognized_leg_assessments)
        if len({value.assessment_id for value in values}) != len(values):
            raise ValueError("duplicate recognized leg cost")
        if any(value.account_id != self.account_id or value.currency != self.gross_snapshot.currency for value in values):
            raise ValueError("recognized cost evidence does not match account")
        object.__setattr__(self, "recognized_leg_assessments", tuple(sorted(values, key=lambda value: value.assessment_id)))

    @classmethod
    def from_evidence(cls, snapshot: AccountSnapshot, assessments: Iterable[CostLegAssessment]):
        values = tuple(assessments)
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            total = quantize_monetary(sum((value.total_cost for value in values), Decimal("0")), snapshot.monetary_quantum)
            available = quantize_monetary(snapshot.cash - total, snapshot.monetary_quantum)
            equity = quantize_monetary(snapshot.equity - total, snapshot.monetary_quantum)
        if available < 0:
            available = Decimal("0").quantize(snapshot.monetary_quantum)
        return cls(snapshot.account_id, snapshot, values, total, available, equity)

    def permits_entry(self, required_gross_cash: Decimal) -> bool:
        return required_gross_cash <= self.available_buying_power
