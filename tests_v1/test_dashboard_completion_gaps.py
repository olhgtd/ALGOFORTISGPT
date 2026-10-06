from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_canonical_owner_users_surface_contains_full_lifecycle_controls() -> None:
    source = read("dashboard/owner-dashboard/authoritative/screens.tsx")
    for token in ("Suspend", "Restore", "Revoke", "Reissue", "Revoke invite", "Renew 3 months", "Lifetime"):
        assert token in source


def test_canonical_owner_connections_data_surface_contains_allowance_controls() -> None:
    source = read("dashboard/owner-dashboard/authoritative/DataOperations.tsx")
    for token in ("Connection Allowance", "ownerConnectionAllowance", "ownerCapabilityAllowance", "ALLOWED", "HOLD", "REVOKED"):
        assert token in source


def test_settings_proposal_is_owner_mutable_authority_bound() -> None:
    source = read("dashboard/backend/api.py")
    assert 'def propose_setting(proposal: SettingsProposalBody, session=Depends(owner_mutable_session))' in source


def test_kill_switch_bridge_is_bounded_and_fail_closed() -> None:
    adapter = read("dashboard/backend/owner_safety_adapter.py")
    api = read("dashboard/backend/api.py")
    assert "kill_switch_authority" in adapter
    assert "CANONICAL_KILL_SWITCH_BRIDGE_NOT_ATTACHED" in adapter
    assert "activate_kill_switch" in adapter
    assert '"/api/v1/owner/safety/kill-switch/engage"' in api
    for forbidden in ("/api/v1/live/arm", "/api/v1/broker/orders", "/api/v1/orders/place", "/api/v1/orders/modify", "/api/v1/orders/cancel"):
        assert forbidden not in adapter


def test_user_legacy_monolith_is_retired() -> None:
    legacy = ROOT / "dashboard" / "user-dashboard" / "screens" / "UserScreens.tsx"
    assert not legacy.exists()


def test_windows_user_package_rebuilds_on_main_push() -> None:
    workflow = read(".github/workflows/owner-user-windows-packages.yml")
    assert "push:" in workflow
    assert "branches: [main]" in workflow
    assert "AlgoFortis-User-Setup.exe" in workflow
