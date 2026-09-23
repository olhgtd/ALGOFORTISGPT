from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from engine.broker_contract.conformance_v2 import assert_broker_port_conformance
from engine.broker_contract.port_v2 import (
    BoundBrokerPort,
    BrokerCredentialScope,
    BrokerMutationKind,
    BrokerPortDescriptor,
    BrokerPortV2Error,
)
from engine.core.runtime import DeterministicIdGenerator, DeterministicSeedSource, FixedClock
from engine.orders.contracts_v2 import ApprovedOrder, OrderIntent, OrderSource, RunMode
from engine.orders.model import OrderType
from engine.portfolio.model import InstrumentIdentity
from engine.risk.gate_v2 import RiskEvaluation, RiskGateV2
from engine.risk.limits import HardLimitHierarchy, LimitDirection


@dataclass
class _Evaluator:
    result: RiskEvaluation

    def evaluate(self, intent: OrderIntent) -> RiskEvaluation:
        return self.result


class _AuditSink:
    def write(self, event_type: str, payload: dict[str, object]) -> None:
        return None


class _FakeAdapter:
    def __init__(self, descriptor: BrokerPortDescriptor) -> None:
        self.descriptor = descriptor
        self.place_calls = 0

    def capabilities(self) -> frozenset[str]:
        return frozenset({"orders", "cancel", "positions", "funds", "health"})

    def place(self, order: ApprovedOrder) -> str:
        self.place_calls += 1
        return f"accepted:{order.client_order_id}"

    def cancel(self, client_order_id: str) -> str:
        return f"cancelled:{client_order_id}"

    def orders(self) -> tuple[object, ...]:
        return ()

    def positions(self) -> tuple[object, ...]:
        return ()

    def funds(self) -> dict[str, object]:
        return {"available": Decimal("100000")}

    def health(self) -> str:
        return "healthy"


def _clock() -> FixedClock:
    return FixedClock(
        datetime(2026, 9, 21, 9, 16, tzinfo=timezone.utc),
        123,
        object(),
    )


def _limits():
    return HardLimitHierarchy(
        definitions={"max_order_qty": LimitDirection.MAXIMUM},
        platform={"max_order_qty": "10"},
    ).resolve()


def _approved_order(mode: RunMode) -> ApprovedOrder:
    created = datetime(2026, 9, 21, 9, 15, tzinfo=timezone.utc)
    intent = OrderIntent(
        intent_id=f"intent-{mode.value.lower()}",
        strategy_id="orb",
        strategy_version="orb/v1",
        run_mode=mode,
        instrument_ref=InstrumentIdentity("NSE", "NIFTY", "index"),
        side="BUY",
        qty=Decimal("2"),
        order_type=OrderType.MARKET,
        created_at=created,
        valid_until=created + timedelta(minutes=10),
        source=OrderSource.STRATEGY,
        provenance={"dataset_version": "ds-v1", "config_snapshot_id": "cfg-v1"},
    )
    limits = _limits()
    runtime_clock = _clock()
    gate = RiskGateV2(
        evaluator=_Evaluator(
            RiskEvaluation.approved(
                approved_qty="2",
                risk_rule_version="risk-policy/v4",
                limits_snapshot_id=limits.snapshot_id,
            )
        ),
        clock=runtime_clock,
        id_generator=DeterministicIdGenerator(
            runtime_clock,
            DeterministicSeedSource(7),
            f"phase2-mode-{mode.value.lower()}",
        ),
        audit_sink=_AuditSink(),
        hard_limits=limits,
    )
    result = gate.evaluate_entry(intent)
    assert isinstance(result, ApprovedOrder)
    return result


def _descriptor(
    *,
    mode: RunMode,
    mutation: BrokerMutationKind,
    credentials: BrokerCredentialScope,
    adapter_id: str,
) -> BrokerPortDescriptor:
    return BrokerPortDescriptor(
        adapter_id=adapter_id,
        run_mode=mode,
        mutation_kind=mutation,
        credential_scope=credentials,
        contract_version="BrokerPortV2@1",
    )


