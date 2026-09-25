"""Freshness gate for continuous AlgoFortis Laya market intelligence."""

from __future__ import annotations

from datetime import datetime, timedelta

from engine.ai.laya.contracts import MarketInsight, MarketIntelligenceRequest
from engine.ai.laya.router import LayaRouter


class LayaMarketError(ValueError):
    """Raised when market intelligence input is unsafe or stale."""


class MarketIntelligenceService:
    """Validate market freshness before allowing one Laya inference."""

    def __init__(self, *, router: LayaRouter, max_input_age_seconds: int) -> None:
        if not isinstance(router, LayaRouter):
            raise TypeError("router must be LayaRouter")
        if (
            isinstance(max_input_age_seconds, bool)
            or not isinstance(max_input_age_seconds, int)
            or max_input_age_seconds <= 0
        ):
            raise LayaMarketError("max_input_age_seconds must be positive")
        self._router = router
        self._max_input_age = timedelta(seconds=max_input_age_seconds)

    def analyze(
        self,
        request: MarketIntelligenceRequest,
        *,
        observed_at: datetime,
    ) -> MarketInsight:
        if not isinstance(request, MarketIntelligenceRequest):
            raise TypeError("request must be MarketIntelligenceRequest")
        if not isinstance(observed_at, datetime):
            raise LayaMarketError("observed_at must be a datetime")
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise LayaMarketError("observed_at must be timezone-aware")

        future_skew = request.event_timestamp - observed_at
        if future_skew > timedelta(seconds=5):
            raise LayaMarketError("market input is from the future")

        age = observed_at - request.event_timestamp
        if age > self._max_input_age:
            raise LayaMarketError("market input is stale")

        return self._router.route_market(request)


__all__ = ["LayaMarketError", "MarketIntelligenceService"]
