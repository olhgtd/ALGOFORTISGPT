"""Aggregate-position protective exits built on the existing portfolio flow."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import Enum
from functools import wraps
from threading import RLock
from typing import Callable, Iterator, Mapping, TypeVar

from engine.backtest.engine import BarEvent
from engine.execution import ExecutionEngine, ExecutionOutcome, ExecutionResult
from engine.market.profile import MarketProfile
from engine.orders import OrderRequest, OrderType
from engine.portfolio import (
    AccountSnapshot,
    AccountingOutcome,
    AccountingResult,
    InstrumentSpecification,
    PortfolioAccount,
    PositionKey,
)
from engine.portfolio.model import as_decimal


_Method = TypeVar("_Method", bound=Callable)


def _serialized_book_mutation(method: _Method) -> _Method:
    """Route every book mutation through its engine-owned RLock."""
    @wraps(method)
    def wrapped(self: "ProtectiveExitBook", *args, **kwargs):
        with self._mutation_guard:
            return method(self, *args, **kwargs)
    return wrapped  # type: ignore[return-value]


class ProtectiveExitKind(str, Enum):
    STOP_LOSS = "STOP_LOSS"
    TARGET = "TARGET"
    TRAILING_STOP = "TRAILING_STOP"


class ProtectiveExitState(str, Enum):
    ACTIVE = "ACTIVE"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class TrailingStopState:
    """Explicit, rule-supplied trailing state; it deliberately has no formula."""

    current_stop: Decimal | int | float | str
    reference_extreme: Decimal | int | float | str
    activated: bool = True
    effective_after: datetime | None = None

    def __post_init__(self) -> None:
        stop = as_decimal(self.current_stop, "current_stop")
        extreme = as_decimal(self.reference_extreme, "reference_extreme")
        if stop <= 0 or extreme <= 0:
            raise ValueError("trailing prices must be positive")
        if self.effective_after is not None and (
            self.effective_after.tzinfo is None or self.effective_after.utcoffset() is None
        ):
            raise ValueError("effective_after must be timezone-aware")
        object.__setattr__(self, "current_stop", stop)
        object.__setattr__(self, "reference_extreme", extreme)


@dataclass(frozen=True)
class ProtectiveExit:
    """One owned protective order; position state remains in PortfolioAccount."""

    protective_id: str
    position_key: PositionKey
    exit_order: OrderRequest
    kind: ProtectiveExitKind
    quantity: Decimal | int | float | str
    oco_group_id: str | None = None
    trailing: TrailingStopState | None = None
    effective_after: datetime | None = None
    state: ProtectiveExitState = ProtectiveExitState.ACTIVE
    termination_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.protective_id, str) or not self.protective_id.strip():
            raise ValueError("protective_id must be a non-empty string")
        if not isinstance(self.position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")
        if not isinstance(self.exit_order, OrderRequest) or self.exit_order.action != "EXIT":
            raise ValueError("protective exit requires an EXIT OrderRequest")
        if not isinstance(self.kind, ProtectiveExitKind) or not isinstance(self.state, ProtectiveExitState):
            raise TypeError("kind and state must be protective enums")
        quantity = as_decimal(self.quantity, "quantity")
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        object.__setattr__(self, "quantity", quantity)
        if self.effective_after is not None and (
            not isinstance(self.effective_after, datetime)
            or self.effective_after.tzinfo is None
            or self.effective_after.utcoffset() is None
        ):
            raise ValueError("effective_after must be a timezone-aware datetime")
        if self.exit_order.strategy_id != self.position_key.strategy_id or self.exit_order.strategy_version != self.position_key.strategy_version:
            raise ValueError("protective order ownership must match position_key")
        if self.exit_order.symbol.upper() != self.position_key.identity.instrument:
            raise ValueError("protective order symbol must match position_key")
        expected_type = OrderType.LIMIT if self.kind is ProtectiveExitKind.TARGET else OrderType.STOP
        if self.exit_order.order_type is not expected_type:
            raise ValueError("protective exit has incompatible order type")
        if self.kind is ProtectiveExitKind.TRAILING_STOP:
            if not isinstance(self.trailing, TrailingStopState):
                raise ValueError("trailing stop requires TrailingStopState")
            if as_decimal(self.exit_order.stop_price, "stop_price") != self.trailing.current_stop:
                raise ValueError("trailing current_stop must match exit order stop_price")
        elif self.trailing is not None:
            raise ValueError("only trailing stops may carry trailing state")


@dataclass(frozen=True)
class ProtectiveEvaluation:
    protective: ProtectiveExit
    snapshot: AccountSnapshot
    execution: ExecutionResult | None
    reason: str | None
    accounting: AccountingResult | None = None


@dataclass(frozen=True)
class _CommittedProtectiveProposal:
    book_identity: int
    session_identity: int
    previous: ProtectiveExit
    replacement: ProtectiveExit


class _CommittedMutationSession:
    def __init__(self, book: "ProtectiveExitBook") -> None:
        self._book = book
        self._active = True
        self._published: set[int] = set()

    def _require_active(self) -> None:
        if not self._active:
            raise RuntimeError("committed mutation session is closed")

    def finalize(self, previous: ProtectiveExit, replacement: ProtectiveExit) -> _CommittedProtectiveProposal:
        self._require_active()
        if self._book._exits.get(previous.protective_id) != previous:
            raise ValueError("committed proposal previous state is stale")
        if not isinstance(replacement, ProtectiveExit):
            raise TypeError("replacement must be a ProtectiveExit")
        if (replacement.protective_id, replacement.position_key, replacement.kind,
                replacement.quantity, replacement.oco_group_id) != (
                previous.protective_id, previous.position_key, previous.kind,
                previous.quantity, previous.oco_group_id):
            raise ValueError("committed proposal may not alter protective identity, position, kind, quantity, or OCO")
        return _CommittedProtectiveProposal(id(self._book), id(self), previous, replacement)

    def publish_committed(self, proposal: _CommittedProtectiveProposal) -> ProtectiveExit:
        self._require_active()
        if not isinstance(proposal, _CommittedProtectiveProposal) or proposal.book_identity != id(self._book) or proposal.session_identity != id(self):
            raise ValueError("proposal does not belong to this committed mutation session")
        if id(proposal) in self._published:
            raise ValueError("committed proposal already published")
        # Staleness was finalized while this same RLock was held; no ordinary
        # domain/economic validation is permitted after durable commit.
        self._book._exits[proposal.replacement.protective_id] = proposal.replacement
        self._published.add(id(proposal))
        return proposal.replacement



class ProtectiveExitBook:
    """Reusable immutable configuration plus one mutable protective runtime.

    ``fresh_runtime_book`` is the ordinary-backtest boundary.  It creates a
    new mutable lifecycle coordinator from the unchanged configured exits;
    it is not live restart/restore persistence.
    """

    def __init__(self, exits: tuple[ProtectiveExit, ...] = ()) -> None:
        values = {item.protective_id: item for item in exits}
        if len(values) != len(exits):
            raise ValueError("duplicate protective_id")
        # ProtectiveExit and its nested value objects are frozen.  Separate
        # dictionaries are nevertheless required because lifecycle updates
        # replace entries in ``_exits`` during a run.
        self._configuration = dict(values)
        self._exits = dict(values)
        self._mutation_guard = RLock()

    @contextmanager
    def committed_mutation(self) -> Iterator[_CommittedMutationSession]:
        """Engine-only final-validation → durable-commit → publish boundary.

        No callback is invoked here.  The frozen order is book guard before
        SQLite transaction; public book mutations share this reentrant guard.
        """
        with self._mutation_guard:
            session = _CommittedMutationSession(self)
            try:
                yield session
            finally:
                session._active = False

    @property
    def exits(self) -> Mapping[str, ProtectiveExit]:
        with self._mutation_guard:
            return dict(self._exits)

    @property
    def configured_exits(self) -> Mapping[str, ProtectiveExit]:
        """Immutable-template values used to start each independent run."""
        with self._mutation_guard:
            return dict(self._configuration)

    def authoritative_exits(self, position_key: PositionKey, *, kind: ProtectiveExitKind) -> tuple[ProtectiveExit, ...]:
        """Exact ACTIVE candidates bound to one key and one protective kind.

        Read-only exact-match selection for the risk gate: returns every
        ACTIVE protective exit whose ``position_key`` equals ``position_key``
        EXACTLY and whose ``kind`` equals ``kind``, in stable ``protective_id``
        order for deterministic iteration.  This method never selects by price,
        insertion order, recency, or symbol fallback; callers must apply
        exactly-one-or-REJECT.  OCO execution semantics are untouched.
        """
        if not isinstance(position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")
        if not isinstance(kind, ProtectiveExitKind):
            raise TypeError("kind must be a ProtectiveExitKind")
        with self._mutation_guard:
            return tuple(sorted(
                (item for item in self._exits.values() if item.state is ProtectiveExitState.ACTIVE
                 and item.position_key == position_key and item.kind is kind),
                key=lambda item: item.protective_id,
            ))

    def fresh_runtime_book(self) -> "ProtectiveExitBook":
        """Create an independent runtime book from immutable configuration."""
        with self._mutation_guard:
            return ProtectiveExitBook(tuple(self._configuration.values()))

    @_serialized_book_mutation
    def add(self, protective: ProtectiveExit) -> None:
        if not isinstance(protective, ProtectiveExit):
            raise TypeError("protective must be a ProtectiveExit")
        if protective.protective_id in self._exits:
            raise ValueError("duplicate protective_id")
        self._configuration[protective.protective_id] = protective
        self._exits[protective.protective_id] = protective

    @_serialized_book_mutation
    def reconcile_position(self, position_key: PositionKey, snapshot: AccountSnapshot) -> tuple[ProtectiveExit, ...]:
        """Reconcile only this key after accepted accounting evidence.

        Reductions may shrink active protection, never grow it.  A full close
        cancels it.  Portfolio remains the sole position authority.
        """
        if not isinstance(position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")
        position = snapshot.positions.get(position_key)
        updated: list[ProtectiveExit] = []
        for item in tuple(self._exits.values()):
            if item.position_key != position_key or item.state is not ProtectiveExitState.ACTIVE:
                continue
            if position is None or position.quantity <= 0:
                replacement = replace(item, state=ProtectiveExitState.CANCELLED, termination_reason="protected_position_closed")
            elif item.quantity > position.quantity:
                replacement_order = OrderRequest.from_intent(
                    item.exit_order.source_intent, item.exit_order.order_type,
                    position.quantity, item.exit_order.time_in_force,
                    limit_price=item.exit_order.limit_price, stop_price=item.exit_order.stop_price,
                )
                replacement = replace(item, quantity=position.quantity, exit_order=replacement_order)
            else:
                continue
            self._exits[item.protective_id] = replacement
            updated.append(replacement)
        return tuple(sorted(updated, key=lambda item: item.protective_id))

    @_serialized_book_mutation
    def evaluate(
        self,
        protective_id: str,
        snapshot: AccountSnapshot,
        bar: BarEvent,
        market_profile: MarketProfile,
        portfolio: PortfolioAccount,
        specification: InstrumentSpecification,
        execution_engine: ExecutionEngine | None = None,
    ) -> ProtectiveEvaluation:
        """Evaluate one protective exit using the existing resolve/execute/apply path."""
        protective = self._exits[protective_id]
        if protective.state is not ProtectiveExitState.ACTIVE:
            return ProtectiveEvaluation(protective, snapshot, None, protective.termination_reason)
        position = snapshot.positions.get(protective.position_key)
        if position is None or position.quantity <= 0:
            return self._cancel(protective, snapshot, "protected_position_closed")
        if protective.quantity > position.quantity:
            return self._cancel(protective, snapshot, "protective_quantity_exceeds_owned_quantity")
        eligibility_after = protective.effective_after
        if eligibility_after is None and protective.trailing is not None:
            eligibility_after = protective.trailing.effective_after
        if eligibility_after is not None and bar.timestamp <= eligibility_after:
            reason = (
                "trailing_level_not_yet_effective"
                if protective.kind is ProtectiveExitKind.TRAILING_STOP and protective.effective_after is None
                else "protective_level_not_yet_effective"
            )
            return ProtectiveEvaluation(protective, snapshot, None, reason)
        if self._ambiguous_with_active_sibling(protective, bar):
            return ProtectiveEvaluation(protective, snapshot, None, "same_bar_oco_ambiguity")

        resolved = portfolio.resolve_exit(snapshot, protective.exit_order, specification, quantity=protective.quantity)
        if resolved.outcome is not AccountingOutcome.ACCEPTED or resolved.close_instruction is None:
            return self._cancel(protective, snapshot, "protective_exit_resolution_rejected")
        execution = (execution_engine or ExecutionEngine()).evaluate(resolved.close_instruction, bar, market_profile)
        if execution.outcome is not ExecutionOutcome.FILLED:
            return ProtectiveEvaluation(protective, snapshot, execution, execution.reason)
        accounted = portfolio.apply_execution(snapshot, execution, specification)
        if accounted.outcome is not AccountingOutcome.ACCEPTED:
            return self._cancel(protective, snapshot, "protective_accounting_rejected")
        updated = replace(protective, state=ProtectiveExitState.FILLED, termination_reason="filled")
        self._exits[protective_id] = updated
        resulting = accounted.resulting_snapshot
        if protective.position_key not in resulting.positions:
            self._cancel_siblings(protective)
        return ProtectiveEvaluation(updated, resulting, execution, "filled", accounted)

    @_serialized_book_mutation
    def record_external_fill(
        self,
        protective_id: str,
        *,
        termination_reason: str = "filled",
    ) -> tuple[ProtectiveExit, ...]:
        """Record that a protective exit was confirmed filled by an external broker.

        Marks the exact protective exit FILLED, cancels active OCO siblings with
        termination_reason='oco_sibling_filled', and returns all modified instances.

        Idempotency:
        - If protective_id is already FILLED with the same termination_reason, returns
          the existing filled instance (idempotent no-op).
        - If protective_id is CANCELLED or has mismatched termination state, fails closed.
        """
        if not isinstance(protective_id, str) or not protective_id.strip():
            raise ValueError("protective_id must be a non-empty string")
        protective = self._exits.get(protective_id)
        if protective is None:
            raise KeyError(f"protective exit not found: {protective_id}")

        if protective.state is ProtectiveExitState.FILLED:
            if protective.termination_reason == termination_reason:
                return (protective,)
            raise ValueError(f"protective exit already filled with different reason: {protective.termination_reason}")

        if protective.state is not ProtectiveExitState.ACTIVE:
            raise ValueError(f"cannot record fill on non-active protective exit: {protective.state}")

        updated_self = replace(protective, state=ProtectiveExitState.FILLED, termination_reason=termination_reason)
        self._exits[protective_id] = updated_self
        modified = [updated_self]

        if protective.oco_group_id is not None:
            for item in tuple(self._exits.values()):
                if item.protective_id != protective.protective_id and item.oco_group_id == protective.oco_group_id and item.state is ProtectiveExitState.ACTIVE:
                    cancelled_sibling = replace(item, state=ProtectiveExitState.CANCELLED, termination_reason="oco_sibling_filled")
                    self._exits[item.protective_id] = cancelled_sibling
                    modified.append(cancelled_sibling)

        return tuple(modified)

    @_serialized_book_mutation
    def update_trailing(
        self,
        protective_id: str,
        *,
        reference_extreme: Decimal | int | float | str,
        next_stop: Decimal | int | float | str,
        bar: BarEvent | None = None,
        effective_after: datetime | None = None,
    ) -> ProtectiveExit:
        """Make a caller-supplied long trailing level effective after a real bar or live timestamp."""
        protective = self._exits.get(protective_id)
        if protective is None:
            raise KeyError(f"protective exit not found: {protective_id}")
        if protective.kind is not ProtectiveExitKind.TRAILING_STOP or protective.state is not ProtectiveExitState.ACTIVE:
            raise ValueError("active trailing stop required")

        if bar is not None:
            if bar.is_synthetic:
                return protective
            ts = bar.timestamp
        elif effective_after is not None:
            if effective_after.tzinfo is None or effective_after.utcoffset() is None:
                raise ValueError("effective_after must be timezone-aware")
            ts = effective_after
        else:
            raise ValueError("either bar or effective_after must be provided")

        next_state = TrailingStopState(next_stop, reference_extreme, protective.trailing.activated, ts)
        if next_state.reference_extreme < protective.trailing.reference_extreme or next_state.current_stop < protective.trailing.current_stop:
            raise ValueError("long trailing stop and reference extreme may not loosen")
        replacement_order = OrderRequest.from_intent(
            protective.exit_order.source_intent, OrderType.STOP, protective.quantity, protective.exit_order.time_in_force,
            stop_price=next_state.current_stop,
        )
        updated = replace(protective, exit_order=replacement_order, trailing=next_state)
        self._exits[protective_id] = updated
        return updated

    @_serialized_book_mutation
    def activate_trailing(
        self,
        protective_id: str,
        *,
        reference_extreme: Decimal | int | float | str,
        next_stop: Decimal | int | float | str,
        effective_after: datetime,
    ) -> ProtectiveExit:
        """Activate a pre-materialized strategy trailing exit through the public book.

        The caller supplies only a candidate level.  This method retains all
        lifecycle ownership: exact exit selection, non-loosening validation,
        and event-time non-retroactivity.
        """
        protective = self._exits.get(protective_id)
        if protective is None:
            raise KeyError(f"protective exit not found: {protective_id}")
        if protective.kind is not ProtectiveExitKind.TRAILING_STOP or protective.state is not ProtectiveExitState.ACTIVE:
            raise ValueError("active trailing stop required")
        if protective.trailing.activated:
            raise ValueError("trailing stop is already activated")
        if effective_after.tzinfo is None or effective_after.utcoffset() is None:
            raise ValueError("effective_after must be timezone-aware")
        next_state = TrailingStopState(next_stop, reference_extreme, True, effective_after)
        if next_state.reference_extreme < protective.trailing.reference_extreme or next_state.current_stop < protective.trailing.current_stop:
            raise ValueError("long trailing stop and reference extreme may not loosen")
        replacement_order = OrderRequest.from_intent(
            protective.exit_order.source_intent, OrderType.STOP, protective.quantity, protective.exit_order.time_in_force,
            stop_price=next_state.current_stop,
        )
        updated = replace(protective, exit_order=replacement_order, trailing=next_state)
        self._exits[protective_id] = updated
        return updated

    def _ambiguous_with_active_sibling(self, protective: ProtectiveExit, bar: BarEvent) -> bool:
        if protective.oco_group_id is None or bar.is_synthetic:
            return False
        siblings = [item for item in self._exits.values() if item.oco_group_id == protective.oco_group_id and item.state is ProtectiveExitState.ACTIVE]
        stop = next((item for item in siblings if item.kind in {ProtectiveExitKind.STOP_LOSS, ProtectiveExitKind.TRAILING_STOP}), None)
        target = next((item for item in siblings if item.kind is ProtectiveExitKind.TARGET), None)
        return stop is not None and target is not None and stop.exit_order.stop_price < bar.open < target.exit_order.limit_price and bar.low <= stop.exit_order.stop_price and bar.high >= target.exit_order.limit_price

    def _cancel(self, protective: ProtectiveExit, snapshot: AccountSnapshot, reason: str) -> ProtectiveEvaluation:
        updated = replace(protective, state=ProtectiveExitState.CANCELLED, termination_reason=reason)
        self._exits[protective.protective_id] = updated
        return ProtectiveEvaluation(updated, snapshot, None, reason)

    def _cancel_siblings(self, protective: ProtectiveExit) -> None:
        if protective.oco_group_id is None:
            return
        for item in tuple(self._exits.values()):
            if item.protective_id != protective.protective_id and item.oco_group_id == protective.oco_group_id and item.state is ProtectiveExitState.ACTIVE:
                self._exits[item.protective_id] = replace(item, state=ProtectiveExitState.CANCELLED, termination_reason="oco_sibling_filled")
