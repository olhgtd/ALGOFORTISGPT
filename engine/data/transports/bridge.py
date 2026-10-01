"""Generation-fenced bridge from provider transport evidence into Data V2."""

from __future__ import annotations

from dataclasses import dataclass

from engine.data.feeds.live_feed import LiveQuoteEvent
from engine.data.live_feed import LiveMarketEvent, MarketState
from engine.data.transports.contracts import FrameKind, ProviderEnvelope
from engine.data.transports.sequence import SourceSequence


class MarketEventBridgeError(ValueError):
    """Raised when transport evidence cannot safely enter Data V2."""


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

    def _require_active_generation(self, connection_generation: int) -> None:
        if self._active_generation is None:
            raise MarketEventBridgeError("active connection generation is not set")
        if connection_generation != self._active_generation:
            raise StaleGenerationError("transport evidence belongs to a stale connection generation")

    @staticmethod
    def _ingress_sequence(value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise MarketEventBridgeError("ingress_sequence must be a non-negative integer")
        return value

    def to_observation(self, envelope: ProviderEnvelope, *, ingress_sequence: int) -> MonitoredMarketEvent:
        if not isinstance(envelope, ProviderEnvelope):
            raise MarketEventBridgeError("envelope must be ProviderEnvelope")
        if envelope.frame_kind is not FrameKind.DATA:
            raise MarketEventBridgeError("only DATA envelopes can become market events")
        self._require_active_generation(envelope.connection_generation)
        sequence = self._ingress_sequence(ingress_sequence)
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
            sequence=sequence,
            market_state=market_state,
            source_sequence=envelope.source_sequence,
        )
        return MonitoredMarketEvent(
            event=event,
            connection_generation=envelope.connection_generation,
            instrument_token=envelope.instrument_token,
            source_sequence=envelope.source_sequence,
        )

    def from_live_quote_event(
        self,
        quote_event: LiveQuoteEvent,
        *,
        ingress_sequence: int,
        market_state: MarketState = MarketState.OPEN,
    ) -> MonitoredMarketEvent:
        """Bridge a normalized quote only when typed transport evidence survived.

        Legacy quote events without Phase-6 transport metadata remain valid for
        old consumers, but they cannot be promoted into Data-V2 monitored
        transport observations because generation/token/source evidence would
        otherwise have to be guessed.
        """
        if not isinstance(quote_event, LiveQuoteEvent):
            raise MarketEventBridgeError("quote_event must be LiveQuoteEvent")
        metadata = quote_event.transport_metadata
        if metadata is None:
            raise MarketEventBridgeError("quote_event is missing Phase-6 transport metadata")
        self._require_active_generation(metadata.connection_generation)
        sequence = self._ingress_sequence(ingress_sequence)
        if not isinstance(market_state, MarketState):
            raise TypeError("market_state must be MarketState")

        quote = quote_event.quote
        event = LiveMarketEvent(
            symbol=quote.instrument_identity.instrument,
            exchange_timestamp=quote.exchange_timestamp,
            receive_timestamp=metadata.receive_timestamp,
            sequence=sequence,
            market_state=market_state,
            source_sequence=metadata.source_sequence,
        )
        return MonitoredMarketEvent(
            event=event,
            connection_generation=metadata.connection_generation,
            instrument_token=metadata.instrument_token,
            source_sequence=metadata.source_sequence,
        )


__all__ = [
    "MarketEventBridgeError",
    "StaleGenerationError",
    "MonitoredMarketEvent",
    "MarketEventBridge",
]
