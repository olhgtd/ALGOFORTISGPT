"""Typed strategy-owned runtime trailing decisions and target replacement.

Policies receive immutable, already accepted quote/protective evidence and
return a candidate only.  They never receive mutable engine state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable, Protocol

from engine.core.numeric import as_decimal
from engine.portfolio import PositionKey
from engine.protective.runtime import ProtectiveExit

if TYPE_CHECKING:
    from engine.persistence.sqlite_store import StrategyStateTransition


@dataclass(frozen=True)
class RuntimeTrailingEvidence:
    """Immutable canonical evidence available to one strategy runtime callback."""

    position_key: PositionKey
    protective: ProtectiveExit
    market_timestamp: datetime
    executable_bid: Decimal | int | float | str

    def __post_init__(self) -> None:
        if not isinstance(self.position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")
        if self.protective.position_key != self.position_key:
            raise ValueError("protective position_key must match evidence position_key")
        if self.market_timestamp.tzinfo is None or self.market_timestamp.utcoffset() is None:
            raise ValueError("market_timestamp must be timezone-aware")
        bid = as_decimal(self.executable_bid, "executable_bid")
        if bid <= 0:
            raise ValueError("executable_bid must be positive")
        object.__setattr__(self, "executable_bid", bid)


@dataclass(frozen=True)
class RuntimeTrailingDecision:
    """A strategy candidate for activation or a later trailing-level update.

    ``effective_after`` is deliberately absent: the engine assigns the
    authoritative quote timestamp, preventing a strategy from backdating or
    looking ahead.  Both price fields are required together when a decision is
    returned.  Economics remain entirely in strategy Python code.

    ``state_transition`` is an optional coupled strategy-state update that the
    engine persists atomically with the trailing ratchet.  The engine owns
    generation validation and atomic commit; the strategy owns only the
    deterministic state payload.
    """

    reference_extreme: Decimal | int | float | str
    next_stop: Decimal | int | float | str
    activate: bool = False
    state_transition: StrategyStateTransition | None = None

    def __post_init__(self) -> None:
        extreme = as_decimal(self.reference_extreme, "reference_extreme")
        stop = as_decimal(self.next_stop, "next_stop")
        if extreme <= 0 or stop <= 0:
            raise ValueError("runtime trailing decision prices must be positive")
        if stop >= extreme:
            raise ValueError("runtime trailing next_stop must be below reference_extreme")
        if not isinstance(self.activate, bool):
            raise TypeError("activate must be bool")
        object.__setattr__(self, "reference_extreme", extreme)
        object.__setattr__(self, "next_stop", stop)
        if self.state_transition is not None:
            from engine.persistence.sqlite_store import StrategyStateTransition
            if not isinstance(self.state_transition, StrategyStateTransition):
                raise TypeError("state_transition must be a StrategyStateTransition or None")


class RuntimeTrailingPolicy(Protocol):
    """Optional strategy plug-in hook for dynamic trailing decisions."""

    def trailing_decision(self, evidence: RuntimeTrailingEvidence) -> RuntimeTrailingDecision | None:
        """Return a deterministic candidate, or ``None`` for no change."""


# ======================================================================
# TARGET REPLACEMENT — immutable strategy-facing contract
# ======================================================================


@dataclass(frozen=True)
class TargetCandidate:
    """Immutable post-entry target replacement candidate from a strategy.

    Carries only the canonical facts required to request a TARGET price
    change.  No mutable book, broker, account, store, or runner state.
    The engine assigns ``effective_after``; the strategy never selects it.
    No target formula exists in generic engine code.
    """

    strategy_id: str
    strategy_version: str
    position_key: PositionKey
    current_target_protective_id: str
    current_target_limit_price: Decimal
    proposed_target_price: Decimal
    market_timestamp: datetime
    state_transition: StrategyStateTransition | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.strategy_id, str) or not self.strategy_id.strip():
            raise ValueError("strategy_id must be a non-empty string")
        if not isinstance(self.strategy_version, str) or not self.strategy_version.strip():
            raise ValueError("strategy_version must be a non-empty string")
        if not isinstance(self.position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")
        if not isinstance(self.current_target_protective_id, str) or not self.current_target_protective_id.strip():
            raise ValueError("current_target_protective_id must be a non-empty string")
        cur = as_decimal(self.current_target_limit_price, "current_target_limit_price")
        if not cur.is_finite() or cur <= 0:
            raise ValueError("current_target_limit_price must be a finite positive")
        object.__setattr__(self, "current_target_limit_price", cur)
        proposed = as_decimal(self.proposed_target_price, "proposed_target_price")
        if not proposed.is_finite() or proposed <= 0:
            raise ValueError("proposed_target_price must be a finite positive")
        object.__setattr__(self, "proposed_target_price", proposed)
        if not isinstance(self.market_timestamp, datetime) or self.market_timestamp.tzinfo is None or self.market_timestamp.utcoffset() is None:
            raise ValueError("market_timestamp must be timezone-aware")
        if self.state_transition is not None:
            from engine.persistence.sqlite_store import StrategyStateTransition
            if not isinstance(self.state_transition, StrategyStateTransition):
                raise TypeError("state_transition must be a StrategyStateTransition or None")


@dataclass(frozen=True)
class TargetReplacementEvidence:
    """Immutable snapshot of current target state supplied to strategy callback.

    The strategy receives this outside any engine lock and returns a
    ``TargetCandidate`` or ``None``.
    """

    position_key: PositionKey
    strategy_id: str
    strategy_version: str
    current_target: ProtectiveExit
    current_limit_price: Decimal
    market_timestamp: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")
        if not isinstance(self.strategy_id, str) or not self.strategy_id.strip():
            raise ValueError("strategy_id must be a non-empty string")
        if not isinstance(self.strategy_version, str) or not self.strategy_version.strip():
            raise ValueError("strategy_version must be a non-empty string")
        if not isinstance(self.current_target, ProtectiveExit):
            raise TypeError("current_target must be a ProtectiveExit")
        if self.current_target.kind.value != "TARGET":
            raise ValueError("current_target must be a TARGET kind")
        if self.current_target.position_key != self.position_key:
            raise ValueError("current_target position_key must match evidence position_key")
        cur = as_decimal(self.current_limit_price, "current_limit_price")
        if cur <= 0:
            raise ValueError("current_limit_price must be positive")
        object.__setattr__(self, "current_limit_price", cur)
        if not isinstance(self.market_timestamp, datetime) or self.market_timestamp.tzinfo is None or self.market_timestamp.utcoffset() is None:
            raise ValueError("market_timestamp must be timezone-aware")


class TargetReplacementPolicy(Protocol):
    """Optional strategy plug-in hook for post-entry target replacement."""

    def target_replacement_decision(self, evidence: TargetReplacementEvidence) -> TargetCandidate | None:
        """Return a deterministic ``TargetCandidate``, or ``None`` for no change."""


# ======================================================================
# STRATEGY EXIT — generic strategy-owned close-decision primitive
# ======================================================================


@dataclass(frozen=True)
class StrategyExitDecision:
    """Immutable strategy-owned decision to close a position.

    The engine owns validation, close-order construction, broker/execution,
    accounting, persistence, audit, and protective reconciliation. The strategy
    owns only the *reason* for exiting.

    ``state_transition`` is an optional coupled strategy-state update that the
    engine persists atomically with the exit submission.  The engine owns
    generation validation and atomic commit; the strategy owns only the
    deterministic state payload.
    """

    state_transition: StrategyStateTransition | None = None

    def __post_init__(self) -> None:
        if self.state_transition is not None:
            from engine.persistence.sqlite_store import StrategyStateTransition
            if not isinstance(self.state_transition, StrategyStateTransition):
                raise TypeError("state_transition must be a StrategyStateTransition or None")


@dataclass(frozen=True)
class StrategyExitEvidence:
    """Immutable snapshot of current position state supplied to strategy callback.

    The strategy receives this outside any engine lock and returns a
    ``StrategyExitDecision`` or ``None``.
    """

    strategy_id: str
    strategy_version: str
    position_key: PositionKey
    instrument_identity: object
    direction: str
    open_quantity: Decimal
    market_timestamp: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.strategy_id, str) or not self.strategy_id.strip():
            raise ValueError("strategy_id must be a non-empty string")
        if not isinstance(self.strategy_version, str) or not self.strategy_version.strip():
            raise ValueError("strategy_version must be a non-empty string")
        if not isinstance(self.position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")
        if self.direction not in ("LONG", "SHORT"):
            raise ValueError("direction must be LONG or SHORT")
        qty = as_decimal(self.open_quantity, "open_quantity")
        if qty <= 0:
            raise ValueError("open_quantity must be positive")
        object.__setattr__(self, "open_quantity", qty)
        if not isinstance(self.market_timestamp, datetime) or self.market_timestamp.tzinfo is None or self.market_timestamp.utcoffset() is None:
            raise ValueError("market_timestamp must be timezone-aware")


class StrategyExitPolicy(Protocol):
    """Optional strategy plug-in hook for generic strategy-owned exit decisions."""

    def strategy_exit_decision(self, evidence: StrategyExitEvidence) -> StrategyExitDecision | None:
        """Return a ``StrategyExitDecision`` to close the position, or ``None`` for no exit."""
