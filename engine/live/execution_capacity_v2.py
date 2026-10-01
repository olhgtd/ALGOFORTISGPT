"""Trusted execution-capacity gate for V2 Live entries.

This service can only further restrict a genuine RiskGate ApprovedOrder. It does
not mint approval, choose trades, or call a broker. Shared cash is reserved in
the durable V9 journal so simultaneous instruments cannot consume the same
broker-account capacity independently.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol

from engine.orders.contracts_v2 import ApprovedOrder, RunMode
from engine.persistence.live_execution_store_v2 import (
    LiveExecutionCapacityReservation,
    LiveExecutionStoreV2,
)


class LiveExecutionCapacityBlocked(RuntimeError):
    """Raised when current trusted evidence cannot prove execution capacity."""


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _aware(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


def _money(value: object, field: str, *, allow_zero: bool = False) -> Decimal:
    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite decimal") from exc
    if not amount.is_finite() or amount < 0 or (amount == 0 and not allow_zero):
        comparator = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{field} must be {comparator}")
    return amount


@dataclass(frozen=True, slots=True)
class LiveExecutionCapacityEvidence:
    broker_id: str
    broker_account_ref: str
    instrument_scope: str
    required_cash: Decimal | int | str
    available_cash: Decimal | int | str
    funds_evidence_ref: str
    observed_at: datetime
    freshness_verified: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "broker_id", _text(self.broker_id, "broker_id"))
        object.__setattr__(self, "broker_account_ref", _text(self.broker_account_ref, "broker_account_ref"))
        object.__setattr__(self, "instrument_scope", _text(self.instrument_scope, "instrument_scope"))
        object.__setattr__(self, "required_cash", _money(self.required_cash, "required_cash"))
        object.__setattr__(self, "available_cash", _money(self.available_cash, "available_cash", allow_zero=True))
        object.__setattr__(self, "funds_evidence_ref", _text(self.funds_evidence_ref, "funds_evidence_ref"))
        object.__setattr__(self, "observed_at", _aware(self.observed_at, "observed_at"))
        if not isinstance(self.freshness_verified, bool):
            raise TypeError("freshness_verified must be bool")


class LiveExecutionCapacityEvidenceProvider(Protocol):
    def current(self, order: ApprovedOrder, now: datetime) -> LiveExecutionCapacityEvidence: ...


class JournalLiveExecutionCapacityGate:
    """Atomically reserves trusted shared broker-account capacity before Live mutation."""

    def __init__(
        self,
        *,
        journal: LiveExecutionStoreV2,
        evidence_provider: LiveExecutionCapacityEvidenceProvider,
    ) -> None:
        if not isinstance(journal, LiveExecutionStoreV2):
            raise TypeError("journal must be LiveExecutionStoreV2")
        if not callable(getattr(evidence_provider, "current", None)):
            raise TypeError("evidence_provider must provide current(order, now)")
        self._journal = journal
        self._provider = evidence_provider

    def reserve(self, order: ApprovedOrder, *, now: datetime) -> str:
        if not isinstance(order, ApprovedOrder):
            raise TypeError("order must be ApprovedOrder")
        if order.run_mode is not RunMode.LIVE:
            raise LiveExecutionCapacityBlocked("execution capacity is only valid for RunMode.LIVE")
        current_time = _aware(now, "now")
        try:
            evidence = self._provider.current(order, current_time)
        except Exception as exc:
            raise LiveExecutionCapacityBlocked("capacity evidence unavailable") from exc
        if not isinstance(evidence, LiveExecutionCapacityEvidence):
            raise LiveExecutionCapacityBlocked("capacity evidence is invalid")
        if evidence.freshness_verified is not True:
            raise LiveExecutionCapacityBlocked("fresh capacity evidence is required")
        if evidence.observed_at > current_time:
            raise LiveExecutionCapacityBlocked("capacity evidence cannot be from the future")

        reservation = LiveExecutionCapacityReservation(
            broker_id=evidence.broker_id,
            broker_account_ref=evidence.broker_account_ref,
            client_order_id=order.client_order_id,
            instrument_scope=evidence.instrument_scope,
            required_cash=evidence.required_cash,
            funds_evidence_ref=evidence.funds_evidence_ref,
            created_at_utc=current_time,
        )
        try:
            accepted = self._journal.try_reserve_capacity(
                reservation,
                available_cash=evidence.available_cash,
            )
        except Exception as exc:
            if isinstance(exc, LiveExecutionCapacityBlocked):
                raise
            raise LiveExecutionCapacityBlocked("capacity reservation failed closed") from exc
        if accepted is not True:
            raise LiveExecutionCapacityBlocked("insufficient unreserved account cash")
        return evidence.funds_evidence_ref

    def release(
        self,
        client_order_id: str,
        *,
        now: datetime,
        reason: str,
    ) -> bool:
        return self._journal.release_capacity_by_client(
            _text(client_order_id, "client_order_id"),
            released_at_utc=_aware(now, "now"),
            reason=_text(reason, "reason"),
        )


__all__ = [
    "JournalLiveExecutionCapacityGate",
    "LiveExecutionCapacityBlocked",
    "LiveExecutionCapacityEvidence",
    "LiveExecutionCapacityEvidenceProvider",
]
