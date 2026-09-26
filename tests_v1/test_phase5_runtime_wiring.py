from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from engine.paper.contracts_v2 import PaperOperationalState
from engine.paper.phase5_runtime_v2 import Phase5PaperRuntime, Phase5RuntimeSafetyError

NOW = datetime(2026, 9, 26, 7, 0, tzinfo=timezone.utc)


class FakeDelegate:
    def __init__(self) -> None:
        self.initialize_calls = 0
        self.run_calls = 0
        self.shutdown_calls = 0

    def initialize(self) -> None:
        self.initialize_calls += 1

    def run(self, **kwargs):
        self.run_calls += 1
        return {"status": "paper-only", **kwargs}

    def shutdown(self) -> None:
        self.shutdown_calls += 1


class FakeLock:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed
        self.acquired = False
        self.release_calls = 0

    def acquire(self) -> bool:
        self.acquired = self.allowed
        return self.allowed

    def release(self) -> None:
        if self.acquired:
            self.release_calls += 1
        self.acquired = False


class FakePower:
    def __init__(self) -> None:
        self.active = False
        self.resume = False
        self.begin_calls = 0
        self.end_calls = 0

    def begin_session(self) -> None:
        self.begin_calls += 1
        self.active = True

    def end_session(self) -> None:
        self.end_calls += 1
        self.active = False

    def resume_detected(self) -> bool:
        return self.resume


class FakeClock:
    def __init__(self, healthy: bool = True) -> None:
        self.healthy = healthy

    def check(self, policy_ref: str | None):
        return SimpleNamespace(
            healthy=self.healthy,
            entry_eligible=self.healthy,
            reason="CLOCK_HEALTHY" if self.healthy else "CLOCK_DRIFT_EXCEEDED",
            policy_ref=policy_ref,
        )


class FakeAlerts:
    def __init__(self) -> None:
        self.envelopes = []

    def dispatch_critical(self, envelope):
        self.envelopes.append(envelope)
        return ()


class FakeRecovery:
    def __init__(self, final_state: PaperOperationalState) -> None:
        self.final_state = final_state
        self.calls = []

    def recover(self, trigger: str, session_id: str):
        self.calls.append((trigger, session_id))
        return SimpleNamespace(final_state=self.final_state, manual_resume_required=True)


def _runtime(
    *,
    delegate=None,
    lock=None,
    power=None,
    clock=None,
    alerts=None,
    recovery=None,
) -> Phase5PaperRuntime:
    return Phase5PaperRuntime(
        delegate=delegate or FakeDelegate(),
        session_id="paper-session-p5",
        instance_lock=lock or FakeLock(),
        power_session=power or FakePower(),
        clock_health=clock or FakeClock(),
        clock_policy_ref="TEST_ONLY/clock-fi-v1@1",
        alerts=alerts or FakeAlerts(),
        recovery=recovery or FakeRecovery(PaperOperationalState.READY_FOR_RESUME),
        now=lambda: NOW,
    )


def test_second_instance_fails_closed_before_delegate_initialization():
    delegate = FakeDelegate()
    alerts = FakeAlerts()
    runtime = _runtime(delegate=delegate, lock=FakeLock(False), alerts=alerts)

    with pytest.raises(Phase5RuntimeSafetyError, match="SECOND_INSTANCE"):
        runtime.initialize()

    assert delegate.initialize_calls == 0
    assert runtime.state is PaperOperationalState.HALTED
    assert len(alerts.envelopes) == 1


def test_unhealthy_clock_blocks_delegate_and_releases_host_ownership():
    delegate = FakeDelegate()
    lock = FakeLock()
    power = FakePower()
    runtime = _runtime(delegate=delegate, lock=lock, power=power, clock=FakeClock(False))

    with pytest.raises(Phase5RuntimeSafetyError, match="CLOCK_DRIFT_EXCEEDED"):
        runtime.initialize()

    assert delegate.initialize_calls == 0
    assert lock.acquired is False
    assert power.active is False
    assert runtime.state is PaperOperationalState.HALTED


def test_healthy_preflight_acquires_lock_prevents_sleep_then_initializes_delegate():
    delegate = FakeDelegate()
    lock = FakeLock()
    power = FakePower()
    runtime = _runtime(delegate=delegate, lock=lock, power=power)

    runtime.initialize()

    assert delegate.initialize_calls == 1
    assert lock.acquired is True
    assert power.active is True
    assert runtime.state is PaperOperationalState.HEALTHY


def test_sleep_resume_forces_recovery_and_never_auto_resumes_delegate_run():
    delegate = FakeDelegate()
    power = FakePower()
    recovery = FakeRecovery(PaperOperationalState.READY_FOR_RESUME)
    runtime = _runtime(delegate=delegate, power=power, recovery=recovery)
    runtime.initialize()
    power.resume = True

    with pytest.raises(Phase5RuntimeSafetyError, match="MANUAL_RESUME_REQUIRED"):
        runtime.run(max_frames=1)

    assert recovery.calls == [("SLEEP_RESUME", "paper-session-p5")]
    assert runtime.state is PaperOperationalState.READY_FOR_RESUME
    assert delegate.run_calls == 0


def test_manual_resume_is_explicit_and_run_only_proceeds_after_resume_signal_clears():
    delegate = FakeDelegate()
    power = FakePower()
    runtime = _runtime(delegate=delegate, power=power)
    runtime.initialize()
    power.resume = True
    with pytest.raises(Phase5RuntimeSafetyError):
        runtime.run()

    power.resume = False
    runtime.manual_resume()
    result = runtime.run(max_frames=2)

    assert runtime.state is PaperOperationalState.HEALTHY
    assert delegate.run_calls == 1
    assert result["max_frames"] == 2


def test_shutdown_always_releases_sleep_prevention_and_instance_lock():
    delegate = FakeDelegate()
    lock = FakeLock()
    power = FakePower()
    runtime = _runtime(delegate=delegate, lock=lock, power=power)
    runtime.initialize()

    runtime.shutdown()

    assert delegate.shutdown_calls == 1
    assert power.active is False
    assert lock.acquired is False
    assert power.end_calls == 1
    assert lock.release_calls == 1


def test_runtime_exposes_no_live_arm_or_order_mutation_capability():
    runtime = _runtime()
    assert not hasattr(runtime, "arm")
    assert not hasattr(runtime, "place_order")
    assert not hasattr(runtime, "submit_order")
