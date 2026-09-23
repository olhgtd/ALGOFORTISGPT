from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from engine.core.runtime import DeterministicIdGenerator, DeterministicSeedSource, FixedClock
from engine.orders.contracts_v2 import ApprovedOrder, OrderIntent, OrderSource, RunMode
from engine.orders.model import OrderType
from engine.portfolio.model import InstrumentIdentity
from engine.risk.gate_v2 import RiskEvaluation, RiskGateV2, RiskRejection
from engine.risk.limits import HardLimitError, HardLimitHierarchy, LimitDirection, ResolvedHardLimits


@dataclass
class _Evaluator:
    result: RiskEvaluation
    calls: int = 0

    def evaluate(self, intent: OrderIntent) -> RiskEvaluation:
        self.calls += 1
        return self.result


class _AuditSink:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def write(self, event_type: str, payload: dict[str, object]) -> None:
        self.events.append((event_type, dict(payload)))


def _limits() -> ResolvedHardLimits:
    return HardLimitHierarchy(
        definitions={
            "max_order_qty": LimitDirection.MAXIMUM,
            "max_daily_loss": LimitDirection.MAXIMUM,
            "min_data_quality": LimitDirection.MINIMUM,
        },
        platform={
            "max_order_qty": "10",
            "max_daily_loss": "1000",
            "min_data_quality": "0.80",
        },
        owner={"max_order_qty": "8", "min_data_quality": "0.82"},
        user={"max_order_qty": "6"},
        strategy={"max_order_qty": "5", "max_daily_loss": "700"},
        run={"max_order_qty": "3", "min_data_quality": "0.90"},
    ).resolve()


def _clock() -> FixedClock:
    return FixedClock(datetime(2026, 9, 21, 9, 16, tzinfo=timezone.utc), 123, object())


def _intent(*, side: str = "BUY") -> OrderIntent:
    created = datetime(2026, 9, 21, 9, 15, tzinfo=timezone.utc)
    return OrderIntent(
        intent_id=f"intent-{side.lower()}",
        strategy_id="orb",
        strategy_version="orb/v1",
        run_mode=RunMode.PAPER,
        instrument_ref=InstrumentIdentity(
            "NSE",
            "NIFTY26SEP22000CE",
            "options",
            underlying="NIFTY",
            expiry=date(2026, 9, 24),
            strike="22000",
            option_type="CE",
        ),
        side=side,
        qty=Decimal("2"),
        order_type=OrderType.MARKET,
        created_at=created,
        valid_until=created + timedelta(minutes=5),
        source=OrderSource.STRATEGY,
        provenance={"dataset_version": "ds-v1", "config_snapshot_id": "cfg-v1"},
    )


def _gate(evaluator: _Evaluator, audit: _AuditSink, limits: ResolvedHardLimits) -> RiskGateV2:
    clock = _clock()
    return RiskGateV2(
        evaluator=evaluator,
        clock=clock,
        id_generator=DeterministicIdGenerator(clock, DeterministicSeedSource(9), "phase2-limits"),
        audit_sink=audit,
        hard_limits=limits,
    )


def test_hierarchy_resolves_most_restrictive_values_and_sources() -> None:
    resolved = _limits()

    assert resolved.values["max_order_qty"] == Decimal("3")
    assert resolved.sources["max_order_qty"] == "run"
    assert resolved.values["max_daily_loss"] == Decimal("700")
    assert resolved.sources["max_daily_loss"] == "strategy"
    assert resolved.values["min_data_quality"] == Decimal("0.90")
    assert resolved.sources["min_data_quality"] == "run"
    assert resolved.snapshot_id.startswith("limits_")


def test_lower_layer_cannot_widen_maximum_limit() -> None:
    with pytest.raises(HardLimitError, match="owner.*max_order_qty"):
        HardLimitHierarchy(
            definitions={"max_order_qty": LimitDirection.MAXIMUM},
            platform={"max_order_qty": "10"},
            owner={"max_order_qty": "11"},
        ).resolve()


def test_lower_layer_cannot_widen_minimum_limit() -> None:
    with pytest.raises(HardLimitError, match="user.*min_data_quality"):
        HardLimitHierarchy(
            definitions={"min_data_quality": LimitDirection.MINIMUM},
            platform={"min_data_quality": "0.80"},
            owner={"min_data_quality": "0.85"},
            user={"min_data_quality": "0.70"},
        ).resolve()


def test_missing_platform_authority_and_float_values_fail_closed() -> None:
    with pytest.raises(HardLimitError, match="platform"):
        HardLimitHierarchy(
            definitions={"max_order_qty": LimitDirection.MAXIMUM},
            platform={},
            owner={"max_order_qty": "5"},
        ).resolve()

    with pytest.raises(HardLimitError, match="float"):
        HardLimitHierarchy(
            definitions={"max_order_qty": LimitDirection.MAXIMUM},
            platform={"max_order_qty": 10.0},
        ).resolve()


def test_snapshot_identity_is_mapping_order_independent() -> None:
    first = HardLimitHierarchy(
        definitions={"max_order_qty": LimitDirection.MAXIMUM, "max_daily_loss": LimitDirection.MAXIMUM},
        platform={"max_order_qty": "10", "max_daily_loss": "1000"},
        owner={"max_order_qty": "8", "max_daily_loss": "900"},
    ).resolve()
    second = HardLimitHierarchy(
        definitions={"max_daily_loss": LimitDirection.MAXIMUM, "max_order_qty": LimitDirection.MAXIMUM},
        platform={"max_daily_loss": "1000", "max_order_qty": "10"},
        owner={"max_daily_loss": "900", "max_order_qty": "8"},
    ).resolve()

    assert first.snapshot_id == second.snapshot_id
    assert dict(first.values) == dict(second.values)


def test_options_sell_entry_is_blocked_before_risk_evaluation() -> None:
    limits = _limits()
    evaluator = _Evaluator(
        RiskEvaluation.approved(
            approved_qty="2",
            risk_rule_version="risk-policy/v4",
            limits_snapshot_id=limits.snapshot_id,
        )
    )
    audit = _AuditSink()

    result = _gate(evaluator, audit, limits).evaluate_entry(_intent(side="SELL"))

    assert isinstance(result, RiskRejection)
    assert result.reasons == ("options_buy_only",)
    assert evaluator.calls == 0
    assert audit.events[0][0] == "RISK_APPROVAL_REJECTED"


def test_gate_requires_risk_evidence_from_exact_resolved_limit_snapshot() -> None:
    limits = _limits()
    evaluator = _Evaluator(
        RiskEvaluation.approved(
            approved_qty="2",
            risk_rule_version="risk-policy/v4",
            limits_snapshot_id="limits_wrong",
        )
    )
    audit = _AuditSink()

    result = _gate(evaluator, audit, limits).evaluate_entry(_intent())

    assert isinstance(result, RiskRejection)
    assert result.reasons == ("limits_snapshot_mismatch",)
    assert audit.events[0][0] == "RISK_APPROVAL_REJECTED"


def test_matching_limit_snapshot_allows_capability_mint() -> None:
    limits = _limits()
    evaluator = _Evaluator(
        RiskEvaluation.approved(
            approved_qty="2",
            risk_rule_version="risk-policy/v4",
            limits_snapshot_id=limits.snapshot_id,
        )
    )

    result = _gate(evaluator, _AuditSink(), limits).evaluate_entry(_intent())

    assert isinstance(result, ApprovedOrder)
