from __future__ import annotations

from datetime import datetime, timedelta, timezone

from engine.ai.v2.contracts import IntelligenceCandidate, TradeCandidateAction
from engine.ai.v2.review_council import ReviewDisposition, ReviewOpinion
from engine.ai.v2.orchestrator import StrategyDecisionIntelligence

NOW = datetime(2026, 10, 1, 9, 30, tzinfo=timezone.utc)


def _opinion(participant: str, provider: str, model: str, disposition: ReviewDisposition, foundation: str = "") -> ReviewOpinion:
    return ReviewOpinion(
        participant_id=participant,
        provider_id=provider,
        model_id=model,
        foundation_model_id=foundation,
        disposition=disposition,
        evidence_refs=(f"evidence:{participant}",),
        source_refs=("market:snapshot:1",),
    )


def _candidate() -> IntelligenceCandidate:
    return IntelligenceCandidate(
        candidate_id="intel-1",
        instrument_ref="NIFTY",
        action=TradeCandidateAction.BUY_CE,
        created_at=NOW,
        valid_until=NOW + timedelta(minutes=5),
        input_fingerprint="a" * 64,
        source_participants=("laya",),
        lineage_refs=("lineage:laya",),
        regime="TRENDING",
        entry_context_ref="entry:research-only",
        invalidation_ref="invalidate:research-only",
        supporting_evidence_refs=("evidence:laya",),
        conflicting_evidence_refs=(),
        policy_refs=("market-watch/v1",),
        schema_version="1.0.0",
    )


def test_strategy_only_fallback_does_not_block_when_no_intelligence_is_available() -> None:
    result = StrategyDecisionIntelligence().review_strategy("strategy-candidate-1", ())
    assert result.strategy_candidate_ref == "strategy-candidate-1"
    assert result.strategy_unblocked is True
    assert result.council.participant_count == 0
    assert result.council.summary_disposition is ReviewDisposition.INSUFFICIENT_DATA


def test_laya_only_and_multi_ai_reviews_are_supported() -> None:
    orchestrator = StrategyDecisionIntelligence()
    laya = orchestrator.review_strategy(
        "strategy-candidate-2",
        (_opinion("laya", "laya-local", "laya-model", ReviewDisposition.CONFIRM, "laya-foundation"),),
    )
    assert laya.council.participant_count == 1
    assert laya.strategy_unblocked is True

    multi = orchestrator.review_strategy(
        "strategy-candidate-3",
        (
            _opinion("reviewer-a", "provider-a", "model-a", ReviewDisposition.CONFIRM, "foundation-a"),
            _opinion("reviewer-b", "provider-b", "model-b", ReviewDisposition.CAUTION, "foundation-b"),
        ),
    )
    assert multi.council.participant_count == 2
    assert multi.council.disagreement is True


def test_one_ai_sequential_proposer_and_critic_is_flagged_correlated() -> None:
    result = StrategyDecisionIntelligence().review_strategy(
        "strategy-candidate-4",
        (
            _opinion("proposer", "provider-a", "same-model", ReviewDisposition.CONFIRM, "foundation-x"),
            _opinion("critic", "provider-a", "same-model", ReviewDisposition.CAUTION, "foundation-x"),
        ),
    )
    assert result.council.correlated_model_flag is True
    assert result.council.independent_lineage_count == 1


def test_independent_intelligence_candidate_remains_research_backtest_paper_only() -> None:
    decision = StrategyDecisionIntelligence().evaluate_independent_candidate(_candidate(), ())
    assert decision.candidate.candidate_id == "intel-1"
    assert decision.candidate.execution_scope == "RISK_GATED_CANDIDATE"
    assert decision.executable_authority is False
    assert not hasattr(decision, "approved_order")
