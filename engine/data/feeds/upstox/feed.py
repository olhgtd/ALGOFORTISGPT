"""Upstox V3 compatibility/normalization facade for Phase-6 market data.

Transport lifecycle authority belongs exclusively to
``MarketDataTransportRuntime``.  This module preserves the historical Upstox
listener/normalization surface, but it does not open sockets, generate transport
connection generations, run reconnect policy, or send provider commands
outside the shared broker-neutral runtime.
"""

from __future__ import annotations

from enum import Enum
import logging
import threading
from typing import Callable

from engine.data.feeds.live_bar_builder import LiveProviderBar, MarketTimeEvent
from engine.data.feeds.live_feed import FeedConnectionState, LiveQuoteEvent, QuoteListener
from engine.data.feeds.provider_mapping import ProviderInstrumentMapper
from engine.data.feeds.upstox.auth import UpstoxV3AuthorizationClient
from engine.data.feeds.upstox.decoder import UpstoxV3Decoder
from engine.data.feeds.upstox.dispatcher import UpstoxFrameEnvelope, UpstoxSerializedDispatcher
from engine.data.feeds.upstox.normalizer import UpstoxV3Normalizer
from engine.data.feeds.upstox.proto import market_data_feed_pb2
from engine.data.transports.contracts import SubscriptionRequest, TransportHealthState
from engine.data.transports.runtime import MarketDataTransportRuntime
from engine.portfolio.model import InstrumentIdentity

__all__ = [
    "BarListener",
    "MarketTimeListener",
    "StateListener",
    "UpstoxLiveMarketDataFeed",
    "UpstoxStartupPhase",
]

logger = logging.getLogger(__name__)

BarListener = Callable[[LiveProviderBar], None]
MarketTimeListener = Callable[[MarketTimeEvent], None]
StateListener = Callable[[FeedConnectionState], None]


class UpstoxStartupPhase(str, Enum):
    """Provider-local payload synchronization phase, not transport health."""

    DISCONNECTED = "DISCONNECTED"
    EXPECT_MARKET_INFO = "EXPECT_MARKET_INFO"
    EXPECT_INITIAL_SNAPSHOT = "EXPECT_INITIAL_SNAPSHOT"
    LIVE = "LIVE"


