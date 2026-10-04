"""Simulated paper-broker for Phase 5 paper trading.

Deterministic, in-memory, stateful virtual broker that turns Slice 3A's
stateless PaperFillAdapter into stateful virtual paper-order execution.

Frozen contracts:
  - OD-2 (§99): ExecutionAdapter architecture — PaperFillAdapter as distinct path
  - OD-3 (§99): Paper Fill Realism V1 — bid/ask fills, slippage, stale rejection
  - OD-5 (§99): Order lifecycle — CREATED/VALIDATED/QUEUED/FILLED/EXPIRED/CANCELLED/REJECTED
  - D11 (§91): Three-layer defense-in-depth idempotency
  - §100 (Slice 3A closure): PaperFillAdapter verified contract preserved unchanged

Owner-approved preflight: SLICE3B_PREFLIGHT_READY.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Literal, Mapping, Sequence

from engine.execution.adapter import ExecutionAdapter
from engine.execution.model import (
    ExecutionResult,
    ExecutableOrder,
)
from engine.execution.paper_fill import (
    PaperFillAdapter,
    ExecutionEvaluationContext,
)
from engine.execution.quote import QuoteSnapshot
from engine.orders.lifecycle import OrderLifecycleState
from engine.orders.model import (
    ConcreteCloseInstruction,
    OrderRequest,
    OrderType,
    TimeInForce,
)
from engine.portfolio.model import InstrumentIdentity, InstrumentSpecification
from engine.portfolio.model import as_decimal
from engine.reproducibility.codec import CanonicalCodec
from engine.risk.risk_manager import entry_intent_identity

logger = logging.getLogger(__name__)

__all__ = [
    "BrokerQuoteEvent",
    "BrokerSubmissionResult",
    "BrokerTerminalEvent",
    "BrokerCancelResult",
    "BrokerOrderRecord",
    "SimulatedPaperBroker",
]


# ---------------------------------------------------------------------------
# Immutable public types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BrokerQuoteEvent:
    """Immutable wrapper carrying a QuoteSnapshot with broker-required metadata.

    Created by the caller (PaperTradingRunner or future LiveDataFeed adapter).
    The broker does NOT construct these; it only receives and processes them.
    """
    event_id: str
    quote: QuoteSnapshot
    authority_timestamp: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, str) or not self.event_id.strip():
            raise ValueError("event_id must be a non-empty string")
        if not isinstance(self.quote, QuoteSnapshot):
            raise TypeError("quote must be a QuoteSnapshot")
        if not isinstance(self.authority_timestamp, datetime):
            raise TypeError("authority_timestamp must be a datetime")
        if self.authority_timestamp.tzinfo is None or self.authority_timestamp.utcoffset() is None:
            raise ValueError("authority_timestamp must be timezone-aware")


@dataclass(frozen=True)
class BrokerSubmissionResult:
    """Immutable result of a broker order submission attempt."""
    accepted: bool
    order_id: str | None = None
    broker_order_identity: str | None = None
    reason: str | None = None
    duplicate: bool = False
    existing_terminal_event: BrokerTerminalEvent | None = None


@dataclass(frozen=True)
class BrokerTerminalEvent:
    """Immutable evidence of a broker order reaching a terminal state.

    Used for all terminal outcomes: FILLED, CANCELLED, EXPIRED, REJECTED.
    """
    order_id: str
    broker_order_identity: str
    original_order: ExecutableOrder
    instrument_identity: InstrumentIdentity
    lifecycle_state: OrderLifecycleState
    market_timestamp: datetime
    execution_result: ExecutionResult | None = None
    reason: str | None = None


@dataclass(frozen=True)
class BrokerCancelResult:
    """Immutable result of a cancel attempt."""
    cancelled: bool
    order_id: str
    reason: str | None = None


@dataclass(frozen=True)
class BrokerOrderRecord:
    """Immutable public view of a broker order's current state."""
    order_id: str
    broker_order_identity: str
    original_order: ExecutableOrder
    instrument_identity: InstrumentIdentity
    lifecycle_state: OrderLifecycleState
    submission_market_timestamp: datetime
    eligibility_timestamp: datetime
    reference_price: Decimal
    stop_triggered: bool
    stop_limit_activated: bool
    stop_limit_activation_timestamp: datetime | None = None
    stop_limit_activation_price: Decimal | None = None


