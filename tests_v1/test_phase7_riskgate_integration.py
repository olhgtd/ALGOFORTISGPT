from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from engine.orders.contracts_v2 import ApprovedOrder, OrderIntent, OrderSource, RunMode
from engine.orders.model import OrderType
from engine.portfolio.model import AccountSnapshot, InstrumentIdentity
from engine.portfolio.v2.circuit_breaker import (
    PortfolioCircuitBreaker,
    PortfolioCircuitBreakerPolicy,
    PortfolioRiskMetrics,
)
from engine.portfolio.v2.contracts import (
    PortfolioBudgetPolicy,
    PortfolioExposurePolicy,
    PortfolioRiskContext,
)
from engine.portfolio.v2.reservations import CapitalReservationBook
from engine.risk.event_day_policy_v2 import EventRiskPolicy
from engine.risk.gate_v2 import RiskApprovalError, RiskEvaluation, RiskGateV2, RiskRejection
from engine.risk.limits import ResolvedHardLimits
from engine.risk.portfolio_v2 import PortfolioAwareRiskEvaluator

_NOW = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
_INSTRUMENT = InstrumentIdentity("nse", "NIFTY", "index")


class _Clock:
    def now_utc(self):
        return _NOW


class _Ids:
    def new_id(self, kind: str) -> str:
        return f"{kind}_phase7_test"


class _Audit:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[tuple[str, dict[str, object]]] = []

    def write(self, event_type: str, payload: dict[str, object]) -> None:
        self.events.append((event_type, payload))
        if self.fail:
            raise OSError("audit unavailable")


class _ContextProvider:
    def __init__(self, context: PortfolioRiskContext) -> None:
        self.context = context

    def context_for(self, intent: OrderIntent) -> PortfolioRiskContext:
        return self.context


class _BaseEvaluator:
    def __init__(self, result: RiskEvaluation | None = None, *, fail: bool = False) -> None:
        self.result = result
        self.fail = fail

    def evaluate(self, intent: OrderIntent) -> RiskEvaluation:
        if self.fail:
            raise RuntimeError("base evaluator failed")
        assert self.result is not None
        return self.result


def _intent(*, qty: str = "50") -> OrderIntent:
    return OrderIntent(
        intent_id=f"intent-{qty}",
        strategy_id="s1",
        strategy_version="1",
        run_mode=RunMode.PAPER,
        instrument_ref=_INSTRUMENT,
        side="BUY",
        qty=Decimal(qty),
        order_type=OrderType.MARKET,
        created_at=_NOW,
        valid_until=_NOW + timedelta(hours=1),
        source=OrderSource.STRATEGY,
        provenance={"test": "phase7"},
    )


def _account() -> AccountSnapshot:
    return AccountSnapshot(
        account_id="acct",
        currency="INR",
        starting_capital=Decimal("10000"),
        cash=Decimal("10000"),
        realized_pnl=Decimal("0"),
        positions={},
        aggregate_exposure={},
        as_of_timestamp=_NOW,
        monetary_quantum=Decimal("0.01"),
    )


def _context() -> PortfolioRiskContext:
    return PortfolioRiskContext(
        _account(),
        Decimal("10"),
        Decimal("1"),
        Decimal("100"),
        Decimal("100"),
        "reservation-intent-50",
        _NOW,
    )


def _book() -> CapitalReservationBook:
    return CapitalReservationBook(
        PortfolioBudgetPolicy(
            "budget",
            "v1",
            Decimal("1000"),
            "u1",
            Decimal("1000"),
            {"s1": Decimal("1000")},
        )
    )


def _limits() -> ResolvedHardLimits:
    return ResolvedHardLimits({}, {}, {}, "limits_phase7_test")


def _approved_eval(*, qty: str = "50") -> RiskEvaluation:
    return RiskEvaluation.approved(
        approved_qty=Decimal(qty),
        risk_rule_version="risk-v1",
        limits_snapshot_id="limits_phase7_test",
    )


def _gate(evaluator, *, entry_policy=None) -> RiskGateV2:
    return RiskGateV2(
        evaluator=evaluator,
        clock=_Clock(),
        id_generator=_Ids(),
        audit_sink=_Audit(),
        hard_limits=_limits(),
        entry_policy=entry_policy,
    )


