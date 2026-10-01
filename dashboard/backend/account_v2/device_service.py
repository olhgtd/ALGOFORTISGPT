"""S2 device registry and cryptographic possession proof."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from enum import Enum
from typing import Callable
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from .repository import (
    AccountAuthorityRecordUnavailable,
    AccountAuthorityRepository,
    DeviceQuotaAuthorityExceeded,
    DeviceRecord,
)


class DeviceTrustError(PermissionError):
    pass


class DeviceQuotaExceeded(DeviceTrustError):
    pass


class DeviceProofPurpose(str, Enum):
    ENROLL = "ENROLL"
    POSSESSION = "POSSESSION"
    REPROOF = "REPROOF"


class P256DeviceProofVerifier:
    @staticmethod
    def verify(*, public_key: bytes, challenge: bytes, signature: bytes) -> bool:
        if not public_key or not challenge or not signature:
            return False
        try:
            key = serialization.load_der_public_key(public_key)
            if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
                return False
            candidate = signature
            if len(signature) == 64:
                r = int.from_bytes(signature[:32], "big")
                s = int.from_bytes(signature[32:], "big")
                candidate = encode_dss_signature(r, s)
            key.verify(candidate, challenge, ec.ECDSA(hashes.SHA256()))
            return True
        except (ValueError, TypeError, InvalidSignature):
            return False


class DeviceRegistryService:
    MAX_ACTIVE_DEVICES = 3

    def __init__(
        self,
        repository: AccountAuthorityRepository,
        verifier: P256DeviceProofVerifier | None = None,
        *,
        challenge_factory: Callable[[int], bytes] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._verifier = verifier or P256DeviceProofVerifier()
        self._challenge_factory = challenge_factory or secrets.token_bytes
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _valid_fingerprint(public_key: bytes, fingerprint: str) -> bool:
        return bool(public_key) and hashlib.sha256(public_key).hexdigest() == fingerprint

    @staticmethod
    def _challenge_hash(challenge: bytes) -> str:
        return hashlib.sha256(challenge).hexdigest()

    @staticmethod
    def _purpose_value(purpose: DeviceProofPurpose | str) -> str:
        try:
            return DeviceProofPurpose(purpose).value
        except ValueError as exc:
            raise DeviceTrustError("device proof purpose unavailable") from exc

    def issue_challenge(
        self,
        *,
        user_id: UUID,
        device_id: str,
        purpose: DeviceProofPurpose | str,
        issued_at: datetime,
        expires_at: datetime,
    ) -> bytes:
        if not device_id or expires_at <= issued_at:
            raise DeviceTrustError("device proof challenge policy unavailable")
        purpose_value = self._purpose_value(purpose)
        challenge = bytes(self._challenge_factory(32))
        if len(challenge) < 32:
            raise DeviceTrustError("device proof challenge generation unavailable")
        try:
            self._repository.save_device_challenge(
                user_id=user_id,
                device_id=device_id,
                purpose=purpose_value,
                challenge_hash=self._challenge_hash(challenge),
                issued_at=issued_at,
                expires_at=expires_at,
            )
        except (AccountAuthorityRecordUnavailable, ValueError) as exc:
            raise DeviceTrustError("device proof challenge unavailable") from exc
        return challenge

    def _consume_challenge(
        self,
        *,
        user_id: UUID,
        device_id: str,
        purpose: DeviceProofPurpose,
        challenge: bytes,
        verified_at: datetime,
    ) -> None:
        try:
            self._repository.consume_device_challenge(
                user_id=user_id,
                device_id=device_id,
                purpose=purpose.value,
                challenge_hash=self._challenge_hash(challenge),
                consumed_at=verified_at,
            )
        except AccountAuthorityRecordUnavailable as exc:
            raise DeviceTrustError("device proof challenge unavailable") from exc

    def _prove(self, *, public_key: bytes, fingerprint: str, challenge: bytes, signature: bytes) -> None:
        if not self._valid_fingerprint(public_key, fingerprint):
            raise DeviceTrustError("device identity proof unavailable")
        if not self._verifier.verify(public_key=public_key, challenge=challenge, signature=signature):
            raise DeviceTrustError("device identity proof unavailable")

    def enroll(self, *, user_id: UUID, device_id: str, public_key: bytes, fingerprint: str,
               challenge: bytes, signature: bytes, created_at: datetime) -> DeviceRecord:
        self._prove(public_key=public_key, fingerprint=fingerprint, challenge=challenge, signature=signature)
        self._consume_challenge(
            user_id=user_id,
            device_id=device_id,
            purpose=DeviceProofPurpose.ENROLL,
            challenge=challenge,
            verified_at=created_at,
        )
        active = tuple(record for record in self._repository.list_devices(user_id=user_id) if record.status == "ACTIVE")
        if len(active) >= self.MAX_ACTIVE_DEVICES:
            raise DeviceQuotaExceeded("active device quota reached")
        try:
            return self._repository.register_device(
                user_id=user_id,
                device_id=device_id,
                public_key=public_key,
                fingerprint=fingerprint,
                created_at=created_at,
                max_active_devices=self.MAX_ACTIVE_DEVICES,
            )
        except DeviceQuotaAuthorityExceeded as exc:
            raise DeviceQuotaExceeded("active device quota reached") from exc
        except AccountAuthorityRecordUnavailable as exc:
            raise DeviceTrustError("device identity enrollment unavailable") from exc

    def verify_possession(self, *, user_id: UUID, device_id: str, challenge: bytes, signature: bytes,
                          verified_at: datetime | None = None) -> DeviceRecord:
        record = self._repository.get_device(user_id=user_id, device_id=device_id)
        if record is None or record.status != "ACTIVE":
            raise DeviceTrustError("device identity proof unavailable")
        self._prove(public_key=record.public_key, fingerprint=record.fingerprint, challenge=challenge, signature=signature)
        self._consume_challenge(
            user_id=user_id,
            device_id=device_id,
            purpose=DeviceProofPurpose.POSSESSION,
            challenge=challenge,
            verified_at=verified_at or self._clock(),
        )
        return record

    def reprove_existing_device(self, *, user_id: UUID, device_id: str, public_key: bytes,
                                fingerprint: str, challenge: bytes, signature: bytes,
                                verified_at: datetime | None = None) -> DeviceRecord:
        record = self._repository.get_device(user_id=user_id, device_id=device_id)
        if record is None or record.status != "ACTIVE":
            raise DeviceTrustError("device identity continuity unavailable")
        if public_key != record.public_key or fingerprint != record.fingerprint:
            raise DeviceTrustError("device identity continuity unavailable")
        self._prove(public_key=public_key, fingerprint=fingerprint, challenge=challenge, signature=signature)
        self._consume_challenge(
            user_id=user_id,
            device_id=device_id,
            purpose=DeviceProofPurpose.REPROOF,
            challenge=challenge,
            verified_at=verified_at or self._clock(),
        )
        return record

    def revoke(self, *, user_id: UUID, device_id: str, revoked_at: datetime) -> None:
        try:
            self._repository.revoke_device(user_id=user_id, device_id=device_id, revoked_at=revoked_at)
        except AccountAuthorityRecordUnavailable as exc:
            raise DeviceTrustError("device revocation unavailable") from exc

    def list_for_user(self, *, user_id: UUID) -> tuple[DeviceRecord, ...]:
        return self._repository.list_devices(user_id=user_id)
