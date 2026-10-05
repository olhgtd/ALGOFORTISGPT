from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dashboard.backend.api import create_app


ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "dashboard" / "backend" / "api.py"
CLIENT = ROOT / "dashboard" / "shared" / "services" / "integrationClient.ts"
AREA5 = ROOT / "tests_v1" / "test_area5_complete_product_workflows.py"
DB_HARDENING = ROOT / "tests_v1" / "test_db007_db009_hardening.py"


def _text(path: Path) -> str:
    assert path.is_file(), f"missing contract source: {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def test_backend_declares_every_canonical_user_mutation_route() -> None:
    source = _text(API)
    required = (
        '@app.post("/api/v1/strategies")',
        '@app.post("/api/v1/backtests", status_code=202)',
        '@app.post("/api/v1/backtests/{run_id}/cancel")',
        '@app.post("/api/v1/walkforward/jobs", status_code=202)',
        '@app.post("/api/v1/walkforward/jobs/{job_id}/cancel")',
        '@app.post("/api/v1/paper/sessions")',
        '@app.post("/api/v1/paper/sessions/{session_id}/start")',
        '@app.post("/api/v1/paper/sessions/{session_id}/stop")',
        '@app.post("/api/v1/user/deployments")',
        '@app.post("/api/v1/user/deployments/{deployment_id}/pause")',
        '@app.post("/api/v1/user/deployments/{deployment_id}/resume")',
        '@app.post("/api/v1/user/deployments/{deployment_id}/stop")',
    )
    missing = [route for route in required if route not in source]
    assert not missing, f"missing canonical backend mutation routes: {missing}"


@pytest.mark.parametrize(
    ("path", "payload"),
    (
        ("/api/v1/strategies", {"source": "class X: pass"}),
        ("/api/v1/backtests", {"strategy_id": "S", "dataset_id": "D"}),
        ("/api/v1/backtests/RUN-1/cancel", None),
        ("/api/v1/walkforward/jobs", {"strategy_id": "S", "dataset_id": "D"}),
        ("/api/v1/walkforward/jobs/WF-1/cancel", None),
        ("/api/v1/paper/sessions", {"strategy_id": "S"}),
        ("/api/v1/paper/sessions/P-1/start", None),
        ("/api/v1/paper/sessions/P-1/stop", None),
        ("/api/v1/user/deployments", {"strategy_id": "S", "connection_id": "C", "instrument": "NIFTY", "execution_mode": "LIVE_PAPER"}),
        ("/api/v1/user/deployments/D-1/pause", {}),
        ("/api/v1/user/deployments/D-1/resume", {}),
        ("/api/v1/user/deployments/D-1/stop", {}),
    ),
)
def test_user_mutation_routes_are_real_authenticated_backend_boundaries(path: str, payload: dict | None) -> None:
    """A missing/fake route would be 404; a UI-only action would never reach this auth boundary."""
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(path, json=payload) if payload is not None else client.post(path)
    assert response.status_code in {401, 403}, (path, response.status_code, response.text)


def test_shared_user_clients_use_exact_backend_routes_and_fail_closed() -> None:
    source = _text(CLIENT)
    required_tokens = (
        '`${getApiBaseUrl()}/api/v1/strategies`',
        '`${getApiBaseUrl()}/api/v1/backtests`',
        '`${getApiBaseUrl()}/api/v1/backtests/${encodeURIComponent(runId)}/cancel`',
        '`${getApiBaseUrl()}/api/v1/walkforward/jobs`',
        '`${getApiBaseUrl()}/api/v1/walkforward/jobs/${encodeURIComponent(jobId)}/cancel`',
        '`${getApiBaseUrl()}/api/v1/paper/sessions`',
        '`${getApiBaseUrl()}/api/v1/paper/sessions/${encodeURIComponent(sessionId)}/start`',
        '`${getApiBaseUrl()}/api/v1/paper/sessions/${encodeURIComponent(sessionId)}/stop`',
        '`${getApiBaseUrl()}/api/v1/user/deployments`',
        '`${getApiBaseUrl()}/api/v1/user/deployments/${encodeURIComponent(deploymentId)}/${action}`',
        'error: "BACKEND_AUTHORITY_UNAVAILABLE"',
        'isFallback: false',
    )
    missing = [token for token in required_tokens if token not in source]
    assert not missing, f"missing fail-closed User client contracts: {missing}"


def test_real_backend_regressions_cover_paper_and_deployment_lifecycle() -> None:
    """Bind this slice to existing real-service tests instead of duplicating their large fixtures."""
    area5 = _text(AREA5)
    hardening = _text(DB_HARDENING)

    for token in (
        '"/api/v1/paper/sessions"',
        '/start", headers=trader_headers',
        '/stop", headers=trader_headers',
        'self.assertEqual(get_resp.json()["status"], "ACTIVE")',
        'self.assertEqual(stop_resp.json()["status"], "STOPPED")',
    ):
        assert token in area5

    assert 'self.assertEqual(paused_dep["status"], "PAUSED")' in hardening
    assert '"LIVE_PAPER"' in _text(ROOT / "dashboard" / "backend" / "deployment_service.py")


def test_user_action_contract_never_grants_live_or_broker_mutation() -> None:
    client = _text(CLIENT)
    for forbidden in (
        "/api/v1/live/arm",
        "/api/v1/live/orders",
        "/api/v1/broker/orders",
    ):
        # These strings may exist elsewhere in the legacy/shared client, but the
        # canonical User action functions added by this slice must not introduce
        # them. Pin the canonical screens separately in the boundary test.
        assert forbidden not in _text(ROOT / "dashboard" / "user-dashboard" / "screens" / "UserStrategies.tsx")
        assert forbidden not in _text(ROOT / "dashboard" / "user-dashboard" / "screens" / "UserTesting.tsx")
        assert forbidden not in _text(ROOT / "dashboard" / "user-dashboard" / "screens" / "UserTrades.tsx")

    assert 'execution_mode: "LIVE_PAPER"' in _text(ROOT / "dashboard" / "user-dashboard" / "screens" / "UserStrategies.tsx")
    assert "BACKEND_AUTHORITY_UNAVAILABLE" in client
