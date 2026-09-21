"""AlgoFortis V2 cross-cutting runtime primitives.

This module provides the injectable time, seed and identifier contracts required by
AF2-ARC-003.  It is deliberately additive: existing V1 components are not rewired
by this slice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from secrets import token_hex
from threading import Lock
from time import monotonic_ns as system_monotonic_ns
from typing import Callable, Protocol, runtime_checkable


_UTC_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_SEED_DOMAIN = b"algofortis-seed/v1"
_ID_DOMAIN = b"algofortis-id/v1"


def _required_label(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _require_aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("wall time must be timezone-aware")
    return value.astimezone(timezone.utc)


def _unix_milliseconds(value: datetime) -> int:
    utc_value = _require_aware(value)
    delta = utc_value - _UTC_EPOCH
    milliseconds = (
        delta.days * 86_400_000
        + delta.seconds * 1_000
        + delta.microseconds // 1_000
    )
    if milliseconds < 0 or milliseconds >= 2**48:
        raise ValueError("wall time is outside the supported sortable-ID range")
    return milliseconds


@runtime_checkable
class Clock(Protocol):
    """Injected wall/monotonic time plus the active session calendar."""

    def now_utc(self) -> datetime:
        """Return a timezone-aware UTC wall-clock value."""

    def monotonic_ns(self) -> int:
        """Return a non-decreasing process-local monotonic counter."""

    def session_calendar(self) -> object:
        """Return the injected session-calendar authority for this runtime."""


@runtime_checkable
class SeedSource(Protocol):
    """Deterministic seed derivation contract for a run/component pair."""

    def seed_for(self, run_id: str, component: str) -> int:
        """Return an unsigned 64-bit seed for the named run component."""


@runtime_checkable
class IdGenerator(Protocol):
    """Sortable identifier generator contract."""

    def new_id(self, kind: str) -> str:
        """Return the next identifier for an entity/event kind."""


class SystemClock:
    """Production clock backed by UTC wall time and OS monotonic time.

    The session calendar remains injected rather than discovered globally so domain
    code cannot silently depend on ambient market-calendar state.
    """

    def __init__(self, session_calendar_provider: Callable[[], object]) -> None:
        if not callable(session_calendar_provider):
            raise TypeError("session_calendar_provider must be callable")
        self._session_calendar_provider = session_calendar_provider

    def now_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic_ns(self) -> int:
        return system_monotonic_ns()

    def session_calendar(self) -> object:
        value = self._session_calendar_provider()
        if value is None:
            raise RuntimeError("session calendar provider returned no calendar")
        return value


@dataclass(frozen=True, slots=True)
class FixedClock:
    """Immutable deterministic clock for tests, replay and pure simulations."""

    wall_time_utc: datetime
    monotonic_ns_value: int
    session_calendar_value: object

    def __post_init__(self) -> None:
        object.__setattr__(self, "wall_time_utc", _require_aware(self.wall_time_utc))
        if (
            isinstance(self.monotonic_ns_value, bool)
            or not isinstance(self.monotonic_ns_value, int)
            or self.monotonic_ns_value < 0
        ):
            raise ValueError("monotonic_ns_value must be a non-negative integer")
        if self.session_calendar_value is None:
            raise ValueError("session_calendar_value must not be None")

    def now_utc(self) -> datetime:
        return self.wall_time_utc

    def monotonic_ns(self) -> int:
        return self.monotonic_ns_value

    def session_calendar(self) -> object:
        return self.session_calendar_value


@dataclass(frozen=True, slots=True)
class DeterministicSeedSource:
    """Stable domain-separated 64-bit seed derivation.

    The root seed is expected to be persisted in the run manifest.  No Python hash()
    value is used, so results are stable across interpreter processes and machines.
    """

    root_seed: int

    def __post_init__(self) -> None:
        if isinstance(self.root_seed, bool) or not isinstance(self.root_seed, int) or self.root_seed < 0:
            raise ValueError("root_seed must be a non-negative integer")

    def seed_for(self, run_id: str, component: str) -> int:
        run = _required_label(run_id, "run_id")
        part = _required_label(component, "component")
        payload = b"\0".join(
            (
                _SEED_DOMAIN,
                str(self.root_seed).encode("ascii"),
                run.encode("utf-8"),
                part.encode("utf-8"),
            )
        )
        return int.from_bytes(sha256(payload).digest()[:8], "big", signed=False)


class DeterministicIdGenerator:
    """Replayable, lexicographically sortable identifier generator.

    IDs contain a 48-bit UTC millisecond prefix, a 32-bit monotonic sequence and an
    80-bit deterministic digest.  The last timestamp is clamped so a wall-clock
    rollback cannot make a later generated ID sort before an earlier one.
    """

    def __init__(self, clock: Clock, seed_source: SeedSource, run_id: str) -> None:
        self._clock = clock
        self._seed_source = seed_source
        self._run_id = _required_label(run_id, "run_id")
        self._counter = 0
        self._last_timestamp_ms = 0
        self._lock = Lock()

    def new_id(self, kind: str) -> str:
        entity_kind = _required_label(kind, "kind")
        with self._lock:
            timestamp_ms = max(_unix_milliseconds(self._clock.now_utc()), self._last_timestamp_ms)
            self._last_timestamp_ms = timestamp_ms
            counter = self._counter
            self._counter += 1
            if counter >= 2**32:
                raise OverflowError("deterministic ID sequence exhausted")

            seed = self._seed_source.seed_for(self._run_id, f"id:{entity_kind}")
            payload = b"\0".join(
                (
                    _ID_DOMAIN,
                    seed.to_bytes(8, "big", signed=False),
                    self._run_id.encode("utf-8"),
                    entity_kind.encode("utf-8"),
                    counter.to_bytes(4, "big", signed=False),
                )
            )
            entropy = sha256(payload).hexdigest()[:20]
            return f"af2_{timestamp_ms:012x}{counter:08x}{entropy}"


class SystemIdGenerator:
    """Production sortable IDs with cryptographic entropy.

    Time still comes from the injected Clock.  Random entropy is intentionally not
    replayable; deterministic/replay paths use DeterministicIdGenerator instead.
    """

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._counter = 0
        self._last_timestamp_ms = 0
        self._lock = Lock()

    def new_id(self, kind: str) -> str:
        _required_label(kind, "kind")
        with self._lock:
            timestamp_ms = max(_unix_milliseconds(self._clock.now_utc()), self._last_timestamp_ms)
            self._last_timestamp_ms = timestamp_ms
            counter = self._counter
            self._counter += 1
            if counter >= 2**32:
                raise OverflowError("system ID sequence exhausted")
            return f"af2_{timestamp_ms:012x}{counter:08x}{token_hex(10)}"


__all__ = [
    "Clock",
    "SeedSource",
    "IdGenerator",
    "SystemClock",
    "FixedClock",
    "DeterministicSeedSource",
    "DeterministicIdGenerator",
    "SystemIdGenerator",
]
