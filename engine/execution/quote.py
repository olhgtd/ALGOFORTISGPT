"""Immutable point-in-time executable quote evidence for paper fills.

Carries ONLY fields genuinely required for V1 fill evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from engine.core.numeric import as_decimal
from engine.portfolio.model import InstrumentIdentity


@dataclass(frozen=True)
class QuoteSnapshot:
    """Immutable point-in-time executable quote evidence.

    ``bid_price`` / ``ask_price`` may be None (thin instrument).
    A crossed quote (bid > ask) is valid evidence — the fill adapter
    evaluates it as UNFILLED rather than rejecting at construction.
    ``last_price`` is informational only and must NEVER be the sole
    executable fill reference.
    """

    instrument_identity: InstrumentIdentity
    exchange_timestamp: datetime
    bid_price: Decimal | None
    ask_price: Decimal | None
    source: str
    bid_quantity: Decimal | None = None
    ask_quantity: Decimal | None = None
    last_price: Decimal | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_identity, InstrumentIdentity):
            raise TypeError("instrument_identity must be an InstrumentIdentity")
        if (
            self.exchange_timestamp is None
            or self.exchange_timestamp.tzinfo is None
            or self.exchange_timestamp.utcoffset() is None
        ):
            raise ValueError("exchange_timestamp must be timezone-aware")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must be a non-empty string")
        object.__setattr__(
            self, "source", self.source.strip(),
        )
        if self.bid_price is not None:
            object.__setattr__(
                self, "bid_price", as_decimal(self.bid_price, "bid_price"),
            )
            if self.bid_price <= 0:
                raise ValueError("bid_price must be positive when present")
        if self.ask_price is not None:
            object.__setattr__(
                self, "ask_price", as_decimal(self.ask_price, "ask_price"),
            )
            if self.ask_price <= 0:
                raise ValueError("ask_price must be positive when present")
        if self.last_price is not None:
            object.__setattr__(
                self, "last_price", as_decimal(self.last_price, "last_price"),
            )
            if self.last_price <= 0:
                raise ValueError("last_price must be positive when present")
        if self.bid_quantity is not None:
            object.__setattr__(
                self,
                "bid_quantity",
                as_decimal(self.bid_quantity, "bid_quantity"),
            )
        if self.ask_quantity is not None:
            object.__setattr__(
                self,
                "ask_quantity",
                as_decimal(self.ask_quantity, "ask_quantity"),
            )
