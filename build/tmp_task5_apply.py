from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"anchor not found in {path}: {old[:140]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

step = Path("dashboard/backend/owner_admin/step_up.py")
anchor = '    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/paper/sessions/(?P<resource>[^/]+)/release-hold$"), "PAPER_HOLD_RELEASE"),\n'
replace_once(step, anchor, anchor + '    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/deployments/(?P<resource>[^/]+)/(?:resume|stop)$"), "DEPLOYMENT_CONTROL"),\n')

api = Path("dashboard/backend/api.py")
anchor = '    @app.post("/api/v1/user/deployments")\n'
routes = '''    @app.get("/api/v1/owner/deployments")
    def list_owner_deployments(
        limit: int = Query(default=200, ge=1, le=500),
        status: str | None = None,
        session=Depends(owner_session),
    ) -> dict[str, Any]:
        service = _deployment_authority()
        rows = service.list_deployments(None, status=status)
        return {"deployments": rows[:limit], "total_count": len(rows), "source": "BACKEND"}

    @app.get("/api/v1/owner/deployments/recovery")
    def owner_deployment_recovery(session=Depends(owner_session)) -> dict[str, Any]:
        service = _deployment_authority()
        return service.recovery_snapshot(None)

    @app.post("/api/v1/owner/deployments/{deployment_id}/pause")
    def pause_owner_deployment(deployment_id: str, session=Depends(owner_mutable_session)) -> dict[str, Any]:
        service = _deployment_authority()
        actor = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            deployment = service.pause_deployment(deployment_id, None, actor=actor)
        except DeploymentError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _record_security_audit(event_type="OWNER_DEPLOYMENT_PAUSED", actor_id=session.user.user_id, details={"deployment_id": deployment_id})
        return {"success": True, "deployment": deployment}

    @app.post("/api/v1/owner/deployments/{deployment_id}/resume")
    def resume_owner_deployment(deployment_id: str, session=Depends(owner_mutable_session)) -> dict[str, Any]:
        service = _deployment_authority()
        actor = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            deployment = service.resume_deployment(deployment_id, None, actor=actor)
        except DeploymentError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _record_security_audit(event_type="OWNER_DEPLOYMENT_RESUMED", actor_id=session.user.user_id, details={"deployment_id": deployment_id})
        return {"success": True, "deployment": deployment}

    @app.post("/api/v1/owner/deployments/{deployment_id}/stop")
    def stop_owner_deployment(deployment_id: str, session=Depends(owner_mutable_session)) -> dict[str, Any]:
        service = _deployment_authority()
        actor = f"OWNER-{str(session.user.user_id)[:4]}"
        try:
            deployment = service.stop_deployment(deployment_id, None, actor=actor)
        except DeploymentError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _record_security_audit(event_type="OWNER_DEPLOYMENT_STOPPED", actor_id=session.user.user_id, details={"deployment_id": deployment_id})
        return {"success": True, "deployment": deployment}

'''
replace_once(api, anchor, routes + anchor)

shell = Path("dashboard/owner-dashboard/OwnerDashboardApp.tsx")
replace_once(shell, 'import { PaperOperations } from "./authoritative/PaperOperations";\n', 'import { PaperOperations } from "./authoritative/PaperOperations";\nimport { DeploymentOperations } from "./authoritative/DeploymentOperations";\n')
replace_once(shell, '      { id: "paper", label: "Paper Sessions", icon: "layers" },\n', '      { id: "paper", label: "Paper Trading", icon: "layers" },\n      { id: "deployments", label: "Deployments", icon: "activity" },\n')
replace_once(shell, '      case "paper": return <PaperOperations />;\n', '      case "paper": return <PaperOperations />;\n      case "deployments": return <DeploymentOperations />;\n')
