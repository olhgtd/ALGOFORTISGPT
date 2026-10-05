from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OWNER_API = ROOT / "dashboard" / "owner-dashboard" / "authoritative" / "api.ts"
OWNER_SHELL = ROOT / "dashboard" / "owner-dashboard" / "OwnerDashboardApp.tsx"
USER_SHELL = ROOT / "dashboard" / "user-dashboard" / "UserDashboardApp.tsx"
LEGACY_USER_SCREENS = ROOT / "dashboard" / "user-dashboard" / "screens" / "UserScreens.tsx"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_owner_oversight_reads_use_installation_wide_owner_routes() -> None:
    source = _text(OWNER_API)
    assert 'ownerFetch<any>("/api/v1/owner/backtests?limit=200")' in source
    assert 'ownerFetch<any>("/api/v1/owner/paper/sessions?limit=200")' in source
    assert 'ownerFetch<any>("/api/v1/backtests?limit=200&offset=0")' not in source
    assert 'ownerFetch<any>("/api/v1/paper/sessions?limit=200&offset=0")' not in source


def test_canonical_owner_client_exposes_no_real_live_or_broker_order_mutation_path() -> None:
    source = _text(OWNER_API)
    forbidden = (
        "/api/v1/live/arm",
        "/api/v1/live/orders",
        "/api/v1/broker/orders",
        "/api/v1/orders/place",
        "/api/v1/orders/modify",
        "/api/v1/orders/cancel",
    )
    for token in forbidden:
        assert token not in source


def test_legacy_hardcoded_killswitch_claim_is_not_reachable_from_canonical_user_shell() -> None:
    shell = _text(USER_SHELL)
    legacy = _text(LEGACY_USER_SCREENS)
    assert "Killswitch Status:" in legacy
    assert "ARMED &amp; READY" in legacy
    assert 'from "./screens/UserScreens"' not in shell
    assert "UserScreens" not in shell


def test_canonical_owner_shell_uses_authoritative_surfaces_only() -> None:
    shell = _text(OWNER_SHELL)
    assert 'from "./authoritative/' in shell
    assert '/screens/' not in shell
    assert "sampleData" not in shell
    assert "localStorage" not in shell
