from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from engine.broker_adapters.contracts import (
    BrokerAdapterOrderSnapshot,
    BrokerAdapterOrderStatus,
)
from engine.orders.contracts_v2 import RunMode
from engine.orders.lifecycle_v2 import OrderExecutionState
from engine.persistence.live_execution_store_v2 import LiveExecutionRecord
from engine.reconciliation.live_reconciler import (
    BrokerTruthUnavailable,
    LiveBrokerReconciler,
    OrderReconciliationAction,
)

try:
    from engine.reconciliation.live_uncertain_reconciliation_v2 import LiveUncertainOrderReconcilerV2
except ModuleNotFoundError as exc:  # RED until Task-4 implementation exists
    pytest.fail(f"focused Live uncertain reconciliation wrapper is not implemented: {exc}", pytrace=False)


class _Adapter:
    broker_name = "FAKE"

    def __init__(self, snapshot: BrokerAdapterOrderSnapshot | None, *, fail: bool = False, client_lookup: bool = True) -> None:
        self.snapshot = snapshot
        self.fail = fail
        self.client_lookup = client_lookup
        self.place_calls = 0
        self.submit_calls = 0

    def query_funds(self):
        return None

    def query_positions(self):
        return ()

    def query_open_orders(self):
        if self.fail:
            raise OSError("broker unavailable")
        if self.snapshot is None or self.snapshot.adapter_status.is_terminal:
            return ()
        return (self.snapshot,)

    def query_order(self, order_id: str):
        if self.fail:
            raise OSError("broker unavailable")
        if self.snapshot is not None and self.snapshot.order_id == order_id:
            return self.snapshot
        return None

    def query_order_by_client_id(self, client_order_id: str):
        if not self.client_lookup:
            raise NotImplementedError("client lookup unsupported")
        if self.fail:
            raise OSError("broker unavailable")
        if self.snapshot is not None and self.snapshot.order_id == client_order_id:
            return self.snapshot
        return None

    def place(self, *args, **kwargs):
        self.place_calls += 1
        raise AssertionError("reconciliation must never place")

    def submit(self, *args, **kwargs):
        self.submit_calls += 1
        raise AssertionError("reconciliation must never submit")


def _record(*, broker_order_identity: str | None = None) -> LiveExecutionRecord:
    now = datetime(2026, 9, 30, 9, 16, tzinfo=timezone.utc)
    return LiveExecutionRecord(
        client_order_id="af2_co_uncertain",
        approved_order_ref="a" * 64,
        run_mode=RunMode.LIVE,
        lifecycle_state=OrderExecutionState.IN_DOUBT,
        broker_order_identity=broker_order_identity,
        submission_attempt_id="attempt-1",
        created_at_utc=now,
        updated_at_utc=now,
        is_uncertain=True,
        adapter_id="fake",
        policy_ref="policy-1",
        audit_ref=None,
    )


def _snapshot(status: BrokerAdapterOrderStatus, *, filled: str = "0") -> BrokerAdapterOrderSnapshot:
    filled_qty = Decimal(filled)
    return BrokerAdapterOrderSnapshot(
        order_id="af2_co_uncertain",
        broker_order_identity="broker-1",
        adapter_status=status,
        ordered_quantity=Decimal("2"),
        cumulative_filled_quantity=filled_qty,
        fragment_count=(1 if filled_qty > 0 else 0),
        last_observation_sequence=1,
        last_observed_at=datetime(2026, 9, 30, 9, 17, tzinfo=timezone.utc),
    )


def _service(adapter: _Adapter) -> LiveUncertainOrderReconcilerV2:
    return LiveUncertainOrderReconcilerV2(
        LiveBrokerReconciler(adapter, user_id="user-1", broker_id="FAKE")
    )


@pytest.mark.parametrize(
    ("status", "filled", "action"),
    [
        (BrokerAdapterOrderStatus.PARTIALLY_FILLED, "1", OrderReconciliationAction.UPDATE_FILLED),
        (BrokerAdapterOrderStatus.FILLED, "2", OrderReconciliationAction.UPDATE_FILLED),
        (BrokerAdapterOrderStatus.CANCELLED, "0", OrderReconciliationAction.UPDATE_CANCELLED),
        (BrokerAdapterOrderStatus.REJECTED, "0", OrderReconciliationAction.UPDATE_REJECTED),
    ],
)
def test_uncertain_order_resolves_only_from_explicit_client_identity_broker_truth(status, filled, action) -> None:
    adapter = _Adapter(_snapshot(status, filled=filled))

    result = _service(adapter).reconcile((_record(),), fail_closed=True)

    assert len(result) == 1
    assert result[0].order_id == "af2_co_uncertain"
    assert result[0].broker_order_identity == "broker-1"
    assert result[0].broker_status is status
    assert result[0].action is action
    assert adapter.place_calls == 0
    assert adapter.submit_calls == 0


def test_missing_client_identity_lookup_does_not_assume_not_found() -> None:
    adapter = _Adapter(None, client_lookup=False)

    with pytest.raises(BrokerTruthUnavailable, match="client-order identity"):
        _service(adapter).reconcile((_record(),), fail_closed=True)
    assert adapter.place_calls == 0
    assert adapter.submit_calls == 0


def test_broker_query_failure_keeps_uncertain_order_fail_closed() -> None:
    adapter = _Adapter(None, fail=True)

    with pytest.raises(BrokerTruthUnavailable):
        _service(adapter).reconcile((_record(),), fail_closed=True)
    assert adapter.place_calls == 0
    assert adapter.submit_calls == 0
