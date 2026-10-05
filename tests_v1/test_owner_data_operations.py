from __future__ import annotations

from pathlib import Path
from dashboard.backend.owner_admin.step_up import classify_destructive_route

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "dashboard" / "backend" / "api.py"
CLIENT = ROOT / "dashboard" / "owner-dashboard" / "authoritative" / "dataOps.ts"
SCREEN = ROOT / "dashboard" / "owner-dashboard" / "authoritative" / "DataOperations.tsx"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_historical_owner_routes_already_exist() -> None:
    source = text(API)
    for route in (
        '@app.get("/api/v1/owner/historical/providers")',
        '@app.post("/api/v1/owner/historical/providers")',
        '@app.post("/api/v1/owner/historical/providers/{provider_id}/toggle")',
        '@app.post("/api/v1/owner/historical/sync/manual")',
        '@app.post("/api/v1/owner/historical/sync/schedule")',
        '@app.get("/api/v1/owner/historical/sync/schedule")',
        '@app.get("/api/v1/owner/historical/sync/jobs")',
        '@app.get("/api/v1/owner/historical/sync/jobs/{job_id}")',
        '@app.post("/api/v1/owner/historical/gaps/repair")',
    ):
        assert route in source


def test_high_impact_historical_controls_have_exact_step_up_classification() -> None:
    assert classify_destructive_route("POST", "/api/v1/owner/historical/providers") == ("HISTORICAL_PROVIDER_CONFIG", None)
    assert classify_destructive_route("POST", "/api/v1/owner/historical/providers/P-1/toggle") == ("HISTORICAL_PROVIDER_CONFIG", "P-1")
    assert classify_destructive_route("POST", "/api/v1/owner/historical/sync/schedule") == ("HISTORICAL_SYNC_POLICY", None)
    assert classify_destructive_route("POST", "/api/v1/owner/historical/gaps/repair") == ("HISTORICAL_DATA_REPAIR", None)


def test_data_client_has_write_only_secret_semantics() -> None:
    source = text(CLIENT)
    assert "api_key?: string" in source
    assert "configureHistoricalProvider" in source
    assert "ownerMutationWithStepUp" in source
    assert "rawApiKey" not in source
    screen = text(SCREEN)
    assert 'type="password"' in screen
    assert "api_key" not in screen.lower()
    assert "secret" not in screen.lower() or "write-only" in screen.lower()


def test_data_ui_covers_sync_jobs_gap_repair_and_dataset_governance() -> None:
    screen = text(SCREEN)
    for label in ("Providers", "Manual Sync", "Schedule", "Sync Jobs", "Gap Repair", "Datasets", "Retire", "Replace", "UNAVAILABLE"):
        assert label in screen
