"""AlgoFortis V1 — Device Identity Foundation & Storage Manager
Implements ADR-07, ADR-08, ADR-10, ADR-34.
Strict separation of WebAuthn user credentials from Device Identity Keys.
- Preferred provider: Windows CNG/TPM (non-exportable hardware-backed asymmetric key).
- Fallback provider: Software asymmetric key protected via Windows DPAPI.
"""
import os
import json
import uuid
import base64
import hashlib
import ctypes
import ctypes.wintypes
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization

# Device Identity Storage Directory under %LOCALAPPDATA%\AlgoFortis\Security\DeviceIdentity\
def get_device_identity_dir() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        local_appdata = str(Path.home() / "AppData" / "Local")
    path = Path(local_appdata) / "AlgoFortis" / "Security" / "DeviceIdentity"
    path.mkdir(parents=True, exist_ok=True)
    return path


class DeviceKeyProvider(ABC):
    """Abstract provider for hardware-backed or DPAPI-protected asymmetric device keys."""
    
    @abstractmethod
    def get_provider_name(self) -> str:
        pass

    @abstractmethod
    def generate_or_load_key(self, storage_dir: Path) -> Tuple[bytes, str]:
        """Returns (public_key_bytes_der, public_key_fingerprint_sha256)."""
        pass

    @abstractmethod
    def sign_payload(self, storage_dir: Path, payload: bytes) -> bytes:
        """Sign payload using device private key."""
        pass


