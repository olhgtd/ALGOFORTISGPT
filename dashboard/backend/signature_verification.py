"""Cryptographic signature verification adapters for release/account artifacts.

Only public verification material belongs here. Production private signing keys
remain outside the client and outside source control.
"""
from __future__ import annotations

import base64
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


class Ed25519KeyringVerifier:
    """Callable detached-signature verifier keyed by an external key id."""

    def __init__(self, public_keys: Mapping[str, bytes | str]):
        if not public_keys:
            raise ValueError("Ed25519 keyring must not be empty")
        parsed: dict[str, Ed25519PublicKey] = {}
        for key_id, material in public_keys.items():
            if not isinstance(key_id, str) or not key_id.strip():
                raise ValueError("Ed25519 key id must be non-empty")
            raw = material.encode("utf-8") if isinstance(material, str) else bytes(material)
            if len(raw) == 32 and b"BEGIN PUBLIC KEY" not in raw:
                key = Ed25519PublicKey.from_public_bytes(raw)
            else:
                loaded = serialization.load_pem_public_key(raw)
                if not isinstance(loaded, Ed25519PublicKey):
                    raise ValueError(f"key {key_id!r} is not Ed25519")
                key = loaded
            parsed[key_id.strip()] = key
        self._keys = parsed

    def __call__(self, payload: bytes, signature: str, key_id: str) -> bool:
        key = self._keys.get(str(key_id).strip())
        if key is None:
            return False
        try:
            signature_bytes = base64.b64decode(signature, validate=True)
        except Exception:
            return False
        try:
            key.verify(signature_bytes, payload)
        except InvalidSignature:
            return False
        except Exception:
            return False
        return True


class WindowsAuthenticodeVerifier:
    """Verify an Authenticode-signed PE against a manifest-bound thumbprint.

    The payload is written to a temporary file and inspected with
    Get-AuthenticodeSignature. The file is never executed.
    """

    @staticmethod
    def _normalize_thumbprint(value: str) -> str:
        return "".join(ch for ch in str(value).upper() if ch in "0123456789ABCDEF")

    def __call__(self, payload: bytes, expected_thumbprint: str) -> bool:
        expected = self._normalize_thumbprint(expected_thumbprint)
        if os.name != "nt" or not expected:
            return False

        temp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as handle:
                handle.write(payload)
                handle.flush()
                temp_path = handle.name

            env = os.environ.copy()
            env["ALGOFORTIS_AUTHENTICODE_PATH"] = temp_path
            command = (
                "$sig = Get-AuthenticodeSignature -LiteralPath "
                "$env:ALGOFORTIS_AUTHENTICODE_PATH; "
                "if ($sig.Status -ne 'Valid' -or $null -eq $sig.SignerCertificate) { exit 2 }; "
                "Write-Output $sig.SignerCertificate.Thumbprint"
            )
            completed = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
            if completed.returncode != 0:
                return False
            lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
            if not lines:
                return False
            observed = self._normalize_thumbprint(lines[-1])
            return bool(observed) and observed == expected
        except Exception:
            return False
        finally:
            if temp_path:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except Exception:
                    pass
