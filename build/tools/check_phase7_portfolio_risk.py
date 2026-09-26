"""Static architecture firewall for AlgoFortis Phase-7 portfolio/risk code."""
from __future__ import annotations

import ast
import re
from pathlib import Path

REQUIRED = (
    "engine/portfolio/v2/contracts.py",
    "engine/portfolio/v2/reservations.py",
    "engine/portfolio/v2/exposure.py",
    "engine/portfolio/v2/circuit_breaker.py",
    "engine/portfolio/v2/attribution.py",
    "engine/portfolio/v2/evidence.py",
    "engine/risk/event_day_policy_v2.py",
    "engine/risk/portfolio_v2.py",
    "engine/risk/portfolio_admission_v2.py",
    "build/tools/check_phase7_portfolio_risk.py",
    "build/tools/phase7_probe.py",
    ".github/workflows/v2-phase7-portfolio-risk.yml",
    "docs/v2/phase7/G7_EVIDENCE.md",
    "tests_v1/test_phase7_contracts.py",
    "tests_v1/test_phase7_architecture_guard.py",
    "tests_v1/test_phase7_reservations.py",
    "tests_v1/test_phase7_exposure.py",
    "tests_v1/test_phase7_circuit_breaker.py",
    "tests_v1/test_phase7_event_day_policy.py",
    "tests_v1/test_phase7_portfolio_evaluator.py",
    "tests_v1/test_phase7_riskgate_integration.py",
    "tests_v1/test_phase7_attribution.py",
    "tests_v1/test_phase7_evidence.py",
    "tests_v1/test_phase7_qualification_guard.py",
)
FORBIDDEN_ROOTS = ("engine.broker_adapters", "engine.live", "engine.ai")
FORBIDDEN_IO_ROOTS = ("requests", "httpx", "sqlite3", "sqlalchemy", "urllib.request")
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
            for forbidden in (*FORBIDDEN_ROOTS, *FORBIDDEN_IO_ROOTS):
                if imported == forbidden or imported.startswith(forbidden + "."):
                    problems.append(f"{relative}: forbidden import root {forbidden}")

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in {"_mint_approved_order", "ApprovedOrder"}:
                        problems.append(f"{relative}: {alias.name} import is forbidden")
            if isinstance(node, ast.Call):
                name: str | None = None
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                if name in {"_mint_approved_order", "ApprovedOrder"}:
                    problems.append(f"{relative}: {name} call is forbidden")

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
