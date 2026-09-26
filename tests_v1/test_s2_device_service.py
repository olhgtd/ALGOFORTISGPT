from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature


class FakeSecurityStore:
    def __init__(self, path: Path) -> None:
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY)")
        self._conn.commit()

    def add_user(self, user_id: UUID) -> None:
        self._conn.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (str(user_id),))
        self._conn.commit()

    def get_user(self, user_id):
        return self._conn.execute("SELECT * FROM users WHERE user_id = ?", (str(user_id),)).fetchone()

    @contextmanager
    def _transaction(self):
        cur = self._conn.cursor()
        cur.execute("BEGIN IMMEDIATE")
        try:
            yield cur
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cur.close()


def _identity():
    private = ec.generate_private_key(ec.SECP256R1())
    public = private.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return private, public, hashlib.sha256(public).hexdigest()


def _setup(tmp_path: Path):
    from dashboard.backend.account_v2.v1_store_adapter import V1SecurityStoreAdapter
    from dashboard.backend.account_v2.device_service import DeviceRegistryService

    store = FakeSecurityStore(tmp_path / "security.sqlite3")
    user = uuid4()
    store.add_user(user)
    repo = V1SecurityStoreAdapter(store)
    return user, repo, DeviceRegistryService(repo)


def _challenge(service, *, user_id, device_id: str, purpose, now: datetime) -> bytes:
    return service.issue_challenge(
        user_id=user_id,
        device_id=device_id,
        purpose=purpose,
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
    )


def test_fourth_device_is_rejected_without_silent_eviction(tmp_path: Path) -> None:
    from dashboard.backend.account_v2.device_service import DeviceProofPurpose, DeviceQuotaExceeded

    user, repo, service = _setup(tmp_path)
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    for idx in range(3):
        private, public, fp = _identity()
        challenge = _challenge(service, user_id=user, device_id=f"d{idx}", purpose=DeviceProofPurpose.ENROLL, now=now)
        sig = private.sign(challenge, ec.ECDSA(hashes.SHA256()))
        service.enroll(user_id=user, device_id=f"d{idx}", public_key=public, fingerprint=fp, challenge=challenge, signature=sig, created_at=now)
    private, public, fp = _identity()
    challenge = _challenge(service, user_id=user, device_id="d3", purpose=DeviceProofPurpose.ENROLL, now=now)
    sig = private.sign(challenge, ec.ECDSA(hashes.SHA256()))
    with pytest.raises(DeviceQuotaExceeded):
        service.enroll(user_id=user, device_id="d3", public_key=public, fingerprint=fp, challenge=challenge, signature=sig, created_at=now)
    assert tuple(d.device_id for d in repo.list_devices(user_id=user)) == ("d0", "d1", "d2")


def test_same_pc_reproof_keeps_same_device_and_quota_slot(tmp_path: Path) -> None:
    from dashboard.backend.account_v2.device_service import DeviceProofPurpose

    user, repo, service = _setup(tmp_path)
    private, public, fp = _identity()
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    enroll_challenge = _challenge(service, user_id=user, device_id="same-pc", purpose=DeviceProofPurpose.ENROLL, now=now)
    sig = private.sign(enroll_challenge, ec.ECDSA(hashes.SHA256()))
    service.enroll(user_id=user, device_id="same-pc", public_key=public, fingerprint=fp, challenge=enroll_challenge, signature=sig, created_at=now)
    reproof_challenge = _challenge(service, user_id=user, device_id="same-pc", purpose=DeviceProofPurpose.REPROOF, now=now)
    proof = private.sign(reproof_challenge, ec.ECDSA(hashes.SHA256()))
    record = service.reprove_existing_device(user_id=user, device_id="same-pc", public_key=public, fingerprint=fp, challenge=reproof_challenge, signature=proof, verified_at=now)
    assert record.device_id == "same-pc"
    assert len(repo.list_devices(user_id=user)) == 1


def test_missing_or_mismatched_key_fails_closed(tmp_path: Path) -> None:
    from dashboard.backend.account_v2.device_service import DeviceProofPurpose, DeviceTrustError

    user, _, service = _setup(tmp_path)
    private, public, fp = _identity()
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    enroll_challenge = _challenge(service, user_id=user, device_id="pc", purpose=DeviceProofPurpose.ENROLL, now=now)
    service.enroll(user_id=user, device_id="pc", public_key=public, fingerprint=fp, challenge=enroll_challenge, signature=private.sign(enroll_challenge, ec.ECDSA(hashes.SHA256())), created_at=now)
    reproof_challenge = _challenge(service, user_id=user, device_id="pc", purpose=DeviceProofPurpose.REPROOF, now=now)
    with pytest.raises(DeviceTrustError):
        service.reprove_existing_device(user_id=user, device_id="pc", public_key=b"", fingerprint=fp, challenge=reproof_challenge, signature=b"", verified_at=now)
    other, other_public, other_fp = _identity()
    reproof_challenge_2 = _challenge(service, user_id=user, device_id="pc", purpose=DeviceProofPurpose.REPROOF, now=now)
    with pytest.raises(DeviceTrustError):
        service.reprove_existing_device(user_id=user, device_id="pc", public_key=other_public, fingerprint=other_fp, challenge=reproof_challenge_2, signature=other.sign(reproof_challenge_2, ec.ECDSA(hashes.SHA256())), verified_at=now)


