"""Independent event-ledger identity check."""
from __future__ import annotations

from .contracts import ExecutionModel, V2Error
from .execution import FillEvent, SimulationResult, _fingerprint
import re


def replay(events: tuple[FillEvent, ...], model: ExecutionModel, *,
           input_fingerprint: str) -> SimulationResult:
    if (not isinstance(events, tuple) or not isinstance(model, ExecutionModel)
            or any(not isinstance(x, FillEvent) for x in events)
            or not isinstance(input_fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", input_fingerprint)):
        raise V2Error("typed replay ledger, input identity and versioned model required")
    return SimulationResult(events, _fingerprint(events, model, input_fingerprint), input_fingerprint)
