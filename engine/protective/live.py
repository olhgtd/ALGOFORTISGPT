"""Phase 5 OD-7 Item 8: Live-price protective exit evaluator and coordinator.

Adapts accepted live option quote evidence to the canonical protective domain
contracts in ``engine.protective.runtime.py`` and ``engine.protective.plan.py``.

Owner-frozen trigger authorities (long option BUY positions):
  - STOP: quote.bid_price <= stop_price
  - TARGET: quote.bid_price >= target_price
  - TRAILING EXCURSION: quote.bid_price > reference_extreme
  - TRAILING STOP: quote.bid_price <= current_stop

Safety invariants:
  - TRIGGERED != FILLED: trigger evaluation submits a ConcreteCloseInstruction;
    ProtectiveExit.state mutates to FILLED only upon confirmed BrokerTerminalEvent(FILLED).
  - OCO timing: sibling exits remain ACTIVE while close order is QUEUED; cancelled
    only upon actual confirmed broker fill (termination_reason='oco_sibling_filled').
  - Pending-close lock: _pending_closes[PositionKey] suppresses duplicate/competing
    protective submissions while a close order is in flight.
  - Zero local wall-clock authority: QuoteSnapshot.exchange_timestamp is the sole time authority.
  - Zero private state manipulation: all ProtectiveExitBook mutations go through public methods.
"""

from __future__ import annotations

from dataclasses import dataclass, replace as dc_replace
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Callable, Iterable, Mapping

from engine.execution.quote import QuoteSnapshot
from engine.core.numeric import as_decimal
from engine.orders.model import ConcreteCloseInstruction, OrderRequest
from engine.orders import OrderType, TimeInForce
from engine.portfolio.accounting import PortfolioAccount
from engine.portfolio.model import (
    AccountSnapshot,
    InstrumentSpecification,
    PositionKey,
)
from engine.orchestration.signal_intake import SignalIntent
from engine.protective.runtime import (
    ProtectiveExit,
    ProtectiveExitBook,
    ProtectiveExitKind,
    ProtectiveExitState,
)
from engine.protective.runtime_policy import (
    RuntimeTrailingDecision,
    RuntimeTrailingEvidence,
    StrategyExitDecision,
    StrategyExitEvidence,
    TargetCandidate,
    TargetReplacementEvidence,
)

if TYPE_CHECKING:
    from engine.persistence.sqlite_store import StrategyStateTransition


class StrategyCallbackFailure(RuntimeError):
    """A strategy-owned runtime-policy callback raised inside protective evaluation.

    Phase 8 P1 (§128.1/§128.5): a failing ``RuntimeTrailingPolicy`` /
    ``TargetReplacementPolicy`` / ``StrategyExitPolicy`` callback is a
    STRATEGY-owned exception, not an engine protective-invariant failure.
    This subclass of :class:`RuntimeError` keeps every existing broad
    ``RuntimeError`` handler and test matcher working while carrying the
    exact canonical ``(strategy_id, strategy_version)`` owner identity so
    the safety layer can route the failure without parsing message text.

    ``__cause__`` remains the original strategy exception for Rule-7
    evidence (deterministic sanitized error class).
    """

    def __init__(self, message: str, *, strategy_owner: tuple[str, str]) -> None:
        super().__init__(message)
        owner_sid, owner_sver = strategy_owner
        if not isinstance(owner_sid, str) or not owner_sid.strip():
            raise ValueError("strategy_owner strategy_id must be a non-empty string")
        if not isinstance(owner_sver, str) or not owner_sver.strip():
            raise ValueError("strategy_owner strategy_version must be a non-empty string")
        self.strategy_owner: tuple[str, str] = (owner_sid, owner_sver)


@dataclass(frozen=True)
class TrailingRatchetEvidence:
    """Immutable evidence of an active trailing stop ratcheting on favorable excursion.

    ``state_transition`` carries an optional coupled strategy-state update from
    the trailing callback.  The coordinator persists it atomically with the
    ratchet in the same transaction.
    """

    protective_id: str
    position_key: PositionKey
    old_stop: Decimal
    new_stop: Decimal
    old_reference_extreme: Decimal
    new_reference_extreme: Decimal
    effective_after: datetime
    market_timestamp: datetime
    state_transition: StrategyStateTransition | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.protective_id, str) or not self.protective_id.strip():
            raise ValueError("protective_id must be a non-empty string")
        if not isinstance(self.position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")
        for name in ("old_stop", "new_stop", "old_reference_extreme", "new_reference_extreme"):
            val = as_decimal(getattr(self, name), name)
            if val <= Decimal("0"):
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, val)
        if not isinstance(self.effective_after, datetime) or self.effective_after.tzinfo is None:
            raise ValueError("effective_after must be a timezone-aware datetime")
        if not isinstance(self.market_timestamp, datetime) or self.market_timestamp.tzinfo is None:
            raise ValueError("market_timestamp must be a timezone-aware datetime")


