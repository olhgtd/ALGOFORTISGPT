from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from engine.backtest.v2.contracts import Bar, ExecutionModel, OrderIntent, V2Error
from engine.backtest.v2.execution import simulate
from engine.backtest.v2.replay import replay


def test_execution_is_replayable_with_costs_partial_fills_and_rejections():
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = (Bar(t, Decimal("100"), Decimal("105"), Decimal("95"), Decimal("102"), Decimal("5")),
            Bar(t + timedelta(minutes=1), Decimal("104"), Decimal("108"), Decimal("103"), Decimal("106"), Decimal("5")))
    model = ExecutionModel(version="exec@v1", latency_bars=1, spread=Decimal("0.2"),
                           slippage=Decimal("0.1"), fee_per_unit=Decimal("0.05"),
                           liquidity_fraction=Decimal("0.5"))
    orders = (OrderIntent(bar_index=0, side="BUY", quantity=Decimal("4")),)
    first = simulate(bars, orders, model)
    assert first.fingerprint == simulate(bars, orders, model).fingerprint
    assert first.events[0].filled_quantity == Decimal("2.5")
    assert replay(first.events, model).fingerprint == first.fingerprint


def test_invalid_future_order_and_gapped_stop_fail_closed():
    with pytest.raises(V2Error):
        OrderIntent(bar_index=-1, side="BUY", quantity=Decimal("1"))
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = (Bar(t, Decimal("90"), Decimal("91"), Decimal("88"), Decimal("90"), Decimal("10")),)
    model = ExecutionModel(version="exec@v1")
    result = simulate(bars, (OrderIntent(0, "SELL", Decimal("1"), stop_price=Decimal("95")),), model)
    assert result.events[0].price == Decimal("90")
