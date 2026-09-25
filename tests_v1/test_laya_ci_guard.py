from __future__ import annotations

from build.tools.check_phase4_research_backtest import REQUIRED, verify


def test_laya_scope_rejects_broker_live_order_and_network_imports(tmp_path):
    samples = {
        "broker.py": "from engine.broker_adapters import mock_broker\n",
        "live.py": "from engine.live import state\n",
        "orders.py": "from engine.orders import lifecycle\n",
        "network.py": "import httpx\n",
    }
    for name, source in samples.items():
        file = tmp_path / "engine" / "ai" / "laya" / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(source, encoding="utf-8")
    issues = verify(tmp_path, check_presence=False)
    assert len(issues) == 4


def test_laya_required_authorities_are_pinned():
    expected = {
        "engine/ai/laya/contracts.py",
        "engine/ai/laya/config.py",
        "engine/ai/laya/model_registry.py",
        "engine/ai/laya/adapter.py",
        "engine/ai/laya/router.py",
        "engine/ai/laya/market_intelligence.py",
        "engine/ai/laya/opportunity_engine.py",
        "engine/ai/laya/strategy_hunter.py",
        "engine/ai/laya/fast_tasks.py",
        "tests_v1/test_laya_contracts.py",
        "tests_v1/test_laya_disabled_adapter.py",
        "tests_v1/test_laya_router.py",
        "tests_v1/test_laya_market_intelligence.py",
        "tests_v1/test_laya_opportunity_engine.py",
        "tests_v1/test_laya_strategy_hunter.py",
        "tests_v1/test_laya_fast_tasks.py",
        "tests_v1/test_laya_ci_guard.py",
    }
    assert expected <= set(REQUIRED)
