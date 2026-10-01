from datetime import datetime, timedelta, timezone

import pytest

from dashboard.backend.product_ops_v2.retention import (
    ErasureEngine,
    ErasureOutcome,
    MinimalTombstone,
    RetentionPolicy,
)

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def policy(data_class="ACCOUNT_IDENTITY", **overrides):
    values = dict(
        policy_id="ret-account",
        version="1.0.0",
        data_class=data_class,
        trigger="ACCOUNT_CLOSED",
        duration_rule_ref="retention-rule/account/v1",
        deletion_action="DELETE",
        legal_hold_ref=None,
        safety_retention_ref=None,
        backup_propagation=True,
        legal_hold_release_at=None,
        safety_retention_release_at=None,
    )
    values.update(overrides)
    return RetentionPolicy(**values)


def test_missing_or_unresolved_retention_policy_never_authorizes_deletion():
    decisions = ErasureEngine().decide((), now=NOW, required_classes=("ACCOUNT_IDENTITY",))
    assert decisions["ACCOUNT_IDENTITY"].outcome is ErasureOutcome.REJECT_POLICY_UNRESOLVED

    unresolved = ErasureEngine().decide(
        (policy(duration_rule_ref=None),),
        now=NOW,
        required_classes=("ACCOUNT_IDENTITY",),
    )
    assert unresolved["ACCOUNT_IDENTITY"].outcome is ErasureOutcome.REJECT_POLICY_UNRESOLVED


def test_legal_hold_is_scoped_and_expired_hold_resumes_delete_eligibility():
    active_hold = policy(legal_hold_ref="hold-1", legal_hold_release_at=NOW + timedelta(days=1))
    unrelated = policy("CONSENT_EVIDENCE", policy_id="ret-consent")
    decisions = ErasureEngine().decide(
        (active_hold, unrelated),
        now=NOW,
        required_classes=("ACCOUNT_IDENTITY", "CONSENT_EVIDENCE"),
    )
    assert decisions["ACCOUNT_IDENTITY"].outcome is ErasureOutcome.RETAIN_LEGAL_HOLD
    assert decisions["CONSENT_EVIDENCE"].outcome is ErasureOutcome.DELETE_ALLOWED

    expired = policy(legal_hold_ref="hold-1", legal_hold_release_at=NOW - timedelta(seconds=1))
    released = ErasureEngine().decide((expired,), now=NOW, required_classes=("ACCOUNT_IDENTITY",))
    assert released["ACCOUNT_IDENTITY"].outcome is ErasureOutcome.DELETE_ALLOWED


def test_safety_retention_is_scoped_and_release_aware():
    held = policy(
        "SESSION_SECURITY",
        policy_id="ret-session",
        safety_retention_ref="recovery-safety-1",
        safety_retention_release_at=NOW + timedelta(hours=2),
    )
    decisions = ErasureEngine().decide((held,), now=NOW, required_classes=("SESSION_SECURITY",))
    assert decisions["SESSION_SECURITY"].outcome is ErasureOutcome.RETAIN_SAFETY

    released = policy(
        "SESSION_SECURITY",
        policy_id="ret-session",
        safety_retention_ref="recovery-safety-1",
        safety_retention_release_at=NOW - timedelta(seconds=1),
    )
    assert ErasureEngine().decide((released,), now=NOW, required_classes=("SESSION_SECURITY",))["SESSION_SECURITY"].outcome is ErasureOutcome.DELETE_ALLOWED


def test_backup_propagation_failure_cannot_be_reported_as_completed():
    engine = ErasureEngine()
    decision = engine.decide((policy(),), now=NOW, required_classes=("ACCOUNT_IDENTITY",))["ACCOUNT_IDENTITY"]
    with pytest.raises(RuntimeError, match="BACKUP_DELETION_PROPAGATION_INCOMPLETE"):
        engine.complete(decision, backup_propagated=False)
    assert engine.complete(decision, backup_propagated=True) == "ERASURE_COMPLETED"


def test_minimal_tombstone_has_no_original_payload_field():
    tombstone = MinimalTombstone("a" * 64, "ACCOUNT_IDENTITY", "ret-account@1.0.0", NOW)
    assert not hasattr(tombstone, "payload")
    assert not hasattr(tombstone, "personal_data")
