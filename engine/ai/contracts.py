"""Typed contracts for the AlgoFortis AI research/shadow plane."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class AgentRole(str, Enum):
    PRIME = "PRIME"
    LAYA = "LAYA"
    RESEARCH = "RESEARCH"
    RISK_CHALLENGER = "RISK_CHALLENGER"


class AIAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"


class AIJobScope(str, Enum):
    RESEARCH = "RESEARCH"
    SHADOW = "SHADOW"


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
    """Research-only Laya observation; never an executable order command."""

    state: AIAvailability
    regime: str | None
    context: Mapping[str, Any]
    evidence_refs: tuple[str, ...]
    research_disposition: str


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
