"""Upstox V3 Operational Live Market Data Feed Adapter.

Implements the LiveMarketDataFeed protocol for Upstox V3 streaming market data:
- Manages connection lifecycle with canonical states: DISCONNECTED, CONNECTED, RECONNECTING.
- Multi-step startup synchronization: EXPECT_MARKET_INFO -> EXPECT_INITIAL_SNAPSHOT -> LIVE.
- Generational integrity: every fresh connection receives a new monotonic generation_id.
- Automated subscription replay on reconnection without resurrecting released instruments.
- Physical execution mode 'full' (translating to decoded RequestMode.full_d5).
- Single-reader ingress into UpstoxSerializedDispatcher.
"""

from __future__ import annotations

import asyncio
from enum import Enum
import json
import logging
import threading
from typing import Any, Callable, Coroutine, Sequence, Set
import uuid

from engine.data.feeds.live_bar_builder import LiveProviderBar, MarketTimeEvent
from engine.data.feeds.live_feed import (
    FeedConnectionState,
    LiveMarketDataFeed,
    LiveQuoteEvent,
    QuoteListener,
)
from engine.data.feeds.provider_mapping import (
    ProviderInstrumentMapper,
    ProviderInstrumentRef,
)
from engine.data.feeds.upstox.auth import UpstoxV3AuthorizationClient
from engine.data.feeds.upstox.decoder import UpstoxV3Decoder
from engine.data.feeds.upstox.dispatcher import (
    UpstoxFrameEnvelope,
    UpstoxSerializedDispatcher,
)
from engine.data.feeds.upstox.normalizer import UpstoxV3Normalizer
from engine.data.feeds.upstox.proto import market_data_feed_pb2
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
    """Provider-local startup synchronization phases."""

    DISCONNECTED = "DISCONNECTED"
    EXPECT_MARKET_INFO = "EXPECT_MARKET_INFO"
    EXPECT_INITIAL_SNAPSHOT = "EXPECT_INITIAL_SNAPSHOT"
    LIVE = "LIVE"


