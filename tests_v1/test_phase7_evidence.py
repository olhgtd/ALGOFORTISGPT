import re


def test_g7_evidence_contains_all_locked_authority_and_safety_markers() -> None:
    from engine.portfolio.v2.evidence import build_g7_evidence

    evidence = build_g7_evidence()
    markers = dict(item.split("=", 1) for item in evidence.markers)
    assert markers["APPROVED_ORDER_AUTHORITY"] == "RISK_GATE_V2_ONLY"
    assert markers["PORTFOLIO_BUDGETS"] == "VERSIONED_EXPLICIT"
    assert markers["CAPITAL_RESERVATION"] == "ATOMIC_FAIL_CLOSED"
    assert markers["PORTFOLIO_EXPOSURE"] == "THROUGH_RISK_GATE"
    assert markers["CIRCUIT_BREAKER"] == "STICKY_ENTRY_POLICY"
    assert markers["EVENT_RISK"] == "SCHEDULED_VERSIONED_NO_SILENT_RESIZE"
    assert markers["LIVE_STATE"] == "READ_ONLY/DISARMED"
    assert markers["G7_ENABLES_REAL_MONEY_TRADING"] == "NO"


def test_g7_fingerprint_is_deterministic_hex_and_rendered() -> None:
    from engine.portfolio.v2.evidence import build_g7_evidence, render_g7_evidence

    first = build_g7_evidence()
    second = build_g7_evidence()
    assert first.fingerprint == second.fingerprint
    assert re.fullmatch(r"[0-9a-f]{64}", first.fingerprint)
    rendered = render_g7_evidence()
    assert f"FINGERPRINT={first.fingerprint}" in rendered
    for marker in first.markers:
        assert marker in rendered
