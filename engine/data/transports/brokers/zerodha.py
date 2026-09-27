"""Zerodha Kite market-data transport edge for Phase 6."""

from __future__ import annotations

from collections.abc import Mapping

from engine.data.transports.contracts import (
    BrokerId,
    FrameKind,
    HeartbeatMode,
    SubscriptionRequest,
    TransportCapabilities,
)
from engine.data.transports.sequence import SequenceScope, SequenceSemantics, SourceSequence

from ._base import ThinInjectedTransportDriver, TransportDriverError


_ALLOWED_MODES = {"LTP": "ltp", "QUOTE": "quote", "FULL": "full"}


def _tokens(instruments: tuple[str, ...]) -> list[int]:
    values: list[int] = []
    for item in instruments:
        if not item.isdigit():
            raise TransportDriverError("Zerodha instrument refs must be numeric instrument_token strings")
        values.append(int(item))
    return values


class ZerodhaTransportDriver(ThinInjectedTransportDriver):
    broker_id = BrokerId.ZERODHA
    capabilities = TransportCapabilities(
        broker_id=BrokerId.ZERODHA,
        heartbeat_mode=HeartbeatMode.PROVIDER_HEARTBEAT_FRAME,
        source_sequence_semantics=SequenceSemantics.UNAVAILABLE,
        source_sequence_scope=SequenceScope.NONE,
        supports_subscription_ack=False,
    )

    def encode_subscribe(self, request: SubscriptionRequest) -> object:
        if not isinstance(request, SubscriptionRequest):
            raise TypeError("request must be SubscriptionRequest")
        mode = _ALLOWED_MODES.get(request.data_mode.upper())
        if mode is None:
            raise TransportDriverError("unsupported Zerodha subscription mode")
        tokens = _tokens(request.instruments)
        messages = (
            {"a": "subscribe", "v": tokens},
            {"a": "mode", "v": [mode, tokens]},
        )
        for message in messages:
            self._send(message)
        return messages

    def encode_unsubscribe(self, request: SubscriptionRequest) -> object:
        if not isinstance(request, SubscriptionRequest):
            raise TypeError("request must be SubscriptionRequest")
        return self._send({"a": "unsubscribe", "v": _tokens(request.instruments)})

    def classify_frame(self, frame: object) -> FrameKind:
        # Kite emits a one-byte heartbeat when there is no quote traffic.
        if isinstance(frame, (bytes, bytearray, memoryview)) and len(frame) == 1:
            return FrameKind.HEARTBEAT
        return super().classify_frame(frame)

    def extract_source_sequence(self, decoded_packet: object) -> SourceSequence | None:
        if not isinstance(decoded_packet, Mapping):
            raise TransportDriverError("decoded packet must be a mapping")
        return SourceSequence(None, SequenceSemantics.UNAVAILABLE, SequenceScope.NONE, None)


__all__ = ["ZerodhaTransportDriver"]
