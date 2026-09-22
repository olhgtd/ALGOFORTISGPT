from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from engine.core.runtime import DeterministicIdGenerator, DeterministicSeedSource, FixedClock
from engine.orders.contracts_v2 import ApprovedOrder, OrderIntent, OrderSource, RunMode
from engine.orders.intent_guard import IntentGuard, IntentGuardReason, IntentGuardState
from engine.orders.model import OrderType
from engine.portfolio.model import InstrumentIdentity
from engine.risk.gate_v2 import RiskEvaluation, RiskGateV2
from engine.risk.limits import HardLimitHierarchy, LimitDirection


@dataclass
class _Evaluator:
    result: RiskEvaluation

    def evaluate(self, intent: OrderIntent) -> RiskEvaluation:
        return self.result


class _AuditSink:
    def write(self, event_type: str, payload: dict[str, object]) -> None:
        return None


def _clock(*, minute: int = 16) -> FixedClock:
    return FixedClock(
        datetime(2026, 9, 21, 9, minute, tzinfo=timezone.utc),
        123,
        object(),
    )


def _limits():
    return HardLimitHierarchy(
        definitions={"max_order_qty": LimitDirection.MAXIMUM},
        platform={"max_order_qty": "10"},
    ).resolve()


def _intent(*, intent_id: str = "intent-001", valid_for_minutes: int = 5) -> OrderIntent:
    created = datetime(2026, 9, 21, 9, 15, tzinfo=timezone.utc)
    instrument = InstrumentIdentity(
        "NSE",
        "NIFTY26SEP22000CE",
        "options",
        underlying="NIFTY",
        expiry=date(2026, 9, 24),
        strike="22000",
        option_type="CE",
    )
    return OrderIntent(
        intent_id=intent_id,
        strategy_id="orb",
        strategy_version="orb/v1",
        run_mode=RunMode.PAPER,
        instrument_ref=instrument,
        side="BUY",
        qty=Decimal("2"),
        order_type=OrderType.MARKET,
        created_at=created,
        valid_until=created + timedelta(minutes=valid_for_minutes),
        source=OrderSource.STRATEGY,
        provenance={"dataset_version": "ds-v1", "config_snapshot_id": "cfg-v1"},
    )


def _approved_order(*, intent_id: str = "intent-001", valid_for_minutes: int = 5) -> ApprovedOrder:
    intent = _intent(intent_id=intent_id, valid_for_minutes=valid_for_minutes)
    limits = _limits()
    runtime_clock = _clock()
    gate = RiskGateV2(
        evaluator=_Evaluator(
            RiskEvaluation.approved(
                approved_qty="2",
                risk_rule_version="risk-policy/v4",
                limits_snapshot_id=limits.snapshot_id,
            )
        ),
        clock=runtime_clock,
        id_generator=DeterministicIdGenerator(
            runtime_clock,
            DeterministicSeedSource(7),
            "phase2-intent-guard-test",
        ),
        audit_sink=_AuditSink(),
        hard_limits=limits,
    )
    result = gate.evaluate_entry(intent)
    assert isinstance(result, ApprovedOrder)
    return result


def test_first_valid_approved_order_is_consumed_once() -> None:
    guard = IntentGuard(clock=_clock())
    order = _approved_order()

    result = guard.consume(order)

    assert result.accepted is True
    assert result.reason is None
    assert result.intent_id == order.intent_id
    assert result.client_order_id == order.client_order_id


def test_same_intent_id_is_rejected_after_first_consumption() -> None:
    guard = IntentGuard(clock=_clock())
    order = _approved_order()

    first = guard.consume(order)
    second = guard.consume(order)

    assert first.accepted is True
    assert second.accepted is False
    assert second.reason is IntentGuardReason.DUPLICATE_INTENT_ID


def test_partial_restart_state_rejects_replayed_client_order_identity() -> None:
    order = _approved_order()
    restored = IntentGuardState(
        consumed_intent_ids=(),
        consumed_client_order_ids=(order.client_order_id,),
    )
    guard = IntentGuard(clock=_clock(), restored_state=restored)

    result = guard.consume(order)

    assert result.accepted is False
    assert result.reason is IntentGuardReason.DUPLICATE_CLIENT_ORDER_ID


def test_expired_approved_order_is_rejected_without_consuming_identity() -> None:
    order = _approved_order(valid_for_minutes=5)
    guard = IntentGuard(clock=_clock(minute=21))

    result = guard.consume(order)

    assert result.accepted is False
    assert result.reason is IntentGuardReason.STALE_INTENT
    assert guard.snapshot() == IntentGuardState((), ())


def test_exported_state_blocks_restart_replay_of_consumed_order() -> None:
    order = _approved_order(intent_id="intent-restart")
    first_guard = IntentGuard(clock=_clock())
    accepted = first_guard.consume(order)
    assert accepted.accepted is True

    restored_guard = IntentGuard(clock=_clock(), restored_state=first_guard.snapshot())
    replay = restored_guard.consume(order)

    assert replay.accepted is False
    assert replay.reason is IntentGuardReason.DUPLICATE_INTENT_ID


def test_snapshot_is_deterministic_and_sorted() -> None:
    guard = IntentGuard(clock=_clock())
    second = _approved_order(intent_id="intent-002")
    first = _approved_order(intent_id="intent-001")

    assert guard.consume(second).accepted is True
    assert guard.consume(first).accepted is True

    snapshot = guard.snapshot()
    assert snapshot.consumed_intent_ids == ("intent-001", "intent-002")
    assert snapshot.consumed_client_order_ids == tuple(sorted(snapshot.consumed_client_order_ids))
