"""AlgoFortis V2 tamper-evident audit-chain foundation.

This module wraps the existing immutable ``AuditEvent`` envelope rather than
replacing it.  Each appended event is linked to the previous entry by a
canonical SHA-256 fingerprint and carries explicit version evidence required by
AF2-AUD-001/003.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from engine.audit.model import AuditEvent
from engine.reproducibility.codec import CanonicalCodec, CanonicalEncodingError


_CHAIN_SCHEMA = "algofortis-audit-chain-entry/v1"


class AuditChainError(ValueError):
    """Raised when audit evidence is incomplete or chain integrity fails."""


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuditChainError(f"{field} must be a non-empty string")
    return value.strip()


def _normalized_versions(event: AuditEvent, versions: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    if not isinstance(versions, Mapping):
        raise AuditChainError("version evidence must be a mapping")
    if not versions:
        raise AuditChainError("version evidence must not be empty")

    normalized: dict[str, str] = {}
    for raw_name, raw_version in versions.items():
        name = _required_text(raw_name, "version evidence name")
        version = _required_text(raw_version, f"version evidence {name}")
        normalized[name] = version

    mandatory = {
        "audit_envelope": event.event_schema_version,
        "payload": event.payload_version,
    }
    for name, expected in mandatory.items():
        existing = normalized.get(name)
        if existing is not None and existing != expected:
            raise AuditChainError(
                f"version evidence {name} conflicts with event envelope: {existing!r} != {expected!r}"
            )
        normalized[name] = expected

    return tuple(sorted(normalized.items(), key=lambda pair: pair[0]))


def _validate_event_identity(event: AuditEvent) -> None:
    if not isinstance(event, AuditEvent):
        raise TypeError("event must be an AuditEvent")
    _required_text(event.run_id, "run_id")
    _required_text(event.correlation_id, "correlation_id")


def _entry_hash(
    *,
    sequence: int,
    previous_hash: str,
    event: AuditEvent,
    versions: tuple[tuple[str, str], ...],
) -> str:
    try:
        return CanonicalCodec.fingerprint(
            _CHAIN_SCHEMA,
            (
                ("sequence", sequence),
                ("previous_hash", previous_hash),
                ("event_id", event.event_id),
                ("recorded_at_utc", event.recorded_at_utc),
                ("event", event.semantic_projection()),
                ("versions", versions),
            ),
        )
    except CanonicalEncodingError as exc:
        raise AuditChainError("audit entry cannot be canonically encoded") from exc


@dataclass(frozen=True, slots=True)
class AuditChainEntry:
    """One immutable, hash-linked audit evidence record."""

    sequence: int
    previous_hash: str
    event: AuditEvent
    versions: tuple[tuple[str, str], ...]
    chain_hash: str


class AuditChain:
    """In-memory append-only chain primitive for V2 audit evidence.

    Persistence is intentionally outside this Phase-1 slice.  Durable stores may
    persist ``AuditChainEntry`` records and use ``verify_audit_chain`` on load or
    export without changing the existing V1 ``AuditEvent`` model.
    """

    GENESIS_HASH = "0" * 64

    def __init__(self) -> None:
        self._entries: list[AuditChainEntry] = []

    @property
    def entries(self) -> tuple[AuditChainEntry, ...]:
        return tuple(self._entries)

    def append(self, event: AuditEvent, *, versions: Mapping[str, str]) -> AuditChainEntry:
        _validate_event_identity(event)
        normalized_versions = _normalized_versions(event, versions)
        sequence = len(self._entries) + 1
        previous_hash = self._entries[-1].chain_hash if self._entries else self.GENESIS_HASH
        chain_hash = _entry_hash(
            sequence=sequence,
            previous_hash=previous_hash,
            event=event,
            versions=normalized_versions,
        )
        entry = AuditChainEntry(
            sequence=sequence,
            previous_hash=previous_hash,
            event=event,
            versions=normalized_versions,
            chain_hash=chain_hash,
        )
        self._entries.append(entry)
        return entry


def verify_audit_chain(entries: Sequence[AuditChainEntry]) -> bool:
    """Fail closed if sequence, linkage, versions, identity or hash was altered."""

    if not isinstance(entries, Sequence):
        raise TypeError("entries must be a sequence")

    previous_hash = AuditChain.GENESIS_HASH
    for expected_sequence, entry in enumerate(entries, start=1):
        if not isinstance(entry, AuditChainEntry):
            raise AuditChainError("audit chain contains an invalid entry type")
        if entry.sequence != expected_sequence:
            raise AuditChainError(
                f"audit chain sequence mismatch: expected {expected_sequence}, got {entry.sequence}"
            )
        if entry.previous_hash != previous_hash:
            raise AuditChainError("audit chain previous hash mismatch")

        _validate_event_identity(entry.event)
        normalized_versions = _normalized_versions(entry.event, dict(entry.versions))
        if normalized_versions != entry.versions:
            raise AuditChainError("audit chain version evidence is not canonical")

        expected_hash = _entry_hash(
            sequence=entry.sequence,
            previous_hash=entry.previous_hash,
            event=entry.event,
            versions=entry.versions,
        )
        if entry.chain_hash != expected_hash:
            raise AuditChainError("audit chain hash mismatch")
        previous_hash = entry.chain_hash

    return True


__all__ = [
    "AuditChainError",
    "AuditChainEntry",
    "AuditChain",
    "verify_audit_chain",
]
