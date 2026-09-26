"""S2 device registry and cryptographic possession proof."""
from __future__ import annotations

import hashlib
from datetime import datetime
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

    def __init__(self, repository: AccountAuthorityRepository, verifier: P256DeviceProofVerifier | None = None) -> None:
        self._repository = repository
        self._verifier = verifier or P256DeviceProofVerifier()

    @staticmethod
    def _valid_fingerprint(public_key: bytes, fingerprint: str) -> bool:
        return bool(public_key) and hashlib.sha256(public_key).hexdigest() == fingerprint

    def _prove(self, *, public_key: bytes, fingerprint: str, challenge: bytes, signature: bytes) -> None:
        if not self._valid_fingerprint(public_key, fingerprint):
            raise DeviceTrustError("device identity proof unavailable")
        if not self._verifier.verify(public_key=public_key, challenge=challenge, signature=signature):
            raise DeviceTrustError("device identity proof unavailable")

    def enroll(self, *, user_id: UUID, device_id: str, public_key: bytes, fingerprint: str,
               challenge: bytes, signature: bytes, created_at: datetime) -> DeviceRecord:
        self._prove(public_key=public_key, fingerprint=fingerprint, challenge=challenge, signature=signature)
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

    def verify_possession(self, *, user_id: UUID, device_id: str, challenge: bytes, signature: bytes) -> DeviceRecord:
        record = self._repository.get_device(user_id=user_id, device_id=device_id)
        if record is None or record.status != "ACTIVE":
            raise DeviceTrustError("device identity proof unavailable")
        self._prove(public_key=record.public_key, fingerprint=record.fingerprint, challenge=challenge, signature=signature)
        return record

    def reprove_existing_device(self, *, user_id: UUID, device_id: str, public_key: bytes,
                                fingerprint: str, challenge: bytes, signature: bytes) -> DeviceRecord:
        record = self._repository.get_device(user_id=user_id, device_id=device_id)
        if record is None or record.status != "ACTIVE":
            raise DeviceTrustError("device identity continuity unavailable")
        if public_key != record.public_key or fingerprint != record.fingerprint:
            raise DeviceTrustError("device identity continuity unavailable")
        self._prove(public_key=public_key, fingerprint=fingerprint, challenge=challenge, signature=signature)
        return record

    def revoke(self, *, user_id: UUID, device_id: str, revoked_at: datetime) -> None:
        try:
            self._repository.revoke_device(user_id=user_id, device_id=device_id, revoked_at=revoked_at)
        except AccountAuthorityRecordUnavailable as exc:
            raise DeviceTrustError("device revocation unavailable") from exc

    def list_for_user(self, *, user_id: UUID) -> tuple[DeviceRecord, ...]:
        return self._repository.list_devices(user_id=user_id)
