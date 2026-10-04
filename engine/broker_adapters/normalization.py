"""Phase 7 Slice 3 — broker-contract normalization (ADR §127.1, §127.5, §127.6).

This layer owns EVERYTHING that may legally cross from the adapter boundary
toward AlgoFortis core concepts.  It is pure and deterministic: no wall clock,
no randomness, no I/O besides one established diagnostic log emission, and no
accounting/lifecycle mutation whatsoever.

NORMALIZATION RULES (frozen)
----------------------------
* Identity: the internal ``order_id`` and the opaque
  ``broker_order_identity`` are carried verbatim; neither is re-derived,
  parsed, or replaced (§127.5 / OD-4).  A broker id is never promoted to any
  authority.
* Fill-dedup verification: fragments are keyed by the adapter-only tuple
  ``(broker_order_identity, broker_fill_id)`` (§127.6).  Normalization
  REJECTS any fragment set containing duplicate keys even though the mock
  adapter already deduplicates — defense in depth at the boundary.
* Aggregation: cumulative quantity is the exact Decimal sum of unique
  fragments; the representative fill price is the deterministic
  quantity-weighted average ``Σ(q·p)/Σq`` under the fixed default Decimal
  context (ROUND_HALF_EVEN, 28 significant digits).
* Core full-fill projection exists ONLY at exact full quantity
  (``cumulative == ordered``).  Nothing else ever produces a projected fill;
  no ``PARTIALLY_FILLED`` state exists in the core lifecycle and none may be
  synthesized here.
* Status normalization: only exact adapter-vocabulary member values are
  recognized.  Anything unmappable normalizes to ``UNKNOWN``, which ALWAYS
  fails closed (never terminal, never projectable).
* PARTIAL THEN TERMINAL NON-FULL (§127.1 item 6): terminal CANCELLED /
  EXPIRED / REJECTED with a non-zero, sub-full exposure is unsupported for
  core projection and fails closed as ``UNSUPPORTED_PARTIAL_SEQUENCE`` —
  no fabricated fill, no silent discard, no accounting mutation, no new
  lifecycle state.

DEFENSIVE CORE-BRIDGE FALLBACK (§127.2)
---------------------------------------
If a contract violation delivers an individual partial-fill fragment toward
the core bridge anyway, :func:`reject_partial_fragment_at_bridge` rejects it
as ``UNSUPPORTED_PARTIAL_FILL``: it emits explicit CRITICAL operational
evidence through the ESTABLISHED Phase-6 stdlib-logging diagnostic surface
(with :func:`engine.audit.sinks.redact_text` bounding all free text), and
returns immutable diagnostic evidence.  The evidence is diagnostic ONLY —
it is never order-state, accounting, risk, or reconciliation authority, and
no AuditEvent family/type is created or required (§127.13).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from engine.broker_adapters.contracts import (
    BrokerAdapterOrderSnapshot,
    BrokerAdapterOrderStatus,
    BrokerFillFragment,
)
from engine.audit.sinks import redact_text

logger = logging.getLogger(__name__)

__all__ = [
    "BRIDGE_REJECTION_SCHEMA",
    "NORMALIZATION_VERSION",
    "UNSUPPORTED_PARTIAL_FILL_TOKEN",
    "UNSUPPORTED_PARTIAL_SEQUENCE_TOKEN",
    "BridgeRejectionEvidence",
    "FragmentAggregate",
    "NormalizedOutcome",
    "NormalizedOutcomeKind",
    "build_fragment_aggregate",
    "evaluate_core_projection",
    "map_raw_status",
    "reject_partial_fragment_at_bridge",
]


NORMALIZATION_VERSION = "algofortis-broker-normalization/v1"
BRIDGE_REJECTION_SCHEMA = "algofortis-bridge-rejection-evidence/v1"
UNSUPPORTED_PARTIAL_FILL_TOKEN = "UNSUPPORTED_PARTIAL_FILL"
UNSUPPORTED_PARTIAL_SEQUENCE_TOKEN = "UNSUPPORTED_PARTIAL_SEQUENCE"

_PROJECTABLE_STATUSES = frozenset(
    {
        BrokerAdapterOrderStatus.FILLED,
        BrokerAdapterOrderStatus.CANCELLED,
        BrokerAdapterOrderStatus.EXPIRED,
        BrokerAdapterOrderStatus.REJECTED,
    }
)


# ======================================================================
# Raw-status normalization (generic; unmappable input always -> UNKNOWN)
# ======================================================================


def map_raw_status(raw_token: str | None) -> BrokerAdapterOrderStatus:
    """Normalize a raw status token into the adapter vocabulary, fail-closed.

    Only exact canonical member names are recognized.  ``None`` and every
    other value normalize to :attr:`BrokerAdapterOrderStatus.UNKNOWN`, which
    downstream evaluation always treats as fail-closed.  No provider-specific
    status sets are invented here.
    """
    if isinstance(raw_token, str):
        for member in BrokerAdapterOrderStatus:
            if raw_token.strip() == member.value:
                return member
    return BrokerAdapterOrderStatus.UNKNOWN


# ======================================================================
# Fragment aggregation
# ======================================================================


@dataclass(frozen=True)
class FragmentAggregate:
    """Deterministic adapter-contained aggregation of unique fill fragments."""

    order_id: str
    broker_order_identity: str
    ordered_quantity: Decimal
    cumulative_filled_quantity: Decimal
    weighted_average_fill_price: Decimal
    fragment_count: int

    @property
    def is_exact_full(self) -> bool:
        return self.cumulative_filled_quantity == self.ordered_quantity


def build_fragment_aggregate(
    fragments: Iterable[BrokerFillFragment],
    *,
    ordered_quantity: Decimal | int | float | str,
) -> FragmentAggregate:
    """Aggregate unique fragments behind one order identity.

    Raises ``ValueError`` when fragments span multiple orders/identities,
    duplicate the §127.6 dedup key, exceed the ordered quantity, or when the
    set is empty (aggregation of nothing is not evidence).
    """
    collected = tuple(fragments)
    if not collected:
        raise ValueError("at least one fill fragment is required")
    ordered = Decimal(ordered_quantity) if not isinstance(ordered_quantity, Decimal) else ordered_quantity
    identities = {fragment.order_id for fragment in collected}
    broker_identities = {fragment.broker_order_identity for fragment in collected}
    if len(identities) != 1 or len(broker_identities) != 1:
        raise ValueError("fragments must share one order_id and one broker_order_identity")
    dedup_keys = [fragment.dedup_key for fragment in collected]
    if len(set(dedup_keys)) != len(dedup_keys):
        raise ValueError("duplicate fragment dedup keys are not representable evidence")
    total_quantity = sum((fragment.fill_quantity for fragment in collected), Decimal("0"))
    if total_quantity > ordered:
        raise ValueError("aggregate exposure exceeds the ordered quantity")
    notional = sum(
        (fragment.fill_quantity * fragment.fill_price for fragment in collected),
        Decimal("0"),
    )
    weighted_price = notional / total_quantity
    first = collected[0]
    return FragmentAggregate(
        order_id=first.order_id,
        broker_order_identity=first.broker_order_identity,
        ordered_quantity=ordered,
        cumulative_filled_quantity=total_quantity,
        weighted_average_fill_price=weighted_price,
        fragment_count=len(collected),
    )


# ======================================================================
# Core-projection decision
# ======================================================================


class NormalizedOutcomeKind:
    """Closed vocabulary of normalization decisions (machine-readable)."""

    OPEN_NO_PROJECTION = "OPEN_NO_PROJECTION"
    UNKNOWN_STATUS_FAIL_CLOSED = "UNKNOWN_STATUS_FAIL_CLOSED"
    FULL_FILL_PROJECTABLE = "FULL_FILL_PROJECTABLE"
    TERMINAL_NO_EXPOSURE_PROJECTABLE = "TERMINAL_NO_EXPOSURE_PROJECTABLE"
    FAIL_CLOSED_UNSUPPORTED_PARTIAL_SEQUENCE = "FAIL_CLOSED_UNSUPPORTED_PARTIAL_SEQUENCE"


_MEMBERS = (
    NormalizedOutcomeKind.OPEN_NO_PROJECTION,
    NormalizedOutcomeKind.UNKNOWN_STATUS_FAIL_CLOSED,
    NormalizedOutcomeKind.FULL_FILL_PROJECTABLE,
    NormalizedOutcomeKind.TERMINAL_NO_EXPOSURE_PROJECTABLE,
    NormalizedOutcomeKind.FAIL_CLOSED_UNSUPPORTED_PARTIAL_SEQUENCE,
)


@dataclass(frozen=True)
class NormalizedOutcome:
    """Immutable decision produced by :func:`evaluate_core_projection`."""

    kind: str
    snapshot: BrokerAdapterOrderSnapshot
    aggregate: FragmentAggregate | None = None
    fail_closed_reason: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in _MEMBERS:
            raise ValueError(f"unknown outcome kind: {self.kind!r}")


def evaluate_core_projection(
    snapshot: BrokerAdapterOrderSnapshot,
    *,
    fragments: tuple[BrokerFillFragment, ...] = (),
) -> NormalizedOutcome:
    """Decide what (if anything) may cross toward AlgoFortis core.

    This function NEVER mutates anything and NEVER fabricates fills.  It is
    the sole gate between adapter-contained evidence and core concepts.
    """
    if snapshot.adapter_status is BrokerAdapterOrderStatus.UNKNOWN:
        logger.error(
            "normalization fail-closed: UNKNOWN adapter status for %s (raw=%r)",
            snapshot.order_id,
            snapshot.raw_status_token,
        )
        return NormalizedOutcome(
            kind=NormalizedOutcomeKind.UNKNOWN_STATUS_FAIL_CLOSED,
            snapshot=snapshot,
            fail_closed_reason="unmapped_adapter_status",
        )

    if snapshot.adapter_status not in _PROJECTABLE_STATUSES:
        return NormalizedOutcome(kind=NormalizedOutcomeKind.OPEN_NO_PROJECTION, snapshot=snapshot)

    has_exposure = snapshot.cumulative_filled_quantity > 0

    if snapshot.adapter_status is BrokerAdapterOrderStatus.FILLED:
        if not snapshot.is_complete_fill:  # defensive; snapshots already validate
            return NormalizedOutcome(
                kind=NormalizedOutcomeKind.FAIL_CLOSED_UNSUPPORTED_PARTIAL_SEQUENCE,
                snapshot=snapshot,
                fail_closed_reason=UNSUPPORTED_PARTIAL_SEQUENCE_TOKEN,
            )
        if not fragments:
            # A full fill without fragment evidence cannot determine a
            # representative price: fail closed rather than invent one.
            logger.error(
                "normalization fail-closed: FILLED order %s has no fragment "
                "evidence for representative-price derivation",
                snapshot.order_id,
            )
            return NormalizedOutcome(
                kind=NormalizedOutcomeKind.UNKNOWN_STATUS_FAIL_CLOSED,
                snapshot=snapshot,
                fail_closed_reason="full_fill_without_fragment_evidence",
            )
        aggregate = build_fragment_aggregate(
            fragments, ordered_quantity=snapshot.ordered_quantity
        )
        if aggregate.cumulative_filled_quantity != snapshot.cumulative_filled_quantity:
            raise ValueError(
                "fragment evidence disagrees with the queried snapshot exposure"
            )
        return NormalizedOutcome(
            kind=NormalizedOutcomeKind.FULL_FILL_PROJECTABLE,
            snapshot=snapshot,
            aggregate=aggregate,
        )

    # Terminal CANCELLED / EXPIRED / REJECTED:
    if has_exposure and not snapshot.is_complete_fill:
        logger.error(
            "normalization fail-closed: %s carries unresolved partial "
            "exposure %s/%s for %s",
            snapshot.adapter_status.value,
            snapshot.cumulative_filled_quantity,
            snapshot.ordered_quantity,
            snapshot.order_id,
        )
        return NormalizedOutcome(
            kind=NormalizedOutcomeKind.FAIL_CLOSED_UNSUPPORTED_PARTIAL_SEQUENCE,
            snapshot=snapshot,
            fail_closed_reason=UNSUPPORTED_PARTIAL_SEQUENCE_TOKEN,
        )

    return NormalizedOutcome(
        kind=NormalizedOutcomeKind.TERMINAL_NO_EXPOSURE_PROJECTABLE,
        snapshot=snapshot,
    )


# ======================================================================
# Defensive core-bridge fallback (§127.2) — observability, zero authority
# ======================================================================


@dataclass(frozen=True)
class BridgeRejectionEvidence:
    """Immutable DIAGNOSTIC-ONLY record of an UNSUPPORTED_PARTIAL_FILL rejection.

    Carries no authority of any kind: never order-state, accounting, risk, or
    reconciliation authority.  Existence of this evidence does not change any
    lifecycle state and does not mutate any accounting figure.
    """

    schema: str
    reason_token: str
    order_id: str
    broker_order_identity: str
    broker_fill_id: str
    fill_quantity: Decimal
    fill_price: Decimal
    observation_sequence: int
    fragment_identity: str
    bridge: str


def reject_partial_fragment_at_bridge(
    fragment: BrokerFillFragment,
    *,
    bridge: str = "phase7-core-bridge",
) -> BridgeRejectionEvidence:
    """Reject one partial fragment that illegally reached the core bridge.

    Emits mandatory CRITICAL diagnostic evidence through the established
    stdlib-logging surface and returns immutable diagnostic-only evidence.
    Performs NO mutation of any kind: callers must keep the affected
    integration path fail-closed, keep lifecycle states unchanged, and leave
    accounting untouched until reconciliation clears the condition.
    """
    if not isinstance(fragment, BrokerFillFragment):
        raise TypeError("fragment must be a BrokerFillFragment")
    evidence = BridgeRejectionEvidence(
        schema=BRIDGE_REJECTION_SCHEMA,
        reason_token=UNSUPPORTED_PARTIAL_FILL_TOKEN,
        order_id=redact_text(fragment.order_id, max_len=120),
        broker_order_identity=redact_text(fragment.broker_order_identity, max_len=120),
        broker_fill_id=redact_text(fragment.broker_fill_id, max_len=120),
        fill_quantity=fragment.fill_quantity,
        fill_price=fragment.fill_price,
        observation_sequence=fragment.observation_sequence,
        fragment_identity=fragment.fragment_identity,
        bridge=redact_text(bridge, max_len=120),
    )
    logger.critical(
        "%s: partial fill fragment rejected at %s "
        "(order=%s identity=%s fill=%s quantity=%s sequence=%s). "
        "Path stays fail-closed; lifecycle and accounting untouched.",
        UNSUPPORTED_PARTIAL_FILL_TOKEN,
        evidence.bridge,
        evidence.order_id,
        evidence.broker_order_identity,
        evidence.broker_fill_id,
        evidence.fill_quantity,
        evidence.observation_sequence,
    )
    return evidence
