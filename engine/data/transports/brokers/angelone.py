"""Angel One SmartAPI market-data transport edge for Phase 6.

Only read-only market-data concerns live here. Reconnect/backoff/watchdog and
subscription replay are owned by ``MarketDataTransportRuntime``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from hashlib import sha256

from engine.data.transports.contracts import (
    BrokerId,
    FrameKind,
    HeartbeatMode,
    SubscriptionRequest,
    TransportCapabilities,
)
from engine.data.transports.sequence import SequenceScope, SequenceSemantics, SourceSequence

from ._base import ThinInjectedTransportDriver, TransportDriverError


_MODE_CODE = {
    "LTP": 1,
    "QUOTE": 2,
    "SNAP_QUOTE": 3,
    "SNAPQUOTE": 3,
}


def _angel_instruments(instruments: tuple[str, ...]) -> list[dict[str, object]]:
    grouped: dict[int, list[str]] = defaultdict(list)
    for item in instruments:
        exchange_raw, separator, token = item.partition(":")
        if not separator or not exchange_raw.isdigit() or not token.strip():
            raise TransportDriverError(
                "Angel One instrument refs must use '<exchangeType>:<token>'"
            )
        grouped[int(exchange_raw)].append(token.strip())
    return [
        {"exchangeType": exchange_type, "tokens": tokens}
        for exchange_type, tokens in sorted(grouped.items())
    ]


def _correlation_id(request: SubscriptionRequest, action: int) -> str:
    canonical = f"{action}|{request.data_mode.upper()}|{'|'.join(request.instruments)}"
    return sha256(canonical.encode("utf-8")).hexdigest()[:10]


class AngelOneTransportDriver(ThinInjectedTransportDriver):
    broker_id = BrokerId.ANGELONE
    capabilities = TransportCapabilities(
        broker_id=BrokerId.ANGELONE,
        heartbeat_mode=HeartbeatMode.PROVIDER_HEARTBEAT_FRAME,
        # SmartAPI exposes a provider sequence number for non-index packets,
        # but the published contract does not promise contiguous increments.
        source_sequence_semantics=SequenceSemantics.MONOTONIC_ONLY,
        source_sequence_scope=SequenceScope.INSTRUMENT,
        supports_subscription_ack=False,
    )

    def _subscription_payload(self, request: SubscriptionRequest, *, action: int) -> dict[str, object]:
        if not isinstance(request, SubscriptionRequest):
            raise TypeError("request must be SubscriptionRequest")
        mode = _MODE_CODE.get(request.data_mode.upper())
        if mode is None:
            raise TransportDriverError("unsupported Angel One subscription mode")
        return {
            "correlationID": _correlation_id(request, action),
            "action": action,
            "params": {
                "mode": mode,
                "tokenList": _angel_instruments(request.instruments),
            },
        }

    def encode_subscribe(self, request: SubscriptionRequest) -> object:
        return self._send(self._subscription_payload(request, action=1))

    def encode_unsubscribe(self, request: SubscriptionRequest) -> object:
        return self._send(self._subscription_payload(request, action=0))

    def classify_frame(self, frame: object) -> FrameKind:
        if frame in ("pong", b"pong"):
            return FrameKind.HEARTBEAT
        return super().classify_frame(frame)

    def extract_source_sequence(self, decoded_packet: object) -> SourceSequence | None:
        if not isinstance(decoded_packet, Mapping):
            raise TransportDriverError("decoded packet must be a mapping")
        if bool(decoded_packet.get("is_index")):
            return SourceSequence(None, SequenceSemantics.UNAVAILABLE, SequenceScope.NONE, None)
        value = decoded_packet.get("sequence_number")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return SourceSequence(None, SequenceSemantics.UNAVAILABLE, SequenceScope.NONE, None)
        return SourceSequence(
            value,
            SequenceSemantics.MONOTONIC_ONLY,
            SequenceScope.INSTRUMENT,
            "sequence_number",
        )


__all__ = ["AngelOneTransportDriver"]
