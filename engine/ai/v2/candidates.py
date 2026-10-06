from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from engine.ai.v2.contracts import (
    CandidateValidationVerdict,
    IntelligenceCandidate,
    NoTradeReason,
    TradeCandidate,
    TradeCandidateAction,
)
from engine.reproducibility.codec import CanonicalCodec


@dataclass(frozen=True, slots=True)
class CandidatePolicy:
    policy_id: str
    allowed_schema_versions: tuple[str, ...]
    allowed_underlyings: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            raise ValueError("policy_id required")
        if not self.allowed_schema_versions or not self.allowed_underlyings:
            raise ValueError("candidate policy scopes required")


@dataclass(frozen=True, slots=True)
class CandidateValidationResult:
    verdict: CandidateValidationVerdict
    reasons: tuple[NoTradeReason, ...]
    effective_action: TradeCandidateAction
    fingerprint: str


class TradeCandidateValidator:
    def __init__(self, clock: Callable[[], datetime], policy: CandidatePolicy) -> None:
        if not callable(clock) or not isinstance(policy, CandidatePolicy):
            raise TypeError("clock and CandidatePolicy required")
        self._clock = clock
        self._policy = policy

    def validate(self, candidate: TradeCandidate) -> CandidateValidationResult:
        reasons: list[NoTradeReason] = []
        now = self._clock()
        if not isinstance(candidate, TradeCandidate):
            reasons.append(NoTradeReason.MALFORMED)
        else:
            if now.tzinfo is None or now.utcoffset() is None:
                reasons.append(NoTradeReason.MALFORMED)
            else:
                if now >= candidate.valid_until:
                    reasons.append(NoTradeReason.STALE_CANDIDATE)
                if candidate.input_data_valid_until is None or now >= candidate.input_data_valid_until:
                    reasons.append(NoTradeReason.STALE_INPUT_DATA)
            if candidate.schema_version not in self._policy.allowed_schema_versions:
                reasons.append(NoTradeReason.UNSUPPORTED_SCHEMA)
            parts = candidate.instrument_ref.split(":")
            if len(parts) != 3 or parts[0] != "NSE" or parts[1] not in self._policy.allowed_underlyings or parts[2] not in ("CE", "PE"):
                reasons.append(NoTradeReason.INSTRUMENT_OUT_OF_SCOPE)
            elif candidate.action is TradeCandidateAction.BUY_CE and parts[2] != "CE":
                reasons.append(NoTradeReason.ACTION_INSTRUMENT_MISMATCH)
            elif candidate.action is TradeCandidateAction.BUY_PE and parts[2] != "PE":
                reasons.append(NoTradeReason.ACTION_INSTRUMENT_MISMATCH)
            if candidate.action is TradeCandidateAction.HOLD:
                reasons.append(NoTradeReason.HOLD_REQUESTED)
        normalized = tuple(sorted(set(reasons), key=lambda x: x.value))
        verdict = CandidateValidationVerdict.VALID if not normalized else CandidateValidationVerdict.NO_TRADE
        effective = candidate.action if verdict is CandidateValidationVerdict.VALID else TradeCandidateAction.HOLD
        fields = (
            ("policy_id", self._policy.policy_id),
            ("allowed_schema_versions", self._policy.allowed_schema_versions),
            ("allowed_underlyings", self._policy.allowed_underlyings),
            ("now", now),
            ("candidate_id", getattr(candidate, "candidate_id", "")),
            ("candidate_input_fingerprint", getattr(candidate, "input_fingerprint", "")),
            ("candidate_valid_until", getattr(candidate, "valid_until", None)),
            ("input_data_valid_until", getattr(candidate, "input_data_valid_until", None)),
            ("verdict", verdict.value),
            ("reasons", tuple(r.value for r in normalized)),
            ("effective_action", effective.value),
        )
        return CandidateValidationResult(
            verdict,
            normalized,
            effective,
            CanonicalCodec.fingerprint("algofortis-ai-candidate-validation/v1", fields),
        )


@dataclass(frozen=True, slots=True)
class IntelligenceCandidateValidationResult:
    valid: bool
    reasons: tuple[str, ...]
    fingerprint: str


class IntelligenceCandidateValidator:
    """Schema/scope/TTL validator for independent intelligence candidates."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime],
        allowed_schema_versions: tuple[str, ...],
        allowed_underlyings: tuple[str, ...],
    ) -> None:
        if not callable(clock):
            raise TypeError("clock must be callable")
        if not allowed_schema_versions or not allowed_underlyings:
            raise ValueError("allowed schema versions and underlyings required")
        self._clock = clock
        self._allowed_schema_versions = tuple(allowed_schema_versions)
        self._allowed_underlyings = tuple(allowed_underlyings)

    def validate(self, candidate: IntelligenceCandidate) -> IntelligenceCandidateValidationResult:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("clock must return timezone-aware datetime")
        reasons: list[str] = []
        if not isinstance(candidate, IntelligenceCandidate):
            reasons.append("MALFORMED")
        else:
            if now >= candidate.valid_until:
                reasons.append("STALE_CANDIDATE")
            if candidate.schema_version not in self._allowed_schema_versions:
                reasons.append("UNSUPPORTED_SCHEMA")
            parts = candidate.instrument_ref.split(":")
            if len(parts) != 3 or parts[0] != "NSE" or parts[1] not in self._allowed_underlyings or parts[2] not in ("CE", "PE"):
                reasons.append("INSTRUMENT_OUT_OF_SCOPE")
            elif candidate.action is TradeCandidateAction.BUY_CE and parts[2] != "CE":
                reasons.append("ACTION_INSTRUMENT_MISMATCH")
            elif candidate.action is TradeCandidateAction.BUY_PE and parts[2] != "PE":
                reasons.append("ACTION_INSTRUMENT_MISMATCH")
            if candidate.execution_scope != "RISK_GATED_CANDIDATE":
                reasons.append("EXECUTION_SCOPE_DENIED")
        normalized = tuple(sorted(set(reasons)))
        fp = CanonicalCodec.fingerprint(
            "algofortis-intelligence-candidate-validation/v1",
            (
                ("candidate_id", getattr(candidate, "candidate_id", "")),
                ("input_fingerprint", getattr(candidate, "input_fingerprint", "")),
                ("now", now),
                ("reasons", normalized),
            ),
        )
        return IntelligenceCandidateValidationResult(not normalized, normalized, fp)


__all__ = [
    "CandidatePolicy",
    "CandidateValidationResult",
    "TradeCandidateValidator",
    "IntelligenceCandidateValidationResult",
    "IntelligenceCandidateValidator",
]
