from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "v2-phase6-readonly.yml"
CHECKER = ROOT / "build" / "tools" / "check_phase6_live_readonly.py"
PROBE = ROOT / "build" / "tools" / "phase6_probe.py"


def test_required_phase6_qualification_files_are_present() -> None:
    for path in (WORKFLOW, CHECKER, PROBE):
        assert path.is_file(), str(path)


def test_workflow_has_dual_windows_legs_and_deterministic_g6_compare() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    for token in (
        "windows-latest",
        "windows-2022",
        "G6 cross-Windows deterministic fingerprint comparison",
        "python build/tools/check_phase6_live_readonly.py",
        "python build/tools/phase6_probe.py",
        "test_phase6_architecture_guard.py",
        "test_phase6_live_reconciliation.py",
        "test_phase6_foreign_activity_incidents.py",
        "test_phase6_connectivity_chaos.py",
    ):
        assert token in text


def test_workflow_does_not_enable_live_mutation() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "ALLOW_LIVE_MUTATION" not in text
    assert "arm_enabled: true" not in text.lower()
    assert "LIVE_STATE=READ_ONLY/DISARMED" in text
