from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
USER_ROOT = ROOT / "dashboard" / "user-dashboard"

CANONICAL_FILES = (
    USER_ROOT / "UserDashboardApp.tsx",
    USER_ROOT / "screens" / "UserHome.tsx",
    USER_ROOT / "screens" / "UserStrategies.tsx",
    USER_ROOT / "screens" / "UserTesting.tsx",
    USER_ROOT / "screens" / "UserTrades.tsx",
    USER_ROOT / "screens" / "UserPortfolio.tsx",
    USER_ROOT / "screens" / "UserAccount.tsx",
    USER_ROOT / "markets" / "UserMarkets.tsx",
    USER_ROOT / "markets" / "MarketsChart.tsx",
    USER_ROOT / "home" / "homeData.ts",
    USER_ROOT / "home" / "homeModel.ts",
    USER_ROOT / "data" / "userSurfaceData.ts",
    USER_ROOT / "data" / "userShellData.ts",
)

LEGACY_SAMPLE_MODULES = (
    "data/userStrategies",
    "data/liveOrders",
    "data/optionsChain",
    "data/userAgents",
    "data/userSecurity",
)

FORBIDDEN_EXECUTION_REFERENCES = (
    "engine.broker_adapters",
    "/api/v1/live/orders",
    "place_order(",
    "modify_order(",
    "cancel_order(",
    "_mint_approved_order(",
)


def _text(path: Path) -> str:
    assert path.is_file(), f"missing canonical user file: {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def test_normal_user_navigation_is_exactly_the_seven_frozen_routes() -> None:
    nav = _text(USER_ROOT / "navigation.ts")
    ids = re.findall(r'\{ id: "([a-z-]+)", label:', nav)
    assert ids == ["home", "markets", "strategies", "testing", "trades", "portfolio", "account"]


def test_canonical_user_surface_does_not_import_legacy_sample_data_modules() -> None:
    violations: list[str] = []
    for path in CANONICAL_FILES:
        text = _text(path)
        for module in LEGACY_SAMPLE_MODULES:
            if module in text:
                violations.append(f"{path.relative_to(ROOT)} -> {module}")
    assert not violations, "legacy sample-data imports found on canonical user surface:\n" + "\n".join(violations)


def test_canonical_user_surface_cannot_become_direct_execution_authority() -> None:
    violations: list[str] = []
    for path in CANONICAL_FILES:
        text = _text(path)
        for token in FORBIDDEN_EXECUTION_REFERENCES:
            if token in text:
                violations.append(f"{path.relative_to(ROOT)} -> {token}")
    assert not violations, "direct execution/broker mutation reference found on canonical user surface:\n" + "\n".join(violations)


def test_user_surface_keeps_live_read_only_disarmed_and_fail_closed_copy() -> None:
    combined = "\n".join(_text(path) for path in CANONICAL_FILES)
    shell = _text(USER_ROOT / "shellState.ts")
    markets = _text(USER_ROOT / "markets" / "UserMarkets.tsx")

    assert "READ_ONLY / DISARMED" in shell
    assert "No execution authority is granted from this surface" in markets
    assert "No generated CE/PE prices" in markets
    assert "UNAVAILABLE" in combined
    assert "UNKNOWN" in combined


def test_shared_shell_is_authoritative_for_all_routes_and_notifications_are_not_hard_coded_empty() -> None:
    app = _text(USER_ROOT / "UserDashboardApp.tsx")
    shell_data = _text(USER_ROOT / "data" / "userShellData.ts")

    assert "loadUserShellAuthority" in app
    assert "notifications={notifications}" in app
    assert "notifications={[]}" not in app
    assert "listUserConnections" in shell_data
    assert "listUserDeployments" in shell_data
    assert "queryPersistenceHealth" in shell_data
    assert "queryMarketChart" in shell_data
    assert "/api/v1/user/live-readiness" in shell_data


def test_home_strategy_testing_and_risk_are_no_longer_hard_coded_placeholders() -> None:
    home_data = _text(USER_ROOT / "home" / "homeData.ts")
    home_model = _text(USER_ROOT / "home" / "homeModel.ts")
    strategy_component = _text(USER_ROOT / "home" / "components" / "StrategyStatusSummary.tsx")

    assert "loadStrategiesSurface" in home_data
    assert "loadTestingSurface" in home_data
    assert "loadUserShellAuthority" in home_data
    assert "strategies: { state: \"UNAVAILABLE\", items: null }" not in home_model
    assert "testing: { state: \"UNAVAILABLE\", items: null }" not in home_model
    assert "not wired into Home yet" not in strategy_component
