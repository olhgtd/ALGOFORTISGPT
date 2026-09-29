"""Authority guards for manual-V1 capability salvage.

These tests do not add a new trading authority. They freeze the V2 boundary so
future V1 feature salvage cannot accidentally resurrect a parallel RiskGate or
a restart-to-active path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.live.state_machine_v2 import (
    LiveState,
    LiveStateMachine,
    LiveStateTransitionError,
    TransitionReason,
)


_REPO_ROOT = Path(__file__).resolve().parents[1]


class _AuditSink:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def write(self, event_type: str, payload: dict[str, object]) -> None:
        self.events.append((event_type, dict(payload)))


def test_only_risk_gate_v2_may_call_private_approved_order_minter() -> None:
    """Freeze RiskGateV2 as the sole engine caller of the private capability minter."""

    references: set[str] = set()
    engine_root = _REPO_ROOT / "engine"
    for path in engine_root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "_mint_approved_order(" in source:
            references.add(path.relative_to(_REPO_ROOT).as_posix())

    assert references == {
        "engine/orders/contracts_v2.py",
        "engine/risk/gate_v2.py",
    }


def test_restart_from_active_is_recovery_and_cannot_jump_back_to_active() -> None:
    """V1 restart/hydration salvage must never restore an armed/active state."""

    audit = _AuditSink()
    machine = LiveStateMachine.restore_after_restart(
        previous_state=LiveState.ACTIVE,
        audit_sink=audit,
    )

    assert machine.state is LiveState.RECOVERY
    assert machine.is_active is False

    with pytest.raises(LiveStateTransitionError):
        machine.transition(
            LiveState.ACTIVE,
            reason=TransitionReason.ARM_REQUEST,
        )

    assert machine.state is LiveState.RECOVERY
    assert audit.events[-1][1]["to_state"] == LiveState.RECOVERY.value
    assert audit.events[-1][1]["arm_enabled"] is False
