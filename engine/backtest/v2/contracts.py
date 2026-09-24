"""Immutable and explicit Backtest V2 inputs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


class V2Error(ValueError):
    pass


def finite(value: object, name: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or (positive and value <= 0) or (not positive and value < 0):
        raise V2Error(f"{name} must be a finite {'positive' if positive else 'nonnegative'} Decimal")
    return value


@dataclass(frozen=True, slots=True)
class Bar:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.timestamp, datetime) or self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise V2Error("bar timestamp requires timezone")
        for field in ("open", "high", "low", "close"):
            finite(getattr(self, field), field, positive=True)
        finite(self.volume, "volume")
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close) or self.high < self.low:
            raise V2Error("OHLC range inconsistent")


@dataclass(frozen=True, slots=True)
class ExecutionModel:
    version: str
    latency_bars: int = 0
    spread: Decimal = Decimal(0)
    slippage: Decimal = Decimal(0)
    fee_per_unit: Decimal = Decimal(0)
    liquidity_fraction: Decimal = Decimal(1)
    tax_per_unit: Decimal = Decimal(0)
    brokerage_per_order: Decimal = Decimal(0)
    fill_edge: str = "OPEN"
    rejected_order_indices: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or "@" not in self.version:
            raise V2Error("versioned execution model required")
        if isinstance(self.latency_bars, bool) or not isinstance(self.latency_bars, int) or self.latency_bars < 0:
            raise V2Error("latency_bars must be nonnegative integer")
        for field in ("spread", "slippage", "fee_per_unit", "tax_per_unit", "brokerage_per_order"):
            finite(getattr(self, field), field)
        if self.fill_edge not in ("OPEN", "CLOSE"):
            raise V2Error("fill_edge must be OPEN or CLOSE")
        if (not isinstance(self.rejected_order_indices, tuple)
                or any(isinstance(x, bool) or not isinstance(x, int) or x < 0 for x in self.rejected_order_indices)
                or tuple(sorted(set(self.rejected_order_indices))) != self.rejected_order_indices):
            raise V2Error("rejected_order_indices must be sorted unique nonnegative integers")
        finite(self.liquidity_fraction, "liquidity_fraction", positive=True)
        if self.liquidity_fraction > 1:
            raise V2Error("liquidity_fraction cannot exceed one")


@dataclass(frozen=True, slots=True)
class OrderIntent:
    bar_index: int
    side: str
    quantity: Decimal
    stop_price: Decimal | None = None

    def __post_init__(self) -> None:
        if isinstance(self.bar_index, bool) or not isinstance(self.bar_index, int) or self.bar_index < 0:
            raise V2Error("bar_index must be nonnegative")
        if self.side not in ("BUY", "SELL"):
            raise V2Error("side must be BUY or SELL")
        finite(self.quantity, "quantity", positive=True)
        if self.stop_price is not None:
            finite(self.stop_price, "stop_price", positive=True)
