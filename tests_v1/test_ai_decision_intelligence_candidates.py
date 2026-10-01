from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from engine.ai.v2.contracts import (
    IntelligenceCandidate,
    TradeCandidateAction,
)
from engine.ai.v2.candidates import IntelligenceCandidateValidator

UTC = timezone.utc


def _candidate(**overrides):
    now = datetime(2026, 10, 1, 9, 30, tzinfo=UTC)
    data = dict(
        candidate_id="ic-1",
        instrument_ref="NSE:NIFTY:CE",
        action=TradeCandidateAction.BUY_CE,
        created_at=now,
        valid_until=now + timedelta(minutes=5),
        input_fingerprint="a" * 64,
        source_participants=("laya",),
        lineage_refs=("provider:p1/model:m1",),
        regime="UPTREND",
        entry_context_ref="entry-zone:paper-only",
        invalidation_ref="invalidate:regime-break",
        supporting_evidence_refs=("e1",),
        conflicting_evidence_refs=(),
        policy_refs=("market-watch/v3",),
        schema_version="1.0.0",
    )
    data.update(overrides)
    return IntelligenceCandidate(**data)


def test_intelligence_candidate_is_immutable_research_paper_evidence() -> None:
    candidate = _candidate()
    assert candidate.execution_scope == "RESEARCH_BACKTEST_PAPER_ONLY"
    assert candidate.source_participants == ("laya",)
    with pytest.raises(Exception):
        candidate.instrument_ref = "NSE:BANKNIFTY:CE"  # type: ignore[misc]


def test_intelligence_candidate_requires_ttl_and_structured_evidence() -> None:
    now = datetime(2026, 10, 1, 9, 30, tzinfo=UTC)
    with pytest.raises(ValueError):
        _candidate(valid_until=now)
    with pytest.raises(ValueError):
        _candidate(source_participants=())
    with pytest.raises(ValueError):
        _candidate(lineage_refs=())


def test_intelligence_candidate_validator_rejects_stale_and_scope_mismatch() -> None:
    now = datetime(2026, 10, 1, 9, 40, tzinfo=UTC)
    validator = IntelligenceCandidateValidator(
        clock=lambda: now,
        allowed_schema_versions=("1.0.0",),
        allowed_underlyings=("NIFTY", "BANKNIFTY", "SENSEX"),
    )
    stale = _candidate(valid_until=now - timedelta(seconds=1))
    result = validator.validate(stale)
    assert result.valid is False
    assert "STALE_CANDIDATE" in result.reasons

    fresh = _candidate(
        instrument_ref="NSE:OTHER:CE",
        created_at=now - timedelta(minutes=1),
        valid_until=now + timedelta(minutes=1),
    )
    result = validator.validate(fresh)
    assert result.valid is False
    assert "INSTRUMENT_OUT_OF_SCOPE" in result.reasons


def test_laya_only_and_one_provider_candidates_use_same_contract() -> None:
    laya = _candidate(source_participants=("laya",), lineage_refs=("laya:native",))
    one_ai = _candidate(
        candidate_id="ic-2",
        source_participants=("ai-reviewer-1",),
        lineage_refs=("provider:p1/model:m1",),
    )
    assert laya.execution_scope == one_ai.execution_scope
