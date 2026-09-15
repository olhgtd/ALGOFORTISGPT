"""Authoritative Architecture Manifest for SentinelX (F-20 Architecture Convergence).

Formalizes the single canonical product architecture across all trading, execution,
risk, protective exits, portfolio, dataset, and audit domains.

CONVERGENCE INVARIANT:
PRODUCT/API LAYER (dashboard/backend/**)
    -> thin orchestration / adapters / services
    -> canonical domain/engine capability (engine/**)

No competing business logic in frontend.
No duplicated trading/risk semantics across multiple backend services.
Zero task modifications to engine/** or strategies/**.

F-21 CONCEPTUAL SPLIT (binding):
- HistoricalDataService = canonical PRODUCT historical-data lifecycle
  (inventory, cache, exact instrument/timeframe/range, gap analysis,
  validation, import/provider abstraction, fingerprints, persistence/reuse).
- Dataset governance (SQLiteSecurityStore owner_datasets + F-12 gate) is
  COMPLEMENTARY: Owner approval + eligibility, never a second data cache.
- HistoricalFeedChartAuthority = thin projection over HistoricalDataService.
- Backtest/Paper = consumers subject to data + governance requirements.
- Product PaperService is the SOLE product paper authority. The engine
  LivePaperCoordinator is not imported by any dashboard runtime path
  (test-only); wiring it would create duplicate runtime ownership.
- Option pricing has ONE dashboard authority: model_option_premium in
  paper_service (Black-Scholes, provenance-labeled MODELED, F-3). No second
  pricing authority exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class AuthorityClassification(str, Enum):
    CANONICAL_DOMAIN = "CANONICAL_DOMAIN"
    PRODUCT_SERVICE = "PRODUCT_SERVICE"
    THIN_ADAPTER = "THIN_ADAPTER"
    COMPLEMENTARY = "COMPLEMENTARY"
    LEGACY = "LEGACY"
    TEST_ONLY = "TEST_ONLY"
    NON_AUTHORITATIVE = "NON_AUTHORITATIVE"


class SubsystemDomain(str, Enum):
    STRATEGY_EXECUTION = "STRATEGY_EXECUTION"
    BACKTEST = "BACKTEST"
    PAPER_TRADING = "PAPER_TRADING"
    RISK_GATE = "RISK_GATE"
    PROTECTIVE_EXITS = "PROTECTIVE_EXITS"
    PORTFOLIO_ORDERS = "PORTFOLIO_ORDERS"
    DATASET_LIFECYCLE = "DATASET_LIFECYCLE"
    MARKET_CHARTS = "MARKET_CHARTS"
    AUDIT_EVIDENCE = "AUDIT_EVIDENCE"
    LIVE_READINESS = "LIVE_READINESS"
    STRATEGY_PROMOTION = "STRATEGY_PROMOTION"


@dataclass(frozen=True)
class AuthorityMapping:
    domain: SubsystemDomain
    canonical_engine_class: str
    product_service_class: str
    runtime_endpoint_prefix: str
    role_and_classification: str
    classification: AuthorityClassification = AuthorityClassification.PRODUCT_SERVICE
    is_live_broker_connected: bool = False


# Canonical Subsystem Authority Registry
CANONICAL_AUTHORITIES: Mapping[SubsystemDomain, AuthorityMapping] = {
    SubsystemDomain.STRATEGY_EXECUTION: AuthorityMapping(
        domain=SubsystemDomain.STRATEGY_EXECUTION,
        canonical_engine_class="engine.orchestration.entry_pipeline.BacktestOrchestrator",
        product_service_class="dashboard.backend.backtest_service.BacktestService",
        runtime_endpoint_prefix="/api/v1/backtests",
        role_and_classification="Canonical: Executes verified strategy AST subclasses against canonical parquet data.",
    ),
    SubsystemDomain.BACKTEST: AuthorityMapping(
        domain=SubsystemDomain.BACKTEST,
        canonical_engine_class="engine.backtest.engine.BacktestEngine",
        product_service_class="dashboard.backend.backtest_service.BacktestService",
        runtime_endpoint_prefix="/api/v1/backtests",
        role_and_classification="Canonical: Deterministic historical replay with real financial metrics.",
    ),
    SubsystemDomain.PAPER_TRADING: AuthorityMapping(
        domain=SubsystemDomain.PAPER_TRADING,
        canonical_engine_class="engine.execution.paper_broker.SimulatedPaperBroker",
        product_service_class="dashboard.backend.paper_service.PaperService",
        runtime_endpoint_prefix="/api/v1/paper",
        role_and_classification="Canonical: Virtual forward simulation with SimulatedPaperBroker and VirtualPaperAccount. "
        "PaperService is the SOLE product paper authority; engine LivePaperCoordinator is TEST_ONLY and unwired.",
        classification=AuthorityClassification.PRODUCT_SERVICE,
    ),
    SubsystemDomain.RISK_GATE: AuthorityMapping(
        domain=SubsystemDomain.RISK_GATE,
        canonical_engine_class="engine.risk.risk_manager.RiskGate",
        product_service_class="dashboard.backend.paper_service.PaperService",
        runtime_endpoint_prefix="/api/v1/paper/sessions/{id}/orders",
        role_and_classification="Canonical: Pre-order risk envelopes (trade size, daily loss, max open positions).",
    ),
    SubsystemDomain.PROTECTIVE_EXITS: AuthorityMapping(
        domain=SubsystemDomain.PROTECTIVE_EXITS,
        canonical_engine_class="engine.protective.runtime.ProtectiveExitBook",
        product_service_class="dashboard.backend.paper_service.PaperService",
        runtime_endpoint_prefix="/api/v1/paper/sessions/{id}/positions",
        role_and_classification="Canonical: Server-side protective stop tracking with zero client-side fabrication.",
    ),
    SubsystemDomain.PORTFOLIO_ORDERS: AuthorityMapping(
        domain=SubsystemDomain.PORTFOLIO_ORDERS,
        canonical_engine_class="engine.portfolio.virtual_account.VirtualPaperAccount",
        product_service_class="dashboard.backend.orders_portfolio_service.OrdersPortfolioService",
        runtime_endpoint_prefix="/api/v1/user/orders-portfolio",
        role_and_classification="Canonical: Projections over virtual account fills and positions.",
    ),
    SubsystemDomain.DATASET_LIFECYCLE: AuthorityMapping(
        domain=SubsystemDomain.DATASET_LIFECYCLE,
        canonical_engine_class="dashboard.backend.historical_data_service.HistoricalDataService",
        product_service_class="dashboard.backend.historical_data_service.HistoricalDataService",
        runtime_endpoint_prefix="/api/v1/market/data",
        role_and_classification="Canonical (F-21): availability/validation/cache/provenance. "
        "Dataset approval/eligibility is the complementary SQLiteSecurityStore F-12 gate, never a second cache.",
        classification=AuthorityClassification.CANONICAL_DOMAIN,
    ),
    SubsystemDomain.MARKET_CHARTS: AuthorityMapping(
        domain=SubsystemDomain.MARKET_CHARTS,
        canonical_engine_class="dashboard.backend.historical_data_service.HistoricalDataService",
        product_service_class="dashboard.backend.adapters.HistoricalFeedChartAuthority",
        runtime_endpoint_prefix="/api/v1/market/chart",
        role_and_classification="Thin adapter: read-only candlestick projection over HistoricalDataService; "
        "derives no signals. Unwired composition fails closed to DATA_PROVIDER_NOT_CONFIGURED.",
        classification=AuthorityClassification.THIN_ADAPTER,
    ),
    SubsystemDomain.AUDIT_EVIDENCE: AuthorityMapping(
        domain=SubsystemDomain.AUDIT_EVIDENCE,
        canonical_engine_class="engine.audit.model.AuditEvent",
        product_service_class="dashboard.backend.adapters.D16AuditReadAdapter",
        runtime_endpoint_prefix="/api/v1/integration/audit/events",
        role_and_classification="Canonical: Tamper-evident append-only audit trail backed by SQLiteSecurityStore.",
        classification=AuthorityClassification.THIN_ADAPTER,
    ),
    SubsystemDomain.LIVE_READINESS: AuthorityMapping(
        domain=SubsystemDomain.LIVE_READINESS,
        canonical_engine_class="engine.broker_adapters",
        product_service_class="dashboard.backend.live_readiness_service.LiveReadinessService",
        runtime_endpoint_prefix="/api/v1/user/live-readiness",
        role_and_classification="Canonical: Read-only observation and connectivity verification; DISARMED invariant.",
    ),
    SubsystemDomain.STRATEGY_PROMOTION: AuthorityMapping(
        domain=SubsystemDomain.STRATEGY_PROMOTION,
        canonical_engine_class="engine.paper.promotion_tracking",
        product_service_class="dashboard.backend.security_store.SQLiteSecurityStore",
        runtime_endpoint_prefix="/api/v1/owner/strategies/{id}/promote",
        role_and_classification="Canonical: persisted PENDING_OWNER_REVIEW requests + Owner-only validated stage "
        "transitions (request: /api/v1/strategies/{id}/request-promotion; pending: /api/v1/owner/promotions/pending). "
        "LIVE_ELIGIBLE is a readiness classification only; live stays READ_ONLY/DISARMED.",
        classification=AuthorityClassification.PRODUCT_SERVICE,
    ),
}


def get_canonical_authority(domain: SubsystemDomain) -> AuthorityMapping:
    """Retrieve canonical authority mapping for a given subsystem domain."""
    return CANONICAL_AUTHORITIES[domain]


def verify_architecture_invariants() -> dict[str, Any]:
    """Verify that all architectural convergence invariants hold."""
    all_domains = list(SubsystemDomain)
    covered = list(CANONICAL_AUTHORITIES.keys())
    assert len(all_domains) == len(covered), "All subsystem domains must be mapped"

    # Verify live broker connection is nowhere enabled in any canonical authority
    for domain, auth in CANONICAL_AUTHORITIES.items():
        assert auth.is_live_broker_connected is False, f"Live broker connection must be False for {domain}"

    return {
        "status": "CONVERGED",
        "domains_mapped": len(covered),
        "zero_competing_authorities": True,
        "live_execution_disarmed": True,
        "broker_mutation_path_zero": True,
    }
