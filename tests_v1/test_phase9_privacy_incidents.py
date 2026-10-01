from datetime import datetime, timezone

import pytest

from engine.paper.contracts_v2 import FailureIncident
from dashboard.backend.product_ops_v2.privacy_incidents import PrivacyIncidentBridge

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


class Dispatcher:
    def __init__(self):
        self.calls = []

    def dispatch(self, incident, message):
        self.calls.append((incident, message))
        return ("alert-local", "alert-telegram")


class Store:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.ids = set()
        self.saved = []

    def save_incident(self, incident):
        if self.fail:
            raise RuntimeError("incident store unavailable")
        if incident.incident_id in self.ids:
            raise RuntimeError("duplicate incident")
        self.ids.add(incident.incident_id)
        self.saved.append(incident)


def test_bridge_reuses_failure_incident_store_before_existing_dispatcher():
    dispatcher = Dispatcher()
    store = Store()
    incident = PrivacyIncidentBridge(dispatcher, incident_store=store).raise_incident(
        "privacy-1",
        affected_classes=("ACCOUNT_IDENTITY", "CONSENT_EVIDENCE"),
        detected_at=NOW,
        audit_ref="audit-1",
    )
    assert isinstance(incident, FailureIncident)
    assert store.saved == [incident]
    assert dispatcher.calls and dispatcher.calls[0][0] is incident


def test_sensitive_scope_and_store_failure_never_dispatch_alert():
    dispatcher = Dispatcher()
    bridge = PrivacyIncidentBridge(dispatcher, incident_store=Store())
    with pytest.raises(ValueError, match="sensitive incident payload rejected"):
        bridge.raise_incident(
            "privacy-2",
            affected_classes=("ACCOUNT_NUMBER",),
            detected_at=NOW,
            audit_ref="audit-2",
        )
    assert dispatcher.calls == []

    dispatcher2 = Dispatcher()
    with pytest.raises(RuntimeError, match="incident store unavailable"):
        PrivacyIncidentBridge(dispatcher2, incident_store=Store(fail=True)).raise_incident(
            "privacy-3",
            affected_classes=("ACCOUNT_IDENTITY",),
            detected_at=NOW,
            audit_ref="audit-3",
        )
    assert dispatcher2.calls == []


def test_duplicate_incident_id_uses_existing_store_idempotency_boundary():
    dispatcher = Dispatcher()
    store = Store()
    bridge = PrivacyIncidentBridge(dispatcher, incident_store=store)
    bridge.raise_incident("privacy-4", affected_classes=("ACCOUNT_IDENTITY",), detected_at=NOW, audit_ref="audit-4")
    with pytest.raises(RuntimeError, match="duplicate incident"):
        bridge.raise_incident("privacy-4", affected_classes=("ACCOUNT_IDENTITY",), detected_at=NOW, audit_ref="audit-4b")
    assert len(dispatcher.calls) == 1
