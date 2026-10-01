"""Deterministic qualification probe for the locked AI/Laya architecture."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from dashboard.backend.account_v2.contracts import (
    DeviceSessionGateResult,
    DeviceSessionGateStatus,
    IntelligenceCapability,
)
from dashboard.backend.account_v2.intelligence_entitlements import IntelligenceEntitlementService
from engine.ai.monitoring_scheduler_v2 import (
    MarketWatchPolicyV2,
    MonitoringSchedulerV2,
    MonitoringTaskClass,
    MonitoringTriggerType,
)
from engine.ai.provider_queue_v2 import ProviderJobQueueV2, ProviderQueuePolicyV2
from engine.ai.v2.contracts import DataClass, ProviderKind, ProviderManifest
from engine.ai.v2.data_policy import DataProvenanceEvidence, ProviderDataPolicy
from engine.ai.v2.orchestrator import StrategyDecisionIntelligence
from engine.ai.v2.provider_gateway import ProviderDataGateway, ProviderGatewayDenied
from engine.ai.v2.review_council import ReviewCouncil, ReviewDisposition, ReviewOpinion
from engine.ai.v2.strategy_hunting import StrategyHuntingOrchestrator
from engine.data import licensing as licensing
from engine.portfolio.candidate_arbitration_v2 import (
    BrokerAccountKey,
    CandidateReservationRequest,
    PortfolioCandidateArbitrator,
)
from engine.portfolio.v2.contracts import PortfolioBudgetPolicy
from engine.portfolio.v2.reservations import CapitalReservationBook

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
USER = UUID("11111111-1111-1111-1111-111111111111")


def _opinion(participant: str, provider: str, model: str, foundation: str, source: str) -> ReviewOpinion:
    return ReviewOpinion(
        participant_id=participant,
        provider_id=provider,
        model_id=model,
        foundation_model_id=foundation,
        disposition=ReviewDisposition.CONFIRM,
        evidence_refs=(f"evidence:{participant}",),
        source_refs=(source,),
    )


def _book(budget: str = "100") -> CapitalReservationBook:
    amount = Decimal(budget)
    return CapitalReservationBook(
        PortfolioBudgetPolicy(
            "probe-budget",
            "1.0.0",
            amount,
            "user-1",
            amount,
            {"strategy-a": amount, "strategy-b": amount},
        )
    )


def _reservation(candidate: str, broker: str, account: str, amount: str, strategy: str) -> CandidateReservationRequest:
    return CandidateReservationRequest(
        candidate_id=candidate,
        broker_account=BrokerAccountKey(broker, account),
        strategy_id=strategy,
        required_capital=Decimal(amount),
        created_at=NOW,
        valid_until=NOW + timedelta(minutes=5),
    )


class _EntitlementStore:
    def __init__(self) -> None:
        self.values: dict[UUID, tuple[IntelligenceCapability, ...]] = {}

    def list_for_user(self, user_id: UUID) -> tuple[IntelligenceCapability, ...]:
        return self.values.get(user_id, ())

    def replace_for_user(self, user_id: UUID, capabilities: tuple[IntelligenceCapability, ...]) -> None:
        self.values[user_id] = capabilities


def _gate(status: DeviceSessionGateStatus) -> DeviceSessionGateResult:
    return DeviceSessionGateResult(
        schema_version="1.0.0",
        user_id=USER,
        device_id="device-probe",
        session_family_id="family-probe",
        status=status,
        reasons=(),
        authority_evidence_ref="s2:probe" if status is DeviceSessionGateStatus.VALID else None,
        evaluated_at=NOW,
        audit_ref="audit:probe",
    )


def _provider_manifest() -> ProviderManifest:
    return ProviderManifest(
        "cloud-probe",
        ProviderKind.CLOUD,
        "1.0.0",
        "model-probe",
        ("strategy-hunting/v1",),
        (DataClass.STRATEGY_RESEARCH.value,),
        "retention:probe",
        False,
    )


def _provider_policy() -> ProviderDataPolicy:
    return ProviderDataPolicy(
        "probe-data-policy",
        "cloud-probe",
        "1.0.0",
        (DataClass.STRATEGY_RESEARCH,),
    )


def _provenance(external: licensing.ExternalProcessingPermission) -> DataProvenanceEvidence:
    metadata = licensing.DataLicenceMetadata(
        "probe-feed",
        "terms-v1",
        licensing.AcquisitionPermission.ALLOWED,
        (licensing.DataUse.RESEARCH,),
        False,
        external,
    )
    return DataProvenanceEvidence(
        "provenance:probe",
        metadata,
        NOW - timedelta(minutes=1),
        NOW + timedelta(hours=1),
        False,
    )


def main() -> int:
    # Strategy independence and 0..N intelligence council.
    decision = StrategyDecisionIntelligence().review_strategy("strategy:probe", ())
    assert decision.strategy_unblocked is True
    assert decision.council.participant_count == 0
    one = ReviewCouncil.aggregate((_opinion("laya", "local", "laya", "laya-f", "source:laya"),))
    many = ReviewCouncil.aggregate(
        (
            _opinion("a", "provider-a", "model-a", "foundation-a", "source:a"),
            _opinion("b", "provider-b", "model-b", "foundation-b", "source:b"),
        )
    )
    correlated = ReviewCouncil.aggregate(
        (
            _opinion("a", "provider-a", "same", "foundation-x", "source:a"),
            _opinion("critic", "provider-a", "same", "foundation-x", "source:b"),
        )
    )
    assert one.participant_count == 1
    assert many.participant_count == 2 and many.independent_lineage_count == 2
    assert correlated.correlated_model_flag is True and correlated.independent_lineage_count == 1

    # Owner-controlled monitoring and bounded provider queue.
    watch = MarketWatchPolicyV2(
        policy_ref="probe-watch/v1",
        policy_version="1.0.0",
        allowed_instruments=("NIFTY",),
        frequency_seconds=60,
        task_ttl_seconds=30,
        provider_id="provider-a",
        model_id="model-a",
        allowed_trigger_types=(MonitoringTriggerType.SCHEDULED, MonitoringTriggerType.EVENT, MonitoringTriggerType.OWNER),
        allowed_task_classes=(MonitoringTaskClass.ACTIVE_CANDIDATE_REVIEW, MonitoringTaskClass.STRATEGY_HUNTING),
        allowed_timeframes=("1m", "5m"),
        strategy_review_mode="OPTIONAL",
        independent_candidate_scan=True,
    )
    scheduler = MonitoringSchedulerV2(watch)
    task = scheduler.schedule(
        task_id="task:probe",
        instrument="NIFTY",
        scheduled_for=NOW,
        hard_eligible=True,
        portfolio_priority=1,
        strategy_priority=1,
        edge_quality=Decimal("1"),
        capital_efficiency=Decimal("1"),
        signal_at=NOW,
        trigger_type=MonitoringTriggerType.EVENT,
        task_class=MonitoringTaskClass.ACTIVE_CANDIDATE_REVIEW,
        timeframe="5m",
    )
    queue = ProviderJobQueueV2(
        ProviderQueuePolicyV2(
            "probe-queue/v1", "provider-a", 1, 4, 5, max_requests_per_window=1, window_seconds=60
        )
    )
    queue.enqueue(task, now=NOW)
    assert len(queue.claim(now=NOW, provider_slots_available=1)) == 1

    # Existing Portfolio reservation books: separate account pools + aggregate cap.
    account_a = BrokerAccountKey("broker-a", "account-a")
    account_b = BrokerAccountKey("broker-b", "account-b")
    arbitrator = PortfolioCandidateArbitrator(
        {account_a: _book("100"), account_b: _book("100")},
        aggregate_capital_limit=Decimal("150"),
    )
    assert arbitrator.reserve(_reservation("candidate-a", "broker-a", "account-a", "60", "strategy-a")).accepted
    assert arbitrator.reserve(_reservation("candidate-b", "broker-b", "account-b", "60", "strategy-b")).accepted
    assert arbitrator.total_reserved == Decimal("120")
    blocked = arbitrator.reserve(_reservation("candidate-c", "broker-a", "account-a", "40", "strategy-b"))
    assert blocked.accepted is False
    assert not hasattr(arbitrator, "mint_approved_order")

    # OD-V2-16: after-hours cloud Strategy Hunting cannot bypass egress licensing.
    events: list[object] = []
    gateway = ProviderDataGateway(
        licence_policy=licensing.DataLicencePolicy(),
        audit_sink=events.append,
        clock=lambda: NOW,
    )
    hunting = StrategyHuntingOrchestrator(gateway)
    try:
        hunting.prepare_job(
            job_id="hunt-denied",
            provider=_provider_manifest(),
            policy=_provider_policy(),
            provenance=(_provenance(licensing.ExternalProcessingPermission.PROHIBITED),),
            dataset_ref="dataset:probe",
            payload={"instrument": "NIFTY"},
        )
    except ProviderGatewayDenied:
        pass
    else:
        raise AssertionError("OD-V2-16 prohibited external processing was not denied")
    allowed = hunting.prepare_job(
        job_id="hunt-allowed",
        provider=_provider_manifest(),
        policy=_provider_policy(),
        provenance=(_provenance(licensing.ExternalProcessingPermission.ALLOWED),),
        dataset_ref="dataset:probe",
        payload={"instrument": "NIFTY"},
    )
    assert allowed.execution_scope == "RESEARCH_BACKTEST_PAPER_ONLY"

    # S2-backed entitlements fail closed when the session/device authority is not VALID.
    store = _EntitlementStore()
    service = IntelligenceEntitlementService(store)
    service.set_for_user(USER, (IntelligenceCapability.ACCESS_LAYA_ANALYSIS,), actor_is_owner=True)
    assert service.authorize(_gate(DeviceSessionGateStatus.VALID), IntelligenceCapability.ACCESS_LAYA_ANALYSIS).allowed
    assert not service.authorize(_gate(DeviceSessionGateStatus.REVOKED), IntelligenceCapability.ACCESS_LAYA_ANALYSIS).allowed

    # Existing Owner/Admin surface only; no user global configuration surface.
    control_source = (ROOT / "dashboard/owner-dashboard/authoritative/DecisionIntelligenceControls.tsx").read_text(encoding="utf-8")
    backend_source = (ROOT / "dashboard/backend/owner_admin/decision_intelligence_router.py").read_text(encoding="utf-8")
    phase8_freeze = (ROOT / "docs/v2/phase8/PHASE8_DECISION_FREEZE.md").read_text(encoding="utf-8")
    risk_gate = (ROOT / "engine/risk/gate_v2.py").read_text(encoding="utf-8")
    assert "/api/v1/owner/admin/ai/intelligence" in control_source
    assert "/api/v1/user/ai/" not in control_source
    assert "RiskGateV2" in backend_source and "READ_ONLY/DISARMED" in backend_source
    assert "class RiskGateV2" in risk_gate
    assert "Live remains `READ_ONLY / DISARMED`" in phase8_freeze

    print("AI_INTELLIGENCE_STRATEGY_INDEPENDENCE=PASS")
    print("AI_INTELLIGENCE_ZERO_TO_N=PASS")
    print("AI_INTELLIGENCE_CORRELATED_MODEL_FLAG=PASS")
    print("AI_INTELLIGENCE_MARKET_WATCH_POLICY=PASS")
    print("AI_INTELLIGENCE_PROVIDER_QUEUE=PASS")
    print("AI_INTELLIGENCE_RISKGATE_AUTHORITY=PASS")
    print("AI_INTELLIGENCE_MULTI_BROKER_RESERVATION=PASS")
    print("AI_INTELLIGENCE_OD16_EGRESS=PASS")
    print("AI_INTELLIGENCE_S2_ENTITLEMENTS=PASS")
    print("AI_INTELLIGENCE_OWNER_DASHBOARD=PASS")
    print("LIVE_STATE=READ_ONLY/DISARMED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
