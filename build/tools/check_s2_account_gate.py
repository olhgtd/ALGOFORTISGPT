"""Fail closed if S2 account code gains trading-mutation authority."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACCOUNT_V2 = ROOT / "dashboard" / "backend" / "account_v2"
FORBIDDEN_MODULE_PREFIXES = (
    "engine.broker_adapters",
    "engine.execution",
    "engine.live",
    "engine.orders",
    "engine.risk.gate_v2",
)
FORBIDDEN_TOKENS = (
    "ApprovedOrder",
    "place_order",
    "submit_order",
    "cancel_order",
    "modify_order",
    "arm(",
)


def check() -> list[str]:
    violations: list[str] = []
    files = sorted(ACCOUNT_V2.rglob("*.py")) if ACCOUNT_V2.is_dir() else []
    if not files:
        return ["S2 account_v2 package is missing or empty"]
    for path in files:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                modules = []
            for module in modules:
                if module.startswith(FORBIDDEN_MODULE_PREFIXES):
                    violations.append(f"{path.relative_to(ROOT)} imports forbidden module {module}")
        for token in FORBIDDEN_TOKENS:
            if token in text:
                violations.append(f"{path.relative_to(ROOT)} contains forbidden capability token {token!r}")
    return violations


if __name__ == "__main__":
    failures = check()
    if failures:
        raise SystemExit("\n".join(failures))
    print("S2 account authority boundary: PASS")
