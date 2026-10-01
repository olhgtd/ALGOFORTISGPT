from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import sqlite3

import pytest

from engine.core.runtime import FixedClock
from engine.live.execution_capacity_v2 import LiveExecutionCapacityBlocked
from engine.live.state_machine_v2 import LiveState, LiveStateMachine
from engine.orders.contracts_v2 import ApprovedOrder, OrderIntent, OrderSource, RunMode
from engine.orders.lifecycle_v2 import OrderExecutionState
from engine.orders.model import OrderType
from engine.persistence.live_execution_schema_v9 import LIVE_EXECUTION_CREATE_TABLES_SQL
from engine.persistence.live_execution_store_v2 import LiveExecutionStoreV2
from engine.portfolio.model import InstrumentIdentity
from engine.risk.gate_v2 import RiskEvaluation, RiskGateV2
from engine.risk.limits import HardLimitHierarchy, LimitDirection

try:
    from engine.live.execution_coordinator_v2 import (
        LiveBrokerAcknowledgementV2,
        LiveExecutionAuditError,
        LiveExecutionCoordinatorError,
        LiveExecutionCoordinatorV2,
        LiveExecutionInDoubt,
    )
    from engine.live.mutation_release_gate_v2 import (
        ClosedLiveMutationReleaseGate,
        LiveMutationBlocked,
    )
except ModuleNotFoundError as exc:
    pytest.fail(f"Live execution coordinator is not implemented: {exc}", pytrace=False)


class _Ids:
    def __init__(self) -> None:
        self._n = 0

    def new_id(self, kind: str) -> str:
        self._n += 1
        return f"{kind}-{self._n}"


@dataclass
class _Evaluator:
    limits_snapshot_id: str

    def evaluate(self, intent: OrderIntent) -> RiskEvaluation:
        return RiskEvaluation.approved(
            approved_qty=intent.qty,
            risk_rule_version="risk/v1",
            limits_snapshot_id=self.limits_snapshot_id,
        )


class _Audit:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[tuple[str, dict[str, object]]] = []

    def write(self, event_type: str, payload: dict[str, object]) -> None:
        if self.fail:
            raise OSError("audit unavailable")
        self.events.append((event_type, dict(payload)))


class _Clock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def now_utc(self) -> datetime:
        return self.current


class _OpenGate:
    def authorize(self, *, order: ApprovedOrder, live_state: LiveState) -> str:
        assert live_state is LiveState.ACTIVE
        return "test-only-release-ref"


class _CapacityGate:
    def __init__(self, *, deny: bool = False) -> None:
        self.deny = deny
        self.reserved: list[str] = []
        self.released: list[tuple[str, str]] = []

    def reserve(self, order: ApprovedOrder, *, now: datetime) -> str:
        if self.deny:
            raise LiveExecutionCapacityBlocked("insufficient unreserved account cash")
        self.reserved.append(order.client_order_id)
        return "funds-ref"

    def release(self, client_order_id: str, *, now: datetime, reason: str) -> bool:
        self.released.append((client_order_id, reason))
        return True


class _Port:
    def __init__(self, journal: LiveExecutionStoreV2, *, fail: bool = False, bad_ack: bool = False) -> None:
        self.journal = journal
        self.fail = fail
        self.bad_ack = bad_ack
        self.calls: list[str] = []
        self.states_seen: list[OrderExecutionState] = []
        self.adapter_id = "fake-live-port"

    def place(self, order: ApprovedOrder):
        self.calls.append(order.client_order_id)
        record = self.journal.get(order.client_order_id)
        assert record is not None
        self.states_seen.append(record.lifecycle_state)
        if self.fail:
            raise TimeoutError("ack timeout")
        if self.bad_ack:
            return object()
        return LiveBrokerAcknowledgementV2(
            client_order_id=order.client_order_id,
            broker_order_identity=f"broker-{len(self.calls)}",
        )


