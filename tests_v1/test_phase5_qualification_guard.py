from __future__ import annotations

from pathlib import Path

from build.tools.check_phase5_paper_recovery import REQUIRED, verify


def _write(tmp_path: Path, relative: str, text: str) -> None:
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_phase5_guard_pins_final_qualification_files():
    assert {
        "engine/paper/drift_report_v2.py",
        "engine/paper/evidence_v2.py",
        "engine/paper/failure_injection_v2.py",
        "build/tools/phase5_probe.py",
        "tests_v1/test_phase5_drift_report.py",
        "tests_v1/test_phase5_failure_injection.py",
        "tests_v1/test_phase5_qualification_guard.py",
    } <= set(REQUIRED)


def test_phase5_guard_rejects_live_arm_enabled_default(tmp_path: Path):
    _write(
        tmp_path,
        "engine/live/state_machine_v2.py",
        "class LiveStateMachine:\n"
        "    def __init__(self, *, arm_enabled: bool = True):\n"
        "        self.arm_enabled = arm_enabled\n",
    )
    problems = verify(tmp_path, check_presence=False, check_state_vocabulary=False)
    assert any("live default" in problem.lower() and "arm" in problem.lower() for problem in problems)


def test_phase5_guard_rejects_live_active_initial_default(tmp_path: Path):
    _write(
        tmp_path,
        "engine/live/state_machine_v2.py",
        "from enum import Enum\n"
        "class LiveState(Enum): ACTIVE='ACTIVE'\n"
        "class LiveStateMachine:\n"
        "    def __init__(self, *, initial_state=LiveState.ACTIVE):\n"
        "        self.state = initial_state\n",
    )
    problems = verify(tmp_path, check_presence=False, check_state_vocabulary=False)
    assert any("live default" in problem.lower() and "active" in problem.lower() for problem in problems)
