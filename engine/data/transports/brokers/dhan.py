"""DhanHQ v2 market-data transport edge for Phase 6."""

from __future__ import annotations

from collections.abc import Mapping

from engine.data.transports.contracts import (
    BrokerId,
    HeartbeatMode,
    SubscriptionRequest,
    TransportCapabilities,
)
from engine.data.transports.sequence import SequenceScope, SequenceSemantics, SourceSequence

from ._base import ThinInjectedTransportDriver, TransportDriverError


_REQUEST_CODES = {
    "LTP": (15, 16),
    "TICKER": (15, 16),
    "QUOTE": (17, 18),
    "FULL": (21, 22),
    "FULL_DEPTH": (23, 24),
}


def _instrument_list(instruments: tuple[str, ...]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in instruments:
        segment, separator, security_id = item.partition(":")
        if not separator or not segment.strip() or not security_id.strip():
            raise TransportDriverError(
                "Dhan instrument refs must use '<ExchangeSegment>:<SecurityId>'"
            )
        result.append(
            {
                "ExchangeSegment": segment.strip(),
                "SecurityId": security_id.strip(),
            }
        )
    return result


class DhanTransportDriver(ThinInjectedTransportDriver):
    broker_id = BrokerId.DHAN
    capabilities = TransportCapabilities(
        broker_id=BrokerId.DHAN,
        heartbeat_mode=HeartbeatMode.PROTOCOL_PING_PONG,
        source_sequence_semantics=SequenceSemantics.UNAVAILABLE,
        source_sequence_scope=SequenceScope.NONE,
        supports_subscription_ack=False,
    )

    def _payload(self, request: SubscriptionRequest, *, subscribe: bool) -> dict[str, object]:
        if not isinstance(request, SubscriptionRequest):
            raise TypeError("request must be SubscriptionRequest")
        codes = _REQUEST_CODES.get(request.data_mode.upper())
        if codes is None:
            raise TransportDriverError("unsupported Dhan subscription mode")
        instruments = _instrument_list(request.instruments)
        return {
            "RequestCode": codes[0] if subscribe else codes[1],
            "InstrumentCount": len(instruments),
            "InstrumentList": instruments,
        }

    def encode_subscribe(self, request: SubscriptionRequest) -> object:
        return self._send(self._payload(request, subscribe=True))

    def encode_unsubscribe(self, request: SubscriptionRequest) -> object:
        return self._send(self._payload(request, subscribe=False))

    def extract_source_sequence(self, decoded_packet: object) -> SourceSequence | None:
        if not isinstance(decoded_packet, Mapping):
            raise TransportDriverError("decoded packet must be a mapping")
        return SourceSequence(None, SequenceSemantics.UNAVAILABLE, SequenceScope.NONE, None)


__all__ = ["DhanTransportDriver"]
