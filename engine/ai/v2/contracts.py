from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import re


class AIContractError(ValueError):
    pass


_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AIContractError(f"{name} must be a non-empty string")
    return value.strip()


def _semver(value: str, name: str = "version") -> str:
    value = _text(value, name)
    if _SEMVER.fullmatch(value) is None:
        raise AIContractError(f"{name} must use semantic version MAJOR.MINOR.PATCH")
    return value


def _text_tuple(values: tuple[str, ...], name: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise AIContractError(f"{name} must be a tuple")
    out = tuple(_text(v, name) for v in values)
    if not allow_empty and not out:
        raise AIContractError(f"{name} must not be empty")
    if len(set(out)) != len(out):
        raise AIContractError(f"{name} must be unique")
    return out


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AIContractError(f"{name} must be timezone-aware")
    return value


class ProviderKind(str, Enum):
    LOCAL = "LOCAL"
    CLOUD = "CLOUD"


class DataClass(str, Enum):
    MARKET_RESEARCH = "MARKET_RESEARCH"
    DATASET_DERIVED = "DATASET_DERIVED"
    NEWS_RESEARCH = "NEWS_RESEARCH"
    STRATEGY_RESEARCH = "STRATEGY_RESEARCH"
    BROKER_CREDENTIAL = "BROKER_CREDENTIAL"
    BROKER_ACCOUNT_IDENTIFIER = "BROKER_ACCOUNT_IDENTIFIER"
    PERSONAL_DATA = "PERSONAL_DATA"
    RAW_TRADE_LOG = "RAW_TRADE_LOG"
    PRIVATE_KEY = "PRIVATE_KEY"
    UNKNOWN = "UNKNOWN"


class TradeCandidateAction(str, Enum):
    BUY_CE = "BUY_CE"
    BUY_PE = "BUY_PE"
    HOLD = "HOLD"


class CandidateValidationVerdict(str, Enum):
    VALID = "VALID"
    NO_TRADE = "NO_TRADE"


class NoTradeReason(str, Enum):
    MALFORMED = "MALFORMED"
    STALE_CANDIDATE = "STALE_CANDIDATE"
    POLICY_DENIED = "POLICY_DENIED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVENANCE_MISSING = "PROVENANCE_MISSING"
    STALE_INPUT_DATA = "STALE_INPUT_DATA"
    UNSUPPORTED_SCHEMA = "UNSUPPORTED_SCHEMA"
    INSTRUMENT_OUT_OF_SCOPE = "INSTRUMENT_OUT_OF_SCOPE"
    ACTION_INSTRUMENT_MISMATCH = "ACTION_INSTRUMENT_MISMATCH"
    HOLD_REQUESTED = "HOLD_REQUESTED"


@dataclass(frozen=True, slots=True)
class ProviderManifest:
    provider_id: str
    kind: ProviderKind
    version: str
    model_id: str
    supported_schemas: tuple[str, ...]
    accepted_data_classes: tuple[str, ...]
    retention_evidence_ref: str | None
    fallback_eligible: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_id", _text(self.provider_id, "provider_id"))
        if not isinstance(self.kind, ProviderKind):
            raise AIContractError("kind must be ProviderKind")
        object.__setattr__(self, "version", _semver(self.version))
        object.__setattr__(self, "model_id", _text(self.model_id, "model_id"))
        object.__setattr__(self, "supported_schemas", _text_tuple(self.supported_schemas, "supported_schemas"))
        object.__setattr__(self, "accepted_data_classes", _text_tuple(self.accepted_data_classes, "accepted_data_classes"))
        if self.retention_evidence_ref is not None:
            object.__setattr__(self, "retention_evidence_ref", _text(self.retention_evidence_ref, "retention_evidence_ref"))
        if not isinstance(self.fallback_eligible, bool):
            raise AIContractError("fallback_eligible must be bool")


@dataclass(frozen=True, slots=True)
class AIRequest:
    request_id: str
    schema_id: str
    data_classes: tuple[DataClass, ...]
    payload: object
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _text(self.request_id, "request_id"))
        object.__setattr__(self, "schema_id", _text(self.schema_id, "schema_id"))
        if not isinstance(self.data_classes, tuple) or not self.data_classes or any(not isinstance(x, DataClass) for x in self.data_classes):
            raise AIContractError("data_classes must be a non-empty tuple of DataClass")
        object.__setattr__(self, "provenance_refs", _text_tuple(self.provenance_refs, "provenance_refs"))


