"""Injected Telegram alert adapter for Phase 5.

Network transport and credentials are provided by the composition root. This
module deliberately contains no Telegram SDK, token, broker, or live authority.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from engine.alerts.contracts import AlertDeliveryRecord, AlertEnvelope


class TelegramAlertAdapter:
    channel = "telegram"

    def __init__(
        self,
        sender: Callable[[str], None],
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not callable(sender):
            raise TypeError("sender must be callable")
        self._sender = sender
        self._now = now or (lambda: datetime.now(timezone.utc))

    def deliver(self, envelope: AlertEnvelope) -> AlertDeliveryRecord:
        if not isinstance(envelope, AlertEnvelope):
            raise TypeError("envelope must be AlertEnvelope")
        attempted_at = self._now()
        message = (
            f"[{envelope.severity.value}] {envelope.incident_type}\n"
            f"session={envelope.session_ref}\n"
            f"state={envelope.safety_state.value}\n"
            f"action={envelope.required_action}\n"
            f"detail={envelope.safe_detail}"
        )
        self._sender(message)
        completed_at = self._now()
        return AlertDeliveryRecord(
            alert_id=envelope.alert_id,
            incident_id=envelope.incident_id,
            channel=self.channel,
            attempt=1,
            delivery_status="DELIVERED",
            failure_reason=None,
            attempted_at=attempted_at,
            completed_at=completed_at,
        )


__all__ = ["TelegramAlertAdapter"]
