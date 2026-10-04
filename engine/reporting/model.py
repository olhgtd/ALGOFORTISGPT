"""Immutable, reporting-only Slice 13 public result contracts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Mapping
from engine.backtest.regime import EntryRegimeSnapshot, entry_regime_evidence_fingerprint
from engine.costs import CostAssessment, CostLegAssessment, cost_evidence_fingerprint


REPORT_SCHEMA_VERSION = "algofortis-report/v1"
REPORT_SCHEMA_VERSION_V2 = "algofortis-report/v2"
REPORT_SCHEMA_VERSION_V3 = "algofortis-report/v3"


class ResultKind(str, Enum):
    SUCCESS = "SUCCESS"
    CATEGORY_A = "CATEGORY_A"
    CATEGORY_B = "CATEGORY_B"
    CATEGORY_C = "CATEGORY_C"
    INVALID_FINALIZED = "INVALID_FINALIZED"


SUCCESS = ResultKind.SUCCESS
CATEGORY_A = ResultKind.CATEGORY_A
CATEGORY_B = ResultKind.CATEGORY_B
CATEGORY_C = ResultKind.CATEGORY_C
INVALID_FINALIZED = ResultKind.INVALID_FINALIZED


def _text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _identity(value: str, field: str) -> str:
    value = _text(value, field)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field} must be a lowercase SHA-256 hexadecimal identity")
    return value


def _safe_mapping(value: Mapping[str, object], field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) and key for key in value):
        raise TypeError(f"{field} must be a mapping with non-empty string keys")
    return MappingProxyType(dict(value))


@dataclass(frozen=True)
class ReportProvenance:
    """Operational, public-safe reporting provenance only."""

    attempt_id: str | None = None
    environment_conformance: str | None = None

    def __post_init__(self) -> None:
        if self.attempt_id is not None:
            object.__setattr__(self, "attempt_id", _text(self.attempt_id, "attempt_id"))
        if self.environment_conformance is not None:
            object.__setattr__(self, "environment_conformance", _text(self.environment_conformance, "environment_conformance"))


@dataclass(frozen=True)
class RandomizedAnalysisEvidence:
    """An upstream-produced randomized result projection; never an execution input."""

    kind: str
    root_seed: int | str
    seed_derivation_policy_identity: str
    result_evidence: Mapping[str, object]
    identity: str
    derived_seed: int | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _text(self.kind, "randomized kind"))
        if isinstance(self.root_seed, bool) or not isinstance(self.root_seed, (int, str)):
            raise TypeError("root_seed must be an int or exact textual representation")
        if self.derived_seed is not None and (isinstance(self.derived_seed, bool) or not isinstance(self.derived_seed, (int, str))):
            raise TypeError("derived_seed must be an int or exact textual representation")
        object.__setattr__(self, "seed_derivation_policy_identity", _identity(self.seed_derivation_policy_identity, "seed_derivation_policy_identity"))
        object.__setattr__(self, "identity", _identity(self.identity, "randomized identity"))
        object.__setattr__(self, "result_evidence", _safe_mapping(self.result_evidence, "result_evidence"))


@dataclass(frozen=True)
class RandomizedAnalysisCollectionEvidence:
    """Public-safe projection of upstream `RandomizedAnalysisCollection/v1`."""

    identity: str
    entries: tuple[Mapping[str, object], ...]
    schema_version: str = "RandomizedAnalysisCollection/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "RandomizedAnalysisCollection/v1":
            raise ValueError("unsupported randomized analysis collection schema")
        object.__setattr__(self, "identity", _identity(self.identity, "randomized collection identity"))
        values = tuple(self.entries)
        if not values or not all(isinstance(value, Mapping) for value in values):
            raise ValueError("randomized analysis collection requires entries")
        projected = tuple(_safe_mapping(value, "randomized collection entry") for value in values)
        required = {"analysis_kind", "scope_identity", "evidence_schema_version", "evidence_result_fingerprint"}
        if any(set(value) != required for value in projected):
            raise ValueError("randomized analysis collection entry has an invalid shape")
        ordered = tuple(sorted(projected, key=lambda value: (str(value["analysis_kind"]), str(value["scope_identity"]))))
        if len({(value["analysis_kind"], value["scope_identity"]) for value in ordered}) != len(ordered):
            raise ValueError("duplicate randomized analysis collection entry")
        object.__setattr__(self, "entries", ordered)


@dataclass(frozen=True)
class SuccessPayload:
    manifest_fingerprint: str
    result_fingerprint: str
    strategy_identity: Mapping[str, object]
    parameter_identity: str
    market_data_identity: str
    configuration_identity: str
    validation_identity: str
    trades: tuple[Mapping[str, object], ...]
    execution_evidence: tuple[Mapping[str, object], ...]
    portfolio_equity_evidence: tuple[Mapping[str, object], ...]
    costs: tuple[Mapping[str, object], ...]
    metrics: tuple[Mapping[str, object], ...]
    validation: Mapping[str, object]
    reproducibility: Mapping[str, object]
    randomized_analysis: RandomizedAnalysisEvidence | RandomizedAnalysisCollectionEvidence | None = None
    regime_evidence: tuple[Mapping[str, object], ...] = ()
    regime_evidence_fingerprint: str | None = None
    promotion_status: str | None = None
    promotable: bool | None = None
    promotion_gates: tuple[Mapping[str, object], ...] = ()
    promotion_evidence_fingerprint: str | None = None
    validation_collection_fingerprint: str | None = None

    def __post_init__(self) -> None:
        for field in ("manifest_fingerprint", "result_fingerprint", "parameter_identity", "market_data_identity", "configuration_identity", "validation_identity"):
            object.__setattr__(self, field, _identity(getattr(self, field), field))
        object.__setattr__(self, "strategy_identity", _safe_mapping(self.strategy_identity, "strategy_identity"))
        for field in ("trades", "execution_evidence", "portfolio_equity_evidence", "costs", "metrics", "regime_evidence"):
            values = tuple(getattr(self, field))
            if not all(isinstance(item, Mapping) for item in values):
                raise TypeError(f"{field} must contain mappings")
            object.__setattr__(self, field, tuple(_safe_mapping(item, field) for item in values))
        object.__setattr__(self, "validation", _safe_mapping(self.validation, "validation"))
        object.__setattr__(self, "reproducibility", _safe_mapping(self.reproducibility, "reproducibility"))
        if self.randomized_analysis is not None and not isinstance(self.randomized_analysis, (RandomizedAnalysisEvidence, RandomizedAnalysisCollectionEvidence)):
            raise TypeError("randomized_analysis must be RandomizedAnalysisEvidence")
        if self.regime_evidence_fingerprint is not None:
            object.__setattr__(self, "regime_evidence_fingerprint", _identity(self.regime_evidence_fingerprint, "regime_evidence_fingerprint"))
        if self.promotion_status is not None:
            object.__setattr__(self, "promotion_status", _text(self.promotion_status, "promotion_status"))
            if not isinstance(self.promotable, bool):
                raise TypeError("promotion projection requires bool promotable")
            object.__setattr__(self, "promotion_gates", tuple(_safe_mapping(value, "promotion gate") for value in self.promotion_gates))
            for field in ("promotion_evidence_fingerprint", "validation_collection_fingerprint"):
                object.__setattr__(self, field, _identity(getattr(self, field), field))
        elif any(value is not None for value in (self.promotable, self.promotion_evidence_fingerprint, self.validation_collection_fingerprint)) or self.promotion_gates:
            raise ValueError("promotion projection fields require promotion_status")


@dataclass(frozen=True)
class InvalidFinalizationPayload:
    manifest_fingerprint: str
    result_fingerprint: str
    promotion_status: str
    promotable: bool
    invalid_reasons: tuple[str, ...]
    promotion_evidence_fingerprint: str
    validation_collection_fingerprint: str
    promotion_gates: tuple[Mapping[str, object], ...] = ()

    def __post_init__(self) -> None:
        for field in ("manifest_fingerprint", "result_fingerprint", "promotion_evidence_fingerprint", "validation_collection_fingerprint"):
            object.__setattr__(self, field, _identity(getattr(self, field), field))
        if self.promotion_status != "INVALID" or self.promotable is not False:
            raise ValueError("invalid finalization payload requires INVALID and promotable=false")
        object.__setattr__(self, "invalid_reasons", tuple(sorted(set(_text(value, "invalid_reason") for value in self.invalid_reasons))))
        object.__setattr__(self, "promotion_gates", tuple(_safe_mapping(value, "promotion gate") for value in self.promotion_gates))


def success_payload_v2(
    payload: SuccessPayload,
    snapshots: tuple[EntryRegimeSnapshot, ...],
    reconciliation: Mapping[str, int],
) -> SuccessPayload:
    """Attach only persisted regime evidence to an existing success payload."""
    if not isinstance(payload, SuccessPayload):
        raise TypeError("payload must be SuccessPayload")
    values = tuple(sorted(snapshots, key=lambda value: value.entry_event_key))
    expected = {"TRENDING", "SIDEWAYS", "VOLATILE", "UNCLASSIFIED_WARMUP"}
    if set(reconciliation) != expected or sum(reconciliation.values()) != len(values):
        raise ValueError("regime reconciliation must contain and reconcile all frozen buckets")
    projected = tuple({
        "run_id": value.entry_event_key.run_id,
        "accounting_sequence": value.entry_event_key.accounting_sequence,
        "timestamp": value.fill_timestamp,
        "regime_status": value.regime_status.value,
        **({"regime": value.regime.value} if value.regime is not None else {}),
    } for value in values)
    return replace(payload, regime_evidence=projected,
                   regime_evidence_fingerprint=entry_regime_evidence_fingerprint(values),
                   reproducibility={**payload.reproducibility, "regime_reconciliation": dict(reconciliation)})


def success_payload_with_cost_evidence(
    payload: SuccessPayload,
    leg_assessments: tuple[CostLegAssessment, ...],
    completed_assessments: tuple[CostAssessment, ...],
) -> SuccessPayload:
    """Project upstream cost evidence only; no fee calculation occurs in reporting."""
    if not isinstance(payload, SuccessPayload):
        raise TypeError("payload must be SuccessPayload")
    legs = tuple(sorted(leg_assessments, key=lambda value: value.assessment_id))
    completed = tuple(sorted(completed_assessments, key=lambda value: value.assessment_id))
    identity = cost_evidence_fingerprint(legs, completed)
    projected_legs = tuple({
        "assessment_id": value.assessment_id,
        "run_id": value.leg_event_key.run_id,
        "accounting_sequence": value.leg_event_key.accounting_sequence,
        "schedule_id": value.schedule_reference.schedule_id,
        "schedule_version": value.schedule_reference.version,
        "schedule_fingerprint": value.schedule_reference.fingerprint,
        "execution_timestamp": value.execution_timestamp,
        "total_cost": value.total_cost,
        "currency": value.currency,
    } for value in legs)
    projected_completed = tuple({
        "assessment_id": value.assessment_id,
        "trade_id": value.trade_id,
        "gross_realized_pnl": value.gross_realized_pnl,
        "total_cost": value.total_cost,
        "net_realized_pnl": value.net_realized_pnl,
        "currency": value.currency,
    } for value in completed)
    return replace(
        payload,
        costs=(*payload.costs, *projected_legs, *projected_completed),
        reproducibility={**payload.reproducibility, "cost_evidence_fingerprint": identity},
    )


@dataclass(frozen=True)
class CategoryAPayload:
    manifest_fingerprint: str
    failure_result_fingerprint: str
    failure_schema: str
    code_type: str
    code_member: str
    stage: str
    policy_identity: str
    evidence: Mapping[str, object]
    reproducibility: Mapping[str, object]
    randomized_analysis: RandomizedAnalysisEvidence | RandomizedAnalysisCollectionEvidence | None = None

    def __post_init__(self) -> None:
        for field in ("manifest_fingerprint", "failure_result_fingerprint", "policy_identity"):
            object.__setattr__(self, field, _identity(getattr(self, field), field))
        for field in ("failure_schema", "code_type", "code_member", "stage"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        object.__setattr__(self, "evidence", _safe_mapping(self.evidence, "evidence"))
        reproducibility = _safe_mapping(self.reproducibility, "reproducibility")
        if "randomized_analysis" in reproducibility:
            raise ValueError("Category-A randomized_analysis is owned by the dedicated reporting field")
        object.__setattr__(self, "reproducibility", reproducibility)
        if self.randomized_analysis is not None and not isinstance(self.randomized_analysis, (RandomizedAnalysisEvidence, RandomizedAnalysisCollectionEvidence)):
            raise TypeError("randomized_analysis must be RandomizedAnalysisEvidence")


@dataclass(frozen=True)
class CategoryBPayload:
    pre_manifest_evidence: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "pre_manifest_evidence", _safe_mapping(self.pre_manifest_evidence, "pre_manifest_evidence"))


@dataclass(frozen=True)
class CategoryCPayload:
    operational_class: str
    manifest_fingerprint: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "operational_class", _text(self.operational_class, "operational_class"))
        if self.manifest_fingerprint is not None:
            object.__setattr__(self, "manifest_fingerprint", _identity(self.manifest_fingerprint, "manifest_fingerprint"))


Payload = SuccessPayload | InvalidFinalizationPayload | CategoryAPayload | CategoryBPayload | CategoryCPayload


@dataclass(frozen=True)
class StructuredBacktestResult:
    """The exact v1 report envelope; it is never replay input or proof."""

    schema_version: str
    result_kind: ResultKind
    report_generated_at: datetime
    provenance: ReportProvenance
    payload: Payload

    def __post_init__(self) -> None:
        if self.schema_version not in {REPORT_SCHEMA_VERSION, REPORT_SCHEMA_VERSION_V2, REPORT_SCHEMA_VERSION_V3}:
            raise ValueError("unknown reporting schema_version")
        if not isinstance(self.result_kind, ResultKind):
            object.__setattr__(self, "result_kind", ResultKind(self.result_kind))
        if self.report_generated_at.tzinfo is None or self.report_generated_at.utcoffset() is None:
            raise ValueError("report_generated_at must be timezone-aware")
        if not isinstance(self.provenance, ReportProvenance):
            raise TypeError("provenance must be ReportProvenance")
        expected = {
            ResultKind.SUCCESS: SuccessPayload,
            ResultKind.INVALID_FINALIZED: InvalidFinalizationPayload,
            ResultKind.CATEGORY_A: CategoryAPayload,
            ResultKind.CATEGORY_B: CategoryBPayload,
            ResultKind.CATEGORY_C: CategoryCPayload,
        }[self.result_kind]
        if not isinstance(self.payload, expected):
            raise TypeError("result_kind and payload variant must agree exactly")
        if self.result_kind is ResultKind.INVALID_FINALIZED and self.schema_version != REPORT_SCHEMA_VERSION_V3:
            raise ValueError("invalid finalized results require algofortis-report/v3")
        if self.schema_version == REPORT_SCHEMA_VERSION_V2 and self.result_kind is ResultKind.SUCCESS:
            if self.payload.regime_evidence_fingerprint is None:
                raise ValueError("algofortis-report/v2 success requires regime_evidence_fingerprint")
        if self.schema_version == REPORT_SCHEMA_VERSION_V3 and self.result_kind is ResultKind.SUCCESS:
            if self.payload.promotion_status is None:
                raise ValueError("algofortis-report/v3 success requires typed promotion projection")
