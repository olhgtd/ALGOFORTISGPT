from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from engine.portfolio.candidate_arbitration_v2 import (
    BrokerAccountKey,
    CandidateReservationRequest,
    PortfolioCandidateArbitrator,
)
from engine.portfolio.v2.contracts import PortfolioBudgetPolicy
from engine.portfolio.v2.reservations import CapitalReservationBook

NOW = datetime(2026, 10, 1, 9, 30, tzinfo=timezone.utc)


def _book(user_budget: str = "100") -> CapitalReservationBook:
    policy = PortfolioBudgetPolicy(
        "portfolio-budget",
        "1.0.0",
        Decimal(user_budget),
        "user-1",
        Decimal(user_budget),
        {"strategy-a": Decimal(user_budget), "strategy-b": Decimal(user_budget)},
    )
    return CapitalReservationBook(policy)


def _request(candidate: str, broker: str, account: str, amount: str, *, ttl_seconds: int = 60, strategy: str = "strategy-a") -> CandidateReservationRequest:
    return CandidateReservationRequest(
        candidate_id=candidate,
        broker_account=BrokerAccountKey(broker, account),
        strategy_id=strategy,
        required_capital=Decimal(amount),
        created_at=NOW,
        valid_until=NOW + timedelta(seconds=ttl_seconds),
    )


def test_same_account_candidates_cannot_double_reserve_shared_capital() -> None:
    pool = BrokerAccountKey("broker-a", "account-1")
    arb = PortfolioCandidateArbitrator({pool: _book("100")}, aggregate_capital_limit=Decimal("200"))
    first = arb.reserve(_request("candidate-1", "broker-a", "account-1", "70"))
    second = arb.reserve(_request("candidate-2", "broker-a", "account-1", "40", strategy="strategy-b"))
    assert first.accepted is True
    assert second.accepted is False
    assert second.reason in {"USER_BUDGET_EXCEEDED", "AGGREGATE_CAPITAL_EXCEEDED"}


def test_distinct_broker_accounts_have_independent_parallel_reservation_pools() -> None:
    a = BrokerAccountKey("broker-a", "account-1")
    b = BrokerAccountKey("broker-b", "account-2")
    arb = PortfolioCandidateArbitrator(
        {a: _book("100"), b: _book("100")},
        aggregate_capital_limit=Decimal("200"),
    )
    assert arb.reserve(_request("candidate-a", "broker-a", "account-1", "80")).accepted is True
    assert arb.reserve(_request("candidate-b", "broker-b", "account-2", "80")).accepted is True
    assert arb.total_reserved == Decimal("160")


def test_aggregate_cap_prevents_cross_account_overexposure() -> None:
    a = BrokerAccountKey("broker-a", "account-1")
    b = BrokerAccountKey("broker-b", "account-2")
    arb = PortfolioCandidateArbitrator(
        {a: _book("100"), b: _book("100")},
        aggregate_capital_limit=Decimal("120"),
    )
    assert arb.reserve(_request("candidate-a", "broker-a", "account-1", "80")).accepted is True
    blocked = arb.reserve(_request("candidate-b", "broker-b", "account-2", "50"))
    assert blocked.accepted is False
    assert blocked.reason == "AGGREGATE_CAPITAL_EXCEEDED"


def test_expired_reservation_is_released_before_new_candidate_is_considered() -> None:
    pool = BrokerAccountKey("broker-a", "account-1")
    arb = PortfolioCandidateArbitrator({pool: _book("100")}, aggregate_capital_limit=Decimal("100"))
    assert arb.reserve(_request("old", "broker-a", "account-1", "90", ttl_seconds=10)).accepted is True
    later = NOW + timedelta(seconds=11)
    fresh = CandidateReservationRequest(
        candidate_id="fresh",
        broker_account=pool,
        strategy_id="strategy-b",
        required_capital=Decimal("90"),
        created_at=later,
        valid_until=later + timedelta(seconds=60),
    )
    assert arb.reserve(fresh).accepted is True
    assert arb.total_reserved == Decimal("90")


def test_release_returns_capital_and_module_has_no_approved_order_authority() -> None:
    pool = BrokerAccountKey("broker-a", "account-1")
    arb = PortfolioCandidateArbitrator({pool: _book("100")}, aggregate_capital_limit=Decimal("100"))
    assert arb.reserve(_request("candidate-1", "broker-a", "account-1", "60")).accepted is True
    assert arb.release("candidate-1", released_at=NOW + timedelta(seconds=1)) is True
    assert arb.total_reserved == Decimal("0")
    for forbidden in ("mint_approved_order", "approved_order", "place_order", "arm_live"):
        assert not hasattr(arb, forbidden)
