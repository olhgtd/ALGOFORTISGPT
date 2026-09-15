"""D6 full-run replay comparison boundary; no cache or downstream replay engine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from engine.reproducibility.model import (InvalidFinalizedResult, ResultEvidenceFamily,
                                          ReproducibilityManifest, StructuredFailureResult,
                                          SuccessfulResult, ValidationEvidenceCollection)


class ReplayStatus(str, Enum):
    REPLAY_MATCH = "REPLAY_MATCH"
    REPLAY_MISMATCH = "REPLAY_MISMATCH"
    REPLAY_UNVERIFIABLE = "REPLAY_UNVERIFIABLE"


@dataclass(frozen=True)
class ReplayComparison:
    status: ReplayStatus
    differences: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", ReplayStatus(self.status))
        object.__setattr__(self, "differences", tuple(self.differences))


def verify_replay(
    original_manifest: ReproducibilityManifest | None,
    original_result: SuccessfulResult | InvalidFinalizedResult | StructuredFailureResult | None,
    replay_manifest: ReproducibilityManifest | None,
    replay_result: SuccessfulResult | InvalidFinalizedResult | StructuredFailureResult | None,
    *,
    full_run_reexecuted: bool,
) -> ReplayComparison:
    """Compare only an actual full re-execution; cache payloads are deliberately absent."""
    if not full_run_reexecuted or None in (original_manifest, original_result, replay_manifest, replay_result):
        return ReplayComparison(ReplayStatus.REPLAY_UNVERIFIABLE, ("required full-run evidence missing",))
    if original_manifest.manifest_fingerprint != replay_manifest.manifest_fingerprint:
        return ReplayComparison(ReplayStatus.REPLAY_MISMATCH, ("manifest",))
    if type(original_result) is not type(replay_result):
        return ReplayComparison(ReplayStatus.REPLAY_MISMATCH, ("result_kind",))
    if isinstance(original_result, (SuccessfulResult, InvalidFinalizedResult)):
        if original_result.result_fingerprint == replay_result.result_fingerprint:
            return ReplayComparison(ReplayStatus.REPLAY_MATCH)
        original = {item.family.value: item.identity for item in original_result.evidence}
        replayed = {item.family.value: item.identity for item in replay_result.evidence}
        differences = tuple(sorted(key for key in set(original) | set(replayed) if original.get(key) != replayed.get(key)))
        localized: tuple[str, ...] = ()
        if ResultEvidenceFamily.RANDOMIZED_ANALYSIS.value in differences:
            old_collection = original_result.randomized_analysis_collection
            new_collection = replay_result.randomized_analysis_collection
            if old_collection is not None and new_collection is not None:
                old_entries = {item.key: item.evidence_result_fingerprint for item in old_collection.entries}
                new_entries = {item.key: item.evidence_result_fingerprint for item in new_collection.entries}
                localized += tuple(
                    f"{ResultEvidenceFamily.RANDOMIZED_ANALYSIS.value}:{key[0]}"
                    for key in sorted(set(old_entries) | set(new_entries)) if old_entries.get(key) != new_entries.get(key)
                )
        if ResultEvidenceFamily.VALIDATION.value in differences:
            localized += _validation_localization(original_result, replay_result)
        return ReplayComparison(ReplayStatus.REPLAY_MISMATCH, differences + localized)
    if original_result.failure_result_fingerprint == replay_result.failure_result_fingerprint:
        return ReplayComparison(ReplayStatus.REPLAY_MATCH)
    return ReplayComparison(ReplayStatus.REPLAY_MISMATCH, ("structured_failure",))


def _validation_localization(
    original: SuccessfulResult | InvalidFinalizedResult,
    replayed: SuccessfulResult | InvalidFinalizedResult,
) -> tuple[str, ...]:
    """Bounded D6 detail for collection-mode VALIDATION; legacy remains top-level."""
    old = getattr(original, "validation_collection", None)
    new = getattr(replayed, "validation_collection", None)
    # Invalid results expose fingerprints but do not retain mutable typed collection;
    # typed collections are intentionally owned by the finalization evidence boundary.
    if not isinstance(old, ValidationEvidenceCollection) or not isinstance(new, ValidationEvidenceCollection):
        return ()
    old_entries = {entry.validation_analysis_kind: entry.evidence_result_fingerprint for entry in old.entries}
    new_entries = {entry.validation_analysis_kind: entry.evidence_result_fingerprint for entry in new.entries}
    return tuple(f"VALIDATION:{kind}" for kind in ("VALIDATION_OUTCOME", "PROMOTION_DECISION")
                 if old_entries.get(kind) != new_entries.get(kind))
