from datetime import datetime, timezone
import pytest

from dashboard.backend.product_ops_v2.contracts import PrivacyDataClass, PrivacyOperation, PrivacyPolicy
from dashboard.backend.product_ops_v2.privacy_policy import PrivacyPolicyRegistry, PrivacyPolicyError
from dashboard.backend.product_ops_v2.consent import ConsentPolicy, ConsentAction, ConsentLedger

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)

def policy(**kw):
    base = dict(policy_id='account-core', version='1.0.0', data_class=PrivacyDataClass.ACCOUNT_IDENTITY, purpose='account-security', allowed_operations=(PrivacyOperation.READ, PrivacyOperation.STORE), storage_boundary='CENTRAL_ACCOUNT', retention_policy_ref='ret-1', processor_scope=(), transfer_policy_ref=None, audit_required=True, effective_at=NOW, review_at=datetime(2027,1,1,tzinfo=timezone.utc))
    base.update(kw); return PrivacyPolicy(**base)

def test_policy_registry_fails_closed_for_missing_stale_and_unlisted_operation():
    reg = PrivacyPolicyRegistry((policy(),))
    assert reg.resolve(PrivacyDataClass.ACCOUNT_IDENTITY, PrivacyOperation.READ, NOW).allowed
    assert not reg.resolve(PrivacyDataClass.UNKNOWN, PrivacyOperation.READ, NOW).allowed
    assert not reg.resolve(PrivacyDataClass.ACCOUNT_IDENTITY, PrivacyOperation.EXPORT, NOW).allowed
    assert not reg.resolve(PrivacyDataClass.ACCOUNT_IDENTITY, PrivacyOperation.READ, datetime(2028,1,1,tzinfo=timezone.utc)).allowed

def test_consent_is_versioned_append_only_and_purpose_expansion_needs_new_version():
    ledger = ConsentLedger()
    cp = ConsentPolicy('privacy-notice','1.0.0','a'*64,'en-IN',('account-security',),(PrivacyDataClass.ACCOUNT_IDENTITY,),NOW,'WITHDRAW_RECONSENT','LEGAL-REVIEW-PENDING')
    rec = ledger.record('user-1', cp, ConsentAction.GRANT, NOW, audit_ref='audit-1')
    assert rec.policy_version == '1.0.0' and rec.document_fingerprint == 'a'*64
    with pytest.raises(ValueError): ledger.record('user-1', ConsentPolicy('privacy-notice','1.0.0','b'*64,'en-IN',('account-security','marketing'),(PrivacyDataClass.ACCOUNT_IDENTITY,),NOW,'WITHDRAW_RECONSENT','LEGAL-REVIEW-PENDING'), ConsentAction.GRANT, NOW, audit_ref='audit-2')
