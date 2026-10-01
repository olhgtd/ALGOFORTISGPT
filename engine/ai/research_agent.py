"""Research Agent evidence-only contract."""
from __future__ import annotations

from typing import Any, Mapping

from .contracts import AIAvailability, ResearchFinding


class ResearchAgent:
    def summarize(
        self,
        *,
        evidence: Mapping[str, Any] | None,
        evidence_refs: tuple[str, ...] = (),
        authority_state: str = "UNKNOWN",
    ) -> ResearchFinding:
        try:
            state = AIAvailability(authority_state)
        except ValueError:
            state = AIAvailability.UNKNOWN
        if state is not AIAvailability.AVAILABLE or not evidence:
            return ResearchFinding(
                state=state if state is not AIAvailability.AVAILABLE else AIAvailability.UNAVAILABLE,
                summary="Research authority unavailable; no conclusion produced.",
                evidence_refs=evidence_refs,
            )
        return ResearchFinding(
            state=AIAvailability.AVAILABLE,
            summary="Authoritative research evidence is available for downstream analysis.",
            evidence_refs=evidence_refs,
        )
