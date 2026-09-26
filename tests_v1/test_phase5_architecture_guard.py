from pathlib import Path

from build.tools.check_phase5_paper_recovery import (
    EXPECTED_OPERATIONAL_STATES,
    FORBIDDEN_IMPORT_ROOTS,
    REQUIRED,
    verify,
)


def _write(tmp_path: Path, relative: str, text: str) -> None:
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_phase5_guard_passes_current_p5_01_scope():
    root = Path(__file__).resolve().parents[1]
    assert verify(root) == ()


def test_phase5_guard_pins_p5_01_authorities_and_tests():
    expected = {
        "engine/paper/contracts_v2.py",
        "engine/paper/operational_state_v2.py",
        "tests_v1/test_phase5_contracts.py",
        "tests_v1/test_phase5_operational_state.py",
        "tests_v1/test_phase5_architecture_guard.py",
        "build/tools/check_phase5_paper_recovery.py",
    }
    assert expected <= set(REQUIRED)


def test_phase5_guard_pins_p5_06_failure_policy_and_tests():
    assert {
        "engine/paper/failure_policy_v2.py",
        "tests_v1/test_phase5_failure_policy.py",
    } <= set(REQUIRED)


def test_phase5_guard_locks_exact_operational_state_vocabulary():
    assert EXPECTED_OPERATIONAL_STATES == (
        "HEALTHY",
        "DEGRADED",
        "HALTED",
        "RECOVERY",
        "READY_FOR_RESUME",
    )


def test_phase5_guard_rejects_real_broker_and_live_imports(tmp_path):
    _write(
        tmp_path,
        "engine/paper/contracts_v2.py",
        "from engine.broker_adapters import angel_adapter\n",
    )
    _write(
        tmp_path,
        "engine/paper/operational_state_v2.py",
        "from engine.live import state_machine_v2\n",
    )
    problems = verify(tmp_path, check_presence=False, check_state_vocabulary=False)
    assert any("engine.broker_adapters" in problem for problem in problems)
    assert any("engine.live" in problem for problem in problems)


def test_phase5_guard_rejects_persistence_network_and_windows_concrete_imports(tmp_path):
    bad_imports = (
        "import sqlite3\n",
        "import requests\n",
        "import httpx\n",
        "import telegram\n",
        "import win32api\n",
        "import win32con\n",
    )
    for index, source in enumerate(bad_imports):
        _write(tmp_path, f"engine/paper/bad_{index}.py", source)
    problems = verify(tmp_path, check_presence=False, check_state_vocabulary=False)
    for root in ("sqlite3", "requests", "httpx", "telegram", "win32api", "win32con"):
        assert any(root in problem for problem in problems)


def test_phase5_guard_forbidden_roots_include_p5_01_boundary_set():
    assert {
        "engine.broker_adapters",
        "engine.live",
        "sqlite3",
        "requests",
        "httpx",
        "telegram",
        "win32api",
        "win32con",
    } <= set(FORBIDDEN_IMPORT_ROOTS)


def test_phase5_guard_rejects_operational_state_vocabulary_drift(tmp_path):
    _write(
        tmp_path,
        "engine/paper/contracts_v2.py",
        "from enum import Enum\n"
        "class PaperOperationalState(str, Enum):\n"
        "    HEALTHY = 'HEALTHY'\n"
        "    AUTO_RESUMED = 'AUTO_RESUMED'\n",
    )
    _write(
        tmp_path,
        "engine/paper/operational_state_v2.py",
        "from engine.paper.contracts_v2 import PaperOperationalState\n",
    )
    problems = verify(tmp_path, check_presence=False)
    assert any("operational state vocabulary" in problem.lower() for problem in problems)


def test_phase5_guard_rejects_guessed_production_storm_threshold_constants(tmp_path):
    _write(
        tmp_path,
        "engine/paper/contracts_v2.py",
        "PRODUCTION_STORM_TRIGGER_COUNT = 5\n",
    )
    _write(
        tmp_path,
        "engine/paper/operational_state_v2.py",
        "# pure state authority\n",
    )
    problems = verify(tmp_path, check_presence=False, check_state_vocabulary=False)
    assert any("storm threshold" in problem.lower() for problem in problems)


def test_phase5_guard_rejects_default_named_storm_threshold_constants(tmp_path):
    _write(
        tmp_path,
        "engine/paper/failure_policy_v2.py",
        "DEFAULT_STORM_TRIGGER_COUNT = 5\n",
    )
    problems = verify(tmp_path, check_presence=False, check_state_vocabulary=False)
    assert any("storm threshold" in problem.lower() for problem in problems)


def test_phase5_guard_rejects_embedded_module_level_storm_policy_profile(tmp_path):
    _write(
        tmp_path,
        "engine/paper/failure_policy_v2.py",
        "DEFAULT_REJECTION_POLICY = FailureStormPolicy(\n"
        "    policy_id='production/rejections', version='1',\n"
        "    failure_class='ORDER_REJECTION', observation_window_ms=10000,\n"
        "    trigger_count=5, cooldown_ms=30000,\n"
        "    escalation_action='HALT_ENTRIES', reset_rule='WINDOW_AND_COOLDOWN',\n"
        ")\n",
    )
    problems = verify(tmp_path, check_presence=False, check_state_vocabulary=False)
    assert any("storm policy profile" in problem.lower() for problem in problems)
