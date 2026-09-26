from __future__ import annotations

from pathlib import Path

from engine.broker_adapters.angelone_v2.order_policy import (
    BrokerOrderPolicyEvidence,
    validate_order_shape_for_policy,
)

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "engine" / "broker_adapters" / "angelone_v2" / "order_policy.py"


def _policy():
    return BrokerOrderPolicyEvidence(
        policy_id="TEST_ONLY/G6/ORDER",
        version="v1",
        allowed_order_types=("LIMIT", "STOP"),
        allowed_product_types=("INTRADAY",),
        tagging_policy_ref="TEST_ONLY/TAGGING@v1",
        requires_algo_tag=True,
        verified=True,
        test_only=True,
    )


def test_market_order_is_rejected_deterministically() -> None:
    decision = validate_order_shape_for_policy(
        _policy(), order_type="MARKET", product_type="INTRADAY", algo_tag_present=True
    )
    assert decision.eligible is False
    assert decision.reason == "ORDER_TYPE_NOT_ALLOWED"
    assert decision.requested_order_type == "MARKET"
    assert decision.effective_order_type is None


def test_validator_never_silently_converts_market_to_limit() -> None:
    decision = validate_order_shape_for_policy(
        _policy(), order_type="MARKET", product_type="INTRADAY", algo_tag_present=True
    )
    assert decision.requested_order_type == "MARKET"
    assert decision.effective_order_type is None
    assert "LIMIT" not in decision.reason


def test_missing_unknown_product_or_tagging_policy_fails_closed() -> None:
    assert validate_order_shape_for_policy(
        None, order_type="LIMIT", product_type="INTRADAY", algo_tag_present=True
    ).reason == "MISSING_ORDER_POLICY"
    assert validate_order_shape_for_policy(
        _policy(), order_type="LIMIT", product_type="UNKNOWN", algo_tag_present=True
    ).reason == "PRODUCT_TYPE_NOT_ALLOWED"
    assert validate_order_shape_for_policy(
        _policy(), order_type="LIMIT", product_type="INTRADAY", algo_tag_present=False
    ).reason == "ALGO_TAG_REQUIRED"


def test_verified_allowed_shape_is_evidence_only() -> None:
    decision = validate_order_shape_for_policy(
        _policy(), order_type="LIMIT", product_type="INTRADAY", algo_tag_present=True
    )
    assert decision.eligible is True
    assert decision.effective_order_type == "LIMIT"
    assert not hasattr(decision, "arm")
    assert not hasattr(decision, "place")


def test_module_has_no_hardcoded_current_rate_or_ops_policy_constants() -> None:
    source = MODULE.read_text(encoding="utf-8")
    forbidden = (
        "REQUESTS_PER_SECOND = 9",
        "MAX_REQUESTS = 9",
        "OPS_THRESHOLD = 10",
        "SQUARE_OFF_TIME =",
    )
    assert all(token not in source for token in forbidden)
