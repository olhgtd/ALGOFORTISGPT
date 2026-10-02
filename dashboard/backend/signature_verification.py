"""Cryptographic signature verification adapters for release/account artifacts.

Only public verification material belongs here. Production private signing keys
remain outside the client and outside source control.
"""
from __future__ import annotations

import base64
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
