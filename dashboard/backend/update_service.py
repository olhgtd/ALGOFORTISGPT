"""AlgoFortis update authority for Track-P S3 and Phase 10 qualification.

Carries forward the V1 update foundation and binds it to OD-V2-20:
- signed manifest verification through an explicit verifier seam;
- SHA-256 payload integrity;
- versioned UpdateSafeWindowPolicy;
- no update while ACTIVE / unsafe open positions;
- update/restart never auto-arms Live.
"""
from __future__ import annotations

import enum
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Protocol

from dashboard.backend.account_v2.policy_seams import (
    UpdateSafeWindowPolicy,
    evaluate_update_safe_window,
)


class UpdateChannel(str, enum.Enum):
    STABLE = "STABLE"
    BETA = "BETA"


class ManifestSignatureVerifier(Protocol):
    def verify(self, *, payload: bytes, signature: str, key_id: str) -> bool: ...


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


@dataclass(frozen=True)
class UpdateApplicationDecision:
    allowed: bool
    reason: str
    auto_arm_live: bool = False


class UpdateService:
    """Validates release manifests and evaluates whether an update may be applied."""

    def __init__(
        self,
        current_version: str = "9.0.0",
        channel: UpdateChannel = UpdateChannel.STABLE,
        *,
        signature_verifier: ManifestSignatureVerifier | None = None,
    ):
        self.current_version = current_version
        self.channel = channel
        self._signature_verifier = signature_verifier

    @staticmethod
    def _signature_payload(data: dict[str, object]) -> bytes:
        signed = dict(data)
        signed.pop("manifest_signature", None)
        return json.dumps(
            signed,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    def parse_and_validate_manifest(self, manifest_json: str) -> UpdateManifest:
        """Parse and authenticate a release manifest.

        Missing signature authority is fail-closed. The verifier itself is
        injected so production signing keys never live in application code.
        """
        data = json.loads(manifest_json)
        if not isinstance(data, dict):
            raise ValueError("Invalid update manifest: root must be an object")

        required_fields = (
            "version",
            "channel",
            "installer_url",
            "sha256_checksum",
            "min_compatible_version",
            "signing_key_id",
            "manifest_signature",
        )
        for field in required_fields:
            value = data.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                raise ValueError(f"Invalid update manifest: missing field '{field}'")

        checksum = str(data["sha256_checksum"]).lower()
        if re.fullmatch(r"[0-9a-f]{64}", checksum) is None:
            raise ValueError("Invalid update manifest: sha256_checksum must be 64 hex characters")

        try:
            channel = UpdateChannel(str(data["channel"]))
        except ValueError as exc:
            raise ValueError("Invalid update manifest: unsupported channel") from exc

        if self._signature_verifier is None:
            raise ValueError("Invalid update manifest: signature verifier is required")

        key_id = str(data["signing_key_id"])
        signature = str(data["manifest_signature"])
        if not self._signature_verifier.verify(
            payload=self._signature_payload(data),
            signature=signature,
            key_id=key_id,
        ):
            raise ValueError("Invalid update manifest: signature verification failed")

        return UpdateManifest(
            version=str(data["version"]),
            channel=channel,
            installer_url=str(data["installer_url"]),
            sha256_checksum=checksum,
            min_compatible_version=str(data["min_compatible_version"]),
            security_critical=bool(data.get("security_critical", False)),
            release_notes=str(data.get("release_notes", "")),
            signing_key_id=key_id,
            manifest_signature=signature,
        )

    def verify_installer_payload(self, installer_bytes: bytes, manifest: UpdateManifest) -> bool:
        """Verify downloaded installer bytes against the signed manifest digest."""
        computed_sha = hashlib.sha256(installer_bytes).hexdigest().lower()
        if computed_sha != manifest.sha256_checksum:
            raise ValueError(
                f"INTEGRITY ERROR: Downloaded installer SHA-256 ({computed_sha}) does not "
                f"match manifest expectation ({manifest.sha256_checksum})."
            )
        return True

    def evaluate_apply_decision(
        self,
        manifest: UpdateManifest,
        *,
        policy: UpdateSafeWindowPolicy | None,
        engine_state: str,
        has_open_positions: bool,
        live_state: str,
    ) -> UpdateApplicationDecision:
        """Return a fail-closed apply/defer decision without changing runtime state."""
        if live_state != "DISARMED":
            return UpdateApplicationDecision(False, "LIVE_STATE_NOT_DISARMED")
        # OD-V2-20 is stricter than any configured allowed-state tuple.
        if engine_state == "ACTIVE":
            return UpdateApplicationDecision(False, "ENGINE_ACTIVE_BLOCKS_UPDATE")
        if manifest.channel != self.channel:
            return UpdateApplicationDecision(False, "UPDATE_CHANNEL_MISMATCH")

        safe_window = evaluate_update_safe_window(
            policy,
            engine_state=engine_state,
            has_open_positions=has_open_positions,
        )
        return UpdateApplicationDecision(
            allowed=safe_window.allowed,
            reason=safe_window.reason,
            auto_arm_live=False,
        )
