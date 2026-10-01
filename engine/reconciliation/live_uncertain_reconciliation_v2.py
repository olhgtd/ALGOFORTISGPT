"""Focused V2 bridge for resolving durable Live IN_DOUBT records from broker truth.

The wrapped LiveBrokerReconciler remains the broker-truth authority. This module
adds no submit/place/cancel path and never treats local persistence as broker
truth.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from engine.broker_adapters.contracts import BrokerAdapterOrderSnapshot, BrokerAdapterOrderStatus
from engine.orders.lifecycle_v2 import OrderExecutionState
from engine.persistence.live_execution_store_v2 import LiveExecutionRecord
from engine.reconciliation.live_reconciler import (
    BrokerTruthUnavailable,
    LiveBrokerReconciler,
    OrderReconciliationAction,
    OrderReconciliationItem,
)


class LiveUncertainOrderReconcilerV2:
    def __init__(self, reconciler: LiveBrokerReconciler) -> None:
        if not isinstance(reconciler, LiveBrokerReconciler):
            raise TypeError("reconciler must be LiveBrokerReconciler")
        self._reconciler = reconciler

    def reconcile(
        self,
        records: Sequence[LiveExecutionRecord],
        *,
        fail_closed: bool = True,
    ) -> tuple[OrderReconciliationItem, ...]:
        if not isinstance(fail_closed, bool):
            raise TypeError("fail_closed must be bool")
        adapter = self._reconciler.broker_adapter
        results: list[OrderReconciliationItem] = []
        for record in records:
            if not isinstance(record, LiveExecutionRecord):
                raise TypeError("records must contain LiveExecutionRecord values")
            if record.lifecycle_state is not OrderExecutionState.IN_DOUBT or record.is_uncertain is not True:
                raise ValueError("uncertain reconciliation requires IN_DOUBT records")
            snapshot = self._lookup(record, fail_closed=fail_closed)
            if snapshot is None:
                results.append(
                    OrderReconciliationItem(
                        order_id=record.client_order_id,
                        broker_order_identity=record.broker_order_identity or "",
                        local_status=BrokerAdapterOrderStatus.UNKNOWN,
                        broker_status=None,
                        action=OrderReconciliationAction.MISSING_AT_BROKER,
                        filled_quantity=Decimal("0"),
                        detail="authoritative client-order lookup returned no broker order",
                    )
                )
                continue
            results.append(self._item(record, snapshot))
        return tuple(results)

    def _lookup(
        self,
        record: LiveExecutionRecord,
        *,
        fail_closed: bool,
    ) -> BrokerAdapterOrderSnapshot | None:
        adapter = self._reconciler.broker_adapter
        client_lookup = getattr(adapter, "query_order_by_client_id", None)
        if callable(client_lookup):
            try:
                return client_lookup(record.client_order_id)
            except NotImplementedError as exc:
                if record.broker_order_identity is None:
                    if fail_closed:
                        raise BrokerTruthUnavailable(
                            "broker cannot prove uncertain order by client-order identity"
                        ) from exc
                # A known broker identity may still be resolved below.
            except Exception as exc:
                if fail_closed:
                    raise BrokerTruthUnavailable(
                        "uncertain client-order broker truth unavailable"
                    ) from exc
                return None
        elif record.broker_order_identity is None:
            if fail_closed:
                raise BrokerTruthUnavailable(
                    "broker cannot prove uncertain order by client-order identity"
                )
            return None

        # If an acknowledgement identity was persisted before uncertainty was
        # discovered, reconcile from the existing broker query surface.
        if record.broker_order_identity is not None:
            try:
                open_orders = adapter.query_open_orders()
            except Exception as exc:
                if fail_closed:
                    raise BrokerTruthUnavailable("uncertain broker order truth unavailable") from exc
                return None
            for snapshot in open_orders:
                if snapshot.broker_order_identity == record.broker_order_identity:
                    return snapshot
            try:
                direct = adapter.query_order(record.client_order_id)
            except Exception as exc:
                if fail_closed:
                    raise BrokerTruthUnavailable("uncertain broker order truth unavailable") from exc
                return None
            if direct is not None:
                return direct

        if fail_closed:
            raise BrokerTruthUnavailable(
                "uncertain order could not be proven absent from broker truth"
            )
        return None

    @staticmethod
    def _item(
        record: LiveExecutionRecord,
        snapshot: BrokerAdapterOrderSnapshot,
    ) -> OrderReconciliationItem:
        status = snapshot.adapter_status
        action = {
            BrokerAdapterOrderStatus.ACCEPTED: OrderReconciliationAction.NO_CHANGE,
            BrokerAdapterOrderStatus.PARTIALLY_FILLED: OrderReconciliationAction.UPDATE_FILLED,
            BrokerAdapterOrderStatus.FILLED: OrderReconciliationAction.UPDATE_FILLED,
            BrokerAdapterOrderStatus.CANCELLED: OrderReconciliationAction.UPDATE_CANCELLED,
            BrokerAdapterOrderStatus.EXPIRED: OrderReconciliationAction.UPDATE_CANCELLED,
            BrokerAdapterOrderStatus.REJECTED: OrderReconciliationAction.UPDATE_REJECTED,
            BrokerAdapterOrderStatus.UNKNOWN: OrderReconciliationAction.STATUS_DIVERGENCE,
        }[status]
        return OrderReconciliationItem(
            order_id=record.client_order_id,
            broker_order_identity=snapshot.broker_order_identity,
            local_status=BrokerAdapterOrderStatus.UNKNOWN,
            broker_status=status,
            action=action,
            filled_quantity=snapshot.cumulative_filled_quantity,
            average_price=getattr(snapshot, "average_fill_price", None),
            detail=f"IN_DOUBT resolved from broker truth: {status.value}",
        )


__all__ = ["LiveUncertainOrderReconcilerV2"]
