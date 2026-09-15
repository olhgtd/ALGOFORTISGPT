"""Broker-independent order-adapter boundary (Phase 7).

Phase 7 scope (ADR §127.0, §127.9) is the broker-independent adapter
architecture plus a deterministic OFFLINE mock contract. This package contains
no vendor SDK, no transport client, no credential handling, and no live-account
integration; nothing in it may be connected to a real brokerage.

Slice 1 exposes the contract surface only: see :mod:`engine.broker_adapters.contracts`.
Slice 2 adds the deterministic offline mock implementation:
:mod:`engine.broker_adapters.mock_broker`.
Slice 3 adds the fail-closed normalization layer toward core concepts:
:mod:`engine.broker_adapters.normalization`.
Slice 4 adds mock-only disconnect/reconnect/reconciliation/retry contracts:
:mod:`engine.broker_adapters.mock_recovery`.
Slice 5 adds the minimal risk-gated integration/parity pipeline:
:mod:`engine.broker_adapters.mock_pipeline`.
"""

from __future__ import annotations

from engine.broker_adapters.contracts import (
    BROKER_ADAPTER_CONTRACT_VERSION,
    FILL_FRAGMENT_SCHEMA,
    ORDER_SNAPSHOT_SCHEMA,
    STATUS_OBSERVATION_SCHEMA,
    BrokerAdapter,
    BrokerAdapterError,
    BrokerAdapterObservation,
    BrokerAdapterOrderSnapshot,
    BrokerAdapterOrderStatus,
    BrokerAdapterUnavailableError,
    BrokerCancelResult,
    BrokerConnectionState,
    BrokerFillFragment,
    BrokerObservationCallback,
    BrokerOrderRecord,
    BrokerStatusObservation,
    BrokerSubmissionResult,
    BrokerTerminalEvent,
    broker_execution_side,
    broker_order_identity,
)
from engine.broker_adapters.mock_broker import (
    MOCK_BROKER_ADAPTER_VERSION,
    MockBrokerAdapter,
    MockOrderView,
    summarize_fragments,
)
from engine.broker_adapters.normalization import (
    BRIDGE_REJECTION_SCHEMA,
    NORMALIZATION_VERSION,
    UNSUPPORTED_PARTIAL_FILL_TOKEN,
    UNSUPPORTED_PARTIAL_SEQUENCE_TOKEN,
    BridgeRejectionEvidence,
    FragmentAggregate,
    NormalizedOutcome,
    NormalizedOutcomeKind,
    build_fragment_aggregate,
    evaluate_core_projection,
    map_raw_status,
    reject_partial_fragment_at_bridge,
)
from engine.broker_adapters.mock_recovery import (
    MOCK_RECONCILIATION_VERSION,
    ExpectedAdapterOrderState,
    FailureClassification,
    ReconciliationDiscrepancy,
    ReconciliationResult,
    ReconciliationVerdict,
    RetryAction,
    RetryDecision,
    SubmissionRetrySupervisor,
    reconcile as reconcile_adapter_state,
)
from engine.broker_adapters.mock_pipeline import (
    MOCK_PIPELINE_VERSION,
    PARITY_SLIPPAGE_MODEL_ID,
    PipelineFullFillProjection,
    PipelineSubmissionOutcome,
    PipelineSubmissionOutcomeKind,
    RiskGatedMockPipeline,
)

__all__ = [
    "BRIDGE_REJECTION_SCHEMA",
    "BROKER_ADAPTER_CONTRACT_VERSION",
    "ExpectedAdapterOrderState",
    "FILL_FRAGMENT_SCHEMA",
    "FailureClassification",
    "MOCK_BROKER_ADAPTER_VERSION",
    "MOCK_PIPELINE_VERSION",
    "MOCK_RECONCILIATION_VERSION",
    "NORMALIZATION_VERSION",
    "ORDER_SNAPSHOT_SCHEMA",
    "STATUS_OBSERVATION_SCHEMA",
    "UNSUPPORTED_PARTIAL_FILL_TOKEN",
    "UNSUPPORTED_PARTIAL_SEQUENCE_TOKEN",
    "BridgeRejectionEvidence",
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
    "FragmentAggregate",
    "MockBrokerAdapter",
    "MockOrderView",
    "NormalizedOutcome",
    "NormalizedOutcomeKind",
    "PARITY_SLIPPAGE_MODEL_ID",
    "PipelineFullFillProjection",
    "PipelineSubmissionOutcome",
    "PipelineSubmissionOutcomeKind",
    "ReconciliationDiscrepancy",
    "ReconciliationResult",
    "ReconciliationVerdict",
    "RetryAction",
    "RetryDecision",
    "RiskGatedMockPipeline",
    "SubmissionRetrySupervisor",
    "broker_execution_side",
    "broker_order_identity",
    "build_fragment_aggregate",
    "evaluate_core_projection",
    "map_raw_status",
    "reconcile_adapter_state",
    "reject_partial_fragment_at_bridge",
    "summarize_fragments",
]