def _database(path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    try:
        for statement in LIVE_EXECUTION_CREATE_TABLES_SQL:
            connection.execute(statement)
        connection.execute("PRAGMA user_version = 9")
        connection.commit()
    finally:
        connection.close()


def _approved(
    *,
    underlying: str = "NIFTY",
    intent_id: str = "intent-nifty",
    run_mode: RunMode = RunMode.LIVE,
    valid_minutes: int = 5,
) -> ApprovedOrder:
    created = datetime(2026, 9, 30, 9, 15, tzinfo=timezone.utc)
    identity = InstrumentIdentity(
        "NSE",
        f"{underlying}26OCT22000CE",
        "options",
        underlying=underlying,
        expiry=date(2026, 10, 29),
        strike="22000",
        option_type="CE",
    )
    intent = OrderIntent(
        intent_id=intent_id,
        strategy_id="orb",
        strategy_version="orb/v1",
        run_mode=run_mode,
        instrument_ref=identity,
        side="BUY",
        qty=Decimal("1"),
        order_type=OrderType.MARKET,
        created_at=created,
        valid_until=created + timedelta(minutes=valid_minutes),
        source=OrderSource.STRATEGY,
        provenance={"market_sequence": 1},
    )
    limits = HardLimitHierarchy(
        definitions={"max_order_qty": LimitDirection.MAXIMUM},
        platform={"max_order_qty": "10"},
    ).resolve()
    gate = RiskGateV2(
        evaluator=_Evaluator(limits.snapshot_id),
        clock=FixedClock(created, 1, object()),
        id_generator=_Ids(),
        audit_sink=_Audit(),
        hard_limits=limits,
    )
    result = gate.evaluate_entry(intent)
    assert isinstance(result, ApprovedOrder)
    return result


def _coordinator(tmp_path, *, release_gate=None, capacity_gate=None, audit=None, state=LiveState.ACTIVE, port_fail=False, bad_ack=False):
    database = tmp_path / "live.sqlite3"
    _database(database)
    journal = LiveExecutionStoreV2(database)
    port = _Port(journal, fail=port_fail, bad_ack=bad_ack)
    capacity = capacity_gate or _CapacityGate()
    audit_sink = audit or _Audit()
    clock = _Clock(datetime(2026, 9, 30, 9, 16, tzinfo=timezone.utc))
    machine = LiveStateMachine(audit_sink=_Audit(), initial_state=state)
    coordinator = LiveExecutionCoordinatorV2(
        broker_port=port,
        journal=journal,
        release_gate=release_gate or _OpenGate(),
        capacity_gate=capacity,
        state_machine=machine,
        audit_sink=audit_sink,
        clock=clock,
    )
    return coordinator, journal, port, capacity, audit_sink, clock


def test_closed_release_gate_blocks_before_capacity_journal_or_port(tmp_path) -> None:
    coordinator, journal, port, capacity, _, _ = _coordinator(tmp_path, release_gate=ClosedLiveMutationReleaseGate())
    order = _approved()
    with pytest.raises(LiveMutationBlocked, match="closed"):
        coordinator.submit(order)
    assert port.calls == []
    assert capacity.reserved == []
    assert journal.get(order.client_order_id) is None


def test_wrong_mode_and_non_active_state_fail_before_port(tmp_path) -> None:
    coordinator, _, port, _, _, _ = _coordinator(tmp_path)
    paper = _approved(run_mode=RunMode.PAPER, intent_id="intent-paper")
    with pytest.raises(LiveExecutionCoordinatorError, match="RunMode.LIVE"):
        coordinator.submit(paper)
    assert port.calls == []

    coordinator2, _, port2, _, _, _ = _coordinator(tmp_path / "second", state=LiveState.READY)
    live = _approved()
    with pytest.raises(LiveExecutionCoordinatorError, match="ACTIVE"):
        coordinator2.submit(live)
    assert port2.calls == []


def test_expired_approval_fails_before_release_or_port(tmp_path) -> None:
    coordinator, _, port, capacity, _, clock = _coordinator(tmp_path)
    order = _approved(valid_minutes=1)
    clock.current = datetime(2026, 9, 30, 9, 17, tzinfo=timezone.utc)
    with pytest.raises(LiveExecutionCoordinatorError, match="expired"):
        coordinator.submit(order)
    assert port.calls == []
    assert capacity.reserved == []


def test_capacity_denial_blocks_before_journal_and_port(tmp_path) -> None:
    capacity = _CapacityGate(deny=True)
    coordinator, journal, port, _, _, _ = _coordinator(tmp_path, capacity_gate=capacity)
    order = _approved()
    with pytest.raises(LiveExecutionCapacityBlocked):
        coordinator.submit(order)
    assert port.calls == []
    assert journal.get(order.client_order_id) is None


def test_success_persists_sent_unacked_before_call_and_ack_mapping_after(tmp_path) -> None:
    coordinator, journal, port, capacity, audit, _ = _coordinator(tmp_path)
    order = _approved()
    result = coordinator.submit(order)
    assert isinstance(result, LiveBrokerAcknowledgementV2)
    assert port.states_seen == [OrderExecutionState.SENT_UNACKED]
    record = journal.get(order.client_order_id)
    assert record is not None
    assert record.lifecycle_state is OrderExecutionState.ACKED
    assert record.broker_order_identity == result.broker_order_identity
    assert record.is_uncertain is False
    assert capacity.reserved == [order.client_order_id]
    assert capacity.released == []
    assert [event for event, _ in audit.events] == ["LIVE_SUBMISSION_PREPARED", "LIVE_SUBMISSION_ACKED"]


def test_send_exception_becomes_in_doubt_and_is_not_released_or_retried(tmp_path) -> None:
    coordinator, journal, port, capacity, _, _ = _coordinator(tmp_path, port_fail=True)
    order = _approved()
    with pytest.raises(LiveExecutionInDoubt):
        coordinator.submit(order)
    record = journal.get(order.client_order_id)
    assert record is not None
    assert record.lifecycle_state is OrderExecutionState.IN_DOUBT
    assert record.is_uncertain is True
    assert capacity.released == []
    assert len(port.calls) == 1
    with pytest.raises(LiveExecutionCoordinatorError, match="duplicate"):
        coordinator.submit(order)
    assert len(port.calls) == 1


def test_invalid_ack_after_send_becomes_in_doubt(tmp_path) -> None:
    coordinator, journal, port, capacity, _, _ = _coordinator(tmp_path, bad_ack=True)
    order = _approved()
    with pytest.raises(LiveExecutionInDoubt, match="acknowledgement"):
        coordinator.submit(order)
    assert journal.get(order.client_order_id).lifecycle_state is OrderExecutionState.IN_DOUBT
    assert capacity.released == []
    assert len(port.calls) == 1


def test_audit_failure_before_send_blocks_port_and_releases_capacity(tmp_path) -> None:
    audit = _Audit(fail=True)
    coordinator, journal, port, capacity, _, _ = _coordinator(tmp_path, audit=audit)
    order = _approved()
    with pytest.raises(LiveExecutionAuditError):
        coordinator.submit(order)
    assert port.calls == []
    assert capacity.released == [(order.client_order_id, "pre_submit_audit_failed")]
    record = journal.get(order.client_order_id)
    assert record is not None
    assert record.lifecycle_state is OrderExecutionState.SUBMITTING


def test_separate_instruments_keep_separate_order_lifecycles(tmp_path) -> None:
    coordinator, journal, port, _, _, _ = _coordinator(tmp_path)
    nifty = _approved(underlying="NIFTY", intent_id="intent-nifty")
    banknifty = _approved(underlying="BANKNIFTY", intent_id="intent-banknifty")
    coordinator.submit(nifty)
    coordinator.submit(banknifty)
    assert nifty.client_order_id != banknifty.client_order_id
    assert journal.get(nifty.client_order_id).broker_order_identity == "broker-1"
    assert journal.get(banknifty.client_order_id).broker_order_identity == "broker-2"
    assert len(port.calls) == 2
