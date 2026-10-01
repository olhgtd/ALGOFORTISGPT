"""Deterministic current and projected portfolio exposure for Phase 7."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from engine.orders.contracts_v2 import OrderIntent
from engine.portfolio.model import AccountSnapshot
from engine.portfolio.v2.contracts import (
    PortfolioExposurePolicy,
    PortfolioExposureSnapshot,
    PortfolioRiskContext,
)


@dataclass(frozen=True, slots=True)
class PortfolioExposureDecision:
    accepted: bool
    reason: str
    policy_ref: str
    projected_trade_exposure: Decimal
    projected_total_exposure: Decimal
    projected_strategy_exposure: Decimal
    projected_instrument_exposure: Decimal


def build_exposure_snapshot(account: AccountSnapshot) -> PortfolioExposureSnapshot:
    if not isinstance(account, AccountSnapshot):
        raise TypeError("account must be AccountSnapshot")
    total = Decimal("0")
    by_strategy: dict[str, Decimal] = {}
    by_instrument: dict[object, Decimal] = {}
    for position in account.positions.values():
        marked = position.marked_value
        if not isinstance(marked, Decimal) or not marked.is_finite() or marked < 0:
            raise ValueError(
                "position marked exposure must be finite non-negative Decimal"
            )
        total += marked
        strategy_id = position.key.strategy_id
        identity = position.key.identity
        by_strategy[strategy_id] = by_strategy.get(strategy_id, Decimal("0")) + marked
        by_instrument[identity] = by_instrument.get(identity, Decimal("0")) + marked
    return PortfolioExposureSnapshot(total, by_strategy, by_instrument)


def _decision(
    accepted: bool,
    reason: str,
    policy: PortfolioExposurePolicy,
    *,
    trade: Decimal = Decimal("0"),
    total: Decimal = Decimal("0"),
    strategy: Decimal = Decimal("0"),
    instrument: Decimal = Decimal("0"),
) -> PortfolioExposureDecision:
    return PortfolioExposureDecision(
        accepted,
        reason,
        policy.reference,
        trade,
        total,
        strategy,
        instrument,
    )


def evaluate_projected_exposure(
    snapshot: PortfolioExposureSnapshot,
    intent: OrderIntent,
    context: PortfolioRiskContext | None,
    policy: PortfolioExposurePolicy,
) -> PortfolioExposureDecision:
    if not isinstance(snapshot, PortfolioExposureSnapshot):
        raise TypeError("snapshot must be PortfolioExposureSnapshot")
    if not isinstance(intent, OrderIntent):
        raise TypeError("intent must be OrderIntent")
    if not isinstance(policy, PortfolioExposurePolicy):
        raise TypeError("policy must be PortfolioExposurePolicy")
    if context is None or not isinstance(context, PortfolioRiskContext):
        return _decision(False, "PORTFOLIO_CONTEXT_UNAVAILABLE", policy)

    strategy_cap = policy.strategy_exposure_caps.get(intent.strategy_id)
    if strategy_cap is None:
        return _decision(False, "STRATEGY_EXPOSURE_POLICY_UNAVAILABLE", policy)

    trade = context.reference_price * intent.qty * context.contract_multiplier
    if not trade.is_finite() or trade <= 0:
        return _decision(False, "PROJECTED_EXPOSURE_UNAVAILABLE", policy)

    projected_total = snapshot.total_exposure + trade
    projected_strategy = (
        snapshot.by_strategy.get(intent.strategy_id, Decimal("0")) + trade
    )
    projected_instrument = (
        snapshot.by_instrument.get(intent.instrument_ref, Decimal("0")) + trade
    )
    values = {
        "trade": trade,
        "total": projected_total,
        "strategy": projected_strategy,
        "instrument": projected_instrument,
    }
    if projected_total > policy.max_total_exposure:
        return _decision(False, "TOTAL_EXPOSURE_EXCEEDED", policy, **values)
    if projected_strategy > strategy_cap:
        return _decision(False, "STRATEGY_EXPOSURE_EXCEEDED", policy, **values)
    if projected_instrument > policy.max_instrument_exposure:
        return _decision(False, "INSTRUMENT_EXPOSURE_EXCEEDED", policy, **values)
    return _decision(True, "EXPOSURE_ACCEPTED", policy, **values)


__all__ = [
    "PortfolioExposureDecision",
    "build_exposure_snapshot",
    "evaluate_projected_exposure",
]
