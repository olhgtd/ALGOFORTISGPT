from __future__ import annotations

import inspect

import pytest

from engine.risk.latency_policy_v2 import (
    LatencyPolicyStatus,
    LatencyStagePolicy,
    RiskGateLatencyPolicy,
)


def _stage(name: str = "riskgate_total") -> LatencyStagePolicy:
    return LatencyStagePolicy(
        stage_name=name,
        percentile_target="p99",
        ceiling_ns=1,
        breach_action="RECORD",
    )


def _policy(**overrides) -> RiskGateLatencyPolicy:
    values = {
        "policy_id": "TEST_ONLY/riskgate-latency",
        "version": "v1",
        "status": LatencyPolicyStatus.TEST_ONLY,
        "environment_scope": "paper-shadow",
        "hardware_profile_ref": "hw:test",
        "runtime_profile_ref": "runtime:py313",
        "sample_minimum_ref": "sample-policy:test",
        "stages": (_stage(),),
        "evidence_bundle_ref": None,
        "approval_ref": None,
    }
    values.update(overrides)
    return RiskGateLatencyPolicy(**values)


def test_latency_stage_requires_positive_ceiling_and_non_empty_fields() -> None:
    with pytest.raises(ValueError):
        LatencyStagePolicy("", "p99", 1, "RECORD")
    with pytest.raises(ValueError):
        LatencyStagePolicy("risk", "p99", 0, "RECORD")
    with pytest.raises(TypeError):
        LatencyStagePolicy("risk", "p99", True, "RECORD")


def test_policy_rejects_duplicate_stage_names() -> None:
    with pytest.raises(ValueError, match="duplicate latency stage"):
        _policy(stages=(_stage("risk"), _stage("risk")))


def test_test_only_policy_requires_test_only_namespace() -> None:
    with pytest.raises(ValueError, match="TEST_ONLY"):
        _policy(policy_id="riskgate-latency")


def test_approved_policy_requires_evidence_and_approval_refs() -> None:
    with pytest.raises(ValueError, match="evidence_bundle_ref"):
        _policy(
            policy_id="riskgate-latency",
            status=LatencyPolicyStatus.APPROVED,
            evidence_bundle_ref=None,
            approval_ref="approval:1",
        )
    with pytest.raises(ValueError, match="approval_ref"):
        _policy(
            policy_id="riskgate-latency",
            status=LatencyPolicyStatus.APPROVED,
            evidence_bundle_ref="evidence:1",
            approval_ref=None,
        )


def test_policy_stage_lookup_and_reference_are_versioned() -> None:
    policy = _policy(stages=(_stage("delta"), _stage("total")))
    assert policy.reference == "TEST_ONLY/riskgate-latency@v1"
    assert policy.stage("total").stage_name == "total"
    with pytest.raises(KeyError):
        policy.stage("missing")


def test_module_has_no_default_production_latency_thresholds() -> None:
    import engine.risk.latency_policy_v2 as module

    source = inspect.getsource(module)
    assert "DEFAULT_SLO" not in source
    assert "DEFAULT_LATENCY" not in source
    assert "PRODUCTION_CEILING" not in source
