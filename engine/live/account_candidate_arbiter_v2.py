"""Deterministic pre-execution arbitration for one broker-account capital domain.

The arbiter may only rank/restrict candidates that already exist. It cannot mint
ApprovedOrder values, reserve capital, call RiskGate, or mutate a broker. All
ranking inputs are deterministic pre-AI evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _aware(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


def _priority(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be int")
    if value < 0:
        raise ValueError(f"{field} must be non-negative")
    return value


def _decimal(value: object, field: str) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be a finite decimal")
    return result


@dataclass(frozen=True, slots=True)
class AccountCapitalDomainKey:
    broker_id: str
    broker_account_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "broker_id", _text(self.broker_id, "broker_id"))
        object.__setattr__(
            self,
            "broker_account_ref",
            _text(self.broker_account_ref, "broker_account_ref"),
        )


@dataclass(frozen=True, slots=True)
class AccountCandidateEvidence:
    domain_key: AccountCapitalDomainKey
    candidate_id: str
    hard_eligible: bool
    exposure_allowed: bool
    portfolio_priority: int
    strategy_priority: int
    edge_quality: Decimal | int | str
    capital_efficiency: Decimal | int | str
    signal_at: datetime
    policy_ref: str

    def __post_init__(self) -> None:
        if not isinstance(self.domain_key, AccountCapitalDomainKey):
            raise TypeError("domain_key must be AccountCapitalDomainKey")
        object.__setattr__(self, "candidate_id", _text(self.candidate_id, "candidate_id"))
        if not isinstance(self.hard_eligible, bool):
            raise TypeError("hard_eligible must be bool")
        if not isinstance(self.exposure_allowed, bool):
            raise TypeError("exposure_allowed must be bool")
        object.__setattr__(
            self,
            "portfolio_priority",
            _priority(self.portfolio_priority, "portfolio_priority"),
        )
        object.__setattr__(
            self,
            "strategy_priority",
            _priority(self.strategy_priority, "strategy_priority"),
        )
        object.__setattr__(self, "edge_quality", _decimal(self.edge_quality, "edge_quality"))
        object.__setattr__(
            self,
            "capital_efficiency",
            _decimal(self.capital_efficiency, "capital_efficiency"),
        )
        object.__setattr__(self, "signal_at", _aware(self.signal_at, "signal_at"))
        object.__setattr__(self, "policy_ref", _text(self.policy_ref, "policy_ref"))


class LiveAccountCandidateArbiterV2:
    """Ranks eligible candidates deterministically inside exactly one account domain."""

    def __init__(self, domain_key: AccountCapitalDomainKey) -> None:
        if not isinstance(domain_key, AccountCapitalDomainKey):
            raise TypeError("domain_key must be AccountCapitalDomainKey")
        self._domain_key = domain_key

    @property
    def domain_key(self) -> AccountCapitalDomainKey:
        return self._domain_key

    def rank(self, candidates: Iterable[AccountCandidateEvidence]) -> tuple[AccountCandidateEvidence, ...]:
        values = tuple(candidates)
        if not all(isinstance(item, AccountCandidateEvidence) for item in values):
            raise TypeError("candidates must contain AccountCandidateEvidence values")
        if any(item.domain_key != self._domain_key for item in values):
            raise ValueError("candidate domain does not match arbiter domain")

        eligible = (
            item
            for item in values
            if item.hard_eligible is True and item.exposure_allowed is True
        )
        return tuple(sorted(eligible, key=self._sort_key))

    @staticmethod
    def _sort_key(item: AccountCandidateEvidence) -> tuple[object, ...]:
        # Lower owner priority numbers win; higher quality/efficiency wins.
        # Signal time then stable identity make the final order schedule-independent.
        return (
            item.portfolio_priority,
            item.strategy_priority,
            -item.edge_quality,
            -item.capital_efficiency,
            item.signal_at,
            item.candidate_id,
        )


__all__ = [
    "AccountCandidateEvidence",
    "AccountCapitalDomainKey",
    "LiveAccountCandidateArbiterV2",
]