# ---------------------------------------------------------------------------
# Internal mutable state (not part of public API)
# ---------------------------------------------------------------------------

@dataclass
class _PendingOrder:
    """Internal broker-owned pending order state."""
    order_id: str
    broker_order_identity: str
    original_order: ExecutableOrder
    instrument_identity: InstrumentIdentity
    specification: InstrumentSpecification
    reference_price: Decimal
    price_increment: Decimal
    execution_context: ExecutionEvaluationContext
    lifecycle_state: OrderLifecycleState
    submission_market_timestamp: datetime
    eligibility_timestamp: datetime
    stop_triggered: bool = False
    stop_limit_activated: bool = False
    stop_limit_activation_timestamp: datetime | None = None
    stop_limit_activation_price: Decimal | None = None


# ---------------------------------------------------------------------------
# Canonical identity helpers
# ---------------------------------------------------------------------------

def _execution_side(order: ExecutableOrder) -> Literal["BUY", "SELL"]:
    """Extract the concrete execution side from an executable order."""
    action = order.action
    if action == "EXIT":
        raise ValueError(
            "raw EXIT orders cannot reach the broker; "
            "resolve via PortfolioAccount.resolve_exit() -> ConcreteCloseInstruction"
        )
    if action not in ("BUY", "SELL"):
        raise ValueError(f"unrecognized execution action: {action!r}")
    return action


def _broker_order_identity(order: ExecutableOrder, instrument_identity: InstrumentIdentity) -> str:
    """Canonical broker Layer-3 order identity (D11 defense-in-depth).

    Embeds the existing entry-intent identity (D11 Layer 2) plus
    execution-side discriminators that D11 Layer 2 excludes.
    Timestamp alone is NEVER sufficient per D11.
    """
    side = _execution_side(order)
    return CanonicalCodec.fingerprint(
        "algofortis-paper-broker-order/v1",
        (
            ("entry_intent_identity", entry_intent_identity(
                strategy_id=order.strategy_id,
                strategy_version=order.strategy_version,
                identity=instrument_identity,
                timeframe=order.timeframe,
                originating_timestamp=order.originating_timestamp,
            )),
            ("action", order.action),
            ("order_type", order.order_type.value),
            ("quantity", str(order.quantity)),
            ("limit_price", str(order.limit_price) if order.limit_price is not None else None),
            ("stop_price", str(order.stop_price) if order.stop_price is not None else None),
            ("time_in_force", order.time_in_force.value),
        ),
    )


# ---------------------------------------------------------------------------
# SimulatedPaperBroker
# ---------------------------------------------------------------------------

