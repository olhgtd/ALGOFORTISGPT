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
``engine.execution.paper_broker`` and already carry AlgoFortis canonical types
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
    "FUNDS_SNAPSHOT_SCHEMA",
    "MODIFY_RESULT_SCHEMA",
    "ORDER_SNAPSHOT_SCHEMA",
    "POSITION_SNAPSHOT_SCHEMA",
    "STATUS_OBSERVATION_SCHEMA",
    "BaseBrokerAdapter",
    "BrokerAdapter",
    "BrokerAdapterError",
    "BrokerAdapterObservation",
    "BrokerAdapterOrderSnapshot",
    "BrokerAdapterOrderStatus",
    "BrokerAdapterUnavailableError",
    "BrokerAuthError",
    "BrokerCancelResult",
    "BrokerCapability",
    "BrokerConnectionState",
    "BrokerFillFragment",
    "BrokerFundsSnapshot",
    "BrokerModifyResult",
    "BrokerNetworkError",
    "BrokerObservationCallback",
    "BrokerOrderRecord",
    "BrokerOrderRejectedError",
    "BrokerPositionSnapshot",
    "BrokerRateLimitError",
    "BrokerStatusObservation",
    "BrokerSubmissionResult",
    "BrokerTerminalEvent",
    "UnsupportedCapabilityError",
    "broker_execution_side",
    "broker_order_identity",
]


# ======================================================================
# Contract identity / canonical evidence schemas
# ======================================================================

BROKER_ADAPTER_CONTRACT_VERSION = "algofortis-broker-adapter-contract/v1"

FILL_FRAGMENT_SCHEMA = "algofortis-broker-fill-fragment/v1"
STATUS_OBSERVATION_SCHEMA = "algofortis-broker-status-observation/v1"
ORDER_SNAPSHOT_SCHEMA = "algofortis-broker-order-snapshot/v1"
FUNDS_SNAPSHOT_SCHEMA = "algofortis-broker-funds-snapshot/v1"
POSITION_SNAPSHOT_SCHEMA = "algofortis-broker-position-snapshot/v1"
MODIFY_RESULT_SCHEMA = "algofortis-broker-modify-result/v1"


# ======================================================================
# Broker Capabilities Model
# ======================================================================


class BrokerCapability(str, Enum):
    """Truthful capability declarations for broker adapters."""

    AUTH = "AUTH"
    ACCOUNT_PROFILE = "ACCOUNT_PROFILE"
    FUNDS = "FUNDS"
    HISTORICAL_DATA = "HISTORICAL_DATA"
    LIVE_QUOTES = "LIVE_QUOTES"
    WEBSOCKET = "WEBSOCKET"
    OPTION_CHAIN = "OPTION_CHAIN"
    PLACE_ORDER = "PLACE_ORDER"
    MODIFY_ORDER = "MODIFY_ORDER"
    CANCEL_ORDER = "CANCEL_ORDER"
    ORDER_STATUS = "ORDER_STATUS"
    TRADES_FILLS = "TRADES_FILLS"
    POSITIONS = "POSITIONS"
    RECONNECT = "RECONNECT"
    RECONCILIATION = "RECONCILIATION"


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


class UnsupportedCapabilityError(BrokerAdapterError):
    """Raised when an operation is invoked that the broker adapter does not support."""

    def __init__(self, capability: BrokerCapability | str, adapter_id: str = "") -> None:
        self.capability = capability
        self.adapter_id = adapter_id
        super().__init__(
            f"Capability '{capability}' is not supported by broker adapter '{adapter_id or 'unknown'}'"
        )


class BrokerAuthError(BrokerAdapterError):
    """Raised when broker authentication, token resolution, or session fails."""


class BrokerNetworkError(BrokerAdapterError):
    """Raised when transport connection or HTTP network call fails."""


class BrokerRateLimitError(BrokerAdapterError):
    """Raised when broker API rate limit is exceeded."""

    def __init__(
        self,
        message: str = "Broker rate limit exceeded",
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class BrokerOrderRejectedError(BrokerAdapterError):
    """Raised when an order request is immediately rejected by broker API."""

    def __init__(self, message: str, rejection_code: str | None = None) -> None:
        super().__init__(message)
        self.rejection_code = rejection_code


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
    OD-5: ``(broker_order_identity, broker_fill_id)``. The AlgoFortis internal
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
# Broker Funds / Margins Snapshot
# ======================================================================


@dataclass(frozen=True)
class BrokerFundsSnapshot:
    """Canonical snapshot of broker funds and available margins."""

    available_balance: Decimal
    used_margin: Decimal
    total_equity: Decimal
    observed_at: datetime
    currency: str = "INR"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "available_balance",
            as_decimal(self.available_balance, "available_balance"),
        )
        object.__setattr__(
            self,
            "used_margin",
            as_decimal(self.used_margin, "used_margin"),
        )
        object.__setattr__(
            self,
            "total_equity",
            as_decimal(self.total_equity, "total_equity"),
        )
        _require_aware(self.observed_at, "observed_at")
        _require_identifier(self.currency, "currency")

    @property
    def snapshot_identity(self) -> str:
        """Deterministic canonical fingerprint of this funds snapshot."""
        return CanonicalCodec.fingerprint(
            FUNDS_SNAPSHOT_SCHEMA,
            (
                ("available_balance", self.available_balance),
                ("used_margin", self.used_margin),
                ("total_equity", self.total_equity),
                ("currency", self.currency),
                ("observed_at", self.observed_at),
            ),
        )


# ======================================================================
# Broker Position Snapshot
# ======================================================================