def test_paper_process_cannot_bind_real_broker_mutation_adapter() -> None:
    live_adapter = _FakeAdapter(
        _descriptor(
            mode=RunMode.LIVE,
            mutation=BrokerMutationKind.REAL_BROKER,
            credentials=BrokerCredentialScope.REAL_BROKER,
            adapter_id="broker.live.fake",
        )
    )

    with pytest.raises(BrokerPortV2Error, match="PAPER.*real broker|mode"):
        BoundBrokerPort.bind(process_mode=RunMode.PAPER, adapter=live_adapter)


def test_backtest_process_cannot_bind_real_broker_mutation_adapter() -> None:
    live_adapter = _FakeAdapter(
        _descriptor(
            mode=RunMode.LIVE,
            mutation=BrokerMutationKind.REAL_BROKER,
            credentials=BrokerCredentialScope.REAL_BROKER,
            adapter_id="broker.live.fake",
        )
    )

    with pytest.raises(BrokerPortV2Error, match="BACKTEST.*real broker|mode"):
        BoundBrokerPort.bind(process_mode=RunMode.BACKTEST, adapter=live_adapter)


def test_paper_adapter_cannot_declare_real_broker_credentials() -> None:
    unsafe_paper = _FakeAdapter(
        _descriptor(
            mode=RunMode.PAPER,
            mutation=BrokerMutationKind.SIMULATED,
            credentials=BrokerCredentialScope.REAL_BROKER,
            adapter_id="paper.unsafe",
        )
    )

    with pytest.raises(BrokerPortV2Error, match="credential"):
        BoundBrokerPort.bind(process_mode=RunMode.PAPER, adapter=unsafe_paper)


def test_approved_order_mode_mismatch_is_blocked_before_adapter_call() -> None:
    paper_adapter = _FakeAdapter(
        _descriptor(
            mode=RunMode.PAPER,
            mutation=BrokerMutationKind.SIMULATED,
            credentials=BrokerCredentialScope.NONE,
            adapter_id="paper.fake",
        )
    )
    port = BoundBrokerPort.bind(process_mode=RunMode.PAPER, adapter=paper_adapter)

    with pytest.raises(BrokerPortV2Error, match="run_mode"):
        port.place(_approved_order(RunMode.BACKTEST))

    assert paper_adapter.place_calls == 0


def test_paper_adapter_passes_broker_neutral_conformance_shell() -> None:
    paper_adapter = _FakeAdapter(
        _descriptor(
            mode=RunMode.PAPER,
            mutation=BrokerMutationKind.SIMULATED,
            credentials=BrokerCredentialScope.NONE,
            adapter_id="paper.fake",
        )
    )

    assert_broker_port_conformance(paper_adapter, expected_mode=RunMode.PAPER)


def test_paper_bound_port_accepts_only_paper_approved_order() -> None:
    paper_adapter = _FakeAdapter(
        _descriptor(
            mode=RunMode.PAPER,
            mutation=BrokerMutationKind.SIMULATED,
            credentials=BrokerCredentialScope.NONE,
            adapter_id="paper.fake",
        )
    )
    port = BoundBrokerPort.bind(process_mode=RunMode.PAPER, adapter=paper_adapter)
    order = _approved_order(RunMode.PAPER)

    result = port.place(order)

    assert result == f"accepted:{order.client_order_id}"
    assert paper_adapter.place_calls == 1


def test_live_mutation_stays_unreachable_while_read_only_or_disarmed() -> None:
    live_adapter = _FakeAdapter(
        _descriptor(
            mode=RunMode.LIVE,
            mutation=BrokerMutationKind.REAL_BROKER,
            credentials=BrokerCredentialScope.REAL_BROKER,
            adapter_id="broker.live.fake",
        )
    )
    port = BoundBrokerPort.bind(
        process_mode=RunMode.LIVE,
        adapter=live_adapter,
        read_only=True,
        disarmed=True,
    )

    with pytest.raises(BrokerPortV2Error, match="READ_ONLY|DISARMED"):
        port.place(_approved_order(RunMode.LIVE))

    assert live_adapter.place_calls == 0
