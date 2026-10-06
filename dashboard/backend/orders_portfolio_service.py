"""Read-only projections of the existing dashboard paper execution persistence.

No execution, valuation, account arithmetic, or lifecycle reconstruction belongs
here. Session accounts are independent and are never summed into an account.
"""
from __future__ import annotations

from typing import Any, Literal

from .paper_service import PaperService

ExecutionMode = Literal["PAPER", "BACKTEST", "LIVE"]


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
            "availability": "AVAILABLE" if mode == "PAPER" else "UNAVAILABLE",
            "source": "PERSISTED_PAPER_RUNTIME" if mode == "PAPER" else None,
            "accounts": [], "positions": [], "orders": [], "events": [],
            "aggregate_exposure": None,
            "limitations": [
                "Independent paper session accounts; no consolidated account or aggregate exposure authority.",
                "Reserved cash, protective relationships, per-position realized P&L and Core Audit links are unavailable.",
                "Historical paper option prices are modeled by the existing paper runtime.",
                "Account values are persisted PaperService summaries; engine account reconciliation is unavailable.",
            ],
            "capabilities": {
                "PAPER": "AVAILABLE", "LIVE": "UNAVAILABLE",
                "BACKTEST": "BACKTEST_SCREEN", "partial_fills": "UNAVAILABLE",
            },
        }
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
        snapshot = self.snapshot(user_id=user_id, session_id=session_id)
        for order in snapshot["orders"]:
            if order["order_id"] == order_id:
                return order
        raise LookupError("paper order unavailable")
