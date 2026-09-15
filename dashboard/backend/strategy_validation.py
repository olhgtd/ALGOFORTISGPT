"""Static gate for untrusted strategy submissions; validation never executes code."""
from __future__ import annotations

import ast
from dataclasses import dataclass


class StrategyValidationError(ValueError):
    pass


_BANNED_IMPORT_ROOTS = {"os", "sys", "subprocess", "socket", "ctypes", "requests", "urllib", "pathlib", "shutil"}
_BANNED_CALLS = {"eval", "exec", "compile", "open", "__import__", "input"}


@dataclass(frozen=True)
class StaticValidationResult:
    accepted: bool
    reasons: tuple[str, ...]


def validate_static_python(source: str) -> StaticValidationResult:
    if not isinstance(source, str) or not source.strip():
        return StaticValidationResult(False, ("strategy source is empty",))
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as exc:
        return StaticValidationResult(False, (f"syntax error: {exc.msg}",))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in _BANNED_IMPORT_ROOTS:
                    violations.append(f"banned import: {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in _BANNED_IMPORT_ROOTS:
            violations.append(f"banned import: {node.module}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _BANNED_CALLS:
            violations.append(f"banned call: {node.func.id}")
    return StaticValidationResult(not violations, tuple(sorted(set(violations))))
