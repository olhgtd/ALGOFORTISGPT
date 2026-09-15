"""In-memory assembler of immutable completed position lifecycles."""
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Mapping, Sequence

from engine.execution import ExecutionOutcome, ExecutionResult
from engine.portfolio import AccountingOutcome, AccountingResult, PositionKey
from engine.portfolio.model import as_decimal
from engine.reproducibility.codec import CanonicalCodec
from engine.trades.model import LedgerEventKey, TradeLeg, TradeRecord, TradeRole, TradeStatus

@dataclass
class _Pending:
    opening: LedgerEventKey
    entries: list[TradeLeg]
    exits: list[TradeLeg]

class TradeLedger:
    def __init__(self):
        self._processed = {}
        self._legs = {}
        self._pending = {}
        self._records = []
        self._by_id = {}

    @classmethod
    def restore(
        cls,
        *,
        records: Sequence[TradeRecord] = (),
        pending: Mapping[PositionKey, tuple[LedgerEventKey, Sequence[TradeLeg], Sequence[TradeLeg]]] | None = None,
        legs: Mapping[LedgerEventKey, TradeLeg] | None = None,
        processed: Mapping[LedgerEventKey, tuple[AccountingResult, TradeRecord | None]] | None = None,
    ) -> "TradeLedger":
        ledger = cls()
        ledger._records = list(records)
        ledger._by_id = {r.trade_id: r for r in records}
        if pending:
            for pkey, (opening, entries, exits) in pending.items():
                ledger._pending[pkey] = _Pending(opening, list(entries), list(exits))
        if legs:
            ledger._legs = dict(legs)
        if processed:
            ledger._processed = dict(processed)
        return ledger

    def record(self, event_key: LedgerEventKey, result: AccountingResult) -> TradeRecord | None:
        if not isinstance(event_key, LedgerEventKey) or not isinstance(result, AccountingResult): raise TypeError("event_key and result are required")
        previous = self._processed.get(event_key)
        if previous is not None:
            if previous[0] != result: raise ValueError("LedgerEventKey collision with different source evidence")
            return previous[1]
        record = self._consume(event_key, result)
        self._processed[event_key] = (result, record)
        return record

    def completed_trades(self, *, account_id=None, strategy_id=None, instrument=None):
        records = self._records
        if account_id is not None: records = [r for r in records if r.account_id == account_id]
        if strategy_id is not None: records = [r for r in records if r.position_key.strategy_id == strategy_id]
        if instrument is not None: records = [r for r in records if r.instrument_identity == instrument]
        return tuple(sorted(records, key=lambda record: (record.closing_event_key, record.trade_id)))

    def leg_for(self, event_key: LedgerEventKey) -> TradeLeg | None:
        """Return immutable accepted-leg evidence already consumed for ``event_key``.

        This is deliberately an evidence lookup, not another position source of
        truth.  It enables post-accounting consumers such as P1-5 costs.
        """
        if not isinstance(event_key, LedgerEventKey):
            raise TypeError("event_key must be a LedgerEventKey")
        return self._legs.get(event_key)

    def _consume(self, key, result):
        evidence = result.source_evidence
        if result.outcome is not AccountingOutcome.ACCEPTED or not isinstance(evidence, ExecutionResult) or evidence.outcome is not ExecutionOutcome.FILLED: return None
        changed = [k for k in set(result.prior_snapshot.positions) | set(result.resulting_snapshot.positions) if result.prior_snapshot.positions.get(k) != result.resulting_snapshot.positions.get(k)]
        if len(changed) != 1: raise ValueError("accepted execution must identify exactly one position transition")
        position_key = changed[0]; prior = result.prior_snapshot.positions.get(position_key); after = result.resulting_snapshot.positions.get(position_key)
        price = as_decimal(evidence.fill_price, "fill_price"); qty = as_decimal(evidence.filled_quantity, "filled_quantity")
        delta = result.resulting_snapshot.realized_pnl - result.prior_snapshot.realized_pnl
        role = TradeRole.ENTRY if evidence.action == "BUY" else TradeRole.EXIT
        leg = TradeLeg(key, result, role, evidence.execution_bar_timestamp, price, qty, delta)
        self._legs[key] = leg
        if role is TradeRole.ENTRY:
            pending = self._pending.get(position_key)
            if pending is None:
                if prior is not None: raise ValueError("missing pending lifecycle")
                self._pending[position_key] = _Pending(key, [leg], [])
            else: pending.entries.append(leg)
            return None
        pending = self._pending.get(position_key)
        if pending is None or prior is None: raise ValueError("missing pending lifecycle for reduction")
        pending.exits.append(leg)
        if after is not None: return None
        trade_id = self._trade_id(result.prior_snapshot.account_id, position_key, pending.opening, key)
        record = TradeRecord(trade_id, result.prior_snapshot.account_id, result.prior_snapshot.currency, result.prior_snapshot.monetary_quantum, position_key, position_key.identity, "LONG", pending.entries[0].execution_timestamp, leg.execution_timestamp, leg.execution_timestamp-pending.entries[0].execution_timestamp, sum((x.execution_quantity for x in pending.entries), Decimal("0")), sum((x.execution_quantity for x in pending.exits), Decimal("0")), prior.average_entry_price, prior.contract_multiplier, tuple(pending.entries), tuple(pending.exits), sum((x.realized_pnl_delta for x in pending.exits), Decimal("0")), TradeStatus.CLOSED, pending.opening, key, leg.accounting_result.provenance)
        self._pending.pop(position_key); self._records.append(record); self._by_id[trade_id] = record
        return record

    @staticmethod
    def _trade_id(
        account_id: str,
        position_key: PositionKey,
        opening_event_key: LedgerEventKey,
        closing_event_key: LedgerEventKey,
    ) -> str:
        """Return the v1 canonical identity of one strategy-owned lifecycle.

        This contains only the frozen lifecycle scope.  It deliberately omits
        P&L, cost, metric, report, and timing outcomes so the trade identifier
        remains a stable ledger identity rather than an outcome fingerprint.
        """
        identity = position_key.identity
        return CanonicalCodec.fingerprint(
            "sentinelx-trade-identity/v1",
            (
                ("account_id", account_id),
                ("strategy_id", position_key.strategy_id),
                ("strategy_version", position_key.strategy_version),
                ("market", identity.market),
                ("instrument", identity.instrument),
                ("segment", identity.segment),
                ("underlying", identity.underlying),
                ("expiry", identity.expiry),
                ("strike", identity.strike),
                ("option_type", identity.option_type),
                ("opening_run_id", opening_event_key.run_id),
                ("opening_sequence", opening_event_key.accounting_sequence),
                ("closing_run_id", closing_event_key.run_id),
                ("closing_sequence", closing_event_key.accounting_sequence),
            ),
        )
