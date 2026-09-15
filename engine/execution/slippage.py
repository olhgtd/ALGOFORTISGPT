"""Replaceable pre-cost slippage boundary for execution."""

from typing import Protocol
from decimal import Decimal

from engine.backtest.engine import BarEvent


class SlippageModel(Protocol):
    """Adjust an already-approved execution basis without portfolio concerns."""

    model_id: str

    def apply(self, *, action: str, price: Decimal, bar: BarEvent) -> Decimal:
        """Return the execution price after slippage."""


class ZeroSlippage:
    """Owner-approved initial model: retain the approved fill basis exactly."""

    model_id = "zero"

    def apply(self, *, action: str, price: Decimal, bar: BarEvent) -> Decimal:
        return price
