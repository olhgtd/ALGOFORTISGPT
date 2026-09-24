from datetime import datetime, timezone
from decimal import Decimal

import pytest

from engine.backtest.v2.contracts import Bar, ExecutionModel, V2Error
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
