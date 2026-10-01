from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import inspect

import pytest

from engine.data.feeds.broker_live_feeds import (
    AngelOneQuoteNormalizer,
    DhanQuoteNormalizer,
    KiteQuoteNormalizer,
    UpstoxQuoteNormalizer,
)
from engine.data.feeds.live_feed import LiveQuoteEvent, LiveQuoteTransportMetadata
from engine.data.transports.bridge import MarketEventBridge, MarketEventBridgeError
from engine.data.transports.sequence import SequenceScope, SequenceSemantics, SourceSequence
from engine.portfolio.model import InstrumentIdentity


UTC = timezone.utc


def _identity() -> InstrumentIdentity:
    return InstrumentIdentity("NSE", "NIFTY", "index")


@pytest.mark.parametrize(
    ("normalizer", "payload", "expected_source"),
    [
        (
            UpstoxQuoteNormalizer(),
            {"timestamp": "2026-09-27T09:15:00+00:00", "bid": "24999", "ask": "25001", "last_price": "25000"},
            "UPSTOX",
        ),
        (
            KiteQuoteNormalizer(),
            {"timestamp": "2026-09-27T09:15:00+00:00", "bid": "24999", "ask": "25001", "last_price": "25000"},
            "ZERODHA_KITE",
        ),
        (
            DhanQuoteNormalizer(),
            {"timestamp": "2026-09-27T09:15:00+00:00", "bid": "24999", "ask": "25001", "LTP": "25000"},
            "DHAN",
        ),
        (
            AngelOneQuoteNormalizer(),
            {"timestamp": "2026-09-27T09:15:00+00:00", "best_buy": "24999", "best_sell": "25001", "last_traded_price": "25000"},
            "ANGEL_ONE",
        ),
    ],
)
def test_provider_specific_normalizers_preserve_quote_behavior(normalizer, payload, expected_source) -> None:
    quote = normalizer.normalize(payload, _identity())

    assert quote.last_price == Decimal("25000")
    assert quote.bid_price == Decimal("24999")
    assert quote.ask_price == Decimal("25001")
    assert quote.source == expected_source


@pytest.mark.parametrize(
    "normalizer_type",
    [UpstoxQuoteNormalizer, KiteQuoteNormalizer, DhanQuoteNormalizer, AngelOneQuoteNormalizer],
)
def test_pure_normalizers_own_no_transport_or_execution_lifecycle(normalizer_type) -> None:
    method_names = {name for name, _ in inspect.getmembers(normalizer_type, predicate=inspect.isfunction)}

    assert method_names == {"normalize"}
    source = inspect.getsource(normalizer_type).lower()
    for forbidden in (
        "connect(",
        "reconnect(",
        "heartbeat",
        "riskgate",
        "approvedorder",
        "place_order",
        "modify_order",
        "cancel_order",
    ):
        assert forbidden not in source


def test_transport_metadata_survives_normalization_to_data_v2_observation() -> None:
    quote = AngelOneQuoteNormalizer().normalize(
        {
            "timestamp": "2026-09-27T09:15:00+00:00",
            "best_buy": "24999",
            "best_sell": "25001",
            "last_traded_price": "25000",
        },
        _identity(),
    )
    source_sequence = SourceSequence(
        501,
        SequenceSemantics.STRICT_CONTIGUOUS,
        SequenceScope.INSTRUMENT,
        "provider_sequence",
    )
    metadata = LiveQuoteTransportMetadata(
        connection_generation=7,
        instrument_token="NSE_INDEX|NIFTY",
        receive_timestamp=datetime(2026, 9, 27, 9, 15, 1, tzinfo=UTC),
        source_sequence=source_sequence,
    )
    event = LiveQuoteEvent("event-1", quote, metadata)
    bridge = MarketEventBridge()
    bridge.activate_generation(7)

    observation = bridge.from_live_quote_event(event, ingress_sequence=91)

    assert observation.connection_generation == 7
    assert observation.instrument_token == "NSE_INDEX|NIFTY"
    assert observation.source_sequence == source_sequence
    assert observation.event.sequence == 91
    assert observation.event.source_sequence == source_sequence
    assert observation.event.exchange_timestamp == quote.exchange_timestamp
    assert observation.event.receive_timestamp == metadata.receive_timestamp


def test_legacy_quote_without_transport_metadata_cannot_fake_data_v2_transport_evidence() -> None:
    quote = UpstoxQuoteNormalizer().normalize(
        {"timestamp": "2026-09-27T09:15:00+00:00", "last_price": "25000"},
        _identity(),
    )
    bridge = MarketEventBridge()
    bridge.activate_generation(1)

    with pytest.raises(MarketEventBridgeError, match="missing Phase-6 transport metadata"):
        bridge.from_live_quote_event(LiveQuoteEvent("legacy", quote), ingress_sequence=1)