class UpstoxLiveMarketDataFeed:
    """Legacy listener/normalizer facade backed by the shared Phase-6 runtime.

    ``transport_runtime`` is required for operational connectivity.  Omitting it
    leaves the object usable only as a disconnected compatibility surface; it
    cannot start, reconnect, subscribe on a wire, or accept ingress frames.
    """

    def __init__(
        self,
        auth_client: UpstoxV3AuthorizationClient,
        provider_mapper: ProviderInstrumentMapper,
        *,
        max_queue_size: int = UpstoxSerializedDispatcher.DEFAULT_MAX_QUEUE_SIZE,
        ws_connect_fn: Callable[[str], object] | None = None,
        transport_runtime: MarketDataTransportRuntime | None = None,
    ) -> None:
        if not isinstance(auth_client, UpstoxV3AuthorizationClient):
            raise TypeError("auth_client must be an UpstoxV3AuthorizationClient")
        if not isinstance(provider_mapper, ProviderInstrumentMapper):
            raise TypeError("provider_mapper must implement ProviderInstrumentMapper")
        if ws_connect_fn is not None:
            raise ValueError(
                "ws_connect_fn is no longer accepted by UpstoxLiveMarketDataFeed; "
                "wire connectivity must be provided through MarketDataTransportRuntime"
            )
        if transport_runtime is not None and not isinstance(transport_runtime, MarketDataTransportRuntime):
            raise TypeError("transport_runtime must be MarketDataTransportRuntime or None")

        self._auth_client = auth_client
        self._provider_mapper = provider_mapper
        self._transport_runtime = transport_runtime
        self._decoder = UpstoxV3Decoder()
        self._normalizer = UpstoxV3Normalizer(provider_mapper=provider_mapper)
        self._dispatcher = UpstoxSerializedDispatcher(
            decoder=self._decoder,
            normalizer=self._normalizer,
            max_queue_size=max_queue_size,
            on_quote=self._dispatch_quote,
            on_bar=self._dispatch_bar,
            on_market_time=self._dispatch_market_time,
            on_overflow=self._handle_overflow,
            on_corrupt_payload=self._handle_corrupt_payload,
        )

        self._startup_phase = UpstoxStartupPhase.DISCONNECTED
        self._packet_ordinal = 0
        self._subscribed_identities: set[InstrumentIdentity] = set()
        self._quote_listeners: list[QuoteListener] = []
        self._bar_listeners: list[BarListener] = []
        self._market_time_listeners: list[MarketTimeListener] = []
        self._state_listeners: list[StateListener] = []
        self._last_notified_state = FeedConnectionState.DISCONNECTED
        self._lock = threading.RLock()

    def _require_runtime(self) -> MarketDataTransportRuntime:
        runtime = self._transport_runtime
        if runtime is None:
            raise RuntimeError(
                "operational Upstox connectivity requires the shared MarketDataTransportRuntime"
            )
        return runtime

    @property
    def connection_state(self) -> FeedConnectionState:
        runtime = self._transport_runtime
        if runtime is None:
            return FeedConnectionState.DISCONNECTED
        if runtime.state in {
            TransportHealthState.CONNECTING,
            TransportHealthState.AUTHORIZING,
            TransportHealthState.RECONNECTING,
        }:
            return FeedConnectionState.RECONNECTING
        if runtime.state in {
            TransportHealthState.CONNECTED,
            TransportHealthState.SUBSCRIBING,
            TransportHealthState.HEALTHY,
        } and self.startup_phase is UpstoxStartupPhase.LIVE:
            return FeedConnectionState.CONNECTED
        return FeedConnectionState.DISCONNECTED

    @property
    def is_connected(self) -> bool:
        return self.connection_state is FeedConnectionState.CONNECTED

    @property
    def startup_phase(self) -> UpstoxStartupPhase:
        with self._lock:
            return self._startup_phase

    @property
    def generation_id(self) -> int:
        runtime = self._transport_runtime
        return 0 if runtime is None else runtime.connection_generation

    @property
    def active_subscriptions_count(self) -> int:
        with self._lock:
            return len(self._subscribed_identities)

    def active_subscriptions(self) -> frozenset[InstrumentIdentity]:
        with self._lock:
            return frozenset(self._subscribed_identities)

    def add_quote_listener(self, listener: QuoteListener) -> None:
        if not callable(listener):
            raise TypeError("listener must be callable")
        with self._lock:
            if listener not in self._quote_listeners:
                self._quote_listeners.append(listener)

    def remove_quote_listener(self, listener: QuoteListener) -> None:
        with self._lock:
            if listener in self._quote_listeners:
                self._quote_listeners.remove(listener)

    def add_bar_listener(self, listener: BarListener) -> None:
        if not callable(listener):
            raise TypeError("listener must be callable")
        with self._lock:
            if listener not in self._bar_listeners:
                self._bar_listeners.append(listener)

    def remove_bar_listener(self, listener: BarListener) -> None:
        with self._lock:
            if listener in self._bar_listeners:
                self._bar_listeners.remove(listener)

    def add_market_time_listener(self, listener: MarketTimeListener) -> None:
        if not callable(listener):
            raise TypeError("listener must be callable")
        with self._lock:
            if listener not in self._market_time_listeners:
                self._market_time_listeners.append(listener)

    def remove_market_time_listener(self, listener: MarketTimeListener) -> None:
        with self._lock:
            if listener in self._market_time_listeners:
                self._market_time_listeners.remove(listener)

    def add_state_listener(self, listener: StateListener) -> None:
        if not callable(listener):
            raise TypeError("listener must be callable")
        with self._lock:
            if listener not in self._state_listeners:
                self._state_listeners.append(listener)

    def remove_state_listener(self, listener: StateListener) -> None:
        with self._lock:
            if listener in self._state_listeners:
                self._state_listeners.remove(listener)

    def _notify_legacy_state(self) -> None:
        state = self.connection_state
        with self._lock:
            if state is self._last_notified_state:
                return
            self._last_notified_state = state
            listeners = list(self._state_listeners)
        for listener in listeners:
            try:
                listener(state)
            except Exception as exc:
                logger.error("Error in state listener: %s", exc)

    def subscribe(self, identity: InstrumentIdentity) -> None:
        if not isinstance(identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")
        ref = self._provider_mapper.to_provider_ref(identity)
        with self._lock:
            if identity in self._subscribed_identities:
                return
            self._subscribed_identities.add(identity)
        runtime = self._require_runtime()
        runtime.subscribe(SubscriptionRequest((ref.token,), "FULL"))
        self._notify_legacy_state()

    def unsubscribe(self, identity: InstrumentIdentity) -> None:
        if not isinstance(identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")
        ref = self._provider_mapper.to_provider_ref(identity)
        with self._lock:
            if identity not in self._subscribed_identities:
                return
            self._subscribed_identities.remove(identity)
        runtime = self._require_runtime()
        runtime.unsubscribe(SubscriptionRequest((ref.token,), "FULL"))
        self._notify_legacy_state()

    def start_connection(self) -> None:
        """Delegate connection generation and authorization to the shared runtime."""
        runtime = self._require_runtime()
        runtime.connect(self._auth_client)
        with self._lock:
            self._packet_ordinal = 0
            self._dispatcher.set_active_generation(runtime.connection_generation)
            self._startup_phase = UpstoxStartupPhase.EXPECT_MARKET_INFO
        self._notify_legacy_state()

    def reconnect(self) -> bool:
        """Delegate bounded reconnect/backoff policy to the shared runtime."""
        runtime = self._require_runtime()
        ok = runtime.reconnect(self._auth_client)
        with self._lock:
            self._packet_ordinal = 0
            if ok:
                self._dispatcher.set_active_generation(runtime.connection_generation)
                self._startup_phase = UpstoxStartupPhase.EXPECT_MARKET_INFO
            else:
                self._startup_phase = UpstoxStartupPhase.DISCONNECTED
        self._notify_legacy_state()
        return ok

    def process_ingress_frame(
        self,
        raw_payload: bytes,
        *,
        connection_generation: int | None = None,
    ) -> bool:
        """Normalize a frame only after shared-runtime generation validation."""
        if not isinstance(raw_payload, (bytes, bytearray)):
            raise TypeError("raw_payload must be bytes")
        runtime = self._require_runtime()
        active_generation = runtime.connection_generation
        generation = active_generation if connection_generation is None else connection_generation
        if runtime.connection is None or generation != active_generation:
            return False
        with self._lock:
            self._packet_ordinal += 1
            ordinal = self._packet_ordinal
        envelope = UpstoxFrameEnvelope(
            generation_id=generation,
            packet_ordinal=ordinal,
            raw_payload=bytes(raw_payload),
        )
        enqueued = self._dispatcher.enqueue(envelope)
        if not enqueued:
            return False
        self._dispatcher.process_one()
        self._evaluate_startup_synchronization(bytes(raw_payload))
        return True

    def _evaluate_startup_synchronization(self, raw_payload: bytes) -> None:
        try:
            resp = self._decoder.decode(raw_payload)
        except Exception:
            return
        changed = False
        with self._lock:
            if self._startup_phase is UpstoxStartupPhase.EXPECT_MARKET_INFO:
                if resp.type == market_data_feed_pb2.Type.market_info:
                    self._startup_phase = UpstoxStartupPhase.EXPECT_INITIAL_SNAPSHOT
                    changed = True
            elif self._startup_phase is UpstoxStartupPhase.EXPECT_INITIAL_SNAPSHOT:
                if resp.type in {
                    market_data_feed_pb2.Type.initial_feed,
                    market_data_feed_pb2.Type.live_feed,
                }:
                    self._startup_phase = UpstoxStartupPhase.LIVE
                    changed = True
        if changed:
            self._notify_legacy_state()

    def _dispatch_quote(self, event: LiveQuoteEvent) -> None:
        with self._lock:
            listeners = list(self._quote_listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception as exc:
                logger.error("Error in quote listener: %s", exc)

    def _dispatch_bar(self, bar: LiveProviderBar) -> None:
        with self._lock:
            listeners = list(self._bar_listeners)
        for listener in listeners:
            try:
                listener(bar)
            except Exception as exc:
                logger.error("Error in bar listener: %s", exc)

    def _dispatch_market_time(self, event: MarketTimeEvent) -> None:
        with self._lock:
            listeners = list(self._market_time_listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception as exc:
                logger.error("Error in market-time listener: %s", exc)

    def _handle_overflow(self, generation_id: int) -> None:
        logger.warning("Upstox dispatcher overflow in generation %s", generation_id)
        self._dispatcher.invalidate_generation(generation_id)
        runtime = self._transport_runtime
        if runtime is not None:
            runtime.fail_closed("UPSTOX_DISPATCH_OVERFLOW")
        with self._lock:
            self._startup_phase = UpstoxStartupPhase.DISCONNECTED
        self._notify_legacy_state()

    def _handle_corrupt_payload(
        self,
        generation_id: int,
        packet_ordinal: int,
        exc: Exception,
    ) -> None:
        logger.warning(
            "Corrupt Upstox payload generation=%s packet=%s: %s",
            generation_id,
            packet_ordinal,
            type(exc).__name__,
        )
        self._dispatcher.invalidate_generation(generation_id)
        runtime = self._transport_runtime
        if runtime is not None:
            runtime.fail_closed("UPSTOX_CORRUPT_PAYLOAD", detail=type(exc).__name__)
        with self._lock:
            self._startup_phase = UpstoxStartupPhase.DISCONNECTED
        self._notify_legacy_state()

    def complete_synchronization_for_testing(self) -> None:
        """Payload-state helper only; never changes transport health or generation."""
        with self._lock:
            self._startup_phase = UpstoxStartupPhase.LIVE
        self._notify_legacy_state()

    def close(self) -> None:
        generation = self.generation_id
        if generation > 0:
            self._dispatcher.invalidate_generation(generation)
        with self._lock:
            self._startup_phase = UpstoxStartupPhase.DISCONNECTED
        runtime = self._transport_runtime
        if runtime is not None:
            runtime.disconnect("upstox_feed_close")
        self._dispatcher.stop()
        self._notify_legacy_state()
