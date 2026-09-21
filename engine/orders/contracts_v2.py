"""Canonical AlgoFortis V2 Safety-Spine trading contracts.

These contracts are additive to the frozen V1 order model.  They define the
minimum V2 boundary from OrderIntent -> RiskDecision -> ApprovedOrder without
wiring any real broker mutation path.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Literal, Mapping

from engine.core.numeric import as_decimal
from engine.orders.model import OrderType
from engine.portfolio.model import InstrumentIdentity
from engine.reproducibility.codec import CanonicalCodec


class RunMode(str, Enum):
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    LIVE = "LIVE"


class OrderSource(str, Enum):
    STRATEGY = "STRATEGY"
    AI_CANDIDATE = "AI_CANDIDATE"
    MANUAL = "MANUAL"


class RiskDecisionKind(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REDUCED = "REDUCED"


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _aware(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    return value


def _frozen_mapping(value: Mapping[str, object], field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    copied = deepcopy(dict(value))
    if not all(isinstance(key, str) and key.strip() for key in copied):
        raise ValueError(f"{field_name} keys must be non-empty strings")
    return MappingProxyType(copied)


@dataclass(frozen=True, slots=True)
class OrderIntent:
    """Immutable, TTL-bound intent consumed by the V2 central Risk Gate."""

    intent_id: str
    strategy_id: str
    strategy_version: str
    run_mode: RunMode
    instrument_ref: InstrumentIdentity
    side: Literal["BUY", "SELL"]
    qty: Decimal | int | str
    order_type: OrderType
    created_at: datetime
    valid_until: datetime
    source: OrderSource
    provenance: Mapping[str, object]
    limit_price: Decimal | int | str | None = None
    protective: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("intent_id", "strategy_id", "strategy_version"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.run_mode, RunMode):
            raise TypeError("run_mode must be a RunMode")
        if not isinstance(self.instrument_ref, InstrumentIdentity):
            raise TypeError("instrument_ref must be an InstrumentIdentity")
        if self.side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        quantity = as_decimal(self.qty, "qty")
        if quantity <= 0:
            raise ValueError("qty must be positive")
        object.__setattr__(self, "qty", quantity)
        if not isinstance(self.order_type, OrderType):
            raise TypeError("order_type must be an OrderType")
        created = _aware(self.created_at, "created_at")
        expires = _aware(self.valid_until, "valid_until")
        if expires <= created:
            raise ValueError("valid_until must be later than created_at")
        if not isinstance(self.source, OrderSource):
            raise TypeError("source must be an OrderSource")
        if self.limit_price is not None:
            price = as_decimal(self.limit_price, "limit_price")
            if price <= 0:
                raise ValueError("limit_price must be positive")
            object.__setattr__(self, "limit_price", price)
        object.__setattr__(self, "provenance", _frozen_mapping(self.provenance, "provenance"))
        object.__setattr__(self, "protective", _frozen_mapping(self.protective, "protective"))


@dataclass(frozen=True, slots=True)
class RiskDecision:
    """Versioned risk decision evidence referenced by ApprovedOrder."""

    intent_id: str
    decision: RiskDecisionKind
    reasons: tuple[str, ...]
    risk_rule_version: str
    limits_snapshot_id: str
    approved_qty: Decimal | int | str | None = None
    approval_token: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "intent_id", _text(self.intent_id, "intent_id"))
        if not isinstance(self.decision, RiskDecisionKind):
            raise TypeError("decision must be a RiskDecisionKind")
        if not isinstance(self.reasons, tuple):
            raise TypeError("reasons must be a tuple")
        reasons = tuple(_text(reason, "reason") for reason in self.reasons)
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(self, "risk_rule_version", _text(self.risk_rule_version, "risk_rule_version"))
        object.__setattr__(self, "limits_snapshot_id", _text(self.limits_snapshot_id, "limits_snapshot_id"))

        quantity: Decimal | None = None
        if self.approved_qty is not None:
            quantity = as_decimal(self.approved_qty, "approved_qty")
            if quantity <= 0:
                raise ValueError("approved_qty must be positive")
            object.__setattr__(self, "approved_qty", quantity)

        if self.decision is RiskDecisionKind.APPROVED:
            if reasons:
                raise ValueError("approved decision excludes rejection reasons")
            if quantity is None:
                raise ValueError("approved decision requires approved_qty")
            object.__setattr__(self, "approval_token", _text(self.approval_token, "approval_token"))
        elif self.decision is RiskDecisionKind.REJECTED:
            if not reasons:
                raise ValueError("rejected decision requires at least one reason")
            if quantity is not None or self.approval_token is not None:
                raise ValueError("rejected decision excludes approved_qty and approval_token")
        else:
            if not reasons:
                raise ValueError("reduced decision requires at least one reason")
            if quantity is None:
                raise ValueError("reduced decision requires approved_qty")
            if self.approval_token is not None:
                raise ValueError("approval_token is present only for APPROVED decisions")

    @property
    def reference(self) -> str:
        """Canonical SHA-256 identity for this exact risk decision."""
        return CanonicalCodec.fingerprint(
            "algofortis-risk-decision/v1",
            (
                ("intent_id", self.intent_id),
                ("decision", self.decision),
                ("reasons", self.reasons),
                ("risk_rule_version", self.risk_rule_version),
                ("limits_snapshot_id", self.limits_snapshot_id),
                ("approved_qty", self.approved_qty),
                ("approval_token", self.approval_token),
            ),
        )


def client_order_id_for_intent(intent_id: str) -> str:
    """Derive the idempotent client order identity only from intent identity."""
    normalized = _text(intent_id, "intent_id")
    digest = CanonicalCodec.fingerprint(
        "algofortis-client-order-id/v1",
        (("intent_id", normalized),),
    )
    return f"af2_co_{digest}"


_APPROVED_ORDER_AUTHORITY = object()


@dataclass(frozen=True, slots=True, init=False)
class ApprovedOrder:
    """Opaque execution capability constructible only through RiskGateV2."""

    client_order_id: str
    intent_id: str
    risk_decision_ref: str
    run_mode: RunMode
    expires_at: datetime
    _intent: OrderIntent

    def __init__(
        self,
        *,
        client_order_id: str,
        intent_id: str,
        risk_decision_ref: str,
        run_mode: RunMode,
        expires_at: datetime,
        _intent: OrderIntent | None = None,
        _authority: object | None = None,
    ) -> None:
        if _authority is not _APPROVED_ORDER_AUTHORITY:
            raise TypeError("ApprovedOrder can only be constructed by RiskGateV2")
        if not isinstance(_intent, OrderIntent):
            raise TypeError("RiskGateV2 must supply the originating OrderIntent")
        client_id = _text(client_order_id, "client_order_id")
        normalized_intent = _text(intent_id, "intent_id")
        decision_ref = _text(risk_decision_ref, "risk_decision_ref")
        if len(decision_ref) != 64 or any(ch not in "0123456789abcdef" for ch in decision_ref.lower()):
            raise ValueError("risk_decision_ref must be a 64-character hexadecimal fingerprint")
        if not isinstance(run_mode, RunMode):
            raise TypeError("run_mode must be a RunMode")
        expiry = _aware(expires_at, "expires_at")
        if normalized_intent != _intent.intent_id:
            raise ValueError("ApprovedOrder intent identity must match originating OrderIntent")
        if run_mode is not _intent.run_mode:
            raise ValueError("ApprovedOrder run_mode must match originating OrderIntent")
        if expiry != _intent.valid_until:
            raise ValueError("ApprovedOrder expiry must match originating OrderIntent TTL")
        if client_id != client_order_id_for_intent(normalized_intent):
            raise ValueError("client_order_id must be deterministically derived from intent_id")

        object.__setattr__(self, "client_order_id", client_id)
        object.__setattr__(self, "intent_id", normalized_intent)
        object.__setattr__(self, "risk_decision_ref", decision_ref.lower())
        object.__setattr__(self, "run_mode", run_mode)
        object.__setattr__(self, "expires_at", expiry)
        object.__setattr__(self, "_intent", _intent)

    @property
    def intent(self) -> OrderIntent:
        return self._intent


def _mint_approved_order(
    *,
    client_order_id: str,
    intent: OrderIntent,
    risk_decision_ref: str,
) -> ApprovedOrder:
    """Module-private mint used exclusively by the central risk gate."""
    return ApprovedOrder(
        client_order_id=client_order_id,
        intent_id=intent.intent_id,
        risk_decision_ref=risk_decision_ref,
        run_mode=intent.run_mode,
        expires_at=intent.valid_until,
        _intent=intent,
        _authority=_APPROVED_ORDER_AUTHORITY,
    )


__all__ = [
    "RunMode",
    "OrderSource",
    "RiskDecisionKind",
    "OrderIntent",
    "RiskDecision",
    "ApprovedOrder",
    "client_order_id_for_intent",
]
