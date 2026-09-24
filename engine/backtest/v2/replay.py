"""Independent event-ledger identity check."""
from __future__ import annotations

from .contracts import ExecutionModel, V2Error
from .execution import FillEvent, SimulationResult, _fingerprint


def replay(events: tuple[FillEvent, ...], model: ExecutionModel) -> SimulationResult:
    if not isinstance(events, tuple) or not isinstance(model, ExecutionModel) or any(not isinstance(x, FillEvent) for x in events):
        raise V2Error("typed replay ledger and versioned model required")
    return SimulationResult(events, _fingerprint(events, model))
