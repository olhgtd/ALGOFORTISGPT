"""Phase 1 RED tests for AF2-AUD-001/003 tamper-evident audit evidence."""

from datetime import datetime, timezone

import pytest

from engine.audit.chain import AuditChain, AuditChainError, verify_audit_chain
from engine.audit.model import AuditEvent


def _event(event_id: str, *, correlation_id: str = "corr-1") -> AuditEvent:
    return AuditEvent(
        event_id=event_id,
        event_family="SESSION",
        event_type="SESSION_STARTED",
        aggregate_type="runtime",
        aggregate_identity="paper-runtime",
        recorded_at_utc=datetime(2026, 9, 21, 6, 0, tzinfo=timezone.utc),
        audit_sequence=None,
        correlation_id=correlation_id,
        run_id="run-001",
        environment="paper",
        canonical_configuration_fingerprint="cfg_abc",
        payload_version="sentinelx-payload/v1",
        payload_json='{"reason":"startup"}',
    )


def test_chain_is_deterministic_and_links_each_entry() -> None:
    chain = AuditChain()
    first = chain.append(
        _event("evt-1"),
        versions={"risk_rule": "risk-policy/v3", "broker_adapter": "paper/v1"},
    )
    second = chain.append(
        _event("evt-2", correlation_id="corr-2"),
        versions={"broker_adapter": "paper/v1", "risk_rule": "risk-policy/v3"},
    )

    assert first.sequence == 1
    assert first.previous_hash == AuditChain.GENESIS_HASH
    assert second.sequence == 2
    assert second.previous_hash == first.chain_hash
    assert len(first.chain_hash) == 64
    assert len(second.chain_hash) == 64
    assert first.versions == (
        ("audit_envelope", "sentinelx-audit-envelope/v2"),
        ("broker_adapter", "paper/v1"),
        ("payload", "sentinelx-payload/v1"),
        ("risk_rule", "risk-policy/v3"),
    )
    assert verify_audit_chain(chain.entries) is True


def test_same_evidence_produces_same_chain_hash() -> None:
    left = AuditChain()
    right = AuditChain()

    left_entry = left.append(_event("evt-1"), versions={"risk_rule": "risk-policy/v3"})
    right_entry = right.append(_event("evt-1"), versions={"risk_rule": "risk-policy/v3"})

    assert left_entry.chain_hash == right_entry.chain_hash


def test_verify_detects_tampering_and_sequence_breaks() -> None:
    chain = AuditChain()
    chain.append(_event("evt-1"), versions={"risk_rule": "risk-policy/v3"})
    chain.append(_event("evt-2"), versions={"risk_rule": "risk-policy/v3"})

    tampered = list(chain.entries)
    tampered[1] = tampered[1].__class__(
        sequence=tampered[1].sequence,
        previous_hash=tampered[1].previous_hash,
        event=tampered[1].event,
        versions=tampered[1].versions + (("model", "changed"),),
        chain_hash=tampered[1].chain_hash,
    )
    with pytest.raises(AuditChainError, match="hash"):
        verify_audit_chain(tuple(tampered))


def test_chain_rejects_missing_or_invalid_version_evidence() -> None:
    chain = AuditChain()
    with pytest.raises(AuditChainError, match="version"):
        chain.append(_event("evt-1"), versions={})
    with pytest.raises(AuditChainError, match="version"):
        chain.append(_event("evt-1"), versions={"risk_rule": ""})


def test_chain_rejects_missing_run_or_correlation_identity() -> None:
    missing_run = _event("evt-1")
    object.__setattr__(missing_run, "run_id", None)
    with pytest.raises(AuditChainError, match="run_id"):
        AuditChain().append(missing_run, versions={"risk_rule": "risk-policy/v3"})

    missing_correlation = _event("evt-2")
    object.__setattr__(missing_correlation, "correlation_id", None)
    with pytest.raises(AuditChainError, match="correlation_id"):
        AuditChain().append(missing_correlation, versions={"risk_rule": "risk-policy/v3"})
