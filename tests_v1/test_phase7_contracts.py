from datetime import datetime, timezone
from decimal import Decimal

import pytest

from engine.portfolio.model import AccountSnapshot
from engine.portfolio.v2.contracts import (
    PortfolioBudgetPolicy,
    PortfolioExposurePolicy,
    PortfolioRiskContext,
    RealizedPnlRecord,
)

NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)


def _account() -> AccountSnapshot:
    return AccountSnapshot(
        account_id="a",
        currency="INR",
        starting_capital=Decimal("100"),
        cash=Decimal("100"),
        realized_pnl=Decimal("0"),
        positions={},
        aggregate_exposure={},
        as_of_timestamp=NOW,
        monetary_quantum=Decimal("0.01"),
    )


def test_budget_hierarchy_rejects_user_over_owner_and_strategy_over_user() -> None:
    with pytest.raises(ValueError, match="user_budget"):
        PortfolioBudgetPolicy("p", "v1", Decimal("100"), "u", Decimal("101"), {"s": Decimal("50")})
    with pytest.raises(ValueError, match="strategy"):
        PortfolioBudgetPolicy("p", "v1", Decimal("100"), "u", Decimal("80"), {"s": Decimal("81")})


def test_budget_policy_is_explicit_decimal_and_missing_strategy_has_no_implicit_budget() -> None:
    policy = PortfolioBudgetPolicy("p", "v1", Decimal("100"), "u", Decimal("80"), {"s": Decimal("40")})
    assert policy.strategy_budget("s") == Decimal("40")
    assert policy.strategy_budget("missing") is None
    with pytest.raises(TypeError):
        PortfolioBudgetPolicy("p", "v1", 100.0, "u", Decimal("80"), {"s": Decimal("40")})


def test_risk_context_requires_positive_decimal_evidence_and_aware_time() -> None:
    context = PortfolioRiskContext(_account(), Decimal("10"), Decimal("1"), Decimal("2"), Decimal("20"), "res-1", NOW)
    assert context.required_capital == Decimal("20")
    with pytest.raises(ValueError):
        PortfolioRiskContext(_account(), Decimal("0"), Decimal("1"), Decimal("2"), Decimal("20"), "res", NOW)
    with pytest.raises(ValueError):
        PortfolioRiskContext(_account(), Decimal("10"), Decimal("1"), Decimal("2"), Decimal("20"), "res", datetime(2026, 9, 27))


def test_exposure_policy_requires_explicit_positive_caps_and_strategy_map() -> None:
    policy = PortfolioExposurePolicy("x", "v1", Decimal("100"), Decimal("50"), {"s": Decimal("60")})
    assert policy.reference == "x@v1"
    with pytest.raises(ValueError):
        PortfolioExposurePolicy("x", "v1", Decimal("0"), Decimal("50"), {"s": Decimal("60")})


def test_realized_pnl_record_accepts_signed_decimal_but_rejects_float() -> None:
    record = RealizedPnlRecord("s", Decimal("-2.5"), "ledger-1")
    assert record.amount == Decimal("-2.5")
    with pytest.raises(TypeError):
        RealizedPnlRecord("s", -2.5, "ledger")
