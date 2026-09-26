from __future__ import annotations

from pathlib import Path


WORKFLOW = Path(".github/workflows/v2-phase0-baseline.yml")


def test_gp_s2_is_wired_on_both_windows_jobs_and_cross_compared() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert text.count("S2 account gate static policy") == 2
    assert text.count("S2 focused validation") == 2
    assert "S2 deterministic fingerprint probe A" in text
    assert "S2 deterministic fingerprint probe B" in text
    assert "name: s2-fingerprint-a" in text
    assert "name: s2-fingerprint-b" in text
    assert "GP-S2 cross-Windows deterministic fingerprint comparison" in text
    assert "GP-S2 cross-Windows fingerprint mismatch" in text
    assert "SESSION_REPLAY_RESULT=FAMILY_REVOKED" in text
    assert "OUTAGE_RUNTIME_MODE=LOCAL_SAFETY_ONLY" in text
    assert "LIVE_STATE=READ_ONLY/DISARMED" in text
    assert "BROKER_MUTATION_CAPABILITY=ABSENT" in text
    assert "runs-on: windows-latest" in text
    assert "runs-on: windows-2022" in text
