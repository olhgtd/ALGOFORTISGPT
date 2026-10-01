from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from engine.orders.contracts_v2 import ApprovedOrder, OrderIntent, OrderSource, RunMode
from engine.orders.model import OrderType
from engine.portfolio.candidate_arbitration_v2 import (
    BrokerAccountKey,
    CandidateReservationRequest,
    PortfolioCandidateArbitrator,
)
from engine.portfolio.model import AccountSnapshot, InstrumentIdentity
from engine.portfolio.v2.contracts import PortfolioBudgetPolicy, PortfolioRiskContext
from engine.portfolio.v2.reservations import CapitalReservationBook
from engine.risk.gate_v2 import RiskEvaluation, RiskGateV2
from engine.risk.limits import ResolvedHardLimits
from engine.risk.portfolio_admission_v2 import PortfolioAdmissionCoordinator

NOW = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
INSTRUMENT = InstrumentIdentity("nse", "NIFTY", "index")


class _Clock:
    def now_utc(self):
        return NOW


class _Ids:
    def new_id(self, kind: str) -> str:
        return f"{kind}_handoff_test"


class _Audit:
    def write(self, event_type: str, payload: dict[str, object]) -> None:
        return None


class _Evaluator:
    def evaluate(self, intent: OrderIntent) -> RiskEvaluation:
        return RiskEvaluation.approved(
            approved_qty=intent.qty,
            risk_rule_version="risk-v1",
            limits_snapshot_id="limits-handoff",
        )


class _ContextProvider:
    def context_for(self, intent: OrderIntent) -> PortfolioRiskContext:
        account = AccountSnapshot(
            account_id="account-1",
            currency="INR",
            starting_capital=Decimal("1000"),
            cash=Decimal("1000"),
            realized_pnl=Decimal("0"),
            positions={},
            aggregate_exposure={},
            as_of_timestamp=NOW,
            monetary_quantum=Decimal("0.01"),
        )
        return PortfolioRiskContext(
            account,
            Decimal("10"),
            Decimal("1"),
            Decimal("10"),
            Decimal("100"),
            "candidate:candidate-1",
            NOW,
        )


def test_pre_reserved_candidate_capital_is_adopted_not_reserved_twice_before_riskgate() -> None:
    book = CapitalReservationBook(
        PortfolioBudgetPolicy(
            "budget",
            "1.0.0",
            Decimal("1000"),
            "user-1",
            Decimal("1000"),
            {"strategy-a": Decimal("1000")},
        )
    )
    pool = BrokerAccountKey("broker-a", "account-1")
    arbitrator = PortfolioCandidateArbitrator(
        {pool: book},
        aggregate_capital_limit=Decimal("1000"),
    )
    reserved = arbitrator.reserve(
        CandidateReservationRequest(
            candidate_id="candidate-1",
            broker_account=pool,
            strategy_id="strategy-a",
            required_capital=Decimal("100"),
            created_at=NOW,
            valid_until=NOW + timedelta(minutes=5),
        )
    )
    assert reserved.accepted is True
    assert book.snapshot().total_reserved == Decimal("100")

    intent = OrderIntent(
        intent_id="intent-handoff",
        strategy_id="strategy-a",
        strategy_version="1",
        run_mode=RunMode.PAPER,
        instrument_ref=INSTRUMENT,
        side="BUY",
        qty=Decimal("10"),
        order_type=OrderType.MARKET,
        created_at=NOW,
        valid_until=NOW + timedelta(minutes=5),
        source=OrderSource.STRATEGY,
        provenance={"candidate_id": "candidate-1"},
    )
    gate = RiskGateV2(
        evaluator=_Evaluator(),
        clock=_Clock(),
        id_generator=_Ids(),
        audit_sink=_Audit(),
        hard_limits=ResolvedHardLimits({}, {}, {}, "limits-handoff"),
    )
    coordinator = PortfolioAdmissionCoordinator(gate, _ContextProvider(), book)
    result = coordinator.evaluate_entry(intent)

    assert isinstance(result, ApprovedOrder)
    assert book.snapshot().total_reserved == Decimal("100")
    assert coordinator.release_terminal("intent-handoff", released_at=NOW + timedelta(seconds=1)) is True
    assert book.snapshot().total_reserved == Decimal("0")
