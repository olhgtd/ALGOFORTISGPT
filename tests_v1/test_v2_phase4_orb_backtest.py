from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from engine.backtest.v2.contracts import Bar
from engine.backtest.v2.options import OptionModel
from engine.backtest.v2.orb_reference import ORBBacktestError, run_orb_option_backtest
from engine.data.instruments import InstrumentTerms
from engine.strategy.protective_policy_v2 import ProtectivePolicyV2
from strategies.orb.orb_v2 import ORBSignalSnapshot


def test_orb_uses_explicit_option_buy_policy_and_is_never_promotable():
    now = datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc)
    snapshot = ORBSignalSnapshot("NIFTY", now, Decimal("22011"),
                                  Decimal("22010"), Decimal("21990"))
    terms = InstrumentTerms("ce", "NSE", "NIFTY-CE", "options",
        date(2026, 1, 1), date(2026, 1, 29), 65, Decimal("0.05"),
        "NIFTY", date(2026, 1, 29), 22000, "CE", "monthly")
    bars = (Bar(now + timedelta(minutes=5), Decimal("100"), Decimal("101"), Decimal("99"), Decimal("100"), Decimal("100")),
            Bar(now + timedelta(minutes=10), Decimal("100"), Decimal("125"), Decimal("99"), Decimal("120"), Decimal("100")))
    policy = ProtectivePolicyV2("TEST_ONLY/orb@v1", Decimal("10"), Decimal("20"),
                                 Decimal("5"), True, Decimal("0.05"), "ROUND_HALF_UP")
    model = OptionModel("options@v1", Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"))
    result = run_orb_option_backtest(snapshot, terms=terms, option_bars=bars,
                                     policy=policy, option_model=model)
    assert result.action == "BUY_CE"
    assert result.exit_reason == "TARGET"
    assert result.promotion_eligible is False
    assert result == run_orb_option_backtest(snapshot, terms=terms, option_bars=bars,
                                              policy=policy, option_model=model)
    with pytest.raises(ORBBacktestError):
        run_orb_option_backtest(snapshot, terms=terms, option_bars=(),
                                policy=policy, option_model=model)
