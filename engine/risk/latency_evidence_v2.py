"""Monotonic, non-authorizing latency evidence for RiskGateV2."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Protocol


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field)


def _non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be int")
    if value < 0:
        raise ValueError(f"{field} must be non-negative")
    return value


class RiskLatencyStage(str, Enum):
    RISK_GATE_ENTER = "RISK_GATE_ENTER"
    SNAPSHOT_LOADED = "SNAPSHOT_LOADED"
    CHECKS_COMPLETE = "CHECKS_COMPLETE"
    AUDIT_APPEND_COMPLETE = "AUDIT_APPEND_COMPLETE"
    DECISION_FINALIZED = "DECISION_FINALIZED"
    TRANSPORT_HANDOFF = "TRANSPORT_HANDOFF"


_STAGE_ORDER = {stage: index for index, stage in enumerate(RiskLatencyStage)}


@dataclass(frozen=True, slots=True)
class RiskGateLatencyRecord:
    intent_id: str
    risk_snapshot_id: str | None
    latency_policy_ref: str | None
    stage_timestamps_ns: Mapping[RiskLatencyStage, int]
    decision_kind: str
    audit_result: str
    rejection_reason: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "intent_id", _text(self.intent_id, "intent_id"))
        object.__setattr__(self, "risk_snapshot_id", _optional_text(self.risk_snapshot_id, "risk_snapshot_id"))
        object.__setattr__(self, "latency_policy_ref", _optional_text(self.latency_policy_ref, "latency_policy_ref"))
        if not isinstance(self.stage_timestamps_ns, Mapping) or not self.stage_timestamps_ns:
            raise ValueError("stage_timestamps_ns must be a non-empty mapping")
        normalized: dict[RiskLatencyStage, int] = {}
        for stage, value in self.stage_timestamps_ns.items():
            if not isinstance(stage, RiskLatencyStage):
                raise TypeError("latency stage keys must be RiskLatencyStage")
            normalized[stage] = _non_negative_int(value, f"stage_timestamps_ns[{stage.value}]")
        ordered = sorted(normalized.items(), key=lambda item: _STAGE_ORDER[item[0]])
        previous: int | None = None
        for _, value in ordered:
            if previous is not None and value < previous:
                raise ValueError("latency stage timestamps must be monotonic")
            previous = value
        object.__setattr__(self, "stage_timestamps_ns", MappingProxyType(normalized))
        decision = _text(self.decision_kind, "decision_kind").upper()
        audit_result = _text(self.audit_result, "audit_result").upper()
        rejection = _optional_text(self.rejection_reason, "rejection_reason")
        if decision == "REJECTED" and rejection is None:
            raise ValueError("REJECTED latency record requires rejection_reason")
        object.__setattr__(self, "decision_kind", decision)
        object.__setattr__(self, "audit_result", audit_result)
        object.__setattr__(self, "rejection_reason", rejection)

    def duration_ns(self, start: RiskLatencyStage, end: RiskLatencyStage) -> int:
        if not isinstance(start, RiskLatencyStage) or not isinstance(end, RiskLatencyStage):
            raise TypeError("start/end must be RiskLatencyStage")
        if start not in self.stage_timestamps_ns or end not in self.stage_timestamps_ns:
            raise KeyError("requested latency stage is not present")
        return self.stage_timestamps_ns[end] - self.stage_timestamps_ns[start]


class RiskLatencySink(Protocol):
    def record(self, record: RiskGateLatencyRecord) -> None: ...


__all__ = ["RiskGateLatencyRecord", "RiskLatencySink", "RiskLatencyStage"]
