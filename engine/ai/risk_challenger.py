"""Risk Challenger advisory-only contract.

This is not RiskGate and cannot approve executable orders.
"""
from __future__ import annotations

from typing import Any, Mapping

from .contracts import AIAvailability, RiskChallenge


class RiskChallenger:
    def challenge(
        self,
        *,
        candidate: Mapping[str, Any] | None,
        evidence_refs: tuple[str, ...] = (),
        authority_state: str = "UNKNOWN",
    ) -> RiskChallenge:
        try:
            state = AIAvailability(authority_state)
        except ValueError:
            state = AIAvailability.UNKNOWN
        if state is not AIAvailability.AVAILABLE or not candidate:
            return RiskChallenge(
                state=state if state is not AIAvailability.AVAILABLE else AIAvailability.UNAVAILABLE,
                concerns=("Authoritative candidate evidence unavailable.",),
                evidence_refs=evidence_refs,
                disposition="BLOCK_RESEARCH_PROMOTION",
            )
        concerns: list[str] = []
        if not candidate.get("evidence_ref") and not evidence_refs:
            concerns.append("Candidate lacks provenance evidence.")
        if candidate.get("freshness") in {"STALE", "UNKNOWN", "UNAVAILABLE"}:
            concerns.append("Candidate input freshness is not AVAILABLE.")
        return RiskChallenge(
            state=AIAvailability.AVAILABLE,
            concerns=tuple(concerns),
            evidence_refs=evidence_refs,
            disposition="CHALLENGE_RECORDED" if concerns else "NO_ADDITIONAL_CONCERN",
        )
