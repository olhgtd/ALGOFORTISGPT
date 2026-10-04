"""Phase 6 Slice 4 — shared structured file-sink infrastructure (Q88/Q89/Q90).

Scope (ADR §123.6, §126.2):
- strict ``config/logging_config.yaml`` loading/validation,
- ONE mandatory non-disableable redaction boundary shared by every sink,
- deterministic compact JSONL serialization (UTF-8, sorted keys),
- NON-DELETING size-based segment rollover (rotated evidence is never
  pruned — OD-B), Windows-safe, single-process/single-writer,
- generic sink writers used by the narrow production seams.

This module is deliberately dependency-free (stdlib only) and carries zero
trading/accounting semantics. Nothing written here is ever read back as a
trading, accounting or audit authority (§123.2, §123.5, §123.7).
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path, PurePath
from typing import Any, Iterator, Mapping

logger = logging.getLogger(__name__)

SUPPORTED_LOGGING_SCHEMA_VERSION = "algofortis-logging-config/v1"

_MAX_SEGMENT_BYTES_MIN = 1024
_MAX_SEGMENT_BYTES_MAX = 1024 * 1024 * 1024
_VALID_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
_SINK_NAMES = ("trade_log", "error_log", "strategy_log", "audit_export")
_ROTATABLE_SINKS = ("trade_log", "error_log", "strategy_log")
_RETENTION_POLICY_NEVER_AUTO_DELETE = "never_auto_delete"

_REDACTED_PLACEHOLDER = "[REDACTED]"

# Defense-in-depth key denylist (mirrors engine.reporting.serializer plus
# credential/header extensions). Whitelisted structured fields are used for
# every record; these keys are never emitted through mapping projection.
FORBIDDEN_RECORD_KEYS = frozenset(
    {
        "path", "filepath", "file_path", "username", "hostname", "host",
        "credential", "credentials", "api_key", "apikey", "token",
        "password", "passwd", "secret", "cookie", "cookies", "set_cookie",
        "authorization", "proxy_authorization", "session_id_cookie",
        "exception", "error", "message", "traceback", "stack", "stacktrace",
        "environment", "env", "operational_context",
    }
)

_SECRET_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Authorization / Proxy-Authorization headers incl. Bearer scheme.
    re.compile(r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?[^\s,;\"']+", ),
    re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9\-._~+/]+=*"),
    re.compile(r"(?i)(proxy-authorization\s*[:=]\s*)[^\s,;\"']+"),
    # Credential-style key=value / key: value pairs.
    re.compile(
        r"(?i)\b(access[_\-]?token|api[_\-]?key|apikey|api[_\-]?secret|"
        r"password|passwd|pwd|secret|client[_\-]?secret|credential|"
        r"credentials|auth[_\-]?token|session[_\-]?token|refresh[_\-]?token)"
        r"(\s*[=:]\s*)(?:[\"']?)[^\s,;\"']+(?:[\"']?)"
    ),
    re.compile(r"(?i)(set-cookie\s*[:=]\s*)[^\r\n]+"),
    re.compile(r"(?i)(cookie\s*[:=]\s*)[^\r\n]+"),
    # Secret-bearing URL query parameters.
    re.compile(
        r"(?i)([?&]"
        r"(?:token|access_token|api_key|apikey|password|secret|signature|"
        r"sig|credential|code|client_secret|session_token)="
        r")[^&\s\"']+"
    ),
)

# Exact registered secret values are replaced wherever they appear.
_REGISTERED_SECRET_VALUES: set[str] = set()


def register_secret_value(value: str) -> None:
    """Register one exact secret value for non-disableable redaction."""
    if isinstance(value, str) and value.strip():
        _REGISTERED_SECRET_VALUES.add(value.strip())


def clear_registered_secret_values() -> None:
    """Clear all registered exact secret values (test/runtime teardown)."""
    _REGISTERED_SECRET_VALUES.clear()


def redact_text(value: Any, *, max_len: int = 4096) -> str:
    """Return a bounded, whitespace-normalized, redacted diagnostic string.

    Mandatory on every free-text field of every sink. Never disableable.
    """
    try:
        text = " ".join(str(value).split())
    except Exception:  # noqa: BLE001 - diagnostics boundary
        return "<unrepresentable>"
    for secret in _REGISTERED_SECRET_VALUES:
        if secret:
            text = text.replace(secret, _REDACTED_PLACEHOLDER)
    for pattern in _SECRET_VALUE_PATTERNS:
        text = pattern.sub(_secret_pattern_repl, text)
    if len(text) > max_len:
        text = text[:max_len]
    return text


def _secret_pattern_repl(match: re.Match[str]) -> str:
    # Every capture group in _SECRET_VALUE_PATTERNS is prefix material
    # (keys/separators/scheme words); the secret value itself is always the
    # un-captured remainder of the match.
    prefix = "".join(group for group in match.groups() if group is not None)
    return f"{prefix}{_REDACTED_PLACEHOLDER}"


def format_traceback_bounded(exc: BaseException, *, max_frames: int = 20, max_chars: int = 8192) -> str:
    """Render a frame-limited traceback with locals excluded and redaction applied.

    Standard library traceback formatting never renders frame locals; the
    rendered text is additionally passed through the shared redactor so no
    secret embedded in source lines/messages survives.
    """
    try:
        lines = traceback_format_exception(exc, limit=max_frames)
    except Exception:  # noqa: BLE001 - diagnostics boundary
        return "<traceback unavailable>"
    text = "".join(lines)
    text = redact_text(text, max_len=max_chars)
    return text


def traceback_format_exception(exc: BaseException, *, limit: int) -> list[str]:
    """Small indirection over ``traceback.format_exception`` (py>=3.10 form)."""
    import traceback

    return traceback.format_exception(exc, limit=limit)


def jsonable(value: Any) -> Any:
    """Deterministically project one value into JSON-serializable primitives.

    Decimals serialize canonically as strings; timestamps as ISO-8601;
    unknown objects degrade to their bounded string form. Mapping keys are
    stringified and checked against the forbidden-key denylist.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value if isinstance(value.value, (str, int, float)) else str(value.value)
    if isinstance(value, PurePath):
        return value.as_posix()
    if isinstance(value, Mapping):
        projected: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            if key.lower() in FORBIDDEN_RECORD_KEYS:
                raise ValueError(f"forbidden record key: {key!r}")
            projected[key] = jsonable(item)
        return projected
    if isinstance(value, (list, tuple, set, frozenset)):
        return [jsonable(item) for item in value]
    return redact_text(value, max_len=512)


