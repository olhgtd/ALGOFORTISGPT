from __future__ import annotations

import json

import pytest

from engine.risk.latency_benchmark_v2 import (
    LatencyDistribution,
    RiskGateBenchmarkEvidence,
    build_benchmark_evidence,
)
from engine.risk.latency_policy_v2 import (
    LatencyPolicyStatus,
    LatencyStagePolicy,
    RiskGateLatencyPolicy,
)


def _policy(status=LatencyPolicyStatus.TEST_ONLY) -> RiskGateLatencyPolicy:
    return RiskGateLatencyPolicy(
        policy_id=("TEST_ONLY/latency" if status is LatencyPolicyStatus.TEST_ONLY else "latency"),
        version="v1",
        status=status,
        environment_scope="paper-shadow",
        hardware_profile_ref="hw:test",
        runtime_profile_ref="runtime:test",
        sample_minimum_ref="samples:test",
        stages=(LatencyStagePolicy("riskgate_total", "p99", 100, "RECORD"),),
        evidence_bundle_ref=("evidence:1" if status is LatencyPolicyStatus.APPROVED else None),
        approval_ref=("approval:1" if status is LatencyPolicyStatus.APPROVED else None),
    )


def test_distribution_uses_deterministic_nearest_rank_percentiles() -> None:
    distribution = LatencyDistribution.from_samples((1, 2, 3, 4, 5, 6, 7, 8, 9, 10))
    assert distribution.sample_count == 10
    assert distribution.p50_ns == 5
    assert distribution.p95_ns == 10
    assert distribution.p99_ns == 10
    assert distribution.max_ns == 10


def test_build_evidence_binds_policy_hardware_runtime_and_warm_state() -> None:
    policy = _policy()
    evidence = build_benchmark_evidence(
        code_sha="a" * 40,
        policy=policy,
        hardware_profile_ref="hw:test",
        runtime_profile_ref="runtime:test",
        warm=True,
        approved_samples=(10, 20),
        rejected_samples=(5, 7),
        candidate_to_handoff_samples=(30, 40),
        audit_samples=(3, 4),
        breach_counts={"riskgate_total": 0},
        sample_method_ref="method:test",
    )
    assert evidence.policy_ref == policy.reference
    assert evidence.warm is True
    assert evidence.production_eligible is False
    assert json.loads(evidence.to_json())["code_sha"] == "a" * 40


def test_benchmark_evidence_rejects_runtime_or_hardware_mismatch() -> None:
    policy = _policy()
    with pytest.raises(ValueError, match="hardware"):
        build_benchmark_evidence(
            code_sha="a" * 40, policy=policy, hardware_profile_ref="hw:other",
            runtime_profile_ref="runtime:test", warm=True,
            approved_samples=(1,), rejected_samples=(1,),
            candidate_to_handoff_samples=(1,), audit_samples=(1,),
            breach_counts={}, sample_method_ref="method:test",
        )
    with pytest.raises(ValueError, match="runtime"):
        build_benchmark_evidence(
            code_sha="a" * 40, policy=policy, hardware_profile_ref="hw:test",
            runtime_profile_ref="runtime:other", warm=True,
            approved_samples=(1,), rejected_samples=(1,),
            candidate_to_handoff_samples=(1,), audit_samples=(1,),
            breach_counts={}, sample_method_ref="method:test",
        )


def test_only_approved_policy_with_matching_evidence_can_be_production_eligible() -> None:
    approved = _policy(LatencyPolicyStatus.APPROVED)
    evidence = build_benchmark_evidence(
        code_sha="b" * 40, policy=approved, hardware_profile_ref="hw:test",
        runtime_profile_ref="runtime:test", warm=True,
        approved_samples=(1,), rejected_samples=(1,),
        candidate_to_handoff_samples=(1,), audit_samples=(1,),
        breach_counts={}, sample_method_ref="method:test",
    )
    assert evidence.production_eligible is True
