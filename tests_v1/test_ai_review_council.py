from __future__ import annotations

from engine.ai.v2.review_council import (
    ReviewCouncil,
    ReviewDisposition,
    ReviewOpinion,
)


def opinion(
    participant: str,
    provider: str,
    model: str,
    disposition: ReviewDisposition,
    *,
    foundation: str = "",
    sources: tuple[str, ...] = (),
) -> ReviewOpinion:
    return ReviewOpinion(
        participant_id=participant,
        provider_id=provider,
        model_id=model,
        foundation_model_id=foundation,
        disposition=disposition,
        evidence_refs=(f"e:{participant}",),
        source_refs=sources,
    )


def test_zero_participants_is_valid_degraded_evidence_not_failure() -> None:
    result = ReviewCouncil.aggregate(())
    assert result.participant_count == 0
    assert result.correlated_model_flag is False
    assert result.summary_disposition is ReviewDisposition.INSUFFICIENT_DATA


def test_one_provider_is_supported_without_fake_independence() -> None:
    result = ReviewCouncil.aggregate(
        (opinion("a1", "p1", "m1", ReviewDisposition.CONFIRM),)
    )
    assert result.participant_count == 1
    assert result.independent_lineage_count == 1
    assert result.correlated_model_flag is False
    assert result.summary_disposition is ReviewDisposition.CONFIRM


def test_same_provider_model_repeated_roles_are_correlated() -> None:
    result = ReviewCouncil.aggregate(
        (
            opinion("proposer", "p1", "m1", ReviewDisposition.CONFIRM),
            opinion("critic", "p1", "m1", ReviewDisposition.CONFIRM),
        )
    )
    assert result.participant_count == 2
    assert result.independent_lineage_count == 1
    assert result.correlated_model_flag is True
    assert result.summary_disposition is ReviewDisposition.CAUTION


def test_same_foundation_or_same_sources_are_correlated() -> None:
    same_foundation = ReviewCouncil.aggregate(
        (
            opinion("a", "p1", "m1", ReviewDisposition.CONFIRM, foundation="f-base"),
            opinion("b", "p2", "m2", ReviewDisposition.CONFIRM, foundation="f-base"),
        )
    )
    assert same_foundation.correlated_model_flag is True

    same_source = ReviewCouncil.aggregate(
        (
            opinion("a", "p1", "m1", ReviewDisposition.CONFIRM, sources=("source:x",)),
            opinion("b", "p2", "m2", ReviewDisposition.CONFIRM, sources=("source:x",)),
        )
    )
    assert same_source.correlated_model_flag is True


def test_disagreement_is_preserved_and_not_majority_approved() -> None:
    result = ReviewCouncil.aggregate(
        (
            opinion("a", "p1", "m1", ReviewDisposition.CONFIRM),
            opinion("b", "p2", "m2", ReviewDisposition.CONFIRM),
            opinion("c", "p3", "m3", ReviewDisposition.CHALLENGE),
        )
    )
    assert result.disagreement is True
    assert result.summary_disposition is ReviewDisposition.CHALLENGE
    assert result.dispositions == (
        ReviewDisposition.CONFIRM,
        ReviewDisposition.CONFIRM,
        ReviewDisposition.CHALLENGE,
    )
