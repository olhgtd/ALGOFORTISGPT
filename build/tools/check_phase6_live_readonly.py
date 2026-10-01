"""Static mutation firewall for AlgoFortis Phase-6 multi-broker read-only qualification."""

import ast
from pathlib import Path

REQUIRED = (
    "engine/broker_adapters/angelone_v2/__init__.py",
    "engine/broker_adapters/angelone_v2/contracts.py",
    "engine/broker_adapters/angelone_v2/rate_policy.py",
    "engine/broker_adapters/angelone_v2/compliance_gate.py",
    "engine/broker_adapters/angelone_v2/session.py",
    "engine/broker_adapters/angelone_v2/read_only_adapter.py",
    "engine/broker_adapters/angelone_v2/order_policy.py",
    "engine/broker_adapters/angelone_v2/protection_capability.py",
    "engine/broker_contract/read_only_conformance_v2.py",
    "engine/live/phase6_readonly_coordinator.py",
    "engine/live/phase6_evidence.py",
    "engine/data/transports/__init__.py",
    "engine/data/transports/contracts.py",
    "engine/data/transports/sequence.py",
    "engine/data/transports/policy.py",
    "engine/data/transports/runtime.py",
    "engine/data/transports/bridge.py",
    "engine/data/transports/registry.py",
    "engine/data/transports/brokers/__init__.py",
    "engine/data/transports/brokers/_base.py",
    "engine/data/transports/brokers/angelone.py",
    "engine/data/transports/brokers/zerodha.py",
    "engine/data/transports/brokers/dhan.py",
    "engine/data/transports/brokers/upstox.py",
    "build/tools/check_phase6_live_readonly.py",
    "build/tools/phase6_probe.py",
    ".github/workflows/v2-phase6-readonly.yml",
    "docs/v2/phase6/G6_EVIDENCE.md",
    "docs/v2/phase6/G6_READ_ONLY_SESSION_TEMPLATE.md",
    "tests_v1/test_phase6_readonly_contracts.py",
    "tests_v1/test_phase6_architecture_guard.py",
    "tests_v1/test_phase6_rate_policy.py",
    "tests_v1/test_phase6_compliance_gate.py",
    "tests_v1/test_phase6_angelone_session.py",
    "tests_v1/test_phase6_angelone_read_only_adapter.py",
    "tests_v1/test_phase6_read_only_conformance.py",
    "tests_v1/test_phase6_live_reconciliation.py",
    "tests_v1/test_phase6_foreign_activity_incidents.py",
    "tests_v1/test_phase6_order_policy.py",
    "tests_v1/test_phase6_protection_capability.py",
    "tests_v1/test_phase6_connectivity_chaos.py",
    "tests_v1/test_phase6_transport_contracts.py",
    "tests_v1/test_phase6_transport_runtime.py",
    "tests_v1/test_phase6_transport_runtime_subscriptions.py",
    "tests_v1/test_phase6_market_event_bridge.py",
    "tests_v1/test_phase6_feed_monitor_multi_instrument.py",
    "tests_v1/test_phase6_feed_riskgate_handoff.py",
    "tests_v1/test_phase6_broker_normalizer_bridge.py",
    "tests_v1/test_phase6_transport_angelone.py",
    "tests_v1/test_phase6_transport_zerodha.py",
    "tests_v1/test_phase6_transport_dhan.py",
    "tests_v1/test_phase6_transport_upstox.py",
    "tests_v1/test_phase6_transport_registry.py",
    "tests_v1/test_phase6_transport_extension.py",
    "tests_v1/test_phase6_transport_conformance.py",
    "tests_v1/test_phase6_evidence.py",
    "tests_v1/test_phase6_qualification_guard.py",
)

_MUTATION_NAMES = frozenset({"place","place_order","submit","submit_order","modify","modify_order","cancel","cancel_order","create_gtt","modify_gtt","cancel_gtt"})
_FORBIDDEN_IMPORT_ROOTS = ("engine.broker_adapters.angel_adapter", "engine.execution")
_ENV_BYPASS_TOKENS = ("ARM", "MUTATION", "BROKER_WRITE", "LIVE_EXECUTION", "ALLOW_LIVE")
_DORMANT_MUTATION_SEAM = "engine/broker_adapters/angelone_v2/mutation_seam_v2.py"
_DORMANT_SEAM_METHODS = frozenset({"place", "cancel"})
_DORMANT_SEAM_EXCEPTION = "AngelOneV2MutationUnavailable"
_DORMANT_SEAM_NETWORK_IMPORTS = ("requests", "httpx", "urllib", "aiohttp", "socket")


def _read(path: Path, problems: list[str]) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        problems.append(f"cannot read {path}: {exc}")
        return None


