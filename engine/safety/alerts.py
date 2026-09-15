"""Phase 8 Slice 3 — safety-alert routing and deterministic local sinks (ADR §128.13/§128.14).

SCOPE
-----
LOCAL/MOCK ONLY.  This module implements the broker/provider-independent
``SafetyAlert`` routing contract plus deterministic local sinks.  It contains
NO network transport of any kind: no chat-app/SMS/email delivery, no external
callback-URL posting, no low-level transport library usage, no credentials,
no tokens.  Real external transports remain deferred behind a separate
owner-authorized integration step (§128.13); the historical frozen
chat/SMS/email requirements are preserved unchanged elsewhere and are NOT
rewritten here.

AUTHORITY RULE (§128.14)
------------------------
Alerts are OBSERVATIONAL evidence.  They never own, clear, or mutate safety
latches.  Any alert associated with a safety halt records a HUMAN-REVIEW
requirement through an injected registrar (wired to the Phase-8 safety
controller's unified manual-review gate) — never through the alert itself.

DETERMINISM (§128.12/OD-9): sinks are invoked in registration order, arrival
order is preserved, duplicate ``alert_id`` deliveries are suppressed
idempotently, and identical inputs produce identical observable results.  All
free-text fields pass through the established Phase-6 redaction boundary.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

from engine.audit.sinks import redact_text
from engine.safety.safety import SafetyAlert

logger = logging.getLogger(__name__)

__all__ = [
    "ALERT_SEVERITY_VOCABULARY",
    "AlertRouteOutcome",
    "AlertRouter",
    "InMemoryAlertSink",
    "SafetyAlertSink",
    "build_redacted_alert",
    "emit_safety_alert",
    "validate_severity",
]


ALERT_SEVERITY_VOCABULARY = ("INFO", "WARNING", "CRITICAL", "FATAL")

_MAX_TEXT_LEN = 512
_MAX_CONTEXT_ENTRIES = 32

# Context keys whose values must be fully masked regardless of content
# (mirrors the established Phase-6 credential-pair denylist).
_SENSITIVE_KEY_TOKENS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "cookie",
    "credential",
)


def _mask_context_value(key: str, value: Any) -> Any:
    key_lower = str(key).lower()
    if any(token in key_lower for token in _SENSITIVE_KEY_TOKENS):
        return "[REDACTED]"
    if isinstance(value, str):
        return redact_text(value, max_len=_MAX_TEXT_LEN)
    return value


def validate_severity(severity: str) -> str:
    """Validate against the frozen severity vocabulary (fail closed)."""
    if not isinstance(severity, str) or severity not in ALERT_SEVERITY_VOCABULARY:
        raise ValueError(
            f"severity must be one of {ALERT_SEVERITY_VOCABULARY}, got {severity!r}"
        )
    return severity


def _require_bounded_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return redact_text(value, max_len=_MAX_TEXT_LEN)


@dataclass(frozen=True)
class AlertRouteOutcome:
    """Immutable per-route result; sink failures never raise upstream."""

    alert_id: str
    delivered_to: tuple[str, ...]
    failed_sinks: tuple[str, ...]
    duplicate_suppressed: bool


@runtime_checkable
class SafetyAlertSink(Protocol):
    """Minimal local sink contract (deterministic, offline)."""

    sink_id: str

    def deliver(self, alert: SafetyAlert) -> bool:
        ...


class InMemoryAlertSink:
    """Deterministic in-order local sink (tests/local operations only)."""

    def __init__(self, *, sink_id: str = "memory") -> None:
        if not isinstance(sink_id, str) or not sink_id.strip():
            raise ValueError("sink_id must be a non-empty string")
        self.sink_id = sink_id
        self.alerts: list[SafetyAlert] = []

    def deliver(self, alert: SafetyAlert) -> bool:
        self.alerts.append(alert)
        return True


class AlertRouter:
    """Deterministic multi-sink dispatcher for local SafetyAlert evidence."""

    def __init__(self, *, router_id: str = "phase8-alert-router") -> None:
        if not isinstance(router_id, str) or not router_id.strip():
            raise ValueError("router_id must be a non-empty string")
        self.router_id = router_id
        self._sinks: list[SafetyAlertSink] = []
        self._sink_ids: set[str] = set()
        self._delivered_alert_ids: set[str] = set()

    def register_sink(self, sink: SafetyAlertSink) -> None:
        if not isinstance(sink, SafetyAlertSink):
            raise TypeError("sink must implement the SafetyAlertSink contract")
        sink_id = getattr(sink, "sink_id", None)
        if not isinstance(sink_id, str) or not sink_id.strip():
            raise ValueError("sink must expose a non-empty sink_id")
        if sink_id in self._sink_ids:
            raise ValueError(f"duplicate sink_id registration: {sink_id!r}")
        self._sink_ids.add(sink_id)
        self._sinks.append(sink)

    @property
    def registered_sink_ids(self) -> tuple[str, ...]:
        return tuple(sink.sink_id for sink in self._sinks)

    def route(self, alert: SafetyAlert) -> AlertRouteOutcome:
        """Deliver ONE alert to every registered sink in registration order.

        Duplicate ``alert_id`` submissions are suppressed idempotently (no
        sink is re-invoked).  A failing sink is recorded as failed and NEVER
        corrupts canonical safety state nor prevents other deliveries.
        """
        if not isinstance(alert, SafetyAlert):
            raise TypeError("alert must be a SafetyAlert")
        if alert.alert_id in self._delivered_alert_ids:
            logger.warning(
                "duplicate safety alert suppressed by router: %s",
                redact_text(alert.alert_id, max_len=120),
            )
            return AlertRouteOutcome(
                alert_id=alert.alert_id,
                delivered_to=(),
                failed_sinks=(),
                duplicate_suppressed=True,
            )
        self._delivered_alert_ids.add(alert.alert_id)
        delivered: list[str] = []
        failed: list[str] = []
        for sink in self._sinks:
            try:
                if sink.deliver(alert):
                    delivered.append(sink.sink_id)
                else:
                    failed.append(sink.sink_id)
            except Exception as exc:  # noqa: BLE001 - sink isolation (§128.13)
                failed.append(sink.sink_id)
                logger.critical(
                    "safety-alert sink %r failed without corrupting safety "
                    "state: %r",
                    sink.sink_id,
                    exc,
                )
        return AlertRouteOutcome(
            alert_id=alert.alert_id,
            delivered_to=tuple(delivered),
            failed_sinks=tuple(failed),
            duplicate_suppressed=False,
        )


def build_redacted_alert(
    *,
    alert_id: str,
    severity: str,
    source: str,
    reason: str,
    timestamp: Any = None,
    context: Mapping[str, Any] | None = None,
) -> SafetyAlert:
    """Build ONE redacted SafetyAlert through the Phase-6 redaction boundary.

    Mandatory redaction applies to source/reason and to every context entry;
    context size is bounded.  Validation fails closed before construction.
    """
    validate_severity(severity)
    safe_id = _require_bounded_text(alert_id, "alert_id")
    safe_source = _require_bounded_text(source, "source")
    safe_reason = _require_bounded_text(reason, "reason")
    redacted_context: dict[str, Any] = {}
    if context is not None:
        for index, (key, value) in enumerate(context.items()):
            if index >= _MAX_CONTEXT_ENTRIES:
                break
            safe_key = redact_text(str(key), max_len=120)
            redacted_context[safe_key] = _mask_context_value(safe_key, value)
    return SafetyAlert(
        alert_id=safe_id,
        severity=severity,
        source=safe_source,
        reason=safe_reason,
        timestamp=timestamp,
        context=redacted_context,
    )


def emit_safety_alert(
    *,
    router: AlertRouter,
    alert: SafetyAlert,
    human_review_registrar: Callable[[tuple[str, ...]], None] | None = None,
    halt_scope: tuple[str, ...] | None = None,
) -> AlertRouteOutcome:
    """Route one alert; record its human-review requirement via the LATCH owner.

    The alert itself carries no authority: the human-review requirement is
    recorded ONLY through the injected registrar (the Phase-8 safety
    controller's unified manual-review gate).  With no registrar wired, this
    is pure observational routing.
    """
    outcome = router.route(alert)
    if halt_scope is not None and human_review_registrar is not None:
        human_review_registrar(halt_scope)
    return outcome
