from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import sqlite3

import pytest

from engine.core.runtime import FixedClock
from engine.orders.contracts_v2 import ApprovedOrder, OrderIntent, OrderSource, RunMode
from engine.orders.model import OrderType
from engine.persistence.live_execution_schema_v9 import LIVE_EXECUTION_CREATE_TABLES_SQL
from engine.persistence.live_execution_store_v2 import LiveExecutionStoreV2
from engine.portfolio.model import InstrumentIdentity
from engine.risk.gate_v2 import RiskEvaluation, RiskGateV2
from engine.risk.limits import HardLimitHierarchy, LimitDirection

try:
    from engine.live.execution_capacity_v2 import (
        JournalLiveExecutionCapacityGate,
        LiveExecutionCapacityBlocked,
        LiveExecutionCapacityEvidence,
    )
except ModuleNotFoundError as exc:
    pytest.fail(f"Live execution capacity gate is not implemented: {exc}", pytrace=False)


class _Audit:
    def write(self, event_type: str, payload: dict[str, object]) -> None:
        return None


class _Ids:
    def __init__(self) -> None:
        self._n = 0

    def new_id(self, kind: str) -> str:
        self._n += 1
        return f"{kind}-{self._n}"


@dataclass
class _Evaluator:
    limits_snapshot_id: str

    def evaluate(self, intent: OrderIntent) -> RiskEvaluation:
        return RiskEvaluation.approved(
            approved_qty=intent.qty,
            risk_rule_version="risk/v1",
            limits_snapshot_id=self.limits_snapshot_id,
        )


class _EvidenceProvider:
    def __init__(
        self,
        *,
        broker_id: str = "angelone",
        broker_account_ref: str = "acct-1",
        available_cash: str = "100",
        required_cash: str = "70",
        fresh: bool = True,
    ) -> None:
        self.broker_id = broker_id
        self.broker_account_ref = broker_account_ref
        self.available_cash = Decimal(available_cash)
        self.required_cash = Decimal(required_cash)
        self.fresh = fresh

    def current(self, order: ApprovedOrder, now: datetime) -> LiveExecutionCapacityEvidence:
        scope = order.intent.instrument_ref.underlying or order.intent.instrument_ref.instrument
        return LiveExecutionCapacityEvidence(
            broker_id=self.broker_id,
            broker_account_ref=self.broker_account_ref,
            instrument_scope=scope,
            required_cash=self.required_cash,
            available_cash=self.available_cash,
            funds_evidence_ref="funds-1",
            observed_at=now,
            freshness_verified=self.fresh,
        )


def _database(path) -> None:
    connection = sqlite3.connect(str(path))
    try:
        for statement in LIVE_EXECUTION_CREATE_TABLES_SQL:
            connection.execute(statement)
        connection.execute("PRAGMA user_version = 9")
        connection.commit()
    finally:
        connection.close()


def _approved(underlying: str, intent_id: str) -> ApprovedOrder:
    now = datetime(2026, 9, 30, 9, 15, tzinfo=timezone.utc)
    identity = InstrumentIdentity(
        "NSE",
        f"{underlying}26OCT22000CE",
        "options",
        underlying=underlying,
        expiry=date(2026, 10, 29),
        strike="22000",
        option_type="CE",
    )
    intent = OrderIntent(
        intent_id=intent_id,
        strategy_id="orb",
        strategy_version="orb/v1",
        run_mode=RunMode.LIVE,
        instrument_ref=identity,
        side="BUY",
        qty=Decimal("1"),
        order_type=OrderType.MARKET,
        created_at=now,
        valid_until=now + timedelta(minutes=5),
        source=OrderSource.STRATEGY,
        provenance={"market_sequence": 1},
    )
    limits = HardLimitHierarchy(
        definitions={"max_order_qty": LimitDirection.MAXIMUM},
        platform={"max_order_qty": "10"},
    ).resolve()
    gate = RiskGateV2(
        evaluator=_Evaluator(limits.snapshot_id),
        clock=FixedClock(now, 1, object()),
        id_generator=_Ids(),
        audit_sink=_Audit(),
        hard_limits=limits,
    )
    result = gate.evaluate_entry(intent)
    assert isinstance(result, ApprovedOrder)
    return result


