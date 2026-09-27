from __future__ import annotations

from pathlib import Path
import importlib
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _mods():
    c = importlib.import_module("engine.data.transports.contracts")
    p = importlib.import_module("engine.data.transports.policy")
    s = importlib.import_module("engine.data.transports.sequence")
    r = importlib.import_module("engine.data.transports.runtime")
    return c, p, s, r


class AckDriver:
    def __init__(self):
        c, _, s, _ = _mods()
        self.broker_id = c.BrokerId.ZERODHA
        self.capabilities = c.TransportCapabilities(c.BrokerId.ZERODHA, c.HeartbeatMode.NONE, s.SequenceSemantics.UNAVAILABLE, s.SequenceScope.NONE, True)
        self.subscribe_calls = []
        self.unsubscribe_calls = []
    def authorize(self, auth_context): return {"endpoint_ref": "wss://redacted.example/ws"}
    def connect(self, authorized_endpoint, *, connection_generation: int):
        c, _, _, _ = _mods(); return c.TransportConnection(f"z-{connection_generation}", connection_generation, authorized_endpoint["endpoint_ref"])
    def encode_subscribe(self, request): self.subscribe_calls.append(request); return ("SUB", request)
    def encode_unsubscribe(self, request): self.unsubscribe_calls.append(request); return ("UNSUB", request)
    def decode_frame(self, frame, *, connection): raise NotImplementedError
    def classify_frame(self, frame): raise NotImplementedError
    def extract_source_sequence(self, frame): return None


def _policy():
    _, p, _, _ = _mods()
    return p.BrokerTransportPolicy(policy_id="TEST_ONLY/subscriptions", version="1", max_reconnect_attempts=2, reconnect_backoff_seconds=(0.0, 0.0), receive_queue_capacity=8, heartbeat_timeout_seconds=5.0, stale_after_seconds=3.0, max_subscriptions_per_socket=100, subscription_batch_limit=25, max_connections=1, queue_overflow_action=p.QueueOverflowAction.FAILED_CLOSED, test_only=True)


def test_desired_set_is_broker_neutral_and_partial_ack_cannot_become_healthy() -> None:
    c, _, _, r = _mods(); d = AckDriver(); rt = r.MarketDataTransportRuntime(d, _policy()); rt.connect(object())
    request = c.SubscriptionRequest(("NIFTY", "BANKNIFTY"), "QUOTE")
    assert rt.subscribe(request) is True
    assert rt.desired_subscriptions == (request,)
    assert rt.state is c.TransportHealthState.SUBSCRIBING
    assert rt.acknowledge_subscription(1, request, ("NIFTY",)) is False
    assert rt.state is c.TransportHealthState.SUBSCRIBING
    assert rt.active_subscriptions == ()
    assert any(e.code == "PARTIAL_SUBSCRIPTION_ACK" for e in rt.events)
    assert rt.acknowledge_subscription(1, request, ("BANKNIFTY", "NIFTY")) is True
    assert rt.active_subscriptions == (request,)
    assert rt.state is c.TransportHealthState.HEALTHY


def test_reconnect_replays_desired_exactly_once_for_new_generation_and_stale_ack_is_ignored() -> None:
    c, _, _, r = _mods(); d = AckDriver(); rt = r.MarketDataTransportRuntime(d, _policy()); rt.connect(object())
    request = c.SubscriptionRequest(("NIFTY",), "QUOTE")
    rt.subscribe(request)
    assert len(d.subscribe_calls) == 1
    assert rt.acknowledge_subscription(1, request, ("NIFTY",)) is True
    rt.unexpected_disconnect("drop")
    assert rt.reconnect(object()) is True
    assert rt.connection_generation == 2
    assert len(d.subscribe_calls) == 2
    assert rt.active_subscriptions == ()
    assert rt.state is c.TransportHealthState.SUBSCRIBING
    assert rt.acknowledge_subscription(1, request, ("NIFTY",)) is False
    assert any(e.code == "STALE_SUBSCRIPTION_ACK_REJECTED" and e.connection_generation == 1 for e in rt.events)
    assert rt.acknowledge_subscription(2, request, ("NIFTY",)) is True
    rt.replay_desired_subscriptions()
    assert len(d.subscribe_calls) == 2


def test_unsubscribe_removes_desired_and_current_active_deterministically() -> None:
    c, _, _, r = _mods(); d = AckDriver(); rt = r.MarketDataTransportRuntime(d, _policy()); rt.connect(object())
    a = c.SubscriptionRequest(("NIFTY",), "QUOTE"); b = c.SubscriptionRequest(("BANKNIFTY",), "QUOTE")
    rt.subscribe(a); rt.subscribe(b)
    rt.acknowledge_subscription(1, a, ("NIFTY",)); rt.acknowledge_subscription(1, b, ("BANKNIFTY",))
    assert rt.state is c.TransportHealthState.HEALTHY
    assert rt.unsubscribe(a) is True
    assert rt.desired_subscriptions == (b,)
    assert rt.active_subscriptions == (b,)
    assert d.unsubscribe_calls == [a]
