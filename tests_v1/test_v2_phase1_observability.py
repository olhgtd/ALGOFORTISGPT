"""Phase 1 RED tests for structured logging, correlation and mandatory redaction."""

from __future__ import annotations

import json

import pytest

from engine.core.observability import (
    CorrelationContext,
    ObservabilityError,
    StructuredLogger,
    correlation_scope,
    current_correlation_context,
)


def test_correlation_context_propagates_and_resets() -> None:
    assert current_correlation_context() is None
    context = CorrelationContext(
        correlation_id="corr-0001",
        run_id="run-0001",
        request_id="req-0001",
    )

    with correlation_scope(context):
        assert current_correlation_context() == context

    assert current_correlation_context() is None


def test_structured_record_contains_correlation_and_is_deterministic() -> None:
    first_lines: list[str] = []
    second_lines: list[str] = []
    context = CorrelationContext(
        correlation_id="corr-0002",
        run_id="run-0002",
        request_id="req-0002",
    )

    with correlation_scope(context):
        StructuredLogger(first_lines.append).emit(
            level="INFO",
            event_name="strategy.evaluated",
            message="evaluation complete",
            fields={"symbol": "NIFTY", "decision": "HOLD"},
        )
        StructuredLogger(second_lines.append).emit(
            level="INFO",
            event_name="strategy.evaluated",
            message="evaluation complete",
            fields={"decision": "HOLD", "symbol": "NIFTY"},
        )

    assert first_lines == second_lines
    record = json.loads(first_lines[0])
    assert record["schema_version"] == "algofortis-structured-log/v1"
    assert record["correlation_id"] == "corr-0002"
    assert record["run_id"] == "run-0002"
    assert record["request_id"] == "req-0002"
    assert record["fields"] == {"decision": "HOLD", "symbol": "NIFTY"}


def test_secret_keys_and_registered_secret_values_never_reach_emitted_text() -> None:
    lines: list[str] = []
    secret = "SUPER-SECRET-123"
    logger = StructuredLogger(lines.append, secret_values=(secret,))

    logger.emit(
        level="ERROR",
        event_name="broker.connection_failed",
        message=f"connection rejected for token {secret}",
        fields={
            "api_secret": secret,
            "password": "hunter2",
            "nested": {
                "access_token": "token-abc",
                "safe": f"value contains {secret}",
            },
        },
    )

    emitted = lines[0]
    assert secret not in emitted
    assert "hunter2" not in emitted
    assert "token-abc" not in emitted
    record = json.loads(emitted)
    assert record["fields"]["api_secret"] == "[REDACTED]"
    assert record["fields"]["password"] == "[REDACTED]"
    assert record["fields"]["nested"]["access_token"] == "[REDACTED]"
    assert record["fields"]["nested"]["safe"] == "value contains [REDACTED]"
    assert record["message"] == "connection rejected for token [REDACTED]"


def test_bearer_tokens_and_inline_secret_assignments_are_redacted() -> None:
    lines: list[str] = []
    logger = StructuredLogger(lines.append)
    logger.emit(
        level="WARN",
        event_name="support.sanitized",
        message='Bearer abc.DEF-123 password="plain-text" api_key="key-value"',
    )

    emitted = lines[0]
    assert "abc.DEF-123" not in emitted
    assert "plain-text" not in emitted
    assert "key-value" not in emitted
    assert "[REDACTED" in emitted


def test_invalid_context_and_fields_fail_closed() -> None:
    with pytest.raises(ObservabilityError, match="correlation_id"):
        CorrelationContext(correlation_id="", run_id="run", request_id="req")

    logger = StructuredLogger(lambda _line: None)
    with pytest.raises(ObservabilityError, match="fields"):
        logger.emit(
            level="INFO",
            event_name="bad.fields",
            message="bad",
            fields={1: "non-string-key"},
        )


def test_sink_failure_is_not_silently_swallowed() -> None:
    def broken_sink(_line: str) -> None:
        raise OSError("disk unavailable")

    logger = StructuredLogger(broken_sink)
    with pytest.raises(ObservabilityError, match="sink"):
        logger.emit(
            level="ERROR",
            event_name="critical.failure",
            message="must surface",
        )
