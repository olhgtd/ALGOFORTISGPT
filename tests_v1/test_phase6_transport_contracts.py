from __future__ import annotations
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path
import importlib
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]

def _contracts():
    assert (ROOT / "engine/data/transports/contracts.py").is_file(), "transport contracts module missing"
    sys.path.insert(0, str(ROOT)) if str(ROOT) not in sys.path else None
    return importlib.import_module("engine.data.transports.contracts")

def _sequence():
    assert (ROOT / "engine/data/transports/sequence.py").is_file(), "transport sequence module missing"
    sys.path.insert(0, str(ROOT)) if str(ROOT) not in sys.path else None
    return importlib.import_module("engine.data.transports.sequence")

def test_transport_health_state_is_exact_and_lower_level() -> None:
    c = _contracts()
    assert [x.value for x in c.TransportHealthState] == [
        "STOPPED","CONNECTING","AUTHORIZING","CONNECTED","SUBSCRIBING","HEALTHY","DEGRADED","RECONNECTING","FAILED_CLOSED"
    ]

def test_heartbeat_modes_are_explicit() -> None:
    c = _contracts()
    assert {x.value for x in c.HeartbeatMode} == {"PROTOCOL_PING_PONG","PROVIDER_HEARTBEAT_FRAME","DATA_ACTIVITY","NONE"}

def test_source_sequence_requires_semantics_and_never_fabricates_unavailable_value() -> None:
    s = _sequence()
    strict = s.SourceSequence(101, s.SequenceSemantics.STRICT_CONTIGUOUS, s.SequenceScope.INSTRUMENT, "seq")
    assert strict.value == 101 and strict.provider_field == "seq"
    unavailable = s.SourceSequence(None, s.SequenceSemantics.UNAVAILABLE, s.SequenceScope.NONE, None)
    assert unavailable.value is None
    with pytest.raises(ValueError):
        s.SourceSequence(1, s.SequenceSemantics.UNAVAILABLE, s.SequenceScope.NONE, None)
    with pytest.raises(ValueError):
        s.SourceSequence(None, s.SequenceSemantics.STRICT_CONTIGUOUS, s.SequenceScope.INSTRUMENT, "seq")

def test_connection_and_provider_envelope_are_immutable_and_generation_scoped() -> None:
    c = _contracts(); s = _sequence()
    conn = c.TransportConnection("conn-42", 42, "wss://redacted.example/ws")
    env = c.ProviderEnvelope(
        broker_id=c.BrokerId.ANGELONE,
        connection_id=conn.connection_id,
        connection_generation=conn.connection_generation,
        instrument_token="NIFTY_TOKEN",
        receive_timestamp=datetime(2026,9,27,tzinfo=timezone.utc),
        exchange_timestamp=None,
        source_sequence=s.SourceSequence(100, s.SequenceSemantics.STRICT_CONTIGUOUS, s.SequenceScope.INSTRUMENT, "seq"),
        frame_kind=c.FrameKind.DATA,
        decoded_payload={"ltp": 25000.0},
    )
    assert env.connection_generation == 42
    with pytest.raises(FrozenInstanceError):
        env.connection_generation = 43

def test_subscription_request_is_broker_neutral_and_deduplicated() -> None:
    c = _contracts()
    req = c.SubscriptionRequest(("NIFTY_TOKEN", "BANKNIFTY_TOKEN", "NIFTY_TOKEN"), "QUOTE")
    assert req.instruments == ("NIFTY_TOKEN", "BANKNIFTY_TOKEN")
    with pytest.raises(ValueError):
        c.SubscriptionRequest((), "QUOTE")

def test_driver_protocol_exposes_only_transport_edge_contract() -> None:
    c = _contracts()
    names = set(c.BrokerTransportDriver.__dict__)
    for required in {"authorize","connect","encode_subscribe","encode_unsubscribe","decode_frame","classify_frame","extract_source_sequence"}:
        assert required in names
    assert not ({"place","submit","modify","cancel","mint_approved_order"} & names)

def test_decode_contract_is_multiplex_safe() -> None:
    c = _contracts()
    annotation = c.BrokerTransportDriver.decode_frame.__annotations__["return"]
    assert "ProviderEnvelopeBatch" in str(annotation)
    assert c.ProviderEnvelopeBatch == tuple[c.ProviderEnvelope, ...]

def test_capabilities_bind_broker_heartbeat_and_sequence_semantics() -> None:
    c = _contracts(); s = _sequence()
    caps = c.TransportCapabilities(c.BrokerId.UPSTOX, c.HeartbeatMode.DATA_ACTIVITY, s.SequenceSemantics.UNAVAILABLE, s.SequenceScope.NONE, True)
    assert caps.broker_id is c.BrokerId.UPSTOX
