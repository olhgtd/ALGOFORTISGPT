"""Owner/Admin audit adapter over the existing authoritative Core Audit.

Core Audit remains the authority.  The local incident table is subordinate
operational evidence linked back to the immutable Core Audit reference.
"""
from __future__ import annotations

from typing import Any, Mapping
from uuid import UUID

from .repository import OwnerAdminRepository


_SENSITIVE_KEYS = {
    "password", "secret", "token", "access_token", "refresh_token",
    "activation_code", "bootstrap_token", "api_key", "credential",
    "step_up_grant", "assertion", "response",
}


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            lower = str(key).lower()
            if lower in _SENSITIVE_KEYS or any(marker in lower for marker in ("password", "secret", "token", "api_key")):
                safe[str(key)] = "[REDACTED]"
            else:
                safe[str(key)] = _sanitize(item)
        return safe
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if isinstance(value, bytes):
        return "[BINARY_REDACTED]"
    return value


class OwnerAdminAudit:
    def __init__(self, *, core_audit: Any, repository: OwnerAdminRepository) -> None:
        if core_audit is None:
            raise RuntimeError("authoritative Core Audit unavailable")
        self._core = core_audit
        self._repository = repository

    def require_authorization_event(
        self,
        *,
        actor_id: UUID,
        action_family: str,
        resource_ref: str | None,
        step_up_ref: str,
        details: Mapping[str, Any] | None = None,
    ) -> str:
        """Persist required pre-mutation authorization evidence or fail closed."""
        payload = {
            "action_family": action_family,
            "resource_ref": resource_ref,
            "step_up": "VERIFIED",
            "step_up_ref": step_up_ref,
            **dict(_sanitize(details or {})),
        }
        reference = self._core.record(
            actor_id=actor_id,
            action="OWNER_ADMIN_MUTATION_AUTHORIZED",
            resource_id=resource_ref,
            payload=payload,
        )
        if not reference:
            raise RuntimeError("required owner mutation audit evidence unavailable")
        return str(reference)

    def record_outcome(
        self,
        *,
        actor_id: UUID,
        action_family: str,
        resource_ref: str | None,
        status: str,
        reason_code: str,
        details: Mapping[str, Any] | None = None,
    ) -> str:
        rejected = status.upper() in {"REJECTED", "DENIED"}
        reference = self._core.record(
            actor_id=actor_id,
            action=f"OWNER_ADMIN_{status.upper()}",
            resource_id=resource_ref,
            rejected=rejected,
            payload={
                "action_family": action_family,
                "reason_code": reason_code,
                **dict(_sanitize(details or {})),
            },
        )
        if not reference:
            raise RuntimeError("owner mutation outcome audit evidence unavailable")
        return str(reference)

    def failure_incident(
        self,
        *,
        actor_id: UUID,
        action_family: str,
        resource_ref: str | None,
        reason_code: str,
        status: str = "REJECTED",
        details: Mapping[str, Any] | None = None,
    ) -> str:
        """Persist a subordinate FailureIncident linked to Core Audit evidence."""
        safe_details = dict(_sanitize(details or {}))
        core_ref: str | None = None
        try:
            core_ref = self.record_outcome(
                actor_id=actor_id,
                action_family=action_family,
                resource_ref=resource_ref,
                status=status,
                reason_code=reason_code,
                details=safe_details,
            )
        finally:
            # The subordinate incident never grants authority.  If Core Audit is
            # down, callers still fail closed; this row records recovery context.
            incident_id = self._repository.save_incident(
                actor_id=actor_id,
                action_family=action_family,
                resource_ref=resource_ref,
                reason_code=reason_code,
                status=status,
                details=safe_details,
                core_audit_ref=core_ref,
            )
        return incident_id
