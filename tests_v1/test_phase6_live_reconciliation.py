from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from engine.broker_adapters.contracts import (
    BrokerAdapterOrderSnapshot,
    BrokerAdapterOrderStatus,
    BrokerFundsSnapshot,
    BrokerPositionSnapshot,
)
from engine.reconciliation.live_reconciler import LiveBrokerReconciler, OrderReconciliationAction

NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)


def _order(local_id="L1", broker_id="B1"):
    return BrokerAdapterOrderSnapshot(
        order_id=local_id,
        broker_order_identity=broker_id,
        adapter_status=BrokerAdapterOrderStatus.ACCEPTED,
        ordered_quantity=Decimal("1"),
        cumulative_filled_quantity=Decimal("0"),
        fragment_count=0,
        last_observation_sequence=0,
        last_observed_at=NOW,
    )


def _position(symbol="NIFTY", qty="1"):
    return BrokerPositionSnapshot("26000", symbol, Decimal(qty), Decimal("100"), "INTRADAY", NOW)


def _funds():
    return BrokerFundsSnapshot(Decimal("100"), Decimal("0"), Decimal("100"), NOW)


class TruthAdapter:
    broker_name = "ANGELONE"

    def __init__(self, *, orders=(), positions=(), funds=None, fail=None):
        self._orders = tuple(orders)
        self._positions = tuple(positions)
        self._funds = funds if funds is not None else _funds()
        self._fail = fail
        self.mutation_calls = 0

    def _maybe(self, area):
        if self._fail == area:
            raise RuntimeError(f"{area} unavailable")

    def query_funds(self):
        self._maybe("funds")
        return self._funds

    def query_open_orders(self):
        self._maybe("orders")
        return self._orders

    def query_order(self, order_id):
        self._maybe("orders")
        return next((o for o in self._orders if o.broker_order_identity == order_id), None)

    def query_positions(self):
        self._maybe("positions")
        return self._positions

    def cancel(self, *args, **kwargs):
        self.mutation_calls += 1
        raise AssertionError("mutation called")

    def submit(self, *args, **kwargs):
        self.mutation_calls += 1
        raise AssertionError("mutation called")


def test_broker_only_order_is_foreign_orphan_verdict() -> None:
    report = LiveBrokerReconciler(
        TruthAdapter(orders=(_order("FOREIGN:B1", "B1"),)), "user"
    ).run_full_reconciliation()
    assert any(item.action is OrderReconciliationAction.ORPHAN_FOUND for item in report.order_items)
    assert report.is_clean is False


def test_broker_only_position_is_foreign_broker_truth() -> None:
    report = LiveBrokerReconciler(
        TruthAdapter(positions=(_position(),)), "user"
    ).run_full_reconciliation(local_positions={})
    assert any(item.action == "BROKER_ONLY_POSITION" for item in report.position_items)
    assert report.is_clean is False


def test_query_failure_is_explicit_uncertainty_not_empty_clean_state() -> None:
    for area in ("funds", "orders", "positions"):
        report = LiveBrokerReconciler(TruthAdapter(fail=area), "user").run_full_reconciliation()
        assert report.is_clean is False
        assert report.errors, area
        assert any(area in error.lower() for error in report.errors)


def test_same_truth_yields_same_verdict_independent_of_adapter_class() -> None:
    class OtherAdapter(TruthAdapter):
        pass

    fixture = dict(orders=(_order(),), positions=(_position(),), funds=_funds())
    a = LiveBrokerReconciler(TruthAdapter(**fixture), "user").run_full_reconciliation(
        local_pending_orders=(_order(),), local_positions={"NIFTY": Decimal("1")}
    )
    b = LiveBrokerReconciler(OtherAdapter(**fixture), "user").run_full_reconciliation(
        local_pending_orders=(_order(),), local_positions={"NIFTY": Decimal("1")}
    )
    assert [(x.action, x.broker_order_identity) for x in a.order_items] == [
        (x.action, x.broker_order_identity) for x in b.order_items
    ]
    assert [(x.action, x.symbol) for x in a.position_items] == [
        (x.action, x.symbol) for x in b.position_items
    ]


def test_reconciler_never_calls_mutation_even_if_fixture_exposes_it() -> None:
    adapter = TruthAdapter(orders=(_order(),), positions=(_position(),))
    LiveBrokerReconciler(adapter, "user").run_full_reconciliation(
        local_pending_orders=(_order(),), local_positions={"NIFTY": Decimal("1")}
    )
    assert adapter.mutation_calls == 0
