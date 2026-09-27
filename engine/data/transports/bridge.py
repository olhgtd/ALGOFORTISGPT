"""Generation-fenced bridge from provider transport envelopes into Data V2."""

from __future__ import annotations

from dataclasses import dataclass

from engine.data.live_feed import LiveMarketEvent, MarketState
from engine.data.transports.contracts import FrameKind, ProviderEnvelope
from engine.data.transports.sequence import SourceSequence


class MarketEventBridgeError(ValueError):
    """Raised when a transport envelope cannot safely enter Data V2."""


class StaleGenerationError(MarketEventBridgeError):
    """Raised when an old connection generation attempts to inject data."""


@dataclass(frozen=True, slots=True)
class MonitoredMarketEvent:
    event: LiveMarketEvent
    connection_generation: int
    instrument_token: str
    source_sequence: SourceSequence | None


class MarketEventBridge:
    """Translate read-only transport evidence without gaining policy authority."""

    def __init__(self) -> None:
        self._active_generation: int | None = None

    def activate_generation(self, connection_generation: int) -> None:
        if isinstance(connection_generation, bool) or not isinstance(connection_generation, int) or connection_generation <= 0:
            raise MarketEventBridgeError("connection_generation must be a positive integer")
        if self._active_generation is not None and connection_generation < self._active_generation:
            raise StaleGenerationError("cannot reactivate an older connection generation")
        self._active_generation = connection_generation

    def to_observation(self, envelope: ProviderEnvelope, *, ingress_sequence: int) -> MonitoredMarketEvent:
        if not isinstance(envelope, ProviderEnvelope):
            raise MarketEventBridgeError("envelope must be ProviderEnvelope")
        if envelope.frame_kind is not FrameKind.DATA:
            raise MarketEventBridgeError("only DATA envelopes can become market events")
        if self._active_generation is None:
            raise MarketEventBridgeError("active connection generation is not set")
        if envelope.connection_generation != self._active_generation:
            raise StaleGenerationError("provider envelope belongs to a stale connection generation")
        if isinstance(ingress_sequence, bool) or not isinstance(ingress_sequence, int) or ingress_sequence < 0:
            raise MarketEventBridgeError("ingress_sequence must be a non-negative integer")
        if envelope.exchange_timestamp is None:
            raise MarketEventBridgeError("DATA envelope must carry exchange_timestamp")

        payload = envelope.decoded_payload
        symbol = payload.get("symbol", envelope.instrument_token)
        state_raw = payload.get("market_state", MarketState.OPEN.value)
        try:
            market_state = state_raw if isinstance(state_raw, MarketState) else MarketState(str(state_raw).upper())
        except ValueError as exc:
            raise MarketEventBridgeError("decoded payload has invalid market_state") from exc

        event = LiveMarketEvent(
            symbol=str(symbol),
            exchange_timestamp=envelope.exchange_timestamp,
            receive_timestamp=envelope.receive_timestamp,
            sequence=ingress_sequence,
            market_state=market_state,
            source_sequence=envelope.source_sequence,
        )
        return MonitoredMarketEvent(
            event=event,
            connection_generation=envelope.connection_generation,
            instrument_token=envelope.instrument_token,
            source_sequence=envelope.source_sequence,
        )


__all__ = [
    "MarketEventBridgeError",
    "StaleGenerationError",
    "MonitoredMarketEvent",
    "MarketEventBridge",
]
