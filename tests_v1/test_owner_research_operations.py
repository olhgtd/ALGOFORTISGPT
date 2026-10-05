from __future__ import annotations

from pathlib import Path

from dashboard.backend.owner_admin.step_up import classify_destructive_route

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "dashboard" / "backend" / "api.py"
RESEARCH_CLIENT = ROOT / "dashboard" / "owner-dashboard" / "authoritative" / "researchOps.ts"
RESEARCH_SCREEN = ROOT / "dashboard" / "owner-dashboard" / "authoritative" / "ResearchOperations.tsx"
OWNER_SHELL = ROOT / "dashboard" / "owner-dashboard" / "OwnerDashboardApp.tsx"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_owner_research_backend_exposes_installation_wide_reads_and_explicit_admin_cancel_routes() -> None:
    source = _text(API)
    assert '@app.get("/api/v1/owner/backtests")' in source
    assert '@app.get("/api/v1/owner/walkforward/jobs")' in source
    assert '@app.post("/api/v1/backtests", status_code=202)' in source
    assert '@app.post("/api/v1/walkforward/jobs", status_code=202)' in source
    assert '@app.post("/api/v1/owner/backtests/{run_id}/cancel")' in source
    assert '@app.post("/api/v1/owner/walkforward/jobs/{job_id}/cancel")' in source


def test_cross_user_research_cancel_is_step_up_bound_to_the_exact_resource() -> None:
    assert classify_destructive_route(
        "POST", "/api/v1/owner/backtests/RUN-1/cancel"
    ) == ("BACKTEST_ADMIN", "RUN-1")
    assert classify_destructive_route(
        "POST", "/api/v1/owner/walkforward/jobs/WF-1/cancel"
    ) == ("WALKFORWARD_ADMIN", "WF-1")


def test_owner_research_client_uses_owner_reads_and_never_live_or_broker_mutation() -> None:
    source = _text(RESEARCH_CLIENT)
    assert "/api/v1/owner/backtests?limit=200" in source
    assert "/api/v1/owner/walkforward/jobs?limit=200" in source
    assert "/api/v1/owner/backtests/${encodeURIComponent(runId)}/cancel" in source
    assert "/api/v1/owner/walkforward/jobs/${encodeURIComponent(jobId)}/cancel" in source
    assert 'actionFamily: "BACKTEST_ADMIN"' in source
    assert 'actionFamily: "WALKFORWARD_ADMIN"' in source
    for forbidden in (
        "/api/v1/live/arm",
        "/api/v1/live/orders",
        "/api/v1/broker/orders",
        "/api/v1/orders/place",
        "/api/v1/orders/modify",
        "/api/v1/orders/cancel",
    ):
        assert forbidden not in source


def test_owner_research_screen_is_canonical_navigation_surface() -> None:
    screen = _text(RESEARCH_SCREEN)
    shell = _text(OWNER_SHELL)
    assert "Backtests / Walk-Forward" in screen
    assert "Run Backtest" in screen
    assert "Run Walk-Forward" in screen
    assert "Cancel" in screen
    assert 'from "./authoritative/ResearchOperations"' in shell
    assert 'case "research": return <ResearchOperations />;' in shell
