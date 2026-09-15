"""Narrow Rule 7 audit-record facade.

Phase 6 / ADR §123.3(d): this facade remains the single Rule 7 boundary.
`record(strategy_id, interface_version, exception)` keeps its frozen public
signature and behavior; a durable E21 sink may be registered by the
paper/live runtime and is invoked best-effort from here.

Phase 6 Slice 4 (Q89 / ADR §123.3(d)(4), §126.1): a separate Q89 error-FILE
sink may also be registered (paper/live production runtime only — never
backtest, per §126.1 OD-A). The Q89 file receives EVERY occurrence; the
durable E21 journal keeps first-occurrence-only evidence per the frozen
dedup tuple `(paper_session_id, strategy_id, error_class)`. Each occurrence
carries a `correlation_reference`; it is passed into the first-occurrence
durable payload ONLY when the Q89 file sink verifiably persisted that exact
record (explicit ``True`` persistence evidence) — §123.3(d)(3) requires "a
correlation reference into the error file", so a dangling reference to a
non-existent record is prohibited. No frozen public interface changes.

Durable E21 contracts implemented at the emission boundary:
- Observational only: `state_generation = NULL`, zero business generation.
- Bounded/sanitized payload: exception class token, one-way fingerprint of a
  whitespace-normalized message digest, strategy identity, interface version.
  NO traceback, NO raw message, NO secrets, NO file-system paths.
- Restart-safe dedup per (paper_session_id, strategy_id, error_class) is owned
  by the registered sink (query-before-append against durable audit_events);
  this module stays persistence-agnostic.
- Persistence-failure paradox (§114.12 / §123.3(d)(5)): sink failures are
  logged critically and never raised into the Rule-7 error path.

Q89 error-file records are bounded and redacted through the shared
non-disableable redaction boundary (`engine.audit.sinks`): sanitized
exception-class token, bounded redacted message, frame-limited traceback with
locals excluded, and the sole approved wall-clock source
(`recorded_at_utc_now`, §123.11(4)). A file-sink failure uses one independent
critical fallback and can never recurse or raise into the Rule-7 path.
"""

from __future__ import annotations

import hashlib
import inspect
import logging
import re
import uuid
from typing import Any, Callable, Mapping, Optional

from engine.audit.model import recorded_at_utc_now
from engine.audit.sinks import format_traceback_bounded, redact_text

logger = logging.getLogger(__name__)

# Durable-sink seam: kind is "strategy" | "runtime".
# Sinks may optionally accept a keyword-only ``correlation_reference``;
# legacy four-positional sinks keep working unchanged.
DurableErrorSink = Callable[..., None]

# Q89 error-file seam: callable receiving ONE bounded/redacted record mapping
# and returning explicit persistence evidence — exactly ``True`` when the
# record was durably appended to the error file, any other result (False,
# None, raised exception) is treated as NOT persisted. Registered ONLY by the
# paper/live production runtime (ADR §126.1).
ErrorFileSink = Callable[[Mapping[str, Any]], bool]

_DURABLE_ERROR_SINK: Optional[DurableErrorSink] = None
_DURABLE_ERROR_SINK_SUPPORTS_CORRELATION: bool = False

_ERROR_FILE_SINK: Optional[ErrorFileSink] = None

_ERROR_CLASS_MAX_LEN = 120
_ERROR_CLASS_SANITIZE = re.compile(r"[^A-Za-z0-9_.]")
_MESSAGE_SAMPLE_MAX_LEN = 512


def register_durable_error_sink(sink: Optional[DurableErrorSink]) -> None:
    """Register (or clear with None) the durable E21 emission sink.

    Only the paper/live runtime registers a sink. Backtest execution never
    registers one, so no D16 journal wiring reaches the backtest path
    (§123.4).
    """
    global _DURABLE_ERROR_SINK, _DURABLE_ERROR_SINK_SUPPORTS_CORRELATION
    if sink is not None and not callable(sink):
        raise TypeError("durable error sink must be callable or None")
    _DURABLE_ERROR_SINK = sink
    _DURABLE_ERROR_SINK_SUPPORTS_CORRELATION = sink is not None and _accepts_correlation(sink)


