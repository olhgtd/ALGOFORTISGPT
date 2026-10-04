"""SQLite Atomic and Fail-Closed Persistence Store for AlgoFortis Phase 5.

Implements the single authoritative relational persistence engine for:
- VirtualPaperAccount financial truth & commitments
- SimulatedPaperBroker orders & event-time watermarks
- ProtectiveExitBook & LiveProtectiveEvaluator pending closes
- TradeLedger lifecycles & CostAssessments
- RiskGateState & entry-intent lifecycle deduplication

Zero pickle. Strict Decimals as canonical TEXT. Strict timezone-aware datetimes.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
import json
import logging
import hashlib
import importlib
import math
from pathlib import Path
import sqlite3
from typing import Any, Iterator, Mapping, Sequence
import uuid

from engine.audit.model import (
    AUDIT_ENVELOPE_SCHEMA_VERSION,
    AuditEvent,
    AuditEventFamily,
    AuditEventType,
    AuditIntegrityError,
    canonical_json_dumps,
    derive_audit_event_id,
    recorded_at_utc_now,
)

from engine.costs.model import (
    CostAssessment,
    CostBasis,
    CostComponentResult,
    ScheduleReference,
    assessment_identity,
    trade_evidence_fingerprint,
)
from engine.execution.model import ExecutionOutcome, ExecutionResult
from engine.execution.paper_broker import (
    BrokerOrderRecord,
    BrokerTerminalEvent,
    ExecutionEvaluationContext,
    OrderLifecycleState,
    PaperFillAdapter,
    SimulatedPaperBroker,
    _PendingOrder,
)
from engine.data.feeds.live_feed import SubscriptionOwnerKey
from engine.orders.model import (
    ConcreteCloseInstruction,
    ConcreteOpenInstruction,
    OrderRequest,
    OrderType,
    TimeInForce,
)
from engine.persistence.schema import CREATE_TABLES_SQL, PRAGMA_STATEMENTS, SCHEMA_VERSION
from engine.portfolio.accounting import AccountingOutcome, AccountingResult
from engine.portfolio.model import (
    AccountSnapshot,
    InstrumentIdentity,
    InstrumentSpecification,
    PositionKey,
    PositionSnapshot,
)

from engine.portfolio.virtual_account import PremiumCommitmentRecord
from engine.protective.runtime import ProtectiveExit, ProtectiveExitKind, ProtectiveExitState, TrailingStopState
from engine.protective.live import LiveProtectivePendingClose
from engine.protective.plan import PreEntryProtectivePlan, TrailingProtectionSpec
from engine.paper.promotion_tracking import (
    PromotionTrackingState,
    PromotionSessionRecord,
    PromotionTrackingStatus,
    PromotionSessionStatus,
    PromotionMilestoneStatus,
)
from engine.reproducibility.codec import CanonicalCodec
from engine.risk.risk_manager import (
    PendingRiskCommitment,
    RiskDay,
    RiskGateState,
)
from engine.reconciliation.paper.engine import (

    ReconciliationFinding,
    ReconciliationPersistedSnapshot,
    ReconciliationReport,
    ReconciliationSeverity,
    ReconciliationStatus,
)
from engine.safety.safety import KillSwitchState
from engine.orchestration.signal_intake import SignalIntent
from engine.trades.ledger import TradeLedger, _Pending
from engine.trades.model import LedgerEventKey, TradeLeg, TradeRecord, TradeRole, TradeStatus

logger = logging.getLogger(__name__)


# ======================================================================
# Persistence Health & Exceptions
# ======================================================================


class PersistenceHealth(str, Enum):
    """Persistence health status for fail-closed operation."""

    HEALTHY = "HEALTHY"
    FAILED = "FAILED"


class PersistenceError(RuntimeError):
    """Base exception for SQLite persistence operations."""


class PersistenceCorruptedError(PersistenceError):
    """Raised when persisted state is corrupted, contradictory, or fails integrity checks."""


class DatabaseIdentityMismatchError(PersistenceError):
    """Raised when database instance, account, or schema version does not match."""


class IncompatibleContractError(PersistenceError):
    """Raised when state-affecting risk or cost contract fingerprint does not match."""


class Q93MarkerRegressionError(RuntimeError):
    """ADR §125.6 (C6): a Q93 last-observed-month update attempted to regress.

    The durable store rejects non-monotonic month transitions atomically; the
    database itself is NOT corrupted — only the attempted write is invalid and
    durable data is left untouched.
    """


class SessionTimeRegressionError(PersistenceError):
    """Raised when live market date moves backward relative to persisted RiskDay."""


class PersistenceTransactionError(PersistenceError):
    """Raised when a persistence transaction fails."""


class PersistenceHealthFailedError(PersistenceError):
    """Raised when persistence health is FAILED."""


class StrategyStateCodecError(PersistenceError, ValueError, TypeError):
    """Raised when strategy state encoding or decoding violates the canonical contract."""


# ======================================================================
# Strategy State Codec & Types (P1-07 / ADR §121)
# ======================================================================

STRATEGY_STATE_CODEC_VERSION: str = "algofortis-strategy-state/v1"


@dataclass(frozen=True)
class StrategyDurableState:
    """Immutable durable strategy runtime state restored from SQLite."""

    strategy_id: str
    strategy_version: str
    paper_session_id: str
    configuration_identity: str
    codec_version: str
    state: dict[str, Any]
    state_fingerprint: str
    last_evaluated_decision_time: datetime | None
    state_generation: int
    updated_at: datetime


@dataclass(frozen=True)
class StrategyStateTransition:
    """Strategy state update payload coupled to an atomic transaction."""

    strategy_id: str
    strategy_version: str
    state: dict[str, Any]
    last_evaluated_decision_time: datetime


def encode_strategy_state(state: dict[str, Any]) -> tuple[str, str]:
    """Encode strategy runtime state dictionary into canonical JSON and SHA256 fingerprint."""
    if not isinstance(state, dict):
        raise StrategyStateCodecError(f"strategy state root must be a dict, got {type(state).__name__}")

    def _encode_val(val: Any) -> Any:
        if val is None:
            return {"__t": "none"}
        elif isinstance(val, bool):
            return {"__t": "bool", "__v": val}
        elif isinstance(val, Enum):
            return {
                "__t": "enum",
                "__module": type(val).__module__,
                "__qualname": type(val).__qualname__,
                "__member": val.name,
            }
        elif isinstance(val, int):
            return {"__t": "int", "__v": val}
        elif isinstance(val, float):
            if not math.isfinite(val):
                raise StrategyStateCodecError(f"Non-finite float value is not allowed in strategy state: {val}")
            return {"__t": "float", "__v": val}
        elif isinstance(val, Decimal):
            if not val.is_finite():
                raise StrategyStateCodecError(f"Non-finite Decimal value is not allowed in strategy state: {val}")
            return {"__t": "decimal", "__v": str(val)}
        elif isinstance(val, datetime):
            if val.tzinfo is None or val.utcoffset() is None:
                raise StrategyStateCodecError(f"Naive datetime without tzinfo is not allowed in strategy state: {val}")
            return {"__t": "datetime", "__v": val.isoformat()}
        elif isinstance(val, date):
            return {"__t": "date", "__v": val.isoformat()}
        elif isinstance(val, str):
            return {"__t": "str", "__v": val}
        elif isinstance(val, tuple):
            return {"__t": "tuple", "__v": [_encode_val(x) for x in val]}
        elif isinstance(val, list):
            return {"__t": "list", "__v": [_encode_val(x) for x in val]}
        elif isinstance(val, Mapping):
            encoded = {}
            for k, v in sorted(val.items()):
                if not isinstance(k, str):
                    raise StrategyStateCodecError(f"Dictionary key must be str, got {type(k).__name__}")
                encoded[k] = _encode_val(v)
            return {"__t": "dict", "__v": encoded}
        else:
            raise StrategyStateCodecError(f"Unsupported type in strategy state: {type(val).__name__}")

    root_dict = {}
    for k, v in sorted(state.items()):
        if not isinstance(k, str):
            raise StrategyStateCodecError(f"Dictionary key must be str, got {type(k).__name__}")
        root_dict[k] = _encode_val(v)

    envelope = {
        "codec_version": STRATEGY_STATE_CODEC_VERSION,
        "state": root_dict,
    }
    payload_json = json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    fp = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    return payload_json, fp


def decode_strategy_state(payload_json: str, expected_fingerprint: str | None = None) -> dict[str, Any]:
    """Decode canonical JSON payload into typed strategy state dictionary with validation."""
    if not isinstance(payload_json, str):
        raise PersistenceCorruptedError("Malformed state_json: must be string")

    if expected_fingerprint is not None:
        computed_fp = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        if computed_fp != expected_fingerprint:
            raise PersistenceCorruptedError(
                f"State fingerprint mismatch: expected {expected_fingerprint}, got {computed_fp}"
            )

    try:
        envelope = json.loads(payload_json)
    except Exception as err:
        raise PersistenceCorruptedError(f"Malformed state_json: {err}") from err

    if not isinstance(envelope, dict):
        raise PersistenceCorruptedError("Malformed state payload: root is not a dict")
    if envelope.get("codec_version") != STRATEGY_STATE_CODEC_VERSION:
        raise IncompatibleContractError(
            f"Unsupported codec_version: {envelope.get('codec_version')!r}, expected {STRATEGY_STATE_CODEC_VERSION!r}"
        )

    def _decode_val(node: Any) -> Any:
        if not isinstance(node, dict) or "__t" not in node:
            raise PersistenceCorruptedError(f"Malformed canonical state node: {node}")
        t = node["__t"]
        if t == "none":
            return None
        elif t == "bool":
            return bool(node["__v"])
        elif t == "int":
            return int(node["__v"])
        elif t == "float":
            v = float(node["__v"])
            if not math.isfinite(v):
                raise PersistenceCorruptedError("Non-finite float in state")
            return v
        elif t == "decimal":
            v = Decimal(str(node["__v"]))
            if not v.is_finite():
                raise PersistenceCorruptedError("Non-finite Decimal in state")
            return v
        elif t == "str":
            return str(node["__v"])
        elif t == "datetime":
            dt = datetime.fromisoformat(node["__v"])
            if dt.tzinfo is None:
                raise PersistenceCorruptedError("Parsed datetime missing tzinfo")
            return dt
        elif t == "date":
            return date.fromisoformat(node["__v"])
        elif t == "enum":
            try:
                mod_name = node["__module"]
                qual_name = node["__qualname"]
                member = node["__member"]
                mod = importlib.import_module(mod_name)
                enum_cls = mod
                for part in qual_name.split("."):
                    enum_cls = getattr(enum_cls, part)
                if not (isinstance(enum_cls, type) and issubclass(enum_cls, Enum)):
                    raise PersistenceCorruptedError(
                        f"Resolved target {qual_name} in {mod_name} is not an Enum subclass"
                    )
                return enum_cls[member]
            except Exception as exc:
                if isinstance(exc, PersistenceCorruptedError):
                    raise
                raise PersistenceCorruptedError(f"Failed to decode enum {node}: {exc}") from exc
        elif t == "tuple":
            return tuple(_decode_val(item) for item in node["__v"])
        elif t == "list":
            return [_decode_val(item) for item in node["__v"]]
        elif t == "dict":
            return {k: _decode_val(v) for k, v in node["__v"].items()}
        else:
            raise PersistenceCorruptedError(f"Unknown canonical state type tag: {t}")

    root_node = envelope.get("state")
    if not isinstance(root_node, dict):
        raise PersistenceCorruptedError("Malformed state payload: state is not a dict")

    return {k: _decode_val(v) for k, v in root_node.items()}


# ======================================================================
# Hydrated State Container
# ======================================================================


@dataclass(frozen=True)
class PaperHydratedState:
    """Complete, immutable aggregate of restored Phase 5 paper state."""

    account_snapshot: AccountSnapshot
    active_commitments: dict[str, PremiumCommitmentRecord]
    processed_fills: dict[str, tuple[BrokerTerminalEvent, AccountingResult]]
    pending_broker_orders: dict[str, _PendingOrder]
    terminal_broker_orders: dict[str, BrokerTerminalEvent]
    broker_watermarks: dict[InstrumentIdentity, datetime]
    entry_intents: dict[str, str]
    retained_protective_plans: dict[str, tuple[PreEntryProtectivePlan, Decimal, str | None]]
    protective_exits: tuple[ProtectiveExit, ...]
    protective_pending_closes: tuple[LiveProtectivePendingClose, ...]
    trade_ledger: TradeLedger
    cost_assessments: list[CostAssessment]
    risk_gate_state: RiskGateState | None
    accounting_sequence: int
    accounting_integrity_breached: bool
    state_generation: int
    database_instance_id: str
    paper_session_id: str
    pending_risk_commitments: tuple[PendingRiskCommitment, ...] = ()
    kill_switch_state: KillSwitchState = KillSwitchState(active=False)
    strategy_states: dict[SubscriptionOwnerKey, StrategyDurableState] = field(default_factory=dict)
    promotion_tracking_states: dict[SubscriptionOwnerKey, PromotionTrackingState] = field(default_factory=dict)
    promotion_session_records: list[PromotionSessionRecord] = field(default_factory=list)

    @property
    def strategy_watermarks(self) -> dict[SubscriptionOwnerKey, datetime | None]:
        return {owner: s.last_evaluated_decision_time for owner, s in self.strategy_states.items()}



# ======================================================================
# Serialization & Deserialization Helpers (Exact, Lossless, Non-Lossy)
# ======================================================================


def _dec_to_str(val: Decimal | int | float | str | None) -> str | None:
    if val is None:
        return None
    return str(val)


def _str_to_dec(val: str | None) -> Decimal | None:
    if val is None:
        return None
    return Decimal(val)


def _dt_to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        raise ValueError(f"Datetime {dt} must be timezone-aware")
    return dt.isoformat()


def _iso_to_dt(iso_str: str | None) -> datetime | None:
    if iso_str is None:
        return None
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        raise ValueError(f"ISO string '{iso_str}' produced naive datetime")
    return dt


# Aliases used throughout the store — canonical names for callers.
_dt_to_str = _dt_to_iso
_str_to_dt = _iso_to_dt

def _identity_canonical_key(ident: InstrumentIdentity) -> str:
    """Build a stable, collision-safe string key for an InstrumentIdentity.

    Used as the primary key in broker_watermarks, pending_protective_closes, and
    other tables that key by instrument rather than order-id.
    """
    parts = [ident.market, ident.segment, ident.instrument]
    if ident.expiry is not None:
        parts.append(ident.expiry.isoformat())
    if ident.strike is not None:
        parts.append(str(ident.strike))
    if ident.option_type is not None:
        parts.append(ident.option_type)
    return "|".join(parts)


def _identity_to_dict(ident: InstrumentIdentity) -> dict[str, Any]:
    return {
        "market": ident.market,
        "instrument": ident.instrument,
        "segment": ident.segment,
        "underlying": ident.underlying,
        "expiry": ident.expiry.isoformat() if ident.expiry is not None else None,
        "strike": _dec_to_str(ident.strike),
        "option_type": ident.option_type if ident.option_type is not None else None,
    }


def _dict_to_identity(data: dict[str, Any]) -> InstrumentIdentity:
    exp = date.fromisoformat(data["expiry"]) if data.get("expiry") is not None else None
    opt = data.get("option_type")
    strike = _str_to_dec(data.get("strike"))
    return InstrumentIdentity(
        market=data["market"],
        instrument=data["instrument"],
        segment=data["segment"],
        underlying=data["underlying"],
        expiry=exp,
        strike=strike,
        option_type=opt,
    )


def _spec_to_dict(spec: InstrumentSpecification) -> dict[str, Any]:
    return {
        "identity": _identity_to_dict(spec.identity),
        "effective_from": spec.effective_from.isoformat(),
        "contract_multiplier": _dec_to_str(spec.contract_multiplier),
        "minimum_quantity": _dec_to_str(spec.minimum_quantity),
        "quantity_step": _dec_to_str(spec.quantity_step),
        "currency": spec.currency,
        "price_increment": _dec_to_str(spec.price_increment),
    }


def _dict_to_spec(data: dict[str, Any]) -> InstrumentSpecification:
    eff = date.fromisoformat(data["effective_from"]) if "effective_from" in data else date(2026, 1, 1)
    min_qty = _str_to_dec(data.get("minimum_quantity") or data.get("lot_size")) or Decimal("1")
    step = _str_to_dec(data.get("quantity_step") or data.get("lot_size")) or Decimal("1")
    return InstrumentSpecification(
        identity=_dict_to_identity(data["identity"]),
        effective_from=eff,
        contract_multiplier=_str_to_dec(data["contract_multiplier"]),
        minimum_quantity=min_qty,
        quantity_step=step,
        currency=data["currency"],
        price_increment=_str_to_dec(data["price_increment"]),
    )


def _position_key_to_dict(pkey: PositionKey) -> dict[str, Any]:
    return {
        "strategy_id": pkey.strategy_id,
        "strategy_version": pkey.strategy_version,
        "identity": _identity_to_dict(pkey.identity),
    }


def _dict_to_position_key(data: dict[str, Any]) -> PositionKey:
    return PositionKey(
        strategy_id=data["strategy_id"],
        strategy_version=data["strategy_version"],
        identity=_dict_to_identity(data["identity"]),
    )


def _row_to_audit_event(row: sqlite3.Row | Mapping[str, Any]) -> AuditEvent:
    market_ts = _str_to_dt(row["market_timestamp"]) if row["market_timestamp"] else None
    recorded_at = _str_to_dt(row["recorded_at_utc"])
    if recorded_at is None:
        raise ValueError("recorded_at_utc cannot be null in audit row")
    return AuditEvent(
        audit_sequence=int(row["audit_sequence"]) if row["audit_sequence"] is not None else None,
        event_id=str(row["event_id"]),
        event_schema_version=str(row["event_schema_version"]),
        event_family=str(row["event_family"]),
        event_type=str(row["event_type"]),
        aggregate_type=str(row["aggregate_type"]),
        aggregate_identity=str(row["aggregate_identity"]),
        market_timestamp=market_ts,
        recorded_at_utc=recorded_at,
        state_generation=int(row["state_generation"]) if row["state_generation"] is not None else None,
        transaction_event_ordinal=int(row["transaction_event_ordinal"]),
        correlation_id=str(row["correlation_id"]) if row["correlation_id"] is not None else None,
        causation_event_id=str(row["causation_event_id"]) if row["causation_event_id"] is not None else None,
        strategy_id=str(row["strategy_id"]) if row["strategy_id"] is not None else None,
        strategy_version=str(row["strategy_version"]) if row["strategy_version"] is not None else None,
        instrument_key=str(row["instrument_key"]) if row["instrument_key"] is not None else None,
        position_key_json=str(row["position_key_json"]) if row["position_key_json"] is not None else None,
        entry_intent_identity=str(row["entry_intent_identity"]) if row["entry_intent_identity"] is not None else None,
        broker_order_identity=str(row["broker_order_identity"]) if row["broker_order_identity"] is not None else None,
        trade_id=str(row["trade_id"]) if row["trade_id"] is not None else None,
        protective_id=str(row["protective_id"]) if row["protective_id"] is not None else None,
        payload_version=str(row["payload_version"]),
        payload_json=str(row["payload_json"]),
        environment=str(row["environment"]),
        run_id=str(row["run_id"]),
        canonical_configuration_fingerprint=str(row["canonical_configuration_fingerprint"]),
        source_identity=str(row["source_identity"]),
        timeframe=str(row["timeframe"]) if row["timeframe"] is not None else None,
        status=str(row["status"]),
        severity=str(row["severity"]),
    )


def _order_to_dict(order: Any) -> dict[str, Any]:
    pkey_dict = None
    if getattr(order, "position_key", None) is not None:
        pk = getattr(order, "position_key")
        pkey_dict = _position_key_to_dict(pk) if isinstance(pk, PositionKey) else pk

    # Serialize source_intent if present, rather than embedding the raw object.
    source_intent_dict = None
    raw_intent = getattr(order, "source_intent", None)
    if raw_intent is not None:
        source_intent_dict = {
            "action": getattr(raw_intent, "action", None),
            "confidence": getattr(raw_intent, "confidence", None),
            "symbol": getattr(raw_intent, "symbol", None),
            "timeframe": getattr(raw_intent, "timeframe", None),
            "originating_timestamp": _dt_to_iso(getattr(raw_intent, "originating_timestamp", None)),
            "strategy_id": getattr(raw_intent, "strategy_id", None),
            "strategy_version": getattr(raw_intent, "strategy_version", None),
            "metadata": dict(getattr(raw_intent, "metadata", {})),
        }

    # For ConcreteOpenInstruction, also record the execution_symbol and opening_action.
    execution_symbol = getattr(order, "execution_symbol", None)
    opening_action = getattr(order, "opening_action", None)
    closing_action = getattr(order, "closing_action", None)

    return {
        "type": type(order).__name__,
        "strategy_id": getattr(order, "strategy_id", ""),
        "strategy_version": getattr(order, "strategy_version", ""),
        "symbol": getattr(order, "symbol", ""),
        "timeframe": getattr(order, "timeframe", ""),
        "originating_timestamp": _dt_to_iso(getattr(order, "originating_timestamp", None)),
        "action": getattr(order, "action", ""),
        "order_type": getattr(order, "order_type", OrderType.MARKET).value if hasattr(order, "order_type") else "MARKET",
        "quantity": _dec_to_str(getattr(order, "quantity", Decimal("0"))),
        "limit_price": _dec_to_str(getattr(order, "limit_price", None)),
        "stop_price": _dec_to_str(getattr(order, "stop_price", None)),
        "time_in_force": getattr(order, "time_in_force", TimeInForce.GTC).value if hasattr(order, "time_in_force") else "GTC",
        "source_intent": source_intent_dict,
        "position_key": pkey_dict,
        "protective_id": getattr(order, "protective_id", None),
        "execution_symbol": execution_symbol,
        "opening_action": opening_action,
        "closing_action": closing_action,
    }


def _dict_to_order(data: dict[str, Any]) -> Any:
    order_cls = data.get("type", "OrderRequest")
    action = data.get("action", "BUY")
    order_type = OrderType(data.get("order_type", "MARKET"))
    qty = _str_to_dec(data.get("quantity"))
    limit = _str_to_dec(data.get("limit_price"))
    stop = _str_to_dec(data.get("stop_price"))
    tif = TimeInForce(data.get("time_in_force", "GTC"))
    orig_ts = _iso_to_dt(data.get("originating_timestamp"))

    if order_cls == "ConcreteOpenInstruction":
        # Reconstruct the source_intent from its serialized dict.
        intent_dict = data.get("source_intent") or {}
        intent = SignalIntent(
            action=intent_dict.get("action") or action,
            confidence=float(intent_dict.get("confidence") or 1.0),
            symbol=intent_dict.get("symbol") or data.get("symbol") or data.get("strategy_id", ""),
            timeframe=intent_dict.get("timeframe") or data.get("timeframe", ""),
            originating_timestamp=_iso_to_dt(intent_dict.get("originating_timestamp")) or orig_ts,
            strategy_id=intent_dict.get("strategy_id") or data.get("strategy_id", ""),
            strategy_version=intent_dict.get("strategy_version") or data.get("strategy_version", ""),
            metadata=dict(intent_dict.get("metadata") or {}),
        )
        req = OrderRequest(
            source_intent=intent,
            order_type=order_type,
            quantity=qty,
            time_in_force=tif,
            limit_price=limit,
            stop_price=stop,
        )
        execution_symbol = data.get("execution_symbol") or data.get("symbol") or data.get("strategy_id", "")
        opening_action = data.get("opening_action") or action
        return ConcreteOpenInstruction(
            source_entry_order=req,
            opening_action=opening_action,
            execution_symbol=execution_symbol,
        )
    elif order_cls == "ConcreteCloseInstruction":
        intent_dict = data.get("source_intent")
        if not isinstance(intent_dict, dict):
            raise ValueError("ConcreteCloseInstruction requires a nested source_intent mapping")

        closing_action = data.get("closing_action")
        if closing_action not in {"BUY", "SELL"}:
            raise ValueError(f"ConcreteCloseInstruction requires closing_action in ('BUY', 'SELL'), got {closing_action!r}")

        strat_id = intent_dict.get("strategy_id")
        if not strat_id:
            raise ValueError("source_intent missing required strategy_id")
        strat_ver = intent_dict.get("strategy_version")
        if not strat_ver:
            raise ValueError("source_intent missing required strategy_version")
        sym = intent_dict.get("symbol")
        if not sym:
            raise ValueError("source_intent missing required symbol")
        tf = intent_dict.get("timeframe")
        if not tf:
            raise ValueError("source_intent missing required timeframe")
        raw_orig_ts = intent_dict.get("originating_timestamp")
        if not raw_orig_ts:
            raise ValueError("source_intent missing required originating_timestamp")
        parsed_orig_ts = _iso_to_dt(raw_orig_ts)
        if parsed_orig_ts is None:
            raise ValueError("source_intent has invalid originating_timestamp")

        action_val = intent_dict.get("action")
        if not action_val:
            raise ValueError("source_intent missing required action")

        if "confidence" not in intent_dict or intent_dict["confidence"] is None:
            raise ValueError("source_intent missing required confidence")
        try:
            confidence_val = float(intent_dict["confidence"])
        except (ValueError, TypeError) as exc:
            raise ValueError(f"source_intent has invalid confidence: {intent_dict['confidence']!r}") from exc

        intent = SignalIntent(
            action=action_val,
            confidence=confidence_val,
            symbol=sym,
            timeframe=tf,
            originating_timestamp=parsed_orig_ts,
            strategy_id=strat_id,
            strategy_version=strat_ver,
            metadata=dict(intent_dict.get("metadata") or {}),
        )
        source_exit_order = OrderRequest(
            source_intent=intent,
            order_type=order_type,
            quantity=qty,
            time_in_force=tif,
            limit_price=limit,
            stop_price=stop,
        )
        return ConcreteCloseInstruction(
            source_exit_order=source_exit_order,
            closing_action=closing_action,
            quantity=qty,
        )
    
    intent_dict = data.get("source_intent") or {}
    intent = SignalIntent(
        action=intent_dict.get("action") or action,
        confidence=float(intent_dict.get("confidence") or 1.0),
        symbol=intent_dict.get("symbol") or data.get("symbol") or data.get("strategy_id", ""),
        timeframe=intent_dict.get("timeframe") or data.get("timeframe", ""),
        originating_timestamp=_iso_to_dt(intent_dict.get("originating_timestamp")) or orig_ts,
        strategy_id=intent_dict.get("strategy_id") or data.get("strategy_id", ""),
        strategy_version=intent_dict.get("strategy_version") or data.get("strategy_version", ""),
        metadata=dict(intent_dict.get("metadata") or {}),
    )
    return OrderRequest(
        source_intent=intent,
        order_type=order_type,
        quantity=qty,
        time_in_force=tif,
        limit_price=limit,
        stop_price=stop,
    )


def _plan_to_dict(plan: PreEntryProtectivePlan) -> dict[str, Any]:
    trailing = plan.trailing
    return {
        "intended_position_key": _position_key_to_dict(plan.intended_position_key),
        "originating_timestamp": _dt_to_iso(plan.originating_timestamp),
        "timeframe": plan.timeframe,
        "protective_plan_policy_identity": plan.protective_plan_policy_identity,
        "stop_price": _dec_to_str(plan.stop_price),
        "target_price": _dec_to_str(plan.target_price),
        "trailing": None if trailing is None else {
            "initial_stop_price": _dec_to_str(trailing.initial_stop_price),
            "initial_reference_extreme": _dec_to_str(trailing.initial_reference_extreme),
            "activated": trailing.activated,
        },
        "oco_enabled": plan.oco_enabled,
    }


def _dict_to_plan(data: dict[str, Any]) -> PreEntryProtectivePlan:
    trailing_data = data.get("trailing")
    trailing = None
    if trailing_data is not None:
        if not isinstance(trailing_data, dict):
            raise PersistenceCorruptedError("retained protective plan trailing must be an object or null")
        try:
            trailing = TrailingProtectionSpec(
                initial_stop_price=_str_to_dec(trailing_data["initial_stop_price"]),
                initial_reference_extreme=_str_to_dec(trailing_data["initial_reference_extreme"]),
                activated=trailing_data.get("activated", True),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise PersistenceCorruptedError("retained protective plan trailing is invalid") from error
    return PreEntryProtectivePlan(
        intended_position_key=_dict_to_position_key(data["intended_position_key"]),
        originating_timestamp=_iso_to_dt(data["originating_timestamp"]),
        timeframe=data["timeframe"],
        protective_plan_policy_identity=data["protective_plan_policy_identity"],
        stop_price=_str_to_dec(data["stop_price"]),
        target_price=_str_to_dec(data.get("target_price")),
        trailing=trailing,
        oco_enabled=data.get("oco_enabled", False),
    )


def _exec_result_to_dict(res: ExecutionResult) -> dict[str, Any]:
    return {
        "order": _order_to_dict(res.order),
        "outcome": res.outcome.value,
        "execution_bar_timestamp": _dt_to_iso(res.execution_bar_timestamp),
        "pre_slippage_price": _dec_to_str(res.pre_slippage_price),
        "fill_price": _dec_to_str(res.fill_price),
        "filled_quantity": _dec_to_str(res.filled_quantity),
        "reason": res.reason,
        "slippage_model_id": res.slippage_model_id,
        "slippage_amount": _dec_to_str(res.slippage_amount),
        "metadata": dict(res.metadata) if res.metadata else {},
    }


def _dict_to_exec_result(data: dict[str, Any]) -> ExecutionResult:
    return ExecutionResult(
        order=_dict_to_order(data["order"]),
        outcome=ExecutionOutcome(data["outcome"]),
        execution_bar_timestamp=_iso_to_dt(data.get("execution_bar_timestamp")),
        pre_slippage_price=_str_to_dec(data.get("pre_slippage_price")),
        fill_price=_str_to_dec(data.get("fill_price")),
        filled_quantity=_str_to_dec(data.get("filled_quantity")) or Decimal("0"),
        reason=data.get("reason"),
        slippage_model_id=data.get("slippage_model_id", "none"),
        slippage_amount=_str_to_dec(data.get("slippage_amount")) or Decimal("0"),
        metadata=data.get("metadata", {}),
    )


def _trade_leg_to_dict(leg: TradeLeg) -> dict[str, Any]:
    return {
        "event_key": {
            "run_id": leg.event_key.run_id,
            "accounting_sequence": leg.event_key.accounting_sequence,
        },
        "role": leg.role.value if hasattr(leg.role, "value") else str(leg.role),
        "execution_timestamp": _dt_to_iso(leg.execution_timestamp),
        "execution_price": _dec_to_str(leg.execution_price),
        "execution_quantity": _dec_to_str(leg.execution_quantity),
        "realized_pnl_delta": _dec_to_str(leg.realized_pnl_delta),
    }


def _dict_to_trade_leg(data: dict[str, Any]) -> TradeLeg:
    ev_data = data["event_key"]
    ev_key = LedgerEventKey(
        run_id=ev_data["run_id"],
        accounting_sequence=int(ev_data["accounting_sequence"]),
    )
    role = TradeRole(data["role"]) if isinstance(data["role"], str) else data["role"]
    ts = _iso_to_dt(data["execution_timestamp"])
    price = _str_to_dec(data["execution_price"])
    qty = _str_to_dec(data["execution_quantity"])
    pnl = _str_to_dec(data["realized_pnl_delta"])
    return TradeLeg(
        event_key=ev_key,
        accounting_result=None,
        role=role,
        execution_timestamp=ts,
        execution_price=price,
        execution_quantity=qty,
        realized_pnl_delta=pnl,
    )


def _trade_record_to_dict(record: TradeRecord) -> dict[str, Any]:
    return {
        "trade_id": record.trade_id,
        "account_id": record.account_id,
        "currency": record.currency,
        "monetary_quantum": _dec_to_str(record.monetary_quantum),
        "position_key": _position_key_to_dict(record.position_key),
        "instrument_identity": _identity_to_dict(record.instrument_identity),
        "position_side": record.position_side,
        "opened_at": _dt_to_iso(record.opened_at),
        "closed_at": _dt_to_iso(record.closed_at),
        "holding_duration_seconds": _dec_to_str(Decimal(str(record.holding_duration.total_seconds()))),
        "entry_quantity": _dec_to_str(record.entry_quantity),
        "exit_quantity": _dec_to_str(record.exit_quantity),
        "average_entry_price": _dec_to_str(record.average_entry_price),
        "contract_multiplier": _dec_to_str(record.contract_multiplier),
        "entry_legs": [_trade_leg_to_dict(leg) for leg in record.entry_legs],
        "exit_legs": [_trade_leg_to_dict(leg) for leg in record.exit_legs],
        "gross_realized_pnl": _dec_to_str(record.gross_realized_pnl),
        "status": record.status.value if hasattr(record.status, "value") else str(record.status),
        "opening_event_key": {
            "run_id": record.opening_event_key.run_id,
            "accounting_sequence": record.opening_event_key.accounting_sequence,
        },
        "closing_event_key": {
            "run_id": record.closing_event_key.run_id,
            "accounting_sequence": record.closing_event_key.accounting_sequence,
        },
        "provenance": dict(record.provenance) if record.provenance else {},
    }


def _dict_to_trade_record(data: dict[str, Any]) -> TradeRecord:
    pkey = _dict_to_position_key(data["position_key"])
    ident = _dict_to_identity(data["instrument_identity"])
    op_key = LedgerEventKey(
        run_id=data["opening_event_key"]["run_id"],
        accounting_sequence=int(data["opening_event_key"]["accounting_sequence"]),
    )
    cl_key = LedgerEventKey(
        run_id=data["closing_event_key"]["run_id"],
        accounting_sequence=int(data["closing_event_key"]["accounting_sequence"]),
    )
    dur = timedelta(seconds=float(data.get("holding_duration_seconds", 0)))
    entry_legs = tuple(_dict_to_trade_leg(leg_d) for leg_d in data.get("entry_legs", ()))
    exit_legs = tuple(_dict_to_trade_leg(leg_d) for leg_d in data.get("exit_legs", ()))
    return TradeRecord(
        trade_id=data["trade_id"],
        account_id=data["account_id"],
        currency=data["currency"],
        monetary_quantum=_str_to_dec(data["monetary_quantum"]),
        position_key=pkey,
        instrument_identity=ident,
        position_side=data.get("position_side", "LONG"),
        opened_at=_iso_to_dt(data["opened_at"]),
        closed_at=_iso_to_dt(data["closed_at"]),
        holding_duration=dur,
        entry_quantity=_str_to_dec(data["entry_quantity"]),
        exit_quantity=_str_to_dec(data["exit_quantity"]),
        average_entry_price=_str_to_dec(data["average_entry_price"]),
        contract_multiplier=_str_to_dec(data["contract_multiplier"]),
        entry_legs=entry_legs,
        exit_legs=exit_legs,
        gross_realized_pnl=_str_to_dec(data["gross_realized_pnl"]),
        status=TradeStatus(data["status"]),
        opening_event_key=op_key,
        closing_event_key=cl_key,
        provenance=dict(data.get("provenance", {})),
    )


def _cost_assessment_to_dict(assessment: CostAssessment) -> dict[str, Any]:
    return {
        "assessment_id": assessment.assessment_id,
        "trade_evidence_fingerprint": assessment.trade_evidence_fingerprint,
        "trade_id": assessment.trade_id,
        "account_id": assessment.account_id,
        "currency": assessment.currency,
        "total_cost": _dec_to_str(assessment.total_cost),
        "gross_realized_pnl": _dec_to_str(assessment.gross_realized_pnl),
        "net_realized_pnl": _dec_to_str(assessment.net_realized_pnl),
        "schedule_references": [
            {
                "schedule_id": ref.schedule_id,
                "version": ref.version,
                "fingerprint": ref.fingerprint,
            }
            for ref in assessment.schedule_references
        ],
        "component_results": [
            {
                "component_id": res.component_id,
                "leg_event_key": {
                    "run_id": res.leg_event_key.run_id,
                    "accounting_sequence": res.leg_event_key.accounting_sequence,
                },
                "basis": res.basis.value if hasattr(res.basis, "value") else str(res.basis),
                "schedule_id": res.schedule_id,
                "schedule_version": res.schedule_version,
                "schedule_fingerprint": res.schedule_fingerprint,
                "input_amount": _dec_to_str(res.input_amount),
                "rate": _dec_to_str(res.rate),
                "unrounded_amount": _dec_to_str(res.unrounded_amount),
                "amount": _dec_to_str(res.amount),
            }
            for res in assessment.component_results
        ],
        "trade_record": _trade_record_to_dict(assessment.trade_record),
    }


def _dict_to_cost_assessment(
    data: dict[str, Any],
    trade_records_by_id: dict[str, TradeRecord],
    expected_total_cost: Decimal,
) -> CostAssessment:
    assessment_id = data.get("assessment_id")
    trade_id = data.get("trade_id")
    account_id = data.get("account_id")
    currency = data.get("currency")
    trade_ev_fp = data.get("trade_evidence_fingerprint")
    total_cost_str = data.get("total_cost")
    if not assessment_id or not trade_id or total_cost_str is None or not account_id or not currency:
        raise PersistenceCorruptedError(
            f"Malformed cost assessment JSON: missing required fields in {data}"
        )
    total_cost = _str_to_dec(total_cost_str)
    if total_cost != expected_total_cost:
        raise PersistenceCorruptedError(
            f"Contradictory cost assessment total_cost: column has {expected_total_cost}, JSON has {total_cost}"
        )

    raw_refs = data.get("schedule_references")
    if raw_refs is None:
        raise PersistenceCorruptedError("Malformed cost assessment JSON: missing schedule_references")
    try:
        sched_refs = tuple(
            ScheduleReference(
                schedule_id=r["schedule_id"],
                version=r["version"],
                fingerprint=r["fingerprint"],
            )
            for r in raw_refs
        )
    except Exception as ref_err:
        raise PersistenceCorruptedError(f"Malformed schedule_references: {ref_err}") from ref_err

    raw_components = data.get("component_results")
    if raw_components is None:
        raise PersistenceCorruptedError("Malformed cost assessment JSON: missing component_results")
    try:
        comp_results = tuple(
            CostComponentResult(
                component_id=c["component_id"],
                leg_event_key=LedgerEventKey(
                    run_id=c["leg_event_key"]["run_id"],
                    accounting_sequence=int(c["leg_event_key"]["accounting_sequence"]),
                ),
                basis=CostBasis(c["basis"]),
                schedule_id=c["schedule_id"],
                schedule_version=c["schedule_version"],
                schedule_fingerprint=c["schedule_fingerprint"],
                input_amount=_str_to_dec(c["input_amount"]),
                rate=_str_to_dec(c["rate"]),
                unrounded_amount=_str_to_dec(c["unrounded_amount"]),
                amount=_str_to_dec(c["amount"]),
            )
            for c in raw_components
        )
    except Exception as comp_err:
        raise PersistenceCorruptedError(f"Malformed component_results: {comp_err}") from comp_err

    tr = trade_records_by_id.get(trade_id)
    if tr is None and "trade_record" in data:
        try:
            tr = _dict_to_trade_record(data["trade_record"])
        except Exception as tr_err:
            raise PersistenceCorruptedError(f"Failed to decode embedded trade_record: {tr_err}") from tr_err

    if tr is None:
        raise PersistenceCorruptedError(
            f"Cannot hydrate CostAssessment '{assessment_id}': missing trade_record for trade_id '{trade_id}'"
        )

    gross_pnl = _str_to_dec(data.get("gross_realized_pnl")) if "gross_realized_pnl" in data else tr.gross_realized_pnl
    net_pnl = _str_to_dec(data.get("net_realized_pnl")) if "net_realized_pnl" in data else (gross_pnl - total_cost)

    try:
        return CostAssessment(
            assessment_id=assessment_id,
            trade_evidence_fingerprint=trade_ev_fp,
            trade_id=trade_id,
            account_id=account_id,
            currency=currency,
            schedule_references=sched_refs,
            component_results=comp_results,
            total_cost=total_cost,
            gross_realized_pnl=gross_pnl,
            net_realized_pnl=net_pnl,
            trade_record=tr,
        )
    except Exception as err:
        raise PersistenceCorruptedError(f"Failed to instantiate CostAssessment from JSON: {err}") from err


def _compute_fill_fingerprint(
    *,
    broker_order_identity: str,
    order_id: str,
    lifecycle_state: str,
    instrument_identity: InstrumentIdentity,
    fill_price: Decimal,
    filled_quantity: Decimal,
    fee: Decimal,
    fill_timestamp: datetime,
) -> str:
    """Deterministic canonical fingerprint for fill idempotency verification (VA-11B)."""
    fields = (
        ("broker_order_identity", broker_order_identity),
        ("order_id", order_id),
        ("lifecycle_state", lifecycle_state),
        ("market", instrument_identity.market),
        ("instrument", instrument_identity.instrument),
        ("segment", instrument_identity.segment),
        ("underlying", instrument_identity.underlying),
        ("expiry", instrument_identity.expiry.isoformat() if instrument_identity.expiry else ""),
        ("strike", instrument_identity.strike),
        ("option_type", instrument_identity.option_type if instrument_identity.option_type else ""),
        ("fill_price", fill_price),
        ("filled_quantity", filled_quantity),
        ("fee", fee),
        ("fill_timestamp", fill_timestamp),
    )
    return CanonicalCodec.fingerprint("algofortis-processed-fill/v1", fields)


# ======================================================================
# SQLite Paper State Store
# ======================================================================


class SQLitePaperStateStore:
    """Atomic, fail-closed SQLite persistence store for Phase 5 Paper Trading.

    Owns the physical SQLite connection, schema bootstrap, WAL initialization,
    durable multi-table transactions (T1–T6), hydration, and health state.
    """

    def __init__(
        self,
        db_path: Path | str,
        *,
        account_id: str,
        currency: str = "INR",
        monetary_quantum: Decimal = Decimal("0.01"),
        starting_capital: Decimal = Decimal("2000000.00"),
        paper_session_id: str = "default_paper_session",
        risk_policy_identity: str = "algofortis-risk-policy/v3",
        cost_schedule_fingerprint: str = "",
        execution_policy_identity: str = "algofortis-paper-execution/v1",
        configuration_identity: str = "",
        initial_strategy_states: Mapping[SubscriptionOwnerKey, dict[str, Any]] | Sequence[Any] | None = None,
        initial_promotion_states: Mapping[SubscriptionOwnerKey, PromotionTrackingState] | None = None,
        audit_environment: str = "paper",
        audit_source_identity: str = "datasource/unspecified",
    ) -> None:
        self._path = Path(db_path)
        self._account_id = account_id
        self._currency = currency
        self._monetary_quantum = monetary_quantum
        self._starting_capital = starting_capital
        self._paper_session_id = paper_session_id
        self._risk_policy_identity = risk_policy_identity
        self._cost_schedule_fingerprint = cost_schedule_fingerprint
        self._execution_policy_identity = execution_policy_identity
        self._configuration_identity = configuration_identity

        # Phase 6 / ADR §123.1: durable per-event audit context providers.
        # The Phase-6 durable-journal provider scope is paper/live only
        # (§123.1 item 6 + provider table); the generic D16 envelope
        # vocabulary (incl. "backtest", never emitted here) remains available
        # at the AuditEvent model layer.
        if not isinstance(audit_environment, str) or audit_environment not in ("paper", "live"):
            raise ValueError(
                "audit_environment must be 'paper' or 'live' at the Phase-6 durable journal boundary, "
                f"got {audit_environment!r}"
            )
        if not isinstance(audit_source_identity, str) or not audit_source_identity.strip():
            raise ValueError("audit_source_identity must be a non-empty string")
        self._audit_environment = audit_environment
        self._audit_source_identity = audit_source_identity

        initial_map: dict[SubscriptionOwnerKey, dict[str, Any]] = {}
        if initial_strategy_states is not None:
            if isinstance(initial_strategy_states, Mapping):
                for k, v in initial_strategy_states.items():
                    if isinstance(k, SubscriptionOwnerKey):
                        key = k
                    elif isinstance(k, tuple) and len(k) == 2:
                        key = SubscriptionOwnerKey(str(k[0]), str(k[1]))
                    else:
                        raise TypeError(f"Invalid strategy owner key in initial_strategy_states: {k!r}")
                    if isinstance(v, dict):
                        initial_map[key] = dict(v)
                    elif hasattr(v, "state") and isinstance(v.state, dict):
                        initial_map[key] = dict(v.state)
                    elif hasattr(v, "strategy") and hasattr(v.strategy, "initial_state"):
                        initial_map[key] = dict(v.strategy.initial_state())
                    else:
                        raise TypeError(f"Invalid strategy state value for owner {k!r}: {v!r}")
            elif isinstance(initial_strategy_states, Sequence):
                for item in initial_strategy_states:
                    if hasattr(item, "requirements") and hasattr(item, "strategy"):
                        key = SubscriptionOwnerKey(item.requirements.strategy_id, item.requirements.strategy_version)
                        initial_map[key] = dict(item.strategy.initial_state())
                    else:
                        raise TypeError(f"Invalid sequence item in initial_strategy_states: {item!r}")
        self._initial_strategy_states_map = initial_map
        self._initial_promotion_states_map = dict(initial_promotion_states) if initial_promotion_states is not None else {}


        self._health: PersistenceHealth = PersistenceHealth.HEALTHY
        self._state_generation: int = 0
        self._database_instance_id: str = ""

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self._path),
            timeout=10.0,
            isolation_level=None,  # Explicit manual transaction control
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row

        # Establish PRAGMAs and verify WAL
        self._bootstrap_pragmas()

        # Bootstrap or validate schema and metadata
        self._bootstrap_schema()

    @property
    def health(self) -> PersistenceHealth:
        """Current persistence health status."""
        return self._health

    @property
    def is_healthy(self) -> bool:
        return self._health is PersistenceHealth.HEALTHY

    @property
    def state_generation(self) -> int:
        return self._state_generation

    @property
    def database_instance_id(self) -> str:
        return self._database_instance_id

    @property
    def paper_session_id(self) -> str:
        return self._paper_session_id

    @property
    def configuration_identity(self) -> str:
        return self._configuration_identity

    def close(self) -> None:
        """Close SQLite database connection cleanly."""
        try:
            self._conn.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # PRAGMA & Schema Bootstrap
    # ------------------------------------------------------------------

    def _bootstrap_pragmas(self) -> None:
        cursor = self._conn.cursor()
        for pragma in PRAGMA_STATEMENTS:
            cursor.execute(pragma)

        # Verify WAL mode was established
        cursor.execute("PRAGMA journal_mode;")
        row = cursor.fetchone()
        current_mode = str(row[0]).lower() if row else ""
        if current_mode != "wal":
            # In memory or specific test mounts might not support WAL, but file DBs must
            if str(self._path) != ":memory:" and not str(self._path).startswith(":memory:"):
                self._health = PersistenceHealth.FAILED
                raise PersistenceCorruptedError(
                    f"SQLite journal_mode must be WAL; established mode was {current_mode!r}"
                )

        cursor.execute("PRAGMA foreign_keys;")
        fk_row = cursor.fetchone()
        if not fk_row or int(fk_row[0]) != 1:
            self._health = PersistenceHealth.FAILED
            raise PersistenceCorruptedError("SQLite foreign_keys must be ON")

    def _bootstrap_schema(self) -> None:
        cursor = self._conn.cursor()

        # Execute DDL
        cursor.execute("BEGIN EXCLUSIVE TRANSACTION;")
        try:
            for ddl in CREATE_TABLES_SQL:
                cursor.execute(ddl)

            # Check existing metadata
            cursor.execute("SELECT key, value FROM paper_metadata;")
            rows = dict(cursor.fetchall())

            if not rows:
                # First run initialization
                db_id = str(uuid.uuid4())
                metadata = {
                    "schema_version": str(SCHEMA_VERSION),
                    "database_instance_id": db_id,
                    "account_id": self._account_id,
                    "currency": self._currency,
                    "monetary_quantum": _dec_to_str(self._monetary_quantum),
                    "starting_capital": _dec_to_str(self._starting_capital),
                    "paper_session_id": self._paper_session_id,
                    "risk_policy_identity": self._risk_policy_identity,
                    "cost_schedule_fingerprint": self._cost_schedule_fingerprint,
                    "execution_policy_identity": self._execution_policy_identity,
                    "configuration_identity": self._configuration_identity,
                    "q93_contract_version": self.Q93_CONTRACT_VERSION,
                    "audit_environment": self._audit_environment,
                    "audit_source_identity": self._audit_source_identity,
                    "state_generation": "0",
                    "created_at": "1970-01-01T00:00:00+00:00",
                }
                for k, v in metadata.items():
                    cursor.execute("INSERT INTO paper_metadata (key, value) VALUES (?, ?);", (k, v))
                cursor.execute(
                    """
                    INSERT INTO account_state (
                        account_id, currency, monetary_quantum, starting_capital,
                        cash, realized_pnl, aggregate_exposure, as_of_timestamp,
                        accounting_sequence, accounting_integrity_breached
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        self._account_id,
                        self._currency,
                        _dec_to_str(self._monetary_quantum),
                        _dec_to_str(self._starting_capital),
                        _dec_to_str(self._starting_capital),
                        "0.00",
                        "0.00",
                        "1970-01-01T00:00:00+00:00",
                        0,
                        0,
                    ),
                )
                if self._initial_strategy_states_map:
                    now_str = _dt_to_str(recorded_at_utc_now())
                    for owner, initial_state in self._initial_strategy_states_map.items():
                        payload_json, fp = encode_strategy_state(initial_state)
                        cursor.execute(
                            """
                            INSERT INTO strategy_states (
                                strategy_id, strategy_version, paper_session_id,
                                configuration_identity, codec_version, state_json,
                                state_fingerprint, last_evaluated_decision_time,
                                state_generation, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 0, ?);
                            """,
                            (
                                owner.strategy_id,
                                owner.strategy_version,
                                self._paper_session_id,
                                self._configuration_identity,
                                STRATEGY_STATE_CODEC_VERSION,
                                payload_json,
                                fp,
                                now_str,
                            ),
                        )

                if self._initial_promotion_states_map:
                    now_str = _dt_to_str(recorded_at_utc_now())
                    for owner, p_state in self._initial_promotion_states_map.items():
                        cursor.execute(
                            """
                            INSERT INTO promotion_tracking_state (
                                strategy_id, strategy_version, paper_session_id,
                                configuration_identity, upstream_promotion_fingerprint,
                                tracking_status, activated_at, window_start_date,
                                clean_days_count, disqualified_days_count,
                                last_evaluated_session_date, milestone_status,
                                state_generation, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?);
                            """,
                            (
                                owner.strategy_id,
                                owner.strategy_version,
                                self._paper_session_id,
                                self._configuration_identity,
                                p_state.upstream_promotion_fingerprint,
                                p_state.tracking_status.value,
                                _dt_to_str(p_state.activated_at) if p_state.activated_at else None,
                                p_state.window_start_date.isoformat() if p_state.window_start_date else None,
                                p_state.clean_days_count,
                                p_state.disqualified_days_count,
                                p_state.last_evaluated_session_date.isoformat() if p_state.last_evaluated_session_date else None,
                                p_state.milestone_status.value,
                                _dt_to_str(p_state.updated_at),
                            ),
                        )

                self._database_instance_id = db_id
                self._state_generation = 0
            else:
                # Validate compatibility of existing metadata (ADR §120 OD-A through OD-H)
                stored_ver = rows.get("schema_version")
                if stored_ver != str(SCHEMA_VERSION):
                    raise DatabaseIdentityMismatchError(
                        f"Incompatible schema_version: database has {stored_ver}, expected {SCHEMA_VERSION}"
                    )

                stored_acc = rows.get("account_id")
                if stored_acc is None or stored_acc != self._account_id:
                    raise DatabaseIdentityMismatchError(
                        f"Mismatched account_id: database has {stored_acc!r}, expected {self._account_id!r}"
                    )

                stored_curr = rows.get("currency")
                if stored_curr is None or stored_curr != self._currency:
                    raise DatabaseIdentityMismatchError(
                        f"Mismatched currency: database has {stored_curr!r}, expected {self._currency!r}"
                    )

                stored_cap = rows.get("starting_capital")
                if stored_cap is None:
                    raise DatabaseIdentityMismatchError(
                        "Missing starting_capital in database metadata: database is legacy or unverifiable"
                    )
                if _str_to_dec(stored_cap) != self._starting_capital:
                    raise DatabaseIdentityMismatchError(
                        f"Mismatched starting_capital: database has {stored_cap!r}, expected {_dec_to_str(self._starting_capital)!r}"
                    )

                stored_quantum = rows.get("monetary_quantum")
                if stored_quantum is None:
                    raise DatabaseIdentityMismatchError(
                        "Missing monetary_quantum in database metadata: database is legacy or unverifiable"
                    )
                if _str_to_dec(stored_quantum) != self._monetary_quantum:
                    raise DatabaseIdentityMismatchError(
                        f"Mismatched monetary_quantum: database has {stored_quantum!r}, expected {_dec_to_str(self._monetary_quantum)!r}"
                    )

                stored_session = rows.get("paper_session_id")
                if stored_session is None or stored_session != self._paper_session_id:
                    raise DatabaseIdentityMismatchError(
                        f"Mismatched paper_session_id: database has {stored_session!r}, expected {self._paper_session_id!r}"
                    )

                stored_risk = rows.get("risk_policy_identity")
                if stored_risk is None:
                    raise IncompatibleContractError(
                        "Missing risk_policy_identity in database metadata: database is legacy or unverifiable"
                    )
                if stored_risk != self._risk_policy_identity:
                    raise IncompatibleContractError(
                        f"Mismatched risk_policy_identity: database has {stored_risk!r}, expected {self._risk_policy_identity!r}"
                    )

                stored_cost = rows.get("cost_schedule_fingerprint")
                if stored_cost is None:
                    raise IncompatibleContractError(
                        "Missing cost_schedule_fingerprint in database metadata: database is legacy or unverifiable"
                    )
                if stored_cost != self._cost_schedule_fingerprint:
                    raise IncompatibleContractError(
                        f"Mismatched cost_schedule_fingerprint: database has {stored_cost!r}, expected {self._cost_schedule_fingerprint!r}"
                    )

                stored_exec = rows.get("execution_policy_identity")
                if stored_exec is None:
                    raise IncompatibleContractError(
                        "Missing execution_policy_identity in database metadata: database is legacy or unverifiable"
                    )
                if stored_exec != self._execution_policy_identity:
                    raise IncompatibleContractError(
                        f"Mismatched execution_policy_identity: database has {stored_exec!r}, expected {self._execution_policy_identity!r}"
                    )

                stored_cfg = rows.get("configuration_identity")
                if stored_cfg is None:
                    raise DatabaseIdentityMismatchError(
                        "Missing configuration_identity in database metadata: database is legacy or unverifiable"
                    )
                if stored_cfg != self._configuration_identity:
                    raise DatabaseIdentityMismatchError(
                        f"Mismatched configuration_identity: database has {stored_cfg!r}, expected {self._configuration_identity!r}"
                    )

                # Phase 6 / ADR §125 (C2): an existing Schema-V7 database that
                # predates the Q93 contract MUST NOT be silently upgraded.
                stored_q93_contract = rows.get(self._Q93_CONTRACT_KEY)
                if stored_q93_contract is None:
                    raise IncompatibleContractError(
                        "Missing q93_contract_version in database metadata: "
                        "database predates the Q93 reporting contract and requires "
                        "a fresh paper session/database"
                    )
                if stored_q93_contract != self.Q93_CONTRACT_VERSION:
                    raise IncompatibleContractError(
                        f"Mismatched q93_contract_version: database has {stored_q93_contract!r}, "
                        f"expected {self.Q93_CONTRACT_VERSION!r}"
                    )

                # Phase 6 / ADR §123.1: durable audit-context identity evidence.
                stored_audit_env = rows.get("audit_environment")
                if stored_audit_env is None:
                    raise DatabaseIdentityMismatchError(
                        "Missing audit_environment in database metadata: database is legacy or unverifiable"
                    )
                if stored_audit_env != self._audit_environment:
                    raise DatabaseIdentityMismatchError(
                        f"Mismatched audit_environment: database has {stored_audit_env!r}, expected {self._audit_environment!r}"
                    )

                stored_audit_src = rows.get("audit_source_identity")
                if stored_audit_src is None:
                    raise DatabaseIdentityMismatchError(
                        "Missing audit_source_identity in database metadata: database is legacy or unverifiable"
                    )
                if stored_audit_src != self._audit_source_identity:
                    raise DatabaseIdentityMismatchError(
                        f"Mismatched audit_source_identity: database has {stored_audit_src!r}, expected {self._audit_source_identity!r}"
                    )

                if self._initial_strategy_states_map:
                    cursor.execute(
                        "SELECT strategy_id, strategy_version FROM strategy_states WHERE paper_session_id = ?;",
                        (self._paper_session_id,),
                    )
                    existing_owners = {SubscriptionOwnerKey(r[0], r[1]) for r in cursor.fetchall()}
                    for owner in self._initial_strategy_states_map:
                        if owner not in existing_owners:
                            raise IncompatibleContractError(
                                f"Missing strategy_states row for configured owner {owner!r} in database"
                            )

                if self._initial_promotion_states_map:
                    cursor.execute(
                        "SELECT strategy_id, strategy_version FROM promotion_tracking_state WHERE paper_session_id = ?;",
                        (self._paper_session_id,),
                    )
                    existing_p_owners = {SubscriptionOwnerKey(r[0], r[1]) for r in cursor.fetchall()}
                    for owner in self._initial_promotion_states_map:
                        if owner not in existing_p_owners:
                            raise IncompatibleContractError(
                                f"Missing promotion_tracking_state row for configured owner {owner!r} in database"
                            )

                self._database_instance_id = rows.get("database_instance_id", "")
                self._state_generation = int(rows.get("state_generation", 0))


            cursor.execute("COMMIT;")
        except Exception as err:
            cursor.execute("ROLLBACK;")
            self._health = PersistenceHealth.FAILED
            raise

    # ------------------------------------------------------------------
    # Transactional Execution Context
    # ------------------------------------------------------------------

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Cursor]:
        """Execute a state-changing database operation atomically in EXCLUSIVE mode."""
        if self._health is not PersistenceHealth.HEALTHY:
            raise PersistenceError("Cannot execute transaction: PersistenceHealth is FAILED")

        cursor = None
        try:
            cursor = self._conn.cursor()
            cursor.execute("BEGIN EXCLUSIVE TRANSACTION;")
            yield cursor
            # Increment monotonic state generation
            self._state_generation += 1
            cursor.execute(
                "UPDATE paper_metadata SET value = ? WHERE key = 'state_generation';",
                (str(self._state_generation),),
            )
            cursor.execute("COMMIT;")
        except AuditIntegrityError as err:
            if cursor is not None:
                try:
                    cursor.execute("ROLLBACK;")
                except Exception:
                    pass
            self._health = PersistenceHealth.FAILED
            logger.critical("SQLite transaction failed with AuditIntegrityError; persistence marked FAILED: %s", err, exc_info=True)
            raise
        except Exception as err:
            if cursor is not None:
                try:
                    cursor.execute("ROLLBACK;")
                except Exception:
                    pass
            self._health = PersistenceHealth.FAILED
            logger.critical("SQLite transaction failed; persistence marked FAILED: %s", err, exc_info=True)
            raise PersistenceError(f"Durable SQLite transaction failed: {err}") from err

    @contextmanager
    def audit_only_transaction(self) -> Iterator[sqlite3.Cursor]:
        """Execute standalone audit-only logging in EXCLUSIVE mode without incrementing state_generation."""
        if self._health is not PersistenceHealth.HEALTHY:
            raise PersistenceError("Cannot execute audit-only transaction: PersistenceHealth is FAILED")

        cursor = None
        try:
            cursor = self._conn.cursor()
            cursor.execute("BEGIN EXCLUSIVE TRANSACTION;")
            yield cursor
            cursor.execute("COMMIT;")
        except AuditIntegrityError as err:
            if cursor is not None:
                try:
                    cursor.execute("ROLLBACK;")
                except Exception:
                    pass
            self._health = PersistenceHealth.FAILED
            logger.critical("SQLite audit-only transaction failed with AuditIntegrityError; persistence marked FAILED: %s", err, exc_info=True)
            raise
        except Exception as err:
            if cursor is not None:
                try:
                    cursor.execute("ROLLBACK;")
                except Exception:
                    pass
            self._health = PersistenceHealth.FAILED
            logger.critical("SQLite audit-only transaction failed; persistence marked FAILED: %s", err, exc_info=True)
            raise PersistenceError(f"Durable SQLite audit-only transaction failed: {err}") from err

    def _insert_audit_events_in_transaction(
        self,
        cursor: sqlite3.Cursor,
        events: Sequence[AuditEvent],
        state_generation: int | None,
    ) -> tuple[AuditEvent, ...]:
        """Insert a sequence of AuditEvent records inside an active SQLite transaction.

        If an event_id is not present, it is inserted and given its audit_sequence.
        If an event_id is already present, its full semantic projection is compared:
        - If equal: idempotent no-op, returns existing.
        - If conflicting: raises AuditIntegrityError and rolls back transaction.
        """
        results: list[AuditEvent] = []
        for ordinal, event in enumerate(events):
            gen = state_generation if event.state_generation is None else event.state_generation
            ord_val = (
                event.transaction_event_ordinal
                if event.transaction_event_ordinal > 0 or len(events) == 1
                else ordinal
            )

            cursor.execute("SELECT * FROM audit_events WHERE event_id = ?;", (event.event_id,))
            existing = cursor.fetchone()

            target_event = replace(
                event,
                state_generation=gen,
                transaction_event_ordinal=ord_val,
                environment=self._audit_environment,
                run_id=self._paper_session_id,
                canonical_configuration_fingerprint=self._configuration_identity,
                source_identity=self._audit_source_identity,
            )

            if existing is not None:
                existing_ev = _row_to_audit_event(existing)
                if existing_ev.semantic_projection() != target_event.semantic_projection():
                    raise AuditIntegrityError(
                        f"Conflicting audit event for event_id={event.event_id!r}: "
                        f"existing projection differs from attempted projection"
                    )
                results.append(existing_ev)
            else:
                market_ts_str = _dt_to_str(target_event.market_timestamp)
                rec_at_str = _dt_to_str(target_event.recorded_at_utc)
                cursor.execute(
                    """
                    INSERT INTO audit_events (
                        event_id, event_schema_version, event_family, event_type,
                        aggregate_type, aggregate_identity, market_timestamp, recorded_at_utc,
                        state_generation, transaction_event_ordinal, correlation_id, causation_event_id,
                        strategy_id, strategy_version, instrument_key, position_key_json,
                        entry_intent_identity, broker_order_identity, trade_id, protective_id,
                        payload_version, payload_json,
                        environment, run_id, canonical_configuration_fingerprint,
                        source_identity, timeframe, status, severity
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        target_event.event_id,
                        target_event.event_schema_version,
                        target_event.event_family,
                        target_event.event_type,
                        target_event.aggregate_type,
                        target_event.aggregate_identity,
                        market_ts_str,
                        rec_at_str,
                        target_event.state_generation,
                        target_event.transaction_event_ordinal,
                        target_event.correlation_id,
                        target_event.causation_event_id,
                        target_event.strategy_id,
                        target_event.strategy_version,
                        target_event.instrument_key,
                        target_event.position_key_json,
                        target_event.entry_intent_identity,
                        target_event.broker_order_identity,
                        target_event.trade_id,
                        target_event.protective_id,
                        target_event.payload_version,
                        target_event.payload_json,
                        target_event.environment,
                        target_event.run_id,
                        target_event.canonical_configuration_fingerprint,
                        target_event.source_identity,
                        target_event.timeframe,
                        target_event.status,
                        target_event.severity,
                    ),
                )
                seq = cursor.lastrowid
                results.append(replace(target_event, audit_sequence=seq))
        return tuple(results)

    # ------------------------------------------------------------------
    # Strategy State Persistence & Atomic Transactions (P1-07 / ADR §121)
    # ------------------------------------------------------------------

    def save_strategy_state(
        self,
        *,
        strategy_id: str,
        strategy_version: str,
        state: dict[str, Any],
        last_evaluated_decision_time: datetime,
        audit_events: Sequence[AuditEvent] = (),
    ) -> int:
        """Atomic state save for non-actionable evaluation (HOLD, REJECTED, observation_only)."""
        payload_json, fp = encode_strategy_state(state)
        now_str = _dt_to_str(recorded_at_utc_now())
        dt_str = _dt_to_str(last_evaluated_decision_time)

        with self.transaction() as cursor:
            cursor.execute(
                """
                SELECT state_generation FROM strategy_states
                WHERE strategy_id = ? AND strategy_version = ?;
                """,
                (strategy_id, strategy_version),
            )
            row = cursor.fetchone()
            if row is None:
                raise PersistenceError(
                    f"Cannot save state for unknown strategy owner ({strategy_id}, {strategy_version})"
                )
            new_gen = int(row[0]) + 1

            cursor.execute(
                """
                UPDATE strategy_states SET
                    state_json = ?,
                    state_fingerprint = ?,
                    last_evaluated_decision_time = ?,
                    state_generation = ?,
                    updated_at = ?
                WHERE strategy_id = ? AND strategy_version = ?;
                """,
                (payload_json, fp, dt_str, new_gen, now_str, strategy_id, strategy_version),
            )

            if audit_events:
                self._insert_audit_events_in_transaction(cursor, audit_events, self._state_generation + 1)

            return new_gen

    def save_t1_entry_submission(
        self,
        *,
        intent_id: str,
        order: _PendingOrder,
        commitment: PremiumCommitmentRecord,
        plan: PreEntryProtectivePlan,
        nominal_stop_risk: Decimal | None = None,
        run_identity: str | None = None,
        strategy_state_transition: StrategyStateTransition | None = None,
        audit_events: Sequence[AuditEvent] = (),
    ) -> None:
        """Atomic Transaction T1: Opening Entry Submission with coupled strategy state."""
        with self.transaction() as cursor:
            # 1. Record entry intent
            cursor.execute(
                "INSERT OR REPLACE INTO entry_intents (intent_id, lifecycle_state, created_at) VALUES (?, ?, ?);",
                (intent_id, "SUBMITTED", _dt_to_str(order.submission_market_timestamp)),
            )

            # 2. Record premium commitment
            cursor.execute(
                """
                INSERT OR REPLACE INTO premium_commitments (
                    reservation_key, strategy_id, strategy_version, instrument_key,
                    identity_json, approved_quantity, worst_permitted_fill_price,
                    contract_multiplier, required_cash, market_time, nominal_stop_risk
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    commitment.reservation_key,
                    commitment.strategy_id,
                    commitment.strategy_version,
                    _identity_canonical_key(commitment.identity),
                    json.dumps(_identity_to_dict(commitment.identity)),
                    _dec_to_str(commitment.approved_quantity),
                    _dec_to_str(commitment.worst_permitted_fill_price),
                    _dec_to_str(commitment.contract_multiplier),
                    _dec_to_str(commitment.required_cash),
                    _dt_to_str(commitment.created_at_market_time),
                    _dec_to_str(nominal_stop_risk),
                ),
            )

            # 3. Record pending broker order
            cursor.execute(
                """
                INSERT OR REPLACE INTO broker_orders (
                    order_id, broker_order_identity, entry_intent_identity, action,
                    order_type, quantity, limit_price, stop_price, time_in_force,
                    lifecycle_state, submission_market_timestamp, eligibility_timestamp,
                    reference_price, price_increment, stop_triggered, stop_limit_activated,
                    instrument_identity_json, specification_json, original_order_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    order.order_id,
                    order.broker_order_identity,
                    intent_id,
                    order.original_order.action,
                    order.original_order.order_type.value,
                    _dec_to_str(order.original_order.quantity),
                    _dec_to_str(order.original_order.limit_price),
                    _dec_to_str(order.original_order.stop_price),
                    order.original_order.time_in_force.value,
                    order.lifecycle_state.value,
                    _dt_to_str(order.submission_market_timestamp),
                    _dt_to_str(getattr(order, "eligibility_timestamp", None)),
                    _dec_to_str(getattr(order, "reference_price", getattr(order, "submission_quote", None) and getattr(order.submission_quote, "mid_price", None))),
                    _dec_to_str(getattr(order, "price_increment", getattr(getattr(order, "specification", None), "price_increment", Decimal("0.05")))),
                    1 if getattr(order, "stop_triggered", False) else 0,
                    1 if getattr(order, "stop_limit_activated", False) else 0,
                    json.dumps(_identity_to_dict(order.instrument_identity)),
                    json.dumps(_spec_to_dict(getattr(order, "specification", None))) if getattr(order, "specification", None) is not None else "{}",
                    json.dumps(_order_to_dict(order.original_order)),
                ),
            )

            # 4. Record retained protective plan
            cursor.execute(
                """
                INSERT OR REPLACE INTO retained_protective_plans (
                    order_id, plan_json, quantity, run_identity
                ) VALUES (?, ?, ?, ?);
                """,
                (
                    order.order_id,
                    json.dumps(_plan_to_dict(plan)),
                    _dec_to_str(order.original_order.quantity),
                    run_identity,
                ),
            )

            # 5. Coupled strategy state transition inside the same SQLite atomic transaction
            if strategy_state_transition is not None:
                st = strategy_state_transition
                payload_json, fp = encode_strategy_state(st.state)
                now_str = _dt_to_str(recorded_at_utc_now())
                dt_str = _dt_to_str(st.last_evaluated_decision_time)

                cursor.execute(
                    """
                    SELECT state_generation FROM strategy_states
                    WHERE strategy_id = ? AND strategy_version = ?;
                    """,
                    (st.strategy_id, st.strategy_version),
                )
                row = cursor.fetchone()
                if row is None:
                    raise PersistenceError(
                        f"Cannot save state for unknown strategy owner ({st.strategy_id}, {st.strategy_version})"
                    )
                new_gen = int(row[0]) + 1

                cursor.execute(
                    """
                    UPDATE strategy_states SET
                        state_json = ?,
                        state_fingerprint = ?,
                        last_evaluated_decision_time = ?,
                        state_generation = ?,
                        updated_at = ?
                    WHERE strategy_id = ? AND strategy_version = ?;
                    """,
                    (payload_json, fp, dt_str, new_gen, now_str, st.strategy_id, st.strategy_version),
                )

            # 6. Insert atomic state audit events
            if audit_events:
                self._insert_audit_events_in_transaction(cursor, audit_events, self._state_generation + 1)

    def save_t2_opening_fill(
        self,
        *,
        terminal_event: BrokerTerminalEvent,
        accounting_result: AccountingResult,
        account_snapshot: AccountSnapshot,
        accounting_sequence: int,
        released_reservation_key: str | None,
        materialized_exits: Sequence[ProtectiveExit],
        retained_order_id_to_remove: str | None,
        entry_intent_id: str | None = None,
        risk_gate_state: RiskGateState | None = None,
        cost_assessment: CostAssessment | None = None,
        audit_events: Sequence[AuditEvent] = (),
    ) -> None:
        """Atomic Transaction T2: Opening Order Filled."""
        with self.transaction() as cursor:
            # 1. Update broker order to terminal FILLED
            exec_res = terminal_event.execution_result
            cursor.execute(
                """
                UPDATE broker_orders SET
                    lifecycle_state = ?,
                    terminal_market_timestamp = ?,
                    terminal_reason = ?,
                    execution_result_json = ?
                WHERE order_id = ?;
                """,
                (
                    terminal_event.lifecycle_state.value,
                    _dt_to_str(terminal_event.market_timestamp),
                    terminal_event.reason,
                    json.dumps(_exec_result_to_dict(exec_res)) if exec_res else None,
                    terminal_event.order_id,
                ),
            )

            # 2. Record processed fill idempotency evidence
            if exec_res is not None:
                fee_val = getattr(exec_res, "fee", Decimal("0"))
                fp = _compute_fill_fingerprint(
                    broker_order_identity=terminal_event.broker_order_identity,
                    order_id=terminal_event.order_id,
                    lifecycle_state=terminal_event.lifecycle_state.value,
                    instrument_identity=terminal_event.instrument_identity,
                    fill_price=exec_res.fill_price,
                    filled_quantity=exec_res.filled_quantity,
                    fee=fee_val,
                    fill_timestamp=exec_res.execution_bar_timestamp,
                )
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO processed_fills (
                        broker_order_identity, order_id, lifecycle_state, instrument_key,
                        fill_price, filled_quantity, fee, fill_timestamp, semantic_fingerprint,
                        event_json, result_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        terminal_event.broker_order_identity,
                        terminal_event.order_id,
                        terminal_event.lifecycle_state.value,
                        _identity_canonical_key(terminal_event.instrument_identity),
                        _dec_to_str(exec_res.fill_price),
                        _dec_to_str(exec_res.filled_quantity),
                        _dec_to_str(fee_val),
                        _dt_to_str(exec_res.execution_bar_timestamp),
                        fp,
                        json.dumps(_exec_result_to_dict(exec_res)),
                        json.dumps({"outcome": accounting_result.outcome.value}),
                    ),
                )

            # 3. Update account state and positions
            self._save_account_state_and_positions(cursor, account_snapshot, accounting_sequence, False)

            # 4. Release premium reservation
            if released_reservation_key:
                cursor.execute(
                    "DELETE FROM premium_commitments WHERE reservation_key = ?;",
                    (released_reservation_key,),
                )
            cursor.execute(
                "DELETE FROM premium_commitments WHERE reservation_key = ?;",
                (terminal_event.order_id,),
            )

            # 5. Remove retained protective plan
            if retained_order_id_to_remove:
                cursor.execute(
                    "DELETE FROM retained_protective_plans WHERE order_id = ?;",
                    (retained_order_id_to_remove,),
                )

            # 6. Materialize protective exits
            for exit_item in materialized_exits:
                self._save_protective_exit(cursor, exit_item)

            # 7. Update entry intent if provided
            if entry_intent_id:
                cursor.execute(
                    "UPDATE entry_intents SET lifecycle_state = ? WHERE intent_id = ?;",
                    ("FILLED", entry_intent_id),
                )

            # 8. Save updated RiskGateState
            if risk_gate_state is not None:
                self._save_risk_gate_state(cursor, risk_gate_state)

            # 9. Save cost assessment if any
            if cost_assessment is not None:
                self._save_cost_assessment(cursor, cost_assessment)

            # 10. Insert atomic state audit events
            if audit_events:
                self._insert_audit_events_in_transaction(cursor, audit_events, self._state_generation + 1)

    def save_t3_protective_submission(
        self,
        *,
        pending_close: LiveProtectivePendingClose,
        close_order: _PendingOrder,
        updated_exits: Sequence[ProtectiveExit] = (),
        audit_events: Sequence[AuditEvent] = (),
    ) -> None:
        """Atomic Transaction T3: Protective Exit Trigger Submission."""
        with self.transaction() as cursor:
            # 1. Record pending protective close order in broker_orders
            cursor.execute(
                """
                INSERT OR REPLACE INTO broker_orders (
                    order_id, broker_order_identity, entry_intent_identity, action,
                    order_type, quantity, limit_price, stop_price, time_in_force,
                    lifecycle_state, submission_market_timestamp, eligibility_timestamp,
                    reference_price, price_increment, stop_triggered, stop_limit_activated,
                    instrument_identity_json, specification_json, original_order_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    close_order.order_id,
                    close_order.broker_order_identity,
                    None,
                    close_order.original_order.action,
                    close_order.original_order.order_type.value,
                    _dec_to_str(close_order.original_order.quantity),
                    _dec_to_str(close_order.original_order.limit_price),
                    _dec_to_str(close_order.original_order.stop_price),
                    close_order.original_order.time_in_force.value,
                    close_order.lifecycle_state.value,
                    _dt_to_str(getattr(close_order, "submission_market_timestamp", None)),
                    _dt_to_str(getattr(close_order, "eligibility_timestamp", None)),
                    _dec_to_str(getattr(close_order, "reference_price", None)),
                    _dec_to_str(getattr(close_order, "price_increment", getattr(getattr(close_order, "specification", None), "price_increment", Decimal("0.05")))),
                    1 if getattr(close_order, "stop_triggered", False) else 0,
                    1 if getattr(close_order, "stop_limit_activated", False) else 0,
                    json.dumps(_identity_to_dict(close_order.instrument_identity)),
                    json.dumps(_spec_to_dict(getattr(close_order, "specification", None))) if getattr(close_order, "specification", None) is not None else "{}",
                    json.dumps(_order_to_dict(close_order.original_order)),
                ),
            )

            # 2. Save any updated exits first before pending close reference
            for ex in updated_exits:
                self._save_protective_exit(cursor, ex)

            # 3. Record in protective_pending_closes
            cursor.execute(
                """
                INSERT OR REPLACE INTO protective_pending_closes (
                    strategy_id, strategy_version, instrument_key, order_id,
                    broker_order_identity, protective_id, kind, trigger_price, trigger_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    pending_close.position_key.strategy_id,
                    pending_close.position_key.strategy_version,
                    _identity_canonical_key(pending_close.position_key.identity),
                    pending_close.order_id,
                    pending_close.broker_order_identity,
                    pending_close.protective_id,
                    pending_close.kind.value,
                    _dec_to_str(pending_close.trigger_price),
                    _dt_to_str(pending_close.trigger_timestamp),
                ),
            )

            # 4. Insert atomic state audit events
            if audit_events:
                self._insert_audit_events_in_transaction(cursor, audit_events, self._state_generation + 1)

    def save_strategy_exit_submission(
        self,
        *,
        close_order: _PendingOrder,
        strategy_state_transition: StrategyStateTransition | None = None,
        expected_state_generation: int | None = None,
        audit_events: Sequence[AuditEvent] = (),
    ) -> int | None:
        """Atomic Transaction S1: Generic Strategy Exit Close Submission.

        Persists exactly the generic broker-order record plus the
        STRATEGY_EXIT_REQUESTED audit evidence in one transaction.
        Optionally couples an atomic strategy-state update: if
        ``strategy_state_transition`` is provided, the state-generation guard
        ``expected_state_generation`` is checked atomically and the state is
        advanced within the same transaction.

        Deliberately writes NO protective tables: a strategy exit is not a
        ProtectiveExit, so no ``protective_pending_closes`` row, no placeholder
        ``kind``, no fake ``protective_id``, and no synthetic ``trigger_price``
        may ever be created for it. Durable pending-close identity and restart
        reconciliation derive solely from this ``broker_orders`` row (QUEUED
        EXIT order with full owner provenance in ``original_order_json``).

        Returns the new state_generation if a state transition was persisted,
        or None otherwise.
        """
        if strategy_state_transition is not None and expected_state_generation is not None:
            if not isinstance(expected_state_generation, int) or expected_state_generation < 0:
                raise ValueError("expected_state_generation must be a non-negative int")
        if expected_state_generation is not None and strategy_state_transition is None:
            raise ValueError("expected_state_generation requires strategy_state_transition")
        new_generation: int | None = None
        with self.transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO broker_orders (
                    order_id, broker_order_identity, entry_intent_identity, action,
                    order_type, quantity, limit_price, stop_price, time_in_force,
                    lifecycle_state, submission_market_timestamp, eligibility_timestamp,
                    reference_price, price_increment, stop_triggered, stop_limit_activated,
                    instrument_identity_json, specification_json, original_order_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    close_order.order_id,
                    close_order.broker_order_identity,
                    None,
                    close_order.original_order.action,
                    close_order.original_order.order_type.value,
                    _dec_to_str(close_order.original_order.quantity),
                    _dec_to_str(close_order.original_order.limit_price),
                    _dec_to_str(close_order.original_order.stop_price),
                    close_order.original_order.time_in_force.value,
                    close_order.lifecycle_state.value,
                    _dt_to_str(getattr(close_order, "submission_market_timestamp", None)),
                    _dt_to_str(getattr(close_order, "eligibility_timestamp", None)),
                    _dec_to_str(getattr(close_order, "reference_price", None)),
                    _dec_to_str(getattr(close_order, "price_increment", getattr(getattr(close_order, "specification", None), "price_increment", Decimal("0.05")))),
                    1 if getattr(close_order, "stop_triggered", False) else 0,
                    1 if getattr(close_order, "stop_limit_activated", False) else 0,
                    json.dumps(_identity_to_dict(close_order.instrument_identity)),
                    json.dumps(_spec_to_dict(getattr(close_order, "specification", None))) if getattr(close_order, "specification", None) is not None else "{}",
                    json.dumps(_order_to_dict(close_order.original_order)),
                ),
            )

            if strategy_state_transition is not None:
                encoded_state = encode_strategy_state(strategy_state_transition.state)
                cursor.execute(
                    "SELECT state_generation FROM strategy_states WHERE strategy_id = ? AND strategy_version = ?;",
                    (strategy_state_transition.strategy_id, strategy_state_transition.strategy_version),
                )
                row = cursor.fetchone()
                if row is None:
                    raise PersistenceError(
                        f"Cannot save strategy exit state for unknown strategy owner "
                        f"({strategy_state_transition.strategy_id}, {strategy_state_transition.strategy_version})"
                    )
                current_generation = int(row[0])
                if expected_state_generation is not None and current_generation != expected_state_generation:
                    raise PersistenceError(
                        f"stale strategy exit state generation: expected {expected_state_generation}, got {current_generation}"
                    )
                new_generation = current_generation + 1
                cursor.execute(
                    """
                    UPDATE strategy_states SET state_json = ?, state_fingerprint = ?,
                        last_evaluated_decision_time = ?, state_generation = ?, updated_at = ?
                    WHERE strategy_id = ? AND strategy_version = ?;
                    """,
                    (
                        encoded_state[0], encoded_state[1],
                        _dt_to_str(strategy_state_transition.last_evaluated_decision_time),
                        new_generation, _dt_to_str(recorded_at_utc_now()),
                        strategy_state_transition.strategy_id, strategy_state_transition.strategy_version,
                    ),
                )

            # Insert atomic state audit events
            if audit_events:
                self._insert_audit_events_in_transaction(cursor, audit_events, self._state_generation + 1)
        return new_generation

    def save_t4_protective_fill(
        self,
        *,
        terminal_event: BrokerTerminalEvent,
        accounting_result: AccountingResult,
        account_snapshot: AccountSnapshot,
        accounting_sequence: int,
        cleared_pending_close_position_key: PositionKey | None,
        updated_exits: Sequence[ProtectiveExit],
        trade_record: TradeRecord | None = None,
        cost_assessment: CostAssessment | None = None,
        trade_ledger: TradeLedger | None = None,
        audit_events: Sequence[AuditEvent] = (),
    ) -> None:
        """Atomic Transaction T4: Protective Exit Order Filled."""
        with self.transaction() as cursor:
            # 1. Update broker order to terminal FILLED
            exec_res = terminal_event.execution_result
            cursor.execute(
                """
                UPDATE broker_orders SET
                    lifecycle_state = ?,
                    terminal_market_timestamp = ?,
                    terminal_reason = ?,
                    execution_result_json = ?
                WHERE order_id = ?;
                """,
                (
                    terminal_event.lifecycle_state.value,
                    _dt_to_str(terminal_event.market_timestamp),
                    terminal_event.reason,
                    json.dumps(_exec_result_to_dict(exec_res)) if exec_res else None,
                    terminal_event.order_id,
                ),
            )

            # 2. Record processed fill idempotency evidence
            if exec_res is not None:
                fee_val = getattr(exec_res, "fee", Decimal("0"))
                fp = _compute_fill_fingerprint(
                    broker_order_identity=terminal_event.broker_order_identity,
                    order_id=terminal_event.order_id,
                    lifecycle_state=terminal_event.lifecycle_state.value,
                    instrument_identity=terminal_event.instrument_identity,
                    fill_price=exec_res.fill_price,
                    filled_quantity=exec_res.filled_quantity,
                    fee=fee_val,
                    fill_timestamp=exec_res.execution_bar_timestamp,
                )
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO processed_fills (
                        broker_order_identity, order_id, lifecycle_state, instrument_key,
                        fill_price, filled_quantity, fee, fill_timestamp, semantic_fingerprint,
                        event_json, result_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        terminal_event.broker_order_identity,
                        terminal_event.order_id,
                        terminal_event.lifecycle_state.value,
                        _identity_canonical_key(terminal_event.instrument_identity),
                        _dec_to_str(exec_res.fill_price),
                        _dec_to_str(exec_res.filled_quantity),
                        _dec_to_str(fee_val),
                        _dt_to_str(exec_res.execution_bar_timestamp),
                        fp,
                        json.dumps(_exec_result_to_dict(exec_res)),
                        json.dumps({"outcome": accounting_result.outcome.value}),
                    ),
                )

            # 3. Update account state and positions
            self._save_account_state_and_positions(cursor, account_snapshot, accounting_sequence, False)

            # 4. Remove protective pending close
            if cleared_pending_close_position_key is not None:
                cursor.execute(
                    """
                    DELETE FROM protective_pending_closes
                    WHERE strategy_id = ? AND strategy_version = ? AND instrument_key = ?;
                    """,
                    (
                        cleared_pending_close_position_key.strategy_id,
                        cleared_pending_close_position_key.strategy_version,
                        _identity_canonical_key(cleared_pending_close_position_key.identity),
                    ),
                )

            # 5. Update protective exits (filled & OCO cancelled siblings)
            for exit_item in updated_exits:
                self._save_protective_exit(cursor, exit_item)

            # 6. Save trade record & cost assessment
            if trade_record is not None:
                self._save_trade_record(cursor, trade_record)
            if cost_assessment is not None:
                self._save_cost_assessment(cursor, cost_assessment)

            # 7. Save trade ledger open pending lifecycles
            if trade_ledger is not None:
                self._save_trade_ledger_pending(cursor, trade_ledger)

            # 8. Insert atomic state audit events
            if audit_events:
                self._insert_audit_events_in_transaction(cursor, audit_events, self._state_generation + 1)

    def save_t5_terminal_non_fill(
        self,
        *,
        terminal_event: BrokerTerminalEvent,
        released_reservation_key: str | None = None,
        cleared_pending_close_position_key: PositionKey | None = None,
        retained_order_id_to_remove: str | None = None,
        entry_intent_id: str | None = None,
        audit_events: Sequence[AuditEvent] = (),
    ) -> None:
        """Atomic Transaction T5: Terminal Non-Fill (Cancel / Expire / Reject)."""
        with self.transaction() as cursor:
            # 1. Update broker order to terminal non-filled state
            cursor.execute(
                """
                UPDATE broker_orders SET
                    lifecycle_state = ?,
                    terminal_market_timestamp = ?,
                    terminal_reason = ?
                WHERE order_id = ?;
                """,
                (
                    terminal_event.lifecycle_state.value,
                    _dt_to_str(terminal_event.market_timestamp),
                    terminal_event.reason,
                    terminal_event.order_id,
                ),
            )

            # 2. Release premium reservation if opening order
            if released_reservation_key:
                cursor.execute(
                    "DELETE FROM premium_commitments WHERE reservation_key = ?;",
                    (released_reservation_key,),
                )
            cursor.execute(
                "DELETE FROM premium_commitments WHERE reservation_key = ?;",
                (terminal_event.order_id,),
            )

            # 3. Discard retained protective plan if opening order
            if retained_order_id_to_remove:
                cursor.execute(
                    "DELETE FROM retained_protective_plans WHERE order_id = ?;",
                    (retained_order_id_to_remove,),
                )

            # 4. Clear pending close lock if protective order
            if cleared_pending_close_position_key:
                cursor.execute(
                    """
                    DELETE FROM protective_pending_closes
                    WHERE strategy_id = ? AND strategy_version = ? AND instrument_key = ?;
                    """,
                    (
                        cleared_pending_close_position_key.strategy_id,
                        cleared_pending_close_position_key.strategy_version,
                        _identity_canonical_key(cleared_pending_close_position_key.identity),
                    ),
                )

            # 5. Update entry intent if applicable
            if entry_intent_id:
                cursor.execute(
                    "UPDATE entry_intents SET lifecycle_state = ? WHERE intent_id = ?;",
                    (terminal_event.lifecycle_state.value, entry_intent_id),
                )

            # 6. Insert atomic state audit events
            if audit_events:
                self._insert_audit_events_in_transaction(cursor, audit_events, self._state_generation + 1)

    def save_t6_trailing_ratchet(
        self,
        exits: Sequence[ProtectiveExit],
        audit_events: Sequence[AuditEvent] = (),
        strategy_state_transitions: Sequence[StrategyStateTransition] = (),
        expected_state_generations: Mapping[tuple[str, str], int] | None = None,
    ) -> dict[tuple[str, str], int]:
        """Atomic Transaction T6: Trailing Stop Ratchet with optional coupled strategy state.

        Persists all protective exits + audit events + optional strategy-state
        updates in one atomic transaction.  ``strategy_state_transitions`` is a
        sequence of ``StrategyStateTransition`` payloads; each is checked against
        ``expected_state_generations`` (if provided) and persisted atomically.

        Returns a mapping of ``(strategy_id, strategy_version) -> new_generation``
        for each successfully persisted state transition.
        """
        advanced_generations: dict[tuple[str, str], int] = {}
        with self.transaction() as cursor:
            for ex in exits:
                self._save_protective_exit(cursor, ex)

            for st in strategy_state_transitions:
                cursor.execute(
                    "SELECT state_generation FROM strategy_states WHERE strategy_id = ? AND strategy_version = ?;",
                    (st.strategy_id, st.strategy_version),
                )
                row = cursor.fetchone()
                if row is None:
                    raise PersistenceError(
                        f"Cannot save trailing state for unknown strategy owner "
                        f"({st.strategy_id}, {st.strategy_version})"
                    )
                current_generation = int(row[0])
                if expected_state_generations is not None:
                    expected = expected_state_generations.get((st.strategy_id, st.strategy_version))
                    if expected is not None and current_generation != expected:
                        raise PersistenceError(
                            f"stale trailing state generation for ({st.strategy_id}, {st.strategy_version}): "
                            f"expected {expected}, got {current_generation}"
                        )
                encoded_state = encode_strategy_state(st.state)
                new_generation = current_generation + 1
                cursor.execute(
                    """
                    UPDATE strategy_states SET state_json = ?, state_fingerprint = ?,
                        last_evaluated_decision_time = ?, state_generation = ?, updated_at = ?
                    WHERE strategy_id = ? AND strategy_version = ?;
                    """,
                    (
                        encoded_state[0], encoded_state[1],
                        _dt_to_str(st.last_evaluated_decision_time),
                        new_generation, _dt_to_str(recorded_at_utc_now()),
                        st.strategy_id, st.strategy_version,
                    ),
                )
                advanced_generations[(st.strategy_id, st.strategy_version)] = new_generation

            # Insert atomic state audit events
            if audit_events:
                self._insert_audit_events_in_transaction(cursor, audit_events, self._state_generation + 1)
        return advanced_generations

    def save_runtime_policy_decision(
        self,
        *,
        decision_owner: SubscriptionOwnerKey,
        protective_exits: Sequence[ProtectiveExit],
        strategy_state_transition: StrategyStateTransition | None = None,
        expected_state_generation: int | None = None,
        audit_events: Sequence[AuditEvent] = (),
    ) -> int | None:
        """Atomically persist one accepted generic runtime-policy decision.

        The policy itself supplies no database access. The caller supplies one
        exact decision owner and constructs
        validated candidate exits/state and this boundary commits all durable
        effects together, or none of them.  ``expected_state_generation`` is
        an optional exact optimistic-concurrency guard for callback state.
        """
        if not isinstance(decision_owner, SubscriptionOwnerKey):
            raise TypeError("decision_owner must be a SubscriptionOwnerKey")
        exits = tuple(protective_exits)
        if not all(isinstance(item, ProtectiveExit) for item in exits):
            raise TypeError("protective_exits must contain ProtectiveExit values")
        if strategy_state_transition is not None and not isinstance(strategy_state_transition, StrategyStateTransition):
            raise TypeError("strategy_state_transition must be a StrategyStateTransition or None")
        if expected_state_generation is not None and (
            not isinstance(expected_state_generation, int) or expected_state_generation < 0
        ):
            raise ValueError("expected_state_generation must be a non-negative int or None")
        if expected_state_generation is not None and strategy_state_transition is None:
            raise ValueError("expected_state_generation requires strategy_state_transition")
        if not exits and strategy_state_transition is None and not audit_events:
            raise ValueError("runtime policy decision requires at least one mutation or audit event")
        for exit_item in exits:
            if (
                exit_item.position_key.strategy_id != decision_owner.strategy_id
                or exit_item.position_key.strategy_version != decision_owner.strategy_version
            ):
                raise ValueError("protective exit owner does not match decision_owner")
        if strategy_state_transition is not None and (
            strategy_state_transition.strategy_id != decision_owner.strategy_id
            or strategy_state_transition.strategy_version != decision_owner.strategy_version
        ):
            raise ValueError("strategy state transition owner does not match decision_owner")
        for event in audit_events:
            if not isinstance(event, AuditEvent):
                raise TypeError("audit_events must contain AuditEvent values")
            if event.strategy_id is not None and event.strategy_id != decision_owner.strategy_id:
                raise ValueError("audit event strategy_id does not match decision_owner")
            if event.strategy_version is not None and event.strategy_version != decision_owner.strategy_version:
                raise ValueError("audit event strategy_version does not match decision_owner")

        encoded_state: tuple[str, str] | None = None
        if strategy_state_transition is not None:
            encoded_state = encode_strategy_state(strategy_state_transition.state)
            if (
                strategy_state_transition.last_evaluated_decision_time.tzinfo is None
                or strategy_state_transition.last_evaluated_decision_time.utcoffset() is None
            ):
                raise ValueError("strategy state transition timestamp must be timezone-aware")

        with self.transaction() as cursor:
            for exit_item in sorted(exits, key=lambda item: item.protective_id):
                self._save_protective_exit(cursor, exit_item)

            new_generation: int | None = None
            if strategy_state_transition is not None and encoded_state is not None:
                cursor.execute(
                    "SELECT state_generation FROM strategy_states WHERE strategy_id = ? AND strategy_version = ?;",
                    (strategy_state_transition.strategy_id, strategy_state_transition.strategy_version),
                )
                row = cursor.fetchone()
                if row is None:
                    raise PersistenceError(
                        "Cannot save runtime policy state for unknown strategy owner "
                        f"({strategy_state_transition.strategy_id}, {strategy_state_transition.strategy_version})"
                    )
                current_generation = int(row[0])
                if expected_state_generation is not None and current_generation != expected_state_generation:
                    raise PersistenceError(
                        f"stale runtime policy state generation: expected {expected_state_generation}, got {current_generation}"
                    )
                new_generation = current_generation + 1
                cursor.execute(
                    """
                    UPDATE strategy_states SET state_json = ?, state_fingerprint = ?,
                        last_evaluated_decision_time = ?, state_generation = ?, updated_at = ?
                    WHERE strategy_id = ? AND strategy_version = ?;
                    """,
                    (
                        encoded_state[0], encoded_state[1],
                        _dt_to_str(strategy_state_transition.last_evaluated_decision_time),
                        new_generation, _dt_to_str(recorded_at_utc_now()),
                        strategy_state_transition.strategy_id, strategy_state_transition.strategy_version,
                    ),
                )

            if audit_events:
                self._insert_audit_events_in_transaction(
                    cursor,
                    tuple(sorted(audit_events, key=lambda event: event.event_id)),
                    self._state_generation + 1,
                )
            return new_generation

    def save_watermark_advance(
        self,
        watermarks: Mapping[InstrumentIdentity, datetime],
    ) -> None:
        """Persist updated broker per-instrument exchange timestamp watermarks."""
        with self.transaction() as cursor:
            for ident, ts in watermarks.items():
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO broker_watermarks (
                        instrument_key, last_exchange_timestamp, identity_json
                    ) VALUES (?, ?, ?);
                    """,
                    (_identity_canonical_key(ident), _dt_to_str(ts), json.dumps(_identity_to_dict(ident))),
                )

    def save_session_rollover(
        self,
        risk_gate_state: RiskGateState,
        audit_events: Sequence[AuditEvent] = (),
    ) -> None:
        """Atomic persistence of daily session rollover."""
        with self.transaction() as cursor:
            self._save_risk_gate_state(cursor, risk_gate_state)
            if audit_events:
                self._insert_audit_events_in_transaction(cursor, audit_events, self._state_generation + 1)

    def save_accounting_integrity_breached(self, breached: bool = True) -> None:
        """Persist accounting integrity breach flag."""
        with self.transaction() as cursor:
            cursor.execute(
                "UPDATE account_state SET accounting_integrity_breached = ? WHERE account_id = ?;",
                (1 if breached else 0, self._account_id),
            )

    def save_safety_state(
        self,
        *,
        kill_switch_active: bool,
        kill_switch_reason: str | None = None,
        activation_source: str | None = None,
        activation_market_timestamp: datetime | None = None,
        activated_at: str | None = None,
        audit_events: Sequence[AuditEvent] = (),
    ) -> None:
        """Atomic persistence of durable kill-switch state."""
        with self.transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO safety_state (
                    account_id, kill_switch_active, kill_switch_reason,
                    activation_source, activation_market_timestamp, activated_at
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    self._account_id,
                    1 if kill_switch_active else 0,
                    kill_switch_reason,
                    activation_source,
                    _dt_to_str(activation_market_timestamp),
                    activated_at,
                ),
            )
            if audit_events:
                self._insert_audit_events_in_transaction(cursor, audit_events, self._state_generation + 1)

    # ------------------------------------------------------------------
    # Public Audit Journal Query & Standalone Append API
    # ------------------------------------------------------------------

    def append_audit_events(self, events: Sequence[AuditEvent]) -> tuple[AuditEvent, ...]:
        """Durably append non-state observational audit events in a standalone transaction (state_generation=NULL)."""
        if not events:
            return ()
        with self.audit_only_transaction() as cursor:
            return self._insert_audit_events_in_transaction(cursor, events, state_generation=None)

    def append_error_evidence_once(
        self,
        event: AuditEvent,
        *,
        error_class: str,
        strategy_id: str | None,
    ) -> tuple[AuditEvent, bool]:
        """Atomically persist ONE first-occurrence E21 ERROR evidence row.

        Frozen dedup tuple (ADR §123.3(d)): (paper_session_id, strategy_id,
        error_class). `event_type` deliberately does NOT participate. The
        session dimension is structural: this journal is bound 1:1 to one
        paper session, enforced here via this database's durable run_id.

        The existence check and the insert share ONE exclusive transaction
        (`audit_only_transaction`, BEGIN EXCLUSIVE), so concurrent emitters
        serialize at the SQLite level and exactly one row per exact tuple can
        ever be committed — restart-safe and concurrency-safe without any
        second authority, migration, trigger, or hash chain.

        Returns (durable_event, appended) where appended is False when an
        existing row for the exact tuple suppressed this occurrence.
        """
        if not isinstance(error_class, str) or not error_class.strip():
            raise ValueError("error_class must be a non-empty string")
        if event.event_family != AuditEventFamily.ERROR.value:
            raise ValueError("append_error_evidence_once requires event_family ERROR")
        if event.event_type not in (
            AuditEventType.STRATEGY_EXCEPTION.value,
            AuditEventType.RUNTIME_ERROR.value,
        ):
            raise ValueError(
                "append_error_evidence_once requires STRATEGY_EXCEPTION or RUNTIME_ERROR"
            )
        if strategy_id is not None and (not isinstance(strategy_id, str) or not strategy_id.strip()):
            raise ValueError("strategy_id must be a non-empty string or None")

        with self.audit_only_transaction() as cursor:
            cursor.execute(
                """
                SELECT * FROM audit_events
                WHERE event_family = 'ERROR'
                  AND run_id = ?
                  AND strategy_id IS ?
                  AND aggregate_identity = ?
                LIMIT 1;
                """,
                (self._paper_session_id, strategy_id, error_class),
            )
            existing = cursor.fetchone()
            if existing is not None:
                return _row_to_audit_event(existing), False
            inserted = self._insert_audit_events_in_transaction(cursor, [event], state_generation=None)[0]
            return inserted, True

    def query_audit_events(
        self,
        *,
        event_family: str | AuditEventFamily | None = None,
        event_type: str | AuditEventType | None = None,
        aggregate_type: str | None = None,
        aggregate_identity: str | None = None,
        entry_intent_identity: str | None = None,
        broker_order_identity: str | None = None,
        trade_id: str | None = None,
        protective_id: str | None = None,
        correlation_id: str | None = None,
        start_market_time: datetime | None = None,
        end_market_time: datetime | None = None,
        since_sequence: int | None = None,
        until_sequence: int | None = None,
        since_audit_sequence: int | None = None,
        until_audit_sequence: int | None = None,
        order_id: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[AuditEvent, ...]:
        """Query audit events with optional filtering."""
        clauses: list[str] = []
        params: list[Any] = []

        if event_family is not None:
            fam = event_family.value if isinstance(event_family, Enum) else str(event_family)
            clauses.append("event_family = ?")
            params.append(fam)

        if event_type is not None:
            typ = event_type.value if isinstance(event_type, Enum) else str(event_type)
            clauses.append("event_type = ?")
            params.append(typ)

        if aggregate_type is not None:
            clauses.append("aggregate_type = ?")
            params.append(aggregate_type)

        if aggregate_identity is not None:
            clauses.append("aggregate_identity = ?")
            params.append(aggregate_identity)

        if entry_intent_identity is not None:
            clauses.append("entry_intent_identity = ?")
            params.append(entry_intent_identity)

        if broker_order_identity is not None:
            clauses.append("broker_order_identity = ?")
            params.append(broker_order_identity)

        if trade_id is not None:
            clauses.append("trade_id = ?")
            params.append(trade_id)

        if protective_id is not None:
            clauses.append("protective_id = ?")
            params.append(protective_id)

        if correlation_id is not None:
            clauses.append("correlation_id = ?")
            params.append(correlation_id)

        if order_id is not None:
            clauses.append("(aggregate_identity = ? OR broker_order_identity = ? OR correlation_id = ?)")
            params.extend([order_id, order_id, order_id])

        if start_market_time is not None:
            clauses.append("market_timestamp >= ?")
            params.append(_dt_to_str(start_market_time))

        if end_market_time is not None:
            clauses.append("market_timestamp <= ?")
            params.append(_dt_to_str(end_market_time))

        min_seq = since_sequence if since_sequence is not None else since_audit_sequence
        if min_seq is not None:
            clauses.append("audit_sequence >= ?")
            params.append(int(min_seq))

        max_seq = until_sequence if until_sequence is not None else until_audit_sequence
        if max_seq is not None:
            clauses.append("audit_sequence <= ?")
            params.append(int(max_seq))

        query = "SELECT * FROM audit_events"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY audit_sequence ASC"

        if limit is not None:
            query += f" LIMIT {int(limit)}"
            if offset is not None:
                query += f" OFFSET {int(offset)}"

        cursor = self._conn.cursor()
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        return tuple(_row_to_audit_event(row) for row in rows)

    def get_audit_event_by_id(self, event_id: str) -> AuditEvent | None:
        """Fetch a single audit event by unique event_id."""
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("event_id must be a non-empty string")
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM audit_events WHERE event_id = ?;", (event_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return _row_to_audit_event(row)

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _save_account_state_and_positions(
        self,
        cursor: sqlite3.Cursor,
        snapshot: AccountSnapshot,
        accounting_sequence: int,
        breached: bool,
    ) -> None:
        cursor.execute(
            """
            INSERT OR REPLACE INTO account_state (
                account_id, currency, monetary_quantum, starting_capital,
                cash, realized_pnl, aggregate_exposure, as_of_timestamp,
                accounting_sequence, accounting_integrity_breached
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                snapshot.account_id,
                snapshot.currency,
                _dec_to_str(snapshot.monetary_quantum),
                _dec_to_str(snapshot.starting_capital),
                _dec_to_str(snapshot.cash),
                _dec_to_str(snapshot.realized_pnl),
                _dec_to_str(snapshot.aggregate_exposure),
                _dt_to_str(snapshot.as_of_timestamp),
                accounting_sequence,
                1 if breached else 0,
            ),
        )

        # Sync positions: delete missing, insert/update active
        cursor.execute("DELETE FROM positions;")
        for pkey, pos in snapshot.positions.items():
            cursor.execute(
                """
                INSERT INTO positions (
                    strategy_id, strategy_version, instrument_key, identity_json,
                    quantity, average_entry_price, contract_multiplier, mark_price,
                    mark_timestamp, valuation_timeframe, price_increment, monetary_quantum
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    pkey.strategy_id,
                    pkey.strategy_version,
                    _identity_canonical_key(pkey.identity),
                    json.dumps(_identity_to_dict(pkey.identity)),
                    _dec_to_str(pos.quantity),
                    _dec_to_str(pos.average_entry_price),
                    _dec_to_str(pos.contract_multiplier),
                    _dec_to_str(pos.mark_price),
                    _dt_to_str(pos.mark_timestamp),
                    pos.valuation_timeframe,
                    _dec_to_str(pos.price_increment),
                    _dec_to_str(pos.monetary_quantum),
                ),
            )

    # ------------------------------------------------------------------
    # Generic protective-exit eligibility (`ProtectiveExit.effective_after`)
    # durable persistence — V7 additive `paper_metadata` facility ONLY
    # (ADR §128.8–§128.10 precedent; owner decision 2026-08-27 denies Schema
    # V8).  Additive metadata key only: no DDL, no schema-version change, no
    # migration.  Contract: "algofortis-protective-exit-eligibility/v1".
    # Written inside the SAME transaction as the owning protective_exits row
    # (every writer funnels through _save_protective_exit), keyed by
    # protective_id; rows are never hard-deleted, so entries stay in lockstep.
    # Semantics preserved unchanged: a deferred exit stays non-triggerable for
    # market events at or before its eligibility timestamp across restarts,
    # exactly as the in-memory PE-19 non-retroactivity rule requires.
    # ------------------------------------------------------------------

    PROTECTIVE_ELIGIBILITY_CONTRACT_VERSION = "algofortis-protective-exit-eligibility/v1"
    _PROTECTIVE_ELIGIBILITY_KEY = "protective_exit_eligibility"

    @staticmethod
    def _load_protective_exit_eligibility(cursor: sqlite3.Cursor) -> dict[str, str]:
        """Fail-closed read of the generic exit eligibility map ([] when absent)."""
        cursor.execute(
            "SELECT value FROM paper_metadata WHERE key = ?;",
            (SQLitePaperStateStore._PROTECTIVE_ELIGIBILITY_KEY,),
        )
        row = cursor.fetchone()
        if row is None:
            return {}
        try:
            body = json.loads(row["value"])
        except (json.JSONDecodeError, TypeError) as exc:
            raise PersistenceCorruptedError(
                f"protective_exit_eligibility payload is corrupt: {exc}"
            ) from exc
        if (
            not isinstance(body, dict)
            or set(body) != {"schema_version", "eligibility"}
            or body["schema_version"] != SQLitePaperStateStore.PROTECTIVE_ELIGIBILITY_CONTRACT_VERSION
            or not isinstance(body["eligibility"], dict)
            or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in body["eligibility"].items()
            )
        ):
            raise PersistenceCorruptedError(
                "protective_exit_eligibility payload has an invalid schema or contract version"
            )
        try:
            for value in body["eligibility"].values():
                _iso_to_dt(value)
        except ValueError as exc:
            raise PersistenceCorruptedError(
                f"protective_exit_eligibility payload is corrupt: {exc}"
            ) from exc
        return dict(body["eligibility"])

    @staticmethod
    def _write_protective_exit_eligibility(cursor: sqlite3.Cursor, doc: dict[str, str]) -> None:
        if doc:
            payload = json.dumps(
                {
                    "schema_version": SQLitePaperStateStore.PROTECTIVE_ELIGIBILITY_CONTRACT_VERSION,
                    "eligibility": doc,
                },
                sort_keys=True,
            )
            cursor.execute(
                """
                INSERT INTO paper_metadata (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value;
                """,
                (SQLitePaperStateStore._PROTECTIVE_ELIGIBILITY_KEY, payload),
            )
        else:
            cursor.execute(
                "DELETE FROM paper_metadata WHERE key = ?;",
                (SQLitePaperStateStore._PROTECTIVE_ELIGIBILITY_KEY,),
            )

    def _save_protective_exit(self, cursor: sqlite3.Cursor, exit_item: ProtectiveExit) -> None:
        trailing = exit_item.trailing
        stop_price = exit_item.exit_order.stop_price if exit_item.exit_order else None
        target_price = exit_item.exit_order.limit_price if exit_item.exit_order else None
        cursor.execute(
            """
            INSERT OR REPLACE INTO protective_exits (
                protective_id, strategy_id, strategy_version, instrument_key,
                identity_json, kind, state, quantity, oco_group_id, stop_price,
                target_price, trailing_current_stop, trailing_reference_extreme,
                trailing_activated, trailing_effective_after, termination_reason,
                exit_order_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                exit_item.protective_id,
                exit_item.position_key.strategy_id,
                exit_item.position_key.strategy_version,
                _identity_canonical_key(exit_item.position_key.identity),
                json.dumps(_identity_to_dict(exit_item.position_key.identity)),
                exit_item.kind.value,
                exit_item.state.value,
                _dec_to_str(exit_item.quantity),
                exit_item.oco_group_id,
                _dec_to_str(stop_price),
                _dec_to_str(target_price),
                _dec_to_str(trailing.current_stop) if trailing else None,
                _dec_to_str(trailing.reference_extreme) if trailing else None,
                1 if (trailing and trailing.activated) else 0,
                _dt_to_str(trailing.effective_after) if trailing else None,
                exit_item.termination_reason,
                json.dumps(_order_to_dict(exit_item.exit_order)) if exit_item.exit_order else None,
            ),
        )
        if exit_item.effective_after is not None and exit_item.effective_after.tzinfo is None:
            raise ValueError("effective_after must be timezone-aware")
        doc = self._load_protective_exit_eligibility(cursor)
        if exit_item.effective_after is None:
            doc.pop(exit_item.protective_id, None)
        else:
            doc[exit_item.protective_id] = _dt_to_str(exit_item.effective_after)
        self._write_protective_exit_eligibility(cursor, doc)

    def _save_trade_record(self, cursor: sqlite3.Cursor, record: TradeRecord) -> None:
        cursor.execute(
            """
            INSERT OR REPLACE INTO trade_records (
                trade_id, account_id, currency, monetary_quantum, strategy_id,
                strategy_version, instrument_key, identity_json, direction,
                entry_timestamp, exit_timestamp, duration_seconds, entry_quantity,
                exit_quantity, average_entry_price, contract_multiplier,
                gross_realized_pnl, status, opening_event_key, closing_event_key,
                provenance, record_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                record.trade_id,
                record.account_id,
                record.currency,
                _dec_to_str(record.monetary_quantum),
                record.position_key.strategy_id,
                record.position_key.strategy_version,
                _identity_canonical_key(record.instrument_identity),
                json.dumps(_identity_to_dict(record.instrument_identity)),
                record.position_side,
                _dt_to_str(record.opened_at),
                _dt_to_str(record.closed_at),
                _dec_to_str(Decimal(str(record.holding_duration.total_seconds()))),
                _dec_to_str(record.entry_quantity),
                _dec_to_str(record.exit_quantity),
                _dec_to_str(record.average_entry_price),
                _dec_to_str(record.contract_multiplier),
                _dec_to_str(record.gross_realized_pnl),
                record.status.value,
                f"{record.opening_event_key.run_id}:{record.opening_event_key.accounting_sequence}",
                f"{record.closing_event_key.run_id}:{record.closing_event_key.accounting_sequence}",
                json.dumps(dict(record.provenance)) if record.provenance else "{}",
                json.dumps(_trade_record_to_dict(record)),
            ),
        )

    def _save_cost_assessment(self, cursor: sqlite3.Cursor, assessment: CostAssessment) -> None:
        cursor.execute(
            """
            INSERT OR REPLACE INTO cost_assessments (
                assessment_id, trade_id, total_cost, assessment_json
            ) VALUES (?, ?, ?, ?);
            """,
            (
                assessment.assessment_id,
                assessment.trade_id,
                _dec_to_str(assessment.total_cost),
                json.dumps(_cost_assessment_to_dict(assessment)),
            ),
        )

    def _save_risk_gate_state(self, cursor: sqlite3.Cursor, state: RiskGateState) -> None:
        cursor.execute(
            """
            INSERT OR REPLACE INTO risk_gate_state (
                calendar_identity, session_date, start_of_day_net_equity,
                current_net_equity, daily_trade_count, filled_entry_identities_json
            ) VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                state.risk_day.calendar_identity,
                state.risk_day.session_date.isoformat(),
                _dec_to_str(state.start_of_day_net_equity),
                _dec_to_str(state.current_net_equity),
                state.daily_trade_count,
                json.dumps(sorted(state._filled_entry_identities)),
            ),
        )

    def _save_trade_ledger_pending(self, cursor: sqlite3.Cursor, ledger: TradeLedger) -> None:
        cursor.execute("DELETE FROM trade_pending_lifecycles;")
        for pkey, pending in ledger._pending.items():
            cursor.execute(
                """
                INSERT INTO trade_pending_lifecycles (
                    strategy_id, strategy_version, instrument_key, opening_event_key,
                    entries_json, exits_json
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    pkey.strategy_id,
                    pkey.strategy_version,
                    _identity_canonical_key(pkey.identity),
                    f"{pending.opening.run_id}:{pending.opening.accounting_sequence}",
                    json.dumps([_dec_to_str(leg.execution_quantity) for leg in pending.entries]),
                    json.dumps([_dec_to_str(leg.execution_quantity) for leg in pending.exits]),
                ),
            )

    # ------------------------------------------------------------------
    # State Loading & Hydration
    # ------------------------------------------------------------------

    def load_state(self) -> PaperHydratedState:
        """Load and cross-validate complete durable aggregate state from SQLite."""
        if self._health is not PersistenceHealth.HEALTHY:
            raise PersistenceError("Cannot load state: PersistenceHealth is FAILED")

        cursor = self._conn.cursor()

        # Run integrity checks
        cursor.execute("PRAGMA integrity_check;")
        res = cursor.fetchall()
        if not res or res[0][0] != "ok":
            self._health = PersistenceHealth.FAILED
            raise PersistenceCorruptedError(f"SQLite PRAGMA integrity_check failed: {res}")

        cursor.execute("PRAGMA foreign_key_check;")
        fk_res = cursor.fetchall()
        if fk_res:
            self._health = PersistenceHealth.FAILED
            raise PersistenceCorruptedError(f"SQLite PRAGMA foreign_key_check failed: {fk_res}")

        # 1. Load metadata
        cursor.execute("SELECT key, value FROM paper_metadata;")
        metadata = dict(cursor.fetchall())
        db_id = metadata.get("database_instance_id", "")
        session_id = metadata.get("paper_session_id", "")
        generation = int(metadata.get("state_generation", 0))

        # 2. Load account state & positions
        cursor.execute("SELECT * FROM account_state WHERE account_id = ?;", (self._account_id,))
        acc_row = cursor.fetchone()

        positions_dict: dict[PositionKey, PositionSnapshot] = {}
        cursor.execute("SELECT * FROM positions;")
        for pos_row in cursor.fetchall():
            ident = _dict_to_identity(json.loads(pos_row["identity_json"]))
            pkey = PositionKey(
                strategy_id=pos_row["strategy_id"],
                strategy_version=pos_row["strategy_version"],
                identity=ident,
            )
            positions_dict[pkey] = PositionSnapshot(
                key=pkey,
                quantity=_str_to_dec(pos_row["quantity"]),
                average_entry_price=_str_to_dec(pos_row["average_entry_price"]),
                contract_multiplier=_str_to_dec(pos_row["contract_multiplier"]),
                mark_price=_str_to_dec(pos_row["mark_price"]),
                mark_timestamp=_str_to_dt(pos_row["mark_timestamp"]),
                valuation_timeframe=pos_row["valuation_timeframe"],
                price_increment=_str_to_dec(pos_row["price_increment"]),
                monetary_quantum=_str_to_dec(pos_row["monetary_quantum"]),
            )

        # Compute aggregate_exposure per instrument identity from positions
        exposure: dict[InstrumentIdentity, Decimal] = {}
        for pos in positions_dict.values():
            ident = pos.key.identity
            exposure[ident] = exposure.get(ident, Decimal("0")) + pos.quantity

        if acc_row:
            snapshot = AccountSnapshot(
                account_id=acc_row["account_id"],
                currency=acc_row["currency"],
                starting_capital=_str_to_dec(acc_row["starting_capital"]),
                cash=_str_to_dec(acc_row["cash"]),
                realized_pnl=_str_to_dec(acc_row["realized_pnl"]),
                positions=positions_dict,
                aggregate_exposure=exposure,
                as_of_timestamp=_str_to_dt(acc_row["as_of_timestamp"]),
                monetary_quantum=_str_to_dec(acc_row["monetary_quantum"]),
            )
            seq = int(acc_row["accounting_sequence"])
            breached = bool(acc_row["accounting_integrity_breached"])
        else:
            snapshot = AccountSnapshot(
                account_id=self._account_id,
                currency=self._currency,
                starting_capital=self._starting_capital,
                cash=self._starting_capital,
                realized_pnl=Decimal("0"),
                positions={},
                aggregate_exposure={},
                as_of_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                monetary_quantum=self._monetary_quantum,
            )
            seq = 0
            breached = False

        # 3. Load premium commitments & pending risk commitments
        commitments: dict[str, PremiumCommitmentRecord] = {}
        pending_risk_commitments: list[PendingRiskCommitment] = []
        cursor.execute("SELECT * FROM premium_commitments;")
        for row in cursor.fetchall():
            ident = _dict_to_identity(json.loads(row["identity_json"]))
            rec = PremiumCommitmentRecord(
                reservation_key=row["reservation_key"],
                strategy_id=row["strategy_id"],
                strategy_version=row["strategy_version"],
                identity=ident,
                approved_quantity=_str_to_dec(row["approved_quantity"]),
                worst_permitted_fill_price=_str_to_dec(row["worst_permitted_fill_price"]),
                contract_multiplier=_str_to_dec(row["contract_multiplier"]),
                required_cash=_str_to_dec(row["required_cash"]),
                created_at_market_time=_str_to_dt(row["market_time"]),
            )
            commitments[row["reservation_key"]] = rec

            # Reconstruct exact PendingRiskCommitment
            nom_risk_raw = row["nominal_stop_risk"]
            if nom_risk_raw is None:
                raise PersistenceCorruptedError(
                    f"Corrupt premium_commitments row '{row['reservation_key']}': missing nominal_stop_risk"
                )
            nom_risk = _str_to_dec(nom_risk_raw)
            if nom_risk is None or nom_risk <= 0:
                raise PersistenceCorruptedError(
                    f"Corrupt premium_commitments row '{row['reservation_key']}': invalid nominal_stop_risk '{nom_risk_raw}'"
                )
            pkey = PositionKey(row["strategy_id"], row["strategy_version"], ident)
            prc = PendingRiskCommitment(
                entry_identity=row["reservation_key"],
                intended_position_key=pkey,
                approved_quantity=_str_to_dec(row["approved_quantity"]),
                nominal_stop_risk=nom_risk,
            )
            pending_risk_commitments.append(prc)

        # 4. Load broker orders
        pending_orders: dict[str, _PendingOrder] = {}
        terminal_orders: dict[str, BrokerTerminalEvent] = {}
        cursor.execute("SELECT * FROM broker_orders;")
        for row in cursor.fetchall():
            order_id = row["order_id"]
            orig_order = _dict_to_order(json.loads(row["original_order_json"]))
            ident = _dict_to_identity(json.loads(row["instrument_identity_json"]))
            spec = _dict_to_spec(json.loads(row["specification_json"]))
            state = OrderLifecycleState(row["lifecycle_state"])

            if state == OrderLifecycleState.QUEUED:
                ctx = ExecutionEvaluationContext(
                    reference_price=_str_to_dec(row["reference_price"]),
                    price_increment=_str_to_dec(row["price_increment"]),
                )
                po = _PendingOrder(
                    order_id=order_id,
                    broker_order_identity=row["broker_order_identity"],
                    original_order=orig_order,
                    instrument_identity=ident,
                    specification=spec,
                    reference_price=_str_to_dec(row["reference_price"]),
                    price_increment=_str_to_dec(row["price_increment"]),
                    execution_context=ctx,
                    lifecycle_state=state,
                    submission_market_timestamp=_str_to_dt(row["submission_market_timestamp"]),
                    eligibility_timestamp=_str_to_dt(row["eligibility_timestamp"]),
                    stop_triggered=bool(row["stop_triggered"]),
                    stop_limit_activated=bool(row["stop_limit_activated"]),
                    stop_limit_activation_timestamp=_str_to_dt(row["stop_limit_activation_timestamp"]),
                    stop_limit_activation_price=_str_to_dec(row["stop_limit_activation_price"]),
                )
                pending_orders[order_id] = po
            else:
                exec_res = _dict_to_exec_result(json.loads(row["execution_result_json"])) if row["execution_result_json"] else None
                te = BrokerTerminalEvent(
                    order_id=order_id,
                    broker_order_identity=row["broker_order_identity"],
                    instrument_identity=ident,
                    lifecycle_state=state,
                    original_order=orig_order,
                    execution_result=exec_res,
                    market_timestamp=_str_to_dt(row["terminal_market_timestamp"]) or datetime(2026, 1, 1, tzinfo=timezone.utc),
                    reason=row["terminal_reason"] or "",
                )
                terminal_orders[order_id] = te

        # 5. Load broker watermarks
        watermarks: dict[InstrumentIdentity, datetime] = {}
        cursor.execute("SELECT * FROM broker_watermarks;")
        for row in cursor.fetchall():
            ts = _str_to_dt(row["last_exchange_timestamp"])
            if ts is None:
                continue
            # identity_json column stores the full identity; fall back to
            # matching against loaded positions/orders for legacy rows without it.
            ident_json = row["identity_json"] if "identity_json" in row.keys() else None
            if ident_json:
                ident = _dict_to_identity(json.loads(ident_json))
                watermarks[ident] = ts
            else:
                key = row["instrument_key"]
                for pkey in positions_dict:
                    if _identity_canonical_key(pkey.identity) == key:
                        watermarks[pkey.identity] = ts
                        break
                else:
                    for po in pending_orders.values():
                        if _identity_canonical_key(po.instrument_identity) == key:
                            watermarks[po.instrument_identity] = ts
                            break

        # 6. Load entry intents
        intents: dict[str, str] = {}
        cursor.execute("SELECT intent_id, lifecycle_state FROM entry_intents;")
        for row in cursor.fetchall():
            intents[row["intent_id"]] = row["lifecycle_state"]

        # 7. Load retained protective plans
        retained_plans: dict[str, tuple[PreEntryProtectivePlan, Decimal, str | None]] = {}
        cursor.execute("SELECT * FROM retained_protective_plans;")
        for row in cursor.fetchall():
            oid = row["order_id"]
            plan = _dict_to_plan(json.loads(row["plan_json"]))
            qty = _str_to_dec(row["quantity"])
            run_id = row["run_identity"]
            retained_plans[oid] = (plan, qty, run_id)

        # 8. Load protective exits
        eligibility_doc = self._load_protective_exit_eligibility(cursor)
        exits_list: list[ProtectiveExit] = []
        cursor.execute("SELECT * FROM protective_exits;")
        for row in cursor.fetchall():
            ident = _dict_to_identity(json.loads(row["identity_json"]))
            pkey = PositionKey(
                strategy_id=row["strategy_id"],
                strategy_version=row["strategy_version"],
                identity=ident,
            )
            trailing = None
            if row["trailing_current_stop"] is not None:
                trailing = TrailingStopState(
                    current_stop=_str_to_dec(row["trailing_current_stop"]),
                    reference_extreme=_str_to_dec(row["trailing_reference_extreme"]),
                    activated=bool(row["trailing_activated"]),
                    effective_after=_str_to_dt(row["trailing_effective_after"]),
                )
            ex_order = _dict_to_order(json.loads(row["exit_order_json"])) if row["exit_order_json"] else None
            ex = ProtectiveExit(
                protective_id=row["protective_id"],
                position_key=pkey,
                exit_order=ex_order,
                kind=ProtectiveExitKind(row["kind"]),
                quantity=_str_to_dec(row["quantity"]),
                oco_group_id=row["oco_group_id"],
                trailing=trailing,
                effective_after=_str_to_dt(eligibility_doc.get(row["protective_id"])),
                state=ProtectiveExitState(row["state"]),
                termination_reason=row["termination_reason"],
            )
            exits_list.append(ex)

        # 9. Load protective pending closes
        pending_closes_list: list[LiveProtectivePendingClose] = []
        cursor.execute("SELECT * FROM protective_pending_closes;")
        for row in cursor.fetchall():
            # Match PositionKey from positions or exits
            pkey = next((ex.position_key for ex in exits_list if ex.protective_id == row["protective_id"]), None)
            if pkey is None:
                for pos_k in positions_dict:
                    if (
                        pos_k.strategy_id == row["strategy_id"]
                        and pos_k.strategy_version == row["strategy_version"]
                        and _identity_canonical_key(pos_k.identity) == row["instrument_key"]
                    ):
                        pkey = pos_k
                        break
            if pkey is None:
                raise PersistenceCorruptedError(
                    f"Orphan protective_pending_close: protective_id {row['protective_id']} has no matching position/exit"
                )
            pc = LiveProtectivePendingClose(
                position_key=pkey,
                protective_id=row["protective_id"],
                order_id=row["order_id"],
                broker_order_identity=row["broker_order_identity"],
                kind=ProtectiveExitKind(row["kind"]),
                trigger_price=_str_to_dec(row["trigger_price"]),
                trigger_timestamp=_str_to_dt(row["trigger_timestamp"]),
            )
            pending_closes_list.append(pc)

        # 10. Load trade records & ledger
        trade_records: list[TradeRecord] = []
        trade_records_by_id: dict[str, TradeRecord] = {}
        cursor.execute("SELECT * FROM trade_records;")
        for row in cursor.fetchall():
            raw_rec_json = row["record_json"]
            rec = None
            if raw_rec_json:
                try:
                    rec_dict = json.loads(raw_rec_json)
                    if "entry_legs" in rec_dict:
                        rec = _dict_to_trade_record(rec_dict)
                except Exception:
                    rec = None
            if rec is None:
                ident = _dict_to_identity(json.loads(row["identity_json"]))
                pkey = PositionKey(
                    strategy_id=row["strategy_id"],
                    strategy_version=row["strategy_version"],
                    identity=ident,
                )
                op_parts = row["opening_event_key"].split(":")
                cl_parts = row["closing_event_key"].split(":")
                op_key = LedgerEventKey(run_id=op_parts[0], accounting_sequence=int(op_parts[1]))
                cl_key = LedgerEventKey(run_id=cl_parts[0], accounting_sequence=int(cl_parts[1]))
                dur = timedelta(seconds=float(row["duration_seconds"]))
                rec = TradeRecord(
                    trade_id=row["trade_id"],
                    account_id=row["account_id"],
                    currency=row["currency"],
                    monetary_quantum=_str_to_dec(row["monetary_quantum"]),
                    position_key=pkey,
                    instrument_identity=ident,
                    position_side=row["direction"],
                    opened_at=_str_to_dt(row["entry_timestamp"]),
                    closed_at=_str_to_dt(row["exit_timestamp"]),
                    holding_duration=dur,
                    entry_quantity=_str_to_dec(row["entry_quantity"]),
                    exit_quantity=_str_to_dec(row["exit_quantity"]),
                    average_entry_price=_str_to_dec(row["average_entry_price"]),
                    contract_multiplier=_str_to_dec(row["contract_multiplier"]),
                    entry_legs=(),
                    exit_legs=(),
                    gross_realized_pnl=_str_to_dec(row["gross_realized_pnl"]),
                    status=TradeStatus(row["status"]),
                    opening_event_key=op_key,
                    closing_event_key=cl_key,
                    provenance=row["provenance"],
                )
            trade_records.append(rec)
            trade_records_by_id[rec.trade_id] = rec

        trade_ledger = TradeLedger.restore(records=trade_records)

        # 11. Load cost assessments
        cost_assessments: list[CostAssessment] = []
        cursor.execute("SELECT * FROM cost_assessments;")
        for row in cursor.fetchall():
            raw_json = row["assessment_json"]
            if not raw_json or not raw_json.strip():
                raise PersistenceCorruptedError(
                    f"Corrupt cost_assessments row '{row['assessment_id']}': missing assessment_json"
                )
            try:
                data = json.loads(raw_json)
            except Exception as j_err:
                raise PersistenceCorruptedError(
                    f"Corrupt cost_assessments row '{row['assessment_id']}': invalid JSON: {j_err}"
                ) from j_err

            expected_total_cost = _str_to_dec(row["total_cost"])
            if expected_total_cost is None:
                raise PersistenceCorruptedError(
                    f"Corrupt cost_assessments row '{row['assessment_id']}': missing total_cost column"
                )

            ca = _dict_to_cost_assessment(data, trade_records_by_id, expected_total_cost)
            cost_assessments.append(ca)

        # 12. Load risk gate state
        cursor.execute("SELECT * FROM risk_gate_state ORDER BY session_date DESC LIMIT 1;")
        risk_row = cursor.fetchone()
        risk_gate_state = None
        if risk_row:
            rday = RiskDay(
                calendar_identity=risk_row["calendar_identity"],
                session_date=date.fromisoformat(risk_row["session_date"]),
            )
            filled_ids = frozenset(json.loads(risk_row["filled_entry_identities_json"]))
            risk_gate_state = RiskGateState(
                risk_day=rday,
                start_of_day_net_equity=_str_to_dec(risk_row["start_of_day_net_equity"]),
                current_net_equity=_str_to_dec(risk_row["current_net_equity"]),
                daily_trade_count=int(risk_row["daily_trade_count"]),
                _filled_entry_identities=filled_ids,
            )

        # 13. Load processed fills
        processed_fills: dict[str, tuple[BrokerTerminalEvent, AccountingResult]] = {}
        cursor.execute("SELECT * FROM processed_fills;")
        for row in cursor.fetchall():
            canonical_id = row["broker_order_identity"]
            # Lookup terminal event from terminal_orders
            te = terminal_orders.get(row["order_id"])
            if te is not None:
                # Construct synthetic accepted AccountingResult
                from engine.portfolio.accounting import AccountingResult
                res = AccountingResult(
                    outcome=AccountingOutcome.ACCEPTED,
                    prior_snapshot=snapshot,
                    resulting_snapshot=snapshot,
                    reason=None,
                    source_evidence=te.execution_result,
                    provenance={},
                )
                processed_fills[canonical_id] = (te, res)

        # 14. Load safety state
        cursor.execute(
            "SELECT kill_switch_active, kill_switch_reason, activation_source, activation_market_timestamp, activated_at FROM safety_state WHERE account_id = ?;",
            (self._account_id,),
        )
        safety_row = cursor.fetchone()
        if safety_row is not None:
            kill_state = KillSwitchState(
                active=bool(safety_row["kill_switch_active"]),
                reason=safety_row["kill_switch_reason"],
                source=safety_row["activation_source"],
                activated_at=safety_row["activated_at"],
                activation_market_timestamp=_iso_to_dt(safety_row["activation_market_timestamp"]),
            )
        else:
            kill_state = KillSwitchState(active=False)

        # 15. Load strategy states (P1-07 / ADR §121)
        strategy_states_dict: dict[SubscriptionOwnerKey, StrategyDurableState] = {}
        cursor.execute("SELECT * FROM strategy_states;")
        for srow in cursor.fetchall():
            sid = srow["strategy_id"]
            sver = srow["strategy_version"]
            owner = SubscriptionOwnerKey(sid, sver)
            row_session_id = srow["paper_session_id"]
            row_cfg_id = srow["configuration_identity"]
            row_codec = srow["codec_version"]
            raw_json = srow["state_json"]
            row_fp = srow["state_fingerprint"]
            raw_dt = srow["last_evaluated_decision_time"]
            gen = int(srow["state_generation"])
            updated_at_dt = _str_to_dt(srow["updated_at"])

            if row_session_id != self._paper_session_id:
                raise DatabaseIdentityMismatchError(
                    f"strategy_states row for {owner!r} has paper_session_id {row_session_id!r}, expected {self._paper_session_id!r}"
                )
            if self._configuration_identity and row_cfg_id != self._configuration_identity:
                raise DatabaseIdentityMismatchError(
                    f"strategy_states row for {owner!r} has configuration_identity {row_cfg_id!r}, expected {self._configuration_identity!r}"
                )
            if row_codec != STRATEGY_STATE_CODEC_VERSION:
                raise IncompatibleContractError(
                    f"strategy_states row for {owner!r} has codec_version {row_codec!r}, expected {STRATEGY_STATE_CODEC_VERSION!r}"
                )
            if gen < 0:
                raise PersistenceCorruptedError(
                    f"strategy_states row for {owner!r} has negative state_generation: {gen}"
                )

            # Decode state with fingerprint validation
            decoded_state = decode_strategy_state(raw_json, row_fp)
            eval_dt = _str_to_dt(raw_dt) if raw_dt else None

            strategy_states_dict[owner] = StrategyDurableState(
                strategy_id=sid,
                strategy_version=sver,
                paper_session_id=row_session_id,
                configuration_identity=row_cfg_id,
                codec_version=row_codec,
                state=decoded_state,
                state_fingerprint=row_fp,
                last_evaluated_decision_time=eval_dt,
                state_generation=gen,
                updated_at=updated_at_dt or recorded_at_utc_now(),
            )

        # 16. Load promotion tracking states and session records (P1-08 / ADR §122)
        promotion_states_dict: dict[SubscriptionOwnerKey, PromotionTrackingState] = {}
        cursor.execute("SELECT * FROM promotion_tracking_state;")
        for prow in cursor.fetchall():
            psid = prow["strategy_id"]
            psver = prow["strategy_version"]
            powner = SubscriptionOwnerKey(psid, psver)
            p_session_id = prow["paper_session_id"]
            p_cfg_id = prow["configuration_identity"]
            p_fp = prow["upstream_promotion_fingerprint"]
            p_status_str = prow["tracking_status"]
            p_act_str = prow["activated_at"]
            p_win_str = prow["window_start_date"]
            p_clean = int(prow["clean_days_count"])
            p_disq = int(prow["disqualified_days_count"])
            p_last_str = prow["last_evaluated_session_date"]
            p_mile_str = prow["milestone_status"]
            p_gen = int(prow["state_generation"])
            p_upd_str = prow["updated_at"]

            if p_session_id != self._paper_session_id:
                raise DatabaseIdentityMismatchError(
                    f"promotion_tracking_state row for {powner!r} has paper_session_id {p_session_id!r}, expected {self._paper_session_id!r}"
                )
            if self._configuration_identity and p_cfg_id != self._configuration_identity:
                raise DatabaseIdentityMismatchError(
                    f"promotion_tracking_state row for {powner!r} has configuration_identity {p_cfg_id!r}, expected {self._configuration_identity!r}"
                )
            if p_gen < 0:
                raise PersistenceCorruptedError(
                    f"promotion_tracking_state row for {powner!r} has negative state_generation: {p_gen}"
                )
            if p_clean < 0 or p_disq < 0:
                raise PersistenceCorruptedError(
                    f"promotion_tracking_state row for {powner!r} has negative counts: clean={p_clean}, disq={p_disq}"
                )

            act_dt = _str_to_dt(p_act_str) if p_act_str else None
            win_d = date.fromisoformat(p_win_str) if p_win_str else None
            last_d = date.fromisoformat(p_last_str) if p_last_str else None
            upd_dt = _str_to_dt(p_upd_str) or recorded_at_utc_now()

            promotion_states_dict[powner] = PromotionTrackingState(
                strategy_id=psid,
                strategy_version=psver,
                paper_session_id=p_session_id,
                configuration_identity=p_cfg_id,
                upstream_promotion_fingerprint=p_fp,
                tracking_status=PromotionTrackingStatus(p_status_str),
                activated_at=act_dt,
                window_start_date=win_d,
                clean_days_count=p_clean,
                disqualified_days_count=p_disq,
                last_evaluated_session_date=last_d,
                milestone_status=PromotionMilestoneStatus(p_mile_str),
                state_generation=p_gen,
                updated_at=upd_dt,
            )

        promotion_records_list: list[PromotionSessionRecord] = []
        cursor.execute("SELECT * FROM promotion_session_records ORDER BY session_date ASC;")
        for srec in cursor.fetchall():
            rec_sid = srec["strategy_id"]
            rec_sver = srec["strategy_version"]
            rec_date_str = srec["session_date"]
            rec_session_id = srec["paper_session_id"]
            rec_cfg_id = srec["configuration_identity"]
            rec_fp = srec["upstream_promotion_fingerprint"]
            rec_status_str = srec["session_status"]
            rec_reasons_raw = srec["reasons_json"]
            rec_utc_str = srec["recorded_at_utc"]

            if rec_session_id != self._paper_session_id:
                raise DatabaseIdentityMismatchError(
                    f"promotion_session_records row has paper_session_id {rec_session_id!r}, expected {self._paper_session_id!r}"
                )
            if self._configuration_identity and rec_cfg_id != self._configuration_identity:
                raise DatabaseIdentityMismatchError(
                    f"promotion_session_records row has configuration_identity {rec_cfg_id!r}, expected {self._configuration_identity!r}"
                )
            try:
                rec_d = date.fromisoformat(rec_date_str)
                reasons_val = json.loads(rec_reasons_raw)
                if not isinstance(reasons_val, list):
                    raise ValueError("reasons_json must be list")
                rec_utc = _str_to_dt(rec_utc_str)
                if rec_utc is None:
                    raise ValueError("invalid recorded_at_utc")
            except Exception as exc:
                raise PersistenceCorruptedError(f"Corrupted promotion_session_records row: {exc}") from exc

            promotion_records_list.append(PromotionSessionRecord(
                strategy_id=rec_sid,
                strategy_version=rec_sver,
                session_date=rec_d,
                paper_session_id=rec_session_id,
                configuration_identity=rec_cfg_id,
                upstream_promotion_fingerprint=rec_fp,
                session_status=PromotionSessionStatus(rec_status_str),
                reasons=tuple(reasons_val),
                recorded_at_utc=rec_utc,
            ))

        # --------------------------------------------------------------
        # Cross-Table Consistency Validations
        # --------------------------------------------------------------

        # Validate: every retained protective plan has a pending QUEUED broker order
        for oid in retained_plans:
            if oid not in pending_orders:
                raise PersistenceCorruptedError(
                    f"Cross-table violation: retained protective plan for order_id {oid!r} has no pending broker order"
                )

        # Validate: every protective pending close has matching pending close order
        for pc in pending_closes_list:
            if pc.order_id not in pending_orders:
                raise PersistenceCorruptedError(
                    f"Cross-table violation: protective pending close order {pc.order_id!r} not in pending broker orders"
                )

        # Append RUNTIME_STARTED and STATE_HYDRATED observational audit events
        try:
            runtime_ev = AuditEvent(
                event_id=derive_audit_event_id(
                    event_family=AuditEventFamily.RESTART_HYDRATION,
                    event_type=AuditEventType.RUNTIME_STARTED,
                    aggregate_type="RUNTIME",
                    aggregate_identity=self._account_id,
                    state_generation=None,
                    transaction_event_ordinal=0,
                ),
                event_family=AuditEventFamily.RESTART_HYDRATION.value,
                event_type=AuditEventType.RUNTIME_STARTED.value,
                aggregate_type="RUNTIME",
                aggregate_identity=self._account_id,
                recorded_at_utc=recorded_at_utc_now(),
                payload_json=canonical_json_dumps({
                    "account_id": self._account_id,
                    "database_instance_id": db_id,
                    "paper_session_id": session_id,
                }),
            )
            hydrated_ev = AuditEvent(
                event_id=derive_audit_event_id(
                    event_family=AuditEventFamily.RESTART_HYDRATION,
                    event_type=AuditEventType.STATE_HYDRATED,
                    aggregate_type="ACCOUNT",
                    aggregate_identity=self._account_id,
                    state_generation=None,
                    transaction_event_ordinal=0,
                ),
                event_family=AuditEventFamily.RESTART_HYDRATION.value,
                event_type=AuditEventType.STATE_HYDRATED.value,
                aggregate_type="ACCOUNT",
                aggregate_identity=self._account_id,
                recorded_at_utc=recorded_at_utc_now(),
                payload_json=canonical_json_dumps({
                    "account_id": self._account_id,
                    "state_generation": generation,
                    "accounting_sequence": seq,
                    "positions_count": len(positions_dict),
                    "pending_orders_count": len(pending_orders),
                }),
            )
            self.append_audit_events([runtime_ev, hydrated_ev])
        except Exception:
            pass

        return PaperHydratedState(
            account_snapshot=snapshot,
            active_commitments=commitments,
            processed_fills=processed_fills,
            pending_broker_orders=pending_orders,
            terminal_broker_orders=terminal_orders,
            broker_watermarks=watermarks,
            entry_intents=intents,
            retained_protective_plans=retained_plans,
            protective_exits=tuple(exits_list),
            protective_pending_closes=tuple(pending_closes_list),
            trade_ledger=trade_ledger,
            cost_assessments=cost_assessments,
            risk_gate_state=risk_gate_state,
            accounting_sequence=seq,
            accounting_integrity_breached=breached,
            state_generation=generation,
            database_instance_id=db_id,
            paper_session_id=session_id,
            pending_risk_commitments=tuple(pending_risk_commitments),
            kill_switch_state=kill_state,
            strategy_states=strategy_states_dict,
            promotion_tracking_states=promotion_states_dict,
            promotion_session_records=promotion_records_list,
        )


    # ------------------------------------------------------------------
    # Phase 5 OD-7 Item 12: Independent Reconciliation Store APIs
    # ------------------------------------------------------------------

    def save_reconciliation_report(self, report: ReconciliationReport) -> None:
        """Atomically persist one reconciliation report and its findings without bumping state_generation."""
        if not isinstance(report, ReconciliationReport):
            raise TypeError("report must be a ReconciliationReport")
        if self._health == PersistenceHealth.FAILED:
            raise PersistenceHealthFailedError("Cannot save reconciliation report: persistence health is FAILED")

        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO reconciliation_reports (
                        report_id, account_id, paper_session_id, checked_state_generation,
                        status, critical_count, warning_count, info_count,
                        evaluated_at_market_time, evaluated_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        report.report_id,
                        report.account_id,
                        report.paper_session_id,
                        report.checked_state_generation,
                        report.status.value,
                        report.critical_count,
                        report.warning_count,
                        report.info_count,
                        _dt_to_iso(report.evaluated_at_market_time) if report.evaluated_at_market_time else None,
                        _dt_to_iso(report.evaluated_at_utc),
                    ),
                )
                for finding in report.findings:
                    cursor.execute(
                        """
                        INSERT INTO reconciliation_findings (
                            finding_id, report_id, finding_key, finding_type,
                            severity, aggregate_type, aggregate_identity,
                            market_timestamp, expected_json, observed_json, details_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            finding.finding_id,
                            finding.report_id,
                            finding.finding_key,
                            finding.finding_type,
                            finding.severity.value,
                            finding.aggregate_type,
                            finding.aggregate_identity,
                            _dt_to_iso(finding.market_timestamp) if finding.market_timestamp else None,
                            finding.expected_json,
                            finding.observed_json,
                            finding.details_json,
                        ),
                    )
        except Exception as ex:
            self._health = PersistenceHealth.FAILED
            logger.critical("Failed to save reconciliation report: %s", ex)
            raise PersistenceTransactionError(f"Failed to save reconciliation report: {ex}") from ex

    def get_reconciliation_snapshot(self) -> ReconciliationPersistedSnapshot:
        """Read all persisted domain evidence in ONE consistent read transaction without bumping state_generation."""
        if self._health == PersistenceHealth.FAILED:
            raise PersistenceHealthFailedError("Cannot acquire reconciliation snapshot: persistence health is FAILED")

        try:
            cursor = self._conn.cursor()

            # 1. State generation
            cursor.execute("SELECT value FROM paper_metadata WHERE key = 'state_generation';")
            gen_row = cursor.fetchone()
            generation = int(gen_row["value"]) if gen_row else 0

            # 2. Account state
            cursor.execute("SELECT * FROM account_state LIMIT 1;")
            acc_row = cursor.fetchone()
            if acc_row:
                acc_snapshot = AccountSnapshot(
                    account_id=acc_row["account_id"],
                    currency=acc_row["currency"],
                    starting_capital=_str_to_dec(acc_row["starting_capital"]),
                    cash=_str_to_dec(acc_row["cash"]),
                    realized_pnl=_str_to_dec(acc_row["realized_pnl"]),
                    positions={},
                    aggregate_exposure={},
                    as_of_timestamp=_str_to_dt(acc_row["as_of_timestamp"]),
                    monetary_quantum=_str_to_dec(acc_row["monetary_quantum"]),
                )
            else:
                acc_snapshot = None

            # 3. Positions
            positions_dict: dict[PositionKey, PositionSnapshot] = {}
            cursor.execute("SELECT * FROM positions;")
            for row in cursor.fetchall():
                ident = _dict_to_identity(json.loads(row["identity_json"]))
                pkey = PositionKey(row["strategy_id"], row["strategy_version"], ident)
                mark_dt = _str_to_dt(row["mark_timestamp"]) if row["mark_timestamp"] else None
                positions_dict[pkey] = PositionSnapshot(
                    key=pkey,
                    quantity=_str_to_dec(row["quantity"]),
                    average_entry_price=_str_to_dec(row["average_entry_price"]),
                    contract_multiplier=_str_to_dec(row["contract_multiplier"]),
                    mark_price=_str_to_dec(row["mark_price"]) if row["mark_price"] else None,
                    mark_timestamp=mark_dt,
                    valuation_timeframe=row["valuation_timeframe"],
                    price_increment=_str_to_dec(row["price_increment"]),
                    monetary_quantum=_str_to_dec(row["monetary_quantum"]),
                )

            # 4. Premium commitments
            commitments_list: list[PremiumCommitmentRecord] = []
            cursor.execute("SELECT * FROM premium_commitments;")
            for row in cursor.fetchall():
                ident = _dict_to_identity(json.loads(row["identity_json"]))
                commitments_list.append(
                    PremiumCommitmentRecord(
                        reservation_key=row["reservation_key"],
                        strategy_id=row["strategy_id"],
                        strategy_version=row["strategy_version"],
                        identity=ident,
                        approved_quantity=_str_to_dec(row["approved_quantity"]),
                        worst_permitted_fill_price=_str_to_dec(row["worst_permitted_fill_price"]),
                        contract_multiplier=_str_to_dec(row["contract_multiplier"]),
                        required_cash=_str_to_dec(row["required_cash"]),
                        created_at_market_time=_str_to_dt(row["market_time"]),
                    )
                )

            # 5. Broker orders
            broker_orders_list: list[BrokerOrderRecord] = []
            cursor.execute("SELECT * FROM broker_orders;")
            for row in cursor.fetchall():
                orig_order = _dict_to_order(json.loads(row["original_order_json"]))
                ident = _dict_to_identity(json.loads(row["instrument_identity_json"]))
                st_act_dt = _str_to_dt(row["stop_limit_activation_timestamp"]) if row["stop_limit_activation_timestamp"] else None
                broker_orders_list.append(
                    BrokerOrderRecord(
                        order_id=row["order_id"],
                        broker_order_identity=row["broker_order_identity"],
                        original_order=orig_order,
                        instrument_identity=ident,
                        lifecycle_state=OrderLifecycleState(row["lifecycle_state"]),
                        submission_market_timestamp=_str_to_dt(row["submission_market_timestamp"]),
                        eligibility_timestamp=_str_to_dt(row["eligibility_timestamp"]),
                        reference_price=_str_to_dec(row["reference_price"]),
                        stop_triggered=bool(row["stop_triggered"]),
                        stop_limit_activated=bool(row["stop_limit_activated"]),
                        stop_limit_activation_timestamp=st_act_dt,
                        stop_limit_activation_price=_str_to_dec(row["stop_limit_activation_price"]) if row["stop_limit_activation_price"] else None,
                    )
                )

            # 6. Processed fills
            processed_fills_list: list[tuple[str, str, str, str, Decimal, Decimal, Decimal, datetime, str]] = []
            cursor.execute(
                "SELECT broker_order_identity, order_id, lifecycle_state, instrument_key, fill_price, filled_quantity, fee, fill_timestamp, semantic_fingerprint FROM processed_fills;"
            )
            for row in cursor.fetchall():
                processed_fills_list.append((
                    row["broker_order_identity"],
                    row["order_id"],
                    row["lifecycle_state"],
                    row["instrument_key"],
                    _str_to_dec(row["fill_price"]),
                    _str_to_dec(row["filled_quantity"]),
                    _str_to_dec(row["fee"]),
                    _str_to_dt(row["fill_timestamp"]),
                    row["semantic_fingerprint"],
                ))

            # 7. Protective exits
            eligibility_doc = self._load_protective_exit_eligibility(cursor)
            protective_exits_list: list[ProtectiveExit] = []
            cursor.execute("SELECT * FROM protective_exits;")
            for row in cursor.fetchall():
                ident = _dict_to_identity(json.loads(row["identity_json"]))
                pkey = PositionKey(
                    strategy_id=row["strategy_id"],
                    strategy_version=row["strategy_version"],
                    identity=ident,
                )
                trailing = None
                if row["trailing_current_stop"] is not None:
                    trailing = TrailingStopState(
                        current_stop=_str_to_dec(row["trailing_current_stop"]),
                        reference_extreme=_str_to_dec(row["trailing_reference_extreme"]),
                        activated=bool(row["trailing_activated"]),
                        effective_after=_str_to_dt(row["trailing_effective_after"]),
                    )
                ex_order = _dict_to_order(json.loads(row["exit_order_json"])) if row["exit_order_json"] else None
                protective_exits_list.append(
                    ProtectiveExit(
                        protective_id=row["protective_id"],
                        position_key=pkey,
                        exit_order=ex_order,
                        kind=ProtectiveExitKind(row["kind"]),
                        quantity=_str_to_dec(row["quantity"]),
                        oco_group_id=row["oco_group_id"],
                        trailing=trailing,
                        effective_after=_str_to_dt(eligibility_doc.get(row["protective_id"])),
                        state=ProtectiveExitState(row["state"]),
                        termination_reason=row["termination_reason"],
                    )
                )

            # 8. Protective pending closes
            pending_closes_list: list[LiveProtectivePendingClose] = []
            cursor.execute("SELECT * FROM protective_pending_closes;")
            for row in cursor.fetchall():
                pkey = next((ex.position_key for ex in protective_exits_list if ex.protective_id == row["protective_id"]), None)
                if pkey is None:
                    for pos_k in positions_dict:
                        if (
                            pos_k.strategy_id == row["strategy_id"]
                            and pos_k.strategy_version == row["strategy_version"]
                            and _identity_canonical_key(pos_k.identity) == row["instrument_key"]
                        ):
                            pkey = pos_k
                            break
                if pkey is not None:
                    pending_closes_list.append(
                        LiveProtectivePendingClose(
                            position_key=pkey,
                            protective_id=row["protective_id"],
                            order_id=row["order_id"],
                            broker_order_identity=row["broker_order_identity"],
                            kind=ProtectiveExitKind(row["kind"]),
                            trigger_price=_str_to_dec(row["trigger_price"]),
                            trigger_timestamp=_str_to_dt(row["trigger_timestamp"]),
                        )
                    )

            # 9. Trade records
            trade_records: list[TradeRecord] = []
            trade_records_by_id: dict[str, TradeRecord] = {}
            cursor.execute("SELECT * FROM trade_records;")
            for row in cursor.fetchall():
                raw_rec_json = row["record_json"]
                rec = None
                if raw_rec_json:
                    try:
                        rec_dict = json.loads(raw_rec_json)
                        if "entry_legs" in rec_dict:
                            rec = _dict_to_trade_record(rec_dict)
                    except Exception:
                        rec = None
                if rec is None:
                    ident = _dict_to_identity(json.loads(row["identity_json"]))
                    pkey = PositionKey(
                        strategy_id=row["strategy_id"],
                        strategy_version=row["strategy_version"],
                        identity=ident,
                    )
                    op_parts = row["opening_event_key"].split(":")
                    cl_parts = row["closing_event_key"].split(":")
                    op_key = LedgerEventKey(run_id=op_parts[0], accounting_sequence=int(op_parts[1]))
                    cl_key = LedgerEventKey(run_id=cl_parts[0], accounting_sequence=int(cl_parts[1]))
                    dur = timedelta(seconds=float(row["duration_seconds"]))
                    rec = TradeRecord(
                        trade_id=row["trade_id"],
                        account_id=row["account_id"],
                        currency=row["currency"],
                        monetary_quantum=_str_to_dec(row["monetary_quantum"]),
                        position_key=pkey,
                        instrument_identity=ident,
                        position_side=row["direction"],
                        opened_at=_str_to_dt(row["entry_timestamp"]),
                        closed_at=_str_to_dt(row["exit_timestamp"]),
                        holding_duration=dur,
                        entry_quantity=_str_to_dec(row["entry_quantity"]),
                        exit_quantity=_str_to_dec(row["exit_quantity"]),
                        average_entry_price=_str_to_dec(row["average_entry_price"]),
                        contract_multiplier=_str_to_dec(row["contract_multiplier"]),
                        entry_legs=(),
                        exit_legs=(),
                        gross_realized_pnl=_str_to_dec(row["gross_realized_pnl"]),
                        status=TradeStatus(row["status"]),
                        opening_event_key=op_key,
                        closing_event_key=cl_key,
                        provenance=row["provenance"],
                    )
                trade_records.append(rec)
                trade_records_by_id[rec.trade_id] = rec

            # 10. Cost assessments
            cost_assessments: list[CostAssessment] = []
            cursor.execute("SELECT * FROM cost_assessments;")
            for row in cursor.fetchall():
                raw_json = row["assessment_json"]
                if raw_json and raw_json.strip():
                    try:
                        data = json.loads(raw_json)
                        expected_total_cost = _str_to_dec(row["total_cost"])
                        ca = _dict_to_cost_assessment(data, trade_records_by_id, expected_total_cost)
                        cost_assessments.append(ca)
                    except Exception:
                        pass

            return ReconciliationPersistedSnapshot(
                state_generation=generation,
                account_state=acc_snapshot,
                positions=positions_dict,
                premium_commitments=tuple(commitments_list),
                broker_orders=tuple(broker_orders_list),
                processed_fills=tuple(processed_fills_list),
                protective_exits=tuple(protective_exits_list),
                protective_pending_closes=tuple(pending_closes_list),
                trade_records=tuple(trade_records),
                cost_assessments=tuple(cost_assessments),
            )
        except Exception as ex:
            self._health = PersistenceHealth.FAILED
            logger.critical("Failed to acquire reconciliation snapshot: %s", ex)
            raise PersistenceTransactionError(f"Failed to acquire reconciliation snapshot: {ex}") from ex

    def query_reconciliation_reports(self, *, limit: int = 50) -> tuple[ReconciliationReport, ...]:
        """Read historical reconciliation reports and findings."""
        if self._health == PersistenceHealth.FAILED:
            raise PersistenceHealthFailedError("Cannot query reconciliation reports: persistence health is FAILED")

        try:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT * FROM reconciliation_reports ORDER BY evaluated_at_utc DESC LIMIT ?;",
                (limit,),
            )
            reports_rows = cursor.fetchall()
            reports: list[ReconciliationReport] = []

            for r_row in reports_rows:
                r_id = r_row["report_id"]
                cursor.execute("SELECT * FROM reconciliation_findings WHERE report_id = ?;", (r_id,))
                f_rows = cursor.fetchall()
                findings = tuple(
                    ReconciliationFinding(
                        finding_id=f["finding_id"],
                        report_id=f["report_id"],
                        finding_key=f["finding_key"],
                        finding_type=f["finding_type"],
                        severity=ReconciliationSeverity(f["severity"]),
                        aggregate_type=f["aggregate_type"],
                        aggregate_identity=f["aggregate_identity"],
                        market_timestamp=_str_to_dt(f["market_timestamp"]) if f["market_timestamp"] else None,
                        expected_json=f["expected_json"],
                        observed_json=f["observed_json"],
                        details_json=f["details_json"],
                    )
                    for f in f_rows
                )
                m_dt = _str_to_dt(r_row["evaluated_at_market_time"]) if r_row["evaluated_at_market_time"] else None
                reports.append(
                    ReconciliationReport(
                        report_id=r_id,
                        account_id=r_row["account_id"],
                        paper_session_id=r_row["paper_session_id"],
                        checked_state_generation=int(r_row["checked_state_generation"]),
                        status=ReconciliationStatus(r_row["status"]),
                        findings=findings,
                        critical_count=int(r_row["critical_count"]),
                        warning_count=int(r_row["warning_count"]),
                        info_count=int(r_row["info_count"]),
                        evaluated_at_market_time=m_dt,
                        evaluated_at_utc=_str_to_dt(r_row["evaluated_at_utc"]),
                    )
                )
            return tuple(reports)
        except Exception as ex:
            self._health = PersistenceHealth.FAILED
            logger.critical("Failed to query reconciliation reports: %s", ex)
            raise PersistenceTransactionError(f"Failed to query reconciliation reports: {ex}") from ex

    def get_latest_reconciliation_report(self) -> ReconciliationReport | None:
        """Read the most recent reconciliation report."""
        reports = self.query_reconciliation_reports(limit=1)
        return reports[0] if reports else None

    # ------------------------------------------------------------------
    # Phase 5 P1-08: Promotion Tracking & Session Evidence Store APIs
    # ------------------------------------------------------------------

    def save_promotion_session_finalization(
        self,
        owner: SubscriptionOwnerKey,
        record: PromotionSessionRecord,
        state: PromotionTrackingState,
    ) -> None:
        """Atomically commit append-only session record and updated promotion state in one SQLite transaction."""
        if self._health is not PersistenceHealth.HEALTHY:
            raise PersistenceError("Cannot save promotion session finalization: PersistenceHealth is FAILED")

        with self.transaction() as cursor:
            # 1. Check if record already exists for (strategy_id, strategy_version, session_date)
            cursor.execute(
                """
                SELECT session_status, reasons_json FROM promotion_session_records
                WHERE strategy_id = ? AND strategy_version = ? AND session_date = ?;
                """,
                (owner.strategy_id, owner.strategy_version, record.session_date.isoformat()),
            )
            existing = cursor.fetchone()
            if existing is not None:
                # Replay / Idempotency check:
                ex_status = existing["session_status"]
                ex_reasons = json.loads(existing["reasons_json"])
                if ex_status == record.session_status.value and tuple(ex_reasons) == record.reasons:
                    return
                raise PersistenceCorruptedError(
                    f"Contradictory promotion session record for {owner} on {record.session_date.isoformat()}: "
                    f"existing=({ex_status}, {ex_reasons}), incoming=({record.session_status.value}, {record.reasons})"
                )

            # 2. Insert append-only session record
            rec_fp = record.record_fingerprint or record.compute_fingerprint()
            rec_paper_sess = record.paper_session_id or self._paper_session_id or "default_paper_session"
            rec_cfg_ident = record.configuration_identity or self._configuration_identity or "default_config_id"
            cursor.execute(
                """
                INSERT INTO promotion_session_records (
                    strategy_id, strategy_version, session_date,
                    paper_session_id, configuration_identity,
                    upstream_promotion_fingerprint, session_status,
                    reasons_json, record_schema_version, record_fingerprint, recorded_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    owner.strategy_id,
                    owner.strategy_version,
                    record.session_date.isoformat(),
                    rec_paper_sess,
                    rec_cfg_ident,
                    record.upstream_promotion_fingerprint,
                    record.session_status.value,
                    json.dumps(list(record.reasons)),
                    record.record_schema_version,
                    rec_fp,
                    _dt_to_str(record.recorded_at_utc),
                ),
            )

            # 3. Update current promotion_tracking_state
            state_paper_sess = state.paper_session_id or self._paper_session_id or "default_paper_session"
            state_cfg_ident = state.configuration_identity or self._configuration_identity or "default_config_id"
            cursor.execute(
                """
                UPDATE promotion_tracking_state SET
                    tracking_status = ?,
                    activated_at = ?,
                    window_start_date = ?,
                    clean_days_count = ?,
                    disqualified_days_count = ?,
                    last_evaluated_session_date = ?,
                    milestone_status = ?,
                    state_generation = ?,
                    updated_at = ?
                WHERE strategy_id = ? AND strategy_version = ? AND paper_session_id = ?;
                """,
                (
                    state.tracking_status.value,
                    _dt_to_str(state.activated_at) if state.activated_at else None,
                    state.window_start_date.isoformat() if state.window_start_date else None,
                    state.clean_days_count,
                    state.disqualified_days_count,
                    state.last_evaluated_session_date.isoformat() if state.last_evaluated_session_date else None,
                    state.milestone_status.value,
                    state.state_generation,
                    _dt_to_str(state.updated_at),
                    owner.strategy_id,
                    owner.strategy_version,
                    state_paper_sess,
                ),
            )
            if cursor.rowcount == 0:
                cursor.execute(
                    """
                    INSERT INTO promotion_tracking_state (
                        strategy_id, strategy_version, paper_session_id,
                        configuration_identity, upstream_promotion_fingerprint,
                        tracking_status, activated_at, window_start_date,
                        clean_days_count, disqualified_days_count,
                        last_evaluated_session_date, milestone_status,
                        state_generation, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        owner.strategy_id,
                        owner.strategy_version,
                        state_paper_sess,
                        state_cfg_ident,
                        state.upstream_promotion_fingerprint,
                        state.tracking_status.value,
                        _dt_to_str(state.activated_at) if state.activated_at else None,
                        state.window_start_date.isoformat() if state.window_start_date else None,
                        state.clean_days_count,
                        state.disqualified_days_count,
                        state.last_evaluated_session_date.isoformat() if state.last_evaluated_session_date else None,
                        state.milestone_status.value,
                        state.state_generation,
                        _dt_to_str(state.updated_at),
                    ),
                )

    def save_promotion_tracking_state(self, state: PromotionTrackingState) -> None:
        """Atomically update promotion_tracking_state row."""
        if self._health is not PersistenceHealth.HEALTHY:
            raise PersistenceError("Cannot save promotion tracking state: PersistenceHealth is FAILED")

        state_paper_sess = state.paper_session_id or self._paper_session_id or "default_paper_session"
        state_cfg_ident = state.configuration_identity or self._configuration_identity or "default_config_id"
        with self.transaction() as cursor:
            cursor.execute(
                """
                UPDATE promotion_tracking_state SET
                    tracking_status = ?,
                    activated_at = ?,
                    window_start_date = ?,
                    clean_days_count = ?,
                    disqualified_days_count = ?,
                    last_evaluated_session_date = ?,
                    milestone_status = ?,
                    state_generation = ?,
                    updated_at = ?
                WHERE strategy_id = ? AND strategy_version = ? AND paper_session_id = ?;
                """,
                (
                    state.tracking_status.value,
                    _dt_to_str(state.activated_at) if state.activated_at else None,
                    state.window_start_date.isoformat() if state.window_start_date else None,
                    state.clean_days_count,
                    state.disqualified_days_count,
                    state.last_evaluated_session_date.isoformat() if state.last_evaluated_session_date else None,
                    state.milestone_status.value,
                    state.state_generation,
                    _dt_to_str(state.updated_at),
                    state.strategy_id,
                    state.strategy_version,
                    state_paper_sess,
                ),
            )
            if cursor.rowcount == 0:
                cursor.execute(
                    """
                    INSERT INTO promotion_tracking_state (
                        strategy_id, strategy_version, paper_session_id,
                        configuration_identity, upstream_promotion_fingerprint,
                        tracking_status, activated_at, window_start_date,
                        clean_days_count, disqualified_days_count,
                        last_evaluated_session_date, milestone_status,
                        state_generation, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        state.strategy_id,
                        state.strategy_version,
                        state_paper_sess,
                        state_cfg_ident,
                        state.upstream_promotion_fingerprint,
                        state.tracking_status.value,
                        _dt_to_str(state.activated_at) if state.activated_at else None,
                        state.window_start_date.isoformat() if state.window_start_date else None,
                        state.clean_days_count,
                        state.disqualified_days_count,
                        state.last_evaluated_session_date.isoformat() if state.last_evaluated_session_date else None,
                        state.milestone_status.value,
                        state.state_generation,
                        _dt_to_str(state.updated_at),
                    ),
                )

    def load_promotion_tracking_states(self) -> dict[SubscriptionOwnerKey, PromotionTrackingState]:
        """Load current promotion tracking states for all configured strategies and validate consistency with session ledger (ADR §122 OD-AA)."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM promotion_tracking_state;")
        result = {}
        for prow in cursor.fetchall():
            owner = SubscriptionOwnerKey(prow["strategy_id"], prow["strategy_version"])
            act_dt = _str_to_dt(prow["activated_at"]) if prow["activated_at"] else None
            win_d = date.fromisoformat(prow["window_start_date"]) if prow["window_start_date"] else None
            last_d = date.fromisoformat(prow["last_evaluated_session_date"]) if prow["last_evaluated_session_date"] else None
            upd_dt = _str_to_dt(prow["updated_at"]) or recorded_at_utc_now()
            state = PromotionTrackingState(
                strategy_id=prow["strategy_id"],
                strategy_version=prow["strategy_version"],
                paper_session_id=prow["paper_session_id"],
                configuration_identity=prow["configuration_identity"],
                upstream_promotion_fingerprint=prow["upstream_promotion_fingerprint"],
                tracking_status=PromotionTrackingStatus(prow["tracking_status"]),
                activated_at=act_dt,
                window_start_date=win_d,
                clean_days_count=int(prow["clean_days_count"]),
                disqualified_days_count=int(prow["disqualified_days_count"]),
                last_evaluated_session_date=last_d,
                milestone_status=PromotionMilestoneStatus(prow["milestone_status"]),
                state_generation=int(prow["state_generation"]),
                updated_at=upd_dt,
            )

            # State vs Session Ledger Consistency Cross-Validation (OD-AA)
            records = self.load_promotion_session_records(owner)
            clean_count = sum(1 for r in records if r.session_status == PromotionSessionStatus.SESSION_QUALIFIED)
            disq_count = sum(1 for r in records if r.session_status == PromotionSessionStatus.SESSION_DISQUALIFIED)
            if clean_count != state.clean_days_count:
                raise PersistenceCorruptedError(
                    f"clean_days_count mismatch for {owner}: state={state.clean_days_count}, ledger={clean_count}"
                )
            if disq_count != state.disqualified_days_count:
                raise PersistenceCorruptedError(
                    f"disqualified_days_count mismatch for {owner}: state={state.disqualified_days_count}, ledger={disq_count}"
                )
            if records:
                max_d = max(r.session_date for r in records)
                if state.last_evaluated_session_date != max_d:
                    raise PersistenceCorruptedError(
                        f"last_evaluated_session_date mismatch for {owner}: state={state.last_evaluated_session_date}, ledger={max_d}"
                    )
            if state.window_start_date is not None:
                for r in records:
                    if r.session_date >= state.window_start_date and r.session_status == PromotionSessionStatus.SESSION_DISQUALIFIED:
                        raise PersistenceCorruptedError(
                            f"window_start_date {state.window_start_date} contradicted by disqualified session on {r.session_date} for {owner}"
                        )
            if state.tracking_status == PromotionTrackingStatus.TRACKING_COMPLETED or state.milestone_status == PromotionMilestoneStatus.CRITERIA_MET_PENDING_REVIEW:
                if state.window_start_date is None or state.clean_days_count == 0:
                    raise PersistenceCorruptedError(
                        f"completed tracking status unsupported by session ledger for {owner}"
                    )
            if state.state_generation < 0:
                raise PersistenceCorruptedError(f"state_generation negative for {owner}")

            result[owner] = state
        return result

    def load_promotion_session_records(
        self,
        owner: SubscriptionOwnerKey | None = None,
    ) -> list[PromotionSessionRecord]:
        """Load append-only promotion session records and verify record fingerprints (ADR §122 OD-Z)."""
        cursor = self._conn.cursor()
        if owner is not None:
            cursor.execute(
                "SELECT * FROM promotion_session_records WHERE strategy_id = ? AND strategy_version = ? ORDER BY session_date ASC;",
                (owner.strategy_id, owner.strategy_version),
            )
        else:
            cursor.execute("SELECT * FROM promotion_session_records ORDER BY session_date ASC;")
        records = []
        for srec in cursor.fetchall():
            rec_d = date.fromisoformat(srec["session_date"])
            reasons_val = json.loads(srec["reasons_json"])
            rec_utc = _str_to_dt(srec["recorded_at_utc"]) or recorded_at_utc_now()
            stored_schema = srec["record_schema_version"]
            stored_fp = srec["record_fingerprint"]
            record = PromotionSessionRecord(
                strategy_id=srec["strategy_id"],
                strategy_version=srec["strategy_version"],
                session_date=rec_d,
                paper_session_id=srec["paper_session_id"],
                configuration_identity=srec["configuration_identity"],
                upstream_promotion_fingerprint=srec["upstream_promotion_fingerprint"],
                session_status=PromotionSessionStatus(srec["session_status"]),
                reasons=tuple(reasons_val),
                recorded_at_utc=rec_utc,
                record_schema_version=stored_schema,
                record_fingerprint=stored_fp,
            )
            computed_fp = record.compute_fingerprint()
            if stored_fp != computed_fp:
                raise PersistenceCorruptedError(
                    f"promotion session record checksum mismatch on {rec_d} for ({record.strategy_id}, {record.strategy_version}): "
                    f"stored={stored_fp!r}, computed={computed_fp!r}"
                )
            records.append(record)
        return records


    def load_completed_trades_for_strategy(
        self,
        owner: SubscriptionOwnerKey,
    ) -> list[TradeRecord]:
        """Load authoritative completed TradeRecord list for the given strategy owner."""
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT record_json FROM trade_records
            WHERE strategy_id = ? AND strategy_version = ?
            ORDER BY exit_timestamp ASC;
            """,
            (owner.strategy_id, owner.strategy_version),
        )
        trades = []
        for row in cursor.fetchall():
            rec_dict = json.loads(row["record_json"])
            trades.append(_dict_to_trade_record(rec_dict))
        return trades

    def load_all_completed_trades(self) -> list[TradeRecord]:
        """Load ALL authoritative completed TradeRecords (Phase 6 Q92/Q93 source).

        Canonical trade evidence only — deterministic order; no audit-table reads.
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT record_json FROM trade_records ORDER BY exit_timestamp ASC, trade_id ASC;"
        )
        return [_dict_to_trade_record(json.loads(row["record_json"])) for row in cursor.fetchall()]

    def load_cost_totals_by_trade(self) -> dict[str, Decimal]:
        """Canonical per-trade cost totals from cost_assessments (Q92/Q93 source).

        Multiple assessment rows for one trade_id are summed exactly once each,
        ordered by assessment_id for determinism. No audit-table reads.
        """
        cursor = self._conn.cursor()
        cursor.execute("SELECT trade_id, total_cost FROM cost_assessments ORDER BY assessment_id ASC;")
        totals: dict[str, Decimal] = {}
        for row in cursor.fetchall():
            tid = str(row["trade_id"])
            amount = _str_to_dec(str(row["total_cost"]))
            totals[tid] = totals.get(tid, Decimal("0")) + amount
        return totals

    # ------------------------------------------------------------------
    # Phase 6 / ADR §124.3/§124.5 + §125 (P1-01/C1–C6): durable Q93
    # observation marker + contract version — operational report-trigger
    # bookkeeping in the EXISTING paper_metadata key/value facility.
    # Additive keys only: no DDL, no schema-version change, no
    # state_generation effect, no accounting authority. Marker canonical
    # value format: "YYYY-MM". Contract: "algofortis-q93-state/v1".
    # ------------------------------------------------------------------

    Q93_CONTRACT_VERSION = "algofortis-q93-state/v1"
    _Q93_CONTRACT_KEY = "q93_contract_version"
    _Q93_LAST_OBSERVED_KEY = "q93_last_observed_ist_month"
    _Q93_MONTH_MIN_YEAR = 1970
    _Q93_MONTH_MAX_YEAR = 9999

    @staticmethod
    def _validate_q93_year_month(year: int, month: int) -> None:
        if not isinstance(year, int) or isinstance(year, bool) or not (
            SQLitePaperStateStore._Q93_MONTH_MIN_YEAR <= year <= SQLitePaperStateStore._Q93_MONTH_MAX_YEAR
        ):
            raise ValueError(f"Q93 marker year out of supported range: {year!r}")
        if not isinstance(month, int) or isinstance(month, bool) or not 1 <= month <= 12:
            raise ValueError(f"Q93 marker month out of range: {month!r}")

    def load_q93_last_observed_ist_month(self) -> tuple[int, int] | None:
        """Durable Q93 last-observed IST (year, month); None = bootstrap state.

        Fail-closed on malformed/corrupt persisted values — never a silent
        reset to None.
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT value FROM paper_metadata WHERE key = ?;",
            (SQLitePaperStateStore._Q93_LAST_OBSERVED_KEY,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        raw = row["value"]
        if not isinstance(raw, str):
            raise PersistenceCorruptedError(
                f"Q93 last-observed marker must be a string, got {type(raw).__name__}"
            )
        parts = raw.split("-")
        if len(parts) != 2 or len(parts[0]) != 4 or len(parts[1]) != 2:
            raise PersistenceCorruptedError(
                f"Q93 last-observed marker is malformed: {raw!r} (expected 'YYYY-MM')"
            )
        try:
            year = int(parts[0])
            month = int(parts[1])
        except ValueError as exc:
            raise PersistenceCorruptedError(
                f"Q93 last-observed marker is non-numeric: {raw!r}"
            ) from exc
        try:
            self._validate_q93_year_month(year, month)
        except ValueError as exc:
            raise PersistenceCorruptedError(str(exc)) from exc
        return (year, month)

    def save_q93_last_observed_ist_month(self, year: int, month: int) -> None:
        """Durably persist the Q93 last-observed IST month (monotonic, atomic).

        ADR §125.6 (C6): validation, existing-marker read, comparison and the
        conditional write all happen inside ONE exclusive transaction
        (`audit_only_transaction`, no state_generation effect). Transitions:
        missing→M inserts; M→M is an idempotent no-op; M→later updates;
        M→earlier raises :class:`Q93MarkerRegressionError` and leaves durable
        data untouched. Concurrent writers serialize at SQLite level, so a
        later month can never be lost or regressed.
        """
        self._validate_q93_year_month(year, month)
        requested = (year, month)
        value = f"{year:04d}-{month:02d}"
        rejection: str | None = None
        with self.audit_only_transaction() as cursor:
            cursor.execute(
                "SELECT value FROM paper_metadata WHERE key = ?;",
                (SQLitePaperStateStore._Q93_LAST_OBSERVED_KEY,),
            )
            row = cursor.fetchone()
            if row is not None:
                existing_raw = row["value"]
                existing = self._parse_q93_month_value(existing_raw)
                if requested < existing:
                    # Logical rejection: commit the read-only exclusive
                    # transaction (durable data untouched, journal stays
                    # healthy), then raise outside so a valid database is
                    # never marked FAILED for a caller's invalid request.
                    rejection = (
                        f"Q93 marker regression rejected: existing "
                        f"{existing[0]:04d}-{existing[1]:02d} -> requested "
                        f"{requested[0]:04d}-{requested[1]:02d}"
                    )
                elif requested == existing:
                    return
                else:
                    cursor.execute(
                        """
                        INSERT INTO paper_metadata (key, value) VALUES (?, ?)
                        ON CONFLICT(key) DO UPDATE SET value = excluded.value;
                        """,
                        (SQLitePaperStateStore._Q93_LAST_OBSERVED_KEY, value),
                    )
            else:
                cursor.execute(
                    """
                    INSERT INTO paper_metadata (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value;
                    """,
                    (SQLitePaperStateStore._Q93_LAST_OBSERVED_KEY, value),
                )
        if rejection is not None:
            raise Q93MarkerRegressionError(rejection)

    @classmethod
    def _parse_q93_month_value(cls, raw: object) -> tuple[int, int]:
        """Strict parser for a persisted 'YYYY-MM' Q93 marker value."""
        if not isinstance(raw, str):
            raise PersistenceCorruptedError(
                f"Q93 last-observed marker must be a string, got {type(raw).__name__}"
            )
        parts = raw.split("-")
        if len(parts) != 2 or len(parts[0]) != 4 or len(parts[1]) != 2:
            raise PersistenceCorruptedError(
                f"Q93 last-observed marker is malformed: {raw!r} (expected 'YYYY-MM')"
            )
        try:
            year = int(parts[0])
            month = int(parts[1])
        except ValueError as exc:
            raise PersistenceCorruptedError(
                f"Q93 last-observed marker is non-numeric: {raw!r}"
            ) from exc
        try:
            cls._validate_q93_year_month(year, month)
        except ValueError as exc:
            raise PersistenceCorruptedError(str(exc)) from exc
        return (year, month)

    def load_contract_version(self) -> str | None:
        """Read the persisted Q93 contract version, if present."""
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT value FROM paper_metadata WHERE key = ?;",
            (SQLitePaperStateStore._Q93_CONTRACT_KEY,),
        )
        row = cursor.fetchone()
        return None if row is None else str(row["value"])

    # ------------------------------------------------------------------
    # Phase 8 / ADR §128.8–§128.10: durable per-strategy halt latch —
    # operational SAFETY-GATING authority in the EXISTING paper_metadata
    # facility.  Additive keys only: no DDL, no schema-version change, no
    # migration.  Contract: "algofortis-halt-state/v1".  Canonical
    # structured owner serialization (no colon-concatenated identities).
    # Authoritative writes use the standard durable `transaction()`
    # semantics (the same class of transaction as save_safety_state), NOT
    # audit_only_transaction (§128.10).
    # ------------------------------------------------------------------

    HALT_CONTRACT_VERSION = "algofortis-halt-state/v1"
    _HALT_CONTRACT_KEY = "halt_contract_version"
    _HALTED_OWNERS_KEY = "halted_strategy_owners"

    def load_halted_strategy_owners(self) -> tuple[tuple[str, str], ...]:
        """Durable halted strategy owners; () when never persisted (bootstrap).

        Fail-closed on any malformed/inconsistent persisted state — never a
        silent reset.  Both metadata keys are written atomically together by
        :meth:`save_halted_strategy_owners`; a state key without a matching
        contract key (or vice versa mismatch) is corruption.
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT key, value FROM paper_metadata WHERE key IN (?, ?);",
            (SQLitePaperStateStore._HALT_CONTRACT_KEY, SQLitePaperStateStore._HALTED_OWNERS_KEY),
        )
        rows = {row["key"]: row["value"] for row in cursor.fetchall()}
        contract = rows.get(SQLitePaperStateStore._HALT_CONTRACT_KEY)
        state = rows.get(SQLitePaperStateStore._HALTED_OWNERS_KEY)
        if contract is None and state is None:
            return ()
        if contract is None:
            raise PersistenceCorruptedError(
                "halted_strategy_owners present without halt_contract_version"
            )
        if contract != SQLitePaperStateStore.HALT_CONTRACT_VERSION:
            raise PersistenceCorruptedError(
                f"Mismatched halt_contract_version: database has {contract!r}, "
                f"expected {SQLitePaperStateStore.HALT_CONTRACT_VERSION!r}"
            )
        if state is None:
            raise PersistenceCorruptedError(
                "halt_contract_version present without halted_strategy_owners"
            )
        from engine.safety.phase8_safety import parse_halted_owners

        try:
            return parse_halted_owners(state)
        except ValueError as exc:
            raise PersistenceCorruptedError(
                f"halted_strategy_owners payload is corrupt: {exc}"
            ) from exc

    def save_halted_strategy_owners(
        self, owners: Sequence[tuple[str, str]]
    ) -> None:
        """Atomically persist the canonical halted-owner set (safety authority).

        Writes BOTH ``halt_contract_version`` and ``halted_strategy_owners``
        inside ONE exclusive durable transaction (standard authoritative
        write semantics per §128.10).  Idempotent when the canonical payload
        is unchanged.  Validation failures raise before any write.
        """
        from engine.safety.phase8_safety import serialize_halted_owners

        payload = serialize_halted_owners(owners)
        with self.transaction() as cursor:
            cursor.execute("SELECT value FROM paper_metadata WHERE key = ?;", (self._HALTED_OWNERS_KEY,))
            existing = cursor.fetchone()
            if existing is not None and str(existing["value"]) == payload:
                cursor.execute(
                    """
                    INSERT INTO paper_metadata (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value;
                    """,
                    (self._HALT_CONTRACT_KEY, self.HALT_CONTRACT_VERSION),
                )
                return
            cursor.execute(
                "DELETE FROM paper_metadata WHERE key = ?;",
                (self._HALTED_OWNERS_KEY,),
            )
            cursor.execute(
                """
                INSERT INTO paper_metadata (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value;
                """,
                (self._HALT_CONTRACT_KEY, self.HALT_CONTRACT_VERSION),
            )
            cursor.execute(
                """
                INSERT INTO paper_metadata (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value;
                """,
                (self._HALTED_OWNERS_KEY, payload),
            )


