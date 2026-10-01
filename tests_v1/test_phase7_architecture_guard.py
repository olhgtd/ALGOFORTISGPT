import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "build" / "tools" / "check_phase7_portfolio_risk.py"


def _load():
    assert CHECKER.is_file(), "Phase-7 static guard missing"
    spec = importlib.util.spec_from_file_location("p7guard", CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(root: Path, relative: str, source: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def test_safe_fixture_passes(tmp_path: Path) -> None:
    module = _load()
    _write(tmp_path, "engine/portfolio/v2/x.py", "from decimal import Decimal\n")
    assert module.verify(tmp_path, check_presence=False) == ()


def test_broker_live_ai_imports_are_rejected(tmp_path: Path) -> None:
    module = _load()
    _write(
        tmp_path,
        "engine/portfolio/v2/x.py",
        "import engine.broker_adapters\nimport engine.live\nimport engine.ai\n",
    )
    joined = "\n".join(module.verify(tmp_path, check_presence=False))
    assert "broker" in joined and "live" in joined and "ai" in joined


def test_approved_order_mint_or_constructor_is_rejected(tmp_path: Path) -> None:
    module = _load()
    _write(
        tmp_path,
        "engine/risk/portfolio_v2.py",
        "from engine.orders.contracts_v2 import ApprovedOrder, _mint_approved_order\n"
        "def x():\n    return ApprovedOrder()\n",
    )
    joined = "\n".join(module.verify(tmp_path, check_presence=False))
    assert "_mint_approved_order" in joined
    assert "ApprovedOrder constructor" in joined
