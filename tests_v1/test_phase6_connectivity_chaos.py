from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from engine.broker_adapters.contracts import BrokerFundsSnapshot
from engine.broker_adapters.angelone_v2.contracts import (
    AngelOneBrokerProfile,
    AngelOneCredentialRef,
)
from engine.broker_adapters.angelone_v2.rate_policy import BrokerRateClass, evaluate_rate
from engine.broker_adapters.angelone_v2.session import (
    AngelOneSessionAuthority,
    AngelOneSessionUnavailable,
)
from engine.live.phase6_readonly_coordinator import Phase6ReadonlyCoordinator
from engine.live.state_machine_v2 import LiveState, LiveStateMachine
from engine.reconciliation.live_reconciler import LiveBrokerReconciler

NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.value = NOW

    def now(self):
        return self.value


class AuthTransport:
    def __init__(self, refresh_fail=False):
        self.refresh_fail = refresh_fail

    def authenticate(self, **_kwargs):
        return {
            "access_token": "a",
            "refresh_token": "r",
            "expires_at": NOW + timedelta(minutes=1),
            "daily_valid_until": NOW + timedelta(hours=8),
        }

    def refresh(self, **_kwargs):
        if self.refresh_fail:
            raise RuntimeError("refresh failed")
        return {
            "access_token": "b",
            "refresh_token": "rr",
            "expires_at": NOW + timedelta(minutes=2),
            "daily_valid_until": NOW + timedelta(hours=8),
        }


class Adapter:
    broker_name = "ANGELONE"

    def __init__(self):
        self.fail = True

    def query_funds(self):
        if self.fail:
            raise RuntimeError("disconnect")
        return BrokerFundsSnapshot(Decimal("1"), Decimal("0"), Decimal("1"), NOW)

    def query_open_orders(self):
        if self.fail:
            raise RuntimeError("disconnect")
        return ()

    def query_order(self, _order_id):
        return None

    def query_positions(self):
        if self.fail:
            raise RuntimeError("disconnect")
        return ()


class Recorder:
    def __init__(self):
        self.ids = set()

    def record_once(self, incident):
        if incident.incident_id in self.ids:
            return False
        self.ids.add(incident.incident_id)
        return True


class Alerts:
    def dispatch_critical(self, envelope):
        return (envelope.incident_id,)


class Halt:
    def halt_new_entries(self, **_kwargs):
        return None


class Audit:
    def __init__(self):
        self.events = []

    def write(self, *args):
        self.events.append(args)


def _coordinator(adapter):
    return Phase6ReadonlyCoordinator(
        reconciler=LiveBrokerReconciler(adapter, "user"),
        incident_sink=Recorder(),
        alerts=Alerts(),
        halt_port=Halt(),
        now=lambda: NOW,
    )


def test_disconnect_then_reconnect_never_restores_entry_permission() -> None:
    adapter = Adapter()
    coordinator = _coordinator(adapter)
    down = coordinator.observe_and_reconcile(session_ref="s1")
    assert down.new_entry_eligible is False
    assert any(i.failure_type == "BROKER_TRUTH_UNAVAILABLE" for i in down.incidents)

    adapter.fail = False
    up = coordinator.observe_and_reconcile(session_ref="s1")
    assert up.report.is_clean is True
    assert up.new_entry_eligible is False


def test_token_expiry_and_refresh_failure_stay_observation_unavailable() -> None:
    profile = AngelOneBrokerProfile(
        "P", "v1", "https://apiconnect.angelone.in", "docs"
    )
    clock = Clock()
    session = AngelOneSessionAuthority(
        profile=profile,
        credential_ref=AngelOneCredentialRef("secret://x", "acct"),
        transport=AuthTransport(refresh_fail=True),
        clock=clock,
    )
    session.authenticate()
    clock.value = NOW + timedelta(minutes=2)
    assert session.health().observation_available is False
    with pytest.raises(AngelOneSessionUnavailable):
        session.refresh()
    assert session.health().observation_available is False


def test_missing_rate_policy_fails_closed_without_unbounded_retry() -> None:
    decision = evaluate_rate(None, BrokerRateClass.READ_ORDERS, observed_requests=0)
    assert decision.allowed is False
    assert decision.retry_unbounded is False


def test_restart_from_active_restores_only_to_recovery() -> None:
    audit = Audit()
    restored = LiveStateMachine.restore_after_restart(
        previous_state=LiveState.ACTIVE,
        audit_sink=audit,
    )
    assert restored.state is LiveState.RECOVERY
    assert audit.events
    assert audit.events[0][1]["arm_enabled"] is False
