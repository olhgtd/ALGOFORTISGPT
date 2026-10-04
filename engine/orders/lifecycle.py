"""Immutable pre-execution order lifecycle transitions and terminal cause evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from engine.orders.model import OrderRequest
from engine.reproducibility.codec import CanonicalCodec


class OrderLifecycleState(str, Enum):
    """States owned by the order lifecycle before broker acceptance or execution exists.

    Phase-4 Slice-1 extension: ``FILLED`` added as the ONLY new terminal state,
    reachable from ``QUEUED`` (accepted accounting ownership).  The existing
    vocabulary (CREATED / VALIDATED / QUEUED / CANCELLED / REJECTED / EXPIRED)
    is preserved; ``QUEUED`` remains the pending/pre-execution state and no
    duplicate SUBMITTED/PENDING state is introduced.
    """

    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    QUEUED = "QUEUED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    FILLED = "FILLED"


_ALLOWED_TRANSITIONS = {
    OrderLifecycleState.CREATED: frozenset(
        {OrderLifecycleState.VALIDATED, OrderLifecycleState.CANCELLED, OrderLifecycleState.REJECTED}
    ),
    OrderLifecycleState.VALIDATED: frozenset(
        {OrderLifecycleState.QUEUED, OrderLifecycleState.CANCELLED, OrderLifecycleState.REJECTED}
    ),
    OrderLifecycleState.QUEUED: frozenset(
        {OrderLifecycleState.CANCELLED, OrderLifecycleState.REJECTED, OrderLifecycleState.EXPIRED, OrderLifecycleState.FILLED}
    ),
    OrderLifecycleState.CANCELLED: frozenset(),
    OrderLifecycleState.REJECTED: frozenset(),
    OrderLifecycleState.EXPIRED: frozenset(),
    OrderLifecycleState.FILLED: frozenset(),
}


@dataclass(frozen=True)
class OrderLifecycle:
    """An immutable lifecycle record; no fill-related transitions exist here."""

    order: OrderRequest
    state: OrderLifecycleState = OrderLifecycleState.CREATED

    def __post_init__(self) -> None:
        if not isinstance(self.order, OrderRequest):
            raise TypeError("order must be an OrderRequest")
        if not isinstance(self.state, OrderLifecycleState):
            raise TypeError("state must be an OrderLifecycleState")

    def transition_to(self, state: OrderLifecycleState) -> "OrderLifecycle":
        """Return a new lifecycle record after one valid transition."""
        if not isinstance(state, OrderLifecycleState):
            raise TypeError("state must be an OrderLifecycleState")
        if state not in _ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(f"invalid order lifecycle transition: {self.state.value} -> {state.value}")
        return OrderLifecycle(self.order, state)


class OrderLifecycleCauseType(str, Enum):
    """One-authority terminal cause classification.

    The lifecycle layer NEVER recomputes authoritative reasons or formulas; it
    mirrors the terminal state and references the EXISTING authoritative
    evidence by a canonical identity (see ``cause_reference``).
    """

    STRATEGY_INVALIDATION = "STRATEGY_INVALIDATION"
    MECHANICAL_EXPIRY = "MECHANICAL_EXPIRY"
    DAY_EXPIRY = "DAY_EXPIRY"
    Q56_REJECTION = "Q56_REJECTION"
    Q65_REJECTION = "Q65_REJECTION"
    ACCOUNTING_REJECTION = "ACCOUNTING_REJECTION"
    FILL = "FILL"


def order_lifecycle_cause_reference(cause_type: OrderLifecycleCauseType, *, reference: str | None = None, reason: str | None = None) -> str:
    """Deterministic canonical cause reference (one authority per fact).

    ``reference`` is the identity of EXISTING authoritative evidence when one
    exists (e.g. ``EntryValidityResult.evidence_identity`` for strategy
    invalidation, ``EntryValiditySpec.spec_identity`` for mechanical expiry).
    Otherwise a canonical fingerprint of the existing authoritative reason
    string is built (e.g. ``daily_loss_limit_exceeded`` from the RiskGateResult,
    ``day_session_expired`` from the ExecutionResult, the AccountingResult
    reason) -- the reason is REFERENCED, never recomputed.
    """
    if not isinstance(cause_type, OrderLifecycleCauseType):
        raise TypeError("cause_type must be an OrderLifecycleCauseType")
    if reference is not None:
        if not isinstance(reference, str) or not reference.strip():
            raise ValueError("cause reference must be a non-empty string")
        return reference.strip()
    if reason is None or not reason.strip():
        raise ValueError("a canonical cause reference requires a reference identity or an authoritative reason")
    return CanonicalCodec.fingerprint(
        "algofortis-order-lifecycle-cause/v1",
        (("cause_type", cause_type.value), ("reason", reason.strip())),
    )


@dataclass(frozen=True)
class OrderLifecycleEvent:
    """Immutable terminal lifecycle evidence for one pending logical entry.

    ``cause_reference`` points at the EXISTING authoritative evidence identity
    (EntryValidityResult / EntryValiditySpec / RiskGateResult reason /
    ExecutionResult reason / AccountingResult reason).  Q56 stays authoritative
    ONLY in ``OrchestrationResult.risk_rejections``; this event references it,
    never duplicates its formula.
    """

    entry_identity: str
    state: OrderLifecycleState
    cause_type: OrderLifecycleCauseType
    cause_reference: str
    decision_timestamp: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.entry_identity, str) or not self.entry_identity.strip():
            raise ValueError("entry_identity must be a non-empty string")
        if not isinstance(self.state, OrderLifecycleState):
            raise TypeError("state must be an OrderLifecycleState")
        if not isinstance(self.cause_type, OrderLifecycleCauseType):
            raise TypeError("cause_type must be an OrderLifecycleCauseType")
        if not isinstance(self.cause_reference, str) or not self.cause_reference.strip():
            raise ValueError("cause_reference must be a non-empty string")
        if self.state not in _ALLOWED_TRANSITIONS[OrderLifecycleState.QUEUED]:
            raise ValueError("lifecycle events record only terminal states")
        if self.decision_timestamp.tzinfo is None or self.decision_timestamp.utcoffset() is None:
            raise ValueError("decision_timestamp must be timezone-aware")
        object.__setattr__(self, "entry_identity", self.entry_identity.strip())
        object.__setattr__(self, "cause_reference", self.cause_reference.strip())

    @property
    def event_identity(self) -> str:
        """Canonical replay identity for this terminal event."""
        return CanonicalCodec.fingerprint(
            "algofortis-order-lifecycle-event/v1",
            (
                ("entry", self.entry_identity),
                ("state", self.state.value),
                ("cause_type", self.cause_type.value),
                ("cause_reference", self.cause_reference),
                ("decision_time", self.decision_timestamp),
            ),
        )
