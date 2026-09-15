"""Upstox Serialized Ingress Dispatcher.

Enforces single-reader, single-consumer serialized processing of incoming binary WebSocket frames.

Guarantees:
- Exactly one reader authority enqueues raw byte envelopes with generation_id and packet_ordinal.
- Bounded ingress queue (default 10,000 frames); queue overflow fails closed immediately.
- Generation guards reject stale envelopes before enqueue and before dispatch (zero mutation for old generations).
- Decode failures invalidate generation and trigger immediate reconnect handler.
- Dispatch order per packet strictly preserves: (1) Quotes, (2) Provider Bars, (3) MarketTime.
"""

from __future__ import annotations

from dataclasses import dataclass
import queue
import threading
from typing import Callable

from engine.data.feeds.live_bar_builder import LiveProviderBar, MarketTimeEvent
from engine.data.feeds.live_feed import LiveQuoteEvent
from engine.data.feeds.upstox.decoder import UpstoxDecodeError, UpstoxV3Decoder
from engine.data.feeds.upstox.normalizer import UpstoxV3Normalizer
from engine.data.feeds.upstox.proto import market_data_feed_pb2

__all__ = [
    "BarHandler",
    "CorruptPayloadHandler",
    "MarketTimeHandler",
    "OverflowHandler",
    "QuoteHandler",
    "UpstoxFrameEnvelope",
    "UpstoxSerializedDispatcher",
]

QuoteHandler = Callable[[LiveQuoteEvent], None]
BarHandler = Callable[[LiveProviderBar], None]
MarketTimeHandler = Callable[[MarketTimeEvent], None]
OverflowHandler = Callable[[int], None]  # generation_id
CorruptPayloadHandler = Callable[[int, int, Exception], None]  # generation_id, packet_ordinal, exc


@dataclass(frozen=True)
class UpstoxFrameEnvelope:
    """Immutable ingress envelope capturing transport metadata and raw binary frame."""

    generation_id: int
    packet_ordinal: int
    raw_payload: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.generation_id, int) or self.generation_id < 0:
            raise ValueError("generation_id must be a non-negative integer")
        if not isinstance(self.packet_ordinal, int) or self.packet_ordinal < 0:
            raise ValueError("packet_ordinal must be a non-negative integer")
        if not isinstance(self.raw_payload, (bytes, bytearray, memoryview)):
            raise TypeError("raw_payload must be bytes-like")
        object.__setattr__(self, "raw_payload", bytes(self.raw_payload))


