"""Untrusted external-content boundary for Phase 8 research/shadow AI."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from posixpath import normpath
from urllib.parse import urlsplit, urlunsplit


class UntrustedContentError(ValueError):
    pass


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise UntrustedContentError(f"{name} must be a non-empty string")
    return value.strip()


def _aware(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise UntrustedContentError(f"{name} must be timezone-aware datetime")
    return value


def _normalize_url(value: str) -> str:
    raw = _text(value, "source_url")
    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        raise UntrustedContentError("source_url must use http or https")
    host = (parts.hostname or "").lower()
    if not host:
        raise UntrustedContentError("source_url host is required")
    port = parts.port
    netloc = host
    if port is not None:
        netloc += f":{port}"
    path = normpath(parts.path or "/")
    if parts.path.endswith("/") and not path.endswith("/"):
        path += "/"
    if not path.startswith("/"):
        path = "/" + path
    return urlunsplit((scheme, netloc, path, parts.query, ""))


@dataclass(frozen=True, slots=True)
class UntrustedEvidence:
    content: str
    normalized_url: str
    provenance_ref: str
    observed_at: datetime
    trust_label: str = "UNTRUSTED_EXTERNAL"

    @classmethod
    def create(cls, *, content: str, source_url: str, provenance_ref: str, observed_at: datetime) -> "UntrustedEvidence":
        return cls(
            content=_text(content, "content"),
            normalized_url=_normalize_url(source_url),
            provenance_ref=_text(provenance_ref, "provenance_ref"),
            observed_at=_aware(observed_at, "observed_at"),
        )


@dataclass(frozen=True, slots=True)
class UntrustedContentVerdict:
    quarantined: bool
    reasons: tuple[str, ...]
    policy_mutation_allowed: bool = False
    tool_permission_expansion_allowed: bool = False


class UntrustedContentGuard:
    _POLICY_OVERRIDE_MARKERS = (
        "ignore system instructions",
        "ignore previous instructions",
        "override policy",
        "disable safety",
        "broker.place_order",
    )
    _SECRET_MARKERS = (
        "api_key",
        "api key",
        "secret key",
        "private key",
        "access token",
        "send it to",
        "exfiltrate",
    )

    def evaluate(self, evidence: UntrustedEvidence) -> UntrustedContentVerdict:
        if not isinstance(evidence, UntrustedEvidence):
            raise UntrustedContentError("evidence must be UntrustedEvidence")
        text = evidence.content.casefold()
        reasons: list[str] = []
        if any(marker in text for marker in self._POLICY_OVERRIDE_MARKERS):
            reasons.append("POLICY_OVERRIDE_INSTRUCTION")
        if any(marker in text for marker in self._SECRET_MARKERS):
            reasons.append("SECRET_EXFILTRATION")
        return UntrustedContentVerdict(
            quarantined=bool(reasons),
            reasons=tuple(sorted(set(reasons))),
        )


@dataclass(frozen=True, slots=True)
class ToolRequestBound:
    allowed: tuple[str, ...]
    denied: tuple[str, ...]


def bound_tool_request(*, requested_tool_ids: tuple[str, ...], allowed_tool_ids: tuple[str, ...]) -> ToolRequestBound:
    if not isinstance(requested_tool_ids, tuple) or not isinstance(allowed_tool_ids, tuple):
        raise UntrustedContentError("tool ids must be tuples")
    requested = tuple(_text(item, "requested_tool_id") for item in requested_tool_ids)
    allowed_policy = {_text(item, "allowed_tool_id") for item in allowed_tool_ids}
    allowed = tuple(sorted({item for item in requested if item in allowed_policy}))
    denied = tuple(sorted({item for item in requested if item not in allowed_policy}))
    return ToolRequestBound(allowed=allowed, denied=denied)


__all__ = [
    "UntrustedContentError", "UntrustedEvidence", "UntrustedContentVerdict",
    "UntrustedContentGuard", "ToolRequestBound", "bound_tool_request",
]
