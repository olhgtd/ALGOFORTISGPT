import pytest

from dashboard.backend.owner_admin.ai_credentials import LocalDPAPIAICredentialStore


class _FakeVault:
    def __init__(self) -> None:
        self.saved = None
        self.deleted = None

    def store_credentials(self, user_id, connection_id, credentials):
        self.saved = (user_id, connection_id, credentials)
        return f"VAULT-{connection_id}"

    def resolve_credentials(self, user_id, credential_ref):
        assert self.saved is not None
        return self.saved[2]

    def delete_credentials(self, user_id, credential_ref):
        self.deleted = (user_id, credential_ref)
        return True


def _store_with(fake: _FakeVault) -> LocalDPAPIAICredentialStore:
    class _Store(LocalDPAPIAICredentialStore):
        @staticmethod
        def _vault():
            return fake

    return _Store()


def test_ai_provider_secret_uses_existing_redacting_vault_envelope() -> None:
    fake = _FakeVault()
    store = _store_with(fake)

    credential_ref = store.store_token(
        user_id="owner-1",
        provider_id="local-ai",
        token="super-secret-provider-token",
    )

    assert credential_ref == "VAULT-ai-provider-local-ai"
    user_id, connection_id, credentials = fake.saved
    assert user_id == "owner-1"
    assert connection_id == "ai-provider-local-ai"
    assert credentials.extra == {
        "credential_kind": "AI_PROVIDER_TOKEN",
        "provider_id": "local-ai",
    }
    assert "super-secret-provider-token" not in repr(credentials)
    assert store.resolve_token(user_id="owner-1", credential_ref=credential_ref) == "super-secret-provider-token"


def test_ai_provider_id_cannot_escape_vault_namespace() -> None:
    store = LocalDPAPIAICredentialStore()
    with pytest.raises(ValueError):
        store._connection_id("../outside")
    with pytest.raises(ValueError):
        store._connection_id("provider/child")


def test_ai_credential_delete_delegates_without_exposing_secret() -> None:
    fake = _FakeVault()
    store = _store_with(fake)
    assert store.delete_token(user_id="owner-1", credential_ref="VAULT-ai-provider-local-ai") is True
    assert fake.deleted == ("owner-1", "VAULT-ai-provider-local-ai")
