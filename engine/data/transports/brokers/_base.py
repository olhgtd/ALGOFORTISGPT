"""Shared mechanics for thin provider-specific Phase-6 market-data drivers.

This module deliberately contains no reconnect loop, RiskGate dependency,
Live-arm state, or broker order mutation surface.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import datetime
from typing import Any

from engine.data.transports.contracts import (
    BrokerId,
    FrameKind,
    ProviderEnvelope,
    ProviderEnvelopeBatch,
    TransportCapabilities,
    TransportConnection,
)
from engine.data.transports.sequence import SourceSequence


class TransportDriverError(ValueError):
    pass


def _aware(value: object, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise TransportDriverError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise TransportDriverError(f"{field} must be timezone-aware")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TransportDriverError(f"{field} must be a non-empty string")
    return value.strip()


class ThinInjectedTransportDriver:
    """Provider-edge driver using injected I/O seams and no lifecycle authority."""

    broker_id: BrokerId
    capabilities: TransportCapabilities

    def __init__(
        self,
        *,
        endpoint_provider: Callable[[object], str],
        connector: Callable[[str], str],
        sender: Callable[[object], None],
        decoder: Callable[[object], object],
    ) -> None:
        for name, value in (
            ("endpoint_provider", endpoint_provider),
            ("connector", connector),
            ("sender", sender),
            ("decoder", decoder),
        ):
            if not callable(value):
                raise TypeError(f"{name} must be callable")
        self._endpoint_provider = endpoint_provider
        self._connector = connector
        self._sender = sender
        self._decoder = decoder

    def authorize(self, auth_context: object) -> str:
        endpoint = _text(self._endpoint_provider(auth_context), "authorized endpoint")
        if not endpoint.startswith("wss://"):
            raise TransportDriverError("authorized endpoint must use wss://")
        return endpoint

    def connect(self, authorized_endpoint: object, *, connection_generation: int) -> TransportConnection:
        endpoint = _text(authorized_endpoint, "authorized endpoint")
        if not endpoint.startswith("wss://"):
            raise TransportDriverError("authorized endpoint must use wss://")
        connection_id = _text(self._connector(endpoint), "connection_id")
        return TransportConnection(connection_id, connection_generation, endpoint)

    def _send(self, payload: object) -> object:
        self._sender(payload)
        return payload

    def _decoded_packets(self, frame: object) -> tuple[Mapping[str, Any], ...]:
        decoded = self._decoder(frame)
        if isinstance(decoded, Mapping):
            items: Iterable[object] = (decoded,)
        elif isinstance(decoded, (tuple, list)):
            items = decoded
        else:
            raise TransportDriverError("decoder must return a mapping or sequence of mappings")
        packets: list[Mapping[str, Any]] = []
        for item in items:
            if not isinstance(item, Mapping):
                raise TransportDriverError("decoded packet must be a mapping")
            packets.append(item)
        return tuple(packets)

    @staticmethod
    def _frame_kind_from_packet(packet: Mapping[str, Any]) -> FrameKind:
        raw = packet.get("frame_kind", FrameKind.DATA)
        if isinstance(raw, FrameKind):
            return raw
        try:
            return FrameKind(str(raw).upper())
        except ValueError:
            return FrameKind.UNKNOWN

    def _source_sequence_for_packet(self, packet: Mapping[str, Any]) -> SourceSequence | None:
        return self.extract_source_sequence(packet)

    def _to_envelope(
        self,
        packet: Mapping[str, Any],
        *,
        connection: TransportConnection,
    ) -> ProviderEnvelope:
        token = _text(packet.get("instrument_token"), "instrument_token")
        receive_timestamp = _aware(packet.get("receive_timestamp"), "receive_timestamp")
        exchange_raw = packet.get("exchange_timestamp")
        exchange_timestamp = None if exchange_raw is None else _aware(exchange_raw, "exchange_timestamp")
        payload = packet.get("decoded_payload", packet)
        if not isinstance(payload, Mapping):
            raise TransportDriverError("decoded_payload must be a mapping")
        return ProviderEnvelope(
            broker_id=self.broker_id,
            connection_id=connection.connection_id,
            connection_generation=connection.connection_generation,
            instrument_token=token,
            receive_timestamp=receive_timestamp,
            exchange_timestamp=exchange_timestamp,
            source_sequence=self._source_sequence_for_packet(packet),
            frame_kind=self._frame_kind_from_packet(packet),
            decoded_payload=payload,
        )

    def decode_frame(self, frame: object, *, connection: TransportConnection) -> ProviderEnvelopeBatch:
        if not isinstance(connection, TransportConnection):
            raise TypeError("connection must be TransportConnection")
        return tuple(self._to_envelope(packet, connection=connection) for packet in self._decoded_packets(frame))

    def classify_frame(self, frame: object) -> FrameKind:
        packets = self._decoded_packets(frame)
        if not packets:
            return FrameKind.UNKNOWN
        kinds = {self._frame_kind_from_packet(packet) for packet in packets}
        if len(kinds) == 1:
            return next(iter(kinds))
        if FrameKind.DATA in kinds:
            return FrameKind.DATA
        return FrameKind.UNKNOWN

    def extract_source_sequence(self, decoded_packet: object) -> SourceSequence | None:
        raise NotImplementedError


__all__ = ["TransportDriverError", "ThinInjectedTransportDriver"]
