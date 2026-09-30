"""Off-hot-path RiskSnapshot builder.

The builder collects and validates a complete immutable snapshot before it is
published.  Failure never replaces the last known published snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from typing import Mapping, Protocol

from engine.risk.snapshot_contracts_v2 import RiskSnapshot
from engine.risk.snapshot_publication_v2 import RiskSnapshotPublication


class RiskSnapshotBuilderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RiskSnapshotInputs:
    schema_version: str
    risk_rule_version: str
    limits_snapshot_id: str
    account_authority_ref: str
    strategy_eligibility_ref: str
    portfolio_state_ref: str
    entry_policy_ref: str
    operational_state: str
    kill_switch_state: str
    hold_state: str
    allowed_instrument_scope: tuple[str, ...]
    allowed_side_scope: tuple[str, ...]
    quantity_ceiling_by_scope: Mapping[str, Decimal]
    risk_budget_evidence: str
    feed_health_ref: str
    latest_market_sequence: int
    source_versions: tuple[str, ...]
    builder_health_generation: int


class SnapshotInputProvider(Protocol):
    def collect(self) -> RiskSnapshotInputs: ...


def _canonical_input_payload(inputs: RiskSnapshotInputs) -> dict[str, object]:
    return {
        "schema_version": inputs.schema_version,
        "risk_rule_version": inputs.risk_rule_version,
        "limits_snapshot_id": inputs.limits_snapshot_id,
        "account_authority_ref": inputs.account_authority_ref,
        "strategy_eligibility_ref": inputs.strategy_eligibility_ref,
        "portfolio_state_ref": inputs.portfolio_state_ref,
        "entry_policy_ref": inputs.entry_policy_ref,
        "operational_state": inputs.operational_state,
        "kill_switch_state": inputs.kill_switch_state,
        "hold_state": inputs.hold_state,
        "allowed_instrument_scope": list(inputs.allowed_instrument_scope),
        "allowed_side_scope": list(inputs.allowed_side_scope),
        "quantity_ceiling_by_scope": {
            key: str(value) for key, value in sorted(dict(inputs.quantity_ceiling_by_scope).items())
        },
        "risk_budget_evidence": inputs.risk_budget_evidence,
        "feed_health_ref": inputs.feed_health_ref,
        "latest_market_sequence": inputs.latest_market_sequence,
        "source_versions": list(inputs.source_versions),
        "builder_health_generation": inputs.builder_health_generation,
    }


class RiskSnapshotBuilder:
    def __init__(self, provider: SnapshotInputProvider, publication: RiskSnapshotPublication) -> None:
        if not callable(getattr(provider, "collect", None)):
            raise TypeError("provider must provide collect()")
        if not isinstance(publication, RiskSnapshotPublication):
            raise TypeError("publication must be RiskSnapshotPublication")
        self._provider = provider
        self._publication = publication

    def build(self, inputs: RiskSnapshotInputs, *, generated_at: datetime) -> RiskSnapshot:
        if not isinstance(inputs, RiskSnapshotInputs):
            raise TypeError("inputs must be RiskSnapshotInputs")
        try:
            canonical = json.dumps(
                _canonical_input_payload(inputs),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            snapshot_id = f"risk_snapshot:{fingerprint[:24]}"
            return RiskSnapshot(
                snapshot_id=snapshot_id,
                schema_version=inputs.schema_version,
                generated_at_utc=generated_at,
                input_fingerprint=fingerprint,
                risk_rule_version=inputs.risk_rule_version,
                limits_snapshot_id=inputs.limits_snapshot_id,
                account_authority_ref=inputs.account_authority_ref,
                strategy_eligibility_ref=inputs.strategy_eligibility_ref,
                portfolio_state_ref=inputs.portfolio_state_ref,
                entry_policy_ref=inputs.entry_policy_ref,
                operational_state=inputs.operational_state,
                kill_switch_state=inputs.kill_switch_state,
                hold_state=inputs.hold_state,
                allowed_instrument_scope=inputs.allowed_instrument_scope,
                allowed_side_scope=inputs.allowed_side_scope,
                quantity_ceiling_by_scope=inputs.quantity_ceiling_by_scope,
                risk_budget_evidence=inputs.risk_budget_evidence,
                feed_health_ref=inputs.feed_health_ref,
                latest_market_sequence=inputs.latest_market_sequence,
                source_versions=inputs.source_versions,
                builder_health_generation=inputs.builder_health_generation,
            )
        except Exception as exc:
            raise RiskSnapshotBuilderError("risk snapshot build failed closed") from exc

    def refresh(self, *, generated_at: datetime) -> RiskSnapshot:
        try:
            inputs = self._provider.collect()
        except Exception as exc:
            raise RiskSnapshotBuilderError("risk snapshot input collection failed closed") from exc
        snapshot = self.build(inputs, generated_at=generated_at)
        self._publication.publish(snapshot)
        return snapshot


__all__ = [
    "RiskSnapshotBuilder",
    "RiskSnapshotBuilderError",
    "RiskSnapshotInputs",
    "SnapshotInputProvider",
]
