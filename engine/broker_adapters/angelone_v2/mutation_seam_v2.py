"""Disarmed Angel One V2 mutation translation seam for Package 1.

This module may translate a genuine V2 ``ApprovedOrder`` into an immutable,
non-secret provider-facing request shape. It deliberately contains no network
transport or authentication material, and mutation methods remain unavailable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from engine.broker_contract.port_v2 import (
    BrokerCredentialScope,
    BrokerMutationKind,
    BrokerPortDescriptor,
)
from engine.orders.contracts_v2 import ApprovedOrder, RunMode


class AngelOneV2MutationUnavailable(RuntimeError):
    pass


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True, slots=True)
class AngelOneMutationRequestV2:
    client_order_id: str
    intent_id: str
    risk_decision_ref: str
    exchange: str
    instrument: str
    segment: str
    underlying: str | None
    expiry: date | None
    strike: Decimal | None
    option_type: str | None
    side: str
    quantity: Decimal
    order_type: str
    limit_price: Decimal | None
    expires_at: datetime
    policy_ref: str
    protection_ref: str


class AngelOneV2MutationSeam:
    """Translation-only real-broker shaped seam; execution is unavailable."""

    def __init__(self, *, policy_ref: str, protection_ref: str) -> None:
        self._policy_ref = _text(policy_ref, "policy_ref")
        self._protection_ref = _text(protection_ref, "protection_ref")
        self.descriptor = BrokerPortDescriptor(
            adapter_id="angelone-v2-mutation-seam",
            run_mode=RunMode.LIVE,
            mutation_kind=BrokerMutationKind.REAL_BROKER,
            credential_scope=BrokerCredentialScope.REAL_BROKER,
        )

    def capabilities(self) -> frozenset[str]:
        # Truthful Package-1 declaration: no executable mutation capability.
        return frozenset()

    def build_place_request(self, order: ApprovedOrder) -> AngelOneMutationRequestV2:
        if not isinstance(order, ApprovedOrder):
            raise TypeError("order must be ApprovedOrder")
        if order.run_mode is not RunMode.LIVE:
            raise ValueError("Angel One V2 mutation seam accepts LIVE ApprovedOrder only")
        intent = order.intent
        instrument = intent.instrument_ref
        return AngelOneMutationRequestV2(
            client_order_id=order.client_order_id,
            intent_id=order.intent_id,
            risk_decision_ref=order.risk_decision_ref,
            exchange=instrument.market.upper(),
            instrument=instrument.instrument,
            segment=instrument.segment,
            underlying=instrument.underlying,
            expiry=instrument.expiry,
            strike=instrument.strike,
            option_type=instrument.option_type,
            side=intent.side,
            quantity=intent.qty,
            order_type=intent.order_type.value,
            limit_price=intent.limit_price,
            expires_at=order.expires_at,
            policy_ref=self._policy_ref,
            protection_ref=self._protection_ref,
        )

    def place(self, order: ApprovedOrder) -> object:
        if not isinstance(order, ApprovedOrder):
            raise TypeError("order must be ApprovedOrder")
        raise AngelOneV2MutationUnavailable(
            "Angel One V2 real-broker mutation is unavailable in Package 1"
        )

    def cancel(self, client_order_id: str) -> object:
        _text(client_order_id, "client_order_id")
        raise AngelOneV2MutationUnavailable(
            "Angel One V2 real-broker mutation is unavailable in Package 1"
        )

    def orders(self) -> object:
        raise AngelOneV2MutationUnavailable("read operations are unavailable on mutation seam")

    def positions(self) -> object:
        raise AngelOneV2MutationUnavailable("read operations are unavailable on mutation seam")

    def funds(self) -> object:
        raise AngelOneV2MutationUnavailable("read operations are unavailable on mutation seam")

    def health(self) -> object:
        return {"mutation_available": False, "read_only": True, "disarmed": True}


__all__ = [
    "AngelOneMutationRequestV2",
    "AngelOneV2MutationSeam",
    "AngelOneV2MutationUnavailable",
]
