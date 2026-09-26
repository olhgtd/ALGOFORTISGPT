from datetime import datetime, timezone
from decimal import Decimal

import pytest

from engine.orders.contracts_v2 import OrderIntent, OrderSource, RunMode
from engine.orders.model import OrderType
from engine.portfolio.model import (
    AccountSnapshot,
    InstrumentIdentity,
    PositionKey,
    PositionSnapshot,
)
from engine.portfolio.v2.contracts import PortfolioExposurePolicy, PortfolioRiskContext

_NOW = datetime(2026, 9, 27, 1, 30, tzinfo=timezone.utc)
_NIFTY = InstrumentIdentity("nse", "NIFTY", "index")
_BANK = InstrumentIdentity("nse", "BANKNIFTY", "index")


def _account() -> AccountSnapshot:
    p1 = PositionSnapshot(
        PositionKey("s1", "1", _NIFTY),
        Decimal("2"),
        Decimal("90"),
        Decimal("1"),
        Decimal("100"),
        _NOW,
        "5m",
        Decimal("0.05"),
        Decimal("0.01"),
    )
    p2 = PositionSnapshot(
        PositionKey("s2", "1", _NIFTY),
        Decimal("3"),
        Decimal("95"),
        Decimal("1"),
        Decimal("100"),
        _NOW,
        "5m",
        Decimal("0.05"),
        Decimal("0.01"),
    )
    p3 = PositionSnapshot(
        PositionKey("s1", "1", _BANK),
        Decimal("1"),
        Decimal("180"),
        Decimal("1"),
        Decimal("200"),
        _NOW,
        "5m",
        Decimal("0.05"),
        Decimal("0.01"),
    )
    positions = {p1.key: p1, p2.key: p2, p3.key: p3}
    return AccountSnapshot(
        account_id="acct",
        currency="INR",
        starting_capital=Decimal("5000"),
        cash=Decimal("4300"),
        realized_pnl=Decimal("0"),
        positions=positions,
        aggregate_exposure={_NIFTY: Decimal("500"), _BANK: Decimal("200")},
        as_of_timestamp=_NOW,
        monetary_quantum=Decimal("0.01"),
    )


def _context(account: AccountSnapshot | None = None) -> PortfolioRiskContext:
    return PortfolioRiskContext(
        account or _account(),
        Decimal("50"),
        Decimal("2"),
        Decimal("2"),
        Decimal("100"),
        "r1",
        _NOW,
    )


def _intent(
    *, strategy: str = "s1", instrument: InstrumentIdentity = _NIFTY, qty: Decimal = Decimal("2")
) -> OrderIntent:
    return OrderIntent(
        intent_id=f"intent-{strategy}-{instrument.instrument}",
        strategy_id=strategy,
        strategy_version="1",
        run_mode=RunMode.PAPER,
        instrument_ref=instrument,
        side="BUY",
        qty=qty,
        order_type=OrderType.MARKET,
        created_at=_NOW,
        valid_until=datetime(2026, 9, 27, 2, 30, tzinfo=timezone.utc),
        source=OrderSource.STRATEGY,
        provenance={"test": "phase7"},
    )


def _policy(
    *,
    total: str = "1000",
    instrument: str = "800",
    caps: dict[str, Decimal] | None = None,
) -> PortfolioExposurePolicy:
    return PortfolioExposurePolicy(
        "exposure",
        "v1",
        Decimal(total),
        Decimal(instrument),
        caps or {"s1": Decimal("700"), "s2": Decimal("600")},
    )


def test_current_exposure_aggregates_gross_by_strategy_and_instrument() -> None:
    from engine.portfolio.v2.exposure import build_exposure_snapshot

    snapshot = build_exposure_snapshot(_account())
    assert snapshot.total_exposure == Decimal("700")
    assert snapshot.by_strategy == {"s1": Decimal("400"), "s2": Decimal("300")}
    assert snapshot.by_instrument[_NIFTY] == Decimal("500")
    assert snapshot.by_instrument[_BANK] == Decimal("200")


def test_projected_exposure_accepts_when_all_caps_hold() -> None:
    from engine.portfolio.v2.exposure import build_exposure_snapshot, evaluate_projected_exposure

    decision = evaluate_projected_exposure(
        build_exposure_snapshot(_account()), _intent(), _context(), _policy()
    )
    assert decision.accepted is True
    assert decision.projected_trade_exposure == Decimal("200")
    assert decision.projected_total_exposure == Decimal("900")
    assert decision.projected_strategy_exposure == Decimal("600")
    assert decision.projected_instrument_exposure == Decimal("700")


def test_missing_strategy_cap_fails_closed() -> None:
    from engine.portfolio.v2.exposure import build_exposure_snapshot, evaluate_projected_exposure

    decision = evaluate_projected_exposure(
        build_exposure_snapshot(_account()),
        _intent(),
        _context(),
        _policy(caps={"s2": Decimal("600")}),
    )
    assert decision.accepted is False
    assert decision.reason == "STRATEGY_EXPOSURE_POLICY_UNAVAILABLE"


@pytest.mark.parametrize(
    ("policy", "reason"),
    [
        (_policy(total="800"), "TOTAL_EXPOSURE_EXCEEDED"),
        (
            _policy(caps={"s1": Decimal("550"), "s2": Decimal("600")}),
            "STRATEGY_EXPOSURE_EXCEEDED",
        ),
        (_policy(instrument="650"), "INSTRUMENT_EXPOSURE_EXCEEDED"),
    ],
)
def test_projected_cap_breaches_reject_with_stable_reason(
    policy: PortfolioExposurePolicy, reason: str
) -> None:
    from engine.portfolio.v2.exposure import build_exposure_snapshot, evaluate_projected_exposure

    decision = evaluate_projected_exposure(
        build_exposure_snapshot(_account()), _intent(), _context(), policy
    )
    assert decision.accepted is False
    assert decision.reason == reason


def test_missing_or_invalid_context_fails_closed() -> None:
    from engine.portfolio.v2.exposure import build_exposure_snapshot, evaluate_projected_exposure

    decision = evaluate_projected_exposure(
        build_exposure_snapshot(_account()), _intent(), None, _policy()
    )
    assert decision.accepted is False
    assert decision.reason == "PORTFOLIO_CONTEXT_UNAVAILABLE"
    with pytest.raises(ValueError):
        PortfolioRiskContext(
            _account(),
            Decimal("0"),
            Decimal("2"),
            Decimal("2"),
            Decimal("100"),
            "r1",
            _NOW,
        )
