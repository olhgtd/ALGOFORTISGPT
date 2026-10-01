import pytest

from dashboard.backend.product_ops_v2.read_models import ProductOpsHealth, UserPrivacyReadModel
from dashboard.backend.product_ops_v2.service import ProductOpsService


def test_product_ops_service_exposes_read_models_only():
    service = ProductOpsService(repository=None)
    health = ProductOpsHealth(
        unresolved_incidents=0,
        alert_health="OK",
        privacy_requests=(),
        stale_policy_count=0,
        backup_status="PASS",
        restore_status="PASS",
        rollback_status="PASS",
        active_policy_versions=("privacy-notice/1.0.0",),
        runbook_status="PASS",
    )
    assert service.owner_health(health=health) is health
    forbidden = ("place_order", "modify_order", "cancel_order", "arm_live", "mint_approved_order")
    assert all(not hasattr(service, name) for name in forbidden)


def test_user_privacy_service_rejects_cross_user_reads():
    service = ProductOpsService(repository=None)
    model = UserPrivacyReadModel(
        notice_policy_ref="privacy-notice/1.0.0",
        notice_fingerprint="a" * 64,
        consent_state="GRANTED",
        request_statuses=(("ACCESS-1", "IN_PROGRESS"),),
        identity_authority="S2_DEVICE_SESSION_GATE",
        device_session_state="VALID",
    )
    assert service.user_privacy(
        principal_ref="user-1",
        model=model,
        requested_principal_ref="user-1",
    ) is model
    with pytest.raises(PermissionError, match="CROSS_USER_READ_DENIED"):
        service.user_privacy(
            principal_ref="user-1",
            model=model,
            requested_principal_ref="user-2",
        )
