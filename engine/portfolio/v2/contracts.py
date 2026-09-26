"""Pure immutable contracts for AlgoFortis Phase-7 portfolio risk."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from engine.portfolio.model import AccountSnapshot, InstrumentIdentity


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _decimal(
    value: object,
    field: str,
    *,
    positive: bool = False,
    non_negative: bool = False,
) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(f"{field} must be Decimal-compatible without float")
    if not isinstance(value, Decimal):
        try:
            value = Decimal(value)  # type: ignore[arg-type]
        except Exception as exc:
            raise TypeError(f"{field} must be Decimal-compatible") from exc
    if not value.is_finite():
        raise ValueError(f"{field} must be finite")
    if positive and value <= 0:
        raise ValueError(f"{field} must be positive")
    if non_negative and value < 0:
        raise ValueError(f"{field} must be non-negative")
    return value


def _aware(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class PortfolioBudgetPolicy:
    policy_id: str
    version: str
    owner_capital_limit: Decimal
    user_id: str
    user_budget: Decimal
    strategy_budgets: Mapping[str, Decimal]

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _text(self.policy_id, "policy_id"))
        object.__setattr__(self, "version", _text(self.version, "version"))
        object.__setattr__(self, "user_id", _text(self.user_id, "user_id"))
        owner = _decimal(self.owner_capital_limit, "owner_capital_limit", positive=True)
        user = _decimal(self.user_budget, "user_budget", positive=True)
        if user > owner:
            raise ValueError("user_budget cannot exceed owner_capital_limit")
        if not isinstance(self.strategy_budgets, Mapping) or not self.strategy_budgets:
            raise ValueError("strategy_budgets must be a non-empty mapping")
        normalized: dict[str, Decimal] = {}
        for key, raw in self.strategy_budgets.items():
            strategy = _text(key, "strategy_id")
            amount = _decimal(raw, f"strategy budget {strategy}", positive=True)
            if amount > user:
                raise ValueError(f"strategy budget {strategy} cannot exceed user_budget")
            normalized[strategy] = amount
        object.__setattr__(self, "owner_capital_limit", owner)
        object.__setattr__(self, "user_budget", user)
        object.__setattr__(self, "strategy_budgets", MappingProxyType(normalized))

    @property
    def reference(self) -> str:
        return f"{self.policy_id}@{self.version}"

    def strategy_budget(self, strategy_id: str) -> Decimal | None:
        return self.strategy_budgets.get(_text(strategy_id, "strategy_id"))


@dataclass(frozen=True, slots=True)
class CapitalReservation:
    reservation_id: str
    user_id: str
    strategy_id: str
    amount: Decimal
    created_at: datetime
    policy_ref: str
    released_at: datetime | None = None

    def __post_init__(self) -> None:
        for field in ("reservation_id", "user_id", "strategy_id", "policy_ref"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        object.__setattr__(self, "amount", _decimal(self.amount, "amount", positive=True))
        object.__setattr__(self, "created_at", _aware(self.created_at, "created_at"))
        if self.released_at is not None:
            released = _aware(self.released_at, "released_at")
            if released < self.created_at:
                raise ValueError("released_at cannot precede created_at")
            object.__setattr__(self, "released_at", released)

    @property
    def active(self) -> bool:
        return self.released_at is None


@dataclass(frozen=True, slots=True)
class ReservationSnapshot:
    policy_ref: str
    active: Mapping[str, CapitalReservation]
    released: Mapping[str, CapitalReservation]
    total_reserved: Decimal
    reserved_by_strategy: Mapping[str, Decimal]

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_ref", _text(self.policy_ref, "policy_ref"))
        object.__setattr__(self, "active", MappingProxyType(dict(self.active)))
        object.__setattr__(self, "released", MappingProxyType(dict(self.released)))
        object.__setattr__(
            self,
            "total_reserved",
            _decimal(self.total_reserved, "total_reserved", non_negative=True),
        )
        object.__setattr__(
            self,
            "reserved_by_strategy",
            MappingProxyType(
                {
                    key: _decimal(value, "reserved_by_strategy", non_negative=True)
                    for key, value in self.reserved_by_strategy.items()
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class PortfolioRiskContext:
    account: AccountSnapshot
    reference_price: Decimal
    contract_multiplier: Decimal
    baseline_qty: Decimal
    required_capital: Decimal
    reservation_id: str
    evaluated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.account, AccountSnapshot):
            raise TypeError("account must be AccountSnapshot")
        for field in (
            "reference_price",
            "contract_multiplier",
            "baseline_qty",
            "required_capital",
        ):
            object.__setattr__(
                self,
                field,
                _decimal(getattr(self, field), field, positive=True),
            )
        object.__setattr__(self, "reservation_id", _text(self.reservation_id, "reservation_id"))
        object.__setattr__(self, "evaluated_at", _aware(self.evaluated_at, "evaluated_at"))


@dataclass(frozen=True, slots=True)
class PortfolioExposurePolicy:
    policy_id: str
    version: str
    max_total_exposure: Decimal
    max_instrument_exposure: Decimal
    strategy_exposure_caps: Mapping[str, Decimal]

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _text(self.policy_id, "policy_id"))
        object.__setattr__(self, "version", _text(self.version, "version"))
        object.__setattr__(
            self,
            "max_total_exposure",
            _decimal(self.max_total_exposure, "max_total_exposure", positive=True),
        )
        object.__setattr__(
            self,
            "max_instrument_exposure",
            _decimal(
                self.max_instrument_exposure,
                "max_instrument_exposure",
                positive=True,
            ),
        )
        if not isinstance(self.strategy_exposure_caps, Mapping) or not self.strategy_exposure_caps:
            raise ValueError("strategy_exposure_caps must be a non-empty mapping")
        caps = {
            _text(key, "strategy_id"): _decimal(
                value,
                "strategy exposure cap",
                positive=True,
            )
            for key, value in self.strategy_exposure_caps.items()
        }
        object.__setattr__(self, "strategy_exposure_caps", MappingProxyType(caps))

    @property
    def reference(self) -> str:
        return f"{self.policy_id}@{self.version}"


@dataclass(frozen=True, slots=True)
class PortfolioExposureSnapshot:
    total_exposure: Decimal
    by_strategy: Mapping[str, Decimal]
    by_instrument: Mapping[InstrumentIdentity, Decimal]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "total_exposure",
            _decimal(self.total_exposure, "total_exposure", non_negative=True),
        )
        object.__setattr__(
            self,
            "by_strategy",
            MappingProxyType(
                {
                    key: _decimal(value, "strategy exposure", non_negative=True)
                    for key, value in self.by_strategy.items()
                }
            ),
        )
        object.__setattr__(
            self,
            "by_instrument",
            MappingProxyType(
                {
                    key: _decimal(value, "instrument exposure", non_negative=True)
                    for key, value in self.by_instrument.items()
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class RealizedPnlRecord:
    strategy_id: str
    amount: Decimal
    evidence_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "strategy_id", _text(self.strategy_id, "strategy_id"))
        object.__setattr__(self, "amount", _decimal(self.amount, "amount"))
        object.__setattr__(self, "evidence_ref", _text(self.evidence_ref, "evidence_ref"))


__all__ = [
    "CapitalReservation",
    "PortfolioBudgetPolicy",
    "PortfolioExposurePolicy",
    "PortfolioExposureSnapshot",
    "PortfolioRiskContext",
    "RealizedPnlRecord",
    "ReservationSnapshot",
]
