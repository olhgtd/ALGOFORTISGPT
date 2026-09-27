from __future__ import annotations
import importlib.util
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "build" / "tools" / "check_phase6_live_readonly.py"

def _load_checker():
    assert CHECKER.is_file(), "Phase-6 static mutation firewall is missing"
    spec = importlib.util.spec_from_file_location("phase6_checker", CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def _write(root: Path, relative: str, source: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")

def test_safe_read_only_fixture_passes_without_runtime_flags(tmp_path: Path) -> None:
    m = _load_checker()
    _write(tmp_path, "engine/broker_adapters/angelone_v2/read_only_adapter.py", "def orders():\n    return ()\n")
    assert m.verify(tmp_path, check_presence=False) == ()

def test_mutation_definition_is_rejected_even_when_disarmed_flag_exists(tmp_path: Path) -> None:
    m = _load_checker()
    _write(tmp_path, "engine/broker_adapters/angelone_v2/read_only_adapter.py", "DISARMED = True\ndef place(order):\n    return order\n")
    problems = m.verify(tmp_path, check_presence=False)
    assert any("mutation entrypoint" in problem and "place" in problem for problem in problems)

def test_legacy_adapter_approved_order_and_arm_true_are_rejected(tmp_path: Path) -> None:
    m = _load_checker()
    _write(tmp_path, "engine/live/phase6_readonly_coordinator.py", "from engine.broker_adapters.angel_adapter import AngelOneBrokerAdapter\nfrom engine.orders.contracts_v2 import ApprovedOrder\narm_enabled = True\n")
    problems = m.verify(tmp_path, check_presence=False)
    joined = "\n".join(problems)
    assert "legacy AngelOneBrokerAdapter" in joined
    assert "ApprovedOrder" in joined
    assert "arm_enabled=True" in joined

def test_mutation_call_and_env_bypass_are_rejected(tmp_path: Path) -> None:
    m = _load_checker()
    _write(tmp_path, "engine/live/phase6_readonly_coordinator.py", "import os\nDISARMED = True\ndef observe(broker):\n    if os.getenv('ALLOW_LIVE_MUTATION'):\n        return broker.cancel('x')\n    return None\n")
    problems = m.verify(tmp_path, check_presence=False)
    joined = "\n".join(problems)
    assert "mutation call" in joined and "cancel" in joined
    assert "environment/config mutation bypass" in joined

def test_transport_package_is_scanned_and_mutation_rejected(tmp_path: Path) -> None:
    m = _load_checker()
    _write(tmp_path, "engine/data/transports/brokers/test_driver.py", "READ_ONLY = True\ndef submit_order(order):\n    return order\n")
    problems = m.verify(tmp_path, check_presence=False)
    assert any("submit_order" in p and "mutation entrypoint" in p for p in problems)

def test_transport_package_rejects_direct_riskgate_and_operational_state_imports(tmp_path: Path) -> None:
    m = _load_checker()
    _write(tmp_path, "engine/data/transports/runtime.py", "from engine.risk.gate_v2 import RiskGateV2\nfrom engine.live.state_machine_v2 import OperationalStateMachine\n")
    joined = "\n".join(m.verify(tmp_path, check_presence=False))
    assert "direct RiskGate import" in joined
    assert "direct Phase-5 operational-state import" in joined
