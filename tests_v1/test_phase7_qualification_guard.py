from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOW = _ROOT / ".github/workflows/v2-phase7-portfolio-risk.yml"
_CHECKER = _ROOT / "build/tools/check_phase7_portfolio_risk.py"
_PROBE = _ROOT / "build/tools/phase7_probe.py"

_REQUIRED_TESTS = (
    "test_phase7_contracts.py",
    "test_phase7_architecture_guard.py",
    "test_phase7_reservations.py",
    "test_phase7_exposure.py",
    "test_phase7_circuit_breaker.py",
    "test_phase7_event_day_policy.py",
    "test_phase7_portfolio_evaluator.py",
    "test_phase7_riskgate_integration.py",
    "test_phase7_attribution.py",
    "test_phase7_evidence.py",
    "test_phase7_qualification_guard.py",
)


def test_g7_workflow_keeps_dual_windows_static_probe_and_focused_tests() -> None:
    text = _WORKFLOW.read_text(encoding="utf-8")
    assert "windows-latest" in text
    assert "windows-2022" in text
    assert "3.13.14" in text
    assert "python build/tools/check_phase7_portfolio_risk.py" in text
    assert "python build/tools/phase7_probe.py" in text
    for name in _REQUIRED_TESTS:
        assert name in text
    assert "G7 cross-Windows deterministic fingerprint comparison" in text
    for marker in (
        "APPROVED_ORDER_AUTHORITY=RISK_GATE_V2_ONLY",
        "LIVE_STATE=READ_ONLY/DISARMED",
        "G7_ENABLES_REAL_MONEY_TRADING=NO",
    ):
        assert marker in text


def test_static_checker_requires_g7_authorities_and_qualification_files() -> None:
    text = _CHECKER.read_text(encoding="utf-8")
    for path in (
        "engine/portfolio/v2/reservations.py",
        "engine/portfolio/v2/exposure.py",
        "engine/portfolio/v2/circuit_breaker.py",
        "engine/portfolio/v2/attribution.py",
        "engine/portfolio/v2/evidence.py",
        "engine/risk/event_day_policy_v2.py",
        "engine/risk/portfolio_v2.py",
        "engine/risk/portfolio_admission_v2.py",
        "build/tools/phase7_probe.py",
        ".github/workflows/v2-phase7-portfolio-risk.yml",
    ):
        assert path in text
    assert _PROBE.is_file()
