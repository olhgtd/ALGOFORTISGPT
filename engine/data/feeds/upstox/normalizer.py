"""Upstox V3 Market Data Feed Normalizer.

Transforms decoded FeedResponse Protobuf instances into canonical AlgoFortis events:
- LiveQuoteEvent (wrapping QuoteSnapshot) for option contracts (CE/PE)
- LiveProviderBar for 1m completed underlying index/equity base bars (no synthetic ticks)
- MarketTimeEvent for advancing market time strictly AFTER intra-packet evidence normalization

Guarantees:
- Deterministic intra-packet processing order strictly follows sorted(response.feeds.keys()).
- Option quote timestamp authority uses FeedResponse.currentTs (never ltpc.ltt).
- Level-0 quotes extracted directly from marketLevel.bidAskQuote[0].
- Never substitutes LTP for missing bid/ask; never fabricates spread.
- Underlying index evidence uses LiveProviderBar without synthetic volume/quantity.
- Provider bars are emitted ONLY when currentTs >= start_timestamp + 1m (no in-progress candle emission).
- Never manufactures future completion timestamps (exchange_timestamp <= currentTs).
- Unmapped provider tokens produce deterministic unmapped tracking with zero mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Sequence, Union

from engine.execution.quote import QuoteSnapshot
from engine.data.feeds.live_bar_builder import LiveProviderBar, MarketTimeEvent
from engine.data.feeds.live_feed import LiveQuoteEvent
from engine.data.feeds.provider_mapping import (
    ProviderInstrumentMapper,
    ProviderInstrumentRef,
    UnknownProviderRefError,
)
from engine.data.feeds.upstox.proto import market_data_feed_pb2
from engine.portfolio.model import InstrumentIdentity

__all__ = [
    "NormalizedBatch",
    "UpstoxNormalizerError",
    "UpstoxV3Normalizer",
]

FeedItemEvent = Union[LiveQuoteEvent, LiveProviderBar]


class UpstoxNormalizerError(ValueError):
    """Raised when normalization encounters an unrecoverable structural format error."""


@dataclass(frozen=True)
class NormalizedBatch:
    """Immutable collection of normalized events produced from a single FeedResponse frame.

    Preserves exact intra-packet sequence derived from sorted(response.feeds.keys()).
    """

    generation_id: int
    packet_ordinal: int
    events: tuple[FeedItemEvent, ...]
    quotes: tuple[LiveQuoteEvent, ...]
    bars: tuple[LiveProviderBar, ...]
    market_time: MarketTimeEvent | None
    unmapped_keys: tuple[str, ...]


def _to_decimal_or_none(val: float | int | None) -> Decimal | None:
    if val is None or val <= 0:
        return None
    try:
        dec = Decimal(str(val))
        return dec if dec > 0 else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def _to_non_negative_decimal(val: float | int | None) -> Decimal:
    if val is None or val < 0:
        return Decimal("0")
    try:
        return Decimal(str(val))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


class UpstoxV3Normalizer:
    """Normalizes Upstox V3 FeedResponse protobuf messages into canonical AlgoFortis events."""

    def __init__(
        self,
        provider_mapper: ProviderInstrumentMapper,
        *,
        source_name: str = "upstox_feed",
    ) -> None:
        if not isinstance(provider_mapper, ProviderInstrumentMapper):
            raise TypeError("provider_mapper must implement ProviderInstrumentMapper")
        if not isinstance(source_name, str) or not source_name.strip():
            raise ValueError("source_name must be a non-empty string")

        self._provider_mapper = provider_mapper
        self._source_name = source_name.strip()

    @property
    def source_name(self) -> str:
        return self._source_name

    def normalize_response(
        self,
        response: market_data_feed_pb2.FeedResponse,
        *,
        generation_id: int,
        packet_ordinal: int,
    ) -> NormalizedBatch:
        """Normalize a FeedResponse message into an ordered batch of canonical events.

        Args:
            response: Decoded FeedResponse Protobuf message.
            generation_id: Generation counter of the active WebSocket connection.
            packet_ordinal: Ingress packet sequence counter.

        Returns:
            NormalizedBatch with events in exact sorted(instrument_keys) order,
            plus quotes, provider bars, market time pulse, and any unmapped keys.
        """
        if not isinstance(response, market_data_feed_pb2.FeedResponse):
            raise TypeError("response must be a market_data_feed_pb2.FeedResponse")
        if not isinstance(generation_id, int) or generation_id < 0:
            raise ValueError("generation_id must be a non-negative integer")
        if not isinstance(packet_ordinal, int) or packet_ordinal < 0:
            raise ValueError("packet_ordinal must be a non-negative integer")

        events_list: list[FeedItemEvent] = []
        quotes_list: list[LiveQuoteEvent] = []
        bars_list: list[LiveProviderBar] = []
        unmapped_keys_list: list[str] = []

        # Time authority: FeedResponse.currentTs is Unix timestamp in milliseconds
        if response.currentTs <= 0:
            raise UpstoxNormalizerError(
                f"FeedResponse missing authoritative event-time evidence: currentTs={response.currentTs}"
            )

        current_ts_dt = datetime.fromtimestamp(
            response.currentTs / 1000.0, tz=timezone.utc
        )

        # Intra-packet determinism: Process feeds strictly in sorted order of instrument_key
        sorted_keys = sorted(response.feeds.keys())

        for inst_key in sorted_keys:
            feed_item = response.feeds[inst_key]

            # Resolve canonical identity via provider mapper
            ref = ProviderInstrumentRef(
                provider="upstox",
                token=inst_key,
                exchange="NSE",
            )
            try:
                ident = self._provider_mapper.to_identity(ref)
            except UnknownProviderRefError:
                unmapped_keys_list.append(inst_key)
                continue

            # Route by segment: Options -> QuoteSnapshot, Non-options -> LiveProviderBar
            if ident.segment == "options":
                quote_event = self._normalize_option_quote(
                    feed_item=feed_item,
                    ident=ident,
                    current_ts_dt=current_ts_dt,
                    generation_id=generation_id,
                    packet_ordinal=packet_ordinal,
                    inst_key=inst_key,
                )
                if quote_event is not None:
                    events_list.append(quote_event)
                    quotes_list.append(quote_event)
            else:
                bar_events = self._normalize_underlying_bars(
                    feed_item=feed_item,
                    ident=ident,
                    current_ts_dt=current_ts_dt,
                )
                for bar in bar_events:
                    events_list.append(bar)
                    bars_list.append(bar)

        # MarketTimeEvent is emitted strictly AFTER intra-packet evidence normalization
        market_time_event = MarketTimeEvent(
            market_timestamp=current_ts_dt,
            source=self._source_name,
        )

        return NormalizedBatch(
            generation_id=generation_id,
            packet_ordinal=packet_ordinal,
            events=tuple(events_list),
            quotes=tuple(quotes_list),
            bars=tuple(bars_list),
            market_time=market_time_event,
            unmapped_keys=tuple(unmapped_keys_list),
        )

    def _normalize_option_quote(
        self,
        feed_item: market_data_feed_pb2.Feed,
        ident: InstrumentIdentity,
        current_ts_dt: datetime,
        generation_id: int,
        packet_ordinal: int,
        inst_key: str,
    ) -> LiveQuoteEvent | None:
        """Extract Level-0 bid/ask quote and LTP from FullFeed or FirstLevelWithGreeks."""
        bid_p: Decimal | None = None
        bid_q: Decimal | None = None
        ask_p: Decimal | None = None
        ask_q: Decimal | None = None
        last_p: Decimal | None = None

        if feed_item.HasField("fullFeed"):
            ff = feed_item.fullFeed
            if ff.HasField("marketFF"):
                mff = ff.marketFF
                # Extract level 0 depth
                if mff.HasField("marketLevel") and mff.marketLevel.bidAskQuote:
                    q0 = mff.marketLevel.bidAskQuote[0]
                    bid_p = _to_decimal_or_none(q0.bidP)
                    bid_q = _to_decimal_or_none(q0.bidQ)
                    ask_p = _to_decimal_or_none(q0.askP)
                    ask_q = _to_decimal_or_none(q0.askQ)

                if mff.HasField("ltpc") and mff.ltpc.ltp > 0:
                    last_p = _to_decimal_or_none(mff.ltpc.ltp)

        elif feed_item.HasField("firstLevelWithGreeks"):
            fl = feed_item.firstLevelWithGreeks
            if fl.HasField("firstDepth"):
                q0 = fl.firstDepth
                bid_p = _to_decimal_or_none(q0.bidP)
                bid_q = _to_decimal_or_none(q0.bidQ)
                ask_p = _to_decimal_or_none(q0.askP)
                ask_q = _to_decimal_or_none(q0.askQ)

            if fl.HasField("ltpc") and fl.ltpc.ltp > 0:
                last_p = _to_decimal_or_none(fl.ltpc.ltp)

        elif feed_item.HasField("ltpc"):
            # LTPC only mode: no depth
            if feed_item.ltpc.ltp > 0:
                last_p = _to_decimal_or_none(feed_item.ltpc.ltp)

        # Build QuoteSnapshot (never substitutes LTP for missing bid/ask)
        quote = QuoteSnapshot(
            instrument_identity=ident,
            exchange_timestamp=current_ts_dt,
            bid_price=bid_p,
            ask_price=ask_p,
            bid_quantity=bid_q,
            ask_quantity=ask_q,
            last_price=last_p,
            source=self._source_name,
        )

        event_id = f"upstox:{generation_id}:{packet_ordinal}:{inst_key}"
        return LiveQuoteEvent(event_id=event_id, quote=quote)

    def _normalize_underlying_bars(
        self,
        feed_item: market_data_feed_pb2.Feed,
        ident: InstrumentIdentity,
        current_ts_dt: datetime,
    ) -> list[LiveProviderBar]:
        """Extract 1m completed OHLC bars for underlying index/equity.

        P1-1 Finality Guarantee:
        A candle is emitted as completed LiveProviderBar ONLY when current_ts_dt >= start_dt + 1m.
        Never fabricates completion evidence for in-progress candles.
        Never emits exchange_timestamp greater than provider current_ts_dt.
        """
        market_ohlc: market_data_feed_pb2.MarketOHLC | None = None

        if feed_item.HasField("fullFeed"):
            ff = feed_item.fullFeed
            if ff.HasField("indexFF") and ff.indexFF.HasField("marketOHLC"):
                market_ohlc = ff.indexFF.marketOHLC
            elif ff.HasField("marketFF") and ff.marketFF.HasField("marketOHLC"):
                market_ohlc = ff.marketFF.marketOHLC

        if market_ohlc is None or not market_ohlc.ohlc:
            return []

        out_bars: list[LiveProviderBar] = []
        for candle in market_ohlc.ohlc:
            # Check for 1m interval
            interval_str = str(candle.interval).strip().upper()
            if interval_str not in {"I1", "1M", "1", "1 MINUTE"}:
                continue

            if candle.ts <= 0:
                continue

            start_dt = datetime.fromtimestamp(candle.ts / 1000.0, tz=timezone.utc)
            interval_end = start_dt + timedelta(minutes=1)

            # Finality Check: currentTs must be >= interval_end
            if current_ts_dt < interval_end:
                # In-progress candle: DO NOT emit completed LiveProviderBar
                continue

            # Authoritative exchange_timestamp: uses current_ts_dt (guaranteed >= interval_end and <= current_ts_dt)
            exchange_ts = current_ts_dt

            o = _to_decimal_or_none(candle.open)
            h = _to_decimal_or_none(candle.high)
            l = _to_decimal_or_none(candle.low)
            c = _to_decimal_or_none(candle.close)
            vol = _to_non_negative_decimal(candle.vol)

            if o is None or h is None or l is None or c is None:
                continue

            # Validate structural OHLC validity
            if h < l or h < o or h < c or l > o or l > c:
                continue

            try:
                bar = LiveProviderBar(
                    identity=ident,
                    timeframe="1m",
                    start_timestamp=start_dt,
                    open=o,
                    high=h,
                    low=l,
                    close=c,
                    volume=vol,
                    exchange_timestamp=exchange_ts,
                )
                out_bars.append(bar)
            except (ValueError, TypeError):
                # Ignore invalid structural bars
                continue

        return out_bars
