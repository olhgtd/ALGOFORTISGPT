"""Mode-independent execution-evaluation seam.

ExecutionAdapter is the common synchronous evaluation contract for the currently
implemented Backtest and Paper architecture.  Future LiveBrokerAdapter compatibility
remains subject to its own live-broker preflight.
"""

from typing import Protocol, runtime_checkable

from engine.execution.model import ExecutionResult, ExecutableOrder


@runtime_checkable
class ExecutionAdapter(Protocol):
    """Minimal protocol for mode-independent order evaluation.

    Each implementation accepts its own mode-specific evidence and context
    types, but the shape is universal: order + evidence + context -> result.
    """

    model_id: str

    def evaluate(
        self,
        order: ExecutableOrder,
        market_evidence: object,
        execution_context: object,
    ) -> ExecutionResult: ...
