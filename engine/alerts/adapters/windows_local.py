"""Injected Windows-visible alert adapter for Phase 5.

The concrete OS UI sink is supplied by the composition root. This module does
not import Windows APIs directly, keeping CI deterministic and side-effect free.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from engine.alerts.contracts import AlertDeliveryRecord, AlertEnvelope


class WindowsLocalAlertAdapter:
    channel = "windows_local"

    def __init__(
        self,
        sink: Callable[[str], None],
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not callable(sink):
            raise TypeError("sink must be callable")
        self._sink = sink
        self._now = now or (lambda: datetime.now(timezone.utc))

    def deliver(self, envelope: AlertEnvelope) -> AlertDeliveryRecord:
        if not isinstance(envelope, AlertEnvelope):
            raise TypeError("envelope must be AlertEnvelope")
        attempted_at = self._now()
        message = (
            f"[{envelope.severity.value}] {envelope.incident_type} | "
            f"state={envelope.safety_state.value} | action={envelope.required_action} | "
            f"{envelope.safe_detail}"
        )
        self._sink(message)
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


__all__ = ["WindowsLocalAlertAdapter"]
