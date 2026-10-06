"""AlgoFortis AI intelligence control-plane contracts.

This package has no broker mutation, Live arm, RiskGate approval, account, or
billing authority. Prime owns orchestration; Laya is market intelligence only.
"""
from .contracts import (
    AgentRole,
    AIAvailability,
    AIJobScope,
    AIJobStatus,
    RoutingDecision,
)
from .evidence import AIEvidenceEnvelope, canonical_evidence, routing_evidence
from .orchestrator import AIUnavailable, PrimeOrchestrator
from .provider_registry import ProviderBinding, ProviderRegistryUnavailable, ProviderRegistryView

__all__ = [
    "AgentRole",
    "AIAvailability",
    "AIJobScope",
    "AIJobStatus",
    "RoutingDecision",
    "AIEvidenceEnvelope",
    "canonical_evidence",
    "routing_evidence",
    "ProviderBinding",
    "ProviderRegistryUnavailable",
    "ProviderRegistryView",
    "AIUnavailable",
    "PrimeOrchestrator",
]
