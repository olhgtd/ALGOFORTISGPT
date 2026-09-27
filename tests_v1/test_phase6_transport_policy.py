from __future__ import annotations
from pathlib import Path
import importlib
import sys
import pytest
ROOT = Path(__file__).resolve().parents[1]

def _policy_module():
    assert (ROOT / "engine/data/transports/policy.py").is_file(), "transport policy module missing"
    sys.path.insert(0, str(ROOT)) if str(ROOT) not in sys.path else None
    return importlib.import_module("engine.data.transports.policy")

def _valid_kwargs():
    return dict(policy_id="TEST_ONLY/transport", version="1", max_reconnect_attempts=3, reconnect_backoff_seconds=(0.1,0.2,0.4), receive_queue_capacity=64, heartbeat_timeout_seconds=5.0, stale_after_seconds=3.0, max_subscriptions_per_socket=100, subscription_batch_limit=25, max_connections=2, test_only=True)

def test_policy_requires_identity_and_version() -> None:
    p = _policy_module(); kw = _valid_kwargs()
    with pytest.raises(ValueError): p.BrokerTransportPolicy(**{**kw, "policy_id":""})
    with pytest.raises(ValueError): p.BrokerTransportPolicy(**{**kw, "version":""})

def test_policy_rejects_invalid_required_limits() -> None:
    p = _policy_module(); kw = _valid_kwargs()
    for field, value in [("max_reconnect_attempts",-1),("receive_queue_capacity",0),("heartbeat_timeout_seconds",0),("stale_after_seconds",0),("max_subscriptions_per_socket",0),("subscription_batch_limit",0),("max_connections",0)]:
        with pytest.raises(ValueError): p.BrokerTransportPolicy(**{**kw, field:value})

def test_reconnect_backoff_must_cover_attempt_budget_and_be_non_negative() -> None:
    p = _policy_module(); kw = _valid_kwargs()
    with pytest.raises(ValueError): p.BrokerTransportPolicy(**{**kw, "reconnect_backoff_seconds":(0.1,)})
    with pytest.raises(ValueError): p.BrokerTransportPolicy(**{**kw, "reconnect_backoff_seconds":(0.1,-1.0,0.4)})

def test_policy_reference_is_versioned_and_immutable() -> None:
    p = _policy_module(); policy = p.BrokerTransportPolicy(**_valid_kwargs())
    assert policy.reference == "TEST_ONLY/transport@1"