@dataclass(frozen=True)
class BrokerPositionSnapshot:
    """Canonical snapshot of an open or closed broker position."""

    instrument_token: str
    trading_symbol: str
    quantity: Decimal
    average_price: Decimal
    product_type: str
    observed_at: datetime
    current_price: Decimal | None = None
    pnl: Decimal | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.instrument_token, "instrument_token")
        _require_identifier(self.trading_symbol, "trading_symbol")
        object.__setattr__(
            self,
            "quantity",
            as_decimal(self.quantity, "quantity"),
        )
        object.__setattr__(
            self,
            "average_price",
            as_decimal(self.average_price, "average_price"),
        )
        _require_identifier(self.product_type, "product_type")
        _require_aware(self.observed_at, "observed_at")
        if self.current_price is not None:
            object.__setattr__(
                self,
                "current_price",
                as_decimal(self.current_price, "current_price"),
            )
        if self.pnl is not None:
            object.__setattr__(
                self,
                "pnl",
                as_decimal(self.pnl, "pnl"),
            )

    @property
    def position_identity(self) -> str:
        """Deterministic canonical fingerprint of this position snapshot."""
        return CanonicalCodec.fingerprint(
            POSITION_SNAPSHOT_SCHEMA,
            (
                ("instrument_token", self.instrument_token),
                ("trading_symbol", self.trading_symbol),
                ("quantity", self.quantity),
                ("average_price", self.average_price),
                ("product_type", self.product_type),
                ("current_price", self.current_price),
                ("pnl", self.pnl),
                ("observed_at", self.observed_at),
            ),
        )


# ======================================================================
# Broker Modify Result
# ======================================================================


@dataclass(frozen=True)
class BrokerModifyResult:
    """Canonical result of an order modification request."""

    order_id: str
    broker_order_identity: str
    modified: bool
    timestamp: datetime
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.order_id, "order_id")
        _require_identifier(self.broker_order_identity, "broker_order_identity")
        _require_aware(self.timestamp, "timestamp")
        _require_optional_text(self.rejection_reason, "rejection_reason")

    @property
    def modify_identity(self) -> str:
        """Deterministic canonical fingerprint of this modify result."""
        return CanonicalCodec.fingerprint(
            MODIFY_RESULT_SCHEMA,
            (
                ("order_id", self.order_id),
                ("broker_order_identity", self.broker_order_identity),
                ("modified", self.modified),
                ("timestamp", self.timestamp),
                ("rejection_reason", self.rejection_reason),
            ),
        )


# ======================================================================
# Base Broker Adapter
# ======================================================================


class BaseBrokerAdapter:
    """Base broker adapter implementing capability enforcement and fail-closed defaults."""

    adapter_id: str = "base"

    def supported_capabilities(self) -> frozenset[BrokerCapability]:
        """Subclasses declare their exact supported capabilities."""
        return frozenset()

    def supports(self, capability: BrokerCapability) -> bool:
        """Truthfully report whether a capability is supported."""
        return capability in self.supported_capabilities()

    def _require_capability(self, capability: BrokerCapability) -> None:
        if not self.supports(capability):
            raise UnsupportedCapabilityError(capability, getattr(self, "adapter_id", "unknown"))

    def connect(self) -> None:
        """Establish transport connection if supported."""
        self._require_capability(BrokerCapability.AUTH)

    def disconnect(self) -> None:
        """Disconnect transport."""
        pass

    def reconnect(self) -> None:
        """Reconnect transport if supported."""
        self._require_capability(BrokerCapability.RECONNECT)

    def modify(
        self,
        order_id: str,
        *,
        new_price: Decimal | None = None,
        new_quantity: Decimal | None = None,
        new_trigger_price: Decimal | None = None,
        timestamp: datetime,
    ) -> BrokerModifyResult:
        """Modify an existing working order if supported."""
        self._require_capability(BrokerCapability.MODIFY_ORDER)
        raise NotImplementedError("modify must be implemented by concrete adapter")

    def query_positions(self) -> tuple[BrokerPositionSnapshot, ...]:
        """Query open broker positions if supported."""
        self._require_capability(BrokerCapability.POSITIONS)
        raise NotImplementedError("query_positions must be implemented by concrete adapter")

    def query_funds(self) -> BrokerFundsSnapshot | None:
        """Query broker funds/margins if supported."""
        self._require_capability(BrokerCapability.FUNDS)
        raise NotImplementedError("query_funds must be implemented by concrete adapter")


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

    * Return only AlgoFortis canonical or adapter-boundary types defined here.
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

    def supported_capabilities(self) -> frozenset[BrokerCapability]:
        """Return declared supported capabilities."""
        ...

    def supports(self, capability: BrokerCapability) -> bool:
        """Check if capability is supported."""
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

    def modify(
        self,
        order_id: str,
        *,
        new_price: Decimal | None = None,
        new_quantity: Decimal | None = None,
        new_trigger_price: Decimal | None = None,
        timestamp: datetime,
    ) -> BrokerModifyResult:
        """Modify an existing working order."""
        ...

    def query_order(self, order_id: str) -> BrokerAdapterOrderSnapshot | None:
        """Return the adapter view of one order, or None when unknown."""
        ...

    def query_open_orders(self) -> tuple[BrokerAdapterOrderSnapshot, ...]:
        """Return adapter views of all non-terminal orders."""
        ...

    def query_positions(self) -> tuple[BrokerPositionSnapshot, ...]:
        """Return all open positions."""
        ...

    def query_funds(self) -> BrokerFundsSnapshot | None:
        """Return current funds and margin state."""
        ...

    def register_observer(self, observer: BrokerObservationCallback) -> None:
        """Register a callback for adapter-originated observations."""
        ...

    def connect(self) -> None:
        """Connect to broker transport."""
        ...

    def disconnect(self) -> None:
        """Disconnect from broker transport."""
        ...

    def reconnect(self) -> None:
        """Reconnect to broker transport."""
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
