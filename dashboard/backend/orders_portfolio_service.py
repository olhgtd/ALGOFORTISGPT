"""Read-only projections of the existing dashboard paper and shadow execution persistence.

No execution, valuation, account arithmetic, or lifecycle reconstruction belongs
here. Session accounts are independent and are never summed into an account.
"""
from __future__ import annotations

from typing import Any, Literal

from .paper_service import PaperService

ExecutionMode = Literal["PAPER", "BACKTEST", "LIVE", "SHADOW"]


class OrdersPortfolioService:
    def __init__(self, paper: PaperService, live_readiness: Any = None) -> None:
        self.paper = paper
        self.live_readiness = live_readiness

    @staticmethod
    def _context(session: dict[str, Any]) -> dict[str, Any]:
        return {
            key: session.get(key) for key in (
                "session_id", "user_id", "strategy_id", "strategy_name",
                "strategy_version", "data_source_mode", "feed_status",
                "last_market_timestamp", "updated_at_utc", "owner_allowance",
                "owner_hold_reason",
            )
        } | {
            "execution_mode": "PAPER",
            "source": "PERSISTED_PAPER_RUNTIME",
            "pricing_basis": "MODELED_HISTORICAL_OPTION_PREMIUM"
            if session.get("data_source_mode") == "HISTORICAL_REPLAY"
            else "LIVE_MARKET_PAPER",
        }

    def snapshot(self, *, user_id: str | None, mode: ExecutionMode = "PAPER",
                 session_id: str | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "execution_mode": mode,
            "availability": "AVAILABLE" if mode in ("PAPER", "SHADOW") else "UNAVAILABLE",
            "source": "PERSISTED_PAPER_RUNTIME" if mode == "PAPER" else ("SENTINELX_SHADOW_RUNTIME" if mode == "SHADOW" else None),
            "accounts": [], "positions": [], "orders": [], "events": [],
            "aggregate_exposure": None,
            "limitations": [
                "Independent paper session accounts; no consolidated account or aggregate exposure authority.",
                "Reserved cash, protective relationships, per-position realized P&L and Core Audit links are unavailable.",
                "Historical paper option prices are modeled by the existing paper runtime.",
                "Account values are persisted PaperService summaries; engine account reconciliation is unavailable.",
            ] if mode == "PAPER" else [
                "Shadow records reflect would-be dry-run orders. Real broker execution is disabled.",
                "Zero broker mutations transmitted; no live holdings or fills created.",
            ],
            "capabilities": {
                "PAPER": "AVAILABLE", "SHADOW": "AVAILABLE", "LIVE": "UNAVAILABLE",
                "BACKTEST": "BACKTEST_SCREEN", "partial_fills": "UNAVAILABLE",
            },
        }
        if mode == "SHADOW":
            shadow_records = []
            if self.live_readiness is not None:
                if hasattr(self.live_readiness, "shadow_orders"):
                    shadow_records = self.live_readiness.shadow_orders(user_id)
                elif hasattr(self.live_readiness, "store"):
                    obs = self.live_readiness.store.live_observations(user_id)
                    shadow_records = [r["data"] for r in obs if r["key"].startswith("shadow:") or (r["key"].startswith("intent:") and r["data"].get("execution_mode") == "SHADOW")]

            for rec in shadow_records:
                would_be = rec.get("would_be_payload") or {}
                order_id = rec.get("intent_id", "UNKNOWN")
                result["orders"].append({
                    "order_id": order_id,
                    "session_id": "SHADOW_VALIDATION",
                    "user_id": rec.get("user_id", user_id or "UNKNOWN"),
                    "execution_mode": "SHADOW",
                    "strategy_name": rec.get("strategy_id", "UNKNOWN"),
                    "instrument": rec.get("canonical_instrument") or would_be.get("canonical_instrument") or rec.get("instrument_token", "UNKNOWN"),
                    "side": rec.get("side", "BUY"),
                    "qty": rec.get("quantity", "0"),
                    "order_type": would_be.get("order_type", "MARKET"),
                    "limit_price": would_be.get("limit_price") or "-",
                    "fill_price": None,
                    "status": rec.get("status", "SHADOW_READY"),
                    "rejection_reason": "; ".join(r.get("detail", r.get("code", "")) for r in rec.get("reasons", [])) if rec.get("reasons") else None,
                    "data_source_mode": "SHADOW_DRY_RUN",
                    "source": "SENTINELX_SHADOW_RUNTIME",
                    "created_at_utc": rec.get("checked_at"),
                    "filled_at_utc": None,
                    "protective_id": None,
                    "core_audit_id": rec.get("audit_id"),
                })
                result["events"].append({
                    "event_id": rec.get("audit_id") or f"EVT-{order_id[:12]}",
                    "session_id": "SHADOW_VALIDATION",
                    "user_id": rec.get("user_id", user_id or "UNKNOWN"),
                    "execution_mode": "SHADOW",
                    "event_time": rec.get("checked_at"),
                    "status": rec.get("status", "SHADOW_READY"),
                    "source": "SENTINELX_SHADOW_PIPELINE",
                    "detail": f"Status: {rec.get('status')} | Idempotency: {rec.get('idempotency_key', order_id)} | Reasons: {[r.get('code') for r in rec.get('reasons', [])]}",
                })
            return result

        if mode != "PAPER":
            return result
        if session_id is not None:
            session = self.paper.get_session(session_id, user_id=user_id)
            if session is None:
                raise LookupError("paper session unavailable")
            sessions = [session]
        else:
            # SQLite's -1 means unbounded; do not silently omit older accounts.
            sessions = self.paper.list_sessions(user_id=user_id, limit=-1)
        for session in sessions:
            sid = session["session_id"]
            context = self._context(session)
            result["accounts"].append(context | {
                key: session.get(key) for key in (
                    "status", "instrument", "initial_capital", "current_equity",
                    "available_cash", "used_capital", "realized_pnl", "unrealized_pnl",
                    "total_pnl", "active_positions", "total_orders", "total_fills",
                    "created_at_utc", "stopped_at_utc", "error_message",
                )
            } | {"reserved_cash": None, "reconciliation_report": None})
            for position in self.paper.get_positions(sid, user_id=user_id):
                result["positions"].append(context | position | {
                    "realized_pnl": None, "protective_id": None,
                    "mark_timestamp": session.get("last_market_timestamp"),
                })
            for order in self.paper.get_orders(sid, user_id=user_id):
                result["orders"].append(context | order | {
                    "protective_id": None, "core_audit_id": None,
                })
            # Risk blocks before submission remain events, not invented orders.
            result["events"].extend(context | event for event in
                                    self.paper.get_events(sid, user_id=user_id, limit=-1))
        return result

    def order(self, *, user_id: str, session_id: str, order_id: str) -> dict[str, Any]:
        if session_id == "SHADOW_VALIDATION":
            snapshot = self.snapshot(user_id=user_id, mode="SHADOW")
            for o in snapshot["orders"]:
                if o["order_id"] == order_id:
                    return o
            raise LookupError("shadow order unavailable")
        snapshot = self.snapshot(user_id=user_id, session_id=session_id)
        for order in snapshot["orders"]:
            if order["order_id"] == order_id:
                return order
        raise LookupError("paper order unavailable")
