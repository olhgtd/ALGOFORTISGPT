from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from engine.core.runtime import FixedClock
from engine.orders.contracts_v2 import OrderIntent, OrderSource, RiskDecisionKind, RunMode
from engine.orders.model import OrderType
from engine.portfolio.model import InstrumentIdentity
from engine.risk.fast_path_v2 import CurrentQuoteEvidence, FastPathRiskEvaluator
from engine.risk.snapshot_contracts_v2 import RiskSnapshot
from engine.risk.snapshot_publication_v2 import RiskSnapshotPublication


class _QuoteProvider:
    def __init__(self, quote: CurrentQuoteEvidence) -> None:
        self.quote = quote

    def current(self, instrument_ref: InstrumentIdentity) -> CurrentQuoteEvidence:
        return self.quote


class _ReplayGuard:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed
        self.claims = []

    def claim(self, intent_id: str, snapshot_id: str, market_sequence: int) -> bool:
        self.claims.append((intent_id, snapshot_id, market_sequence))
        return self.allowed


class _Freshness:
    reference = "freshness@test"

    def __init__(self, fresh: bool = True) -> None:
        self.fresh = fresh

    def is_fresh(self, snapshot: RiskSnapshot, now: datetime) -> bool:
        return self.fresh


class _PricePolicy:
    reference = "price@test"

    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed

    def allows(self, intent: OrderIntent, quote: CurrentQuoteEvidence) -> bool:
        return self.allowed


class _EntryStatePolicy:
    reference = "entry-state@test"

    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed

    def entries_allowed(self, snapshot: RiskSnapshot) -> bool:
        return self.allowed


def _instrument() -> InstrumentIdentity:
    return InstrumentIdentity(
        market="NSE",
        instrument="NIFTY26OCT25000CE",
        segment="options",
        underlying="NIFTY",
        expiry=date(2026, 10, 29),
        strike=Decimal("25000"),
        option_type="CE",
    )


def _intent(*, side: str = "BUY", qty: str = "1", provenance=None) -> OrderIntent:
    created = datetime(2026, 9, 30, 9, 15, tzinfo=timezone.utc)
    return OrderIntent(
        intent_id="intent-fast-1",
        strategy_id="strategy-1",
        strategy_version="v1",
        run_mode=RunMode.PAPER,
        instrument_ref=_instrument(),
        side=side,
        qty=Decimal(qty),
        order_type=OrderType.MARKET,
        created_at=created,
        valid_until=created + timedelta(seconds=10),
        source=OrderSource.STRATEGY,
        provenance=provenance or {"market_sequence": 100},
    )


def _snapshot(**overrides) -> RiskSnapshot:
    values = {
        "snapshot_id": "snap-fast-1",
        "schema_version": "v1",
        "generated_at_utc": datetime(2026, 9, 30, 9, 15, tzinfo=timezone.utc),
        "input_fingerprint": "a" * 64,
        "risk_rule_version": "risk-v1",
        "limits_snapshot_id": "limits-v1",
        "account_authority_ref": "acct:1",
        "strategy_eligibility_ref": "strategy:1",
        "portfolio_state_ref": "portfolio:1",
        "entry_policy_ref": "entry:1",
        "operational_state": "HEALTHY",
        "kill_switch_state": "CLEAR",
        "hold_state": "CLEAR",
        "allowed_instrument_scope": ("NIFTY",),
        "allowed_side_scope": ("BUY",),
        "quantity_ceiling_by_scope": {"NIFTY": Decimal("75")},
        "risk_budget_evidence": "risk-budget:1",
        "feed_health_ref": "feed:1",
        "latest_market_sequence": 101,
        "source_versions": ("feed@1",),
        "builder_health_generation": 4,
    }
    values.update(overrides)
    return RiskSnapshot(**values)


def _quote(sequence: int = 101) -> CurrentQuoteEvidence:
    return CurrentQuoteEvidence(
        instrument_ref=_instrument(),
        observed_at=datetime(2026, 9, 30, 9, 15, 0, 1000, tzinfo=timezone.utc),
        market_sequence=sequence,
        bid=Decimal("224.90"),
        ask=Decimal("225.10"),
        source_ref="quote:1",
    )


