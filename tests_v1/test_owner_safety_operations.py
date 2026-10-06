from __future__ import annotations

from pathlib import Path
from dashboard.backend.owner_admin.step_up import classify_destructive_route

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "dashboard" / "backend" / "owner_safety_adapter.py"
API = ROOT / "dashboard" / "backend" / "api.py"
CLIENT = ROOT / "dashboard" / "owner-dashboard" / "authoritative" / "safetyOps.ts"
SCREEN = ROOT / "dashboard" / "owner-dashboard" / "authoritative" / "RiskSafetyScreen.tsx"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_safety_snapshot_never_invents_killswitch_or_live_readiness() -> None:
    source = text(ADAPTER)
    assert '"live_state": "READ_ONLY/DISARMED"' in source
    assert '"broker_mutation": "ABSENT"' in source
    assert "def _kill_switch_snapshot" in source
    assert "CANONICAL_KILL_SWITCH_BRIDGE_NOT_ATTACHED" in source
    assert '"kill_switch": self._kill_switch_snapshot()' in source
    assert "ARMED & READY" not in source
    assert "disable_kill" not in source.lower()


def test_owner_safety_routes_are_narrow_and_release_is_step_up_bound() -> None:
    api = text(API)
    assert '@app.get("/api/v1/owner/safety")' in api
    assert '@app.post("/api/v1/owner/safety/safe-mode/engage")' in api
    assert '@app.post("/api/v1/owner/safety/global-hold/engage")' in api
    assert '@app.post("/api/v1/owner/safety/global-hold/release")' in api
    assert '@app.post("/api/v1/owner/safety/kill-switch/engage")' in api
    assert classify_destructive_route("POST", "/api/v1/owner/safety/global-hold/release") == ("SAFETY_RELEASE", None)


def test_owner_safety_client_contains_no_restriction_bypass_or_broker_mutation() -> None:
    source = text(CLIENT)
    assert "engageSafeMode" in source
    assert "engageGlobalHold" in source
    assert "releaseGlobalHold" in source
    assert "engageKillSwitch" in source
    assert 'actionFamily: "SAFETY_RELEASE"' in source
    for forbidden in ("disableKillSwitch", "/api/v1/live/arm", "/api/v1/broker/orders", "/api/v1/orders/place", "/api/v1/orders/modify", "/api/v1/orders/cancel"):
        assert forbidden not in source


def test_risk_safety_ui_is_explicit_about_unavailable_authority() -> None:
    screen = text(SCREEN)
    for label in ("Risk & Safety", "READ_ONLY/DISARMED", "NOT_CONNECTED", "UNAVAILABLE", "Engage Safe Mode", "Engage Global Hold", "Release Global Hold", "Engage Kill Switch", "daily_loss_limit"):
        assert label in screen