class WindowsCngTpmKeyProvider(DeviceKeyProvider):
    """Windows CNG / TPM 2.0 hardware-backed non-exportable key provider via NCrypt APIs."""

    PROVIDER_NAME = "Microsoft Platform Crypto Provider"
    KEY_NAME = "AlgoFortis_DeviceIdentity_MasterKey"
    PUBKEY_FILE = "device_key.cng.pub"

    def __init__(self, key_name: Optional[str] = None):
        self.key_name = key_name or self.KEY_NAME

    def get_provider_name(self) -> str:
        return "WINDOWS_CNG_TPM"

    def _open_provider(self) -> ctypes.wintypes.HANDLE:
        hProv = ctypes.wintypes.HANDLE()
        res = ctypes.windll.ncrypt.NCryptOpenStorageProvider(
            ctypes.byref(hProv), self.PROVIDER_NAME, 0
        )
        if res != 0:
            raise RuntimeError(f"TPM_UNAVAILABLE: NCryptOpenStorageProvider failed with error 0x{res & 0xFFFFFFFF:08X}")
        return hProv

    def generate_or_load_key(self, storage_dir: Path) -> Tuple[bytes, str]:
        """Load existing persisted CNG/TPM key or generate a new hardware-bound non-exportable key."""
        pub_file = storage_dir / self.PUBKEY_FILE
        
        hProv = self._open_provider()
        try:
            hKey = ctypes.wintypes.HANDLE()
            # Attempt to open existing persisted key
            res_open = ctypes.windll.ncrypt.NCryptOpenKey(
                hProv, ctypes.byref(hKey), self.key_name, 0, 0
            )

            if res_open != 0:
                # Key does not exist; create fresh persisted non-exportable key in TPM
                res_create = ctypes.windll.ncrypt.NCryptCreatePersistedKey(
                    hProv, ctypes.byref(hKey), "ECDSA_P256", self.key_name, 0, 0
                )
                if res_create != 0:
                    raise RuntimeError(f"NCryptCreatePersistedKey failed: 0x{res_create & 0xFFFFFFFF:08X}")

                # Set non-exportable policy: NCRYPT_EXPORT_POLICY_PROPERTY = 0
                export_policy = ctypes.c_ulong(0)
                ctypes.windll.ncrypt.NCryptSetProperty(
                    hKey, "Export Policy", ctypes.byref(export_policy), ctypes.sizeof(export_policy), 0
                )

                # Finalize key in hardware TPM
                res_fin = ctypes.windll.ncrypt.NCryptFinalizeKey(hKey, 0)
                if res_fin != 0:
                    raise RuntimeError(f"NCryptFinalizeKey failed: 0x{res_fin & 0xFFFFFFFF:08X}")

            # Export public key blob (BCRYPT_ECCPUBLIC_BLOB)
            cbBlob = ctypes.wintypes.DWORD(0)
            res_exp1 = ctypes.windll.ncrypt.NCryptExportKey(
                hKey, ctypes.wintypes.HANDLE(0), "ECCPUBLICBLOB", None, None, 0, ctypes.byref(cbBlob), 0
            )
            if res_exp1 != 0:
                raise RuntimeError(f"NCryptExportKey (size) failed: 0x{res_exp1 & 0xFFFFFFFF:08X}")

            blob_buf = ctypes.create_string_buffer(cbBlob.value)
            res_exp2 = ctypes.windll.ncrypt.NCryptExportKey(
                hKey, ctypes.wintypes.HANDLE(0), "ECCPUBLICBLOB", None, blob_buf, cbBlob.value, ctypes.byref(cbBlob), 0
            )
            if res_exp2 != 0:
                raise RuntimeError(f"NCryptExportKey failed: 0x{res_exp2 & 0xFFFFFFFF:08X}")

            raw_ecc_blob = blob_buf.raw[:cbBlob.value]
            # Convert BCRYPT_ECCKEY_BLOB (Magic 4B, cbKey 4B, X 32B, Y 32B) to standard DER SubjectPublicKeyInfo
            # Magic for P256 Public is 0x31534345 ("ECS1")
            x = raw_ecc_blob[8:40]
            y = raw_ecc_blob[40:72]
            raw_uncompressed_point = b"\x04" + x + y
            pubkey_obj = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), raw_uncompressed_point)
            pub_der = pubkey_obj.public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )

            fingerprint = hashlib.sha256(pub_der).hexdigest()
            # Cache public key DER on disk
            pub_file.write_bytes(pub_der)

            ctypes.windll.ncrypt.NCryptFreeObject(hKey)
            return pub_der, fingerprint
        finally:
            ctypes.windll.ncrypt.NCryptFreeObject(hProv)

    def sign_payload(self, storage_dir: Path, payload: bytes) -> bytes:
        """Sign a payload using the hardware TPM non-exportable private key."""
        hProv = self._open_provider()
        try:
            hKey = ctypes.wintypes.HANDLE()
            res_open = ctypes.windll.ncrypt.NCryptOpenKey(
                hProv, ctypes.byref(hKey), self.key_name, 0, 0
            )
            if res_open != 0:
                raise FileNotFoundError(f"TPM hardware key '{self.key_name}' missing: fail-closed")

            digest = hashlib.sha256(payload).digest()
            cbSig = ctypes.wintypes.DWORD(0)
            res_sign1 = ctypes.windll.ncrypt.NCryptSignHash(
                hKey, None, digest, len(digest), None, 0, ctypes.byref(cbSig), 0
            )
            if res_sign1 != 0:
                raise RuntimeError(f"NCryptSignHash (size) failed: 0x{res_sign1 & 0xFFFFFFFF:08X}")

            sig_buf = ctypes.create_string_buffer(cbSig.value)
            res_sign2 = ctypes.windll.ncrypt.NCryptSignHash(
                hKey, None, digest, len(digest), sig_buf, cbSig.value, ctypes.byref(cbSig), 0
            )
            if res_sign2 != 0:
                raise RuntimeError(f"NCryptSignHash failed: 0x{res_sign2 & 0xFFFFFFFF:08X}")

            ctypes.windll.ncrypt.NCryptFreeObject(hKey)
            return sig_buf.raw[:cbSig.value]
        finally:
            ctypes.windll.ncrypt.NCryptFreeObject(hProv)


