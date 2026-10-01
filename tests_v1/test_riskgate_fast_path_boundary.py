from __future__ import annotations

from pathlib import Path

from build.tools.check_riskgate_fast_path_boundary import check_repository, check_source_text


def test_guard_rejects_broker_import_and_mutation_tokens() -> None:
    source = """
from engine.broker_adapters.angel_adapter import AngelAdapter

def run():
    place_order()
"""
    failures = check_source_text("engine/risk/fast_path_v2.py", source)
    assert any("forbidden broker" in item for item in failures)
    assert any("forbidden mutation" in item for item in failures)


def test_guard_rejects_direct_approved_order_mint() -> None:
    failures = check_source_text(
        "engine/risk/fast_path_v2.py",
        "def approve():\n    return _mint_approved_order()\n",
    )
    assert any("direct ApprovedOrder mint" in item for item in failures)


def test_guard_rejects_live_arm_and_ai_approval_authority() -> None:
    failures = check_source_text(
        "engine/risk/snapshot_builder_v2.py",
        "from engine.ai.orchestrator import Prime\n\ndef run():\n    arm_live()\n",
    )
    assert any("AI/Laya authority" in item for item in failures)
    assert any("Live mutation" in item for item in failures)


def test_guard_rejects_hardcoded_latency_policy_literal_outside_policy_contract() -> None:
    failures = check_source_text(
        "engine/risk/fast_path_v2.py",
        "policy = RiskGateLatencyPolicy(ceiling_ns=1000000)\n",
    )
    assert any("hardcoded latency" in item for item in failures)


def test_guard_rejects_parallel_incident_or_alert_authority() -> None:
    source = "class RiskIncidentStore: pass\nclass RiskAlertDispatcher: pass\n"
    failures = check_source_text("engine/risk/snapshot_health_v2.py", source)
    assert any("parallel safety authority" in item for item in failures)


def test_current_fast_path_tree_passes_boundary_guard() -> None:
    assert check_repository(Path(".")) == []
