"""Pure S2 account/device/session prerequisite gate.

This module has no broker, order, or Live-arming capability.  It evaluates
central account authority state and returns a prerequisite result only.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from .contracts import DeviceSessionGateResult, DeviceSessionGateStatus


S2_GATE_SCHEMA_VERSION = "s2-device-session-gate/v1"


class DeviceSessionGate:
    def __init__(self, repository, *, authority_evidence_ref: str | None = None) -> None:
        self._repository = repository
        self._authority_evidence_ref = authority_evidence_ref

    def _result(
        self,
        *,
        user_id: UUID,
        device_id: str,
        session_family_id: str | None,
        status: DeviceSessionGateStatus,
        reason: str,
        now: datetime,
    ) -> DeviceSessionGateResult:
        return DeviceSessionGateResult(
            schema_version=S2_GATE_SCHEMA_VERSION,
            user_id=user_id,
            device_id=device_id,
            session_family_id=session_family_id,
            status=status,
            reasons=(reason,),
            authority_evidence_ref=self._authority_evidence_ref,
            evaluated_at=now,
            audit_ref=None,
        )

    def evaluate(
        self,
        user_id: UUID,
        device_id: str,
        session_family_id: str | None,
        now: datetime,
    ) -> DeviceSessionGateResult:
        try:
            device = self._repository.get_device(user_id=user_id, device_id=device_id)

            if device is None:
                return self._result(
                    user_id=user_id,
                    device_id=device_id,
                    session_family_id=session_family_id,
                    status=DeviceSessionGateStatus.DEVICE_UNTRUSTED,
                    reason="DEVICE_NOT_REGISTERED",
                    now=now,
                )
            if device.status == "REVOKED":
                return self._result(
                    user_id=user_id,
                    device_id=device_id,
                    session_family_id=session_family_id,
                    status=DeviceSessionGateStatus.REVOKED,
                    reason="DEVICE_REVOKED",
                    now=now,
                )
            if device.status != "ACTIVE":
                return self._result(
                    user_id=user_id,
                    device_id=device_id,
                    session_family_id=session_family_id,
                    status=DeviceSessionGateStatus.DEVICE_UNTRUSTED,
                    reason="DEVICE_NOT_TRUSTED",
                    now=now,
                )
            if not session_family_id:
                return self._result(
                    user_id=user_id,
                    device_id=device_id,
                    session_family_id=None,
                    status=DeviceSessionGateStatus.SESSION_EXPIRED,
                    reason="SESSION_FAMILY_MISSING",
                    now=now,
                )

            family = self._repository.get_session_family(user_id=user_id, family_id=session_family_id)
            if family is None:
                return self._result(
                    user_id=user_id,
                    device_id=device_id,
                    session_family_id=session_family_id,
                    status=DeviceSessionGateStatus.SESSION_EXPIRED,
                    reason="SESSION_FAMILY_UNAVAILABLE",
                    now=now,
                )
            if family.device_id != device_id:
                return self._result(
                    user_id=user_id,
                    device_id=device_id,
                    session_family_id=session_family_id,
                    status=DeviceSessionGateStatus.DEVICE_UNTRUSTED,
                    reason="SESSION_DEVICE_MISMATCH",
                    now=now,
                )
            if family.state == "RECOVERY_REQUIRED":
                return self._result(
                    user_id=user_id,
                    device_id=device_id,
                    session_family_id=session_family_id,
                    status=DeviceSessionGateStatus.RECOVERY_REQUIRED,
                    reason="RECOVERY_REQUIRED",
                    now=now,
                )
            if family.state == "REVOKED":
                return self._result(
                    user_id=user_id,
                    device_id=device_id,
                    session_family_id=session_family_id,
                    status=DeviceSessionGateStatus.REVOKED,
                    reason="SESSION_REVOKED",
                    now=now,
                )
            if family.state != "ACTIVE":
                return self._result(
                    user_id=user_id,
                    device_id=device_id,
                    session_family_id=session_family_id,
                    status=DeviceSessionGateStatus.SESSION_EXPIRED,
                    reason="SESSION_NOT_ACTIVE",
                    now=now,
                )

            policy = self._repository.get_session_policy(user_id=user_id, family_id=session_family_id)
            if policy is None or now > policy.absolute_expires_at or now > policy.idle_expires_at:
                return self._result(
                    user_id=user_id,
                    device_id=device_id,
                    session_family_id=session_family_id,
                    status=DeviceSessionGateStatus.SESSION_EXPIRED,
                    reason="SESSION_EXPIRED",
                    now=now,
                )

            return self._result(
                user_id=user_id,
                device_id=device_id,
                session_family_id=session_family_id,
                status=DeviceSessionGateStatus.VALID,
                reason="ACCOUNT_DEVICE_SESSION_VALID",
                now=now,
            )
        except (TimeoutError, ConnectionError, OSError):
            return self._result(
                user_id=user_id,
                device_id=device_id,
                session_family_id=session_family_id,
                status=DeviceSessionGateStatus.AUTHORITY_UNAVAILABLE,
                reason="ACCOUNT_AUTHORITY_UNAVAILABLE",
                now=now,
            )
