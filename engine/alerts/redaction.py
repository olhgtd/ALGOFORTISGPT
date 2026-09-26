"""Recursive redaction for Phase-5 alert payloads."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_SENSITIVE_KEY_FRAGMENTS = (
    "token",
    "secret",
    "password",
    "authorization",
    "api_key",
    "apikey",
    "account_id",
    "accountid",
    "broker_account",
    "trade_log",
    "raw_trade",
)


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    return any(fragment in normalized for fragment in _SENSITIVE_KEY_FRAGMENTS)


def redact_alert_payload(value: Any) -> Any:
    """Return a structurally similar payload with sensitive fields removed."""
    if isinstance(value, Mapping):
        return {
            key: redact_alert_payload(item)
            for key, item in value.items()
            if not _is_sensitive_key(key)
        }
    if isinstance(value, tuple):
        return tuple(redact_alert_payload(item) for item in value)
    if isinstance(value, list):
        return [redact_alert_payload(item) for item in value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return type(value)(redact_alert_payload(item) for item in value)
    return value


__all__ = ["redact_alert_payload"]
