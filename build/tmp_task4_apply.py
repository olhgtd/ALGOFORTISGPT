from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"anchor not found in {path}: {old[:140]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


step = Path("dashboard/backend/owner_admin/step_up.py")
anchor = '    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/backtests/(?P<resource>[^/]+)/cancel$"), "BACKTEST_ADMIN"),\n'
insert = '    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/paper/sessions/(?P<resource>[^/]+)/release-hold$"), "PAPER_HOLD_RELEASE"),\n' + anchor
replace_once(step, anchor, insert)

api = Path("dashboard/backend/api.py")
hold_anchor = '''        updated = app.state.paper_service.set_session_hold(
            session_id,
            hold=body.hold,
            reason=body.reason or ("Owner hold applied" if body.hold else "Owner hold released"),
        )'''
hold_replacement = '''        if not body.hold:
            raise HTTPException(status_code=409, detail="Use protected release-hold authority to reduce Owner Paper restriction")
        updated = app.state.paper_service.set_session_hold(
            session_id,
            hold=True,
            reason=body.reason or "Owner hold applied",
        )'''
replace_once(api, hold_anchor, hold_replacement)

readiness_anchor = '    # ── P1-A (R-03): strategy readiness authority ──\n'
release_route = '''    @app.post("/api/v1/owner/paper/sessions/{session_id}/release-hold")
    def release_owner_paper_session_hold(
        session_id: str,
        body: ActionNotesRequest = ActionNotesRequest(),
        session=Depends(owner_mutable_session),
    ) -> dict[str, Any]:
        """Reduce an Owner Paper restriction only through fresh step-up authority."""
        if app.state.security_store is None or app.state.paper_service is None:
            raise HTTPException(status_code=503, detail="Paper service unavailable")
        updated = app.state.paper_service.set_session_hold(
            session_id,
            hold=False,
            reason=body.notes or "Owner verified hold release",
        )
        if not updated:
            raise HTTPException(status_code=404, detail=f"Paper session '{session_id}' not found")
        _record_security_audit(
            event_type="PAPER_SESSION_HOLD_RELEASED",
            actor_id=session.user.user_id,
            details={"session_id": session_id, "reason": body.notes},
        )
        return {"success": True, "session_id": session_id, "hold": False}

'''
replace_once(api, readiness_anchor, release_route + readiness_anchor)

shell = Path("dashboard/owner-dashboard/OwnerDashboardApp.tsx")
replace_once(shell, '  OwnerPaperScreen,\n', '')
replace_once(
    shell,
    'import { ResearchOperations } from "./authoritative/ResearchOperations";\n',
    'import { ResearchOperations } from "./authoritative/ResearchOperations";\nimport { PaperOperations } from "./authoritative/PaperOperations";\n',
)
replace_once(shell, '      case "paper": return <OwnerPaperScreen />;\n', '      case "paper": return <PaperOperations />;\n')
