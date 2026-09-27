from __future__ import annotations

from engine.data.transports.contracts import (
    BrokerId,
    FrameKind,
    HeartbeatMode,
    ProviderEnvelopeBatch,
    SubscriptionRequest,
    TransportCapabilities,
    TransportConnection,
    TransportHealthState,
)
from engine.data.transports.policy import BrokerTransportPolicy, QueueOverflowAction
from engine.data.transports.runtime import MarketDataTransportRuntime
from engine.data.transports.sequence import SequenceScope, SequenceSemantics, SourceSequence


def _policy() -> BrokerTransportPolicy:
    return BrokerTransportPolicy(
        policy_id="TEST_ONLY/runtime-subscriptions",
        version="v1",
        max_reconnect_attempts=2,
        reconnect_backoff_seconds=(0.0, 0.0),
        receive_queue_capacity=4,
        heartbeat_timeout_seconds=5.0,
        stale_after_seconds=5.0,
        max_subscriptions_per_socket=10,
        subscription_batch_limit=10,
        max_connections=1,
        queue_overflow_action=QueueOverflowAction.FAILED_CLOSED,
        test_only=True,
    )


class _Driver:
    broker_id = BrokerId.UPSTOX

    def __init__(self, *, supports_ack: bool) -> None:
        self.capabilities = TransportCapabilities(
            broker_id=self.broker_id,
            heartbeat_mode=HeartbeatMode.NONE,
            source_sequence_semantics=SequenceSemantics.UNAVAILABLE,
            source_sequence_scope=SequenceScope.NONE,
            supports_subscription_ack=supports_ack,
        )
        self.sent: list[SubscriptionRequest] = []

    def authorize(self, auth_context: object) -> object:
        return "wss://example.invalid/feed"

    def connect(self, authorized_endpoint: object, *, connection_generation: int) -> TransportConnection:
        return TransportConnection("conn", connection_generation, str(authorized_endpoint))

    def encode_subscribe(self, request: SubscriptionRequest) -> object:
        self.sent.append(request)
        return request

    def encode_unsubscribe(self, request: SubscriptionRequest) -> object:
        return request

    def decode_frame(self, frame: object, *, connection: TransportConnection) -> ProviderEnvelopeBatch:
        return ()

    def classify_frame(self, frame: object) -> FrameKind:
        return FrameKind.UNKNOWN

    def extract_source_sequence(self, decoded_packet: object) -> SourceSequence | None:
        return SourceSequence(None, SequenceSemantics.UNAVAILABLE, SequenceScope.NONE, None)


def test_no_ack_provider_marks_successfully_sent_subscription_active_and_healthy() -> None:
    driver = _Driver(supports_ack=False)
    runtime = MarketDataTransportRuntime(driver, _policy())
    runtime.connect(object())
    request = SubscriptionRequest(("NSE_INDEX|Nifty 50",), "FULL")

    assert runtime.subscribe(request) is True

    assert driver.sent == [request]
    assert runtime.active_subscriptions == (request,)
    assert runtime.state is TransportHealthState.HEALTHY
    assert any(event.code == "SUBSCRIPTION_ACTIVATED_WITHOUT_ACK" for event in runtime.events)


def test_ack_capable_provider_stays_subscribing_until_full_ack() -> None:
    driver = _Driver(supports_ack=True)
    runtime = MarketDataTransportRuntime(driver, _policy())
    runtime.connect(object())
    request = SubscriptionRequest(("token-a", "token-b"), "QUOTE")

    runtime.subscribe(request)

    assert runtime.active_subscriptions == ()
    assert runtime.state is TransportHealthState.SUBSCRIBING
    assert runtime.acknowledge_subscription(
        runtime.connection_generation,
        request,
        ("token-a",),
    ) is False
    assert runtime.state is TransportHealthState.SUBSCRIBING
    assert runtime.active_subscriptions == ()

    assert runtime.acknowledge_subscription(
        runtime.connection_generation,
        request,
        ("token-a", "token-b"),
    ) is True
    assert runtime.active_subscriptions == (request,)
    assert runtime.state is TransportHealthState.HEALTHY


def test_no_ack_reconnect_replays_desired_subscription_into_new_generation() -> None:
    driver = _Driver(supports_ack=False)
    runtime = MarketDataTransportRuntime(driver, _policy())
    runtime.connect(object())
    request = SubscriptionRequest(("token-a",), "LTP")
    runtime.subscribe(request)
    first_generation = runtime.connection_generation

    runtime.unexpected_disconnect("drop")
    assert runtime.reconnect(object()) is True

    assert runtime.connection_generation == first_generation + 1
    assert driver.sent == [request, request]
    assert runtime.active_subscriptions == (request,)
    assert runtime.state is TransportHealthState.HEALTHY
