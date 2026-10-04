"""Phase 7 Slice 4 — deterministic mock-only recovery, reconciliation, retry.

Frozen contracts: ADR §127.4 (OD-3), §127.8 (OD-6), §127.10 (OD-8 absolute
precedence), §127.11 (PaperReconciliationEngine separation), §127.12 (OD-9).

ABSOLUTE PRECEDENCE (§127.10)
-----------------------------
RECONNECT / RECONCILIATION SAFETY > RETRY LOGIC.  The
:class:`SubmissionRetrySupervisor` enforces this structurally: submission
retries are permitted ONLY while (a) the transport is connected AND (b) the
latest recorded reconciliation verdict is CLEAN.  A disconnect suspends every
pending retry immediately; any non-CLEAN reconciliation verdict fails the
affected integration path CLOSED until a fresh CLEAN reconciliation is
explicitly recorded.  Retry policies can never override this gate.

DETERMINISM (§127.12 / OD-9)
----------------------------
Everything here is driven by explicitly supplied values.  No wall clock, no
randomness, no delays.  Timeout / transport-failure / rate-limit conditions
exist only as scripted failure classifications consumed by the deterministic
retry policy.

MOCK-ONLY SCOPE (§127.8 / OD-6, §127.9 / OD-7)
----------------------------------------------
These are software-contract simulations for the offline mock boundary.  No
real external submission retry is authorized; a future real provider requires
a separate owner-approved review.

SEPARATION (§127.11)
--------------------
This module is a SEPARATE thin broker-contract/mock reconciliation boundary.
It never modifies ``engine.reconciliation.paper.engine.PaperReconciliationEngine``, adds no
live/provider state to it, and shares nothing with it beyond public concepts.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from engine.broker_adapters.contracts import (
    BrokerAdapterOrderSnapshot,
    BrokerAdapterOrderStatus,
)

__all__ = [
    "MOCK_RECONCILIATION_VERSION",
    "ExpectedAdapterOrderState",
    "FailureClassification",
    "ReconciliationDiscrepancy",
    "ReconciliationResult",
    "ReconciliationVerdict",
    "RetryAction",
    "RetryDecision",
    "SubmissionRetrySupervisor",
    "reconcile",
]


MOCK_RECONCILIATION_VERSION = "algofortis-mock-reconciliation/v1"


class ReconciliationVerdict(str, Enum):
    """Closed verdict vocabulary (§127.10)."""

    CLEAN = "CLEAN"
    MISMATCH = "MISMATCH"
    UNCERTAIN = "UNCERTAIN"
    INCOMPLETE = "INCOMPLETE"
    UNSUPPORTED = "UNSUPPORTED"

    @property
    def is_clean(self) -> bool:
        return self is ReconciliationVerdict.CLEAN


@dataclass(frozen=True)
class ExpectedAdapterOrderState:
    """AlgoFortis-owned expectation for one order at the adapter boundary."""

    order_id: str
    broker_order_identity: str
    ordered_quantity: Decimal
    expected_cumulative_filled_quantity: Decimal
    expected_status: BrokerAdapterOrderStatus | None = None
    expected_last_observation_sequence: int | None = None

    def __post_init__(self) -> None:
        from engine.core.numeric import as_decimal

        if not isinstance(self.order_id, str) or not self.order_id.strip():
            raise ValueError("order_id must be a non-empty string")
        if (
            not isinstance(self.broker_order_identity, str)
            or not self.broker_order_identity.strip()
        ):
            raise ValueError("broker_order_identity must be a non-empty string")
        object.__setattr__(self, "ordered_quantity", as_decimal(self.ordered_quantity, "ordered_quantity"))
        object.__setattr__(
            self,
            "expected_cumulative_filled_quantity",
            as_decimal(self.expected_cumulative_filled_quantity, "expected_cumulative_filled_quantity"),
        )
        if self.ordered_quantity <= 0:
            raise ValueError("ordered_quantity must be positive")
        if self.expected_cumulative_filled_quantity < 0:
            raise ValueError("expected_cumulative_filled_quantity must be >= 0")
        if self.expected_cumulative_filled_quantity > self.ordered_quantity:
            raise ValueError("expected_cumulative_filled_quantity exceeds ordered_quantity")
        if self.expected_status is not None and not isinstance(
            self.expected_status, BrokerAdapterOrderStatus
        ):
            raise TypeError("expected_status must be a BrokerAdapterOrderStatus or None")
        if self.expected_last_observation_sequence is not None:
            sequence = self.expected_last_observation_sequence
            if isinstance(sequence, bool) or not isinstance(sequence, int):
                raise TypeError("expected_last_observation_sequence must be an int or None")
            if sequence < 0:
                raise ValueError("expected_last_observation_sequence must be >= 0")


@dataclass(frozen=True)
class ReconciliationDiscrepancy:
    """One machine-readable field-level discrepancy."""

    field: str
    expected: str
    observed: str


@dataclass(frozen=True)
class ReconciliationResult:
    """Immutable outcome of one thin-boundary reconciliation comparison.

    This result IS the reconciliation authority for the MOCK processing path
    (§127.10).  It carries no accounting authority and mutates nothing.
    """

    verdict: ReconciliationVerdict
    expected_order_id: str
    discrepancies: tuple[ReconciliationDiscrepancy, ...] = ()
    detail: str | None = None

    @property
    def is_clean(self) -> bool:
        return self.verdict.is_clean


def reconcile(
    *,
    expected: ExpectedAdapterOrderState,
    adapter_snapshot: BrokerAdapterOrderSnapshot | None,
) -> ReconciliationResult:
    """Compare AlgoFortis-owned expectations against the synchronous query view.

    Deterministic rules:

    * ``None`` snapshot while an open order is expected ⇒ ``UNCERTAIN``
      (an unavailable/absent answer is never treated as "nothing happened").
    * Any identity, status, or exposure difference ⇒ ``MISMATCH``.
    * Exact agreement on every compared field ⇒ ``CLEAN``.
    * Expectation states that cannot legally be compared (unknown expected
      status paired with impossible exposure geometry) are rejected at
      construction time; comparison itself never invents support.
    """
    if adapter_snapshot is None:
        return ReconciliationResult(
            verdict=ReconciliationVerdict.UNCERTAIN,
            expected_order_id=expected.order_id,
            detail="adapter returned no snapshot for an expected order",
            discrepancies=(
                ReconciliationDiscrepancy("snapshot", "present", "absent"),
            ),
        )

    discrepancies: list[ReconciliationDiscrepancy] = []
    if adapter_snapshot.order_id != expected.order_id:
        discrepancies.append(
            ReconciliationDiscrepancy("order_id", expected.order_id, adapter_snapshot.order_id)
        )
    if adapter_snapshot.broker_order_identity != expected.broker_order_identity:
        discrepancies.append(
            ReconciliationDiscrepancy(
                "broker_order_identity",
                expected.broker_order_identity,
                adapter_snapshot.broker_order_identity,
            )
        )
    if adapter_snapshot.cumulative_filled_quantity != expected.expected_cumulative_filled_quantity:
        discrepancies.append(
            ReconciliationDiscrepancy(
                "cumulative_filled_quantity",
                str(expected.expected_cumulative_filled_quantity),
                str(adapter_snapshot.cumulative_filled_quantity),
            )
        )
    if adapter_snapshot.ordered_quantity != expected.ordered_quantity:
        discrepancies.append(
            ReconciliationDiscrepancy(
                "ordered_quantity",
                str(expected.ordered_quantity),
                str(adapter_snapshot.ordered_quantity),
            )
        )
    if (
        expected.expected_status is not None
        and adapter_snapshot.adapter_status is not expected.expected_status
    ):
        discrepancies.append(
            ReconciliationDiscrepancy(
                "adapter_status",
                expected.expected_status.value,
                adapter_snapshot.adapter_status.value,
            )
        )
    if (
        expected.expected_last_observation_sequence is not None
        and adapter_snapshot.last_observation_sequence
        < expected.expected_last_observation_sequence
    ):
        # The adapter's own view is BEHIND evidence already delivered to the
        # owner: the answer is present but incomplete.
        return ReconciliationResult(
            verdict=ReconciliationVerdict.INCOMPLETE,
            expected_order_id=expected.order_id,
            discrepancies=(
                ReconciliationDiscrepancy(
                    "last_observation_sequence",
                    str(expected.expected_last_observation_sequence),
                    str(adapter_snapshot.last_observation_sequence),
                ),
            ),
            detail="adapter view is behind the owner-delivered observation record",
        )

    if discrepancies:
        return ReconciliationResult(
            verdict=ReconciliationVerdict.MISMATCH,
            expected_order_id=expected.order_id,
            discrepancies=tuple(discrepancies),
            detail="field-level disagreement between owned state and adapter view",
        )

    return ReconciliationResult(
        verdict=ReconciliationVerdict.CLEAN,
        expected_order_id=expected.order_id,
        detail="deterministic match on identity, quantities, and status",
    )


class FailureClassification(str, Enum):
    """Scripted submission-failure classification consumed by the retry policy.

    These are SOFTWARE-CONTRACT SIMULATIONS ONLY (§127.8 / OD-6).
    """

    TIMEOUT = "TIMEOUT"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    DUPLICATE_ALREADY_ACCEPTED = "DUPLICATE_ALREADY_ACCEPTED"
    PERMANENT_REJECTION = "PERMANENT_REJECTION"
    PATH_FAIL_CLOSED = "PATH_FAIL_CLOSED"


class RetryAction(str, Enum):
    RETRY_NOW = "RETRY_NOW"
    STOP_RETRY = "STOP_RETRY"


_RETRYABLE = frozenset(
    {
        FailureClassification.TIMEOUT,
        FailureClassification.TRANSPORT_ERROR,
        FailureClassification.RATE_LIMITED,
    }
)


@dataclass(frozen=True)
class RetryDecision:
    action: RetryAction
    reason: str


class SubmissionRetrySupervisor:
    """Deterministic gate owning retry permission and path health.

    Structural enforcement of §127.10: :attr:`retry_permitted` is True only
    while the simulated transport is connected AND the latest recorded
    reconciliation verdict is CLEAN.  Disconnects suspend retries instantly;
    any non-CLEAN verdict fails the path closed until a fresh CLEAN verdict is
    explicitly recorded.
    """

    def __init__(
        self,
        *,
        max_attempts_per_submission: int = 3,
        connected: bool = True,
    ) -> None:
        if isinstance(max_attempts_per_submission, bool) or not isinstance(
            max_attempts_per_submission, int
        ):
            raise TypeError("max_attempts_per_submission must be an int")
        if max_attempts_per_submission < 1:
            raise ValueError("max_attempts_per_submission must be >= 1")
        self._connected = bool(connected)
        self._max_attempts = max_attempts_per_submission
        self._latest_verdict: ReconciliationVerdict | None = None
        self._fail_closed_reason: str | None = None
        self._submitted_intents: set[str] = set()

    # ------------------------------------------------------------------
    # Path health (§127.10)
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def latest_reconciliation_verdict(self) -> ReconciliationVerdict | None:
        return self._latest_verdict

    @property
    def fail_closed_reason(self) -> str | None:
        return self._fail_closed_reason

    @property
    def retry_permitted(self) -> bool:
        """True only when connected AND latest reconciliation is CLEAN."""
        return self._connected and self._latest_verdict is ReconciliationVerdict.CLEAN

    def suspend_for_disconnect(self, reason: str) -> None:
        """DISCONNECT: submission-retry activity is suspended immediately.

        Any previously recorded CLEAN verdict is invalidated: connectivity
        restoration alone can never re-eligibilize the path (§127.10); a
        fresh query → reconcile → CLEAN cycle is structurally required.
        """
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason must be a non-empty string")
        self._connected = False
        self._latest_verdict = ReconciliationVerdict.UNCERTAIN
        self._fail_closed_reason = f"disconnected:{reason}"

    def restore_connectivity(self) -> None:
        """RECONNECT transport availability only.

        Connectivity alone does NOT make the path eligible: a fresh CLEAN
        reconciliation must still be recorded (query → reconcile).
        """
        self._connected = True

    def record_reconciliation(self, result: ReconciliationResult) -> ReconciliationResult:
        """Record one reconciliation verdict for the affected path."""
        if not isinstance(result, ReconciliationResult):
            raise TypeError("result must be a ReconciliationResult")
        self._latest_verdict = result.verdict
        if result.is_clean:
            self._fail_closed_reason = None
        else:
            self._fail_closed_reason = f"reconciliation:{result.verdict.value}"
        return result

    def mark_fail_closed(self, reason: str) -> None:
        """Fail the affected integration path closed (unsupported condition)."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason must be a non-empty string")
        self._latest_verdict = ReconciliationVerdict.UNSUPPORTED
        self._fail_closed_reason = f"unsupported:{reason}"

    # ------------------------------------------------------------------
    # Idempotent logical-submission ledger (entry-intent authority, §127.4)
    # ------------------------------------------------------------------

    def register_logical_submission(self, entry_intent_identity: str) -> bool:
        """Register one logical submission; return False when already known.

        The ``entry_intent_identity`` REMAINS the AlgoFortis-owned deterministic
        submission/dedup identity (§127.4 / OD-3).  This ledger is a mock-path
        convenience that reuses that identity verbatim; it never replaces the
        core or adapter dedup layers.
        """
        if not isinstance(entry_intent_identity, str) or not entry_intent_identity.strip():
            raise ValueError("entry_intent_identity must be a non-empty string")
        if entry_intent_identity in self._submitted_intents:
            return False
        self._submitted_intents.add(entry_intent_identity)
        return True

    # ------------------------------------------------------------------
    # Deterministic retry decisioning (§127.8 / OD-6, mock-only)
    # ------------------------------------------------------------------

    def evaluate_retry(
        self,
        *,
        classification: FailureClassification,
        attempt: int,
    ) -> RetryDecision:
        """Decide the next action for one scripted failed attempt."""
        if isinstance(classification, bool) or not isinstance(classification, FailureClassification):
            raise TypeError("classification must be a FailureClassification")
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
            raise ValueError("attempt must be a positive int")

        if not self.retry_permitted:
            return RetryDecision(
                action=RetryAction.STOP_RETRY,
                reason=self._fail_closed_reason or "path_not_eligible",
            )
        if classification is FailureClassification.DUPLICATE_ALREADY_ACCEPTED:
            return RetryDecision(
                action=RetryAction.STOP_RETRY,
                reason="duplicate_logical_submission_already_accepted",
            )
        if classification is FailureClassification.PERMANENT_REJECTION:
            return RetryDecision(
                action=RetryAction.STOP_RETRY,
                reason="permanent_rejection_not_retryable",
            )
        if classification is FailureClassification.PATH_FAIL_CLOSED:
            return RetryDecision(action=RetryAction.STOP_RETRY, reason="path_fail_closed")
        if classification not in _RETRYABLE:
            return RetryDecision(action=RetryAction.STOP_RETRY, reason="unclassified")
        if attempt >= self._max_attempts:
            return RetryDecision(
                action=RetryAction.STOP_RETRY,
                reason=f"attempt_budget_exhausted_at_{self._max_attempts}",
            )
        return RetryDecision(action=RetryAction.RETRY_NOW, reason=f"retryable_{classification.value}")
