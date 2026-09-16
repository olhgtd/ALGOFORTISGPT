"""AlgoFortis V1 — Area 8: Local Credential Vault (DPAPI/CNG) Tests (Phase 2)
Verifies:
- DPAPI round trip: store credentials & resolve credentials
- Multi-user isolation: User A credentials cannot be decrypted by User B (fails closed)
- Redaction on logging/printing: BrokerCredentials.__repr__ and __str__ never leak secret values
- Corrupt/tampered encrypted file fails closed with CredentialDecryptionError
- Deletion of credentials
- Integration with SecurityStore: set_connection_credentials & get_connection_credentials
- Multi-broker operational connection resolution & filtering
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

root_dir = Path(__file__).resolve().parents[1]
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from dashboard.backend.credential_vault import (
    BrokerCredentials,
    CredentialDecryptionError,
    CredentialNotFoundError,
    LocalCredentialVault,
)
from dashboard.backend.security_store import SQLiteSecurityStore


class TestCredentialVault(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.vault = LocalCredentialVault(vault_dir=self.temp_dir / "vault")
        self.db_path = self.temp_dir / "security.sqlite"
        self.store = SQLiteSecurityStore(str(self.db_path))

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_credential_vault_roundtrip(self):
        user_id = "user_alpha_123"
        conn_id = "CONN-UPSTOX-01"
        creds = BrokerCredentials(
            api_key="my_upstox_api_key",
            api_secret="my_super_secret_secret",
            access_token="live_bearer_token_abc",
            extra={"client_id": "CLIENT999"},
        )

        cred_ref = self.vault.store_credentials(user_id, conn_id, creds)
        self.assertTrue(cred_ref.startswith("VAULT-"))
        self.assertTrue(self.vault.has_credentials(user_id, cred_ref))

        resolved = self.vault.resolve_credentials(user_id, cred_ref)
        self.assertEqual(resolved.api_key, "my_upstox_api_key")
        self.assertEqual(resolved.api_secret, "my_super_secret_secret")
        self.assertEqual(resolved.access_token, "live_bearer_token_abc")
        self.assertEqual(resolved.extra["client_id"], "CLIENT999")

        token = self.vault.resolve_token(user_id, cred_ref)
        self.assertEqual(token, "live_bearer_token_abc")

    def test_wrong_user_cannot_decrypt(self):
        user_a = "user_alpha_123"
        user_b = "user_beta_456"
        conn_id = "CONN-ZERODHA-01"

        creds = BrokerCredentials(
            api_key="kite_api_key",
            api_secret="kite_api_secret",
            access_token="kite_access_token",
        )

        cred_ref = self.vault.store_credentials(user_a, conn_id, creds)

        # User A decrypts successfully
        resolved = self.vault.resolve_credentials(user_a, cred_ref)
        self.assertEqual(resolved.api_key, "kite_api_key")

        # User B cannot decrypt User A's credential - fails closed with CredentialDecryptionError
        with self.assertRaises(CredentialDecryptionError):
            self.vault.resolve_credentials(user_b, cred_ref)

    def test_logging_redaction(self):
        creds = BrokerCredentials(
            api_key="my_secret_key_12345",
            api_secret="super_confidential_secret",
            access_token="token_xyz_top_secret",
            refresh_token="refresh_secret",
            pin_or_totp="123456",
        )

        repr_str = repr(creds)
        str_str = str(creds)

        # Plaintext secrets must never appear in repr or str
        self.assertNotIn("super_confidential_secret", repr_str)
        self.assertNotIn("token_xyz_top_secret", repr_str)
        self.assertNotIn("refresh_secret", repr_str)
        self.assertNotIn("123456", repr_str)

        self.assertNotIn("super_confidential_secret", str_str)
        self.assertNotIn("token_xyz_top_secret", str_str)

    def test_corrupt_secret_fails_closed(self):
        user_id = "user_gamma"
        conn_id = "CONN-DHAN-01"
        creds = BrokerCredentials(api_key="dhan_key", access_token="dhan_token")

        cred_ref = self.vault.store_credentials(user_id, conn_id, creds)

        # Corrupt the file
        file_path = self.vault._file_path(cred_ref)
        file_path.write_bytes(b"corrupted_random_gibberish_bytes_not_dpapi")

        with self.assertRaises(CredentialDecryptionError):
            self.vault.resolve_credentials(user_id, cred_ref)

    def test_missing_credential_raises_not_found(self):
        with self.assertRaises(CredentialNotFoundError):
            self.vault.resolve_credentials("user_1", "VAULT-nonexistent")

    def test_delete_credentials(self):
        user_id = "user_delta"
        conn_id = "CONN-ANGEL-01"
        creds = BrokerCredentials(api_key="angel_key", access_token="angel_token")

        cred_ref = self.vault.store_credentials(user_id, conn_id, creds)
        self.assertTrue(self.vault.has_credentials(user_id, cred_ref))

        deleted = self.vault.delete_credentials(user_id, cred_ref)
        self.assertTrue(deleted)
        self.assertFalse(self.vault.has_credentials(user_id, cred_ref))

    def test_security_store_vault_integration(self):
        user_id = uuid4()
        self.store.ensure_user(
            user_id=user_id,
            display_name="Alpha Trader",
            role="USER",
            lifecycle="ACTIVE",
        )

        # Create connection for Upstox
        conn_upstox = self.store.create_user_connection(
            user_id=user_id,
            provider="UPSTOX",
            account_ref="UPSTOX_ACC_01",
        )
        conn_id_up = conn_upstox["connectionId"]

        # Store credentials via security store helper
        self.store.set_connection_credentials(
            connection_id=conn_id_up,
            user_id=user_id,
            credentials=BrokerCredentials(api_key="up_key", access_token="up_tok"),
            vault=self.vault,
        )

        # Create second connection for Zerodha
        conn_kite = self.store.create_user_connection(
            user_id=user_id,
            provider="KITE",
            account_ref="ZERODHA_ACC_02",
        )
        conn_id_kite = conn_kite["connectionId"]

        self.store.set_connection_credentials(
            connection_id=conn_id_kite,
            user_id=user_id,
            credentials=BrokerCredentials(api_key="kite_key", access_token="kite_tok"),
            vault=self.vault,
        )

        # Retrieve and decrypt credentials
        creds_up = self.store.get_connection_credentials(
            connection_id=conn_id_up,
            user_id=user_id,
            vault=self.vault,
        )
        self.assertEqual(creds_up.api_key, "up_key")
        self.assertEqual(creds_up.access_token, "up_tok")

        creds_kite = self.store.get_connection_credentials(
            connection_id=conn_id_kite,
            user_id=user_id,
            vault=self.vault,
        )
        self.assertEqual(creds_kite.api_key, "kite_key")
        self.assertEqual(creds_kite.access_token, "kite_tok")

        # Multi-broker operational connection resolution
        op_up = self.store.get_operational_connection(user_id, provider="UPSTOX")
        self.assertIsNotNone(op_up)
        self.assertEqual(op_up["provider"], "UPSTOX")

        op_kite = self.store.get_operational_connection(user_id, provider="KITE")
        self.assertIsNotNone(op_kite)
        self.assertEqual(op_kite["provider"], "KITE")

        op_by_id = self.store.get_operational_connection(user_id, connection_id=conn_id_up)
        self.assertIsNotNone(op_by_id)
        self.assertEqual(op_by_id["connectionId"], conn_id_up)


if __name__ == "__main__":
    unittest.main()
