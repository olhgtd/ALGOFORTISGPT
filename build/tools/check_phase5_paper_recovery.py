"""Static safety guard for AlgoFortis V2 Phase 5 paper/recovery code.

The guard is extended slice-by-slice as Phase 5 advances. It deliberately uses
source inspection rather than importing runtime modules so synthetic fixtures
can prove that unsafe dependencies/defaults are rejected.
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
    "engine/paper/failure_policy_v2.py",
    "engine/paper/drift_report_v2.py",
    "engine/paper/evidence_v2.py",
    "engine/paper/failure_injection_v2.py",
    "engine/host/__init__.py",
    "engine/host/instance_lock.py",
    "engine/host/clock_health.py",
    "engine/host/power_session.py",
    "engine/host/watchdog_policy.py",
    "engine/alerts/__init__.py",
    "engine/alerts/contracts.py",
    "engine/alerts/dispatcher.py",
    "engine/alerts/redaction.py",
    "engine/alerts/adapters/__init__.py",
    "engine/alerts/adapters/windows_local.py",
    "engine/alerts/adapters/telegram.py",
    "build/tools/phase5_probe.py",
    "tests_v1/test_phase5_contracts.py",
    "tests_v1/test_phase5_operational_state.py",
    "tests_v1/test_phase5_failure_policy.py",
    "tests_v1/test_phase5_host_resilience.py",
    "tests_v1/test_phase5_alerts.py",
    "tests_v1/test_phase5_drift_report.py",
    "tests_v1/test_phase5_failure_injection.py",
    "tests_v1/test_phase5_architecture_guard.py",
    "tests_v1/test_phase5_qualification_guard.py",
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
_HOST_FORBIDDEN_IMPORT_ROOTS = ("engine.broker_adapters", "engine.live")
_ALERT_FORBIDDEN_IMPORT_ROOTS = ("engine.broker_adapters", "engine.live")

_STORM_CONSTANT = re.compile(
    r"(?im)^\s*(?:(?:PRODUCTION|DEFAULT)_)?STORM_"
    r"(?:TRIGGER_COUNT|WINDOW|WINDOW_SECONDS|THRESHOLD)\s*=\s*\d+"
)
_CLOCK_DRIFT_CONSTANT = re.compile(
    r"(?im)^\s*(?:(?:PRODUCTION|DEFAULT)_)?CLOCK_"
    r"(?:DRIFT|DRIFT_MS|MAX_DRIFT_MS|DRIFT_THRESHOLD)\s*=\s*\d+"
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


def _matching_forbidden_import(name: str, roots: tuple[str, ...]) -> str | None:
    for root in roots:
        if name == root or name.startswith(root + "."):
            return root
    return None


def _is_forbidden_import(name: str) -> str | None:
    return _matching_forbidden_import(name, FORBIDDEN_IMPORT_ROOTS)


def _is_named_call(value: ast.AST | None, name: str) -> bool:
    if not isinstance(value, ast.Call):
        return False
    func = value.func
    return (isinstance(func, ast.Name) and func.id == name) or (
        isinstance(func, ast.Attribute) and func.attr == name
    )


def _has_module_level_named_call(source: str, name: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in tree.body:
        if isinstance(node, ast.Assign) and _is_named_call(node.value, name):
            return True
        if isinstance(node, ast.AnnAssign) and _is_named_call(node.value, name):
            return True
    return False


def _has_module_level_storm_policy_profile(source: str) -> bool:
    return _has_module_level_named_call(source, "FailureStormPolicy")


def _has_module_level_clock_policy_profile(source: str) -> bool:
    return _has_module_level_named_call(source, "ClockHealthPolicy")


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
            if isinstance(target, ast.Name) and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
                values.append(item.value.value)
        return tuple(values)
    return None


def _read_source(path: Path, problems: list[str]) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        problems.append(f"cannot read {path}: {error}")
        return None


def _live_default_problems(source: str) -> tuple[str, ...]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ()
    problems: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "__init__":
            continue
        positional = list(node.args.args)
        positional_defaults = list(node.args.defaults)
        default_map: dict[str, ast.AST] = {}
        if positional_defaults:
            for arg, default in zip(positional[-len(positional_defaults):], positional_defaults):
                default_map[arg.arg] = default
        for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
            if default is not None:
                default_map[arg.arg] = default
        arm_default = default_map.get("arm_enabled")
        if isinstance(arm_default, ast.Constant) and arm_default.value is True:
            problems.append("live default arm_enabled must remain false")
        initial_default = default_map.get("initial_state")
        if isinstance(initial_default, ast.Attribute) and initial_default.attr == "ACTIVE":
            problems.append("live default initial state must not be ACTIVE")
    return tuple(problems)


def verify(root: Path, *, check_presence: bool = True, check_state_vocabulary: bool = True) -> tuple[str, ...]:
    root = Path(root)
    problems: list[str] = []

    if check_presence:
        for relative in REQUIRED:
            if not (root / relative).is_file():
                problems.append(f"missing required Phase-5 file: {relative}")

    paper_root = root / "engine" / "paper"
    if paper_root.is_dir():
        for path in sorted(paper_root.rglob("*.py")):
            source = _read_source(path, problems)
            if source is None:
                continue
            relative = path.relative_to(root).as_posix()
            for imported in _import_names(source):
                forbidden = _is_forbidden_import(imported)
                if forbidden:
                    problems.append(f"{relative}: forbidden import root {forbidden}")
            if _STORM_CONSTANT.search(source):
                problems.append(f"{relative}: guessed production storm threshold constant is forbidden")
            if _has_module_level_storm_policy_profile(source):
                problems.append(f"{relative}: embedded module-level storm policy profile is forbidden; inject a versioned policy instead")

    host_root = root / "engine" / "host"
    if host_root.is_dir():
        for path in sorted(host_root.rglob("*.py")):
            source = _read_source(path, problems)
            if source is None:
                continue
            relative = path.relative_to(root).as_posix()
            for imported in _import_names(source):
                forbidden = _matching_forbidden_import(imported, _HOST_FORBIDDEN_IMPORT_ROOTS)
                if forbidden:
                    problems.append(f"{relative}: forbidden host import root {forbidden}")
            if _CLOCK_DRIFT_CONSTANT.search(source):
                problems.append(f"{relative}: guessed production clock drift threshold constant is forbidden")
            if _has_module_level_clock_policy_profile(source):
                problems.append(f"{relative}: embedded module-level clock policy profile is forbidden; inject a versioned policy instead")
            lowered = source.lower()
            if "powercfg" in lowered and "setactive" in lowered:
                problems.append(f"{relative}: permanent power-plan mutation command is forbidden")

    alerts_root = root / "engine" / "alerts"
    if alerts_root.is_dir():
        for path in sorted(alerts_root.rglob("*.py")):
            source = _read_source(path, problems)
            if source is None:
                continue
            relative = path.relative_to(root).as_posix()
            for imported in _import_names(source):
                forbidden = _matching_forbidden_import(imported, _ALERT_FORBIDDEN_IMPORT_ROOTS)
                if forbidden:
                    problems.append(f"{relative}: forbidden alert import root {forbidden}")

    live_state = root / "engine" / "live" / "state_machine_v2.py"
    if live_state.is_file():
        source = _read_source(live_state, problems)
        if source is not None:
            problems.extend(_live_default_problems(source))

    if check_state_vocabulary:
        contracts = root / "engine" / "paper" / "contracts_v2.py"
        if contracts.is_file():
            source = _read_source(contracts, problems)
            if source is not None:
                actual = _state_vocabulary(source)
                if actual != EXPECTED_OPERATIONAL_STATES:
                    problems.append(f"operational state vocabulary drift: expected {EXPECTED_OPERATIONAL_STATES!r}, got {actual!r}")
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
    print("PHASE5_PAPER_RECOVERY_STATIC_PASS: Phase-5 authorities, fail-closed defaults, host/alert boundaries, evidence files, and Live DISARMED defaults locked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
