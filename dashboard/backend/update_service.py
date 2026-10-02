"""AlgoFortis V2 — S3 fail-closed update verification.

Track-P / S3 responsibilities:
- update manifests are signature verified before use;
- installer payloads require both SHA-256 integrity and signature verification;
- application/restart/migration is allowed only through the existing versioned
  UpdateSafeWindowPolicy seam;
- missing/invalid/inapplicable policy defers the update;
- update application never grants or restores Live ARM authority.

Production signing keys and verification adapters remain external release
configuration. The service deliberately has no permissive fallback verifier.
"""
from __future__ import annotations

import enum
import hashlib
import json
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urlparse

from dashboard.backend.account_v2.policy_seams import (
    UpdateSafeWindowPolicy,
    evaluate_update_safe_window,
)


class UpdateChannel(str, enum.Enum):
    STABLE = "STABLE"
    BETA = "BETA"


SignatureVerifier = Callable[[bytes, str, str], bool]


@dataclass(frozen=True)
class UpdateManifest:
    version: str
    channel: UpdateChannel
    installer_url: str
    sha256_checksum: str
    min_compatible_version: str
    security_critical: bool
    release_notes: str
    signing_key_id: str
    manifest_signature: str
    installer_signer_id: str
    installer_signature: str
    safe_window_policy_id: str
    safe_window_policy_version: str


@dataclass(frozen=True)
class UpdateApplyDecision:
    allowed: bool
    reason: str
    auto_arm_live: bool = False


class UpdateService:
    """Verify update evidence and resolve whether an update may be applied."""

    def __init__(
        self,
        current_version: str = "9.0.0",
        channel: UpdateChannel = UpdateChannel.STABLE,
        *,
        manifest_signature_verifier: Optional[SignatureVerifier] = None,
        installer_signature_verifier: Optional[SignatureVerifier] = None,
    ):
        self.current_version = current_version
        self.channel = channel
        self._manifest_signature_verifier = manifest_signature_verifier
        self._installer_signature_verifier = installer_signature_verifier

    @staticmethod
    def canonical_manifest_bytes(data: dict) -> bytes:
        """Canonical bytes covered by the detached manifest signature."""
        unsigned = dict(data)
        unsigned.pop("manifest_signature", None)
        return json.dumps(
            unsigned,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    @staticmethod
    def _require_non_empty(data: dict, field: str) -> str:
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Invalid update manifest: missing field '{field}'")
        return value.strip()

    def parse_and_validate_manifest(self, manifest_json: str) -> UpdateManifest:
        """Parse and signature-verify a manifest. There is no unsigned fallback."""
        try:
            data = json.loads(manifest_json)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid update manifest: malformed JSON") from exc
        if not isinstance(data, dict):
            raise ValueError("Invalid update manifest: top level must be an object")

        required_fields = (
            "version",
            "channel",
            "installer_url",
            "sha256_checksum",
            "min_compatible_version",
            "signing_key_id",
            "manifest_signature",
            "installer_signer_id",
            "installer_signature",
            "safe_window_policy_id",
            "safe_window_policy_version",
        )
        values = {field: self._require_non_empty(data, field) for field in required_fields}

        try:
            channel = UpdateChannel(values["channel"])
        except ValueError as exc:
            raise ValueError("Invalid update manifest: unsupported channel") from exc
        if channel is not self.channel:
            raise ValueError(
                f"Invalid update manifest: channel mismatch ({channel.value} != {self.channel.value})"
            )

        checksum = values["sha256_checksum"].lower()
        if len(checksum) != 64 or any(ch not in "0123456789abcdef" for ch in checksum):
            raise ValueError("Invalid update manifest: sha256_checksum must be 64 lowercase hex chars")

        parsed_url = urlparse(values["installer_url"])
        if parsed_url.scheme.lower() != "https" or not parsed_url.netloc:
            raise ValueError("Invalid update manifest: installer_url must use HTTPS")

        if self._manifest_signature_verifier is None:
            raise ValueError("UPDATE_MANIFEST_SIGNATURE_VERIFIER_UNAVAILABLE")
        canonical = self.canonical_manifest_bytes(data)
        try:
            signature_valid = bool(
                self._manifest_signature_verifier(
                    canonical,
                    values["manifest_signature"],
                    values["signing_key_id"],
                )
            )
        except Exception as exc:
            raise ValueError("UPDATE_MANIFEST_SIGNATURE_INVALID") from exc
        if not signature_valid:
            raise ValueError("UPDATE_MANIFEST_SIGNATURE_INVALID")

        return UpdateManifest(
            version=values["version"],
            channel=channel,
            installer_url=values["installer_url"],
            sha256_checksum=checksum,
            min_compatible_version=values["min_compatible_version"],
            security_critical=bool(data.get("security_critical", False)),
            release_notes=str(data.get("release_notes", "")),
            signing_key_id=values["signing_key_id"],
            manifest_signature=values["manifest_signature"],
            installer_signer_id=values["installer_signer_id"],
            installer_signature=values["installer_signature"],
            safe_window_policy_id=values["safe_window_policy_id"],
            safe_window_policy_version=values["safe_window_policy_version"],
        )

    def verify_installer_payload(self, installer_bytes: bytes, manifest: UpdateManifest) -> bool:
        """Require digest integrity and a trusted installer signature."""
        computed_sha = hashlib.sha256(installer_bytes).hexdigest().lower()
        if computed_sha != manifest.sha256_checksum:
            raise ValueError(
                f"INTEGRITY ERROR: Downloaded installer SHA-256 ({computed_sha}) does not "
                f"match manifest expectation ({manifest.sha256_checksum})."
            )

        if self._installer_signature_verifier is None:
            raise ValueError("UPDATE_INSTALLER_SIGNATURE_VERIFIER_UNAVAILABLE")
        try:
            signature_valid = bool(
                self._installer_signature_verifier(
                    installer_bytes,
                    manifest.installer_signature,
                    manifest.installer_signer_id,
                )
            )
        except Exception as exc:
            raise ValueError("UPDATE_INSTALLER_SIGNATURE_INVALID") from exc
        if not signature_valid:
            raise ValueError("UPDATE_INSTALLER_SIGNATURE_INVALID")
        return True

    def evaluate_apply_decision(
        self,
        manifest: UpdateManifest,
        policy: UpdateSafeWindowPolicy | None,
        *,
        engine_state: str,
        has_open_positions: bool,
    ) -> UpdateApplyDecision:
        """Resolve INV-20 through the frozen S2 policy seam.

        This method never contains a production clock window and never auto-arms
        Live. Policy identity/version must exactly match the signed manifest.
        """
        if manifest.channel is not self.channel:
            return UpdateApplyDecision(False, "UPDATE_CHANNEL_MISMATCH")
        if policy is None:
            return UpdateApplyDecision(False, "UPDATE_POLICY_UNAVAILABLE")
        if (
            policy.policy_id != manifest.safe_window_policy_id
            or policy.version != manifest.safe_window_policy_version
        ):
            return UpdateApplyDecision(False, "UPDATE_POLICY_REFERENCE_MISMATCH")

        decision = evaluate_update_safe_window(
            policy,
            engine_state=engine_state,
            has_open_positions=has_open_positions,
        )
        return UpdateApplyDecision(
            allowed=decision.allowed,
            reason=decision.reason,
            auto_arm_live=False,
        )
