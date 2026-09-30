from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from threading import Thread

from engine.risk.snapshot_contracts_v2 import RiskSnapshot
from engine.risk.snapshot_publication_v2 import RiskSnapshotPublication


def _snapshot(snapshot_id: str, sequence: int) -> RiskSnapshot:
    return RiskSnapshot(
        snapshot_id=snapshot_id,
        schema_version="v1",
        generated_at_utc=datetime(2026, 9, 30, tzinfo=timezone.utc),
        input_fingerprint=("a" if sequence == 1 else "b") * 64,
        risk_rule_version="risk-v1",
        limits_snapshot_id="limits-v1",
        account_authority_ref="acct:1",
        strategy_eligibility_ref="strategy:1",
        portfolio_state_ref="portfolio:1",
        entry_policy_ref="entry:1",
        operational_state="HEALTHY",
        kill_switch_state="CLEAR",
        hold_state="CLEAR",
        allowed_instrument_scope=("NIFTY",),
        allowed_side_scope=("BUY",),
        quantity_ceiling_by_scope={"NIFTY": Decimal("75")},
        risk_budget_evidence="risk-budget:1",
        feed_health_ref="feed:1",
        latest_market_sequence=sequence,
        source_versions=("feed@1",),
        builder_health_generation=sequence,
    )


def test_publication_starts_empty_and_replaces_whole_snapshot() -> None:
    publication = RiskSnapshotPublication()
    assert publication.current() is None
    first = _snapshot("snap-1", 1)
    second = _snapshot("snap-2", 2)
    publication.publish(first)
    assert publication.current() is first
    publication.publish(second)
    assert publication.current() is second


def test_concurrent_readers_only_observe_complete_published_objects() -> None:
    publication = RiskSnapshotPublication()
    first = _snapshot("snap-1", 1)
    second = _snapshot("snap-2", 2)
    publication.publish(first)
    observed: list[RiskSnapshot] = []

    def writer() -> None:
        for index in range(200):
            publication.publish(first if index % 2 == 0 else second)

    def reader() -> None:
        for _ in range(1000):
            value = publication.current()
            if value is not None:
                observed.append(value)

    threads = [Thread(target=writer), Thread(target=reader), Thread(target=reader)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert observed
    assert all(item is first or item is second for item in observed)