def _production_paths(root: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    adapter_root = root / "engine" / "broker_adapters" / "angelone_v2"
    if adapter_root.is_dir():
        paths.extend(sorted(adapter_root.rglob("*.py")))
    live_root = root / "engine" / "live"
    if live_root.is_dir():
        paths.extend(sorted(live_root.glob("phase6*.py")))
    transport_root = root / "engine" / "data" / "transports"
    if transport_root.is_dir():
        paths.extend(sorted(transport_root.rglob("*.py")))
    return tuple(dict.fromkeys(paths))


def _import_names(tree: ast.AST) -> tuple[str, ...]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return tuple(names)


def _is_true(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _is_env_lookup(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in {"getenv", "get"}:
        if isinstance(func.value, ast.Name) and func.value.id in {"os", "environ"}:
            return True
        if isinstance(func.value, ast.Attribute) and func.value.attr == "environ":
            return True
    return False


def _raises_named_unavailable(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Raise) or child.exc is None:
            continue
        exc = child.exc
        if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
            if exc.func.id == _DORMANT_SEAM_EXCEPTION:
                return True
        if isinstance(exc, ast.Name) and exc.id == _DORMANT_SEAM_EXCEPTION:
            return True
    return False


def _source_problems(path: Path, root: Path, source: str) -> tuple[str, ...]:
    relative = path.relative_to(root).as_posix()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return (f"{relative}: syntax error prevents Phase-6 static proof: {exc}",)

    problems: list[str] = []
    imports = _import_names(tree)
    is_transport = relative.startswith("engine/data/transports/")
    is_dormant_seam = relative == _DORMANT_MUTATION_SEAM
    if is_transport:
        for imported in imports:
            if imported == "engine.risk.gate_v2" or imported.startswith("engine.risk.gate_v2."):
                problems.append(f"{relative}: direct RiskGate import is forbidden in transport code")
            if imported == "engine.live.state_machine_v2" or imported.startswith("engine.live.state_machine_v2."):
                problems.append(f"{relative}: direct Phase-5 operational-state import is forbidden in transport code")
    for imported in imports:
        for forbidden in _FORBIDDEN_IMPORT_ROOTS:
            if imported == forbidden or imported.startswith(forbidden + "."):
                if forbidden == "engine.broker_adapters.angel_adapter":
                    problems.append(f"{relative}: legacy AngelOneBrokerAdapter import is forbidden")
                else:
                    problems.append(f"{relative}: execution mutation import root {forbidden} is forbidden")
        if is_dormant_seam and any(
            imported == prefix or imported.startswith(prefix + ".")
            for prefix in _DORMANT_SEAM_NETWORK_IMPORTS
        ):
            problems.append(f"{relative}: dormant mutation seam network import {imported} is forbidden")

    seen_dormant_methods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "ApprovedOrder" and not is_dormant_seam:
                    problems.append(f"{relative}: ApprovedOrder import is forbidden in Phase-6 read-only code")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in _MUTATION_NAMES:
            if is_dormant_seam and node.name in _DORMANT_SEAM_METHODS:
                seen_dormant_methods.add(node.name)
                if not _raises_named_unavailable(node):
                    problems.append(
                        f"{relative}: dormant mutation entrypoint {node.name} must raise {_DORMANT_SEAM_EXCEPTION}"
                    )
            else:
                problems.append(f"{relative}: mutation entrypoint {node.name} is structurally forbidden")
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name in _MUTATION_NAMES:
                problems.append(f"{relative}: mutation call {name} is structurally forbidden")
            if _is_env_lookup(node) and node.args and isinstance(node.args[0], ast.Constant):
                key = node.args[0].value
                if isinstance(key, str) and any(token in key.upper() for token in _ENV_BYPASS_TOKENS):
                    problems.append(f"{relative}: environment/config mutation bypass {key!r} is forbidden")
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if _is_true(value):
                for target in targets:
                    if isinstance(target, ast.Name) and target.id == "arm_enabled":
                        problems.append(f"{relative}: arm_enabled=True is forbidden")
                    if isinstance(target, ast.Attribute) and target.attr == "arm_enabled":
                        problems.append(f"{relative}: arm_enabled=True is forbidden")
    if is_dormant_seam and seen_dormant_methods != set(_DORMANT_SEAM_METHODS):
        missing = sorted(set(_DORMANT_SEAM_METHODS) - seen_dormant_methods)
        if missing:
            problems.append(f"{relative}: dormant mutation seam missing fail-closed methods {missing}")
    return tuple(problems)


def verify(root: Path, *, check_presence: bool = True) -> tuple[str, ...]:
    root = Path(root)
    problems: list[str] = []
    if check_presence:
        for relative in REQUIRED:
            if not (root / relative).is_file():
                problems.append(f"missing required Phase-6 read-only file: {relative}")
    for path in _production_paths(root):
        source = _read(path, problems)
        if source is None:
            continue
        problems.extend(_source_problems(path, root, source))
    return tuple(problems)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    problems = verify(root)
    if problems:
        for problem in problems:
            print(f"PHASE6_LIVE_READONLY_STATIC_FAIL: {problem}")
        return 1
    print("PHASE6_LIVE_READONLY_STATIC_PASS: multi-broker mutation capability absent and read-only boundary locked")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
