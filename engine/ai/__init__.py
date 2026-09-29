"""AlgoFortis AI research/shadow control-plane contracts.

This package has no broker mutation, Live arm, RiskGate approval, account, or
billing authority.  Prime owns orchestration; Laya is market intelligence only.
"""
from .contracts import (
    AgentRole,
    AIAvailability,
    AIJobScope,
    AIJobStatus,
    RoutingDecision,
)
from .orchestrator import AIUnavailable, PrimeOrchestrator

__all__ = [
    "AgentRole",
    "AIAvailability",
    "AIJobScope",
    "AIJobStatus",
    "RoutingDecision",
    "AIUnavailable",
    "PrimeOrchestrator",
]
