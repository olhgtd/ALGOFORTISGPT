"""Phase 5 OD-7 Item 12: Independent Reconciliation Engine for Paper Trading.

Pure read-only deterministic reconciliation engine that compares independently
maintained runtime and persisted evidence across paper broker, virtual account,
positions, cash, premium commitments, risk commitments, protective exits,
trade ledger, and transaction costs.

OWNER FROZEN CONTRACTS:
  - REC-1: Dedicated engine/reconciliation/paper/engine.py module.
  - REC-2: Real cross-authority/cross-domain comparison; distinguishes live
           same-process independence from restart same-source mirror.
  - REC-3: Immutable typed ReconciliationReport and ReconciliationFinding models.
  - REC-4: Deterministic finding_key and finding_id derivation.
  - REC-5: Broker order ledger reconciliation (order_id, identity, lifecycle, quantity).
  - REC-6: Processed fill reconciliation across broker, account, and store.
  - REC-7: Independent net position quantity derivation from processed fills
           (multi-leg scale-in and partial reduction supported).
  - REC-8: Gross cash and realized P&L invariants (zero transaction fee deduction from cash).
  - REC-9: Premium commitment 1:1 match with QUEUED opening BUY orders.
  - REC-10: Risk commitment 1:1 match with in-flight opening intent lifecycle.
  - REC-11: Protective exit and pending-close reconciliation.
  - REC-12: Multi-leg closed trade ledger reconciliation.
  - REC-13: Frozen cost assessment evidence verification (no live policy recalculation).
  - REC-14: Audit journal is read-only supporting evidence (zero audit mutation).
  - REC-15 / REC-16: Startup reconciliation and post-transaction dirty lifecycle.
  - REC-17: Severity matrix: CRITICAL (blocks new exposure), WARNING, INFO.
  - REC-20 / REC-20A: Orthogonal coordinator health (UNKNOWN/DIRTY/MATCHED/FAILED);
                      FAILED is latched; manual operator run required to clear.
  - REC-21 / REC-45: Observational report persistence (zero state_generation bump).
  - REC-22 / REC-48: Closed Item-11 taxonomy preserved (zero new audit families).
  - REC-25 / REC-44: Coherent point-in-time snapshot contract.
  - REC-46: Pure read-only reconciliation logic; zero canonical state mutation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from enum import Enum
from typing import Any, Mapping, Sequence

from engine.audit.model import recorded_at_utc_now
from engine.costs.model import CostAssessment, trade_evidence_fingerprint
from engine.execution.paper_broker import BrokerOrderRecord, BrokerTerminalEvent
from engine.core.numeric import as_decimal
from engine.orders.lifecycle import OrderLifecycleState
from engine.portfolio.model import (
    INTERNAL_DECIMAL_CONTEXT,
    AccountSnapshot,
    AccountingResult,
    InstrumentIdentity,
    PositionKey,
    PositionSnapshot,
    quantize_monetary,
)
from engine.risk.risk_manager import PendingRiskCommitment, entry_intent_identity
from engine.portfolio.virtual_account import PremiumCommitmentRecord
from engine.protective.runtime import ProtectiveExit, ProtectiveExitState
from engine.protective.live import LiveProtectivePendingClose
from engine.reproducibility.codec import CanonicalCodec
from engine.risk.risk_manager import PendingRiskCommitment
from engine.trades.model import TradeLeg, TradeRecord

logger = logging.getLogger(__name__)

__all__ = [
    "ReconciliationHealth",
    "ReconciliationStatus",
    "ReconciliationSeverity",
    "ReconciliationFinding",
    "ReconciliationReport",
    "ReconciliationRuntimeSnapshot",
    "ReconciliationPersistedSnapshot",
    "PaperReconciliationEngine",
    "derive_reconciliation_finding_key",
    "derive_reconciliation_finding_id",
    "canonical_reconciliation_json",
]


# ======================================================================
# 1. Enums
# ======================================================================

class ReconciliationHealth(str, Enum):
    """Coordinator-owned orthogonal reconciliation health state."""

    UNKNOWN = "UNKNOWN"
    DIRTY = "DIRTY"
    MATCHED = "MATCHED"
    FAILED = "FAILED"


class ReconciliationStatus(str, Enum):
    """Immutable status of a single reconciliation evaluation report."""

    MATCHED = "MATCHED"
    MISMATCH = "MISMATCH"
    UNAVAILABLE = "UNAVAILABLE"


class ReconciliationSeverity(str, Enum):
    """Discrepancy severity classification."""

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


# ======================================================================
# 2. Canonical JSON Serialization Helper
# ======================================================================

def _serialize_canonical_value(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, (str, int, bool)):
        return val
    if isinstance(val, Decimal):
        return str(val)
    if isinstance(val, datetime):
        if val.tzinfo is None or val.utcoffset() is None:
            return val.replace(tzinfo=timezone.utc).isoformat()
        return val.isoformat()
    if isinstance(val, Enum):
        return val.value
    if isinstance(val, (list, tuple)):
        return [_serialize_canonical_value(x) for x in val]
    if isinstance(val, (dict, Mapping)):
        return {str(k): _serialize_canonical_value(v) for k, v in sorted(val.items(), key=lambda x: str(x[0]))}
    if hasattr(val, "__dataclass_fields__"):
        return {k: _serialize_canonical_value(getattr(val, k)) for k in sorted(val.__dataclass_fields__.keys())}
    return str(val)


def canonical_reconciliation_json(data: Any) -> str:
    """Deterministic, allowlisted JSON serialization for reconciliation payloads."""
    canonical_obj = _serialize_canonical_value(data)
    return json.dumps(canonical_obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


# ======================================================================
# 3. Deterministic Identity Derivation
# ======================================================================

def derive_reconciliation_finding_key(
    finding_type: str,
    aggregate_type: str,
    aggregate_identity: str,
    expected_payload: Any,
    observed_payload: Any,
) -> str:
    """Derive stable, report-independent fingerprint for a discrepancy finding."""
    exp_json = canonical_reconciliation_json(expected_payload)
    obs_json = canonical_reconciliation_json(observed_payload)
    raw = f"{finding_type}|{aggregate_type}|{aggregate_identity}|{exp_json}|{obs_json}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def derive_reconciliation_finding_id(report_id: str, finding_key: str) -> str:
    """Derive run-scoped unique identifier for a finding in a specific report."""
    raw = f"{report_id}|{finding_key}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ======================================================================
# 4. Immutable Finding & Report Models
# ======================================================================

@dataclass(frozen=True)
class ReconciliationFinding:
    """Immutable record of one discrepancy or consistency observation."""

    finding_id: str
    report_id: str
    finding_key: str
    finding_type: str
    severity: ReconciliationSeverity
    aggregate_type: str
    aggregate_identity: str
    market_timestamp: datetime | None
    expected_json: str
    observed_json: str
    details_json: str

    def __post_init__(self) -> None:
        if not isinstance(self.finding_id, str) or not self.finding_id.strip():
            raise ValueError("finding_id must be a non-empty string")
        if not isinstance(self.report_id, str) or not self.report_id.strip():
            raise ValueError("report_id must be a non-empty string")
        if not isinstance(self.finding_key, str) or not self.finding_key.strip():
            raise ValueError("finding_key must be a non-empty string")
        if not isinstance(self.finding_type, str) or not self.finding_type.strip():
            raise ValueError("finding_type must be a non-empty string")
        if not isinstance(self.severity, ReconciliationSeverity):
            raise TypeError("severity must be a ReconciliationSeverity")
        if not isinstance(self.aggregate_type, str) or not self.aggregate_type.strip():
            raise ValueError("aggregate_type must be a non-empty string")
        if not isinstance(self.aggregate_identity, str) or not self.aggregate_identity.strip():
            raise ValueError("aggregate_identity must be a non-empty string")


@dataclass(frozen=True)
class ReconciliationReport:
    """Immutable complete evaluation result from one reconciliation execution."""

    report_id: str
    account_id: str
    paper_session_id: str
    checked_state_generation: int
    status: ReconciliationStatus
    findings: tuple[ReconciliationFinding, ...]
    critical_count: int
    warning_count: int
    info_count: int
    evaluated_at_market_time: datetime | None
    evaluated_at_utc: datetime
    is_restart_hydration: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.report_id, str) or not self.report_id.strip():
            raise ValueError("report_id must be a non-empty string")
        if not isinstance(self.account_id, str) or not self.account_id.strip():
            raise ValueError("account_id must be a non-empty string")
        if not isinstance(self.paper_session_id, str) or not self.paper_session_id.strip():
            raise ValueError("paper_session_id must be a non-empty string")
        if not isinstance(self.checked_state_generation, int) or self.checked_state_generation < 0:
            raise ValueError("checked_state_generation must be a non-negative integer")
        if not isinstance(self.status, ReconciliationStatus):
            raise TypeError("status must be a ReconciliationStatus")
        if not isinstance(self.evaluated_at_utc, datetime) or self.evaluated_at_utc.tzinfo is None:
            raise ValueError("evaluated_at_utc must be a timezone-aware datetime")


# ======================================================================
# 5. Snapshot Models
# ======================================================================

@dataclass(frozen=True)
class ReconciliationRuntimeSnapshot:
    """Immutable runtime snapshot captured inside coordinator serialization lock."""

    account_id: str
    paper_session_id: str
    state_generation: int
    market_timestamp: datetime | None
    is_restart_hydration: bool
    broker_pending_orders: tuple[BrokerOrderRecord, ...]
    broker_terminal_orders: tuple[BrokerTerminalEvent, ...]
    account_snapshot: AccountSnapshot
    positions: Mapping[PositionKey, PositionSnapshot]
    active_commitments: tuple[PremiumCommitmentRecord, ...]
    processed_fills: Mapping[str, tuple[BrokerTerminalEvent, AccountingResult]]
    completed_trades: tuple[TradeRecord, ...]
    cost_assessments: tuple[CostAssessment, ...]
    protective_exits: tuple[ProtectiveExit, ...] = ()
    protective_pending_closes: tuple[LiveProtectivePendingClose, ...] = ()
    pending_risk_commitments: tuple[PendingRiskCommitment, ...] = ()


@dataclass(frozen=True)
class ReconciliationPersistedSnapshot:
    """Immutable snapshot read from SQLite in one consistent read transaction."""

    state_generation: int
    account_state: AccountSnapshot | None
    positions: Mapping[PositionKey, PositionSnapshot]
    premium_commitments: tuple[PremiumCommitmentRecord, ...]
    broker_orders: tuple[BrokerOrderRecord, ...]
    processed_fills: tuple[tuple[str, str, str, str, Decimal, Decimal, Decimal, datetime, str], ...]
    # tuple of (broker_order_identity, order_id, lifecycle_state, instrument_key, fill_price, filled_quantity, fee, fill_timestamp, semantic_fingerprint)
    protective_exits: tuple[ProtectiveExit, ...] = ()
    protective_pending_closes: tuple[LiveProtectivePendingClose, ...] = ()
    trade_records: tuple[TradeRecord, ...] = ()
    trade_legs: tuple[TradeLeg, ...] = ()
    cost_assessments: tuple[CostAssessment, ...] = ()


# ======================================================================
# 6. PaperReconciliationEngine
# ======================================================================

class PaperReconciliationEngine:
    """Pure, read-only reconciliation engine for Phase 5 paper trading.

    Performs strictly deterministic comparisons and structural verifications
    over immutable runtime and persisted snapshots. Never calls mutation methods.
    """

    def reconcile(
        self,
        runtime: ReconciliationRuntimeSnapshot,
        persisted: ReconciliationPersistedSnapshot,
        *,
        report_id: str | None = None,
        evaluated_at_utc: datetime | None = None,
    ) -> ReconciliationReport:
        """Execute full reconciliation evaluation and return an immutable report."""
        if report_id is None:
            report_id = str(uuid.uuid4())
        if evaluated_at_utc is None:
            evaluated_at_utc = recorded_at_utc_now()
        findings: list[ReconciliationFinding] = []

        def add_finding(
            finding_type: str,
            severity: ReconciliationSeverity,
            aggregate_type: str,
            aggregate_identity: str,
            expected: Any,
            observed: Any,
            details: Any = None,
        ) -> None:
            f_key = derive_reconciliation_finding_key(
                finding_type, aggregate_type, aggregate_identity, expected, observed
            )
            f_id = derive_reconciliation_finding_id(report_id, f_key)
            findings.append(
                ReconciliationFinding(
                    finding_id=f_id,
                    report_id=report_id,
                    finding_key=f_key,
                    finding_type=finding_type,
                    severity=severity,
                    aggregate_type=aggregate_type,
                    aggregate_identity=aggregate_identity,
                    market_timestamp=runtime.market_timestamp,
                    expected_json=canonical_reconciliation_json(expected),
                    observed_json=canonical_reconciliation_json(observed),
                    details_json=canonical_reconciliation_json(details or {}),
                )
            )

        # --------------------------------------------------------------
        # 1. State Generation Consistency
        # --------------------------------------------------------------
        if runtime.state_generation != persisted.state_generation:
            add_finding(
                finding_type="STATE_GENERATION_MISMATCH",
                severity=ReconciliationSeverity.CRITICAL,
                aggregate_type="STATE_STORE",
                aggregate_identity="paper_metadata",
                expected={"state_generation": runtime.state_generation},
                observed={"persisted_state_generation": persisted.state_generation},
                details={"reason": "runtime snapshot generation diverged from persisted snapshot generation"},
            )

        # --------------------------------------------------------------
        # 2. Broker Order Ledger Reconciliation
        # --------------------------------------------------------------
        persisted_orders_by_id = {o.order_id: o for o in persisted.broker_orders}
        persisted_orders_by_ident = {o.broker_order_identity: o for o in persisted.broker_orders}

        # Check duplicate broker identities in persisted
        if len(persisted_orders_by_ident) != len(persisted.broker_orders):
            add_finding(
                finding_type="DUPLICATE_BROKER_ORDER_IDENTITY",
                severity=ReconciliationSeverity.CRITICAL,
                aggregate_type="BROKER",
                aggregate_identity="persisted_broker_orders",
                expected={"unique_identities": len(persisted.broker_orders)},
                observed={"distinct_identities": len(persisted_orders_by_ident)},
            )

        # Same-process live check: compare in-memory broker vs SQLite
        if not runtime.is_restart_hydration:
            runtime_pending_by_id = {o.order_id: o for o in runtime.broker_pending_orders}
            runtime_terminal_by_id = {o.order_id: o for o in runtime.broker_terminal_orders}

            # All runtime pending orders must exist in persisted as QUEUED
            for order_id, r_order in runtime_pending_by_id.items():
                p_order = persisted_orders_by_id.get(order_id)
                if p_order is None:
                    add_finding(
                        finding_type="RUNTIME_BROKER_ORDER_ORPHAN",
                        severity=ReconciliationSeverity.CRITICAL,
                        aggregate_type="BROKER_ORDER",
                        aggregate_identity=order_id,
                        expected={"persisted_exists": True, "lifecycle": "QUEUED"},
                        observed={"persisted_exists": False},
                    )
                else:
                    if p_order.lifecycle_state != OrderLifecycleState.QUEUED:
                        add_finding(
                            finding_type="BROKER_ORDER_LIFECYCLE_CONFLICT",
                            severity=ReconciliationSeverity.CRITICAL,
                            aggregate_type="BROKER_ORDER",
                            aggregate_identity=order_id,
                            expected={"lifecycle_state": "QUEUED"},
                            observed={"persisted_lifecycle_state": p_order.lifecycle_state.value},
                        )
                    if p_order.broker_order_identity != r_order.broker_order_identity:
                        add_finding(
                            finding_type="BROKER_ORDER_IDENTITY_MISMATCH",
                            severity=ReconciliationSeverity.CRITICAL,
                            aggregate_type="BROKER_ORDER",
                            aggregate_identity=order_id,
                            expected={"broker_order_identity": r_order.broker_order_identity},
                            observed={"persisted_broker_order_identity": p_order.broker_order_identity},
                        )
                    if p_order.original_order.quantity != r_order.original_order.quantity:
                        add_finding(
                            finding_type="BROKER_ORDER_QUANTITY_MISMATCH",
                            severity=ReconciliationSeverity.CRITICAL,
                            aggregate_type="BROKER_ORDER",
                            aggregate_identity=order_id,
                            expected={"quantity": str(r_order.original_order.quantity)},
                            observed={"persisted_quantity": str(p_order.original_order.quantity)},
                        )

            # All runtime terminal orders must exist in persisted with matching terminal state
            for order_id, r_term in runtime_terminal_by_id.items():
                p_order = persisted_orders_by_id.get(order_id)
                if p_order is None:
                    add_finding(
                        finding_type="RUNTIME_TERMINAL_ORDER_ORPHAN",
                        severity=ReconciliationSeverity.CRITICAL,
                        aggregate_type="BROKER_ORDER",
                        aggregate_identity=order_id,
                        expected={"persisted_exists": True, "lifecycle": r_term.lifecycle_state.value},
                        observed={"persisted_exists": False},
                    )
                elif p_order.lifecycle_state != r_term.lifecycle_state:
                    add_finding(
                        finding_type="BROKER_ORDER_TERMINAL_STATE_MISMATCH",
                        severity=ReconciliationSeverity.CRITICAL,
                        aggregate_type="BROKER_ORDER",
                        aggregate_identity=order_id,
                        expected={"lifecycle_state": r_term.lifecycle_state.value},
                        observed={"persisted_lifecycle_state": p_order.lifecycle_state.value},
                    )
                elif p_order.broker_order_identity != r_term.broker_order_identity:
                    add_finding(
                        finding_type="BROKER_ORDER_IDENTITY_MISMATCH",
                        severity=ReconciliationSeverity.CRITICAL,
                        aggregate_type="BROKER_ORDER",
                        aggregate_identity=order_id,
                        expected={"broker_order_identity": r_term.broker_order_identity},
                        observed={"persisted_broker_order_identity": p_order.broker_order_identity},
                    )

            # Persisted QUEUED orders must exist in runtime pending
            for p_order in persisted.broker_orders:
                if p_order.lifecycle_state == OrderLifecycleState.QUEUED:
                    if p_order.order_id not in runtime_pending_by_id:
                        add_finding(
                            finding_type="PERSISTED_QUEUED_ORDER_ORPHAN",
                            severity=ReconciliationSeverity.CRITICAL,
                            aggregate_type="BROKER_ORDER",
                            aggregate_identity=p_order.order_id,
                            expected={"runtime_pending_exists": True},
                            observed={"runtime_pending_exists": False},
                        )

        # --------------------------------------------------------------
        # 3. Processed Fill Reconciliation
        # --------------------------------------------------------------
        persisted_fills_by_ident: dict[str, Any] = {}
        for row in persisted.processed_fills:
            ident, o_id, l_state, inst_key, price, qty, fee, ts, fp = row
            if ident in persisted_fills_by_ident:
                add_finding(
                    finding_type="DUPLICATE_PROCESSED_FILL",
                    severity=ReconciliationSeverity.CRITICAL,
                    aggregate_type="PROCESSED_FILL",
                    aggregate_identity=ident,
                    expected={"distinct_fill": True},
                    observed={"duplicate_fill": True},
                )
            persisted_fills_by_ident[ident] = {
                "order_id": o_id,
                "lifecycle_state": l_state,
                "instrument_key": inst_key,
                "fill_price": price,
                "filled_quantity": qty,
                "fee": fee,
                "fill_timestamp": ts,
                "fingerprint": fp,
            }

        # For every FILLED order in broker: must exist in processed_fills
        for p_order in persisted.broker_orders:
            if p_order.lifecycle_state == OrderLifecycleState.FILLED:
                fill_rec = persisted_fills_by_ident.get(p_order.broker_order_identity)
                if fill_rec is None:
                    add_finding(
                        finding_type="MISSING_PROCESSED_FILL_FOR_FILLED_ORDER",
                        severity=ReconciliationSeverity.CRITICAL,
                        aggregate_type="BROKER_ORDER",
                        aggregate_identity=p_order.order_id,
                        expected={"processed_fill_exists": True},
                        observed={"processed_fill_exists": False},
                    )

        # For every processed fill: broker order must be FILLED
        for ident, fill_data in persisted_fills_by_ident.items():
            p_order = persisted_orders_by_ident.get(ident)
            if p_order is None:
                add_finding(
                    finding_type="ORPHAN_PROCESSED_FILL",
                    severity=ReconciliationSeverity.CRITICAL,
                    aggregate_type="PROCESSED_FILL",
                    aggregate_identity=ident,
                    expected={"broker_order_exists": True, "lifecycle": "FILLED"},
                    observed={"broker_order_exists": False},
                )
            elif p_order.lifecycle_state != OrderLifecycleState.FILLED:
                add_finding(
                    finding_type="PROCESSED_FILL_LIFECYCLE_CONFLICT",
                    severity=ReconciliationSeverity.CRITICAL,
                    aggregate_type="PROCESSED_FILL",
                    aggregate_identity=ident,
                    expected={"broker_order_lifecycle": "FILLED"},
                    observed={"broker_order_lifecycle": p_order.lifecycle_state.value},
                )

        # --------------------------------------------------------------
        # 4. Position Quantity Derived from Fills (Multi-leg Scale-in / Scale-out)
        # --------------------------------------------------------------
        derived_position_quantities: dict[PositionKey, Decimal] = {}
        buy_fills: list[Any] = []
        sell_fills: list[Any] = []

        for p_order in persisted.broker_orders:
            if p_order.lifecycle_state == OrderLifecycleState.FILLED:
                strat_id = getattr(p_order.original_order, "strategy_id", None)
                strat_ver = getattr(p_order.original_order, "strategy_version", None)
                if strat_id is None and hasattr(p_order.original_order, "source_intent"):
                    strat_id = getattr(p_order.original_order.source_intent, "strategy_id", "default")
                    strat_ver = getattr(p_order.original_order.source_intent, "strategy_version", "default")
                key = PositionKey(
                    strategy_id=strat_id or "default",
                    strategy_version=strat_ver or "default",
                    identity=p_order.instrument_identity,
                )

                qty = as_decimal(p_order.original_order.quantity, "quantity")
                action = getattr(p_order.original_order, "action", None)
                if action is None and hasattr(p_order.original_order, "source_entry_order"):
                    action = getattr(p_order.original_order.source_entry_order, "action", None)
                if action is None and hasattr(p_order.original_order, "source_intent"):
                    action = getattr(p_order.original_order.source_intent, "action", None)

                p_spec = getattr(p_order, "specification", None)
                if p_spec is not None and hasattr(p_spec, "contract_multiplier"):
                    multiplier = as_decimal(p_spec.contract_multiplier, "contract_multiplier")
                else:
                    pos = runtime.positions.get(key) or persisted.positions.get(key)
                    if pos is not None:
                        multiplier = pos.contract_multiplier
                    else:
                        tr_matching = next((tr for tr in runtime.completed_trades if hasattr(tr, "position_key") and tr.position_key == key), None)
                        if tr_matching is not None and hasattr(tr_matching, "contract_multiplier"):
                            multiplier = tr_matching.contract_multiplier
                        else:
                            multiplier = Decimal("1")

                fill_info = persisted_fills_by_ident.get(p_order.broker_order_identity)
                fill_price = fill_info["fill_price"] if fill_info else p_order.reference_price

                if action == "BUY":
                    derived_position_quantities[key] = (
                        derived_position_quantities.get(key, Decimal("0")) + qty
                    )
                    buy_fills.append((qty, fill_price, multiplier))
                elif action == "SELL":
                    derived_position_quantities[key] = (
                        derived_position_quantities.get(key, Decimal("0")) - qty
                    )
                    sell_fills.append((qty, fill_price, multiplier))

        # Check derived quantity against active runtime and persisted positions
        all_position_keys = set(derived_position_quantities.keys()) | set(runtime.positions.keys()) | set(persisted.positions.keys())

        for key in sorted(all_position_keys, key=lambda k: str(k)):
            derived_qty = derived_position_quantities.get(key, Decimal("0"))
            r_pos = runtime.positions.get(key)
            p_pos = persisted.positions.get(key)

            if derived_qty < Decimal("0"):
                add_finding(
                    finding_type="NEGATIVE_DERIVED_POSITION_QUANTITY",
                    severity=ReconciliationSeverity.CRITICAL,
                    aggregate_type="POSITION",
                    aggregate_identity=str(key),
                    expected={"derived_quantity": ">= 0"},
                    observed={"derived_quantity": str(derived_qty)},
                )
            elif derived_qty == Decimal("0"):
                if r_pos is not None:
                    add_finding(
                        finding_type="CLOSED_POSITION_PRESENT_IN_RUNTIME",
                        severity=ReconciliationSeverity.CRITICAL,
                        aggregate_type="POSITION",
                        aggregate_identity=str(key),
                        expected={"position_present": False},
                        observed={"runtime_quantity": str(r_pos.quantity)},
                    )
                if p_pos is not None:
                    add_finding(
                        finding_type="CLOSED_POSITION_PRESENT_IN_PERSISTED",
                        severity=ReconciliationSeverity.CRITICAL,
                        aggregate_type="POSITION",
                        aggregate_identity=str(key),
                        expected={"position_present": False},
                        observed={"persisted_quantity": str(p_pos.quantity)},
                    )
            else:  # derived_qty > 0
                if r_pos is None:
                    add_finding(
                        finding_type="OPEN_POSITION_MISSING_IN_RUNTIME",
                        severity=ReconciliationSeverity.CRITICAL,
                        aggregate_type="POSITION",
                        aggregate_identity=str(key),
                        expected={"position_present": True, "quantity": str(derived_qty)},
                        observed={"runtime_position_present": False},
                    )
                elif r_pos.quantity != derived_qty:
                    add_finding(
                        finding_type="POSITION_QUANTITY_MISMATCH_RUNTIME",
                        severity=ReconciliationSeverity.CRITICAL,
                        aggregate_type="POSITION",
                        aggregate_identity=str(key),
                        expected={"derived_quantity": str(derived_qty)},
                        observed={"runtime_quantity": str(r_pos.quantity)},
                    )

                if p_pos is None:
                    add_finding(
                        finding_type="OPEN_POSITION_MISSING_IN_PERSISTED",
                        severity=ReconciliationSeverity.CRITICAL,
                        aggregate_type="POSITION",
                        aggregate_identity=str(key),
                        expected={"position_present": True, "quantity": str(derived_qty)},
                        observed={"persisted_position_present": False},
                    )
                elif p_pos.quantity != derived_qty:
                    add_finding(
                        finding_type="POSITION_QUANTITY_MISMATCH_PERSISTED",
                        severity=ReconciliationSeverity.CRITICAL,
                        aggregate_type="POSITION",
                        aggregate_identity=str(key),
                        expected={"derived_quantity": str(derived_qty)},
                        observed={"persisted_quantity": str(p_pos.quantity)},
                    )

        # --------------------------------------------------------------
        # 5. Gross Cash & Realized P&L Invariants (Zero Fee Deduction from Cash)
        # --------------------------------------------------------------
        starting_capital = runtime.account_snapshot.starting_capital
        monetary_quantum = runtime.account_snapshot.monetary_quantum

        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            total_buy_consideration = sum(
                (qty * price * mult for qty, price, mult in buy_fills), Decimal("0")
            )
            total_sell_proceeds = sum(
                (qty * price * mult for qty, price, mult in sell_fills), Decimal("0")
            )
            expected_cash = quantize_monetary(
                starting_capital - total_buy_consideration + total_sell_proceeds, monetary_quantum
            )

        if runtime.account_snapshot.cash != expected_cash:
            add_finding(
                finding_type="ACCOUNT_CASH_ARITHMETIC_MISMATCH",
                severity=ReconciliationSeverity.CRITICAL,
                aggregate_type="ACCOUNT",
                aggregate_identity=runtime.account_id,
                expected={"calculated_cash": str(expected_cash)},
                observed={"runtime_cash": str(runtime.account_snapshot.cash)},
                details={"starting_capital": str(starting_capital), "total_buys": str(total_buy_consideration), "total_sells": str(total_sell_proceeds)},
            )

        if persisted.account_state is None:
            add_finding(
                finding_type="MISSING_PERSISTED_ACCOUNT_STATE",
                severity=ReconciliationSeverity.CRITICAL,
                aggregate_type="ACCOUNT",
                aggregate_identity=runtime.account_id,
                expected={"persisted_account_exists": True},
                observed={"persisted_account_exists": False},
            )
        elif persisted.account_state.cash != expected_cash:
            add_finding(
                finding_type="PERSISTED_CASH_ARITHMETIC_MISMATCH",
                severity=ReconciliationSeverity.CRITICAL,
                aggregate_type="ACCOUNT",
                aggregate_identity=runtime.account_id,
                expected={"calculated_cash": str(expected_cash)},
                observed={"persisted_cash": str(persisted.account_state.cash)},
                details={"starting_capital": str(starting_capital), "total_buys": str(total_buy_consideration), "total_sells": str(total_sell_proceeds)},
            )

        # Realized P&L equals sum of closed trade records gross realized P&L
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            expected_realized_pnl = sum(
                (tr.gross_realized_pnl for tr in runtime.completed_trades if tr is not None and hasattr(tr, "gross_realized_pnl")), Decimal("0")
            ).quantize(monetary_quantum, rounding=ROUND_HALF_EVEN)

        if runtime.account_snapshot.realized_pnl != expected_realized_pnl:
            add_finding(
                finding_type="ACCOUNT_REALIZED_PNL_MISMATCH",
                severity=ReconciliationSeverity.CRITICAL,
                aggregate_type="ACCOUNT",
                aggregate_identity=runtime.account_id,
                expected={"trades_realized_pnl": str(expected_realized_pnl)},
                observed={"account_realized_pnl": str(runtime.account_snapshot.realized_pnl)},
            )

        # --------------------------------------------------------------
        # 6. Premium Commitment Reconciliation
        # --------------------------------------------------------------
        queued_opening_orders: dict[str, BrokerOrderRecord] = {}
        for o in persisted.broker_orders:
            if o.lifecycle_state == OrderLifecycleState.QUEUED and getattr(o.original_order, "action", "") == "BUY":
                intent_key = entry_intent_identity(
                    strategy_id=o.original_order.strategy_id,
                    strategy_version=o.original_order.strategy_version,
                    identity=o.instrument_identity,
                    timeframe=o.original_order.timeframe,
                    originating_timestamp=o.original_order.originating_timestamp,
                )
                queued_opening_orders[intent_key] = o
        active_commitments_by_key = {c.reservation_key: c for c in runtime.active_commitments}

        # Every active commitment must have a matching QUEUED opening BUY order
        for res_key, comm in active_commitments_by_key.items():
            order = queued_opening_orders.get(res_key)
            if order is None:
                add_finding(
                    finding_type="ORPHAN_PREMIUM_COMMITMENT",
                    severity=ReconciliationSeverity.CRITICAL,
                    aggregate_type="PREMIUM_COMMITMENT",
                    aggregate_identity=res_key,
                    expected={"queued_opening_order_exists": True},
                    observed={"queued_opening_order_exists": False},
                )
            else:
                with localcontext(INTERNAL_DECIMAL_CONTEXT):
                    expected_req_cash = quantize_monetary(
                        comm.approved_quantity * comm.worst_permitted_fill_price * comm.contract_multiplier,
                        monetary_quantum,
                    )
                if comm.required_cash != expected_req_cash:
                    add_finding(
                        finding_type="PREMIUM_COMMITMENT_REQUIRED_CASH_MISMATCH",
                        severity=ReconciliationSeverity.CRITICAL,
                        aggregate_type="PREMIUM_COMMITMENT",
                        aggregate_identity=res_key,
                        expected={"calculated_required_cash": str(expected_req_cash)},
                        observed={"stored_required_cash": str(comm.required_cash)},
                    )

        # Every terminal opening order must NOT have an active commitment
        for p_order in persisted.broker_orders:
            if getattr(p_order.original_order, "action", "") == "BUY" and p_order.lifecycle_state != OrderLifecycleState.QUEUED:
                term_intent_key = entry_intent_identity(
                    strategy_id=p_order.original_order.strategy_id,
                    strategy_version=p_order.original_order.strategy_version,
                    identity=p_order.instrument_identity,
                    timeframe=p_order.original_order.timeframe,
                    originating_timestamp=p_order.original_order.originating_timestamp,
                )
                if term_intent_key in active_commitments_by_key:
                    add_finding(
                        finding_type="TERMINAL_ORDER_SURVIVING_COMMITMENT",
                        severity=ReconciliationSeverity.CRITICAL,
                        aggregate_type="PREMIUM_COMMITMENT",
                        aggregate_identity=term_intent_key,
                        expected={"commitment_active": False},
                        observed={"commitment_active": True, "lifecycle": p_order.lifecycle_state.value},
                    )

        # --------------------------------------------------------------
        # 7. Risk Commitment Consistency
        # --------------------------------------------------------------
        for prc in runtime.pending_risk_commitments:
            # Active pending risk commitment must correspond to an active queued opening order
            order = queued_opening_orders.get(prc.entry_identity)
            if order is None:
                add_finding(
                    finding_type="ORPHAN_PENDING_RISK_COMMITMENT",
                    severity=ReconciliationSeverity.CRITICAL,
                    aggregate_type="RISK_COMMITMENT",
                    aggregate_identity=prc.entry_identity,
                    expected={"queued_opening_order_exists": True},
                    observed={"queued_opening_order_exists": False},
                )

        # --------------------------------------------------------------
        # 8. Protective Exit & Pending Close Reconciliation
        # --------------------------------------------------------------
        queued_closing_orders = {
            o.order_id: o
            for o in persisted.broker_orders
            if o.lifecycle_state == OrderLifecycleState.QUEUED and o.original_order.action == "SELL"
        }

        # Active protective exits must match held positions
        for exit_item in runtime.protective_exits:
            if exit_item.state == ProtectiveExitState.ACTIVE:
                held_pos = runtime.positions.get(exit_item.position_key)
                if held_pos is None:
                    add_finding(
                        finding_type="ORPHAN_ACTIVE_PROTECTIVE_EXIT",
                        severity=ReconciliationSeverity.CRITICAL,
                        aggregate_type="PROTECTIVE_EXIT",
                        aggregate_identity=exit_item.protective_id,
                        expected={"position_held": True, "position_key": str(exit_item.position_key)},
                        observed={"position_held": False},
                    )
                elif exit_item.quantity > held_pos.quantity:
                    add_finding(
                        finding_type="PROTECTIVE_QUANTITY_EXCEEDS_HELD",
                        severity=ReconciliationSeverity.CRITICAL,
                        aggregate_type="PROTECTIVE_EXIT",
                        aggregate_identity=exit_item.protective_id,
                        expected={"max_quantity": str(held_pos.quantity)},
                        observed={"protective_quantity": str(exit_item.quantity)},
                    )

        # In-flight protective pending closes must match queued broker close orders
        for pclose in runtime.protective_pending_closes:
            b_order = queued_closing_orders.get(pclose.order_id)
            if b_order is None:
                add_finding(
                    finding_type="ORPHAN_PROTECTIVE_PENDING_CLOSE",
                    severity=ReconciliationSeverity.CRITICAL,
                    aggregate_type="PROTECTIVE_PENDING_CLOSE",
                    aggregate_identity=pclose.protective_id,
                    expected={"queued_closing_order_exists": True, "order_id": pclose.order_id},
                    observed={"queued_closing_order_exists": False},
                )

        # --------------------------------------------------------------
        # 9. Trade Ledger Reconciliation
        # --------------------------------------------------------------
        trade_ids: set[str] = set()
        for tr in runtime.completed_trades:
            if tr.trade_id in trade_ids:
                add_finding(
                    finding_type="DUPLICATE_TRADE_ID",
                    severity=ReconciliationSeverity.CRITICAL,
                    aggregate_type="TRADE_RECORD",
                    aggregate_identity=tr.trade_id,
                    expected={"unique_trade_id": True},
                    observed={"duplicate_trade_id": True},
                )
            trade_ids.add(tr.trade_id)

            if not tr.entry_legs or not tr.exit_legs:
                add_finding(
                    finding_type="TRADE_RECORD_MISSING_LEGS",
                    severity=ReconciliationSeverity.CRITICAL,
                    aggregate_type="TRADE_RECORD",
                    aggregate_identity=tr.trade_id,
                    expected={"entry_legs_present": True, "exit_legs_present": True},
                    observed={"entry_legs_count": len(tr.entry_legs), "exit_legs_count": len(tr.exit_legs)},
                )
            else:
                with localcontext(INTERNAL_DECIMAL_CONTEXT):
                    sum_entry_qty = sum((leg.execution_quantity for leg in tr.entry_legs), Decimal("0"))
                    sum_exit_qty = sum((leg.execution_quantity for leg in tr.exit_legs), Decimal("0"))
                    sum_gross_pnl = sum((leg.realized_pnl_delta for leg in tr.exit_legs), Decimal("0")).quantize(
                        tr.monetary_quantum, rounding=ROUND_HALF_EVEN
                    )

                if tr.entry_quantity != sum_entry_qty or tr.exit_quantity != sum_exit_qty or sum_entry_qty != sum_exit_qty:
                    add_finding(
                        finding_type="TRADE_RECORD_QUANTITY_INVARIANT_MISMATCH",
                        severity=ReconciliationSeverity.CRITICAL,
                        aggregate_type="TRADE_RECORD",
                        aggregate_identity=tr.trade_id,
                        expected={"entry_qty": str(tr.entry_quantity), "exit_qty": str(tr.exit_quantity)},
                        observed={"sum_entry_legs": str(sum_entry_qty), "sum_exit_legs": str(sum_exit_qty)},
                    )

                if tr.gross_realized_pnl != sum_gross_pnl:
                    add_finding(
                        finding_type="TRADE_RECORD_GROSS_PNL_MISMATCH",
                        severity=ReconciliationSeverity.CRITICAL,
                        aggregate_type="TRADE_RECORD",
                        aggregate_identity=tr.trade_id,
                        expected={"calculated_gross_pnl": str(sum_gross_pnl)},
                        observed={"stored_gross_pnl": str(tr.gross_realized_pnl)},
                    )

                if tr.opened_at > tr.closed_at:
                    add_finding(
                        finding_type="TRADE_RECORD_TIMESTAMP_INVERSION",
                        severity=ReconciliationSeverity.CRITICAL,
                        aggregate_type="TRADE_RECORD",
                        aggregate_identity=tr.trade_id,
                        expected={"opened_at_lte_closed_at": True},
                        observed={"opened_at": tr.opened_at.isoformat(), "closed_at": tr.closed_at.isoformat()},
                    )

        # --------------------------------------------------------------
        # 10. Cost Assessment Reconciliation
        # --------------------------------------------------------------
        for ca in runtime.cost_assessments:
            expected_fp = trade_evidence_fingerprint(ca.trade_record)
            if ca.trade_evidence_fingerprint != expected_fp:
                add_finding(
                    finding_type="COST_ASSESSMENT_FINGERPRINT_MISMATCH",
                    severity=ReconciliationSeverity.CRITICAL,
                    aggregate_type="COST_ASSESSMENT",
                    aggregate_identity=ca.assessment_id,
                    expected={"trade_evidence_fingerprint": expected_fp},
                    observed={"stored_fingerprint": ca.trade_evidence_fingerprint},
                )

            with localcontext(INTERNAL_DECIMAL_CONTEXT):
                sum_components = sum((c.amount for c in ca.component_results), Decimal("0")).quantize(
                    ca.trade_record.monetary_quantum, rounding=ROUND_HALF_EVEN
                )
                expected_net_pnl = ca.gross_realized_pnl - ca.total_cost

            if ca.total_cost != sum_components:
                add_finding(
                    finding_type="COST_ASSESSMENT_TOTAL_MISMATCH",
                    severity=ReconciliationSeverity.CRITICAL,
                    aggregate_type="COST_ASSESSMENT",
                    aggregate_identity=ca.assessment_id,
                    expected={"sum_components": str(sum_components)},
                    observed={"stored_total_cost": str(ca.total_cost)},
                )

            if ca.net_realized_pnl != expected_net_pnl:
                add_finding(
                    finding_type="COST_ASSESSMENT_NET_PNL_MISMATCH",
                    severity=ReconciliationSeverity.CRITICAL,
                    aggregate_type="COST_ASSESSMENT",
                    aggregate_identity=ca.assessment_id,
                    expected={"calculated_net_pnl": str(expected_net_pnl)},
                    observed={"stored_net_pnl": str(ca.net_realized_pnl)},
                )

        # --------------------------------------------------------------
        # 11. Compute Overall Report Status & Counts
        # --------------------------------------------------------------
        critical_count = sum(1 for f in findings if f.severity == ReconciliationSeverity.CRITICAL)
        warning_count = sum(1 for f in findings if f.severity == ReconciliationSeverity.WARNING)
        info_count = sum(1 for f in findings if f.severity == ReconciliationSeverity.INFO)

        if critical_count > 0:
            status = ReconciliationStatus.MISMATCH
        else:
            status = ReconciliationStatus.MATCHED

        return ReconciliationReport(
            report_id=report_id,
            account_id=runtime.account_id,
            paper_session_id=runtime.paper_session_id,
            checked_state_generation=runtime.state_generation,
            status=status,
            findings=tuple(findings),
            critical_count=critical_count,
            warning_count=warning_count,
            info_count=info_count,
            evaluated_at_market_time=runtime.market_timestamp,
            evaluated_at_utc=evaluated_at_utc,
            is_restart_hydration=runtime.is_restart_hydration,
        )
