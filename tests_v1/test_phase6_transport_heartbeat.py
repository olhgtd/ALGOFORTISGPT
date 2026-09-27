from __future__ import annotations

import importlib
from pathlib import Path
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


class Driver:
    def __init__(self, heartbeat_mode):
        c, _, s, _ = _mods(); self.broker_id = c.BrokerId.DHAN
        self.capabilities = c.TransportCapabilities(c.BrokerId.DHAN, heartbeat_mode, s.SequenceSemantics.UNAVAILABLE, s.SequenceScope.NONE, False)
    def authorize(self, auth_context): return {"endpoint_ref": "wss://redacted.example/ws"}
    def connect(self, authorized_endpoint, *, connection_generation: int):
        c, _, _, _ = _mods(); return c.TransportConnection(f"d-{connection_generation}", connection_generation, authorized_endpoint["endpoint_ref"])
    def encode_subscribe(self, request): return request
    def encode_unsubscribe(self, request): return request
    def decode_frame(self, frame, *, connection): raise NotImplementedError
    def classify_frame(self, frame): raise NotImplementedError
    def extract_source_sequence(self, frame): return None


def _runtime(mode):
    c, p, _, r = _mods()
    policy = p.BrokerTransportPolicy(policy_id="TEST_ONLY/heartbeat", version="1", max_reconnect_attempts=1, reconnect_backoff_seconds=(0.0,), receive_queue_capacity=8, heartbeat_timeout_seconds=5.0, stale_after_seconds=3.0, max_subscriptions_per_socket=10, subscription_batch_limit=5, max_connections=1, queue_overflow_action=p.QueueOverflowAction.FAILED_CLOSED, test_only=True)
    rt = r.MarketDataTransportRuntime(Driver(mode), policy); rt.connect(object()); return rt, c


def test_data_frame_tracks_frame_and_data_but_not_protocol_heartbeat_by_default() -> None:
    c, _, _, _ = _mods(); rt, _ = _runtime(c.HeartbeatMode.PROTOCOL_PING_PONG)
    rt.observe_frame_activity(c.FrameKind.DATA, at=10.0)
    assert rt.last_frame_at == 10.0 and rt.last_data_at == 10.0 and rt.last_protocol_heartbeat_at is None
    rt.observe_protocol_heartbeat(at=11.0)
    assert rt.last_protocol_heartbeat_at == 11.0
    assert rt.heartbeat_expired(now=15.9) is False
    assert rt.heartbeat_expired(now=16.1) is True


def test_data_activity_mode_explicitly_uses_market_data_as_heartbeat() -> None:
    c, _, _, _ = _mods(); rt, _ = _runtime(c.HeartbeatMode.DATA_ACTIVITY)
    rt.observe_frame_activity(c.FrameKind.DATA, at=20.0)
    assert rt.last_frame_at == 20.0 and rt.last_data_at == 20.0 and rt.last_protocol_heartbeat_at == 20.0
    assert rt.heartbeat_expired(now=24.9) is False
    assert rt.heartbeat_expired(now=25.1) is True


def test_provider_heartbeat_frame_is_distinct_from_data_clock() -> None:
    c, _, _, _ = _mods(); rt, _ = _runtime(c.HeartbeatMode.PROVIDER_HEARTBEAT_FRAME)
    rt.observe_frame_activity(c.FrameKind.HEARTBEAT, at=30.0)
    assert rt.last_frame_at == 30.0 and rt.last_data_at is None and rt.last_protocol_heartbeat_at == 30.0


def test_none_heartbeat_mode_never_invents_a_deadline() -> None:
    c, _, _, _ = _mods(); rt, _ = _runtime(c.HeartbeatMode.NONE)
    rt.observe_frame_activity(c.FrameKind.DATA, at=40.0)
    assert rt.last_protocol_heartbeat_at is None
    assert rt.heartbeat_expired(now=1000.0) is False
