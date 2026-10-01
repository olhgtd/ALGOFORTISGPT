from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from dashboard.backend.account_v2.contracts import (
    DeviceSessionGateResult,
    DeviceSessionGateStatus,
    IntelligenceCapability,
)
from dashboard.backend.account_v2.intelligence_entitlements import (
    IntelligenceEntitlementService,
)

NOW = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
USER = UUID("11111111-1111-1111-1111-111111111111")


class _Store:
    def __init__(self) -> None:
        self.values: dict[UUID, tuple[IntelligenceCapability, ...]] = {}

    def list_for_user(self, user_id: UUID) -> tuple[IntelligenceCapability, ...]:
        return self.values.get(user_id, ())

    def replace_for_user(self, user_id: UUID, capabilities: tuple[IntelligenceCapability, ...]) -> None:
        self.values[user_id] = capabilities


def _gate(status: DeviceSessionGateStatus) -> DeviceSessionGateResult:
    return DeviceSessionGateResult(
        schema_version="1.0.0",
        user_id=USER,
        device_id="device-1",
        session_family_id="family-1",
        status=status,
        reasons=(),
        authority_evidence_ref="s2:evidence" if status is DeviceSessionGateStatus.VALID else None,
        evaluated_at=NOW,
        audit_ref="audit:s2",
    )


def test_valid_s2_principal_receives_only_explicitly_granted_capability() -> None:
    store = _Store()
    service = IntelligenceEntitlementService(store)
    service.set_for_user(
        USER,
        (IntelligenceCapability.ACCESS_LAYA_ANALYSIS, IntelligenceCapability.ACCESS_AI_REVIEW),
        actor_is_owner=True,
    )
    allowed = service.authorize(_gate(DeviceSessionGateStatus.VALID), IntelligenceCapability.ACCESS_LAYA_ANALYSIS)
    denied = service.authorize(_gate(DeviceSessionGateStatus.VALID), IntelligenceCapability.ACCESS_STRATEGY_HUNTING)
    assert allowed.allowed is True
    assert denied.allowed is False
    assert denied.reason == "CAPABILITY_NOT_GRANTED"


@pytest.mark.parametrize(
    "status",
    [
        DeviceSessionGateStatus.REVOKED,
        DeviceSessionGateStatus.SESSION_EXPIRED,
        DeviceSessionGateStatus.DEVICE_UNTRUSTED,
        DeviceSessionGateStatus.RECOVERY_REQUIRED,
        DeviceSessionGateStatus.AUTHORITY_UNAVAILABLE,
    ],
)
def test_invalid_or_unavailable_s2_authority_fails_closed(status: DeviceSessionGateStatus) -> None:
    store = _Store()
    store.values[USER] = (IntelligenceCapability.ACCESS_ADVANCED_RESEARCH,)
    result = IntelligenceEntitlementService(store).authorize(
        _gate(status), IntelligenceCapability.ACCESS_ADVANCED_RESEARCH
    )
    assert result.allowed is False
    assert result.reason == f"S2_{status.value}"


def test_normal_user_cannot_self_grant_intelligence_capabilities() -> None:
    service = IntelligenceEntitlementService(_Store())
    with pytest.raises(PermissionError, match="Owner"):
        service.set_for_user(
            USER,
            (IntelligenceCapability.ACCESS_STRATEGY_HUNTING,),
            actor_is_owner=False,
        )


def test_owner_can_inspect_current_entitlement_set_without_creating_identity_authority() -> None:
    store = _Store()
    service = IntelligenceEntitlementService(store)
    service.set_for_user(
        USER,
        (
            IntelligenceCapability.ACCESS_AI_REVIEW,
            IntelligenceCapability.ACCESS_INTELLIGENCE_CANDIDATES,
        ),
        actor_is_owner=True,
    )
    assert service.list_for_user(USER) == (
        IntelligenceCapability.ACCESS_AI_REVIEW,
        IntelligenceCapability.ACCESS_INTELLIGENCE_CANDIDATES,
    )
    for forbidden in ("login", "issue_token", "create_session", "validate_password"):
        assert not hasattr(service, forbidden)
