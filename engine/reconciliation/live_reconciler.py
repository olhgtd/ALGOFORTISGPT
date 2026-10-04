"""Live Broker Reconciliation & Restart Recovery Engine.

Provides deterministic state synchronization between live broker accounts
and AlgoFortis local persistence upon system startup / recovery.

Features:
1. Broker State Query: Synchronously queries open orders, positions, and funds
   via the active BrokerAdapter.
2. In-Flight Order Settlement: Reconciles non-terminal orders that transitioned to
   FILLED, CANCELLED, or REJECTED at the broker while the engine was offline.
3. Stale & Duplicate Signal Suppression: Uses persisted entry_intent_identity
   and signal timestamps to ensure historical or already-executed entry signals
   are dropped and NEVER double-submitted upon restart.
4. Position & Protection Restoration: Synchronizes net open positions with the
   ProtectiveExitBook so stops/targets manage active broker exposure without
   re-submitting duplicate entries.
5. Strict Isolation & Failure Boundaries: Adapter-level network exceptions or
   broker discrepancies are captured in typed ReconciliationReports without
   crashing the runtime.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from engine.broker_adapters.contracts import (
    BrokerAdapter,
    BrokerAdapterOrderSnapshot,
    BrokerAdapterOrderStatus,
    BrokerFundsSnapshot,
    BrokerPositionSnapshot,
)
from engine.core.numeric import as_decimal
from engine.orchestration.signal_intake import SignalIntent, signal_intent_identity
from engine.protective.runtime import ProtectiveExit, ProtectiveExitBook, ProtectiveExitState
from engine.portfolio.model import PositionKey

logger = logging.getLogger("algofortis.reconciliation.live")


class BrokerTruthUnavailable(RuntimeError):
    """Raised when Phase-6 strict reconciliation cannot prove broker truth."""


class OrderReconciliationAction(str, Enum):
    """Action determined for a reconciled order."""

    NO_CHANGE = "NO_CHANGE"
    UPDATE_FILLED = "UPDATE_FILLED"
    UPDATE_CANCELLED = "UPDATE_CANCELLED"
    UPDATE_REJECTED = "UPDATE_REJECTED"
    ORPHAN_FOUND = "ORPHAN_FOUND"
    MISSING_AT_BROKER = "MISSING_AT_BROKER"
    STATUS_DIVERGENCE = "STATUS_DIVERGENCE"


@dataclass(frozen=True)
class OrderReconciliationItem:
    """Reconciliation outcome for one order."""

    order_id: str
    broker_order_identity: str
    local_status: BrokerAdapterOrderStatus
    broker_status: BrokerAdapterOrderStatus | None
    action: OrderReconciliationAction
    filled_quantity: Decimal
    average_price: Decimal | None = None
    detail: str | None = None


@dataclass(frozen=True)
class PositionReconciliationItem:
    """Reconciliation outcome for one instrument position."""

    symbol: str
    local_quantity: Decimal
    broker_quantity: Decimal
    discrepancy: Decimal
    action: str
    detail: str | None = None


@dataclass(frozen=True)
class LiveReconciliationReport:
    """Complete immutable audit report of a restart reconciliation cycle."""

    user_id: str
    broker_id: str
    reconciled_at_utc: datetime
    funds: BrokerFundsSnapshot | None
    order_items: tuple[OrderReconciliationItem, ...] = ()
    position_items: tuple[PositionReconciliationItem, ...] = ()
    stale_signals_dropped: tuple[str, ...] = ()
    protected_positions_restored: int = 0
    errors: tuple[str, ...] = ()

    @property
    def is_clean(self) -> bool:
        """True only when broker truth is available and no discrepancy/error exists."""
        has_order_discrepancy = any(
            item.action in (
                OrderReconciliationAction.ORPHAN_FOUND,
                OrderReconciliationAction.MISSING_AT_BROKER,
                OrderReconciliationAction.STATUS_DIVERGENCE,
            )
            for item in self.order_items
        )
        has_pos_discrepancy = any(
            item.action != "MATCHED" for item in self.position_items
        )
        return (
            self.funds is not None
            and not has_order_discrepancy
            and not has_pos_discrepancy
            and len(self.errors) == 0
        )


def _to_decimal(val: Any) -> Decimal:
    """Convert value safely to Decimal."""
    if isinstance(val, Decimal):
        return val
    try:
        return Decimal(str(val))
    except Exception:
        return Decimal("0")


def _get_order_status(snap: Any) -> BrokerAdapterOrderStatus:
    """Safely extract BrokerAdapterOrderStatus from snapshot or dict."""
    if hasattr(snap, "adapter_status") and isinstance(snap.adapter_status, BrokerAdapterOrderStatus):
        return snap.adapter_status
    if hasattr(snap, "status"):
        s = snap.status
        if isinstance(s, BrokerAdapterOrderStatus):
            return s
        try:
            return BrokerAdapterOrderStatus(str(s).upper())
        except Exception:
            pass
    return BrokerAdapterOrderStatus.UNKNOWN


class LiveBrokerReconciler:
    """Deterministic Live Broker Reconciler for startup and recovery.

    Enforces:
    - Broker query of open orders, positions, funds via BrokerAdapter.
    - Reconciliation of terminal events during downtime.
    - Stale / duplicate entry drop using persisted entry_intent_identity.
    - ProtectiveExitBook synchronization without duplicate entry submission.
    """

    def __init__(
        self,
        broker_adapter: BrokerAdapter | Any,
        user_id: str,
        broker_id: str = "",
    ) -> None:
        if broker_adapter is None:
            raise ValueError("broker_adapter cannot be None")
        if not hasattr(broker_adapter, "query_funds") or not hasattr(broker_adapter, "query_positions"):
            raise TypeError("broker_adapter must implement BrokerAdapter methods")
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("user_id must be a non-empty string")
        self._adapter = broker_adapter
        self._user_id = user_id
        self._broker_id = broker_id or getattr(broker_adapter, "broker_name", "UNKNOWN")

    @property
    def broker_adapter(self) -> BrokerAdapter:
        return self._adapter

    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def broker_id(self) -> str:
        return self._broker_id

    def reconcile_funds(self, *, fail_closed: bool = False) -> BrokerFundsSnapshot | None:
        """Query live account funds snapshot from the broker adapter."""
        try:
            return self._adapter.query_funds()
        except Exception as ex:
            logger.error("Failed to query live funds for user %s: %s", self._user_id, ex)
            if fail_closed:
                raise BrokerTruthUnavailable("funds broker truth unavailable") from ex
            return None

    def reconcile_orders(
        self,
        local_pending_orders: Sequence[BrokerAdapterOrderSnapshot | dict[str, Any]],
        *,
        fail_closed: bool = False,
    ) -> tuple[OrderReconciliationItem, ...]:
        """Reconcile locally pending/in-flight orders against live broker state."""
        results: list[OrderReconciliationItem] = []
        try:
            broker_open_orders = self._adapter.query_open_orders()
        except Exception as ex:
            logger.error("Failed to query open orders: %s", ex)
            if fail_closed:
                raise BrokerTruthUnavailable("orders broker truth unavailable") from ex
            broker_open_orders = ()

        broker_open_by_id: dict[str, BrokerAdapterOrderSnapshot] = {
            snap.broker_order_identity: snap for snap in broker_open_orders
        }

        seen_broker_order_ids: set[str] = set()

        for raw_order in local_pending_orders:
            if isinstance(raw_order, BrokerAdapterOrderSnapshot):
                order_id = raw_order.order_id
                broker_order_id = raw_order.broker_order_identity
                local_status = raw_order.adapter_status
                local_filled = raw_order.cumulative_filled_quantity
            elif isinstance(raw_order, dict):
                order_id = str(raw_order.get("order_id", ""))
                broker_order_id = str(raw_order.get("broker_order_identity", ""))
                status_raw = raw_order.get("status", raw_order.get("adapter_status", "SUBMITTED"))
                local_status = (
                    status_raw if isinstance(status_raw, BrokerAdapterOrderStatus)
                    else (
                        BrokerAdapterOrderStatus(str(status_raw).upper())
                        if str(status_raw).upper() in BrokerAdapterOrderStatus.__members__
                        else BrokerAdapterOrderStatus.ACCEPTED
                    )
                )
                local_filled = _to_decimal(raw_order.get("cumulative_filled_quantity", 0))
            else:
                continue

            if not broker_order_id:
                results.append(
                    OrderReconciliationItem(
                        order_id=order_id,
                        broker_order_identity="",
                        local_status=local_status,
                        broker_status=None,
                        action=OrderReconciliationAction.MISSING_AT_BROKER,
                        filled_quantity=local_filled,
                        detail="Local order had no broker_order_identity assigned",
                    )
                )
                continue

            seen_broker_order_ids.add(broker_order_id)

            if broker_order_id in broker_open_by_id:
                broker_snap = broker_open_by_id[broker_order_id]
                b_status = _get_order_status(broker_snap)
                avg_px = getattr(broker_snap, "average_fill_price", getattr(broker_snap, "average_price", None))

                if b_status == local_status and broker_snap.cumulative_filled_quantity == local_filled:
                    results.append(
                        OrderReconciliationItem(
                            order_id=order_id,
                            broker_order_identity=broker_order_id,
                            local_status=local_status,
                            broker_status=b_status,
                            action=OrderReconciliationAction.NO_CHANGE,
                            filled_quantity=broker_snap.cumulative_filled_quantity,
                            average_price=avg_px,
                        )
                    )
                else:
                    action = (
                        OrderReconciliationAction.UPDATE_FILLED
                        if broker_snap.cumulative_filled_quantity > local_filled
                        else OrderReconciliationAction.STATUS_DIVERGENCE
                    )
                    results.append(
                        OrderReconciliationItem(
                            order_id=order_id,
                            broker_order_identity=broker_order_id,
                            local_status=local_status,
                            broker_status=b_status,
                            action=action,
                            filled_quantity=broker_snap.cumulative_filled_quantity,
                            average_price=avg_px,
                            detail=f"Open order progressed to {b_status.value}",
                        )
                    )
            else:
                try:
                    term_snap = self._adapter.query_order(broker_order_id)
                except Exception as ex:
                    logger.warning("Could not query individual order %s: %s", broker_order_id, ex)
                    if fail_closed:
                        raise BrokerTruthUnavailable(
                            f"order {broker_order_id} broker truth unavailable"
                        ) from ex
                    term_snap = None

                if term_snap is None:
                    results.append(
                        OrderReconciliationItem(
                            order_id=order_id,
                            broker_order_identity=broker_order_id,
                            local_status=local_status,
                            broker_status=None,
                            action=OrderReconciliationAction.MISSING_AT_BROKER,
                            filled_quantity=local_filled,
                            detail="Order missing from open orders and query returned None",
                        )
                    )
                else:
                    t_status = _get_order_status(term_snap)
                    avg_px = getattr(term_snap, "average_fill_price", getattr(term_snap, "average_price", None))
                    qty = getattr(term_snap, "cumulative_filled_quantity", Decimal("0"))

                    if t_status == BrokerAdapterOrderStatus.FILLED:
                        results.append(
                            OrderReconciliationItem(
                                order_id=order_id,
                                broker_order_identity=broker_order_id,
                                local_status=local_status,
                                broker_status=t_status,
                                action=OrderReconciliationAction.UPDATE_FILLED,
                                filled_quantity=qty,
                                average_price=avg_px,
                                detail="Order filled completely at broker during downtime",
                            )
                        )
                    elif t_status in (BrokerAdapterOrderStatus.CANCELLED, BrokerAdapterOrderStatus.EXPIRED):
                        results.append(
                            OrderReconciliationItem(
                                order_id=order_id,
                                broker_order_identity=broker_order_id,
                                local_status=local_status,
                                broker_status=t_status,
                                action=OrderReconciliationAction.UPDATE_CANCELLED,
                                filled_quantity=qty,
                                average_price=avg_px,
                                detail=f"Order reached {t_status.value} at broker during downtime",
                            )
                        )
                    elif t_status == BrokerAdapterOrderStatus.REJECTED:
                        results.append(
                            OrderReconciliationItem(
                                order_id=order_id,
                                broker_order_identity=broker_order_id,
                                local_status=local_status,
                                broker_status=t_status,
                                action=OrderReconciliationAction.UPDATE_REJECTED,
                                filled_quantity=qty,
                                average_price=avg_px,
                                detail="Order was rejected at broker during downtime",
                            )
                        )
                    else:
                        results.append(
                            OrderReconciliationItem(
                                order_id=order_id,
                                broker_order_identity=broker_order_id,
                                local_status=local_status,
                                broker_status=t_status,
                                action=OrderReconciliationAction.STATUS_DIVERGENCE,
                                filled_quantity=qty,
                                average_price=avg_px,
                                detail=f"Divergent status {t_status.value}",
                            )
                        )

        for b_id, b_snap in broker_open_by_id.items():
            if b_id not in seen_broker_order_ids:
                b_status = _get_order_status(b_snap)
                avg_px = getattr(b_snap, "average_fill_price", getattr(b_snap, "average_price", None))
                results.append(
                    OrderReconciliationItem(
                        order_id="",
                        broker_order_identity=b_id,
                        local_status=BrokerAdapterOrderStatus.UNKNOWN,
                        broker_status=b_status,
                        action=OrderReconciliationAction.ORPHAN_FOUND,
                        filled_quantity=getattr(b_snap, "cumulative_filled_quantity", Decimal("0")),
                        average_price=avg_px,
                        detail="Order exists open at broker but is unknown in local tracking",
                    )
                )

        return tuple(results)

    def reconcile_positions(
        self,
        local_positions: Mapping[str, Decimal | int | float],
        *,
        fail_closed: bool = False,
    ) -> tuple[PositionReconciliationItem, ...]:
        """Reconcile net positions between local state and broker positions."""
        results: list[PositionReconciliationItem] = []
        try:
            broker_positions = self._adapter.query_positions()
        except Exception as ex:
            logger.error("Failed to query live positions: %s", ex)
            if fail_closed:
                raise BrokerTruthUnavailable("positions broker truth unavailable") from ex
            broker_positions = ()

        broker_by_sym: dict[str, Decimal] = {}
        for pos in broker_positions:
            sym = getattr(pos, "trading_symbol", getattr(pos, "symbol", "")).upper().strip()
            qty = getattr(pos, "quantity", getattr(pos, "net_quantity", Decimal("0")))
            if sym:
                broker_by_sym[sym] = broker_by_sym.get(sym, Decimal("0")) + _to_decimal(qty)

        local_by_sym: dict[str, Decimal] = {
            sym.upper().strip(): _to_decimal(qty)
            for sym, qty in local_positions.items()
        }

        all_syms = set(broker_by_sym.keys()).union(local_by_sym.keys())

        for sym in sorted(all_syms):
            b_qty = broker_by_sym.get(sym, Decimal("0"))
            l_qty = local_by_sym.get(sym, Decimal("0"))
            discrepancy = b_qty - l_qty

            if b_qty == l_qty:
                action = "MATCHED"
                detail = "Positions perfectly aligned"
            elif sym not in local_by_sym:
                action = "BROKER_ONLY_POSITION"
                detail = f"Position of {b_qty} exists at broker but missing in local state"
            elif sym not in broker_by_sym:
                action = "LOCAL_ONLY_POSITION"
                detail = f"Local state has {l_qty} but position is 0 at broker"
            else:
                action = "DISCREPANCY_DETECTED"
                detail = f"Discrepancy of {discrepancy} (broker={b_qty}, local={l_qty})"

            results.append(
                PositionReconciliationItem(
                    symbol=sym,
                    local_quantity=l_qty,
                    broker_quantity=b_qty,
                    discrepancy=discrepancy,
                    action=action,
                    detail=detail,
                )
            )

        return tuple(results)

    def filter_stale_or_duplicate_signals(
        self,
        signals: Sequence[SignalIntent],
        persisted_intent_ids: set[str],
        cutoff_timestamp: datetime | None = None,
    ) -> tuple[tuple[SignalIntent, ...], tuple[SignalIntent, ...]]:
        """Filter incoming candidate signals upon restart."""
        valid: list[SignalIntent] = []
        dropped: list[SignalIntent] = []

        for sig in signals:
            try:
                intent_id = signal_intent_identity(sig)
            except Exception:
                intent_id = ""

            if intent_id and intent_id in persisted_intent_ids:
                logger.info("Dropping duplicate entry signal on restart: %s", intent_id)
                dropped.append(sig)
                continue

            if cutoff_timestamp is not None:
                sig_ts = sig.originating_timestamp
                if sig_ts.tzinfo is None:
                    sig_ts = sig_ts.replace(tzinfo=timezone.utc)
                cutoff = cutoff_timestamp
                if cutoff.tzinfo is None:
                    cutoff = cutoff.replace(tzinfo=timezone.utc)

                if sig_ts < cutoff:
                    logger.info(
                        "Dropping stale historical signal from prior session: %s (ts=%s < cutoff=%s)",
                        intent_id, sig_ts, cutoff,
                    )
                    dropped.append(sig)
                    continue

            valid.append(sig)

        return tuple(valid), tuple(dropped)

    def restore_protective_positions(
        self,
        protective_book: ProtectiveExitBook,
        current_broker_positions: Sequence[BrokerPositionSnapshot],
    ) -> int:
        """Synchronize existing ProtectiveExitBook exits with live broker positions."""
        if not isinstance(protective_book, ProtectiveExitBook):
            raise TypeError("protective_book must be a ProtectiveExitBook")

        broker_pos_by_sym = {
            getattr(pos, "trading_symbol", getattr(pos, "symbol", "")).upper().strip(): _to_decimal(
                getattr(pos, "quantity", getattr(pos, "net_quantity", Decimal("0")))
            )
            for pos in current_broker_positions
        }

        maintained_count = 0

        class _EmptySnapshot:
            positions: dict[Any, Any] = {}

        for protective_id, item in tuple(protective_book.exits.items()):
            if item.state != ProtectiveExitState.ACTIVE:
                continue

            ident = item.position_key.identity
            sym = getattr(ident, "instrument", getattr(ident, "symbol", "")).upper().strip()
            broker_qty = broker_pos_by_sym.get(sym, Decimal("0"))

            if broker_qty <= 0:
                logger.info(
                    "Position %s closed at broker; reconciling protective exit %s to CANCELLED",
                    sym, protective_id,
                )
                protective_book.reconcile_position(item.position_key, _EmptySnapshot())
            else:
                maintained_count += 1

        return maintained_count

    def run_full_reconciliation(
        self,
        local_pending_orders: Sequence[BrokerAdapterOrderSnapshot | dict[str, Any]] = (),
        local_positions: Mapping[str, Decimal | int | float] | None = None,
        persisted_intent_ids: set[str] | None = None,
        candidate_signals: Sequence[SignalIntent] = (),
        cutoff_timestamp: datetime | None = None,
        protective_book: ProtectiveExitBook | None = None,
    ) -> LiveReconciliationReport:
        """Run complete synchronous restart reconciliation across funds, orders, and positions.

        Phase-6 uses strict broker-truth queries here: a failed broker query is
        explicit uncertainty in the report and can never become an empty-clean
        state. Direct helper methods keep their legacy non-strict default for
        backward compatibility.
        """
        errors: list[str] = []
        now = datetime.now(timezone.utc)

        funds = None
        try:
            funds = self.reconcile_funds(fail_closed=True)
        except Exception as ex:
            errors.append(f"Funds query failed: {ex}")

        order_items: tuple[OrderReconciliationItem, ...] = ()
        try:
            order_items = self.reconcile_orders(local_pending_orders, fail_closed=True)
        except Exception as ex:
            errors.append(f"Orders reconciliation failed: {ex}")

        position_items: tuple[PositionReconciliationItem, ...] = ()
        try:
            position_items = self.reconcile_positions(local_positions or {}, fail_closed=True)
        except Exception as ex:
            errors.append(f"Positions reconciliation failed: {ex}")

        dropped_ids: list[str] = []
        if candidate_signals:
            try:
                _, dropped = self.filter_stale_or_duplicate_signals(
                    candidate_signals,
                    persisted_intent_ids or set(),
                    cutoff_timestamp,
                )
                dropped_ids = [signal_intent_identity(s) for s in dropped]
            except Exception as ex:
                errors.append(f"Signal deduplication failed: {ex}")

        restored_count = 0
        if protective_book is not None:
            try:
                broker_positions = self._adapter.query_positions()
                restored_count = self.restore_protective_positions(protective_book, broker_positions)
            except Exception as ex:
                errors.append(f"Protective exits restoration failed: {ex}")

        return LiveReconciliationReport(
            user_id=self._user_id,
            broker_id=self._broker_id,
            reconciled_at_utc=now,
            funds=funds,
            order_items=order_items,
            position_items=position_items,
            stale_signals_dropped=tuple(dropped_ids),
            protected_positions_restored=restored_count,
            errors=tuple(errors),
        )
