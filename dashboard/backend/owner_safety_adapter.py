"""Bounded Owner safety projection over already-attached canonical authorities.

This adapter never imports broker/order execution. Kill-switch control is exposed
only when the canonical Paper/Live-Paper coordinator authority is explicitly
attached by the dashboard runtime; otherwise the surface remains fail-closed.
"""
from __future__ import annotations

from typing import Any


class OwnerSafetyAdapter:
    def __init__(
        self,
        *,
        security_store: Any,
        safe_mode: Any,
        live_readiness_service: Any | None,
        kill_switch_authority: Any | None = None,
    ) -> None:
        self._store = security_store
        self._safe_mode = safe_mode
        self._live = live_readiness_service
        self._kill_switch = kill_switch_authority

    def _kill_switch_snapshot(self) -> dict[str, Any]:
        authority = self._kill_switch
        if authority is None:
            return {"state": "NOT_CONNECTED", "reason": "CANONICAL_KILL_SWITCH_BRIDGE_NOT_ATTACHED"}

        try:
            active = getattr(authority, "is_kill_switch_active", None)
            if callable(active):
                active = active()
            if active is None:
                state = getattr(authority, "safety_state", None)
                state_name = getattr(state, "name", str(state or "UNKNOWN")).upper()
                active = state_name == "KILL_SWITCH_ACTIVE"
            return {
                "state": "ACTIVE" if bool(active) else "CLEAR",
                "reason": "CANONICAL_PAPER_COORDINATOR",
            }
        except Exception:
            return {"state": "UNKNOWN", "reason": "CANONICAL_KILL_SWITCH_STATE_UNAVAILABLE"}

    def _risk_snapshot(self) -> dict[str, Any]:
        provider = getattr(self._live, "risk_provider", None) if self._live is not None else None
        if not callable(provider):
            return {"state": "UNAVAILABLE", "reason": "RISK_SNAPSHOT_AUTHORITY_UNAVAILABLE"}

        try:
            raw = provider()
        except Exception:
            return {"state": "UNAVAILABLE", "reason": "RISK_SNAPSHOT_AUTHORITY_UNAVAILABLE"}

        if not isinstance(raw, dict):
            return {"state": "UNAVAILABLE", "reason": "RISK_SNAPSHOT_AUTHORITY_INVALID"}

        allowed = (
            "policy_version",
            "daily_loss_limit",
            "max_daily_loss_pct",
            "portfolio_exposure_limit",
            "max_portfolio_risk_pct",
            "max_drawdown",
            "max_open_positions",
            "max_daily_trades",
            "per_trade_risk_pct",
            "per_order_limit",
            "slippage_threshold",
            "as_of_utc",
            "source",
        )
        projection = {key: raw[key] for key in allowed if key in raw}
        projection["state"] = "AVAILABLE"
        projection.setdefault("source", "RISK_AUTHORITY")
        return projection

    def snapshot(self) -> dict[str, Any]:
        safe_available = self._safe_mode is not None
        hold_available = self._store is not None and hasattr(self._store, "live_global_hold")
        global_hold = None
        if hold_available:
            try:
                global_hold = bool(self._store.live_global_hold())
            except Exception:
                hold_available = False

        risk = self._risk_snapshot()
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
            "risk_gate": risk,
            "live_state": "READ_ONLY/DISARMED",
            "broker_mutation": "ABSENT",
            "kill_switch": self._kill_switch_snapshot(),
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

    def engage_kill_switch(self, reason: str) -> dict[str, Any]:
        authority = self._kill_switch
        if authority is None:
            raise RuntimeError("CANONICAL_KILL_SWITCH_BRIDGE_NOT_ATTACHED")
        if not reason.strip():
            raise ValueError("kill switch reason is required")
        activate = getattr(authority, "activate_kill_switch", None)
        if not callable(activate):
            raise RuntimeError("CANONICAL_KILL_SWITCH_AUTHORITY_INVALID")
        activate(reason=reason, source="owner_dashboard")
        return self.snapshot()

    def release_global_hold(self, actor_id: str) -> dict[str, Any]:
        if self._live is None:
            raise RuntimeError("LIVE_SAFETY_AUTHORITY_UNAVAILABLE")
        self._live.set_hold(actor_id, False)
        return self.snapshot()
