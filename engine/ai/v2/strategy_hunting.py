from __future__ import annotations

from dataclasses import dataclass

from engine.ai.v2.contracts import AIRequest, DataClass, ProviderManifest
from engine.ai.v2.data_policy import DataProvenanceEvidence, ProviderDataPolicy
from engine.ai.v2.provider_gateway import ProviderDataGateway, ProviderReadyRequest


@dataclass(frozen=True, slots=True)
class StrategyHuntingPreparedJob:
    job_id: str
    provider_id: str
    dataset_ref: str
    execution_scope: str
    ready_request: ProviderReadyRequest


class StrategyHuntingOrchestrator:
    """After-hours research orchestration with mandatory existing OD-16 gate reuse."""

    def __init__(self, gateway: ProviderDataGateway) -> None:
        if not isinstance(gateway, ProviderDataGateway):
            raise TypeError("gateway must be ProviderDataGateway")
        self._gateway = gateway

    def prepare_job(
        self,
        *,
        job_id: str,
        provider: ProviderManifest,
        policy: ProviderDataPolicy,
        provenance: tuple[DataProvenanceEvidence, ...],
        dataset_ref: str,
        payload: object,
    ) -> StrategyHuntingPreparedJob:
        job = str(job_id).strip()
        dataset = str(dataset_ref).strip()
        if not job:
            raise ValueError("job_id required")
        if not dataset:
            raise ValueError("dataset_ref required")

        request = AIRequest(
            request_id=job,
            schema_id="strategy-hunting/v1",
            data_classes=(DataClass.STRATEGY_RESEARCH,),
            payload={"dataset_ref": dataset, "research_payload": payload},
            provenance_refs=tuple(ev.evidence_ref for ev in provenance),
        )
        ready = self._gateway.prepare_strategy_hunting(
            request,
            provider=provider,
            policy=policy,
            provenance=provenance,
        )
        return StrategyHuntingPreparedJob(
            job_id=job,
            provider_id=provider.provider_id,
            dataset_ref=dataset,
            execution_scope="RISK_GATED_CANDIDATE",
            ready_request=ready,
        )


__all__ = ["StrategyHuntingOrchestrator", "StrategyHuntingPreparedJob"]
