"""Durable device-bound S2 session families with single-use refresh tokens."""
from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from .repository import (
    AccountAuthorityRecordUnavailable,
    AccountAuthorityRepository,
    RefreshTokenReplayDetected,
)


ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_IDLE_TTL = timedelta(days=7)
REFRESH_ABSOLUTE_TTL = timedelta(days=30)


class SessionUnavailable(PermissionError):
    pass


class RefreshTokenReuseDetected(SessionUnavailable):
    pass


@dataclass(frozen=True, slots=True)
class SessionIssue:
    family_id: str
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_absolute_expires_at: datetime


class DurableSessionService:
    def __init__(self, repository: AccountAuthorityRepository) -> None:
        self._repository = repository

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _new_access_token() -> str:
        return "af_at_" + secrets.token_urlsafe(32)

    @staticmethod
    def _new_refresh_token() -> str:
        return "af_rt_" + secrets.token_urlsafe(32)

    def create_session(self, *, user_id: UUID, device_id: str, now: datetime) -> SessionIssue:
        try:
            device = self._repository.get_device(user_id=user_id, device_id=device_id)
        except AccountAuthorityRecordUnavailable as exc:
            raise SessionUnavailable("device/session unavailable") from exc
        if device is None or device.status != "ACTIVE":
            raise SessionUnavailable("device/session unavailable")

        family_id = "fam_" + uuid.uuid4().hex
        access_token = self._new_access_token()
        refresh_token = self._new_refresh_token()
        absolute_expires_at = now + REFRESH_ABSOLUTE_TTL
        self._repository.save_session_family(
            user_id=user_id,
            family_id=family_id,
            device_id=device_id,
            current_refresh_hash=self.hash_token(refresh_token),
            state="ACTIVE",
            created_at=now,
            updated_at=now,
        )
        self._repository.save_session_policy(
            user_id=user_id,
            family_id=family_id,
            absolute_expires_at=absolute_expires_at,
            idle_expires_at=now + REFRESH_IDLE_TTL,
        )
        return SessionIssue(
            family_id=family_id,
            access_token=access_token,
            refresh_token=refresh_token,
            access_expires_at=now + ACCESS_TOKEN_TTL,
            refresh_absolute_expires_at=absolute_expires_at,
        )

    def rotate_refresh_token(self, *, user_id: UUID, device_id: str, family_id: str,
                             presented_refresh_token: str, now: datetime) -> SessionIssue:
        token_hash = self.hash_token(presented_refresh_token)
        try:
            if self._repository.is_consumed_refresh_hash(
                user_id=user_id,
                family_id=family_id,
                token_hash=token_hash,
            ):
                self._repository.revoke_session_family(user_id=user_id, family_id=family_id, revoked_at=now)
                raise RefreshTokenReuseDetected("refresh token reuse detected; family revoked")
            family = self._repository.get_session_family(user_id=user_id, family_id=family_id)
            device = self._repository.get_device(user_id=user_id, device_id=device_id)
        except AccountAuthorityRecordUnavailable as exc:
            raise SessionUnavailable("device/session unavailable") from exc

        if (family is None or family.state != "ACTIVE" or family.device_id != device_id
                or device is None or device.status != "ACTIVE"):
            raise SessionUnavailable("device/session unavailable")
        if family.current_refresh_hash != token_hash:
            raise SessionUnavailable("device/session unavailable")

        policy = self._repository.get_session_policy(user_id=user_id, family_id=family_id)
        if policy is None:
            self._repository.revoke_session_family(user_id=user_id, family_id=family_id, revoked_at=now)
            raise SessionUnavailable("session policy unavailable")
        if now > policy.absolute_expires_at or now > policy.idle_expires_at:
            self._repository.revoke_session_family(user_id=user_id, family_id=family_id, revoked_at=now)
            raise SessionUnavailable("session expired")

        new_access_token = self._new_access_token()
        new_refresh_token = self._new_refresh_token()
        try:
            self._repository.rotate_refresh_hash(
                user_id=user_id,
                family_id=family_id,
                expected_current_hash=token_hash,
                new_current_hash=self.hash_token(new_refresh_token),
                consumed_hash=token_hash,
                updated_at=now,
                idle_expires_at=now + REFRESH_IDLE_TTL,
            )
        except RefreshTokenReplayDetected as exc:
            raise RefreshTokenReuseDetected("refresh token reuse detected; family revoked") from exc
        except AccountAuthorityRecordUnavailable as exc:
            raise SessionUnavailable("session rotation unavailable") from exc

        return SessionIssue(
            family_id=family_id,
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            access_expires_at=now + ACCESS_TOKEN_TTL,
            refresh_absolute_expires_at=policy.absolute_expires_at,
        )
