"""Deterministic research fills; no broker or live path."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Callable

from engine.reproducibility.codec import CanonicalCodec
from .contracts import Bar, ExecutionModel, OrderIntent, V2Error


@dataclass(frozen=True, slots=True)
class FillEvent:
    bar_index: int
    timestamp: datetime
    side: str
    requested_quantity: Decimal
    filled_quantity: Decimal
    price: Decimal | None
    fee: Decimal
    status: str


@dataclass(frozen=True, slots=True)
class SimulationResult:
    events: tuple[FillEvent, ...]
    fingerprint: str


def _fingerprint(events: tuple[FillEvent, ...], model: ExecutionModel) -> str:
    return CanonicalCodec.fingerprint("algofortis-backtest-v2-replay/v1", (
        ("model", (model.version, model.latency_bars, model.spread, model.slippage,
                    model.fee_per_unit, model.liquidity_fraction)),
        ("events", tuple((e.bar_index, e.timestamp, e.side, e.requested_quantity,
                          e.filled_quantity, e.price, e.fee, e.status) for e in events)),
    ))


def simulate(bars: tuple[Bar, ...], orders: tuple[OrderIntent, ...],
             model: ExecutionModel) -> SimulationResult:
    if not isinstance(model, ExecutionModel) or not isinstance(bars, tuple) or not isinstance(orders, tuple):
        raise V2Error("versioned model, tuple bars and tuple orders required")
    if any(not isinstance(b, Bar) for b in bars) or any(b.timestamp >= c.timestamp for b, c in zip(bars, bars[1:])):
        raise V2Error("bars must have strictly increasing timestamps")
    if any(not isinstance(o, OrderIntent) or o.bar_index >= len(bars) for o in orders):
        raise V2Error("orders must refer to an available bar")
    events = []
    remaining_liquidity: dict[int, Decimal] = {}
    for order in sorted(orders, key=lambda item: item.bar_index):
        index = order.bar_index + model.latency_bars
        if index >= len(bars):
            events.append(FillEvent(index, bars[-1].timestamp, order.side, order.quantity,
                                    Decimal(0), None, Decimal(0), "REJECTED_LATENCY"))
            continue
        bar = bars[index]
        remaining_liquidity.setdefault(index, bar.volume * model.liquidity_fraction)
        if order.stop_price is not None:
            hit = bar.high >= order.stop_price if order.side == "BUY" else bar.low <= order.stop_price
            if not hit:
                events.append(FillEvent(index, bar.timestamp, order.side, order.quantity,
                                        Decimal(0), None, Decimal(0), "UNTRIGGERED"))
                continue
            base = max(bar.open, order.stop_price) if order.side == "BUY" else min(bar.open, order.stop_price)
        else:
            base = bar.open
        filled = min(order.quantity, remaining_liquidity[index])
        remaining_liquidity[index] -= filled
        sign = Decimal(1) if order.side == "BUY" else Decimal(-1)
        price = base + sign * (model.spread / 2 + model.slippage) if filled else None
        if price is not None and price <= 0:
            raise V2Error("modeled fill price must be positive")
        events.append(FillEvent(index, bar.timestamp, order.side, order.quantity, filled,
                                price, filled * model.fee_per_unit,
                                "REJECTED_LIQUIDITY" if not filled else "PARTIAL" if filled < order.quantity else "FILLED"))
    ordered = tuple(events)
    return SimulationResult(ordered, _fingerprint(ordered, model))


def simulate_strategy(bars: tuple[Bar, ...], strategy: Callable[[tuple[Bar, ...]], tuple[OrderIntent, ...]],
                      model: ExecutionModel) -> SimulationResult:
    intents = []
    for index in range(len(bars)):
        try:
            generated = strategy(bars[:index + 1])
        except (IndexError, KeyError) as exc:
            raise V2Error("strategy attempted unavailable or future data") from exc
        if not isinstance(generated, tuple) or any(not isinstance(x, OrderIntent) or x.bar_index != index for x in generated):
            raise V2Error("strategy may issue intents for the current bar only")
        intents.extend(generated)
    return simulate(bars, tuple(intents), model)
