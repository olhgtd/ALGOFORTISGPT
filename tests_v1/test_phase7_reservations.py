from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from engine.portfolio.v2.contracts import PortfolioBudgetPolicy


def _policy() -> PortfolioBudgetPolicy:
    return PortfolioBudgetPolicy(
        policy_id="budget",
        version="v1",
        owner_capital_limit=Decimal("1000"),
        user_id="u1",
        user_budget=Decimal("700"),
        strategy_budgets={"s1": Decimal("500"), "s2": Decimal("400")},
    )


def _now() -> datetime:
    return datetime(2026, 9, 27, 1, 30, tzinfo=timezone.utc)


def test_duplicate_active_reservation_id_fails_closed_without_double_count() -> None:
    from engine.portfolio.v2.reservations import CapitalReservationBook

    book = CapitalReservationBook(_policy())
    first = book.reserve(
        reservation_id="r1",
        user_id="u1",
        strategy_id="s1",
        amount=Decimal("100"),
        created_at=_now(),
    )
    second = book.reserve(
        reservation_id="r1",
        user_id="u1",
        strategy_id="s1",
        amount=Decimal("100"),
        created_at=_now(),
    )
    assert first.accepted is True
    assert second.accepted is False
    assert second.reason == "duplicate_active_reservation"
    assert book.snapshot().total_reserved == Decimal("100")


def test_unknown_strategy_wrong_user_and_budget_breaches_reject() -> None:
    from engine.portfolio.v2.reservations import CapitalReservationBook

    book = CapitalReservationBook(_policy())
    assert book.reserve(reservation_id="r0", user_id="bad", strategy_id="s1", amount=Decimal("1"), created_at=_now()).reason == "user_mismatch"
    assert book.reserve(reservation_id="r1", user_id="u1", strategy_id="missing", amount=Decimal("1"), created_at=_now()).reason == "unknown_strategy"
    assert book.reserve(reservation_id="r2", user_id="u1", strategy_id="s1", amount=Decimal("501"), created_at=_now()).reason == "strategy_budget_exceeded"
    assert book.reserve(reservation_id="r3", user_id="u1", strategy_id="s1", amount=Decimal("400"), created_at=_now()).accepted is True
    assert book.reserve(reservation_id="r4", user_id="u1", strategy_id="s2", amount=Decimal("301"), created_at=_now()).reason == "user_budget_exceeded"


def test_release_unknown_or_already_released_never_mints_capacity() -> None:
    from engine.portfolio.v2.reservations import CapitalReservationBook

    book = CapitalReservationBook(_policy())
    unknown = book.release("none", released_at=_now())
    assert unknown.accepted is False and unknown.reason == "unknown_reservation"
    book.reserve(reservation_id="r1", user_id="u1", strategy_id="s1", amount=Decimal("100"), created_at=_now())
    first = book.release("r1", released_at=_now())
    second = book.release("r1", released_at=_now())
    assert first.accepted is True
    assert second.accepted is False and second.reason == "already_released"
    snapshot = book.snapshot()
    assert snapshot.total_reserved == Decimal("0")
    assert snapshot.reserved_by_strategy["s1"] == Decimal("0")


def test_competing_reservations_cannot_oversubscribe_same_cap() -> None:
    from engine.portfolio.v2.reservations import CapitalReservationBook

    book = CapitalReservationBook(_policy())

    def attempt(reservation_id: str):
        return book.reserve(
            reservation_id=reservation_id,
            user_id="u1",
            strategy_id="s1",
            amount=Decimal("300"),
            created_at=_now(),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, ["a", "b"]))

    assert sum(1 for result in results if result.accepted) == 1
    assert book.snapshot().total_reserved == Decimal("300")


def test_reserve_rejects_float_amount_and_naive_time() -> None:
    from engine.portfolio.v2.reservations import CapitalReservationBook

    book = CapitalReservationBook(_policy())
    with pytest.raises(TypeError):
        book.reserve(reservation_id="r", user_id="u1", strategy_id="s1", amount=1.5, created_at=_now())
    with pytest.raises(ValueError):
        book.reserve(
            reservation_id="r",
            user_id="u1",
            strategy_id="s1",
            amount=Decimal("1"),
            created_at=datetime(2026, 9, 27, 1, 30),
        )
