from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

_NOW = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)


def _window(
    window_id,
    action,
    fraction=None,
    *,
    offset_start: int = -60,
    offset_end: int = 60,
):
    from engine.risk.event_day_policy_v2 import EventRiskWindow

    return EventRiskWindow(
        window_id,
        "event",
        _NOW + timedelta(minutes=offset_start),
        _NOW + timedelta(minutes=offset_end),
        action,
        fraction,
    )


def _policy(*windows):
    from engine.risk.event_day_policy_v2 import EventRiskPolicy

    return EventRiskPolicy("events", "v1", tuple(windows))


def test_missing_policy_fails_closed() -> None:
    from engine.risk.event_day_policy_v2 import evaluate_event_risk

    decision = evaluate_event_risk(
        None,
        at=_NOW,
        baseline_qty=Decimal("100"),
        requested_qty=Decimal("50"),
    )
    assert decision.allowed is False
    assert decision.reason == "EVENT_POLICY_UNAVAILABLE"


def test_active_no_trade_blocks() -> None:
    from engine.risk.event_day_policy_v2 import EventRiskAction, evaluate_event_risk

    decision = evaluate_event_risk(
        _policy(_window("n", EventRiskAction.NO_TRADE)),
        at=_NOW,
        baseline_qty=Decimal("100"),
        requested_qty=Decimal("10"),
    )
    assert decision.allowed is False
    assert decision.reason == "EVENT_NO_TRADE"
    assert decision.max_allowed_qty == Decimal("0")


def test_size_cap_never_rewrites_requested_quantity() -> None:
    from engine.risk.event_day_policy_v2 import EventRiskAction, evaluate_event_risk

    decision = evaluate_event_risk(
        _policy(_window("s", EventRiskAction.SIZE_CAP, Decimal("0.5"))),
        at=_NOW,
        baseline_qty=Decimal("100"),
        requested_qty=Decimal("60"),
    )
    assert decision.allowed is False
    assert decision.reason == "EVENT_SIZE_CAP_EXCEEDED"
    assert decision.requested_qty == Decimal("60")
    assert decision.max_allowed_qty == Decimal("50")


def test_requested_qty_at_or_below_explicit_cap_passes() -> None:
    from engine.risk.event_day_policy_v2 import EventRiskAction, evaluate_event_risk

    for quantity in (Decimal("50"), Decimal("40")):
        decision = evaluate_event_risk(
            _policy(_window("s", EventRiskAction.SIZE_CAP, Decimal("0.5"))),
            at=_NOW,
            baseline_qty=Decimal("100"),
            requested_qty=quantity,
        )
        assert decision.allowed is True
        assert decision.max_allowed_qty == Decimal("50")


def test_overlapping_windows_choose_most_restrictive() -> None:
    from engine.risk.event_day_policy_v2 import EventRiskAction, evaluate_event_risk

    policy = _policy(
        _window("a", EventRiskAction.SIZE_CAP, Decimal("0.8")),
        _window("b", EventRiskAction.SIZE_CAP, Decimal("0.3")),
    )
    decision = evaluate_event_risk(
        policy,
        at=_NOW,
        baseline_qty=Decimal("100"),
        requested_qty=Decimal("40"),
    )
    assert decision.allowed is False
    assert decision.max_allowed_qty == Decimal("30")
    assert decision.applied_fraction == Decimal("0.3")

    policy2 = _policy(
        _window("a", EventRiskAction.SIZE_CAP, Decimal("0.2")),
        _window("z", EventRiskAction.NO_TRADE),
    )
    decision2 = evaluate_event_risk(
        policy2,
        at=_NOW,
        baseline_qty=Decimal("100"),
        requested_qty=Decimal("1"),
    )
    assert decision2.allowed is False
    assert decision2.reason == "EVENT_NO_TRADE"


def test_versioned_policy_with_no_active_window_passes() -> None:
    from engine.risk.event_day_policy_v2 import EventRiskAction, evaluate_event_risk

    policy = _policy(
        _window(
            "future",
            EventRiskAction.NO_TRADE,
            offset_start=120,
            offset_end=180,
        )
    )
    decision = evaluate_event_risk(
        policy,
        at=_NOW,
        baseline_qty=Decimal("100"),
        requested_qty=Decimal("100"),
    )
    assert decision.allowed is True
    assert decision.reason == "NO_ACTIVE_EVENT_WINDOW"


def test_policy_validation_rejects_float_fraction_and_naive_window() -> None:
    from engine.risk.event_day_policy_v2 import EventRiskAction, EventRiskWindow

    with pytest.raises(TypeError):
        _window("s", EventRiskAction.SIZE_CAP, 0.5)
    with pytest.raises(ValueError):
        EventRiskWindow(
            "x",
            "event",
            datetime(2026, 9, 27, 9),
            datetime(2026, 9, 27, 10),
            EventRiskAction.NO_TRADE,
            None,
        )
