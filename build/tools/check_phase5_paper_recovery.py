"""Static Phase-5 P5-01 paper/recovery boundary guard.

The initial scope is intentionally narrow: pure paper contracts and the
operational-state authority. Later Phase-5 slices extend the guarded file set
rather than weakening these rules.
"""
from __future__ import annotations

import ast
from pathlib import Path


REQUIRED = (
    "build/tools/check_phase5_paper_recovery.py",
    "engine/paper/contracts_v2.py",
    "engine/paper/operational_state_v2.py",
    "tests_v1/test_phase5_contracts.py",
    "tests_v1/test_phase5_operational_state.py",
    "tests_v1/test_phase5_architecture_guard.py",
)

P5_01_PRODUCTION = (
    "engine/paper/contracts_v2.py",
    "engine/paper/operational_state_v2.py",
)

FORBIDDEN_IMPORT_ROOTS = (
    "engine.broker_adapters",
    "engine.live",
    "sqlite3",
    "requests",
    "httpx",
    "telegram",
    "win32api",
    "win32con",
)

EXPECTED_OPERATIONAL_STATES = (
    "HEALTHY",
    "DEGRADED",
    "HALTED",
    "RECOVERY",
    "READY_FOR_RESUME",
)


def _import_names(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom):
            yield node.lineno, node.module or ""


def _matches_forbidden(name: str) -> bool:
    return any(
        name == banned or name.startswith(banned + ".")
        for banned in FORBIDDEN_IMPORT_ROOTS
    )


def _numeric_literal(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool)


def _storm_threshold_issues(tree: ast.AST, file: Path) -> list[str]:
    issues: list[str] = []
    for node in ast.walk(tree):
        target_name: str | None = None
        value: ast.AST | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target_name = node.targets[0].id
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_name = node.target.id
            value = node.value
        if not target_name or value is None:
            continue
        upper = target_name.upper()
        if "STORM" not in upper:
            continue
        if not any(marker in upper for marker in ("THRESHOLD", "TRIGGER_COUNT", "WINDOW")):
            continue
        if _numeric_literal(value):
            issues.append(
                f"guessed production storm threshold {file}:{getattr(node, 'lineno', '?')}: {target_name}"
            )
    return issues


def _state_vocabulary(root: Path) -> tuple[str, ...] | None:
    file = root / "engine/paper/contracts_v2.py"
    if not file.is_file():
        return None
    try:
        tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
    except (SyntaxError, UnicodeError):
        return None
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "PaperOperationalState":
            continue
        names: list[str] = []
        for item in node.body:
            if isinstance(item, ast.Assign) and len(item.targets) == 1 and isinstance(item.targets[0], ast.Name):
                if item.targets[0].id.startswith("_"):
                    continue
                names.append(item.targets[0].id)
        return tuple(names)
    return None


def _files_to_scan(root: Path, *, check_presence: bool) -> tuple[Path, ...]:
    if check_presence:
        return tuple(root / relative for relative in P5_01_PRODUCTION)
    paper_dir = root / "engine/paper"
    if not paper_dir.is_dir():
        return ()
    return tuple(sorted(paper_dir.rglob("*.py")))


def verify(
    root: Path,
    *,
    check_presence: bool = True,
    check_state_vocabulary: bool = True,
) -> tuple[str, ...]:
    issues: list[str] = []

    if check_presence:
        issues.extend(
            "missing " + relative
            for relative in REQUIRED
            if not (root / relative).is_file()
        )

    for file in _files_to_scan(root, check_presence=check_presence):
        if not file.is_file():
            continue
        try:
            tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        except (SyntaxError, UnicodeError) as exc:
            issues.append(f"syntax {file}: {exc}")
            continue
        for lineno, name in _import_names(tree):
            if _matches_forbidden(name):
                issues.append(f"forbidden import {file}:{lineno}: {name}")
        issues.extend(_storm_threshold_issues(tree, file))

    if check_state_vocabulary:
        actual = _state_vocabulary(root)
        if actual != EXPECTED_OPERATIONAL_STATES:
            issues.append(
                "operational state vocabulary mismatch: "
                f"expected={EXPECTED_OPERATIONAL_STATES!r} actual={actual!r}"
            )

    return tuple(issues)


if __name__ == "__main__":
    problems = verify(Path(__file__).resolve().parents[2])
    if problems:
        raise SystemExit("\n".join(problems))
    print("Phase-5 P5-01 paper/recovery static guard: PASS")
