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


def _mods():
    c = importlib.import_module("engine.data.transports.contracts")
    p = importlib.import_module("engine.data.transports.policy")
    s = importlib.import_module("engine.data.transports.sequence")
    return c, p, s


class FakeDriver:
    def __init__(self, *, fail_connect_times: int = 0):
        c, _, s = _mods()
        self.broker_id = c.BrokerId.ANGELONE
        self.capabilities = c.TransportCapabilities(c.BrokerId.ANGELONE, c.HeartbeatMode.NONE, s.SequenceSemantics.UNAVAILABLE, s.SequenceScope.NONE, False)
        self.fail_connect_times = fail_connect_times
        self.authorize_calls = 0
        self.connect_calls = 0

    def authorize(self, auth_context):
        self.authorize_calls += 1
        return {"endpoint_ref": "wss://redacted.example/ws"}

    def connect(self, authorized_endpoint, *, connection_generation: int):
        c, _, _ = _mods()
        self.connect_calls += 1
        if self.fail_connect_times > 0:
            self.fail_connect_times -= 1
            raise RuntimeError("simulated connect failure")
        return c.TransportConnection(f"conn-{connection_generation}", connection_generation, authorized_endpoint["endpoint_ref"])

    def encode_subscribe(self, request): raise NotImplementedError
    def encode_unsubscribe(self, request): raise NotImplementedError
    def decode_frame(self, frame, *, connection): raise AssertionError("old generation must be rejected before decode")
    def classify_frame(self, frame): raise NotImplementedError
    def extract_source_sequence(self, frame): return None


def _policy(*, attempts=3, overflow="FAILED_CLOSED", queue=2):
    _, p, _ = _mods()
    return p.BrokerTransportPolicy(
        policy_id="TEST_ONLY/runtime", version="1", max_reconnect_attempts=attempts,
        reconnect_backoff_seconds=tuple(float(i) / 10 for i in range(1, attempts + 1)),
        receive_queue_capacity=queue, heartbeat_timeout_seconds=5.0, stale_after_seconds=3.0,
        max_subscriptions_per_socket=100, subscription_batch_limit=25, max_connections=2,
        queue_overflow_action=p.QueueOverflowAction(overflow), test_only=True,
    )


def test_runtime_starts_stopped_and_connects_through_explicit_states() -> None:
    r = _runtime(); c, _, _ = _mods(); driver = FakeDriver()
    rt = r.MarketDataTransportRuntime(driver, _policy())
    assert rt.state is c.TransportHealthState.STOPPED
    conn = rt.connect({"secret_ref": "injected"})
    assert conn.connection_generation == 1
    assert rt.connection_generation == 1
    assert rt.state is c.TransportHealthState.CONNECTED
    assert [x.value for x in rt.state_history] == ["STOPPED", "CONNECTING", "AUTHORIZING", "CONNECTED"]


def test_reconnect_increments_generation_and_old_callback_is_rejected_before_decode() -> None:
    r = _runtime(); c, _, _ = _mods(); driver = FakeDriver()
    rt = r.MarketDataTransportRuntime(driver, _policy())
    rt.connect(object())
    rt.unexpected_disconnect("wire_closed")
    assert rt.state is c.TransportHealthState.RECONNECTING
    assert rt.reconnect(object()) is True
    assert rt.connection_generation == 2
    assert rt.enqueue_frame(1, b"delayed-old") is False
    assert rt.queued_frame_count == 0
    assert any(e.code == "STALE_GENERATION_REJECTED" and e.connection_generation == 1 for e in rt.events)
    assert rt.enqueue_frame(2, b"current") is True
    assert rt.queued_frame_count == 1


def test_bounded_reconnect_uses_policy_backoff_and_fails_closed_on_exhaustion() -> None:
    r = _runtime(); c, _, _ = _mods(); sleeps = []
    driver = FakeDriver(fail_connect_times=99)
    rt = r.MarketDataTransportRuntime(driver, _policy(attempts=3), sleeper=sleeps.append)
    rt.unexpected_disconnect("no_socket")
    assert rt.reconnect(object()) is False
    assert rt.state is c.TransportHealthState.FAILED_CLOSED
    assert driver.connect_calls == 3
    assert sleeps == [0.1, 0.2, 0.3]
    assert any(e.code == "RECONNECT_EXHAUSTED" for e in rt.events)


def test_reconnect_success_never_exposes_live_arm_or_entry_authority() -> None:
    r = _runtime(); driver = FakeDriver()
    rt = r.MarketDataTransportRuntime(driver, _policy())
    rt.connect(object())
    rt.unexpected_disconnect("drop")
    assert rt.reconnect(object()) is True
    assert not hasattr(rt, "arm_enabled")
    assert not hasattr(rt, "entries_allowed")
    assert not hasattr(rt, "risk_gate")
