from datetime import datetime, timezone
from decimal import Decimal

import pytest

from engine.backtest.v2.contracts import Bar, ExecutionModel, OrderIntent, V2Error
from engine.backtest.v2.execution import simulate_strategy


def test_strategy_sees_only_current_and_prior_bars():
    bars = tuple(Bar(datetime(2026, 1, day, tzinfo=timezone.utc),
                     Decimal("1"), Decimal("2"), Decimal("1"), Decimal("1"), Decimal("10"))
                 for day in (1, 2, 3))
    seen = []
    def strategy(history):
        seen.append(len(history))
        return ()
    simulate_strategy(bars, strategy, ExecutionModel(version="exec@v1"))
    assert seen == [1, 2, 3]
    def future(history):
        history[100]
        return ()
    with pytest.raises(V2Error):
        simulate_strategy(bars, future, ExecutionModel(version="exec@v1"))


def test_signal_using_current_close_cannot_fill_at_current_open():
    bars = (Bar(datetime(2026, 1, 1, tzinfo=timezone.utc), Decimal("1"), Decimal("2"), Decimal("1"), Decimal("2"), Decimal("10")),
            Bar(datetime(2026, 1, 2, tzinfo=timezone.utc), Decimal("3"), Decimal("3"), Decimal("3"), Decimal("3"), Decimal("10")))
    def strategy(history):
        return (OrderIntent(0, "BUY", Decimal("1")),) if len(history) == 1 else ()
    result = simulate_strategy(bars, strategy, ExecutionModel(version="exec@v1"))
    assert result.events[0].bar_index == 1
    assert result.events[0].price == Decimal("3")
