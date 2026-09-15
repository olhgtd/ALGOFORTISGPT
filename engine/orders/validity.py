"""Phase-4 Slice-1 strategy-owned pending-entry validity capability.

``PendingEntryValidityPolicy/v1`` is a SEPARATE optional strategy-owned
capability bound alongside ``StrategySignalGenerator`` (never a method on it,
per architecture-rules Rule 1 / Rule 6).  The core consumes its results
blindly and never understands ORB/EMA/RSI/breakout semantics.

Ownership split (frozen owner locks D1/D2/D3, Phase-4 preflight):
- STRATEGY owns whether the trading setup/thesis remains logically valid
  (``evaluate``).
- The strategy also freezes any immutable MECHANICAL validity evidence for a
  logical entry at approval time (``freeze_spec`` -> ``EntryValiditySpec``);
  the core lifecycle stores and enforces those mechanical fields
  (``valid_until_timestamp``, ``valid_through_session``).
- RISK LAYER owns account-level risk (Phase-3 Q56 reauthorization stays the
  risk-layer authority and is never evaluated here).
- ORDER LIFECYCLE owns pending state / expiry / cancel / terminal lifecycle.

Slice-1 mechanical fields are ONLY the unambiguous generic ones:
``valid_until_timestamp`` and ``valid_through_session`` (authoritative frozen
calendar identity + session date).  ``valid_for_bars`` is DEFERRED_CORE: there
is no frozen universal bar-count authority for multi-stream / multi-timeframe
strategies; a strategy may express its own N-bar semantics through its
evaluator/state.

Purity: ``evaluate`` MUST NOT mutate authoritative strategy state.  The engine
passes an isolated deep copy; any mutation of that copy is discarded.

No-lookahead: ``evaluate`` receives only the retained MOST-RECENT PRE-T
``MarketDataView`` (bars strictly before the execution opportunity T) and the
strategy state as of its last ``generate_signal`` decision.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Mapping

from engine.core.numeric import as_decimal
from engine.portfolio.model import InstrumentIdentity
from engine.reproducibility.codec import CanonicalCodec


class EntryValidityOutcome(str, Enum):
    """Deterministic strategy-owned validity decision consumed blindly by the core."""

    VALID = "VALID"
    INVALID = "INVALID"


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


@dataclass(frozen=True)
class EntryValiditySpec:
    """Immutable MECHANICAL validity evidence frozen by the bound validity policy.

    Created/finalized ONLY by ``PendingEntryValidityPolicy.freeze_spec`` from
    the current logical entry context at approval time; the core lifecycle
    stores and enforces these fields.  It never depends on approved quantity,
    RiskGate sizing, fill price, or future market evidence, and strategy
    validity values never travel through ``Signal.metadata``.

    ``valid_until_timestamp``: opportunity time strictly before this is
    mechanically valid; ``>=`` is mechanical expiry.

    ``valid_through_session``: frozen authoritative calendar identity +
    session date at approval; a later opportunity on the same calendar
    identity AND same session date is valid; anything else is expiry.

    An empty spec (all fields None) means "no additional mechanical
    constraints"; it is still distinguishable from no provider because the
    policy identity is stored alongside.
    """

    valid_until_timestamp: datetime | None = None
    calendar_identity: str | None = None
    session_date: date | None = None

    def __post_init__(self) -> None:
        if self.valid_until_timestamp is not None:
            _require_aware(self.valid_until_timestamp, "valid_until_timestamp")
        if (self.calendar_identity is None) != (self.session_date is None):
            raise ValueError("valid_through_session requires calendar identity and session date together")
        if self.calendar_identity is not None and not self.calendar_identity.strip():
            raise ValueError("calendar_identity must be a non-empty string")
        if self.session_date is not None and isinstance(self.session_date, datetime):
            raise TypeError("session_date must be a plain date")
        if self.calendar_identity is not None:
            object.__setattr__(self, "calendar_identity", self.calendar_identity.strip())

    @property
    def spec_identity(self) -> str:
        """Canonical identity over the frozen mechanical fields (never quantity/fill)."""
        return CanonicalCodec.fingerprint(
            "sentinelx-entry-validity-spec/v1",
            (
                ("valid_until", None if self.valid_until_timestamp is None else self.valid_until_timestamp),
                ("calendar_identity", self.calendar_identity),
                ("session_date", self.session_date),
            ),
        )


@dataclass(frozen=True)
class EntryValidityResult:
    """Deterministic strategy-owned validity result consumed blindly by the core.

    Reasons are STRATEGY/lifecycle reasons ONLY.  Engine risk reasons
    (``daily_loss_limit_exceeded``, ``portfolio_risk_exceeded``,
    ``insufficient_cost_adjusted_buying_power``, ...) are forbidden here and
    remain owned by their existing authorities (RiskGate / accounting).
    """

    policy_identity: str
    outcome: EntryValidityOutcome
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.policy_identity, str) or not self.policy_identity.strip():
            raise ValueError("policy_identity must be a non-empty string")
        if not isinstance(self.outcome, EntryValidityOutcome):
            raise TypeError("outcome must be an EntryValidityOutcome")
        object.__setattr__(self, "policy_identity", self.policy_identity.strip())
        if self.outcome is EntryValidityOutcome.VALID:
            if self.reason is not None:
                raise ValueError("VALID entry-validity result excludes a reason")
        elif self.reason is None or not self.reason.strip():
            raise ValueError("INVALID entry-validity result requires a non-empty deterministic reason")

    @property
    def evidence_identity(self) -> str:
        """Canonical identity referenced by the lifecycle terminal event."""
        return CanonicalCodec.fingerprint(
            "sentinelx-entry-validity-result/v1",
            (
                ("policy", self.policy_identity),
                ("outcome", self.outcome.value),
                ("reason", self.reason),
            ),
        )


@dataclass(frozen=True)
class EntryValidityContext:
    """Immutable logical-entry context supplied to the validity policy.

    ``entry_reference`` is the authoritative pre-order entry reference
    (MARKET = completed source close; LIMIT = planned limit) resolved exactly
    once at approval.  ``calendar_identity``/``session_date`` are the
    authoritative approval-time RiskDay evidence (used to freeze
    ``valid_through_session``); at later evaluation the frozen spec supplies
    them when the provider needs them.
    """

    strategy_id: str
    strategy_version: str
    identity: InstrumentIdentity
    timeframe: str
    originating_timestamp: datetime
    entry_reference: Decimal
    calendar_identity: str | None = None
    session_date: date | None = None

    def __post_init__(self) -> None:
        for name in ("strategy_id", "strategy_version", "timeframe"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")
        _require_aware(self.originating_timestamp, "originating_timestamp")
        reference = as_decimal(self.entry_reference, "entry_reference")
        if reference <= 0:
            raise ValueError("entry_reference must be positive")
        object.__setattr__(self, "entry_reference", reference)
        if (self.calendar_identity is None) != (self.session_date is None):
            raise ValueError("calendar identity and session date must be provided together")
        if self.calendar_identity is not None:
            object.__setattr__(self, "calendar_identity", self.calendar_identity.strip())


class PendingEntryValidityPolicy(ABC):
    """Strategy-owned pending-entry validity capability (``PendingEntryValidityPolicy/v1``).

    Bound alongside ``StrategySignalGenerator`` (NOT part of it).  No provider
    bound -> default semantics: the pending entry remains strategy-valid,
    subject to existing mechanical lifecycle (DAY/GTC) and RiskGate rules.

    Responsibilities:
    A. ``freeze_spec`` — at entry approval, freeze any immutable mechanical
       validity evidence required by that logical entry.
    B. ``evaluate`` — before a later pending execution opportunity, evaluate
       strategy-semantic validity using only authorized evidence.
    C. Return a deterministic ``EntryValidityResult``; the engine consumes it
       blindly.
    """

    @property
    @abstractmethod
    def policy_identity(self) -> str:
        """Explicit versioned identity (``PendingEntryValidityPolicy/v1`` + owner version)."""

    @abstractmethod
    def freeze_spec(self, *, entry_context: EntryValidityContext) -> EntryValiditySpec:
        """Finalize the immutable mechanical spec for this logical entry."""

    @abstractmethod
    def evaluate(
        self,
        *,
        entry_context: EntryValidityContext,
        spec: EntryValiditySpec | None,
        data_view: Any,
        state_snapshot: Mapping[str, Any],
    ) -> EntryValidityResult:
        """Deterministic READ-ONLY semantic validity decision.

        ``data_view`` is delivered with the SAME shape convention as
        ``generate_signal`` (single-instrument strategies receive
        timeframe-keyed DataFrames; multi-stream strategies receive the
        ``MarketDataView``), but always from the retained MOST-RECENT PRE-T
        view (bars strictly before the execution opportunity).  ``state_snapshot``
        is an isolated deep copy of the authoritative strategy state; any
        mutation is discarded.
        """


def entry_validity_binding_fingerprint(bindings: Iterable[tuple[str, str | None]]) -> str:
    """Canonical RUN-LEVEL strategy-keyed validity binding evidence (owner decision O1).

    Accepts ``(strategy_id, policy_identity_or_None)`` pairs (no
    ``StrategyBinding`` import needed to avoid import cycles).  Ordering is
    deterministic by strategy_id.  ``None`` encodes distinctly from any
    provider identity (CanonicalCodec ``none`` atom), so ``provider=None`` can
    never collide with a concrete provider identity.
    """
    ordered = tuple(
        sorted(
            ((strategy_id, policy_identity) for strategy_id, policy_identity in bindings),
            key=lambda item: item[0],
        )
    )
    if not ordered or any(not isinstance(strategy_id, str) or not strategy_id.strip() for strategy_id, _ in ordered):
        raise ValueError("validity binding requires non-empty strategy identities")
    if any(policy is not None and (not isinstance(policy, str) or not policy.strip()) for _, policy in ordered):
        raise ValueError("validity binding policy identities must be non-empty strings or None")
    return CanonicalCodec.fingerprint(
        "sentinelx-entry-validity-binding/v1",
        tuple((strategy_id, policy_identity) for strategy_id, policy_identity in ordered),
    )
