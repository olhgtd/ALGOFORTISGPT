from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from engine.ai.v2.contracts import DataClass, ProviderKind, ProviderManifest
from engine.ai.v2.data_policy import DataProvenanceEvidence, ProviderDataPolicy
from engine.ai.v2.provider_gateway import ProviderDataGateway, ProviderGatewayDenied
from engine.ai.v2.strategy_hunting import StrategyHuntingOrchestrator
from engine.data import licensing as l

NOW = datetime(2026, 10, 1, 16, 0, tzinfo=timezone.utc)


def _manifest(kind: ProviderKind) -> ProviderManifest:
    provider_id = "cloud-a" if kind is ProviderKind.CLOUD else "local-a"
    return ProviderManifest(
        provider_id,
        kind,
        "1.0.0",
        "model-a",
        ("strategy-hunting/v1",),
        (DataClass.STRATEGY_RESEARCH.value,),
        "retention:approved" if kind is ProviderKind.CLOUD else None,
        False,
    )


def _policy(provider_id: str) -> ProviderDataPolicy:
    return ProviderDataPolicy("ai-data/strategy-hunting", provider_id, "1.0.0", (DataClass.STRATEGY_RESEARCH,))


def _evidence(external: l.ExternalProcessingPermission) -> DataProvenanceEvidence:
    meta = l.DataLicenceMetadata(
        "feed-a",
        "terms-v5",
        l.AcquisitionPermission.ALLOWED,
        (l.DataUse.RESEARCH,),
        False,
        external,
    )
    return DataProvenanceEvidence(
        "prov:strategy-hunting",
        meta,
        NOW - timedelta(minutes=1),
        NOW + timedelta(hours=2),
        False,
    )


def _orchestrator(events: list[object]) -> StrategyHuntingOrchestrator:
    gateway = ProviderDataGateway(
        licence_policy=l.DataLicencePolicy(),
        audit_sink=events.append,
        clock=lambda: NOW,
    )
    return StrategyHuntingOrchestrator(gateway)


def test_cloud_strategy_hunting_requires_od16_external_processing_authorization() -> None:
    with pytest.raises(ProviderGatewayDenied):
        _orchestrator([]).prepare_job(
            job_id="hunt-1",
            provider=_manifest(ProviderKind.CLOUD),
            policy=_policy("cloud-a"),
            provenance=(_evidence(l.ExternalProcessingPermission.PROHIBITED),),
            dataset_ref="dataset:session-1",
            payload={"instrument": "NIFTY", "purpose": "hypothesis-generation"},
        )


def test_cloud_strategy_hunting_allowed_when_od16_and_dataset_policy_allow_it() -> None:
    events: list[object] = []
    ready = _orchestrator(events).prepare_job(
        job_id="hunt-2",
        provider=_manifest(ProviderKind.CLOUD),
        policy=_policy("cloud-a"),
        provenance=(_evidence(l.ExternalProcessingPermission.ALLOWED),),
        dataset_ref="dataset:session-1",
        payload={"instrument": "NIFTY", "purpose": "hypothesis-generation"},
    )
    assert ready.provider_id == "cloud-a"
    assert ready.execution_scope == "RESEARCH_BACKTEST_PAPER_ONLY"
    assert ready.dataset_ref == "dataset:session-1"
    assert events


def test_local_strategy_hunting_does_not_require_cloud_egress_permission_but_still_uses_data_policy() -> None:
    ready = _orchestrator([]).prepare_job(
        job_id="hunt-3",
        provider=_manifest(ProviderKind.LOCAL),
        policy=_policy("local-a"),
        provenance=(_evidence(l.ExternalProcessingPermission.PROHIBITED),),
        dataset_ref="dataset:session-1",
        payload={"instrument": "BANKNIFTY"},
    )
    assert ready.provider_id == "local-a"
    assert ready.execution_scope == "RESEARCH_BACKTEST_PAPER_ONLY"
