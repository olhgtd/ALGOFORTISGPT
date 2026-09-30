"""AlgoFortis V2 central Risk Gate approval authority.

The gate is deliberately broker-neutral.  It can approve/reject an immutable
OrderIntent and mint an ApprovedOrder capability only after required audit
evidence is written successfully.  It never calls a broker and does not enable
live mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Protocol

from engine.core.numeric import as_decimal
from engine.core.runtime import Clock, IdGenerator
from engine.orders.contracts_v2 import (
    ApprovedOrder,
    OrderIntent,
    RiskDecision,
    RiskDecisionKind,
    client_order_id_for_intent,
    _mint_approved_order,
)
from engine.risk.limits import ResolvedHardLimits


class RiskApprovalError(RuntimeError):
    """Raised when the gate cannot safely establish approval/rejection evidence."""


class RiskEvaluator(Protocol):
    def evaluate(self, intent: OrderIntent) -> "RiskEvaluation": ...


class RiskAuditSink(Protocol):
    def write(self, event_type: str, payload: dict[str, object]) -> None: ...


class EntryPolicy(Protocol):
    @property
    def entries_allowed(self) -> bool: ...


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _text(value, field_name)


def _reasons(values: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(values, tuple) or not values:
        raise ValueError("reasons must be a non-empty tuple")
    return tuple(_text(value, "reason") for value in values)


@dataclass(frozen=True, slots=True)
class RiskEvaluation:
    """Broker-free adapter result consumed by RiskGateV2.

    Optional fast-path evidence is additive so legacy evaluators remain valid.
    """

    decision: RiskDecisionKind
    reasons: tuple[str, ...]
    risk_rule_version: str
    limits_snapshot_id: str
    approved_qty: Decimal | None = None
    risk_snapshot_id: str | None = None
    market_sequence_ref: str | None = None
    latency_policy_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, RiskDecisionKind):
            raise TypeError("decision must be a RiskDecisionKind")
        object.__setattr__(self, "risk_rule_version", _text(self.risk_rule_version, "risk_rule_version"))
        object.__setattr__(self, "limits_snapshot_id", _text(self.limits_snapshot_id, "limits_snapshot_id"))
        object.__setattr__(self, "risk_snapshot_id", _optional_text(self.risk_snapshot_id, "risk_snapshot_id"))
        object.__setattr__(self, "market_sequence_ref", _optional_text(self.market_sequence_ref, "market_sequence_ref"))
        object.__setattr__(self, "latency_policy_ref", _optional_text(self.latency_policy_ref, "latency_policy_ref"))

        if self.decision is RiskDecisionKind.APPROVED:
            if self.reasons:
                raise ValueError("approved evaluation excludes reasons")
            if self.approved_qty is None:
                raise ValueError("approved evaluation requires approved_qty")
            quantity = as_decimal(self.approved_qty, "approved_qty")
            if quantity <= 0:
                raise ValueError("approved_qty must be positive")
            object.__setattr__(self, "approved_qty", quantity)
        elif self.decision is RiskDecisionKind.REJECTED:
            object.__setattr__(self, "reasons", _reasons(self.reasons))
            if self.approved_qty is not None:
                raise ValueError("rejected evaluation excludes approved_qty")
        else:
            object.__setattr__(self, "reasons", _reasons(self.reasons))
            if self.approved_qty is None:
                raise ValueError("reduced evaluation requires approved_qty")
            quantity = as_decimal(self.approved_qty, "approved_qty")
            if quantity <= 0:
                raise ValueError("approved_qty must be positive")
            object.__setattr__(self, "approved_qty", quantity)

    @classmethod
    def approved(
        cls,
        *,
        approved_qty: Decimal | int | str,
        risk_rule_version: str,
        limits_snapshot_id: str,
        risk_snapshot_id: str | None = None,
        market_sequence_ref: str | None = None,
        latency_policy_ref: str | None = None,
    ) -> "RiskEvaluation":
        return cls(
            RiskDecisionKind.APPROVED,
            (),
            risk_rule_version,
            limits_snapshot_id,
            as_decimal(approved_qty, "approved_qty"),
            risk_snapshot_id,
            market_sequence_ref,
            latency_policy_ref,
        )

    @classmethod
    def rejected(
        cls,
        reason: str,
        *,
        risk_rule_version: str,
        limits_snapshot_id: str,
        risk_snapshot_id: str | None = None,
        market_sequence_ref: str | None = None,
        latency_policy_ref: str | None = None,
    ) -> "RiskEvaluation":
        return cls(
            RiskDecisionKind.REJECTED,
            (_text(reason, "reason"),),
            risk_rule_version,
            limits_snapshot_id,
            None,
            risk_snapshot_id,
            market_sequence_ref,
            latency_policy_ref,
        )


@dataclass(frozen=True, slots=True)
class RiskRejection:
    intent_id: str
    reasons: tuple[str, ...]
    risk_rule_version: str | None = None
    limits_snapshot_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "intent_id", _text(self.intent_id, "intent_id"))
        object.__setattr__(self, "reasons", _reasons(self.reasons))
        if self.risk_rule_version is not None:
            object.__setattr__(self, "risk_rule_version", _text(self.risk_rule_version, "risk_rule_version"))
        if self.limits_snapshot_id is not None:
            object.__setattr__(self, "limits_snapshot_id", _text(self.limits_snapshot_id, "limits_snapshot_id"))


class RiskGateV2:
    """The sole Phase-2 authority able to mint ApprovedOrder capabilities."""

    def __init__(
        self,
        *,
        evaluator: RiskEvaluator,
        clock: Clock,
        id_generator: IdGenerator,
        audit_sink: RiskAuditSink,
        hard_limits: ResolvedHardLimits,
        entry_policy: EntryPolicy | None = None,
    ) -> None:
        if not callable(getattr(evaluator, "evaluate", None)):
            raise TypeError("evaluator must provide evaluate(intent)")
        if not callable(getattr(clock, "now_utc", None)):
            raise TypeError("clock must provide now_utc()")
        if not callable(getattr(id_generator, "new_id", None)):
            raise TypeError("id_generator must provide new_id(kind)")
        if not callable(getattr(audit_sink, "write", None)):
            raise TypeError("audit_sink must provide write(event_type, payload)")
        if not isinstance(hard_limits, ResolvedHardLimits):
            raise TypeError("hard_limits must be ResolvedHardLimits")
        if entry_policy is not None:
            try:
                allowed = entry_policy.entries_allowed
            except Exception as error:
                raise TypeError("entry_policy must expose entries_allowed") from error
            if not isinstance(allowed, bool):
                raise TypeError("entry_policy.entries_allowed must be bool")
        self._evaluator = evaluator
        self._clock = clock
        self._id_generator = id_generator
        self._audit_sink = audit_sink
        self._hard_limits = hard_limits
        self._entry_policy = entry_policy

    def evaluate_entry(self, intent: OrderIntent) -> ApprovedOrder | RiskRejection:
        if not isinstance(intent, OrderIntent):
            raise TypeError("intent must be an OrderIntent")

        now = self._clock.now_utc()
        if now.tzinfo is None or now.utcoffset() is None:
            raise RiskApprovalError("clock returned a non-timezone-aware value")
        if now >= intent.valid_until:
            return self._reject(intent, ("intent_expired",), limits_snapshot_id=self._hard_limits.snapshot_id)

        if self._entry_policy is not None:
            try:
                entries_allowed = self._entry_policy.entries_allowed
            except Exception as error:
                raise RiskApprovalError("entry policy unavailable; risk action blocked") from error
            if entries_allowed is not True:
                return self._reject(intent, ("entries_halted",), limits_snapshot_id=self._hard_limits.snapshot_id)

        if intent.instrument_ref.segment == "options" and intent.side != "BUY":
            return self._reject(intent, ("options_buy_only",), limits_snapshot_id=self._hard_limits.snapshot_id)

        max_order_qty = self._hard_limits.values.get("max_order_qty")
        if max_order_qty is not None and intent.qty > max_order_qty:
            return self._reject(intent, ("max_order_qty",), limits_snapshot_id=self._hard_limits.snapshot_id)

        try:
            evaluation = self._evaluator.evaluate(intent)
        except Exception as error:
            raise RiskApprovalError("risk evaluation failed closed") from error
        if not isinstance(evaluation, RiskEvaluation):
            raise RiskApprovalError("risk evaluator returned invalid evidence")

        if evaluation.limits_snapshot_id != self._hard_limits.snapshot_id:
            return self._reject(
                intent,
                ("limits_snapshot_mismatch",),
                risk_rule_version=evaluation.risk_rule_version,
                limits_snapshot_id=self._hard_limits.snapshot_id,
            )
        if evaluation.decision is RiskDecisionKind.REJECTED:
            return self._reject(
                intent,
                evaluation.reasons,
                risk_rule_version=evaluation.risk_rule_version,
                limits_snapshot_id=self._hard_limits.snapshot_id,
            )
        if evaluation.decision is RiskDecisionKind.REDUCED:
            return self._reject(
                intent,
                ("reduced_order_requires_explicit_contract",),
                risk_rule_version=evaluation.risk_rule_version,
                limits_snapshot_id=self._hard_limits.snapshot_id,
            )
        if evaluation.approved_qty != intent.qty:
            return self._reject(
                intent,
                ("risk_quantity_mismatch",),
                risk_rule_version=evaluation.risk_rule_version,
                limits_snapshot_id=self._hard_limits.snapshot_id,
            )

        approval_token = self._id_generator.new_id("risk_approval")
        risk_decision = RiskDecision(
            intent_id=intent.intent_id,
            decision=RiskDecisionKind.APPROVED,
            reasons=(),
            risk_rule_version=evaluation.risk_rule_version,
            limits_snapshot_id=self._hard_limits.snapshot_id,
            approved_qty=evaluation.approved_qty,
            approval_token=approval_token,
        )
        decision_ref = risk_decision.reference
        client_order_id = client_order_id_for_intent(intent.intent_id)
        payload: dict[str, object] = {
            "client_order_id": client_order_id,
            "intent_id": intent.intent_id,
            "risk_decision_ref": decision_ref,
            "risk_rule_version": evaluation.risk_rule_version,
            "limits_snapshot_id": self._hard_limits.snapshot_id,
        }
        if evaluation.risk_snapshot_id is not None:
            payload["risk_snapshot_id"] = evaluation.risk_snapshot_id
        if evaluation.market_sequence_ref is not None:
            payload["market_sequence_ref"] = evaluation.market_sequence_ref
        if evaluation.latency_policy_ref is not None:
            payload["latency_policy_ref"] = evaluation.latency_policy_ref
        self._write_audit("RISK_APPROVAL_GRANTED", payload)

        return _mint_approved_order(
            client_order_id=client_order_id,
            intent=intent,
            risk_decision_ref=decision_ref,
        )

    def _reject(
        self,
        intent: OrderIntent,
        reasons: tuple[str, ...],
        *,
        risk_rule_version: str | None = None,
        limits_snapshot_id: str | None = None,
    ) -> RiskRejection:
        normalized = _reasons(reasons)
        payload: dict[str, object] = {"intent_id": intent.intent_id, "reasons": normalized}
        if risk_rule_version is not None:
            payload["risk_rule_version"] = risk_rule_version
        if limits_snapshot_id is not None:
            payload["limits_snapshot_id"] = limits_snapshot_id
        self._write_audit("RISK_APPROVAL_REJECTED", payload)
        return RiskRejection(intent.intent_id, normalized, risk_rule_version, limits_snapshot_id)

    def _write_audit(self, event_type: str, payload: Mapping[str, object]) -> None:
        try:
            self._audit_sink.write(event_type, dict(payload))
        except Exception as error:
            raise RiskApprovalError("audit write failed; risk action blocked") from error


__all__ = ["RiskApprovalError", "RiskEvaluation", "RiskRejection", "RiskGateV2"]
