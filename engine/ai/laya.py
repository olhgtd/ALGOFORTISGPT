"""Laya market-intelligence boundary from ADR-017.

Laya consumes already-approved market context and emits research observations.
It has no agent dispatch, provider/model selection, RiskGate, broker, order, or
Live-arm capability.
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

        # This native control-plane adapter intentionally does not invent a
        # trading signal.  A qualified model adapter may populate structured
        # regime/context later, still under research/shadow constraints.
        regime = market_context.get("regime")
        return MarketIntelligenceObservation(
            state=AIAvailability.AVAILABLE,
            regime=str(regime) if regime else None,
            context=dict(market_context),
            evidence_refs=evidence_refs,
            research_disposition="RESEARCH_ONLY",
        )
