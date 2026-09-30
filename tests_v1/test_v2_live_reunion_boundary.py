from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


GUARD_PATH = Path("build/tools/check_live_reunion_boundary.py")
MANIFEST_PATH = Path("docs/v2/live/V1_V2_LIVE_REUNION_MANIFEST.md")
EXPECTED_STATUSES = (
    "SALVAGED",
    "REFERENCE_ONLY",
    "REPLACED_BY_V2",
    "DEFERRED",
)


def _load_guard() -> ModuleType:
    assert GUARD_PATH.is_file(), "Live reunion boundary guard is missing"
    spec = importlib.util.spec_from_file_location("check_live_reunion_boundary", GUARD_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_reunion_manifest_exists_with_all_binding_classifications() -> None:
    assert MANIFEST_PATH.is_file(), "Live reunion manifest is missing"
    text = MANIFEST_PATH.read_text(encoding="utf-8")
    for status in EXPECTED_STATUSES:
        assert status in text


def test_guard_rejects_direct_broker_mutation_from_noncanonical_runtime() -> None:
    guard = _load_guard()
    failures = guard.check_source_text(
        "dashboard/backend/live_actions.py",
        "from engine.broker_adapters.angel_adapter import AngelAdapter\n\ndef run():\n    place_order()\n",
    )
    assert any("legacy mutation adapter" in item for item in failures)
    assert any("direct broker mutation" in item for item in failures)


def test_guard_rejects_direct_live_port_place_outside_coordinator() -> None:
    guard = _load_guard()
    failures = guard.check_source_text(
        "engine/live/shortcut.py",
        "def shortcut(port, order):\n    return port.place(order)\n",
    )
    assert any("direct Live broker mutation" in item for item in failures)


def test_guard_rejects_production_open_mutation_gate_class() -> None:
    guard = _load_guard()
    failures = guard.check_source_text(
        "engine/live/mutation_release_gate_v2.py",
        "class OpenLiveMutationReleaseGate:\n    def authorize(self, *, order, live_state):\n        return 'allowed'\n",
    )
    assert any("open mutation gate" in item.lower() for item in failures)


def test_guard_rejects_direct_approved_order_mint_outside_riskgate() -> None:
    guard = _load_guard()
    failures = guard.check_source_text(
        "engine/live/shortcut.py",
        "def approve():\n    return _mint_approved_order()\n",
    )
    assert any("ApprovedOrder mint" in item for item in failures)


def test_guard_rejects_second_reconnect_authority() -> None:
    guard = _load_guard()
    failures = guard.check_source_text(
        "engine/live/reconnect_manager_v2.py",
        "class ReconnectGenerationAuthority:\n    pass\n",
    )
    assert any("reconnect" in item.lower() and "authority" in item.lower() for item in failures)


def test_guard_rejects_restart_auto_arm_outside_state_machine() -> None:
    guard = _load_guard()
    failures = guard.check_source_text(
        "engine/reconciliation/live_reconciler.py",
        "def restore_after_restart():\n    arm_live()\n",
    )
    assert any("auto-arm" in item.lower() or "arm" in item.lower() for item in failures)


def test_guard_ignores_protected_setting_names_that_are_not_calls() -> None:
    guard = _load_guard()
    failures = guard.check_source_text(
        "dashboard/backend/security_store.py",
        "_PROTECTED_SETTING_KEYS = {'arm_live_trading', 'enable_broker_mutation'}\n",
    )
    assert failures == []


def test_guard_allows_canonical_live_state_machine_arm_vocabulary() -> None:
    guard = _load_guard()
    failures = guard.check_source_text(
        "engine/live/state_machine_v2.py",
        "class LiveStateMachine:\n    def transition(self):\n        return 'ARM_REQUEST'\n",
    )
    assert failures == []


def test_current_repository_passes_live_reunion_boundary_guard() -> None:
    guard = _load_guard()
    assert guard.check_repository(Path(".")) == []