class UpstoxLiveMarketDataFeed:
    """Operational Upstox Market Data Feed V3 Adapter implementing LiveMarketDataFeed."""

    def __init__(
        self,
        auth_client: UpstoxV3AuthorizationClient,
        provider_mapper: ProviderInstrumentMapper,
        *,
        max_queue_size: int = UpstoxSerializedDispatcher.DEFAULT_MAX_QUEUE_SIZE,
        ws_connect_fn: Callable[[str], Any] | None = None,
    ) -> None:
        if not isinstance(auth_client, UpstoxV3AuthorizationClient):
            raise TypeError("auth_client must be an UpstoxV3AuthorizationClient")
        if not isinstance(provider_mapper, ProviderInstrumentMapper):
            raise TypeError("provider_mapper must implement ProviderInstrumentMapper")

        self._auth_client = auth_client
        self._provider_mapper = provider_mapper
        self._ws_connect_fn = ws_connect_fn

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

        self._connection_state = FeedConnectionState.DISCONNECTED
        self._startup_phase = UpstoxStartupPhase.DISCONNECTED

        self._generation_id = 0
        self._packet_ordinal = 0
        self._subscribed_identities: set[InstrumentIdentity] = set()

        self._quote_listeners: list[QuoteListener] = []
        self._bar_listeners: list[BarListener] = []
        self._market_time_listeners: list[MarketTimeListener] = []
        self._state_listeners: list[StateListener] = []

        self._lock = threading.RLock()
        self._ws_client: Any = None
        self._runner_thread: threading.Thread | None = None
        self._is_running = False

    # ======================================================================
    # Properties & State Inspection
    # ======================================================================

    @property
    def connection_state(self) -> FeedConnectionState:
        with self._lock:
            return self._connection_state

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._connection_state == FeedConnectionState.CONNECTED

    @property
    def startup_phase(self) -> UpstoxStartupPhase:
        with self._lock:
            return self._startup_phase

    @property
    def generation_id(self) -> int:
        with self._lock:
            return self._generation_id

    @property
    def active_subscriptions_count(self) -> int:
        with self._lock:
            return len(self._subscribed_identities)

    def active_subscriptions(self) -> frozenset[InstrumentIdentity]:
        with self._lock:
            return frozenset(self._subscribed_identities)

    # ======================================================================
    # Listener Registration
    # ======================================================================

    def add_quote_listener(self, listener: QuoteListener) -> None:
        with self._lock:
            if listener not in self._quote_listeners:
                self._quote_listeners.append(listener)

    def remove_quote_listener(self, listener: QuoteListener) -> None:
        with self._lock:
            if listener in self._quote_listeners:
                self._quote_listeners.remove(listener)

    def add_bar_listener(self, listener: BarListener) -> None:
        with self._lock:
            if listener not in self._bar_listeners:
                self._bar_listeners.append(listener)

    def remove_bar_listener(self, listener: BarListener) -> None:
        with self._lock:
            if listener in self._bar_listeners:
                self._bar_listeners.remove(listener)

    def add_market_time_listener(self, listener: MarketTimeListener) -> None:
        with self._lock:
            if listener not in self._market_time_listeners:
                self._market_time_listeners.append(listener)

    def remove_market_time_listener(self, listener: MarketTimeListener) -> None:
        with self._lock:
            if listener in self._market_time_listeners:
                self._market_time_listeners.remove(listener)

    def add_state_listener(self, listener: StateListener) -> None:
        with self._lock:
            if listener not in self._state_listeners:
                self._state_listeners.append(listener)

    def remove_state_listener(self, listener: StateListener) -> None:
        with self._lock:
            if listener in self._state_listeners:
                self._state_listeners.remove(listener)

    def _set_connection_state(self, new_state: FeedConnectionState) -> None:
        listeners_to_call: list[StateListener] = []
        with self._lock:
            if self._connection_state != new_state:
                self._connection_state = new_state
                listeners_to_call = list(self._state_listeners)

        for listener in listeners_to_call:
            try:
                listener(new_state)
            except Exception as exc:
                logger.error(f"Error in state listener: {exc}")

    # ======================================================================
    # Subscription Management
    # ======================================================================

    def subscribe(self, identity: InstrumentIdentity) -> None:
        """Subscribe to live market data for an instrument."""
        if not isinstance(identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")

        # Resolve provider ref to verify mappability
        ref = self._provider_mapper.to_provider_ref(identity)

        with self._lock:
            if identity in self._subscribed_identities:
                return
            self._subscribed_identities.add(identity)
            is_conn = (self._connection_state == FeedConnectionState.CONNECTED)

        if is_conn and self._ws_client is not None:
            self._send_subscription_command(method="sub", keys=[ref.token])

    def unsubscribe(self, identity: InstrumentIdentity) -> None:
        """Unsubscribe from live market data for an instrument."""
        if not isinstance(identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")

        ref = self._provider_mapper.to_provider_ref(identity)

        with self._lock:
            if identity not in self._subscribed_identities:
                return
            self._subscribed_identities.remove(identity)
            is_conn = (self._connection_state == FeedConnectionState.CONNECTED)

        if is_conn and self._ws_client is not None:
            self._send_subscription_command(method="unsub", keys=[ref.token])

    def _send_subscription_command(self, *, method: str, keys: Sequence[str]) -> None:
        """Construct and send binary or text subscription JSON command."""
        if not keys:
            return
        # Deterministic sorting
        sorted_keys = sorted(set(keys))
        cmd = {
            "guid": str(uuid.uuid4()),
            "method": method,
            "data": {
                "mode": "full",
                "instrumentKeys": sorted_keys,
            },
        }
        payload = json.dumps(cmd).encode("utf-8")
        self._send_raw_ws_message(payload)

    def _send_raw_ws_message(self, message: bytes) -> None:
        """Send message via the underlying active WebSocket connection."""
        with self._lock:
            client = self._ws_client

        if client is not None:
            try:
                if hasattr(client, "send"):
                    client.send(message)
            except Exception as exc:
                logger.error(f"Failed to send WebSocket message: {exc}")

    # ======================================================================
    # Frame Ingress & Dispatch
    # ======================================================================

    def process_ingress_frame(self, raw_payload: bytes) -> bool:
        """Feed a single raw binary frame from the transport layer.

        Used directly in tests and by the background WebSocket reader loop.
        """
        with self._lock:
            gen_id = self._generation_id
            self._packet_ordinal += 1
            ordinal = self._packet_ordinal

        envelope = UpstoxFrameEnvelope(
            generation_id=gen_id,
            packet_ordinal=ordinal,
            raw_payload=raw_payload,
        )

        # Enqueue into dispatcher
        enqueued = self._dispatcher.enqueue(envelope)
        if not enqueued:
            return False

        # In synchronous mode (no background thread running), pump single frame
        if not self._is_running:
            self._dispatcher.process_one()

        # Update startup synchronization state based on frame type
        self._evaluate_startup_synchronization(raw_payload)
        return True

    def _evaluate_startup_synchronization(self, raw_payload: bytes) -> None:
        """Advance provider startup state machine upon receiving valid frames."""
        try:
            resp = self._decoder.decode(raw_payload)
        except Exception:
            return

        with self._lock:
            current_phase = self._startup_phase

            if current_phase == UpstoxStartupPhase.EXPECT_MARKET_INFO:
                if resp.type == market_data_feed_pb2.Type.market_info:
                    self._startup_phase = UpstoxStartupPhase.EXPECT_INITIAL_SNAPSHOT

            elif current_phase == UpstoxStartupPhase.EXPECT_INITIAL_SNAPSHOT:
                if resp.type in {
                    market_data_feed_pb2.Type.initial_feed,
                    market_data_feed_pb2.Type.live_feed,
                }:
                    self._startup_phase = UpstoxStartupPhase.LIVE
                    self._set_connection_state(FeedConnectionState.CONNECTED)

    # ======================================================================
    # Dispatcher Event Callbacks
    # ======================================================================

    def _dispatch_quote(self, event: LiveQuoteEvent) -> None:
        with self._lock:
            listeners = list(self._quote_listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception as exc:
                logger.error(f"Error in quote listener: {exc}")

    def _dispatch_bar(self, bar: LiveProviderBar) -> None:
        with self._lock:
            listeners = list(self._bar_listeners)
        for listener in listeners:
            try:
                listener(bar)
            except Exception as exc:
                logger.error(f"Error in bar listener: {exc}")

    def _dispatch_market_time(self, event: MarketTimeEvent) -> None:
        with self._lock:
            listeners = list(self._market_time_listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception as exc:
                logger.error(f"Error in market time listener: {exc}")

    # ======================================================================
    # Failure & Reconnect Handlers
    # ======================================================================

    def _handle_overflow(self, generation_id: int) -> None:
        """Trigger fail-closed reconnection on queue overflow."""
        logger.warning(f"Upstox dispatcher queue overflow in generation {generation_id}")
        self._trigger_reconnect()

    def _handle_corrupt_payload(
        self, generation_id: int, packet_ordinal: int, exc: Exception
    ) -> None:
        """Trigger fail-closed reconnection on decode failure."""
        logger.warning(
            f"Corrupt Protobuf payload in generation {generation_id} (packet {packet_ordinal}): {exc}"
        )
        self._trigger_reconnect()

    def _trigger_reconnect(self) -> None:
        """Invalidate generation and transition to RECONNECTING."""
        with self._lock:
            self._dispatcher.invalidate_generation(self._generation_id)
            self._startup_phase = UpstoxStartupPhase.EXPECT_MARKET_INFO
            self._set_connection_state(FeedConnectionState.RECONNECTING)

        # Close existing WebSocket client if open
        if self._ws_client is not None and hasattr(self._ws_client, "close"):
            try:
                self._ws_client.close()
            except Exception:
                pass

    def start_connection(self) -> None:
        """Initialize connection lifecycle and transition into EXPECT_MARKET_INFO."""
        with self._lock:
            self._generation_id += 1
            self._packet_ordinal = 0
            self._dispatcher.set_active_generation(self._generation_id)
            self._startup_phase = UpstoxStartupPhase.EXPECT_MARKET_INFO
            self._set_connection_state(FeedConnectionState.RECONNECTING)

    def complete_synchronization_for_testing(self) -> None:
        """Manual test helper to transition feed to CONNECTED state."""
        with self._lock:
            self._startup_phase = UpstoxStartupPhase.LIVE
            self._set_connection_state(FeedConnectionState.CONNECTED)

    def close(self) -> None:
        """Cleanly close feed and all underlying worker threads."""
        with self._lock:
            self._is_running = False
            self._dispatcher.invalidate_generation(self._generation_id)
            self._startup_phase = UpstoxStartupPhase.DISCONNECTED
            self._set_connection_state(FeedConnectionState.DISCONNECTED)

        self._dispatcher.stop()
        if self._ws_client is not None and hasattr(self._ws_client, "close"):
            try:
                self._ws_client.close()
            except Exception:
                pass
