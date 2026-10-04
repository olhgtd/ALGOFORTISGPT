"""Phase 5 OD-7 Item 11: D16 Versioned Audit and Event Journal Envelope.

Provides:
- AuditEvent: Immutable versioned event envelope for all Phase-5 lifecycle transitions.
- AuditEventFamily & AuditEventType: Approved D16 taxonomy (E1-E20).
- AuditIntegrityError: Fail-closed exception for conflicting event IDs.
- derive_audit_event_id: Deterministic event ID generator for state events and UUID for observations.
- recorded_at_utc_now: Centralized, isolated diagnostic UTC wall-clock helper.
- Canonical JSON serializers and payload helpers for typed audit events.

Durability is provided according to SQLite, operating-system, filesystem,
and storage-device guarantees under WAL + synchronous=FULL.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Sequence

from engine.core.numeric import as_decimal
from engine.portfolio.model import InstrumentIdentity, PositionKey

AUDIT_ENVELOPE_SCHEMA_VERSION = "algofortis-audit-envelope/v2"
AUDIT_PAYLOAD_SCHEMA_VERSION_DEFAULT = "algofortis-payload/v1"

# Phase 6 / ADR §123.1: D16 environment vocabulary. The durable paper/live
# journal populates "paper" and "live" only; "backtest" remains defined by D16
# but is never emitted into this journal (§123.1 item 6, §123.4).
AUDIT_ENVIRONMENT_VOCABULARY: tuple[str, ...] = ("backtest", "paper", "live")


# ======================================================================
# 1. Taxonomy: Families and Event Types (D16 E1–E20)
# ======================================================================

class AuditEventFamily(str, Enum):
    """Approved D16 audit event taxonomy families."""

    SESSION = "SESSION"                                   # D16-E1
    FEED_CONNECTIVITY = "FEED_CONNECTIVITY"               # D16-E2
    STRATEGY_SIGNAL = "STRATEGY_SIGNAL"                   # D16-E3
    OPTION_SELECTION = "OPTION_SELECTION"                 # D16-E4
    ENTRY_INTENT = "ENTRY_INTENT"                         # D16-E5
    RISK_DECISION = "RISK_DECISION"                       # D16-E6
    CAPITAL_RESERVATION = "CAPITAL_RESERVATION"           # D16-E7
    ORDER_LIFECYCLE = "ORDER_LIFECYCLE"                   # D16-E8
    FILL = "FILL"                                         # D16-E9
    ACCOUNTING = "ACCOUNTING"                             # D16-E10
    TRADE_LEDGER = "TRADE_LEDGER"                         # D16-E11
    COST_ASSESSMENT = "COST_ASSESSMENT"                   # D16-E12
    PROTECTIVE_LIFECYCLE = "PROTECTIVE_LIFECYCLE"         # D16-E13
    SAFETY_KILL_SWITCH = "SAFETY_KILL_SWITCH"             # D16-E14
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"           # D16-E15
    ACCOUNTING_INTEGRITY = "ACCOUNTING_INTEGRITY"         # D16-E16
    RESTART_HYDRATION = "RESTART_HYDRATION"               # D16-E17
    ADMIN_CANCELLATION = "ADMIN_CANCELLATION"             # D16-E18
    REJECTION_FAIL_CLOSED = "REJECTION_FAIL_CLOSED"       # D16-E19
    MANUAL_REDUCE_CLOSE = "MANUAL_REDUCE_CLOSE"           # D16-E20
    # Phase 6 / ADR §123.3(d): approved additive family D16-E21. The E1–E20
    # members above are never renamed, renumbered or reordered; this extension
    # is purely additive under the explicit §123.10 supersession scope.
    ERROR = "ERROR"                                       # D16-E21
    # Phase 9 / ADR §131: approved additive family D16-E22.
    # Governed AlgoFortis Phase 9 control-plane mutation lifecycle evidence.
    PHASE9_MUTATION = "PHASE9_MUTATION"                   # D16-E22


class AuditEventType(str, Enum):
    """Granular event types across all D16 families."""

    # E1 SESSION
    SESSION_STARTED = "SESSION_STARTED"
    SESSION_ROLLOVER = "SESSION_ROLLOVER"
    SESSION_CLOSED = "SESSION_CLOSED"

    # E2 FEED_CONNECTIVITY
    FEED_CONNECTED = "FEED_CONNECTED"
    FEED_DISCONNECTED = "FEED_DISCONNECTED"
    FEED_RECONNECTED = "FEED_RECONNECTED"

    # E3 STRATEGY_SIGNAL
    SIGNAL_EMITTED = "SIGNAL_EMITTED"
    SIGNAL_REJECTED_DUPLICATE = "SIGNAL_REJECTED_DUPLICATE"

    # E4 OPTION_SELECTION
    OPTION_SELECTED = "OPTION_SELECTED"
    OPTION_SELECTION_REJECTED = "OPTION_SELECTION_REJECTED"

    # E5 ENTRY_INTENT
    INTENT_CREATED = "INTENT_CREATED"
    INTENT_QUEUED = "INTENT_QUEUED"
    INTENT_SUBMITTED = "INTENT_SUBMITTED"
    INTENT_FILLED = "INTENT_FILLED"
    INTENT_TERMINATED = "INTENT_TERMINATED"
    INTENT_REJECTED = "INTENT_REJECTED"

    # E6 RISK_DECISION
    RISK_EVALUATED_APPROVED = "RISK_EVALUATED_APPROVED"
    RISK_EVALUATED_REJECTED = "RISK_EVALUATED_REJECTED"

    # E7 CAPITAL_RESERVATION
    PREMIUM_RESERVED = "PREMIUM_RESERVED"
    PREMIUM_RELEASED = "PREMIUM_RELEASED"

    # E8 ORDER_LIFECYCLE
    ORDER_QUEUED = "ORDER_QUEUED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    ORDER_EXPIRED = "ORDER_EXPIRED"
    ORDER_REJECTED = "ORDER_REJECTED"

    # E9 FILL
    FILL_EXECUTED = "FILL_EXECUTED"

    # E10 ACCOUNTING
    ACCOUNT_STATE_MUTATED = "ACCOUNT_STATE_MUTATED"
    POSITION_MUTATED = "POSITION_MUTATED"

    # E11 TRADE_LEDGER
    TRADE_OPENED = "TRADE_OPENED"
    TRADE_CLOSED = "TRADE_CLOSED"

    # E12 COST_ASSESSMENT
    COST_ASSESSED = "COST_ASSESSED"

    # E13 PROTECTIVE_LIFECYCLE
    PLAN_RETAINED = "PLAN_RETAINED"
    PROTECTIVE_MATERIALIZED = "PROTECTIVE_MATERIALIZED"
    TRAILING_ACTIVATED = "TRAILING_ACTIVATED"
    TRAILING_RATCHETED = "TRAILING_RATCHETED"
    PROTECTIVE_TRIGGERED = "PROTECTIVE_TRIGGERED"
    PROTECTIVE_CLOSE_QUEUED = "PROTECTIVE_CLOSE_QUEUED"
    PROTECTIVE_CLOSE_CANCELLED_REARMED = "PROTECTIVE_CLOSE_CANCELLED_REARMED"
    PROTECTIVE_FILLED = "PROTECTIVE_FILLED"
    OCO_SIBLINGS_CANCELLED = "OCO_SIBLINGS_CANCELLED"
    PROTECTIVE_TERMINATED = "PROTECTIVE_TERMINATED"
    TARGET_REPLACED = "TARGET_REPLACED"
    # STRATEGY_EXIT provenance: STRATEGY_EXIT_REQUESTED alone (committed
    # atomically with the generic broker_orders close row) plus the canonical
    # ORDER_*/FILL_EXECUTED order lifecycle events provide complete durable
    # provenance. Dedicated SUBMITTED/FILLED variants would duplicate that
    # evidence and were removed as dead event types.
    STRATEGY_EXIT_REQUESTED = "STRATEGY_EXIT_REQUESTED"

    # E14 SAFETY_KILL_SWITCH
    KILL_SWITCH_ACTIVATED = "KILL_SWITCH_ACTIVATED"
    KILL_SWITCH_IDEMPOTENT_REPEAT = "KILL_SWITCH_IDEMPOTENT_REPEAT"
    RESUME_ATTEMPTED = "RESUME_ATTEMPTED"
    RESUME_REJECTED = "RESUME_REJECTED"
    RESUME_SUCCEEDED = "RESUME_SUCCEEDED"

    # E15 PERSISTENCE_FAILURE
    PERSISTENCE_HEALTH_FAILED = "PERSISTENCE_HEALTH_FAILED"

    # E16 ACCOUNTING_INTEGRITY
    ACCOUNTING_INTEGRITY_BREACHED = "ACCOUNTING_INTEGRITY_BREACHED"

    # E17 RESTART_HYDRATION
    RUNTIME_STARTED = "RUNTIME_STARTED"
    STATE_HYDRATED = "STATE_HYDRATED"
    STARTUP_KILL_CLEANUP_COMPLETED = "STARTUP_KILL_CLEANUP_COMPLETED"

    # E18 ADMIN_CANCELLATION
    ADMINISTRATIVE_CANCELLATION_EXECUTED = "ADMINISTRATIVE_CANCELLATION_EXECUTED"

    # E19 REJECTION_FAIL_CLOSED
    STALE_QUOTE_REJECTED = "STALE_QUOTE_REJECTED"
    SESSION_REGRESSION_REJECTED = "SESSION_REGRESSION_REJECTED"
    REJECTION_FAIL_CLOSED = "REJECTION_FAIL_CLOSED"

    # E20 MANUAL_REDUCE_CLOSE
    MANUAL_CLOSE_SUBMITTED = "MANUAL_CLOSE_SUBMITTED"
    MANUAL_CLOSE_REJECTED = "MANUAL_CLOSE_REJECTED"

    # E21 ERROR (ADR §123.3(d)) — observational durable error evidence only
    STRATEGY_EXCEPTION = "STRATEGY_EXCEPTION"
    RUNTIME_ERROR = "RUNTIME_ERROR"

    # E22 PHASE9_MUTATION (ADR §131)
    PHASE9_MUTATION_INTENT = "PHASE9_MUTATION_INTENT"
    PHASE9_MUTATION_APPLIED = "PHASE9_MUTATION_APPLIED"
    PHASE9_MUTATION_REJECTED = "PHASE9_MUTATION_REJECTED"
    PHASE9_MUTATION_FAILED = "PHASE9_MUTATION_FAILED"


class AuditIntegrityError(Exception):
    """Raised when an event_id conflicts with differing immutable semantic payload."""


# ======================================================================
# 1b. Phase 6 (§123.1 item 7): Total status/severity derivation maps
# ======================================================================

# Deterministic TOTAL derivations of envelope `status` and `severity` from
# AuditEventType. Every enum member MUST have an explicit entry; a missing
# entry is a defect and fails closed at import time.
_AUDIT_STATUS_BY_EVENT_TYPE: dict[str, str] = {
    # E1 SESSION
    "SESSION_STARTED": "SUCCESS",
    "SESSION_ROLLOVER": "SUCCESS",
    "SESSION_CLOSED": "SUCCESS",
    # E2 FEED_CONNECTIVITY
    "FEED_CONNECTED": "SUCCESS",
    "FEED_DISCONNECTED": "FAILED",
    "FEED_RECONNECTED": "SUCCESS",
    # E3 STRATEGY_SIGNAL
    "SIGNAL_EMITTED": "SUCCESS",
    "SIGNAL_REJECTED_DUPLICATE": "REJECTED",
    # E4 OPTION_SELECTION
    "OPTION_SELECTED": "SUCCESS",
    "OPTION_SELECTION_REJECTED": "REJECTED",
    # E5 ENTRY_INTENT
    "INTENT_CREATED": "SUCCESS",
    "INTENT_QUEUED": "SUCCESS",
    "INTENT_SUBMITTED": "SUCCESS",
    "INTENT_FILLED": "SUCCESS",
    "INTENT_TERMINATED": "SUCCESS",
    "INTENT_REJECTED": "REJECTED",
    # E6 RISK_DECISION
    "RISK_EVALUATED_APPROVED": "SUCCESS",
    "RISK_EVALUATED_REJECTED": "REJECTED",
    # E7 CAPITAL_RESERVATION
    "PREMIUM_RESERVED": "SUCCESS",
    "PREMIUM_RELEASED": "SUCCESS",
    # E8 ORDER_LIFECYCLE
    "ORDER_QUEUED": "SUCCESS",
    "ORDER_CANCELLED": "CANCELLED",
    "ORDER_EXPIRED": "EXPIRED",
    "ORDER_REJECTED": "REJECTED",
    # E9 FILL
    "FILL_EXECUTED": "SUCCESS",
    # E10 ACCOUNTING
    "ACCOUNT_STATE_MUTATED": "SUCCESS",
    "POSITION_MUTATED": "SUCCESS",
    # E11 TRADE_LEDGER
    "TRADE_OPENED": "SUCCESS",
    "TRADE_CLOSED": "SUCCESS",
    # E12 COST_ASSESSMENT
    "COST_ASSESSED": "SUCCESS",
    # E13 PROTECTIVE_LIFECYCLE
    "PLAN_RETAINED": "SUCCESS",
    "PROTECTIVE_MATERIALIZED": "SUCCESS",
    "TRAILING_ACTIVATED": "SUCCESS",
    "TRAILING_RATCHETED": "SUCCESS",
    "PROTECTIVE_TRIGGERED": "SUCCESS",
    "PROTECTIVE_CLOSE_QUEUED": "SUCCESS",
    "PROTECTIVE_CLOSE_CANCELLED_REARMED": "CANCELLED",
    "PROTECTIVE_FILLED": "SUCCESS",        "OCO_SIBLINGS_CANCELLED": "CANCELLED",
        "PROTECTIVE_TERMINATED": "CANCELLED",
        "TARGET_REPLACED": "SUCCESS",
        "STRATEGY_EXIT_REQUESTED": "SUCCESS",
        # E14 SAFETY_KILL_SWITCH
    "KILL_SWITCH_ACTIVATED": "FAILED",
    "KILL_SWITCH_IDEMPOTENT_REPEAT": "FAILED",
    "RESUME_ATTEMPTED": "SUCCESS",
    "RESUME_REJECTED": "REJECTED",
    "RESUME_SUCCEEDED": "SUCCESS",
    # E15 PERSISTENCE_FAILURE
    "PERSISTENCE_HEALTH_FAILED": "FAILED",
    # E16 ACCOUNTING_INTEGRITY
    "ACCOUNTING_INTEGRITY_BREACHED": "FAILED",
    # E17 RESTART_HYDRATION
    "RUNTIME_STARTED": "SUCCESS",
    "STATE_HYDRATED": "SUCCESS",
    "STARTUP_KILL_CLEANUP_COMPLETED": "SUCCESS",
    # E18 ADMIN_CANCELLATION
    "ADMINISTRATIVE_CANCELLATION_EXECUTED": "CANCELLED",
    # E19 REJECTION_FAIL_CLOSED
    "STALE_QUOTE_REJECTED": "REJECTED",
    "SESSION_REGRESSION_REJECTED": "REJECTED",
    "REJECTION_FAIL_CLOSED": "REJECTED",
    # E20 MANUAL_REDUCE_CLOSE
    "MANUAL_CLOSE_SUBMITTED": "SUCCESS",
    "MANUAL_CLOSE_REJECTED": "REJECTED",
    # E21 ERROR (ADR §123.3(d)) — contained, bounded observational evidence;
    # kill-switch/integrity/persistence paths remain the CRITICAL carriers.
    "STRATEGY_EXCEPTION": "FAILED",
    "RUNTIME_ERROR": "FAILED",
    # E22 PHASE9_MUTATION (ADR §131)
    "PHASE9_MUTATION_INTENT": "SUCCESS",
    "PHASE9_MUTATION_APPLIED": "SUCCESS",
    "PHASE9_MUTATION_REJECTED": "REJECTED",
    "PHASE9_MUTATION_FAILED": "FAILED",
}

_AUDIT_SEVERITY_BY_EVENT_TYPE: dict[str, str] = {
    # E1 SESSION
    "SESSION_STARTED": "INFO",
    "SESSION_ROLLOVER": "INFO",
    "SESSION_CLOSED": "INFO",
    # E2 FEED_CONNECTIVITY
    "FEED_CONNECTED": "INFO",
    "FEED_DISCONNECTED": "WARNING",
    "FEED_RECONNECTED": "INFO",
    # E3 STRATEGY_SIGNAL
    "SIGNAL_EMITTED": "INFO",
    "SIGNAL_REJECTED_DUPLICATE": "WARNING",
    # E4 OPTION_SELECTION
    "OPTION_SELECTED": "INFO",
    "OPTION_SELECTION_REJECTED": "WARNING",
    # E5 ENTRY_INTENT
    "INTENT_CREATED": "INFO",
    "INTENT_QUEUED": "INFO",
    "INTENT_SUBMITTED": "INFO",
    "INTENT_FILLED": "INFO",
    "INTENT_TERMINATED": "INFO",
    "INTENT_REJECTED": "WARNING",
    # E6 RISK_DECISION
    "RISK_EVALUATED_APPROVED": "INFO",
    "RISK_EVALUATED_REJECTED": "WARNING",
    # E7 CAPITAL_RESERVATION
    "PREMIUM_RESERVED": "INFO",
    "PREMIUM_RELEASED": "INFO",
    # E8 ORDER_LIFECYCLE
    "ORDER_QUEUED": "INFO",
    "ORDER_CANCELLED": "INFO",
    "ORDER_EXPIRED": "INFO",
    "ORDER_REJECTED": "WARNING",
    # E9 FILL
    "FILL_EXECUTED": "INFO",
    # E10 ACCOUNTING
    "ACCOUNT_STATE_MUTATED": "INFO",
    "POSITION_MUTATED": "INFO",
    # E11 TRADE_LEDGER
    "TRADE_OPENED": "INFO",
    "TRADE_CLOSED": "INFO",
    # E12 COST_ASSESSMENT
    "COST_ASSESSED": "INFO",
    # E13 PROTECTIVE_LIFECYCLE
    "PLAN_RETAINED": "INFO",
    "PROTECTIVE_MATERIALIZED": "INFO",
    "TRAILING_ACTIVATED": "INFO",
    "TRAILING_RATCHETED": "INFO",
    "PROTECTIVE_TRIGGERED": "INFO",
    "PROTECTIVE_CLOSE_QUEUED": "INFO",
    "PROTECTIVE_CLOSE_CANCELLED_REARMED": "INFO",
    "PROTECTIVE_FILLED": "INFO",        "OCO_SIBLINGS_CANCELLED": "INFO",
        "PROTECTIVE_TERMINATED": "INFO",
        "TARGET_REPLACED": "INFO",
        "STRATEGY_EXIT_REQUESTED": "INFO",
        # E14 SAFETY_KILL_SWITCH
    "KILL_SWITCH_ACTIVATED": "CRITICAL",
    "KILL_SWITCH_IDEMPOTENT_REPEAT": "WARNING",
    "RESUME_ATTEMPTED": "INFO",
    "RESUME_REJECTED": "WARNING",
    "RESUME_SUCCEEDED": "INFO",
    # E15 PERSISTENCE_FAILURE
    "PERSISTENCE_HEALTH_FAILED": "CRITICAL",
    # E16 ACCOUNTING_INTEGRITY
    "ACCOUNTING_INTEGRITY_BREACHED": "CRITICAL",
    # E17 RESTART_HYDRATION
    "RUNTIME_STARTED": "INFO",
    "STATE_HYDRATED": "INFO",
    "STARTUP_KILL_CLEANUP_COMPLETED": "INFO",
    # E18 ADMIN_CANCELLATION
    "ADMINISTRATIVE_CANCELLATION_EXECUTED": "INFO",
    # E19 REJECTION_FAIL_CLOSED
    "STALE_QUOTE_REJECTED": "WARNING",
    "SESSION_REGRESSION_REJECTED": "WARNING",
    "REJECTION_FAIL_CLOSED": "WARNING",
    # E20 MANUAL_REDUCE_CLOSE
    "MANUAL_CLOSE_SUBMITTED": "INFO",
    "MANUAL_CLOSE_REJECTED": "WARNING",
    # E21 ERROR (ADR §123.3(d))
    "STRATEGY_EXCEPTION": "WARNING",
    "RUNTIME_ERROR": "WARNING",
    # E22 PHASE9_MUTATION (ADR §131)
    "PHASE9_MUTATION_INTENT": "INFO",
    "PHASE9_MUTATION_APPLIED": "INFO",
    "PHASE9_MUTATION_REJECTED": "WARNING",
    "PHASE9_MUTATION_FAILED": "CRITICAL",
}


def _assert_total_status_severity_mappings() -> None:
    for _member in AuditEventType:
        if (
            _member.value not in _AUDIT_STATUS_BY_EVENT_TYPE
            or _member.value not in _AUDIT_SEVERITY_BY_EVENT_TYPE
        ):
            raise RuntimeError(
                f"AuditEventType {_member.value!r} has no total status/severity mapping "
                "(§123.1 item 7 — partial coverage is a defect)"
            )


_assert_total_status_severity_mappings()


def derive_audit_status(event_type: str | AuditEventType) -> str:
    """Deterministic total `status` derivation from AuditEventType (§123.1 item 7)."""
    typ = event_type.value if isinstance(event_type, Enum) else str(event_type)
    try:
        return _AUDIT_STATUS_BY_EVENT_TYPE[typ]
    except KeyError as exc:
        raise ValueError(f"Unknown AuditEventType for status derivation: {typ!r}") from exc


def derive_audit_severity(event_type: str | AuditEventType) -> str:
    """Deterministic total `severity` derivation from AuditEventType (§123.1 item 7)."""
    typ = event_type.value if isinstance(event_type, Enum) else str(event_type)
    try:
        return _AUDIT_SEVERITY_BY_EVENT_TYPE[typ]
    except KeyError as exc:
        raise ValueError(f"Unknown AuditEventType for severity derivation: {typ!r}") from exc


# ======================================================================
# 2. Centralized UTC Operational Clock Helper
# ======================================================================

def recorded_at_utc_now() -> datetime:
    """Centralized diagnostic operational UTC wall-clock generator.

    This timestamp is for audit logging observation only.
    It MUST NEVER be used to make trading, sizing, fill, or protective decisions.
    """
    return datetime.now(timezone.utc)


# ======================================================================
# 3. Serialization Helpers
# ======================================================================

def _custom_json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        if not obj.is_finite():
            raise ValueError(f"Non-finite Decimal cannot be serialized to audit JSON: {obj}")
        return str(obj)
    if isinstance(obj, datetime):
        if obj.tzinfo is None or obj.utcoffset() is None:
            raise ValueError(f"Naive datetime cannot be serialized to audit JSON: {obj}")
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (InstrumentIdentity, PositionKey)):
        return obj.to_dict() if hasattr(obj, "to_dict") else dict(obj.__dict__)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable in audit subsystem")


def canonical_json_dumps(data: Mapping[str, Any] | Sequence[Any] | Any) -> str:
    """Deterministic JSON serialization with sorted keys and type checking."""
    return json.dumps(
        data,
        default=_custom_json_default,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )


def compute_payload_fingerprint(payload_json: str | Mapping[str, Any]) -> str:
    """Compute canonical SHA256 fingerprint over payload JSON."""
    if isinstance(payload_json, Mapping):
        encoded = canonical_json_dumps(payload_json).encode("utf-8")
    else:
        # Validate that payload_json is valid JSON
        parsed = json.loads(payload_json)
        encoded = canonical_json_dumps(parsed).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def derive_audit_event_id(
    *,
    event_family: str | AuditEventFamily,
    event_type: str | AuditEventType,
    aggregate_type: str,
    aggregate_identity: str,
    state_generation: int | None = None,
    transaction_event_ordinal: int = 0,
    canonical_domain_identity: str | None = None,
    payload_json: str | Mapping[str, Any] | None = None,
    payload_fingerprint: str | None = None,
) -> str:
    """Derive deterministic collision-free event ID for state events or UUID for observations."""
    fam = event_family.value if isinstance(event_family, Enum) else str(event_family)
    typ = event_type.value if isinstance(event_type, Enum) else str(event_type)

    if state_generation is None and not canonical_domain_identity:
        return str(uuid.uuid4())

    fp = payload_fingerprint
    if fp is None and payload_json is not None:
        fp = compute_payload_fingerprint(payload_json)

    raw = (
        f"{fam}:{typ}:{aggregate_type}:{aggregate_identity}:"
        f"{state_generation}:{transaction_event_ordinal}:"
        f"{canonical_domain_identity or ''}:{fp or ''}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ======================================================================
# 4. Immutable AuditEvent Envelope Model
# ======================================================================

@dataclass(frozen=True)
class AuditEvent:
    """Immutable versioned D16 audit event envelope."""

    event_id: str
    event_family: str
    event_type: str
    aggregate_type: str
    aggregate_identity: str
    recorded_at_utc: datetime
    event_schema_version: str = AUDIT_ENVELOPE_SCHEMA_VERSION
    audit_sequence: int | None = None
    market_timestamp: datetime | None = None
    state_generation: int | None = None
    transaction_event_ordinal: int = 0
    correlation_id: str | None = None
    causation_event_id: str | None = None
    strategy_id: str | None = None
    strategy_version: str | None = None
    instrument_key: str | None = None
    position_key_json: str | None = None
    entry_intent_identity: str | None = None
    broker_order_identity: str | None = None
    trade_id: str | None = None
    protective_id: str | None = None
    payload_version: str = AUDIT_PAYLOAD_SCHEMA_VERSION_DEFAULT
    payload_json: str = "{}"
    # --- Phase 6 / ADR §123.1: seven approved D16 envelope fields (v2) ---
    environment: str | None = None
    run_id: str | None = None
    canonical_configuration_fingerprint: str | None = None
    source_identity: str | None = None
    timeframe: str | None = None
    status: str | None = None
    severity: str | None = None

    def __post_init__(self) -> None:
        if not self.event_id or not self.event_id.strip():
            raise ValueError("event_id must be a non-empty string")
        if self.event_schema_version != AUDIT_ENVELOPE_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported event_schema_version: {self.event_schema_version!r}, "
                f"expected {AUDIT_ENVELOPE_SCHEMA_VERSION!r}"
            )
        if not self.event_family or not self.event_family.strip():
            raise ValueError("event_family must be a non-empty string")
        if not self.event_type or not self.event_type.strip():
            raise ValueError("event_type must be a non-empty string")
        if not self.aggregate_type or not self.aggregate_type.strip():
            raise ValueError("aggregate_type must be a non-empty string")
        if not self.aggregate_identity or not self.aggregate_identity.strip():
            raise ValueError("aggregate_identity must be a non-empty string")

        if not isinstance(self.recorded_at_utc, datetime):
            raise TypeError("recorded_at_utc must be a datetime")
        if self.recorded_at_utc.tzinfo is None or self.recorded_at_utc.utcoffset() != timedelta(0):
            raise ValueError("recorded_at_utc must be a timezone-aware UTC datetime")

        if self.market_timestamp is not None:
            if not isinstance(self.market_timestamp, datetime) or self.market_timestamp.tzinfo is None:
                raise ValueError("market_timestamp must be a timezone-aware datetime when provided")

        if self.state_generation is not None and self.state_generation < 0:
            raise ValueError("state_generation must be non-negative when provided")

        if self.transaction_event_ordinal < 0:
            raise ValueError("transaction_event_ordinal must be non-negative")

        if not self.payload_version or not self.payload_version.strip():
            raise ValueError("payload_version must be a non-empty string")

        # Validate that payload_json is parseable JSON
        try:
            parsed = json.loads(self.payload_json)
            if not isinstance(parsed, dict):
                raise ValueError("payload_json must encode a JSON object (dict)")
        except Exception as exc:
            raise ValueError(f"payload_json must be valid JSON: {exc}") from exc

        # --- Phase 6 / ADR §123.1: v2 envelope field validation ---
        if self.environment is not None:
            if not isinstance(self.environment, str) or self.environment not in AUDIT_ENVIRONMENT_VOCABULARY:
                raise ValueError(
                    f"environment must be one of {AUDIT_ENVIRONMENT_VOCABULARY!r}, got {self.environment!r}"
                )
        # canonical_configuration_fingerprint mirrors its provider
        # (paper_metadata.configuration_identity, P1-06 §120) VERBATIM, so an
        # explicitly-configured empty identity is preserved as "" rather than
        # rejected here; absence/mismatch of the metadata key itself fails
        # closed at store bootstrap (§120 OD-C).
        _cfg_fp = self.canonical_configuration_fingerprint
        if _cfg_fp is not None and not isinstance(_cfg_fp, str):
            raise ValueError("canonical_configuration_fingerprint must be a string when provided")
        for _field in ("run_id", "source_identity", "timeframe"):
            _val = getattr(self, _field)
            if _val is not None and (not isinstance(_val, str) or not _val.strip()):
                raise ValueError(f"{_field} must be a non-empty string when provided")

        # status/severity are total derivations from event_type; explicit
        # values are honored but must be non-empty strings.
        if self.status is None:
            object.__setattr__(self, "status", derive_audit_status(self.event_type))
        elif not isinstance(self.status, str) or not self.status.strip():
            raise ValueError("status must be a non-empty string when provided")
        if self.severity is None:
            object.__setattr__(self, "severity", derive_audit_severity(self.event_type))
        elif not isinstance(self.severity, str) or not self.severity.strip():
            raise ValueError("severity must be a non-empty string when provided")

    def semantic_projection(self) -> tuple[Any, ...]:
        """Full canonical projection for idempotency and conflict comparison.

        Deliberately excludes audit_sequence and recorded_at_utc so that
        replays of deterministic state events compare identically.
        """
        # Parse and re-serialize payload to normalize key order
        norm_payload = canonical_json_dumps(json.loads(self.payload_json))
        market_ts_str = self.market_timestamp.isoformat() if self.market_timestamp else None
        return (
            self.event_schema_version,
            self.event_family,
            self.event_type,
            self.aggregate_type,
            self.aggregate_identity,
            market_ts_str,
            self.state_generation,
            self.transaction_event_ordinal,
            self.correlation_id,
            self.causation_event_id,
            self.strategy_id,
            self.strategy_version,
            self.instrument_key,
            self.position_key_json,
            self.entry_intent_identity,
            self.broker_order_identity,
            self.trade_id,
            self.protective_id,
            self.payload_version,
            norm_payload,
            # --- Phase 6 / ADR §123.1 item 2: all seven v2 fields join the
            # semantic projection; audit_sequence/recorded_at_utc stay excluded.
            self.environment,
            self.run_id,
            self.canonical_configuration_fingerprint,
            self.source_identity,
            self.timeframe,
            self.status,
            self.severity,
        )
