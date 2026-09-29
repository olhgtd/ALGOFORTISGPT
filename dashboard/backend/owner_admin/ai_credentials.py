"""AI provider credential storage through the existing local DPAPI authority.

This module deliberately reuses LocalCredentialVault instead of creating a
second secret database. Plaintext provider tokens exist only for the duration
of the request/store call, are encrypted with Owner user entropy, and are never
returned to the caller or persisted in SQLite.
"""
from __future__ import annotations

from typing import Protocol

from dashboard.backend.credential_vault import BrokerCredentials, LocalCredentialVault


class AICredentialStore(Protocol):
    def store_token(self, *, user_id: str, provider_id: str, token: str) -> str: ...
    def delete_token(self, *, user_id: str, credential_ref: str) -> bool: ...
    def resolve_token(self, *, user_id: str, credential_ref: str) -> str: ...


class LocalDPAPIAICredentialStore:
    """Thin AI namespace over the already-qualified Windows DPAPI vault."""

    @staticmethod
    def _vault() -> LocalCredentialVault:
        # Construct lazily so merely importing/starting non-Windows tooling does
        # not perform DPAPI work. Runtime credential operations remain Windows-only.
        return LocalCredentialVault()

    @staticmethod
    def _connection_id(provider_id: str) -> str:
        clean = "".join(ch for ch in str(provider_id) if ch.isalnum() or ch in ("-", "_", "."))
        if not clean or clean != str(provider_id):
            raise ValueError("provider_id contains unsupported credential-vault characters")
        return f"ai-provider-{clean}"

    def store_token(self, *, user_id: str, provider_id: str, token: str) -> str:
        secret = str(token)
        if not secret or not secret.strip():
            raise ValueError("AI provider credential must be non-empty")
        # BrokerCredentials is the existing redacting DPAPI payload envelope.
        # The marker prevents consumers from mistaking this blob for a broker credential.
        payload = BrokerCredentials(
            api_key=secret,
            access_token=secret,
            extra={"credential_kind": "AI_PROVIDER_TOKEN", "provider_id": provider_id},
        )
        return self._vault().store_credentials(
            str(user_id),
            self._connection_id(provider_id),
            payload,
        )

    def delete_token(self, *, user_id: str, credential_ref: str) -> bool:
        return self._vault().delete_credentials(str(user_id), credential_ref)

    def resolve_token(self, *, user_id: str, credential_ref: str) -> str:
        credentials = self._vault().resolve_credentials(str(user_id), credential_ref)
        if credentials.extra.get("credential_kind") != "AI_PROVIDER_TOKEN":
            raise PermissionError("credential reference is not an AI provider credential")
        return credentials.access_token or credentials.api_key
