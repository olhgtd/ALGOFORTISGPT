"""Centralized, recursive server filesystem path redaction boundary (P3-2).

Ensures non-Owner / user-facing serialized payloads (reports, backtest runs,
paper sessions, event logs, and error details) never leak server-local
filesystem structures, absolute Windows drive paths, UNC network shares,
or POSIX server-internal directory trees.
"""

from __future__ import annotations

import re
from typing import Any

# Windows drive paths: C:\..., D:/..., and escaped C:\\...
WINDOWS_PATH_RE = re.compile(
    r'(?<![a-zA-Z0-9_])([a-zA-Z]:(?:\\+|/+)(?:[^\\/:*?"<>|\r\n\s]+(?:\\+|/+))*[^\\/:*?"<>|\r\n\s]*)'
)

# UNC network shares: \\server\share\... and escaped \\\\server\\share\...
UNC_PATH_RE = re.compile(
    r'(?<![a-zA-Z0-9_])((?:\\{2,})[a-zA-Z0-9_.$ -]+(?:\\+|/+)[a-zA-Z0-9_.$ -]+(?:(?:\\+|/+)[^\\/:*?"<>|\r\n\s]+)*)'
)

# POSIX server-internal directory roots: /home/..., /tmp/..., /var/..., etc.
POSIX_SERVER_PATH_RE = re.compile(
    r'(?<![a-zA-Z0-9_])(/(?:home|tmp|var|usr|opt|etc|root|private|Users|AppData)/[^:*?"<>|\r\n\s]*)'
)


def _clean_path_match(match: re.Match[str]) -> str:
    matched = match.group(0)
    # Strip trailing punctuation often attached in error messages or JSON strings
    trailing_punct = ""
    while matched and matched[-1] in '.,;:!?)":':
        trailing_punct = matched[-1] + trailing_punct
        matched = matched[:-1]

    normalized = re.sub(r"\\+", "/", matched)
    parts = [p for p in normalized.split("/") if p]
    basename = parts[-1] if parts else "[REDACTED_PATH]"
    return basename + trailing_punct


def redact_server_paths_in_string(val: str) -> str:
    """Redact server-local paths embedded inside a string, retaining only basenames."""
    if not val or not isinstance(val, str):
        return val

    # Fast check: if string does not contain path indicators, return as-is
    if not (":\\" in val or ":/" in val or "\\\\" in val or "/home/" in val or "/tmp/" in val
            or "/var/" in val or "/usr/" in val or "/opt/" in val or "/etc/" in val
            or "/root/" in val or "/private/" in val or "/Users/" in val or "/AppData/" in val):
        return val

    res = WINDOWS_PATH_RE.sub(_clean_path_match, val)
    res = UNC_PATH_RE.sub(_clean_path_match, res)
    res = POSIX_SERVER_PATH_RE.sub(_clean_path_match, res)
    return res


def redact_server_paths(obj: Any) -> Any:
    """Recursively redact server-local paths throughout nested structures."""
    if isinstance(obj, str):
        return redact_server_paths_in_string(obj)
    elif isinstance(obj, dict):
        return {k: redact_server_paths(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [redact_server_paths(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(redact_server_paths(item) for item in obj)
    elif isinstance(obj, set):
        return {redact_server_paths(item) for item in obj}
    return obj


def sanitize_report_for_client(item: dict[str, Any], is_owner: bool = False) -> dict[str, Any]:
    """Strip raw server internal filesystem paths for normal users (F-17 / P3-2).

    Owner / internal oversight retains authoritative evidence paths.
    Normal users receive recursively redacted payloads with server paths stripped to basenames.
    """
    if is_owner:
        return item
    return redact_server_paths(item)
