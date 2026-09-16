"""Phase 7 Slice 2 — deterministic OFFLINE mock broker adapter (ADR §127).

SCOPE AND AUTHORITY
-------------------
This module implements :class:`engine.broker_adapters.contracts.BrokerAdapter`
for the Phase-7 frozen scope only: a broker-independent adapter boundary plus
a deterministic offline mock/sandbox contract (§127.0, §127.9).  It is a
software-contract simulator.  It contains no vendor SDK, no transport client,
no credential handling, and no live-account concept; it must never be wired
to any real brokerage (§127.9 / OD-7).

DETERMINISM CONTRACT (§127.12 / OD-9)
-------------------------------------
Every observable behaviour is driven by explicitly supplied canonical
arguments or explicit script calls made by the owning test/session:

* No uncontrolled randomness, no system wall clock, no latency simulation by
  waiting, no scheduling dependence, and no timing-by-delay of any kind.
* Timeouts, rate limits, disconnects, reconnects, duplicates, out-of-order
  observations, partial fragments, cancels and expiries are all produced by
  deterministic scripted scenarios.
* The same scripted scenario applied to the same canonical inputs produces
  identical semantic output.

PARTIAL FRAGMENTS STAY ADAPTER-CONTAINED (§127.1 / OD-1 Option A)
-----------------------------------------------------------------
Fragments accumulate inside this adapter only.  They never become core
lifecycle states, never mutate accounting, and never fabricate a fill.  The
adapter merely maintains adapter-contained exposure evidence; core projection
is exclusively the job of the Slice-3 normalization layer.

OBSERVATION MODEL (§127.3 / OD-2)
---------------------------------
Scripted events are queued in exact order and delivered to registered
observers only when the owner calls :meth:`MockBrokerAdapter.drain_observations`
— delivery order is therefore fully scripted.  Ingest rules are deterministic:

* duplicate fill fragments (same ``(broker_order_identity, broker_fill_id)``
  dedup key, §127.6) are dropped at the adapter boundary and counted;
* observations whose ``observation_sequence`` is not strictly greater than the
  order's last processed sequence are stale/out-of-order and are dropped and
  counted;
* fragments that would push cumulative quantity past the ordered quantity fail
  closed — overfill is not representable evidence.

FAIL-CLOSED TRANSPORT (§127.10)
-------------------------------
While disconnected, submit/cancel/queries raise
:class:`BrokerAdapterUnavailableError` instead of returning empty/absent
results: an unavailable transport is never an implicit "nothing happened".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Iterable

from engine.broker_adapters.contracts import (
    BrokerAdapterError,
    BrokerAdapterOrderSnapshot,
    BrokerAdapterOrderStatus,
    BrokerAdapterUnavailableError,
    BrokerCancelResult,
    BrokerCapability,
    BrokerConnectionState,
    BrokerFillFragment,
    BrokerFundsSnapshot,
    BrokerModifyResult,
    BrokerObservationCallback,
    BrokerPositionSnapshot,
    BrokerStatusObservation,
    BrokerSubmissionResult,
    UnsupportedCapabilityError,
    broker_execution_side,
    broker_order_identity,
)
from engine.execution.model import ExecutableOrder
from engine.core.numeric import as_decimal
from engine.orders.model import TimeInForce
from engine.portfolio.model import InstrumentIdentity, InstrumentSpecification

logger = logging.getLogger(__name__)

__all__ = [
    "MOCK_BROKER_ADAPTER_VERSION",
    "MockBrokerAdapter",
    "MockOrderView",
]


MOCK_BROKER_ADAPTER_VERSION = "sentinelx-mock-broker-adapter/v1"

_RATE_LIMITED_REASON = "rate_limited"


@dataclass
class _MockOrder:
    """Internal mutable per-order state owned by the mock adapter."""

    order_id: str
    broker_order_identity: str
    original_order: ExecutableOrder
    instrument_identity: InstrumentIdentity
    specification: InstrumentSpecification
    ordered_quantity: Decimal
    submission_market_timestamp: datetime
    status: BrokerAdapterOrderStatus = BrokerAdapterOrderStatus.ACCEPTED
    terminal_reason: str | None = None
    last_observation_sequence: int = -1
    fragments: dict[tuple[str, str], BrokerFillFragment] = field(default_factory=dict)

    @property
    def cumulative_filled_quantity(self) -> Decimal:
        return sum(
            (fragment.fill_quantity for fragment in self.fragments.values()),
            Decimal("0"),
        )

    @property
    def is_terminal(self) -> bool:
        return self.status.is_terminal


@dataclass(frozen=True)
class MockOrderView:
    """Immutable read-only view of one mock order's adapter-side state."""

    order_id: str
    broker_order_identity: str
    adapter_status: BrokerAdapterOrderStatus
    ordered_quantity: Decimal
    cumulative_filled_quantity: Decimal
    fragment_count: int
    terminal_reason: str | None


