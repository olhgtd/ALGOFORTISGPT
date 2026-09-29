"""Explicit WebAuthn step-up authority for Owner/Admin trust-changing actions."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from .repository import OwnerAdminRepository


STEP_UP_TTL = timedelta(minutes=5)
CHALLENGE_TTL = timedelta(minutes=5)


@dataclass(frozen=True, slots=True)
class DestructiveRoute:
    method: str
    pattern: re.Pattern[str]
    action_family: str
    resource_group: str | None = "resource"


ROUTES: tuple[DestructiveRoute, ...] = (
    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/access/users$"), "ACCOUNT_CREATE", None),
    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/access/users/(?P<resource>[^/]+)/suspend$"), "ACCOUNT_SUSPEND"),
    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/access/users/(?P<resource>[^/]+)/restore$"), "ACCOUNT_RESTORE"),
    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/access/users/(?P<resource>[^/]+)/revoke$"), "ACCOUNT_REVOKE"),
    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/access/users/(?P<resource>[^/]+)/reissue-activation$"), "ACTIVATION_REISSUE"),
    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/access/users/(?P<resource>[^/]+)/revoke-activation$"), "ACTIVATION_REVOKE"),
    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/access/users/(?P<resource>[^/]+)/(?:extend-service|renew-service|convert-lifetime)$"), "ENTITLEMENT_CHANGE"),
    DestructiveRoute("DELETE", re.compile(r"^/api/v1/owner/access/users/(?P<resource>[^/]+)/draft$"), "ACCOUNT_DRAFT_DELETE"),
    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/security/sessions/(?P<resource>[^/]+)/revoke$"), "SESSION_REVOKE"),
    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/security/users/(?P<resource>[^/]+)/sessions/revoke-all$"), "SESSION_REVOKE_ALL"),
    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/security/devices/(?P<resource>[^/]+)/revoke$"), "DEVICE_REVOKE"),
    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/security/users/(?P<resource>[^/]+)/devices/revoke-all$"), "DEVICE_REVOKE_ALL"),
    DestructiveRoute("POST", re.compile(r"^/api/v1/security/credentials/(?P<resource>[^/]+)/lifecycle$"), "CREDENTIAL_LIFECYCLE"),
    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/strategies/(?P<resource>[^/]+)/(?:allowance|visibility|suspend|restore|promote)$"), "STRATEGY_GOVERNANCE"),
    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/connections/(?P<resource>[^/]+)/(?:allowance|capabilities/[^/]+/allowance)$"), "CONNECTION_GOVERNANCE"),
    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/datasets/(?P<resource>[^/]+)/(?:approval|retire|replace)$"), "DATASET_GOVERNANCE"),
    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/settings/confirm$"), "SETTINGS_APPLY", None),
    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/admin/ai/providers/(?P<resource>[^/]+)/verify$"), "AI_PROVIDER_VERIFY"),
    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/admin/ai/providers/(?P<resource>[^/]+)$"), "AI_PROVIDER_CONFIG"),
    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/admin/ai/models/(?P<resource>[^/]+)$"), "AI_MODEL_CONFIG"),
    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/admin/ai/agents/(?P<resource>[^/]+)/(?:binding|policy)$"), "AI_AGENT_POLICY"),
    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/admin/ai/jobs$"), "AI_JOB_START", None),
    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/admin/ai/jobs/(?P<resource>[^/]+)/(?:cancel|resume|pause)$"), "AI_JOB_CONTROL"),
)


def classify_destructive_route(method: str, path: str) -> tuple[str, str | None] | None:
    method = method.upper()
    for item in ROUTES:
        if item.method != method:
            continue
        match = item.pattern.match(path)
        if match:
            resource = match.groupdict().get(item.resource_group or "") if item.resource_group else None
            return item.action_family, resource
    return None


class OwnerStepUpAuthority:
    """Binds fresh WebAuthn proof to one action/resource and consumes it once."""

    def __init__(self, *, repository: OwnerAdminRepository, ceremonies: Any) -> None:
        self._repository = repository
        self._ceremonies = ceremonies

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def issue_options(
        self,
        *,
        user: Any,
        action_family: str,
        resource_ref: str | None,
    ) -> dict[str, Any]:
        if self._ceremonies is None or not bool(getattr(self._ceremonies, "configured", False)):
            raise PermissionError("WebAuthn step-up authority unavailable")
        rp_id = self._ceremonies.normal_rp_id()
        issued = self._ceremonies.issue_authentication(user=user, rp_id=rp_id)
        challenge_id = str(issued.get("challenge_id") or "")
        if not challenge_id:
            raise PermissionError("step-up challenge unavailable")
        self._repository.save_step_up_challenge(
            challenge_id=challenge_id,
            user_id=user.user_id,
            action_family=action_family,
            resource_ref=resource_ref,
            expires_at=self._now() + CHALLENGE_TTL,
        )
        return {
            **issued,
            "action_family": action_family,
            "resource_ref": resource_ref,
            "expires_in_seconds": int(CHALLENGE_TTL.total_seconds()),
        }

    def complete(
        self,
        *,
        user: Any,
        challenge_id: str,
        action_family: str,
        resource_ref: str | None,
        response: dict[str, Any],
    ) -> dict[str, Any]:
        now = self._now()
        self._repository.consume_step_up_challenge(
            challenge_id=challenge_id,
            user_id=user.user_id,
            action_family=action_family,
            resource_ref=resource_ref,
            now=now,
        )
        credential_id, rp_id = self._ceremonies.complete_authentication(
            user=user,
            challenge_id=challenge_id,
            response=response,
        )
        if rp_id != self._ceremonies.normal_rp_id():
            raise PermissionError("step-up proof used an unexpected relying party")
        token = self._repository.create_step_up_grant(
            user_id=user.user_id,
            action_family=action_family,
            resource_ref=resource_ref,
            expires_at=now + STEP_UP_TTL,
        )
        return {
            "step_up_grant": token,
            "action_family": action_family,
            "resource_ref": resource_ref,
            "expires_in_seconds": int(STEP_UP_TTL.total_seconds()),
            "credential_ref": credential_id[:16],
        }

    def consume_grant(
        self,
        *,
        token: str,
        user_id: UUID,
        action_family: str,
        resource_ref: str | None,
    ) -> str:
        if not token:
            raise PermissionError("fresh step-up proof required")
        return self._repository.consume_step_up_grant(
            token=token,
            user_id=user_id,
            action_family=action_family,
            resource_ref=resource_ref,
            now=self._now(),
        )
