from __future__ import annotations
from datetime import datetime
from .contracts import PrivacyDataClass, PrivacyOperation, PrivacyPolicy, PrivacyPolicyDecision


class PrivacyPolicyError(ValueError):
    pass


class PrivacyPolicyRegistry:
    def __init__(self, policies: tuple[PrivacyPolicy, ...] = ()):
        self._policies = {}
        for policy in policies:
            key = (policy.data_class, policy.policy_id, policy.version)
            if key in self._policies:
                raise PrivacyPolicyError("duplicate privacy policy")
            self._policies[key] = policy

    def resolve(
        self,
        data_class: PrivacyDataClass,
        operation: PrivacyOperation,
        now: datetime,
        *,
        purpose: str | None = None,
        processor: str | None = None,
        transfer_evidence_ref: str | None = None,
        external_egress: bool = False,
    ) -> PrivacyPolicyDecision:
        if data_class is PrivacyDataClass.UNKNOWN:
            return PrivacyPolicyDecision(False, ("UNKNOWN_DATA_CLASS",), None)

        candidates = [
            policy
            for policy in self._policies.values()
            if policy.data_class is data_class
            and (purpose is None or policy.purpose == purpose)
            and policy.effective_at <= now
            and (policy.review_at is None or now <= policy.review_at)
        ]
        if not candidates:
            return PrivacyPolicyDecision(False, ("MISSING_OR_STALE_POLICY",), None)
        if len(candidates) != 1:
            return PrivacyPolicyDecision(False, ("AMBIGUOUS_POLICY",), None)

        policy = candidates[0]
        reasons: list[str] = []
        if operation not in policy.allowed_operations:
            reasons.append("OPERATION_NOT_PERMITTED")
        if processor is not None and processor not in policy.processor_scope:
            reasons.append("PROCESSOR_NOT_PERMITTED")

        requires_transfer_evidence = operation is PrivacyOperation.PROCESSOR_USE or external_egress
        if operation is PrivacyOperation.PROCESSOR_USE and not processor:
            reasons.append("PROCESSOR_REQUIRED")
        if requires_transfer_evidence:
            if not policy.transfer_policy_ref:
                reasons.append("TRANSFER_POLICY_UNRESOLVED")
            elif not transfer_evidence_ref:
                reasons.append("TRANSFER_EVIDENCE_MISSING")

        return PrivacyPolicyDecision(
            not reasons,
            tuple(reasons),
            f"{policy.policy_id}@{policy.version}",
        )
