from datetime import date
from decimal import Decimal

import pytest

from engine.backtest.v2.options import OptionModel, OptionsError, price_option_fill
from engine.data.instruments import InstrumentTerms


def _terms():
    return InstrumentTerms("nifty-ce", "NSE", "NIFTY-CE", "options", date(2026, 1, 1),
                           date(2026, 1, 29), 65, Decimal("0.05"), "NIFTY",
                           date(2026, 1, 29), 22000, "CE", "monthly")


def test_as_of_lot_and_expiry_are_enforced():
    model = OptionModel("option@v1", Decimal("0.1"), Decimal("0.2"),
                        Decimal("0.01"), Decimal("0.02"))
    result = price_option_fill(_terms(), date(2026, 1, 15), Decimal("100"), 1, model)
    assert result.quantity == Decimal(65)
    assert result.premium > 0
    assert result.promotion_eligible is False
    with pytest.raises(OptionsError):
        price_option_fill(_terms(), date(2026, 2, 1), Decimal("100"), 1, model)
