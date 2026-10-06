"""F8 — LivePaperCoordinator safety surface contracts.

These tests lock high-value kill-switch resume and protective routing behaviour
without enabling Live broker mutation.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from engine.paper.coordinator import LivePaperCoordinator
from engine.persistence.sqlite_store import PersistenceHealth


ROOT = Path(__file__).resolve().parents[1]
COORD_PATH = ROOT / "engine" / "paper" / "coordinator.py"


def _coord_source() -> str:
    return COORD_PATH.read_text(encoding="utf-8")


def test_f8_resume_requires_operator_id_in_source() -> None:
    src = _coord_source()
    assert "def resume_from_kill_switch" in src
    assert "operator_id is required to resume from kill switch" in src


def test_f8_resume_consults_phase8_before_clearing_latch() -> None:
    src = _coord_source()
    assert "request_global_resume" in src
    assert "Phase8 global resume rejected" in src
    assert "never clears a latch or auto-resumes" in src or "never" in src.lower()


def test_f8_resume_lists_fail_closed_prerequisites() -> None:
    src = _coord_source()
    for token in (
        "persistence_not_healthy",
        "accounting_integrity_breached",
        "feed_not_connected",
        "pending_broker_orders_exist",
        "no_fresh_market_evidence",
        "session_time_regression",
        "required_subscriptions_not_ready",
        "held_positions_valuation_not_live",
    ):
        assert token in src, f"missing prereq token: {token}"


def test_f8_protective_failure_routing_is_phase8_oriented() -> None:
    src = _coord_source()
    assert "def _route_protective_evaluation_failure" in src
    assert "StrategyCallbackFailure" in src
    assert "observe_protective_failure" in src or "PROTECTIVE_AMBIGUITY" in src
    assert "record_runtime_error" in src


def test_f8_no_disable_kill_switch_public_api() -> None:
    src = _coord_source()
    assert "def disable_kill" not in src
    assert "def clear_kill_switch" not in src


class _FakeSafety:
    def __init__(self, active: bool = True) -> None:
        self.is_kill_switch_active = active
        self._state = SimpleNamespace(name="KILL_SWITCH_ACTIVE" if active else "OPERATIONAL")

    @property
    def safety_state(self) -> object:
        return self._state

    def derive_effective_state(self, **_: object) -> object:
        return self._state

    def emit_alert(self, _alert: object) -> None:
        # Test double for the coordinator's alert side-effect.  Production
        # safety authority remains the real SafetyManager.
        return None


class _FakePhase8:
    def __init__(self, approved: bool, failed: list[str] | None = None) -> None:
        self._approved = approved
        self._failed = failed or ["phase8_manual_review_required"]

    def request_global_resume(self, *, operator_id: str) -> object:
        return SimpleNamespace(
            approved=self._approved,
            failed_prerequisites=list(self._failed),
        )


class _FailingLoadPersistence:
    # Match the real SQLitePaperStateStore health contract used by
    # LivePaperCoordinator.safety_state.
    health = PersistenceHealth.HEALTHY
    is_healthy = True

    def load_state(self) -> object:
        raise OSError("persistence load unavailable")

    def append_audit_events(self, events: object) -> None:
        raise OSError("audit append unavailable")


def _minimal_coordinator(*, phase8: object | None = None, persistence: object | None = None,
                         has_quote: bool = True) -> LivePaperCoordinator:
    coord = object.__new__(LivePaperCoordinator)
    coord._safety = _FakeSafety(active=True)
    coord._phase8_safety = phase8
    coord._persistence_store = persistence
    coord._persistence_failed = False
    coord._virtual_account = None
    from engine.data.feeds.live_feed import FeedConnectionState
    coord._live_feed = SimpleNamespace(connection_state=FeedConnectionState.CONNECTED)
    coord._paper_broker = SimpleNamespace(pending_orders=[])
    coord._has_received_quote = has_quote
    coord._reconnected_waiting_for_quote = False
    coord._latest_market_timestamp = (
        datetime(2026, 10, 6, 10, 0, tzinfo=timezone.utc) if has_quote else None
    )
    coord._last_canonical_session_date = date(2026, 10, 6)
    coord._quote_cache = MagicMock()
    return coord  # type: ignore[return-value]


def test_f8_resume_rejects_empty_operator_id() -> None:
    coord = _minimal_coordinator()
    with pytest.raises(ValueError, match="operator_id is required"):
        LivePaperCoordinator.resume_from_kill_switch(coord, operator_id="")


def test_f8_resume_rejects_when_phase8_denies() -> None:
    coord = _minimal_coordinator(
        phase8=_FakePhase8(approved=False, failed=["protective_latch"]),
    )
    result = LivePaperCoordinator.resume_from_kill_switch(coord, operator_id="owner-1")
    assert result.success is False
    assert "Phase8 global resume rejected" in result.reason
    assert result.failed_prerequisites == ["protective_latch"]


def test_f8_resume_rejects_without_fresh_market_evidence() -> None:
    coord = _minimal_coordinator(
        phase8=_FakePhase8(approved=True),
        has_quote=False,
    )
    result = LivePaperCoordinator.resume_from_kill_switch(coord, operator_id="owner-1")
    assert result.success is False
    assert "no_fresh_market_evidence" in result.failed_prerequisites


def test_f8_resume_rejects_when_pending_broker_orders() -> None:
    coord = _minimal_coordinator(phase8=_FakePhase8(approved=True))
    coord._paper_broker.pending_orders = [object()]
    result = LivePaperCoordinator.resume_from_kill_switch(coord, operator_id="owner-1")
    assert result.success is False
    assert "pending_broker_orders_exist" in result.failed_prerequisites


def test_f8_persistence_load_failure_is_a_resume_prerequisite_failure() -> None:
    coord = _minimal_coordinator(
        phase8=_FakePhase8(approved=True),
        persistence=_FailingLoadPersistence(),
    )
    result = LivePaperCoordinator.resume_from_kill_switch(coord, operator_id="owner-1")
    assert result.success is False
    assert "persistence_check_failed" in result.failed_prerequisites


def test_f8_rejected_resume_audit_failure_is_critical_logged_and_stays_rejected(
    caplog: pytest.LogCaptureFixture,
) -> None:
    coord = _minimal_coordinator(
        phase8=_FakePhase8(approved=True),
        persistence=_FailingLoadPersistence(),
    )
    with caplog.at_level("CRITICAL"):
        result = LivePaperCoordinator.resume_from_kill_switch(coord, operator_id="owner-1")
    assert result.success is False
    assert "persistence_check_failed" in result.failed_prerequisites
    assert "failed to append RESUME_REJECTED audit" in caplog.text
