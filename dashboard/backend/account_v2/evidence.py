"""Deterministic GP-S2 evidence markers.

The probe is intentionally side-effect free and carries no broker or Live
mutation capability.  Fingerprints are canonical SHA-256 digests over fixed
S2 safety-contract fixtures so Windows runners can compare byte-for-byte.
"""
from __future__ import annotations

import hashlib
import json
from typing import Mapping


_MARKER_ORDER = (
    "S2_SCHEMA_VERSION",
    "ACCOUNT_AUTHORITY_FINGERPRINT",
    "DEVICE_REPROOF_FINGERPRINT",
    "SESSION_REPLAY_RESULT",
    "CROSS_USER_ESCAPE_COUNT",
    "OUTAGE_GATE_STATUS",
    "OUTAGE_RUNTIME_MODE",
    "DEVICE_LIMIT",
    "PRODUCTION_DOMAIN",
    "LIVE_STATE",
    "BROKER_MUTATION_CAPABILITY",
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _fixture_fingerprint(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def build_gp_s2_evidence() -> dict[str, str]:
    account_authority_fixture = {
        "schema": "s2-account-authority/v1",
        "scope": "SELF_SCOPED",
        "required_audit": "FAIL_CLOSED",
        "recovery": "REVOKE_ALL_TARGET_ONLY",
        "cloud_trading_authority": False,
    }
    device_reproof_fixture = {
        "schema": "s2-device-reproof/v1",
        "proof": "P256_SIGNATURE",
        "metadata_trust_anchor": False,
        "same_logical_device": True,
        "missing_key": "FRESH_ENROLLMENT",
    }
    return {
        "S2_SCHEMA_VERSION": "s2-account-gate/v1",
        "ACCOUNT_AUTHORITY_FINGERPRINT": _fixture_fingerprint(account_authority_fixture),
        "DEVICE_REPROOF_FINGERPRINT": _fixture_fingerprint(device_reproof_fixture),
        "SESSION_REPLAY_RESULT": "FAMILY_REVOKED",
        "CROSS_USER_ESCAPE_COUNT": "0",
        "OUTAGE_GATE_STATUS": "AUTHORITY_UNAVAILABLE",
        "OUTAGE_RUNTIME_MODE": "LOCAL_SAFETY_ONLY",
        "DEVICE_LIMIT": "3",
        "PRODUCTION_DOMAIN": "PENDING_EXTERNAL",
        "LIVE_STATE": "READ_ONLY/DISARMED",
        "BROKER_MUTATION_CAPABILITY": "ABSENT",
    }


def render_gp_s2_evidence(evidence: Mapping[str, str]) -> bytes:
    return "".join(f"{key}={evidence[key]}\n" for key in _MARKER_ORDER).encode("utf-8")


def evidence_fingerprint(evidence: Mapping[str, str]) -> str:
    return hashlib.sha256(render_gp_s2_evidence(evidence)).hexdigest()
