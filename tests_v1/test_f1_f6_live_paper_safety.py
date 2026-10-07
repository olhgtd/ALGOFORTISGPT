"""F1–F6 live-paper safety contracts (fail-closed protective / session / audit)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COORD = ROOT / "engine" / "paper" / "coordinator.py"
SAFETY = ROOT / "engine" / "safety" / "safety.py"


def _coord() -> str:
    return COORD.read_text(encoding="utf-8")


def _safety() -> str:
    return SAFETY.read_text(encoding="utf-8")


def test_f1_protective_submit_failure_routes_not_silent_continue() -> None:
    src = _coord()
    assert "_paper_broker.submit(" in src
    assert "_route_protective_evaluation_failure" in src
    assert "protective close submission failed" in src
    assert "logger.critical" in src


def test_f2_missing_spec_for_held_position_escalates() -> None:
    src = _coord()
    assert "_find_specification_for_identity" in src
    assert "protective_specification_missing" in src
    assert "_route_protective_evaluation_failure" in src


def test_f3_on_market_time_does_not_set_has_received_quote() -> None:
    src = _coord()
    start = src.find("def on_market_time(")
    assert start != -1
    end = src.find("\n    def ", start + 1)
    body = src[start:end if end != -1 else start + 500]
    assert "_latest_market_timestamp" in body
    assert "_has_received_quote = True" not in body


def test_f3_accepted_quote_still_owns_fresh_quote_evidence() -> None:
    src = _coord()
    start = src.find("def on_live_quote(")
    assert start != -1
    end = src.find("\n    def ", start + 1)
    body = src[start:end if end != -1 else start + 50000]
    assert "_has_received_quote = True" in body
    assert "_latest_quote_market_timestamp" in body


def test_f4_risk_gate_rollover_failure_marks_persistence_failed() -> None:
    src = _coord()
    assert "def _handle_session_rollover" in src
    assert "Failed to advance risk gate state on session rollover" in src
    assert "_persistence_failed = True" in src
    assert "fail-closed" in src.lower()


def test_f5_startup_kill_cleanup_audit_failure_marks_persistence_failed() -> None:
    src = _coord()
    assert "STARTUP_KILL_CLEANUP_COMPLETED" in src
    assert "failed to append STARTUP_KILL_CLEANUP_COMPLETED audit" in src
    assert "marking persistence failed" in src


def test_f6_emit_alert_logs_critical_on_callback_failure() -> None:
    src = _safety()
    assert "def emit_alert" in src
    assert "safety alert delivery failed" in src
    assert "logger.critical" in src
