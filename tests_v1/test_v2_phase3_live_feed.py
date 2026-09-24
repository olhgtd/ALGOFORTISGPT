from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from importlib import import_module

import pytest

from engine.core.runtime import DeterministicIdGenerator, DeterministicSeedSource, FixedClock
from engine.orders.contracts_v2 import OrderIntent, OrderSource, RunMode
from engine.orders.model import OrderType
from engine.portfolio.model import InstrumentIdentity
from engine.risk.gate_v2 import RiskEvaluation, RiskGateV2, RiskRejection
from engine.risk.limits import HardLimitHierarchy, LimitDirection


def _feed_api():
    try:
        return import_module("engine.data.live_feed")
    except ModuleNotFoundError:
        pytest.fail("engine.data.live_feed is missing", pytrace=False)


def _monitor_api():
    try:
        return import_module("engine.data.feed_monitor")
    except ModuleNotFoundError:
        pytest.fail("engine.data.feed_monitor is missing", pytrace=False)


def _clock(minute: int = 16, second: int = 0) -> FixedClock:
    return FixedClock(datetime(2026, 9, 24, 9, minute, second, tzinfo=timezone.utc), 77, object())


def _event(*, sequence: int = 1, receive_second: int = 59, exchange_second: int = 58, state_name: str = "OPEN"):
    feed = _feed_api()
    return feed.LiveMarketEvent(
        symbol="NIFTY",
        exchange_timestamp=datetime(2026, 9, 24, 9, 15, exchange_second, tzinfo=timezone.utc),
        receive_timestamp=datetime(2026, 9, 24, 9, 15, receive_second, tzinfo=timezone.utc),
        sequence=sequence,
        market_state=getattr(feed.MarketState, state_name),
    )


def _monitor(*, clock: FixedClock | None = None):
    api = _monitor_api()
    return api.FeedMonitor(
        clock=clock or _clock(),
        stale_after=timedelta(seconds=5),
        max_clock_skew=timedelta(seconds=5),
    )


def test_healthy_feed_allows_new_entries_and_preserves_protective_exits():
    monitor = _monitor()
    monitor.observe(_event())

    assert monitor.entries_allowed is True
    assert monitor.protective_exits_allowed is True
    assert monitor.reasons == ()


def test_stale_feed_blocks_entries_but_not_protective_exits():
    monitor = _monitor()
    monitor.observe(_event(receive_second=50, exchange_second=49))

    assert monitor.entries_allowed is False
    assert _monitor_api().FeedHealthReason.STALE in monitor.reasons
    assert monitor.protective_exits_allowed is True


def test_sequence_gap_and_out_of_order_events_fail_closed():
    api = _monitor_api()
    gap = _monitor()
    gap.observe(_event(sequence=10))
    gap.observe(_event(sequence=12))
    assert gap.entries_allowed is False
    assert api.FeedHealthReason.SEQUENCE_GAP in gap.reasons

    out_of_order = _monitor()
    out_of_order.observe(_event(sequence=10))
    out_of_order.observe(_event(sequence=9))
    assert out_of_order.entries_allowed is False
    assert api.FeedHealthReason.OUT_OF_ORDER in out_of_order.reasons


def test_excessive_exchange_receive_clock_skew_blocks_entries():
    api = _monitor_api()
    monitor = _monitor()
    monitor.observe(_event(receive_second=59, exchange_second=40))

    assert monitor.entries_allowed is False
    assert api.FeedHealthReason.CLOCK_SKEW in monitor.reasons


def test_closed_or_halted_market_blocks_entries():
    api = _monitor_api()
    for state in ("CLOSED", "HALTED"):
        monitor = _monitor()
        monitor.observe(_event(state_name=state))
        assert monitor.entries_allowed is False
        expected = api.FeedHealthReason.MARKET_CLOSED if state == "CLOSED" else api.FeedHealthReason.MARKET_HALTED
        assert expected in monitor.reasons
        assert monitor.protective_exits_allowed is True


def test_reconnect_requires_explicit_resubscribe_before_entries_resume():
    api = _monitor_api()
    monitor = _monitor()
    monitor.observe(_event())
    assert monitor.entries_allowed is True

    monitor.mark_disconnected()
    assert monitor.entries_allowed is False
    assert api.FeedHealthReason.RECONNECTING in monitor.reasons

    monitor.mark_reconnected()
    assert monitor.entries_allowed is False
    assert api.FeedHealthReason.RESUBSCRIBE_REQUIRED in monitor.reasons

    monitor.mark_resubscribed()
    monitor.observe(_event(sequence=2))
    assert monitor.entries_allowed is True


_LIMITS = HardLimitHierarchy(
    definitions={"max_order_qty": LimitDirection.MAXIMUM},
    platform={"max_order_qty": "10"},
).resolve()


@dataclass
class _Evaluator:
    calls: int = 0

    def evaluate(self, intent: OrderIntent) -> RiskEvaluation:
        self.calls += 1
        return RiskEvaluation.approved(
            approved_qty=intent.qty,
            risk_rule_version="risk/v1",
            limits_snapshot_id=_LIMITS.snapshot_id,
        )


class _Audit:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def write(self, event_type: str, payload: dict[str, object]) -> None:
        self.events.append((event_type, dict(payload)))


def _intent() -> OrderIntent:
    created = datetime(2026, 9, 24, 9, 15, tzinfo=timezone.utc)
    instrument = InstrumentIdentity(
        "NSE", "NIFTY26SEP22000CE", "options",
        underlying="NIFTY", expiry=date(2026, 9, 24), strike="22000", option_type="CE",
    )
    return OrderIntent(
        intent_id="feed-gate-intent",
        strategy_id="orb",
        strategy_version="orb/v1",
        run_mode=RunMode.PAPER,
        instrument_ref=instrument,
        side="BUY",
        qty=Decimal("1"),
        order_type=OrderType.MARKET,
        created_at=created,
        valid_until=created + timedelta(minutes=5),
        source=OrderSource.STRATEGY,
        provenance={"dataset_version": "ds-v1"},
    )


def test_stale_feed_policy_blocks_risk_gate_before_evaluator():
    clock = _clock()
    monitor = _monitor(clock=clock)
    monitor.observe(_event(receive_second=50, exchange_second=49))
    evaluator = _Evaluator()
    audit = _Audit()
    gate = RiskGateV2(
        evaluator=evaluator,
        clock=clock,
        id_generator=DeterministicIdGenerator(clock, DeterministicSeedSource(9), "phase3-feed"),
        audit_sink=audit,
        hard_limits=_LIMITS,
        entry_policy=monitor,
    )

    result = gate.evaluate_entry(_intent())

    assert isinstance(result, RiskRejection)
    assert result.reasons == ("entries_halted",)
    assert evaluator.calls == 0
    assert audit.events[0][0] == "RISK_APPROVAL_REJECTED"
