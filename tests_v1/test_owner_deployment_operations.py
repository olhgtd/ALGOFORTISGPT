from __future__ import annotations

import re
from pathlib import Path
from dashboard.backend.owner_admin.step_up import classify_destructive_route

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "dashboard" / "backend" / "api.py"
CLIENT = ROOT / "dashboard" / "owner-dashboard" / "authoritative" / "deploymentOps.ts"
SCREEN = ROOT / "dashboard" / "owner-dashboard" / "authoritative" / "DeploymentOperations.tsx"
SHELL = ROOT / "dashboard" / "owner-dashboard" / "OwnerDashboardApp.tsx"


def t(path: Path) -> str: return path.read_text(encoding="utf-8")


def test_owner_deployment_routes_are_installation_wide_and_bounded() -> None:
    source = t(API)
    for route in (
        '@app.get("/api/v1/owner/deployments")',
        '@app.get("/api/v1/owner/deployments/recovery")',
        '@app.post("/api/v1/owner/deployments/{deployment_id}/pause")',
        '@app.post("/api/v1/owner/deployments/{deployment_id}/resume")',
        '@app.post("/api/v1/owner/deployments/{deployment_id}/stop")',
    ):
        assert route in source
    assert re.search(r"list_deployments\(\s*(?:user_id\s*=\s*)?None", source)
    assert re.search(r"recovery_snapshot\(\s*(?:user_id\s*=\s*)?None", source)


def test_resume_and_stop_are_step_up_bound() -> None:
    assert classify_destructive_route("POST", "/api/v1/owner/deployments/D-1/resume") == ("DEPLOYMENT_CONTROL", "D-1")
    assert classify_destructive_route("POST", "/api/v1/owner/deployments/D-1/stop") == ("DEPLOYMENT_CONTROL", "D-1")


def test_owner_deployment_client_exposes_live_paper_only_and_no_broker_mutation() -> None:
    source = t(CLIENT)
    assert 'execution_mode: "LIVE_PAPER"' in source
    assert 'execution_mode: "LIVE"' not in source
    assert "/api/v1/owner/deployments" in source
    for forbidden in ("/api/v1/live/arm", "/api/v1/broker/orders", "/api/v1/orders/place", "/api/v1/orders/modify", "/api/v1/orders/cancel"):
        assert forbidden not in source


def test_deployment_operations_is_canonical_owner_surface() -> None:
    assert "LIVE_PAPER" in t(SCREEN)
    assert "Recovery" in t(SCREEN)
    shell = t(SHELL)
    assert 'from "./authoritative/DeploymentOperations"' in shell
    assert 'case "deployments": return <DeploymentOperations />;' in shell
