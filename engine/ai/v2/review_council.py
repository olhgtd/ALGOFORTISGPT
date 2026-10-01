from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ReviewDisposition(str, Enum):
    CONFIRM = "CONFIRM"
    CAUTION = "CAUTION"
    CHALLENGE = "CHALLENGE"
    REJECT_FOR_RESEARCH = "REJECT_FOR_RESEARCH"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True, slots=True)
class ReviewOpinion:
    participant_id: str
    provider_id: str
    model_id: str
    foundation_model_id: str
    disposition: ReviewDisposition
    evidence_refs: tuple[str, ...]
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("participant_id", "provider_id", "model_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} required")
            object.__setattr__(self, name, value.strip())
        if not isinstance(self.foundation_model_id, str):
            raise TypeError("foundation_model_id must be str")
        object.__setattr__(self, "foundation_model_id", self.foundation_model_id.strip())
        if not isinstance(self.disposition, ReviewDisposition):
            raise TypeError("disposition must be ReviewDisposition")
        for name in ("evidence_refs", "source_refs"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(not isinstance(v, str) or not v.strip() for v in values):
                raise ValueError(f"{name} must be a tuple of non-empty strings")
            object.__setattr__(self, name, tuple(v.strip() for v in values))

    @property
    def lineage_key(self) -> tuple[str, ...]:
        if self.foundation_model_id:
            return ("foundation", self.foundation_model_id)
        return ("provider-model", self.provider_id, self.model_id)


@dataclass(frozen=True, slots=True)
class ReviewCouncilEvidence:
    participant_count: int
    independent_lineage_count: int
    correlated_model_flag: bool
    disagreement: bool
    dispositions: tuple[ReviewDisposition, ...]
    summary_disposition: ReviewDisposition
    evidence_refs: tuple[str, ...]


class ReviewCouncil:
    """Evidence aggregator only; it has no order/risk/execution authority."""

    @staticmethod
    def aggregate(opinions: tuple[ReviewOpinion, ...]) -> ReviewCouncilEvidence:
        if not isinstance(opinions, tuple) or any(not isinstance(x, ReviewOpinion) for x in opinions):
            raise TypeError("opinions must be tuple[ReviewOpinion, ...]")
        if not opinions:
            return ReviewCouncilEvidence(
                participant_count=0,
                independent_lineage_count=0,
                correlated_model_flag=False,
                disagreement=False,
                dispositions=(),
                summary_disposition=ReviewDisposition.INSUFFICIENT_DATA,
                evidence_refs=(),
            )

        lineage_keys = tuple(opinion.lineage_key for opinion in opinions)
        correlated = len(set(lineage_keys)) != len(lineage_keys)

        seen_sources: set[str] = set()
        for opinion in opinions:
            sources = set(opinion.source_refs)
            if seen_sources.intersection(sources):
                correlated = True
            seen_sources.update(sources)

        dispositions = tuple(opinion.disposition for opinion in opinions)
        unique_dispositions = set(dispositions)
        disagreement = len(unique_dispositions) > 1

        if ReviewDisposition.REJECT_FOR_RESEARCH in unique_dispositions:
            summary = ReviewDisposition.REJECT_FOR_RESEARCH
        elif ReviewDisposition.CHALLENGE in unique_dispositions:
            summary = ReviewDisposition.CHALLENGE
        elif ReviewDisposition.INSUFFICIENT_DATA in unique_dispositions:
            summary = ReviewDisposition.INSUFFICIENT_DATA
        elif ReviewDisposition.CAUTION in unique_dispositions:
            summary = ReviewDisposition.CAUTION
        elif unique_dispositions == {ReviewDisposition.CONFIRM}:
            summary = ReviewDisposition.CAUTION if correlated else ReviewDisposition.CONFIRM
        else:
            summary = ReviewDisposition.CAUTION

        evidence_refs = tuple(sorted({ref for opinion in opinions for ref in opinion.evidence_refs}))
        return ReviewCouncilEvidence(
            participant_count=len(opinions),
            independent_lineage_count=len(set(lineage_keys)),
            correlated_model_flag=correlated,
            disagreement=disagreement,
            dispositions=dispositions,
            summary_disposition=summary,
            evidence_refs=evidence_refs,
        )


__all__ = [
    "ReviewCouncil",
    "ReviewCouncilEvidence",
    "ReviewDisposition",
    "ReviewOpinion",
]
