"""Compose existing authorities for a private, same-origin product runtime."""
from contextlib import asynccontextmanager
from decimal import Decimal
import os
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from engine.persistence.sqlite_store import SQLitePaperStateStore
from dashboard.backend.adapters import HistoricalFeedChartAuthority
from dashboard.backend.api import create_app
from dashboard.backend.backtest_service import BacktestService
from dashboard.backend.historical_data_service import (
    HistoricalDataService,
    LocalImportDataProvider,
)
from dashboard.backend.paper_service import PaperService
from dashboard.backend.core_audit import MandatoryCoreSecurityAudit
from dashboard.backend.security_store import SQLiteSecurityStore
from dashboard.backend.governance_store import SQLiteGovernanceStore
from dashboard.backend.security import SecurityConfiguration, WebAuthnCeremonyService, WebAuthnRelyingParty
from dashboard.backend.identity import local_owner, UnavailableRoamingIdentity
from dashboard.backend.account_v2.owner_bootstrap import resolve_owner_bootstrap
from dashboard.backend.owner_admin.router import attach_owner_admin_control_plane
from dashboard.backend.owner_admin.inspection_router import attach_owner_user_inspection
from dashboard.backend.owner_admin.ai_verification_router import attach_ai_verification_routes
from .paths import RuntimeMode, CurrentUserAcl


_OWNER_BOOTSTRAP_MUTATIONS = frozenset({
    "/api/v1/auth/local/setup",
    "/api/v1/auth/webauthn/bootstrap-registration/options",
    "/api/v1/auth/webauthn/bootstrap-registration/complete",
})


