from __future__ import annotations

import dataclasses
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "engine" / "broker_adapters" / "angelone_v2" / "contracts.py"


def _load_contracts():
    assert CONTRACTS.is_file(), "Phase-6 read-only contracts module is missing"
    spec = importlib.util.spec_from_file_location("phase6_contracts", CONTRACTS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contracts_are_frozen_validate_explicit_references_and_expose_no_mutation_authority() -> None:
    m = _load_contracts()
    reviewed_at = datetime(2026, 9, 27, tzinfo=timezone.utc)
    profile = m.AngelOneBrokerProfile(
        profile_id="ANGELONE/SMARTAPI/READ_ONLY",
        version="2026-09-27",
        api_base_url="https://apiconnect.angelone.in",
        documentation_ref="SMARTAPI-DOCS-2026-09-27",
    )
    credential = m.AngelOneCredentialRef(
        secret_ref="secret://angelone/profile-1",
        account_ref="acct-ref-1",
    )
    capability = m.AngelOneReadOnlyCapability(
        capability_id="READ_ONLY_TRUTH",
        evidence_ref="g6-readonly-v1",
    )
    rule = m.BrokerRuleEvidenceRef(
        evidence_id="G6-RULE-REVIEW",
        version="2026-09-27",
        reviewed_at=reviewed_at,
        source_refs=("ANGELONE-REGS", "NSE-FAQ"),
    )
    health = m.AngelOneReadOnlyHealth(
        session_state="AUTHENTICATED",
        broker_truth_available=True,
        profile_ref=profile.reference,
        rule_evidence_ref=rule.reference,
    )

    assert profile.reference == "ANGELONE/SMARTAPI/READ_ONLY@2026-09-27"
    assert credential.secret_ref.startswith("secret://")
    assert capability.capability_id == "READ_ONLY_TRUTH"
    assert health.broker_truth_available is True

    for obj in (profile, credential, capability, rule, health):
        params = {field.name for field in dataclasses.fields(obj)}
        assert not params.intersection({"arm", "arm_enabled", "place", "submit", "modify", "cancel", "approved_order"})
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(obj, dataclasses.fields(obj)[0].name, "mutated")


def test_contracts_reject_empty_or_unaware_required_evidence() -> None:
    m = _load_contracts()
    with pytest.raises(ValueError):
        m.AngelOneBrokerProfile("", "v1", "https://apiconnect.angelone.in", "docs")
    with pytest.raises(ValueError):
        m.AngelOneCredentialRef("", "acct")
    with pytest.raises(ValueError):
        m.AngelOneReadOnlyCapability("", "evidence")
    with pytest.raises(ValueError):
        m.BrokerRuleEvidenceRef("rules", "v1", datetime(2026, 9, 27), ("src",))
    with pytest.raises(ValueError):
        m.BrokerRuleEvidenceRef("rules", "v1", datetime(2026, 9, 27, tzinfo=timezone.utc), ())
