"""Versioned broker-neutral market-data transport policy for Phase 6.

No production broker limits are guessed here. Callers must inject a complete,
versioned policy; invalid or missing required values fail closed upstream.
"""

from __future__ import annotations

from dataclasses import dataclass


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _positive_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{field} must be a positive number")
    return float(value)


@dataclass(frozen=True, slots=True)
class BrokerTransportPolicy:
    policy_id: str
    version: str
    max_reconnect_attempts: int
    reconnect_backoff_seconds: tuple[float, ...]
    receive_queue_capacity: int
    heartbeat_timeout_seconds: float
    stale_after_seconds: float
    max_subscriptions_per_socket: int
    subscription_batch_limit: int
    max_connections: int
    test_only: bool = False

    def __post_init__(self) -> None:
        policy_id = _text(self.policy_id, "policy_id")
        version = _text(self.version, "version")
        if not isinstance(self.test_only, bool):
            raise TypeError("test_only must be bool")
        if self.test_only and not policy_id.startswith("TEST_ONLY/"):
            raise ValueError("TEST_ONLY policy_id must start with TEST_ONLY/")
        if not self.test_only and policy_id.startswith("TEST_ONLY/"):
            raise ValueError("TEST_ONLY policy_id requires test_only=True")
        attempts = _non_negative_int(self.max_reconnect_attempts, "max_reconnect_attempts")
        if not isinstance(self.reconnect_backoff_seconds, tuple):
            raise TypeError("reconnect_backoff_seconds must be a tuple")
        backoffs: list[float] = []
        for value in self.reconnect_backoff_seconds:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ValueError("reconnect_backoff_seconds values must be non-negative numbers")
            backoffs.append(float(value))
        if len(backoffs) < attempts:
            raise ValueError("reconnect_backoff_seconds must cover max_reconnect_attempts")
        object.__setattr__(self, "policy_id", policy_id)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "max_reconnect_attempts", attempts)
        object.__setattr__(self, "reconnect_backoff_seconds", tuple(backoffs))
        object.__setattr__(self, "receive_queue_capacity", _positive_int(self.receive_queue_capacity, "receive_queue_capacity"))
        object.__setattr__(self, "heartbeat_timeout_seconds", _positive_number(self.heartbeat_timeout_seconds, "heartbeat_timeout_seconds"))
        object.__setattr__(self, "stale_after_seconds", _positive_number(self.stale_after_seconds, "stale_after_seconds"))
        object.__setattr__(self, "max_subscriptions_per_socket", _positive_int(self.max_subscriptions_per_socket, "max_subscriptions_per_socket"))
        object.__setattr__(self, "subscription_batch_limit", _positive_int(self.subscription_batch_limit, "subscription_batch_limit"))
        object.__setattr__(self, "max_connections", _positive_int(self.max_connections, "max_connections"))
        if self.subscription_batch_limit > self.max_subscriptions_per_socket:
            raise ValueError("subscription_batch_limit cannot exceed max_subscriptions_per_socket")

    @property
    def reference(self) -> str:
        return f"{self.policy_id}@{self.version}"


__all__ = ["BrokerTransportPolicy"]