class UpstoxSerializedDispatcher:
    """Bounded, generation-guarded serialized dispatcher for Upstox V3 live feed frames."""

    DEFAULT_MAX_QUEUE_SIZE = 10_000

    def __init__(
        self,
        decoder: UpstoxV3Decoder,
        normalizer: UpstoxV3Normalizer,
        *,
        max_queue_size: int = DEFAULT_MAX_QUEUE_SIZE,
        on_quote: QuoteHandler | None = None,
        on_bar: BarHandler | None = None,
        on_market_time: MarketTimeHandler | None = None,
        on_overflow: OverflowHandler | None = None,
        on_corrupt_payload: CorruptPayloadHandler | None = None,
    ) -> None:
        if not isinstance(decoder, UpstoxV3Decoder):
            raise TypeError("decoder must be an instance of UpstoxV3Decoder")
        if not isinstance(normalizer, UpstoxV3Normalizer):
            raise TypeError("normalizer must be an instance of UpstoxV3Normalizer")
        if not isinstance(max_queue_size, int) or max_queue_size <= 0:
            raise ValueError("max_queue_size must be a positive integer")

        self._decoder = decoder
        self._normalizer = normalizer
        self._max_queue_size = max_queue_size

        self._on_quote = on_quote
        self._on_bar = on_bar
        self._on_market_time = on_market_time
        self._on_overflow = on_overflow
        self._on_corrupt_payload = on_corrupt_payload

        self._queue: queue.Queue[UpstoxFrameEnvelope] = queue.Queue(maxsize=max_queue_size)
        self._active_generation_id: int = 0
        self._invalidated_generations: set[int] = set()
        self._lock = threading.Lock()

        self._running = False
        self._worker_thread: threading.Thread | None = None

    @property
    def max_queue_size(self) -> int:
        return self._max_queue_size

    @property
    def active_generation_id(self) -> int:
        with self._lock:
            return self._active_generation_id

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    def set_active_generation(self, generation_id: int) -> None:
        """Set the authoritative active generation ID and purge invalidated generations."""
        with self._lock:
            if generation_id < self._active_generation_id:
                raise ValueError("generation_id cannot move backwards")
            self._active_generation_id = generation_id

    def invalidate_generation(self, generation_id: int) -> None:
        """Mark a generation as invalid to prevent any further processing or state mutation."""
        with self._lock:
            self._invalidated_generations.add(generation_id)

    def is_generation_valid(self, generation_id: int) -> bool:
        """Check if a generation ID is currently active and valid."""
        with self._lock:
            return (
                generation_id == self._active_generation_id
                and generation_id not in self._invalidated_generations
            )

    def enqueue(self, envelope: UpstoxFrameEnvelope) -> bool:
        """Enqueue an incoming frame envelope.

        Returns:
            True if successfully enqueued; False if dropped due to stale generation or queue overflow.
        """
        if not isinstance(envelope, UpstoxFrameEnvelope):
            raise TypeError("envelope must be an UpstoxFrameEnvelope")

        # Fast pre-check generation
        if not self.is_generation_valid(envelope.generation_id):
            return False

        try:
            self._queue.put_nowait(envelope)
            return True
        except queue.Full:
            # FAIL CLOSED on queue overflow
            self.invalidate_generation(envelope.generation_id)
            self._drain_queue()
            if self._on_overflow:
                self._on_overflow(envelope.generation_id)
            return False

    def _drain_queue(self) -> None:
        """Empty the queue discarding all stale envelopes."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break

    def process_one(self, *, block: bool = False, timeout: float | None = None) -> bool:
        """Process a single envelope from the queue (test & worker pump).

        Returns:
            True if an item was processed or skipped; False if queue was empty.
        """
        try:
            envelope = self._queue.get(block=block, timeout=timeout)
        except queue.Empty:
            return False

        try:
            # Post-dequeue generation check
            if not self.is_generation_valid(envelope.generation_id):
                # Stale generation frame: Zero state mutation
                return True

            # Decode frame
            try:
                feed_response = self._decoder.decode(envelope.raw_payload)
            except UpstoxDecodeError as exc:
                self.invalidate_generation(envelope.generation_id)
                self._drain_queue()
                if self._on_corrupt_payload:
                    self._on_corrupt_payload(
                        envelope.generation_id, envelope.packet_ordinal, exc
                    )
                return True

            # If market_info packet: Zero QuoteSnapshot / LiveProviderBar signals
            if feed_response.type == market_data_feed_pb2.Type.market_info:
                return True

            # Normalize frame into canonical batch
            batch = self._normalizer.normalize_response(
                feed_response,
                generation_id=envelope.generation_id,
                packet_ordinal=envelope.packet_ordinal,
            )

            # Re-verify generation validity before invoking listeners
            if not self.is_generation_valid(envelope.generation_id):
                return True

            # Dispatch all intra-packet events in exact sorted instrument_key sequence
            for event in batch.events:
                if isinstance(event, LiveQuoteEvent) and self._on_quote:
                    self._on_quote(event)
                elif isinstance(event, LiveProviderBar) and self._on_bar:
                    self._on_bar(event)

            # Market Time pulse is dispatched strictly LAST after all instrument evidence
            if self._on_market_time and batch.market_time is not None:
                self._on_market_time(batch.market_time)

            return True

        finally:
            self._queue.task_done()

    def start(self) -> None:
        """Start background consumer worker thread."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._worker_thread = threading.Thread(
                target=self._worker_loop, name="UpstoxDispatcherWorker", daemon=True
            )
            self._worker_thread.start()

    def stop(self) -> None:
        """Stop background consumer worker thread."""
        with self._lock:
            self._running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
        self._drain_queue()

    def _worker_loop(self) -> None:
        """Continuous consumer loop."""
        while True:
            with self._lock:
                if not self._running:
                    break
            self.process_one(block=True, timeout=0.1)
