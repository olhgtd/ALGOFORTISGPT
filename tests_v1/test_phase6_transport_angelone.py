from __future__ import annotations

from datetime import datetime, timezone

from engine.data.transports.contracts import (
    BrokerId,
    FrameKind,
    HeartbeatMode,
    SubscriptionRequest,
)
from engine.data.transports.sequence import SequenceScope, SequenceSemantics
from engine.data.transports.brokers.angelone import AngelOneTransportDriver


UTC = timezone.utc


def _driver(sent: list[object]) -> AngelOneTransportDriver:
    return AngelOneTransportDriver(
        endpoint_provider=lambda _ctx: "wss://smartapisocket.angelone.in/smart-stream",
        connector=lambda _endpoint: "angel-conn-1",
        sender=sent.append,
        decoder=lambda frame: frame,
    )


def test_angelone_driver_declares_read_only_market_data_capabilities() -> None:
    driver = _driver([])

    assert driver.broker_id is BrokerId.ANGELONE
    assert driver.capabilities.heartbeat_mode is HeartbeatMode.PROVIDER_HEARTBEAT_FRAME
    assert driver.capabilities.source_sequence_semantics is SequenceSemantics.MONOTONIC_ONLY
    assert driver.capabilities.source_sequence_scope is SequenceScope.INSTRUMENT
    for forbidden in ("place_order", "modify_order", "cancel_order", "mint_approved_order"):
        assert not hasattr(driver, forbidden)


def test_angelone_subscription_translation_is_provider_specific_and_sent_once() -> None:
    sent: list[object] = []
    driver = _driver(sent)
    request = SubscriptionRequest(("1:10626", "1:5290", "2:4321"), "LTP")

    payload = driver.encode_subscribe(request)

    assert payload["action"] == 1
    assert payload["params"]["mode"] == 1
    assert payload["params"]["tokenList"] == [
        {"exchangeType": 1, "tokens": ["10626", "5290"]},
        {"exchangeType": 2, "tokens": ["4321"]},
    ]
    assert sent == [payload]
    assert len(payload["correlationID"]) == 10

    unsubscribe = driver.encode_unsubscribe(request)
    assert unsubscribe["action"] == 0
    assert sent[-1] == unsubscribe


def test_angelone_decode_preserves_generation_token_and_provider_sequence() -> None:
    sent: list[object] = []
    driver = _driver(sent)
    connection = driver.connect(driver.authorize(object()), connection_generation=4)
    receive = datetime(2026, 9, 27, 9, 15, 1, tzinfo=UTC)
    exchange = datetime(2026, 9, 27, 9, 15, 0, tzinfo=UTC)

    batch = driver.decode_frame(
        [
            {
                "instrument_token": "1:10626",
                "receive_timestamp": receive,
                "exchange_timestamp": exchange,
                "sequence_number": 501,
                "decoded_payload": {"last_traded_price": "25000", "symbol": "NIFTY"},
            }
        ],
        connection=connection,
    )

    assert len(batch) == 1
    envelope = batch[0]
    assert envelope.connection_generation == 4
    assert envelope.instrument_token == "1:10626"
    assert envelope.source_sequence is not None
    assert envelope.source_sequence.value == 501
    assert envelope.source_sequence.semantics is SequenceSemantics.MONOTONIC_ONLY
    assert envelope.source_sequence.scope is SequenceScope.INSTRUMENT


def test_angelone_index_sequence_is_explicitly_unavailable_and_heartbeat_is_classified() -> None:
    driver = _driver([])
    sequence = driver.extract_source_sequence({"sequence_number": 999, "is_index": True})

    assert sequence is not None
    assert sequence.semantics is SequenceSemantics.UNAVAILABLE
    assert sequence.value is None
    assert driver.classify_frame("pong") is FrameKind.HEARTBEAT