def register_error_file_sink(sink: Optional[ErrorFileSink]) -> None:
    """Register (or clear with None) the Q89 error-FILE sink.

    Phase 6 Slice 4 / ADR §126.1: paper/live production runtime only.
    Backtest execution never registers this sink, so backtest behavior is
    preserved exactly. The Q89 file receives EVERY error occurrence; the
    durable E21 journal remains first-occurrence-only.
    """
    global _ERROR_FILE_SINK
    if sink is not None and not callable(sink):
        raise TypeError("error file sink must be callable or None")
    _ERROR_FILE_SINK = sink


def sanitize_error_class(exception: BaseException) -> str:
    """Deterministic, bounded, charset-restricted exception-class identity."""
    raw = f"{type(exception).__module__}.{type(exception).__qualname__}"
    cleaned = _ERROR_CLASS_SANITIZE.sub("_", raw)[:_ERROR_CLASS_MAX_LEN]
    return cleaned or "UnknownError"


def sanitized_message_fingerprint(exception: BaseException) -> str:
    """One-way SHA256 over a bounded, whitespace-normalized message sample."""
    sample = " ".join(str(exception).split())[:_MESSAGE_SAMPLE_MAX_LEN]
    return hashlib.sha256(sample.encode("utf-8")).hexdigest()


def new_error_correlation_reference() -> str:
    """Return a fresh opaque correlation reference binding Q89 ↔ durable E21."""
    return uuid.uuid4().hex


def build_q89_error_record(
    *,
    kind: str,
    strategy_id,
    interface_version,
    exception: BaseException,
    correlation_reference: str,
) -> dict[str, Any]:
    """Build ONE bounded, redacted Q89 error-file record.

    Bounded/redacted fields only (§123.3(d)(4)): sanitized exception-class
    token, bounded redacted message, frame-limited traceback with locals
    excluded, diagnostic wall-clock via ``recorded_at_utc_now()``. Identity
    enrichment (environment/session/run) is applied by the registering
    runtime closure, which owns that context.
    """
    if kind not in ("strategy", "runtime"):
        raise ValueError(f"unknown error-record kind: {kind!r}")
    return {
        "record_kind": "q89_error",
        "kind": "STRATEGY_EXCEPTION" if kind == "strategy" else "RUNTIME_ERROR",
        "correlation_reference": correlation_reference,
        "strategy_id": strategy_id,
        "interface_version": interface_version,
        "error_class": sanitize_error_class(exception),
        "sanitized_message": redact_text(exception, max_len=1024),
        "traceback_text": format_traceback_bounded(exception),
        "recorded_at_utc": recorded_at_utc_now().isoformat(),
    }


def _accepts_correlation(sink: Callable[..., None]) -> bool:
    """Return True when ``sink`` binds an optional correlation_reference kwarg."""
    try:
        signature = inspect.signature(sink)
        probe = TypeError("probe")
        signature.bind("strategy", None, None, probe, correlation_reference="x")
    except (TypeError, ValueError):
        return False
    return True


def _emit_to_file_sink(record: Mapping[str, Any], error_class_hint: str) -> bool:
    """Best-effort Q89 file emission with one-shot critical fallback.

    Returns explicit persistence evidence for the caller's correlation
    decision: ``True`` ONLY when the registered sink reported a successful
    append; ``False`` on construction/append failure, a dropped record, or
    any other non-True result. Failure semantics (§114.12 / §123.3(d)(5)):
    never raises into the Rule-7 error path, never retries recursively; the
    fallback goes through the independent stdlib logging channel only.
    """
    sink = _ERROR_FILE_SINK
    if sink is None:
        return False
    try:
        result = sink(record)
    except Exception as sink_exc:  # noqa: BLE001 - paradox boundary
        logger.critical(
            "Q89 error-file sink failed without recording; "
            "error_class=%r sink_error=%r",
            error_class_hint,
            sink_exc,
        )
        return False
    if result is not True:
        # The writer/sink internally reported a dropped or unverified record.
        logger.critical(
            "Q89 error-file sink did not confirm persistence; "
            "error_class=%r persisted_evidence=%r",
            error_class_hint,
            result,
        )
        return False
    return True


