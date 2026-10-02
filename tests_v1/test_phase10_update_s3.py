"""Phase 10 S3 update-policy and signed-manifest qualification tests."""
from __future__ import annotations

import hashlib
import json

import pytest

from dashboard.backend.account_v2.policy_seams import UpdateSafeWindowPolicy
from dashboard.backend.update_service import UpdateChannel, UpdateService


class _DeterministicSignatureVerifier:
    """Test verifier for the production verification seam."""

    def verify(self, *, payload: bytes, signature: str, key_id: str) -> bool:
        return bool(payload) and key_id == "test-release-key" and signature == "VALID_SIGNATURE"


def _manifest_json(*, channel: str = "STABLE", signature: str = "VALID_SIGNATURE") -> str:
    payload = b"phase10-installer"
    return json.dumps(
        {
            "version": "9.1.0",
            "channel": channel,
            "installer_url": "https://updates.example.invalid/AlgoFortis-Setup-9.1.0.exe",
            "sha256_checksum": hashlib.sha256(payload).hexdigest(),
            "min_compatible_version": "9.0.0",
            "security_critical": False,
            "release_notes": "Phase 10 qualification fixture.",
            "signing_key_id": "test-release-key",
            "manifest_signature": signature,
        }
    )


def _safe_policy(*, allowed_states: tuple[str, ...] = ("IDLE",)) -> UpdateSafeWindowPolicy:
    return UpdateSafeWindowPolicy(
        policy_id="updates/safe-window/v1",
        version="1",
        allowed_engine_states=allowed_states,
        allow_open_positions=False,
        session_calendar_ref="calendar/india-index/v1",
        applicability="APPLICABLE",
    )


def _service(*, channel: UpdateChannel = UpdateChannel.STABLE) -> UpdateService:
    return UpdateService(
        current_version="9.0.0",
        channel=channel,
        signature_verifier=_DeterministicSignatureVerifier(),
    )


def test_manifest_requires_signature_metadata_and_verifier() -> None:
    unsigned = json.loads(_manifest_json())
    unsigned.pop("manifest_signature")

    with pytest.raises(ValueError, match="manifest_signature"):
        _service().parse_and_validate_manifest(json.dumps(unsigned))

    with pytest.raises(ValueError, match="signature verifier"):
        UpdateService(current_version="9.0.0").parse_and_validate_manifest(_manifest_json())


def test_manifest_signature_failure_is_fail_closed() -> None:
    with pytest.raises(ValueError, match="signature"):
        _service().parse_and_validate_manifest(_manifest_json(signature="INVALID_SIGNATURE"))


def test_channel_mismatch_is_not_update_ready() -> None:
    manifest = _service().parse_and_validate_manifest(_manifest_json(channel="BETA"))
    decision = _service().evaluate_apply_decision(
        manifest,
        policy=_safe_policy(),
        engine_state="IDLE",
        has_open_positions=False,
        live_state="DISARMED",
    )

    assert decision.allowed is False
    assert decision.reason == "UPDATE_CHANNEL_MISMATCH"
    assert decision.auto_arm_live is False


def test_missing_or_inapplicable_safe_window_defers_update() -> None:
    manifest = _service().parse_and_validate_manifest(_manifest_json())

    missing = _service().evaluate_apply_decision(
        manifest,
        policy=None,
        engine_state="IDLE",
        has_open_positions=False,
        live_state="DISARMED",
    )
    assert missing.allowed is False
    assert missing.reason == "UPDATE_POLICY_UNAVAILABLE"

    inapplicable = UpdateSafeWindowPolicy(
        policy_id="updates/safe-window/v1",
        version="1",
        allowed_engine_states=("IDLE",),
        allow_open_positions=False,
        session_calendar_ref="calendar/india-index/v1",
        applicability="STALE",
    )
    stale = _service().evaluate_apply_decision(
        manifest,
        policy=inapplicable,
        engine_state="IDLE",
        has_open_positions=False,
        live_state="DISARMED",
    )
    assert stale.allowed is False
    assert stale.reason == "UPDATE_POLICY_NOT_APPLICABLE"


def test_active_engine_or_open_positions_block_update_even_if_manifest_is_valid() -> None:
    manifest = _service().parse_and_validate_manifest(_manifest_json())

    active = _service().evaluate_apply_decision(
        manifest,
        policy=_safe_policy(allowed_states=("ACTIVE", "IDLE")),
        engine_state="ACTIVE",
        has_open_positions=False,
        live_state="DISARMED",
    )
    assert active.allowed is False
    assert active.reason == "ENGINE_ACTIVE_BLOCKS_UPDATE"

    positions = _service().evaluate_apply_decision(
        manifest,
        policy=_safe_policy(),
        engine_state="IDLE",
        has_open_positions=True,
        live_state="DISARMED",
    )
    assert positions.allowed is False
    assert positions.reason == "OPEN_POSITIONS_BLOCK_UPDATE"


def test_safe_update_is_allowed_only_while_live_remains_disarmed() -> None:
    manifest = _service().parse_and_validate_manifest(_manifest_json())

    allowed = _service().evaluate_apply_decision(
        manifest,
        policy=_safe_policy(),
        engine_state="IDLE",
        has_open_positions=False,
        live_state="DISARMED",
    )
    assert allowed.allowed is True
    assert allowed.reason == "UPDATE_SAFE_WINDOW_ALLOWED"
    assert allowed.auto_arm_live is False

    armed = _service().evaluate_apply_decision(
        manifest,
        policy=_safe_policy(),
        engine_state="IDLE",
        has_open_positions=False,
        live_state="ARMED",
    )
    assert armed.allowed is False
    assert armed.reason == "LIVE_STATE_NOT_DISARMED"
    assert armed.auto_arm_live is False