class DpapiSoftwareKeyProvider(DeviceKeyProvider):
    """Windows DPAPI-protected software EC (SECP256R1 / P-256) fallback key provider."""
    
    KEY_FILE = "device_key.dpapi"

    def get_provider_name(self) -> str:
        return "WINDOWS_DPAPI_SOFTWARE"

    def _dpapi_protect(self, data: bytes) -> bytes:
        """Protect data using Windows DPAPI (CryptProtectData)."""
        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", ctypes.wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        try:
            in_buf = ctypes.create_string_buffer(data)
            in_blob = DATA_BLOB(len(data), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_char)))
            out_blob = DATA_BLOB()

            res = ctypes.windll.crypt32.CryptProtectData(
                ctypes.byref(in_blob),
                "AlgoFortis Device Key",
                None,
                None,
                None,
                0x01,  # CRYPTPROTECT_UI_FORBIDDEN
                ctypes.byref(out_blob)
            )
            if not res:
                raise RuntimeError(f"CryptProtectData failed with error {ctypes.GetLastError()}")

            protected = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)
            return protected
        except Exception as e:
            raise RuntimeError(f"Windows DPAPI protection failed: {e}")

    def _dpapi_unprotect(self, data: bytes) -> bytes:
        """Unprotect data using Windows DPAPI (CryptUnprotectData)."""
        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", ctypes.wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        try:
            in_buf = ctypes.create_string_buffer(data)
            in_blob = DATA_BLOB(len(data), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_char)))
            out_blob = DATA_BLOB()

            res = ctypes.windll.crypt32.CryptUnprotectData(
                ctypes.byref(in_blob),
                None,
                None,
                None,
                None,
                0x01,  # CRYPTPROTECT_UI_FORBIDDEN
                ctypes.byref(out_blob)
            )
            if not res:
                raise RuntimeError(f"CryptUnprotectData failed with error {ctypes.GetLastError()}")

            unprotected = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)
            return unprotected
        except Exception as e:
            raise ValueError(f"Corrupt or invalid DPAPI key blob: {e}")

    def generate_or_load_key(self, storage_dir: Path) -> Tuple[bytes, str]:
        key_path = storage_dir / self.KEY_FILE
        if key_path.exists():
            protected_blob = key_path.read_bytes()
            raw_pem = self._dpapi_unprotect(protected_blob)
            private_key = serialization.load_pem_private_key(raw_pem, password=None)
        else:
            private_key = ec.generate_private_key(ec.SECP256R1())
            raw_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
            protected_blob = self._dpapi_protect(raw_pem)
            key_path.write_bytes(protected_blob)

        pub_der = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        fingerprint = hashlib.sha256(pub_der).hexdigest()
        return pub_der, fingerprint

    def sign_payload(self, storage_dir: Path, payload: bytes) -> bytes:
        key_path = storage_dir / self.KEY_FILE
        if not key_path.exists():
            raise FileNotFoundError("Device private key material missing: fail-closed")
        raw_pem = self._dpapi_unprotect(key_path.read_bytes())
        private_key = serialization.load_pem_private_key(raw_pem, password=None)
        signature = private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
        return signature


def get_preferred_device_key_provider(force_provider: Optional[str] = None) -> DeviceKeyProvider:
    """Selects the preferred provider (Windows CNG/TPM) and falls back to DPAPI if TPM is unavailable."""
    if force_provider == "DPAPI":
        return DpapiSoftwareKeyProvider()
    elif force_provider == "CNG_TPM":
        return WindowsCngTpmKeyProvider()

    # Automatic Probe: attempt TPM provider
    try:
        tpm = WindowsCngTpmKeyProvider()
        hProv = tpm._open_provider()
        ctypes.windll.ncrypt.NCryptFreeObject(hProv)
        return tpm
    except Exception:
        # Graceful fallback to DPAPI software provider
        return DpapiSoftwareKeyProvider()


class DeviceIdentityManager:
    """Manages machine-bound cryptographic device identification."""

    METADATA_FILE = "device_identity.json"
    SCHEMA_VERSION = "AlgoFortisDeviceIdentity/v1"

    def __init__(self, storage_dir: Optional[Path] = None, provider: Optional[DeviceKeyProvider] = None):
        self.storage_dir = storage_dir or get_device_identity_dir()
        self.provider = provider or get_preferred_device_key_provider()

    def get_or_create_identity(self) -> Dict[str, Any]:
        """Load existing device identity or generate a new cryptographically bound device ID."""
        meta_path = self.storage_dir / self.METADATA_FILE
        
        if meta_path.exists():
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                if data.get("schema_version") != self.SCHEMA_VERSION:
                    raise ValueError("Incompatible device identity schema version")
                # Verify key material exists and matches fingerprint
                _, active_fp = self.provider.generate_or_load_key(self.storage_dir)
                if data.get("public_key_fingerprint") != active_fp:
                    raise ValueError("Device identity public key fingerprint mismatch: fail-closed")
                return data
            except Exception as e:
                # Fail closed on corruption
                raise RuntimeError(f"Device identity validation failed: {e}")

        # Create fresh identity
        pub_der, fingerprint = self.provider.generate_or_load_key(self.storage_dir)
        device_id = f"dev_{uuid.uuid4().hex[:16]}"
        
        metadata = {
            "schema_version": self.SCHEMA_VERSION,
            "device_id": device_id,
            "provider": self.provider.get_provider_name(),
            "public_key_fingerprint": fingerprint,
            "public_key_der_b64": base64.b64encode(pub_der).decode("ascii"),
            "enrolled_at_utc": "2026-09-14T22:00:00Z"
        }
        
        meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return metadata

    def sign_device_challenge(self, challenge: bytes) -> bytes:
        """Cryptographically sign a challenge using the device identity private key."""
        return self.provider.sign_payload(self.storage_dir, challenge)
