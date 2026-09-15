"""Narrow Rule 7 strategy-halt facade."""

import logging
from typing import NoReturn

logger = logging.getLogger(__name__)

_halted: dict[str, str] = {}


class StrategyHaltError(Exception):
    """Fatal live halt signal; normal control flow must not continue after it.

    Deliberately a plain ``Exception`` subclass rather than ``RuntimeError``,
    ``ValueError``, or any type a strategy might raise, so broad handlers for
    the original strategy error cannot accidentally swallow the halt.
    """

    def __init__(self, strategy_id: str, reason: str) -> None:
        super().__init__(f"strategy {strategy_id!r} halted: {reason}")
        self.strategy_id = strategy_id
        self.reason = reason


def alert_and_halt(strategy_id, exception) -> NoReturn:
    """Emit the strategy-specific halt alert, retain halted state, and raise.

    The frozen Rule 7 contract declares ``-> NoReturn``: after a fatal live
    condition, normal execution must not continue on this control-flow path.
    Full alerting infrastructure and per-strategy process isolation are later
    live-control dependencies; this facade performs the in-process fail-closed
    termination behind the same narrow boundary.
    """
    # Full alerting infrastructure is a later-phase dependency.
    logger.error(
        "strategy_halt_alert strategy_id=%r exception_type=%r exception_message=%r",
        strategy_id,
        type(exception).__name__,
        str(exception),
    )
    # Retain halted state and the first recorded reason, deterministically and
    # idempotently, before terminating control flow.
    _halted.setdefault(str(strategy_id), str(exception))
    raise StrategyHaltError(str(strategy_id), str(exception))


def halted_reason(strategy_id) -> str | None:
    """Return the retained halt reason for a strategy, or None if not halted."""
    return _halted.get(str(strategy_id))
