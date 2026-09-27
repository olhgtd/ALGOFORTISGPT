from __future__ import annotations

from pathlib import Path
import importlib
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _runtime():
    assert (ROOT / "engine/data/transports/runtime.py").is_file(), "shared transport runtime missing"
    return importlib.import_module("engine.data.transports.runtime")


def _build(action: str):
    c = importlib.import_module("engine.data.transports.contracts")
    p = importlib.import_module("engine.data.transports.policy")
    s = importlib.import_module("engine.data.transports.sequence")
    r = _runtime()

    class Driver:
        broker_id = c.BrokerId.DHAN
        capabilities = c.TransportCapabilities(c.BrokerId.DHAN, c.HeartbeatMode.NONE, s.SequenceSemantics.UNAVAILABLE, s.SequenceScope.NONE, False)
        def authorize(self, auth_context): return {"endpoint_ref": "wss://redacted.example/ws"}
        def connect(self, authorized_endpoint, *, connection_generation: int):
            return c.TransportConnection(f"c-{connection_generation}", connection_generation, authorized_endpoint["endpoint_ref"])
        def encode_subscribe(self, request): raise NotImplementedError
        def encode_unsubscribe(self, request): raise NotImplementedError
        def decode_frame(self, frame, *, connection): raise NotImplementedError
        def classify_frame(self, frame): raise NotImplementedError
        def extract_source_sequence(self, frame): return None

    policy = p.BrokerTransportPolicy(
        policy_id="TEST_ONLY/backpressure", version="1", max_reconnect_attempts=1,
        reconnect_backoff_seconds=(0.0,), receive_queue_capacity=2,
        heartbeat_timeout_seconds=5.0, stale_after_seconds=3.0,
        max_subscriptions_per_socket=10, subscription_batch_limit=5, max_connections=1,
        queue_overflow_action=p.QueueOverflowAction(action), test_only=True,
    )
    rt = r.MarketDataTransportRuntime(Driver(), policy)
    rt.connect(object())
    return rt, c


def test_queue_overflow_is_explicit_and_degrades_when_policy_says_degraded() -> None:
    rt, c = _build("DEGRADED")
    assert rt.enqueue_frame(1, b"a") is True
    assert rt.enqueue_frame(1, b"b") is True
    assert rt.enqueue_frame(1, b"c") is False
    assert rt.queued_frame_count == 2
    assert rt.state is c.TransportHealthState.DEGRADED
    assert any(e.code == "QUEUE_OVERFLOW" for e in rt.events)


def test_queue_overflow_can_fail_closed_by_versioned_policy() -> None:
    rt, c = _build("FAILED_CLOSED")
    rt.enqueue_frame(1, b"a"); rt.enqueue_frame(1, b"b")
    assert rt.enqueue_frame(1, b"c") is False
    assert rt.state is c.TransportHealthState.FAILED_CLOSED
    assert any(e.code == "QUEUE_OVERFLOW" for e in rt.events)
