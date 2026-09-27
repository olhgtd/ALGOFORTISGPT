"""Shared broker-neutral market-data transport runtime for Phase 6.

The runtime owns transport lifecycle, generation fencing, bounded reconnect and
bounded receive buffering. It has no RiskGate, Live-arm, or order authority.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Callable

from .contracts import BrokerTransportDriver, TransportConnection, TransportHealthState
from .policy import BrokerTransportPolicy, QueueOverflowAction


@dataclass(frozen=True, slots=True)
class TransportRuntimeEvent:
    code: str
    state: TransportHealthState
    connection_generation: int | None = None
    detail: str = ""


class MarketDataTransportRuntime:
    """Shared transport lifecycle with fail-closed generation/backpressure rules."""

    def __init__(
        self,
        driver: BrokerTransportDriver,
        policy: BrokerTransportPolicy,
        *,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        if not isinstance(policy, BrokerTransportPolicy):
            raise TypeError("policy must be BrokerTransportPolicy")
        for name in (
            "broker_id", "capabilities", "authorize", "connect", "encode_subscribe",
            "encode_unsubscribe", "decode_frame", "classify_frame", "extract_source_sequence",
        ):
            if not hasattr(driver, name):
                raise TypeError(f"driver is missing BrokerTransportDriver member {name}")
        self._driver = driver
        self._policy = policy
        self._sleeper = sleeper if sleeper is not None else (lambda _seconds: None)
        self._state = TransportHealthState.STOPPED
        self._state_history: list[TransportHealthState] = [self._state]
        self._events: list[TransportRuntimeEvent] = []
        self._connection_generation = 0
        self._connection: TransportConnection | None = None
        self._queue: deque[tuple[int, object]] = deque()

    @property
    def state(self) -> TransportHealthState:
        return self._state

    @property
    def state_history(self) -> tuple[TransportHealthState, ...]:
        return tuple(self._state_history)

    @property
    def events(self) -> tuple[TransportRuntimeEvent, ...]:
        return tuple(self._events)

    @property
    def connection_generation(self) -> int:
        return self._connection_generation

    @property
    def connection(self) -> TransportConnection | None:
        return self._connection

    @property
    def queued_frame_count(self) -> int:
        return len(self._queue)

    def _transition(self, state: TransportHealthState) -> None:
        if not isinstance(state, TransportHealthState):
            raise TypeError("state must be TransportHealthState")
        if state is self._state:
            return
        self._state = state
        self._state_history.append(state)

    def _record(self, code: str, *, generation: int | None = None, detail: str = "") -> None:
        self._events.append(
            TransportRuntimeEvent(
                code=code,
                state=self._state,
                connection_generation=generation,
                detail=detail,
            )
        )

    def connect(self, auth_context: object) -> TransportConnection:
        self._transition(TransportHealthState.CONNECTING)
        self._transition(TransportHealthState.AUTHORIZING)
        authorized_endpoint = self._driver.authorize(auth_context)
        candidate_generation = self._connection_generation + 1
        connection = self._driver.connect(
            authorized_endpoint,
            connection_generation=candidate_generation,
        )
        if not isinstance(connection, TransportConnection):
            raise TypeError("driver.connect must return TransportConnection")
        if connection.connection_generation != candidate_generation:
            raise ValueError("driver returned unexpected connection_generation")
        self._connection_generation = candidate_generation
        self._connection = connection
        self._queue.clear()
        self._transition(TransportHealthState.CONNECTED)
        self._record("CONNECTION_ACCEPTED", generation=candidate_generation)
        return connection

    def unexpected_disconnect(self, reason: str) -> None:
        self._connection = None
        self._queue.clear()
        self._transition(TransportHealthState.RECONNECTING)
        self._record(
            "UNEXPECTED_DISCONNECT",
            generation=self._connection_generation or None,
            detail=type(reason).__name__ if not isinstance(reason, str) else "transport_disconnect",
        )

    def reconnect(self, auth_context: object) -> bool:
        self._connection = None
        self._transition(TransportHealthState.RECONNECTING)
        for attempt in range(self._policy.max_reconnect_attempts):
            delay = self._policy.reconnect_backoff_seconds[attempt]
            self._sleeper(delay)
            try:
                self.connect(auth_context)
                self._record("RECONNECT_SUCCEEDED", generation=self._connection_generation)
                return True
            except Exception as exc:
                self._connection = None
                self._transition(TransportHealthState.RECONNECTING)
                self._record(
                    "RECONNECT_ATTEMPT_FAILED",
                    generation=self._connection_generation or None,
                    detail=type(exc).__name__,
                )
        self._transition(TransportHealthState.FAILED_CLOSED)
        self._record("RECONNECT_EXHAUSTED", generation=self._connection_generation or None)
        return False

    def enqueue_frame(self, connection_generation: int, frame: object) -> bool:
        if isinstance(connection_generation, bool) or not isinstance(connection_generation, int) or connection_generation <= 0:
            raise ValueError("connection_generation must be a positive integer")
        if self._connection is None or connection_generation != self._connection_generation:
            self._record("STALE_GENERATION_REJECTED", generation=connection_generation)
            return False
        if len(self._queue) >= self._policy.receive_queue_capacity:
            target = (
                TransportHealthState.DEGRADED
                if self._policy.queue_overflow_action is QueueOverflowAction.DEGRADED
                else TransportHealthState.FAILED_CLOSED
            )
            self._transition(target)
            self._record("QUEUE_OVERFLOW", generation=connection_generation)
            return False
        self._queue.append((connection_generation, frame))
        return True


__all__ = ["TransportRuntimeEvent", "MarketDataTransportRuntime"]
