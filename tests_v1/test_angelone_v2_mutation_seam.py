from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import inspect

import pytest

from engine.broker_contract.port_v2 import (
    BrokerCredentialScope,
    BrokerMutationKind,
)
from engine.orders.contracts_v2 import ApprovedOrder, OrderIntent, OrderSource, RunMode
from engine.orders.model import OrderType
from engine.portfolio.model import InstrumentIdentity
from engine.risk.gate_v2 import RiskEvaluation, RiskGateV2
from engine.risk.limits import HardLimitHierarchy, LimitDirection

try:
    from engine.broker_adapters.angelone_v2.mutation_seam_v2 import (
        AngelOneMutationRequestV2,
        AngelOneV2MutationSeam,
        AngelOneV2MutationUnavailable,
    )
except ModuleNotFoundError as exc:
    pytest.fail(f"Angel One V2 mutation seam is not implemented: {exc}", pytrace=False)


class _Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now_utc(self) -> datetime:
        return self.value


class _Ids:
    def new_id(self, kind: str) -> str:
        return f"{kind}-1"


class _Audit:
    def write(self, event_type: str, payload: dict[str, object]) -> None:
        return None


class _Evaluator:
    def __init__(self, snapshot_id: str) -> None:
        self.snapshot_id = snapshot_id

    def evaluate(self, intent: OrderIntent) -> RiskEvaluation:
        return RiskEvaluation.approved(
            approved_qty=intent.qty,
            risk_rule_version="risk/v2",
            limits_snapshot_id=self.snapshot_id,
        )


def _approved() -> ApprovedOrder:
    created = datetime(2026, 9, 30, 9, 15, tzinfo=timezone.utc)
    instrument = InstrumentIdentity(
        "NSE",
        "NIFTY26OCT25000CE",
        "options",
        underlying="NIFTY",
        expiry=date(2026, 10, 29),
        strike="25000",
        option_type="CE",
    )
    intent = OrderIntent(
        intent_id="intent-angel-seam-1",
        strategy_id="orb",
        strategy_version="v2",
        run_mode=RunMode.LIVE,
        instrument_ref=instrument,
        side="BUY",
        qty=Decimal("2"),
        order_type=OrderType.LIMIT,
        created_at=created,
        valid_until=created + timedelta(minutes=5),
        source=OrderSource.STRATEGY,
        provenance={"market_sequence": 100},
        limit_price=Decimal("125.50"),
        protective={"policy_ref": "protective-policy/v1"},
    )
    limits = HardLimitHierarchy(
        definitions={"max_order_qty": LimitDirection.MAXIMUM},
        platform={"max_order_qty": "10"},
    ).resolve()
    result = RiskGateV2(
        evaluator=_Evaluator(limits.snapshot_id),
        clock=_Clock(created + timedelta(seconds=1)),
        id_generator=_Ids(),
        audit_sink=_Audit(),
        hard_limits=limits,
    ).evaluate_entry(intent)
    assert isinstance(result, ApprovedOrder)
    return result


def _seam() -> AngelOneV2MutationSeam:
    return AngelOneV2MutationSeam(
        policy_ref="angelone-order-policy/v1",
        protection_ref="angelone-protection-evidence/v1",
    )


def test_descriptor_is_live_real_broker_shaped_but_not_enabled() -> None:
    descriptor = _seam().descriptor

    assert descriptor.run_mode is RunMode.LIVE
    assert descriptor.mutation_kind is BrokerMutationKind.REAL_BROKER
    assert descriptor.credential_scope is BrokerCredentialScope.REAL_BROKER
    assert _seam().capabilities() == frozenset()


def test_build_place_request_translates_only_canonical_non_secret_fields() -> None:
    order = _approved()

    request = _seam().build_place_request(order)

    assert isinstance(request, AngelOneMutationRequestV2)
    assert request.client_order_id == order.client_order_id
    assert request.intent_id == order.intent_id
    assert request.exchange == "NSE"
    assert request.instrument == "NIFTY26OCT25000CE"
    assert request.segment == "options"
    assert request.side == "BUY"
    assert request.quantity == Decimal("2")
    assert request.order_type == "LIMIT"
    assert request.limit_price == Decimal("125.50")
    assert request.policy_ref == "angelone-order-policy/v1"
    assert request.protection_ref == "angelone-protection-evidence/v1"

    names = request.__dataclass_fields__.keys()
    assert not any(
        token in name.lower()
        for name in names
        for token in ("secret", "password", "token", "credential", "api_key", "totp")
    )


def test_translation_rejects_non_live_or_non_approved_inputs() -> None:
    with pytest.raises(TypeError):
        _seam().build_place_request(object())


def test_place_and_cancel_are_unconditionally_unavailable_in_package1() -> None:
    seam = _seam()
    order = _approved()

    with pytest.raises(AngelOneV2MutationUnavailable, match="unavailable"):
        seam.place(order)
    with pytest.raises(AngelOneV2MutationUnavailable, match="unavailable"):
        seam.cancel(order.client_order_id)


def test_module_contains_no_network_client_credential_loader_or_legacy_adapter_dependency() -> None:
    source = inspect.getsource(__import__(
        "engine.broker_adapters.angelone_v2.mutation_seam_v2",
        fromlist=["*"],
    ))
    lowered = source.lower()

    assert "engine.broker_adapters.angel_adapter" not in source
    assert "import requests" not in lowered
    assert "import httpx" not in lowered
    assert "urllib" not in lowered
    assert "credential_loader" not in lowered
    assert "api_key" not in lowered
    assert "totp" not in lowered
    assert "access_token" not in lowered
