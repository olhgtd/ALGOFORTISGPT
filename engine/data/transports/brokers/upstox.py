"""Upstox V3 market-data transport edge for the shared Phase-6 runtime."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json

from engine.data.transports.contracts import (
    BrokerId,
    HeartbeatMode,
    SubscriptionRequest,
    TransportCapabilities,
)
from engine.data.transports.sequence import SequenceScope, SequenceSemantics, SourceSequence

from ._base import ThinInjectedTransportDriver, TransportDriverError


_ALLOWED_MODES = {
    "LTP": "ltpc",
    "LTPC": "ltpc",
    "OPTION_GREEKS": "option_greeks",
    "FULL": "full",
    "FULL_D30": "full_d30",
}


def _guid(request: SubscriptionRequest, method: str) -> str:
    raw = f"{method}|{request.data_mode.upper()}|{'|'.join(request.instruments)}"
    return sha256(raw.encode("utf-8")).hexdigest()[:24]


class UpstoxTransportDriver(ThinInjectedTransportDriver):
    broker_id = BrokerId.UPSTOX
    capabilities = TransportCapabilities(
        broker_id=BrokerId.UPSTOX,
        heartbeat_mode=HeartbeatMode.PROTOCOL_PING_PONG,
        source_sequence_semantics=SequenceSemantics.UNAVAILABLE,
        source_sequence_scope=SequenceScope.NONE,
        supports_subscription_ack=False,
    )

    def __init__(self, *, auth_client: object, connector, sender, decoder) -> None:
        getter = getattr(auth_client, "get_authorized_websocket_url", None)
        if not callable(getter):
            raise TypeError("auth_client must provide get_authorized_websocket_url()")
        self._auth_client = auth_client
        super().__init__(
            endpoint_provider=lambda _context: getter(),
            connector=connector,
            sender=sender,
            decoder=decoder,
        )

    def _payload(self, request: SubscriptionRequest, *, method: str) -> bytes:
        if not isinstance(request, SubscriptionRequest):
            raise TypeError("request must be SubscriptionRequest")
        mode = _ALLOWED_MODES.get(request.data_mode.upper())
        if mode is None:
            raise TransportDriverError("unsupported Upstox V3 subscription mode")
        body = {
            "guid": _guid(request, method),
            "method": method,
            "data": {
                "mode": mode,
                "instrumentKeys": list(request.instruments),
            },
        }
        return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def encode_subscribe(self, request: SubscriptionRequest) -> object:
        return self._send(self._payload(request, method="sub"))

    def encode_unsubscribe(self, request: SubscriptionRequest) -> object:
        return self._send(self._payload(request, method="unsub"))

    def extract_source_sequence(self, decoded_packet: object) -> SourceSequence | None:
        if not isinstance(decoded_packet, Mapping):
            raise TransportDriverError("decoded packet must be a mapping")
        return SourceSequence(None, SequenceSemantics.UNAVAILABLE, SequenceScope.NONE, None)


__all__ = ["UpstoxTransportDriver"]
