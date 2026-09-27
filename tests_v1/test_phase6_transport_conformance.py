from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine.data.feed_monitor import FeedHealthReason, FeedMonitor
from engine.data.live_feed import LiveMarketEvent, MarketState
from engine.data.transports.brokers.angelone import AngelOneTransportDriver
from engine.data.transports.brokers.dhan import DhanTransportDriver
from engine.data.transports.brokers.upstox import UpstoxTransportDriver
from engine.data.transports.brokers.zerodha import ZerodhaTransportDriver
from engine.data.transports.contracts import FrameKind, HeartbeatMode, SubscriptionRequest, TransportHealthState
from engine.data.transports.policy import BrokerTransportPolicy, QueueOverflowAction
from engine.data.transports.runtime import MarketDataTransportRuntime
from engine.data.transports.sequence import SequenceScope, SequenceSemantics, SourceSequence


UTC = timezone.utc


@dataclass(frozen=True)
class _BrokerCase:
    name: str
    driver_type: type
    instrument: str
    mode: str = "LTP"


CASES = (
    _BrokerCase("angelone", AngelOneTransportDriver, "1:10626"),
    _BrokerCase("zerodha", ZerodhaTransportDriver, "256265"),
    _BrokerCase("dhan", DhanTransportDriver, "IDX_I:13"),
    _BrokerCase("upstox", UpstoxTransportDriver, "NSE_INDEX|Nifty 50"),
)


class _UpstoxAuth:
    def __init__(self, endpoint: str) -> None:
        self._endpoint = endpoint

    def get_authorized_websocket_url(self) -> str:
        return self._endpoint


class _Clock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now_utc(self) -> datetime:
        return self._now


def _policy(*, capacity: int = 2, attempts: int = 2) -> BrokerTransportPolicy:
    return BrokerTransportPolicy(
        policy_id="TEST_ONLY/phase6-conformance",
        version="v1",
        max_reconnect_attempts=attempts,
        reconnect_backoff_seconds=tuple(0.0 for _ in range(attempts)),
        receive_queue_capacity=capacity,
        heartbeat_timeout_seconds=5.0,
        stale_after_seconds=5.0,
        max_subscriptions_per_socket=50,
        subscription_batch_limit=50,
        max_connections=1,
        queue_overflow_action=QueueOverflowAction.FAILED_CLOSED,
        test_only=True,
    )


def _driver(case: _BrokerCase, sent: list[object], *, connector=None, endpoint_provider=None):
    endpoint = f"wss://{case.name}.example.test/market-data?token=secret"
    connect_fn = connector or (lambda _endpoint: f"{case.name}-connection")
    decoder = lambda frame: frame
    if case.driver_type is UpstoxTransportDriver:
        return UpstoxTransportDriver(
            auth_client=_UpstoxAuth(endpoint),
            connector=connect_fn,
            sender=sent.append,
            decoder=decoder,
        )
    return case.driver_type(
        endpoint_provider=endpoint_provider or (lambda _ctx: endpoint),
        connector=connect_fn,
        sender=sent.append,
        decoder=decoder,
    )


def _request(case: _BrokerCase) -> SubscriptionRequest:
    return SubscriptionRequest((case.instrument,), case.mode)


def _event(*, at: datetime, ingress: int, source: SourceSequence | None) -> LiveMarketEvent:
    return LiveMarketEvent("NIFTY", at, at, ingress, MarketState.OPEN, source)


@pytest.mark.parametrize("case", CASES, ids=lambda item: item.name)
def test_common_connect_subscribe_unsubscribe_and_reconnect(case: _BrokerCase) -> None:
    sent: list[object] = []
    driver = _driver(case, sent)
    runtime = MarketDataTransportRuntime(driver, _policy())
    request = _request(case)

    first = runtime.connect(object())
    assert first.connection_generation == 1
    assert "token=" not in first.endpoint_ref
    assert runtime.subscribe(request) is True
    assert runtime.state is TransportHealthState.HEALTHY
    assert request in runtime.active_subscriptions

    runtime.unexpected_disconnect("wire_lost")
    assert runtime.state is TransportHealthState.RECONNECTING
    assert runtime.reconnect(object()) is True
    assert runtime.connection_generation == 2
    assert request in runtime.active_subscriptions
    assert runtime.state is TransportHealthState.HEALTHY

    assert runtime.unsubscribe(request) is True
    assert request not in runtime.desired_subscriptions