def test_cross_user_reproof_is_rejected(tmp_path: Path) -> None:
    from dashboard.backend.account_v2.device_service import DeviceProofPurpose, DeviceRegistryService, DeviceTrustError
    from dashboard.backend.account_v2.v1_store_adapter import V1SecurityStoreAdapter

    store = FakeSecurityStore(tmp_path / "security.sqlite3")
    a, b = uuid4(), uuid4()
    store.add_user(a)
    store.add_user(b)
    repo = V1SecurityStoreAdapter(store)
    service = DeviceRegistryService(repo)
    private, public, fp = _identity()
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    enroll_challenge = _challenge(service, user_id=a, device_id="a-device", purpose=DeviceProofPurpose.ENROLL, now=now)
    service.enroll(user_id=a, device_id="a-device", public_key=public, fingerprint=fp, challenge=enroll_challenge, signature=private.sign(enroll_challenge, ec.ECDSA(hashes.SHA256())), created_at=now)
    foreign_challenge = _challenge(service, user_id=b, device_id="a-device", purpose=DeviceProofPurpose.REPROOF, now=now)
    with pytest.raises(DeviceTrustError):
        service.reprove_existing_device(user_id=b, device_id="a-device", public_key=public, fingerprint=fp, challenge=foreign_challenge, signature=private.sign(foreign_challenge, ec.ECDSA(hashes.SHA256())), verified_at=now)


def test_tpm_style_raw_p256_signature_is_accepted(tmp_path: Path) -> None:
    from dashboard.backend.account_v2.device_service import DeviceProofPurpose

    user, _, service = _setup(tmp_path)
    private, public, fp = _identity()
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    challenge = _challenge(service, user_id=user, device_id="tpm", purpose=DeviceProofPurpose.ENROLL, now=now)
    der = private.sign(challenge, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    record = service.enroll(user_id=user, device_id="tpm", public_key=public, fingerprint=fp, challenge=challenge, signature=raw, created_at=now)
    assert record.device_id == "tpm"


def test_unissued_device_challenge_is_rejected(tmp_path: Path) -> None:
    from dashboard.backend.account_v2.device_service import DeviceTrustError

    user, _, service = _setup(tmp_path)
    private, public, fp = _identity()
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    attacker_challenge = b"caller-controlled-challenge"
    with pytest.raises(DeviceTrustError, match="challenge"):
        service.enroll(
            user_id=user,
            device_id="pc",
            public_key=public,
            fingerprint=fp,
            challenge=attacker_challenge,
            signature=private.sign(attacker_challenge, ec.ECDSA(hashes.SHA256())),
            created_at=now,
        )


def test_device_challenge_is_single_use_and_replay_is_rejected(tmp_path: Path) -> None:
    from dashboard.backend.account_v2.device_service import DeviceProofPurpose, DeviceTrustError

    user, _, service = _setup(tmp_path)
    private, public, fp = _identity()
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    enroll_challenge = _challenge(service, user_id=user, device_id="pc", purpose=DeviceProofPurpose.ENROLL, now=now)
    service.enroll(user_id=user, device_id="pc", public_key=public, fingerprint=fp, challenge=enroll_challenge, signature=private.sign(enroll_challenge, ec.ECDSA(hashes.SHA256())), created_at=now)

    proof_challenge = _challenge(service, user_id=user, device_id="pc", purpose=DeviceProofPurpose.POSSESSION, now=now)
    signature = private.sign(proof_challenge, ec.ECDSA(hashes.SHA256()))
    service.verify_possession(user_id=user, device_id="pc", challenge=proof_challenge, signature=signature, verified_at=now)
    with pytest.raises(DeviceTrustError, match="challenge"):
        service.verify_possession(user_id=user, device_id="pc", challenge=proof_challenge, signature=signature, verified_at=now)


def test_expired_or_wrong_purpose_challenge_fails_closed(tmp_path: Path) -> None:
    from dashboard.backend.account_v2.device_service import DeviceProofPurpose, DeviceTrustError

    user, _, service = _setup(tmp_path)
    private, public, fp = _identity()
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    enroll_challenge = _challenge(service, user_id=user, device_id="pc", purpose=DeviceProofPurpose.ENROLL, now=now)
    service.enroll(user_id=user, device_id="pc", public_key=public, fingerprint=fp, challenge=enroll_challenge, signature=private.sign(enroll_challenge, ec.ECDSA(hashes.SHA256())), created_at=now)

    expired = service.issue_challenge(
        user_id=user,
        device_id="pc",
        purpose=DeviceProofPurpose.POSSESSION,
        issued_at=now,
        expires_at=now + timedelta(seconds=1),
    )
    with pytest.raises(DeviceTrustError, match="challenge"):
        service.verify_possession(
            user_id=user,
            device_id="pc",
            challenge=expired,
            signature=private.sign(expired, ec.ECDSA(hashes.SHA256())),
            verified_at=now + timedelta(seconds=2),
        )

    wrong_purpose = _challenge(service, user_id=user, device_id="pc", purpose=DeviceProofPurpose.REPROOF, now=now)
    with pytest.raises(DeviceTrustError, match="challenge"):
        service.verify_possession(
            user_id=user,
            device_id="pc",
            challenge=wrong_purpose,
            signature=private.sign(wrong_purpose, ec.ECDSA(hashes.SHA256())),
            verified_at=now,
        )
