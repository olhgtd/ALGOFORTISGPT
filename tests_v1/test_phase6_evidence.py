from __future__ import annotations

from engine.live.phase6_evidence import build_g6_evidence, render_g6_evidence


def test_g6_evidence_contains_all_locked_markers_and_stable_fingerprint() -> None:
    a = build_g6_evidence()
    b = build_g6_evidence()
    required = {
        "BROKER_BOUNDARY=V2_ISOLATED_READ_ONLY",
        "RECONCILIATION_AUTHORITY=LIVE_RECONCILER",
        "FOREIGN_ACTIVITY_INCIDENT_MODEL=PHASE5_SHARED",
        "LIVE_STATE=READ_ONLY/DISARMED",
        "REAL_BROKER_MUTATION_CAPABILITY=ABSENT",
        "G6_ENABLES_REAL_MONEY_TRADING=NO",
    }
    assert required.issubset(set(a.markers))
    assert a.fingerprint == b.fingerprint
    assert len(a.fingerprint) == 64


def test_evidence_render_is_deterministic_and_contains_no_secret_fields() -> None:
    text = render_g6_evidence(build_g6_evidence())
    assert text == render_g6_evidence(build_g6_evidence())
    assert "FINGERPRINT=" in text
    lowered = text.lower()
    for token in ("access_token", "refresh_token", "api_key", "password", "account_id"):
        assert token not in lowered
