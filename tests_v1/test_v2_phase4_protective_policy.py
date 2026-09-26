from decimal import Decimal

import pytest

from engine.strategy.protective_policy_v2 import ProtectivePolicyError, ProtectivePolicyV2, PolicyRegistryV2
from strategies.orb.orb_v2 import ORBReferenceStrategyV2


def test_orb_preparation_requires_registered_complete_policy():
    strategy = ORBReferenceStrategyV2()
    registry = PolicyRegistryV2()
    with pytest.raises(ProtectivePolicyError):
        strategy.prepare_policy_bound_simulation("TEST_ONLY/orb@v1", registry)
    policy = ProtectivePolicyV2(ref="TEST_ONLY/orb@v1",
        stop_distance=Decimal("10"), target_distance=Decimal("20"),
        trailing_distance=Decimal("5"), oco=True,
        tick_size=Decimal("0.05"), rounding="ROUND_HALF_UP")
    registry.register(policy)
    prepared = strategy.prepare_policy_bound_simulation("TEST_ONLY/orb@v1", registry)
    assert prepared.promotion_eligible is False
    assert prepared.protective_policy_ref == policy.ref
    assert registry.resolve(policy.ref).fingerprint == policy.fingerprint


def test_incomplete_policy_rejected():
    with pytest.raises(ProtectivePolicyError):
        ProtectivePolicyV2(ref="orb@v1", stop_distance=Decimal("1"),
            target_distance=Decimal("2"), trailing_distance=None, oco=True,
            tick_size=Decimal("0.05"), rounding="ROUND_HALF_UP")
