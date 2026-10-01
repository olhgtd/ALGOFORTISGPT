from __future__ import annotations

from datetime import datetime, timezone
import json

from engine.data.transports.brokers.upstox import UpstoxTransportDriver
from engine.data.transports.contracts import BrokerId, HeartbeatMode, SubscriptionRequest
from engine.data.transports.sequence import SequenceSemantics


UTC = timezone.utc


class _Auth:
    def get_authorized_websocket_url(self) -> str:
        return "wss://feed.upstox.example/v3?redacted=1"


def _driver(sent: list[object]) -> UpstoxTransportDriver:
    return UpstoxTransportDriver(
        auth_client=_Auth(),
        connector=lambda _endpoint: "upstox-conn-1",
        sender=sent.append,
        decoder=lambda frame: frame,
    )


def test_upstox_driver_reuses_authorized_wss_and_shared_lifecycle_contract() -> None:
    driver = _driver([])
    endpoint = driver.authorize(object())
    connection = driver.connect(endpoint, connection_generation=9)

    assert driver.broker_id is BrokerId.UPSTOX
    assert driver.capabilities.heartbeat_mode is HeartbeatMode.PROTOCOL_PING_PONG
    assert driver.capabilities.source_sequence_semantics is SequenceSemantics.UNAVAILABLE
    assert connection.connection_generation == 9
    assert connection.endpoint_ref.startswith("wss://")
    assert not hasattr(driver, "reconnect")
    assert not hasattr(driver, "watchdog_tick")


def test_upstox_subscription_uses_v3_binary_json_request_shape() -> None:
    sent: list[object] = []
    driver = _driver(sent)
    request = SubscriptionRequest(("NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank"), "FULL")

    payload = driver.encode_subscribe(request)
    decoded = json.loads(payload.decode("utf-8"))

    assert decoded["method"] == "sub"
    assert decoded["data"] == {
        "mode": "full",
        "instrumentKeys": ["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank"],
    }
    assert sent == [payload]
    unsub = json.loads(driver.encode_unsubscribe(request).decode("utf-8"))
    assert unsub["method"] == "unsub"


def test_upstox_decoded_batch_keeps_each_instrument_without_fake_sequence() -> None:
    driver = _driver([])
    connection = driver.connect(driver.authorize(None), connection_generation=2)
    now = datetime(2026, 9, 27, 9, 15, tzinfo=UTC)
    batch = driver.decode_frame(
        [
            {"instrument_token": "NSE_INDEX|Nifty 50", "receive_timestamp": now, "exchange_timestamp": now, "decoded_payload": {"last_price": 25000}},
            {"instrument_token": "NSE_INDEX|Nifty Bank", "receive_timestamp": now, "exchange_timestamp": now, "decoded_payload": {"last_price": 55000}},
        ],
        connection=connection,
    )

    assert len(batch) == 2
    assert all(item.source_sequence is not None for item in batch)
    assert all(item.source_sequence.value is None for item in batch if item.source_sequence is not None)
