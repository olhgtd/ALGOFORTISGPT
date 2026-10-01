from datetime import datetime, timezone

import pytest

from engine.data.live_feed import MarketState
from engine.data.transports.bridge import MarketEventBridge, StaleGenerationError
from engine.data.transports.contracts import BrokerId, FrameKind, ProviderEnvelope
from engine.data.transports.sequence import SequenceScope, SequenceSemantics, SourceSequence


def _envelope(generation: int, source_value: int) -> ProviderEnvelope:
    timestamp = datetime(2026, 9, 27, 9, 0, tzinfo=timezone.utc)
    return ProviderEnvelope(
        broker_id=BrokerId.ANGELONE,
        connection_id="connection-1",
        connection_generation=generation,
        instrument_token="NIFTY",
        receive_timestamp=timestamp,
        exchange_timestamp=timestamp,
        source_sequence=SourceSequence(
            source_value,
            SequenceSemantics.STRICT_CONTIGUOUS,
            SequenceScope.INSTRUMENT,
            "provider_sequence",
        ),
        frame_kind=FrameKind.DATA,
        decoded_payload={"symbol": "NIFTY", "market_state": MarketState.OPEN.value},
    )


def test_bridge_keeps_ingress_sequence_separate_from_source_sequence() -> None:
    bridge = MarketEventBridge()
    bridge.activate_generation(7)

    observation = bridge.to_observation(_envelope(7, 100), ingress_sequence=900)

    assert observation.event.ingress_sequence == 900
    assert observation.event.sequence == 900
    assert observation.event.source_sequence == observation.source_sequence
    assert observation.source_sequence is not None
    assert observation.source_sequence.value == 100
    assert observation.connection_generation == 7
    assert observation.instrument_token == "NIFTY"


def test_bridge_rejects_old_generation_before_monitor() -> None:
    bridge = MarketEventBridge()
    bridge.activate_generation(2)

    with pytest.raises(StaleGenerationError):
        bridge.to_observation(_envelope(1, 100), ingress_sequence=1)
