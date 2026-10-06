"""Typed contracts for the AlgoFortis AI decision-intelligence plane.

These contracts are limited to research, backtest and paper workflows. They do
not grant broker mutation, Live arming, ApprovedOrder or RiskGate authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class AgentRole(str, Enum):
    PRIME = "PRIME"
    LAYA = "LAYA"
    RESEARCH = "RESEARCH"
    RISK_CHALLENGER = "RISK_CHALLENGER"
    STRATEGY_CRITIC = "STRATEGY_CRITIC"
    VALIDATION = "VALIDATION"


class AIAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"


class AIJobScope(str, Enum):
    RESEARCH = "RESEARCH"
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"


class AIJobStatus(str, Enum):
    QUEUED = "QUEUED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    agent_id: str
    role: AgentRole
    provider_id: str
    model_id: str
    scope: AIJobScope
    evidence: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class MarketIntelligenceObservation:
    """Laya evidence for research/backtest/paper; never an executable order command."""

    state: AIAvailability
    regime: str | None
    context: Mapping[str, Any]
    evidence_refs: tuple[str, ...]
    research_disposition: str
    candidate_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResearchFinding:
    state: AIAvailability
    summary: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RiskChallenge:
    state: AIAvailability
    concerns: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    disposition: str