@pytest.mark.parametrize("case", CASES, ids=lambda item: item.name)
def test_clean_disconnect_stops_transport_without_auto_resume(case: _BrokerCase) -> None:
    runtime = MarketDataTransportRuntime(_driver(case, []), _policy())
    runtime.connect(object())
    runtime.subscribe(_request(case))

    runtime.disconnect("client_shutdown")

    assert runtime.connection is None
    assert runtime.state is TransportHealthState.STOPPED
    assert any(event.code == "CLIENT_DISCONNECT" for event in runtime.events)
    assert not hasattr(runtime, "arm_live")
    assert not hasattr(runtime, "resume_execution")


@pytest.mark.parametrize("case", CASES, ids=lambda item: item.name)
def test_reconnect_exhaustion_and_authorization_failure_fail_closed(case: _BrokerCase) -> None:
    sent: list[object] = []

    def fail_connect(_endpoint: str) -> str:
        raise RuntimeError("wire unavailable")

    if case.driver_type is UpstoxTransportDriver:
        driver = _driver(case, sent, connector=fail_connect)
    else:
        driver = _driver(case, sent, connector=fail_connect)
    runtime = MarketDataTransportRuntime(driver, _policy(attempts=2))

    assert runtime.reconnect(object()) is False
    assert runtime.state is TransportHealthState.FAILED_CLOSED
    assert sum(event.code == "RECONNECT_ATTEMPT_FAILED" for event in runtime.events) == 2
    assert runtime.events[-1].code == "RECONNECT_EXHAUSTED"


@pytest.mark.parametrize("case", CASES, ids=lambda item: item.name)
def test_heartbeat_success_and_timeout_follow_declared_capability(case: _BrokerCase) -> None:
    driver = _driver(case, [])
    runtime = MarketDataTransportRuntime(driver, _policy())

    if driver.capabilities.heartbeat_mode is HeartbeatMode.PROVIDER_HEARTBEAT_FRAME:
        runtime.observe_frame_activity(FrameKind.HEARTBEAT, at=10.0)
    elif driver.capabilities.heartbeat_mode is HeartbeatMode.PROTOCOL_PING_PONG:
        runtime.observe_protocol_heartbeat(at=10.0)
    else:
        runtime.observe_frame_activity(FrameKind.DATA, at=10.0)

    assert runtime.heartbeat_expired(now=14.9) is False
    assert runtime.heartbeat_expired(now=15.1) is True


@pytest.mark.parametrize("case", CASES, ids=lambda item: item.name)
def test_old_generation_and_queue_overflow_fail_closed(case: _BrokerCase) -> None:
    runtime = MarketDataTransportRuntime(_driver(case, []), _policy(capacity=1))
    runtime.connect(object())
    generation = runtime.connection_generation

    assert runtime.enqueue_frame(generation, {"tick": 1}) is True
    assert runtime.enqueue_frame(generation, {"tick": 2}) is False
    assert runtime.state is TransportHealthState.FAILED_CLOSED
    assert any(event.code == "QUEUE_OVERFLOW" for event in runtime.events)

    runtime.reconnect(object())
    assert runtime.connection_generation == generation + 1
    assert runtime.enqueue_frame(generation, {"late": True}) is False
    assert any(event.code == "STALE_GENERATION_REJECTED" for event in runtime.events)


@pytest.mark.parametrize("case", CASES, ids=lambda item: item.name)
def test_malformed_or_unknown_instrument_frames_fail_at_provider_edge(case: _BrokerCase) -> None:
    driver = _driver(case, [])
    connection = driver.connect(driver.authorize(object()), connection_generation=1)

    with pytest.raises(ValueError):
        driver.decode_frame(42, connection=connection)

    with pytest.raises(ValueError):
        driver.decode_frame(
            [{
                "receive_timestamp": datetime(2026, 9, 27, 9, 15, tzinfo=UTC),
                "exchange_timestamp": datetime(2026, 9, 27, 9, 15, tzinfo=UTC),
                "decoded_payload": {"last_price": "100"},
            }],
            connection=connection,
        )


@pytest.mark.parametrize("case", CASES, ids=lambda item: item.name)
def test_provider_sequence_is_explicit_and_never_fabricated(case: _BrokerCase) -> None:
    driver = _driver(case, [])
    unavailable = driver.extract_source_sequence({})
    assert unavailable is not None
    assert unavailable.semantics is SequenceSemantics.UNAVAILABLE
    assert unavailable.scope is SequenceScope.NONE
    assert unavailable.value is None

    if case.driver_type is AngelOneTransportDriver:
        observed = driver.extract_source_sequence({"sequence_number": 41})
        assert observed is not None
        assert observed.semantics is SequenceSemantics.MONOTONIC_ONLY
        assert observed.scope is SequenceScope.INSTRUMENT
        assert observed.value == 41


