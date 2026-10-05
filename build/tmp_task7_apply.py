from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"anchor not found in {path}: {old[:140]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

api = Path("dashboard/backend/api.py")
replace_once(api, 'from .auth_policy import AuthPolicyManager\n', 'from .auth_policy import AuthPolicyManager\nfrom .owner_safety_adapter import OwnerSafetyAdapter\n')
anchor = '    @app.get("/api/v1/owner/live-readiness")\n'
routes = '''    def _owner_safety_adapter() -> OwnerSafetyAdapter:
        return OwnerSafetyAdapter(
            security_store=app.state.security_store,
            safe_mode=app.state.safe_mode,
            live_readiness_service=app.state.live_readiness_service,
        )

    @app.get("/api/v1/owner/safety")
    def owner_safety_snapshot(session=Depends(owner_session)) -> dict[str, Any]:
        return _owner_safety_adapter().snapshot()

    @app.post("/api/v1/owner/safety/safe-mode/engage")
    def engage_owner_safe_mode(session=Depends(owner_mutable_session)) -> dict[str, Any]:
        result = _owner_safety_adapter().engage_safe_mode()
        _record_security_audit(event_type="OWNER_SAFE_MODE_ENGAGED", actor_id=session.user.user_id, details={})
        return result

    @app.post("/api/v1/owner/safety/global-hold/engage")
    def engage_owner_global_hold(session=Depends(owner_mutable_session)) -> dict[str, Any]:
        try:
            result = _owner_safety_adapter().engage_global_hold(str(session.user.user_id))
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        _record_security_audit(event_type="OWNER_GLOBAL_HOLD_ENGAGED", actor_id=session.user.user_id, details={})
        return result

    @app.post("/api/v1/owner/safety/global-hold/release")
    def release_owner_global_hold(session=Depends(owner_mutable_session)) -> dict[str, Any]:
        try:
            result = _owner_safety_adapter().release_global_hold(str(session.user.user_id))
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        _record_security_audit(event_type="OWNER_GLOBAL_HOLD_RELEASED", actor_id=session.user.user_id, details={})
        return result

'''
replace_once(api, anchor, routes + anchor)

step = Path("dashboard/backend/owner_admin/step_up.py")
anchor = '    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/historical/gaps/repair$"), "HISTORICAL_DATA_REPAIR", None),\n'
replace_once(step, anchor, anchor + '    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/safety/global-hold/release$"), "SAFETY_RELEASE", None),\n')

shell = Path("dashboard/owner-dashboard/OwnerDashboardApp.tsx")
replace_once(shell, 'import { DataOperations } from "./authoritative/DataOperations";\n', 'import { DataOperations } from "./authoritative/DataOperations";\nimport { RiskSafetyScreen } from "./authoritative/RiskSafetyScreen";\n')
replace_once(shell, '    label: "AI",\n', '    label: "SAFETY & INTELLIGENCE",\n')
replace_once(shell, '    items: [\n      { id: "ai-control", label: "AI Control Center", icon: "activity", badge: "Decision Intel", badgeTone: "dim" },\n', '    items: [\n      { id: "risk-safety", label: "Risk & Safety", icon: "shield", badge: "Live disarmed", badgeTone: "warn" },\n      { id: "ai-control", label: "AI Control Center", icon: "activity", badge: "Decision Intel", badgeTone: "dim" },\n')
replace_once(shell, '      case "ai-control": return <OwnerAIControlScreen />;\n', '      case "risk-safety": return <RiskSafetyScreen />;\n      case "ai-control": return <OwnerAIControlScreen />;\n')
