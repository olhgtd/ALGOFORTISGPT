from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

try:
    from engine.live.account_candidate_arbiter_v2 import (
        AccountCandidateEvidence,
        AccountCapitalDomainKey,
        LiveAccountCandidateArbiterV2,
    )
except ModuleNotFoundError as exc:  # RED until Task-2A implementation exists
    pytest.fail(f"Live account candidate arbiter is not implemented: {exc}", pytrace=False)


NOW = datetime(2026, 10, 1, 9, 15, tzinfo=timezone.utc)


def _candidate(
    candidate_id: str,
    *,
    broker_id: str = "angelone",
    account: str = "acct-1",
    hard_eligible: bool = True,
    exposure_allowed: bool = True,
    portfolio_priority: int = 10,
    strategy_priority: int = 10,
    edge_quality: str = "1.0",
    capital_efficiency: str = "1.0",
    signal_offset_ms: int = 0,
) -> AccountCandidateEvidence:
    return AccountCandidateEvidence(
        domain_key=AccountCapitalDomainKey(broker_id=broker_id, broker_account_ref=account),
        candidate_id=candidate_id,
        hard_eligible=hard_eligible,
        exposure_allowed=exposure_allowed,
        portfolio_priority=portfolio_priority,
        strategy_priority=strategy_priority,
        edge_quality=Decimal(edge_quality),
        capital_efficiency=Decimal(capital_efficiency),
        signal_at=NOW + timedelta(milliseconds=signal_offset_ms),
        policy_ref="account-arbiter-policy/v1",
    )


def test_same_domain_ranking_is_deterministic_and_independent_of_arrival_order() -> None:
    domain = AccountCapitalDomainKey("angelone", "acct-1")
    arbiter = LiveAccountCandidateArbiterV2(domain)
    candidates = (
        _candidate("nifty", portfolio_priority=2, strategy_priority=1, edge_quality="4.0"),
        _candidate("banknifty", portfolio_priority=1, strategy_priority=5, edge_quality="2.0"),
        _candidate("sensex", portfolio_priority=1, strategy_priority=2, edge_quality="3.0"),
    )

    first = tuple(item.candidate_id for item in arbiter.rank(candidates))
    second = tuple(item.candidate_id for item in arbiter.rank(tuple(reversed(candidates))))

    assert first == ("sensex", "banknifty", "nifty")
    assert second == first


def test_correlated_exposure_policy_blocks_candidate_even_when_other_metrics_win() -> None:
    arbiter = LiveAccountCandidateArbiterV2(AccountCapitalDomainKey("angelone", "acct-1"))
    blocked = _candidate(
        "blocked-best-edge",
        exposure_allowed=False,
        portfolio_priority=0,
        strategy_priority=0,
        edge_quality="999",
        capital_efficiency="999",
    )
    allowed = _candidate(
        "allowed",
        exposure_allowed=True,
        portfolio_priority=5,
        strategy_priority=5,
        edge_quality="1",
        capital_efficiency="1",
    )

    assert tuple(item.candidate_id for item in arbiter.rank((blocked, allowed))) == ("allowed",)


def test_hard_ineligible_candidate_never_enters_ranked_batch() -> None:
    arbiter = LiveAccountCandidateArbiterV2(AccountCapitalDomainKey("angelone", "acct-1"))
    assert arbiter.rank((_candidate("blocked", hard_eligible=False),)) == ()


def test_final_tie_break_is_stable_candidate_identity() -> None:
    arbiter = LiveAccountCandidateArbiterV2(AccountCapitalDomainKey("angelone", "acct-1"))
    a = _candidate("candidate-a")
    b = _candidate("candidate-b")

    assert tuple(item.candidate_id for item in arbiter.rank((b, a))) == (
        "candidate-a",
        "candidate-b",
    )


def test_mixed_account_domains_fail_closed_in_one_arbiter() -> None:
    arbiter = LiveAccountCandidateArbiterV2(AccountCapitalDomainKey("angelone", "acct-1"))
    with pytest.raises(ValueError, match="domain"):
        arbiter.rank((_candidate("a"), _candidate("b", account="acct-2")))


def test_same_account_ref_on_different_brokers_is_not_the_same_capital_domain() -> None:
    angel = AccountCapitalDomainKey("angelone", "same-ref")
    dhan = AccountCapitalDomainKey("dhan", "same-ref")
    assert angel != dhan

    angel_rank = LiveAccountCandidateArbiterV2(angel).rank(
        (_candidate("angel-candidate", broker_id="angelone", account="same-ref"),)
    )
    dhan_rank = LiveAccountCandidateArbiterV2(dhan).rank(
        (_candidate("dhan-candidate", broker_id="dhan", account="same-ref"),)
    )
    assert angel_rank[0].candidate_id == "angel-candidate"
    assert dhan_rank[0].candidate_id == "dhan-candidate"


def test_ai_output_cannot_be_injected_as_same_job_priority_input() -> None:
    with pytest.raises(TypeError):
        AccountCandidateEvidence(
            domain_key=AccountCapitalDomainKey("angelone", "acct-1"),
            candidate_id="candidate-ai",
            hard_eligible=True,
            exposure_allowed=True,
            portfolio_priority=1,
            strategy_priority=1,
            edge_quality=Decimal("1"),
            capital_efficiency=Decimal("1"),
            signal_at=NOW,
            policy_ref="account-arbiter-policy/v1",
            ai_score=Decimal("999"),
        )
