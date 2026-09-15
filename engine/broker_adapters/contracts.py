"""Phase 7 Slice 1 — broker-independent adapter contracts (ADR §127.3 / OD-2).

OFFLINE SCOPE
-------------
Phase 7 delivers a broker-independent adapter boundary plus a deterministic
offline mock ONLY (ADR §127.0, §127.9). This module defines provider-neutral
shapes. It has no vendor SDK import, no network client, no transport library,
no credential handling, and no live-account concept. Nothing here may be wired
to a real brokerage.

WHAT IS REUSED, NOT REDEFINED
-----------------------------
The canonical broker-boundary result types already exist in
``engine.execution.paper_broker`` and already carry SentinelX canonical types
only, so they are re-exported here instead of duplicated:

* :class:`BrokerSubmissionResult`
* :class:`BrokerTerminalEvent`
* :class:`BrokerCancelResult`
* :class:`BrokerOrderRecord`
* :func:`broker_order_identity` — the EXISTING canonical broker-layer (D11
  Layer 3) deterministic order identity, unchanged (§127.5 / OD-4). Phase 7
  introduces no new order-identity scheme and no UUID substitution.
* :func:`broker_execution_side` — the existing BUY/SELL resolution, unchanged.

WHAT IS ADDED (proven gaps only)
--------------------------------
* :class:`BrokerConnectionState` — transport availability, required by the
  disconnect/reconnect reconciliation precedence of §127.10.
* :class:`BrokerAdapterOrderStatus` — a provider-neutral ADAPTER-BOUNDARY
  status vocabulary. It is deliberately NOT ``OrderLifecycleState``; it is
  never persisted and never projected as a core lifecycle state without
  explicit normalization. ``UNKNOWN`` always fails closed.
* :class:`BrokerFillFragment` — an adapter-contained fill fragment. A fragment
  is NOT an ``ExecutionResult`` and never reaches core accounting or the core
  order lifecycle (§127.1 / OD-1 Option A).
* :class:`BrokerStatusObservation` — an adapter-contained status observation.
* :class:`BrokerAdapterOrderSnapshot` — the synchronous query/reconciliation
  view required by the hybrid boundary (§127.3 / OD-2).
* :class:`BrokerAdapter` — the hybrid submit / cancel / query / observe
  protocol.

NO CORE PARTIAL-FILL STATE
--------------------------
Per §127.1 (OD-1), partial fills stay adapter-contained. No
``PARTIALLY_FILLED`` member is added to ``OrderLifecycleState``.
``BrokerAdapterOrderStatus.PARTIALLY_FILLED`` belongs to a *different*
vocabulary and has no core projection: an unresolved partial exposure fails
closed rather than being accounted.

PERSISTENCE
-----------
Nothing in this module is persisted. The fingerprint schema tokens below are
canonical-evidence schemas (D4 codec), not storage schemas: SCHEMA_VERSION
remains 7 and no table, column, or migration is introduced (§127.13).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Callable, Protocol, runtime_checkable

from engine.execution.model import ExecutableOrder
from engine.execution.paper_broker import (
    BrokerCancelResult,
    BrokerOrderRecord,
    BrokerSubmissionResult,
    BrokerTerminalEvent,
    _broker_order_identity,
    _execution_side,
)
from engine.core.numeric import as_decimal
from engine.portfolio.model import InstrumentIdentity, InstrumentSpecification
from engine.reproducibility.codec import CanonicalCodec

__all__ = [
    "BROKER_ADAPTER_CONTRACT_VERSION",
    "FILL_FRAGMENT_SCHEMA",
    "ORDER_SNAPSHOT_SCHEMA",
    "STATUS_OBSERVATION_SCHEMA",
    "BrokerAdapter",
    "BrokerAdapterError",
    "BrokerAdapterObservation",
    "BrokerAdapterOrderSnapshot",
    "BrokerAdapterOrderStatus",
    "BrokerAdapterUnavailableError",
    "BrokerCancelResult",
    "BrokerConnectionState",
    "BrokerFillFragment",
    "BrokerObservationCallback",
    "BrokerOrderRecord",
    "BrokerStatusObservation",
    "BrokerSubmissionResult",
    "BrokerTerminalEvent",
    "broker_execution_side",
    "broker_order_identity",
]


# ======================================================================
# Contract identity / canonical evidence schemas
# ======================================================================

BROKER_ADAPTER_CONTRACT_VERSION = "sentinelx-broker-adapter-contract/v1"

FILL_FRAGMENT_SCHEMA = "sentinelx-broker-fill-fragment/v1"
STATUS_OBSERVATION_SCHEMA = "sentinelx-broker-status-observation/v1"
ORDER_SNAPSHOT_SCHEMA = "sentinelx-broker-order-snapshot/v1"


# ======================================================================
# Adapter-boundary exceptions
# ======================================================================


class BrokerAdapterError(Exception):
    """Base class for adapter-boundary failures raised by a broker adapter."""


class BrokerAdapterUnavailableError(BrokerAdapterError):
    """Raised when the adapter transport cannot answer an order query.

    Fail-closed contract (§127.10): an unavailable query is NEVER an implicit
    "nothing happened" answer. Callers must treat it as UNRESOLVED and must
    not resubmit or retry while it stays unresolved.
    """


# ======================================================================
# Connection state
# ======================================================================


class BrokerConnectionState(str, Enum):
    """Adapter transport availability (§127.10)."""

    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"

    @property
    def is_usable(self) -> bool:
        """True only when the adapter may be queried or submitted to."""
        return self is BrokerConnectionState.CONNECTED


# ======================================================================
# Adapter-boundary order status vocabulary
# ======================================================================


class BrokerAdapterOrderStatus(str, Enum):
    """Provider-neutral ADAPTER-BOUNDARY order status.

    This vocabulary exists because real broker status sets do not align 1:1
    with ``OrderLifecycleState`` and frequently contain intermediate or
    vendor-specific tokens. It is therefore kept strictly at the adapter
    boundary:

    * It is never persisted.
    * It is never used as a core lifecycle state.
    * ``PARTIALLY_FILLED`` here does NOT imply core partial-fill support
      (§127.1 / OD-1); it is adapter-contained exposure information only.
    * ``UNKNOWN`` is the mandatory sink for any status the adapter cannot map
      and always fails closed at normalization.
    """

    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"

    @property
    def is_terminal(self) -> bool:
        """True for broker-terminal statuses.

        ``UNKNOWN`` is deliberately NOT terminal: an unmapped status is never
        allowed to close an order.
        """
        return self in _TERMINAL_ADAPTER_STATUSES


_TERMINAL_ADAPTER_STATUSES = frozenset(
    {
        BrokerAdapterOrderStatus.FILLED,
        BrokerAdapterOrderStatus.CANCELLED,
        BrokerAdapterOrderStatus.EXPIRED,
        BrokerAdapterOrderStatus.REJECTED,
    }
)


# ======================================================================
# Validation helpers
# ======================================================================


def _require_identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _require_optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be None or a non-empty string")
    return value


def _require_aware(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _require_ordinal(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return value


def _require_status(value: object, field_name: str) -> BrokerAdapterOrderStatus:
    if not isinstance(value, BrokerAdapterOrderStatus):
        raise TypeError(f"{field_name} must be a BrokerAdapterOrderStatus")
    return value


# ======================================================================
# Adapter-contained fill fragment
# ======================================================================


@dataclass(frozen=True)
class BrokerFillFragment:
    """One adapter-contained broker fill fragment (§127.1 / OD-1 Option A).

    A fragment is provider-neutral evidence held BEHIND the adapter boundary.
    It is not an ``ExecutionResult``, carries no accounting authority, and must
    never be projected into core position/P&L state on its own. Only a
    supported terminal FULL fill may project into the existing core full-fill
    path.

    ``dedup_key`` is the adapter-ONLY fill dedup tuple mandated by §127.6 /
    OD-5: ``(broker_order_identity, broker_fill_id)``. The SentinelX internal
    ``order_id`` and ``broker_order_identity`` remain authoritative for order
    identity; ``broker_fill_id`` is never promoted to an order identity.
    """

    order_id: str
    broker_order_identity: str
    broker_fill_id: str
    fill_quantity: Decimal
    fill_price: Decimal
    observed_at: datetime
    observation_sequence: int

    def __post_init__(self) -> None:
        _require_identifier(self.order_id, "order_id")
        _require_identifier(self.broker_order_identity, "broker_order_identity")
        _require_identifier(self.broker_fill_id, "broker_fill_id")
        object.__setattr__(
            self, "fill_quantity", as_decimal(self.fill_quantity, "fill_quantity")
        )
        object.__setattr__(
            self, "fill_price", as_decimal(self.fill_price, "fill_price")
        )
        if self.fill_quantity <= 0:
            raise ValueError("fill_quantity must be > 0")
        if self.fill_price <= 0:
            raise ValueError("fill_price must be > 0")
        _require_aware(self.observed_at, "observed_at")
        _require_ordinal(self.observation_sequence, "observation_sequence")

    @property
    def dedup_key(self) -> tuple[str, str]:
        """Adapter-only fill dedup key (§127.6 / OD-5)."""
        return (self.broker_order_identity, self.broker_fill_id)

    @property
    def fragment_identity(self) -> str:
        """Deterministic canonical fingerprint of this fragment."""
        return CanonicalCodec.fingerprint(
            FILL_FRAGMENT_SCHEMA,
            (
                ("order_id", self.order_id),
                ("broker_order_identity", self.broker_order_identity),
                ("broker_fill_id", self.broker_fill_id),
                ("fill_quantity", self.fill_quantity),
                ("fill_price", self.fill_price),
                ("observed_at", self.observed_at),
                ("observation_sequence", self.observation_sequence),
            ),
        )


# ======================================================================
# Adapter-contained status observation
# ======================================================================


@dataclass(frozen=True)
class BrokerStatusObservation:
    """One adapter-contained broker status observation (callback path).

    ``raw_status_token`` retains the provider's own status text purely as
    diagnostic evidence for fail-closed reporting of unmapped statuses. It is
    never interpreted as a lifecycle state.
    """

    order_id: str
    broker_order_identity: str
    adapter_status: BrokerAdapterOrderStatus
    observed_at: datetime
    observation_sequence: int
    raw_status_token: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.order_id, "order_id")
        _require_identifier(self.broker_order_identity, "broker_order_identity")
        _require_status(self.adapter_status, "adapter_status")
        _require_aware(self.observed_at, "observed_at")
        _require_ordinal(self.observation_sequence, "observation_sequence")
        _require_optional_text(self.raw_status_token, "raw_status_token")
        _require_optional_text(self.reason, "reason")

    @property
    def observation_identity(self) -> str:
        """Deterministic canonical fingerprint of this observation."""
        return CanonicalCodec.fingerprint(
            STATUS_OBSERVATION_SCHEMA,
            (
                ("order_id", self.order_id),
                ("broker_order_identity", self.broker_order_identity),
                ("adapter_status", self.adapter_status.value),
                ("observed_at", self.observed_at),
                ("observation_sequence", self.observation_sequence),
                ("raw_status_token", self.raw_status_token),
                ("reason", self.reason),
            ),
        )


BrokerAdapterObservation = BrokerFillFragment | BrokerStatusObservation
BrokerObservationCallback = Callable[[BrokerAdapterObservation], None]


# ======================================================================
# Adapter query snapshot
# ======================================================================


@dataclass(frozen=True)
class BrokerAdapterOrderSnapshot:
    """Synchronous adapter-side view of one order (query path, §127.3).

    This is the reconciliation-facing half of the hybrid boundary. It reports
    adapter-contained exposure (``cumulative_filled_quantity``) WITHOUT
    implying any core partial-fill support.
    """

    order_id: str
    broker_order_identity: str
    adapter_status: BrokerAdapterOrderStatus
    ordered_quantity: Decimal
    cumulative_filled_quantity: Decimal
    fragment_count: int
    last_observation_sequence: int
    last_observed_at: datetime | None = None
    raw_status_token: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.order_id, "order_id")
        _require_identifier(self.broker_order_identity, "broker_order_identity")
        _require_status(self.adapter_status, "adapter_status")
        object.__setattr__(
            self,
            "ordered_quantity",
            as_decimal(self.ordered_quantity, "ordered_quantity"),
        )
        object.__setattr__(
            self,
            "cumulative_filled_quantity",
            as_decimal(self.cumulative_filled_quantity, "cumulative_filled_quantity"),
        )
        if self.ordered_quantity <= 0:
            raise ValueError("ordered_quantity must be > 0")
        if self.cumulative_filled_quantity < 0:
            raise ValueError("cumulative_filled_quantity must be >= 0")
        if self.cumulative_filled_quantity > self.ordered_quantity:
            raise ValueError("cumulative_filled_quantity must not exceed ordered_quantity")
        _require_ordinal(self.fragment_count, "fragment_count")
        _require_ordinal(self.last_observation_sequence, "last_observation_sequence")
        if self.last_observed_at is not None:
            _require_aware(self.last_observed_at, "last_observed_at")
        _require_optional_text(self.raw_status_token, "raw_status_token")
        _require_optional_text(self.reason, "reason")

        filled = self.cumulative_filled_quantity
        if (filled > 0) != (self.fragment_count > 0):
            raise ValueError(
                "cumulative_filled_quantity and fragment_count must agree on exposure"
            )
        if self.adapter_status is BrokerAdapterOrderStatus.FILLED:
            if filled != self.ordered_quantity:
                raise ValueError("FILLED snapshot requires full cumulative quantity")
        elif self.adapter_status is BrokerAdapterOrderStatus.ACCEPTED:
            if filled != 0:
                raise ValueError("ACCEPTED snapshot requires zero cumulative quantity")
        elif self.adapter_status is BrokerAdapterOrderStatus.PARTIALLY_FILLED:
            if not (0 < filled < self.ordered_quantity):
                raise ValueError(
                    "PARTIALLY_FILLED snapshot requires partial cumulative quantity"
                )

    @property
    def has_partial_exposure(self) -> bool:
        """True when the adapter observed a non-zero, non-complete exposure."""
        return 0 < self.cumulative_filled_quantity < self.ordered_quantity

    @property
    def is_complete_fill(self) -> bool:
        """True when adapter-contained fills sum exactly to the ordered quantity."""
        return self.cumulative_filled_quantity == self.ordered_quantity

    @property
    def snapshot_identity(self) -> str:
        """Deterministic canonical fingerprint of this snapshot."""
        return CanonicalCodec.fingerprint(
            ORDER_SNAPSHOT_SCHEMA,
            (
                ("order_id", self.order_id),
                ("broker_order_identity", self.broker_order_identity),
                ("adapter_status", self.adapter_status.value),
                ("ordered_quantity", self.ordered_quantity),
                ("cumulative_filled_quantity", self.cumulative_filled_quantity),
                ("fragment_count", self.fragment_count),
                ("last_observation_sequence", self.last_observation_sequence),
                ("last_observed_at", self.last_observed_at),
                ("raw_status_token", self.raw_status_token),
                ("reason", self.reason),
            ),
        )


# ======================================================================
# Hybrid broker adapter protocol
# ======================================================================


@runtime_checkable
class BrokerAdapter(Protocol):
    """Hybrid broker-order adapter boundary (§127.3 / OD-2).

    The boundary is deliberately hybrid: adapter-originated observations are
    delivered through :meth:`register_observer`, and an independent
    synchronous query path (:meth:`query_order`, :meth:`query_open_orders`)
    supports authoritative reconciliation after any gap or disconnect.

    Contract obligations for every implementation:

    * Return only SentinelX canonical or adapter-boundary types defined here.
      Vendor payload models must not cross this boundary.
    * Never bypass the core order lifecycle or core risk gates.
    * Order identity comes from :func:`broker_order_identity` — implementations
      do not invent identities.
    * Queries must raise :class:`BrokerAdapterUnavailableError` rather than
      report an absent or empty result when the transport cannot answer.
    """

    adapter_id: str

    @property
    def connection_state(self) -> BrokerConnectionState:
        """Current transport availability."""
        ...

    def submit(
        self,
        order: ExecutableOrder,
        *,
        instrument_identity: InstrumentIdentity,
        specification: InstrumentSpecification,
        submission_market_timestamp: datetime,
    ) -> BrokerSubmissionResult:
        """Submit one already risk-approved canonical order."""
        ...

    def cancel(
        self,
        order_id: str,
        cancel_market_timestamp: datetime,
    ) -> BrokerCancelResult:
        """Request cancellation of a previously accepted order."""
        ...

    def query_order(self, order_id: str) -> BrokerAdapterOrderSnapshot | None:
        """Return the adapter view of one order, or None when unknown."""
        ...

    def query_open_orders(self) -> tuple[BrokerAdapterOrderSnapshot, ...]:
        """Return adapter views of all non-terminal orders."""
        ...

    def register_observer(self, observer: BrokerObservationCallback) -> None:
        """Register a callback for adapter-originated observations."""
        ...


# ======================================================================
# Reused canonical identity derivations (unchanged)
# ======================================================================


def broker_order_identity(
    order: ExecutableOrder, instrument_identity: InstrumentIdentity
) -> str:
    """Existing canonical broker-layer (D11 Layer 3) deterministic identity.

    Re-exposed UNCHANGED per §127.5 / OD-4. Phase 7 adds no new identity
    scheme, no UUID substitution, and no vendor-supplied identity promotion:
    every adapter derives the same identity from the same canonical order
    evidence, so the same logical order maps to the same identity across the
    paper broker and any offline adapter.
    """
    return _broker_order_identity(order, instrument_identity)


def broker_execution_side(order: ExecutableOrder) -> str:
    """Existing canonical BUY/SELL execution-side resolution, unchanged.

    Raises ``ValueError`` for an unresolved exit action, exactly as the
    established broker boundary does.
    """
    return _execution_side(order)
