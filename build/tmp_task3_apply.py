from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"anchor not found in {path}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# Step-up bindings for cross-user administrative cancellation.
step = Path("dashboard/backend/owner_admin/step_up.py")
anchor = '    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/connections/(?P<resource>[^/]+)/(?:allowance|capabilities/[^/]+/allowance)$"), "CONNECTION_GOVERNANCE"),\n'
insert = (
    '    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/backtests/(?P<resource>[^/]+)/cancel$"), "BACKTEST_ADMIN"),\n'
    '    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/walkforward/jobs/(?P<resource>[^/]+)/cancel$"), "WALKFORWARD_ADMIN"),\n'
    + anchor
)
replace_once(step, anchor, insert)

# Narrow Owner cancel adapters over existing services. No engine logic is duplicated.
api = Path("dashboard/backend/api.py")
backtest_anchor = '    @app.post("/api/v1/walkforward/jobs", status_code=202)\n'
backtest_route = '''    @app.post("/api/v1/owner/backtests/{run_id}/cancel")
    def cancel_owner_backtest_run(
        run_id: str,
        session=Depends(owner_mutable_session),
    ) -> dict[str, Any]:
        """Owner administrative cancellation over the canonical Backtest service."""
        service = app.state.backtest_service
        if service is None:
            raise HTTPException(status_code=503, detail="Backtest service unavailable")
        try:
            cancelled = service.cancel_run(run_id, user_id=None)
        except Exception as exc:
            logger.exception("Owner backtest cancellation failed")
            raise HTTPException(status_code=422, detail="BACKTEST_CANCEL_REJECTED") from exc
        if not cancelled:
            raise HTTPException(status_code=404, detail=f"Backtest run '{run_id}' not found or not cancellable")
        _record_security_audit(
            event_type="OWNER_BACKTEST_CANCELLED",
            actor_id=session.user.user_id,
            details={"run_id": run_id},
        )
        return {"success": True, "run_id": run_id, "cancel_requested": True}

'''
replace_once(api, backtest_anchor, backtest_route + backtest_anchor)

wfo_anchor = '    @app.get("/api/v1/owner/walkforward/jobs")\n'
wfo_route = '''    @app.post("/api/v1/owner/walkforward/jobs/{job_id}/cancel")
    def cancel_owner_walkforward_job(
        job_id: str,
        session=Depends(owner_mutable_session),
    ) -> dict[str, Any]:
        """Owner administrative cancellation over the canonical Walk-Forward service."""
        service = _walkforward_authority()
        try:
            job = service.cancel_job(job_id, None)
        except (WalkForwardError, SecurityStoreError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if job is None:
            raise HTTPException(status_code=404, detail=f"Walk-forward job '{job_id}' not found")
        _record_security_audit(
            event_type="OWNER_WALKFORWARD_CANCELLED",
            actor_id=session.user.user_id,
            details={"job_id": job_id},
        )
        return {"success": True, "job_id": job_id, "cancel_requested": True, "job": job}

'''
replace_once(api, wfo_anchor, wfo_route + wfo_anchor)

# Canonical Owner navigation: replace legacy Backtests oversight with Research Operations.
shell = Path("dashboard/owner-dashboard/OwnerDashboardApp.tsx")
replace_once(shell, '  OwnerBacktestsScreen,\n', '')
replace_once(
    shell,
    'import { ProductOperationsScreen } from "./authoritative/ProductOperationsScreen";\n',
    'import { ProductOperationsScreen } from "./authoritative/ProductOperationsScreen";\nimport { ResearchOperations } from "./authoritative/ResearchOperations";\n',
)
replace_once(
    shell,
    '      { id: "backtests", label: "Backtests Oversight", icon: "play" },\n',
    '      { id: "research", label: "Backtests / Walk-Forward", icon: "play" },\n',
)
replace_once(shell, '      case "backtests": return <OwnerBacktestsScreen />;\n', '      case "research": return <ResearchOperations />;\n')
replace_once(
    shell,
    '["control", "portfolio-oversight", "ai-control", "users", "product-operations"].includes(screen)',
    '["control", "portfolio-oversight", "ai-control", "users", "product-operations", "research"].includes(screen)',
)
