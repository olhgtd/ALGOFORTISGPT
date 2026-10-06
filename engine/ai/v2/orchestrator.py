from __future__ import annotations

from dataclasses import dataclass

from engine.ai.v2.agents import ChallengeDecision
from engine.ai.v2.candidates import CandidateValidationResult, TradeCandidateValidator
from engine.ai.v2.contracts import (
    CandidateValidationVerdict,
    IntelligenceCandidate,
    TradeCandidate,
    TradeCandidateAction,
)
from engine.ai.v2.review_council import ReviewCouncil, ReviewCouncilEvidence, ReviewDisposition, ReviewOpinion
from engine.reproducibility.codec import CanonicalCodec


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    candidate_validation: CandidateValidationResult
    challenge: ChallengeDecision | None
    effective_action: TradeCandidateAction
    reason_refs: tuple[str, ...]
    fingerprint: str


class IntelligenceCandidateOrchestrator:
    def __init__(self, validator: TradeCandidateValidator):
        if not isinstance(validator, TradeCandidateValidator):
            raise TypeError("TradeCandidateValidator required")
        self._validator = validator

    def evaluate(self, candidate: TradeCandidate, *, challenge: ChallengeDecision | None) -> OrchestrationResult:
        validation = self._validator.validate(candidate)
        reasons = [r.value for r in validation.reasons]
        if validation.verdict is not CandidateValidationVerdict.VALID:
            effective = TradeCandidateAction.HOLD
        elif challenge is ChallengeDecision.PASS:
            effective = candidate.action
        else:
            effective = TradeCandidateAction.HOLD
            reasons.append(
                "RISK_CHALLENGER_VETO"
                if challenge is ChallengeDecision.VETO
                else "UNRESOLVED_AGENT_DISAGREEMENT"
            )
        fp = CanonicalCodec.fingerprint(
            "algofortis-ai-orchestration/v1",
            (
                ("candidate_validation", validation.fingerprint),
                ("challenge", "" if challenge is None else challenge.value),
                ("effective_action", effective.value),
                ("reason_refs", tuple(sorted(set(reasons)))),
            ),
        )
        return OrchestrationResult(validation, challenge, effective, tuple(sorted(set(reasons))), fp)


@dataclass(frozen=True, slots=True)
class StrategyReviewEvidence:
    strategy_candidate_ref: str
    council: ReviewCouncilEvidence
    strategy_unblocked: bool
    executable_authority: bool = False


@dataclass(frozen=True, slots=True)
class IntelligenceCandidateDecision:
    candidate: IntelligenceCandidate
    council: ReviewCouncilEvidence
    executable_authority: bool = False


class StrategyDecisionIntelligence:
    """Strategy review and independent-candidate orchestration.

    This class has no broker or ApprovedOrder surface. AI/Laya can originate
    independent candidates, but deterministic downstream arbitration and
    RiskGateV2 remain the only route to execution approval.
    """

    def review_strategy(
        self,
        strategy_candidate_ref: str,
        opinions: tuple[ReviewOpinion, ...],
    ) -> StrategyReviewEvidence:
        ref = str(strategy_candidate_ref).strip()
        if not ref:
            raise ValueError("strategy_candidate_ref required")
        council = ReviewCouncil.aggregate(opinions)
        return StrategyReviewEvidence(
            strategy_candidate_ref=ref,
            council=council,
            strategy_unblocked=council.summary_disposition is not ReviewDisposition.REJECT_FOR_RESEARCH,
            executable_authority=False,
        )

    def evaluate_independent_candidate(
        self,
        candidate: IntelligenceCandidate,
        opinions: tuple[ReviewOpinion, ...],
    ) -> IntelligenceCandidateDecision:
        if not isinstance(candidate, IntelligenceCandidate):
            raise TypeError("candidate must be IntelligenceCandidate")
        if candidate.execution_scope != "RISK_GATED_CANDIDATE":
            raise ValueError("independent intelligence candidate scope is not permitted")
        return IntelligenceCandidateDecision(
            candidate=candidate,
            council=ReviewCouncil.aggregate(opinions),
            executable_authority=False,
        )


__all__ = [
    "IntelligenceCandidateDecision",
    "OrchestrationResult",
    "IntelligenceCandidateOrchestrator",
    "StrategyDecisionIntelligence",
    "StrategyReviewEvidence",
]
