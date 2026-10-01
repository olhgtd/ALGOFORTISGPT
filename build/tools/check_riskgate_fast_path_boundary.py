"""Static fail-closed boundary guard for RiskGateV2 fast-path modules."""
from __future__ import annotations

import ast
from pathlib import Path, PurePosixPath
import re


FORBIDDEN_BROKER_PREFIXES = (
    "engine.broker",
    "engine.broker_adapters",
    "engine.execution.live",
    "engine.live",
)
FORBIDDEN_MUTATION_TOKENS = (
    "place_order",
    "submit_order",
    "modify_order",
    "cancel_order",
)
FORBIDDEN_LIVE_TOKENS = (
    "arm_live",
    "enable_live",
    "live_arm",
    "LIVE_ARMED",
)
FORBIDDEN_AI_PREFIXES = ("engine.ai",)
PARALLEL_AUTHORITY_CLASS_NAMES = {
    "RiskIncidentStore",
    "RiskAlertDispatcher",
    "RiskOperationalState",
    "RiskAuditStore",
}


def _norm(path: str | Path) -> str:
    return PurePosixPath(str(path).replace("\\", "/")).as_posix()


def _imports(source: str, *, path: str) -> tuple[str, ...]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return ()
    values: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            values.append(node.module)
    return tuple(values)


def _class_names(source: str, *, path: str) -> tuple[str, ...]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return ()
    return tuple(node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef))


def _governed(path: str) -> bool:
    if path == "engine/paper/warm_handoff_v2.py":
        return True
    if path == "build/tools/benchmark_riskgate_fast_path.py":
        return True
    if path.startswith("engine/risk/") and any(
        token in PurePosixPath(path).name
        for token in ("fast_path", "snapshot_", "latency_")
    ):
        return True
    return False


def check_source_text(path: str, source: str) -> list[str]:
    path = _norm(path)
    failures: list[str] = []
    if not _governed(path):
        return failures

    for module in _imports(source, path=path):
        if any(module == prefix or module.startswith(prefix + ".") for prefix in FORBIDDEN_BROKER_PREFIXES):
            failures.append(f"{path}: forbidden broker import {module}")
        if any(module == prefix or module.startswith(prefix + ".") for prefix in FORBIDDEN_AI_PREFIXES):
            failures.append(f"{path}: AI/Laya authority import {module}")

    for token in FORBIDDEN_MUTATION_TOKENS:
        if token in source:
            failures.append(f"{path}: forbidden mutation token {token!r}")
    for token in FORBIDDEN_LIVE_TOKENS:
        if token in source:
            failures.append(f"{path}: Live mutation token {token!r}")
    if "_mint_approved_order" in source:
        failures.append(f"{path}: direct ApprovedOrder mint is forbidden outside canonical RiskGate/order contracts")

    if path != "engine/risk/latency_policy_v2.py":
        if "RiskGateLatencyPolicy(" in source and re.search(r"ceiling_ns\s*=\s*\d+", source):
            failures.append(f"{path}: hardcoded latency policy literal is forbidden")

    for name in _class_names(source, path=path):
        if name in PARALLEL_AUTHORITY_CLASS_NAMES:
            failures.append(f"{path}: parallel safety authority class {name} is forbidden")

    return failures


def _candidate_files(root: Path) -> list[Path]:
    files: list[Path] = []
    risk = root / "engine" / "risk"
    if risk.is_dir():
        for path in risk.glob("*.py"):
            name = path.name
            if any(token in name for token in ("fast_path", "snapshot_", "latency_")):
                files.append(path)
    for relative in (
        "engine/paper/warm_handoff_v2.py",
        "build/tools/benchmark_riskgate_fast_path.py",
    ):
        path = root / relative
        if path.is_file():
            files.append(path)
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
    print("RiskGateV2 fast-path boundary: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
