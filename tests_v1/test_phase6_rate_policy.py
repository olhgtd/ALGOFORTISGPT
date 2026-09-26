from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "engine" / "broker_adapters" / "angelone_v2" / "rate_policy.py"


def _load():
    assert MODULE.is_file(), "Phase-6 rate policy module is missing"
    spec = importlib.util.spec_from_file_location("phase6_rate_policy", MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_rate_policy_fails_closed_without_unbounded_retry() -> None:
    m = _load()
    decision = m.evaluate_rate(None, m.BrokerRateClass.READ_ORDERS, observed_requests=1)
    assert decision.allowed is False
    assert decision.retry_unbounded is False
    assert decision.reason == "MISSING_RATE_POLICY"


def test_test_only_numeric_policy_requires_explicit_test_profile() -> None:
    m = _load()
    rules = {m.BrokerRateClass.READ_ORDERS: m.BrokerRateRule(max_requests=2, window_seconds=1)}
    with pytest.raises(ValueError):
        m.BrokerRatePolicy("BROKER/RATE", "v1", rules, test_only=True)
    policy = m.BrokerRatePolicy("TEST_ONLY/BROKER/RATE", "v1", rules, test_only=True)
    assert policy.reference == "TEST_ONLY/BROKER/RATE@v1"
    assert m.evaluate_rate(policy, m.BrokerRateClass.READ_ORDERS, observed_requests=2).allowed is False
    assert m.evaluate_rate(policy, m.BrokerRateClass.READ_ORDERS, observed_requests=1).allowed is True


def test_missing_rate_class_rule_fails_closed() -> None:
    m = _load()
    policy = m.BrokerRatePolicy(
        "TEST_ONLY/BROKER/RATE",
        "v1",
        {m.BrokerRateClass.READ_ORDERS: m.BrokerRateRule(max_requests=2, window_seconds=1)},
        test_only=True,
    )
    decision = m.evaluate_rate(policy, m.BrokerRateClass.AUTH_SESSION, observed_requests=0)
    assert decision.allowed is False
    assert decision.reason == "MISSING_RATE_CLASS_RULE"
