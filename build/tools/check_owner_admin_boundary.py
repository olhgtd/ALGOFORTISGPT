"""Static fail-closed boundary guard for canonical Owner/Admin, AI, and entry-gate code.

Legacy V1 Owner screens remain in the repository as UI donors, but production
navigation resolves only through the canonical Owner shell and authoritative
adapters.  The entry gate is also governed because authentication code must
never acquire broker mutation, RiskGate approval, or sample/localStorage
identity authority.
"""
from __future__ import annotations

import ast
from pathlib import Path, PurePosixPath
from typing import Iterable


FORBIDDEN_MODULE_PREFIXES = (
    "engine.broker_adapters",
    "engine.execution",
    "engine.live",
)

FORBIDDEN_AUTHORITY_TOKENS = (
    "place_order",
    "submit_order",
    "modify_order",
    "cancel_order",
    "_mint_approved_order",
)

FORBIDDEN_OWNER_TRUTH_TOKENS = (
    "sampleData",
    "localStorage",
    "SAMPLE_FALLBACK",
    "simulateFirstActivation",
    "generatePrototypeActivationCode",
    "generatePrototypeAlgoFortisId",
)

LAYA_ROUTING_TOKENS = (
    "LayaRouter",
    "select_provider",
    "choose_provider",
    "route_agent",
    "dispatch_agent",
)

ENTRY_FRONTEND_FILES = frozenset({
    "dashboard/web/src/visual-lab/secure-entry/SecureEntryApp.tsx",
    "dashboard/web/src/visual-lab/secure-entry/FirstTimeCustomerFlow.tsx",
    "dashboard/web/src/visual-lab/secure-entry/ReturningUserFlow.tsx",
    "dashboard/web/src/visual-lab/secure-entry/LocalOwnerSetupCard.tsx",
})

ENTRY_BACKEND_FILES = frozenset({
    "dashboard/backend/account_v2/password_accounts.py",
    "dashboard/backend/account_v2/password_router.py",
    "dashboard/backend/account_v2/owner_bootstrap.py",
})


def _norm(path: str | Path) -> str:
    return PurePosixPath(str(path).replace("\\", "/")).as_posix()


def _python_imports(source: str, *, path: str) -> Iterable[str]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return ()
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.append(node.module)
    return tuple(imports)


def check_source_text(path: str, source: str) -> list[str]:
    path = _norm(path)
    failures: list[str] = []

    is_owner_shell = path == "dashboard/owner-dashboard/OwnerDashboardApp.tsx"
    is_owner_frontend = path.startswith("dashboard/owner-dashboard/authoritative/") and path.endswith((".ts", ".tsx"))
    is_owner_backend = path.startswith("dashboard/backend/owner_admin/") and path.endswith(".py")
    is_ai_engine = path.startswith("engine/ai/") and path.endswith(".py")
    is_ai_backend = path == "dashboard/backend/ai_control.py"
    is_entry_frontend = path in ENTRY_FRONTEND_FILES
    is_entry_backend = path in ENTRY_BACKEND_FILES
    governed = (
        is_owner_shell
        or is_owner_frontend
        or is_owner_backend
        or is_ai_engine
        or is_ai_backend
        or is_entry_frontend
        or is_entry_backend
    )
    if not governed:
        return failures

    for module in _python_imports(source, path=path):
        if any(module == prefix or module.startswith(prefix + ".") for prefix in FORBIDDEN_MODULE_PREFIXES):
            failures.append(f"{path}: forbidden module {module}")

    for module in FORBIDDEN_MODULE_PREFIXES:
        if module in source:
            failures.append(f"{path}: forbidden module {module}")

    for token in FORBIDDEN_AUTHORITY_TOKENS:
        if token in source:
            failures.append(f"{path}: forbidden authority token {token!r}")

    if is_owner_shell or is_owner_frontend or is_entry_frontend:
        for token in FORBIDDEN_OWNER_TRUTH_TOKENS:
            if token in source:
                failures.append(f"{path}: sample/prototype authority token {token!r}")

    if path.endswith("/laya.py") or PurePosixPath(path).name.lower().startswith("laya"):
        for token in LAYA_ROUTING_TOKENS:
            if token in source:
                failures.append(f"{path}: Laya-owned routing token {token!r}")

    if is_owner_shell and "/screens/" in source:
        failures.append(f"{path}: canonical Owner shell must not import legacy donor screens")

    return failures


def _candidate_files(root: Path) -> list[Path]:
    files: list[Path] = []
    shell = root / "dashboard" / "owner-dashboard" / "OwnerDashboardApp.tsx"
    if shell.is_file():
        files.append(shell)

    authoritative = root / "dashboard" / "owner-dashboard" / "authoritative"
    if authoritative.is_dir():
        files.extend(path for path in authoritative.rglob("*") if path.suffix in {".ts", ".tsx"})

    owner_backend = root / "dashboard" / "backend" / "owner_admin"
    if owner_backend.is_dir():
        files.extend(owner_backend.rglob("*.py"))

    ai_engine = root / "engine" / "ai"
    if ai_engine.is_dir():
        files.extend(ai_engine.rglob("*.py"))

    ai_control = root / "dashboard" / "backend" / "ai_control.py"
    if ai_control.is_file():
        files.append(ai_control)

    for relative in sorted(ENTRY_FRONTEND_FILES | ENTRY_BACKEND_FILES):
        candidate = root / relative
        if candidate.is_file():
            files.append(candidate)

    return sorted(set(files))


def check_repository(root: Path | None = None) -> list[str]:
    root = (root or Path(__file__).resolve().parents[2]).resolve()
    failures: list[str] = []
    for path in _candidate_files(root):
        relative = _norm(path.relative_to(root))
        failures.extend(check_source_text(relative, path.read_text(encoding="utf-8")))
    return failures


def main() -> int:
    failures = check_repository()
    if failures:
        raise SystemExit("\n".join(failures))
    print("Owner/Admin + AI + entry-gate authority boundary: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
