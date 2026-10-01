"""Dormant V2 Live execution coordinator for Package-1 qualification.

The coordinator owns orchestration only. It requires a genuine RiskGate
ApprovedOrder, current ACTIVE Live state, a release-gate authorization, and a
trusted execution-capacity reservation before a broker mutation call. Package-1
ships only a closed production release gate and the existing BoundBrokerPort
still hard-blocks Live mutation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from engine.live.mutation_release_gate_v2 import LiveMutationReleaseGate
from engine.live.state_machine_v2 import LiveState, LiveStateMachine
from engine.orders.contracts_v2 import ApprovedOrder, RunMode
from engine.orders.lifecycle_v2 import OrderExecutionLifecycle, OrderExecutionState
from engine.persistence.live_execution_store_v2 import (
    LiveExecutionDuplicateError,
    LiveExecutionRecord,
    LiveExecutionStoreV2,
)
from engine.reproducibility.codec import CanonicalCodec


class LiveExecutionCoordinatorError(RuntimeError):
    """Raised when a Live submission cannot safely enter the broker boundary."""


class LiveExecutionInDoubt(LiveExecutionCoordinatorError):
    """Raised after the broker call boundary when acknowledgement is uncertain."""


class LiveExecutionAuditError(LiveExecutionCoordinatorError):
    """Raised when mandatory trading-critical audit persistence fails."""


class _LiveBrokerMutationPort(Protocol):
    def place(self, order: ApprovedOrder) -> object: ...


class _LiveExecutionCapacityGate(Protocol):
    def reserve(self, order: ApprovedOrder, *, now: datetime) -> str: ...
    def release(self, client_order_id: str, *, now: datetime, reason: str) -> bool: ...


class _AuditSink(Protocol):
    def write(self, event_type: str, payload: dict[str, object]) -> None: ...


class _Clock(Protocol):
    def now_utc(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class LiveBrokerAcknowledgementV2:
    client_order_id: str
    broker_order_identity: str

    def __post_init__(self) -> None:
        for field_name in ("client_order_id", "broker_order_identity"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
            object.__setattr__(self, field_name, value.strip())


class LiveExecutionCoordinatorV2:
    """Single dormant orchestration seam from ApprovedOrder to broker mutation."""

    def __init__(
        self,
        *,
        broker_port: _LiveBrokerMutationPort,
        journal: LiveExecutionStoreV2,
        release_gate: LiveMutationReleaseGate,
        capacity_gate: _LiveExecutionCapacityGate,
        state_machine: LiveStateMachine,
        audit_sink: _AuditSink,
        clock: _Clock,
    ) -> None:
        if not callable(getattr(broker_port, "place", None)):
            raise TypeError("broker_port must provide place(order)")
        if not isinstance(journal, LiveExecutionStoreV2):
            raise TypeError("journal must be LiveExecutionStoreV2")
        if not callable(getattr(release_gate, "authorize", None)):
            raise TypeError("release_gate must provide authorize(order, live_state)")
        if not callable(getattr(capacity_gate, "reserve", None)) or not callable(
            getattr(capacity_gate, "release", None)
        ):
            raise TypeError("capacity_gate must provide reserve() and release()")
        if not isinstance(state_machine, LiveStateMachine):
            raise TypeError("state_machine must be LiveStateMachine")
        if not callable(getattr(audit_sink, "write", None)):
            raise TypeError("audit_sink must provide write(event_type, payload)")
        if not callable(getattr(clock, "now_utc", None)):
            raise TypeError("clock must provide now_utc()")
        self._broker_port = broker_port
        self._journal = journal
        self._release_gate = release_gate
        self._capacity_gate = capacity_gate
        self._state_machine = state_machine
        self._audit_sink = audit_sink
        self._clock = clock

    def submit(self, order: ApprovedOrder) -> LiveBrokerAcknowledgementV2:
        if not isinstance(order, ApprovedOrder):
            raise TypeError("order must be ApprovedOrder")
        if order.run_mode is not RunMode.LIVE:
            raise LiveExecutionCoordinatorError("Live execution requires RunMode.LIVE ApprovedOrder")

        now = self._now()
        if now >= order.expires_at:
            raise LiveExecutionCoordinatorError("ApprovedOrder expired before Live submission")
        if self._state_machine.state is not LiveState.ACTIVE:
            raise LiveExecutionCoordinatorError("LiveState.ACTIVE is required for submission")
        if self._journal.get(order.client_order_id) is not None:
            raise LiveExecutionCoordinatorError(
                f"duplicate client_order_id already has Live journal evidence: {order.client_order_id}"
            )

        release_ref = self._release_gate.authorize(
            order=order,
            live_state=self._state_machine.state,
        )
        release_ref = self._required_ref(release_ref, "release authorization reference")

        capacity_ref = self._capacity_gate.reserve(order, now=now)
        capacity_ref = self._required_ref(capacity_ref, "capacity evidence reference")

        attempt_id = self._attempt_id(order, now)
        adapter_id = getattr(self._broker_port, "adapter_id", None)
        if adapter_id is not None and (not isinstance(adapter_id, str) or not adapter_id.strip()):
            raise LiveExecutionCoordinatorError("broker_port adapter_id must be non-empty when provided")
        record = LiveExecutionRecord(
            client_order_id=order.client_order_id,
            approved_order_ref=order.risk_decision_ref,
            run_mode=RunMode.LIVE,
            lifecycle_state=OrderExecutionState.RISK_APPROVED,
            broker_order_identity=None,
            submission_attempt_id=attempt_id,
            created_at_utc=now,
            updated_at_utc=now,
            is_uncertain=False,
            adapter_id=(adapter_id.strip() if isinstance(adapter_id, str) else None),
            policy_ref=release_ref,
            audit_ref=None,
        )
        try:
            self._journal.reserve(record)
        except LiveExecutionDuplicateError as exc:
            # A concurrent identical path may already own the idempotent capacity
            # reservation. Never release it from the losing duplicate submitter.
            raise LiveExecutionCoordinatorError(
                f"duplicate client_order_id raced Live journal reservation: {order.client_order_id}"
            ) from exc
        except Exception:
            self._release_capacity_best_effort(order.client_order_id, now, "pre_submit_journal_failed")
            raise

        lifecycle = OrderExecutionLifecycle(order, clock=self._clock)
        lifecycle = lifecycle.transition_to(
            OrderExecutionState.SUBMITTING,
            reason="live_coordinator_prepare",
        )
        self._journal.transition(
            order.client_order_id,
            lifecycle_state=lifecycle.state,
            is_uncertain=False,
        )

        try:
            self._write_audit(
                "LIVE_SUBMISSION_PREPARED",
                {
                    "client_order_id": order.client_order_id,
                    "intent_id": order.intent_id,
                    "risk_decision_ref": order.risk_decision_ref,
                    "release_authorization_ref": release_ref,
                    "capacity_evidence_ref": capacity_ref,
                    "submission_attempt_id": attempt_id,
                    "lifecycle_state": lifecycle.state.value,
                },
            )
        except LiveExecutionAuditError:
            self._release_capacity_best_effort(
                order.client_order_id,
                self._now(),
                "pre_submit_audit_failed",
            )
            raise

        lifecycle = lifecycle.transition_to(
            OrderExecutionState.SENT_UNACKED,
            reason="broker_call_boundary_entered",
        )
        self._journal.transition(
            order.client_order_id,
            lifecycle_state=lifecycle.state,
            is_uncertain=False,
        )

        try:
            raw_ack = self._broker_port.place(order)
        except Exception as exc:
            self._mark_in_doubt(order, lifecycle, reason="broker_call_exception")
            raise LiveExecutionInDoubt(
                f"Live broker acknowledgement is uncertain for {order.client_order_id}"
            ) from exc

        if not isinstance(raw_ack, LiveBrokerAcknowledgementV2):
            self._mark_in_doubt(order, lifecycle, reason="invalid_broker_acknowledgement")
            raise LiveExecutionInDoubt("broker acknowledgement is invalid or incomplete")
        if raw_ack.client_order_id != order.client_order_id:
            self._mark_in_doubt(order, lifecycle, reason="broker_ack_identity_mismatch")
            raise LiveExecutionInDoubt("broker acknowledgement client identity mismatch")

        lifecycle = lifecycle.transition_to(
            OrderExecutionState.ACKED,
            reason="broker_acknowledged",
        )
        self._journal.transition(
            order.client_order_id,
            lifecycle_state=lifecycle.state,
            broker_order_identity=raw_ack.broker_order_identity,
            is_uncertain=False,
        )

        self._write_audit(
            "LIVE_SUBMISSION_ACKED",
            {
                "client_order_id": order.client_order_id,
                "intent_id": order.intent_id,
                "risk_decision_ref": order.risk_decision_ref,
                "broker_order_identity": raw_ack.broker_order_identity,
                "submission_attempt_id": attempt_id,
                "lifecycle_state": lifecycle.state.value,
            },
        )
        return raw_ack

    def _mark_in_doubt(
        self,
        order: ApprovedOrder,
        lifecycle: OrderExecutionLifecycle,
        *,
        reason: str,
    ) -> None:
        uncertain = lifecycle.mark_in_doubt(reason=reason)
        self._journal.transition(
            order.client_order_id,
            lifecycle_state=uncertain.state,
            is_uncertain=True,
        )
        try:
            self._write_audit(
                "LIVE_SUBMISSION_IN_DOUBT",
                {
                    "client_order_id": order.client_order_id,
                    "intent_id": order.intent_id,
                    "risk_decision_ref": order.risk_decision_ref,
                    "lifecycle_state": uncertain.state.value,
                    "reason": reason,
                },
            )
        except LiveExecutionAuditError:
            # Broker uncertainty already exists. Preserve IN_DOUBT and never mask
            # it with a retry or capacity release.
            return

    def _release_capacity_best_effort(
        self,
        client_order_id: str,
        now: datetime,
        reason: str,
    ) -> None:
        try:
            self._capacity_gate.release(
                client_order_id,
                now=now,
                reason=reason,
            )
        except Exception:
            # Failure to release is conservative: capacity remains reserved and
            # prevents oversubscription until explicit recovery/reconciliation.
            return

    def _write_audit(self, event_type: str, payload: dict[str, object]) -> None:
        try:
            self._audit_sink.write(event_type, dict(payload))
        except Exception as exc:
            raise LiveExecutionAuditError(f"mandatory Live audit failed: {event_type}") from exc

    def _now(self) -> datetime:
        value = self._clock.now_utc()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise LiveExecutionCoordinatorError("clock returned non-timezone-aware datetime")
        return value

    @staticmethod
    def _required_ref(value: object, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise LiveExecutionCoordinatorError(f"{field} must be non-empty")
        return value.strip()

    @staticmethod
    def _attempt_id(order: ApprovedOrder, now: datetime) -> str:
        digest = CanonicalCodec.fingerprint(
            "algofortis-live-submission-attempt/v1",
            (
                ("client_order_id", order.client_order_id),
                ("risk_decision_ref", order.risk_decision_ref),
                ("timestamp", now),
            ),
        )
        return f"af2_live_attempt_{digest}"


__all__ = [
    "LiveBrokerAcknowledgementV2",
    "LiveExecutionAuditError",
    "LiveExecutionCoordinatorError",
    "LiveExecutionCoordinatorV2",
    "LiveExecutionInDoubt",
]
