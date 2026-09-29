"""Static fail-closed boundary guard for canonical Owner/Admin and AI code.

This guard is intentionally dependency-free and does not import application code.
It prevents governance/research presentation code from acquiring broker mutation,
Live-arm/recovery-resume authority, legacy order-approval authority, or hidden
sample/prototype production truth.
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
)

Lाया_ROUTING_TOKENS = (
    "LayaRouter",
    "select_provider",
    "choose_provider",
    "route_agent",
    "dispatch_agent",
)

# Existing canonical Owner files are being migrated in the same implementation
# plan. The allowlist is deliberately narrow and MUST be emptied before final
# qualification; unit-level check_source_text still rejects these capabilities.
TRANSITIONAL_OWNER_ALLOWLIST = frozenset(
    {
        "dashboard/owner-dashboard/OwnerDashboardApp.tsx",
        "dashboard/owner-dashboard/screens/AdminHome.tsx",
        "dashboard/owner-dashboard/screens/AdminScreens.tsx",
        "dashboard/owner-dashboard/screens/AccessRegistryScreen.tsx",
    }
)


def _norm(path: str | Path) -> str:
    return PurePosixPath(str(path).replace("\\", "/")).as_posix()


def _is_preview_path(path: str) -> bool:
    parts = {part.lower() for part in PurePosixPath(path).parts}
    stem = PurePosixPath(path).stem.lower()
    return bool(parts & {"preview", "previews", "dev", "fixtures", "sample", "samples"}) or stem.endswith("preview")


def _python_imports(source: str, *, path: str) -> Iterable[str]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return ()
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                imports.append(node.module)
    return tuple(imports)


def check_source_text(path: str, source: str) -> list[str]:
    """Return boundary violations for one canonical Owner/Admin or AI source."""
    path = _norm(path)
    if _is_preview_path(path):
        return []

    failures: list[str] = []
    is_owner_frontend = path.startswith("dashboard/owner-dashboard/") and path.endswith((".ts", ".tsx"))
    is_owner_backend = path.startswith("dashboard/backend/owner_admin/") and path.endswith(".py")
    is_ai_engine = path.startswith("engine/ai/") and path.endswith(".py")
    is_ai_backend = path == "dashboard/backend/ai_control.py"
    governed = is_owner_frontend or is_owner_backend or is_ai_engine or is_ai_backend
    if not governed:
        return failures

    for module in _python_imports(source, path=path):
        if any(module == prefix or module.startswith(prefix + ".") for prefix in FORBIDDEN_MODULE_PREFIXES):
            failures.append(f"{path}: forbidden module {module}")

    # Text check also catches TypeScript imports and dynamic references.
    for module in FORBIDDEN_MODULE_PREFIXES:
        if module in source:
            failures.append(f"{path}: forbidden module {module}")

    for token in FORBIDDEN_AUTHORITY_TOKENS:
        if token in source:
            failures.append(f"{path}: forbidden authority token {token!r}")

    if is_owner_frontend:
        for token in FORBIDDEN_OWNER_TRUTH_TOKENS:
            if token in source:
                failures.append(f"{path}: sample/prototype authority token {token!r}")

    if path.endswith("/laya.py") or PurePosixPath(path).name.lower().startswith("laya"):
        for token in Lाया_ROUTING_TOKENS:
            if token in source:
                failures.append(f"{path}: Laya-owned routing token {token!r}")

    return failures


def _candidate_files(root: Path) -> list[Path]:
    files: list[Path] = []
    owner_root = root / "dashboard" / "owner-dashboard"
    if owner_root.is_dir():
        files.extend(path for path in owner_root.rglob("*") if path.suffix in {".ts", ".tsx"})

    owner_backend = root / "dashboard" / "backend" / "owner_admin"
    if owner_backend.is_dir():
        files.extend(owner_backend.rglob("*.py"))

    ai_engine = root / "engine" / "ai"
    if ai_engine.is_dir():
        files.extend(ai_engine.rglob("*.py"))

    ai_control = root / "dashboard" / "backend" / "ai_control.py"
    if ai_control.is_file():
        files.append(ai_control)

    return sorted(set(files))


def check_repository(root: Path | None = None) -> list[str]:
    root = (root or Path(__file__).resolve().parents[2]).resolve()
    failures: list[str] = []
    for path in _candidate_files(root):
        relative = _norm(path.relative_to(root))
        if relative in TRANSITIONAL_OWNER_ALLOWLIST:
            continue
        failures.extend(check_source_text(relative, path.read_text(encoding="utf-8")))
    return failures


def main() -> int:
    failures = check_repository()
    if failures:
        raise SystemExit("\n".join(failures))
    print("Owner/Admin + AI authority boundary: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
