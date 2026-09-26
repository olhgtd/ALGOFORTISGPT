"""Static architecture firewall for AlgoFortis Phase-7 portfolio/risk code."""
from __future__ import annotations

import ast
import re
from pathlib import Path

REQUIRED = (
    "engine/portfolio/v2/contracts.py",
    "build/tools/check_phase7_portfolio_risk.py",
    "tests_v1/test_phase7_contracts.py",
    "tests_v1/test_phase7_architecture_guard.py",
)
FORBIDDEN_ROOTS = ("engine.broker_adapters", "engine.live", "engine.ai")
THRESHOLD_RE = re.compile(
    r"(?im)^\s*(?:DEFAULT|PRODUCTION)_(?:BUDGET|EXPOSURE|DAILY_LOSS|DRAWDOWN|SIZE_FRACTION)\s*=\s*[\"']?\d"
)


def _imports(tree: ast.AST) -> tuple[str, ...]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return tuple(names)


def _paths(root: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    portfolio = root / "engine" / "portfolio" / "v2"
    if portfolio.is_dir():
        paths.extend(portfolio.rglob("*.py"))
    risk = root / "engine" / "risk"
    if risk.is_dir():
        names = {"portfolio_v2.py", "portfolio_admission_v2.py", "event_day_policy_v2.py"}
        paths.extend(path for path in risk.glob("*v2.py") if path.name in names)
    return tuple(sorted(set(paths)))


def verify(root: Path, *, check_presence: bool = True) -> tuple[str, ...]:
    root = Path(root)
    problems: list[str] = []
    if check_presence:
        for relative in REQUIRED:
            if not (root / relative).is_file():
                problems.append(f"missing required Phase-7 file: {relative}")

    for path in _paths(root):
        relative = path.relative_to(root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as error:
            problems.append(f"cannot read {relative}: {error}")
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError as error:
            problems.append(f"{relative}: syntax error {error}")
            continue

        for imported in _imports(tree):
            for forbidden in FORBIDDEN_ROOTS:
                if imported == forbidden or imported.startswith(forbidden + "."):
                    problems.append(f"{relative}: forbidden import root {forbidden}")

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "_mint_approved_order":
                        problems.append(f"{relative}: _mint_approved_order import is forbidden")
            if isinstance(node, ast.Call):
                name: str | None = None
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                if name == "_mint_approved_order":
                    problems.append(f"{relative}: _mint_approved_order call is forbidden")
                if name == "ApprovedOrder":
                    problems.append(f"{relative}: ApprovedOrder constructor is forbidden")

        if THRESHOLD_RE.search(source):
            problems.append(
                f"{relative}: guessed production portfolio threshold constant is forbidden"
            )

    return tuple(problems)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    problems = verify(root)
    if problems:
        for problem in problems:
            print(f"PHASE7_PORTFOLIO_RISK_STATIC_FAIL: {problem}")
        return 1
    print(
        "PHASE7_PORTFOLIO_RISK_STATIC_PASS: central RiskGate authority and policy-driven portfolio boundaries locked"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
