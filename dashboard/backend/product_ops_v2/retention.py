from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ErasureOutcome(str, Enum):
    DELETE_ALLOWED = "DELETE_ALLOWED"
    RETAIN_LEGAL_HOLD = "RETAIN_LEGAL_HOLD"
    RETAIN_SAFETY = "RETAIN_SAFETY"
    REJECT_POLICY_UNRESOLVED = "REJECT_POLICY_UNRESOLVED"


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    policy_id: str
    version: str
    data_class: str
    trigger: str
    duration_rule_ref: str | None
    deletion_action: str
    legal_hold_ref: str | None
    safety_retention_ref: str | None
    backup_propagation: bool
    legal_hold_release_at: datetime | None = None
    safety_retention_release_at: datetime | None = None

    def __post_init__(self):
        for value in (self.legal_hold_release_at, self.safety_retention_release_at):
            if value is not None and value.tzinfo is None:
                raise ValueError("retention release timestamps must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ErasureDecision:
    outcome: ErasureOutcome
    reason_ref: str | None
    data_class: str
    backup_propagation_required: bool = False


class ErasureEngine:
    def decide(
        self,
        policies: tuple[RetentionPolicy, ...],
        *,
        now: datetime,
        required_classes: tuple[str, ...] = (),
    ) -> dict[str, ErasureDecision]:
        by_class: dict[str, list[RetentionPolicy]] = {}
        for policy in policies:
            by_class.setdefault(policy.data_class, []).append(policy)

        targets = tuple(dict.fromkeys(required_classes or tuple(by_class)))
        decisions: dict[str, ErasureDecision] = {}
        for data_class in targets:
            candidates = by_class.get(data_class, [])
            if len(candidates) != 1:
                decisions[data_class] = ErasureDecision(
                    ErasureOutcome.REJECT_POLICY_UNRESOLVED,
                    "MISSING_OR_AMBIGUOUS_RETENTION_POLICY",
                    data_class,
                )
                continue

            policy = candidates[0]
            if (
                not policy.policy_id.strip()
                or not policy.version.strip()
                or not policy.trigger.strip()
                or not policy.duration_rule_ref
                or policy.deletion_action not in {"DELETE", "ANONYMIZE"}
            ):
                decisions[data_class] = ErasureDecision(
                    ErasureOutcome.REJECT_POLICY_UNRESOLVED,
                    "RETENTION_POLICY_INCOMPLETE",
                    data_class,
                    policy.backup_propagation,
                )
                continue

            legal_hold_active = bool(policy.legal_hold_ref) and (
                policy.legal_hold_release_at is None or now < policy.legal_hold_release_at
            )
            safety_hold_active = bool(policy.safety_retention_ref) and (
                policy.safety_retention_release_at is None or now < policy.safety_retention_release_at
            )

            if legal_hold_active:
                decision = ErasureDecision(
                    ErasureOutcome.RETAIN_LEGAL_HOLD,
                    policy.legal_hold_ref,
                    data_class,
                    policy.backup_propagation,
                )
            elif safety_hold_active:
                decision = ErasureDecision(
                    ErasureOutcome.RETAIN_SAFETY,
                    policy.safety_retention_ref,
                    data_class,
                    policy.backup_propagation,
                )
            else:
                decision = ErasureDecision(
                    ErasureOutcome.DELETE_ALLOWED,
                    f"{policy.policy_id}@{policy.version}",
                    data_class,
                    policy.backup_propagation,
                )
            decisions[data_class] = decision
        return decisions

    def complete(self, decision: ErasureDecision, *, backup_propagated: bool) -> str:
        if decision.outcome is not ErasureOutcome.DELETE_ALLOWED:
            raise RuntimeError("ERASURE_NOT_AUTHORIZED")
        if decision.backup_propagation_required and not backup_propagated:
            raise RuntimeError("BACKUP_DELETION_PROPAGATION_INCOMPLETE")
        return "ERASURE_COMPLETED"


@dataclass(frozen=True, slots=True)
class MinimalTombstone:
    principal_fingerprint: str
    data_class: str
    deletion_policy_ref: str
    completed_at: datetime

    def __post_init__(self):
        if len(self.principal_fingerprint) != 64:
            raise ValueError("minimal principal fingerprint required")
