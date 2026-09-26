from __future__ import annotations

import dataclasses
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "engine" / "broker_adapters" / "angelone_v2" / "compliance_gate.py"


def _load():
    assert MODULE.is_file(), "Phase-6 compliance gate module is missing"
    spec = importlib.util.spec_from_file_location("phase6_compliance_gate", MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _now():
    return datetime(2026, 9, 27, tzinfo=timezone.utc)


def test_missing_or_unverified_evidence_is_not_eligible() -> None:
    m = _load()
    gate = m.BrokerComplianceGate()
    missing = gate.evaluate(None, now=_now())
    assert missing.status is m.BrokerEligibilityStatus.UNVERIFIED
    assert missing.eligible is False

    evidence = m.BrokerComplianceEvidence(
        evidence_id="G6-COMPLIANCE",
        version="v1",
        reviewed_at=_now(),
        valid_until=_now() + timedelta(days=1),
        static_ip_verified=False,
        rule_review_verified=True,
        source_refs=("angel", "nse"),
    )
    result = gate.evaluate(evidence, now=_now())
    assert result.status is m.BrokerEligibilityStatus.NOT_ELIGIBLE
    assert result.eligible is False


def test_stale_evidence_fails_closed_and_result_has_no_arm_or_order_authority() -> None:
    m = _load()
    gate = m.BrokerComplianceGate()
    evidence = m.BrokerComplianceEvidence(
        evidence_id="G6-COMPLIANCE",
        version="v1",
        reviewed_at=_now() - timedelta(days=2),
        valid_until=_now() - timedelta(seconds=1),
        static_ip_verified=True,
        rule_review_verified=True,
        source_refs=("angel", "nse"),
    )
    result = gate.evaluate(evidence, now=_now())
    assert result.status is m.BrokerEligibilityStatus.NOT_ELIGIBLE
    assert result.reason == "STALE_COMPLIANCE_EVIDENCE"
    names = {field.name for field in dataclasses.fields(result)}
    assert not names.intersection({"arm", "arm_enabled", "order", "approved_order", "place"})


def test_verified_current_evidence_is_observation_eligible_only() -> None:
    m = _load()
    gate = m.BrokerComplianceGate()
    evidence = m.BrokerComplianceEvidence(
        evidence_id="G6-COMPLIANCE",
        version="v1",
        reviewed_at=_now(),
        valid_until=_now() + timedelta(days=1),
        static_ip_verified=True,
        rule_review_verified=True,
        source_refs=("angel", "nse"),
    )
    result = gate.evaluate(evidence, now=_now())
    assert result.status is m.BrokerEligibilityStatus.ELIGIBLE_READ_ONLY
    assert result.eligible is True
    assert result.reason == "READ_ONLY_EVIDENCE_VERIFIED"
