from __future__ import annotations

from datetime import datetime, timezone

from engine.data.transports.brokers.dhan import DhanTransportDriver
from engine.data.transports.contracts import BrokerId, HeartbeatMode, SubscriptionRequest
from engine.data.transports.sequence import SequenceSemantics


UTC = timezone.utc


def _driver(sent: list[object]) -> DhanTransportDriver:
    return DhanTransportDriver(
        endpoint_provider=lambda _ctx: "wss://api-feed.dhan.co?redacted=1",
        connector=lambda _endpoint: "dhan-conn-1",
        sender=sent.append,
        decoder=lambda frame: frame,
    )


def test_dhan_driver_capabilities_are_market_data_only() -> None:
    driver = _driver([])
    assert driver.broker_id is BrokerId.DHAN
    assert driver.capabilities.heartbeat_mode is HeartbeatMode.PROTOCOL_PING_PONG
    assert driver.capabilities.source_sequence_semantics is SequenceSemantics.UNAVAILABLE
    for forbidden in ("place_order", "modify_order", "cancel_order"):
        assert not hasattr(driver, forbidden)


def test_dhan_full_subscription_and_unsubscription_use_provider_codes() -> None:
    sent: list[object] = []
    driver = _driver(sent)
    request = SubscriptionRequest(("NSE_EQ:1333", "BSE_EQ:532540"), "FULL")

    subscribe = driver.encode_subscribe(request)
    unsubscribe = driver.encode_unsubscribe(request)

    assert subscribe == {
        "RequestCode": 21,
        "InstrumentCount": 2,
        "InstrumentList": [
            {"ExchangeSegment": "NSE_EQ", "SecurityId": "1333"},
            {"ExchangeSegment": "BSE_EQ", "SecurityId": "532540"},
        ],
    }
    assert unsubscribe["RequestCode"] == 22
    assert sent == [subscribe, unsubscribe]


def test_dhan_decode_keeps_multiplexed_instruments_and_never_fabricates_sequence() -> None:
    driver = _driver([])
    conn = driver.connect(driver.authorize(object()), connection_generation=8)
    now = datetime(2026, 9, 27, 9, 15, tzinfo=UTC)
    batch = driver.decode_frame(
        [
            {"instrument_token": "NSE_EQ:1333", "receive_timestamp": now, "exchange_timestamp": now, "decoded_payload": {"LTP": 100}},
            {"instrument_token": "BSE_EQ:532540", "receive_timestamp": now, "exchange_timestamp": now, "decoded_payload": {"LTP": 200}},
        ],
        connection=conn,
    )

    assert len(batch) == 2
    assert all(item.source_sequence is not None for item in batch)
    assert all(item.source_sequence.value is None for item in batch if item.source_sequence is not None)