def _evaluator(publication: RiskSnapshotPublication, **overrides) -> FastPathRiskEvaluator:
    values = {
        "publication": publication,
        "quote_provider": _QuoteProvider(_quote()),
        "replay_guard": _ReplayGuard(),
        "freshness_policy": _Freshness(),
        "price_policy": _PricePolicy(),
        "entry_state_policy": _EntryStatePolicy(),
        "clock": FixedClock(
            datetime(2026, 9, 30, 9, 15, 0, 2000, tzinfo=timezone.utc),
            10,
            object(),
        ),
        "active_risk_rule_version": "risk-v1",
        "active_limits_snapshot_id": "limits-v1",
        "active_builder_health_generation": lambda: 4,
        "latency_policy_ref": "TEST_ONLY/latency@v1",
    }
    values.update(overrides)
    return FastPathRiskEvaluator(**values)


def test_fast_evaluator_approves_healthy_matching_candidate() -> None:
    publication = RiskSnapshotPublication()
    publication.publish(_snapshot())
    result = _evaluator(publication).evaluate(_intent())
    assert result.decision is RiskDecisionKind.APPROVED
    assert result.approved_qty == Decimal("1")
    assert result.risk_snapshot_id == "snap-fast-1"
    assert result.market_sequence_ref == "101"
    assert result.latency_policy_ref == "TEST_ONLY/latency@v1"


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda snap: None, "snapshot_unavailable"),
        (lambda snap: _snapshot(operational_state="HALTED"), "entries_not_allowed"),
        (lambda snap: _snapshot(kill_switch_state="ACTIVE"), "kill_switch_active"),
        (lambda snap: _snapshot(hold_state="ACTIVE"), "hold_active"),
        (lambda snap: _snapshot(risk_rule_version="risk-v0"), "risk_rule_version_mismatch"),
        (lambda snap: _snapshot(limits_snapshot_id="limits-v0"), "limits_snapshot_mismatch"),
        (lambda snap: _snapshot(builder_health_generation=3), "builder_generation_mismatch"),
    ],
)
def test_fast_evaluator_fails_closed_for_snapshot_authority_problems(mutation, expected) -> None:
    publication = RiskSnapshotPublication()
    value = mutation(_snapshot())
    if value is not None:
        publication.publish(value)
    result = _evaluator(publication).evaluate(_intent())
    assert result.decision is RiskDecisionKind.REJECTED
    assert expected in result.reasons


def test_fast_evaluator_rejects_stale_snapshot_duplicate_and_old_quote() -> None:
    publication = RiskSnapshotPublication()
    publication.publish(_snapshot())
    stale = _evaluator(publication, freshness_policy=_Freshness(False)).evaluate(_intent())
    assert stale.reasons == ("snapshot_stale",)

    duplicate = _evaluator(publication, replay_guard=_ReplayGuard(False)).evaluate(_intent())
    assert duplicate.reasons == ("duplicate_or_replay",)

    old_quote = _evaluator(publication, quote_provider=_QuoteProvider(_quote(99))).evaluate(_intent())
    assert old_quote.reasons == ("quote_sequence_behind_candidate",)


def test_fast_evaluator_rejects_price_policy_side_and_quantity() -> None:
    publication = RiskSnapshotPublication()
    publication.publish(_snapshot())
    price = _evaluator(publication, price_policy=_PricePolicy(False)).evaluate(_intent())
    assert price.reasons == ("price_policy_rejected",)

    sell = _evaluator(publication).evaluate(_intent(side="SELL"))
    assert "options_buy_only" in sell.reasons

    qty = _evaluator(publication).evaluate(_intent(qty="100"))
    assert qty.reasons == ("quantity_ceiling",)


def test_fast_evaluator_has_no_slow_fallback_when_snapshot_missing() -> None:
    publication = RiskSnapshotPublication()
    quote_provider = _QuoteProvider(_quote())
    evaluator = _evaluator(publication, quote_provider=quote_provider)
    result = evaluator.evaluate(_intent())
    assert result.reasons == ("snapshot_unavailable",)
