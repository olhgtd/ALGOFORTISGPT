"""Static safety guard for AlgoFortis V2 Phase 5 paper/recovery code.

This guard starts with the approved P5-01 domain boundary and is extended by
later Phase-5 slices.  It deliberately uses source inspection rather than
importing runtime modules so it can validate synthetic fixtures in tests.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re


EXPECTED_OPERATIONAL_STATES = (
    "HEALTHY",
    "DEGRADED",
    "HALTED",
    "RECOVERY",
    "READY_FOR_RESUME",
)

REQUIRED = (
    "engine/paper/contracts_v2.py",
    "engine/paper/operational_state_v2.py",
    "tests_v1/test_phase5_contracts.py",
    "tests_v1/test_phase5_operational_state.py",
    "tests_v1/test_phase5_architecture_guard.py",
    "build/tools/check_phase5_paper_recovery.py",
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

_STORM_CONSTANT = re.compile(
    r"(?im)^\s*(?:PRODUCTION_)?STORM_(?:TRIGGER_COUNT|WINDOW|WINDOW_SECONDS|THRESHOLD)\s*=\s*\d+"
)


def _import_names(source: str) -> tuple[str, ...]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ()
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return tuple(names)


def _is_forbidden_import(name: str) -> str | None:
    for root in FORBIDDEN_IMPORT_ROOTS:
        if name == root or name.startswith(root + "."):
            return root
    return None


def _state_vocabulary(source: str) -> tuple[str, ...] | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "PaperOperationalState":
            continue
        values: list[str] = []
        for item in node.body:
            if not isinstance(item, ast.Assign) or len(item.targets) != 1:
                continue
            target = item.targets[0]
            if not isinstance(target, ast.Name):
                continue
            if isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
                values.append(item.value.value)
        return tuple(values)
    return None


def verify(
    root: Path,
    *,
    check_presence: bool = True,
    check_state_vocabulary: bool = True,
) -> tuple[str, ...]:
    root = Path(root)
    problems: list[str] = []

    if check_presence:
        for relative in REQUIRED:
            if not (root / relative).is_file():
                problems.append(f"missing required Phase-5 file: {relative}")

    paper_root = root / "engine" / "paper"
    if paper_root.is_dir():
        for path in sorted(paper_root.rglob("*.py")):
            try:
                source = path.read_text(encoding="utf-8")
            except OSError as error:
                problems.append(f"cannot read {path}: {error}")
                continue
            relative = path.relative_to(root).as_posix()
            for imported in _import_names(source):
                forbidden = _is_forbidden_import(imported)
                if forbidden:
                    problems.append(f"{relative}: forbidden import root {forbidden}")
            if _STORM_CONSTANT.search(source):
                problems.append(
                    f"{relative}: guessed production storm threshold constant is forbidden"
                )

    if check_state_vocabulary:
        contracts = root / "engine" / "paper" / "contracts_v2.py"
        if contracts.is_file():
            try:
                actual = _state_vocabulary(contracts.read_text(encoding="utf-8"))
            except OSError as error:
                problems.append(f"cannot read {contracts}: {error}")
            else:
                if actual != EXPECTED_OPERATIONAL_STATES:
                    problems.append(
                        "operational state vocabulary drift: "
                        f"expected {EXPECTED_OPERATIONAL_STATES!r}, got {actual!r}"
                    )
        elif not check_presence:
            problems.append("operational state vocabulary unavailable")

    return tuple(problems)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    problems = verify(root)
    if problems:
        for problem in problems:
            print(f"PHASE5_PAPER_RECOVERY_STATIC_FAIL: {problem}")
        return 1
    print("PHASE5_PAPER_RECOVERY_STATIC_PASS: P5-01 boundaries and safety vocabulary locked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
