from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_g9_requires_frozen_owner_decision_and_separate_legal_status():
    register = read("ALGOFORTIS_V2_OWNER_DECISIONS.md")
    section = register.split("**OD-V2-25 — Data-protection (DPDP) and retention**", 1)[1].split("**OD-V2-26", 1)[0]
    assert "*Status:* **FROZEN**" in section
    assert "PHASE9_DPDP_DECISION_FREEZE.md" in section
    assert "qualified legal adviser" in section

    legal = read("docs/v2/phase9/G9_LEGAL_REVIEW_STATUS.md")
    assert "PENDING_EXTERNAL_REVIEW" in legal
    assert "software test result is evidence of legal compliance" in legal
    assert "COMPLIANT" not in legal


def test_g9_workflow_preserves_full_stack_and_dashboard_qualification():
    workflow = read(".github/workflows/v2-phase9-product-ops.yml")
    for marker in (
        "windows-latest",
        "windows-2022",
        "python -m pytest tests_v1 -q",
        "check_phase5_paper_recovery.py",
        "check_phase6_live_readonly.py",
        "check_phase7_portfolio_risk.py",
        "check_phase8_ai_shadow.py",
        "check_phase9_product_ops.py",
        "npm run typecheck",
        "npm run build",
        "test:user-dashboard",
        "G9_CROSS_WINDOWS_COMPARE=PASS",
    ):
        assert marker in workflow


def test_g9_probe_keeps_trading_and_legal_authority_separate():
    evidence = read("dashboard/backend/product_ops_v2/evidence.py")
    assert "('APPROVED_ORDER_AUTHORITY','RISK_GATE_V2_ONLY')" in evidence
    assert "('LIVE_STATE','READ_ONLY/DISARMED')" in evidence
    assert "('SOFTWARE_TESTS_PROVE_LEGAL_COMPLIANCE','NO')" in evidence
    assert "G9_ENABLES_REAL_MONEY_" in evidence


def test_phase9_firewall_covers_backend_and_new_read_model_clients():
    guard = read("build/tools/check_phase9_product_ops.py")
    for path in (
        "productOps.ts",
        "ProductOperationsScreen.tsx",
        "privacy.ts",
        "PrivacyAndRequestsScreen.tsx",
    ):
        assert path in guard
    assert "PHASE9_UI_AUTHORITY=READ_MODEL_ONLY" in guard
