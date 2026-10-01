"""Paper-only execution boundary for AlgoFortis V2 Phase 5."""

from __future__ import annotations

from datetime import datetime

from engine.orders.contracts_v2 import ApprovedOrder, RunMode
from engine.paper.fill_simulator_v2 import (
    FillSimulationPolicy,
    PaperFillSimulator,
    QuoteSnapshot,
    SimulatedExecutionResult,
)


class PaperExecutionAdapterV2:
    """Accept only RiskGate-minted PAPER capabilities and simulate execution."""

    def __init__(self, simulator: PaperFillSimulator) -> None:
        if not isinstance(simulator, PaperFillSimulator):
            raise TypeError("simulator must be PaperFillSimulator")
        self._simulator = simulator

    def execute(
        self,
        approved_order: ApprovedOrder,
        quote: QuoteSnapshot,
        policy: FillSimulationPolicy,
        *,
        now: datetime,
    ) -> SimulatedExecutionResult:
        if not isinstance(approved_order, ApprovedOrder):
            raise TypeError("approved_order must be an ApprovedOrder")
        if approved_order.run_mode is not RunMode.PAPER:
            raise ValueError("ApprovedOrder must be PAPER mode")
        return self._simulator.simulate(
            approved_order,
            quote,
            policy,
            now=now,
        )


__all__ = ["PaperExecutionAdapterV2"]
