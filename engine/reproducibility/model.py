"""Immutable D2/D6/D7 manifest, result, and failure identities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from engine.reproducibility.codec import CanonicalCodec
from engine.reproducibility.dependencies import RuntimeDependencyClosure
from engine.reproducibility.market_data import MarketDataSnapshot
from engine.reproducibility.source import SourceIdentity
from engine.backtest.regime import EntryRegimeSnapshot, entry_regime_evidence_fingerprint
from engine.costs import CostAssessment, CostLegAssessment, cost_evidence_fingerprint


def _text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class RuntimeIdentity:
    implementation: str
    version: str
    timezone_calendar_identity: str

    def __post_init__(self) -> None:
        for name in ("implementation", "version", "timezone_calendar_identity"):
            object.__setattr__(self, name, _text(getattr(self, name), name))

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-runtime-identity/v1",
            (("implementation", self.implementation), ("version", self.version), ("timezone_calendar", self.timezone_calendar_identity)),
        )


@dataclass(frozen=True)
class RuntimeConfigurationSnapshot:
    """Complete Tier-1 runtime configuration, without UI/log/report settings.

    The ``risk`` field semantic contract is versioned: under
    ``config/v1`` it is free-form text; under ``config/v2`` it must bind the
    ACTIVE ``RiskPolicy.fingerprint`` for gate-enabled runs (or the literal
    ``"risk-deferred"`` for explicit non-gated legacy runs), so the v2
    fingerprint schema identity is distinct from v1 and no v1 free-form
    fingerprint can be compared against v2 authoritative evidence.

    Phase-4 Slice-1 (owner decision O1): ``config/v3`` adds the
    ``entry_validity`` field carrying the canonical RUN-LEVEL strategy-keyed
    ``PendingEntryValidityPolicy`` binding evidence (see
    ``engine.orders.validity.entry_validity_binding_fingerprint``).  The v1
    and v2 schema identities are UNCHANGED (v2 historical replay remains
    byte-stable; the new field participates only under v3).
    """

    version: str
    strategy: str
    risk: str
    execution: str
    broker: str
    slippage: str
    environment: str
    entry_validity: str | None = None

    def __post_init__(self) -> None:
        for name in ("version", "strategy", "risk", "execution", "broker", "slippage", "environment"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.version.endswith("/v3"):
            object.__setattr__(self, "entry_validity", _text(self.entry_validity, "entry_validity"))
        elif self.entry_validity is not None:
            raise ValueError("entry_validity requires RuntimeConfigurationSnapshot/v3")

    @property
    def fingerprint(self) -> str:
        if self.version.endswith("/v3"):
            return CanonicalCodec.fingerprint(
                "algofortis-runtime-configuration/v3",
                (("version", self.version), ("strategy", self.strategy), ("risk", self.risk),
                 ("execution", self.execution), ("broker", self.broker),
                 ("slippage", self.slippage), ("environment", self.environment),
                 ("entry_validity", self.entry_validity)),
            )
        return CanonicalCodec.fingerprint(
            "algofortis-runtime-configuration/v2" if self.version.endswith("/v2") else "algofortis-runtime-configuration/v1",
            (("version", self.version), ("strategy", self.strategy), ("risk", self.risk),
             ("execution", self.execution), ("broker", self.broker),
             ("slippage", self.slippage), ("environment", self.environment)),
        )


@dataclass(frozen=True)
class ReproducibilityManifest:
    """Tier-1 only logical-run identity.  No attempt/run/result identifier is accepted."""

    version: str
    source: SourceIdentity
    market_data: MarketDataSnapshot
    configuration: RuntimeConfigurationSnapshot
    runtime: RuntimeIdentity
    dependencies: RuntimeDependencyClosure
    execution_policy_identity: str
    cost_policy_identity: str
    validation_policy_identity: str
    randomness_policy_identity: str
    tier2_provenance: Mapping[str, str] | None = None
    regime_policy_identity: str | None = None

    def __post_init__(self) -> None:
        if not all((isinstance(self.source, SourceIdentity), isinstance(self.market_data, MarketDataSnapshot), isinstance(self.configuration, RuntimeConfigurationSnapshot), isinstance(self.runtime, RuntimeIdentity), isinstance(self.dependencies, RuntimeDependencyClosure))):
            raise TypeError("manifest requires frozen Tier-1 identity contracts")
        for name in ("version", "execution_policy_identity", "cost_policy_identity", "validation_policy_identity", "randomness_policy_identity"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        provenance = dict(self.tier2_provenance or {})
        if not all(isinstance(key, str) and isinstance(value, str) for key, value in provenance.items()):
            raise TypeError("Tier-2 provenance must be string metadata")
        object.__setattr__(self, "tier2_provenance", MappingProxyType(dict(sorted(provenance.items()))))
        if self.version.endswith("/v2"):
            object.__setattr__(self, "regime_policy_identity", _text(self.regime_policy_identity, "regime_policy_identity"))
        elif self.regime_policy_identity is not None:
            raise ValueError("regime_policy_identity requires ReproducibilityManifest/v2")

    @property
    def manifest_fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-reproducibility-manifest/v2" if self.regime_policy_identity is not None else "algofortis-reproducibility-manifest/v1",
            (("version", self.version), ("source", self.source.fingerprint),
             ("market_data", self.market_data.fingerprint), ("configuration", self.configuration.fingerprint),
             ("runtime", self.runtime.fingerprint), ("dependencies", self.dependencies.fingerprint),
             ("execution_policy", self.execution_policy_identity), ("cost_policy", self.cost_policy_identity),
             ("validation_policy", self.validation_policy_identity), ("randomness_policy", self.randomness_policy_identity))
            + (() if self.regime_policy_identity is None else (("regime_policy", self.regime_policy_identity),)),
        )


class ResultEvidenceFamily(str, Enum):
    TRADE_LEDGER = "TRADE_LEDGER"
    EXECUTION = "EXECUTION"
    PORTFOLIO_ACCOUNTING = "PORTFOLIO_ACCOUNTING"
    COST = "COST"
    METRICS = "METRICS"
    VALIDATION = "VALIDATION"
    RANDOMIZED_ANALYSIS = "RANDOMIZED_ANALYSIS"
    REGIME = "REGIME"


@dataclass(frozen=True)
class ResultEvidence:
    family: ResultEvidenceFamily
    identity: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "family", ResultEvidenceFamily(self.family))
        object.__setattr__(self, "identity", _text(self.identity, "result evidence identity"))


@dataclass(frozen=True)
class RandomizedAnalysisEntry:
    analysis_kind: str
    scope_identity: str
    evidence_schema_version: str
    evidence_result_fingerprint: str

    def __post_init__(self) -> None:
        for name in ("analysis_kind", "scope_identity", "evidence_schema_version", "evidence_result_fingerprint"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.analysis_kind not in {"BOOTSTRAP", "MC1", "MC2"}:
            raise ValueError("analysis_kind must be an existing randomized analysis kind")

    @property
    def key(self) -> tuple[str, str]:
        return self.analysis_kind, self.scope_identity


@dataclass(frozen=True)
class RandomizedAnalysisCollection:
    entries: tuple[RandomizedAnalysisEntry, ...]
    schema_version: str = "RandomizedAnalysisCollection/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "RandomizedAnalysisCollection/v1":
            raise ValueError("unsupported randomized analysis collection schema_version")
        values = tuple(self.entries)
        if not values or not all(isinstance(value, RandomizedAnalysisEntry) for value in values):
            raise ValueError("randomized analysis collection requires typed entries")
        ordered = tuple(sorted(values, key=lambda value: value.key))
        if len({value.key for value in ordered}) != len(ordered):
            raise ValueError("duplicate randomized analysis kind/scope is invalid")
        object.__setattr__(self, "entries", ordered)

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-randomized-analysis-collection/v1",
            (("schema_version", self.schema_version),
             ("entries", tuple((value.analysis_kind, value.scope_identity,
                                 value.evidence_schema_version, value.evidence_result_fingerprint)
                               for value in self.entries))),
        )


_VALIDATION_COLLECTION_ORDER = ("VALIDATION_OUTCOME", "PROMOTION_DECISION")


@dataclass(frozen=True)
class ValidationEvidenceEntry:
    """One typed child of the additive validation result-evidence parent."""

    validation_analysis_kind: str
    scope_identity: str
    evidence_schema_version: str
    evidence_result_fingerprint: str

    def __post_init__(self) -> None:
        for name in ("validation_analysis_kind", "scope_identity", "evidence_schema_version", "evidence_result_fingerprint"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.validation_analysis_kind not in _VALIDATION_COLLECTION_ORDER:
            raise ValueError("unsupported validation analysis kind")
        allowed = {
            "VALIDATION_OUTCOME": {"ValidationOutcomeIdentity/v1", "ValidationOutcomeApplicabilityBinding/v1"},
            "PROMOTION_DECISION": {"PromotionDecisionEvidence/v1"},
        }
        if self.evidence_schema_version not in allowed[self.validation_analysis_kind]:
            raise ValueError("unsupported validation evidence schema")

    @property
    def key(self) -> tuple[str, str]:
        return self.validation_analysis_kind, self.scope_identity


@dataclass(frozen=True)
class ValidationEvidenceCollection:
    """Canonical compound VALIDATION parent for promotion-aware finalization."""

    entries: tuple[ValidationEvidenceEntry, ...]
    schema_version: str = "ValidationEvidenceCollection/v1"

    def __post_init__(self) -> None:
        if self.schema_version != "ValidationEvidenceCollection/v1":
            raise ValueError("unsupported validation evidence collection schema_version")
        values = tuple(self.entries)
        if not all(isinstance(value, ValidationEvidenceEntry) for value in values):
            raise TypeError("validation evidence collection requires typed entries")
        if len({value.key for value in values}) != len(values):
            raise ValueError("duplicate validation analysis kind/scope is invalid")
        if len({value.validation_analysis_kind for value in values}) != len(values):
            raise ValueError("validation evidence collection allows one entry per analysis kind")
        by_kind = {value.validation_analysis_kind: value for value in values}
        if set(by_kind) != set(_VALIDATION_COLLECTION_ORDER):
            raise ValueError("validation evidence collection requires each supported child")
        object.__setattr__(self, "entries", tuple(by_kind[kind] for kind in _VALIDATION_COLLECTION_ORDER))

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-validation-evidence-collection/v1",
            (("schema_version", self.schema_version),
             ("entries", tuple((value.validation_analysis_kind, value.scope_identity,
                                 value.evidence_schema_version, value.evidence_result_fingerprint)
                               for value in self.entries))),
        )


@dataclass(frozen=True)
class SuccessfulResult:
    version: str
    evidence: tuple[ResultEvidence, ...]
    operational_provenance: Mapping[str, str] | None = None
    randomized_analysis_collection: RandomizedAnalysisCollection | None = None
    validation_collection: ValidationEvidenceCollection | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "version", _text(self.version, "version"))
        values = tuple(sorted(self.evidence, key=lambda item: item.family.value))
        if not values or not all(isinstance(item, ResultEvidence) for item in values):
            raise ValueError("successful result requires authoritative evidence")
        if len({item.family for item in values}) != len(values):
            raise ValueError("result evidence family may occur once")
        if self.version.endswith("/v2") and ResultEvidenceFamily.REGIME not in {item.family for item in values}:
            raise ValueError("SuccessfulResult/v2 requires regime evidence")
        if self.randomized_analysis_collection is not None:
            if not isinstance(self.randomized_analysis_collection, RandomizedAnalysisCollection):
                raise TypeError("randomized_analysis_collection must be RandomizedAnalysisCollection")
            randomized = [item for item in values if item.family is ResultEvidenceFamily.RANDOMIZED_ANALYSIS]
            if len(randomized) != 1 or randomized[0].identity != self.randomized_analysis_collection.fingerprint:
                raise ValueError("randomized analysis collection must bind the sole randomized parent")
        if self.validation_collection is not None:
            if not isinstance(self.validation_collection, ValidationEvidenceCollection):
                raise TypeError("validation_collection must be ValidationEvidenceCollection")
            validation = [item for item in values if item.family is ResultEvidenceFamily.VALIDATION]
            if len(validation) != 1 or validation[0].identity != self.validation_collection.fingerprint:
                raise ValueError("validation collection must bind the sole validation parent")
        object.__setattr__(self, "evidence", values)
        provenance = dict(self.operational_provenance or {})
        if not all(isinstance(key, str) and isinstance(value, str) for key, value in provenance.items()):
            raise TypeError("operational provenance must be string metadata")
        object.__setattr__(self, "operational_provenance", MappingProxyType(dict(sorted(provenance.items()))))

    @property
    def result_fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-successful-result/v2" if self.version.endswith("/v2") else "algofortis-successful-result/v1",
            (("version", self.version), ("evidence", tuple((item.family, item.identity) for item in self.evidence))),
        )


def successful_result_v2(
    economic_evidence: tuple[ResultEvidence, ...],
    entry_regimes: tuple[EntryRegimeSnapshot, ...],
    *,
    cost_leg_assessments: tuple[CostLegAssessment, ...] = (),
    completed_cost_assessments: tuple[CostAssessment, ...] = (),
    cost_evidence_required: bool = False,
    randomized_analysis_collection: RandomizedAnalysisCollection | None = None,
) -> SuccessfulResult:
    """Produce v2 result identity from upstream result evidence only."""
    values = tuple(economic_evidence)
    prohibited = {ResultEvidenceFamily.REGIME}
    if cost_evidence_required and not (cost_leg_assessments or completed_cost_assessments):
        raise ValueError("required authoritative cost evidence is missing")
    if cost_leg_assessments or completed_cost_assessments:
        prohibited.add(ResultEvidenceFamily.COST)
    if any(item.family in prohibited for item in values):
        raise ValueError("regime and supplied cost evidence must come from persisted authoritative evidence")
    regime = ResultEvidence(ResultEvidenceFamily.REGIME, entry_regime_evidence_fingerprint(entry_regimes))
    costs = ()
    if cost_leg_assessments or completed_cost_assessments:
        costs = (ResultEvidence(
            ResultEvidenceFamily.COST,
            cost_evidence_fingerprint(cost_leg_assessments, completed_cost_assessments),
        ),)
    return SuccessfulResult("result/v2", (*values, *costs, regime),
                            randomized_analysis_collection=randomized_analysis_collection)


@dataclass(frozen=True)
class InvalidFinalizedResult:
    """Completed audit whose established promotion decision is INVALID, not D7."""

    manifest_fingerprint: str
    validation_collection_fingerprint: str
    promotion_decision_fingerprint: str
    invalid_reason_identities: tuple[str, ...]
    evidence: tuple[ResultEvidence, ...]
    schema_version: str = "InvalidFinalizedResult/v1"
    terminal_status: str = "INVALID"
    promotable: bool = False
    randomized_analysis_collection: RandomizedAnalysisCollection | None = None
    validation_collection: ValidationEvidenceCollection | None = None

    def __post_init__(self) -> None:
        if self.schema_version != "InvalidFinalizedResult/v1":
            raise ValueError("unsupported invalid finalized result schema")
        if self.terminal_status != "INVALID" or self.promotable is not False:
            raise ValueError("invalid finalized result requires INVALID and promotable=false")
        for name in ("manifest_fingerprint", "validation_collection_fingerprint", "promotion_decision_fingerprint"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        reasons = tuple(sorted(set(_text(value, "invalid_reason_identity") for value in self.invalid_reason_identities)))
        object.__setattr__(self, "invalid_reason_identities", reasons)
        values = tuple(sorted(self.evidence, key=lambda item: item.family.value))
        if not values or not all(isinstance(item, ResultEvidence) for item in values):
            raise ValueError("invalid finalized result requires established authoritative evidence")
        if len({item.family for item in values}) != len(values):
            raise ValueError("result evidence family may occur once")
        validation = [item for item in values if item.family is ResultEvidenceFamily.VALIDATION]
        if len(validation) != 1 or validation[0].identity != self.validation_collection_fingerprint:
            raise ValueError("invalid finalized result must retain its validation collection parent")
        if self.randomized_analysis_collection is not None:
            randomized = [item for item in values if item.family is ResultEvidenceFamily.RANDOMIZED_ANALYSIS]
            if len(randomized) != 1 or randomized[0].identity != self.randomized_analysis_collection.fingerprint:
                raise ValueError("invalid finalized result randomized parent mismatch")
        if self.validation_collection is not None:
            if not isinstance(self.validation_collection, ValidationEvidenceCollection) or self.validation_collection.fingerprint != self.validation_collection_fingerprint:
                raise ValueError("invalid finalized result validation collection mismatch")
        object.__setattr__(self, "evidence", values)

    @property
    def result_fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-invalid-finalized-result/v1",
            (("schema_version", self.schema_version), ("manifest", self.manifest_fingerprint),
             ("terminal_status", self.terminal_status), ("promotable", self.promotable),
             ("validation_collection", self.validation_collection_fingerprint),
             ("promotion_decision", self.promotion_decision_fingerprint),
             ("invalid_reasons", self.invalid_reason_identities),
             ("evidence", tuple((item.family, item.identity) for item in self.evidence))),
        )


@dataclass(frozen=True)
class StructuredFailureResult:
    """Category-A only; code is an existing stable Enum, not exception text."""

    version: str
    manifest_fingerprint: str
    stage: str
    code: Enum
    evidence_identity: str
    policy_identity: str

    def __post_init__(self) -> None:
        for name in ("version", "manifest_fingerprint", "stage", "evidence_identity", "policy_identity"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.code, Enum):
            raise TypeError("Category-A code must reuse a stable Enum member")

    @property
    def failure_result_fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            "algofortis-structured-failure-result/v1",
            (("version", self.version), ("manifest", self.manifest_fingerprint), ("stage", self.stage),
             ("code", self.code), ("evidence", self.evidence_identity), ("policy", self.policy_identity)),
        )


@dataclass(frozen=True)
class CategoryBManifestFailure:
    """No manifest or failure-result fingerprint exists for Category B."""

    missing_tier1_component: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "missing_tier1_component", _text(self.missing_tier1_component, "missing_tier1_component"))


@dataclass(frozen=True)
class CategoryCOperationalFailure:
    """Operational provenance only; never authoritative reproducibility identity."""

    operational_context: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "operational_context", _text(self.operational_context, "operational_context"))
