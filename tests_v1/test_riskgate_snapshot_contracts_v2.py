from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from engine.risk.snapshot_contracts_v2 import RiskSnapshot


def _snapshot(**overrides) -> RiskSnapshot:
    values = {
        "snapshot_id": "snap-1",
        "schema_version": "v1",
        "generated_at_utc": datetime(2026, 9, 30, tzinfo=timezone.utc),
        "input_fingerprint": "a" * 64,
        "risk_rule_version": "risk-v1",
        "limits_snapshot_id": "limits-v1",
        "account_authority_ref": "acct:1",
        "strategy_eligibility_ref": "strategy:1",
        "portfolio_state_ref": "portfolio:1",
        "entry_policy_ref": "entry:1",
        "operational_state": "HEALTHY",
        "kill_switch_state": "CLEAR",
        "hold_state": "CLEAR",
        "allowed_instrument_scope": ("NIFTY",),
        "allowed_side_scope": ("BUY",),
        "quantity_ceiling_by_scope": {"NIFTY": Decimal("75")},
        "risk_budget_evidence": "risk-budget:1",
        "feed_health_ref": "feed:1",
        "latest_market_sequence": 10,
        "source_versions": ("feed@1", "portfolio@1"),
        "builder_health_generation": 3,
    }
    values.update(overrides)
    return RiskSnapshot(**values)


def test_snapshot_is_frozen_and_deeply_read_only() -> None:
    snap = _snapshot()
    with pytest.raises(FrozenInstanceError):
        snap.snapshot_id = "other"  # type: ignore[misc]
    with pytest.raises(TypeError):
        snap.quantity_ceiling_by_scope["NIFTY"] = Decimal("1")  # type: ignore[index]


def test_snapshot_requires_timezone_aware_time_and_hex_fingerprint() -> None:
    with pytest.raises(ValueError):
        _snapshot(generated_at_utc=datetime(2026, 9, 30))
    with pytest.raises(ValueError):
        _snapshot(input_fingerprint="not-a-fingerprint")


def test_snapshot_rejects_negative_sequence_or_generation() -> None:
    with pytest.raises(ValueError):
        _snapshot(latest_market_sequence=-1)
    with pytest.raises(ValueError):
        _snapshot(builder_health_generation=-1)


def test_snapshot_reference_is_stable_for_same_content() -> None:
    first = _snapshot(snapshot_id="snap-stable")
    second = _snapshot(snapshot_id="snap-stable")
    assert first.reference == second.reference
    assert len(first.reference) == 64
