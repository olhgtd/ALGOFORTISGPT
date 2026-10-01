"""Append-only non-executable shadow evidence for Phase 8."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from engine.ai.v2.candidates import CandidateValidationResult
from engine.ai.v2.contracts import CandidateValidationVerdict, TradeCandidate, TradeCandidateAction
from engine.reproducibility.codec import CanonicalCodec


class ShadowPolicyError(ValueError):
    pass


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ShadowPolicyError(f"{name} must be a non-empty string")
    return value.strip()


def _aware(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ShadowPolicyError(f"{name} must be timezone-aware datetime")
    return value


class ShadowStatus(str, Enum):
    ACTIVE_RECOMMENDATION = "ACTIVE_RECOMMENDATION"
    NO_TRADE = "NO_TRADE"


@dataclass(frozen=True, slots=True)
class ShadowRecord:
    record_id: str
    candidate_id: str
    status: ShadowStatus
    effective_action: TradeCandidateAction
    candidate_input_fingerprint: str
    validation_fingerprint: str
    challenger_verdict: str
    policy_ref: str
    licensing_ref: str
    audit_ref: str
    provider_id: str
    provider_version: str
    model_id: str
    model_version: str
    agent_id: str
    agent_version: str
    observed_at: datetime
    valid_until: datetime
    provenance_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ShadowOutcome:
    outcome_id: str
    record_id: str
    outcome_ref: str
    metrics_ref: str
    observed_at: datetime


class ShadowLedger:
    def __init__(self) -> None:
        self._records: dict[str, ShadowRecord] = {}
        self._outcomes: dict[str, list[ShadowOutcome]] = {}

    def record(self, *, candidate: TradeCandidate, validation: CandidateValidationResult, challenger_verdict: str, policy_ref: str, licensing_ref: str, audit_ref: str, provider_version: str, model_version: str, agent_version: str, observed_at: datetime) -> ShadowRecord:
        if not isinstance(candidate, TradeCandidate):
            raise ShadowPolicyError("candidate must be TradeCandidate")
        if not isinstance(validation, CandidateValidationResult):
            raise ShadowPolicyError("validation must be CandidateValidationResult")
        if not candidate.provenance_refs:
            raise ShadowPolicyError("candidate provenance is required")
        challenger_verdict = _text(challenger_verdict, "challenger_verdict")
        policy_ref = _text(policy_ref, "policy_ref")
        licensing_ref = _text(licensing_ref, "licensing_ref")
        audit_ref = _text(audit_ref, "audit_ref")
        provider_version = _text(provider_version, "provider_version")
        model_version = _text(model_version, "model_version")
        agent_version = _text(agent_version, "agent_version")
        observed_at = _aware(observed_at, "observed_at")

        active = validation.verdict is CandidateValidationVerdict.VALID and validation.effective_action is not TradeCandidateAction.HOLD and observed_at < candidate.valid_until
        status = ShadowStatus.ACTIVE_RECOMMENDATION if active else ShadowStatus.NO_TRADE
        action = validation.effective_action if active else TradeCandidateAction.HOLD
        fields = (
            ("candidate_id", candidate.candidate_id), ("candidate_input_fingerprint", candidate.input_fingerprint),
            ("validation_fingerprint", validation.fingerprint), ("challenger_verdict", challenger_verdict),
            ("policy_ref", policy_ref), ("licensing_ref", licensing_ref), ("audit_ref", audit_ref),
            ("provider_id", candidate.provider_id), ("provider_version", provider_version),
            ("model_id", candidate.model_id), ("model_version", model_version),
            ("agent_id", candidate.agent_id), ("agent_version", agent_version),
            ("observed_at", observed_at), ("valid_until", candidate.valid_until),
            ("status", status.value), ("effective_action", action.value),
            ("provenance_refs", candidate.provenance_refs),
        )
        record_id = CanonicalCodec.fingerprint("algofortis-ai-shadow-record/v1", fields)
        record = ShadowRecord(record_id, candidate.candidate_id, status, action, candidate.input_fingerprint,
            validation.fingerprint, challenger_verdict, policy_ref, licensing_ref, audit_ref,
            candidate.provider_id, provider_version, candidate.model_id, model_version, candidate.agent_id,
            agent_version, observed_at, candidate.valid_until, candidate.provenance_refs)
        existing = self._records.get(record_id)
        if existing is not None and existing != record:
            raise ShadowPolicyError("shadow record identity collision")
        self._records[record_id] = record
        return record

    def get_record(self, record_id: str) -> ShadowRecord | None:
        return self._records.get(_text(record_id, "record_id"))

    def attach_outcome(self, *, record_id: str, outcome_ref: str, metrics_ref: str, observed_at: datetime) -> ShadowOutcome:
        record_id = _text(record_id, "record_id")
        if record_id not in self._records:
            raise ShadowPolicyError("unknown shadow record")
        outcome_ref = _text(outcome_ref, "outcome_ref")
        metrics_ref = _text(metrics_ref, "metrics_ref")
        observed_at = _aware(observed_at, "observed_at")
        outcome_id = CanonicalCodec.fingerprint("algofortis-ai-shadow-outcome/v1", (("record_id", record_id), ("outcome_ref", outcome_ref), ("metrics_ref", metrics_ref), ("observed_at", observed_at)))
        outcome = ShadowOutcome(outcome_id, record_id, outcome_ref, metrics_ref, observed_at)
        bucket = self._outcomes.setdefault(record_id, [])
        if outcome not in bucket:
            bucket.append(outcome)
        return outcome

    def outcomes(self, record_id: str) -> tuple[ShadowOutcome, ...]:
        return tuple(self._outcomes.get(_text(record_id, "record_id"), ()))


__all__ = ["ShadowPolicyError", "ShadowStatus", "ShadowRecord", "ShadowOutcome", "ShadowLedger"]
