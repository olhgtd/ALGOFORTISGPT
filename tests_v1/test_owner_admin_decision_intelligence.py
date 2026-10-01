from __future__ import annotations

from contextlib import contextmanager
import sqlite3
from types import SimpleNamespace
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.backend.owner_admin.decision_intelligence_router import attach_owner_decision_intelligence
from dashboard.backend.owner_admin.step_up import classify_destructive_route


OWNER_ID = UUID("22222222-2222-2222-2222-222222222222")


class _SecurityStore:
    def __init__(self) -> None:
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    @contextmanager
    def _transaction(self):
        cur = self._conn.cursor()
        try:
            yield cur
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cur.close()


class _Sessions:
    def __init__(self, role: str) -> None:
        self.role = role

    def require(self, token):
        if token != "ok":
            raise PermissionError("bad token")
        user = SimpleNamespace(
            user_id=OWNER_ID,
            role=SimpleNamespace(value=self.role),
            account_status=SimpleNamespace(value="ACTIVE"),
        )
        return SimpleNamespace(user=user)


class _AI:
    def snapshot(self):
        return {
            "authority_state": "AVAILABLE",
            "agents": [],
            "providers": [],
            "models": [],
            "jobs": [],
        }


def _app(role: str = "OWNER") -> FastAPI:
    app = FastAPI()
    app.state.security_store = _SecurityStore()
    app.state.sessions = _Sessions(role)
    app.state.ai_control = _AI()
    attach_owner_decision_intelligence(app)
    return app


def test_owner_only_read_surface_reuses_existing_session_authority() -> None:
    client = TestClient(_app("OWNER"))
    denied = client.get("/api/v1/owner/admin/ai/intelligence")
    assert denied.status_code == 401
    ok = client.get(
        "/api/v1/owner/admin/ai/intelligence",
        headers={"Authorization": "Bearer ok"},
    )
    assert ok.status_code == 200
    payload = ok.json()
    assert payload["live_state"] == "READ_ONLY/DISARMED"
    assert payload["broker_mutation"] == "ABSENT"


def test_normal_user_cannot_access_owner_intelligence_surface() -> None:
    client = TestClient(_app("USER"))
    response = client.get(
        "/api/v1/owner/admin/ai/intelligence",
        headers={"Authorization": "Bearer ok"},
    )
    assert response.status_code == 403


def test_all_intelligence_mutations_are_bound_to_existing_owner_step_up_middleware() -> None:
    assert classify_destructive_route(
        "POST", "/api/v1/owner/admin/ai/intelligence/market-watch-policy"
    ) == ("AI_MONITORING_POLICY", None)
    assert classify_destructive_route(
        "POST", "/api/v1/owner/admin/ai/intelligence/strategy-hunting"
    ) == ("AI_STRATEGY_HUNTING_POLICY", None)
    assert classify_destructive_route(
        "POST", "/api/v1/owner/admin/ai/intelligence/provider-queue"
    ) == ("AI_PROVIDER_QUEUE_POLICY", None)
    assert classify_destructive_route(
        "POST", f"/api/v1/owner/admin/ai/intelligence/entitlements/{OWNER_ID}"
    ) == ("AI_ENTITLEMENT_CHANGE", str(OWNER_ID))


def test_no_normal_user_global_ai_configuration_route_is_created() -> None:
    paths = {route.path for route in _app("OWNER").routes if hasattr(route, "path")}
    assert "/api/v1/user/ai/intelligence/config" not in paths
    assert "/api/v1/user/ai/providers" not in paths