def _portfolio_evaluator(
    book: CapitalReservationBook,
    provider: _ContextProvider,
    *,
    total_exposure_cap: str = "2000",
):
    return PortfolioAwareRiskEvaluator(
        _BaseEvaluator(_approved_eval()),
        provider,
        book,
        PortfolioExposurePolicy(
            "exposure",
            "v1",
            Decimal(total_exposure_cap),
            Decimal("2000"),
            {"s1": Decimal("2000")},
        ),
        EventRiskPolicy("events", "v1", ()),
    )


def test_required_capital_is_reserved_before_gate_and_approval_retains_until_terminal() -> None:
    from engine.risk.portfolio_admission_v2 import PortfolioAdmissionCoordinator

    book = _book()
    provider = _ContextProvider(_context())
    gate = _gate(_portfolio_evaluator(book, provider))
    coordinator = PortfolioAdmissionCoordinator(gate, provider, book)

    result = coordinator.evaluate_entry(_intent())
    assert isinstance(result, ApprovedOrder)
    assert book.get_active("reservation-intent-50") is not None
    assert coordinator.release_terminal("intent-50", released_at=_NOW) is True
    assert book.get_active("reservation-intent-50") is None


def test_gate_rejection_and_exception_release_reservation() -> None:
    from engine.risk.portfolio_admission_v2 import PortfolioAdmissionCoordinator

    book = _book()
    provider = _ContextProvider(_context())
    rejected_eval = RiskEvaluation.rejected(
        "BASE_REJECT",
        risk_rule_version="risk-v1",
        limits_snapshot_id="limits_phase7_test",
    )
    rejection = PortfolioAdmissionCoordinator(
        _gate(_BaseEvaluator(rejected_eval)), provider, book
    ).evaluate_entry(_intent())
    assert isinstance(rejection, RiskRejection)
    assert rejection.reasons == ("BASE_REJECT",)
    assert book.snapshot().total_reserved == Decimal("0")

    failing_book = _book()
    failing = PortfolioAdmissionCoordinator(
        _gate(_BaseEvaluator(fail=True)), provider, failing_book
    )
    with pytest.raises(RiskApprovalError):
        failing.evaluate_entry(_intent())
    assert failing_book.snapshot().total_reserved == Decimal("0")


def test_duplicate_active_intent_does_not_gain_second_admission() -> None:
    from engine.risk.portfolio_admission_v2 import (
        PortfolioAdmissionCoordinator,
        PortfolioAdmissionRejection,
    )

    book = _book()
    provider = _ContextProvider(_context())
    coordinator = PortfolioAdmissionCoordinator(
        _gate(_portfolio_evaluator(book, provider)), provider, book
    )
    assert isinstance(coordinator.evaluate_entry(_intent()), ApprovedOrder)
    second = coordinator.evaluate_entry(_intent())
    assert isinstance(second, PortfolioAdmissionRejection)
    assert second.reason == "DUPLICATE_ACTIVE_ADMISSION"
    assert book.snapshot().total_reserved == Decimal("100")


def test_circuit_breaker_blocks_entry_through_existing_riskgate() -> None:
    from engine.risk.portfolio_admission_v2 import PortfolioAdmissionCoordinator

    circuit = PortfolioCircuitBreaker(
        PortfolioCircuitBreakerPolicy(
            "circuit", "v1", Decimal("100"), Decimal("50")
        ),
        audit_sink=_Audit(),
    )
    circuit.observe(PortfolioRiskMetrics(Decimal("-100"), Decimal("0"), _NOW))

    book = _book()
    provider = _ContextProvider(_context())
    result = PortfolioAdmissionCoordinator(
        _gate(_BaseEvaluator(_approved_eval()), entry_policy=circuit), provider, book
    ).evaluate_entry(_intent())
    assert isinstance(result, RiskRejection)
    assert result.reasons == ("entries_halted",)
    assert book.snapshot().total_reserved == Decimal("0")


def test_portfolio_exposure_breach_reaches_existing_riskgate_as_normal_rejection() -> None:
    from engine.risk.portfolio_admission_v2 import PortfolioAdmissionCoordinator

    book = _book()
    provider = _ContextProvider(_context())
    result = PortfolioAdmissionCoordinator(
        _gate(_portfolio_evaluator(book, provider, total_exposure_cap="400")),
        provider,
        book,
    ).evaluate_entry(_intent())
    assert isinstance(result, RiskRejection)
    assert result.reasons == ("TOTAL_EXPOSURE_EXCEEDED",)
    assert book.snapshot().total_reserved == Decimal("0")