class MockBrokerAdapter:
    """Deterministic offline mock implementation of the hybrid broker boundary.

    The adapter accepts already risk-approved canonical orders, keeps them in
    an internal ledger keyed by the existing canonical broker identity, and
    exposes exactly the frozen hybrid surface: callback/event path for
    adapter-originated observations plus synchronous query path for
    reconciliation/state inspection.
    """

    def __init__(self, *, adapter_id: str = "mock-broker") -> None:
        if not isinstance(adapter_id, str) or not adapter_id.strip():
            raise ValueError("adapter_id must be a non-empty string")
        self.adapter_id = adapter_id
        self._connection = BrokerConnectionState.CONNECTED
        self._unavailable_reason: str | None = None
        self._orders: dict[str, _MockOrder] = {}
        self._queued_observations: list[object] = []
        self._observers: list[BrokerObservationCallback] = []
        self._delivered: list[object] = []
        self._scripted_rejections: list[str] = []
        self._rate_limit_max: int | None = None
        self._rate_limit_window: timedelta | None = None
        self._rate_limit_attempts: list[datetime] = []
        self.duplicate_fragments_dropped = 0
        self.stale_or_out_of_order_dropped = 0
        self.rate_limited_rejections = 0

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def connection_state(self) -> BrokerConnectionState:
        return self._connection

    @property
    def unavailable_reason(self) -> str | None:
        return self._unavailable_reason

    @property
    def delivered_observations(self) -> tuple[object, ...]:
        """Every observation actually dispatched to observers, in order."""
        return tuple(self._delivered)

    def order_view(self, order_id: str) -> MockOrderView | None:
        order = self._orders.get(order_id)
        if order is None:
            return None
        return MockOrderView(
            order_id=order.order_id,
            broker_order_identity=order.broker_order_identity,
            adapter_status=order.status,
            ordered_quantity=order.ordered_quantity,
            cumulative_filled_quantity=order.cumulative_filled_quantity,
            fragment_count=len(order.fragments),
            terminal_reason=order.terminal_reason,
        )

    def order_views(self) -> tuple[MockOrderView, ...]:
        return tuple(
            view
            for _, view in sorted(
                (
                    (order.submission_market_timestamp, self.order_view(order.order_id))
                    for order in self._orders.values()
                ),
                key=lambda item: (item[0], item[1].order_id),
            )
        )

    # ------------------------------------------------------------------
    # Deterministic scripting surface (test/session-owned scenarios)
    # ------------------------------------------------------------------

    def disconnect(self, reason: str = "scripted_disconnect") -> None:
        """Make the transport unavailable; every remote interaction fails closed."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason must be a non-empty string")
        self._connection = BrokerConnectionState.DISCONNECTED
        self._unavailable_reason = reason

    def reconnect(self) -> None:
        """Restore transport availability (scripted successful reconnect)."""
        self._connection = BrokerConnectionState.CONNECTED
        self._unavailable_reason = None

    def reject_next_submissions(self, reason: str, count: int = 1) -> None:
        """Script the next ``count`` eligible submissions as rejected."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason must be a non-empty string")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError("count must be a positive int")
        self._scripted_rejections.extend([reason] * count)

    def configure_rate_limit(self, *, max_submissions: int, window: timedelta) -> None:
        """Enable a deterministic sliding-window placement rate limit.

        The window is evaluated purely from caller-supplied market timestamps;
        no wall clock is consulted.  Attempts that pass connectivity and
        duplicate checks consume budget; exceeding the limit yields a
        deterministic ``rate_limited`` rejection.
        """
        if isinstance(max_submissions, bool) or not isinstance(max_submissions, int):
            raise TypeError("max_submissions must be an int")
        if max_submissions < 1:
            raise ValueError("max_submissions must be >= 1")
        if not isinstance(window, timedelta):
            raise TypeError("window must be a timedelta")
        if window <= timedelta(0):
            raise ValueError("window must be positive")
        self._rate_limit_max = max_submissions
        self._rate_limit_window = window

    def queue_fill(
        self,
        order_id: str,
        *,
        fill_id: str,
        quantity: Decimal | int | float | str,
        price: Decimal | int | float | str,
        observed_at: datetime,
        sequence: int,
    ) -> None:
        """Queue one adapter-originated fill-fragment observation."""
        order = self._require_known_order(order_id)
        self._queued_observations.append(
            BrokerFillFragment(
                order_id=order.order_id,
                broker_order_identity=order.broker_order_identity,
                broker_fill_id=fill_id,
                fill_quantity=quantity,
                fill_price=price,
                observed_at=observed_at,
                observation_sequence=sequence,
            )
        )

    def queue_status(
        self,
        order_id: str,
        *,
        status: BrokerAdapterOrderStatus,
        observed_at: datetime,
        sequence: int,
        raw_status_token: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Queue one adapter-originated status observation."""
        order = self._require_known_order(order_id)
        self._queued_observations.append(
            BrokerStatusObservation(
                order_id=order.order_id,
                broker_order_identity=order.broker_order_identity,
                adapter_status=status,
                observed_at=observed_at,
                observation_sequence=sequence,
                raw_status_token=raw_status_token,
                reason=reason,
            )
        )

    def drain_observations(self) -> tuple[object, ...]:
        """Deliver queued observations in scripted order; return what was delivered.

        Ingest is deterministic: duplicates are dropped by the §127.6 dedup
        key, stale/out-of-order sequences are dropped, overfills fail closed,
        and each accepted observation mutates adapter-contained state before
        being dispatched to observers.
        """
        delivered: list[object] = []
        while self._queued_observations:
            observation = self._queued_observations.pop(0)
            if not self._ingest(observation):
                continue
            delivered.append(observation)
            self._delivered.append(observation)
            for observer in list(self._observers):
                observer(observation)
        return tuple(delivered)

    def expire_day_session(self, session_end_market_timestamp: datetime) -> tuple[str, ...]:
        """Expire every open DAY-TIF order (deterministic day-session rollover)."""
        self._require_connected("expire_day_session")
        if not isinstance(session_end_market_timestamp, datetime):
            raise TypeError("session_end_market_timestamp must be a datetime")
        if (
            session_end_market_timestamp.tzinfo is None
            or session_end_market_timestamp.utcoffset() is None
        ):
            raise ValueError("session_end_market_timestamp must be timezone-aware")
        expired: list[str] = []
        for order in sorted(
            self._orders.values(),
            key=lambda item: (item.submission_market_timestamp, item.order_id),
        ):
            if order.is_terminal:
                continue
            if order.original_order.time_in_force is not TimeInForce.DAY:
                continue
            order.status = BrokerAdapterOrderStatus.EXPIRED
            order.terminal_reason = "day_tif_expired"
            expired.append(order.order_id)
        return tuple(expired)

    # ------------------------------------------------------------------
    # BrokerAdapter protocol — synchronous paths
    # ------------------------------------------------------------------

    def submit(
        self,
        order: ExecutableOrder,
        *,
        instrument_identity: InstrumentIdentity,
        specification: InstrumentSpecification,
        submission_market_timestamp: datetime,
    ) -> BrokerSubmissionResult:
        """Accept/reject one already risk-approved canonical order."""
        self._require_connected("submit")
        try:
            broker_execution_side(order)
        except ValueError:
            return BrokerSubmissionResult(
                accepted=False,
                reason="unresolved_exit_action",
            )
        if not isinstance(submission_market_timestamp, datetime):
            raise TypeError("submission_market_timestamp must be a datetime")
        if (
            submission_market_timestamp.tzinfo is None
            or submission_market_timestamp.utcoffset() is None
        ):
            raise ValueError("submission_market_timestamp must be timezone-aware")

        canonical_identity = broker_order_identity(order, instrument_identity)
        order_id = canonical_identity

        pending_by_identity = {
            state.broker_order_identity: state for state in self._orders.values()
        }
        existing = pending_by_identity.get(canonical_identity)
        if existing is not None:
            return BrokerSubmissionResult(
                accepted=False,
                reason=(
                    "duplicate_of_terminal_order"
                    if existing.is_terminal
                    else "duplicate_order"
                ),
                duplicate=True,
                order_id=existing.order_id,
                broker_order_identity=canonical_identity,
            )

        limited_reason = self._evaluate_rate_limit(submission_market_timestamp)
        if limited_reason is not None:
            self.rate_limited_rejections += 1
            return BrokerSubmissionResult(
                accepted=False,
                reason=limited_reason,
            )

        if self._scripted_rejections:
            scripted_reason = self._scripted_rejections.pop(0)
            return BrokerSubmissionResult(
                accepted=False,
                reason=scripted_reason,
            )

        ordered_quantity = as_decimal(order.quantity, "order.quantity")
        if ordered_quantity <= 0:
            raise ValueError("order quantity must be positive")

        self._orders[order_id] = _MockOrder(
            order_id=order_id,
            broker_order_identity=canonical_identity,
            original_order=order,
            instrument_identity=instrument_identity,
            specification=specification,
            ordered_quantity=ordered_quantity,
            submission_market_timestamp=submission_market_timestamp,
        )
        return BrokerSubmissionResult(
            accepted=True,
            order_id=order_id,
            broker_order_identity=canonical_identity,
        )

    def cancel(
        self,
        order_id: str,
        cancel_market_timestamp: datetime,
    ) -> BrokerCancelResult:
        """Request cancellation of a previously accepted order."""
        self._require_connected("cancel")
        order = self._orders.get(order_id)
        if order is None:
            return BrokerCancelResult(
                cancelled=False,
                order_id=order_id,
                reason="order_not_found",
            )
        if order.is_terminal:
            return BrokerCancelResult(
                cancelled=False,
                order_id=order_id,
                reason="already_terminal",
            )
        order.status = BrokerAdapterOrderStatus.CANCELLED
        order.terminal_reason = "explicit_cancel"
        return BrokerCancelResult(cancelled=True, order_id=order_id)

    def query_order(self, order_id: str) -> BrokerAdapterOrderSnapshot | None:
        """Synchronous query path: adapter view of one order (fail-closed)."""
        self._require_connected("query_order")
        order = self._orders.get(order_id)
        if order is None:
            return None
        return self._snapshot(order)

    def query_open_orders(self) -> tuple[BrokerAdapterOrderSnapshot, ...]:
        """Synchronous query path: adapter views of all non-terminal orders."""
        self._require_connected("query_open_orders")
        open_orders = sorted(
            (state for state in self._orders.values() if not state.is_terminal),
            key=lambda state: (state.submission_market_timestamp, state.order_id),
        )
        return tuple(self._snapshot(state) for state in open_orders)

    def register_observer(self, observer: BrokerObservationCallback) -> None:
        """Register a callback for adapter-originated observations."""
        if not callable(observer):
            raise TypeError("observer must be callable")
        self._observers.append(observer)

    def supported_capabilities(self) -> frozenset[BrokerCapability]:
        """Declared mock adapter capabilities."""
        return frozenset(
            {
                BrokerCapability.PLACE_ORDER,
                BrokerCapability.CANCEL_ORDER,
                BrokerCapability.ORDER_STATUS,
                BrokerCapability.TRADES_FILLS,
                BrokerCapability.RECONNECT,
                BrokerCapability.RECONCILIATION,
            }
        )

    def supports(self, capability: BrokerCapability) -> bool:
        """Truthful capability query."""
        return capability in self.supported_capabilities()

    def connect(self) -> None:
        """Connect mock transport."""
        self._connection = BrokerConnectionState.CONNECTED
        self._unavailable_reason = None

    def modify(
        self,
        order_id: str,
        *,
        new_price: Decimal | None = None,
        new_quantity: Decimal | None = None,
        new_trigger_price: Decimal | None = None,
        timestamp: datetime,
    ) -> BrokerModifyResult:
        """Mock modify fails truthfully as unsupported."""
        raise UnsupportedCapabilityError(BrokerCapability.MODIFY_ORDER, self.adapter_id)

    def query_positions(self) -> tuple[BrokerPositionSnapshot, ...]:
        """Synchronous query path for positions."""
        self._require_connected("query_positions")
        return ()

    def query_funds(self) -> BrokerFundsSnapshot | None:
        """Synchronous query path for funds."""
        self._require_connected("query_funds")
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_connected(self, operation: str) -> None:
        if not self._connection.is_usable:
            raise BrokerAdapterUnavailableError(
                f"{operation} unavailable: transport disconnected "
                f"(reason={self._unavailable_reason!r})"
            )

    def _require_known_order(self, order_id: str) -> _MockOrder:
        if not isinstance(order_id, str) or not order_id.strip():
            raise ValueError("order_id must be a non-empty string")
        order = self._orders.get(order_id)
        if order is None:
            raise KeyError(f"unknown mock order: {order_id!r}")
        return order

    def _evaluate_rate_limit(self, submission_market_timestamp: datetime) -> str | None:
        if self._rate_limit_max is None or self._rate_limit_window is None:
            return None
        window = self._rate_limit_window
        recent = [
            attempt
            for attempt in self._rate_limit_attempts
            if submission_market_timestamp - attempt < window
        ]
        if len(recent) >= self._rate_limit_max:
            return _RATE_LIMITED_REASON
        self._rate_limit_attempts = [*recent, submission_market_timestamp]
        return None

    def _ingest(self, observation: object) -> bool:
        """Apply deterministic ingest rules. Returns False when dropped."""
        if isinstance(observation, BrokerFillFragment):
            order = self._orders.get(observation.order_id)
            if order is None or order.broker_order_identity != observation.broker_order_identity:
                raise BrokerAdapterError(
                    "fragment references an unknown or mismatched mock order"
                )
            if observation.observation_sequence <= order.last_observation_sequence:
                self.stale_or_out_of_order_dropped += 1
                logger.warning(
                    "mock broker dropped stale/out-of-order fragment for %s",
                    observation.order_id,
                )
                return False
            if observation.dedup_key in order.fragments:
                self.duplicate_fragments_dropped += 1
                logger.warning(
                    "mock broker dropped duplicate fragment %s for %s",
                    observation.broker_fill_id,
                    observation.order_id,
                )
                return False
            projected = order.cumulative_filled_quantity + observation.fill_quantity
            if projected > order.ordered_quantity:
                raise ValueError(
                    "scripted fragment would overfill the order; "
                    "overfill is not representable adapter evidence"
                )
            order.last_observation_sequence = observation.observation_sequence
            order.fragments[observation.dedup_key] = observation
            if (
                not order.is_terminal
                and order.cumulative_filled_quantity == order.ordered_quantity
            ):
                order.status = BrokerAdapterOrderStatus.FILLED
            elif not order.is_terminal:
                order.status = BrokerAdapterOrderStatus.PARTIALLY_FILLED
            return True

        if isinstance(observation, BrokerStatusObservation):
            order = self._orders.get(observation.order_id)
            if order is None or order.broker_order_identity != observation.broker_order_identity:
                raise BrokerAdapterError(
                    "status observation references an unknown or mismatched mock order"
                )
            if observation.observation_sequence <= order.last_observation_sequence:
                self.stale_or_out_of_order_dropped += 1
                logger.warning(
                    "mock broker dropped stale/out-of-order status for %s",
                    observation.order_id,
                )
                return False
            order.last_observation_sequence = observation.observation_sequence
            if order.is_terminal and observation.adapter_status is not order.status:
                # Terminal states are monotonic: later non-matching statuses
                # cannot reopen or retarget a terminal order.
                logger.warning(
                    "mock broker ignored post-terminal status %s for %s",
                    observation.adapter_status.value,
                    observation.order_id,
                )
                return False
            order.status = observation.adapter_status
            if observation.adapter_status.is_terminal:
                order.terminal_reason = observation.reason or observation.raw_status_token
            elif observation.adapter_status is BrokerAdapterOrderStatus.UNKNOWN:
                # UNKNOWN is retained as diagnostic-only state; it must never
                # terminate an order and always fails closed downstream.
                logger.error(
                    "mock broker received UNKNOWN status for %s (raw=%r)",
                    observation.order_id,
                    observation.raw_status_token,
                )
            return True

        raise TypeError(f"unsupported queued observation type: {type(observation)!r}")

    def _snapshot(self, order: _MockOrder) -> BrokerAdapterOrderSnapshot:
        cumulative = order.cumulative_filled_quantity
        return BrokerAdapterOrderSnapshot(
            order_id=order.order_id,
            broker_order_identity=order.broker_order_identity,
            adapter_status=order.status,
            ordered_quantity=order.ordered_quantity,
            cumulative_filled_quantity=cumulative,
            fragment_count=len(order.fragments),
            last_observation_sequence=max(order.last_observation_sequence, 0),
            raw_status_token=None,
            reason=order.terminal_reason,
        )


def summarize_fragments(
    fragments: Iterable[BrokerFillFragment],
) -> tuple[Decimal, Decimal, int]:
    """Deterministic adapter-contained aggregation helper.

    Returns ``(cumulative_quantity, weighted_average_price, fragment_count)``
    computed with exact Decimal arithmetic under a fixed context.  This helper
    performs no core projection and carries no accounting authority.
    """
    collected = tuple(fragments)
    total_quantity = sum((f.fill_quantity for f in collected), Decimal("0"))
    if not collected:
        return Decimal("0"), Decimal("0"), 0
    notional = sum(
        (fragment.fill_quantity * fragment.fill_price for fragment in collected),
        Decimal("0"),
    )
    weighted_price = notional / total_quantity
    return total_quantity, weighted_price, len(collected)
