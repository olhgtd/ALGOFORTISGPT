from __future__ import annotations

import ast
from pathlib import Path


ACCOUNT_V2 = Path("dashboard/backend/account_v2")

FORBIDDEN_MODULE_PREFIXES = (
    "engine.broker_adapters",
    "engine.execution",
    "engine.live",
    "engine.orders",
    "engine.risk.gate_v2",
)

FORBIDDEN_AUTHORITY_TOKENS = (
    "ApprovedOrder",
    "place_order",
    "submit_order",
    "cancel_order",
    "modify_order",
    "arm(",
)


def _python_files() -> list[Path]:
    assert ACCOUNT_V2.is_dir(), "S2 account_v2 package is missing"
    files = sorted(ACCOUNT_V2.rglob("*.py"))
    assert files, "S2 account_v2 package has no Python files"
    return files


def test_s2_account_package_cannot_import_trading_mutation_authority() -> None:
    violations: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(FORBIDDEN_MODULE_PREFIXES):
                        violations.append(f"{path}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith(FORBIDDEN_MODULE_PREFIXES):
                    violations.append(f"{path}: from {module} import ...")
    assert violations == []


def test_s2_account_package_exposes_no_obvious_broker_or_arm_capability() -> None:
    violations: list[str] = []
    for path in _python_files():
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_AUTHORITY_TOKENS:
            if token in text:
                violations.append(f"{path}: forbidden token {token!r}")
    assert violations == []
