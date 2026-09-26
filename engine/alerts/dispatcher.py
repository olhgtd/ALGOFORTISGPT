"""Independent fan-out dispatcher for Phase-5 critical alerts."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone

from engine.alerts.contracts import AlertAdapter, AlertDeliveryRecord, AlertEnvelope
from engine.paper.contracts_v2 import FailureSeverity


class AlertDispatcher:
    def __init__(
        self,
        adapters: Iterable[AlertAdapter],
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._adapters = tuple(adapters)
        if not self._adapters:
            raise ValueError("at least one alert adapter is required")
        self._now = now or (lambda: datetime.now(timezone.utc))

    def dispatch_critical(self, envelope: AlertEnvelope) -> tuple[AlertDeliveryRecord, ...]:
        if not isinstance(envelope, AlertEnvelope):
            raise TypeError("envelope must be AlertEnvelope")
        if envelope.severity not in {
            FailureSeverity.CRITICAL,
            FailureSeverity.RECOVERY_REQUIRED,
        }:
            raise ValueError("dispatch_critical requires CRITICAL or RECOVERY_REQUIRED severity")

        records: list[AlertDeliveryRecord] = []
        for adapter in self._adapters:
            attempted_at = self._now()
            try:
                record = adapter.deliver(envelope)
            except Exception as error:  # adapter isolation is intentional
                completed_at = self._now()
                channel = getattr(adapter, "channel", adapter.__class__.__name__)
                records.append(
                    AlertDeliveryRecord(
                        alert_id=envelope.alert_id,
                        incident_id=envelope.incident_id,
                        channel=str(channel),
                        attempt=1,
                        delivery_status="FAILED",
                        failure_reason=f"{error.__class__.__name__}: {error}",
                        attempted_at=attempted_at,
                        completed_at=completed_at,
                    )
                )
                continue
            if not isinstance(record, AlertDeliveryRecord):
                raise TypeError("alert adapter must return AlertDeliveryRecord")
            records.append(record)
        return tuple(records)


__all__ = ["AlertDispatcher"]