@dataclass(frozen=True, slots=True)
class AIResponse:
    request_id: str
    provider_id: str
    model_id: str
    schema_id: str
    payload: object
    provenance_refs: tuple[str, ...]
    output_fingerprint: str

    def __post_init__(self) -> None:
        for name in ("request_id", "provider_id", "model_id", "schema_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "provenance_refs", _text_tuple(self.provenance_refs, "provenance_refs"))
        fp = _text(self.output_fingerprint, "output_fingerprint").lower()
        if _HEX64.fullmatch(fp) is None:
            raise AIContractError("output_fingerprint must be lowercase sha256 hex")
        object.__setattr__(self, "output_fingerprint", fp)


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    healthy: bool
    evidence_ref: str
    observed_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.healthy, bool):
            raise AIContractError("healthy must be bool")
        object.__setattr__(self, "evidence_ref", _text(self.evidence_ref, "evidence_ref"))
        _aware(self.observed_at, "observed_at")


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    request_count: int
    concurrent_requests: int
    evidence_ref: str

    def __post_init__(self) -> None:
        for name in ("request_count", "concurrent_requests"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AIContractError(f"{name} must be a non-negative integer")
        object.__setattr__(self, "evidence_ref", _text(self.evidence_ref, "evidence_ref"))


@dataclass(frozen=True, slots=True)
class TradeCandidate:
    candidate_id: str
    context_ref: str
    instrument_ref: str
    action: TradeCandidateAction
    created_at: datetime
    valid_until: datetime
    input_fingerprint: str
    provider_id: str
    model_id: str
    agent_id: str
    schema_version: str
    provenance_refs: tuple[str, ...]
    rationale_refs: tuple[str, ...]
    input_data_valid_until: datetime | None = None

    def __post_init__(self) -> None:
        for name in ("candidate_id", "context_ref", "instrument_ref", "provider_id", "model_id", "agent_id", "schema_version"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.action, TradeCandidateAction):
            raise AIContractError("action must be TradeCandidateAction")
        created = _aware(self.created_at, "created_at")
        valid_until = _aware(self.valid_until, "valid_until")
        if valid_until <= created:
            raise AIContractError("valid_until must be after created_at")
        fp = _text(self.input_fingerprint, "input_fingerprint").lower()
        if _HEX64.fullmatch(fp) is None:
            raise AIContractError("input_fingerprint must be lowercase sha256 hex")
        object.__setattr__(self, "input_fingerprint", fp)
        object.__setattr__(self, "provenance_refs", _text_tuple(self.provenance_refs, "provenance_refs"))
        object.__setattr__(self, "rationale_refs", _text_tuple(self.rationale_refs, "rationale_refs", allow_empty=True))
        if self.input_data_valid_until is not None:
            _aware(self.input_data_valid_until, "input_data_valid_until")


@dataclass(frozen=True, slots=True)
class IntelligenceCandidate:
    """AI/Laya candidate source for the common risk-gated decision path."""

    candidate_id: str
    instrument_ref: str
    action: TradeCandidateAction
    created_at: datetime
    valid_until: datetime
    input_fingerprint: str
    source_participants: tuple[str, ...]
    lineage_refs: tuple[str, ...]
    regime: str
    entry_context_ref: str
    invalidation_ref: str
    supporting_evidence_refs: tuple[str, ...]
    conflicting_evidence_refs: tuple[str, ...]
    policy_refs: tuple[str, ...]
    schema_version: str
    execution_scope: str = "RISK_GATED_CANDIDATE"

    def __post_init__(self) -> None:
        for name in ("candidate_id", "instrument_ref", "regime", "entry_context_ref", "invalidation_ref"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.action, TradeCandidateAction):
            raise AIContractError("action must be TradeCandidateAction")
        created = _aware(self.created_at, "created_at")
        valid_until = _aware(self.valid_until, "valid_until")
        if valid_until <= created:
            raise AIContractError("valid_until must be after created_at")
        fp = _text(self.input_fingerprint, "input_fingerprint").lower()
        if _HEX64.fullmatch(fp) is None:
            raise AIContractError("input_fingerprint must be lowercase sha256 hex")
        object.__setattr__(self, "input_fingerprint", fp)
        object.__setattr__(self, "source_participants", _text_tuple(self.source_participants, "source_participants"))
        object.__setattr__(self, "lineage_refs", _text_tuple(self.lineage_refs, "lineage_refs"))
        object.__setattr__(self, "supporting_evidence_refs", _text_tuple(self.supporting_evidence_refs, "supporting_evidence_refs"))
        object.__setattr__(self, "conflicting_evidence_refs", _text_tuple(self.conflicting_evidence_refs, "conflicting_evidence_refs", allow_empty=True))
        object.__setattr__(self, "policy_refs", _text_tuple(self.policy_refs, "policy_refs"))
        object.__setattr__(self, "schema_version", _semver(self.schema_version, "schema_version"))
        if self.execution_scope != "RISK_GATED_CANDIDATE":
            raise AIContractError("IntelligenceCandidate execution_scope is fixed to the common risk-gated candidate path")


__all__ = [
    "AIContractError", "ProviderKind", "DataClass", "TradeCandidateAction",
    "CandidateValidationVerdict", "NoTradeReason", "ProviderManifest", "AIRequest",
    "AIResponse", "ProviderHealth", "ProviderUsage", "TradeCandidate", "IntelligenceCandidate"
]
