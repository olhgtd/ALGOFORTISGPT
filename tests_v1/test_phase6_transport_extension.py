from __future__ import annotations

from pathlib import Path

from engine.data.transports.contracts import (
    FrameKind,
    HeartbeatMode,
    SubscriptionRequest,
    TransportCapabilities,
    TransportConnection,
)
from engine.data.transports.registry import MarketDataTransportRegistry
from engine.data.transports.sequence import SequenceScope, SequenceSemantics, SourceSequence


class TestBrokerTransportDriver:
    broker_id = "TEST_BROKER"
    capabilities = TransportCapabilities(
        broker_id=broker_id,
        heartbeat_mode=HeartbeatMode.NONE,
        source_sequence_semantics=SequenceSemantics.UNAVAILABLE,
        source_sequence_scope=SequenceScope.NONE,
        supports_subscription_ack=False,
    )

    def authorize(self, auth_context: object) -> object:
        return "wss://example.invalid/feed"

    def connect(self, authorized_endpoint: object, *, connection_generation: int) -> TransportConnection:
        return TransportConnection("test-connection", connection_generation, str(authorized_endpoint))

    def encode_subscribe(self, request: SubscriptionRequest) -> object:
        return request

    def encode_unsubscribe(self, request: SubscriptionRequest) -> object:
        return request

    def decode_frame(self, frame: object, *, connection: TransportConnection):
        return ()

    def classify_frame(self, frame: object) -> FrameKind:
        return FrameKind.UNKNOWN

    def extract_source_sequence(self, decoded_packet: object) -> SourceSequence | None:
        return SourceSequence(None, SequenceSemantics.UNAVAILABLE, SequenceScope.NONE, None)


def test_fifth_broker_registers_without_adding_brokerid_enum_member() -> None:
    registry = MarketDataTransportRegistry()
    registry.register("TEST_BROKER", TestBrokerTransportDriver)

    assert registry.resolve("TEST_BROKER") is TestBrokerTransportDriver
    assert registry.supported_keys == ("TEST_BROKER",)


def test_extension_does_not_require_test_broker_special_case_in_core_modules() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "engine/data/transports/runtime.py",
        "engine/data/feed_monitor.py",
        "engine/data/transports/bridge.py",
        "engine/risk/gate_v2.py",
        "engine/broker_contract/port_v2.py",
    ):
        text = (root / relative).read_text(encoding="utf-8")
        assert "TEST_BROKER" not in text
