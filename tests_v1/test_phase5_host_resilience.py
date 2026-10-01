from __future__ import annotations

from dataclasses import dataclass

from engine.host.clock_health import ClockHealthPolicy, ClockHealthProvider
from engine.host.instance_lock import InstanceLock
from engine.host.power_session import PowerSessionProvider, classify_power_event
from engine.host.watchdog_policy import WatchdogPolicy
from engine.paper.contracts_v2 import PaperOperationalState


class FakeLockBackend:
    def __init__(self) -> None:
        self.held: set[str] = set()

    def try_acquire(self, key: str) -> bool:
        if key in self.held:
            return False
        self.held.add(key)
        return True

    def release(self, key: str) -> None:
        self.held.discard(key)


class FakePowerBackend:
    def __init__(self, *, resume: bool = False) -> None:
        self.resume = resume
        self.prevent_calls = 0
        self.release_calls = 0

    def request_sleep_prevention(self) -> None:
        self.prevent_calls += 1

    def release_sleep_prevention(self) -> None:
        self.release_calls += 1

    def resume_detected(self) -> bool:
        return self.resume


@dataclass
class FakeDriftSource:
    drift_ms: int

    def observed_drift_ms(self) -> int:
        return self.drift_ms


def _clock_policy() -> ClockHealthPolicy:
    return ClockHealthPolicy(
        policy_id="TEST_ONLY/clock-fi-v1",
        version="1",
        max_abs_drift_ms=500,
        test_only=True,
    )


def test_second_instance_fails_closed_until_owner_releases_lock():
    backend = FakeLockBackend()
    first = InstanceLock(backend, lock_key="paper/profile-a")
    second = InstanceLock(backend, lock_key="paper/profile-a")

    assert first.acquire() is True
    assert second.acquire() is False

    first.release()
    assert second.acquire() is True


def test_missing_clock_policy_fails_closed_for_entry_eligibility():
    provider = ClockHealthProvider(
        policies={},
        drift_source=FakeDriftSource(drift_ms=0),
    )

    result = provider.check(None)

    assert result.healthy is False
    assert result.entry_eligible is False
    assert result.reason == "MISSING_CLOCK_POLICY"
    assert result.policy_ref is None


def test_unknown_clock_policy_reference_fails_closed():
    provider = ClockHealthProvider(
        policies={},
        drift_source=FakeDriftSource(drift_ms=0),
    )

    result = provider.check("clock/missing@1")

    assert result.healthy is False
    assert result.entry_eligible is False
    assert result.reason == "UNKNOWN_CLOCK_POLICY"


def test_explicit_test_clock_policy_controls_health_without_production_default():
    policy = _clock_policy()
    provider = ClockHealthProvider(
        policies={policy.reference: policy},
        drift_source=FakeDriftSource(drift_ms=501),
    )

    unhealthy = provider.check(policy.reference)
    assert unhealthy.healthy is False
    assert unhealthy.entry_eligible is False
    assert unhealthy.reason == "CLOCK_DRIFT_EXCEEDED"

    healthy_provider = ClockHealthProvider(
        policies={policy.reference: policy},
        drift_source=FakeDriftSource(drift_ms=-499),
    )
    healthy = healthy_provider.check(policy.reference)
    assert healthy.healthy is True
    assert healthy.entry_eligible is True
    assert healthy.reason == "CLOCK_HEALTHY"


def test_test_only_clock_policy_cannot_masquerade_as_production_policy():
    try:
        ClockHealthPolicy(
            policy_id="production/clock",
            version="1",
            max_abs_drift_ms=500,
            test_only=True,
        )
    except ValueError as error:
        assert "TEST_ONLY" in str(error)
    else:
        raise AssertionError("TEST_ONLY clock policy accepted a production-looking id")


def test_active_session_requests_temporary_sleep_prevention_and_releases_it():
    backend = FakePowerBackend()
    provider = PowerSessionProvider(backend)

    provider.begin_session()
    provider.end_session()

    assert backend.prevent_calls == 1
    assert backend.release_calls == 1


def test_resume_discontinuity_requires_recovery_before_new_entries():
    provider = PowerSessionProvider(FakePowerBackend(resume=True))

    assert classify_power_event(provider) is PaperOperationalState.RECOVERY


def test_no_resume_discontinuity_does_not_invent_recovery():
    provider = PowerSessionProvider(FakePowerBackend(resume=False))

    assert classify_power_event(provider) is PaperOperationalState.HEALTHY


def test_watchdog_restart_target_is_recovery_only_and_never_auto_arms():
    policy = WatchdogPolicy()

    assert policy.restart_target() is PaperOperationalState.RECOVERY
    assert policy.auto_arm_allowed is False
