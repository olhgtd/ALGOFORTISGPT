from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.backend.product_ops_v2.read_models import ProductOpsHealth, UserPrivacyReadModel
from dashboard.backend.product_ops_v2.router import attach_product_ops_routes
from dashboard.backend.product_ops_v2.service import ProductOpsService


class Sessions:
    def __init__(self, user):
        self.user = user

    def require(self, token):
        if token != "ok":
            raise PermissionError("AUTH_REQUIRED")
        return SimpleNamespace(user=self.user)


def make_app(*, role="USER", user_id="user-1", owner_health=None, privacy_models=None):
    app = FastAPI()
    app.state.sessions = Sessions(SimpleNamespace(user_id=user_id, role=role, account_status="ACTIVE"))
    app.state.product_ops_service = ProductOpsService(repository=None)
    if owner_health is not None:
        app.state.product_ops_owner_health_provider = lambda: owner_health
    if privacy_models is not None:
        app.state.product_ops_user_privacy_provider = lambda principal_ref: privacy_models[principal_ref]
    attach_product_ops_routes(app)
    return app


def test_owner_health_requires_active_owner_and_returns_only_read_model_plus_safety_markers():
    health = ProductOpsHealth(
        unresolved_incidents=2,
        alert_health="DEGRADED",
        privacy_requests=(("RECEIVED", 3), ("IN_PROGRESS", 1)),
        stale_policy_count=1,
        backup_status="PASS",
        restore_status="PASS",
        rollback_status="PASS",
        active_policy_versions=("privacy-notice/1.0.0",),
    )
    user_client = TestClient(make_app(owner_health=health))
    assert user_client.get("/api/v1/product-ops/owner/health", headers={"authorization": "Bearer ok"}).status_code == 403

    owner_client = TestClient(make_app(role="OWNER", user_id="owner-1", owner_health=health))
    response = owner_client.get("/api/v1/product-ops/owner/health", headers={"authorization": "Bearer ok"})
    assert response.status_code == 200
    body = response.json()
    assert body["unresolved_incidents"] == 2
    assert body["alert_health"] == "DEGRADED"
    assert body["live_state"] == "READ_ONLY/DISARMED"
    assert body["ai_authority"] == "RESEARCH_SHADOW_ONLY"
    assert "broker" not in body and "approved_order" not in body


def test_current_privacy_read_is_derived_from_authenticated_principal_only():
    model = UserPrivacyReadModel(
        notice_policy_ref="privacy-notice/1.0.0",
        notice_fingerprint="a" * 64,
        consent_state="GRANTED",
        request_statuses=(("ACCESS-1", "IN_PROGRESS"), ("GRIEVANCE-1", "RECEIVED")),
    )
    app = make_app(user_id="user-1", privacy_models={"user-1": model})
    response = TestClient(app).get(
        "/api/v1/product-ops/privacy/current",
        headers={"authorization": "Bearer ok"},
    )
    assert response.status_code == 200
    assert response.json()["notice_policy_ref"] == "privacy-notice/1.0.0"
    assert response.json()["request_statuses"][0] == ["ACCESS-1", "IN_PROGRESS"]


def test_missing_product_ops_read_model_authority_fails_closed():
    owner = TestClient(make_app(role="OWNER", user_id="owner-1"))
    response = owner.get("/api/v1/product-ops/owner/health", headers={"authorization": "Bearer ok"})
    assert response.status_code == 503
    assert response.json()["detail"] == "PRODUCT_OPS_READ_MODEL_UNAVAILABLE"
