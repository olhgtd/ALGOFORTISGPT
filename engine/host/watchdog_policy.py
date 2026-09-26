"""Fail-closed watchdog restart policy for Phase-5 host recovery."""

from __future__ import annotations

from dataclasses import dataclass

from engine.paper.contracts_v2 import PaperOperationalState


@dataclass(frozen=True, slots=True)
class WatchdogPolicy:
    """A crashed engine may restart only into RECOVERY and can never auto-arm."""

    @property
    def auto_arm_allowed(self) -> bool:
        return False

    def restart_target(self) -> PaperOperationalState:
        return PaperOperationalState.RECOVERY


__all__ = ["WatchdogPolicy"]
