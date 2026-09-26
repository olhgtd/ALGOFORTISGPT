from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from engine.broker_adapters.angelone_v2.protection_capability import (
    ProtectionCapabilityEvidence,
    ProtectionCapabilityStatus,
    evaluate_required_protection,
)

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "engine" / "broker_adapters" / "angelone_v2" / "protection_capability.py"
NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)


def test_missing_or_unknown_required_capability_keeps_path_disarmed() -> None:
    missing = evaluate_required_protection(
        requirement_ref="risk@v1",
        required_capabilities=("STOP", "TARGET"),
        evidence=None,
    )
    assert missing.status is ProtectionCapabilityStatus.UNVERIFIED
    assert missing.disarmed_required is True

    evidence = ProtectionCapabilityEvidence(
        "cap", "v1", NOW, ("STOP",), True, "broker-docs", False
    )
    unsupported = evaluate_required_protection(
        requirement_ref="risk@v1",
        required_capabilities=("STOP", "TARGET"),
        evidence=evidence,
    )
    assert unsupported.status is ProtectionCapabilityStatus.UNSUPPORTED
    assert unsupported.missing_capabilities == ("TARGET",)
    assert unsupported.disarmed_required is True


def test_verified_required_capabilities_are_observation_evidence_only() -> None:
    evidence = ProtectionCapabilityEvidence(
        "cap", "v1", NOW, ("STOP", "TARGET"), True, "broker-docs", False
    )
    result = evaluate_required_protection(
        requirement_ref="risk@v1",
        required_capabilities=("STOP", "TARGET"),
        evidence=evidence,
    )
    assert result.status is ProtectionCapabilityStatus.VERIFIED_SUPPORTED
    assert result.disarmed_required is True
    assert result.existing_protection_adopted is False
    assert not hasattr(result, "arm")
    assert not hasattr(result, "place")


def test_existing_broker_protection_is_not_auto_adopted_without_ownership_evidence() -> None:
    evidence = ProtectionCapabilityEvidence(
        "cap", "v1", NOW, ("STOP", "TARGET"), True, "broker-docs", False
    )
    result = evaluate_required_protection(
        requirement_ref="risk@v1",
        required_capabilities=("STOP",),
        evidence=evidence,
        existing_protection_observed=True,
    )
    assert result.existing_protection_observed is True
    assert result.existing_protection_adopted is False


def test_module_exposes_no_protective_order_mutation_calls() -> None:
    source = MODULE.read_text(encoding="utf-8")
    for token in (
        "def place",
        "def modify",
        "def cancel",
        "create_gtt",
        "modify_gtt",
        "cancel_gtt",
    ):
        assert token not in source
