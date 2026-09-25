"""Pure non-executable conversion of Laya market insights to opportunity candidates."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from engine.ai.laya.contracts import (
    DirectionalBias,
    MarketInsight,
    MarketIntelligenceRequest,
    OpportunityCandidate,
    OpportunityIntent,
)


class LayaOpportunityError(ValueError):
    """Raised when a Laya opportunity cannot be formed safely."""


class OpportunityEngine:
    """Create bounded candidate-only opportunities from validated Laya insights."""

    def __init__(self, *, min_confidence: Decimal) -> None:
        if (
            not isinstance(min_confidence, Decimal)
            or not min_confidence.is_finite()
            or not Decimal("0") <= min_confidence <= Decimal("1")
        ):
            raise LayaOpportunityError(
                "min_confidence must be a finite Decimal between 0 and 1"
            )
        self._min_confidence = min_confidence

    def from_insight(
        self,
        *,
        request: MarketIntelligenceRequest,
        insight: MarketInsight,
        validity_seconds: int,
    ) -> OpportunityCandidate | None:
        if not isinstance(request, MarketIntelligenceRequest):
            raise TypeError("request must be MarketIntelligenceRequest")
        if not isinstance(insight, MarketInsight):
            raise TypeError("insight must be MarketInsight")
        if insight.request_fingerprint != request.fingerprint:
            raise LayaOpportunityError("insight must be bound to request")
        if (
            isinstance(validity_seconds, bool)
            or not isinstance(validity_seconds, int)
            or validity_seconds <= 0
        ):
            raise LayaOpportunityError("validity_seconds must be positive")
        if insight.confidence < self._min_confidence:
            return None

        tags = set(insight.event_tags)
        if "REVERSAL_CANDIDATE" in tags:
            setup_type = "REVERSAL"
        elif "BREAKOUT_CANDIDATE" in tags:
            setup_type = "BREAKOUT"
        else:
            return None

        if insight.bias is DirectionalBias.BEARISH:
            intent = OpportunityIntent.PE_CANDIDATE
        elif insight.bias is DirectionalBias.BULLISH:
            intent = OpportunityIntent.CE_CANDIDATE
        else:
            return None

        return OpportunityCandidate.create(
            request=request,
            insight=insight,
            intent=intent,
            setup_type=setup_type,
            evidence_tags=insight.event_tags,
            valid_until=insight.produced_at + timedelta(seconds=validity_seconds),
        )


__all__ = ["LayaOpportunityError", "OpportunityEngine"]