def record(strategy_id, interface_version, exception) -> None:
    """Record every strategy exception through the current audit facade."""
    # Frozen behavior first: structured application-log line, never raising.
    logger.error(
        "strategy_exception strategy_id=%r interface_version=%r "
        "exception_type=%r exception_message=%r",
        strategy_id,
        interface_version,
        type(exception).__name__,
        str(exception),
    )
    # Phase 6 Slice 4: bounded Q89 error-file row for EVERY occurrence.
    error_class = sanitize_error_class(exception)
    correlation_reference = new_error_correlation_reference()
    q89_persisted = False
    try:
        q89_record = build_q89_error_record(
            kind="strategy",
            strategy_id=strategy_id,
            interface_version=interface_version,
            exception=exception,
            correlation_reference=correlation_reference,
        )
    except Exception as exc:  # noqa: BLE001 - paradox boundary
        logger.critical(
            "Q89 record construction failed; error_class=%r cause=%r", error_class, exc
        )
    else:
        q89_persisted = _emit_to_file_sink(q89_record, error_class)

    # Phase 6 §123.3(d): best-effort durable E21 evidence via the registered
    # sink. Sink failures MUST NOT propagate into the Rule-7 error path and
    # MUST NOT fabricate durable evidence when the journal itself is failing.
    #
    # Correlation discipline: the payload may carry correlation_reference ONLY
    # when this exact occurrence was verifiably persisted to the Q89 error
    # file — a dangling reference into a non-existent record is prohibited.
    sink = _DURABLE_ERROR_SINK
    if sink is None:
        return
    try:
        if _DURABLE_ERROR_SINK_SUPPORTS_CORRELATION and q89_persisted:
            sink("strategy", strategy_id, interface_version, exception,
                 correlation_reference=correlation_reference)
        else:
            # Legacy form (also used when Q89 was not persisted); a
            # correlation-aware sink binds its optional kwarg to None.
            sink("strategy", strategy_id, interface_version, exception)
    except Exception as sink_exc:  # noqa: BLE001 - paradox boundary
        logger.critical(
            "durable ERROR audit sink failed without recording; "
            "error_class=%r sink_error=%r",
            sanitize_error_class(exception),
            sink_exc,
        )


def record_runtime_error(exception: BaseException) -> None:
    """Record a contained non-strategy runtime error through the same seam.

    Same observational/dedup/fail-closed contracts as `record`. Callers keep
    their original fail-closed handling; this function never converts a fatal
    error into success and never raises into the caller's error path beyond
    argument validation.
    """
    if not isinstance(exception, BaseException):
        raise TypeError("exception must be a BaseException instance")
    logger.error(
        "runtime_error exception_type=%r exception_message=%r",
        type(exception).__name__,
        str(exception),
    )
    error_class = sanitize_error_class(exception)
    correlation_reference = new_error_correlation_reference()
    q89_persisted = False
    try:
        q89_record = build_q89_error_record(
            kind="runtime",
            strategy_id=None,
            interface_version=None,
            exception=exception,
            correlation_reference=correlation_reference,
        )
    except Exception as exc:  # noqa: BLE001 - paradox boundary
        logger.critical(
            "Q89 record construction failed; error_class=%r cause=%r", error_class, exc
        )
    else:
        q89_persisted = _emit_to_file_sink(q89_record, error_class)

    sink = _DURABLE_ERROR_SINK
    if sink is None:
        return
    try:
        if _DURABLE_ERROR_SINK_SUPPORTS_CORRELATION and q89_persisted:
            sink("runtime", None, None, exception,
                 correlation_reference=correlation_reference)
        else:
            sink("runtime", None, None, exception)
    except Exception as sink_exc:  # noqa: BLE001 - paradox boundary
        logger.critical(
            "durable ERROR audit sink failed without recording; "
            "error_class=%r sink_error=%r",
            sanitize_error_class(exception),
            sink_exc,
        )
