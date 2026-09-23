"""Static Phase-2 Safety Spine policy gate.

This checker deliberately does not import project modules.  It verifies that the
required Safety Spine authorities/tests are present and that safety-critical
modules remain broker-neutral and retain the frozen no-auto-arm / kill-switch
markers required by G2.
"""

from __future__ import annotations

import ast
from pathlib import Path


_REQUIRED_FILES = (
    "engine/orders/contracts_v2.py",
    "engine/orders/intent_guard.py",
    "engine/orders/lifecycle_v2.py",
    "engine/risk/gate_v2.py",
    "engine/risk/limits.py",
    "engine/risk/kill_switch.py",
    "engine/live/state_machine_v2.py",
    "engine/broker_contract/port_v2.py",
    "engine/broker_contract/conformance_v2.py",
    "tests_v1/test_v2_phase2_risk_gate_authority.py",
    "tests_v1/test_v2_phase2_hard_limits.py",
    "tests_v1/test_v2_phase2_intent_guard.py",
    "tests_v1/test_v2_phase2_order_lifecycle.py",
    "tests_v1/test_v2_phase2_mode_isolation.py",
    "tests_v1/test_v2_phase2_live_state_machine.py",
    "tests_v1/test_v2_phase2_kill_switch.py",
    "docs/v2/adr/ADR-010-phase2-kill-switch-semantics.md",
)

_SAFETY_DOMAIN_FILES = (
    "engine/orders/contracts_v2.py",
    "engine/orders/intent_guard.py",
    "engine/orders/lifecycle_v2.py",
    "engine/risk/gate_v2.py",
    "engine/risk/limits.py",
    "engine/risk/kill_switch.py",
    "engine/live/state_machine_v2.py",
)

_FORBIDDEN_IMPORT_PREFIXES = (
    "engine.broker_adapters",
    "engine.broker.angel_adapter",
    "engine.broker.dhan_adapter",
    "engine.broker.kite_adapter",
    "engine.broker.upstox_adapter",
)

_REQUIRED_MARKERS: dict[str, tuple[str, ...]] = {
    "engine/risk/gate_v2.py": (
        "entry_policy",
        "entries_halted",
        "_mint_approved_order",
    ),
    "engine/risk/kill_switch.py": (
        "HALT_ENTRIES",
        "CANCEL_PENDING",
        "FLATTEN_ALL",
        "ENTRY_ORDERS_ONLY",
        '"flatten_all": False',
        "protective_exits_active=True",
        "reconciliation_active=True",
    ),
    "engine/live/state_machine_v2.py": (
        "arm_enabled: bool = False",
        "ACTIVE requires explicit arm request",
        "LiveState.RECOVERY",
        "arm_enabled=False",
    ),
}


def _module_names(tree: ast.AST) -> tuple[str, ...]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return tuple(names)


def _is_forbidden_import(module_name: str) -> bool:
    return any(
        module_name == prefix or module_name.startswith(prefix + ".")
        for prefix in _FORBIDDEN_IMPORT_PREFIXES
    )


def check_phase2_safety_spine(root: Path) -> tuple[str, ...]:
    """Return deterministic diagnostics; an empty tuple means the gate passes."""

    root = Path(root)
    diagnostics: list[str] = []

    for relative in _REQUIRED_FILES:
        if not (root / relative).is_file():
            diagnostics.append(f"missing required Phase-2 file: {relative}")

    for relative in _SAFETY_DOMAIN_FILES:
        path = root / relative
        if not path.is_file():
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=relative)
        except (OSError, UnicodeError, SyntaxError) as error:
            diagnostics.append(f"cannot statically inspect {relative}: {error}")
            continue
        for module_name in _module_names(tree):
            if _is_forbidden_import(module_name):
                diagnostics.append(
                    f"forbidden concrete broker import in {relative}: {module_name}"
                )

    for relative, markers in _REQUIRED_MARKERS.items():
        path = root / relative
        if not path.is_file():
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            diagnostics.append(f"cannot read {relative}: {error}")
            continue
        for marker in markers:
            if marker not in source:
                diagnostics.append(
                    f"required Phase-2 safety marker missing in {relative}: {marker}"
                )

    return tuple(sorted(diagnostics))


def main() -> int:
    diagnostics = check_phase2_safety_spine(Path("."))
    if diagnostics:
        print("PHASE2_SAFETY_SPINE_STATIC_FAIL")
        for diagnostic in diagnostics:
            print(f"- {diagnostic}")
        return 1
    print(
        "PHASE2_SAFETY_SPINE_STATIC_PASS: required authorities/tests present; "
        "safety domain broker-neutral; kill-switch/no-auto-arm markers locked"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
