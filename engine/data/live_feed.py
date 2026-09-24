"""Broker-neutral live market-data event contracts for AlgoFortis Data V2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class LiveFeedError(ValueError):
    """Raised when a live-feed event is structurally invalid."""


class MarketState(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    HALTED = "HALTED"


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise LiveFeedError(f"{name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class LiveMarketEvent:
    """Canonical health envelope for one live market-data observation."""

    symbol: str
    exchange_timestamp: datetime
    receive_timestamp: datetime
    sequence: int
    market_state: MarketState

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise LiveFeedError("symbol must be non-empty")
        object.__setattr__(self, "symbol", self.symbol.strip().upper())
        _aware(self.exchange_timestamp, "exchange_timestamp")
        _aware(self.receive_timestamp, "receive_timestamp")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 0:
            raise LiveFeedError("sequence must be a non-negative integer")
        if not isinstance(self.market_state, MarketState):
            raise LiveFeedError("market_state must be MarketState")


__all__ = ["LiveFeedError", "MarketState", "LiveMarketEvent"]
