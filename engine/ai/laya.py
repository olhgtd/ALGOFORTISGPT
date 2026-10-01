"""Laya market-intelligence boundary from ADR-017 and the 2026-10-01 amendment.

Laya consumes scheduler-authorized market context and emits market-intelligence
evidence. Decision-intelligence orchestration may use that evidence to form
research/backtest/paper IntelligenceCandidates. Laya itself has no provider
selection, RiskGate, broker, order, ApprovedOrder or Live-arm capability.
"""
from __future__ import annotations

from typing import Any, Mapping

from .contracts import AIAvailability, MarketIntelligenceObservation


class LayaMarketIntelligence:
    def observe(
        self,
        *,
        market_context: Mapping[str, Any] | None,
        evidence_refs: tuple[str, ...] = (),
        authority_state: str = "UNKNOWN",
    ) -> MarketIntelligenceObservation:
        try:
            state = AIAvailability(authority_state)
        except ValueError:
            state = AIAvailability.UNKNOWN

        if state is not AIAvailability.AVAILABLE or not market_context:
            return MarketIntelligenceObservation(
                state=state if state is not AIAvailability.AVAILABLE else AIAvailability.UNAVAILABLE,
                regime=None,
                context={},
                evidence_refs=evidence_refs,
                research_disposition="NO-TRADE",
            )

        regime = market_context.get("regime")
        return MarketIntelligenceObservation(
            state=AIAvailability.AVAILABLE,
            regime=str(regime) if regime else None,
            context=dict(market_context),
            evidence_refs=evidence_refs,
            research_disposition="DECISION_INTELLIGENCE_AVAILABLE",
        )
