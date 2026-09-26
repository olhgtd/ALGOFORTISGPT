from datetime import datetime, timezone
from decimal import Decimal

import pytest

from engine.portfolio.model import AccountSnapshot, InstrumentIdentity, PositionKey, PositionSnapshot
from engine.portfolio.v2.contracts import RealizedPnlRecord

_NOW = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
_NIFTY = InstrumentIdentity("nse", "NIFTY", "index")
_BANK = InstrumentIdentity("nse", "BANKNIFTY", "index")


def _position(strategy: str, identity: InstrumentIdentity, *, qty: str, entry: str, mark: str) -> PositionSnapshot:
    return PositionSnapshot(
        PositionKey(strategy, "1", identity),
        Decimal(qty),
        Decimal(entry),
        Decimal("1"),
        Decimal(mark),
        _NOW,
        "5m",
        Decimal("0.05"),
        Decimal("0.01"),
    )


def _account(*, realized: str = "30") -> AccountSnapshot:
    p1 = _position("s1", _NIFTY, qty="1", entry="90", mark="100")
    p2 = _position("s1", _BANK, qty="1", entry="205", mark="200")
    p3 = _position("s2", _NIFTY, qty="3", entry="93.33333333333333333333333333", mark="100")
    return AccountSnapshot(
        account_id="acct",
        currency="INR",
        starting_capital=Decimal("5000"),
        cash=Decimal("4400"),
        realized_pnl=Decimal(realized),
        positions={p1.key: p1, p2.key: p2, p3.key: p3},
        aggregate_exposure={_NIFTY: Decimal("400"), _BANK: Decimal("200")},
        as_of_timestamp=_NOW,
        monetary_quantum=Decimal("0.01"),
    )


def _records() -> tuple[RealizedPnlRecord, ...]:
    return (
        RealizedPnlRecord("s1", Decimal("10"), "realized-1"),
        RealizedPnlRecord("s2", Decimal("20"), "realized-2"),
    )


def test_marked_exposure_and_unrealized_group_exactly_by_strategy() -> None:
    from engine.portfolio.v2.attribution import build_attribution

    report = build_attribution(_account(), _records())
    assert report.by_strategy["s1"].marked_exposure == Decimal("300")
    assert report.by_strategy["s1"].unrealized_pnl == Decimal("5.00")
    assert report.by_strategy["s1"].open_position_count == 2
    assert report.by_strategy["s2"].marked_exposure == Decimal("300")
    assert report.total_unrealized_pnl == _account().unrealized_pnl


def test_realized_records_aggregate_by_strategy() -> None:
    from engine.portfolio.v2.attribution import build_attribution

    report = build_attribution(_account(), _records())
    assert report.by_strategy["s1"].realized_pnl == Decimal("10")
    assert report.by_strategy["s2"].realized_pnl == Decimal("20")
    assert report.total_realized_pnl == Decimal("30")


def test_realized_record_total_mismatch_fails_closed() -> None:
    from engine.portfolio.v2.attribution import build_attribution

    with pytest.raises(ValueError, match="realized attribution"):
        build_attribution(_account(realized="31"), _records())


def test_report_totals_reconcile_exactly_to_account() -> None:
    from engine.portfolio.v2.attribution import build_attribution

    report = build_attribution(_account(), _records())
    assert report.total_marked_exposure == Decimal("600")
    assert sum(
        (row.marked_exposure for row in report.by_strategy.values()), Decimal("0")
    ) == report.total_marked_exposure
    assert sum(
        (row.unrealized_pnl for row in report.by_strategy.values()), Decimal("0")
    ) == report.total_unrealized_pnl
    assert sum(
        (row.realized_pnl for row in report.by_strategy.values()), Decimal("0")
    ) == report.total_realized_pnl


def test_realized_only_strategy_is_not_silently_dropped() -> None:
    from engine.portfolio.v2.attribution import build_attribution

    records = (
        RealizedPnlRecord("s1", Decimal("10"), "realized-1"),
        RealizedPnlRecord("s2", Decimal("10"), "realized-2"),
        RealizedPnlRecord("closed", Decimal("10"), "realized-3"),
    )
    report = build_attribution(_account(), records)
    assert report.by_strategy["closed"].open_position_count == 0
    assert report.by_strategy["closed"].realized_pnl == Decimal("10")
