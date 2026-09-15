"""Phase 7 Slice 5 — minimal internal/mock integration pipeline (ADR §127).

PURPOSE
-------
The smallest offline wiring needed to PROVE the broker-independent boundary
preserves SentinelX authority end-to-end.  It composes EXISTING canonical
components in the FROZEN order and adds no authority of its own:

    existing RiskGate.evaluate_pre_order  →  MockBrokerAdapter.submit
    →  Slice-3 normalization  →  existing ExecutionResult full-fill shape

AUTHORITY PRESERVATION (frozen properties)
------------------------------------------
* The existing RiskGate ALWAYS precedes mock submission; a risk rejection
  never reaches the adapter (the adapter cannot see rejected candidates).
* The approved gate quantity is frozen: submitting an order whose quantity
  differs from the gate-approved sizing fails closed (§73 lock preserved).
* ``entry_intent_identity`` remains the SentinelX-owned submission/dedup
  identity (§127.4 / OD-3); the supervisor ledger reuses it verbatim.
* Full-fill projection exists ONLY at exact full quantity and produces the
  existing canonical ``ExecutionResult`` FILLED shape — nothing new is
  invented downstream (§127.1 / OD-1 Option A).
* An individual partial fragment reaching this bridge is rejected as
  ``UNSUPPORTED_PARTIAL_FILL`` through the established diagnostic surface;
  no accounting mutation, no lifecycle change, no audit-family invention
  (§127.2, §127.13).
* Reconnect/reconciliation safety outranks retry: the wired
  :class:`SubmissionRetrySupervisor` enforces §127.10 structurally.
* No accounting, persistence, protective, or audit component is imported,
  called, or modified here.  SCHEMA_VERSION remains 7 (§127.13).

DETERMINISM (§127.12 / OD-9): every input is caller-supplied and scripted;
this module contains no clocks, randomness, delays, threads, or network.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from engine.broker_adapters.mock_broker import MockBrokerAdapter
from engine.broker_adapters.mock_recovery import (
    ExpectedAdapterOrderState,
    SubmissionRetrySupervisor,
    reconcile as reconcile_adapter_state,
)
from engine.broker_adapters.normalization import (
    NormalizedOutcomeKind,
    evaluate_core_projection,
    reject_partial_fragment_at_bridge,
)
from engine.broker_adapters.contracts import BrokerFillFragment, BrokerSubmissionResult
from engine.execution.model import ExecutionOutcome, ExecutionResult
from engine.core.numeric import as_decimal
from engine.portfolio.model import InstrumentIdentity, InstrumentSpecification
from engine.risk.risk_manager import (
    RiskDay,
    RiskGate,
    RiskOutcome,
    entry_intent_identity,
)

logger = logging.getLogger(__name__)

__all__ = [
    "MOCK_PIPELINE_VERSION",
    "PARITY_SLIPPAGE_MODEL_ID",
    "PipelineFullFillProjection",
    "PipelineSubmissionOutcome",
    "PipelineSubmissionOutcomeKind",
    "RiskGatedMockPipeline",
]


MOCK_PIPELINE_VERSION = "sentinelx-mock-pipeline/v1"

# Parity label recorded on projected execution evidence so reviewers can
# distinguish pipeline-projected fills from live execution paths in logs.
PARITY_SLIPPAGE_MODEL_ID = "phase7-mock-parity/v1"


class PipelineSubmissionOutcomeKind:
    """Closed vocabulary of pipeline submission outcomes."""

    SUBMITTED = "SUBMITTED"
    RISK_REJECTED = "RISK_REJECTED"
    DUPLICATE_LOGICAL_SUBMISSION = "DUPLICATE_LOGICAL_SUBMISSION"
    ADAPTER_REJECTED = "ADAPTER_REJECTED"


@dataclass(frozen=True)
class PipelineSubmissionOutcome:
    """Immutable result of one risk-gated mock submission attempt."""

    kind: str
    submission: BrokerSubmissionResult | None = None
    risk_reason: str | None = None
    approved_quantity: Decimal | None = None


@dataclass(frozen=True)
class PipelineFullFillProjection:
    """Immutable full-fill projection produced ONLY at exact full quantity."""

    execution_result: ExecutionResult
    weighted_average_fill_price: Decimal
    cumulative_filled_quantity: Decimal
    fragment_count: int


class RiskGatedMockPipeline:
    """Risk-gate-first wiring over the deterministic offline mock adapter."""

    def __init__(
        self,
        *,
        risk_gate: RiskGate,
        adapter: MockBrokerAdapter,
        supervisor: SubmissionRetrySupervisor,
        account_id: str = "pipeline-account",
    ) -> None:
        if not isinstance(risk_gate, RiskGate):
            raise TypeError("risk_gate must be a RiskGate")
        if not isinstance(adapter, MockBrokerAdapter):
            raise TypeError("adapter must be a MockBrokerAdapter")
        if not isinstance(supervisor, SubmissionRetrySupervisor):
            raise TypeError("supervisor must be a SubmissionRetrySupervisor")
        self._risk_gate = risk_gate
        self._adapter = adapter
        self._supervisor = supervisor
        self._account_id = account_id

    @property
    def adapter(self) -> MockBrokerAdapter:
        return self._adapter

    @property
    def supervisor(self) -> SubmissionRetrySupervisor:
        return self._supervisor

    # ------------------------------------------------------------------
    # Submission: existing risk gate ALWAYS precedes the mock boundary
    # ------------------------------------------------------------------

    def submit(
        self,
        order,
        *,
        instrument_identity: InstrumentIdentity,
        specification: InstrumentSpecification,
        direction: PositionDirection,
        intended_position_key,
        capital,
        entry_price,
        snapshot,
        book,
        candidate_plan,
        risk_day: RiskDay,
        current_net_equity,
        starting_capital,
        submission_market_timestamp,
    ) -> PipelineSubmissionOutcome:
        gate_result = self._risk_gate.evaluate_pre_order(
            direction=direction,
            intended_position_key=intended_position_key,
            capital=capital,
            entry_price=entry_price,
            specification=specification,
            snapshot=snapshot,
            book=book,
            candidate_plan=candidate_plan,
            risk_day=risk_day,
            current_net_equity=current_net_equity,
            starting_capital=starting_capital,
            prior_state=None,
            pending_commitments=(),
            cost_projection=None,
        )
        if gate_result.outcome is not RiskOutcome.APPROVED:
            logger.warning(
                "pipeline submission blocked by existing risk gate: %s",
                gate_result.reason,
            )
            return PipelineSubmissionOutcome(
                kind=PipelineSubmissionOutcomeKind.RISK_REJECTED,
                risk_reason=gate_result.reason,
            )

        approved_quantity = as_decimal(gate_result.quantity, "gate_result.quantity")
        requested_quantity = as_decimal(order.quantity, "order.quantity")
        if requested_quantity != approved_quantity:
            # §73 lock: approved quantity is frozen; never resized here.
            raise ValueError(
                "submitted order quantity differs from the gate-approved quantity"
            )

        intent_identity = entry_intent_identity(
            strategy_id=order.strategy_id,
            strategy_version=order.strategy_version,
            identity=instrument_identity,
            timeframe=order.timeframe,
            originating_timestamp=order.originating_timestamp,
        )
        if not self._supervisor.register_logical_submission(intent_identity):
            return PipelineSubmissionOutcome(
                kind=PipelineSubmissionOutcomeKind.DUPLICATE_LOGICAL_SUBMISSION,
            )

        submission = self._adapter.submit(
            order,
            instrument_identity=instrument_identity,
            specification=specification,
            submission_market_timestamp=submission_market_timestamp,
        )
        if not submission.accepted:
            return PipelineSubmissionOutcome(
                kind=PipelineSubmissionOutcomeKind.ADAPTER_REJECTED,
                submission=submission,
            )
        self._record_clean_state(
            order_id=submission.order_id,
            broker_order_identity=submission.broker_order_identity,
            ordered_quantity=requested_quantity,
        )
        return PipelineSubmissionOutcome(
            kind=PipelineSubmissionOutcomeKind.SUBMITTED,
            submission=submission,
            approved_quantity=approved_quantity,
        )

    # ------------------------------------------------------------------
    # Reconciliation (query → compare → record; §127.10 precedence holds)
    # ------------------------------------------------------------------

    def refresh_reconciliation(self, order_id: str):
        expected = self._expected_for(order_id)
        verdict = reconcile_adapter_state(
            expected=expected,
            adapter_snapshot=self._adapter.query_order(order_id),
        )
        self._supervisor.record_reconciliation(verdict)
        return verdict

    # ------------------------------------------------------------------
    # Full-fill projection (exact-full gate → canonical ExecutionResult)
    # ------------------------------------------------------------------

    def project_full_fill(
        self, order, *, order_id: str
    ) -> PipelineFullFillProjection | None:
        """Project an exact full fill into the existing canonical fill shape.

        The owning caller supplies the original canonical order: this pipeline
        keeps no second order ledger of its own.
        """
        order_state = self._adapter.order_view(order_id)
        if order_state is None:
            return None
        snapshot = self._adapter.query_order(order_id)
        fragments = tuple(self.fragments_for(order_id))
        outcome = evaluate_core_projection(snapshot, fragments=fragments)
        if outcome.kind is not NormalizedOutcomeKind.FULL_FILL_PROJECTABLE:
            return None
        aggregate = outcome.aggregate
        execution_result = ExecutionResult(
            order=order,
            outcome=ExecutionOutcome.FILLED,
            execution_bar_timestamp=max(f.observed_at for f in fragments),
            pre_slippage_price=aggregate.weighted_average_fill_price,
            fill_price=aggregate.weighted_average_fill_price,
            filled_quantity=aggregate.cumulative_filled_quantity,
            reason="phase7_mock_full_fill_projection",
            slippage_model_id=PARITY_SLIPPAGE_MODEL_ID,
            slippage_amount=Decimal("0"),
            metadata={
                "fragment_count": aggregate.fragment_count,
                "broker_order_identity": aggregate.broker_order_identity,
            },
        )
        return PipelineFullFillProjection(
            execution_result=execution_result,
            weighted_average_fill_price=aggregate.weighted_average_fill_price,
            cumulative_filled_quantity=aggregate.cumulative_filled_quantity,
            fragment_count=aggregate.fragment_count,
        )

    # ------------------------------------------------------------------
    # Defensive bridge fallback visibility (§127.2)
    # ------------------------------------------------------------------

    def handle_bridge_fragment(self, fragment: BrokerFillFragment):
        """Route one illegally-bridged partial fragment through §127.2."""
        evidence = reject_partial_fragment_at_bridge(fragment, bridge=self._account_id)
        self._supervisor.mark_fail_closed(evidence.reason_token)
        return evidence

    # ------------------------------------------------------------------
    # Introspection helpers
    # ------------------------------------------------------------------

    def fragments_for(self, order_id: str) -> tuple[BrokerFillFragment, ...]:
        return tuple(
            observation
            for observation in self._adapter.delivered_observations
            if isinstance(observation, BrokerFillFragment) and observation.order_id == order_id
        )

    def _expected_for(self, order_id: str) -> ExpectedAdapterOrderState:
        view = self._adapter.order_view(order_id)
        if view is None:
            raise KeyError(f"unknown pipeline order: {order_id!r}")
        return ExpectedAdapterOrderState(
            order_id=view.order_id,
            broker_order_identity=view.broker_order_identity,
            ordered_quantity=view.ordered_quantity,
            expected_cumulative_filled_quantity=view.cumulative_filled_quantity,
        )

    def _record_clean_state(
        self, *, order_id: str, broker_order_identity: str, ordered_quantity: Decimal
    ) -> None:
        verdict = reconcile_adapter_state(
            expected=ExpectedAdapterOrderState(
                order_id=order_id,
                broker_order_identity=broker_order_identity,
                ordered_quantity=ordered_quantity,
                expected_cumulative_filled_quantity=Decimal("0"),
            ),
            adapter_snapshot=self._adapter.query_order(order_id),
        )
        self._supervisor.record_reconciliation(verdict)