def create_runtime_app(paths, origin: str, instance_id: str):
    if not (paths.frontend / "index.html").is_file():
        raise RuntimeError("Built AlgoFortis frontend resources are unavailable")
    profile = paths.mode.value.lower()
    options = dict(profile=profile, data_root=paths.databases, windows_acl_validator=CurrentUserAcl())
    security = SQLiteSecurityStore(paths.databases / "security" / "sentinelx_security.sqlite3", seed_governance=False, **options)
    governance = SQLiteGovernanceStore(paths.databases / "governance" / "sentinelx_governance.sqlite3", **options)
    core = SQLitePaperStateStore(paths.databases / "core-audit.sqlite3", account_id="sentinelx-local",
                                starting_capital=Decimal("0.00"), audit_source_identity="sentinelx-local")
    owner = local_owner(security, paths.config / "identity.json")
    normal_rp_id = os.environ.get("ALGOFORTIS_WEBAUTHN_RP_ID", os.environ.get("SENTINELX_WEBAUTHN_RP_ID", "algofortis.com")).strip()
    normal_origin = os.environ.get("ALGOFORTIS_WEBAUTHN_ORIGIN", os.environ.get("SENTINELX_WEBAUTHN_ORIGIN", f"https://app.{normal_rp_id}")).strip()
    recovery_rp_id = os.environ.get("ALGOFORTIS_WEBAUTHN_RECOVERY_RP_ID", os.environ.get("SENTINELX_WEBAUTHN_RECOVERY_RP_ID", "algofortis-recovery.com")).strip()
    recovery_origin = os.environ.get("ALGOFORTIS_WEBAUTHN_RECOVERY_ORIGIN", os.environ.get("SENTINELX_WEBAUTHN_RECOVERY_ORIGIN", f"https://access.{recovery_rp_id}")).strip()

    ceremonies = WebAuthnCeremonyService(
        store=security,
        normal_rp=WebAuthnRelyingParty(normal_rp_id, normal_origin) if paths.mode is RuntimeMode.PRODUCTION
        else WebAuthnRelyingParty("localhost", origin, development_only=True),
        recovery_rp=WebAuthnRelyingParty(recovery_rp_id, recovery_origin) if paths.mode is RuntimeMode.PRODUCTION else None,
    )
    market_data = HistoricalDataService(
        paths.cache / "market-data",
        imports_root=paths.imports,
        security_store=security,
    )
    local_import_path = os.environ.get("ALGOFORTIS_LOCAL_IMPORT_PATH", os.environ.get("SENTINELX_LOCAL_IMPORT_PATH", "")).strip()
    if local_import_path:
        candidate = Path(local_import_path)
        if candidate.is_file():
            market_data.set_provider(LocalImportDataProvider(source_path=candidate))
    app = create_app(owner=owner, config=SecurityConfiguration(normal_mtls_required=paths.mode is RuntimeMode.PRODUCTION),
                     security_store=security, governance_store=governance, webauthn_ceremonies=ceremonies,
                     core_security_audit=MandatoryCoreSecurityAudit(audit_store=core, security_store=security),
                     backtest_service=BacktestService(security, feed=market_data),
                     paper_service=PaperService(security, governance_store=governance, artifact_root=paths.artifacts, feed=market_data, dataset_feed=market_data),
                     chart_authority=HistoricalFeedChartAuthority(
                         feed=market_data, source_identity="algofortis-canonical-cache"),
                     historical_data_service=market_data,
                     artifact_root=paths.artifacts)
    # Additive Owner/Admin + AI authority layer. It hardens legacy destructive
    # Owner routes with fresh WebAuthn step-up and exposes backend-only Owner/AI
    # read models. It has no broker mutation or Live-arm authority.
    attach_owner_admin_control_plane(app)
    attach_owner_user_inspection(app)
    attach_ai_verification_routes(app)
    app.state.roaming_identity = UnavailableRoamingIdentity()

    def owner_bootstrap_decision():
        """Never infer global Owner absence from an empty local database."""
        return resolve_owner_bootstrap(
            local_owner_initialized=security.has_initialized_owner(),
            roaming_identity_configured=bool(getattr(app.state.roaming_identity, "configured", False)),
            explicit_trusted_local_bootstrap=(
                os.environ.get("ALGOFORTIS_ALLOW_LOCAL_OWNER_BOOTSTRAP", "").strip() == "1"
            ),
            production=paths.mode is RuntimeMode.PRODUCTION,
        )

    app.state.owner_bootstrap_decision = owner_bootstrap_decision

    backtest_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(_app):
        try:
            async with backtest_lifespan(_app):
                yield
        finally:
            security.close()
            governance.close()
            core.close()
    app.router.lifespan_context = lifespan

    @app.middleware("http")
    async def owner_bootstrap_firewall(request: Request, call_next):
        # Every Owner-provisioning mutation is denied unless an explicit trusted
        # authority allows setup. Empty local state alone is never sufficient.
        if request.method.upper() == "POST" and request.url.path in _OWNER_BOOTSTRAP_MUTATIONS:
            decision = owner_bootstrap_decision()
            if not decision.setup_allowed:
                return JSONResponse(
                    {
                        "detail": "OWNER_SETUP_NOT_AUTHORIZED",
                        **decision.public_dict(),
                    },
                    status_code=403,
                )
        return await call_next(request)

    @app.middleware("http")
    async def private_origin(request: Request, call_next):
        # Reject DNS rebinding and cross-origin mutation; no permissive CORS.
        if request.headers.get("host") != origin.removeprefix("http://"):
            return JSONResponse({"detail": "Unrecognized runtime host"}, status_code=403)
        if request.headers.get("origin") not in (None, origin):
            return JSONResponse({"detail": "Unrecognized runtime origin"}, status_code=403)
        if paths.mode is RuntimeMode.PRODUCTION and request.url.path.startswith("/api/v1/auth/webauthn/"):
            return JSONResponse({"detail": "Approved HTTPS identity transport is not configured for this local installation"}, status_code=503)
        return await call_next(request)

    @app.get("/api/v1/identity/bootstrap-status")
    def identity_bootstrap_status():
        return owner_bootstrap_decision().public_dict()

    @app.get("/api/v1/runtime/status")
    def runtime_status():
        try:
            security._conn.execute("SELECT COUNT(*) FROM users").fetchone()
            governance._conn.execute("SELECT 1").fetchone()
            app.state.security_status.public_status(owner.user_id)
        except Exception:
            return JSONResponse({"state": "UNAVAILABLE", "instance_id": instance_id}, status_code=503)
        identity_type = "LOCAL_PRIVATE" if paths.mode is RuntimeMode.LOCAL_PRIVATE else "LOCAL_WEBAUTHN"
        device_authority = "LOCAL_AUTHORITY" if paths.mode is RuntimeMode.LOCAL_PRIVATE else "WEBAUTHN_CREDENTIAL"
        bootstrap = owner_bootstrap_decision()
        return {"state": "READY", "mode": paths.mode.value, "instance_id": instance_id,
                "api_base": "/api/v1", "identity": identity_type,
                "roaming_identity": "CONFIGURED" if getattr(app.state.roaming_identity, "configured", False) else "UNAVAILABLE",
                "device_authority": device_authority,
                "local_auth_transport": "UNAVAILABLE" if paths.mode is RuntimeMode.PRODUCTION else "CONFIGURED",
                "owner_presence": bootstrap.presence.value,
                "owner_setup_allowed": bootstrap.setup_allowed,
                "owner_entry_flow": bootstrap.flow.value,
                "live_execution": "DISARMED"}

    @app.post("/api/v1/identity/roaming/verify")
    def roaming_verify():
        return JSONResponse({"detail": "Cross-PC identity authority is not configured"}, status_code=503)

    @app.get("/")
    @app.get("/index.html")
    def product_index():
        html = (paths.frontend / "index.html").read_text(encoding="utf-8")
        marker = f'<meta name="algofortis-runtime" content="{paths.mode.value}"><meta name="sentinelx-runtime" content="{paths.mode.value}">'
        return HTMLResponse(html.replace("<head>", "<head>" + marker, 1), headers={"Cache-Control": "no-store"})

    # API routes precede immutable static assets; the API client keeps /api/v1.
    app.mount("/", StaticFiles(directory=paths.frontend, html=True), name="product")
    return app
