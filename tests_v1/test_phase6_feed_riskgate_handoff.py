from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from engine.core.runtime import DeterministicIdGenerator, DeterministicSeedSource, FixedClock
from engine.data.feed_monitor import FeedHealthReason, FeedMonitor
from engine.data.live_feed import LiveMarketEvent, MarketState
from engine.data.transports.contracts import TransportHealthState
from engine.data.transports.sequence import SequenceScope, SequenceSemantics, SourceSequence
from engine.orders.contracts_v2 import OrderIntent, OrderSource, RunMode
from engine.orders.model import OrderType
from engine.portfolio.model import InstrumentIdentity
from engine.risk.gate_v2 import RiskEvaluation, RiskGateV2, RiskRejection
from engine.risk.limits import HardLimitHierarchy, LimitDirection


def _clock() -> FixedClock:
    return FixedClock(datetime(2026, 9, 27, 9, 16, tzinfo=timezone.utc), 77, object())


def _monitor(clock: FixedClock | None = None) -> FeedMonitor:
    return FeedMonitor(
        clock=clock or _clock(),
        stale_after=timedelta(seconds=5),
        max_clock_skew=timedelta(seconds=5),
        required_instruments=("NIFTY",),
    )


def _observe_healthy(monitor: FeedMonitor) -> None:
    timestamp = datetime(2026, 9, 27, 9, 15, 59, tzinfo=timezone.utc)
    monitor.observe(
        LiveMarketEvent(
            symbol="NIFTY",
            exchange_timestamp=timestamp,
            receive_timestamp=timestamp,
            sequence=1,
            market_state=MarketState.OPEN,
        ),
        connection_generation=1,
        instrument_token="NIFTY",
        source_sequence=SourceSequence(
            1,
            SequenceSemantics.STRICT_CONTIGUOUS,
            SequenceScope.INSTRUMENT,
            "phase6_test_sequence",
        ),
    )


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
    created = datetime(2026, 9, 27, 9, 15, tzinfo=timezone.utc)
    instrument = InstrumentIdentity(
        "NSE",
        "NIFTY26SEP22000CE",
        "options",
        underlying="NIFTY",
        expiry=date(2026, 9, 27),
        strike="22000",
        option_type="CE",
    )
    return OrderIntent(
        intent_id="phase6-feed-handoff",
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


@pytest.mark.parametrize(
    ("transport_state", "expected_reason"),
    [
        (TransportHealthState.DEGRADED, FeedHealthReason.TRANSPORT_DEGRADED),
        (TransportHealthState.FAILED_CLOSED, FeedHealthReason.TRANSPORT_FAILED_CLOSED),
    ],
)
def test_unhealthy_transport_blocks_riskgate_through_existing_entry_policy(
    transport_state: TransportHealthState,
    expected_reason: FeedHealthReason,
) -> None:
    clock = _clock()
    monitor = _monitor(clock)
    _observe_healthy(monitor)
    monitor.observe_transport_health(transport_state)
    evaluator = _Evaluator()
    audit = _Audit()
    gate = RiskGateV2(
        evaluator=evaluator,
        clock=clock,
        id_generator=DeterministicIdGenerator(clock, DeterministicSeedSource(9), "phase6-feed"),
        audit_sink=audit,
        hard_limits=_LIMITS,
        entry_policy=monitor,
    )

    result = gate.evaluate_entry(_intent())

    assert expected_reason in monitor.reasons
    assert monitor.protective_exits_allowed is True
    assert isinstance(result, RiskRejection)
    assert result.reasons == ("entries_halted",)
    assert evaluator.calls == 0
    assert audit.events[0][0] == "RISK_APPROVAL_REJECTED"


def test_healthy_transport_does_not_override_other_feed_integrity_blocks() -> None:
    clock = _clock()
    monitor = _monitor(clock)
    stale_timestamp = datetime(2026, 9, 27, 9, 15, 40, tzinfo=timezone.utc)
    monitor.observe(
        LiveMarketEvent("NIFTY", stale_timestamp, stale_timestamp, 1, MarketState.OPEN),
        connection_generation=1,
        instrument_token="NIFTY",
        source_sequence=SourceSequence(
            1,
            SequenceSemantics.STRICT_CONTIGUOUS,
            SequenceScope.INSTRUMENT,
            "phase6_test_sequence",
        ),
    )
    monitor.observe_transport_health(TransportHealthState.HEALTHY)

    assert FeedHealthReason.STALE in monitor.reasons
    assert monitor.entries_allowed is False
    assert monitor.protective_exits_allowed is True


def test_transport_runtime_and_bridge_have_no_direct_riskgate_or_operational_state_authority() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "engine/data/transports/runtime.py",
        "engine/data/transports/bridge.py",
    ):
        source = (root / relative).read_text(encoding="utf-8").lower()
        assert "engine.risk" not in source
        assert "riskgate" not in source
        assert "approvedorder" not in source
        assert "operational_state" not in source
        assert "engine.live" not in source
