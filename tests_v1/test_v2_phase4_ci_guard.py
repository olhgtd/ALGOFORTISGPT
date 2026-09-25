from pathlib import Path

from build.tools.check_phase4_research_backtest import verify


def test_phase4_guard_finds_required_authorities_and_rejects_broker_import(tmp_path):
    root = Path(__file__).resolve().parents[1]
    assert verify(root) == ()
    file = tmp_path / "engine" / "research" / "bad.py"
    file.parent.mkdir(parents=True)
    file.write_text("from engine.broker_adapters import mock_broker\n", encoding="utf-8")
    assert any("broker" in x.lower() for x in verify(tmp_path, check_presence=False))


def test_phase4_guard_covers_strategy_and_orb_boundaries(tmp_path):
    strategy_file = tmp_path / "engine" / "strategy" / "bad.py"
    strategy_file.parent.mkdir(parents=True)
    strategy_file.write_text("from engine.execution.live import executor\n", encoding="utf-8")

    orb_file = tmp_path / "strategies" / "orb" / "bad.py"
    orb_file.parent.mkdir(parents=True)
    orb_file.write_text("import socket\n", encoding="utf-8")

    problems = verify(tmp_path, check_presence=False)
    assert any("engine\\strategy\\bad.py" in item or "engine/strategy/bad.py" in item for item in problems)
    assert any("strategies\\orb\\bad.py" in item or "strategies/orb/bad.py" in item for item in problems)
