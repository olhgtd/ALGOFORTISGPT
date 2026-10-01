from datetime import datetime, timedelta, timezone

import pytest

from engine.data.feed_monitor import FeedHealthReason, FeedMonitor, FeedMonitorError
from engine.data.live_feed import LiveMarketEvent, MarketState
from engine.data.transports.sequence import SequenceScope, SequenceSemantics, SourceSequence


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def now_utc(self) -> datetime:
        return self.now


def _event(symbol: str, timestamp: datetime, ingress_sequence: int) -> LiveMarketEvent:
    return LiveMarketEvent(
        symbol=symbol,
        exchange_timestamp=timestamp,
        receive_timestamp=timestamp,
        sequence=ingress_sequence,
        market_state=MarketState.OPEN,
    )


def _source(value: int, semantics: SequenceSemantics = SequenceSemantics.STRICT_CONTIGUOUS) -> SourceSequence:
    return SourceSequence(value, semantics, SequenceScope.INSTRUMENT, "provider_sequence")


def test_strict_gap_is_keyed_by_generation_and_instrument() -> None:
    timestamp = datetime(2026, 9, 27, 9, 0, tzinfo=timezone.utc)
    monitor = FeedMonitor(
        clock=_Clock(timestamp),
        stale_after=timedelta(seconds=5),
        max_clock_skew=timedelta(seconds=1),
        required_instruments=("NIFTY", "BANKNIFTY"),
    )

    monitor.observe(_event("NIFTY", timestamp, 1), connection_generation=42, instrument_token="NIFTY", source_sequence=_source(100))
    monitor.observe(_event("BANKNIFTY", timestamp, 2), connection_generation=42, instrument_token="BANKNIFTY", source_sequence=_source(501))
    monitor.observe(_event("NIFTY", timestamp, 3), connection_generation=42, instrument_token="NIFTY", source_sequence=_source(101))
    monitor.observe(_event("BANKNIFTY", timestamp, 4), connection_generation=42, instrument_token="BANKNIFTY", source_sequence=_source(502))
    monitor.observe(_event("NIFTY", timestamp, 5), connection_generation=42, instrument_token="NIFTY", source_sequence=_source(103))
    monitor.observe(_event("BANKNIFTY", timestamp, 6), connection_generation=42, instrument_token="BANKNIFTY", source_sequence=_source(503))

    assert FeedHealthReason.SEQUENCE_GAP in monitor.reasons_for("NIFTY")
    assert FeedHealthReason.SEQUENCE_GAP not in monitor.reasons_for("BANKNIFTY")
    assert FeedHealthReason.SEQUENCE_GAP in monitor.reasons


def test_new_generation_starts_new_sequence_history_and_old_generation_is_rejected() -> None:
    timestamp = datetime(2026, 9, 27, 9, 0, tzinfo=timezone.utc)
    monitor = FeedMonitor(
        clock=_Clock(timestamp),
        stale_after=timedelta(seconds=5),
        max_clock_skew=timedelta(seconds=1),
    )

    monitor.observe(_event("NIFTY", timestamp, 1), connection_generation=1, instrument_token="NIFTY", source_sequence=_source(999))
    monitor.observe(_event("NIFTY", timestamp, 2), connection_generation=2, instrument_token="NIFTY", source_sequence=_source(10))

    assert FeedHealthReason.OUT_OF_ORDER not in monitor.reasons_for("NIFTY")
    assert FeedHealthReason.SEQUENCE_GAP not in monitor.reasons_for("NIFTY")

    with pytest.raises(FeedMonitorError):
        monitor.observe(_event("NIFTY", timestamp, 3), connection_generation=1, instrument_token="NIFTY", source_sequence=_source(1000))


def test_monotonic_only_detects_regression_but_not_numeric_gap() -> None:
    timestamp = datetime(2026, 9, 27, 9, 0, tzinfo=timezone.utc)
    monitor = FeedMonitor(
        clock=_Clock(timestamp),
        stale_after=timedelta(seconds=5),
        max_clock_skew=timedelta(seconds=1),
    )

    monitor.observe(_event("NIFTY", timestamp, 1), connection_generation=1, instrument_token="NIFTY", source_sequence=_source(10, SequenceSemantics.MONOTONIC_ONLY))
    monitor.observe(_event("NIFTY", timestamp, 2), connection_generation=1, instrument_token="NIFTY", source_sequence=_source(20, SequenceSemantics.MONOTONIC_ONLY))
    assert FeedHealthReason.SEQUENCE_GAP not in monitor.reasons_for("NIFTY")

    monitor.observe(_event("NIFTY", timestamp, 3), connection_generation=1, instrument_token="NIFTY", source_sequence=_source(19, SequenceSemantics.MONOTONIC_ONLY))
    assert FeedHealthReason.OUT_OF_ORDER in monitor.reasons_for("NIFTY")


def test_unavailable_sequence_never_uses_ingress_sequence_as_provider_gap_evidence() -> None:
    timestamp = datetime(2026, 9, 27, 9, 0, tzinfo=timezone.utc)
    monitor = FeedMonitor(
        clock=_Clock(timestamp),
        stale_after=timedelta(seconds=5),
        max_clock_skew=timedelta(seconds=1),
    )
    unavailable = SourceSequence(None, SequenceSemantics.UNAVAILABLE, SequenceScope.NONE)

    monitor.observe(_event("NIFTY", timestamp, 1), connection_generation=1, instrument_token="NIFTY", source_sequence=unavailable)
    monitor.observe(_event("NIFTY", timestamp, 999), connection_generation=1, instrument_token="NIFTY", source_sequence=unavailable)

    assert FeedHealthReason.SEQUENCE_GAP not in monitor.reasons_for("NIFTY")
    assert FeedHealthReason.OUT_OF_ORDER not in monitor.reasons_for("NIFTY")


def test_required_instrument_staleness_is_independent() -> None:
    timestamp = datetime(2026, 9, 27, 9, 0, tzinfo=timezone.utc)
    clock = _Clock(timestamp)
    monitor = FeedMonitor(
        clock=clock,
        stale_after=timedelta(seconds=5),
        max_clock_skew=timedelta(seconds=1),
        required_instruments=("NIFTY", "BANKNIFTY"),
    )

    monitor.observe(_event("NIFTY", timestamp, 1), connection_generation=1, instrument_token="NIFTY", source_sequence=_source(1))
    monitor.observe(_event("BANKNIFTY", timestamp, 2), connection_generation=1, instrument_token="BANKNIFTY", source_sequence=_source(1))

    clock.now = timestamp + timedelta(seconds=7)
    monitor.observe(_event("BANKNIFTY", clock.now, 3), connection_generation=1, instrument_token="BANKNIFTY", source_sequence=_source(2))

    assert FeedHealthReason.STALE in monitor.reasons_for("NIFTY")
    assert FeedHealthReason.STALE not in monitor.reasons_for("BANKNIFTY")
    assert not monitor.entries_allowed
