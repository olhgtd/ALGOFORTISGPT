"""Immutable RiskGate snapshot evidence contracts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import re
from types import MappingProxyType
from typing import Mapping

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _aware(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


def _non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be an int")
    if value < 0:
        raise ValueError(f"{field} must be non-negative")
    return value


def _text_tuple(value: object, field: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"{field} must be a tuple")
    normalized = tuple(_text(item, field) for item in value)
    if not allow_empty and not normalized:
        raise ValueError(f"{field} must not be empty")
    return normalized


def _decimal_mapping(value: object, field: str) -> Mapping[str, Decimal]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field} must be a mapping")
    normalized: dict[str, Decimal] = {}
    for key, raw in value.items():
        name = _text(key, f"{field}.key")
        if isinstance(raw, bool):
            raise TypeError(f"{field}[{name}] must be numeric")
        try:
            amount = raw if isinstance(raw, Decimal) else Decimal(str(raw))
        except Exception as exc:
            raise TypeError(f"{field}[{name}] must be numeric") from exc
        if not amount.is_finite() or amount <= 0:
            raise ValueError(f"{field}[{name}] must be positive and finite")
        normalized[name] = amount
    return MappingProxyType(normalized)


@dataclass(frozen=True, slots=True)
class RiskSnapshot:
    snapshot_id: str
    schema_version: str
    generated_at_utc: datetime
    input_fingerprint: str
    risk_rule_version: str
    limits_snapshot_id: str
    account_authority_ref: str
    strategy_eligibility_ref: str
    portfolio_state_ref: str
    entry_policy_ref: str
    operational_state: str
    kill_switch_state: str
    hold_state: str
    allowed_instrument_scope: tuple[str, ...]
    allowed_side_scope: tuple[str, ...]
    quantity_ceiling_by_scope: Mapping[str, Decimal]
    risk_budget_evidence: str
    feed_health_ref: str
    latest_market_sequence: int
    source_versions: tuple[str, ...]
    builder_health_generation: int

    def __post_init__(self) -> None:
        for field in (
            "snapshot_id",
            "schema_version",
            "risk_rule_version",
            "limits_snapshot_id",
            "account_authority_ref",
            "strategy_eligibility_ref",
            "portfolio_state_ref",
            "entry_policy_ref",
            "operational_state",
            "kill_switch_state",
            "hold_state",
            "risk_budget_evidence",
            "feed_health_ref",
        ):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        object.__setattr__(self, "generated_at_utc", _aware(self.generated_at_utc, "generated_at_utc"))
        fingerprint = _text(self.input_fingerprint, "input_fingerprint").lower()
        if not _HEX64.fullmatch(fingerprint):
            raise ValueError("input_fingerprint must be lowercase 64-character hex")
        object.__setattr__(self, "input_fingerprint", fingerprint)
        object.__setattr__(self, "allowed_instrument_scope", _text_tuple(self.allowed_instrument_scope, "allowed_instrument_scope"))
        sides = tuple(side.upper() for side in _text_tuple(self.allowed_side_scope, "allowed_side_scope"))
        if any(side not in {"BUY", "SELL"} for side in sides):
            raise ValueError("allowed_side_scope supports BUY/SELL only")
        object.__setattr__(self, "allowed_side_scope", sides)
        object.__setattr__(self, "quantity_ceiling_by_scope", _decimal_mapping(self.quantity_ceiling_by_scope, "quantity_ceiling_by_scope"))
        object.__setattr__(self, "latest_market_sequence", _non_negative_int(self.latest_market_sequence, "latest_market_sequence"))
        object.__setattr__(self, "source_versions", _text_tuple(self.source_versions, "source_versions"))
        object.__setattr__(self, "builder_health_generation", _non_negative_int(self.builder_health_generation, "builder_health_generation"))

    @property
    def reference(self) -> str:
        payload = {
            "snapshot_id": self.snapshot_id,
            "schema_version": self.schema_version,
            "generated_at_utc": self.generated_at_utc.isoformat(),
            "input_fingerprint": self.input_fingerprint,
            "risk_rule_version": self.risk_rule_version,
            "limits_snapshot_id": self.limits_snapshot_id,
            "account_authority_ref": self.account_authority_ref,
            "strategy_eligibility_ref": self.strategy_eligibility_ref,
            "portfolio_state_ref": self.portfolio_state_ref,
            "entry_policy_ref": self.entry_policy_ref,
            "operational_state": self.operational_state,
            "kill_switch_state": self.kill_switch_state,
            "hold_state": self.hold_state,
            "allowed_instrument_scope": self.allowed_instrument_scope,
            "allowed_side_scope": self.allowed_side_scope,
            "quantity_ceiling_by_scope": {key: str(value) for key, value in sorted(self.quantity_ceiling_by_scope.items())},
            "risk_budget_evidence": self.risk_budget_evidence,
            "feed_health_ref": self.feed_health_ref,
            "latest_market_sequence": self.latest_market_sequence,
            "source_versions": self.source_versions,
            "builder_health_generation": self.builder_health_generation,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = ["RiskSnapshot"]
