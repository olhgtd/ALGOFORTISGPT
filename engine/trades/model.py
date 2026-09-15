"""Immutable Slice 7 trade-ledger values."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from engine.portfolio import AccountingResult, InstrumentIdentity, PositionKey


@dataclass(frozen=True, order=True)
class LedgerEventKey:
    run_id: str
    accounting_sequence: int
    def __post_init__(self):
        if not isinstance(self.run_id, str) or not self.run_id.strip(): raise ValueError("run_id must be non-empty")
        if not isinstance(self.accounting_sequence, int) or isinstance(self.accounting_sequence, bool) or self.accounting_sequence <= 0: raise ValueError("accounting_sequence must be positive")


class TradeRole(str, Enum): ENTRY="ENTRY"; EXIT="EXIT"
class TradeStatus(str, Enum): CLOSED="CLOSED"


@dataclass(frozen=True)
class TradeLeg:
    event_key: LedgerEventKey
    accounting_result: AccountingResult
    role: TradeRole
    execution_timestamp: datetime
    execution_price: Decimal
    execution_quantity: Decimal
    realized_pnl_delta: Decimal


@dataclass(frozen=True)
class TradeRecord:
    trade_id: str
    account_id: str
    currency: str
    monetary_quantum: Decimal
    position_key: PositionKey
    instrument_identity: InstrumentIdentity
    position_side: str
    opened_at: datetime
    closed_at: datetime
    holding_duration: timedelta
    entry_quantity: Decimal
    exit_quantity: Decimal
    average_entry_price: Decimal
    contract_multiplier: Decimal
    entry_legs: tuple[TradeLeg, ...]
    exit_legs: tuple[TradeLeg, ...]
    gross_realized_pnl: Decimal
    status: TradeStatus
    opening_event_key: LedgerEventKey
    closing_event_key: LedgerEventKey
    provenance: Mapping[str, object]
    def __post_init__(self):
        if self.opening_event_key.run_id != self.closing_event_key.run_id:
            raise ValueError("completed trade cannot span different runs")
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))
