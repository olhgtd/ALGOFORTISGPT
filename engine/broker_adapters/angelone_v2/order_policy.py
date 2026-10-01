"""Versioned Phase-6 order-shape qualification evidence.

This module is pure validation. It has no broker mutation capability and never
converts one requested order type into another.
"""
from __future__ import annotations

from dataclasses import dataclass


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip().upper()


def _values(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not value:
        raise ValueError(f"{field} must be a non-empty tuple")
    return tuple(_text(item, field) for item in value)


@dataclass(frozen=True, slots=True)
class BrokerOrderPolicyEvidence:
    policy_id: str
    version: str
    allowed_order_types: tuple[str, ...]
    allowed_product_types: tuple[str, ...]
    tagging_policy_ref: str
    requires_algo_tag: bool
    verified: bool
    test_only: bool = False

    def __post_init__(self) -> None:
        policy_id = self.policy_id.strip() if isinstance(self.policy_id, str) else ""
        version = self.version.strip() if isinstance(self.version, str) else ""
        tag_ref = self.tagging_policy_ref.strip() if isinstance(self.tagging_policy_ref, str) else ""
        if not policy_id or not version or not tag_ref:
            raise ValueError("policy_id, version and tagging_policy_ref are required")
        if self.test_only and not policy_id.startswith("TEST_ONLY/"):
            raise ValueError("TEST_ONLY policy_id must start with TEST_ONLY/")
        if not isinstance(self.requires_algo_tag, bool):
            raise TypeError("requires_algo_tag must be bool")
        if not isinstance(self.verified, bool):
            raise TypeError("verified must be bool")
        if not isinstance(self.test_only, bool):
            raise TypeError("test_only must be bool")
        object.__setattr__(self, "policy_id", policy_id)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "tagging_policy_ref", tag_ref)
        object.__setattr__(
            self, "allowed_order_types", _values(self.allowed_order_types, "allowed_order_types")
        )
        object.__setattr__(
            self, "allowed_product_types", _values(self.allowed_product_types, "allowed_product_types")
        )

    @property
    def reference(self) -> str:
        return f"{self.policy_id}@{self.version}"


@dataclass(frozen=True, slots=True)
class BrokerOrderPolicyDecision:
    eligible: bool
    reason: str
    requested_order_type: str
    requested_product_type: str
    effective_order_type: str | None
    policy_ref: str | None


def validate_order_shape_for_policy(
    policy: BrokerOrderPolicyEvidence | None,
    *,
    order_type: str,
    product_type: str,
    algo_tag_present: bool,
) -> BrokerOrderPolicyDecision:
    requested_order = _text(order_type, "order_type")
    requested_product = _text(product_type, "product_type")
    if not isinstance(algo_tag_present, bool):
        raise TypeError("algo_tag_present must be bool")
    if policy is None:
        return BrokerOrderPolicyDecision(
            False,
            "MISSING_ORDER_POLICY",
            requested_order,
            requested_product,
            None,
            None,
        )
    if not isinstance(policy, BrokerOrderPolicyEvidence):
        raise TypeError("policy must be BrokerOrderPolicyEvidence or None")
    if not policy.verified:
        return BrokerOrderPolicyDecision(
            False,
            "ORDER_POLICY_UNVERIFIED",
            requested_order,
            requested_product,
            None,
            policy.reference,
        )
    if requested_order not in policy.allowed_order_types:
        return BrokerOrderPolicyDecision(
            False,
            "ORDER_TYPE_NOT_ALLOWED",
            requested_order,
            requested_product,
            None,
            policy.reference,
        )
    if requested_product not in policy.allowed_product_types:
        return BrokerOrderPolicyDecision(
            False,
            "PRODUCT_TYPE_NOT_ALLOWED",
            requested_order,
            requested_product,
            None,
            policy.reference,
        )
    if policy.requires_algo_tag and not algo_tag_present:
        return BrokerOrderPolicyDecision(
            False,
            "ALGO_TAG_REQUIRED",
            requested_order,
            requested_product,
            None,
            policy.reference,
        )
    return BrokerOrderPolicyDecision(
        True,
        "ORDER_SHAPE_VERIFIED_READ_ONLY",
        requested_order,
        requested_product,
        requested_order,
        policy.reference,
    )


__all__ = [
    "BrokerOrderPolicyDecision",
    "BrokerOrderPolicyEvidence",
    "validate_order_shape_for_policy",
]
