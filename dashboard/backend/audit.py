"""Tamper-evident dashboard security evidence, cross-linked by caller to core audit."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import UUID

from .domain import utc_now


@dataclass(frozen=True)
class SecurityAuditRecord:
    actor_id: str
    action: str
    payload: dict[str, object]
    recorded_at_utc: str
    previous_hash: str | None
    record_hash: str


class HashChainSecurityAudit:
    """Append-only local evidence; callers also emit/bridge core audit references."""
    def __init__(self, path: Path) -> None:
        self._path = path
        self._previous_hash: str | None = None
        if path.exists():
            last = path.read_text(encoding="utf-8").strip().splitlines()
            if last:
                self._previous_hash = json.loads(last[-1])["record_hash"]

    def record(self, *, actor_id: UUID, action: str, payload: dict[str, object]) -> None:
        material = {"actor_id": str(actor_id), "action": action, "payload": payload, "recorded_at_utc": utc_now().isoformat(), "previous_hash": self._previous_hash}
        digest = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        record = SecurityAuditRecord(**material, record_hash=digest)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")
        self._previous_hash = digest