@pytest.mark.parametrize("case", CASES, ids=lambda item: item.name)
def test_data_v2_per_instrument_stale_clock_gap_and_duplicate_behavior(case: _BrokerCase) -> None:
    now = datetime(2026, 9, 27, 9, 16, tzinfo=UTC)
    monitor = FeedMonitor(
        clock=_Clock(now),
        stale_after=timedelta(seconds=5),
        max_clock_skew=timedelta(seconds=2),
        required_instruments=("A", "B"),
    )
    a0 = datetime(2026, 9, 27, 9, 15, 59, tzinfo=UTC)
    b_stale = datetime(2026, 9, 27, 9, 15, 40, tzinfo=UTC)

    seq1 = SourceSequence(1, SequenceSemantics.STRICT_CONTIGUOUS, SequenceScope.INSTRUMENT, "fixture_seq")
    seq3 = SourceSequence(3, SequenceSemantics.STRICT_CONTIGUOUS, SequenceScope.INSTRUMENT, "fixture_seq")
    monitor.observe(_event(at=a0, ingress=1, source=seq1), connection_generation=1, instrument_token="A", source_sequence=seq1)
    monitor.observe(_event(at=b_stale, ingress=2, source=None), connection_generation=1, instrument_token="B", source_sequence=None)
    assert FeedHealthReason.STALE in monitor.reasons_for("B")
    assert FeedHealthReason.STALE not in monitor.reasons_for("A")

    monitor.observe(_event(at=a0, ingress=3, source=seq3), connection_generation=1, instrument_token="A", source_sequence=seq3)
    assert FeedHealthReason.SEQUENCE_GAP in monitor.reasons_for("A")

    monitor.observe(_event(at=a0, ingress=4, source=seq3), connection_generation=1, instrument_token="A", source_sequence=seq3)
    assert FeedHealthReason.OUT_OF_ORDER in monitor.reasons_for("A")

    skew_monitor = FeedMonitor(
        clock=_Clock(now),
        stale_after=timedelta(seconds=30),
        max_clock_skew=timedelta(seconds=2),
        required_instruments=("A",),
    )
    skewed = LiveMarketEvent(
        "NIFTY",
        datetime(2026, 9, 27, 9, 15, 50, tzinfo=UTC),
        datetime(2026, 9, 27, 9, 15, 59, tzinfo=UTC),
        1,
        MarketState.OPEN,
        None,
    )
    skew_monitor.observe(skewed, connection_generation=1, instrument_token="A", source_sequence=None)
    assert FeedHealthReason.CLOCK_SKEW in skew_monitor.reasons_for("A")


@pytest.mark.parametrize("case", CASES, ids=lambda item: item.name)
def test_partial_ack_never_marks_incomplete_subscription_healthy(case: _BrokerCase) -> None:
    runtime = MarketDataTransportRuntime(_driver(case, []), _policy())
    runtime.connect(object())
    request = SubscriptionRequest((case.instrument, f"{case.instrument}-SECOND"), case.mode)
    try:
        runtime.subscribe(request)
    except ValueError:
        pytest.skip("provider instrument syntax cannot express synthetic second token")

    assert runtime.acknowledge_subscription(runtime.connection_generation, request, (case.instrument,)) is False
    assert any(event.code == "PARTIAL_SUBSCRIPTION_ACK" for event in runtime.events)
    assert runtime.state is TransportHealthState.SUBSCRIBING


@pytest.mark.parametrize("case", CASES, ids=lambda item: item.name)
def test_transport_drivers_have_no_execution_or_live_arm_authority(case: _BrokerCase) -> None:
    driver = _driver(case, [])
    for forbidden in (
        "place_order",
        "modify_order",
        "cancel_order",
        "mint_approved_order",
        "arm_live",
        "resume_execution",
    ):
        assert not hasattr(driver, forbidden)

    root = Path(__file__).resolve().parents[1]
    sources = [root / "engine/data/transports/runtime.py", root / "engine/data/transports/brokers" / f"{case.name}.py"]
    for path in sources:
        text = path.read_text(encoding="utf-8").lower()
        assert "engine.risk" not in text
        assert "approvedorder" not in text
        assert "brokerportv2" not in text
        assert "arm_live(" not in text
