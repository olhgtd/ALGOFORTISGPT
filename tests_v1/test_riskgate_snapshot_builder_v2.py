from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from engine.risk.snapshot_builder_v2 import (
    RiskSnapshotBuilder,
    RiskSnapshotBuilderError,
    RiskSnapshotInputs,
)
from engine.risk.snapshot_publication_v2 import RiskSnapshotPublication


def _inputs(**overrides) -> RiskSnapshotInputs:
    values = {
        "schema_version": "v1",
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
        "latest_market_sequence": 42,
        "source_versions": ("feed@1", "portfolio@1"),
        "builder_health_generation": 2,
    }
    values.update(overrides)
    return RiskSnapshotInputs(**values)


class _Provider:
    def __init__(self, value: RiskSnapshotInputs | Exception) -> None:
        self.value = value

    def collect(self) -> RiskSnapshotInputs:
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


def test_same_inputs_produce_same_snapshot_id() -> None:
    publication = RiskSnapshotPublication()
    builder = RiskSnapshotBuilder(_Provider(_inputs()), publication)
    at = datetime(2026, 9, 30, tzinfo=timezone.utc)
    first = builder.build(_inputs(), generated_at=at)
    second = builder.build(_inputs(), generated_at=at)
    assert first.snapshot_id == second.snapshot_id
    assert first.input_fingerprint == second.input_fingerprint


def test_input_version_change_changes_snapshot_identity() -> None:
    publication = RiskSnapshotPublication()
    builder = RiskSnapshotBuilder(_Provider(_inputs()), publication)
    at = datetime(2026, 9, 30, tzinfo=timezone.utc)
    first = builder.build(_inputs(), generated_at=at)
    second = builder.build(_inputs(source_versions=("feed@2", "portfolio@1")), generated_at=at)
    assert first.snapshot_id != second.snapshot_id


def test_refresh_publishes_only_completed_snapshot() -> None:
    publication = RiskSnapshotPublication()
    builder = RiskSnapshotBuilder(_Provider(_inputs()), publication)
    first = builder.refresh(generated_at=datetime(2026, 9, 30, tzinfo=timezone.utc))
    assert publication.current() is first

    failing = RiskSnapshotBuilder(_Provider(RuntimeError("collector down")), publication)
    with pytest.raises(RiskSnapshotBuilderError):
        failing.refresh(generated_at=datetime(2026, 9, 30, 0, 0, 1, tzinfo=timezone.utc))
    assert publication.current() is first


def test_missing_authority_reference_fails_closed() -> None:
    publication = RiskSnapshotPublication()
    builder = RiskSnapshotBuilder(_Provider(_inputs()), publication)
    with pytest.raises(RiskSnapshotBuilderError):
        builder.build(
            _inputs(account_authority_ref=""),
            generated_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
        )
