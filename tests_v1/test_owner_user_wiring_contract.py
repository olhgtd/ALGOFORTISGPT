"""Wiring contract: the Owner step-up policy and the Owner/User frontends may only
reference routes that really exist on the booted runtime app.

Regression guard for a real defect: the step-up policy protected
`/api/v1/owner/settings/confirm` and the Owner UI called `/api/v1/owner/settings*`,
while the backend serves `/api/v1/settings*` - so the real settings-confirm route had
no WebAuthn step-up and the Owner settings page received 404/405.
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest

import dashboard.runtime.application as application
from dashboard.backend.owner_admin.step_up import ROUTES as STEP_UP_ROUTES
from dashboard.runtime.paths import RuntimeMode, RuntimePaths

ROOT = Path(__file__).resolve().parents[1]
AUTHORITATIVE = ROOT / "dashboard" / "owner-dashboard" / "authoritative"


class _AllowAcl:
    def validate(self, path) -> bool: return True
    def create(self, path) -> bool: return True


def _flatten(routes, prefix=""):
    for route in routes:
        if hasattr(route, "original_router"):
            yield from _flatten(route.original_router.routes, prefix + (route.include_context.prefix or ""))
        elif getattr(route, "methods", None):
            for method in route.methods:
                if method not in {"HEAD", "OPTIONS"}:
                    yield method, prefix + route.path


@pytest.fixture(scope="module")
def real_routes():
    with tempfile.TemporaryDirectory(prefix="algo-wiring-") as tmp:
        install = Path(tmp) / "install"
        (install / "dashboard" / "web" / "dist").mkdir(parents=True)
        (install / "dashboard" / "web" / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")
        data = Path(tmp) / "data"
        paths = RuntimePaths.resolve(RuntimeMode.DEVELOPMENT, install_root=install, data_root=data)
        for directory in (paths.databases, paths.cache, paths.artifacts, paths.config, paths.imports):
            Path(directory).mkdir(parents=True, exist_ok=True)
        original = application.CurrentUserAcl
        application.CurrentUserAcl = _AllowAcl
        try:
            app = application.create_runtime_app(paths, "http://localhost:8000", "wiring-contract")
            routes = list(_flatten(app.routes))
        finally:
            application.CurrentUserAcl = original
        yield routes


def _sample(template: str) -> str:
    return re.sub(r"\{[^}]*\}", "sample-id", template)


def test_runtime_app_registers_the_expected_surface(real_routes) -> None:
    paths = {path for _, path in real_routes}
    assert len(paths) > 150
    for required in ("/api/v1/settings", "/api/v1/settings/propose", "/api/v1/settings/confirm",
                     "/api/v1/owner/admin/authority", "/api/v1/user/live-readiness", "/api/v1/owner/live-readiness"):
        assert required in paths, f"missing real route: {required}"


@pytest.mark.parametrize("item", STEP_UP_ROUTES, ids=lambda item: f"{item.method} {item.pattern.pattern}")
def test_every_step_up_policy_entry_protects_a_real_route(real_routes, item) -> None:
    matches = [(m, p) for m, p in real_routes if m == item.method and item.pattern.match(_sample(p))]
    assert matches, f"step-up policy protects a route that does not exist: {item.method} {item.pattern.pattern}"


def _owner_frontend_paths() -> set[str]:
    found: set[str] = set()
    for file in AUTHORITATIVE.glob("*.ts*"):
        if ".test." in file.name:
            continue
        for raw in re.findall(r"[`\"'](/api/v1/[^`\"'?\s]*)", file.read_text(encoding="utf-8")):
            path = re.sub(r"\$\{[^}]*\}", "sample-id", raw).rstrip("/")
            if path.endswith("/sample-id") and path.count("/sample-id") >= 2:
                continue  # dynamic action suffix, validated separately below
            found.add(path)
    return found


def test_owner_frontend_calls_only_real_backend_routes(real_routes) -> None:
    real = [_sample(p) for _, p in real_routes]
    patterns = [re.compile("^" + re.escape(p).replace("sample\\-id", "[^/]+") + "/?$") for p in real]
    missing = sorted(p for p in _owner_frontend_paths() if not any(rx.match(p) for rx in patterns))
    assert missing == [], f"Owner UI calls routes the backend does not serve: {missing}"


def test_owner_frontend_dynamic_actions_exist_on_backend(real_routes) -> None:
    text = (AUTHORITATIVE / "api.ts").read_text(encoding="utf-8")
    access = set(re.findall(r'"(suspend|restore|revoke|reissue-activation|revoke-activation|extend-service|renew-service|convert-lifetime)"', text))
    strategy = set(re.findall(r'"(allowance|visibility|promote)"', text)) | {"suspend", "restore"}
    real = {p for _, p in real_routes}
    for action in access:
        assert f"/api/v1/owner/access/users/{{identifier}}/{action}" in real, action
    for action in strategy:
        assert f"/api/v1/owner/strategies/{{strategy_id}}/{action}" in real, action
