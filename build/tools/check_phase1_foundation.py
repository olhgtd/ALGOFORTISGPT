"""Repo-local static policy checks for the AlgoFortis V2 Phase 1 gate.

The checker intentionally depends only on the locked runtime environment. It
verifies direct dependency pins, rejects raw secret-bearing config keys, keeps
the V2.0 adapter registry internal-only, and confirms required foundation files
exist. It performs no network access and does not execute adapter code.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re
import sys
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]

REQUIREMENT_FILES = (
    ROOT / "requirements-runtime.lock.txt",
    ROOT / "requirements-dashboard.in",
    ROOT / "requirements-test.in",
)

REQUIRED_PHASE1_FILES = (
    ROOT / "engine/core/runtime.py",
    ROOT / "engine/core/configuration.py",
    ROOT / "engine/core/observability.py",
    ROOT / "engine/core/adapter_registry.py",
    ROOT / "engine/audit/chain.py",
    ROOT / "engine/persistence/migrations.py",
    ROOT / "build/tools/check_module_boundaries.py",
    ROOT / "docs/v2/adr/ADR-009-v2-plugin-scope.md",
)

SECRET_KEY_NAMES = {
    "api_key",
    "api_secret",
    "secret_key",
    "broker_secret",
    "client_secret",
    "password",
    "passwd",
    "access_token",
    "refresh_token",
    "auth_token",
    "session_token",
    "private_key",
    "private_material",
    "recovery_code",
    "device_private",
    "credential_private",
}

DISALLOWED_REGISTRY_IMPORT_ROOTS = {"importlib", "pkgutil"}
DISALLOWED_REGISTRY_CALLS = {"__import__", "eval", "exec"}
PIN_RE = re.compile(r"^[A-Za-z0-9_.\-]+(?:\[[A-Za-z0-9_,.\-]+\])?==[^=\s]+$")


def _requirement_entries(path: Path) -> list[tuple[int, str]]:
    entries: list[tuple[int, str]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        value = raw.split("#", 1)[0].strip()
        if value:
            entries.append((line_number, value))
    return entries


def check_direct_dependency_pins(errors: list[str]) -> None:
    for path in REQUIREMENT_FILES:
        if not path.is_file():
            errors.append(f"missing dependency file: {path.relative_to(ROOT)}")
            continue
        for line_number, entry in _requirement_entries(path):
            lowered = entry.lower()
            if lowered.startswith(("-e ", "git+", "http://", "https://", "file:")):
                errors.append(
                    f"untrusted/non-index dependency source in {path.relative_to(ROOT)}:{line_number}: {entry}"
                )
                continue
            requirement = entry.split(";", 1)[0].strip()
            if not PIN_RE.fullmatch(requirement):
                errors.append(
                    f"direct dependency must use an exact == pin in "
                    f"{path.relative_to(ROOT)}:{line_number}: {entry}"
                )


def _is_secret_ref(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized == "secret_ref" or normalized.endswith("_secret_ref")


def _is_raw_secret_key(key: str) -> bool:
    normalized = key.strip().lower()
    if _is_secret_ref(normalized):
        return False
    if normalized in SECRET_KEY_NAMES:
        return True
    return any(normalized.endswith(f"_{name}") for name in SECRET_KEY_NAMES)


def _scan_config_node(value: Any, *, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                errors.append(f"config mapping key must be text at {path}")
                continue
            child_path = f"{path}.{key}" if path else key
            if _is_raw_secret_key(key):
                errors.append(
                    f"raw secret-bearing config key is forbidden; use secret_ref: {child_path}"
                )
            _scan_config_node(child, path=child_path, errors=errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_config_node(child, path=f"{path}[{index}]", errors=errors)


def check_config_secret_policy(errors: list[str]) -> None:
    config_root = ROOT / "config"
    for path in sorted((*config_root.rglob("*.yaml"), *config_root.rglob("*.yml"))):
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"config parse failed for {path.relative_to(ROOT)}: {exc}")
            continue
        _scan_config_node(payload, path=str(path.relative_to(ROOT)), errors=errors)


def check_internal_registry_scope(errors: list[str]) -> None:
    path = ROOT / "engine/core/adapter_registry.py"
    if not path.is_file():
        errors.append("missing internal adapter registry implementation")
        return
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        errors.append(f"adapter registry syntax error: {exc}")
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in DISALLOWED_REGISTRY_IMPORT_ROOTS:
                    errors.append(f"external/dynamic plugin loader import forbidden: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root in DISALLOWED_REGISTRY_IMPORT_ROOTS:
                errors.append(f"external/dynamic plugin loader import forbidden: {node.module}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in DISALLOWED_REGISTRY_CALLS:
                errors.append(f"dynamic code loading call forbidden in adapter registry: {node.func.id}")


def check_required_files(errors: list[str]) -> None:
    for path in REQUIRED_PHASE1_FILES:
        if not path.is_file():
            errors.append(f"missing Phase 1 foundation file: {path.relative_to(ROOT)}")


def main() -> int:
    errors: list[str] = []
    check_direct_dependency_pins(errors)
    check_config_secret_policy(errors)
    check_internal_registry_scope(errors)
    check_required_files(errors)

    if errors:
        print("PHASE1_FOUNDATION_STATIC_FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print("PHASE1_FOUNDATION_STATIC_PASS: dependencies pinned; config secrets absent; registry internal-only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