def test_unverified_capacity_evidence_fails_closed(tmp_path) -> None:
    database = tmp_path / "live.sqlite3"
    _database(database)
    gate = JournalLiveExecutionCapacityGate(
        journal=LiveExecutionStoreV2(database),
        evidence_provider=_EvidenceProvider(fresh=False),
    )
    order = _approved("NIFTY", "intent-nifty")
    now = datetime(2026, 9, 30, 9, 16, tzinfo=timezone.utc)

    with pytest.raises(LiveExecutionCapacityBlocked, match="fresh"):
        gate.reserve(order, now=now)


def test_shared_broker_account_budget_blocks_second_simultaneous_scope(tmp_path) -> None:
    database = tmp_path / "live.sqlite3"
    _database(database)
    journal = LiveExecutionStoreV2(database)
    gate = JournalLiveExecutionCapacityGate(
        journal=journal,
        evidence_provider=_EvidenceProvider(available_cash="100", required_cash="70"),
    )
    now = datetime(2026, 9, 30, 9, 16, tzinfo=timezone.utc)
    nifty = _approved("NIFTY", "intent-nifty")
    banknifty = _approved("BANKNIFTY", "intent-banknifty")

    assert gate.reserve(nifty, now=now) == "funds-1"
    with pytest.raises(LiveExecutionCapacityBlocked, match="insufficient"):
        gate.reserve(banknifty, now=now)

    assert journal.active_reserved_cash("angelone", "acct-1") == Decimal("70")
    assert {item.instrument_scope for item in journal.list_active_capacity("angelone", "acct-1")} == {"NIFTY"}


def test_pre_submit_release_frees_capacity_for_another_instrument(tmp_path) -> None:
    database = tmp_path / "live.sqlite3"
    _database(database)
    journal = LiveExecutionStoreV2(database)
    gate = JournalLiveExecutionCapacityGate(
        journal=journal,
        evidence_provider=_EvidenceProvider(available_cash="100", required_cash="70"),
    )
    now = datetime(2026, 9, 30, 9, 16, tzinfo=timezone.utc)
    nifty = _approved("NIFTY", "intent-nifty")
    sensex = _approved("SENSEX", "intent-sensex")

    gate.reserve(nifty, now=now)
    assert gate.release(nifty.client_order_id, now=now + timedelta(seconds=1), reason="pre_submit_abort") is True
    assert gate.reserve(sensex, now=now + timedelta(seconds=2)) == "funds-1"
    assert journal.active_reserved_cash("angelone", "acct-1") == Decimal("70")


def test_same_account_ref_on_different_brokers_has_independent_capacity(tmp_path) -> None:
    database = tmp_path / "live.sqlite3"
    _database(database)
    journal = LiveExecutionStoreV2(database)
    now = datetime(2026, 9, 30, 9, 16, tzinfo=timezone.utc)
    angel = JournalLiveExecutionCapacityGate(
        journal=journal,
        evidence_provider=_EvidenceProvider(broker_id="angelone", available_cash="100", required_cash="70"),
    )
    zerodha = JournalLiveExecutionCapacityGate(
        journal=journal,
        evidence_provider=_EvidenceProvider(broker_id="zerodha", available_cash="100", required_cash="70"),
    )

    assert angel.reserve(_approved("NIFTY", "intent-angel"), now=now) == "funds-1"
    assert zerodha.reserve(_approved("BANKNIFTY", "intent-zerodha"), now=now) == "funds-1"
    assert journal.active_reserved_cash("angelone", "acct-1") == Decimal("70")
    assert journal.active_reserved_cash("zerodha", "acct-1") == Decimal("70")
