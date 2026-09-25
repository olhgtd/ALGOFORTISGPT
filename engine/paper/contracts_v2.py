"""Pure Phase-5 paper-domain contracts.

This module is intentionally stdlib-only and has no persistence, network,
Windows, live, or broker-adapter dependency.  It models owned paper state and
recovery evidence; it does not authorize execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
import re


_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class PaperMode(str, Enum):
    PAPER = "PAPER"


class PaperOperationalState(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    HALTED = "HALTED"
    RECOVERY = "RECOVERY"
    READY_FOR_RESUME = "READY_FOR_RESUME"


class FailureSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, field)


def _require_aware(value: object, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value


def _optional_aware(value: object, field: str) -> datetime | None:
    if value is None:
        return None
    return _require_aware(value, field)


def _require_decimal(value: object, field: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field} must be a Decimal")
    if not value.is_finite():
        raise ValueError(f"{field} must be finite")
    return value


def _require_positive_decimal(value: object, field: str) -> Decimal:
    result = _require_decimal(value, field)
    if result <= 0:
        raise ValueError(f"{field} must be positive")
    return result


def _require_non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be an int")
    if value < 0:
        raise ValueError(f"{field} must be non-negative")
    return value


def _require_positive_int(value: object, field: str) -> int:
    result = _require_non_negative_int(value, field)
    if result == 0:
        raise ValueError(f"{field} must be positive")
    return result


def _require_state(value: object, field: str) -> PaperOperationalState:
    if not isinstance(value, PaperOperationalState):
        raise TypeError(f"{field} must be PaperOperationalState")
    return value


def _require_severity(value: object) -> FailureSeverity:
    if not isinstance(value, FailureSeverity):
        raise TypeError("severity must be FailureSeverity")
    return value


def _require_mode(value: object) -> PaperMode:
    if not isinstance(value, PaperMode):
        raise TypeError("mode must be PaperMode")
    return value


def _require_text_tuple(value: object, field: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"{field} must be a tuple")
    normalized = tuple(_require_text(item, field) for item in value)
    if not allow_empty and not normalized:
        raise ValueError(f"{field} must not be empty")
    return normalized


def _require_fingerprint(value: object, field: str) -> str:
    text = _require_text(value, field)
    if not _HEX64.fullmatch(text):
        raise ValueError(f"{field} must be lowercase 64-character hex")
    return text


@dataclass(frozen=True, slots=True)
class PaperSession:
    session_id: str
    mode: PaperMode
    started_at: datetime
    trading_date: str
    session_state: PaperOperationalState
    config_snapshot_ref: str
    strategy_versions: tuple[str, ...]
    risk_policy_version: str
    instrument_master_version: str
    failure_policy_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _require_text(self.session_id, "session_id"))
        object.__setattr__(self, "mode", _require_mode(self.mode))
        object.__setattr__(self, "started_at", _require_aware(self.started_at, "started_at"))
        object.__setattr__(self, "trading_date", _require_text(self.trading_date, "trading_date"))
        object.__setattr__(self, "session_state", _require_state(self.session_state, "session_state"))
        object.__setattr__(self, "config_snapshot_ref", _require_text(self.config_snapshot_ref, "config_snapshot_ref"))
        object.__setattr__(self, "strategy_versions", _require_text_tuple(self.strategy_versions, "strategy_versions", allow_empty=False))
        object.__setattr__(self, "risk_policy_version", _require_text(self.risk_policy_version, "risk_policy_version"))
        object.__setattr__(self, "instrument_master_version", _require_text(self.instrument_master_version, "instrument_master_version"))
        object.__setattr__(self, "failure_policy_version", _require_text(self.failure_policy_version, "failure_policy_version"))


@dataclass(frozen=True, slots=True)
class PaperOrderRecord:
    logical_intent_id: str
    approved_order_id: str
    instrument: str
    side: str
    quantity: Decimal
    lifecycle_state: str
    cumulative_fill: Decimal
    submitted_at: datetime
    last_observed_at: datetime
    last_observation_sequence: int
    terminal_reason: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "logical_intent_id", _require_text(self.logical_intent_id, "logical_intent_id"))
        object.__setattr__(self, "approved_order_id", _require_text(self.approved_order_id, "approved_order_id"))
        object.__setattr__(self, "instrument", _require_text(self.instrument, "instrument"))
        object.__setattr__(self, "side", _require_text(self.side, "side"))
        quantity = _require_positive_decimal(self.quantity, "quantity")
        fill = _require_decimal(self.cumulative_fill, "cumulative_fill")
        if fill < 0 or fill > quantity:
            raise ValueError("cumulative_fill must be between zero and quantity")
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "cumulative_fill", fill)
        object.__setattr__(self, "lifecycle_state", _require_text(self.lifecycle_state, "lifecycle_state"))
        object.__setattr__(self, "submitted_at", _require_aware(self.submitted_at, "submitted_at"))
        object.__setattr__(self, "last_observed_at", _require_aware(self.last_observed_at, "last_observed_at"))
        object.__setattr__(self, "last_observation_sequence", _require_non_negative_int(self.last_observation_sequence, "last_observation_sequence"))
        object.__setattr__(self, "terminal_reason", _optional_text(self.terminal_reason, "terminal_reason"))


@dataclass(frozen=True, slots=True)
class PaperPositionRecord:
    position_id: str
    instrument: str
    quantity: Decimal
    average_price: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    protective_policy_ref: str
    protective_state: str
    expiry_metadata: str
    session_metadata: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "position_id", _require_text(self.position_id, "position_id"))
        object.__setattr__(self, "instrument", _require_text(self.instrument, "instrument"))
        object.__setattr__(self, "quantity", _require_positive_decimal(self.quantity, "quantity"))
        object.__setattr__(self, "average_price", _require_decimal(self.average_price, "average_price"))
        object.__setattr__(self, "realized_pnl", _require_decimal(self.realized_pnl, "realized_pnl"))
        object.__setattr__(self, "unrealized_pnl", _require_decimal(self.unrealized_pnl, "unrealized_pnl"))
        object.__setattr__(self, "protective_policy_ref", _require_text(self.protective_policy_ref, "protective_policy_ref"))
        object.__setattr__(self, "protective_state", _require_text(self.protective_state, "protective_state"))
        object.__setattr__(self, "expiry_metadata", _require_text(self.expiry_metadata, "expiry_metadata"))
        object.__setattr__(self, "session_metadata", _require_text(self.session_metadata, "session_metadata"))


@dataclass(frozen=True, slots=True)
class RecoveryCheckpoint:
    checkpoint_id: str
    session_id: str
    persisted_at: datetime
    last_event_sequence: int
    open_order_refs: tuple[str, ...]
    open_position_refs: tuple[str, ...]
    recovery_required: bool
    reason: str
    fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "checkpoint_id", _require_text(self.checkpoint_id, "checkpoint_id"))
        object.__setattr__(self, "session_id", _require_text(self.session_id, "session_id"))
        object.__setattr__(self, "persisted_at", _require_aware(self.persisted_at, "persisted_at"))
        object.__setattr__(self, "last_event_sequence", _require_non_negative_int(self.last_event_sequence, "last_event_sequence"))
        object.__setattr__(self, "open_order_refs", _require_text_tuple(self.open_order_refs, "open_order_refs"))
        object.__setattr__(self, "open_position_refs", _require_text_tuple(self.open_position_refs, "open_position_refs"))
        if not isinstance(self.recovery_required, bool):
            raise TypeError("recovery_required must be bool")
        object.__setattr__(self, "reason", _require_text(self.reason, "reason"))
        object.__setattr__(self, "fingerprint", _require_fingerprint(self.fingerprint, "fingerprint"))


@dataclass(frozen=True, slots=True)
class FailureIncident:
    incident_id: str
    failure_type: str
    severity: FailureSeverity
    detected_at: datetime
    source: str
    affected_scope: str
    previous_state: PaperOperationalState
    resulting_state: PaperOperationalState
    transition_reason: str
    halt_latched: bool
    recovery_id: str | None
    storm_policy_ref: str | None
    resolved_at: datetime | None
    resolution_evidence: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "incident_id", _require_text(self.incident_id, "incident_id"))
        object.__setattr__(self, "failure_type", _require_text(self.failure_type, "failure_type"))
        object.__setattr__(self, "severity", _require_severity(self.severity))
        object.__setattr__(self, "detected_at", _require_aware(self.detected_at, "detected_at"))
        object.__setattr__(self, "source", _require_text(self.source, "source"))
        object.__setattr__(self, "affected_scope", _require_text(self.affected_scope, "affected_scope"))
        object.__setattr__(self, "previous_state", _require_state(self.previous_state, "previous_state"))
        object.__setattr__(self, "resulting_state", _require_state(self.resulting_state, "resulting_state"))
        object.__setattr__(self, "transition_reason", _require_text(self.transition_reason, "transition_reason"))
        if not isinstance(self.halt_latched, bool):
            raise TypeError("halt_latched must be bool")
        object.__setattr__(self, "recovery_id", _optional_text(self.recovery_id, "recovery_id"))
        object.__setattr__(self, "storm_policy_ref", _optional_text(self.storm_policy_ref, "storm_policy_ref"))
        object.__setattr__(self, "resolved_at", _optional_aware(self.resolved_at, "resolved_at"))
        object.__setattr__(self, "resolution_evidence", _optional_text(self.resolution_evidence, "resolution_evidence"))


@dataclass(frozen=True, slots=True)
class AlertDeliveryRecord:
    alert_id: str
    incident_id: str
    channel: str
    attempt: int
    delivery_status: str
    failure_reason: str | None
    attempted_at: datetime
    completed_at: datetime | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "alert_id", _require_text(self.alert_id, "alert_id"))
        object.__setattr__(self, "incident_id", _require_text(self.incident_id, "incident_id"))
        object.__setattr__(self, "channel", _require_text(self.channel, "channel"))
        object.__setattr__(self, "attempt", _require_positive_int(self.attempt, "attempt"))
        object.__setattr__(self, "delivery_status", _require_text(self.delivery_status, "delivery_status"))
        object.__setattr__(self, "failure_reason", _optional_text(self.failure_reason, "failure_reason"))
        object.__setattr__(self, "attempted_at", _require_aware(self.attempted_at, "attempted_at"))
        object.__setattr__(self, "completed_at", _optional_aware(self.completed_at, "completed_at"))


@dataclass(frozen=True, slots=True)
class RecoveryReport:
    recovery_id: str
    trigger: str
    previous_state: PaperOperationalState
    checkpoint_fingerprint: str
    restored_order_refs: tuple[str, ...]
    restored_position_refs: tuple[str, ...]
    reconciliation_result: str
    protective_integrity_result: str
    feed_health: str
    clock_health: str
    session_expiry_validity: str
    unresolved_discrepancies: tuple[str, ...]
    alert_refs: tuple[str, ...]
    final_state: PaperOperationalState
    manual_resume_required: bool
    produced_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "recovery_id", _require_text(self.recovery_id, "recovery_id"))
        object.__setattr__(self, "trigger", _require_text(self.trigger, "trigger"))
        object.__setattr__(self, "previous_state", _require_state(self.previous_state, "previous_state"))
        object.__setattr__(self, "checkpoint_fingerprint", _require_fingerprint(self.checkpoint_fingerprint, "checkpoint_fingerprint"))
        object.__setattr__(self, "restored_order_refs", _require_text_tuple(self.restored_order_refs, "restored_order_refs"))
        object.__setattr__(self, "restored_position_refs", _require_text_tuple(self.restored_position_refs, "restored_position_refs"))
        for field in (
            "reconciliation_result",
            "protective_integrity_result",
            "feed_health",
            "clock_health",
            "session_expiry_validity",
        ):
            object.__setattr__(self, field, _require_text(getattr(self, field), field))
        object.__setattr__(self, "unresolved_discrepancies", _require_text_tuple(self.unresolved_discrepancies, "unresolved_discrepancies"))
        object.__setattr__(self, "alert_refs", _require_text_tuple(self.alert_refs, "alert_refs"))
        object.__setattr__(self, "final_state", _require_state(self.final_state, "final_state"))
        if not isinstance(self.manual_resume_required, bool):
            raise TypeError("manual_resume_required must be bool")
        object.__setattr__(self, "produced_at", _require_aware(self.produced_at, "produced_at"))


@dataclass(frozen=True, slots=True)
class FailureInjectionResult:
    fi_id: str
    fixture_version: str
    starting_state: PaperOperationalState
    injected_event: str
    expected_state: PaperOperationalState
    actual_state: PaperOperationalState
    duplicate_order_count: int
    stale_replay_count: int
    unresolved_mismatch_count: int
    recovery_report_ref: str | None
    alert_evidence_refs: tuple[str, ...]
    passed: bool
    observed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "fi_id", _require_text(self.fi_id, "fi_id"))
        object.__setattr__(self, "fixture_version", _require_text(self.fixture_version, "fixture_version"))
        object.__setattr__(self, "starting_state", _require_state(self.starting_state, "starting_state"))
        object.__setattr__(self, "injected_event", _require_text(self.injected_event, "injected_event"))
        object.__setattr__(self, "expected_state", _require_state(self.expected_state, "expected_state"))
        object.__setattr__(self, "actual_state", _require_state(self.actual_state, "actual_state"))
        object.__setattr__(self, "duplicate_order_count", _require_non_negative_int(self.duplicate_order_count, "duplicate_order_count"))
        object.__setattr__(self, "stale_replay_count", _require_non_negative_int(self.stale_replay_count, "stale_replay_count"))
        object.__setattr__(self, "unresolved_mismatch_count", _require_non_negative_int(self.unresolved_mismatch_count, "unresolved_mismatch_count"))
        object.__setattr__(self, "recovery_report_ref", _optional_text(self.recovery_report_ref, "recovery_report_ref"))
        object.__setattr__(self, "alert_evidence_refs", _require_text_tuple(self.alert_evidence_refs, "alert_evidence_refs"))
        if not isinstance(self.passed, bool):
            raise TypeError("passed must be bool")
        object.__setattr__(self, "observed_at", _require_aware(self.observed_at, "observed_at"))


__all__ = [
    "AlertDeliveryRecord",
    "FailureIncident",
    "FailureInjectionResult",
    "FailureSeverity",
    "PaperMode",
    "PaperOperationalState",
    "PaperOrderRecord",
    "PaperPositionRecord",
    "PaperSession",
    "RecoveryCheckpoint",
    "RecoveryReport",
]
