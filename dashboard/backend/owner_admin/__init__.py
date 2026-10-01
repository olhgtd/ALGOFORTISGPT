"""Owner/Admin authoritative governance plane.

This package contains presentation/read-model and governed mutation boundaries.
It must not acquire trading, broker mutation, Live-arm, or RiskGate authority.
"""

from .contracts import AuthorityEnvelope, AuthorityState, authority_state_from_source

__all__ = ["AuthorityEnvelope", "AuthorityState", "authority_state_from_source"]
