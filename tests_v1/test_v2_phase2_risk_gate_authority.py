from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from engine.core.runtime import DeterministicIdGenerator, DeterministicSeedSource, FixedClock
from engine.orders.model import OrderRequest, OrderType, TimeInForce
from engine.orchestration.signal_intake import SignalIntent
from engine.risk.approval import ApprovedOrder, RiskApprovalError, RiskGateV2, RiskRejection
from engine.risk.risk_manager import RiskDay, RiskGateResult, RiskGateState, RiskOutcome


@dataclass
class _Evaluator:
    result: RiskGateResult
    calls: int = 0

    def evaluate(self, order: OrderRequest) -> RiskGateResult:
        assert isinstance(order, OrderRequest)
        self.calls += 1
        return self.result


class _AuditSink:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[tuple[str, dict[str, object]]] = []

    def write(self, event_type: str, payload: dict[str, object]) -> None:
        if self.fail:
            raise RuntimeError("audit unavailable")
        self.events.append((event_type, dict(payload)))


def _order(*, quantity: str = "2") -> OrderRequest:
    intent = SignalIntent(
        action="BUY",
        confidence=0.9,
        symbol="nifty",
        timeframe="5m",
        originating_timestamp=datetime(2026, 9, 21, 9, 15, tzinfo=timezone.utc),
        strategy_id="orb",
        strategy_version="orb/v1",
        metadata={},
    )
    return OrderRequest.from_intent(
        intent,
        OrderType.MARKET,
        Decimal(quantity),
        TimeInForce.DAY,
    )


def _state() -> RiskGateState:
    return RiskGateState(
        RiskDay("NSE_EQ", date(2026, 9, 21)),
        Decimal("100000"),
        Decimal("100000"),
        0,
    )


def _approved_result(*, quantity: str = "2") -> RiskGateResult:
    return RiskGateResult(
        RiskOutcome.APPROVED,
        None,
        _state(),
        Decimal(quantity),
        Decimal("500"),
    )


def _rejected_result(reason: str = "daily_loss_limit") -> RiskGateResult:
    return RiskGateResult(RiskOutcome.REJECTED, reason, _state())


def _ids() -> DeterministicIdGenerator:
    clock = FixedClock(
        datetime(2026, 9, 21, 9, 15, tzinfo=timezone.utc),
        123,
        object(),
    )
    return DeterministicIdGenerator(clock, DeterministicSeedSource(7), "phase2-test")


def test_approved_order_cannot_be_constructed_outside_risk_gate() -> None:
    with pytest.raises(TypeError, match="RiskGateV2"):
        ApprovedOrder(
            order=_order(),
            approval_id="forged",
            intent_id="forged-intent",
            risk_rule_version="risk-policy/v4",
            approved_quantity=Decimal("2"),
        )


def test_gate_mints_capability_only_after_approved_risk_and_audit() -> None:
    evaluator = _Evaluator(_approved_result())
    audit = _AuditSink()
    gate = RiskGateV2(
        evaluator=evaluator,
        id_generator=_ids(),
        audit_sink=audit,
        risk_rule_version="risk-policy/v4",
    )

    order = _order()
    result = gate.evaluate_entry(order)

    assert isinstance(result, ApprovedOrder)
    assert result.order is order
    assert result.intent_id == order.source_intent.identity
    assert result.risk_rule_version == "risk-policy/v4"
    assert result.approved_quantity == Decimal("2")
    assert result.approval_id.startswith("af2_")
    assert evaluator.calls == 1
    assert len(audit.events) == 1
    event_type, payload = audit.events[0]
    assert event_type == "RISK_APPROVAL_GRANTED"
    assert payload["approval_id"] == result.approval_id
    assert payload["intent_id"] == result.intent_id
    assert payload["risk_rule_version"] == "risk-policy/v4"


def test_rejected_risk_never_mints_approved_order() -> None:
    audit = _AuditSink()
    gate = RiskGateV2(
        evaluator=_Evaluator(_rejected_result()),
        id_generator=_ids(),
        audit_sink=audit,
        risk_rule_version="risk-policy/v4",
    )

    result = gate.evaluate_entry(_order())

    assert isinstance(result, RiskRejection)
    assert result.reason == "daily_loss_limit"
    assert audit.events == []


def test_gate_fails_closed_when_risk_quantity_differs_from_order_quantity() -> None:
    audit = _AuditSink()
    gate = RiskGateV2(
        evaluator=_Evaluator(_approved_result(quantity="1")),
        id_generator=_ids(),
        audit_sink=audit,
        risk_rule_version="risk-policy/v4",
    )

    result = gate.evaluate_entry(_order(quantity="2"))

    assert isinstance(result, RiskRejection)
    assert result.reason == "risk_quantity_mismatch"
    assert audit.events == []


def test_audit_failure_blocks_approval_capability() -> None:
    gate = RiskGateV2(
        evaluator=_Evaluator(_approved_result()),
        id_generator=_ids(),
        audit_sink=_AuditSink(fail=True),
        risk_rule_version="risk-policy/v4",
    )

    with pytest.raises(RiskApprovalError, match="audit"):
        gate.evaluate_entry(_order())


def test_fixed_runtime_replays_same_approval_identity() -> None:
    order_a = _order()
    order_b = _order()
    gate_a = RiskGateV2(
        evaluator=_Evaluator(_approved_result()),
        id_generator=_ids(),
        audit_sink=_AuditSink(),
        risk_rule_version="risk-policy/v4",
    )
    gate_b = RiskGateV2(
        evaluator=_Evaluator(_approved_result()),
        id_generator=_ids(),
        audit_sink=_AuditSink(),
        risk_rule_version="risk-policy/v4",
    )

    approved_a = gate_a.evaluate_entry(order_a)
    approved_b = gate_b.evaluate_entry(order_b)

    assert isinstance(approved_a, ApprovedOrder)
    assert isinstance(approved_b, ApprovedOrder)
    assert approved_a.approval_id == approved_b.approval_id
    assert approved_a.intent_id == approved_b.intent_id
