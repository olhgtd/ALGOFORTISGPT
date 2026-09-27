"""Broker-neutral market-data transport contracts for AlgoFortis Phase 6.

These are market-data-only contracts. They carry no RiskGate, Live-arm, or
broker-order mutation authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Protocol, runtime_checkable

from .sequence import SequenceScope, SequenceSemantics, SourceSequence


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _aware(value: object, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value


def _generation(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("connection_generation must be a positive integer")
    return value


class BrokerId(str, Enum):
    ANGELONE = "ANGELONE"
    ZERODHA = "ZERODHA"
    DHAN = "DHAN"
    UPSTOX = "UPSTOX"


class TransportHealthState(str, Enum):
    STOPPED = "STOPPED"
    CONNECTING = "CONNECTING"
    AUTHORIZING = "AUTHORIZING"
    CONNECTED = "CONNECTED"
    SUBSCRIBING = "SUBSCRIBING"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    RECONNECTING = "RECONNECTING"
    FAILED_CLOSED = "FAILED_CLOSED"


class HeartbeatMode(str, Enum):
    PROTOCOL_PING_PONG = "PROTOCOL_PING_PONG"
    PROVIDER_HEARTBEAT_FRAME = "PROVIDER_HEARTBEAT_FRAME"
    DATA_ACTIVITY = "DATA_ACTIVITY"
    NONE = "NONE"


class FrameKind(str, Enum):
    DATA = "DATA"
    HEARTBEAT = "HEARTBEAT"
    SUBSCRIPTION_ACK = "SUBSCRIPTION_ACK"
    AUTH = "AUTH"
    CONTROL = "CONTROL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class TransportCapabilities:
    broker_id: BrokerId
    heartbeat_mode: HeartbeatMode
    source_sequence_semantics: SequenceSemantics
    source_sequence_scope: SequenceScope
    supports_subscription_ack: bool

    def __post_init__(self) -> None:
        if not isinstance(self.broker_id, BrokerId):
            raise TypeError("broker_id must be BrokerId")
        if not isinstance(self.heartbeat_mode, HeartbeatMode):
            raise TypeError("heartbeat_mode must be HeartbeatMode")
        if not isinstance(self.source_sequence_semantics, SequenceSemantics):
            raise TypeError("source_sequence_semantics must be SequenceSemantics")
        if not isinstance(self.source_sequence_scope, SequenceScope):
            raise TypeError("source_sequence_scope must be SequenceScope")
        if not isinstance(self.supports_subscription_ack, bool):
            raise TypeError("supports_subscription_ack must be bool")
        if self.source_sequence_semantics is SequenceSemantics.UNAVAILABLE:
            if self.source_sequence_scope is not SequenceScope.NONE:
                raise ValueError("UNAVAILABLE sequence capability must use NONE scope")
        elif self.source_sequence_scope is SequenceScope.NONE:
            raise ValueError("available sequence capability must declare a non-NONE scope")


@dataclass(frozen=True, slots=True)
class TransportConnection:
    connection_id: str
    connection_generation: int
    endpoint_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "connection_id", _text(self.connection_id, "connection_id"))
        object.__setattr__(self, "connection_generation", _generation(self.connection_generation))
        endpoint = _text(self.endpoint_ref, "endpoint_ref")
        if not endpoint.startswith("wss://"):
            raise ValueError("endpoint_ref must be a wss:// reference")
        object.__setattr__(self, "endpoint_ref", endpoint)


@dataclass(frozen=True, slots=True)
class SubscriptionRequest:
    instruments: tuple[str, ...]
    data_mode: str

    def __post_init__(self) -> None:
        if not isinstance(self.instruments, tuple) or not self.instruments:
            raise ValueError("instruments must be a non-empty tuple")
        normalized: list[str] = []
        seen: set[str] = set()
        for token in self.instruments:
            item = _text(token, "instrument_token")
            if item not in seen:
                normalized.append(item)
                seen.add(item)
        object.__setattr__(self, "instruments", tuple(normalized))
        object.__setattr__(self, "data_mode", _text(self.data_mode, "data_mode"))


@dataclass(frozen=True, slots=True)
class ProviderEnvelope:
    broker_id: BrokerId
    connection_id: str
    connection_generation: int
    instrument_token: str
    receive_timestamp: datetime
    exchange_timestamp: datetime | None
    source_sequence: SourceSequence | None
    frame_kind: FrameKind
    decoded_payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.broker_id, BrokerId):
            raise TypeError("broker_id must be BrokerId")
        object.__setattr__(self, "connection_id", _text(self.connection_id, "connection_id"))
        object.__setattr__(self, "connection_generation", _generation(self.connection_generation))
        object.__setattr__(self, "instrument_token", _text(self.instrument_token, "instrument_token"))
        object.__setattr__(self, "receive_timestamp", _aware(self.receive_timestamp, "receive_timestamp"))
        if self.exchange_timestamp is not None:
            object.__setattr__(self, "exchange_timestamp", _aware(self.exchange_timestamp, "exchange_timestamp"))
        if self.source_sequence is not None and not isinstance(self.source_sequence, SourceSequence):
            raise TypeError("source_sequence must be SourceSequence or None")
        if not isinstance(self.frame_kind, FrameKind):
            raise TypeError("frame_kind must be FrameKind")
        if not isinstance(self.decoded_payload, Mapping):
            raise TypeError("decoded_payload must be a mapping")
        object.__setattr__(self, "decoded_payload", MappingProxyType(dict(self.decoded_payload)))


@runtime_checkable
class BrokerTransportDriver(Protocol):
    broker_id: BrokerId
    capabilities: TransportCapabilities

    def authorize(self, auth_context: object) -> object: ...
    def connect(self, authorized_endpoint: object, *, connection_generation: int) -> TransportConnection: ...
    def encode_subscribe(self, request: SubscriptionRequest) -> object: ...
    def encode_unsubscribe(self, request: SubscriptionRequest) -> object: ...
    def decode_frame(self, frame: object, *, connection: TransportConnection) -> ProviderEnvelope: ...
    def classify_frame(self, frame: object) -> FrameKind: ...
    def extract_source_sequence(self, frame: object) -> SourceSequence | None: ...


__all__ = [
    "BrokerId",
    "TransportHealthState",
    "HeartbeatMode",
    "FrameKind",
    "TransportCapabilities",
    "TransportConnection",
    "SubscriptionRequest",
    "ProviderEnvelope",
    "BrokerTransportDriver",
]
