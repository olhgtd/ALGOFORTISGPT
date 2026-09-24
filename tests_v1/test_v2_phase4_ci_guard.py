from pathlib import Path

from build.tools.check_phase4_research_backtest import verify


def test_phase4_guard_finds_required_authorities_and_rejects_broker_import(tmp_path):
    root = Path(__file__).resolve().parents[1]
    assert verify(root) == ()
    file = tmp_path / "engine" / "research" / "bad.py"
    file.parent.mkdir(parents=True)
    file.write_text("from engine.broker_adapters import mock_broker\n", encoding="utf-8")
    assert any("broker" in x.lower() for x in verify(tmp_path, check_presence=False))
