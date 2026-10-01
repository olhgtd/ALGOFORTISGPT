from datetime import datetime, timedelta, timezone
from decimal import Decimal

from engine.orders.contracts_v2 import OrderIntent, OrderSource, RiskDecisionKind, RunMode
from engine.orders.model import OrderType
from engine.portfolio.model import AccountSnapshot, InstrumentIdentity
from engine.portfolio.v2.contracts import PortfolioBudgetPolicy, PortfolioExposurePolicy, PortfolioRiskContext
from engine.portfolio.v2.reservations import CapitalReservationBook
from engine.risk.event_day_policy_v2 import EventRiskAction, EventRiskPolicy, EventRiskWindow
from engine.risk.gate_v2 import RiskEvaluation

_NOW = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
_INSTRUMENT = InstrumentIdentity("nse", "NIFTY", "index")


class _BaseEvaluator:
    def __init__(self, result: RiskEvaluation) -> None:
        self.result = result

    def evaluate(self, intent: OrderIntent) -> RiskEvaluation:
        return self.result


class _ContextProvider:
    def __init__(self, context: PortfolioRiskContext | None, *, fail: bool = False) -> None:
        self.context = context
        self.fail = fail
        self.calls = 0

    def context_for(self, intent: OrderIntent) -> PortfolioRiskContext:
        self.calls += 1
        if self.fail:
            raise RuntimeError("context unavailable")
        assert self.context is not None
        return self.context


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


def _context(*, required_capital: str = "100", reservation_id: str = "r1") -> PortfolioRiskContext:
    return PortfolioRiskContext(
        _account(),
        Decimal("10"),
        Decimal("1"),
        Decimal("100"),
        Decimal(required_capital),
        reservation_id,
        _NOW,
    )


def _budget_policy() -> PortfolioBudgetPolicy:
    return PortfolioBudgetPolicy(
        "budget",
        "v1",
        Decimal("1000"),
        "u1",
        Decimal("1000"),
        {"s1": Decimal("1000")},
    )


def _book(*, amount: str | None = "100") -> CapitalReservationBook:
    book = CapitalReservationBook(_budget_policy())
    if amount is not None:
        result = book.reserve(
            reservation_id="r1",
            user_id="u1",
            strategy_id="s1",
            amount=Decimal(amount),
            created_at=_NOW,
        )
        assert result.accepted is True
    return book


def _exposure_policy(*, total: str = "2000") -> PortfolioExposurePolicy:
    return PortfolioExposurePolicy(
        "exposure",
        "v1",
        Decimal(total),
        Decimal("2000"),
        {"s1": Decimal("2000")},
    )


def _empty_event_policy() -> EventRiskPolicy:
    return EventRiskPolicy("events", "v1", ())


def _approved(*, qty: str = "50") -> RiskEvaluation:
    return RiskEvaluation.approved(
        approved_qty=Decimal(qty),
        risk_rule_version="risk-v1",
        limits_snapshot_id="limits-v1",
    )


def _rejected() -> RiskEvaluation:
    return RiskEvaluation.rejected(
        "BASE_REJECT",
        risk_rule_version="risk-v1",
        limits_snapshot_id="limits-v1",
    )


def _evaluator(
    *,
    base: _BaseEvaluator | None = None,
    provider: _ContextProvider | None = None,
    book: CapitalReservationBook | None = None,
    exposure_policy: PortfolioExposurePolicy | None = None,
    event_policy: EventRiskPolicy | None = None,
):
    from engine.risk.portfolio_v2 import PortfolioAwareRiskEvaluator

    return PortfolioAwareRiskEvaluator(
        base or _BaseEvaluator(_approved()),
        provider or _ContextProvider(_context()),
        book or _book(),
        exposure_policy or _exposure_policy(),
        _empty_event_policy() if event_policy is None else event_policy,
    )


def test_base_rejection_is_preserved_without_portfolio_override() -> None:
    provider = _ContextProvider(None, fail=True)
    base = _BaseEvaluator(_rejected())
    result = _evaluator(base=base, provider=provider).evaluate(_intent())
    assert result is base.result
    assert provider.calls == 0


def test_missing_context_reservation_or_insufficient_reservation_rejects() -> None:
    missing_context = _evaluator(provider=_ContextProvider(None, fail=True)).evaluate(_intent())
    assert missing_context.decision is RiskDecisionKind.REJECTED
    assert missing_context.reasons == ("PORTFOLIO_CONTEXT_UNAVAILABLE",)

    missing_reservation = _evaluator(book=_book(amount=None)).evaluate(_intent())
    assert missing_reservation.reasons == ("CAPITAL_RESERVATION_UNAVAILABLE",)

    insufficient = _evaluator(book=_book(amount="99")).evaluate(_intent())
    assert insufficient.reasons == ("CAPITAL_RESERVATION_INSUFFICIENT",)


def test_exposure_breach_rejects_with_existing_risk_evidence_authority() -> None:
    result = _evaluator(exposure_policy=_exposure_policy(total="400")).evaluate(_intent())
    assert result.decision is RiskDecisionKind.REJECTED
    assert result.reasons == ("TOTAL_EXPOSURE_EXCEEDED",)
    assert result.limits_snapshot_id == "limits-v1"
    assert result.risk_rule_version == "risk-v1"


def test_event_policy_breach_rejects_and_explicit_smaller_intent_can_continue() -> None:
    window = EventRiskWindow(
        "event-cap",
        "event",
        _NOW - timedelta(minutes=1),
        _NOW + timedelta(minutes=1),
        EventRiskAction.SIZE_CAP,
        Decimal("0.4"),
    )
    policy = EventRiskPolicy("events", "v1", (window,))
    rejected = _evaluator(event_policy=policy).evaluate(_intent(qty="50"))
    assert rejected.reasons == ("EVENT_SIZE_CAP_EXCEEDED",)

    base = _BaseEvaluator(_approved(qty="40"))
    allowed = _evaluator(base=base, event_policy=policy).evaluate(_intent(qty="40"))
    assert allowed is base.result
    assert allowed.approved_qty == Decimal("40")


def test_successful_portfolio_checks_preserve_base_approval_exactly() -> None:
    base = _BaseEvaluator(_approved())
    result = _evaluator(base=base).evaluate(_intent())
    assert result is base.result
