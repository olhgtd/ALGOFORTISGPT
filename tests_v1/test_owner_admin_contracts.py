from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone

import pytest

from dashboard.backend.owner_admin.contracts import AuthorityEnvelope, AuthorityState, authority_state_from_source


def test_owner_authority_state_set_is_exact() -> None:
    assert {item.value for item in AuthorityState} == {
        "AVAILABLE",
        "STALE",
        "UNKNOWN",
        "UNAVAILABLE",
    }


def test_owner_authority_envelope_is_immutable_and_has_no_trading_authority() -> None:
    envelope = AuthorityEnvelope(
        state=AuthorityState.AVAILABLE,
        source="BACKEND",
        as_of=datetime(2026, 9, 29, tzinfo=timezone.utc),
        payload={"count": 0},
        reason=None,
        evidence_ref="audit-1",
    )
    names = {field.name for field in fields(envelope)}
    assert names.isdisjoint({"armed", "can_trade", "approved_order", "broker_order", "place_order"})
    with pytest.raises(FrozenInstanceError):
        envelope.state = AuthorityState.UNKNOWN  # type: ignore[misc]


def test_source_and_trust_mapping_is_fail_closed() -> None:
    assert authority_state_from_source(source="BACKEND", trust="FRESH") is AuthorityState.AVAILABLE
    assert authority_state_from_source(source="BACKEND", trust="STALE") is AuthorityState.STALE
    assert authority_state_from_source(source="BACKEND", trust="UNKNOWN") is AuthorityState.UNKNOWN
    assert authority_state_from_source(source="UNAVAILABLE", trust="UNKNOWN") is AuthorityState.UNAVAILABLE
    assert authority_state_from_source(source="SAMPLE_FALLBACK", trust="UNKNOWN") is AuthorityState.UNKNOWN


def test_zero_is_only_authoritative_when_state_is_available() -> None:
    available = AuthorityEnvelope(
        state=AuthorityState.AVAILABLE,
        source="BACKEND",
        as_of=datetime(2026, 9, 29, tzinfo=timezone.utc),
        payload={"count": 0},
    )
    unavailable = AuthorityEnvelope(
        state=AuthorityState.UNAVAILABLE,
        source="UNAVAILABLE",
        as_of=datetime(2026, 9, 29, tzinfo=timezone.utc),
        payload={"count": 0},
        reason="AUTHORITY_UNAVAILABLE",
    )
    assert available.authoritative_value("count") == 0
    assert unavailable.authoritative_value("count") is None
