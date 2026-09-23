from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from engine.core.runtime import DeterministicIdGenerator, DeterministicSeedSource, FixedClock
from engine.live.state_machine_v2 import LiveState, LiveStateMachine
from engine.orders.contracts_v2 import OrderIntent, OrderSource, RunMode
from engine.orders.model import OrderType
from engine.portfolio.model import InstrumentIdentity
from engine.risk.gate_v2 import RiskEvaluation, RiskGateV2, RiskRejection
from engine.risk.kill_switch import (
    CancelPendingScope,
    EmergencyStopController,
    EntryHaltLatch,
    KillSwitchAction,
    KillSwitchError,
    KillSwitchScope,
)
from engine.risk.limits import HardLimitHierarchy, LimitDirection


class _AuditSink:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[tuple[str, dict[str, object]]] = []

    def write(self, event_type: str, payload: dict[str, object]) -> None:
        if self.fail:
            raise OSError("audit unavailable")
        self.events.append((event_type, dict(payload)))


@dataclass
class _Evaluator:
    result: RiskEvaluation
    calls: int = 0

    def evaluate(self, intent: OrderIntent) -> RiskEvaluation:
        self.calls += 1
        return self.result


def _clock() -> FixedClock:
    return FixedClock(
        datetime(2026, 9, 21, 9, 16, tzinfo=timezone.utc),
        100,
        object(),
    )


def _limits():
    return HardLimitHierarchy(
        definitions={"max_order_qty": LimitDirection.MAXIMUM},
        platform={"max_order_qty": "10"},
    ).resolve()


def _intent() -> OrderIntent:
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
        intent_id="intent-kill-switch-001",
        strategy_id="orb",
        strategy_version="orb/v1",
        run_mode=RunMode.PAPER,
        instrument_ref=instrument,
        side="BUY",
        qty=Decimal("2"),
        order_type=OrderType.MARKET,
        created_at=created,
        valid_until=created + timedelta(minutes=5),
        source=OrderSource.STRATEGY,
        provenance={"dataset_version": "ds-v1", "config_snapshot_id": "cfg-v1"},
    )


def test_standard_emergency_stop_halts_entries_and_cancels_only_pending_entries() -> None:
    audit = _AuditSink()
    machine = LiveStateMachine(audit_sink=audit, initial_state=LiveState.READY)
    entry_halt = EntryHaltLatch()
    controller = EmergencyStopController(
        audit_sink=audit,
        state_machine=machine,
        entry_halt=entry_halt,
    )

    evidence = controller.emergency_stop(
        scope=KillSwitchScope.PLATFORM,
        reason="manual_emergency_stop",
    )

    assert machine.state is LiveState.EMERGENCY_STOP
    assert entry_halt.halted is True
    assert evidence.actions == (
        KillSwitchAction.HALT_ENTRIES,
        KillSwitchAction.CANCEL_PENDING,
    )
    assert evidence.cancel_pending_scope is CancelPendingScope.ENTRY_ORDERS_ONLY
    assert evidence.protective_exits_active is True
    assert evidence.reconciliation_active is True
    assert KillSwitchAction.FLATTEN_ALL not in evidence.actions


def test_emergency_stop_is_audited_before_mutating_state_or_entry_latch() -> None:
    audit = _AuditSink(fail=True)
    machine = LiveStateMachine(audit_sink=audit, initial_state=LiveState.READY)
    entry_halt = EntryHaltLatch()
    controller = EmergencyStopController(
        audit_sink=audit,
        state_machine=machine,
        entry_halt=entry_halt,
    )

    with pytest.raises(KillSwitchError, match="audit"):
        controller.emergency_stop(
            scope=KillSwitchScope.PLATFORM,
            reason="manual_emergency_stop",
        )

    assert machine.state is LiveState.READY
    assert entry_halt.halted is False


def test_reconciliation_mismatch_halts_and_alerts_without_flattening() -> None:
    audit = _AuditSink()
    machine = LiveStateMachine(audit_sink=audit, initial_state=LiveState.READY)
    entry_halt = EntryHaltLatch()
    controller = EmergencyStopController(
        audit_sink=audit,
        state_machine=machine,
        entry_halt=entry_halt,
    )

    evidence = controller.reconciliation_mismatch(
        scope=KillSwitchScope.USER,
        reason="broker_truth_mismatch",
    )

    assert entry_halt.halted is True
    assert evidence.actions == (KillSwitchAction.HALT_ENTRIES,)
    assert evidence.alert_required is True
    assert evidence.recovery_required is True
    assert evidence.reconciliation_active is True
    assert KillSwitchAction.FLATTEN_ALL not in evidence.actions


def test_central_risk_gate_rejects_new_entry_after_halt_without_calling_evaluator() -> None:
    audit = _AuditSink()
    entry_halt = EntryHaltLatch()
    limits = _limits()
    evaluator = _Evaluator(
        RiskEvaluation.approved(
            approved_qty="2",
            risk_rule_version="risk-policy/v4",
            limits_snapshot_id=limits.snapshot_id,
        )
    )
    clock = _clock()
    gate = RiskGateV2(
        evaluator=evaluator,
        clock=clock,
        id_generator=DeterministicIdGenerator(
            clock,
            DeterministicSeedSource(7),
            "phase2-kill-switch-test",
        ),
        audit_sink=audit,
        hard_limits=limits,
        entry_policy=entry_halt,
    )
    machine = LiveStateMachine(audit_sink=audit, initial_state=LiveState.READY)
    controller = EmergencyStopController(
        audit_sink=audit,
        state_machine=machine,
        entry_halt=entry_halt,
    )
    controller.emergency_stop(
        scope=KillSwitchScope.PLATFORM,
        reason="manual_emergency_stop",
    )

    result = gate.evaluate_entry(_intent())

    assert isinstance(result, RiskRejection)
    assert result.reasons == ("entries_halted",)
    assert evaluator.calls == 0


def test_flatten_all_exists_as_distinct_domain_action_but_is_never_implicit() -> None:
    assert KillSwitchAction.FLATTEN_ALL.value == "FLATTEN_ALL"
    assert KillSwitchAction.FLATTEN_ALL is not KillSwitchAction.HALT_ENTRIES
    assert KillSwitchAction.FLATTEN_ALL is not KillSwitchAction.CANCEL_PENDING