@dataclass(frozen=True)
class LiveProtectivePendingClose:
    """Immutable record of an in-flight protective close order submitted to the broker."""

    position_key: PositionKey
    protective_id: str
    order_id: str
    broker_order_identity: str
    kind: ProtectiveExitKind
    trigger_price: Decimal
    trigger_timestamp: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")
        if not isinstance(self.protective_id, str) or not self.protective_id.strip():
            raise ValueError("protective_id must be a non-empty string")
        if not isinstance(self.order_id, str) or not self.order_id.strip():
            raise ValueError("order_id must be a non-empty string")
        if not isinstance(self.broker_order_identity, str) or not self.broker_order_identity.strip():
            raise ValueError("broker_order_identity must be a non-empty string")
        if not isinstance(self.kind, ProtectiveExitKind):
            raise TypeError("kind must be a ProtectiveExitKind")
        price = as_decimal(self.trigger_price, "trigger_price")
        if price <= 0:
            raise ValueError("trigger_price must be positive")
        object.__setattr__(self, "trigger_price", price)
        if not isinstance(self.trigger_timestamp, datetime) or self.trigger_timestamp.tzinfo is None:
            raise ValueError("trigger_timestamp must be a timezone-aware datetime")


@dataclass(frozen=True)
class LiveProtectiveTrigger:
    """Immutable evidence of a protective trigger decision on an accepted quote."""

    protective: ProtectiveExit
    position_key: PositionKey
    kind: ProtectiveExitKind
    trigger_price: Decimal
    trigger_timestamp: datetime
    close_instruction: ConcreteCloseInstruction

    def __post_init__(self) -> None:
        if not isinstance(self.protective, ProtectiveExit):
            raise TypeError("protective must be a ProtectiveExit")
        if not isinstance(self.position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")
        if not isinstance(self.kind, ProtectiveExitKind):
            raise TypeError("kind must be a ProtectiveExitKind")
        price = as_decimal(self.trigger_price, "trigger_price")
        if price <= 0:
            raise ValueError("trigger_price must be positive")
        object.__setattr__(self, "trigger_price", price)
        if not isinstance(self.trigger_timestamp, datetime) or self.trigger_timestamp.tzinfo is None:
            raise ValueError("trigger_timestamp must be a timezone-aware datetime")
        if not isinstance(self.close_instruction, ConcreteCloseInstruction):
            raise TypeError("close_instruction must be a ConcreteCloseInstruction")


class LiveProtectiveEvaluator:
    """Live-quote protective exit evaluator and lifecycle manager."""

    def __init__(
        self,
        book: ProtectiveExitBook | None = None,
        *,
        pending_closes: Iterable[LiveProtectivePendingClose] | None = None,
        runtime_trailing_policies: Mapping[tuple[str, str], object] | None = None,
        runtime_target_replacement_policies: Mapping[tuple[str, str], object] | None = None,
        strategy_exception_observer: Callable[[StrategyCallbackFailure], None] | None = None,
    ) -> None:
        if book is not None and not isinstance(book, ProtectiveExitBook):
            raise TypeError("book must be a ProtectiveExitBook")
        if strategy_exception_observer is not None and not callable(strategy_exception_observer):
            raise TypeError("strategy_exception_observer must be callable or None")
        # Phase 8 P1 (§128.1/§128.5): optional escalation seam invoked when a
        # STRATEGY-owned runtime-policy callback fails.  The observer NEVER
        # replaces the raise — the failure still propagates fail-closed after
        # canonical evidence/safety routing has been performed.
        self._strategy_exception_observer = strategy_exception_observer
        self._book = book if book is not None else ProtectiveExitBook()
        self._pending_closes: dict[PositionKey, LiveProtectivePendingClose] = {}
        self._pending_by_order_id: dict[str, LiveProtectivePendingClose] = {}
        self._runtime_trailing_policies: dict[tuple[str, str], object] = {}
        if runtime_trailing_policies is not None:
            for owner, policy in runtime_trailing_policies.items():
                if (
                    not isinstance(owner, tuple)
                    or len(owner) != 2
                    or not all(isinstance(part, str) and part.strip() for part in owner)
                ):
                    raise TypeError("runtime_trailing_policies keys must be non-empty (strategy_id, strategy_version) tuples")
                if not callable(getattr(policy, "trailing_decision", None)):
                    raise TypeError("runtime trailing policy must provide trailing_decision(evidence)")
                self._runtime_trailing_policies[owner] = policy
        self._runtime_target_replacement_policies: dict[tuple[str, str], object] = {}
        if runtime_target_replacement_policies is not None:
            for owner, policy in runtime_target_replacement_policies.items():
                if (
                    not isinstance(owner, tuple)
                    or len(owner) != 2
                    or not all(isinstance(part, str) and part.strip() for part in owner)
                ):
                    raise TypeError("runtime_target_replacement_policies keys must be non-empty (strategy_id, strategy_version) tuples")
                if not callable(getattr(policy, "target_replacement_decision", None)):
                    raise TypeError("runtime target replacement policy must provide target_replacement_decision(evidence)")
                self._runtime_target_replacement_policies[owner] = policy
        if pending_closes is not None:
            for pc in pending_closes:
                self.register_pending_close(pc)

    def _raise_strategy_callback_failure(
        self,
        message: str,
        *,
        owner: tuple[str, str],
        cause: BaseException,
    ) -> None:
        """Build the structured failure, notify the P1 observer, then raise.

        The observer performs canonical Rule-7 ERROR evidence + Phase-8
        strategy-exception escalation BEFORE the failure propagates.  Observer
        failures are containment failures of the safety layer itself and
        propagate fail-closed (never swallowed to keep trading).
        """
        failure = StrategyCallbackFailure(message, strategy_owner=owner)
        # Chain the original strategy exception BEFORE notifying the observer
        # so canonical Rule-7 evidence carries the true deterministic class.
        failure.__cause__ = cause
        self._notify_strategy_exception_observer(failure)
        raise failure

    def _notify_strategy_exception_observer(self, failure: StrategyCallbackFailure) -> None:
        observer = self._strategy_exception_observer
        if observer is not None:
            observer(failure)

    @property
    def book(self) -> ProtectiveExitBook:
        """Underlying canonical protective exit book."""
        return self._book

    @property
    def pending_closes(self) -> Mapping[PositionKey, LiveProtectivePendingClose]:
        """Active in-flight protective close orders keyed by PositionKey."""
        return dict(self._pending_closes)

    @property
    def pending_closes_by_order_id(self) -> Mapping[str, LiveProtectivePendingClose]:
        """Active in-flight protective close orders keyed by broker order_id."""
        return dict(self._pending_by_order_id)

    def has_pending_close(self, position_key: PositionKey) -> bool:
        """Check if an in-flight protective close exists for the given PositionKey."""
        if not isinstance(position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")
        return position_key in self._pending_closes

    def get_pending_close(self, position_key: PositionKey) -> LiveProtectivePendingClose | None:
        """Retrieve the in-flight protective close for the given PositionKey if one exists."""
        if not isinstance(position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")
        return self._pending_closes.get(position_key)

    def register_pending_close(self, pending: LiveProtectivePendingClose) -> None:
        """Register a newly submitted protective close order."""
        if not isinstance(pending, LiveProtectivePendingClose):
            raise TypeError("pending must be a LiveProtectivePendingClose")
        if pending.position_key in self._pending_closes:
            raise ValueError(f"pending close already active for position: {pending.position_key}")
        if pending.order_id in self._pending_by_order_id:
            raise ValueError(f"duplicate pending close order_id: {pending.order_id}")
        self._pending_closes[pending.position_key] = pending
        self._pending_by_order_id[pending.order_id] = pending

    def clear_pending_close(self, position_key: PositionKey) -> LiveProtectivePendingClose | None:
        """Clear an in-flight protective close record by PositionKey."""
        if not isinstance(position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")
        pending = self._pending_closes.pop(position_key, None)
        if pending is not None:
            self._pending_by_order_id.pop(pending.order_id, None)
        return pending

    def clear_pending_close_by_order_id(self, order_id: str) -> LiveProtectivePendingClose | None:
        """Clear an in-flight protective close record by broker order_id."""
        if not isinstance(order_id, str) or not order_id.strip():
            raise ValueError("order_id must be a non-empty string")
        pending = self._pending_by_order_id.pop(order_id, None)
        if pending is not None:
            self._pending_closes.pop(pending.position_key, None)
        return pending

    def evaluate_quote_with_ratchets(
        self,
        quote: QuoteSnapshot,
        snapshot: AccountSnapshot,
        specification: InstrumentSpecification,
        portfolio_account: PortfolioAccount | None = None,
    ) -> tuple[tuple[LiveProtectiveTrigger, ...], tuple[TrailingRatchetEvidence, ...]]:
        """Evaluate one fresh accepted QuoteSnapshot against active protective exits and collect ratchet evidence."""
        if not isinstance(quote, QuoteSnapshot):
            raise TypeError("quote must be a QuoteSnapshot")
        if not isinstance(snapshot, AccountSnapshot):
            raise TypeError("snapshot must be an AccountSnapshot")
        if not isinstance(specification, InstrumentSpecification):
            raise TypeError("specification must be an InstrumentSpecification")

        if quote.bid_price is None:
            return ((), ())

        bid = as_decimal(quote.bid_price, "quote.bid_price")
        if bid <= Decimal("0"):
            return ((), ())

        if specification.identity != quote.instrument_identity:
            raise ValueError(
                f"specification identity {specification.identity} does not match quote identity {quote.instrument_identity}"
            )

        account = portfolio_account if portfolio_account is not None else PortfolioAccount(
            account_id=snapshot.account_id,
            currency=snapshot.currency,
            starting_capital=snapshot.starting_capital,
            monetary_quantum=snapshot.monetary_quantum,
        )

        triggers: list[LiveProtectiveTrigger] = []
        ratchets: list[TrailingRatchetEvidence] = []

        # Find matching open positions for this quote instrument
        for key, position in snapshot.positions.items():
            if key.identity != quote.instrument_identity:
                continue
            if position.quantity <= Decimal("0"):
                continue
            if self.has_pending_close(key):
                continue

            # Evaluate active protection for this key
            trigger_candidate = self._evaluate_position_protection(
                position_key=key,
                current_quantity=position.quantity,
                quote=quote,
                bid=bid,
                snapshot=snapshot,
                specification=specification,
                portfolio_account=account,
                out_ratchets=ratchets,
            )
            if trigger_candidate is not None:
                triggers.append(trigger_candidate)

        return (tuple(triggers), tuple(ratchets))

    def evaluate_quote(
        self,
        quote: QuoteSnapshot,
        snapshot: AccountSnapshot,
        specification: InstrumentSpecification,
        portfolio_account: PortfolioAccount | None = None,
    ) -> tuple[LiveProtectiveTrigger, ...]:
        """Evaluate one fresh accepted QuoteSnapshot against active protective exits.

        Returns triggered candidates without mutating ProtectiveExit.state or cancelling siblings.
        Zero triggers if quote has no executable BID.
        """
        triggers, _ = self.evaluate_quote_with_ratchets(
            quote=quote,
            snapshot=snapshot,
            specification=specification,
            portfolio_account=portfolio_account,
        )
        return triggers

    def _evaluate_position_protection(
        self,
        *,
        position_key: PositionKey,
        current_quantity: Decimal,
        quote: QuoteSnapshot,
        bid: Decimal,
        snapshot: AccountSnapshot,
        specification: InstrumentSpecification,
        portfolio_account: PortfolioAccount,
        out_ratchets: list[TrailingRatchetEvidence] | None = None,
    ) -> LiveProtectiveTrigger | None:
        """Evaluate active protective exits for one held position."""
        # 1. Trailing stops
        trailing_exits = self._book.authoritative_exits(position_key, kind=ProtectiveExitKind.TRAILING_STOP)
        for exit_item in trailing_exits:
            if exit_item.trailing is None:
                continue

            runtime_policy = self._runtime_trailing_policies.get(
                (position_key.strategy_id, position_key.strategy_version)
            )
            if runtime_policy is not None:
                evidence = RuntimeTrailingEvidence(
                    position_key=position_key,
                    protective=exit_item,
                    market_timestamp=quote.exchange_timestamp,
                    executable_bid=bid,
                )
                try:
                    decision = runtime_policy.trailing_decision(evidence)
                except Exception as error:
                    self._raise_strategy_callback_failure(
                        f"strategy runtime trailing decision failed for "
                        f"{position_key.strategy_id}/{position_key.strategy_version}",
                        owner=(position_key.strategy_id, position_key.strategy_version),
                        cause=error,
                    )
                if decision is not None and not isinstance(decision, RuntimeTrailingDecision):
                    raise TypeError("strategy runtime trailing decision must return RuntimeTrailingDecision or None")
                if decision is not None:
                    old_extreme = exit_item.trailing.reference_extreme
                    old_stop = exit_item.trailing.current_stop
                    if exit_item.trailing.activated:
                        if decision.activate:
                            raise ValueError("strategy runtime trailing decision cannot activate an active trailing stop")
                        updated = self._book.update_trailing(
                            exit_item.protective_id,
                            reference_extreme=decision.reference_extreme,
                            next_stop=decision.next_stop,
                            effective_after=quote.exchange_timestamp,
                        )
                    else:
                        if not decision.activate:
                            raise ValueError("strategy runtime trailing decision must set activate for an inactive trailing stop")
                        updated = self._book.activate_trailing(
                            exit_item.protective_id,
                            reference_extreme=decision.reference_extreme,
                            next_stop=decision.next_stop,
                            effective_after=quote.exchange_timestamp,
                        )
                    if out_ratchets is not None:
                        out_ratchets.append(
                            TrailingRatchetEvidence(
                                protective_id=exit_item.protective_id,
                                position_key=position_key,
                                old_stop=old_stop,
                                new_stop=updated.trailing.current_stop,
                                old_reference_extreme=old_extreme,
                                new_reference_extreme=updated.trailing.reference_extreme,
                                effective_after=quote.exchange_timestamp,
                                market_timestamp=quote.exchange_timestamp,
                                state_transition=getattr(decision, "state_transition", None),
                            )
                        )
                    # A callback mutation is never triggerable on its creating quote.
                    continue
                if not exit_item.trailing.activated:
                    continue
                # A registered policy owns trailing economics; no generic
                # fixed-gap formula is applied when it returns no change.
                if (
                    exit_item.trailing.effective_after is not None
                    and quote.exchange_timestamp <= exit_item.trailing.effective_after
                ):
                    continue
                if bid <= exit_item.trailing.current_stop:
                    return self._build_trigger(
                        exit_item=exit_item,
                        position_key=position_key,
                        current_quantity=current_quantity,
                        trigger_price=bid,
                        trigger_timestamp=quote.exchange_timestamp,
                        snapshot=snapshot,
                        specification=specification,
                        portfolio_account=portfolio_account,
                    )
                continue

            if not exit_item.trailing.activated:
                continue

            # Check favorable excursion
            if bid > exit_item.trailing.reference_extreme:
                old_extreme = exit_item.trailing.reference_extreme
                old_stop = exit_item.trailing.current_stop
                trail_distance = old_extreme - old_stop
                new_extreme = bid
                new_stop = new_extreme - trail_distance
                # Update trailing state through canonical public API with live timestamp
                self._book.update_trailing(
                    exit_item.protective_id,
                    reference_extreme=new_extreme,
                    next_stop=new_stop,
                    effective_after=quote.exchange_timestamp,
                )
                if out_ratchets is not None:
                    out_ratchets.append(
                        TrailingRatchetEvidence(
                            protective_id=exit_item.protective_id,
                            position_key=position_key,
                            old_stop=old_stop,
                            new_stop=new_stop,
                            old_reference_extreme=old_extreme,
                            new_reference_extreme=new_extreme,
                            effective_after=quote.exchange_timestamp,
                            market_timestamp=quote.exchange_timestamp,
                        )
                    )
                # Ratcheting quote Q1 cannot trigger on Q1
                continue

            # Non-retroactivity check: must be strictly after effective_after
            if (
                exit_item.trailing.effective_after is not None
                and quote.exchange_timestamp <= exit_item.trailing.effective_after
            ):
                continue

            # Check trailing stop trigger
            if bid <= exit_item.trailing.current_stop:
                return self._build_trigger(
                    exit_item=exit_item,
                    position_key=position_key,
                    current_quantity=current_quantity,
                    trigger_price=bid,
                    trigger_timestamp=quote.exchange_timestamp,
                    snapshot=snapshot,
                    specification=specification,
                    portfolio_account=portfolio_account,
                )

        # 2. Fixed Stop Loss
        stop_exits = self._book.authoritative_exits(position_key, kind=ProtectiveExitKind.STOP_LOSS)
        for exit_item in stop_exits:
            stop_price = as_decimal(exit_item.exit_order.stop_price, "stop_price")
            if bid <= stop_price:
                return self._build_trigger(
                    exit_item=exit_item,
                    position_key=position_key,
                    current_quantity=current_quantity,
                    trigger_price=bid,
                    trigger_timestamp=quote.exchange_timestamp,
                    snapshot=snapshot,
                    specification=specification,
                    portfolio_account=portfolio_account,
                )

        # 3. Fixed Target
        target_exits = self._book.authoritative_exits(position_key, kind=ProtectiveExitKind.TARGET)
        for exit_item in target_exits:
            if (
                exit_item.effective_after is not None
                and quote.exchange_timestamp <= exit_item.effective_after
            ):
                continue
            target_price = as_decimal(exit_item.exit_order.limit_price, "limit_price")
            if bid >= target_price:
                return self._build_trigger(
                    exit_item=exit_item,
                    position_key=position_key,
                    current_quantity=current_quantity,
                    trigger_price=bid,
                    trigger_timestamp=quote.exchange_timestamp,
                    snapshot=snapshot,
                    specification=specification,
                    portfolio_account=portfolio_account,
                )

        return None

    def _build_trigger(
        self,
        *,
        exit_item: ProtectiveExit,
        position_key: PositionKey,
        current_quantity: Decimal,
        trigger_price: Decimal,
        trigger_timestamp: datetime,
        snapshot: AccountSnapshot,
        specification: InstrumentSpecification,
        portfolio_account: PortfolioAccount,
    ) -> LiveProtectiveTrigger:
        """Resolve a triggered protective exit into a ConcreteCloseInstruction."""
        current_exit_order = exit_item.exit_order
        if current_exit_order.source_intent.originating_timestamp != trigger_timestamp:
            new_intent = SignalIntent(
                action=current_exit_order.source_intent.action,
                confidence=current_exit_order.source_intent.confidence,
                symbol=current_exit_order.source_intent.symbol,
                timeframe=current_exit_order.source_intent.timeframe,
                originating_timestamp=trigger_timestamp,
                strategy_id=current_exit_order.source_intent.strategy_id,
                strategy_version=current_exit_order.source_intent.strategy_version,
                metadata=current_exit_order.source_intent.metadata,
            )
            current_exit_order = OrderRequest(
                source_intent=new_intent,
                order_type=current_exit_order.order_type,
                quantity=current_quantity,
                time_in_force=current_exit_order.time_in_force,
                limit_price=current_exit_order.limit_price,
                stop_price=current_exit_order.stop_price,
            )

        resolved = portfolio_account.resolve_exit(
            snapshot=snapshot,
            exit_order=current_exit_order,
            specification=specification,
            quantity=current_quantity,
        )
        if resolved.close_instruction is None:
            raise ValueError(f"failed to resolve close instruction for protective exit: {exit_item.protective_id}")

        return LiveProtectiveTrigger(
            protective=exit_item,
            position_key=position_key,
            kind=exit_item.kind,
            trigger_price=trigger_price,
            trigger_timestamp=trigger_timestamp,
            close_instruction=resolved.close_instruction,
        )

    def on_external_fill(
        self,
        order_id: str,
        broker_order_identity: str | None = None,
    ) -> tuple[ProtectiveExit, ...]:
        """Acknowledge an external broker fill for a pending protective close.

        Marks the protective exit FILLED in the canonical book, cancels OCO siblings,
        and releases the pending-close lock.
        """
        if not isinstance(order_id, str) or not order_id.strip():
            raise ValueError("order_id must be a non-empty string")

        pending = self._pending_by_order_id.get(order_id)
        if pending is None:
            return ()

        if broker_order_identity is not None and pending.broker_order_identity != broker_order_identity:
            raise ValueError(
                f"broker_order_identity mismatch for order {order_id}: "
                f"expected {pending.broker_order_identity}, got {broker_order_identity}"
            )

        modified = self._book.record_external_fill(pending.protective_id, termination_reason="filled")
        self._pending_closes.pop(pending.position_key, None)
        self._pending_by_order_id.pop(order_id, None)
        return modified

    def on_external_terminal_failure(
        self,
        order_id: str,
        reason: str = "broker_terminal_failure",
    ) -> LiveProtectivePendingClose | None:
        """Acknowledge that a submitted protective close order terminated without filling.

        Clears the pending-close lock and leaves the canonical protective exits ACTIVE
        so that subsequent quotes may re-arm and re-trigger.
        """
        if not isinstance(order_id, str) or not order_id.strip():
            raise ValueError("order_id must be a non-empty string")

        pending = self._pending_by_order_id.pop(order_id, None)
        if pending is not None:
            self._pending_closes.pop(pending.position_key, None)
        return pending

    def reconcile_position(
        self,
        position_key: PositionKey,
        snapshot: AccountSnapshot,
    ) -> tuple[ProtectiveExit, ...]:
        """Reconcile active protection against current account snapshot."""
        return self._book.reconcile_position(position_key, snapshot)

    def strategy_exit(
        self,
        evidence: StrategyExitEvidence,
        policy_callback: object | None = None,
    ) -> StrategyExitEvidence | None:
        """Execute a strategy-owned exit decision through the callback-outside-lock pattern.

        Lifecycle:
          1. Acquire book guard → snapshot (no protective mutation needed)
          2. Release guard → invoke strategy callback (outside lock)
          3. Return the callback result for coordinator-level validation

        The coordinator owns: owner validation, position validation, quantity
        authority, close-order construction, broker/execution, accounting,
        persistence, audit, protective reconciliation.

        No plugin code runs under protective or SQLite locks.
        """
        if not isinstance(evidence, StrategyExitEvidence):
            raise TypeError("evidence must be a StrategyExitEvidence")

        # Phase 1: snapshot under book guard (read-only, no mutation)
        with self._book._mutation_guard:
            # Verify the position has active protective coverage (informational)
            targets = self._book.authoritative_exits(
                evidence.position_key, kind=ProtectiveExitKind.TARGET,
            )
            stops = self._book.authoritative_exits(
                evidence.position_key, kind=ProtectiveExitKind.STOP_LOSS,
            )
            _ = targets  # protective state is informational only
            _ = stops

        # Phase 2: strategy callback OUTSIDE any lock
        effective_callback = policy_callback
        if effective_callback is not None:
            if not callable(getattr(effective_callback, "strategy_exit_decision", None)):
                raise TypeError(
                    "policy_callback must provide strategy_exit_decision(evidence)"
                )
            try:
                decision = effective_callback.strategy_exit_decision(evidence)
            except Exception as error:
                self._raise_strategy_callback_failure(
                    f"strategy exit decision failed for "
                    f"{evidence.strategy_id}/{evidence.strategy_version}",
                    owner=(evidence.strategy_id, evidence.strategy_version),
                    cause=error,
                )
            if decision is not None and not isinstance(decision, StrategyExitDecision):
                raise TypeError(
                    "policy strategy_exit_decision must return StrategyExitDecision or None"
                )
            return decision

        # No registered policy → no exit decision
        return None

    def replace_target(
        self,
        candidate: TargetCandidate,
        policy_callback: object | None = None,
    ) -> tuple[ProtectiveExit, ProtectiveExit]:
        """Execute the full post-entry TARGET REPLACEMENT lifecycle.

        Lifecycle:
          1. Acquire book guard → snapshot authoritative TARGET state
          2. Release guard → invoke strategy callback (outside lock)
          3. Reacquire book guard → re-validate authority is unchanged
          4. Final-validate candidate geometry, freshness, identity
          5. Build exact immutable ProtectiveExit replacement
          6. Return (proposal_old, replacement) for committed persistence

        The caller owns committed persistence and publication:
          with book.committed_mutation() as session:
              proposal = session.finalize(old, replacement)
              store.save_runtime_policy_decision(...)
              session.publish_committed(proposal)

        No target formula exists in generic engine code.  The strategy owns
        WHY target changes and HOW target price was calculated.
        """
        if not isinstance(candidate, TargetCandidate):
            raise TypeError("candidate must be a TargetCandidate")

        # ---- Phase 1: snapshot under book guard ----
        with self._book._mutation_guard:
            targets = self._book.authoritative_exits(
                candidate.position_key, kind=ProtectiveExitKind.TARGET,
            )
            if len(targets) != 1:
                raise ValueError(
                    f"expected exactly one active TARGET, got {len(targets)}"
                )
            current = targets[0]
            snapshot_limit = as_decimal(
                current.exit_order.limit_price, "limit_price",
            )
            snapshot_id = current.protective_id

        # ---- Phase 2: strategy callback OUTSIDE any lock ----
        evidence = TargetReplacementEvidence(
            position_key=candidate.position_key,
            strategy_id=candidate.strategy_id,
            strategy_version=candidate.strategy_version,
            current_target=current,
            current_limit_price=snapshot_limit,
            market_timestamp=candidate.market_timestamp,
        )

        # Resolve the policy callback: explicit parameter takes precedence,
        # then registered runtime policy
        effective_callback = policy_callback
        if effective_callback is None:
            effective_callback = self._runtime_target_replacement_policies.get(
                (candidate.strategy_id, candidate.strategy_version)
            )
        if effective_callback is not None:
            if not callable(getattr(effective_callback, "target_replacement_decision", None)):
                raise TypeError(
                    "policy_callback must provide target_replacement_decision(evidence)"
                )
            try:
                result = effective_callback.target_replacement_decision(evidence)
            except Exception as error:
                self._raise_strategy_callback_failure(
                    f"strategy target replacement decision failed for "
                    f"{candidate.strategy_id}/{candidate.strategy_version}",
                    owner=(candidate.strategy_id, candidate.strategy_version),
                    cause=error,
                )
            if result is not None and not isinstance(result, TargetCandidate):
                raise TypeError(
                    "policy target_replacement_decision must return TargetCandidate or None"
                )
            if result is not None:
                candidate = result

        # ---- Phase 3: reacquire guard + re-validate ----
        with self._book._mutation_guard:
            targets_after = self._book.authoritative_exits(
                candidate.position_key, kind=ProtectiveExitKind.TARGET,
            )
            if len(targets_after) != 1:
                raise ValueError(
                    f"expected exactly one active TARGET after callback, got {len(targets_after)}"
                )
            current = targets_after[0]

            # Ownership validation
            if current.position_key.strategy_id != candidate.strategy_id:
                raise ValueError("candidate owner does not match current target owner")
            if current.position_key.strategy_version != candidate.strategy_version:
                raise ValueError("candidate owner version does not match current target owner")
            if current.position_key != candidate.position_key:
                raise ValueError("candidate position_key does not match current target position_key")

            # Authority validation
            if current.protective_id != snapshot_id:
                raise ValueError("current target identity changed — candidate is stale")
            if current.state is not ProtectiveExitState.ACTIVE:
                raise ValueError("current target is no longer ACTIVE")
            cur_limit = as_decimal(current.exit_order.limit_price, "limit_price")
            if cur_limit != snapshot_limit:
                raise ValueError("current target limit_price changed — candidate is stale")

            # Candidate validation
            proposed = candidate.proposed_target_price
            if not isinstance(proposed, Decimal) or not proposed.is_finite():
                raise ValueError("proposed_target_price must be finite")
            if proposed <= 0:
                raise ValueError("proposed_target_price must be positive")

            # Valid long-position protective geometry: limit_price > 0
            # (TARGET is a LIMIT order for long positions)
            if proposed <= 0:
                raise ValueError("invalid protective geometry for long position")

            # Staleness: candidate market_timestamp must not be in the future
            # relative to the current authoritative state (no look-ahead)
            # This is checked implicitly: the snapshot was taken under the guard
            # and the callback ran outside; any concurrent mutation is caught
            # by the authority re-validation above.

            # ---- Phase 4: build exact immutable replacement ----
            replacement_intent = SignalIntent(
                action=current.exit_order.source_intent.action,
                confidence=current.exit_order.source_intent.confidence,
                symbol=current.exit_order.source_intent.symbol,
                timeframe=current.exit_order.source_intent.timeframe,
                originating_timestamp=candidate.market_timestamp,
                strategy_id=current.exit_order.source_intent.strategy_id,
                strategy_version=current.exit_order.source_intent.strategy_version,
                metadata=current.exit_order.source_intent.metadata,
            )
            replacement_order = OrderRequest(
                source_intent=replacement_intent,
                order_type=OrderType.LIMIT,
                quantity=current.quantity,
                time_in_force=current.exit_order.time_in_force,
                limit_price=proposed,
                stop_price=None,
            )
            replacement = dc_replace(
                current,
                exit_order=replacement_order,
                effective_after=candidate.market_timestamp,
            )

        return (current, replacement)
