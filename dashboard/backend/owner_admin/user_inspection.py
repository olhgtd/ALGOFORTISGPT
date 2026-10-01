"""Read-only Owner inspection composition over existing product authorities.

This module deliberately creates no new strategy, trading, Paper, report, or
security authority.  Each tab either reads an existing tenant-scoped authority
or returns UNAVAILABLE.  Missing data is never replaced with sample fixtures.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID

from dashboard.backend.domain import Role


class OwnerUserInspectionUnavailable(LookupError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _surface(data: Any, *, state: str = "AVAILABLE", reason: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "authority_state": state,
        "source": "BACKEND" if state != "UNAVAILABLE" else "UNAVAILABLE",
        "trust": "FRESH" if state == "AVAILABLE" else "UNKNOWN",
        "as_of_utc": _now(),
        "data": data,
    }
    if reason:
        result["error"] = reason
    return result


def _unavailable(reason: str) -> dict[str, Any]:
    return _surface(None, state="UNAVAILABLE", reason=reason)


class OwnerUserInspectionService:
    """Composes the frozen inspection tabs from current authorities."""

    def __init__(self, app: Any) -> None:
        self._app = app

    @property
    def _security(self):
        store = getattr(self._app.state, "security_store", None)
        if store is None:
            raise OwnerUserInspectionUnavailable("SECURITY_AUTHORITY_UNAVAILABLE")
        return store

    def _resolve_profile(self, identifier: str) -> dict[str, Any]:
        clean = str(identifier or "").strip()
        if not clean:
            raise OwnerUserInspectionUnavailable("USER_IDENTIFIER_REQUIRED")
        rows = self._security._conn.execute(
            """SELECT user_id, role, lifecycle, display_name, created_at_utc,
                      security_state, sx_id, account_status, activation_status,
                      service_status, service_started_at, service_expires_at,
                      service_term_type, custom_term_value, custom_term_unit,
                      bound_email, bound_phone, notes, plan, created_by
               FROM users
               WHERE user_id = ? OR UPPER(COALESCE(sx_id, '')) = UPPER(?)
                  OR LOWER(COALESCE(bound_email, '')) = LOWER(?)
               LIMIT 2""",
            (clean, clean, clean),
        ).fetchall()
        if len(rows) != 1:
            raise OwnerUserInspectionUnavailable("USER_AUTHORITY_UNAVAILABLE")
        return dict(rows[0])

    @staticmethod
    def _attempt(reader: Callable[[], Any], unavailable_code: str) -> dict[str, Any]:
        try:
            return _surface(reader())
        except Exception:
            return _unavailable(unavailable_code)

    def snapshot(self, identifier: str) -> dict[str, Any]:
        profile = self._resolve_profile(identifier)
        user_id = str(profile["user_id"])
        user_uuid = UUID(user_id)
        try:
            role = Role(str(profile["role"]))
        except Exception:
            role = Role.USER

        strategies_service = getattr(self._app.state, "strategies", None)
        backtest_service = getattr(self._app.state, "backtest_service", None)
        paper_service = getattr(self._app.state, "paper_service", None)
        portfolio_service = getattr(self._app.state, "orders_portfolio_service", None)
        entitlement_service = getattr(self._app.state, "intelligence_entitlements", None)

        strategies = (
            self._attempt(
                lambda: strategies_service.list_user_strategies(user_uuid, role),
                "USER_STRATEGY_AUTHORITY_UNAVAILABLE",
            ) if strategies_service is not None else _unavailable("USER_STRATEGY_AUTHORITY_UNAVAILABLE")
        )
        backtests = (
            self._attempt(
                lambda: backtest_service.list_runs(user_id=user_id, limit=100),
                "USER_BACKTEST_AUTHORITY_UNAVAILABLE",
            ) if backtest_service is not None else _unavailable("USER_BACKTEST_AUTHORITY_UNAVAILABLE")
        )
        paper = (
            self._attempt(
                lambda: paper_service.list_sessions(user_id=user_id, limit=100),
                "USER_PAPER_AUTHORITY_UNAVAILABLE",
            ) if paper_service is not None else _unavailable("USER_PAPER_AUTHORITY_UNAVAILABLE")
        )
        portfolio_snapshot = (
            self._attempt(
                lambda: portfolio_service.snapshot(user_id=user_id, mode="PAPER"),
                "USER_PORTFOLIO_AUTHORITY_UNAVAILABLE",
            ) if portfolio_service is not None else _unavailable("USER_PORTFOLIO_AUTHORITY_UNAVAILABLE")
        )
        if portfolio_snapshot.get("authority_state") == "AVAILABLE":
            raw = portfolio_snapshot.get("data") or {}
            portfolio = _surface({
                "accounts": raw.get("accounts", []),
                "positions": raw.get("positions", []),
                "limitations": raw.get("limitations", []),
            })
            orders = _surface({
                "orders": raw.get("orders", []),
                "events": raw.get("events", []),
                "limitations": raw.get("limitations", []),
            })
        else:
            portfolio = _unavailable("USER_PORTFOLIO_AUTHORITY_UNAVAILABLE")
            orders = _unavailable("USER_ORDER_AUTHORITY_UNAVAILABLE")

        connections = self._attempt(
            lambda: self._security.list_user_connections(user_id, mask_account_ref=True),
            "USER_CONNECTION_AUTHORITY_UNAVAILABLE",
        )
        sessions = self._attempt(
            lambda: self._security.list_all_sessions(user_id=user_id),
            "USER_SESSION_AUTHORITY_UNAVAILABLE",
        )

        def security_projection() -> dict[str, Any]:
            credentials = self._security._conn.execute(
                """SELECT hex(credential_id) AS credential_id, rp_id, label,
                          is_backup_hardware, enabled, revoked, created_at_utc,
                          last_used_at_utc, revoked_at_utc
                   FROM webauthn_credentials
                   WHERE user_id = ?
                   ORDER BY created_at_utc DESC""",
                (user_id,),
            ).fetchall()
            return {
                "security_state": profile.get("security_state"),
                "account_status": profile.get("account_status"),
                "activation_status": profile.get("activation_status"),
                "credentials": [dict(row) for row in credentials],
            }

        security = self._attempt(security_projection, "USER_SECURITY_AUTHORITY_UNAVAILABLE")
        intelligence_access = (
            self._attempt(
                lambda: {
                    "identity_authority": "S2",
                    "capabilities": [item.value for item in entitlement_service.list_for_user(user_uuid)],
                },
                "USER_INTELLIGENCE_ENTITLEMENT_AUTHORITY_UNAVAILABLE",
            ) if entitlement_service is not None else _unavailable("USER_INTELLIGENCE_ENTITLEMENT_AUTHORITY_UNAVAILABLE")
        )

        # The current report endpoint is system-wide. Until a tenant-scoped
        # report read port exists, fail closed rather than filtering an
        # ambiguous system report projection in the presentation layer.
        reports = _unavailable("PER_USER_REPORT_AUTHORITY_NOT_EXPOSED")

        return {
            "source": "BACKEND",
            "trust": "FRESH",
            "as_of_utc": _now(),
            "user_id": user_id,
            "sx_id": profile.get("sx_id"),
            "live_state": "READ_ONLY/DISARMED",
            "tabs": {
                "Profile": _surface(profile),
                "Strategies": strategies,
                "Backtests": backtests,
                "Paper": paper,
                "Portfolio": portfolio,
                "Orders": orders,
                "Connections": connections,
                "Reports": reports,
                "Sessions": sessions,
                "Security State": security,
                "Intelligence Access": intelligence_access,
            },
        }
