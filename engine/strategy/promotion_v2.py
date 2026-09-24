"""Fail-closed promotion evidence evaluation; never arms Live."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping
import re

from engine.reproducibility.codec import CanonicalCodec


class PromotionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PromotionProfile:
    version: str
    criteria: Mapping[str, int | Decimal]
    is_research_only: bool
    stage: str = "PAPER_TO_ELIGIBLE_FOR_LIVE"

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not isinstance(self.criteria, Mapping) or not isinstance(self.is_research_only, bool):
            raise PromotionError("invalid immutable promotion profile")
        if self.is_research_only:
            if self.version != "research-only/v1" or self.stage != "RESEARCH_ONLY" or self.criteria:
                raise PromotionError("research-only/v1 cannot carry numeric criteria")
        else:
            if "@" not in self.version or self.stage not in ("BACKTEST_TO_PAPER", "PAPER_TO_ELIGIBLE_FOR_LIVE"):
                raise PromotionError("numeric profile needs a version and supported stage")
            shared = {"minimum_trades", "minimum_oos_share", "minimum_wfo_windows",
                      "minimum_wfo_pass_rate", "maximum_mc_drawdown", "minimum_stress_margin"}
            expected = shared if self.stage == "BACKTEST_TO_PAPER" else shared | {"minimum_paper_days", "maximum_paper_drift"}
            if set(self.criteria) != expected:
                raise PromotionError("all stage criteria must be explicit")
            for key, value in self.criteria.items():
                if isinstance(value, bool) or not isinstance(value, (int, Decimal)) or (isinstance(value, Decimal) and not value.is_finite()) or value < 0:
                    raise PromotionError(f"invalid criterion {key}")
            if any(self.criteria[key] <= 0 for key in ("minimum_trades", "minimum_wfo_windows")):
                raise PromotionError("sample minimums must be positive")
            if self.stage == "PAPER_TO_ELIGIBLE_FOR_LIVE" and self.criteria["minimum_paper_days"] <= 0:
                raise PromotionError("minimum paper duration must be positive")
            if any(self.criteria[key] > 1 for key in ("minimum_oos_share", "minimum_wfo_pass_rate")):
                raise PromotionError("share and pass rate must not exceed one")
        object.__setattr__(self, "criteria", MappingProxyType(dict(sorted(self.criteria.items()))))

    @classmethod
    def research_only(cls) -> "PromotionProfile":
        return cls("research-only/v1", MappingProxyType({}), True, "RESEARCH_ONLY")

    @classmethod
    def backtest_to_paper(cls, *, version: str, minimum_trades: int,
                          minimum_oos_share: Decimal, minimum_wfo_windows: int,
                          minimum_wfo_pass_rate: Decimal, maximum_mc_drawdown: Decimal,
                          minimum_stress_margin: Decimal) -> "PromotionProfile":
        complete = cls.numeric(version=version, minimum_trades=minimum_trades,
            minimum_oos_share=minimum_oos_share, minimum_wfo_windows=minimum_wfo_windows,
            minimum_wfo_pass_rate=minimum_wfo_pass_rate, maximum_mc_drawdown=maximum_mc_drawdown,
            minimum_stress_margin=minimum_stress_margin, minimum_paper_days=1,
            maximum_paper_drift=Decimal(0))
        criteria = {key: value for key, value in complete.criteria.items()
                    if key not in ("minimum_paper_days", "maximum_paper_drift")}
        return cls(version, MappingProxyType(criteria), False, "BACKTEST_TO_PAPER")

    @classmethod
    def numeric(cls, *, version: str, minimum_trades: int, minimum_oos_share: Decimal,
                minimum_wfo_windows: int, minimum_wfo_pass_rate: Decimal,
                maximum_mc_drawdown: Decimal, minimum_stress_margin: Decimal,
                minimum_paper_days: int, maximum_paper_drift: Decimal) -> "PromotionProfile":
        if not isinstance(version, str) or "@" not in version:
            raise PromotionError("numeric profile requires an explicit version")
        criteria = dict(minimum_trades=minimum_trades, minimum_oos_share=minimum_oos_share,
                        minimum_wfo_windows=minimum_wfo_windows, minimum_wfo_pass_rate=minimum_wfo_pass_rate,
                        maximum_mc_drawdown=maximum_mc_drawdown, minimum_stress_margin=minimum_stress_margin,
                        minimum_paper_days=minimum_paper_days, maximum_paper_drift=maximum_paper_drift)
        for key, value in criteria.items():
            if isinstance(value, bool) or not isinstance(value, (int, Decimal)) or (isinstance(value, Decimal) and not value.is_finite()):
                raise PromotionError(f"invalid criterion {key}")
            if value < 0:
                raise PromotionError(f"negative criterion {key}")
        if minimum_trades == 0 or minimum_wfo_windows == 0 or minimum_paper_days == 0:
            raise PromotionError("minimum sample requirements must be positive")
        if minimum_oos_share > 1 or minimum_wfo_pass_rate > 1 or maximum_paper_drift > 1:
            raise PromotionError("fractions must be at most one")
        return cls(version, MappingProxyType(criteria), False)


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    status: str
    reasons: tuple[str, ...]
    live_state: str = "READ_ONLY/DISARMED"


@dataclass(frozen=True, slots=True)
class PromotionEvidenceBundle:
    values: Mapping[str, object]
    fingerprint: str
    _attested: bool = field(default=False, init=False, repr=False)
    _metrics_verified: bool = field(default=False, init=False, repr=False)

    @classmethod
    def from_authorities(cls, *, ledger: object, validation: object,
                         overfitting: object, licence_metadata: object, market: str,
                         metrics: Mapping[str, int | Decimal]) -> "PromotionEvidenceBundle":
        from engine.research.durable_ledger import DurableTrialsLedger
        from engine.research.validation_v2 import ValidationBundle
        from engine.research.overfitting import OverfittingEvidence
        from engine.data.licensing import DataLicenceMetadata
        if not isinstance(licence_metadata, DataLicenceMetadata):
            raise PromotionError("source licence metadata required")
        licence = _promotion_licence(licence_metadata, market=market)
        if (not isinstance(ledger, DurableTrialsLedger)
                or not isinstance(validation, ValidationBundle)
                or not isinstance(overfitting, OverfittingEvidence)
                or not licence.allowed or "SYNTHETIC" in licence.labels
                or not validation.dataset_ref.startswith(licence_metadata.source_id + "@")
                or validation.dataset_ref not in ledger.experiment.dataset_versions
                or ledger.trial_count != overfitting.trial_count or ledger.trial_count < 2
                or not ledger.oos_viewed or validation.wfo_evidence is None
                or validation.final_oos is None or validation.robustness is None):
            raise PromotionError("complete durable, licensed and closed research authorities required")
        if not isinstance(metrics, Mapping) or any(isinstance(value, bool) or not isinstance(value, (int, Decimal))
                 or (isinstance(value, Decimal) and not value.is_finite()) for value in metrics.values()):
            raise PromotionError("metrics must be finite numeric values")
        ledger_fp = CanonicalCodec.fingerprint("algofortis-trials-closed/v1", (
            ("experiment", ledger.experiment.experiment_id),
            ("records", tuple(item.fingerprint for item in ledger.records())), ("oos_viewed", True)))
        values = dict(metrics, validation_fingerprint=validation.fingerprint,
                      trials_ledger_fingerprint=ledger_fp,
                      overfitting_fingerprint=overfitting.fingerprint, licensed_data=True)
        fingerprint = CanonicalCodec.fingerprint("algofortis-promotion-evidence/v1", (
            ("metrics", tuple(sorted(metrics.items()))),
            ("validation", validation.fingerprint), ("ledger", ledger_fp),
            ("overfitting", overfitting.fingerprint), ("licence", licence.fingerprint)))
        bundle = cls(MappingProxyType(values), fingerprint)
        object.__setattr__(bundle, "_attested", True)
        return bundle


@dataclass(frozen=True, slots=True)
class PromotionAttemptBundle:
    """Auditable automatic rejection bundle for synthetic test evidence."""
    fingerprint: str
    reasons: tuple[str, ...]
    status: str = "NON_PROMOTABLE"
    evidence_scope: str = "TEST_ONLY"

    @classmethod
    def test_only(cls, *, validation_fingerprint: str,
                  overfitting_fingerprint: str, licence: object) -> "PromotionAttemptBundle":
        from engine.data.licensing import DataLicenceDecision
        if (not isinstance(licence, DataLicenceDecision) or "SYNTHETIC" not in licence.labels
                or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                       for value in (validation_fingerprint, overfitting_fingerprint))):
            raise PromotionError("test-only rejection bundle requires synthetic evidence fingerprints")
        reasons = ("SYNTHETIC_NOT_PROMOTION_EVIDENCE", "RESEARCH_ONLY")
        fingerprint = CanonicalCodec.fingerprint("algofortis-test-only-promotion-attempt/v1", (
            ("validation", validation_fingerprint), ("overfitting", overfitting_fingerprint),
            ("licence", licence.fingerprint), ("reasons", reasons), ("status", "NON_PROMOTABLE")))
        return cls(fingerprint, reasons)


def _promotion_licence(metadata: object, *, market: str):
    from engine.data.licensing import DataLicenceMetadata, DataLicencePolicy, DataUse
    if not isinstance(metadata, DataLicenceMetadata):
        raise PromotionError("source licence metadata required")
    return DataLicencePolicy().evaluate(metadata, market=market,
        requested_use=DataUse.PROMOTION, programmatic_acquisition=False)


def licensed_for_promotion(metadata: object, *, market: str) -> bool:
    return _promotion_licence(metadata, market=market).allowed


def evaluate_promotion(profile: PromotionProfile, evidence: Mapping[str, object] | PromotionEvidenceBundle) -> PromotionDecision:
    if not isinstance(profile, PromotionProfile) or not isinstance(evidence, (Mapping, PromotionEvidenceBundle)):
        raise PromotionError("profile and evidence required")
    if profile.is_research_only:
        return PromotionDecision("NON_PROMOTABLE", ("RESEARCH_ONLY",))
    if not isinstance(evidence, PromotionEvidenceBundle) or not evidence._attested:
        return PromotionDecision("NON_PROMOTABLE", ("MISSING_EVIDENCE",))
    if not evidence._metrics_verified:
        return PromotionDecision("NON_PROMOTABLE", ("UNVERIFIED_METRICS",))
    evidence = evidence.values
    required = ("trades", "oos_share", "wfo_windows", "wfo_pass_rate", "mc_drawdown",
                "stress_margin")
    if profile.stage == "PAPER_TO_ELIGIBLE_FOR_LIVE":
        required += ("paper_days", "paper_drift")
    elif profile.stage != "BACKTEST_TO_PAPER":
        return PromotionDecision("NON_PROMOTABLE", ("INVALID_PROFILE_STAGE",))
    required += ("validation_fingerprint", "trials_ledger_fingerprint",
                 "overfitting_fingerprint", "licensed_data")
    if any(key not in evidence for key in required):
        return PromotionDecision("NON_PROMOTABLE", ("MISSING_EVIDENCE",))
    if evidence["licensed_data"] is not True:
        return PromotionDecision("NON_PROMOTABLE", ("UNLICENSED_DATA",))
    checks = (("trades", "minimum_trades", False), ("oos_share", "minimum_oos_share", False),
              ("wfo_windows", "minimum_wfo_windows", False), ("wfo_pass_rate", "minimum_wfo_pass_rate", False),
              ("mc_drawdown", "maximum_mc_drawdown", True), ("stress_margin", "minimum_stress_margin", False),
              ("paper_days", "minimum_paper_days", False), ("paper_drift", "maximum_paper_drift", True))
    checks = tuple(item for item in checks if item[1] in profile.criteria)
    try:
        failures = tuple(key.upper() + "_FAIL" for key, threshold, maximum in checks
                         if isinstance(evidence[key], bool) or not isinstance(evidence[key], (int, Decimal))
                         or (not isinstance(evidence[key], Decimal) and isinstance(profile.criteria[threshold], Decimal))
                         or (isinstance(evidence[key], Decimal) and not evidence[key].is_finite())
                         or ((evidence[key] > profile.criteria[threshold]) if maximum else (evidence[key] < profile.criteria[threshold])))
    except (TypeError, ValueError):
        return PromotionDecision("NON_PROMOTABLE", ("INVALID_EVIDENCE",))
    identity_fields = ("validation_fingerprint", "trials_ledger_fingerprint", "overfitting_fingerprint")
    if failures or any(not isinstance(evidence[k], str) or not re.fullmatch(r"[0-9a-f]{64}", evidence[k]) for k in identity_fields):
        return PromotionDecision("NON_PROMOTABLE", failures or ("INVALID_EVIDENCE",))
    status = "ELIGIBLE_FOR_PAPER_EVIDENCE_ONLY" if profile.stage == "BACKTEST_TO_PAPER" else "ELIGIBLE_FOR_LIVE_EVIDENCE_ONLY"
    return PromotionDecision(status, ())
