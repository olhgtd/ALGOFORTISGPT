"""AlgoFortis V1 — Local User Credential Vault (ADR §128 / Phase 2).

Provides hardware/OS-level local credential protection using Windows DPAPI (CryptProtectData).
Enforces:
- Local Windows DPAPI protection bound to current Windows user session
- User entropy isolation: User A cannot decrypt User B's credentials even in the same Windows session
- Absolute exclusion of plaintext secrets from SQLite, Git, logs, backups, and telemetry
- Fail-closed behavior on corrupt, tampered, or wrong-user credential blobs
- Automatic secret masking in __repr__ and __str__
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


class CredentialVaultError(Exception):
    """Base exception for credential vault operations."""


class CredentialNotFoundError(CredentialVaultError):
    """Raised when a requested credential reference does not exist."""


class CredentialDecryptionError(CredentialVaultError):
    """Raised when a credential cannot be decrypted (corrupt, wrong user, or unauthorized)."""


@dataclass(frozen=True)
class BrokerCredentials:
    """Container for broker API credentials with strict redaction on string representation."""

    api_key: str
    api_secret: str = ""
    access_token: str = ""
    refresh_token: str | None = None
    pin_or_totp: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ValueError("api_key must be a non-empty string")

    def __repr__(self) -> str:
        masked_key = f"{self.api_key[:3]}...{self.api_key[-2:]}" if len(self.api_key) > 5 else "***"
        return (
            f"BrokerCredentials(api_key='{masked_key}', "
            f"api_secret='***', access_token='***', "
            f"has_refresh={self.refresh_token is not None}, "
            f"has_totp={self.pin_or_totp is not None})"
        )

    def __str__(self) -> str:
        return self.__repr__()

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_key": self.api_key,
            "api_secret": self.api_secret,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "pin_or_totp": self.pin_or_totp,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrokerCredentials:
        return cls(
            api_key=str(data.get("api_key") or ""),
            api_secret=str(data.get("api_secret") or ""),
            access_token=str(data.get("access_token") or ""),
            refresh_token=data.get("refresh_token"),
            pin_or_totp=data.get("pin_or_totp"),
            extra=dict(data.get("extra") or {}),
        )


def _get_default_vault_dir() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        local_appdata = str(Path.home() / "AppData" / "Local")
    path = Path(local_appdata) / "AlgoFortis" / "Security" / "Vault"
    path.mkdir(parents=True, exist_ok=True)
    return path


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _dpapi_protect(data: bytes, entropy: bytes) -> bytes:
    """Encrypt data via Windows DPAPI CryptProtectData with user entropy."""
    if sys.platform != "win32":
        raise CredentialVaultError("DPAPI is only supported on Windows")

    in_buf = ctypes.create_string_buffer(data)
    in_blob = DATA_BLOB(len(data), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_char)))
    ent_buf = ctypes.create_string_buffer(entropy)
    ent_blob = DATA_BLOB(len(entropy), ctypes.cast(ent_buf, ctypes.POINTER(ctypes.c_char)))
    out_blob = DATA_BLOB()

    res = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "AlgoFortis Broker Credential",
        ctypes.byref(ent_blob),
        None,
        None,
        0x01,  # CRYPTPROTECT_UI_FORBIDDEN
        ctypes.byref(out_blob),
    )
    if not res:
        raise CredentialVaultError(
            f"CryptProtectData failed with error {ctypes.GetLastError()}"
        )
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def _dpapi_unprotect(data: bytes, entropy: bytes) -> bytes:
    """Decrypt data via Windows DPAPI CryptUnprotectData with user entropy."""
    if sys.platform != "win32":
        raise CredentialVaultError("DPAPI is only supported on Windows")

    in_buf = ctypes.create_string_buffer(data)
    in_blob = DATA_BLOB(len(data), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_char)))
    ent_buf = ctypes.create_string_buffer(entropy)
    ent_blob = DATA_BLOB(len(entropy), ctypes.cast(ent_buf, ctypes.POINTER(ctypes.c_char)))
    out_blob = DATA_BLOB()

    res = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        ctypes.byref(ent_blob),
        None,
        None,
        0x01,  # CRYPTPROTECT_UI_FORBIDDEN
        ctypes.byref(out_blob),
    )
    if not res:
        raise CredentialDecryptionError(
            f"CryptUnprotectData failed: invalid or corrupt data (error {ctypes.GetLastError()})"
        )
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


class LocalCredentialVault:
    """Local Windows DPAPI-backed credential vault with user entropy isolation."""

    def __init__(self, vault_dir: Path | None = None) -> None:
        self._vault_dir = Path(vault_dir) if vault_dir is not None else _get_default_vault_dir()
        self._vault_dir.mkdir(parents=True, exist_ok=True)

    @property
    def vault_dir(self) -> Path:
        return self._vault_dir

    def _file_path(self, credential_ref: str) -> Path:
        # Sanitize credential_ref for filesystem safety
        clean_ref = "".join(c for c in credential_ref if c.isalnum() or c in ("-", "_", "."))
        return self._vault_dir / f"{clean_ref}.enc"

    def store_credentials(
        self,
        user_id: str,
        connection_id: str,
        credentials: BrokerCredentials | dict[str, Any] | str,
    ) -> str:
        """Encrypt and persist broker credentials under user isolation.

        Returns opaque credential_ref string suitable for storing in user_connections.
        """
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("user_id must be a non-empty string")
        if not isinstance(connection_id, str) or not connection_id.strip():
            raise ValueError("connection_id must be a non-empty string")

        if isinstance(credentials, str):
            cred_obj = BrokerCredentials(api_key=credentials, access_token=credentials)
        elif isinstance(credentials, dict):
            cred_obj = BrokerCredentials.from_dict(credentials)
        elif isinstance(credentials, BrokerCredentials):
            cred_obj = credentials
        else:
            raise TypeError("credentials must be BrokerCredentials, dict, or str")

        payload_bytes = json.dumps(cred_obj.to_dict()).encode("utf-8")
        entropy_bytes = user_id.encode("utf-8")

        encrypted_bytes = _dpapi_protect(payload_bytes, entropy_bytes)

        credential_ref = f"VAULT-{connection_id}"
        dest_path = self._file_path(credential_ref)
        dest_path.write_bytes(encrypted_bytes)
        return credential_ref

    def resolve_credentials(
        self,
        user_id: str,
        credential_ref: str,
    ) -> BrokerCredentials:
        """Resolve and decrypt credentials for the given user.

        Fails closed with CredentialNotFoundError if file missing, or
        CredentialDecryptionError if corrupted or attempted by wrong user.
        """
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("user_id must be a non-empty string")
        if not isinstance(credential_ref, str) or not credential_ref.strip():
            raise ValueError("credential_ref must be a non-empty string")

        file_path = self._file_path(credential_ref)
        if not file_path.exists():
            raise CredentialNotFoundError(f"Credential reference '{credential_ref}' not found in vault")

        encrypted_bytes = file_path.read_bytes()
        entropy_bytes = user_id.encode("utf-8")

        try:
            decrypted_bytes = _dpapi_unprotect(encrypted_bytes, entropy_bytes)
            data = json.loads(decrypted_bytes.decode("utf-8"))
            return BrokerCredentials.from_dict(data)
        except CredentialDecryptionError:
            raise
        except Exception as exc:
            raise CredentialDecryptionError(f"Failed to decode decrypted credentials: {exc}") from exc

    def resolve_token(self, user_id: str, credential_ref: str) -> str:
        """Helper to resolve the primary access token or api key."""
        creds = self.resolve_credentials(user_id, credential_ref)
        return creds.access_token or creds.api_key

    def delete_credentials(self, user_id: str, credential_ref: str) -> bool:
        """Delete stored encrypted credential file."""
        file_path = self._file_path(credential_ref)
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def has_credentials(self, user_id: str, credential_ref: str) -> bool:
        """Check whether credential exists."""
        return self._file_path(credential_ref).exists()
