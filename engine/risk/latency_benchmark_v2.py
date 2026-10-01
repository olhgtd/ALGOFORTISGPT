"""Evidence model for RiskGate fast-path benchmark/calibration runs."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import ceil
import json
from typing import Mapping, Sequence

from engine.risk.latency_policy_v2 import LatencyPolicyStatus, RiskGateLatencyPolicy


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _samples(values: Sequence[int], field: str) -> tuple[int, ...]:
    if not isinstance(values, Sequence) or not values:
        raise ValueError(f"{field} must contain at least one sample")
    normalized: list[int] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{field} samples must be ints")
        if value < 0:
            raise ValueError(f"{field} samples must be non-negative")
        normalized.append(value)
    return tuple(normalized)


def _nearest_rank(sorted_values: tuple[int, ...], percentile: int) -> int:
    rank = max(1, ceil((percentile / 100) * len(sorted_values)))
    return sorted_values[rank - 1]


@dataclass(frozen=True, slots=True)
class LatencyDistribution:
    sample_count: int
    p50_ns: int
    p95_ns: int
    p99_ns: int
    max_ns: int

    @classmethod
    def from_samples(cls, values: Sequence[int]) -> "LatencyDistribution":
        samples = tuple(sorted(_samples(values, "values")))
        return cls(
            sample_count=len(samples),
            p50_ns=_nearest_rank(samples, 50),
            p95_ns=_nearest_rank(samples, 95),
            p99_ns=_nearest_rank(samples, 99),
            max_ns=samples[-1],
        )


@dataclass(frozen=True, slots=True)
class RiskGateBenchmarkEvidence:
    code_sha: str
    policy_ref: str
    hardware_profile_ref: str
    runtime_profile_ref: str
    warm: bool
    approved_distribution: LatencyDistribution
    rejected_distribution: LatencyDistribution
    candidate_to_handoff_distribution: LatencyDistribution
    audit_distribution: LatencyDistribution
    breach_counts: Mapping[str, int]
    sample_method_ref: str
    production_eligible: bool

    def to_json(self) -> str:
        payload = asdict(self)
        payload["breach_counts"] = dict(sorted(self.breach_counts.items()))
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def build_benchmark_evidence(
    *,
    code_sha: str,
    policy: RiskGateLatencyPolicy,
    hardware_profile_ref: str,
    runtime_profile_ref: str,
    warm: bool,
    approved_samples: Sequence[int],
    rejected_samples: Sequence[int],
    candidate_to_handoff_samples: Sequence[int],
    audit_samples: Sequence[int],
    breach_counts: Mapping[str, int],
    sample_method_ref: str,
) -> RiskGateBenchmarkEvidence:
    code_sha = _text(code_sha, "code_sha").lower()
    if len(code_sha) != 40 or any(ch not in "0123456789abcdef" for ch in code_sha):
        raise ValueError("code_sha must be lowercase 40-character hex")
    if not isinstance(policy, RiskGateLatencyPolicy):
        raise TypeError("policy must be RiskGateLatencyPolicy")
    hardware = _text(hardware_profile_ref, "hardware_profile_ref")
    runtime = _text(runtime_profile_ref, "runtime_profile_ref")
    if hardware != policy.hardware_profile_ref:
        raise ValueError("hardware profile does not match latency policy")
    if runtime != policy.runtime_profile_ref:
        raise ValueError("runtime profile does not match latency policy")
    if not isinstance(warm, bool):
        raise TypeError("warm must be bool")
    normalized_breaches: dict[str, int] = {}
    for key, value in dict(breach_counts).items():
        name = _text(key, "breach_counts key")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("breach counts must be non-negative integers")
        normalized_breaches[name] = value
    production_eligible = (
        policy.status is LatencyPolicyStatus.APPROVED
        and policy.evidence_bundle_ref is not None
        and policy.approval_ref is not None
        and all(count == 0 for count in normalized_breaches.values())
    )
    return RiskGateBenchmarkEvidence(
        code_sha=code_sha,
        policy_ref=policy.reference,
        hardware_profile_ref=hardware,
        runtime_profile_ref=runtime,
        warm=warm,
        approved_distribution=LatencyDistribution.from_samples(approved_samples),
        rejected_distribution=LatencyDistribution.from_samples(rejected_samples),
        candidate_to_handoff_distribution=LatencyDistribution.from_samples(candidate_to_handoff_samples),
        audit_distribution=LatencyDistribution.from_samples(audit_samples),
        breach_counts=normalized_breaches,
        sample_method_ref=_text(sample_method_ref, "sample_method_ref"),
        production_eligible=production_eligible,
    )


__all__ = [
    "LatencyDistribution",
    "RiskGateBenchmarkEvidence",
    "build_benchmark_evidence",
]
