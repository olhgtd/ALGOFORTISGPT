"""Versioned RiskGate latency policy contracts.

Production latency ceilings are never defined in source.  Callers must supply
an explicit versioned policy backed by qualification evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field)


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be an int")
    if value <= 0:
        raise ValueError(f"{field} must be positive")
    return value


class LatencyPolicyStatus(str, Enum):
    TEST_ONLY = "TEST_ONLY"
    CALIBRATION = "CALIBRATION"
    APPROVED = "APPROVED"


@dataclass(frozen=True, slots=True)
class LatencyStagePolicy:
    stage_name: str
    percentile_target: str
    ceiling_ns: int
    breach_action: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage_name", _text(self.stage_name, "stage_name"))
        object.__setattr__(self, "percentile_target", _text(self.percentile_target, "percentile_target").lower())
        object.__setattr__(self, "ceiling_ns", _positive_int(self.ceiling_ns, "ceiling_ns"))
        object.__setattr__(self, "breach_action", _text(self.breach_action, "breach_action").upper())


@dataclass(frozen=True, slots=True)
class RiskGateLatencyPolicy:
    policy_id: str
    version: str
    status: LatencyPolicyStatus
    environment_scope: str
    hardware_profile_ref: str
    runtime_profile_ref: str
    sample_minimum_ref: str
    stages: tuple[LatencyStagePolicy, ...]
    evidence_bundle_ref: str | None = None
    approval_ref: str | None = None

    def __post_init__(self) -> None:
        policy_id = _text(self.policy_id, "policy_id")
        version = _text(self.version, "version")
        if not isinstance(self.status, LatencyPolicyStatus):
            raise TypeError("status must be LatencyPolicyStatus")
        if not isinstance(self.stages, tuple) or not self.stages:
            raise ValueError("stages must be a non-empty tuple")
        normalized_stages: list[LatencyStagePolicy] = []
        seen: set[str] = set()
        for stage in self.stages:
            if not isinstance(stage, LatencyStagePolicy):
                raise TypeError("stages must contain LatencyStagePolicy values")
            if stage.stage_name in seen:
                raise ValueError(f"duplicate latency stage: {stage.stage_name}")
            seen.add(stage.stage_name)
            normalized_stages.append(stage)

        evidence = _optional_text(self.evidence_bundle_ref, "evidence_bundle_ref")
        approval = _optional_text(self.approval_ref, "approval_ref")
        if self.status is LatencyPolicyStatus.TEST_ONLY and not policy_id.startswith("TEST_ONLY/"):
            raise ValueError("TEST_ONLY policy_id must start with TEST_ONLY/")
        if self.status is LatencyPolicyStatus.APPROVED:
            if evidence is None:
                raise ValueError("APPROVED policy requires evidence_bundle_ref")
            if approval is None:
                raise ValueError("APPROVED policy requires approval_ref")

        object.__setattr__(self, "policy_id", policy_id)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "environment_scope", _text(self.environment_scope, "environment_scope"))
        object.__setattr__(self, "hardware_profile_ref", _text(self.hardware_profile_ref, "hardware_profile_ref"))
        object.__setattr__(self, "runtime_profile_ref", _text(self.runtime_profile_ref, "runtime_profile_ref"))
        object.__setattr__(self, "sample_minimum_ref", _text(self.sample_minimum_ref, "sample_minimum_ref"))
        object.__setattr__(self, "stages", tuple(normalized_stages))
        object.__setattr__(self, "evidence_bundle_ref", evidence)
        object.__setattr__(self, "approval_ref", approval)

    @property
    def reference(self) -> str:
        return f"{self.policy_id}@{self.version}"

    def stage(self, name: str) -> LatencyStagePolicy:
        wanted = _text(name, "name")
        for stage in self.stages:
            if stage.stage_name == wanted:
                return stage
        raise KeyError(wanted)


__all__ = [
    "LatencyPolicyStatus",
    "LatencyStagePolicy",
    "RiskGateLatencyPolicy",
]
