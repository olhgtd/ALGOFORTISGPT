from __future__ import annotations

from pathlib import Path

from dashboard.backend.owner_admin.step_up import classify_destructive_route

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "dashboard" / "backend" / "api.py"
CLIENT = ROOT / "dashboard" / "owner-dashboard" / "authoritative" / "paperOps.ts"
SCREEN = ROOT / "dashboard" / "owner-dashboard" / "authoritative" / "PaperOperations.tsx"
SHELL = ROOT / "dashboard" / "owner-dashboard" / "OwnerDashboardApp.tsx"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_owner_paper_hold_release_is_split_and_step_up_protected() -> None:
    api = _text(API)
    assert '@app.post("/api/v1/owner/paper/sessions/{session_id}/hold")' in api
    assert '@app.post("/api/v1/owner/paper/sessions/{session_id}/release-hold")' in api
    assert "PAPER_HOLD_RELEASE" in _text(ROOT / "dashboard" / "backend" / "owner_admin" / "step_up.py")
    assert classify_destructive_route(
        "POST", "/api/v1/owner/paper/sessions/PS-1/release-hold"
    ) == ("PAPER_HOLD_RELEASE", "PS-1")


def test_owner_paper_client_uses_simulated_paper_authority_only() -> None:
    source = _text(CLIENT)
    for expected in (
        "/api/v1/owner/paper/sessions?limit=200",
        "/api/v1/paper/sessions",
        "/start",
        "/stop",
        "/positions",
        "/orders",
        "/events",
        "/hold",
        "/release-hold",
    ):
        assert expected in source
    for forbidden in (
        "/api/v1/live/arm",
        "/api/v1/broker/orders",
        "/api/v1/orders/place",
        "/api/v1/orders/modify",
        "/api/v1/orders/cancel",
    ):
        assert forbidden not in source


def test_paper_operations_is_the_canonical_owner_paper_surface() -> None:
    screen = _text(SCREEN)
    shell = _text(SHELL)
    for label in ("Create Paper Session", "Start", "Stop", "HOLD", "Release HOLD", "Positions", "Orders", "Events", "UNAVAILABLE"):
        assert label in screen
    assert 'from "./authoritative/PaperOperations"' in shell
    assert 'case "paper": return <PaperOperations />;' in shell
