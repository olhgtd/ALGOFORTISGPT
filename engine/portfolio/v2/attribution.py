"""Exact strategy-level P&L and exposure attribution for Phase 7."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from engine.portfolio.model import AccountSnapshot
from engine.portfolio.v2.contracts import RealizedPnlRecord


@dataclass(frozen=True, slots=True)
class StrategyAttribution:
    strategy_id: str
    marked_exposure: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    open_position_count: int


@dataclass(frozen=True, slots=True)
class PortfolioAttributionReport:
    by_strategy: Mapping[str, StrategyAttribution]
    total_marked_exposure: Decimal
    total_unrealized_pnl: Decimal
    total_realized_pnl: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "by_strategy", MappingProxyType(dict(self.by_strategy)))


def build_attribution(
    account: AccountSnapshot,
    realized_records: tuple[RealizedPnlRecord, ...],
) -> PortfolioAttributionReport:
    if not isinstance(account, AccountSnapshot):
        raise TypeError("account must be AccountSnapshot")
    if not isinstance(realized_records, tuple) or not all(
        isinstance(record, RealizedPnlRecord) for record in realized_records
    ):
        raise TypeError("realized_records must be a tuple of RealizedPnlRecord")

    realized_by_strategy: dict[str, Decimal] = {}
    for record in realized_records:
        realized_by_strategy[record.strategy_id] = (
            realized_by_strategy.get(record.strategy_id, Decimal("0"))
            + record.amount
        )
    realized_total = sum(realized_by_strategy.values(), Decimal("0"))
    if realized_total != account.realized_pnl:
        raise ValueError(
            "realized attribution total does not match AccountSnapshot.realized_pnl"
        )

    marked_by_strategy: dict[str, Decimal] = {}
    unrealized_by_strategy: dict[str, Decimal] = {}
    counts: dict[str, int] = {}
    for position in account.positions.values():
        strategy_id = position.key.strategy_id
        marked_by_strategy[strategy_id] = (
            marked_by_strategy.get(strategy_id, Decimal("0"))
            + position.marked_value
        )
        unrealized_by_strategy[strategy_id] = (
            unrealized_by_strategy.get(strategy_id, Decimal("0"))
            + position.unrealized_pnl
        )
        counts[strategy_id] = counts.get(strategy_id, 0) + 1

    all_strategies = set(marked_by_strategy) | set(realized_by_strategy)
    by_strategy = {
        strategy_id: StrategyAttribution(
            strategy_id=strategy_id,
            marked_exposure=marked_by_strategy.get(strategy_id, Decimal("0")),
            unrealized_pnl=unrealized_by_strategy.get(strategy_id, Decimal("0")),
            realized_pnl=realized_by_strategy.get(strategy_id, Decimal("0")),
            open_position_count=counts.get(strategy_id, 0),
        )
        for strategy_id in sorted(all_strategies)
    }

    total_marked = sum(marked_by_strategy.values(), Decimal("0"))
    total_unrealized = sum(unrealized_by_strategy.values(), Decimal("0"))
    if total_unrealized != account.unrealized_pnl:
        raise ValueError(
            "unrealized attribution total does not match AccountSnapshot.unrealized_pnl"
        )

    if sum(
        (row.marked_exposure for row in by_strategy.values()), Decimal("0")
    ) != total_marked:
        raise ValueError("marked exposure attribution does not reconcile")
    if sum(
        (row.realized_pnl for row in by_strategy.values()), Decimal("0")
    ) != realized_total:
        raise ValueError("realized attribution does not reconcile")
    if sum(
        (row.unrealized_pnl for row in by_strategy.values()), Decimal("0")
    ) != total_unrealized:
        raise ValueError("unrealized attribution does not reconcile")

    return PortfolioAttributionReport(
        by_strategy=by_strategy,
        total_marked_exposure=total_marked,
        total_unrealized_pnl=total_unrealized,
        total_realized_pnl=realized_total,
    )


__all__ = [
    "PortfolioAttributionReport",
    "StrategyAttribution",
    "build_attribution",
]
