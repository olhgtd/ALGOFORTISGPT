"""Evidence-only strategy lifecycle without live execution capability."""
from __future__ import annotations

from dataclasses import dataclass, replace
import re


class LifecycleError(ValueError):
    pass


STAGES = ("DRAFT", "RESEARCH", "BACKTEST", "VALIDATION", "PAPER", "ELIGIBLE_FOR_LIVE")


@dataclass(frozen=True, slots=True)
class StrategyLifecycle:
    strategy_id: str
    strategy_version: str
    stage: str = "DRAFT"
    evidence: tuple[str, ...] = ()
    live_state: str = "READ_ONLY/DISARMED"

    def __post_init__(self) -> None:
        if not self.strategy_id or not self.strategy_version or self.stage not in (*STAGES, "DEACTIVATED"):
            raise LifecycleError("invalid strategy identity or stage")
        if self.live_state != "READ_ONLY/DISARMED":
            raise LifecycleError("Phase 4 never arms Live")

    def advance(self, stage: str, *, evidence_fingerprint: str) -> "StrategyLifecycle":
        if self.stage == "DEACTIVATED" or self.stage not in STAGES or STAGES.index(self.stage) + 1 >= len(STAGES) or stage != STAGES[STAGES.index(self.stage) + 1]:
            raise LifecycleError("only one forward evidence transition is allowed")
        if not isinstance(evidence_fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", evidence_fingerprint):
            raise LifecycleError("versioned evidence fingerprint required")
        return replace(self, stage=stage, evidence=self.evidence + (evidence_fingerprint,))

    def rollback(self) -> "StrategyLifecycle":
        if self.stage not in STAGES or self.stage == "DRAFT":
            raise LifecycleError("no stage to roll back")
        return replace(self, stage=STAGES[STAGES.index(self.stage) - 1], evidence=self.evidence[:-1])

    def deactivate(self) -> "StrategyLifecycle":
        return replace(self, stage="DEACTIVATED")
