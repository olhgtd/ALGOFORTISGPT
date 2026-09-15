"""Strategy exception handling contract."""

from typing import Literal

from engine.audit import log as audit_log
from engine.safety import strategy_halt
from engine.strategy.base import Signal


def safe_generate_signal(
    strategy, data, state, mode: Literal["backtest", "live"]
) -> Signal:
    """Run a strategy signal evaluation under the frozen Rule 7 policy."""
    try:
        return strategy.generate_signal(data, state)
    except Exception as exception:
        audit_log.record(strategy.id, strategy.interface_version, exception)
        if mode == "backtest":
            return Signal(
                action="HOLD",
                confidence=0.0,
                metadata={"error": str(exception)},
            )
        strategy_halt.alert_and_halt(strategy.id, exception)
