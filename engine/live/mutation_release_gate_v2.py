"""Package-1 Live mutation release gate.

Production has no open implementation in this package. The only concrete gate
is closed; tests may provide local Protocol-compatible fakes to exercise the
dormant coordinator without creating a production arming path.
"""
from __future__ import annotations

from typing import Protocol

from engine.live.state_machine_v2 import LiveState
from engine.orders.contracts_v2 import ApprovedOrder


class LiveMutationBlocked(RuntimeError):
    """Raised when Package-1 cannot authorize a Live broker mutation."""


class LiveMutationReleaseGate(Protocol):
    def authorize(self, *, order: ApprovedOrder, live_state: LiveState) -> str: ...


class ClosedLiveMutationReleaseGate:
    """Fail-closed production gate for Package-1."""

    def authorize(self, *, order: ApprovedOrder, live_state: LiveState) -> str:
        if not isinstance(order, ApprovedOrder):
            raise TypeError("order must be ApprovedOrder")
        if not isinstance(live_state, LiveState):
            raise TypeError("live_state must be LiveState")
        raise LiveMutationBlocked("live mutation release gate is closed")


__all__ = [
    "ClosedLiveMutationReleaseGate",
    "LiveMutationBlocked",
    "LiveMutationReleaseGate",
]
