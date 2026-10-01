from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _decision_block(text: str, heading: str) -> str:
    start = text.index(heading)
    next_heading = text.find("\n**OD-V2-", start + len(heading))
    if next_heading == -1:
        next_heading = len(text)
    return text[start:next_heading]


def test_owner_decision_register_freezes_ai_scope_and_data_rules() -> None:
    text = (ROOT / "ALGOFORTIS_V2_OWNER_DECISIONS.md").read_text(encoding="utf-8")
    od15 = _decision_block(text, "**OD-V2-15 — AI scope and provider set for V2.0**")
    od16 = _decision_block(text, "**OD-V2-16 — AI data-sharing rules**")

    assert "*Status:* **FROZEN**" in od15
    assert "0..N" in od15
    assert "Strategy" in od15 and "Laya" in od15
    assert "*Status:* **FROZEN**" in od16
    assert "Strategy Hunting" in od16
    assert "provenance" in od16.lower() and "licensing" in od16.lower()


def test_phase8_freeze_preserves_existing_authorities_and_live_disarmed() -> None:
    text = (ROOT / "docs/v2/phase8/PHASE8_DECISION_FREEZE.md").read_text(encoding="utf-8")
    assert "RiskGateV2" in text
    assert "engine/portfolio/" in text or "Portfolio/accounting" in text
    assert "S2" in text and "DeviceSession" in text
    assert "Owner/Admin" in text
    assert "READ_ONLY / DISARMED" in text
    assert "does **not** authorize real-money broker mutation" in text


def test_static_boundary_checker_rejects_parallel_authorities() -> None:
    checker = ROOT / "build/tools/check_ai_decision_intelligence_boundary.py"
    assert checker.exists(), "AI decision-intelligence static boundary checker must exist"

    spec = importlib.util.spec_from_file_location("ai_boundary", checker)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    violations = module.scan_text(
        "engine/ai/parallel_authority.py",
        """
class AIRiskGateV2: pass
class AIAccountingLedger: pass
class AISessionAuthority: pass
class AIAdminAuthority: pass

def mint_approved_order():
    return ApprovedOrder()
""",
    )
    joined = "\n".join(violations)
    assert "parallel risk" in joined.lower()
    assert "parallel accounting" in joined.lower()
    assert "parallel identity" in joined.lower()
    assert "parallel admin" in joined.lower()
    assert "ApprovedOrder" in joined


def test_static_boundary_checker_allows_reused_authorities() -> None:
    checker = ROOT / "build/tools/check_ai_decision_intelligence_boundary.py"
    assert checker.exists(), "AI decision-intelligence static boundary checker must exist"
    spec = importlib.util.spec_from_file_location("ai_boundary", checker)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    text = """
from engine.risk.gate_v2 import RiskGateV2
from engine.portfolio.accounting import PortfolioAccounting
from dashboard.backend.account_v2.gate import DeviceSessionGate
OWNER_SURFACE = 'dashboard/owner-dashboard/authoritative/AIControlCenter.tsx'
LIVE_STATE = 'READ_ONLY/DISARMED'
"""
    assert module.scan_text("engine/ai/authority_reuse.py", text) == []
