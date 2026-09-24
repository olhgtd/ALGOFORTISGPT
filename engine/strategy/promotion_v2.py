"""Fail-closed promotion evidence evaluation; never arms Live."""
from __future__ import annotations

from dataclasses import dataclass
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

    @classmethod
    def from_authorities(cls, *, ledger: object, validation: object,
                         overfitting: object, licence: object,
                         metrics: Mapping[str, int | Decimal]) -> "PromotionEvidenceBundle":
        from engine.research.durable_ledger import DurableTrialsLedger
        from engine.research.validation_v2 import ValidationBundle
        from engine.research.overfitting import OverfittingEvidence
        from engine.data.licensing import DataLicenceDecision
        if (not isinstance(ledger, DurableTrialsLedger)
                or not isinstance(validation, ValidationBundle)
                or not isinstance(overfitting, OverfittingEvidence)
                or not isinstance(licence, DataLicenceDecision)
                or not licence.allowed or "SYNTHETIC" in licence.labels
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
        return cls(MappingProxyType(values), fingerprint)


def evaluate_promotion(profile: PromotionProfile, evidence: Mapping[str, object] | PromotionEvidenceBundle) -> PromotionDecision:
    if not isinstance(profile, PromotionProfile) or not isinstance(evidence, (Mapping, PromotionEvidenceBundle)):
        raise PromotionError("profile and evidence required")
    if profile.is_research_only:
        return PromotionDecision("NON_PROMOTABLE", ("RESEARCH_ONLY",))
    if not isinstance(evidence, PromotionEvidenceBundle):
        return PromotionDecision("NON_PROMOTABLE", ("MISSING_EVIDENCE",))
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
