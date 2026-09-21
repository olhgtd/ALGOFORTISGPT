"""Phase 1 RED tests for injectable deterministic runtime primitives."""

from datetime import datetime, timedelta, timezone

import pytest

from engine.core.runtime import (
    DeterministicIdGenerator,
    DeterministicSeedSource,
    FixedClock,
    SystemClock,
)


def test_fixed_clock_normalizes_utc_and_exposes_injected_calendar() -> None:
    ist = timezone(timedelta(hours=5, minutes=30))
    calendar = object()
    clock = FixedClock(
        datetime(2026, 9, 21, 6, 0, tzinfo=ist),
        monotonic_ns_value=123456789,
        session_calendar_value=calendar,
    )

    assert clock.now_utc() == datetime(2026, 9, 21, 0, 30, tzinfo=timezone.utc)
    assert clock.monotonic_ns() == 123456789
    assert clock.session_calendar() is calendar


def test_fixed_clock_rejects_naive_wall_time_and_negative_monotonic_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        FixedClock(datetime(2026, 9, 21, 0, 30), 0, object())

    with pytest.raises(ValueError, match="monotonic"):
        FixedClock(datetime(2026, 9, 21, tzinfo=timezone.utc), -1, object())


def test_system_clock_is_utc_aware_and_monotonic() -> None:
    calendar = object()
    clock = SystemClock(lambda: calendar)

    first = clock.monotonic_ns()
    second = clock.monotonic_ns()
    now = clock.now_utc()

    assert now.utcoffset() == timedelta(0)
    assert second >= first
    assert clock.session_calendar() is calendar


def test_deterministic_seed_source_replays_and_separates_scope() -> None:
    a = DeterministicSeedSource(42)
    b = DeterministicSeedSource(42)

    assert a.seed_for("run-001", "bootstrap") == b.seed_for("run-001", "bootstrap")
    assert a.seed_for("run-001", "bootstrap") != a.seed_for("run-001", "monte-carlo")
    assert a.seed_for("run-001", "bootstrap") != a.seed_for("run-002", "bootstrap")
    assert 0 <= a.seed_for("run-001", "bootstrap") < 2**64


def test_deterministic_seed_source_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="root_seed"):
        DeterministicSeedSource(-1)

    source = DeterministicSeedSource(7)
    with pytest.raises(ValueError, match="run_id"):
        source.seed_for("", "component")
    with pytest.raises(ValueError, match="component"):
        source.seed_for("run", "   ")


def test_deterministic_id_generator_replays_unique_sortable_sequence() -> None:
    fixed_time = datetime(2026, 9, 21, 0, 30, tzinfo=timezone.utc)
    clock_a = FixedClock(fixed_time, 100, object())
    clock_b = FixedClock(fixed_time, 100, object())
    generator_a = DeterministicIdGenerator(clock_a, DeterministicSeedSource(99), "run-001")
    generator_b = DeterministicIdGenerator(clock_b, DeterministicSeedSource(99), "run-001")

    ids_a = [generator_a.new_id("order") for _ in range(3)]
    ids_b = [generator_b.new_id("order") for _ in range(3)]

    assert ids_a == ids_b
    assert len(set(ids_a)) == 3
    assert ids_a == sorted(ids_a)
    assert all(value.startswith("af2_") for value in ids_a)


def test_deterministic_id_generator_scope_and_run_are_bound_into_identity() -> None:
    fixed_time = datetime(2026, 9, 21, 0, 30, tzinfo=timezone.utc)
    seed = DeterministicSeedSource(123)

    order_id = DeterministicIdGenerator(FixedClock(fixed_time, 0, object()), seed, "run-a").new_id("order")
    audit_id = DeterministicIdGenerator(FixedClock(fixed_time, 0, object()), seed, "run-a").new_id("audit")
    other_run_id = DeterministicIdGenerator(FixedClock(fixed_time, 0, object()), seed, "run-b").new_id("order")

    assert len({order_id, audit_id, other_run_id}) == 3

    generator = DeterministicIdGenerator(FixedClock(fixed_time, 0, object()), seed, "run-a")
    with pytest.raises(ValueError, match="kind"):
        generator.new_id("")