class SimulatedPaperBroker:
    """Stateful, deterministic virtual paper-order broker.

    Owns pending orders, lifecycle transitions, repeated quote-event
    evaluation, latency eligibility, stale-quote filtering, TIF expiration,
    STOP trigger state, STOP_LIMIT activation state, in-memory idempotency.

    Stateless fill economics are delegated to PaperFillAdapter (Slice 3A).
    """

    def __init__(
        self,
        *,
        adapter: PaperFillAdapter,
        latency: timedelta = timedelta(0),
        stale_quote_threshold: timedelta = timedelta(seconds=5),
    ) -> None:
        if not isinstance(adapter, PaperFillAdapter):
            raise TypeError("adapter must be a PaperFillAdapter")
        if not isinstance(latency, timedelta):
            raise TypeError("latency must be a timedelta")
        if latency < timedelta(0):
            raise ValueError("latency must be non-negative")
        if not isinstance(stale_quote_threshold, timedelta):
            raise TypeError("stale_quote_threshold must be a timedelta")
        if stale_quote_threshold <= timedelta(0):
            raise ValueError("stale_quote_threshold must be positive")

        self._adapter = adapter
        self._latency = latency
        self._stale_quote_threshold = stale_quote_threshold

        # Internal state
        self._pending: dict[str, _PendingOrder] = {}
        self._terminal: dict[str, BrokerTerminalEvent] = {}
        self._processed_event_ids: set[str] = set()
        self._last_exchange_ts: dict[InstrumentIdentity, datetime] = {}

    @property
    def pending_orders(self) -> Mapping[str, _PendingOrder]:
        """Active queued pending orders keyed by order_id."""
        return dict(self._pending)

    @property
    def terminal_orders(self) -> Mapping[str, BrokerTerminalEvent]:
        """Terminal broker events keyed by order_id."""
        return dict(self._terminal)

    @property
    def last_exchange_timestamps(self) -> Mapping[InstrumentIdentity, datetime]:
        """Per-instrument last exchange timestamp watermarks."""
        return dict(self._last_exchange_ts)

    def get_order_snapshots(self) -> tuple[tuple[BrokerOrderRecord, ...], tuple[BrokerTerminalEvent, ...]]:
        """Return an immutable snapshot of all pending and terminal orders."""
        pending = tuple(
            BrokerOrderRecord(
                order_id=po.order_id,
                broker_order_identity=po.broker_order_identity,
                original_order=po.original_order,
                instrument_identity=po.instrument_identity,
                lifecycle_state=po.lifecycle_state,
                submission_market_timestamp=po.submission_market_timestamp,
                eligibility_timestamp=po.eligibility_timestamp,
                reference_price=po.reference_price,
                stop_triggered=po.stop_triggered,
                stop_limit_activated=po.stop_limit_activated,
                stop_limit_activation_timestamp=po.stop_limit_activation_timestamp,
                stop_limit_activation_price=po.stop_limit_activation_price,
            )
            for po in self._pending.values()
        )
        terminal = tuple(self._terminal.values())
        return pending, terminal

    @classmethod
    def restore(
        cls,
        *,
        adapter: PaperFillAdapter,
        latency: timedelta = timedelta(0),
        stale_quote_threshold: timedelta = timedelta(seconds=5),
        pending_orders: Sequence[_PendingOrder] | Mapping[str, _PendingOrder] | None = None,
        terminal_orders: Sequence[BrokerTerminalEvent] | Mapping[str, BrokerTerminalEvent] | None = None,
        last_exchange_timestamps: Mapping[InstrumentIdentity, datetime] | None = None,
    ) -> "SimulatedPaperBroker":
        """Restore a SimulatedPaperBroker exactly from authoritative persisted state."""
        broker = cls(
            adapter=adapter,
            latency=latency,
            stale_quote_threshold=stale_quote_threshold,
        )
        if pending_orders:
            if isinstance(pending_orders, Mapping):
                broker._pending = dict(pending_orders)
            else:
                broker._pending = {po.order_id: po for po in pending_orders}
        if terminal_orders:
            if isinstance(terminal_orders, Mapping):
                broker._terminal = dict(terminal_orders)
            else:
                broker._terminal = {te.order_id: te for te in terminal_orders}
        if last_exchange_timestamps:
            broker._last_exchange_ts = dict(last_exchange_timestamps)
        return broker

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(
        self,
        order: ExecutableOrder,
        *,
        instrument_identity: InstrumentIdentity,
        specification: InstrumentSpecification,
        submission_quote: QuoteSnapshot,
        submission_market_timestamp: datetime,
    ) -> BrokerSubmissionResult:
        """Submit an executable order for paper trading.

        Returns immediately. No sleep(). No wall clock.
        The order enters QUEUED state on successful acceptance.
        """
        # --- Validate execution side ---
        try:
            _execution_side(order)
        except ValueError:
            return BrokerSubmissionResult(
                accepted=False,
                reason="unresolved_exit_action",
            )

        # --- Validate timestamps ---
        if not isinstance(submission_market_timestamp, datetime):
            return BrokerSubmissionResult(
                accepted=False,
                reason="submission_market_timestamp_must_be_datetime",
            )
        if submission_market_timestamp.tzinfo is None or submission_market_timestamp.utcoffset() is None:
            return BrokerSubmissionResult(
                accepted=False,
                reason="submission_market_timestamp_must_be_timezone_aware",
            )

        # --- Validate instrument match ---
        if submission_quote.instrument_identity != instrument_identity:
            return BrokerSubmissionResult(
                accepted=False,
                reason="submission_quote_instrument_mismatch",
            )

        # --- Compute canonical identity ---
        canonical_id = _broker_order_identity(order, instrument_identity)

        # --- Dedup check ---
        if canonical_id in {p.broker_order_identity for p in self._pending.values()}:
            existing = next(p for p in self._pending.values() if p.broker_order_identity == canonical_id)
            term = self._terminal.get(existing.order_id)
            return BrokerSubmissionResult(
                accepted=False,
                reason="duplicate_order",
                duplicate=True,
                order_id=existing.order_id,
                broker_order_identity=canonical_id,
                existing_terminal_event=term,
            )
        if canonical_id in {t.broker_order_identity for t in self._terminal.values()}:
            term = next(t for t in self._terminal.values() if t.broker_order_identity == canonical_id)
            return BrokerSubmissionResult(
                accepted=False,
                reason="duplicate_of_terminal_order",
                duplicate=True,
                order_id=term.order_id,
                broker_order_identity=canonical_id,
                existing_terminal_event=term,
            )

        # --- Extract concrete execution side ---
        side = order.action  # BUY or SELL (never EXIT at this point)

        # --- Submission quote validation ---
        exec_side_result = self._validate_submission_quote(
            submission_quote, side, submission_market_timestamp,
            self._stale_quote_threshold,
        )
        if exec_side_result is not None:
            return exec_side_result

        # --- Capture immutable reference price ---
        if side == "BUY":
            ref_price = submission_quote.ask_price
        else:
            ref_price = submission_quote.bid_price

        price_increment = specification.price_increment
        eligibility_ts = submission_market_timestamp + self._latency

        ctx = ExecutionEvaluationContext(
            reference_price=ref_price,
            price_increment=price_increment,
        )

        order_id = canonical_id  # use canonical identity as internal order ID

        pending = _PendingOrder(
            order_id=order_id,
            broker_order_identity=canonical_id,
            original_order=order,
            instrument_identity=instrument_identity,
            specification=specification,
            reference_price=ref_price,
            price_increment=price_increment,
            execution_context=ctx,
            lifecycle_state=OrderLifecycleState.QUEUED,
            submission_market_timestamp=submission_market_timestamp,
            eligibility_timestamp=eligibility_ts,
        )
        self._pending[order_id] = pending

        return BrokerSubmissionResult(
            accepted=True,
            order_id=order_id,
            broker_order_identity=canonical_id,
        )

    def on_quote_event(self, event: BrokerQuoteEvent) -> list[BrokerTerminalEvent]:
        """Process one broker quote event against all matching queued orders.

        Returns zero or more terminal events. Deterministic. No wall clock.
        """
        terminals: list[BrokerTerminalEvent] = []

        # Step 1: validate BrokerQuoteEvent
        if not isinstance(event, BrokerQuoteEvent):
            logger.warning("on_quote_event received non-BrokerQuoteEvent, skipping")
            return []

        # Step 2: dedup by event_id
        if event.event_id in self._processed_event_ids:
            return []
        quote = event.quote

        # Step 3: reject future-dated / out-of-order evidence
        instr = quote.instrument_identity
        last_ts = self._last_exchange_ts.get(instr)
        if last_ts is not None and quote.exchange_timestamp <= last_ts:
            return []  # out-of-order, skip

        # Step 4: staleness / freshness validation
        quote_age = event.authority_timestamp - quote.exchange_timestamp
        if quote_age > self._stale_quote_threshold:
            return []  # stale, skip
        if quote_age < timedelta(0):
            return []  # future-dated, fail closed

        # Step 5: record event as processed
        self._processed_event_ids.add(event.event_id)
        self._last_exchange_ts[instr] = quote.exchange_timestamp

        # Step 6: route by InstrumentIdentity
        matching_orders = sorted(
            [p for p in self._pending.values() if p.instrument_identity == instr],
            key=lambda p: (p.submission_market_timestamp, p.order_id),
        )

        # Steps 7–9: evaluate each matching order
        for po in matching_orders:
            # 7a: terminal suppression
            if po.order_id in self._terminal:
                continue

            # 7b: latency eligibility
            if quote.exchange_timestamp < po.eligibility_timestamp:
                continue

            # 7c: STOP / STOP_LIMIT trigger detection
            if po.original_order.order_type in (OrderType.STOP, OrderType.STOP_LIMIT):
                self._check_stop_trigger(po, quote)

            # 7d+7e: delegate to PaperFillAdapter (may return None for untriggered)
            result = self._evaluate_order(po, quote)

            # 7f: apply lifecycle result
            if result is not None and result.outcome.name == "FILLED":
                terminal = BrokerTerminalEvent(
                    order_id=po.order_id,
                    broker_order_identity=po.broker_order_identity,
                    original_order=po.original_order,
                    instrument_identity=po.instrument_identity,
                    lifecycle_state=OrderLifecycleState.FILLED,
                    market_timestamp=quote.exchange_timestamp,
                    execution_result=result,
                )
                self._terminal[po.order_id] = terminal
                del self._pending[po.order_id]
                terminals.append(terminal)

        return terminals

    def cancel(
        self,
        order_id: str,
        cancel_market_timestamp: datetime,
    ) -> BrokerCancelResult:
        """Explicitly cancel a queued order."""
        if order_id in self._terminal:
            return BrokerCancelResult(
                cancelled=False,
                order_id=order_id,
                reason="already_terminal",
            )
        if order_id not in self._pending:
            return BrokerCancelResult(
                cancelled=False,
                order_id=order_id,
                reason="order_not_found",
            )
        po = self._pending.pop(order_id)
        terminal = BrokerTerminalEvent(
            order_id=order_id,
            broker_order_identity=po.broker_order_identity,
            original_order=po.original_order,
            instrument_identity=po.instrument_identity,
            lifecycle_state=OrderLifecycleState.CANCELLED,
            market_timestamp=cancel_market_timestamp,
            reason="explicit_cancel",
        )
        self._terminal[order_id] = terminal
        return BrokerCancelResult(cancelled=True, order_id=order_id)

    def expire_day_session(
        self,
        session_end_market_timestamp: datetime,
    ) -> list[BrokerTerminalEvent]:
        """Expire all DAY orders that are still QUEUED."""
        terminals: list[BrokerTerminalEvent] = []
        to_expire = [
            oid for oid, po in self._pending.items()
            if po.original_order.time_in_force is TimeInForce.DAY
        ]
        for order_id in to_expire:
            po = self._pending.pop(order_id)
            terminal = BrokerTerminalEvent(
                order_id=order_id,
                broker_order_identity=po.broker_order_identity,
                original_order=po.original_order,
                instrument_identity=po.instrument_identity,
                lifecycle_state=OrderLifecycleState.EXPIRED,
                market_timestamp=session_end_market_timestamp,
                reason="day_tif_expired",
            )
            self._terminal[order_id] = terminal
            terminals.append(terminal)
        return terminals

    def get_order(self, order_id: str) -> BrokerOrderRecord | None:
        """Return a read-only view of one order's current state."""
        po = self._pending.get(order_id)
        if po is not None:
            return self._to_record(po)
        te = self._terminal.get(order_id)
        if te is not None:
            return BrokerOrderRecord(
                order_id=te.order_id,
                broker_order_identity=te.broker_order_identity,
                original_order=te.original_order,
                instrument_identity=te.instrument_identity,
                lifecycle_state=te.lifecycle_state,
                submission_market_timestamp=datetime.min.replace(tzinfo=te.market_timestamp.tzinfo),
                eligibility_timestamp=datetime.min.replace(tzinfo=te.market_timestamp.tzinfo),
                reference_price=Decimal("0"),
                stop_triggered=False,
                stop_limit_activated=False,
            )
        return None

    def pending_orders(self) -> list[BrokerOrderRecord]:
        """Return read-only views of all currently queued orders."""
        return [self._to_record(po) for po in self._pending.values()]

    def terminal_results(self) -> list[BrokerTerminalEvent]:
        """Return all terminal events in order of occurrence."""
        return list(self._terminal.values())

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_submission_quote(
        quote: QuoteSnapshot,
        side: Literal["BUY", "SELL"],
        submission_ts: datetime,
        stale_threshold: timedelta,
    ) -> BrokerSubmissionResult | None:
        """Validate submission quote. Returns rejection result or None if valid."""
        if side == "BUY":
            if quote.ask_price is None:
                return BrokerSubmissionResult(
                    accepted=False,
                    reason="no_executable_ask_at_submission",
                )
        else:
            if quote.bid_price is None:
                return BrokerSubmissionResult(
                    accepted=False,
                    reason="no_executable_bid_at_submission",
                )

        # Crossed quote check
        if (
            quote.bid_price is not None
            and quote.ask_price is not None
            and quote.bid_price > quote.ask_price
        ):
            return BrokerSubmissionResult(
                accepted=False,
                reason="crossed_quote_at_submission",
            )

        # Future-dated quote check
        age = submission_ts - quote.exchange_timestamp
        if age < timedelta(0):
            return BrokerSubmissionResult(
                accepted=False,
                reason="future_quote_at_submission",
            )

        # Staleness check
        if age > stale_threshold:
            return BrokerSubmissionResult(
                accepted=False,
                reason="stale_quote_at_submission",
            )

        return None

    def _check_stop_trigger(self, po: _PendingOrder, quote: QuoteSnapshot) -> None:
        """Check and record STOP / STOP_LIMIT trigger state."""
        if po.stop_triggered and po.stop_limit_activated:
            return  # already fully triggered/activated

        last_price = quote.last_price
        if last_price is None:
            return  # no trigger evidence

        stop_price = po.original_order.stop_price
        if stop_price is None:
            return  # should not happen for STOP/STOP_LIMIT, but defensive

        side = po.original_order.action  # BUY or SELL

        triggered = False
        if side == "BUY":
            if last_price >= stop_price:
                triggered = True
        else:  # SELL
            if last_price <= stop_price:
                triggered = True

        if triggered:
            po.stop_triggered = True
            if po.original_order.order_type is OrderType.STOP_LIMIT:
                po.stop_limit_activated = True
                po.stop_limit_activation_timestamp = quote.exchange_timestamp
                po.stop_limit_activation_price = last_price

    def _evaluate_order(
        self, po: _PendingOrder, quote: QuoteSnapshot
    ) -> ExecutionResult | None:
        """Delegate fill evaluation to PaperFillAdapter.

        Returns None if the order should not be evaluated (untriggered STOP/STOP_LIMIT).
        Returns ExecutionResult for all other cases (including UNFILLED).
        """
        order_type = po.original_order.order_type

        # Untriggered STOP → do not evaluate at all
        if order_type is OrderType.STOP and not po.stop_triggered:
            return None

        # Unactivated STOP_LIMIT → do not evaluate at all
        if order_type is OrderType.STOP_LIMIT and not po.stop_limit_activated:
            return None

        # Triggered STOP → evaluate as MARKET
        if order_type is OrderType.STOP and po.stop_triggered:
            return self._adapter.evaluate_market(
                po.original_order, quote, po.execution_context,
            )

        # Activated STOP_LIMIT → evaluate as LIMIT
        if order_type is OrderType.STOP_LIMIT and po.stop_limit_activated:
            return self._adapter.evaluate_limit(
                po.original_order, quote, po.execution_context,
            )

        # Normal MARKET/LIMIT
        if order_type is OrderType.MARKET:
            return self._adapter.evaluate_market(
                po.original_order, quote, po.execution_context,
            )
        if order_type is OrderType.LIMIT:
            return self._adapter.evaluate_limit(
                po.original_order, quote, po.execution_context,
            )

        return None  # unreachable for well-typed orders

    @staticmethod
    def _to_record(po: _PendingOrder) -> BrokerOrderRecord:
        return BrokerOrderRecord(
            order_id=po.order_id,
            broker_order_identity=po.broker_order_identity,
            original_order=po.original_order,
            instrument_identity=po.instrument_identity,
            lifecycle_state=po.lifecycle_state,
            submission_market_timestamp=po.submission_market_timestamp,
            eligibility_timestamp=po.eligibility_timestamp,
            reference_price=po.reference_price,
            stop_triggered=po.stop_triggered,
            stop_limit_activated=po.stop_limit_activated,
            stop_limit_activation_timestamp=po.stop_limit_activation_timestamp,
            stop_limit_activation_price=po.stop_limit_activation_price,
        )
