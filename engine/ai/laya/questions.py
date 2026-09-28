"""Typed questions used by Laya for shadow-only market intelligence."""

from __future__ import annotations

from typing import Mapping


def market_questions() -> Mapping[str, object]:
    """Return the fixed V1 market-intelligence question contract."""
    return {
        "regime": {
            "type": "choice",
            "instructions": "Classify the current market regime from the supplied normalized evidence.",
            "criteria": {
                "UPTREND": "higher-high/higher-low structure with positive directional persistence",
                "DOWNTREND": "lower-high/lower-low structure with negative directional persistence",
                "SIDEWAYS": "range-bound or mean-reverting structure without directional persistence",
                "UNCERTAIN": "evidence is mixed, stale-looking, insufficient, or contradictory",
            },
        },
        "bias": {
            "type": "choice",
            "instructions": "Classify directional bias without issuing an order instruction.",
            "criteria": {
                "BULLISH": "evidence supports upward directional bias",
                "BEARISH": "evidence supports downward directional bias",
                "NEUTRAL": "no material directional edge is supported",
                "UNCERTAIN": "direction cannot be supported from the supplied evidence",
            },
        },
        "volatility": {
            "type": "choice",
            "instructions": "Classify volatility state relative to the supplied market context.",
            "criteria": {
                "LOW": "compressed volatility relative to recent context",
                "NORMAL": "volatility is within normal recent context",
                "HIGH": "expanded volatility relative to recent context",
                "UNCERTAIN": "volatility cannot be supported from the supplied evidence",
            },
        },
        "opportunity": {
            "type": "choice",
            "instructions": "Classify only a research/shadow opportunity view. This is never an executable instruction.",
            "criteria": {
                "CE_CANDIDATE": "bullish evidence is strong enough to record a CE research candidate",
                "PE_CANDIDATE": "bearish evidence is strong enough to record a PE research candidate",
                "NO_TRADE": "evidence does not justify a research candidate or is uncertain",
            },
        },
    }


__all__ = ["market_questions"]
