"""Fail-closed promotion evidence evaluation; never arms Live."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping


class PromotionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PromotionProfile:
    version: str
    criteria: Mapping[str, int | Decimal]
    is_research_only: bool

    @classmethod
    def research_only(cls) -> "PromotionProfile":
        return cls("research-only/v1", MappingProxyType({}), True)

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


def evaluate_promotion(profile: PromotionProfile, evidence: Mapping[str, object]) -> PromotionDecision:
    if not isinstance(profile, PromotionProfile) or not isinstance(evidence, Mapping):
        raise PromotionError("profile and evidence required")
    if profile.is_research_only:
        return PromotionDecision("NON_PROMOTABLE", ("RESEARCH_ONLY",))
    required = ("trades", "oos_share", "wfo_windows", "wfo_pass_rate", "mc_drawdown",
                "stress_margin", "paper_days", "paper_drift", "validation_fingerprint",
                "trials_ledger_fingerprint", "overfitting_fingerprint", "licensed_data")
    if any(key not in evidence for key in required):
        return PromotionDecision("NON_PROMOTABLE", ("MISSING_EVIDENCE",))
    if evidence["licensed_data"] is not True:
        return PromotionDecision("NON_PROMOTABLE", ("UNLICENSED_DATA",))
    checks = (("trades", "minimum_trades", False), ("oos_share", "minimum_oos_share", False),
              ("wfo_windows", "minimum_wfo_windows", False), ("wfo_pass_rate", "minimum_wfo_pass_rate", False),
              ("mc_drawdown", "maximum_mc_drawdown", True), ("stress_margin", "minimum_stress_margin", False),
              ("paper_days", "minimum_paper_days", False), ("paper_drift", "maximum_paper_drift", True))
    try:
        failures = tuple(key.upper() + "_FAIL" for key, threshold, maximum in checks
                         if isinstance(evidence[key], bool) or not isinstance(evidence[key], (int, Decimal))
                         or (not isinstance(evidence[key], Decimal) and isinstance(profile.criteria[threshold], Decimal))
                         or (isinstance(evidence[key], Decimal) and not evidence[key].is_finite())
                         or ((evidence[key] > profile.criteria[threshold]) if maximum else (evidence[key] < profile.criteria[threshold])))
    except (TypeError, ValueError):
        return PromotionDecision("NON_PROMOTABLE", ("INVALID_EVIDENCE",))
    if failures or any(not isinstance(evidence[k], str) or not evidence[k] for k in required[8:11]):
        return PromotionDecision("NON_PROMOTABLE", failures or ("INVALID_EVIDENCE",))
    return PromotionDecision("ELIGIBLE_FOR_LIVE_EVIDENCE_ONLY", ())
