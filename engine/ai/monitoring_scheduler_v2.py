"""Owner-policy-controlled deterministic AI monitoring scheduler.

The scheduler is the sole authority for AI/Laya monitoring scope, cadence,
provider/model assignment and task TTL. Provider/model output cannot widen or
reschedule work through this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum
import re

from .scope_expansion_v2 import ScopeExpansionRequest, ScopeExpansionType

_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _aware(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be int")
    if value <= 0:
        raise ValueError(f"{field} must be positive")
    return value


def _priority(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be int")
    if value < 0:
        raise ValueError(f"{field} must be non-negative")
    return value


def _decimal(value: object, field: str) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be a finite decimal")
    return result


def _enum(value: object, enum_type: type[Enum], field: str):
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} is outside owner policy") from exc


class MonitoringTriggerType(str, Enum):
    SCHEDULED = "SCHEDULED"
    EVENT = "EVENT"
    OWNER = "OWNER"


class MonitoringTaskClass(str, Enum):
    ACTIVE_CANDIDATE_REVIEW = "ACTIVE_CANDIDATE_REVIEW"
    REGIME_EVENT = "REGIME_EVENT"
    SCHEDULED_MONITORING = "SCHEDULED_MONITORING"
    STRATEGY_HUNTING = "STRATEGY_HUNTING"
    LOW_PRIORITY_RESEARCH = "LOW_PRIORITY_RESEARCH"


@dataclass(frozen=True, slots=True)
class MonitoringPolicyV2:
    policy_ref: str
    allowed_instruments: tuple[str, ...]
    frequency_seconds: int
    task_ttl_seconds: int
    provider_id: str
    model_id: str
    policy_version: str = "1.0.0"
    allowed_trigger_types: tuple[MonitoringTriggerType, ...] = (MonitoringTriggerType.SCHEDULED,)
    allowed_task_classes: tuple[MonitoringTaskClass, ...] = (MonitoringTaskClass.SCHEDULED_MONITORING,)
    allowed_timeframes: tuple[str, ...] = ("5m",)
    strategy_review_mode: str = "OPTIONAL"
    independent_candidate_scan: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_ref", _text(self.policy_ref, "policy_ref"))
        if not isinstance(self.allowed_instruments, tuple) or not self.allowed_instruments:
            raise ValueError("allowed_instruments must be a non-empty tuple")
        normalized = tuple(_text(item, "allowed_instrument") for item in self.allowed_instruments)
        if len(set(normalized)) != len(normalized):
            raise ValueError("allowed_instruments must be unique")
        object.__setattr__(self, "allowed_instruments", normalized)
        object.__setattr__(self, "frequency_seconds", _positive_int(self.frequency_seconds, "frequency_seconds"))
        object.__setattr__(self, "task_ttl_seconds", _positive_int(self.task_ttl_seconds, "task_ttl_seconds"))
        object.__setattr__(self, "provider_id", _text(self.provider_id, "provider_id"))
        object.__setattr__(self, "model_id", _text(self.model_id, "model_id"))
        version = _text(self.policy_version, "policy_version")
        if _SEMVER.fullmatch(version) is None:
            raise ValueError("policy_version must be semantic version")
        object.__setattr__(self, "policy_version", version)
        if not isinstance(self.allowed_trigger_types, tuple) or not self.allowed_trigger_types or any(not isinstance(x, MonitoringTriggerType) for x in self.allowed_trigger_types):
            raise ValueError("allowed_trigger_types must be non-empty MonitoringTriggerType tuple")
        if not isinstance(self.allowed_task_classes, tuple) or not self.allowed_task_classes or any(not isinstance(x, MonitoringTaskClass) for x in self.allowed_task_classes):
            raise ValueError("allowed_task_classes must be non-empty MonitoringTaskClass tuple")
        if not isinstance(self.allowed_timeframes, tuple) or not self.allowed_timeframes:
            raise ValueError("allowed_timeframes must be non-empty tuple")
        object.__setattr__(self, "allowed_timeframes", tuple(_text(x, "timeframe") for x in self.allowed_timeframes))
        mode = _text(self.strategy_review_mode, "strategy_review_mode").upper()
        if mode not in {"OPTIONAL", "PREFERRED", "REQUIRED"}:
            raise ValueError("strategy_review_mode invalid")
        object.__setattr__(self, "strategy_review_mode", mode)
        if not isinstance(self.independent_candidate_scan, bool):
            raise TypeError("independent_candidate_scan must be bool")


MarketWatchPolicyV2 = MonitoringPolicyV2


@dataclass(frozen=True, slots=True)
class MonitoringTaskV2:
    task_id: str
    instrument: str
    provider_id: str
    model_id: str
    scheduled_for: datetime
    expires_at: datetime
    hard_eligible: bool
    portfolio_priority: int
    strategy_priority: int
    edge_quality: Decimal | int | str
    capital_efficiency: Decimal | int | str
    signal_at: datetime
    policy_ref: str
    policy_version: str = "1.0.0"
    trigger_type: MonitoringTriggerType = MonitoringTriggerType.SCHEDULED
    task_class: MonitoringTaskClass = MonitoringTaskClass.SCHEDULED_MONITORING
    timeframe: str = "5m"

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _text(self.task_id, "task_id"))
        object.__setattr__(self, "instrument", _text(self.instrument, "instrument"))
        object.__setattr__(self, "provider_id", _text(self.provider_id, "provider_id"))
        object.__setattr__(self, "model_id", _text(self.model_id, "model_id"))
        scheduled = _aware(self.scheduled_for, "scheduled_for")
        expires = _aware(self.expires_at, "expires_at")
        if expires <= scheduled:
            raise ValueError("expires_at must be after scheduled_for")
        if not isinstance(self.hard_eligible, bool):
            raise TypeError("hard_eligible must be bool")
        object.__setattr__(self, "portfolio_priority", _priority(self.portfolio_priority, "portfolio_priority"))
        object.__setattr__(self, "strategy_priority", _priority(self.strategy_priority, "strategy_priority"))
        object.__setattr__(self, "edge_quality", _decimal(self.edge_quality, "edge_quality"))
        object.__setattr__(self, "capital_efficiency", _decimal(self.capital_efficiency, "capital_efficiency"))
        object.__setattr__(self, "signal_at", _aware(self.signal_at, "signal_at"))
        object.__setattr__(self, "policy_ref", _text(self.policy_ref, "policy_ref"))
        object.__setattr__(self, "policy_version", _text(self.policy_version, "policy_version"))
        if not isinstance(self.trigger_type, MonitoringTriggerType):
            raise TypeError("trigger_type must be MonitoringTriggerType")
        if not isinstance(self.task_class, MonitoringTaskClass):
            raise TypeError("task_class must be MonitoringTaskClass")
        object.__setattr__(self, "timeframe", _text(self.timeframe, "timeframe"))


class MonitoringSchedulerV2:
    """Creates immutable monitoring work only from one Owner-supplied policy."""

    def __init__(self, policy: MonitoringPolicyV2) -> None:
        if not isinstance(policy, MonitoringPolicyV2):
            raise TypeError("policy must be MonitoringPolicyV2")
        self._policy = policy

    @property
    def policy(self) -> MonitoringPolicyV2:
        return self._policy

    def next_run(self, after: datetime) -> datetime:
        value = _aware(after, "after")
        return value + timedelta(seconds=self._policy.frequency_seconds)

    def schedule(
        self,
        *,
        task_id: str,
        instrument: str,
        scheduled_for: datetime,
        hard_eligible: bool,
        portfolio_priority: int,
        strategy_priority: int,
        edge_quality: Decimal | int | str,
        capital_efficiency: Decimal | int | str,
        signal_at: datetime,
        trigger_type: MonitoringTriggerType | str | None = None,
        task_class: MonitoringTaskClass | str | None = None,
        timeframe: str | None = None,
    ) -> MonitoringTaskV2:
        normalized_instrument = _text(instrument, "instrument")
        if normalized_instrument not in self._policy.allowed_instruments:
            raise ValueError("instrument is outside owner monitoring policy")
        scheduled = _aware(scheduled_for, "scheduled_for")
        trigger = _enum(trigger_type or self._policy.allowed_trigger_types[0], MonitoringTriggerType, "trigger")
        if trigger not in self._policy.allowed_trigger_types:
            raise ValueError("trigger is outside owner policy")
        task_kind = _enum(task_class or self._policy.allowed_task_classes[0], MonitoringTaskClass, "task class")
        if task_kind not in self._policy.allowed_task_classes:
            raise ValueError("task class is outside owner policy")
        frame = _text(timeframe or self._policy.allowed_timeframes[0], "timeframe")
        if frame not in self._policy.allowed_timeframes:
            raise ValueError("timeframe is outside owner policy")
        return MonitoringTaskV2(
            task_id=task_id,
            instrument=normalized_instrument,
            provider_id=self._policy.provider_id,
            model_id=self._policy.model_id,
            scheduled_for=scheduled,
            expires_at=scheduled + timedelta(seconds=self._policy.task_ttl_seconds),
            hard_eligible=hard_eligible,
            portfolio_priority=portfolio_priority,
            strategy_priority=strategy_priority,
            edge_quality=edge_quality,
            capital_efficiency=capital_efficiency,
            signal_at=signal_at,
            policy_ref=self._policy.policy_ref,
            policy_version=self._policy.policy_version,
            trigger_type=trigger,
            task_class=task_kind,
            timeframe=frame,
        )


__all__ = [
    "MarketWatchPolicyV2",
    "MonitoringPolicyV2",
    "MonitoringSchedulerV2",
    "MonitoringTaskClass",
    "MonitoringTaskV2",
    "MonitoringTriggerType",
    "ScopeExpansionRequest",
    "ScopeExpansionType",
]
