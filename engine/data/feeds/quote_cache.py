"""Phase 5 Slice 4A — LatestQuoteCache implementation.

Maintains ordering-valid, deduplicated, and conflict-checked latest quote evidence
per InstrumentIdentity.

Key invariants:
- Monotonic exchange_timestamp enforcement per instrument.
- Same-timestamp conflicting payloads enter fail-closed AMBIGUOUS state.
- AMBIGUOUS state returns None for get(identity).
- Recovery requires strictly newer exchange timestamp (T > conflicted_ts).
- Reused event_id with differing payload fails closed and cannot lower ambiguity boundary.
- Stores ordering evidence only; does not invent competing staleness or crossed-quote policies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Mapping

from engine.execution.quote import QuoteSnapshot
from engine.data.feeds.live_feed import LiveQuoteEvent, quote_payload_fingerprint
from engine.portfolio.model import InstrumentIdentity

__all__ = [
    "QuoteCacheStatus",
    "QuoteCacheResult",
    "LatestQuoteCache",
]


class QuoteCacheStatus(str, Enum):
    """Result status of on_quote_event evaluation."""

    ACCEPTED = "ACCEPTED"
    DUPLICATE_IGNORED = "DUPLICATE_IGNORED"
    OUT_OF_ORDER_REJECTED = "OUT_OF_ORDER_REJECTED"
    AMBIGUOUS_CONFLICT_REJECTED = "AMBIGUOUS_CONFLICT_REJECTED"
    CONFLICTED_TIMESTAMP_REJECTED = "CONFLICTED_TIMESTAMP_REJECTED"
    REUSED_EVENT_ID_CONFLICT_REJECTED = "REUSED_EVENT_ID_CONFLICT_REJECTED"


@dataclass(frozen=True)
class QuoteCacheResult:
    """Immutable result of processing one LiveQuoteEvent through the cache."""

    status: QuoteCacheStatus
    instrument_identity: InstrumentIdentity
    quote: QuoteSnapshot | None
    message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, QuoteCacheStatus):
            raise TypeError("status must be a QuoteCacheStatus")
        if not isinstance(self.instrument_identity, InstrumentIdentity):
            raise TypeError("instrument_identity must be an InstrumentIdentity")
        if self.quote is not None and not isinstance(self.quote, QuoteSnapshot):
            raise TypeError("quote must be a QuoteSnapshot or None")


class LatestQuoteCache:
    """Synchronous deterministic cache of latest ordering-valid option quotes.

    Thread safety / locking is intentionally outside Slice 4A scope.
    """

    def __init__(self) -> None:
        # Valid latest quote per instrument
        self._valid_quotes: dict[InstrumentIdentity, QuoteSnapshot] = {}
        # Ambiguous conflicted timestamp per instrument (if in AMBIGUOUS state)
        self._ambiguous_timestamps: dict[InstrumentIdentity, datetime] = {}
        # Dedup map: InstrumentIdentity -> dict[event_id, payload_fingerprint]
        self._seen_events: dict[InstrumentIdentity, dict[str, str]] = {}
        # Latest observed exchange timestamp per instrument
        self._last_exchange_timestamps: dict[InstrumentIdentity, datetime] = {}

    def on_quote_event(self, event: LiveQuoteEvent) -> QuoteCacheResult:
        """Process one incoming LiveQuoteEvent through monotonic ordering and conflict checks.

        Returns QuoteCacheResult detailing the outcome.
        """
        if not isinstance(event, LiveQuoteEvent):
            raise TypeError("event must be a LiveQuoteEvent")

        quote = event.quote
        ident = quote.instrument_identity
        ts = quote.exchange_timestamp
        fingerprint = quote_payload_fingerprint(quote)
        event_id = event.event_id

        seen_map = self._seen_events.setdefault(ident, {})

        # ------------------------------------------------------------------
        # 1. Event ID history check (per-instrument scope)
        # ------------------------------------------------------------------
        if event_id in seen_map:
            prev_fingerprint = seen_map[event_id]
            if prev_fingerprint == fingerprint:
                # Exact identical event re-delivered -> duplicate
                if ident in self._ambiguous_timestamps:
                    if ts <= self._ambiguous_timestamps[ident]:
                        return QuoteCacheResult(
                            QuoteCacheStatus.CONFLICTED_TIMESTAMP_REJECTED,
                            ident,
                            None,
                            "conflicted_timestamp_unrecovered",
                        )
                if ident in self._last_exchange_timestamps and ts < self._last_exchange_timestamps[ident]:
                    return QuoteCacheResult(
                        QuoteCacheStatus.OUT_OF_ORDER_REJECTED,
                        ident,
                        self._valid_quotes.get(ident),
                        "out_of_order_timestamp",
                    )
                return QuoteCacheResult(
                    QuoteCacheStatus.DUPLICATE_IGNORED,
                    ident,
                    self._valid_quotes.get(ident),
                    "duplicate_event_id",
                )
            else:
                # Same event_id with differing normalized payload -> corruption conflict
                known_ts = self._last_exchange_timestamps.get(ident)
                conflicted_ts = ts if known_ts is None else max(known_ts, ts)
                if ident in self._ambiguous_timestamps:
                    conflicted_ts = max(self._ambiguous_timestamps[ident], conflicted_ts)

                self._ambiguous_timestamps[ident] = conflicted_ts
                self._valid_quotes.pop(ident, None)
                self._last_exchange_timestamps[ident] = conflicted_ts

                return QuoteCacheResult(
                    QuoteCacheStatus.REUSED_EVENT_ID_CONFLICT_REJECTED,
                    ident,
                    None,
                    "reused_event_id_differing_payload",
                )

        # ------------------------------------------------------------------
        # 2. Ambiguous state check and recovery
        # ------------------------------------------------------------------
        if ident in self._ambiguous_timestamps:
            conflicted_ts = self._ambiguous_timestamps[ident]
            if ts <= conflicted_ts:
                # Cannot clear ambiguity with same or older timestamp
                seen_map[event_id] = fingerprint
                return QuoteCacheResult(
                    QuoteCacheStatus.CONFLICTED_TIMESTAMP_REJECTED,
                    ident,
                    None,
                    "conflicted_timestamp_unrecovered",
                )
            else:
                # Strictly newer timestamp clears ambiguity!
                del self._ambiguous_timestamps[ident]
                self._valid_quotes[ident] = quote
                self._last_exchange_timestamps[ident] = ts
                seen_map[event_id] = fingerprint
                return QuoteCacheResult(
                    QuoteCacheStatus.ACCEPTED,
                    ident,
                    quote,
                    "ambiguity_recovered",
                )

        # ------------------------------------------------------------------
        # 3. Monotonic ordering and same-timestamp conflict checks
        # ------------------------------------------------------------------
        if ident in self._last_exchange_timestamps:
            last_ts = self._last_exchange_timestamps[ident]
            if ts < last_ts:
                # Older timestamp -> out-of-order drop
                seen_map[event_id] = fingerprint
                return QuoteCacheResult(
                    QuoteCacheStatus.OUT_OF_ORDER_REJECTED,
                    ident,
                    self._valid_quotes.get(ident),
                    "out_of_order_timestamp",
                )
            elif ts == last_ts:
                # Same timestamp -> check payload
                curr_quote = self._valid_quotes[ident]
                curr_fingerprint = quote_payload_fingerprint(curr_quote)
                if fingerprint == curr_fingerprint:
                    # Identical payload at same timestamp -> duplicate ignored
                    seen_map[event_id] = fingerprint
                    return QuoteCacheResult(
                        QuoteCacheStatus.DUPLICATE_IGNORED,
                        ident,
                        curr_quote,
                        "same_timestamp_identical_payload",
                    )
                else:
                    # Conflicting payload at same timestamp -> fail closed
                    self._ambiguous_timestamps[ident] = ts
                    self._valid_quotes.pop(ident, None)
                    seen_map[event_id] = fingerprint
                    return QuoteCacheResult(
                        QuoteCacheStatus.AMBIGUOUS_CONFLICT_REJECTED,
                        ident,
                        None,
                        "same_timestamp_conflicting_payload",
                    )
            else:
                # Strictly newer timestamp -> accept and update
                self._valid_quotes[ident] = quote
                self._last_exchange_timestamps[ident] = ts
                seen_map[event_id] = fingerprint
                return QuoteCacheResult(
                    QuoteCacheStatus.ACCEPTED,
                    ident,
                    quote,
                    "newer_timestamp_accepted",
                )

        # ------------------------------------------------------------------
        # 4. First quote for instrument (EMPTY -> VALID)
        # ------------------------------------------------------------------
        self._valid_quotes[ident] = quote
        self._last_exchange_timestamps[ident] = ts
        seen_map[event_id] = fingerprint
        return QuoteCacheResult(
            QuoteCacheStatus.ACCEPTED,
            ident,
            quote,
            "first_quote_accepted",
        )

    def get(self, identity: InstrumentIdentity) -> QuoteSnapshot | None:
        """Return the latest valid QuoteSnapshot for an instrument.

        Returns None if no quote has been received or if the instrument
        is currently in an AMBIGUOUS state.
        """
        if not isinstance(identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")
        if identity in self._ambiguous_timestamps:
            return None
        return self._valid_quotes.get(identity)

    def is_ambiguous(self, identity: InstrumentIdentity) -> bool:
        """Return True iff the instrument is currently in an unrecovered AMBIGUOUS state."""
        if not isinstance(identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")
        return identity in self._ambiguous_timestamps

    def clear(self) -> None:
        """Clear all cached quotes, ambiguity markers, and event history."""
        self._valid_quotes.clear()
        self._ambiguous_timestamps.clear()
        self._seen_events.clear()
        self._last_exchange_timestamps.clear()
