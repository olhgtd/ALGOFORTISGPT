"""Shared broker-neutral market-data transport runtime for Phase 6.

The runtime owns transport lifecycle, generation fencing, bounded reconnect and
bounded receive buffering. It has no RiskGate, Live-arm, or order authority.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Callable

from .contracts import (
    BrokerTransportDriver,
    FrameKind,
    HeartbeatMode,
    SubscriptionRequest,
    TransportConnection,
    TransportHealthState,
)
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
        self._desired_subscriptions: set[SubscriptionRequest] = set()
        self._active_subscriptions: dict[int, set[SubscriptionRequest]] = {}
        self._subscription_replays: set[tuple[int, SubscriptionRequest]] = set()
        self._last_frame_at: float | None = None
        self._last_data_at: float | None = None
        self._last_protocol_heartbeat_at: float | None = None

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

    @staticmethod
    def _subscription_key(request: SubscriptionRequest) -> tuple[str, tuple[str, ...]]:
        return request.data_mode, request.instruments

    @property
    def desired_subscriptions(self) -> tuple[SubscriptionRequest, ...]:
        return tuple(sorted(self._desired_subscriptions, key=self._subscription_key))

    @property
    def active_subscriptions(self) -> tuple[SubscriptionRequest, ...]:
        active = self._active_subscriptions.get(self._connection_generation, set())
        return tuple(sorted(active, key=self._subscription_key))

    @property
    def last_frame_at(self) -> float | None:
        return self._last_frame_at

    @property
    def last_data_at(self) -> float | None:
        return self._last_data_at

    @property
    def last_protocol_heartbeat_at(self) -> float | None:
        return self._last_protocol_heartbeat_at

    def _transition(self, state: TransportHealthState) -> None:
        if not isinstance(state, TransportHealthState):
            raise TypeError("state must be TransportHealthState")
        if state is self._state:
            return
        self._state = state
        self._state_history.append(state)

    def _record(self, code: str, *, generation: int | None = None, detail: str = "") -> None:
        self._events.append(
            TransportRuntimeEvent(code=code, state=self._state, connection_generation=generation, detail=detail)
        )

    def connect(self, auth_context: object) -> TransportConnection:
        self._transition(TransportHealthState.CONNECTING)
        self._transition(TransportHealthState.AUTHORIZING)
        authorized_endpoint = self._driver.authorize(auth_context)
        candidate_generation = self._connection_generation + 1
        connection = self._driver.connect(authorized_endpoint, connection_generation=candidate_generation)
        if not isinstance(connection, TransportConnection):
            raise TypeError("driver.connect must return TransportConnection")
        if connection.connection_generation != candidate_generation:
            raise ValueError("driver returned unexpected connection_generation")
        self._connection_generation = candidate_generation
        self._connection = connection
        self._queue.clear()
        self._transition(TransportHealthState.CONNECTED)
        self._record("CONNECTION_ACCEPTED", generation=candidate_generation)
        if self._desired_subscriptions:
            self.replay_desired_subscriptions()
        return connection

    def unexpected_disconnect(self, reason: str) -> None:
        self._connection = None
        self._queue.clear()
        self._transition(TransportHealthState.RECONNECTING)
        self._record("UNEXPECTED_DISCONNECT", generation=self._connection_generation or None, detail=type(reason).__name__ if not isinstance(reason, str) else "transport_disconnect")

    def reconnect(self, auth_context: object) -> bool:
        self._connection = None
        self._transition(TransportHealthState.RECONNECTING)
        for attempt in range(self._policy.max_reconnect_attempts):
            self._sleeper(self._policy.reconnect_backoff_seconds[attempt])
            try:
                self.connect(auth_context)
                self._record("RECONNECT_SUCCEEDED", generation=self._connection_generation)
                return True
            except Exception as exc:
                self._connection = None
                self._transition(TransportHealthState.RECONNECTING)
                self._record("RECONNECT_ATTEMPT_FAILED", generation=self._connection_generation or None, detail=type(exc).__name__)
        self._transition(TransportHealthState.FAILED_CLOSED)
        self._record("RECONNECT_EXHAUSTED", generation=self._connection_generation or None)
        return False

    def subscribe(self, request: SubscriptionRequest) -> bool:
        if not isinstance(request, SubscriptionRequest):
            raise TypeError("request must be SubscriptionRequest")
        if request in self._desired_subscriptions:
            return False
        self._desired_subscriptions.add(request)
        if self._connection is not None:
            self._transition(TransportHealthState.SUBSCRIBING)
            self._encode_subscription_once(request)
        return True

    def _encode_subscription_once(self, request: SubscriptionRequest) -> bool:
        key = (self._connection_generation, request)
        if self._connection is None or key in self._subscription_replays:
            return False
        self._driver.encode_subscribe(request)
        self._subscription_replays.add(key)
        self._record("SUBSCRIPTION_SENT", generation=self._connection_generation)
        return True

    def replay_desired_subscriptions(self) -> int:
        if self._connection is None or not self._desired_subscriptions:
            return 0
        self._transition(TransportHealthState.SUBSCRIBING)
        sent = 0
        for request in self.desired_subscriptions:
            sent += int(self._encode_subscription_once(request))
        return sent

    def acknowledge_subscription(self, connection_generation: int, request: SubscriptionRequest, acknowledged_instruments: tuple[str, ...]) -> bool:
        if connection_generation != self._connection_generation or self._connection is None:
            self._record("STALE_SUBSCRIPTION_ACK_REJECTED", generation=connection_generation)
            return False
        if request not in self._desired_subscriptions:
            self._record("UNKNOWN_SUBSCRIPTION_ACK_REJECTED", generation=connection_generation)
            return False
        if not isinstance(acknowledged_instruments, tuple):
            raise TypeError("acknowledged_instruments must be a tuple")
        expected = set(request.instruments)
        observed = {item.strip() for item in acknowledged_instruments if isinstance(item, str) and item.strip()}
        if observed != expected:
            self._record("PARTIAL_SUBSCRIPTION_ACK", generation=connection_generation)
            self._transition(TransportHealthState.SUBSCRIBING)
            return False
        active = self._active_subscriptions.setdefault(connection_generation, set())
        active.add(request)
        self._record("SUBSCRIPTION_ACKNOWLEDGED", generation=connection_generation)
        if self._desired_subscriptions.issubset(active):
            self._transition(TransportHealthState.HEALTHY)
        return True

    def unsubscribe(self, request: SubscriptionRequest) -> bool:
        if not isinstance(request, SubscriptionRequest):
            raise TypeError("request must be SubscriptionRequest")
        if request not in self._desired_subscriptions:
            return False
        self._desired_subscriptions.remove(request)
        if self._connection is not None:
            self._driver.encode_unsubscribe(request)
            self._record("UNSUBSCRIPTION_SENT", generation=self._connection_generation)
        self._active_subscriptions.get(self._connection_generation, set()).discard(request)
        self._subscription_replays.discard((self._connection_generation, request))
        active = self._active_subscriptions.get(self._connection_generation, set())
        if self._connection is not None and self._desired_subscriptions.issubset(active):
            self._transition(TransportHealthState.HEALTHY)
        return True

    @staticmethod
    def _timestamp(value: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ValueError("timestamp must be a non-negative number")
        return float(value)

    def observe_frame_activity(self, frame_kind: FrameKind, *, at: float) -> None:
        if not isinstance(frame_kind, FrameKind):
            raise TypeError("frame_kind must be FrameKind")
        stamp = self._timestamp(at)
        self._last_frame_at = stamp
        if frame_kind is FrameKind.DATA:
            self._last_data_at = stamp
            if self._driver.capabilities.heartbeat_mode is HeartbeatMode.DATA_ACTIVITY:
                self._last_protocol_heartbeat_at = stamp
        elif frame_kind is FrameKind.HEARTBEAT and self._driver.capabilities.heartbeat_mode is HeartbeatMode.PROVIDER_HEARTBEAT_FRAME:
            self._last_protocol_heartbeat_at = stamp

    def observe_protocol_heartbeat(self, *, at: float) -> None:
        stamp = self._timestamp(at)
        self._last_frame_at = stamp
        if self._driver.capabilities.heartbeat_mode is not HeartbeatMode.NONE:
            self._last_protocol_heartbeat_at = stamp

    def heartbeat_expired(self, *, now: float) -> bool:
        current = self._timestamp(now)
        if self._driver.capabilities.heartbeat_mode is HeartbeatMode.NONE:
            return False
        anchor = self._last_protocol_heartbeat_at
        if anchor is None:
            return True
        return current - anchor > self._policy.heartbeat_timeout_seconds

    def enqueue_frame(self, connection_generation: int, frame: object) -> bool:
        if isinstance(connection_generation, bool) or not isinstance(connection_generation, int) or connection_generation <= 0:
            raise ValueError("connection_generation must be a positive integer")
        if self._connection is None or connection_generation != self._connection_generation:
            self._record("STALE_GENERATION_REJECTED", generation=connection_generation)
            return False
        if len(self._queue) >= self._policy.receive_queue_capacity:
            target = TransportHealthState.DEGRADED if self._policy.queue_overflow_action is QueueOverflowAction.DEGRADED else TransportHealthState.FAILED_CLOSED
            self._transition(target)
            self._record("QUEUE_OVERFLOW", generation=connection_generation)
            return False
        self._queue.append((connection_generation, frame))
        return True


__all__ = ["TransportRuntimeEvent", "MarketDataTransportRuntime"]
