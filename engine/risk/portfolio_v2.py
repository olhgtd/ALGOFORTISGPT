"""Portfolio-aware RiskEvaluator composition for Phase 7."""
from __future__ import annotations

from typing import Protocol

from engine.orders.contracts_v2 import OrderIntent, RiskDecisionKind
from engine.portfolio.v2.contracts import PortfolioExposurePolicy, PortfolioRiskContext
from engine.portfolio.v2.exposure import build_exposure_snapshot, evaluate_projected_exposure
from engine.risk.event_day_policy_v2 import EventRiskPolicy, evaluate_event_risk
from engine.risk.gate_v2 import RiskEvaluation


class PortfolioContextProvider(Protocol):
    def context_for(self, intent: OrderIntent) -> PortfolioRiskContext: ...


class PortfolioAwareRiskEvaluator:
    """Compose portfolio evidence into the existing RiskEvaluation contract."""

    def __init__(
        self,
        base_evaluator,
        context_provider,
        reservation_book,
        exposure_policy: PortfolioExposurePolicy,
        event_policy: EventRiskPolicy | None,
    ) -> None:
        if not callable(getattr(base_evaluator, "evaluate", None)):
            raise TypeError("base_evaluator must provide evaluate(intent)")
        if not callable(getattr(context_provider, "context_for", None)):
            raise TypeError("context_provider must provide context_for(intent)")
        if not callable(getattr(reservation_book, "get_active", None)):
            raise TypeError("reservation_book must provide get_active(reservation_id)")
        if not isinstance(exposure_policy, PortfolioExposurePolicy):
            raise TypeError("exposure_policy must be PortfolioExposurePolicy")
        self._base = base_evaluator
        self._contexts = context_provider
        self._reservations = reservation_book
        self._exposure_policy = exposure_policy
        self._event_policy = event_policy

    @staticmethod
    def _reject(base: RiskEvaluation, reason: str) -> RiskEvaluation:
        return RiskEvaluation.rejected(
            reason,
            risk_rule_version=base.risk_rule_version,
            limits_snapshot_id=base.limits_snapshot_id,
        )

    def evaluate(self, intent: OrderIntent) -> RiskEvaluation:
        if not isinstance(intent, OrderIntent):
            raise TypeError("intent must be OrderIntent")

        base = self._base.evaluate(intent)
        if not isinstance(base, RiskEvaluation):
            raise TypeError("base evaluator returned invalid RiskEvaluation")
        if base.decision is not RiskDecisionKind.APPROVED:
            return base

        try:
            context = self._contexts.context_for(intent)
        except Exception:
            return self._reject(base, "PORTFOLIO_CONTEXT_UNAVAILABLE")
        if not isinstance(context, PortfolioRiskContext):
            return self._reject(base, "PORTFOLIO_CONTEXT_UNAVAILABLE")

        try:
            reservation = self._reservations.get_active(context.reservation_id)
        except Exception:
            return self._reject(base, "CAPITAL_RESERVATION_UNAVAILABLE")
        if reservation is None:
            return self._reject(base, "CAPITAL_RESERVATION_UNAVAILABLE")
        if getattr(reservation, "strategy_id", None) != intent.strategy_id:
            return self._reject(base, "CAPITAL_RESERVATION_MISMATCH")
        amount = getattr(reservation, "amount", None)
        if amount is None or amount < context.required_capital:
            return self._reject(base, "CAPITAL_RESERVATION_INSUFFICIENT")

        book_policy = getattr(self._reservations, "policy", None)
        if book_policy is not None and (
            getattr(reservation, "policy_ref", None)
            != getattr(book_policy, "reference", None)
        ):
            return self._reject(base, "CAPITAL_RESERVATION_POLICY_MISMATCH")

        try:
            exposure = evaluate_projected_exposure(
                build_exposure_snapshot(context.account),
                intent,
                context,
                self._exposure_policy,
            )
        except Exception:
            return self._reject(base, "PORTFOLIO_EXPOSURE_UNAVAILABLE")
        if exposure.accepted is not True:
            return self._reject(base, exposure.reason)

        try:
            event = evaluate_event_risk(
                self._event_policy,
                at=context.evaluated_at,
                baseline_qty=context.baseline_qty,
                requested_qty=intent.qty,
            )
        except Exception:
            return self._reject(base, "EVENT_POLICY_UNAVAILABLE")
        if event.allowed is not True:
            return self._reject(base, event.reason)

        return base


__all__ = ["PortfolioAwareRiskEvaluator", "PortfolioContextProvider"]
