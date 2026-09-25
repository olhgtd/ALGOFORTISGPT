from __future__ import annotations

from build.tools.laya_probe import run


def test_laya_probe_is_deterministic_and_non_executable():
    first = run()
    second = run()
    assert first == second
    assert first["OPPORTUNITY_STATUS"] == "CANDIDATE_ONLY"
    assert first["STRATEGY_SIGNAL_COUNT"] == "0"
    assert first["DEFAULT_LIVE_STATE"] == "READ_ONLY/DISARMED"
