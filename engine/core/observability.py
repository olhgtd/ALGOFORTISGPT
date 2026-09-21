"""Structured, correlated and redacted logging primitives for AlgoFortis V2.

This module is intentionally sink-agnostic and contains no concrete dashboard,
filesystem or network dependency. Callers provide a trusted sink accepting one
canonical JSON line. Mandatory redaction happens before the sink is invoked.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import json
import math
import re
from typing import Any, Callable, Iterator, Mapping, Sequence


STRUCTURED_LOG_SCHEMA_VERSION = "algofortis-structured-log/v1"
REDACTED = "[REDACTED]"


class ObservabilityError(ValueError):
    """Raised when structured logging would violate the observability contract."""


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ObservabilityError(f"{field} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class CorrelationContext:
    """Request/run correlation propagated without global mutable state."""

    correlation_id: str
    run_id: str | None = None
    request_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "correlation_id", _text(self.correlation_id, "correlation_id"))
        if self.run_id is not None:
            object.__setattr__(self, "run_id", _text(self.run_id, "run_id"))
        if self.request_id is not None:
            object.__setattr__(self, "request_id", _text(self.request_id, "request_id"))


_CURRENT_CORRELATION: ContextVar[CorrelationContext | None] = ContextVar(
    "algofortis_correlation_context",
    default=None,
)


def current_correlation_context() -> CorrelationContext | None:
    """Return the correlation context bound to the current execution context."""

    return _CURRENT_CORRELATION.get()


@contextmanager
def correlation_scope(context: CorrelationContext) -> Iterator[CorrelationContext]:
    """Bind correlation for this context and restore the previous value on exit."""

    if not isinstance(context, CorrelationContext):
        raise TypeError("context must be a CorrelationContext")
    token = _CURRENT_CORRELATION.set(context)
    try:
        yield context
    finally:
        _CURRENT_CORRELATION.reset(token)


_SECRET_KEY_TOKENS = (
    "api_key",
    "api_secret",
    "secret_key",
    "broker_secret",
    "client_secret",
    "password",
    "passwd",
    "pin",
    "access_token",
    "refresh_token",
    "auth_token",
    "session_token",
    "private_key",
    "private_material",
    "recovery_code",
    "credential_private",
    "device_private",
)

_BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9_.\-~+/]+=*", re.IGNORECASE)
_INLINE_SECRET_RE = re.compile(
    r"\b(api_key|api_secret|secret_key|broker_secret|client_secret|password|passwd|"
    r"access_token|refresh_token|auth_token|session_token)\b"
    r"\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)",
    re.IGNORECASE,
)


def _is_secret_key(key: str) -> bool:
    normalized = key.strip().lower()
    if normalized == "secret_ref" or normalized.endswith("_secret_ref"):
        return False
    return any(token in normalized for token in _SECRET_KEY_TOKENS)


def _redact_string(value: str, secret_values: tuple[str, ...]) -> str:
    clean = value
    for secret in secret_values:
        clean = clean.replace(secret, REDACTED)
    clean = _BEARER_RE.sub("Bearer [REDACTED_TOKEN]", clean)

    def replace_inline(match: re.Match[str]) -> str:
        key = match.group(1)
        return f"{key}={REDACTED}"

    return _INLINE_SECRET_RE.sub(replace_inline, clean)


def _sanitize_value(value: Any, secret_values: tuple[str, ...], *, path: str) -> Any:
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ObservabilityError(f"fields contains non-finite float at {path}")
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ObservabilityError(f"fields contains non-finite Decimal at {path}")
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ObservabilityError(f"fields contains naive datetime at {path}")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        return _redact_string(value, secret_values)
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key in sorted(value, key=lambda item: str(item)):
            if not isinstance(key, str):
                raise ObservabilityError(f"fields mapping keys must be strings at {path}")
            if _is_secret_key(key):
                sanitized[key] = REDACTED
            else:
                sanitized[key] = _sanitize_value(
                    value[key],
                    secret_values,
                    path=f"{path}.{key}",
                )
        return sanitized
    if isinstance(value, (list, tuple)):
        return [
            _sanitize_value(item, secret_values, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    raise ObservabilityError(
        f"fields contains unsupported value type {type(value).__name__} at {path}"
    )


def _normalize_secret_values(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ObservabilityError("secret_values must be a sequence of strings, not one string")
    normalized: list[str] = []
    for value in values:
        secret = _text(value, "secret_values item")
        if secret not in normalized:
            normalized.append(secret)
    # Replace longest values first so overlapping secrets cannot leak suffixes.
    return tuple(sorted(normalized, key=lambda item: (-len(item), item)))


LogSink = Callable[[str], None]


class StructuredLogger:
    """Emit canonical JSON lines after mandatory recursive redaction."""

    def __init__(
        self,
        sink: LogSink,
        *,
        secret_values: Sequence[str] = (),
    ) -> None:
        if not callable(sink):
            raise TypeError("sink must be callable")
        self._sink = sink
        self._secret_values = _normalize_secret_values(secret_values)

    def emit(
        self,
        *,
        level: str,
        event_name: str,
        message: str,
        fields: Mapping[str, Any] | None = None,
        correlation: CorrelationContext | None = None,
    ) -> str:
        level_text = _text(level, "level").upper()
        event_text = _text(event_name, "event_name")
        if not isinstance(message, str):
            raise ObservabilityError("message must be a string")
        if fields is not None and not isinstance(fields, Mapping):
            raise ObservabilityError("fields must be a mapping")
        context = correlation if correlation is not None else current_correlation_context()
        if context is not None and not isinstance(context, CorrelationContext):
            raise TypeError("correlation must be a CorrelationContext or None")

        sanitized_fields = _sanitize_value(
            fields or {},
            self._secret_values,
            path="fields",
        )
        record = {
            "schema_version": STRUCTURED_LOG_SCHEMA_VERSION,
            "level": level_text,
            "event_name": event_text,
            "message": _redact_string(message, self._secret_values),
            "correlation_id": context.correlation_id if context is not None else None,
            "run_id": context.run_id if context is not None else None,
            "request_id": context.request_id if context is not None else None,
            "fields": sanitized_fields,
        }
        try:
            line = json.dumps(
                record,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
        except Exception as exc:
            raise ObservabilityError("structured log serialization failed") from exc

        try:
            self._sink(line)
        except Exception as exc:
            raise ObservabilityError("structured log sink failed") from exc
        return line
