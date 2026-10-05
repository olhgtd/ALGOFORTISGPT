"""Bounded Owner safety projection over already-attached canonical authorities.

This adapter never imports broker/order execution or engine kill-switch control.
If a canonical authority is not attached to the dashboard runtime, it reports
that fact explicitly instead of manufacturing a healthy/readiness state.
"""
from __future__ import annotations

from typing import Any


class OwnerSafetyAdapter:
    def __init__(self, *, security_store: Any, safe_mode: Any, live_readiness_service: Any | None) -> None:
        self._store = security_store
        self._safe_mode = safe_mode
        self._live = live_readiness_service

    def snapshot(self) -> dict[str, Any]:
        safe_available = self._safe_mode is not None
        hold_available = self._store is not None and hasattr(self._store, "live_global_hold")
        risk_available = bool(self._live is not None and getattr(self._live, "risk_provider", None) is not None)
        global_hold = None
        if hold_available:
            try:
                global_hold = bool(self._store.live_global_hold())
            except Exception:
                hold_available = False
        return {
            "authority_state": "AVAILABLE" if safe_available and hold_available else "UNAVAILABLE",
            "safe_mode": {
                "state": "AVAILABLE" if safe_available else "UNAVAILABLE",
                "enabled": bool(self._safe_mode.enabled) if safe_available else None,
            },
            "global_hold": {
                "state": "AVAILABLE" if hold_available else "UNAVAILABLE",
                "enabled": global_hold if hold_available else None,
            },
            "risk_gate": {
                "state": "AVAILABLE" if risk_available else "UNAVAILABLE",
                "reason": None if risk_available else "RISK_SNAPSHOT_AUTHORITY_UNAVAILABLE",
            },
            "live_state": "READ_ONLY/DISARMED",
            "broker_mutation": "ABSENT",
            "kill_switch": {"state": "NOT_CONNECTED", "reason": "CANONICAL_KILL_SWITCH_BRIDGE_NOT_ATTACHED"},
        }

    def engage_safe_mode(self) -> dict[str, Any]:
        if self._safe_mode is None:
            raise RuntimeError("SAFE_MODE_AUTHORITY_UNAVAILABLE")
        self._safe_mode.set(True)
        return self.snapshot()

    def engage_global_hold(self, actor_id: str) -> dict[str, Any]:
        if self._live is None:
            raise RuntimeError("LIVE_SAFETY_AUTHORITY_UNAVAILABLE")
        self._live.set_hold(actor_id, True)
        return self.snapshot()

    def release_global_hold(self, actor_id: str) -> dict[str, Any]:
        if self._live is None:
            raise RuntimeError("LIVE_SAFETY_AUTHORITY_UNAVAILABLE")
        self._live.set_hold(actor_id, False)
        return self.snapshot()
