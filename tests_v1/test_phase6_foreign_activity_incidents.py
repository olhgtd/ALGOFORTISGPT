from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from engine.broker_adapters.contracts import (
    BrokerAdapterOrderSnapshot,
    BrokerAdapterOrderStatus,
    BrokerFundsSnapshot,
    BrokerPositionSnapshot,
)
from engine.live.phase6_readonly_coordinator import Phase6ReadonlyCoordinator
from engine.paper.contracts_v2 import FailureSeverity
from engine.reconciliation.live_reconciler import LiveBrokerReconciler

NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)


def _order(broker="B1"):
    return BrokerAdapterOrderSnapshot(
        f"FOREIGN:{broker}", broker, BrokerAdapterOrderStatus.ACCEPTED,
        Decimal("1"), Decimal("0"), 0, 0, NOW,
    )


def _position():
    return BrokerPositionSnapshot("26000", "NIFTY", Decimal("1"), Decimal("100"), "INTRADAY", NOW)


def _funds():
    return BrokerFundsSnapshot(Decimal("100"), Decimal("0"), Decimal("100"), NOW)


class Adapter:
    broker_name = "ANGELONE"

    def __init__(self, *, orders=(), positions=(), fail=False):
        self.orders = orders
        self.positions = positions
        self.fail = fail

    def query_funds(self):
        if self.fail:
            raise RuntimeError("secret-token broker unavailable")
        return _funds()

    def query_open_orders(self):
        if self.fail:
            raise RuntimeError("secret-token broker unavailable")
        return tuple(self.orders)

    def query_order(self, _order_id):
        return None

    def query_positions(self):
        if self.fail:
            raise RuntimeError("secret-token broker unavailable")
        return tuple(self.positions)


class Recorder:
    def __init__(self):
        self.by_id = {}

    def record_once(self, incident):
        if incident.incident_id in self.by_id:
            return False
        self.by_id[incident.incident_id] = incident
        return True


class Alerts:
    def __init__(self):
        self.envelopes = []

    def dispatch_critical(self, envelope):
        self.envelopes.append(envelope)
        return ("delivered",)


class Halt:
    def __init__(self):
        self.calls = []

    def halt_new_entries(self, *, reason, incident_id):
        self.calls.append((reason, incident_id))


def _coordinator(adapter):
    recorder = Recorder()
    alerts = Alerts()
    halt = Halt()
    coordinator = Phase6ReadonlyCoordinator(
        reconciler=LiveBrokerReconciler(adapter, "user"),
        incident_sink=recorder,
        alerts=alerts,
        halt_port=halt,
        now=lambda: NOW,
    )
    return coordinator, recorder, alerts, halt


def test_foreign_order_reuses_shared_incident_and_alert_pipeline() -> None:
    coordinator, recorder, alerts, halt = _coordinator(Adapter(orders=(_order(),)))
    result = coordinator.observe_and_reconcile(session_ref="s1")
    incident = result.incidents[0]
    assert incident.failure_type == "FOREIGN_BROKER_ORDER"
    assert incident.severity is FailureSeverity.CRITICAL
    assert incident.halt_latched is True
    assert result.new_entry_eligible is False
    assert len(alerts.envelopes) == 1
    assert alerts.envelopes[0].incident_id == incident.incident_id
    assert len(halt.calls) == 1


def test_foreign_position_uses_same_shared_incident_model() -> None:
    coordinator, recorder, alerts, halt = _coordinator(Adapter(positions=(_position(),)))
    result = coordinator.observe_and_reconcile(session_ref="s1")
    assert any(i.failure_type == "FOREIGN_BROKER_POSITION" for i in result.incidents)
    assert all(type(i).__module__ == "engine.paper.contracts_v2" for i in result.incidents)
    assert result.new_entry_eligible is False


def test_broker_truth_uncertainty_fails_closed_without_leaking_error_text() -> None:
    coordinator, recorder, alerts, halt = _coordinator(Adapter(fail=True))
    result = coordinator.observe_and_reconcile(session_ref="s1")
    assert any(i.failure_type == "BROKER_TRUTH_UNAVAILABLE" for i in result.incidents)
    assert result.new_entry_eligible is False
    rendered = " ".join(e.safe_detail for e in alerts.envelopes)
    assert "secret-token" not in rendered


def test_repeated_identical_unresolved_observation_is_bounded_and_idempotent() -> None:
    coordinator, recorder, alerts, halt = _coordinator(Adapter(orders=(_order(),)))
    first = coordinator.observe_and_reconcile(session_ref="s1")
    second = coordinator.observe_and_reconcile(session_ref="s1")
    assert first.incidents[0].incident_id == second.incidents[0].incident_id
    assert len(recorder.by_id) == 1
    assert len(alerts.envelopes) == 1
    assert len(halt.calls) == 1


def test_clean_reconciliation_does_not_grant_entry_or_arm_authority() -> None:
    coordinator, recorder, alerts, halt = _coordinator(Adapter())
    result = coordinator.observe_and_reconcile(session_ref="s1")
    assert result.report.is_clean is True
    assert result.incidents == ()
    assert result.new_entry_eligible is False
    assert not hasattr(result, "arm")
    assert not hasattr(result, "approved_order")
