"""Sticky audited portfolio circuit breaker for Phase 7."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from threading import RLock
from typing import Protocol


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


class CircuitAuditSink(Protocol):
    def write(self, event_type: str, payload: dict[str, object]) -> None: ...


@dataclass(frozen=True, slots=True)
class PortfolioCircuitBreakerPolicy:
    policy_id: str
    version: str
    max_daily_loss: Decimal
    max_drawdown: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _text(self.policy_id, "policy_id"))
        object.__setattr__(self, "version", _text(self.version, "version"))
        object.__setattr__(
            self,
            "max_daily_loss",
            _decimal(self.max_daily_loss, "max_daily_loss", positive=True),
        )
        object.__setattr__(
            self,
            "max_drawdown",
            _decimal(self.max_drawdown, "max_drawdown", positive=True),
        )

    @property
    def reference(self) -> str:
        return f"{self.policy_id}@{self.version}"


@dataclass(frozen=True, slots=True)
class PortfolioRiskMetrics:
    daily_pnl: Decimal
    drawdown: Decimal
    observed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "daily_pnl", _decimal(self.daily_pnl, "daily_pnl"))
        object.__setattr__(
            self,
            "drawdown",
            _decimal(self.drawdown, "drawdown", non_negative=True),
        )
        object.__setattr__(self, "observed_at", _aware(self.observed_at, "observed_at"))


@dataclass(frozen=True, slots=True)
class PortfolioResetAuthority:
    allowed: bool
    reference: str

    def __post_init__(self) -> None:
        if not isinstance(self.allowed, bool):
            raise TypeError("allowed must be bool")
        object.__setattr__(self, "reference", _text(self.reference, "reference"))


@dataclass(frozen=True, slots=True)
class CircuitDecision:
    entries_allowed: bool
    latched: bool
    reason: str
    policy_ref: str


class PortfolioCircuitBreaker:
    def __init__(
        self,
        policy: PortfolioCircuitBreakerPolicy,
        *,
        audit_sink: CircuitAuditSink,
    ) -> None:
        if not isinstance(policy, PortfolioCircuitBreakerPolicy):
            raise TypeError("policy must be PortfolioCircuitBreakerPolicy")
        if not callable(getattr(audit_sink, "write", None)):
            raise TypeError("audit_sink must provide write(event_type, payload)")
        self._policy = policy
        self._audit = audit_sink
        self._latched = False
        self._audit_failure_block = False
        self._lock = RLock()

    @property
    def entries_allowed(self) -> bool:
        with self._lock:
            return not self._latched and not self._audit_failure_block

    def _breach_reason(self, metrics: PortfolioRiskMetrics) -> str | None:
        if metrics.daily_pnl <= -self._policy.max_daily_loss:
            return "DAILY_LOSS_LIMIT_BREACHED"
        if metrics.drawdown >= self._policy.max_drawdown:
            return "DRAWDOWN_LIMIT_BREACHED"
        return None

    def _decision(self, reason: str) -> CircuitDecision:
        return CircuitDecision(
            self.entries_allowed,
            self._latched,
            reason,
            self._policy.reference,
        )

    def observe(self, metrics: PortfolioRiskMetrics) -> CircuitDecision:
        if not isinstance(metrics, PortfolioRiskMetrics):
            raise TypeError("metrics must be PortfolioRiskMetrics")
        with self._lock:
            if self._latched:
                return self._decision("CIRCUIT_LATCHED")
            if self._audit_failure_block:
                return self._decision("AUDIT_FAILURE_BLOCKED")
            reason = self._breach_reason(metrics)
            if reason is None:
                return self._decision("HEALTHY")
            try:
                self._audit.write(
                    "PORTFOLIO_CIRCUIT_LATCHED",
                    {
                        "reason": reason,
                        "policy_ref": self._policy.reference,
                        "observed_at": metrics.observed_at.isoformat(),
                    },
                )
            except Exception:
                self._audit_failure_block = True
                return self._decision("AUDIT_WRITE_FAILED")
            self._latched = True
            return self._decision(reason)

    def manual_reset(
        self,
        authority: PortfolioResetAuthority,
        metrics: PortfolioRiskMetrics,
    ) -> CircuitDecision:
        if not isinstance(authority, PortfolioResetAuthority):
            raise TypeError("authority must be PortfolioResetAuthority")
        if not isinstance(metrics, PortfolioRiskMetrics):
            raise TypeError("metrics must be PortfolioRiskMetrics")
        with self._lock:
            if authority.allowed is not True:
                return self._decision("RESET_AUTHORITY_DENIED")
            if self._breach_reason(metrics) is not None:
                return self._decision("RESET_METRICS_NOT_CLEAN")
            try:
                self._audit.write(
                    "PORTFOLIO_CIRCUIT_MANUAL_RESET",
                    {
                        "authority_ref": authority.reference,
                        "policy_ref": self._policy.reference,
                        "observed_at": metrics.observed_at.isoformat(),
                    },
                )
            except Exception:
                self._audit_failure_block = True
                return self._decision("AUDIT_WRITE_FAILED")
            self._latched = False
            self._audit_failure_block = False
            return self._decision("MANUAL_RESET_ACCEPTED")


__all__ = [
    "CircuitDecision",
    "PortfolioCircuitBreaker",
    "PortfolioCircuitBreakerPolicy",
    "PortfolioResetAuthority",
    "PortfolioRiskMetrics",
]
