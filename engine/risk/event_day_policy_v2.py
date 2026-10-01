"""Versioned event/expiry entry-risk policy for Phase 7."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _aware(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value


def _decimal(value: object, field: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(f"{field} must be Decimal-compatible without float")
    if not isinstance(value, Decimal):
        try:
            value = Decimal(value)  # type: ignore[arg-type]
        except Exception as exc:
            raise TypeError(f"{field} must be Decimal-compatible") from exc
    if not value.is_finite():
        raise ValueError(f"{field} must be finite")
    if positive and value <= 0:
        raise ValueError(f"{field} must be positive")
    return value


class EventRiskAction(str, Enum):
    NO_TRADE = "NO_TRADE"
    SIZE_CAP = "SIZE_CAP"


@dataclass(frozen=True, slots=True)
class EventRiskWindow:
    window_id: str
    category: str
    start_at: datetime
    end_at: datetime
    action: EventRiskAction
    size_fraction: Decimal | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "window_id", _text(self.window_id, "window_id"))
        object.__setattr__(self, "category", _text(self.category, "category"))
        start = _aware(self.start_at, "start_at")
        end = _aware(self.end_at, "end_at")
        if end <= start:
            raise ValueError("end_at must be later than start_at")
        if not isinstance(self.action, EventRiskAction):
            raise TypeError("action must be EventRiskAction")
        if self.action is EventRiskAction.NO_TRADE:
            if self.size_fraction is not None:
                raise ValueError("NO_TRADE window cannot carry size_fraction")
        else:
            if self.size_fraction is None:
                raise ValueError("SIZE_CAP window requires size_fraction")
            fraction = _decimal(self.size_fraction, "size_fraction", positive=True)
            if fraction > Decimal("1"):
                raise ValueError("size_fraction must be <= 1")
            object.__setattr__(self, "size_fraction", fraction)

    def active_at(self, at: datetime) -> bool:
        return self.start_at <= at < self.end_at


@dataclass(frozen=True, slots=True)
class EventRiskPolicy:
    policy_id: str
    version: str
    windows: tuple[EventRiskWindow, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _text(self.policy_id, "policy_id"))
        object.__setattr__(self, "version", _text(self.version, "version"))
        if not isinstance(self.windows, tuple):
            raise TypeError("windows must be a tuple")
        if not all(isinstance(window, EventRiskWindow) for window in self.windows):
            raise TypeError("windows must contain EventRiskWindow values")
        ids = [window.window_id for window in self.windows]
        if len(ids) != len(set(ids)):
            raise ValueError("window_id values must be unique")

    @property
    def reference(self) -> str:
        return f"{self.policy_id}@{self.version}"


@dataclass(frozen=True, slots=True)
class EventRiskDecision:
    allowed: bool
    reason: str
    policy_ref: str | None
    requested_qty: Decimal
    baseline_qty: Decimal
    max_allowed_qty: Decimal | None
    applied_fraction: Decimal | None
    active_window_ids: tuple[str, ...]


def evaluate_event_risk(
    policy: EventRiskPolicy | None,
    *,
    at: datetime,
    baseline_qty: Decimal,
    requested_qty: Decimal,
) -> EventRiskDecision:
    when = _aware(at, "at")
    baseline = _decimal(baseline_qty, "baseline_qty", positive=True)
    requested = _decimal(requested_qty, "requested_qty", positive=True)
    if policy is None:
        return EventRiskDecision(
            False,
            "EVENT_POLICY_UNAVAILABLE",
            None,
            requested,
            baseline,
            None,
            None,
            (),
        )
    if not isinstance(policy, EventRiskPolicy):
        raise TypeError("policy must be EventRiskPolicy or None")

    active = tuple(
        sorted(
            (window for window in policy.windows if window.active_at(when)),
            key=lambda window: window.window_id,
        )
    )
    active_ids = tuple(window.window_id for window in active)
    if not active:
        return EventRiskDecision(
            True,
            "NO_ACTIVE_EVENT_WINDOW",
            policy.reference,
            requested,
            baseline,
            baseline,
            None,
            (),
        )
    if any(window.action is EventRiskAction.NO_TRADE for window in active):
        return EventRiskDecision(
            False,
            "EVENT_NO_TRADE",
            policy.reference,
            requested,
            baseline,
            Decimal("0"),
            None,
            active_ids,
        )

    fractions = tuple(
        window.size_fraction
        for window in active
        if window.size_fraction is not None
    )
    if not fractions:
        return EventRiskDecision(
            False,
            "EVENT_POLICY_INVALID",
            policy.reference,
            requested,
            baseline,
            None,
            None,
            active_ids,
        )
    fraction = min(fractions)
    maximum = baseline * fraction
    allowed = requested <= maximum
    return EventRiskDecision(
        allowed,
        "EVENT_SIZE_CAP_ACCEPTED" if allowed else "EVENT_SIZE_CAP_EXCEEDED",
        policy.reference,
        requested,
        baseline,
        maximum,
        fraction,
        active_ids,
    )


__all__ = [
    "EventRiskAction",
    "EventRiskDecision",
    "EventRiskPolicy",
    "EventRiskWindow",
    "evaluate_event_risk",
]