def jsonl_line(record: Mapping[str, Any]) -> bytes:
    """Serialize ONE record as a deterministic compact UTF-8 JSONL line."""
    projected = jsonable(dict(record))
    text = json.dumps(projected, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def segment_glob_parts(base_name: str) -> tuple[str, str]:
    """Return (current_filename, rotated_prefix) for a sink base name."""
    return f"{base_name}.jsonl", f"{base_name}."


class NonDeletingJsonlWriter:
    """Append-only JSONL writer with NON-deleting size-based segment rollover.

    Layout (per ADR §126.2 OD-B — rotation bounds individual files, history
    is NEVER deleted/pruned):

        <base_name>.jsonl          current active segment (append target)
        <base_name>.000001.jsonl   first rolled segment
        <base_name>.000002.jsonl   second rolled segment
        ...

    - rolls BEFORE exceeding ``max_segment_bytes`` (record-granular),
    - restart discovers the next safe sequence and never overwrites an
      existing historical segment,
    - Windows-safe: the current handle is closed before rename and reopened,
    - single-process/single-writer assumption only (the durable SQLite
      journal remains the multi-writer-safe authority),
    - a crash-truncated final line stays diagnostic-only.
    """

    def __init__(self, directory: Path | str, base_name: str, *, max_segment_bytes: int) -> None:
        if not isinstance(max_segment_bytes, int) or isinstance(max_segment_bytes, bool):
            raise TypeError("max_segment_bytes must be an int")
        if not (_MAX_SEGMENT_BYTES_MIN <= max_segment_bytes <= _MAX_SEGMENT_BYTES_MAX):
            raise ValueError(f"max_segment_bytes out of supported range: {max_segment_bytes!r}")
        if not re.fullmatch(r"[A-Za-z0-9._-]+", base_name or ""):
            raise ValueError(f"unsafe sink base name: {base_name!r}")
        self._directory = Path(directory)
        self._base_name = base_name
        self._max_segment_bytes = max_segment_bytes
        self._directory.mkdir(parents=True, exist_ok=True)
        current_name, _ = segment_glob_parts(base_name)
        self._current_path = self._directory / current_name
        self._handle = None
        self._current_size = 0
        self._open_current()

    # -- public API -----------------------------------------------------

    @property
    def directory(self) -> Path:
        return self._directory

    @property
    def base_name(self) -> str:
        return self._base_name

    @property
    def current_path(self) -> Path:
        return self._current_path

    @property
    def max_segment_bytes(self) -> int:
        return self._max_segment_bytes

    def write_record(self, record: Mapping[str, Any]) -> bool:
        """Append one record; returns False (with critical diagnostic) when dropped."""
        try:
            line = jsonl_line(record)
        except Exception as exc:  # noqa: BLE001 - sink boundary
            logger.critical("Q-sink record serialization failed; record dropped; cause=%r", exc)
            return False
        if len(line) > self._max_segment_bytes:
            logger.critical(
                "Q-sink record exceeds configured segment capacity; record dropped; "
                "base_name=%r line_bytes=%d max_segment_bytes=%d",
                self._base_name, len(line), self._max_segment_bytes,
            )
            return False
        try:
            if self._current_size > 0 and self._current_size + len(line) > self._max_segment_bytes:
                self._roll()
            self._ensure_open()
            self._handle.write(line)
            self._handle.flush()
            self._current_size += len(line)
            return True
        except Exception as exc:  # noqa: BLE001 - sink failure semantics
            logger.critical(
                "Q-sink append failed; trading state unaffected; "
                "base_name=%r cause=%r", self._base_name, exc,
            )
            return False

    def flush(self) -> None:
        if self._handle is not None:
            self._handle.flush()
            os.fsync(self._handle.fileno())

    def close(self) -> None:
        if self._handle is not None:
            try:
                self._handle.flush()
                os.fsync(self._handle.fileno())
            finally:
                self._handle.close()
                self._handle = None

    def __enter__(self) -> "NonDeletingJsonlWriter":
        return self

    def __exit__(self, *_exc_info: Any) -> None:
        self.close()

    # -- internals ------------------------------------------------------

    def _open_current(self) -> None:
        existed = self._current_path.exists()
        self._handle = open(self._current_path, "ab")
        self._current_size = self._current_path.stat().st_size if existed else 0

    def _ensure_open(self) -> None:
        if self._handle is None:
            self._open_current()

    def _next_sequence(self) -> int:
        _, rotated_prefix = segment_glob_parts(self._base_name)
        highest = 0
        if self._directory.exists():
            for entry in self._directory.iterdir():
                name = entry.name
                if not name.startswith(rotated_prefix) or not name.endswith(".jsonl"):
                    continue
                middle = name[len(rotated_prefix):-len(".jsonl")]
                if not re.fullmatch(r"\d{6}", middle):
                    continue
                highest = max(highest, int(middle))
        return highest + 1

    def _roll(self) -> None:
        if self._handle is None and self._current_size == 0:
            return
        self.close()
        if self._current_size == 0:
            self._open_current()
            return
        seq = self._next_sequence()
        while True:
            target = self._directory / f"{self._base_name}.{seq:06d}.jsonl"
            if not target.exists():
                break
            seq += 1  # never overwrite an existing historical segment
        os.replace(self._current_path, target)
        self._current_size = 0
        self._open_current()


def read_jsonl_records(directory: Path | str, base_name: str) -> tuple[list[dict[str, Any]], int]:
    """Read every parseable record across ordered segments + current file.

    Order: rolled segments ascending by sequence, then the current segment.
    Malformed lines are skipped (diagnostic-only tail policy) and counted;
    they never mutate any financial/accounting state.
    """
    directory = Path(directory)
    current_name, rotated_prefix = segment_glob_parts(base_name)
    paths: list[Path] = []
    if directory.exists():
        rotated: list[tuple[int, Path]] = []
        for entry in directory.iterdir():
            name = entry.name
            if name == current_name:
                continue
            if name.startswith(rotated_prefix) and name.endswith(".jsonl"):
                middle = name[len(rotated_prefix):-len(".jsonl")]
                if re.fullmatch(r"\d{6}", middle):
                    rotated.append((int(middle), entry))
        paths.extend(path for _seq, path in sorted(rotated))
        current = directory / current_name
        if current.exists():
            paths.append(current)

    records: list[dict[str, Any]] = []
    malformed = 0
    for path in paths:
        try:
            raw = path.read_bytes()
        except OSError:
            malformed += 1
            continue
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                malformed += 1
                continue
            if isinstance(obj, dict):
                records.append(obj)
            else:
                malformed += 1
    return records, malformed


@dataclass(frozen=True)
class LoggingConfig:
    """Validated Phase-6 logging configuration (ADR §123.6 / §126.2)."""

    schema_version: str
    sinks: Mapping[str, Path | None]
    levels: Mapping[str, str] = field(default_factory=dict)
    rotation: Mapping[str, int] = field(default_factory=dict)
    retention_policy: str = _RETENTION_POLICY_NEVER_AUTO_DELETE


def _reject_trading_semantic_keys(keys: Iterator[str]) -> None:
    forbidden_fragments = (
        "strategy_binding", "risk_", "position_sizing", "order_",
        "execution_policy", "cost_profile", "account", "capital",
        "instrument", "signal_", "protective", "broker",
    )
    for key in keys:
        lowered = str(key).lower()
        for fragment in forbidden_fragments:
            if fragment in lowered:
                raise LoggingConfigError(
                    f"trading-semantic configuration key is not permitted in logging config: {key!r}"
                )


class LoggingConfigError(ValueError):
    """Raised when config/logging_config.yaml violates the §123.6 contract."""


def load_logging_config(path: Path | str) -> LoggingConfig:
    """Load and strictly validate the logging configuration. Fail-closed."""
    import yaml

    config_path = Path(path)
    if not config_path.exists() or not config_path.is_file():
        raise LoggingConfigError(f"logging config file does not exist: {config_path}")
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - fail-closed config boundary
        raise LoggingConfigError(f"logging config is not valid YAML: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise LoggingConfigError("logging config root must be a mapping")

    allowed_top = {"schema_version", "sinks", "levels", "rotation", "retention"}
    _reject_trading_semantic_keys(raw.keys())
    unknown = sorted(set(raw.keys()) - allowed_top)
    if unknown:
        raise LoggingConfigError(f"unknown logging config keys: {unknown!r}")

    version = raw.get("schema_version")
    if version != SUPPORTED_LOGGING_SCHEMA_VERSION:
        raise LoggingConfigError(
            f"unsupported logging config schema_version: {version!r} "
            f"(expected {SUPPORTED_LOGGING_SCHEMA_VERSION!r})"
        )

    sinks_raw = raw.get("sinks", {})
    if not isinstance(sinks_raw, Mapping):
        raise LoggingConfigError("sinks must be a mapping")
    _reject_trading_semantic_keys(sinks_raw.keys())
    unknown_sinks = sorted(set(sinks_raw.keys()) - set(_SINK_NAMES))
    if unknown_sinks:
        raise LoggingConfigError(f"unknown sink names: {unknown_sinks!r}")
    sinks: dict[str, Path | None] = {}
    for name in _SINK_NAMES:
        value = sinks_raw.get(name)
        if value is None:
            sinks[name] = None
            continue
        if not isinstance(value, str) or not value.strip():
            raise LoggingConfigError(f"sink {name!r} destination must be a non-empty string or null")
        if name == "audit_export":
            raise LoggingConfigError(
                "audit_export tooling is not built; destination must remain null (§123.5)"
            )
        sinks[name] = Path(value)

    levels_raw = raw.get("levels", {})
    if not isinstance(levels_raw, Mapping):
        raise LoggingConfigError("levels must be a mapping")
    _reject_trading_semantic_keys(levels_raw.keys())
    levels: dict[str, str] = {}
    for logger_name, level in levels_raw.items():
        if not isinstance(logger_name, str) or not logger_name.strip():
            raise LoggingConfigError("levels keys must be non-empty strings")
        if not isinstance(level, str) or level.upper() not in _VALID_LEVELS:
            raise LoggingConfigError(f"invalid level for {logger_name!r}: {level!r}")
        levels[logger_name] = level.upper()

    rotation_raw = raw.get("rotation", {})
    if not isinstance(rotation_raw, Mapping):
        raise LoggingConfigError("rotation must be a mapping")
    _reject_trading_semantic_keys(rotation_raw.keys())
    unknown_rotation = sorted(set(rotation_raw.keys()) - set(_ROTATABLE_SINKS))
    if unknown_rotation:
        raise LoggingConfigError(f"unknown rotation sink names: {unknown_rotation!r}")
    rotation: dict[str, int] = {}
    for name, spec in rotation_raw.items():
        if not isinstance(spec, Mapping):
            raise LoggingConfigError(f"rotation.{name} must be a mapping")
        extra = sorted(set(spec.keys()) - {"max_segment_bytes"})
        if extra:
            raise LoggingConfigError(f"unknown rotation.{name} keys: {extra!r}")
        raw_bytes = spec.get("max_segment_bytes")
        if not isinstance(raw_bytes, int) or isinstance(raw_bytes, bool):
            raise LoggingConfigError(f"rotation.{name}.max_segment_bytes must be an int")
        if not (_MAX_SEGMENT_BYTES_MIN <= raw_bytes <= _MAX_SEGMENT_BYTES_MAX):
            raise LoggingConfigError(
                f"rotation.{name}.max_segment_bytes out of supported range "
                f"[{_MAX_SEGMENT_BYTES_MIN}, {_MAX_SEGMENT_BYTES_MAX}]: {raw_bytes!r}"
            )
        rotation[name] = raw_bytes

    retention_raw = raw.get("retention", {})
    if not isinstance(retention_raw, Mapping):
        raise LoggingConfigError("retention must be a mapping")
    _reject_trading_semantic_keys(retention_raw.keys())
    allowed_retention = {"policy"}
    unknown_retention = sorted(set(retention_raw.keys()) - allowed_retention)
    if unknown_retention:
        raise LoggingConfigError(
            f"unknown retention keys (numeric auto-delete durations are prohibited): {unknown_retention!r}"
        )
    policy = retention_raw.get("policy")
    if policy != _RETENTION_POLICY_NEVER_AUTO_DELETE:
        raise LoggingConfigError(
            f"retention.policy must be {_RETENTION_POLICY_NEVER_AUTO_DELETE!r} (ADR §126.2 OD-B); got {policy!r}"
        )

    return LoggingConfig(
        schema_version=str(version),
        sinks=sinks,
        levels=levels,
        rotation=rotation,
        retention_policy=str(policy),
    )


def build_sink_writer(config: LoggingConfig, sink_name: str, base_name: str) -> NonDeletingJsonlWriter | None:
    """Build the non-deleting writer for one configured sink, or None."""
    destination = config.sinks.get(sink_name)
    if destination is None:
        return None
    default_bytes = {
        "trade_log": 50 * 1024 * 1024,
        "error_log": 10 * 1024 * 1024,
        "strategy_log": 50 * 1024 * 1024,
    }[sink_name]
    max_bytes = config.rotation.get(sink_name, default_bytes)
    return NonDeletingJsonlWriter(destination, base_name, max_segment_bytes=max_bytes)
