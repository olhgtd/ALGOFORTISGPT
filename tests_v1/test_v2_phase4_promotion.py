from decimal import Decimal

from engine.strategy.promotion_v2 import PromotionProfile, evaluate_promotion


def test_default_is_non_promotable_even_with_positive_score():
    result = evaluate_promotion(PromotionProfile.research_only(), {})
    assert result.status == "NON_PROMOTABLE"
    assert "RESEARCH_ONLY" in result.reasons


def test_numeric_profile_still_requires_complete_evidence():
    profile = PromotionProfile.numeric(
        version="baseline@v1", minimum_trades=200, minimum_oos_share=Decimal("0.2"),
        minimum_wfo_windows=3, minimum_wfo_pass_rate=Decimal("0.6"),
        maximum_mc_drawdown=Decimal("0.2"), minimum_stress_margin=Decimal("0"),
        minimum_paper_days=30, maximum_paper_drift=Decimal("0.1"),
    )
    result = evaluate_promotion(profile, {"trades": 300})
    assert result.status == "NON_PROMOTABLE"
    assert "MISSING_EVIDENCE" in result.reasons
