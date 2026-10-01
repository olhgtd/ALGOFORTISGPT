from datetime import datetime, timezone

from dashboard.backend.product_ops_v2.contracts import PrivacyDataClass, PrivacyOperation, PrivacyPolicy
from dashboard.backend.product_ops_v2.privacy_policy import PrivacyPolicyRegistry

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def make_policy(**overrides):
    values = dict(
        policy_id="account-core",
        version="1.0.0",
        data_class=PrivacyDataClass.ACCOUNT_IDENTITY,
        purpose="account-security",
        allowed_operations=(PrivacyOperation.READ, PrivacyOperation.EXPORT, PrivacyOperation.PROCESSOR_USE),
        storage_boundary="CENTRAL_ACCOUNT",
        retention_policy_ref="retention/account-core/v1",
        processor_scope=("approved-processor",),
        transfer_policy_ref="transfer/account-core/v1",
        audit_required=True,
        effective_at=NOW,
        review_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
    )
    values.update(overrides)
    return PrivacyPolicy(**values)


def test_external_processor_use_requires_positive_transfer_policy_and_evidence():
    registry = PrivacyPolicyRegistry((make_policy(),))
    missing_evidence = registry.resolve(
        PrivacyDataClass.ACCOUNT_IDENTITY,
        PrivacyOperation.PROCESSOR_USE,
        NOW,
        purpose="account-security",
        processor="approved-processor",
    )
    assert not missing_evidence.allowed
    assert "TRANSFER_EVIDENCE_MISSING" in missing_evidence.reasons

    allowed = registry.resolve(
        PrivacyDataClass.ACCOUNT_IDENTITY,
        PrivacyOperation.PROCESSOR_USE,
        NOW,
        purpose="account-security",
        processor="approved-processor",
        transfer_evidence_ref="legal-transfer-review-2026-10-01",
    )
    assert allowed.allowed


def test_external_egress_fails_closed_when_transfer_policy_is_unresolved():
    registry = PrivacyPolicyRegistry((make_policy(transfer_policy_ref=None),))
    decision = registry.resolve(
        PrivacyDataClass.ACCOUNT_IDENTITY,
        PrivacyOperation.EXPORT,
        NOW,
        purpose="account-security",
        external_egress=True,
        transfer_evidence_ref="cannot-authorize-without-policy",
    )
    assert not decision.allowed
    assert "TRANSFER_POLICY_UNRESOLVED" in decision.reasons


def test_normal_data_principal_export_does_not_invent_cloud_egress_requirement():
    registry = PrivacyPolicyRegistry((make_policy(transfer_policy_ref=None),))
    decision = registry.resolve(
        PrivacyDataClass.ACCOUNT_IDENTITY,
        PrivacyOperation.EXPORT,
        NOW,
        purpose="account-security",
        external_egress=False,
    )
    assert decision.allowed


def test_unapproved_processor_and_ambiguous_policy_fail_closed():
    registry = PrivacyPolicyRegistry((make_policy(),))
    denied = registry.resolve(
        PrivacyDataClass.ACCOUNT_IDENTITY,
        PrivacyOperation.PROCESSOR_USE,
        NOW,
        purpose="account-security",
        processor="unknown-processor",
        transfer_evidence_ref="review-1",
    )
    assert not denied.allowed
    assert "PROCESSOR_NOT_PERMITTED" in denied.reasons

    ambiguous = PrivacyPolicyRegistry((make_policy(version="1.0.0"), make_policy(version="1.1.0")))
    result = ambiguous.resolve(
        PrivacyDataClass.ACCOUNT_IDENTITY,
        PrivacyOperation.READ,
        NOW,
        purpose="account-security",
    )
    assert not result.allowed
    assert result.reasons == ("AMBIGUOUS_POLICY",)
