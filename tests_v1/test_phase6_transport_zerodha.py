from __future__ import annotations

from datetime import datetime, timezone

from engine.data.transports.brokers.zerodha import ZerodhaTransportDriver
from engine.data.transports.contracts import BrokerId, FrameKind, HeartbeatMode, SubscriptionRequest
from engine.data.transports.sequence import SequenceSemantics


UTC = timezone.utc


def _driver(sent: list[object]) -> ZerodhaTransportDriver:
    return ZerodhaTransportDriver(
        endpoint_provider=lambda _ctx: "wss://ws.kite.trade?redacted=1",
        connector=lambda _endpoint: "kite-conn-1",
        sender=sent.append,
        decoder=lambda frame: frame,
    )


def test_zerodha_driver_capabilities_are_read_only_and_sequence_is_not_fabricated() -> None:
    driver = _driver([])
    assert driver.broker_id is BrokerId.ZERODHA
    assert driver.capabilities.heartbeat_mode is HeartbeatMode.PROVIDER_HEARTBEAT_FRAME
    assert driver.capabilities.source_sequence_semantics is SequenceSemantics.UNAVAILABLE
    sequence = driver.extract_source_sequence({"instrument_token": "408065"})
    assert sequence is not None and sequence.value is None


def test_zerodha_subscribe_and_mode_translation() -> None:
    sent: list[object] = []
    driver = _driver(sent)
    request = SubscriptionRequest(("408065", "884737"), "FULL")

    messages = driver.encode_subscribe(request)

    assert messages == (
        {"a": "subscribe", "v": [408065, 884737]},
        {"a": "mode", "v": ["full", [408065, 884737]]},
    )
    assert sent == list(messages)
    unsubscribe = driver.encode_unsubscribe(request)
    assert unsubscribe == {"a": "unsubscribe", "v": [408065, 884737]}


def test_zerodha_one_byte_heartbeat_is_not_decoded_as_market_data() -> None:
    driver = _driver([])
    assert driver.classify_frame(b"\x00") is FrameKind.HEARTBEAT


def test_zerodha_multiplexed_decoded_frame_preserves_each_instrument() -> None:
    driver = _driver([])
    conn = driver.connect(driver.authorize(object()), connection_generation=3)
    now = datetime(2026, 9, 27, 9, 15, tzinfo=UTC)
    packets = [
        {"instrument_token": "408065", "receive_timestamp": now, "exchange_timestamp": now, "decoded_payload": {"last_price": 100}},
        {"instrument_token": "884737", "receive_timestamp": now, "exchange_timestamp": now, "decoded_payload": {"last_price": 200}},
    ]

    batch = driver.decode_frame(packets, connection=conn)

    assert [item.instrument_token for item in batch] == ["408065", "884737"]
    assert all(item.connection_generation == 3 for item in batch)
