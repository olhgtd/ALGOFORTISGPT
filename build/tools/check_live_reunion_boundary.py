"""Static fail-closed boundary guard for the V1 -> V2 Live reunion."""
from __future__ import annotations

import ast
from pathlib import Path, PurePosixPath


LEGACY_MUTATION_ADAPTER = "engine.broker_adapters.angel_adapter"
CANONICAL_MINT_PATHS = {
    "engine/orders/contracts_v2.py",
    "engine/risk/gate_v2.py",
}
CANONICAL_ARM_PATHS = {"engine/live/state_machine_v2.py"}
CANONICAL_MUTATION_PATHS = {
    "engine/live/execution_coordinator_v2.py",
    "engine/broker_adapters/angelone_v2/mutation_seam_v2.py",
}
MUTATION_GATE_PATH = "engine/live/mutation_release_gate_v2.py"
NONCANONICAL_ROOTS = (
    "dashboard/",
    "engine/ai/",
    "engine/alerts/",
    "engine/backtest/",
    "engine/paper/",
    "engine/persistence/",
    "engine/reporting/",
    "engine/strategies/",
    "engine/strategy/",
)
DIRECT_MUTATION_CALLS = (
    "place_order",
    "submit_order",
    "modify_order",
    "cancel_order",
)
LIVE_PORT_MUTATION_CALLS = ("place", "cancel")
AUTO_ARM_CALLS = (
    "arm_live",
    "auto_arm",
    "enable_live",
    "live_arm",
)
RECONNECT_AUTHORITY_NAMES = {
    "ReconnectGenerationAuthority",
    "ReconnectAuthority",
    "GenerationAuthority",
}
SCAN_ROOTS = (
    "dashboard/backend",
    "engine/ai",
    "engine/alerts",
    "engine/backtest",
    "engine/broker_adapters/angelone_v2",
    "engine/live",
    "engine/paper",
    "engine/persistence",
    "engine/reconciliation",
    "engine/reporting",
    "engine/risk",
    "engine/strategies",
    "engine/strategy",
)


def _norm(path: str | Path) -> str:
    return PurePosixPath(str(path).replace("\\", "/")).as_posix()


def _tree(source: str, *, path: str) -> ast.AST | None:
    try:
        return ast.parse(source, filename=path)
    except SyntaxError:
        return None


def _imports(source: str, *, path: str) -> tuple[str, ...]:
    tree = _tree(source, path=path)
    if tree is None:
        return ()
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.append(node.module)
    return tuple(modules)


def _class_names(source: str, *, path: str) -> tuple[str, ...]:
    tree = _tree(source, path=path)
    if tree is None:
        return ()
    return tuple(node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef))


def _call_names(source: str, *, path: str) -> tuple[str, ...]:
    tree = _tree(source, path=path)
    if tree is None:
        return ()
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            names.append(func.id)
        elif isinstance(func, ast.Attribute):
            names.append(func.attr)
    return tuple(names)


def _is_noncanonical_runtime(path: str) -> bool:
    return path.startswith(NONCANONICAL_ROOTS)


def check_source_text(path: str, source: str) -> list[str]:
    path = _norm(path)
    failures: list[str] = []
    if not path.endswith(".py") or path.startswith("tests_v1/"):
        return failures

    imports = _imports(source, path=path)
    for module in imports:
        if module == LEGACY_MUTATION_ADAPTER or module.startswith(LEGACY_MUTATION_ADAPTER + "."):
            if path != "engine/broker_adapters/angel_adapter.py":
                failures.append(f"{path}: legacy mutation adapter import {module} is forbidden")
        if module.startswith("engine.broker_adapters.") and _is_noncanonical_runtime(path):
            failures.append(f"{path}: direct broker mutation authority import {module} is forbidden")

    calls = _call_names(source, path=path)
    if _is_noncanonical_runtime(path) and path not in CANONICAL_MUTATION_PATHS:
        for name in DIRECT_MUTATION_CALLS:
            if name in calls:
                failures.append(f"{path}: direct broker mutation call {name!r} is forbidden")

    if path.startswith("engine/live/") and path not in CANONICAL_MUTATION_PATHS:
        for name in LIVE_PORT_MUTATION_CALLS:
            if name in calls:
                failures.append(f"{path}: direct Live broker mutation call {name!r} is forbidden")

    if "_mint_approved_order" in calls and path not in CANONICAL_MINT_PATHS:
        failures.append(f"{path}: direct ApprovedOrder mint is forbidden outside RiskGateV2")

    class_names = _class_names(source, path=path)
    for name in class_names:
        if name in RECONNECT_AUTHORITY_NAMES or ("Reconnect" in name and "Authority" in name):
            failures.append(f"{path}: second reconnect/generation authority class {name} is forbidden")

    if path == MUTATION_GATE_PATH:
        for name in class_names:
            if name in {"LiveMutationReleaseGate", "ClosedLiveMutationReleaseGate", "LiveMutationBlocked"}:
                continue
            lowered = name.casefold()
            if "livemutation" in lowered and "gate" in lowered:
                failures.append(f"{path}: production open mutation gate class {name} is forbidden")

    if path not in CANONICAL_ARM_PATHS:
        for name in AUTO_ARM_CALLS:
            if name in calls:
                failures.append(f"{path}: restart/recovery auto-arm call {name!r} is forbidden")

    return failures


def _candidate_files(root: Path) -> list[Path]:
    files: set[Path] = set()
    for relative in SCAN_ROOTS:
        base = root / relative
        if base.is_dir():
            files.update(path for path in base.rglob("*.py") if "__pycache__" not in path.parts)
    return sorted(files)


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
    print("LIVE_REUNION_BOUNDARY_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
