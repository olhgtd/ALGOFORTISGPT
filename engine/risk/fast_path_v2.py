"""Deterministic candidate-time RiskEvaluator backed by immutable snapshots.

No database, broker, LLM, research, backtest, or synchronous rebuild dependency is
permitted here.  Missing or ambiguous authority returns deterministic rejection.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Callable, Protocol

from engine.core.numeric import as_decimal
from engine.core.runtime import Clock
from engine.orders.contracts_v2 import OrderIntent
from engine.portfolio.model import InstrumentIdentity
from engine.risk.gate_v2 import RiskEvaluation
from engine.risk.snapshot_contracts_v2 import RiskSnapshot
from engine.risk.snapshot_publication_v2 import RiskSnapshotPublication


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _aware(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware datetime")
    return value


def _non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be int")
    if value < 0:
        raise ValueError(f"{field} must be non-negative")
    return value


@dataclass(frozen=True, slots=True)
class CurrentQuoteEvidence:
    instrument_ref: InstrumentIdentity
    observed_at: datetime
    market_sequence: int
    bid: Decimal | int | str
    ask: Decimal | int | str
    source_ref: str

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_ref, InstrumentIdentity):
            raise TypeError("instrument_ref must be InstrumentIdentity")
        object.__setattr__(self, "observed_at", _aware(self.observed_at, "observed_at"))
        object.__setattr__(self, "market_sequence", _non_negative_int(self.market_sequence, "market_sequence"))
        bid = as_decimal(self.bid, "bid")
        ask = as_decimal(self.ask, "ask")
        if bid <= 0 or ask <= 0 or ask < bid:
            raise ValueError("quote requires positive bid/ask with ask >= bid")
        object.__setattr__(self, "bid", bid)
        object.__setattr__(self, "ask", ask)
        object.__setattr__(self, "source_ref", _text(self.source_ref, "source_ref"))


class CurrentQuoteProvider(Protocol):
    def current(self, instrument_ref: InstrumentIdentity) -> CurrentQuoteEvidence: ...


class ReplayGuard(Protocol):
    def claim(self, intent_id: str, snapshot_id: str, market_sequence: int) -> bool: ...


class SnapshotFreshnessPolicy(Protocol):
    reference: str
    def is_fresh(self, snapshot: RiskSnapshot, now: datetime) -> bool: ...


class CandidatePricePolicy(Protocol):
    reference: str
    def allows(self, intent: OrderIntent, quote: CurrentQuoteEvidence) -> bool: ...


class OperationalEntryPolicy(Protocol):
    reference: str
    def entries_allowed(self, snapshot: RiskSnapshot) -> bool: ...


class FastPathRiskEvaluator:
    def __init__(
        self,
        *,
        publication: RiskSnapshotPublication,
        quote_provider: CurrentQuoteProvider,
        replay_guard: ReplayGuard,
        freshness_policy: SnapshotFreshnessPolicy,
        price_policy: CandidatePricePolicy,
        entry_state_policy: OperationalEntryPolicy,
        clock: Clock,
        active_risk_rule_version: str,
        active_limits_snapshot_id: str,
        active_builder_health_generation: Callable[[], int],
        latency_policy_ref: str,
    ) -> None:
        if not isinstance(publication, RiskSnapshotPublication):
            raise TypeError("publication must be RiskSnapshotPublication")
        for obj, method, name in (
            (quote_provider, "current", "quote_provider"),
            (replay_guard, "claim", "replay_guard"),
            (freshness_policy, "is_fresh", "freshness_policy"),
            (price_policy, "allows", "price_policy"),
            (entry_state_policy, "entries_allowed", "entry_state_policy"),
        ):
            if not callable(getattr(obj, method, None)):
                raise TypeError(f"{name} must provide {method}()")
        if not callable(getattr(clock, "now_utc", None)):
            raise TypeError("clock must provide now_utc()")
        if not callable(active_builder_health_generation):
            raise TypeError("active_builder_health_generation must be callable")
        self._publication = publication
        self._quote_provider = quote_provider
        self._replay_guard = replay_guard
        self._freshness_policy = freshness_policy
        self._price_policy = price_policy
        self._entry_state_policy = entry_state_policy
        self._clock = clock
        self._active_risk_rule_version = _text(active_risk_rule_version, "active_risk_rule_version")
        self._active_limits_snapshot_id = _text(active_limits_snapshot_id, "active_limits_snapshot_id")
        self._active_builder_health_generation = active_builder_health_generation
        self._latency_policy_ref = _text(latency_policy_ref, "latency_policy_ref")

    def evaluate(self, intent: OrderIntent) -> RiskEvaluation:
        if not isinstance(intent, OrderIntent):
            raise TypeError("intent must be OrderIntent")
        snapshot = self._publication.current()
        if snapshot is None:
            return self._reject("snapshot_unavailable")

        now = self._clock.now_utc()
        if now >= intent.valid_until:
            return self._reject("intent_expired", snapshot=snapshot)
        try:
            if self._freshness_policy.is_fresh(snapshot, now) is not True:
                return self._reject("snapshot_stale", snapshot=snapshot)
        except Exception:
            return self._reject("snapshot_freshness_unavailable", snapshot=snapshot)

        try:
            active_generation = _non_negative_int(
                self._active_builder_health_generation(),
                "active_builder_health_generation",
            )
        except Exception:
            return self._reject("builder_generation_unavailable", snapshot=snapshot)
        if snapshot.builder_health_generation != active_generation:
            return self._reject("builder_generation_mismatch", snapshot=snapshot)
        if snapshot.risk_rule_version != self._active_risk_rule_version:
            return self._reject("risk_rule_version_mismatch", snapshot=snapshot)
        if snapshot.limits_snapshot_id != self._active_limits_snapshot_id:
            return self._reject("limits_snapshot_mismatch", snapshot=snapshot)

        try:
            if self._entry_state_policy.entries_allowed(snapshot) is not True:
                return self._reject("entries_not_allowed", snapshot=snapshot)
        except Exception:
            return self._reject("entry_state_policy_unavailable", snapshot=snapshot)
        if snapshot.kill_switch_state.upper() != "CLEAR":
            return self._reject("kill_switch_active", snapshot=snapshot)
        if snapshot.hold_state.upper() != "CLEAR":
            return self._reject("hold_active", snapshot=snapshot)
        if intent.instrument_ref.segment == "options" and intent.side != "BUY":
            return self._reject("options_buy_only", snapshot=snapshot)
        if intent.side not in snapshot.allowed_side_scope:
            return self._reject("side_scope_rejected", snapshot=snapshot)

        scope = intent.instrument_ref.underlying or intent.instrument_ref.instrument
        if scope not in snapshot.allowed_instrument_scope:
            return self._reject("instrument_scope_rejected", snapshot=snapshot)
        ceiling = snapshot.quantity_ceiling_by_scope.get(scope)
        if ceiling is None:
            return self._reject("quantity_scope_unavailable", snapshot=snapshot)
        if intent.qty > ceiling:
            return self._reject("quantity_ceiling", snapshot=snapshot)

        candidate_sequence = intent.provenance.get("market_sequence")
        try:
            candidate_sequence = _non_negative_int(candidate_sequence, "market_sequence")
        except Exception:
            return self._reject("candidate_market_sequence_missing", snapshot=snapshot)
        if snapshot.latest_market_sequence < candidate_sequence:
            return self._reject("snapshot_sequence_behind_candidate", snapshot=snapshot)

        try:
            quote = self._quote_provider.current(intent.instrument_ref)
        except Exception:
            return self._reject("quote_unavailable", snapshot=snapshot)
        if not isinstance(quote, CurrentQuoteEvidence):
            return self._reject("quote_invalid", snapshot=snapshot)
        if quote.instrument_ref != intent.instrument_ref:
            return self._reject("quote_instrument_mismatch", snapshot=snapshot)
        if quote.market_sequence < candidate_sequence:
            return self._reject(
                "quote_sequence_behind_candidate",
                snapshot=snapshot,
                market_sequence=quote.market_sequence,
            )

        try:
            claimed = self._replay_guard.claim(
                intent.intent_id,
                snapshot.snapshot_id,
                quote.market_sequence,
            )
        except Exception:
            return self._reject(
                "replay_guard_unavailable",
                snapshot=snapshot,
                market_sequence=quote.market_sequence,
            )
        if claimed is not True:
            return self._reject(
                "duplicate_or_replay",
                snapshot=snapshot,
                market_sequence=quote.market_sequence,
            )

        try:
            price_allowed = self._price_policy.allows(intent, quote)
        except Exception:
            return self._reject(
                "price_policy_unavailable",
                snapshot=snapshot,
                market_sequence=quote.market_sequence,
            )
        if price_allowed is not True:
            return self._reject(
                "price_policy_rejected",
                snapshot=snapshot,
                market_sequence=quote.market_sequence,
            )

        return RiskEvaluation.approved(
            approved_qty=intent.qty,
            risk_rule_version=snapshot.risk_rule_version,
            limits_snapshot_id=snapshot.limits_snapshot_id,
            risk_snapshot_id=snapshot.snapshot_id,
            market_sequence_ref=str(quote.market_sequence),
            latency_policy_ref=self._latency_policy_ref,
        )

    def _reject(
        self,
        reason: str,
        *,
        snapshot: RiskSnapshot | None = None,
        market_sequence: int | None = None,
    ) -> RiskEvaluation:
        return RiskEvaluation.rejected(
            reason,
            risk_rule_version=(snapshot.risk_rule_version if snapshot is not None else self._active_risk_rule_version),
            limits_snapshot_id=(snapshot.limits_snapshot_id if snapshot is not None else self._active_limits_snapshot_id),
            risk_snapshot_id=(snapshot.snapshot_id if snapshot is not None else None),
            market_sequence_ref=(str(market_sequence) if market_sequence is not None else None),
            latency_policy_ref=self._latency_policy_ref,
        )


__all__ = [
    "CandidatePricePolicy",
    "CurrentQuoteEvidence",
    "CurrentQuoteProvider",
    "FastPathRiskEvaluator",
    "OperationalEntryPolicy",
    "ReplayGuard",
    "SnapshotFreshnessPolicy",
]
