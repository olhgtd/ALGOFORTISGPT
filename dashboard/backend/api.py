"""Governed FastAPI boundary.  It exposes state; it does not replace engine authority."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from .domain import (
    AccessRoute,
    AccountAccessStatus,
    ActivationStatus,
    Lifecycle,
    Role,
    ServiceEntitlementStatus,
    ServiceTermType,
    SessionRisk,
    StrategyQualityAuthority,
    UserIdentity,
    compute_service_expiry,
)
from .security import (
    AuthenticatorRegistry,
    MtlsAuthority,
    RejectingMtlsAuthority,
    RejectingWebAuthnVerifier,
    SecurityConfiguration,
    SecurityError,
    SecurityStatus,
    SecurityStatusAuthority,
    SessionService,
    WebAuthnCeremonyService,
    WebAuthnVerifier,
)
from .security_store import SQLiteSecurityStore, SecurityStoreError, AmbiguousSessionRefError
from .governance_store import SQLiteGovernanceStore
from .core_audit import MandatoryCoreSecurityAudit
from .services import DashboardSafeMode, StrategyService
from .strategy_projection import StrategyProjectionPending
from .strategy_execution import BoundedConformanceAuthority
from .historical_data_service import DataProviderNotConfiguredError, HistoricalDataError
from .adapters import (
    AccessRegistryReadAdapter,
    ChartRequest,
    D16AuditReadAdapter,
    MarketChartAuthority,
    OwnerConnectionsReadAdapter,
    OwnerDatasetsReadAdapter,
    OwnerStrategiesReadAdapter,
    PersistenceHealthReadAdapter,
    UnavailableMarketChartAuthority,
)
from .path_redaction import redact_server_paths, sanitize_report_for_client
from .auth_policy import AuthPolicyManager


class StrategySubmission(BaseModel):
    source: str = Field(min_length=1, max_length=200_000)
    protective_policy_identity: str | None = Field(default=None, max_length=200)


class SafeModeChange(BaseModel):
    enabled: bool


class SettingsProposalBody(BaseModel):
    key: str = Field(min_length=1, max_length=200)
    proposed_value: Any = None


class SettingsConfirmBody(BaseModel):
    proposal_id: str = Field(min_length=1, max_length=200)


class PromoteStrategyRequest(BaseModel):
    target_stage: str = Field(min_length=1, max_length=50)
    version: str | None = Field(default=None, max_length=100)
    source_sha256: str | None = Field(default=None, max_length=128)
    run_id: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=500)


class RequestPromotionBody(BaseModel):
    target_stage: str = Field(default="PAPER_ELIGIBLE", max_length=50)
    run_id: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=500)


class WebAuthnOptionsRequest(BaseModel):
    rp_id: str | None = Field(default=None, min_length=1, max_length=253)
    identifier: str | None = Field(default=None, min_length=1, max_length=254)


class ActivationRedemptionRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=254)
    activation_code: str = Field(min_length=1, max_length=128, repr=False)


class WebAuthnRegistrationComplete(BaseModel):
    challenge_id: str
    label: str = Field(min_length=1, max_length=200)
    is_backup_hardware: bool = False
    response: dict[str, Any]


class WebAuthnAuthenticationComplete(BaseModel):
    challenge_id: str
    response: dict[str, Any]


class CreateUserAccessRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=254)
    phone: str = Field(default="", max_length=50)
    role: str = Field(default="USER", max_length=50)
    plan: str = Field(default="Quant Professional", max_length=100)
    service_term_type: str = Field(default="3_MONTHS", max_length=50)
    custom_term_value: int | None = Field(default=None, ge=1, le=3650)
    custom_term_unit: str | None = Field(default=None, max_length=20)
    is_draft: bool = False
    notes: str = Field(default="Owner-created access record", max_length=1000)
    idempotency_key: str | None = Field(default=None, max_length=128)


class ServiceTermModificationRequest(BaseModel):
    service_term_type: str = Field(min_length=1, max_length=50)
    custom_term_value: int | None = Field(default=None, ge=1, le=3650)
    custom_term_unit: str | None = Field(default=None, max_length=20)
    notes: str = Field(default="", max_length=1000)


class ActionNotesRequest(BaseModel):
    notes: str = Field(default="", max_length=1000)


class WebAuthnBootstrapRegistrationComplete(WebAuthnRegistrationComplete):
    bootstrap_token: str = Field(min_length=32, max_length=512)


class LocalOwnerSetupRequest(BaseModel):
    display_name: str = Field(default="Super Owner", min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    bootstrap_token: str = Field(min_length=32, max_length=512)
    password: str = Field(min_length=8, max_length=256)
    confirm_password: str = Field(min_length=8, max_length=256)


class LocalLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class CredentialLifecycleChange(BaseModel):
    disabled: bool = False
    revoked: bool = False


class UpdateStrategyAllowanceRequest(BaseModel):
    sandbox: str = Field(min_length=1, max_length=20)
    allowance: str = Field(min_length=1, max_length=20)
    reason: str | None = Field(default=None, max_length=500)


class StrategyVisibilityRequest(BaseModel):
    visibility: str = Field(min_length=1, max_length=20)


class SuspendStrategyRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class RestoreStrategyRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=500)


class UpdateConnectionAllowanceRequest(BaseModel):
    allowance: str = Field(min_length=1, max_length=20)
    reason: str | None = Field(default=None, max_length=500)


class UpdateCapabilityAllowanceRequest(BaseModel):
    allowance: str = Field(min_length=1, max_length=20)
    reason: str | None = Field(default=None, max_length=500)


class UpdateDatasetApprovalRequest(BaseModel):
    approval: str = Field(min_length=1, max_length=20)
    reason: str | None = Field(default=None, max_length=500)


class BacktestGateRequest(BaseModel):
    strategy_id: str = Field(min_length=1, max_length=100)
    dataset_id: str = Field(min_length=1, max_length=100)


class CreateBacktestRequest(BaseModel):
    strategy_id: str = Field(min_length=1, max_length=100)
    version_id: str | None = Field(default=None, max_length=100)
    instrument: str = Field(default="NIFTY", max_length=50)
    timeframe: str = Field(default="1m", max_length=20)
    initial_capital: float = Field(default=500000.0, gt=0)
    policy: dict[str, Any] | None = None
    date_range: str = Field(default="2026-01-05", max_length=100)
    dataset_id: str = Field(default="nse-tick-primary", max_length=100)


class CreateWalkForwardRequest(BaseModel):
    strategy_id: str = Field(min_length=1, max_length=100)
    version_id: str | None = Field(default=None, max_length=100)
    dataset_id: str | None = Field(default=None, max_length=100)
    instrument: str = Field(default="NIFTY", max_length=50)
    timeframe: str = Field(default="1m", max_length=20)
    is_days: int = Field(default=20, ge=1, le=120)
    oos_days: int = Field(default=5, ge=1, le=120)
    max_windows: int = Field(default=12, ge=1, le=12)
    initial_capital: float = Field(default=500000.0, gt=0)
    policy: dict[str, Any] | None = None


class CreatePaperSessionRequest(BaseModel):
    strategy_id: str = Field(min_length=1, max_length=100)
    instrument: str = Field(default="NIFTY", max_length=50)
    timeframe: str = Field(default="1m", max_length=20)
    initial_capital: float = Field(default=50000.0, ge=1000.0, le=100_000_000.0)
    policy: dict[str, Any] | None = None
    data_source_mode: str = Field(default="HISTORICAL_REPLAY", max_length=50)
    date_range: str | None = None
    dataset_id: str | None = None


class IngestLiveQuoteRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=100)
    market: str = Field(default="NSE", max_length=20)
    instrument: str = Field(min_length=1, max_length=100)
    segment: str = Field(default="INDEX", max_length=20)
    underlying: str | None = None
    strike: float | None = None
    option_type: str | None = None
    expiry: str | None = None
    exchange_timestamp: str = Field(min_length=1, max_length=50)
    last_price: float = Field(gt=0.0)
    bid_price: float | None = None
    ask_price: float | None = None
    bid_quantity: int | None = None
    ask_quantity: int | None = None
    source: str = Field(default="LIVE_MARKET", max_length=50)


class FeedStateRequest(BaseModel):
    state: str = Field(min_length=1, max_length=50)


class PaperHoldRequest(BaseModel):
    hold: bool
    reason: str | None = Field(default=None, max_length=500)


class MarketDataImportRequest(BaseModel):
    instrument: str = Field(min_length=1, max_length=20)
    timeframe: str = Field(min_length=1, max_length=10)
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=50000)


class MarketDataFetchRequest(BaseModel):
    instrument: str = Field(min_length=1, max_length=20)
    timeframe: str = Field(min_length=1, max_length=10)
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    allow_fetch: bool = True


class HistoricalProviderConfigRequest(BaseModel):
    provider_id: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)
    supported_instruments: list[str] = Field(default_factory=list)
    supported_timeframes: list[str] = Field(default_factory=list)
    is_enabled: bool = True
    provider_type: str | None = Field(default=None, max_length=50)
    is_test: bool = False


class ToggleProviderRequest(BaseModel):
    enabled: bool


class HistoricalSyncRequest(BaseModel):
    instrument: str = Field(min_length=1, max_length=20)
    timeframe: str = Field(min_length=1, max_length=10)
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    provider_id: str | None = Field(default=None, max_length=50)
    force_refresh: bool = False


class ScheduledSyncConfigRequest(BaseModel):
    instrument: str = Field(min_length=1, max_length=20)
    timeframe: str = Field(min_length=1, max_length=10)
    frequency: str = Field(default="DAILY", max_length=20)
    lookback_days: int = Field(default=7, ge=1, le=365)
    provider_id: str | None = Field(default=None, max_length=50)
    is_enabled: bool = True


class RepairGapsRequest(BaseModel):
    dataset_id: str | None = Field(default=None, max_length=100)
    instrument: str | None = Field(default=None, max_length=20)
    timeframe: str | None = Field(default=None, max_length=10)
    provider_id: str | None = Field(default=None, max_length=50)


class RetireDatasetRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ReplaceDatasetRequest(BaseModel):
    replacement_dataset_id: str | None = Field(default=None, max_length=100)
    reason: str = Field(min_length=1, max_length=500)


class StrategyAssignmentRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)


class CreateUserConnectionRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=50)
    account_ref: str = Field(min_length=1, max_length=128)
    credential_ref: str | None = Field(default=None, max_length=256)


class UpdateUserConnectionRequest(BaseModel):
    account_ref: str | None = Field(default=None, max_length=128)
    credential_ref: str | None = Field(default=None, max_length=256)
    clear_credential_ref: bool = False
    status: str | None = Field(default=None, max_length=30)


class MapStrategyConnectionRequest(BaseModel):
    connection_id: str = Field(min_length=1, max_length=100)
    execution_mode: str = Field(default="LIVE_PAPER", max_length=20)
    strategy_version_id: str | None = Field(default=None, max_length=100)


class CreateDeploymentRequest(BaseModel):
    strategy_id: str = Field(min_length=1, max_length=100)
    strategy_version_id: str | None = Field(default=None, max_length=100)
    connection_id: str | None = Field(default=None, max_length=100)
    instrument: str = Field(min_length=1, max_length=50)
    timeframe: str = Field(default="1m", max_length=20)
    execution_mode: str = Field(default="LIVE_PAPER", max_length=20)
    risk_ref: str | None = Field(default=None, max_length=200)


class BlockDeploymentRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class LinkDeploymentRuntimeRequest(BaseModel):
    runtime_session_id: str | None = Field(default=None, max_length=100)


class UpdateUserConnectionStatusRequest(BaseModel):
    status: str = Field(min_length=1, max_length=30)
    reason: str | None = Field(default=None, max_length=500)


from datetime import datetime
from decimal import Decimal
from engine.portfolio.model import InstrumentIdentity
from engine.execution.quote import QuoteSnapshot
from engine.data.feeds.live_feed import LiveQuoteEvent
from .backtest_service import BacktestService, GovernanceRejectionError, InvalidBacktestParameterError
from .walkforward_service import WalkForwardService, WalkForwardError
from .paper_service import (
    PaperService,
    PaperSessionNotFoundError,
    InvalidPaperParameterError,
    ExternalLiveDataSourceRequiredError,
    LiveOptionQuoteUnavailableError,
    FeedNotConnectedError,
    StaleQuoteError,
    OutOfOrderQuoteError,
    WrongInstrumentError,
)
from .orders_portfolio_service import OrdersPortfolioService, ExecutionMode
from .deployment_service import DeploymentService, DeploymentError
from .live_readiness_service import LiveReadinessService, LiveAuthorityUnavailable, LiveExecutionDisabled
from pydantic import AwareDatetime, ConfigDict
from typing import Literal


class LiveIntentValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strategy_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    instrument_token: str = Field(pattern=r"^(NSE_FO\|[0-9]{1,20}|UNRESOLVED)$")
    side: Literal["BUY", "SELL"] = "BUY"
    quantity: Decimal = Field(gt=0, le=10000000, allow_inf_nan=False)
    timeframe: Literal["1m", "5m", "15m"] = "1m"
    originating_timestamp: AwareDatetime
    execution_mode: Literal["SHADOW", "LIVE"] = "LIVE"
    idempotency_key: str | None = Field(default=None, max_length=128)


def create_app(*, owner: UserIdentity | None = None, config: SecurityConfiguration | None = None,
               chart_authority: MarketChartAuthority | None = None,
               quality_authority: StrategyQualityAuthority | None = None,
               webauthn_verifier: WebAuthnVerifier | None = None,
               security_store: SQLiteSecurityStore | None = None,
               governance_store: SQLiteGovernanceStore | None = None,
               webauthn_ceremonies: WebAuthnCeremonyService | None = None,
               core_security_audit: MandatoryCoreSecurityAudit | None = None,
               audit_adapter: D16AuditReadAdapter | None = None,
               health_adapter: PersistenceHealthReadAdapter | None = None,
               access_adapter: AccessRegistryReadAdapter | None = None,
               strategies_adapter: OwnerStrategiesReadAdapter | None = None,
               connections_adapter: OwnerConnectionsReadAdapter | None = None,
               datasets_adapter: OwnerDatasetsReadAdapter | None = None,
               backtest_service: BacktestService | None = None,
               paper_service: PaperService | None = None,
               historical_data_service: Any | None = None,
               mtls_authority: MtlsAuthority | None = None,
               artifact_root: Path | None = None,
               auth_policy: AuthPolicyManager | None = None) -> FastAPI:
    """Create an app that is secure-by-default and has no password endpoint."""
    app = FastAPI(title="SentinelX Control Center API", version="9.0.0")
    @app.exception_handler(StrategyProjectionPending)
    async def strategy_projection_pending(request: Request, exc: StrategyProjectionPending):
        return JSONResponse(status_code=503, content={"detail": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def sanitized_live_validation_error(request: Request, exc: RequestValidationError):
        if request.url.path.startswith("/api/v1/auth/"):
            return JSONResponse(status_code=422, content={"detail": "Invalid authentication request"})
        if "/live-readiness" in request.url.path or request.url.path.startswith("/api/v1/live/") or "/shadow" in request.url.path:
            return JSONResponse(status_code=422, content={"detail": "INVALID_LIVE_READINESS_REQUEST"})
        return await request_validation_exception_handler(request, exc)
    configured_owner = owner or UserIdentity(uuid4(), Role.OWNER, Lifecycle.ACTIVE, "Owner")
    session_service = SessionService(config or SecurityConfiguration(), store=security_store)
    app.state.owner = configured_owner
    app.state.sessions = session_service
    app.state.authenticators = AuthenticatorRegistry()
    app.state.webauthn_verifier = webauthn_verifier or RejectingWebAuthnVerifier()
    app.state.security_store = security_store
    app.state.governance_store = governance_store
    app.state.webauthn_ceremonies = webauthn_ceremonies
    app.state.core_security_audit = core_security_audit
    app.state.auth_policy = auth_policy or AuthPolicyManager()
    status_verifier = webauthn_ceremonies or app.state.webauthn_verifier
    enrollment_reader = None
    if security_store is not None and webauthn_ceremonies is not None:
        enrollment_reader = lambda user_id: SecurityStatus(
            security_store.credential_status(user_id=user_id, rp_id=webauthn_ceremonies.normal_rp_id())
        )
    owner_init_reader = security_store.has_initialized_owner if security_store is not None else None
    app.state.security_status = SecurityStatusAuthority(
        config=app.state.sessions._config,
        registry=app.state.authenticators,
        verifier=status_verifier,
        enrollment_status_reader=enrollment_reader,
        owner_initialized_reader=owner_init_reader,
    )
    app.state.safe_mode = DashboardSafeMode()
    app.state.live_readiness_service = LiveReadinessService.from_environment(
        store=security_store, audit=core_security_audit, safe_mode=app.state.safe_mode
    ) if security_store is not None else None
    # StrategyService derives the immutable usr_<uuid>/strategies namespace
    # from the authoritative owner; passing a user-derived root here would
    # create a double-nested, non-canonical artifact path.
    app.state.strategies = StrategyService(artifact_root=artifact_root or Path("users"), governance_store=governance_store,
                                           security_store=security_store,
                                           conformance_authority=BoundedConformanceAuthority())
    app.state.chart_authority = chart_authority or UnavailableMarketChartAuthority()
    app.state.quality_authority = quality_authority or StrategyQualityAuthority()
    app.state.audit_adapter = audit_adapter or D16AuditReadAdapter(persistence_store=getattr(core_security_audit, "_audit_store", None))
    app.state.health_adapter = health_adapter or PersistenceHealthReadAdapter(persistence_store=getattr(core_security_audit, "_audit_store", None))
    app.state.access_adapter = access_adapter or AccessRegistryReadAdapter(security_store=security_store)
    app.state.strategies_adapter = strategies_adapter or OwnerStrategiesReadAdapter(security_store=security_store)
    app.state.connections_adapter = connections_adapter or OwnerConnectionsReadAdapter(security_store=security_store)
    app.state.datasets_adapter = datasets_adapter or OwnerDatasetsReadAdapter(security_store=security_store)
    _dataset_feed = historical_data_service if (
        historical_data_service is not None and hasattr(historical_data_service, "fetch_dataset")) else None
    app.state.backtest_service = backtest_service or (BacktestService(security_store=security_store, feed=_dataset_feed) if security_store is not None else None)
    if app.state.backtest_service is not None:
        app.state.backtest_service.configure_artifacts(governance_store, artifact_root or Path("users"))
        if getattr(app.state.backtest_service, "_feed", None) is None and _dataset_feed is not None:
            app.state.backtest_service._feed = _dataset_feed
    app.state.paper_service = paper_service or (PaperService(security_store=security_store, governance_store=governance_store, artifact_root=artifact_root or Path("users"), dataset_feed=_dataset_feed) if security_store is not None else None)
    if app.state.paper_service is not None and getattr(app.state.paper_service, "_dataset_feed", None) is None and _dataset_feed is not None:
        app.state.paper_service._dataset_feed = _dataset_feed
    # R-05: manual walk-forward/OOS productization around paper replay.
    app.state.walkforward_service = (
        WalkForwardService(security_store=security_store, backtest_service=app.state.backtest_service,
                           paper_service=app.state.paper_service)
        if security_store is not None and app.state.backtest_service is not None else None
    )
    # F-21 canonical historical-data lifecycle (product runtime storage
    # authority). Charting, import, inventory and coverage resolve here.
    app.state.historical_data_service = historical_data_service
    app.state.orders_portfolio_service = (
        OrdersPortfolioService(app.state.paper_service, live_readiness=app.state.live_readiness_service) if app.state.paper_service is not None else None
    )
    # P1-A (R-07): persistent deployment orchestration over canonical authorities.
    # State management only — no execution handle beyond the paper service
    # reference used for runtime-session ownership checks. No broker handle exists.
    app.state.deployment_service = (
        DeploymentService(
            security_store=security_store,
            governance_store=governance_store,
            artifact_root=artifact_root or Path("users"),
            paper_service=app.state.paper_service,
        ) if security_store is not None else None
    )
    # This is process-wired rather than request-derived. Until a deployment
    # supplies authoritative TLS or proven trusted-edge evidence, reject all
    # mTLS assertions rather than trusting a caller-controlled HTTP header.
    app.state.mtls_authority = mtls_authority or RejectingMtlsAuthority()

    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def backtest_lifespan(_app):
        # DB-004: finish bounded repair before dependent workers/routes are ready.
        app.state.strategies._projection.reconcile_startup()
        if app.state.backtest_service is not None:
            app.state.backtest_service.jobs.start()
        if app.state.walkforward_service is not None:
            app.state.walkforward_service.start()
        try:
            yield
        finally:
            if app.state.backtest_service is not None:
                app.state.backtest_service.jobs.shutdown()
            if app.state.walkforward_service is not None:
                app.state.walkforward_service.shutdown()
    app.router.lifespan_context = backtest_lifespan

    def _verified_mtls(request: Request) -> bool:
        try:
            return bool(app.state.mtls_authority.verified(request))
        except Exception:
            return False

    def session_from_header(authorization: str | None = Header(default=None)):
        token = authorization.removeprefix("Bearer ").strip() if authorization else None
        try:
            return session_service.require(token)
        except SecurityError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required") from exc

    def mutable_session(session=Depends(session_from_header)):
        try:
            return session_service.require(session.token, mutable=True)
        except SecurityError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="step-up authentication required") from exc

    def owner_session(session=Depends(session_from_header)):
        if session.user.role is not Role.OWNER:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="owner authorization required")
        return session

    def _client_ip(req: Request) -> str:
        forwarded = req.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return req.client.host if req.client else "127.0.0.1"

    def _check_cooldown(tracker, key: str) -> None:
        is_locked, cooldown = tracker.is_locked_out(key)
        if is_locked:
            raise HTTPException(
                status_code=429,
                detail=f"RATE_LIMIT_COOLDOWN: Cooldown active for {cooldown}s",
                headers={"Retry-After": str(cooldown)},
            )

    def _check_expensive_throttle(user_id: str | UUID) -> None:
        if not hasattr(app.state, "auth_policy") or app.state.auth_policy is None:
            return
        key = f"expensive:{str(user_id)}"
        throttled, rem = app.state.auth_policy.expensive_limiter.record_request(key, max_requests=30, window_seconds=60)
        if throttled:
            raise HTTPException(
                status_code=429,
                detail=f"RATE_LIMIT_EXCEEDED: Too many requests. Retry after {rem}s",
                headers={"Retry-After": str(rem)},
            )

    def live_authority():
        if app.state.live_readiness_service is None:
            raise HTTPException(503, "LIVE_AUTHORITY_UNAVAILABLE")
        return app.state.live_readiness_service

    def live_call(method, *args):
        try:
            return method(*args)
        except LiveAuthorityUnavailable:
            raise HTTPException(503, "CORE_AUDIT_UNAVAILABLE") from None
        except LiveExecutionDisabled:
            raise HTTPException(403, "EXECUTION_DISABLED") from None

    def bind_canonical_user_authority(service, user_id: str) -> bool:
        # NF-R203-04: resolve the session user's canonical user_connections
        # record before any operational use. Best-effort: False keeps honest
        # UNCONFIGURED truth; no process-global credential is ever consulted.
        try:
            return service.bind_operational_connection(
                str(user_id), security_store=app.state.security_store,
                credential_provider=None)
        except Exception:
            return False

    @app.get("/api/v1/user/live-readiness")
    def user_live_readiness(session=Depends(session_from_header), service=Depends(live_authority)):
        bind_canonical_user_authority(service, str(session.user.user_id))
        return service.readiness(str(session.user.user_id))

    @app.post("/api/v1/user/live-readiness/refresh")
    def refresh_live_readiness(session=Depends(session_from_header), service=Depends(live_authority)):
        bind_canonical_user_authority(service, str(session.user.user_id))
        return live_call(service.refresh, str(session.user.user_id))

    @app.post("/api/v1/user/live-readiness/intents")
    def validate_live_intent(body: LiveIntentValidationRequest, session=Depends(session_from_header), service=Depends(live_authority)):
        bind_canonical_user_authority(service, str(session.user.user_id))
        return live_call(service.validate, str(session.user.user_id), body.model_dump())

    @app.post("/api/v1/user/shadow/intents")
    def validate_shadow_intent(body: LiveIntentValidationRequest, session=Depends(session_from_header), service=Depends(live_authority)):
        bind_canonical_user_authority(service, str(session.user.user_id))
        payload = body.model_dump()
        payload["execution_mode"] = "SHADOW"
        return live_call(service.validate, str(session.user.user_id), payload)

    @app.get("/api/v1/owner/live-readiness")
    def owner_live_readiness(session=Depends(owner_session), service=Depends(live_authority)):
        return service.oversight()

    @app.post("/api/v1/owner/live-readiness/hold")
    def live_global_hold(body: SafeModeChange, session=Depends(owner_session), stepped=Depends(mutable_session), service=Depends(live_authority)):
        return live_call(service.set_hold, str(session.user.user_id), body.enabled)

    # P3: one route object per (path, method) with a unique operation ID so
    # OpenAPI generation stays warning-free. All of them deny mutation.
    def disabled_live_mutation(session=Depends(session_from_header), service=Depends(live_authority)):
        return live_call(service.deny_mutation, str(session.user.user_id))

    for _deny_method, _deny_path in (
        ("POST", "/api/v1/user/live-readiness/arm"),
        ("POST", "/api/v1/user/shadow/arm"),
        ("POST", "/api/v1/live/orders"),
        ("PUT", "/api/v1/live/orders"),
        ("PATCH", "/api/v1/live/orders"),
        ("DELETE", "/api/v1/live/orders"),
        ("POST", "/api/v1/live/orders/{order_path:path}"),
        ("PUT", "/api/v1/live/orders/{order_path:path}"),
        ("PATCH", "/api/v1/live/orders/{order_path:path}"),
        ("DELETE", "/api/v1/live/orders/{order_path:path}"),
        ("POST", "/api/v1/shadow/orders"),
        ("PUT", "/api/v1/shadow/orders"),
        ("PATCH", "/api/v1/shadow/orders"),
        ("DELETE", "/api/v1/shadow/orders"),
        ("POST", "/api/v1/shadow/orders/{order_path:path}"),
        ("PUT", "/api/v1/shadow/orders/{order_path:path}"),
        ("PATCH", "/api/v1/shadow/orders/{order_path:path}"),
        ("DELETE", "/api/v1/shadow/orders/{order_path:path}"),
    ):
        _deny_oid = ("deny_live_mutation_" + _deny_path.strip("/").replace("/", "_").replace("{", "").replace("}", "").replace(":", "")
                      + "_" + _deny_method.lower())
        app.api_route(_deny_path, methods=[_deny_method], operation_id=_deny_oid)(disabled_live_mutation)

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"service": "sentinelx-control-center", "status": "OK", "safe_mode": app.state.safe_mode.enabled}

    # ── Phase BI-1: Read-only integration endpoints ──

    @app.get("/api/v1/integration/audit/events")
    def integration_audit_events(limit: int = Query(default=50, ge=1, le=500), offset: int = Query(default=0, ge=0), event_family: str | None = None, severity: str | None = None, session=Depends(owner_session)) -> dict[str, object]:
        """Read-only D16 audit events projection from persistence authority."""
        from datetime import datetime, timezone
        adapter = getattr(app.state, "audit_adapter", None)
        if adapter is None:
            return {"source": "BACKEND", "trust": "UNKNOWN", "as_of_utc": datetime.now(timezone.utc).isoformat(), "total_count": 0, "events": []}
        return adapter.read_audit_events(limit=limit, offset=offset, event_family=event_family, severity=severity)

    @app.get("/api/v1/integration/system/health")
    def integration_system_health(session=Depends(owner_session)) -> dict[str, object]:
        """Read-only persistence and subsystem health projection."""
        from datetime import datetime, timezone
        adapter = getattr(app.state, "health_adapter", None)
        if adapter is None:
            return {
                "source": "BACKEND",
                "trust": "UNKNOWN",
                "as_of_utc": datetime.now(timezone.utc).isoformat(),
                "adapter_reachable": True,
                "database_connected": False,
                "schema_version": None,
                "journal_mode": "UNKNOWN",
                "audit_store_operational": False,
                "audit_event_count": 0,
                "subsystems": {
                    "backend_api": "OPERATIONAL",
                    "persistence": "UNAVAILABLE",
                    "audit_journal": "UNAVAILABLE",
                    "engine_orchestrator": "NOT_CONNECTED",
                    "broker_adapters": "DEFERRED",
                    "market_data_feeds": "NOT_CONNECTED",
                    "risk_runtime": "DEFERRED",
                    "service_entitlement": "DEFERRED",
                },
            }
        return adapter.read_persistence_health()

    @app.get("/api/v1/system/time")
    def system_time() -> dict[str, object]:
        """Read-only current UTC operational time."""
        from datetime import datetime, timezone
        return {
            "source": "BACKEND",
            "as_of_utc": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/api/v1/integration/access/records")
    def integration_access_records(session=Depends(owner_session)) -> dict[str, object]:
        """Read-only Owner Access Registry projection from security store authority."""
        from datetime import datetime, timezone
        adapter = getattr(app.state, "access_adapter", None)
        if adapter is None:
            return {
                "source": "BACKEND",
                "trust": "UNKNOWN",
                "as_of_utc": datetime.now(timezone.utc).isoformat(),
                "total_count": 0,
                "records": [],
                "error": "ACCESS_ADAPTER_UNAVAILABLE",
            }
        return adapter.read_access_records()

    @app.get("/api/v1/security/status")
    def security_status() -> dict[str, object]:
        return app.state.security_status.public_status(configured_owner.user_id)

    def ceremony_service() -> WebAuthnCeremonyService:
        service = app.state.webauthn_ceremonies
        if service is None or not service.configured:
            raise HTTPException(status_code=503, detail="WebAuthn ceremony authority is not configured")
        return service

    def mandatory_audit(action: str, *, rejected: bool = False, actor_id: UUID | None = None) -> None:
        audit = app.state.core_security_audit
        if audit is None:
            raise HTTPException(status_code=503, detail="authoritative security audit is not configured")
        try:
            audit.record(actor_id=actor_id or configured_owner.user_id, action=action, payload={}, rejected=rejected)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="authoritative security audit unavailable") from exc

    @app.post("/api/v1/auth/webauthn/authentication/options")
    def webauthn_authentication_options(body: WebAuthnOptionsRequest, request: Request) -> dict[str, object]:
        """Public challenge issuance only; it never creates a session."""
        id_key = f"auth_opt:{body.identifier.strip().lower()}" if body.identifier and body.identifier.strip() else f"ip:{_client_ip(request)}"
        if hasattr(app.state, "auth_policy") and app.state.auth_policy is not None:
            _check_cooldown(app.state.auth_policy.login_limiter, id_key)
        try:
            mandatory_audit("WEBAUTHN_AUTHENTICATION_CHALLENGE")
            service = ceremony_service()
            user = service.authentication_identity(body.identifier, configured_owner)
            return service.issue_authentication(user=user, rp_id=body.rp_id or service.normal_rp_id())
        except (SecurityError, SecurityStoreError) as exc:
            raise HTTPException(status_code=403, detail="WebAuthn authentication unavailable") from exc
    @app.post("/api/v1/auth/webauthn/authentication/complete")
    def webauthn_authentication_complete(body: WebAuthnAuthenticationComplete,
                                         request: Request) -> dict[str, object]:
        """The sole production API route that issues a normal bearer session."""
        ip_key = f"ip:{_client_ip(request)}"
        if hasattr(app.state, "auth_policy") and app.state.auth_policy is not None:
            _check_cooldown(app.state.auth_policy.login_limiter, ip_key)
        try:
            mandatory_audit("WEBAUTHN_AUTHENTICATION_ATTEMPT")
            user = ceremony_service().assertion_identity(body.response)
            user_key = f"auth_user:{user.user_id}"
            if hasattr(app.state, "auth_policy") and app.state.auth_policy is not None:
                _check_cooldown(app.state.auth_policy.login_limiter, user_key)
            credential_id, rp_id = ceremony_service().complete_authentication(
                user=user, challenge_id=body.challenge_id, response=body.response,
            )
            route = AccessRoute.BREAK_GLASS if rp_id == "sentinelx-recovery.com" else AccessRoute.NORMAL
            session = session_service.issue(
                user=user, route=route,
                mtls_verified=_verified_mtls(request),
                step_up_satisfied=True,
                credential_id=bytes.fromhex(credential_id),
            )
            if hasattr(app.state, "auth_policy") and app.state.auth_policy is not None:
                app.state.auth_policy.login_limiter.record_success(user_key)
                app.state.auth_policy.login_limiter.record_success(ip_key)
            return {"access_token": session.token, "expires_at_utc": session.expires_at.isoformat(), "credential_id": credential_id,
                    "subject": str(session.user.user_id), "role": session.user.role.value, "sx_id": session.user.sx_id}
        except (SecurityError, SecurityStoreError, ValueError, sqlite3.IntegrityError) as exc:
            if hasattr(app.state, "auth_policy") and app.state.auth_policy is not None:
                locked, rem = app.state.auth_policy.login_limiter.record_failure(ip_key)
                if locked:
                    raise HTTPException(status_code=429, detail=f"RATE_LIMIT_COOLDOWN: Cooldown active for {rem}s", headers={"Retry-After": str(rem)}) from exc
            raise HTTPException(status_code=401, detail="WebAuthn authentication failed") from exc

    @app.post("/api/v1/auth/webauthn/activation/redeem")
    def redeem_user_activation(body: ActivationRedemptionRequest, request: Request):
        act_key = f"act:{body.identifier.strip().lower()}"
        if hasattr(app.state, "auth_policy") and app.state.auth_policy is not None:
            _check_cooldown(app.state.auth_policy.otp_limiter, act_key)
        try:
            service = ceremony_service()
            subject = service._store.activation_subject(body.identifier, body.activation_code)
            mandatory_audit("USER_ACTIVATION_REDEMPTION", actor_id=UUID(subject["user_id"]))
            res = service.redeem_user_activation(identifier=body.identifier, code=body.activation_code)
            if hasattr(app.state, "auth_policy") and app.state.auth_policy is not None:
                app.state.auth_policy.otp_limiter.record_success(act_key)
            return res
        except (SecurityError, SecurityStoreError, ValueError, sqlite3.IntegrityError, KeyError) as exc:
            if hasattr(app.state, "auth_policy") and app.state.auth_policy is not None:
                locked, rem = app.state.auth_policy.otp_limiter.record_failure(act_key)
                if locked:
                    raise HTTPException(status_code=429, detail=f"RATE_LIMIT_COOLDOWN: Cooldown active for {rem}s", headers={"Retry-After": str(rem)}) from exc
            raise HTTPException(status_code=403, detail="Activation unavailable") from None

    @app.post("/api/v1/auth/webauthn/activation/complete")
    def complete_user_activation(body: WebAuthnRegistrationComplete):
        try:
            service = ceremony_service()
            subject = service._store.challenge_subject(body.challenge_id, "USER_ENROLLMENT")
            mandatory_audit("USER_CREDENTIAL_ENROLLMENT", actor_id=UUID(subject["user_id"]))
            credential_id = service.complete_user_enrollment(challenge_id=body.challenge_id, label=body.label, response=body.response)
            return {"registered": True, "credential_id": credential_id, "authentication_required": True}
        except (SecurityError, SecurityStoreError, ValueError, sqlite3.IntegrityError):
            raise HTTPException(status_code=422, detail="User enrollment failed; request a new invitation if necessary") from None

    @app.post("/api/v1/auth/webauthn/registration/options")
    def webauthn_registration_options(body: WebAuthnOptionsRequest, session=Depends(mutable_session)) -> dict[str, object]:
        """Credential enrollment is session- and step-up-gated; no public enrollment."""
        try:
            mandatory_audit("WEBAUTHN_REGISTRATION_CHALLENGE")
            return ceremony_service().issue_registration(
                user=session.user, rp_id=body.rp_id, label="Pending enrollment", is_backup_hardware=False,
            )
        except (SecurityError, SecurityStoreError) as exc:
            raise HTTPException(status_code=403, detail="WebAuthn registration unavailable") from exc

    @app.post("/api/v1/auth/webauthn/bootstrap-registration/options")
    def webauthn_bootstrap_registration_options(body: WebAuthnOptionsRequest,
                                                x_sentinelx_bootstrap: str | None = Header(default=None)) -> dict[str, object]:
        """Consumes no authority itself; a trusted-host-created token is required."""
        if not x_sentinelx_bootstrap:
            raise HTTPException(status_code=401, detail="bootstrap authorization required")
        try:
            mandatory_audit("WEBAUTHN_BOOTSTRAP_VALIDATION")
            issued = ceremony_service().issue_bootstrap_registration(user=configured_owner, bootstrap_token=x_sentinelx_bootstrap, rp_id=body.rp_id or ceremony_service().normal_rp_id())
            issued.pop("bootstrap_token", None)
            return issued
        except (SecurityError, SecurityStoreError) as exc:
            raise HTTPException(status_code=403, detail="bootstrap enrollment unavailable") from exc

    @app.post("/api/v1/auth/webauthn/registration/complete")
    def webauthn_registration_complete(body: WebAuthnRegistrationComplete, session=Depends(mutable_session)) -> dict[str, object]:
        try:
            mandatory_audit("WEBAUTHN_CREDENTIAL_ENROLLMENT")
            credential_id = ceremony_service().complete_registration(
                user=session.user, challenge_id=body.challenge_id, label=body.label,
                is_backup_hardware=body.is_backup_hardware, response=body.response,
            )
            return {"credential_id": credential_id, "registered": True}
        except (SecurityError, SecurityStoreError, ValueError, sqlite3.IntegrityError) as exc:
            raise HTTPException(status_code=422, detail="WebAuthn registration failed") from exc

    @app.post("/api/v1/auth/webauthn/bootstrap-registration/complete")
    def webauthn_bootstrap_registration_complete(body: WebAuthnBootstrapRegistrationComplete) -> dict[str, object]:
        try:
            mandatory_audit("WEBAUTHN_BOOTSTRAP_CONSUMPTION")
            credential_id = ceremony_service().complete_bootstrap_registration(
                user=configured_owner, bootstrap_token=body.bootstrap_token,
                challenge_id=body.challenge_id, label=body.label, response=body.response,
            )
            return {"credential_id": credential_id, "registered": True, "security_setup": "ENROLLMENT_INCOMPLETE"}
        except (SecurityError, SecurityStoreError, ValueError, sqlite3.IntegrityError) as exc:
            raise HTTPException(status_code=422, detail="bootstrap WebAuthn registration failed") from exc

    @app.post("/api/v1/auth/local/setup")
    def local_owner_setup(body: LocalOwnerSetupRequest, request: Request) -> dict[str, object]:
        """First-run owner provisioning for local private desktop deployment."""
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store is unavailable")

        if body.password != body.confirm_password:
            raise HTTPException(status_code=422, detail="Passwords do not match")

        if app.state.security_store.has_initialized_owner():
            raise HTTPException(status_code=403, detail="Super Owner is already initialized; re-provisioning forbidden")

        ip_key = f"ip:{_client_ip(request)}"
        if hasattr(app.state, "auth_policy") and app.state.auth_policy is not None:
            _check_cooldown(app.state.auth_policy.login_limiter, ip_key)

        try:
            if getattr(app.state, "core_security_audit", None) is not None:
                mandatory_audit("LOCAL_OWNER_PROVISIONING")
            owner_identity = app.state.security_store.initialize_owner_password(
                token=body.bootstrap_token.strip(),
                display_name=body.display_name.strip(),
                email=body.email.strip(),
                password=body.password,
            )
            session = session_service.issue(
                user=owner_identity,
                route=AccessRoute.NORMAL,
                mtls_verified=False,
                step_up_satisfied=True,
            )
            if hasattr(app.state, "auth_policy") and app.state.auth_policy is not None:
                app.state.auth_policy.login_limiter.record_success(ip_key)

            return {
                "access_token": session.token,
                "expires_at_utc": session.expires_at.isoformat(),
                "subject": str(session.user.user_id),
                "role": session.user.role.value,
                "sx_id": session.user.sx_id,
            }
        except (SecurityError, SecurityStoreError, ValueError) as exc:
            if hasattr(app.state, "auth_policy") and app.state.auth_policy is not None:
                locked, rem = app.state.auth_policy.login_limiter.record_failure(ip_key)
                if locked:
                    raise HTTPException(status_code=429, detail=f"RATE_LIMIT_COOLDOWN: Cooldown active for {rem}s", headers={"Retry-After": str(rem)}) from exc
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/v1/auth/local/login")
    def local_login(body: LocalLoginRequest, request: Request) -> dict[str, object]:
        """Local desktop email + password authentication."""
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store is unavailable")

        clean_email = body.email.strip().lower()
        ip_key = f"ip:{_client_ip(request)}"
        email_key = f"auth_email:{clean_email}"

        if hasattr(app.state, "auth_policy") and app.state.auth_policy is not None:
            _check_cooldown(app.state.auth_policy.login_limiter, ip_key)
            _check_cooldown(app.state.auth_policy.login_limiter, email_key)

        user = app.state.security_store.verify_owner_password(
            email=clean_email,
            password=body.password,
        )

        if user is None:
            if hasattr(app.state, "auth_policy") and app.state.auth_policy is not None:
                app.state.auth_policy.login_limiter.record_failure(email_key)
                locked, rem = app.state.auth_policy.login_limiter.record_failure(ip_key)
                if locked:
                    raise HTTPException(status_code=429, detail=f"RATE_LIMIT_COOLDOWN: Cooldown active for {rem}s", headers={"Retry-After": str(rem)})
            if getattr(app.state, "core_security_audit", None) is not None:
                try:
                    mandatory_audit("LOCAL_LOGIN_FAILED", rejected=True)
                except Exception:
                    pass
            raise HTTPException(status_code=401, detail="INVALID_EMAIL_OR_PASSWORD")

        try:
            if getattr(app.state, "core_security_audit", None) is not None:
                mandatory_audit("LOCAL_LOGIN_SUCCESS")
            session = session_service.issue(
                user=user,
                route=AccessRoute.NORMAL,
                mtls_verified=False,
                step_up_satisfied=True,
            )
            if hasattr(app.state, "auth_policy") and app.state.auth_policy is not None:
                app.state.auth_policy.login_limiter.record_success(ip_key)
                app.state.auth_policy.login_limiter.record_success(email_key)

            return {
                "access_token": session.token,
                "expires_at_utc": session.expires_at.isoformat(),
                "subject": str(session.user.user_id),
                "role": session.user.role.value,
                "sx_id": session.user.sx_id,
            }
        except SecurityError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @app.post("/api/v1/security/credentials/{credential_id}/lifecycle")
    def credential_lifecycle(credential_id: str, change: CredentialLifecycleChange, session=Depends(mutable_session)) -> dict[str, object]:
        if session.user.role is not Role.OWNER or app.state.security_store is None:
            raise HTTPException(status_code=403, detail="owner security authority required")
        try:
            mandatory_audit("WEBAUTHN_CREDENTIAL_REVOKE" if change.revoked else "WEBAUTHN_CREDENTIAL_DISABLE")
            changed = app.state.security_store.set_credential_state(
                credential_id=bytes.fromhex(credential_id), disabled=change.disabled, revoked=change.revoked,
            )
            return {"credential_id": credential_id, "changed": changed, "disabled": change.disabled, "revoked": change.revoked}
        except (SecurityStoreError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="credential lifecycle change rejected") from exc

    @app.post("/api/v1/security/sessions/revoke")
    def revoke_current_session(session=Depends(mutable_session)) -> dict[str, bool]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="durable security store unavailable")
        mandatory_audit("SESSION_REVOKE")
        return {"revoked": app.state.security_store.revoke_session(session.token)}

    @app.get("/api/v1/overview")
    def overview(session=Depends(session_from_header)) -> dict[str, object]:
        return {"owner_id": str(session.user.user_id), "role": session.user.role.value, "session_risk": session.risk.value, "safe_mode": app.state.safe_mode.enabled, "live_state": {"value": None, "trust": "UNKNOWN", "as_of_utc": None}}

    @app.get("/api/v1/market/chart")
    def market_chart(instrument: str, timeframe: str, mode: str,
                     start_date: str | None = None, end_date: str | None = None,
                     limit: int = 1000,
                     session=Depends(session_from_header)) -> dict[str, object]:
        if mode not in {"LIVE", "FROZEN_HISTORICAL", "BACKTEST"}:
            raise HTTPException(status_code=422, detail="unsupported chart mode")
        if limit < 1 or limit > 5000:
            raise HTTPException(status_code=422, detail="limit must be between 1 and 5000")
        for label, value in (("start_date", start_date), ("end_date", end_date)):
            if value is not None:
                try:
                    datetime.strptime(value, "%Y-%m-%d")
                except ValueError:
                    raise HTTPException(status_code=422, detail=f"invalid {label}, expected YYYY-MM-DD") from None
        return app.state.chart_authority.chart(ChartRequest(instrument=instrument, timeframe=timeframe, mode=mode,
                                                            start_date=start_date, end_date=end_date, limit=limit))

    @app.get("/api/v1/market/timeframes")
    def market_timeframes(instrument: str, mode: str, session=Depends(session_from_header)) -> dict[str, object]:
        if mode not in {"LIVE", "FROZEN_HISTORICAL", "BACKTEST"}:
            raise HTTPException(status_code=422, detail="unsupported chart mode")
        return {"timeframes": app.state.chart_authority.available_timeframes(instrument, mode)}

    def historical_data_service_or_503() -> Any:
        service = getattr(app.state, "historical_data_service", None)
        if service is None:
            raise HTTPException(status_code=503, detail="DATA_PROVIDER_NOT_CONFIGURED: historical data service unavailable")
        return service

    @app.get("/api/v1/market/data/inventory")
    def market_data_inventory(session=Depends(session_from_header)) -> dict[str, object]:
        """F-21: list locally cached instrument/timeframe datasets with fingerprints."""
        service = historical_data_service_or_503()
        try:
            items = service.list_inventory()
        except Exception as exc:
            logger.exception("Inventory service error")
            raise HTTPException(status_code=500, detail="Historical inventory service unavailable") from exc
        return {"datasets": [item.__dict__ for item in items]}

    @app.get("/api/v1/market/data/coverage")
    def market_data_coverage(instrument: str, timeframe: str, start_date: str, end_date: str,
                             session=Depends(session_from_header)) -> dict[str, object]:
        """F-21: exact available/missing range for instrument+timeframe+date range."""
        from datetime import date as _date
        service = historical_data_service_or_503()
        try:
            requested_start = _date.fromisoformat(start_date)
            requested_end = _date.fromisoformat(end_date)
        except ValueError:
            raise HTTPException(status_code=422, detail="start_date/end_date must be YYYY-MM-DD") from None
        try:
            missing = service.calculate_missing_intervals(
                instrument=instrument, timeframe=timeframe,
                requested_start=requested_start, requested_end=requested_end)
            inventory = service.check_inventory(instrument, timeframe)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Coverage service error")
            raise HTTPException(status_code=500, detail="Historical coverage service unavailable") from exc
        return {
            "instrument": instrument.upper().strip(),
            "timeframe": timeframe.strip(),
            "requested_start": start_date,
            "requested_end": end_date,
            "available": inventory.__dict__ if inventory is not None else None,
            "missing": [{"start": interval.start.isoformat(), "end": interval.end.isoformat()} for interval in missing],
            "complete": len(missing) == 0,
        }

    @app.post("/api/v1/market/data/import")
    def market_data_import(body: MarketDataImportRequest,
                           session=Depends(mutable_session)) -> dict[str, object]:
        """F-21: Owner local import through the product service (no repo/filesystem paths)."""
        if session.user.role is not Role.OWNER:
            raise HTTPException(status_code=403, detail="owner authorization required")
        _check_expensive_throttle(session.user.user_id)
        import pandas as _pd
        service = historical_data_service_or_503()
        if not body.rows or len(body.rows) > 50000:
            raise HTTPException(status_code=422, detail="rows must contain 1..50000 bars")
        try:
            frame = _pd.DataFrame(body.rows)
        except Exception as exc:
            logger.error("Invalid market data import rows: %s", exc)
            raise HTTPException(status_code=422, detail="INVALID_IMPORT_PAYLOAD") from exc
        try:
            item = service.import_dataframe(frame, instrument=body.instrument,
                                            timeframe=body.timeframe, source_name="OWNER_LOCAL_IMPORT")
        except Exception as exc:
            message = str(exc)
            if "DATA_PROVIDER_NOT_CONFIGURED" in message or "DATA_UNAVAILABLE" in message:
                raise HTTPException(status_code=404, detail=message) from exc
            logger.error("Market data import failed: %s", exc)
            raise HTTPException(status_code=422, detail="MARKET_DATA_IMPORT_FAILED") from exc
        _record_security_audit(
            event_type="MARKET_DATA_IMPORTED",
            actor_id=session.user.user_id,
            details={"instrument": item.instrument, "timeframe": item.timeframe,
                     "row_count": item.row_count, "sha256": item.file_sha256},
        )
        return {"imported": item.__dict__}

    @app.post("/api/v1/market/data/request")
    def market_data_request(
        body: MarketDataFetchRequest,
        session=Depends(session_from_header),
    ) -> dict[str, object]:
        """F-21: request historical data from canonical service."""
        from datetime import date as _date
        if body.allow_fetch and session.user.role is not Role.OWNER:
            raise HTTPException(status_code=403, detail="owner authorization required to provision or download historical data")
        service = historical_data_service_or_503()
        try:
            st = _date.fromisoformat(body.start_date)
            et = _date.fromisoformat(body.end_date)
        except Exception:
            raise HTTPException(status_code=422, detail="invalid start_date or end_date, expected YYYY-MM-DD")
        try:
            res = service.request_data(body.instrument, body.timeframe, st, et, auto_provision=body.allow_fetch)
            cached = res[1] if isinstance(res, tuple) else res
            if session.user.role is not Role.OWNER and app.state.security_store is not None:
                ds_id = f"{body.instrument.lower().strip()}-{body.timeframe.lower().strip()}-primary"
                ds = app.state.security_store.get_owner_dataset(ds_id)
                if ds is not None and ds.get("ownerApproval") != "APPROVED":
                    raise HTTPException(
                        status_code=403,
                        detail=f"dataset '{ds_id}' requires owner approval for consumption",
                    )
            return {
                "status": "AVAILABLE",
                "instrument": body.instrument.upper().strip(),
                "timeframe": body.timeframe.strip(),
                "dataset": cached.__dict__ if cached else None,
            }
        except HTTPException:
            raise
        except Exception as exc:
            msg = str(exc)
            if "DATA_PROVIDER_NOT_CONFIGURED" in msg:
                raise HTTPException(status_code=503, detail=msg)
            elif "DATA_UNAVAILABLE" in msg or "NO_DATA" in msg:
                raise HTTPException(status_code=404, detail=msg)
            raise HTTPException(status_code=422, detail=msg)

    @app.post("/api/v1/settings/safe-mode")
    def set_safe_mode(change: SafeModeChange, session=Depends(mutable_session)) -> dict[str, bool]:
        if session.user.role is not Role.OWNER:
            raise HTTPException(status_code=403, detail="owner role required")
        app.state.safe_mode.set(change.enabled)
        return {"enabled": app.state.safe_mode.enabled}

    @app.post("/api/v1/strategies")
    def submit_strategy(submission: StrategySubmission, session=Depends(mutable_session)) -> dict[str, object]:
        _check_expensive_throttle(session.user.user_id)
        if not session.user.is_workspace_eligible("user") and session.user.role is not Role.OWNER:
            raise HTTPException(status_code=403, detail="active service entitlement required")
        try:
            app.state.safe_mode.require_mutable()
            version, result = app.state.strategies.submit(
                owner=session.user,
                source=submission.source,
                protective_policy_identity=submission.protective_policy_identity,
                validate_conformance=True,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=423, detail=str(exc)) from exc
        if version is None:
            raise HTTPException(status_code=422, detail={"validation": list(result.reasons)})
        if (security_store is not None and governance_store is not None
                and app.state.strategies._conformance_authority.validate_version(version)):
            version = app.state.strategies.mark_validated(actor=session.user, version_id=version.version_id)
        return {"strategy_id": str(version.strategy_id), "version_id": str(version.version_id), "stage": version.stage.value, "source_sha256": version.source_sha256}

    @app.get("/api/v1/strategies/{version_id}/quality")
    def quality(version_id: str, session=Depends(session_from_header)) -> dict[str, object]:
        try:
            app.state.strategies._owned(session.user, UUID(version_id))
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="cross-user strategy quality access denied") from exc
        except (ValueError, Exception) as exc:
            raise HTTPException(status_code=404, detail="strategy version unavailable") from exc
        result = app.state.quality_authority.score_for(version_id)
        if result is None:
            return {"trust": "UNKNOWN", "eligibility_changed": False}
        return {"score": result.score, "grade": result.grade, "components": result.components, "eligibility_changed": False}

    # ── Slice 9.7: Portfolio / Data / Audit projection endpoints ──

    def orders_portfolio_authority() -> OrdersPortfolioService:
        service = app.state.orders_portfolio_service
        if service is None:
            raise HTTPException(status_code=503, detail="Orders and portfolio authority unavailable")
        return service

    @app.get("/api/v1/user/orders-portfolio")
    def user_orders_portfolio(mode: ExecutionMode = "PAPER", session=Depends(session_from_header),
                              service=Depends(orders_portfolio_authority)) -> dict[str, Any]:
        return service.snapshot(user_id=str(session.user.user_id), mode=mode)

    @app.get("/api/v1/owner/orders-portfolio")
    def owner_orders_portfolio(mode: ExecutionMode = "PAPER", session=Depends(owner_session),
                               service=Depends(orders_portfolio_authority)) -> dict[str, Any]:
        return service.snapshot(user_id=None, mode=mode)

    @app.get("/api/v1/paper/sessions/{session_id}/orders/{order_id}")
    def paper_order_detail(session_id: str, order_id: str, session=Depends(session_from_header),
                           service=Depends(orders_portfolio_authority)) -> dict[str, Any]:
        try:
            # Even an Owner uses their own tenant here; system-wide inspection
            # is explicitly provided by the Owner-only oversight endpoint.
            return service.order(user_id=str(session.user.user_id), session_id=session_id, order_id=order_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="Paper order unavailable") from exc

    @app.get("/api/v1/portfolio", deprecated=True)
    def portfolio(session=Depends(owner_session)) -> dict[str, object]:
        """[DEPRECATED - F-9 Legacy Compatibility Route]
        Canonical Authorities:
          - User: /api/v1/user/orders-portfolio (OrdersPortfolioService)
          - Owner: /api/v1/owner/orders-portfolio (OrdersPortfolioService)
        Classification: LEGACY_COMPATIBILITY
        Thin read-only projection of existing persistence authority.
        Maintains ZERO separate, fabricated, or shadow portfolio state."""
        reader = getattr(app.state, "core_read_authority", None)
        if reader is None or not hasattr(reader, "read"):
            return {"trust": "UNKNOWN", "as_of_utc": None, "positions": {"value": None, "trust": "UNKNOWN", "as_of_utc": None}, "daily_pnl": {"value": None, "trust": "UNKNOWN", "as_of_utc": None}, "capital": {"value": None, "trust": "UNKNOWN", "as_of_utc": None}}
        from .domain import utc_now as _utc
        now = _utc()
        positions = reader.read("positions", now_utc=now) if hasattr(reader, "read") else None
        return {"trust": "UNKNOWN", "as_of_utc": now.isoformat() if now else None, "positions": positions.public_dict() if positions and hasattr(positions, "public_dict") else {"value": None, "trust": "UNKNOWN", "as_of_utc": None}, "daily_pnl": {"value": None, "trust": "UNKNOWN", "as_of_utc": None}, "capital": {"value": None, "trust": "UNKNOWN", "as_of_utc": None}}

    @app.get("/api/v1/audit/events", deprecated=True)
    def audit_events(session=Depends(owner_session)) -> dict[str, object]:
        """[DEPRECATED - F-9 Legacy Compatibility Route]
        Canonical Authority:
          - Owner: /api/v1/integration/audit/events (AuditAdapter / AuditStore)
        Classification: LEGACY_COMPATIBILITY
        Thin read-only projection delegating directly to authoritative audit source.
        Maintains ZERO competing or separate audit state."""
        reader = getattr(app.state, "audit_reader", None)
        if reader is not None and callable(reader):
            try:
                entries = reader()
                return {"entries": list(entries) if entries else [], "trust": "FRESH" if entries else "UNKNOWN"}
            except Exception:
                return {"entries": [], "trust": "UNKNOWN"}
        adapter = getattr(app.state, "audit_adapter", None)
        if adapter is not None and hasattr(adapter, "read_audit_events"):
            try:
                res = adapter.read_audit_events(limit=50, offset=0)
                events = res.get("events", [])
                return {"entries": events, "trust": res.get("trust", "FRESH" if events else "UNKNOWN")}
            except Exception:
                return {"entries": [], "trust": "UNKNOWN"}
        return {"entries": [], "trust": "UNKNOWN"}

    @app.get("/api/v1/strategies")
    def list_strategies(session=Depends(session_from_header)) -> dict[str, object]:
        """F-10: list strategies from the persisted governance/assignment authority (restart-stable)."""
        try:
            strategies = app.state.strategies.list_user_strategies(session.user.user_id, session.user.role)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"strategy registry unavailable: {exc}") from exc
        return {"strategies": strategies, "trust": "FRESH" if strategies else "UNKNOWN"}

    @app.post("/api/v1/strategies/{version_id}/archive")
    def archive_strategy(version_id: str, session=Depends(mutable_session)) -> dict[str, object]:
        """Safe archive / disable. §131.15: do not hard-delete evidence."""
        try:
            app.state.safe_mode.require_mutable()
            version = app.state.strategies.archive(actor=session.user, version_id=UUID(version_id))
        except PermissionError as exc:
            raise HTTPException(status_code=423, detail=str(exc)) from exc
        except (ValueError, Exception) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"version_id": str(version.version_id), "stage": version.stage.value, "archived": version.archived}

    # ── Slice 9.8: Settings governance ──

    @app.post("/api/v1/settings/propose")
    def propose_setting(proposal: SettingsProposalBody, session=Depends(mutable_session)) -> dict[str, object]:
        """§131.10: PROPOSE → VALIDATE → DRY RUN → DIFF → CONFIRM → ATOMIC → VERIFY → AUDIT.
        This endpoint handles PROPOSE + VALIDATE + DRY RUN + DIFF and persists the
        proposal only. No effective setting is mutated here; CONFIRM is separate.
        Risk/safety settings are NOT ordinary convenience settings."""
        try:
            app.state.safe_mode.require_mutable()
        except PermissionError as exc:
            raise HTTPException(status_code=423, detail=str(exc)) from exc
        if session.user.role is not Role.OWNER:
            raise HTTPException(status_code=403, detail="owner role required for settings changes")
        # Validate: only known, non-secret, server-writable keys
        known_keys = {"safe_mode", "stale_threshold_seconds", "retention_policy_days",
                      "auto_archive_inactive_strategies"}
        if proposal.key not in known_keys:
            return {"accepted": False, "diff": None, "reason": "unknown or protected setting key", "dry_run_result": "REJECTED"}
        # Dry-run: compute before/after
        if proposal.key == "safe_mode":
            current: Any = app.state.safe_mode.enabled
        elif app.state.security_store is not None:
            current = app.state.security_store.get_server_setting(proposal.key)
        else:
            current = None
        diff = f"-{proposal.key}: {current}\n+{proposal.key}: {proposal.proposed_value}"
        response: dict[str, object] = {"accepted": True, "diff": diff, "current_value": current,
                                       "proposed_value": proposal.proposed_value,
                                       "dry_run_result": "OK", "requires_confirmation": True,
                                       "proposal_id": None, "persisted": False}
        # F-18: persist the proposal (Owner, expiring, unconsumed) for CONFIRM.
        if app.state.security_store is not None:
            proposal_id = f"setprop-{uuid4().hex[:12]}"
            expires_at = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
            try:
                app.state.security_store.stage_setting_proposal(
                    proposal_id=proposal_id, key=proposal.key, current_value=current,
                    proposed_value=proposal.proposed_value,
                    actor=f"OWNER-{str(session.user.user_id)[:4]}", diff=diff,
                    expires_at_utc=expires_at,
                )
            except SecurityStoreError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            response["proposal_id"] = proposal_id
            response["expires_at_utc"] = expires_at
            response["persisted"] = True
        return response

    # ── Slice 9.9: OWNER/USER isolation foundation ──

    @app.get("/api/v1/users/current")
    def current_user(session=Depends(session_from_header)) -> dict[str, object]:
        """Immutable UUID-based user identity and authoritative 3-axis access & service entitlement status."""
        user = session.user
        eff_service = user.effective_service_status()
        user_eligible = user.is_workspace_eligible("user")
        owner_eligible = user.is_workspace_eligible("owner")

        return {
            "user_id": str(user.user_id),
            "sx_id": user.sx_id or f"SX-U-{str(user.user_id)[:4].upper()}-{str(user.user_id)[-4].upper()}",
            "role": user.role.value,
            "lifecycle": user.lifecycle.value,
            "account_status": user.account_status.value,
            "activation_status": user.activation_status.value,
            "service_status": eff_service.value,
            "service_started_at": user.service_started_at.isoformat() if user.service_started_at else None,
            "service_expires_at": user.service_expires_at.isoformat() if user.service_expires_at else None,
            "service_term_type": user.service_term_type,
            "custom_term_value": user.custom_term_value,
            "display_name": user.display_name,
            "namespace": user.namespace,
            "workspace_eligibility": {
                "user": user_eligible,
                "owner": owner_eligible,
            },
            "effective_access": owner_eligible if user.role is Role.OWNER else user_eligible,
        }

    @app.get("/api/v1/users/retention")
    def retention_policy(session=Depends(session_from_header)) -> dict[str, object]:
        """§131.20: retention duration UNCONFIRMED. Automatic deletion DISABLED."""
        if session.user.role is not Role.OWNER:
            raise HTTPException(status_code=403, detail="owner role required")
        return {"retention_duration": "UNCONFIRMED", "automatic_deletion": "DISABLED", "pii_anonymization": "INACTIVE", "lifecycle_states": ["ACTIVE", "SUSPENDED", "CLOSED", "ARCHIVED"]}

    def owner_mutable_session(session=Depends(mutable_session)) -> Any:
        if session.user.role is not Role.OWNER or session.user.account_status != AccountAccessStatus.ACTIVE:
            raise HTTPException(status_code=403, detail="owner role and active account status required")
        return session

    def _record_security_audit(event_type: str, actor_id: UUID, details: dict[str, Any], operation_id: str | None = None) -> str | None:
        audit = getattr(app.state, "core_security_audit", None)
        if audit is not None:
            try:
                try:
                    ref = audit.record(action=event_type, actor_id=actor_id, payload=details, operation_id=operation_id)
                except TypeError:
                    try:
                        ref = audit.record(action=event_type, actor_id=actor_id, payload=details)
                    except TypeError:
                        ref = audit.record(event_type=event_type, user_id=actor_id, details=details)
                if app.state.security_store is not None and hasattr(app.state.security_store, "save_audit_reference"):
                    try:
                        app.state.security_store.save_audit_reference(event_id=str(ref), user_id=actor_id, action=event_type)
                    except Exception:
                        pass
                return str(ref)
            except Exception as exc:
                logger.error("Mandatory security audit recording failed: %s", exc)
                raise HTTPException(status_code=503, detail="Mandatory security audit recording failed: AUDIT_RECORDING_FAILED") from exc
        return None

    # ── Owner Access & Service Entitlement Mutation Authority Endpoints ──

    @app.post("/api/v1/owner/access/users")
    def create_user_access(body: CreateUserAccessRequest, session=Depends(owner_mutable_session)) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        op_id = getattr(body, "idempotency_key", None) or (f"user-create-{body.email.strip().lower()}" if body.email else None)
        try:
            record, plain_code = app.state.security_store.create_user_access(
                display_name=body.display_name,
                email=body.email,
                phone=body.phone,
                role=body.role,
                plan=body.plan,
                service_term_type=body.service_term_type,
                custom_term_value=body.custom_term_value,
                custom_term_unit=body.custom_term_unit,
                is_draft=body.is_draft,
                actor=actor_tag,
                notes=body.notes,
                operation_id=op_id,
                allow_idempotent_onboarding=True,
            )
            audit_ref = _record_security_audit(
                event_type="USER_ACCESS_CREATED",
                actor_id=session.user.user_id,
                details={
                    "target_user_id": record["user_id"],
                    "sx_id": record["sx_id"],
                    "is_draft": body.is_draft,
                    "service_term_type": body.service_term_type,
                },
                operation_id=op_id,
            )
            if hasattr(app.state.security_store, "update_outbox_state") and op_id:
                try:
                    app.state.security_store.update_outbox_state(
                        operation_id=op_id,
                        stage_state="VERIFIED_APPLIED",
                        applied_event_id=audit_ref,
                    )
                except Exception:
                    pass
            return {"success": True, "record": record, "activation_code": plain_code}
        except SecurityStoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/owner/access/users/{identifier}/reissue-activation")
    def reissue_activation(identifier: str, body: ActionNotesRequest = ActionNotesRequest(), session=Depends(owner_mutable_session)) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            res, plain_code = app.state.security_store.reissue_activation_code(
                identifier,
                actor=actor_tag,
                notes=body.notes or "Reissued 24h activation code",
            )
            _record_security_audit(
                event_type="ACTIVATION_CODE_REISSUED",
                actor_id=session.user.user_id,
                details={"target": identifier, "sx_id": res.get("sx_id")},
            )
            return {"success": True, "reissuance": res, "activation_code": plain_code}
        except SecurityStoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/owner/access/users/{identifier}/revoke-activation")
    def revoke_activation(identifier: str, body: ActionNotesRequest = ActionNotesRequest(), session=Depends(owner_mutable_session)) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            app.state.security_store.revoke_activation_code(
                identifier,
                actor=actor_tag,
                notes=body.notes or "Activation invitation revoked",
            )
            _record_security_audit(
                event_type="ACTIVATION_CODE_REVOKED",
                actor_id=session.user.user_id,
                details={"target": identifier},
            )
            return {"success": True}
        except SecurityStoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/owner/access/users/{identifier}/suspend")
    def suspend_account(identifier: str, body: ActionNotesRequest = ActionNotesRequest(), session=Depends(owner_mutable_session)) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            app.state.security_store.suspend_user_account(
                identifier,
                actor=actor_tag,
                notes=body.notes or "Account suspended",
            )
            _record_security_audit(
                event_type="ACCOUNT_SUSPENDED",
                actor_id=session.user.user_id,
                details={"target": identifier},
            )
            return {"success": True}
        except SecurityStoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/owner/access/users/{identifier}/restore")
    def restore_account(identifier: str, body: ActionNotesRequest = ActionNotesRequest(), session=Depends(owner_mutable_session)) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            res = app.state.security_store.restore_user_account(
                identifier,
                actor=actor_tag,
                notes=body.notes or "Account restored",
            )
            _record_security_audit(
                event_type="ACCOUNT_RESTORED",
                actor_id=session.user.user_id,
                details={"target": identifier, "account_status": res.get("account_status")},
            )
            return {"success": True, **res}
        except SecurityStoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/owner/access/users/{identifier}/revoke")
    def revoke_account(identifier: str, body: ActionNotesRequest = ActionNotesRequest(), session=Depends(owner_mutable_session)) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            app.state.security_store.revoke_user_account(
                identifier,
                actor=actor_tag,
                notes=body.notes or "Account permanently revoked",
            )
            _record_security_audit(
                event_type="ACCOUNT_REVOKED",
                actor_id=session.user.user_id,
                details={"target": identifier},
            )
            return {"success": True}
        except SecurityStoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/owner/access/users/{identifier}/extend-service")
    def extend_service(identifier: str, body: ServiceTermModificationRequest, session=Depends(owner_mutable_session)) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            res = app.state.security_store.extend_service_entitlement(
                identifier,
                term_type=body.service_term_type,
                custom_value=body.custom_term_value,
                custom_unit=body.custom_term_unit,
                actor=actor_tag,
                notes=body.notes or "Service entitlement extended",
            )
            _record_security_audit(
                event_type="SERVICE_ENTITLEMENT_EXTENDED",
                actor_id=session.user.user_id,
                details={"target": identifier, "service_term_type": body.service_term_type, "new_expiry": res.get("service_expires_at")},
            )
            return {"success": True, **res}
        except SecurityStoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/owner/access/users/{identifier}/renew-service")
    def renew_service(identifier: str, body: ServiceTermModificationRequest, session=Depends(owner_mutable_session)) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            res = app.state.security_store.renew_service_entitlement(
                identifier,
                term_type=body.service_term_type,
                custom_value=body.custom_term_value,
                custom_unit=body.custom_term_unit,
                actor=actor_tag,
                notes=body.notes or "Service entitlement renewed",
            )
            _record_security_audit(
                event_type="SERVICE_ENTITLEMENT_RENEWED",
                actor_id=session.user.user_id,
                details={"target": identifier, "service_term_type": body.service_term_type, "new_expiry": res.get("service_expires_at")},
            )
            return {"success": True, **res}
        except SecurityStoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/owner/access/users/{identifier}/convert-lifetime")
    def convert_lifetime(identifier: str, body: ActionNotesRequest = ActionNotesRequest(), session=Depends(owner_mutable_session)) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            res = app.state.security_store.convert_to_lifetime_entitlement(
                identifier,
                actor=actor_tag,
                notes=body.notes or "Converted to Lifetime",
            )
            _record_security_audit(
                event_type="SERVICE_ENTITLEMENT_LIFETIME_CONVERTED",
                actor_id=session.user.user_id,
                details={"target": identifier},
            )
            return {"success": True, **res}
        except SecurityStoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.delete("/api/v1/owner/access/users/{identifier}/draft")
    def delete_draft(identifier: str, session=Depends(owner_mutable_session)) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            app.state.security_store.delete_draft_user(identifier, actor=actor_tag)
            _record_security_audit(
                event_type="DRAFT_USER_DELETED",
                actor_id=session.user.user_id,
                details={"target": identifier},
            )
            return {"success": True}
        except SecurityStoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    # ── Slice 3: Owner Security, Session & Device Authority Endpoints ──

    @app.get("/api/v1/owner/security/sessions")
    def list_owner_sessions(session=Depends(owner_session)) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        cur_hash = SQLiteSecurityStore.token_hash(session.token) if session.token else None
        sessions_list = app.state.security_store.list_all_sessions(current_token_hash=cur_hash)
        return {"sessions": sessions_list, "trust": "FRESH"}

    @app.post("/api/v1/owner/security/sessions/{session_ref}/revoke")
    def revoke_owner_session(session_ref: str, session=Depends(owner_mutable_session)) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            revoked = app.state.security_store.revoke_session_by_ref(session_ref)
            if not revoked:
                raise HTTPException(status_code=404, detail="Session not found or already revoked")
            exact_session_id = revoked.get("exact_session_id") if isinstance(revoked, dict) else session_ref
            audit_details = {
                "session_ref": session_ref,
                "exact_session_id": exact_session_id,
                "actor": actor_tag,
            }
            if isinstance(revoked, dict) and "user_id" in revoked:
                audit_details["user_id"] = revoked["user_id"]
            _record_security_audit(
                event_type="OWNER_SESSION_REVOKE",
                actor_id=session.user.user_id,
                details=audit_details,
            )
            return {
                "success": True,
                "session_ref": session_ref,
                "exact_session_id": exact_session_id,
                "revoked": True,
            }
        except AmbiguousSessionRefError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/owner/security/users/{identifier}/sessions/revoke-all")
    def revoke_all_user_sessions(identifier: str, session=Depends(owner_mutable_session)) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        user = app.state.security_store.find_user_by_identifier(identifier)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        uid = user["user_id"]
        try:
            count = app.state.security_store.revoke_user_sessions(uid)
            _record_security_audit(
                event_type="OWNER_REVOKE_ALL_USER_SESSIONS",
                actor_id=session.user.user_id,
                details={"target_user_id": uid, "target_sx_id": user["sx_id"], "revoked_count": count, "actor": actor_tag},
            )
            return {"success": True, "user_id": uid, "revoked_count": count}
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/v1/security/devices")
    def list_current_devices(session=Depends(session_from_header)) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        return {"devices": app.state.security_store.list_all_devices(user_id=session.user.user_id), "trust": "FRESH"}

    @app.get("/api/v1/owner/security/devices")
    def list_owner_devices(session=Depends(owner_session)) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        devices_list = app.state.security_store.list_all_devices()
        return {"devices": devices_list, "trust": "FRESH"}

    @app.post("/api/v1/owner/security/devices/{credential_id}/revoke")
    def revoke_owner_device(credential_id: str, session=Depends(owner_mutable_session)) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            revoked = app.state.security_store.revoke_device(credential_id)
            if not revoked:
                raise HTTPException(status_code=404, detail="Device not found or already revoked")
            _record_security_audit(
                event_type="OWNER_DEVICE_REVOKE",
                actor_id=session.user.user_id,
                details={"credential_id": credential_id, "actor": actor_tag},
            )
            return {"success": True, "credential_id": credential_id, "revoked": True}
        except HTTPException:
            raise
        except SecurityStoreError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/owner/security/users/{identifier}/devices/revoke-all")
    def revoke_all_user_devices(identifier: str, session=Depends(owner_mutable_session)) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        user = app.state.security_store.find_user_by_identifier(identifier)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        uid = user["user_id"]
        try:
            count = app.state.security_store.revoke_all_user_devices(uid)
            _record_security_audit(
                event_type="OWNER_REVOKE_ALL_USER_DEVICES",
                actor_id=session.user.user_id,
                details={"target_user_id": uid, "target_sx_id": user["sx_id"], "revoked_count": count, "actor": actor_tag},
            )
            return {"success": True, "user_id": uid, "revoked_count": count}
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    # ── Slice 4: Owner Strategy Governance Endpoints ──

    @app.get("/api/v1/owner/strategies")
    def list_owner_strategies(session=Depends(owner_session)) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        return app.state.strategies_adapter.read_strategies()

    @app.post("/api/v1/owner/strategies/{strategy_id}/allowance")
    def update_strategy_allowance(
        strategy_id: str,
        body: UpdateStrategyAllowanceRequest,
        session=Depends(owner_mutable_session),
    ) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            strat, eff, msg = app.state.security_store.update_strategy_allowance(
                strategy_id=strategy_id,
                sandbox=body.sandbox,
                allowance=body.allowance,
                reason=body.reason,
                actor=actor_tag,
            )
            _record_security_audit(
                event_type="STRATEGY_ALLOWANCE_UPDATED",
                actor_id=session.user.user_id,
                details={
                    "strategy_id": strategy_id,
                    "sandbox": body.sandbox,
                    "allowance": body.allowance,
                    "effective": eff,
                    "actor": actor_tag,
                },
            )
            return {"success": True, "strategy": strat, "effective": eff, "message": msg}
        except HTTPException:
            raise
        except SecurityStoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/owner/strategies/{strategy_id}/visibility")
    def update_strategy_visibility(
        strategy_id: str,
        body: StrategyVisibilityRequest,
        session=Depends(owner_mutable_session),
    ) -> dict[str, object]:
        """Explicit privileged publish (GLOBAL) / unpublish (OWNER_PRIVATE).

        Only Owner-authored or system strategies may enter the global catalog;
        user-private strategies are rejected. Unpublish preserves all
        historical runs/evidence; new unauthorized starts fail closed."""
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            strat = app.state.security_store.set_strategy_visibility(
                strategy_id=strategy_id,
                visibility=body.visibility,
                actor_user_id=str(session.user.user_id),
                actor=actor_tag,
            )
            _record_security_audit(
                event_type="STRATEGY_VISIBILITY_UPDATED",
                actor_id=session.user.user_id,
                details={
                    "strategy_id": strategy_id,
                    "visibility": strat.get("visibility"),
                    "actor": actor_tag,
                },
            )
            return {"success": True, "strategy": strat}
        except SecurityStoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/owner/strategies/{strategy_id}/suspend")
    def suspend_strategy(
        strategy_id: str,
        body: SuspendStrategyRequest = SuspendStrategyRequest(),
        session=Depends(owner_mutable_session),
    ) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            strat = app.state.security_store.suspend_strategy(
                strategy_id=strategy_id,
                reason=body.reason or "Owner administrative hold",
                actor=actor_tag,
            )
            _record_security_audit(
                event_type="STRATEGY_SUSPENDED",
                actor_id=session.user.user_id,
                details={"strategy_id": strategy_id, "actor": actor_tag, "reason": body.reason},
            )
            return {"success": True, "strategy": strat}
        except HTTPException:
            raise
        except SecurityStoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/owner/strategies/{strategy_id}/restore")
    def restore_strategy(
        strategy_id: str,
        body: RestoreStrategyRequest = RestoreStrategyRequest(),
        session=Depends(owner_mutable_session),
    ) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            strat = app.state.security_store.restore_strategy(
                strategy_id=strategy_id,
                actor=actor_tag,
            )
            _record_security_audit(
                event_type="STRATEGY_RESTORED",
                actor_id=session.user.user_id,
                details={"strategy_id": strategy_id, "actor": actor_tag},
            )
            return {"success": True, "strategy": strat}
        except HTTPException:
            raise
        except SecurityStoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/v1/owner/strategies/{strategy_id}/execution-hold")
    def get_strategy_execution_hold(
        strategy_id: str,
        sandbox: str = "live",
        session=Depends(owner_session),
    ) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        held, reason = app.state.security_store.is_strategy_execution_held(strategy_id, sandbox)
        return {"strategy_id": strategy_id, "sandbox": sandbox, "held": held, "reason": reason}

    @app.post("/api/v1/owner/strategies/{strategy_id}/assign")
    def assign_strategy_to_user(
        strategy_id: str,
        body: StrategyAssignmentRequest,
        session=Depends(owner_mutable_session),
    ) -> dict[str, object]:
        """F-10: Owner-only persisted User strategy assignment (restart-stable)."""
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            assignment = app.state.security_store.assign_strategy_to_user(
                user_id=body.user_id,
                strategy_id=strategy_id,
                actor=actor_tag,
            )
            _record_security_audit(
                event_type="STRATEGY_ASSIGNED",
                actor_id=session.user.user_id,
                details={"strategy_id": strategy_id, "user_id": body.user_id, "actor": actor_tag},
            )
            return {"success": True, "assignment": assignment}
        except SecurityStoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/owner/strategies/{strategy_id}/revoke")
    @app.post("/api/v1/owner/strategies/{strategy_id}/revoke-assignment")
    def revoke_strategy_from_user(
        strategy_id: str,
        body: StrategyAssignmentRequest,
        session=Depends(owner_mutable_session),
    ) -> dict[str, object]:
        """F-10: Owner-only persisted assignment revocation (restart-stable)."""
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            revoked = app.state.security_store.revoke_strategy_assignment(
                user_id=body.user_id,
                strategy_id=strategy_id,
                actor=actor_tag,
            )
            if not revoked:
                raise HTTPException(status_code=404, detail="assignment not found")
            _record_security_audit(
                event_type="STRATEGY_REVOKED",
                actor_id=session.user.user_id,
                details={"strategy_id": strategy_id, "user_id": body.user_id, "actor": actor_tag},
            )
            return {"success": True, "strategy_id": strategy_id, "user_id": body.user_id}
        except HTTPException:
            raise
        except SecurityStoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/v1/owner/strategies/{strategy_id}/assignments")
    def list_strategy_assignments(
        strategy_id: str,
        session=Depends(owner_session),
    ) -> dict[str, object]:
        """F-10: list user assignments for a strategy."""
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        assignments = app.state.security_store.list_user_strategy_assignments(strategy_id=strategy_id)
        return {"strategy_id": strategy_id, "assignments": assignments}

    @app.post("/api/v1/strategies/{strategy_id}/request-promotion")
    def request_strategy_promotion(
        strategy_id: str,
        body: RequestPromotionBody,
        session=Depends(mutable_session),
    ) -> dict[str, object]:
        """F-19: authenticated authorized User requests promotion (persisted PENDING, no stage change)."""
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        access = app.state.security_store.check_user_strategy_access(
            str(session.user.user_id), strategy_id)
        if not access.get("permitted"):
            raise HTTPException(status_code=403, detail=f"strategy not available: {access.get('reason')}")
        try:
            result = app.state.security_store.request_strategy_promotion(
                strategy_id=strategy_id,
                user_id=str(session.user.user_id),
                target_stage=body.target_stage,
                run_id=body.run_id,
                notes=body.notes or "",
                actor=f"{session.user.role.value}-{str(session.user.user_id)[:4]}",
            )
        except SecurityStoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _record_security_audit(
            event_type="STRATEGY_PROMOTION_REQUESTED",
            actor_id=session.user.user_id,
            details={"strategy_id": strategy_id, "target_stage": body.target_stage,
                     "run_id": body.run_id},
        )
        return result

    @app.get("/api/v1/owner/promotions/pending")
    def list_pending_promotions(session=Depends(owner_session)) -> dict[str, object]:
        """F-19: Owner reviews persisted PENDING_OWNER_REVIEW promotion requests."""
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        return {"requests": app.state.security_store.list_pending_strategy_promotions()}

    @app.post("/api/v1/owner/strategies/{strategy_id}/promote")
    def promote_strategy(
        strategy_id: str,
        body: PromoteStrategyRequest,
        session=Depends(owner_mutable_session),
    ) -> dict[str, object]:
        """F-19: Owner-only authoritative stage transition (validated, persisted, re-read)."""
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        strat = app.state.security_store.get_owner_strategy(strategy_id)
        if strat is None:
            raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found")
        if body.version is not None and str(body.version) != str(strat.get("version")):
            raise HTTPException(status_code=422, detail="stale strategy version: re-read authoritative record")
        if body.source_sha256 is not None:
            gov = getattr(app.state, "governance_store", None)
            if gov is None:
                raise HTTPException(status_code=422, detail="artifact hash cannot be verified without governance store")
            try:
                digests = gov.get_strategy_source_digests(strat.get("strategyId") or strategy_id)
            except Exception as exc:
                logger.exception("Artifact verification error")
                raise HTTPException(status_code=422, detail="artifact verification unavailable") from exc
            if str(body.source_sha256) not in digests:
                raise HTTPException(status_code=422, detail="artifact hash mismatch: stale artifact")
        if body.run_id is not None:
            run = app.state.security_store.get_backtest_run(body.run_id)
            if run is None or run.get("status") != "COMPLETED":
                raise HTTPException(status_code=422, detail="promotion evidence run is not COMPLETED")
            if str(run.get("strategy_id")) != str(strat.get("strategyId") or strategy_id):
                raise HTTPException(status_code=422, detail="evidence run does not belong to this strategy")
        try:
            promoted = app.state.security_store.promote_strategy(
                strategy_id=strategy_id,
                target_stage=body.target_stage,
                actor=actor_tag,
                notes=body.notes or "",
            )
        except SecurityStoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _record_security_audit(
            event_type="STRATEGY_PROMOTED",
            actor_id=session.user.user_id,
            details={"strategy_id": strategy_id, "target_stage": body.target_stage,
                     "version": promoted.get("version"), "actor": actor_tag},
        )
        return {"success": True, "strategy": promoted}

    @app.post("/api/v1/user/strategies/{strategy_id}/promote")
    @app.post("/api/v1/strategies/{strategy_id}/promote")
    def user_promote_strategy(
        strategy_id: str,
        body: PromoteStrategyRequest,
        session=Depends(mutable_session),
    ) -> dict[str, object]:
        """User self-service strategy stage transition (PAPER_ELIGIBLE or LIVE_ELIGIBLE)."""
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")

        uid = str(session.user.user_id)
        access = app.state.security_store.check_user_strategy_access(uid, strategy_id)
        if not access.get("permitted"):
            raise HTTPException(status_code=403, detail=f"strategy not available: {access.get('reason')}")

        strat = app.state.security_store.get_owner_strategy(strategy_id)
        if strat is None:
            raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found")
        admin_status = strat.get("adminStatus") or strat.get("admin_status") or "ACTIVE"
        if admin_status != "ACTIVE":
            raise HTTPException(status_code=422, detail=f"Cannot promote strategy '{strategy_id}': admin status is {admin_status}")

        target_stage = (body.target_stage or "").upper().strip()
        if target_stage == "PAPER_ELIGIBLE":
            elig = app.state.security_store.check_self_service_paper_eligibility(strategy_id, user_id=uid)
            if not elig.get("permitted"):
                raise HTTPException(status_code=422, detail=str(elig.get("reason") or "Strategy is not eligible for paper"))
        elif target_stage == "LIVE_ELIGIBLE":
            elig = app.state.security_store.check_self_service_live_eligibility(strategy_id, user_id=uid)
            if not elig.get("permitted"):
                raise HTTPException(status_code=422, detail=str(elig.get("reason") or "Strategy is not eligible for live"))
        else:
            raise HTTPException(status_code=422, detail=f"Invalid target stage '{target_stage}'. Valid: ['PAPER_ELIGIBLE', 'LIVE_ELIGIBLE']")

        actor_tag = f"USER-{uid[:4]}"
        try:
            promoted = app.state.security_store.promote_strategy(
                strategy_id=strategy_id,
                target_stage=target_stage,
                actor=actor_tag,
                notes=body.notes or f"User self-service promotion to {target_stage}",
            )
        except SecurityStoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        _record_security_audit(
            event_type="STRATEGY_PROMOTED",
            actor_id=session.user.user_id,
            details={"strategy_id": strategy_id, "target_stage": target_stage,
                     "version": promoted.get("version"), "actor": actor_tag},
        )
        return {"success": True, "strategy": promoted}

    @app.post("/api/v1/settings/confirm")
    def confirm_setting(body: SettingsConfirmBody, session=Depends(owner_mutable_session)) -> dict[str, object]:
        """F-18: CONFIRM → ATOMIC APPLY → VERIFY. Owner-only; success only after re-read VERIFIED."""
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="settings authority unavailable")
        try:
            app.state.safe_mode.require_mutable()
        except PermissionError as exc:
            raise HTTPException(status_code=423, detail=str(exc)) from exc
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            key, verified, old_value = app.state.security_store.apply_setting_proposal(
                proposal_id=body.proposal_id, actor=actor_tag)
        except SecurityStoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if key == "safe_mode":
            app.state.safe_mode.set(bool(verified))
        _record_security_audit(
            event_type="SERVER_SETTING_APPLIED",
            actor_id=session.user.user_id,
            details={"key": key, "old_value": old_value, "effective_value": verified,
                     "actor": actor_tag},
        )
        return {"success": True, "key": key, "old_value": old_value,
                "effective_value": verified, "verification": "VERIFIED"}

    @app.get("/api/v1/settings")
    def list_settings(session=Depends(owner_session)) -> dict[str, object]:
        """F-18: re-read effective server-authoritative settings (local UI prefs excluded)."""
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="settings authority unavailable")
        return {"settings": app.state.security_store.list_server_settings()}

    # ── Slice 4: Owner Broker / Connection Authority Endpoints ──

    @app.get("/api/v1/owner/connections")
    def list_owner_connections(session=Depends(owner_session)) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        return app.state.connections_adapter.read_connections()

    @app.post("/api/v1/owner/connections/{connection_id}/allowance")
    def update_connection_allowance(
        connection_id: str,
        body: UpdateConnectionAllowanceRequest,
        session=Depends(owner_mutable_session),
    ) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            conn, msg = app.state.security_store.update_connection_allowance(
                connection_id=connection_id,
                allowance=body.allowance,
                reason=body.reason,
                actor=actor_tag,
            )
            _record_security_audit(
                event_type="CONNECTION_ALLOWANCE_UPDATED",
                actor_id=session.user.user_id,
                details={
                    "connection_id": connection_id,
                    "allowance": body.allowance,
                    "actor": actor_tag,
                },
            )
            return {"success": True, "connection": conn, "message": msg}
        except HTTPException:
            raise
        except SecurityStoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/owner/connections/{connection_id}/capabilities/{capability}/allowance")
    def update_capability_allowance(
        connection_id: str,
        capability: str,
        body: UpdateCapabilityAllowanceRequest,
        session=Depends(owner_mutable_session),
    ) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            conn, eff, msg = app.state.security_store.update_capability_allowance(
                connection_id=connection_id,
                capability=capability,
                allowance=body.allowance,
                reason=body.reason,
                actor=actor_tag,
            )
            _record_security_audit(
                event_type="CAPABILITY_ALLOWANCE_UPDATED",
                actor_id=session.user.user_id,
                details={
                    "connection_id": connection_id,
                    "capability": capability,
                    "allowance": body.allowance,
                    "effective": eff,
                    "actor": actor_tag,
                },
            )
            return {"success": True, "connection": conn, "effective": eff, "message": msg}
        except HTTPException:
            raise
        except SecurityStoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    # ── Slice 4: Owner Dataset Authority Endpoints ──

    @app.get("/api/v1/owner/datasets")
    def list_owner_datasets(session=Depends(owner_session)) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        return app.state.datasets_adapter.read_datasets()

    @app.post("/api/v1/owner/datasets/{dataset_id}/approval")
    def update_dataset_approval(
        dataset_id: str,
        body: UpdateDatasetApprovalRequest,
        session=Depends(owner_mutable_session),
    ) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            ds, eff, msg = app.state.security_store.update_dataset_approval(
                dataset_id=dataset_id,
                approval=body.approval,
                reason=body.reason,
                actor=actor_tag,
            )
            _record_security_audit(
                event_type="DATASET_APPROVAL_UPDATED",
                actor_id=session.user.user_id,
                details={
                    "dataset_id": dataset_id,
                    "approval": body.approval,
                    "effective": eff,
                    "actor": actor_tag,
                },
            )
            return {"success": True, "dataset": ds, "effective": eff, "message": msg}
        except HTTPException:
            raise
        except SecurityStoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/owner/backtest/gate")
    def check_backtest_gate(
        body: BacktestGateRequest,
        session=Depends(owner_session),
    ) -> dict[str, object]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        return app.state.security_store.check_backtest_gate(body.strategy_id, body.dataset_id)

    # ── Owner Historical Data Acquisition, Sync & Governance Endpoints ──

    @app.post("/api/v1/owner/datasets/{dataset_id}/retire")
    def retire_owner_dataset(
        dataset_id: str,
        body: RetireDatasetRequest,
        session=Depends(owner_mutable_session),
    ) -> dict[str, object]:
        service = historical_data_service_or_503()
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            res = service.retire_dataset(dataset_id, reason=body.reason, actor=actor_tag)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _record_security_audit(
            event_type="DATASET_RETIRED",
            actor_id=session.user.user_id,
            details={"dataset_id": dataset_id, "reason": body.reason, "actor": actor_tag},
        )
        return {"success": True, "dataset": res}

    @app.post("/api/v1/owner/datasets/{dataset_id}/replace")
    def replace_owner_dataset(
        dataset_id: str,
        body: ReplaceDatasetRequest,
        session=Depends(owner_mutable_session),
    ) -> dict[str, object]:
        service = historical_data_service_or_503()
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            res = service.replace_dataset(
                dataset_id,
                replacement_dataset_id=body.replacement_dataset_id,
                reason=body.reason,
                actor=actor_tag,
            )
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _record_security_audit(
            event_type="DATASET_REPLACED",
            actor_id=session.user.user_id,
            details={"dataset_id": dataset_id, "replacement_dataset_id": body.replacement_dataset_id, "reason": body.reason, "actor": actor_tag},
        )
        return {"success": True, "dataset": res}

    @app.get("/api/v1/owner/historical/providers")
    def list_historical_providers(session=Depends(owner_session)) -> dict[str, object]:
        service = historical_data_service_or_503()
        return {"providers": service.list_providers()}

    @app.post("/api/v1/owner/historical/providers")
    def configure_historical_provider(
        body: HistoricalProviderConfigRequest,
        session=Depends(owner_mutable_session),
    ) -> dict[str, object]:
        service = historical_data_service_or_503()
        try:
            prov = service.register_provider(
                provider_id=body.provider_id,
                name=body.name,
                base_url=body.base_url,
                api_key=body.api_key,
                supported_instruments=body.supported_instruments,
                supported_timeframes=body.supported_timeframes,
                is_enabled=body.is_enabled,
                provider_type=body.provider_type,
                is_test=body.is_test,
            )
        except DataProviderNotConfiguredError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        _record_security_audit(
            event_type="HISTORICAL_PROVIDER_CONFIGURED",
            actor_id=session.user.user_id,
            details={"provider_id": body.provider_id, "name": body.name, "is_enabled": body.is_enabled},
        )
        return {"success": True, "provider": prov.get_status() if hasattr(prov, "get_status") else {"provider_id": body.provider_id, "provider_name": body.name}}

    @app.post("/api/v1/owner/historical/providers/{provider_id}/toggle")
    def toggle_historical_provider(
        provider_id: str,
        body: ToggleProviderRequest,
        session=Depends(owner_mutable_session),
    ) -> dict[str, object]:
        service = historical_data_service_or_503()
        res = service.toggle_provider(provider_id, body.enabled)
        _record_security_audit(
            event_type="HISTORICAL_PROVIDER_TOGGLED",
            actor_id=session.user.user_id,
            details={"provider_id": provider_id, "enabled": body.enabled},
        )
        return {"success": True, "provider": res}

    @app.post("/api/v1/owner/historical/sync/manual")
    def manual_historical_sync(
        body: HistoricalSyncRequest,
        session=Depends(owner_mutable_session),
    ) -> dict[str, object]:
        _check_expensive_throttle(session.user.user_id)
        from datetime import date as _date
        service = historical_data_service_or_503()
        try:
            st = _date.fromisoformat(body.start_date)
            et = _date.fromisoformat(body.end_date)
        except Exception:
            raise HTTPException(status_code=422, detail="invalid start_date or end_date, expected YYYY-MM-DD")
        if st > et:
            raise HTTPException(status_code=422, detail=f"invalid date range: start_date ({st}) > end_date ({et})")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            job = service.sync_dataset(
                instrument=body.instrument,
                timeframe=body.timeframe,
                start_date=st,
                end_date=et,
                provider_name=body.provider_id,
                force_refresh=body.force_refresh,
                actor=actor_tag,
            )
        except Exception as exc:
            msg = str(exc)
            if "DATA_PROVIDER_NOT_CONFIGURED" in msg:
                raise HTTPException(status_code=503, detail="DATA_PROVIDER_NOT_CONFIGURED")
            elif "DATA_UNAVAILABLE" in msg or "NO_DATA" in msg:
                raise HTTPException(status_code=404, detail="DATA_UNAVAILABLE")
            logger.error("Historical dataset sync failed: %s", exc)
            raise HTTPException(status_code=422, detail="HISTORICAL_SYNC_FAILED") from exc

        _record_security_audit(
            event_type="HISTORICAL_DATA_SYNCED",
            actor_id=session.user.user_id,
            details={
                "job_id": job.job_id,
                "instrument": body.instrument,
                "timeframe": body.timeframe,
                "status": job.status,
                "rows_fetched": job.rows_fetched,
            },
        )
        inv = service.check_inventory(body.instrument, body.timeframe)
        return {
            "success": job.status == "COMPLETED",
            "job": job.__dict__,
            "dataset": inv.__dict__ if inv else None,
        }

    @app.post("/api/v1/owner/historical/sync/schedule")
    def configure_sync_schedule(
        body: ScheduledSyncConfigRequest,
        session=Depends(owner_mutable_session),
    ) -> dict[str, object]:
        service = historical_data_service_or_503()
        cfg = service.update_schedule(
            instrument=body.instrument,
            timeframe=body.timeframe,
            frequency=body.frequency,
            lookback_days=body.lookback_days,
            provider_id=body.provider_id,
            is_enabled=body.is_enabled,
        )
        _record_security_audit(
            event_type="HISTORICAL_SYNC_SCHEDULE_UPDATED",
            actor_id=session.user.user_id,
            details={
                "instrument": body.instrument,
                "timeframe": body.timeframe,
                "frequency": body.frequency,
                "enabled": body.is_enabled,
            },
        )
        return {"success": True, "schedule": cfg.__dict__}

    @app.get("/api/v1/owner/historical/sync/schedule")
    def get_sync_schedule(
        instrument: str | None = None,
        timeframe: str | None = None,
        session=Depends(owner_session),
    ) -> dict[str, object]:
        service = historical_data_service_or_503()
        cfg = service.get_schedule(instrument=instrument, timeframe=timeframe)
        return {"schedule": cfg.__dict__ if cfg else None}

    @app.get("/api/v1/owner/historical/sync/jobs")
    def list_sync_jobs(
        instrument: str | None = None,
        limit: int = Query(default=50, ge=1, le=500),
        session=Depends(owner_session),
    ) -> dict[str, object]:
        service = historical_data_service_or_503()
        jobs = service.list_jobs(instrument=instrument, limit=limit)
        return {"jobs": [j.__dict__ for j in jobs]}

    @app.get("/api/v1/owner/historical/sync/jobs/{job_id}")
    def get_sync_job(
        job_id: str,
        session=Depends(owner_session),
    ) -> dict[str, object]:
        service = historical_data_service_or_503()
        job = service.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
        return {"job": job.__dict__}

    @app.post("/api/v1/owner/historical/gaps/repair")
    def repair_historical_gaps(
        body: RepairGapsRequest,
        session=Depends(owner_mutable_session),
    ) -> dict[str, object]:
        service = historical_data_service_or_503()
        inst = body.instrument
        tf = body.timeframe
        if body.dataset_id and (not inst or not tf):
            parts = body.dataset_id.split("-")
            if len(parts) >= 2:
                inst = inst or parts[0]
                tf = tf or parts[1]
        if not inst or not tf:
            raise HTTPException(status_code=422, detail="instrument and timeframe or valid dataset_id required")
        try:
            report = service.repair_gaps(
                instrument=inst,
                timeframe=tf,
                provider_name=body.provider_id,
            )
        except Exception as exc:
            msg = str(exc)
            if "DATA_PROVIDER_NOT_CONFIGURED" in msg:
                raise HTTPException(status_code=503, detail="DATA_PROVIDER_NOT_CONFIGURED")
            logger.error("Historical gap repair failed: %s", exc)
            raise HTTPException(status_code=422, detail="GAP_REPAIR_FAILED") from exc

        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        _record_security_audit(
            event_type="HISTORICAL_GAPS_REPAIRED",
            actor_id=session.user.user_id,
            details={"instrument": inst, "timeframe": tf, "repaired_gaps": report.repaired_gaps, "actor": actor_tag},
        )
        return {
            "success": report.success,
            "report": report.__dict__,
        }

    # ── BI-2 Slice 5: Authoritative Backtest Runtime Endpoints ──

    @app.post("/api/v1/backtests", status_code=202)
    def create_backtest(
        body: CreateBacktestRequest,
        session=Depends(session_from_header),
    ) -> dict[str, Any]:
        """Execute an authoritative backtest with fail-closed governance enforcement."""
        if app.state.security_store is None or app.state.backtest_service is None:
            raise HTTPException(status_code=503, detail="Backtest service unavailable")
        _check_expensive_throttle(session.user.user_id)
        user_id_str = str(session.user.user_id)
        try:
            run = app.state.backtest_service.submit_backtest(
                user_id=user_id_str,
                strategy_id=body.strategy_id,
                version_id=body.version_id,
                instrument=body.instrument,
                timeframe=body.timeframe,
                initial_capital=body.initial_capital,
                policy=body.policy,
                date_range=body.date_range,
                dataset_id=body.dataset_id,
            )
            _record_security_audit(
                event_type="BACKTEST_QUEUED",
                actor_id=session.user.user_id,
                details={
                    "run_id": run["run_id"],
                    "strategy_id": body.strategy_id,
                    "instrument": body.instrument,
                    "status": run["status"],
                },
            )
            return run
        except GovernanceRejectionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except InvalidBacktestParameterError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Unexpected backtest execution error")
            raise HTTPException(status_code=500, detail="Backtest execution unavailable") from exc

    @app.get("/api/v1/backtests/datasets")
    def backtest_datasets(session=Depends(session_from_header)):
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Dataset authority unavailable")
        # Owner datasets are installation-wide market data, not user-owned artifacts.
        # Do not disclose filesystem locations or administrative history to Users.
        keys = ("datasetId", "instrument", "timeframe", "startDate", "endDate", "rowCount",
                "hashSha256", "effectiveBacktestReadiness", "gapStatus", "lastUpdated")
        return [{k: ds[k] for k in keys} for ds in app.state.security_store.list_owner_datasets()]

    @app.get("/api/v1/backtests/{run_id}")
    def get_backtest_run(
        run_id: str,
        session=Depends(session_from_header),
    ) -> dict[str, Any]:
        """Fetch backtest run details for the authenticated user (or owner)."""
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        user_id_scope = None if session.user.role is Role.OWNER else str(session.user.user_id)
        run = app.state.security_store.get_backtest_run(run_id, user_id=user_id_scope)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Backtest run '{run_id}' not found")
        if session.user.role is not Role.OWNER:
            run = redact_server_paths(run)
        return run

    @app.get("/api/v1/backtests/{run_id}/trades")
    def get_backtest_trades(
        run_id: str,
        session=Depends(session_from_header),
    ) -> list[dict[str, Any]]:
        """Fetch trades list for a backtest run."""
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        user_id_scope = None if session.user.role is Role.OWNER else str(session.user.user_id)
        trades = app.state.security_store.get_backtest_trades(run_id, user_id=user_id_scope)
        if trades is None:
            raise HTTPException(status_code=404, detail=f"Backtest run '{run_id}' not found")
        return trades

    @app.get("/api/v1/backtests")
    def list_backtests(
        limit: int = Query(default=50, ge=1, le=500),
        session=Depends(session_from_header),
    ) -> list[dict[str, Any]]:
        """List backtest runs for the authenticated user."""
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        return app.state.security_store.list_backtest_runs(user_id=str(session.user.user_id), limit=limit)

    @app.post("/api/v1/backtests/{run_id}/cancel")
    def cancel_backtest_run(
        run_id: str,
        session=Depends(session_from_header),
    ) -> dict[str, Any]:
        """Cancel a backtest run."""
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        user_id_scope = None if session.user.role is Role.OWNER else str(session.user.user_id)
        cancelled = app.state.security_store.cancel_backtest_run(run_id, user_id=user_id_scope)
        if not cancelled:
            raise HTTPException(status_code=404, detail=f"Backtest run '{run_id}' not found or cannot be cancelled")
        run = app.state.security_store.get_backtest_run(run_id, user_id=user_id_scope)
        return {"ok": True, "cancelled": run["status"] == "CANCELLED",
                "cancel_requested": run["status"] == "CANCEL_REQUESTED", "status": run["status"], "run_id": run_id}

    # ── R-05: manual Walk-Forward / OOS ──
    # Product wiring around BacktestService. Manual RUN only: no schedulers,
    # no auto-runs. Each window is an exact registered backtest run.

    def _walkforward_authority() -> WalkForwardService:
        service = app.state.walkforward_service
        if service is None:
            raise HTTPException(status_code=503, detail="Walk-forward service unavailable")
        return service

    @app.post("/api/v1/walkforward/jobs", status_code=202)
    def create_walkforward_job(
        body: CreateWalkForwardRequest,
        session=Depends(mutable_session),
        service=Depends(_walkforward_authority),
    ) -> dict[str, Any]:
        """Manually RUN a walk-forward/OOS job (created and enqueued once)."""
        _check_expensive_throttle(session.user.user_id)
        try:
            job = service.create_and_run(
                user_id=str(session.user.user_id),
                strategy_id=body.strategy_id,
                version_id=body.version_id,
                dataset_id=body.dataset_id,
                instrument=body.instrument,
                timeframe=body.timeframe,
                is_days=body.is_days,
                oos_days=body.oos_days,
                initial_capital=body.initial_capital,
                policy=body.policy,
                max_windows=body.max_windows,
            )
            return {"job_id": job["jobId"], "status": job["status"], "job": job}
        except WalkForwardError as exc:
            msg = str(exc)
            if "not available to user" in msg or "denied" in msg or "Active authenticated" in msg:
                raise HTTPException(status_code=403, detail=msg) from exc
            raise HTTPException(status_code=422, detail=msg) from exc

    @app.get("/api/v1/walkforward/jobs")
    def list_walkforward_jobs(
        status: str | None = None,
        session=Depends(session_from_header),
        service=Depends(_walkforward_authority),
    ) -> dict[str, Any]:
        """List own walk-forward jobs (newest first)."""
        try:
            jobs = service.list_jobs(str(session.user.user_id), status=status)
        except WalkForwardError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"jobs": jobs, "total_count": len(jobs)}

    @app.get("/api/v1/walkforward/jobs/{job_id}")
    def get_walkforward_job(
        job_id: str,
        session=Depends(session_from_header),
        service=Depends(_walkforward_authority),
    ) -> dict[str, Any]:
        job = service.get_job(job_id, str(session.user.user_id))
        if job is None:
            raise HTTPException(status_code=404, detail=f"Walk-forward job '{job_id}' not found")
        return {"job": job}

    @app.post("/api/v1/walkforward/jobs/{job_id}/cancel")
    def cancel_walkforward_job(
        job_id: str,
        session=Depends(mutable_session),
        service=Depends(_walkforward_authority),
    ) -> dict[str, Any]:
        """Cooperatively cancel a pending/running job (stops between windows)."""
        try:
            job = service.cancel_job(job_id, str(session.user.user_id))
        except (WalkForwardError, SecurityStoreError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if job is None:
            raise HTTPException(status_code=404, detail=f"Walk-forward job '{job_id}' not found")
        return {"job_id": job_id, "cancel_requested": True, "job": job}

    @app.get("/api/v1/owner/walkforward/jobs")
    def list_owner_walkforward_jobs(
        status: str | None = None,
        session=Depends(owner_session),
        service=Depends(_walkforward_authority),
    ) -> dict[str, Any]:
        """Owner oversight across tenants (explicit privileged path)."""
        try:
            jobs = service.list_jobs(None, status=status)
        except WalkForwardError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"jobs": jobs, "total_count": len(jobs)}

    @app.get("/api/v1/owner/backtests")
    def list_owner_backtests(
        limit: int = Query(default=100, ge=1, le=500),
        session=Depends(owner_session),
    ) -> list[dict[str, Any]]:
        """List all system-wide backtest runs for Owner oversight."""
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        return app.state.security_store.list_backtest_runs(user_id=None, limit=limit)

    # ── BI-2 Slice 5: Authoritative Paper Trading Runtime Endpoints ──

    @app.post("/api/v1/paper/sessions")
    def create_paper_session(
        body: CreatePaperSessionRequest,
        session=Depends(session_from_header),
    ) -> dict[str, Any]:
        """Create a new paper trading session with fail-closed governance enforcement."""
        if app.state.security_store is None or app.state.paper_service is None:
            raise HTTPException(status_code=503, detail="Paper service unavailable")
        user_id_str = str(session.user.user_id)
        if session.user.role is not Role.OWNER and app.state.security_store is not None:
            access = app.state.security_store.check_user_strategy_access(user_id_str, body.strategy_id)
            if not access.get("permitted"):
                reason = access.get("reason", "")
                if "SUSPENDED" in str(reason):
                    raise HTTPException(status_code=403, detail=f"Strategy '{body.strategy_id}' is SUSPENDED under Owner governance")
                raise HTTPException(status_code=403, detail=f"User does not have access to strategy '{body.strategy_id}'")
        try:
            ses = app.state.paper_service.create_session(
                user_id=user_id_str,
                strategy_id=body.strategy_id,
                instrument=body.instrument,
                timeframe=body.timeframe,
                initial_capital=body.initial_capital,
                policy=body.policy,
                data_source_mode=body.data_source_mode,
                date_range=body.date_range,
                dataset_id=body.dataset_id,
            )
            _record_security_audit(
                event_type="PAPER_SESSION_CREATED",
                actor_id=session.user.user_id,
                details={
                    "session_id": ses["session_id"],
                    "strategy_id": body.strategy_id,
                    "instrument": body.instrument,
                    "initial_capital": body.initial_capital,
                    "data_source_mode": body.data_source_mode,
                },
            )
            return ses
        except GovernanceRejectionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except InvalidPaperParameterError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Unexpected paper session creation error")
            raise HTTPException(status_code=500, detail="Paper session creation failed") from exc

    @app.post("/api/v1/paper/sessions/{session_id}/start")
    def start_paper_session(
        session_id: str,
        session=Depends(session_from_header),
    ) -> dict[str, Any]:
        """Start paper execution for a session."""
        if app.state.security_store is None or app.state.paper_service is None:
            raise HTTPException(status_code=503, detail="Paper service unavailable")
        user_id_str = str(session.user.user_id)
        try:
            ses = app.state.paper_service.start_session(session_id, user_id=user_id_str)
            _record_security_audit(
                event_type="PAPER_SESSION_STARTED",
                actor_id=session.user.user_id,
                details={"session_id": session_id, "status": ses["status"]},
            )
            return ses
        except PaperSessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except GovernanceRejectionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ExternalLiveDataSourceRequiredError as exc:
            _record_security_audit(
                event_type="PAPER_EXTERNAL_LIVE_DATA_SOURCE_REQUIRED",
                actor_id=session.user.user_id,
                details={"session_id": session_id, "error": str(exc)},
            )
            raise HTTPException(status_code=424, detail=str(exc)) from exc
        except InvalidPaperParameterError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Unexpected paper session start error")
            raise HTTPException(status_code=500, detail="Paper session start failed") from exc

    @app.post("/api/v1/paper/sessions/{session_id}/stop")
    def stop_paper_session(
        session_id: str,
        session=Depends(session_from_header),
    ) -> dict[str, Any]:
        """Stop paper execution for a session."""
        if app.state.security_store is None or app.state.paper_service is None:
            raise HTTPException(status_code=503, detail="Paper service unavailable")
        user_id_str = str(session.user.user_id)
        try:
            ses = app.state.paper_service.stop_session(session_id, user_id=user_id_str)
            _record_security_audit(
                event_type="PAPER_SESSION_STOPPED",
                actor_id=session.user.user_id,
                details={"session_id": session_id},
            )
            return ses
        except PaperSessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Unexpected paper session stop error")
            raise HTTPException(status_code=500, detail="Paper session stop failed") from exc

    @app.get("/api/v1/paper/sessions/{session_id}")
    def get_paper_session(
        session_id: str,
        session=Depends(session_from_header),
    ) -> dict[str, Any]:
        """Fetch paper session details for the authenticated user (or owner)."""
        if app.state.security_store is None or app.state.paper_service is None:
            raise HTTPException(status_code=503, detail="Paper service unavailable")
        user_id_scope = None if session.user.role is Role.OWNER else str(session.user.user_id)
        ses = app.state.paper_service.get_session(session_id, user_id=user_id_scope)
        if ses is None:
            raise HTTPException(status_code=404, detail=f"Paper session '{session_id}' not found")
        if session.user.role is not Role.OWNER:
            ses = redact_server_paths(ses)
        return ses

    @app.get("/api/v1/paper/sessions")
    def list_paper_sessions(
        limit: int = Query(default=50, ge=1, le=500),
        session=Depends(session_from_header),
    ) -> list[dict[str, Any]]:
        """List paper sessions for the authenticated user."""
        if app.state.security_store is None or app.state.paper_service is None:
            raise HTTPException(status_code=503, detail="Paper service unavailable")
        return app.state.paper_service.list_sessions(user_id=str(session.user.user_id), limit=limit)

    @app.get("/api/v1/paper/sessions/{session_id}/positions")
    def get_paper_positions(
        session_id: str,
        session=Depends(session_from_header),
    ) -> list[dict[str, Any]]:
        """Fetch positions for a paper session."""
        if app.state.security_store is None or app.state.paper_service is None:
            raise HTTPException(status_code=503, detail="Paper service unavailable")
        user_id_scope = None if session.user.role is Role.OWNER else str(session.user.user_id)
        ses = app.state.paper_service.get_session(session_id, user_id=user_id_scope)
        if ses is None:
            raise HTTPException(status_code=404, detail=f"Paper session '{session_id}' not found")
        return app.state.paper_service.get_positions(session_id, user_id=user_id_scope)

    @app.get("/api/v1/paper/sessions/{session_id}/orders")
    def get_paper_orders(
        session_id: str,
        session=Depends(session_from_header),
    ) -> list[dict[str, Any]]:
        """Fetch orders and fills for a paper session."""
        if app.state.security_store is None or app.state.paper_service is None:
            raise HTTPException(status_code=503, detail="Paper service unavailable")
        user_id_scope = None if session.user.role is Role.OWNER else str(session.user.user_id)
        ses = app.state.paper_service.get_session(session_id, user_id=user_id_scope)
        if ses is None:
            raise HTTPException(status_code=404, detail=f"Paper session '{session_id}' not found")
        return app.state.paper_service.get_orders(session_id, user_id=user_id_scope)

    @app.get("/api/v1/paper/sessions/{session_id}/events")
    def get_paper_events(
        session_id: str,
        limit: int = Query(default=50, ge=1, le=500),
        session=Depends(session_from_header),
    ) -> list[dict[str, Any]]:
        """Fetch simulation and risk events for a paper session."""
        if app.state.security_store is None or app.state.paper_service is None:
            raise HTTPException(status_code=503, detail="Paper service unavailable")
        user_id_scope = None if session.user.role is Role.OWNER else str(session.user.user_id)
        ses = app.state.paper_service.get_session(session_id, user_id=user_id_scope)
        if ses is None:
            raise HTTPException(status_code=404, detail=f"Paper session '{session_id}' not found")
        return app.state.paper_service.get_events(session_id, user_id=user_id_scope, limit=limit)

    @app.post("/api/v1/paper/sessions/{session_id}/live-quote")
    def inject_live_quote(
        session_id: str,
        body: IngestLiveQuoteRequest,
        session=Depends(session_from_header),
    ) -> dict[str, Any]:
        """Ingest an authorized live quote / tick into an active LIVE_MARKET session."""
        if app.state.security_store is None or app.state.paper_service is None:
            raise HTTPException(status_code=503, detail="Paper service unavailable")
        user_id_scope = None if session.user.role is Role.OWNER else str(session.user.user_id)
        ses = app.state.paper_service.get_session(session_id, user_id=user_id_scope)
        if not ses:
            raise HTTPException(status_code=404, detail=f"Paper session '{session_id}' not found or access denied")
        try:
            ts = datetime.fromisoformat(body.exchange_timestamp.replace("Z", "+00:00"))
            from datetime import date
            session_inst = (ses.get("instrument") or "NIFTY").upper()
            is_opt = (
                body.segment.lower() in ("options", "optidx")
                or body.option_type is not None
                or body.strike is not None
                or "CE" in body.instrument.upper()
                or "PE" in body.instrument.upper()
            )
            if is_opt:
                if body.strike is None or body.strike <= 0:
                    raise HTTPException(status_code=422, detail="Option quotes must specify a positive strike price")
                if not body.expiry:
                    raise HTTPException(status_code=422, detail="Option quotes must specify an explicit expiry date (YYYY-MM-DD)")
                try:
                    opt_expiry = date.fromisoformat(body.expiry)
                except Exception:
                    raise HTTPException(status_code=422, detail=f"Invalid option expiry date format '{body.expiry}', expected YYYY-MM-DD")

                opt_type = (body.option_type or ("PE" if "PE" in body.instrument.upper() else ("CE" if "CE" in body.instrument.upper() else ""))).upper()
                if opt_type not in ("CE", "PE"):
                    raise HTTPException(status_code=422, detail=f"Invalid option type '{opt_type}', must be CE or PE")

                opt_underlying = (body.underlying or session_inst).upper()
                if opt_underlying != session_inst:
                    raise HTTPException(status_code=400, detail=f"Option underlying '{opt_underlying}' does not match session instrument '{session_inst}'")

                ident = InstrumentIdentity(
                    market=body.market.lower(),
                    instrument=body.instrument.upper(),
                    segment="options",
                    underlying=opt_underlying,
                    expiry=opt_expiry,
                    strike=Decimal(str(body.strike)),
                    option_type=opt_type,
                )
            else:
                if body.instrument.upper() != session_inst:
                    raise HTTPException(status_code=400, detail=f"Quote instrument '{body.instrument}' does not match session instrument '{session_inst}'")
                ident = InstrumentIdentity(
                    market=body.market.lower(),
                    instrument=body.instrument.upper(),
                    segment=body.segment.lower() if body.segment.lower() in ("index", "equity", "futures") else "index",
                )
            lp = Decimal(str(body.last_price)) if body.last_price is not None else None
            bp = Decimal(str(body.bid_price)) if body.bid_price is not None else None
            ap = Decimal(str(body.ask_price)) if body.ask_price is not None else None
            bid_qty = Decimal(str(body.bid_quantity)) if body.bid_quantity is not None else None
            ask_qty = Decimal(str(body.ask_quantity)) if body.ask_quantity is not None else None
            quote = QuoteSnapshot(
                instrument_identity=ident,
                exchange_timestamp=ts,
                bid_price=bp,
                ask_price=ap,
                bid_quantity=bid_qty,
                ask_quantity=ask_qty,
                last_price=lp,
                source=body.source,
            )
            event = LiveQuoteEvent(event_id=body.event_id, quote=quote)
            return app.state.paper_service.process_live_quote(session_id, event)
        except (FeedNotConnectedError, StaleQuoteError, OutOfOrderQuoteError, WrongInstrumentError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (PaperSessionNotFoundError, InvalidPaperParameterError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Unexpected error processing live quote")
            raise HTTPException(status_code=500, detail="Failed to process live quote") from exc

    @app.post("/api/v1/paper/sessions/{session_id}/feed-state")
    def set_paper_feed_state(
        session_id: str,
        body: FeedStateRequest,
        session=Depends(session_from_header),
    ) -> dict[str, Any]:
        """Update feed connection state for a paper session."""
        if app.state.security_store is None or app.state.paper_service is None:
            raise HTTPException(status_code=503, detail="Paper service unavailable")
        user_id_scope = None if session.user.role is Role.OWNER else str(session.user.user_id)
        ses = app.state.paper_service.get_session(session_id, user_id=user_id_scope)
        if not ses:
            raise HTTPException(status_code=404, detail=f"Paper session '{session_id}' not found or access denied")
        try:
            return app.state.paper_service.set_live_feed_state(session_id, body.state)
        except Exception as exc:
            logger.error("Failed to set paper live feed state for session %s: %s", session_id, exc)
            raise HTTPException(status_code=400, detail="PAPER_LIVE_FEED_STATE_FAILED") from exc

    @app.post("/api/v1/paper/sessions/{session_id}/reattach")
    def reattach_paper_session(
        session_id: str,
        session=Depends(session_from_header),
    ) -> dict[str, Any]:
        """F-11: explicit re-attach of a persisted ACTIVE live-market-paper session after restart (paper only)."""
        if app.state.security_store is None or app.state.paper_service is None:
            raise HTTPException(status_code=503, detail="Paper service unavailable")
        user_id_scope = None if session.user.role is Role.OWNER else str(session.user.user_id)
        ses = app.state.paper_service.get_session(session_id, user_id=user_id_scope)
        if not ses:
            raise HTTPException(status_code=404, detail=f"Paper session '{session_id}' not found or access denied")
        try:
            result = app.state.paper_service.reattach_live_session(
                session_id, user_id=user_id_scope)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (PaperSessionNotFoundError, InvalidPaperParameterError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except GovernanceRejectionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        _record_security_audit(
            event_type="PAPER_SESSION_REATTACHED",
            actor_id=session.user.user_id,
            details={"session_id": session_id},
        )
        return result

    @app.get("/api/v1/paper/sessions/{session_id}/recovery-status")
    def paper_session_recovery_status(
        session_id: str,
        session=Depends(session_from_header),
    ) -> dict[str, Any]:
        """F-11: restart recovery classification and status."""
        if app.state.security_store is None or app.state.paper_service is None:
            raise HTTPException(status_code=503, detail="Paper service unavailable")
        user_id_scope = None if session.user.role is Role.OWNER else str(session.user.user_id)
        ses = app.state.paper_service.get_session(session_id, user_id=user_id_scope)
        if not ses:
            raise HTTPException(status_code=404, detail=f"Paper session '{session_id}' not found or access denied")
        classification = app.state.paper_service.classify_session_for_recovery(ses)
        reattachable = classification in (
            "RECOVERY_ELIGIBLE",
            "FEED_RESUMABLE",
            "LIVE_ACTIVE_REATTACHABLE",
            "LIVE_ACTIVE_PROVIDER_UNAVAILABLE",
        )
        return {
            "session_id": session_id,
            "status": ses.get("status"),
            "data_source_mode": ses.get("data_source_mode"),
            "classification": classification,
            "feed_state": ses.get("feed_status") or ses.get("feed_state"),
            "reattachable": reattachable,
        }

    @app.get("/api/v1/owner/paper/sessions")
    def list_owner_paper_sessions(
        limit: int = Query(default=100, ge=1, le=500),
        session=Depends(owner_session),
    ) -> list[dict[str, Any]]:
        """List all system-wide paper sessions for Owner oversight."""
        if app.state.security_store is None or app.state.paper_service is None:
            raise HTTPException(status_code=503, detail="Paper service unavailable")
        return app.state.paper_service.list_sessions(user_id=None, limit=limit)

    @app.post("/api/v1/owner/paper/sessions/{session_id}/hold")
    def set_owner_paper_session_hold(
        session_id: str,
        body: PaperHoldRequest,
        session=Depends(owner_mutable_session),
    ) -> dict[str, Any]:
        """Set or release Owner hold on a paper session."""
        if app.state.security_store is None or app.state.paper_service is None:
            raise HTTPException(status_code=503, detail="Paper service unavailable")
        updated = app.state.paper_service.set_session_hold(
            session_id,
            hold=body.hold,
            reason=body.reason or ("Owner hold applied" if body.hold else "Owner hold released"),
        )
        if not updated:
            raise HTTPException(status_code=404, detail=f"Paper session '{session_id}' not found")
        _record_security_audit(
            event_type="PAPER_SESSION_HOLD_UPDATED",
            actor_id=session.user.user_id,
            details={"session_id": session_id, "hold": body.hold, "reason": body.reason},
        )
        return {"success": True, "session_id": session_id, "hold": body.hold}

    # ── P1-A (R-03): strategy readiness authority ──
    # Backend-authoritative Backtest/Paper/Live readiness. Ordinary Backtest and
    # Paper readiness NEVER require Owner promotion; LIVE real-money readiness
    # remains Owner-governed and DISARMED.

    @app.get("/api/v1/strategies/{strategy_id}/readiness")
    def get_strategy_readiness(
        strategy_id: str,
        session=Depends(session_from_header),
    ) -> dict[str, Any]:
        """Authoritative readiness for backtest / paper / live-paper / live."""
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        store = app.state.security_store
        user_id_str = str(session.user.user_id)
        backtest = store.check_self_service_backtest_eligibility(strategy_id, user_id=user_id_str)
        paper = store.check_self_service_paper_eligibility(strategy_id, user_id=user_id_str)
        return {
            "strategyId": strategy_id,
            "backtest": {"ready": bool(backtest.get("permitted")), "code": backtest.get("code"), "reason": backtest.get("reason")},
            "paper": {"ready": bool(paper.get("permitted")), "code": paper.get("code"), "reason": paper.get("reason")},
            "livePaper": {"ready": bool(paper.get("permitted")), "code": paper.get("code"), "reason": paper.get("reason")},
            "live": {"ready": False, "code": "LIVE_EXECUTION_DISARMED",
                     "reason": "Live real-money execution is DISARMED in this runtime and remains under Owner governance."},
        }

    # ── P1-A (R-02): per-user broker/API connection authority ──

    def _user_scope(session) -> str:
        return str(session.user.user_id)

    @app.post("/api/v1/user/connections")
    def create_user_connection(
        body: CreateUserConnectionRequest,
        session=Depends(mutable_session),
    ) -> dict[str, Any]:
        """Create an isolated per-user broker/API connection record (architecture only)."""
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        try:
            conn = app.state.security_store.create_user_connection(
                user_id=_user_scope(session),
                provider=body.provider,
                account_ref=body.account_ref,
                credential_ref=body.credential_ref,
                actor=str(session.user.role),
            )
            _record_security_audit(
                event_type="USER_CONNECTION_CREATED",
                actor_id=session.user.user_id,
                details={"connection_id": conn["connectionId"], "provider": conn["provider"]},
            )
            return {"success": True, "connection": conn}
        except SecurityStoreError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/v1/user/connections")
    def list_user_connections(session=Depends(session_from_header)) -> dict[str, Any]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        connections = app.state.security_store.list_user_connections(_user_scope(session))
        return {"source": "BACKEND", "connections": connections, "total_count": len(connections)}

    @app.get("/api/v1/user/connections/{connection_id}")
    def get_user_connection(
        connection_id: str,
        session=Depends(session_from_header),
    ) -> dict[str, Any]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        conn = app.state.security_store.get_user_connection(connection_id, _user_scope(session))
        if conn is None:
            raise HTTPException(status_code=404, detail="Connection not found")
        return {"source": "BACKEND", "connection": conn}

    @app.patch("/api/v1/user/connections/{connection_id}")
    def update_user_connection(
        connection_id: str,
        body: UpdateUserConnectionRequest,
        session=Depends(mutable_session),
    ) -> dict[str, Any]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        try:
            conn = app.state.security_store.update_user_connection(
                connection_id=connection_id,
                user_id=_user_scope(session),
                account_ref=body.account_ref,
                credential_ref=body.credential_ref,
                clear_credential_ref=body.clear_credential_ref,
                status=body.status,
                actor=str(session.user.role),
            )
            _record_security_audit(
                event_type="USER_CONNECTION_UPDATED",
                actor_id=session.user.user_id,
                details={"connection_id": connection_id},
            )
            return {"success": True, "connection": conn}
        except SecurityStoreError as exc:
            msg = str(exc)
            if "not found" in msg:
                raise HTTPException(status_code=404, detail=msg) from exc
            raise HTTPException(status_code=422, detail=msg) from exc

    @app.post("/api/v1/user/strategies/{strategy_id}/connection")
    def map_user_strategy_connection(
        strategy_id: str,
        body: MapStrategyConnectionRequest,
        session=Depends(mutable_session),
    ) -> dict[str, Any]:
        """Map own strategy to own connection/account (preparation only, no execution)."""
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        try:
            mapping = app.state.security_store.map_strategy_connection(
                user_id=_user_scope(session),
                strategy_id=strategy_id,
                connection_id=body.connection_id,
                execution_mode=body.execution_mode,
                strategy_version_id=body.strategy_version_id,
                governance_store=app.state.governance_store,
                actor=str(session.user.role),
            )
            _record_security_audit(
                event_type="STRATEGY_CONNECTION_MAPPED",
                actor_id=session.user.user_id,
                details={"strategy_id": strategy_id, "connection_id": body.connection_id,
                         "execution_mode": body.execution_mode},
            )
            return {"success": True, "mapping": mapping}
        except SecurityStoreError as exc:
            msg = str(exc)
            if "not found" in msg or "denied" in msg:
                raise HTTPException(status_code=403, detail=msg) from exc
            raise HTTPException(status_code=422, detail=msg) from exc

    @app.get("/api/v1/user/strategies/{strategy_id}/connection")
    def get_user_strategy_connection(
        strategy_id: str,
        execution_mode: str = "LIVE_PAPER",
        session=Depends(session_from_header),
    ) -> dict[str, Any]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        mapping = app.state.security_store.get_strategy_connection_mapping(
            _user_scope(session), strategy_id, execution_mode)
        if mapping is None:
            raise HTTPException(status_code=404, detail="No strategy-connection mapping found")
        return {"source": "BACKEND", "mapping": mapping}

    @app.get("/api/v1/owner/user-connections")
    def list_all_user_connections(session=Depends(owner_session)) -> dict[str, Any]:
        """Owner oversight of per-user connections (masked identifiers, secrets never projected)."""
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        connections = app.state.security_store.list_user_connections(None, mask_account_ref=True)
        return {"source": "BACKEND", "connections": connections, "total_count": len(connections)}

    @app.post("/api/v1/user/connections/{connection_id}/retire")
    def retire_user_connection(
        connection_id: str,
        session=Depends(mutable_session),
    ) -> dict[str, Any]:
        """Explicit retirement (NF-R203-06): the record is preserved for
        deployment/audit/report history but becomes operationally dead
        (RETIRED, credential reference cleared). Idempotent."""
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        try:
            conn = app.state.security_store.retire_user_connection(
                connection_id=connection_id,
                user_id=_user_scope(session),
                actor=str(session.user.role),
            )
            _record_security_audit(
                event_type="USER_CONNECTION_RETIRED",
                actor_id=session.user.user_id,
                details={"connection_id": connection_id},
            )
            return {"success": True, "connection": conn}
        except SecurityStoreError as exc:
            msg = str(exc)
            if "not found" in msg:
                raise HTTPException(status_code=404, detail=msg) from exc
            raise HTTPException(status_code=422, detail=msg) from exc

    @app.post("/api/v1/owner/user-connections/{connection_id}/status")
    def set_user_connection_status(
        connection_id: str,
        body: UpdateUserConnectionStatusRequest,
        session=Depends(owner_mutable_session),
    ) -> dict[str, Any]:
        if app.state.security_store is None:
            raise HTTPException(status_code=503, detail="Security store unavailable")
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            conn = app.state.security_store.set_user_connection_status(
                connection_id=connection_id, status=body.status, reason=body.reason, actor=actor_tag)
            _record_security_audit(
                event_type="USER_CONNECTION_STATUS_UPDATED",
                actor_id=session.user.user_id,
                details={"connection_id": connection_id, "status": body.status, "actor": actor_tag},
            )
            return {"success": True, "connection": conn}
        except SecurityStoreError as exc:
            msg = str(exc)
            if "not found" in msg:
                raise HTTPException(status_code=404, detail=msg) from exc
            raise HTTPException(status_code=422, detail=msg) from exc

    # ── P1-A (R-07): persistent deployment lifecycle ──
    # State management only. These endpoints never execute orders and never arm live trading.

    def _deployment_authority():
        if app.state.deployment_service is None:
            raise HTTPException(status_code=503, detail="Deployment service unavailable")
        return app.state.deployment_service

    @app.post("/api/v1/user/deployments")
    def create_user_deployment(
        body: CreateDeploymentRequest,
        session=Depends(mutable_session),
        service=Depends(_deployment_authority),
    ) -> dict[str, Any]:
        try:
            deployment = service.create_deployment(
                user_id=_user_scope(session),
                strategy_id=body.strategy_id,
                version_id=body.strategy_version_id,
                connection_id=body.connection_id,
                instrument=body.instrument,
                timeframe=body.timeframe,
                execution_mode=body.execution_mode,
                risk_ref=body.risk_ref,
                actor=str(session.user.role),
            )
            _record_security_audit(
                event_type="DEPLOYMENT_CREATED",
                actor_id=session.user.user_id,
                details={"deployment_id": deployment["deploymentId"], "strategy_id": body.strategy_id,
                         "execution_mode": body.execution_mode, "status": deployment["status"]},
            )
            return {"success": True, "deployment": deployment}
        except DeploymentError as exc:
            msg = str(exc)
            if "not found" in msg or "denied" in msg or "eligible" in msg or "Connection" in msg:
                raise HTTPException(status_code=403, detail=msg) from exc
            raise HTTPException(status_code=422, detail=msg) from exc

    @app.get("/api/v1/user/deployments")
    def list_user_deployments(
        status: str | None = None,
        session=Depends(session_from_header),
        service=Depends(_deployment_authority),
    ) -> dict[str, Any]:
        try:
            deployments = service.list_deployments(_user_scope(session), status=status)
            return {"source": "BACKEND", "deployments": deployments, "total_count": len(deployments)}
        except DeploymentError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/v1/user/deployments/{deployment_id}")
    def get_user_deployment(
        deployment_id: str,
        session=Depends(session_from_header),
        service=Depends(_deployment_authority),
    ) -> dict[str, Any]:
        try:
            return {"source": "BACKEND", "deployment": service.get_deployment(deployment_id, _user_scope(session))}
        except DeploymentError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/user/deployments/{deployment_id}/pause")
    def pause_user_deployment(
        deployment_id: str,
        session=Depends(mutable_session),
        service=Depends(_deployment_authority),
    ) -> dict[str, Any]:
        try:
            deployment = service.pause_deployment(deployment_id, _user_scope(session), actor=str(session.user.role))
            _record_security_audit(event_type="DEPLOYMENT_PAUSED", actor_id=session.user.user_id,
                                   details={"deployment_id": deployment_id})
            return {"success": True, "deployment": deployment}
        except DeploymentError as exc:
            msg = str(exc)
            if "not found" in msg:
                raise HTTPException(status_code=404, detail=msg) from exc
            raise HTTPException(status_code=422, detail=msg) from exc

    @app.post("/api/v1/user/deployments/{deployment_id}/resume")
    def resume_user_deployment(
        deployment_id: str,
        session=Depends(mutable_session),
        service=Depends(_deployment_authority),
    ) -> dict[str, Any]:
        try:
            deployment = service.resume_deployment(deployment_id, _user_scope(session), actor=str(session.user.role))
            _record_security_audit(event_type="DEPLOYMENT_RESUMED", actor_id=session.user.user_id,
                                   details={"deployment_id": deployment_id, "status": deployment["status"]})
            return {"success": True, "deployment": deployment}
        except DeploymentError as exc:
            msg = str(exc)
            if "not found" in msg:
                raise HTTPException(status_code=404, detail=msg) from exc
            raise HTTPException(status_code=422, detail=msg) from exc

    @app.post("/api/v1/user/deployments/{deployment_id}/stop")
    def stop_user_deployment(
        deployment_id: str,
        session=Depends(mutable_session),
        service=Depends(_deployment_authority),
    ) -> dict[str, Any]:
        try:
            deployment = service.stop_deployment(deployment_id, _user_scope(session), actor=str(session.user.role))
            _record_security_audit(event_type="DEPLOYMENT_STOPPED", actor_id=session.user.user_id,
                                   details={"deployment_id": deployment_id})
            return {"success": True, "deployment": deployment}
        except DeploymentError as exc:
            msg = str(exc)
            if "not found" in msg:
                raise HTTPException(status_code=404, detail=msg) from exc
            raise HTTPException(status_code=422, detail=msg) from exc

    @app.post("/api/v1/user/deployments/{deployment_id}/runtime")
    def link_user_deployment_runtime(
        deployment_id: str,
        body: LinkDeploymentRuntimeRequest,
        session=Depends(mutable_session),
        service=Depends(_deployment_authority),
    ) -> dict[str, Any]:
        try:
            deployment = service.link_runtime_session(deployment_id, _user_scope(session), body.runtime_session_id)
            _record_security_audit(event_type="DEPLOYMENT_RUNTIME_LINKED", actor_id=session.user.user_id,
                                   details={"deployment_id": deployment_id,
                                            "runtime_session_id": body.runtime_session_id})
            return {"success": True, "deployment": deployment}
        except DeploymentError as exc:
            msg = str(exc)
            if "not found" in msg:
                raise HTTPException(status_code=404, detail=msg) from exc
            raise HTTPException(status_code=422, detail=msg) from exc

    @app.get("/api/v1/user/deployments-recovery")
    def user_deployments_recovery(
        session=Depends(session_from_header),
        service=Depends(_deployment_authority),
    ) -> dict[str, Any]:
        return {"source": "BACKEND", **service.recovery_snapshot(_user_scope(session))}

    @app.get("/api/v1/owner/deployments")
    def list_all_deployments(
        status: str | None = None,
        session=Depends(owner_session),
        service=Depends(_deployment_authority),
    ) -> dict[str, Any]:
        try:
            deployments = service.list_deployments(None, status=status)
            return {"source": "BACKEND", "deployments": deployments, "total_count": len(deployments)}
        except DeploymentError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/owner/deployments/{deployment_id}/block")
    def block_deployment(
        deployment_id: str,
        body: BlockDeploymentRequest,
        session=Depends(owner_mutable_session),
        service=Depends(_deployment_authority),
    ) -> dict[str, Any]:
        actor_tag = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            deployment = service.block_deployment(deployment_id, reason=body.reason, actor=actor_tag)
            _record_security_audit(event_type="DEPLOYMENT_BLOCKED", actor_id=session.user.user_id,
                                   details={"deployment_id": deployment_id, "reason": body.reason})
            return {"success": True, "deployment": deployment}
        except DeploymentError as exc:
            msg = str(exc)
            if "not found" in msg:
                raise HTTPException(status_code=404, detail=msg) from exc
            raise HTTPException(status_code=422, detail=msg) from exc

    @app.get("/api/v1/owner/deployments-recovery")
    def owner_deployments_recovery(
        session=Depends(owner_session),
        service=Depends(_deployment_authority),
    ) -> dict[str, Any]:
        return {"source": "BACKEND", **service.recovery_snapshot(None)}

    def _format_file_size(num_bytes: int) -> str:
        if num_bytes < 1024:
            return f"{num_bytes} B"
        elif num_bytes < 1024 * 1024:
            return f"{num_bytes / 1024:.1f} KB"
        else:
            return f"{num_bytes / (1024 * 1024):.1f} MB"

    def _sanitize_report_for_client(item: dict[str, Any], is_owner: bool) -> dict[str, Any]:
        """Strip raw server internal filesystem paths for normal users recursively (F-17 / P3-2)."""
        return sanitize_report_for_client(item, is_owner=is_owner)

    def _build_authoritative_reports(user_id: str | None = None, is_owner: bool = False) -> list[dict[str, Any]]:
        store = getattr(app.state, "security_store", None)
        if store is None:
            raise HTTPException(status_code=503, detail="Reports backend authority unavailable")

        reports: list[dict[str, Any]] = []

        # 1. Backtest completed runs from authoritative store
        try:
            runs = store.list_backtest_runs(user_id=user_id, limit=50)
        except Exception as exc:
            logger.error("Failed to query backtest runs: %s", exc)
            raise HTTPException(status_code=503, detail="QUERY_BACKTEST_RUNS_FAILED") from exc

        for r in runs:
            run_id = str(r.get("run_id", ""))
            raw_status = str(r.get("status", "COMPLETED")).upper()
            meta = r.get("execution_metadata") or {}
            artifact_file = meta.get("artifact_path") or r.get("artifact_path")

            if raw_status in {"COMPLETED", "SUCCESS"}:
                rep_status = "AVAILABLE"
            elif raw_status in {"RUNNING", "PENDING", "INITIALIZED"}:
                rep_status = "PENDING"
            elif raw_status in {"FAILED", "CANCELLED", "CANCEL_REQUESTED"}:
                rep_status = "FAILED"
            else:
                rep_status = raw_status

            format_ext = "JSON"
            if artifact_file:
                if os.path.exists(artifact_file):
                    file_size = _format_file_size(os.path.getsize(artifact_file))
                    ext = os.path.splitext(artifact_file)[1].lstrip(".").upper()
                    if ext:
                        format_ext = ext
                else:
                    rep_status = "ARTIFACT_MISSING"
                    file_size = "UNAVAILABLE"
            else:
                raw_bytes = len(json.dumps(r, default=str).encode("utf-8"))
                file_size = _format_file_size(raw_bytes)

            date_range = r.get("date_range")
            created_at = r.get("created_at_utc") or ""
            if date_range and str(date_range).strip():
                period = str(date_range).strip()
            elif created_at:
                tf = r.get("timeframe", "1m")
                period = f"{tf} · {str(created_at)[:10]}"
            else:
                period = "UNAVAILABLE"

            generated_at = r.get("completed_at_utc") or created_at or "UNAVAILABLE"

            if rep_status == "FAILED":
                err = r.get("error_message") or "Backtest run failed"
                summary = f"Failed: {err}"
            else:
                trades_cnt = r.get("total_trades", r.get("trades_count", 0))
                win_rate = r.get("win_rate_pct", r.get("win_rate", 0))
                sharpe = r.get("sharpe_ratio", 0)
                dd = r.get("max_drawdown", 0)
                summary = f"Trades: {trades_cnt} · Win Rate: {win_rate}% · Sharpe: {sharpe} · Max DD: {dd}%"

            rep = {
                "id": f"rep-bt-{run_id}",
                "reportId": f"rep-bt-{run_id}",
                "title": f"Backtest Performance Report · {r.get('strategy_name') or r.get('strategy_id')} ({r.get('instrument', 'NIFTY')})",
                "category": "BACKTEST_SUMMARY",
                "period": period,
                "generatedAt": generated_at,
                "fileSize": file_size,
                "format": format_ext,
                "status": rep_status,
                "summary": summary,
                "originatingRunId": run_id,
                "userId": r.get("user_id"),
                "provenance": "BACKTEST_ENGINE",
                "errorState": r.get("error_message") if rep_status == "FAILED" else None,
                "data": r,
            }
            reports.append(_sanitize_report_for_client(rep, is_owner=is_owner))

        # 2. Paper trading sessions
        try:
            sessions = store.list_paper_sessions(user_id=user_id, limit=50)
        except Exception as exc:
            logger.error("Failed to query paper sessions: %s", exc)
            raise HTTPException(status_code=503, detail="QUERY_PAPER_SESSIONS_FAILED") from exc

        for s in sessions:
            session_id = str(s.get("session_id", ""))
            s_status = str(s.get("status", "INITIALIZED")).upper()

            if s_status in {"COMPLETED", "ARCHIVED", "CLOSED"}:
                rep_status = "AVAILABLE"
            elif s_status in {"RUNNING", "ACTIVE", "INITIALIZED"}:
                rep_status = "PENDING"
            elif s_status in {"FAILED", "ERROR", "REJECTED"}:
                rep_status = "FAILED"
            else:
                rep_status = s_status

            dr = s.get("date_range")
            c_at = s.get("created_at_utc") or ""
            u_at = s.get("stopped_at_utc") or s.get("updated_at_utc") or ""
            if dr and str(dr).strip():
                period = str(dr).strip()
            elif c_at and u_at and str(c_at)[:10] != str(u_at)[:10]:
                period = f"{str(c_at)[:10]} to {str(u_at)[:10]}"
            elif c_at:
                period = str(c_at)[:10]
            else:
                period = "UNAVAILABLE"

            generated_at = u_at or c_at or "UNAVAILABLE"
            raw_bytes = len(json.dumps(s, default=str).encode("utf-8"))
            file_size = _format_file_size(raw_bytes)

            summary = f"Status: {s_status} · Realized PnL: ₹{s.get('realized_pnl', 0)} · Trades: {s.get('trades_count', 0)}"

            rep = {
                "id": f"rep-paper-{session_id}",
                "reportId": f"rep-paper-{session_id}",
                "title": f"Paper Trading Session Audit · {s.get('strategy_name', 'Strategy')} ({session_id})",
                "category": "TRADE_LEDGER",
                "period": period,
                "generatedAt": generated_at,
                "fileSize": file_size,
                "format": "JSON",
                "status": rep_status,
                "summary": summary,
                "originatingRunId": session_id,
                "userId": s.get("user_id"),
                "provenance": "PAPER_ENGINE",
                "errorState": s.get("error_message") if rep_status == "FAILED" else None,
                "data": s,
            }
            reports.append(_sanitize_report_for_client(rep, is_owner=is_owner))

        # 3. Shadow executions digest
        if app.state.live_readiness_service is not None:
            try:
                shadow_orders = app.state.live_readiness_service.shadow_orders(user_id=user_id, limit=20)
                if shadow_orders:
                    timestamps = [o.get("created_at") or o.get("timestamp") for o in shadow_orders if isinstance(o, dict) and (o.get("created_at") or o.get("timestamp"))]
                    if timestamps:
                        period = f"{str(min(timestamps))[:10]} to {str(max(timestamps))[:10]}" if str(min(timestamps))[:10] != str(max(timestamps))[:10] else str(min(timestamps))[:10]
                    else:
                        period = datetime.now(timezone.utc).date().isoformat()

                    data_bytes = len(json.dumps(shadow_orders, default=str).encode("utf-8"))
                    rep = {
                        "id": "rep-shadow-digest",
                        "reportId": "rep-shadow-digest",
                        "title": "Shadow Dry-Run Validation Digest",
                        "category": "RISK_SUMMARY",
                        "period": period,
                        "generatedAt": datetime.now(timezone.utc).isoformat(),
                        "fileSize": _format_file_size(data_bytes),
                        "format": "JSON",
                        "status": "AVAILABLE",
                        "summary": f"Evaluated {len(shadow_orders)} shadow dry-run intents under broker-agnostic constraints.",
                        "provenance": "SHADOW_VALIDATOR",
                        "data": {"shadow_orders": shadow_orders},
                    }
                    reports.append(_sanitize_report_for_client(rep, is_owner=is_owner))
            except Exception as exc:
                logger.warning("Error querying shadow orders for reports: %s", exc)

        # 4. Security & Audit Digest (for owner oversight only)
        if user_id is None:
            try:
                adapter = getattr(app.state, "audit_adapter", None)
                if adapter is not None and hasattr(adapter, "read_audit_events"):
                    events = adapter.read_audit_events(limit=50).get("events", [])
                else:
                    events = []
                if events:
                    ts_list = [e.get("timestamp") or e.get("recorded_at_utc") for e in events if isinstance(e, dict) and (e.get("timestamp") or e.get("recorded_at_utc"))]
                    if ts_list:
                        period = f"{str(min(ts_list))[:10]} to {str(max(ts_list))[:10]}" if str(min(ts_list))[:10] != str(max(ts_list))[:10] else str(min(ts_list))[:10]
                    else:
                        period = datetime.now(timezone.utc).date().isoformat()

                    ev_bytes = len(json.dumps(events, default=str).encode("utf-8"))
                    rep = {
                        "id": "rep-audit-digest",
                        "reportId": "rep-audit-digest",
                        "title": "Core Security & Governance Audit Digest",
                        "category": "AUDIT_EVIDENCE",
                        "period": period,
                        "generatedAt": datetime.now(timezone.utc).isoformat(),
                        "fileSize": _format_file_size(ev_bytes),
                        "format": "JSON",
                        "status": "AVAILABLE",
                        "summary": f"Recorded {len(events)} security and governance events in immutable core audit store.",
                        "provenance": "AUDIT_STORE",
                        "data": {"events": events},
                    }
                    reports.append(_sanitize_report_for_client(rep, is_owner=is_owner))
            except Exception as exc:
                logger.warning("Error querying audit events for reports: %s", exc)

        return reports

    @app.get("/api/v1/reports")
    def list_user_reports(session=Depends(session_from_header)) -> list[dict[str, Any]]:
        """List authoritative reports for the calling user."""
        return _build_authoritative_reports(user_id=str(session.user.user_id), is_owner=(session.user.role == Role.OWNER))

    @app.get("/api/v1/owner/reports")
    def list_owner_reports(session=Depends(owner_session)) -> list[dict[str, Any]]:
        """List system-wide authoritative reports for Owner oversight."""
        return _build_authoritative_reports(user_id=None, is_owner=True)

    @app.get("/api/v1/reports/{report_id}")
    def get_report(report_id: str, session=Depends(session_from_header)) -> dict[str, Any]:
        """Fetch a specific authoritative report."""
        is_owner = (session.user.role == Role.OWNER)
        user_id = None if is_owner else str(session.user.user_id)
        reports = _build_authoritative_reports(user_id=user_id, is_owner=is_owner)
        found = next((r for r in reports if r["id"] == report_id or r.get("reportId") == report_id), None)
        if not found:
            raise HTTPException(status_code=404, detail=f"Report '{report_id}' not found")
        return found

    return app


def _create_unconfigured_sentinel_app() -> FastAPI:
    sentinel = FastAPI(
        title="SentinelX — Unconfigured Direct API Entrypoint",
        description="Direct invocation of dashboard.backend.api:app is not an authoritative SentinelX runtime. "
                    "Use dashboard.runtime.application.create_runtime_app or dashboard.backend.dev_app.",
    )

    @sentinel.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
    def unconfigured_catchall(path: str):
        raise HTTPException(
            status_code=503,
            detail={
                "error": "UNCONFIGURED_ENTRYPOINT",
                "message": "dashboard.backend.api:app is not a runnable SentinelX server. "
                           "Production runtime must use create_runtime_app via RuntimeController. "
                           "Development must use dashboard.backend.dev_app.",
                "state": "UNCONFIGURED",
                "authority_ready": False,
            },
        )

    return sentinel


app = _create_unconfigured_sentinel_app()
