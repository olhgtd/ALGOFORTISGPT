"""Core broker- and data-source-agnostic strategy contracts."""

from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, Literal


SUPPORTED_SIGNAL_ACTIONS = frozenset({"BUY", "SELL", "HOLD", "EXIT"})
INTERFACE_VERSION = "1.0"


@dataclass(frozen=True)
class Signal:
    """A strategy output consumed by later engine layers."""

    action: Literal["BUY", "SELL", "HOLD", "EXIT"]
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate the frozen Signal contract."""
        if self.action not in SUPPORTED_SIGNAL_ACTIONS:
            raise ValueError(f"Unsupported signal action: {self.action}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Signal confidence must be between 0.0 and 1.0")
        if not isinstance(self.metadata, dict):
            raise TypeError("Signal metadata must be a dictionary")


class StrategySignalGenerator(ABC):
    """Abstract contract for strategies that generate signals from supplied data."""

    interface_version: ClassVar[str] = INTERFACE_VERSION
    state_schema: ClassVar[dict[str, Any]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Require every concrete strategy to declare the frozen interface version."""
        super().__init_subclass__(**kwargs)
        if "interface_version" not in cls.__dict__:
            raise TypeError("Strategies must declare interface_version = '1.0'")
        if cls.interface_version != INTERFACE_VERSION:
            raise ValueError(
                f"Unsupported strategy interface_version: {cls.interface_version}"
            )

    def initial_state(self) -> dict[str, Any]:
        """Return an independent state dictionary populated from state_schema defaults."""
        return deepcopy(self.state_schema)

    @abstractmethod
    def generate_signal(
        self,
        data: Dict[str, "DataFrame"],
        state: dict[str, Any] | None,
    ) -> Signal:
        """Generate one Signal from timeframe-keyed market data and strategy state."""
