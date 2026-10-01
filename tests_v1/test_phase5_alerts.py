from __future__ import annotations

from datetime import datetime, timezone

from engine.alerts.contracts import AlertDeliveryRecord, AlertEnvelope
from engine.alerts.dispatcher import AlertDispatcher
from engine.alerts.redaction import redact_alert_payload
from engine.paper.contracts_v2 import FailureSeverity, PaperOperationalState

NOW = datetime(2026, 9, 26, 5, 55, tzinfo=timezone.utc)


def _alert() -> AlertEnvelope:
    return AlertEnvelope(
        alert_id="alert-p5-08",
        incident_id="incident-p5-08",
        severity=FailureSeverity.CRITICAL,
        incident_type="CLOCK_UNHEALTHY",
        session_ref="session-p5",
        occurred_at=NOW,
        safety_state=PaperOperationalState.HALTED,
        required_action="MANUAL_REVIEW",
        safe_detail="Clock health policy rejected entry eligibility",
    )


class RecordingAdapter:
    def __init__(self, channel: str, *, fail: bool = False) -> None:
        self.channel = channel
        self.fail = fail
        self.calls = 0

    def deliver(self, envelope: AlertEnvelope) -> AlertDeliveryRecord:
        self.calls += 1
        if self.fail:
            raise RuntimeError(f"{self.channel} unavailable")
        return AlertDeliveryRecord(
            alert_id=envelope.alert_id,
            incident_id=envelope.incident_id,
            channel=self.channel,
            attempt=1,
            delivery_status="DELIVERED",
            failure_reason=None,
            attempted_at=NOW,
            completed_at=NOW,
        )


def test_windows_failure_does_not_suppress_telegram_attempt():
    windows = RecordingAdapter("windows_local", fail=True)
    telegram = RecordingAdapter("telegram")
    dispatcher = AlertDispatcher((windows, telegram), now=lambda: NOW)

    records = dispatcher.dispatch_critical(_alert())

    assert windows.calls == 1
    assert telegram.calls == 1
    assert [record.channel for record in records] == ["windows_local", "telegram"]
    assert records[0].delivery_status == "FAILED"
    assert records[1].delivery_status == "DELIVERED"


def test_telegram_failure_does_not_suppress_local_attempt():
    windows = RecordingAdapter("windows_local")
    telegram = RecordingAdapter("telegram", fail=True)
    dispatcher = AlertDispatcher((windows, telegram), now=lambda: NOW)

    records = dispatcher.dispatch_critical(_alert())

    assert windows.calls == 1
    assert telegram.calls == 1
    assert records[0].delivery_status == "DELIVERED"
    assert records[1].delivery_status == "FAILED"


def test_adapter_exception_becomes_auditable_failed_delivery_record():
    adapter = RecordingAdapter("telegram", fail=True)
    dispatcher = AlertDispatcher((adapter,), now=lambda: NOW)

    records = dispatcher.dispatch_critical(_alert())

    assert len(records) == 1
    record = records[0]
    assert record.delivery_status == "FAILED"
    assert record.failure_reason == "RuntimeError: telegram unavailable"
    assert record.attempted_at == NOW
    assert record.completed_at == NOW


def test_alert_redaction_removes_secrets_raw_account_ids_and_unrestricted_trade_logs():
    safe = redact_alert_payload(
        {
            "token": "secret-token",
            "api_key": "secret-key",
            "account_id": "raw-account-123",
            "broker_account": "raw-broker-456",
            "trade_log": "BUY NIFTY with unrestricted internals",
            "detail": "clock unhealthy",
            "nested": {
                "authorization": "Bearer private",
                "safe_reason": "policy drift exceeded",
            },
        }
    )

    rendered = repr(safe)
    assert "secret-token" not in rendered
    assert "secret-key" not in rendered
    assert "raw-account-123" not in rendered
    assert "raw-broker-456" not in rendered
    assert "BUY NIFTY" not in rendered
    assert "Bearer private" not in rendered
    assert safe["detail"] == "clock unhealthy"
    assert safe["nested"]["safe_reason"] == "policy drift exceeded"


def test_dispatch_preserves_latched_safety_state_and_cannot_resume_or_arm():
    alert = _alert()
    dispatcher = AlertDispatcher((RecordingAdapter("windows_local"),), now=lambda: NOW)

    records = dispatcher.dispatch_critical(alert)

    assert records[0].delivery_status == "DELIVERED"
    assert alert.safety_state is PaperOperationalState.HALTED
    assert not hasattr(dispatcher, "arm")
    assert not hasattr(dispatcher, "resume")
    assert not hasattr(dispatcher, "place_order")
