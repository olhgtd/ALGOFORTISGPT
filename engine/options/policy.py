# flake8: noqa: E501
"""Owner-locked option selection policy types.

Expiry V1 — NEAREST_LISTED only.
Strike V1 — ATM / ITM / OTM with integer offset_steps.

Per-strategy policy MUST explicitly contain all required fields.
No silent defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class StrikeMode(str, Enum):
    """Authoritative strike selection mode."""

    ATM = "ATM"
    ITM = "ITM"
    OTM = "OTM"


@dataclass(frozen=True)
class ExpiryPolicy:
    """Per-strategy expiry selection configuration.

    All fields are mandatory — no silent defaults.
    """

    mode: Literal["NEAREST_LISTED"]
    min_dte_days: int
    allow_expiry_day: bool

    def __post_init__(self) -> None:
        if self.mode != "NEAREST_LISTED":
            raise ValueError("only NEAREST_LISTED expiry mode is supported in V1")
        if not isinstance(self.min_dte_days, int) or isinstance(self.min_dte_days, bool):
            raise TypeError("min_dte_days must be an integer")
        if self.min_dte_days < 0:
            raise ValueError("min_dte_days must be >= 0")
        if not isinstance(self.allow_expiry_day, bool):
            raise TypeError("allow_expiry_day must be a bool")


@dataclass(frozen=True)
class StrikePolicy:
    """Per-strategy strike selection configuration.

    All fields are mandatory — no silent defaults.
    Strike ladder comes only from actual catalog strikes.
    No hard-coded strike intervals.
    """

    mode: StrikeMode
    offset_steps: int

    def __post_init__(self) -> None:
        if not isinstance(self.mode, StrikeMode):
            raise TypeError("mode must be a StrikeMode")
        if not isinstance(self.offset_steps, int) or isinstance(self.offset_steps, bool):
            raise TypeError("offset_steps must be an integer")
        if self.offset_steps < 0:
            raise ValueError("offset_steps must be >= 0")


@dataclass(frozen=True)
class OptionSelectionPolicy:
    """Per-strategy option selection policy.

    Every strategy that uses the option selector MUST have an explicit
    OptionSelectionPolicy.  Missing policy = fail closed.
    """

    strategy_id: str
    strategy_version: str
    expiry: ExpiryPolicy
    strike: StrikePolicy

    def __post_init__(self) -> None:
        if not isinstance(self.strategy_id, str) or not self.strategy_id.strip():
            raise ValueError("strategy_id must be a non-empty string")
        if not isinstance(self.strategy_version, str) or not self.strategy_version.strip():
            raise ValueError("strategy_version must be a non-empty string")
        object.__setattr__(self, "strategy_id", self.strategy_id.strip())
        object.__setattr__(self, "strategy_version", self.strategy_version.strip())
        if not isinstance(self.expiry, ExpiryPolicy):
            raise TypeError("expiry must be an ExpiryPolicy")
        if not isinstance(self.strike, StrikePolicy):
            raise TypeError("strike must be a StrikePolicy")
