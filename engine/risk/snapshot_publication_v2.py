"""Atomic publication boundary for immutable RiskSnapshot evidence."""
from __future__ import annotations

from threading import Lock

from engine.risk.snapshot_contracts_v2 import RiskSnapshot


class RiskSnapshotPublication:
    def __init__(self) -> None:
        self._current: RiskSnapshot | None = None
        self._write_lock = Lock()

    def publish(self, snapshot: RiskSnapshot) -> None:
        if not isinstance(snapshot, RiskSnapshot):
            raise TypeError("snapshot must be RiskSnapshot")
        with self._write_lock:
            self._current = snapshot

    def current(self) -> RiskSnapshot | None:
        return self._current


__all__ = ["RiskSnapshotPublication"]
