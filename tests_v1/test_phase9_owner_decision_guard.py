from pathlib import Path

REGISTER = Path("ALGOFORTIS_V2_OWNER_DECISIONS.md")


def test_od_v2_25_is_frozen_for_phase9_with_legal_review_gate():
    text = REGISTER.read_text(encoding="utf-8")
    section = text.split("**OD-V2-25 — Data-protection (DPDP) and retention**", 1)[1]
    section = section.split("**OD-V2-26", 1)[0] if "**OD-V2-26" in section else section
    assert "*Status:* **FROZEN**" in section
    assert "PHASE9_DPDP_DECISION_FREEZE.md" in section
    assert "legal" in section.lower() and "G9" in section
    assert "READ_ONLY / DISARMED" in section


def test_phase9_blocking_matrix_is_frozen_on_2026_09_27():
    text = REGISTER.read_text(encoding="utf-8")
    phase9_rows = [line for line in text.splitlines() if "| Phase 9 |" in line]
    assert phase9_rows, "Phase 9 blocking row is missing"
    row = phase9_rows[0]
    assert "| Phase 9 | 25 —" in row
    assert "FROZEN" in row
    assert "2026-09-27" in row
    assert "legal review" in row.lower()
