"""Phase 5 Slice 4D / OD-7 Item 7 — Virtual Paper Account and Live MTM.

Stateful in-memory virtual account maintaining active AccountSnapshot,
pending premium cash commitments, live quote mark-to-market valuation,
5-second authoritative market-time staleness, broker fill accounting,
and D5 canonical cost-booking parity.

OWNER FROZEN CONTRACTS:
  - VA-1: VirtualPaperAccount owns active snapshot; PortfolioAccount owns transformations.
  - VA-2: Starting capital owned as single account-level value.
  - VA-3: Fill-driven accounting: only FILLED events mutate cash/positions/realized P&L.
  - VA-4 / VA-4A: Premium cash commitment reservation & available_cash gating.
  - VA-4B / VA-4C / VA-4D: Canonical reservation creation, identity, and broker submit rollback.
  - VA-5: Shared capital pool across all strategies under D14.
  - VA-6: Long option mark price = authoritative executable BID.
  - VA-7 / VA-7A / VA-7B: 5-second market-time staleness, sidecar metadata, and account-wide gating.
  - VA-7C / VA-7D: MarketTime advancement and fail-closed entry gating.
  - VA-8 / VA-9: Account equity formulas and QuoteSnapshot exchange timestamp authority.
  - VA-10: Disconnect marks positions STALE; reconnect requires fresh accepted quote.
  - VA-11 / VA-11A / VA-11B / VA-11C: BrokerTerminalEvent delivery, fill idempotency, stale context gate.
  - VA-12: IN-MEMORY and NON-RESTART-SAFE until Item 9 SQLite persistence.
  - VA-13: D5 gross accounting in snapshot + recognized costs on closed trades.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping

from engine.costs.model import CostAssessment, CostSchedule
from engine.execution.model import ExecutionOutcome, ExecutionResult
from engine.execution.paper_broker import BrokerTerminalEvent
from engine.execution.quote import QuoteSnapshot
from engine.data.feeds.live_feed import FeedConnectionState
from engine.core.numeric import as_decimal

from engine.orders.lifecycle import OrderLifecycleState
from engine.portfolio.accounting import PortfolioAccount
from engine.portfolio.model import (
    INTERNAL_DECIMAL_CONTEXT,
    AccountSnapshot,
    AccountingOutcome,
    AccountingResult,
    InstrumentIdentity,
    InstrumentSpecification,
    PositionKey,
    PositionSnapshot,
    quantize_monetary,
)
from engine.protective.runtime import ProtectiveExitBook
from engine.risk.risk_manager import PendingRiskCommitment, RiskDay
from engine.trades.ledger import TradeLedger
from engine.trades.model import LedgerEventKey, TradeRole

__all__ = [
    "ValuationState",
    "PositionValuationRecord",
    "PremiumCommitmentRecord",
    "ValuationUnavailableError",
    "VirtualAccountInvariantError",
    "InsufficientAvailableCashError",
    "VirtualPaperAccount",
]


# ======================================================================
# 1. Valuation and Commitment Enums & Records
# ======================================================================


class ValuationState(str, Enum):
    """Valuation status for an open position or the overall account."""

    LIVE = "LIVE"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


class ValuationUnavailableError(RuntimeError):
    """Raised when entry runtime context is requested while valuation is STALE or UNAVAILABLE."""


class VirtualAccountInvariantError(RuntimeError):
    """Raised when an internal accounting or fill invariant is breached."""


class InsufficientAvailableCashError(RuntimeError):
    """Raised when an operation requires more available cash than exists."""


@dataclass(frozen=True)
class PositionValuationRecord:
    """Sidecar valuation metadata for one held PositionKey."""

    position_key: PositionKey
    state: ValuationState
    last_valid_mark_price: Decimal | None
    last_valid_mark_timestamp: datetime | None
    latest_quote_timestamp: datetime | None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")
        if not isinstance(self.state, ValuationState):
            raise TypeError("state must be a ValuationState")


@dataclass(frozen=True)
class PremiumCommitmentRecord:
    """Immutable reservation evidence for one approved pending opening BUY."""

    reservation_key: str
    strategy_id: str
    strategy_version: str
    identity: InstrumentIdentity
    approved_quantity: Decimal
    worst_permitted_fill_price: Decimal
    contract_multiplier: Decimal
    required_cash: Decimal
    created_at_market_time: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.reservation_key, str) or not self.reservation_key.strip():
            raise ValueError("reservation_key must be a non-empty string")
        if not isinstance(self.identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")
        for field_name in (
            "approved_quantity",
            "worst_permitted_fill_price",
            "contract_multiplier",
            "required_cash",
        ):
            val = as_decimal(getattr(self, field_name), field_name)
            if val <= 0:
                raise ValueError(f"{field_name} must be positive")
            object.__setattr__(self, field_name, val)
        if not isinstance(self.created_at_market_time, datetime) or self.created_at_market_time.tzinfo is None:
            raise ValueError("created_at_market_time must be a timezone-aware datetime")


# ======================================================================
# 2. VirtualPaperAccount Implementation
# ======================================================================


class VirtualPaperAccount:
    """Stateful, deterministic virtual paper-trading account manager.

    In-memory only (Item 7). Non-restart-safe until Item 9 SQLite persistence.
    """

    def __init__(
        self,
        portfolio_account: PortfolioAccount,
        *,
        stale_mtm_threshold: timedelta = timedelta(seconds=5),
        cost_schedules: Sequence[CostSchedule] = (),
        specifications: Mapping[InstrumentIdentity, InstrumentSpecification] | None = None,
        require_opening_reservation: bool = True,
    ) -> None:
        if not isinstance(portfolio_account, PortfolioAccount):
            raise TypeError("portfolio_account must be a PortfolioAccount")
        if not isinstance(stale_mtm_threshold, timedelta) or stale_mtm_threshold <= timedelta(0):
            raise ValueError("stale_mtm_threshold must be a positive timedelta")

        self._portfolio_account = portfolio_account
        self._stale_mtm_threshold = stale_mtm_threshold
        self._cost_schedules = tuple(cost_schedules)
        self._specifications: dict[InstrumentIdentity, InstrumentSpecification] = (
            dict(specifications) if specifications is not None else {}
        )
        self._require_opening_reservation = require_opening_reservation

        # Canonical initial state
        self._snapshot: AccountSnapshot = portfolio_account.initial_snapshot()

        # Sidecar state
        self._active_commitments: dict[str, PremiumCommitmentRecord] = {}
        self._processed_fills: dict[str, tuple[BrokerTerminalEvent, AccountingResult]] = {}
        self._position_valuations: dict[PositionKey, PositionValuationRecord] = {}
        self._last_market_time: datetime | None = None
        self._is_feed_connected: bool = True
        self._accounting_integrity_breached: bool = False

        # Cost tracking & ledger
        from engine.costs.calculator import CostCalculator

        self._trade_ledger = TradeLedger()
        self._cost_calculator = CostCalculator()
        self._cost_assessments: list[CostAssessment] = []
        self._accounting_sequence: int = 0



    # ------------------------------------------------------------------
    # Public Read-Only Properties
    # ------------------------------------------------------------------

    @property
    def snapshot(self) -> AccountSnapshot:
        """Active immutable gross AccountSnapshot."""
        return self._snapshot

    @property
    def account_id(self) -> str:
        return self._snapshot.account_id

    @property
    def currency(self) -> str:
        return self._snapshot.currency

    @property
    def monetary_quantum(self) -> Decimal:
        return self._snapshot.monetary_quantum

    @property
    def starting_capital(self) -> Decimal:
        return self._snapshot.starting_capital

    @property
    def cash(self) -> Decimal:
        """Booked gross settled cash balance."""
        return self._snapshot.cash

    @property
    def realized_pnl(self) -> Decimal:
        """Gross realized P&L."""
        return self._snapshot.realized_pnl

    @property
    def unrealized_pnl(self) -> Decimal:
        """Unrealized P&L from marked positions."""
        return self._snapshot.unrealized_pnl

    @property
    def gross_equity(self) -> Decimal:
        """Gross marked portfolio equity (cash + open positions marked value)."""
        return self._snapshot.equity

    @property
    def equity(self) -> Decimal:
        """Canonical equity alias (gross equity)."""
        return self._snapshot.equity

    @property
    def positions(self) -> Mapping[PositionKey, PositionSnapshot]:
        return self._snapshot.positions

    @property
    def active_commitments(self) -> tuple[PremiumCommitmentRecord, ...]:
        return tuple(self._active_commitments.values())

    @property
    def reserved_cash(self) -> Decimal:
        """Total cash currently reserved for pending opening BUY orders."""
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            total = sum((c.required_cash for c in self._active_commitments.values()), Decimal("0"))
        return quantize_monetary(total, self._snapshot.monetary_quantum)

    @property
    def available_cash(self) -> Decimal:
        """Available cash for new commitments: cash - sum(active premium commitments)."""
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            avail = self._snapshot.cash - self.reserved_cash
        return quantize_monetary(avail, self._snapshot.monetary_quantum)

    @property
    def recognized_costs(self) -> Decimal:
        """Sum of recognized transaction costs on completed closed trades."""
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            total = sum((a.total_cost for a in self._cost_assessments), Decimal("0"))
        return quantize_monetary(total, self._snapshot.monetary_quantum)

    @property
    def cost_adjusted_equity(self) -> Decimal:
        """Net equity after recognized closed-trade transaction costs."""
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            net = self.gross_equity - self.recognized_costs
        return quantize_monetary(net, self._snapshot.monetary_quantum)

    @property
    def valuation_state(self) -> ValuationState:
        """Derived account-wide valuation state."""
        if not self._snapshot.positions:
            return ValuationState.LIVE
        states = {rec.state for rec in self._position_valuations.values()}
        if ValuationState.UNAVAILABLE in states:
            return ValuationState.UNAVAILABLE
        if ValuationState.STALE in states:
            return ValuationState.STALE
        return ValuationState.LIVE

    @property
    def is_valuation_live(self) -> bool:
        return self.valuation_state is ValuationState.LIVE

    @property
    def is_integrity_breached(self) -> bool:
        return self._accounting_integrity_breached

    @property
    def trade_ledger(self) -> TradeLedger:
        """Underlying TradeLedger tracking completed trades and lifecycles."""
        return self._trade_ledger

    @property
    def cost_assessments(self) -> tuple[CostAssessment, ...]:
        """Recognized closed-trade cost assessments."""
        return tuple(self._cost_assessments)

    @property
    def accounting_sequence(self) -> int:
        """Monotonic accounting sequence counter."""
        return self._accounting_sequence

    @property
    def accounting_integrity_breached(self) -> bool:
        """Whether accounting integrity has been permanently breached."""
        return self._accounting_integrity_breached

    @property
    def processed_fills(self) -> Mapping[str, tuple[BrokerTerminalEvent, AccountingResult]]:
        """Processed broker fill idempotency records keyed by broker_order_identity."""
        return dict(self._processed_fills)

    @classmethod
    def restore(
        cls,
        portfolio_account: PortfolioAccount,
        *,
        snapshot: AccountSnapshot,
        active_commitments: Mapping[str, PremiumCommitmentRecord] | None = None,
        processed_fills: Mapping[str, tuple[BrokerTerminalEvent, AccountingResult]] | None = None,
        trade_ledger: TradeLedger | None = None,
        cost_assessments: Sequence[CostAssessment] | None = None,
        accounting_sequence: int = 0,
        accounting_integrity_breached: bool = False,
        stale_mtm_threshold: timedelta = timedelta(seconds=5),
        cost_schedules: Sequence[CostSchedule] = (),
        specifications: Mapping[InstrumentIdentity, InstrumentSpecification] | None = None,
        require_opening_reservation: bool = True,
    ) -> "VirtualPaperAccount":
        """Restore a VirtualPaperAccount exactly from authoritative persisted state.

        Forces all restored open positions to non-LIVE (STALE/UNAVAILABLE) status
        until fresh accepted QuoteSnapshots arrive on those contracts.
        """
        account = cls(
            portfolio_account,
            stale_mtm_threshold=stale_mtm_threshold,
            cost_schedules=cost_schedules,
            specifications=specifications,
            require_opening_reservation=require_opening_reservation,
        )
        account._snapshot = snapshot
        if active_commitments:
            account._active_commitments = dict(active_commitments)
        if processed_fills:
            account._processed_fills = dict(processed_fills)
        if trade_ledger is not None:
            account._trade_ledger = trade_ledger
        if cost_assessments:
            account._cost_assessments = list(cost_assessments)
        account._accounting_sequence = accounting_sequence
        account._accounting_integrity_breached = accounting_integrity_breached

        # After restart, held positions MUST NOT restore as LIVE.
        # Force all positions to STALE or UNAVAILABLE awaiting fresh quotes.
        account._position_valuations.clear()
        for pkey, pos in snapshot.positions.items():
            account._position_valuations[pkey] = PositionValuationRecord(
                position_key=pkey,
                state=ValuationState.STALE if pos.mark_price is not None else ValuationState.UNAVAILABLE,
                last_valid_mark_price=pos.mark_price,
                last_valid_mark_timestamp=pos.mark_timestamp,
                latest_quote_timestamp=None,
                reason="restart_hydration",
            )
        return account

    def valuation_record(self, position_key: PositionKey) -> PositionValuationRecord | None:
        """Return the sidecar valuation record for a specific held PositionKey."""
        return self._position_valuations.get(position_key)

    def register_specification(self, specification: InstrumentSpecification) -> None:
        """Register or update an instrument specification in the account cache."""
        if not isinstance(specification, InstrumentSpecification):
            raise TypeError("specification must be an InstrumentSpecification")
        self._specifications[specification.identity] = specification

    # ------------------------------------------------------------------
    # Premium Cash Commitments (VA-4 / VA-4A / VA-4B / VA-4C / VA-4D)
    # ------------------------------------------------------------------

    def reserve_premium(
        self,
        *,
        reservation_key: str,
        strategy_id: str,
        strategy_version: str,
        identity: InstrumentIdentity,
        approved_quantity: Decimal | int | float | str,
        worst_permitted_fill_price: Decimal | int | float | str,
        contract_multiplier: Decimal | int | float | str,
        market_time: datetime,
    ) -> bool:
        """Reserve worst-case premium cash before broker submission.

        Returns True if reservation was accepted or already exists identically.
        Returns False if available_cash is insufficient.
        Fails closed on conflicting reservation payload.
        """
        if self._accounting_integrity_breached:
            raise VirtualAccountInvariantError("Accounting integrity is breached; reservations blocked")

        qty = as_decimal(approved_quantity, "approved_quantity")
        price = as_decimal(worst_permitted_fill_price, "worst_permitted_fill_price")
        mult = as_decimal(contract_multiplier, "contract_multiplier")
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            req_cash = quantize_monetary(qty * price * mult, self._snapshot.monetary_quantum)

        existing = self._active_commitments.get(reservation_key)
        if existing is not None:
            # Idempotency / conflict check
            if (
                existing.strategy_id == strategy_id
                and existing.strategy_version == strategy_version
                and existing.identity == identity
                and existing.approved_quantity == qty
                and existing.worst_permitted_fill_price == price
                and existing.contract_multiplier == mult
                and existing.required_cash == req_cash
            ):
                return True
            raise ValueError(
                f"Conflicting duplicate reservation for key {reservation_key!r}: "
                f"existing={existing}, requested qty={qty}, price={price}, mult={mult}, cash={req_cash}"
            )

        if req_cash > self.available_cash:
            return False

        record = PremiumCommitmentRecord(
            reservation_key=reservation_key,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            identity=identity,
            approved_quantity=qty,
            worst_permitted_fill_price=price,
            contract_multiplier=mult,
            required_cash=req_cash,
            created_at_market_time=market_time,
        )
        self._active_commitments[reservation_key] = record
        return True

    def release_reservation(self, reservation_key: str, *, reason: str | None = None) -> bool:
        """Release a pending premium commitment upon terminal disposition or pre-submit abort."""
        if reservation_key in self._active_commitments:
            del self._active_commitments[reservation_key]
            return True
        return False

    # ------------------------------------------------------------------
    # Broker Fill Accounting (VA-3 / VA-11 / VA-11A / VA-11B)
    # ------------------------------------------------------------------

    def on_broker_terminal_event(
        self,
        event: BrokerTerminalEvent,
        specification: InstrumentSpecification | None = None,
    ) -> AccountingResult | None:
        """Process one broker terminal event atomically.

        Non-FILLED events release any corresponding pre-submit reservation and return None.
        FILLED events execute atomic accounting mutation via PortfolioAccount.apply_execution().
        """
        if not isinstance(event, BrokerTerminalEvent):
            raise TypeError("event must be a BrokerTerminalEvent")

        if self._accounting_integrity_breached:
            raise VirtualAccountInvariantError("Accounting integrity is breached; fills blocked")

        order_id = event.order_id
        canonical_id = event.broker_order_identity

        # Non-FILLED terminal events: release reservation if present
        if event.lifecycle_state is not OrderLifecycleState.FILLED:
            try:
                from engine.risk.risk_manager import entry_intent_identity

                orig_order = event.original_order
                res_key = entry_intent_identity(
                    strategy_id=orig_order.strategy_id,
                    strategy_version=orig_order.strategy_version,
                    identity=event.instrument_identity,
                    timeframe=orig_order.timeframe,
                    originating_timestamp=orig_order.originating_timestamp,
                )
                self._active_commitments.pop(res_key, None)
            except Exception:
                pass
            self._active_commitments.pop(order_id, None)
            self._active_commitments.pop(canonical_id, None)
            return None

        # FILLED terminal event validation
        if event.execution_result is None:
            self._accounting_integrity_breached = True
            raise VirtualAccountInvariantError("FILLED BrokerTerminalEvent missing execution_result")

        # Fill idempotency check (VA-11B)
        if canonical_id in self._processed_fills:
            prev_event, prev_result = self._processed_fills[canonical_id]
            if (
                prev_event.order_id == event.order_id
                and prev_event.lifecycle_state == event.lifecycle_state
                and prev_event.instrument_identity == event.instrument_identity
                and prev_event.execution_result == event.execution_result
            ):
                return prev_result  # Idempotent no-op
            self._accounting_integrity_breached = True
            raise ValueError(
                f"Conflicting duplicate fill for broker order identity {canonical_id!r}"
            )

        # Resolve specification
        spec = specification or self._specifications.get(event.instrument_identity)
        if spec is None:
            self._accounting_integrity_breached = True
            raise VirtualAccountInvariantError(
                f"Missing InstrumentSpecification for filled instrument {event.instrument_identity}"
            )

        # Apply execution through canonical PortfolioAccount
        accounting_result = self._portfolio_account.apply_execution(
            self._snapshot,
            event.execution_result,
            spec,
        )

        if accounting_result.outcome is not AccountingOutcome.ACCEPTED:
            self._accounting_integrity_breached = True
            raise VirtualAccountInvariantError(
                f"Broker-confirmed fill rejected by canonical accounting: {accounting_result.reason}"
            )

        # Atomic commit of new snapshot
        self._snapshot = accounting_result.resulting_snapshot
        
        # Release matching active commitment
        had_reservation = False
        res_key = None
        try:
            from engine.risk.risk_manager import entry_intent_identity

            orig_order = event.original_order
            res_key = entry_intent_identity(
                strategy_id=orig_order.strategy_id,
                strategy_version=orig_order.strategy_version,
                identity=event.instrument_identity,
                timeframe=orig_order.timeframe,
                originating_timestamp=orig_order.originating_timestamp,
            )
            if res_key in self._active_commitments:
                self._active_commitments.pop(res_key)
                had_reservation = True
        except Exception:
            pass

        if not had_reservation and order_id in self._active_commitments:
            self._active_commitments.pop(order_id)
            had_reservation = True
        if not had_reservation and canonical_id in self._active_commitments:
            self._active_commitments.pop(canonical_id)
            had_reservation = True

        from engine.orders.model import ConcreteCloseInstruction

        is_close_or_exit = (
            isinstance(event.original_order, ConcreteCloseInstruction)
            or event.original_order.action in ("SELL", "EXIT")
        )

        if not is_close_or_exit and not had_reservation and self._require_opening_reservation:
            self._accounting_integrity_breached = True
            raise VirtualAccountInvariantError(
                f"Opening BUY fill {canonical_id!r} missing required active premium reservation"
            )

        # Update position valuation sidecars (VA-7B)
        prior_keys = set(accounting_result.prior_snapshot.positions.keys())
        resulting_keys = set(accounting_result.resulting_snapshot.positions.keys())

        # Added positions: start UNAVAILABLE awaiting first valid BID
        for added_key in resulting_keys - prior_keys:
            self._position_valuations[added_key] = PositionValuationRecord(
                position_key=added_key,
                state=ValuationState.UNAVAILABLE,
                last_valid_mark_price=None,
                last_valid_mark_timestamp=None,
                latest_quote_timestamp=None,
                reason="awaiting_first_accepted_bid",
            )

        # Removed positions: drop sidecar valuation record
        for removed_key in prior_keys - resulting_keys:
            self._position_valuations.pop(removed_key, None)

        # Record in TradeLedger & assess canonical completed-trade costs (VA-13)
        self._accounting_sequence += 1
        event_key = LedgerEventKey(
            run_id=self._snapshot.account_id,
            accounting_sequence=self._accounting_sequence,
        )
        record = self._trade_ledger.record(event_key, accounting_result)
        if record is not None and self._cost_schedules:
            assessment = self._cost_calculator.assess(record, self._cost_schedules)
            self._cost_assessments.append(assessment)


        # Record processed fill evidence
        self._processed_fills[canonical_id] = (event, accounting_result)
        return accounting_result

    # ------------------------------------------------------------------
    # Live Mark-to-Market & Quote Valuation (VA-6 / VA-7 / VA-7A / VA-9)
    # ------------------------------------------------------------------

    def on_quote(self, quote: QuoteSnapshot) -> None:
        """Update live mark-to-market for matching open positions from an accepted QuoteSnapshot.

        Long options: mark_price = quote.bid_price (conservative executable BID).
        Invalid/missing BID: preserves last valid mark as STALE (or UNAVAILABLE if none).
        """
        if not isinstance(quote, QuoteSnapshot):
            raise TypeError("quote must be a QuoteSnapshot")

        matching_keys = [
            key for key in self._snapshot.positions.keys()
            if key.identity == quote.instrument_identity
        ]
        if not matching_keys:
            return

        quote_ts = quote.exchange_timestamp
        ref_time = self._last_market_time if (
            self._last_market_time is not None and self._last_market_time >= quote_ts
        ) else quote_ts

        bid_price = quote.bid_price

        # Missing or non-positive BID: cannot evaluate fresh LIVE mark
        if bid_price is None or bid_price <= 0:
            for key in matching_keys:
                existing_rec = self._position_valuations.get(key)
                if existing_rec is not None and existing_rec.last_valid_mark_price is not None:
                    self._position_valuations[key] = PositionValuationRecord(
                        position_key=key,
                        state=ValuationState.STALE,
                        last_valid_mark_price=existing_rec.last_valid_mark_price,
                        last_valid_mark_timestamp=existing_rec.last_valid_mark_timestamp,
                        latest_quote_timestamp=quote_ts,
                        reason="missing_executable_bid",
                    )
                else:
                    self._position_valuations[key] = PositionValuationRecord(
                        position_key=key,
                        state=ValuationState.UNAVAILABLE,
                        last_valid_mark_price=None,
                        last_valid_mark_timestamp=None,
                        latest_quote_timestamp=quote_ts,
                        reason="missing_executable_bid",
                    )
            return

        # Check temporal consistency (age)
        age = ref_time - quote_ts
        if age < timedelta(0):
            # Future-dated anomaly: fail closed
            for key in matching_keys:
                self._position_valuations[key] = PositionValuationRecord(
                    position_key=key,
                    state=ValuationState.UNAVAILABLE,
                    last_valid_mark_price=None,
                    last_valid_mark_timestamp=None,
                    latest_quote_timestamp=quote_ts,
                    reason="future_dated_quote",
                )
            return

        # Determine valuation state based on exact 5s boundary
        val_state = ValuationState.LIVE if age <= self._stale_mtm_threshold and self._is_feed_connected else ValuationState.STALE

        # Update matching PositionSnapshot marks and sidecar metadata
        positions_dict = dict(self._snapshot.positions)
        for key in matching_keys:
            existing = positions_dict[key]
            positions_dict[key] = PositionSnapshot(
                key=existing.key,
                quantity=existing.quantity,
                average_entry_price=existing.average_entry_price,
                contract_multiplier=existing.contract_multiplier,
                mark_price=bid_price,
                mark_timestamp=quote_ts,
                valuation_timeframe=existing.valuation_timeframe,
                price_increment=existing.price_increment,
                monetary_quantum=existing.monetary_quantum,
            )
            self._position_valuations[key] = PositionValuationRecord(
                position_key=key,
                state=val_state,
                last_valid_mark_price=bid_price,
                last_valid_mark_timestamp=quote_ts,
                latest_quote_timestamp=quote_ts,
                reason=None if val_state is ValuationState.LIVE else "quote_stale_or_feed_disconnected",
            )

        # Update snapshot positions and timestamp
        self._snapshot = AccountSnapshot(
            account_id=self._snapshot.account_id,
            currency=self._snapshot.currency,
            starting_capital=self._snapshot.starting_capital,
            cash=self._snapshot.cash,
            realized_pnl=self._snapshot.realized_pnl,
            positions=positions_dict,
            aggregate_exposure=self._snapshot.aggregate_exposure,
            as_of_timestamp=quote_ts,
            monetary_quantum=self._snapshot.monetary_quantum,
        )

    # ------------------------------------------------------------------
    # MarketTime Advancement & Disconnect Handling (VA-7C / VA-10)
    # ------------------------------------------------------------------

    def on_market_time(self, market_time: datetime) -> None:
        """Advance authoritative market time and evaluate 5s staleness without wall-clock timers.

        Monotonic market-time semantics (4C-2):
        - newer timestamp: updates market time and evaluates position staleness.
        - same timestamp: deterministic idempotent no-op.
        - older timestamp: raises ValueError (fails closed) to prevent backward time warp.
        """
        if not isinstance(market_time, datetime) or market_time.tzinfo is None:
            raise ValueError("market_time must be a timezone-aware datetime")

        if self._last_market_time is not None:
            if market_time == self._last_market_time:
                return  # Idempotent re-advancement
            if market_time < self._last_market_time:
                self._accounting_integrity_breached = True
                raise ValueError(
                    f"Market time cannot move backwards: received {market_time.isoformat()} "
                    f"after {self._last_market_time.isoformat()}"
                )

        self._last_market_time = market_time

        for key, rec in list(self._position_valuations.items()):
            if rec.last_valid_mark_timestamp is not None:
                age = market_time - rec.last_valid_mark_timestamp
                if age > self._stale_mtm_threshold:
                    self._position_valuations[key] = PositionValuationRecord(
                        position_key=key,
                        state=ValuationState.STALE,
                        last_valid_mark_price=rec.last_valid_mark_price,
                        last_valid_mark_timestamp=rec.last_valid_mark_timestamp,
                        latest_quote_timestamp=rec.latest_quote_timestamp,
                        reason="stale_by_market_time_advancement",
                    )
                elif age < timedelta(0):
                    self._position_valuations[key] = PositionValuationRecord(
                        position_key=key,
                        state=ValuationState.UNAVAILABLE,
                        last_valid_mark_price=None,
                        last_valid_mark_timestamp=None,
                        latest_quote_timestamp=rec.latest_quote_timestamp,
                        reason="future_dated_market_time",
                    )
                elif self._is_feed_connected:
                    self._position_valuations[key] = PositionValuationRecord(
                        position_key=key,
                        state=ValuationState.LIVE,
                        last_valid_mark_price=rec.last_valid_mark_price,
                        last_valid_mark_timestamp=rec.last_valid_mark_timestamp,
                        latest_quote_timestamp=rec.latest_quote_timestamp,
                        reason=None,
                    )
            else:
                self._position_valuations[key] = PositionValuationRecord(
                    position_key=key,
                    state=ValuationState.UNAVAILABLE,
                    last_valid_mark_price=None,
                    last_valid_mark_timestamp=None,
                    latest_quote_timestamp=rec.latest_quote_timestamp,
                    reason="awaiting_first_accepted_bid",
                )

    def on_feed_state_change(
        self,
        state: FeedConnectionState | bool | None = None,
        *,
        is_connected: bool | None = None,
    ) -> None:
        """Handle feed connection state changes (VA-10).

        DISCONNECTED / RECONNECTING -> all held positions STALE immediately.
        CONNECTED -> does NOT automatically restore LIVE. Fresh accepted quote required.
        """
        if state is not None:
            if isinstance(state, FeedConnectionState):
                conn = (state == FeedConnectionState.CONNECTED)
            elif isinstance(state, bool):
                conn = state
            else:
                raise TypeError("state must be FeedConnectionState or bool")
        elif is_connected is not None:
            conn = bool(is_connected)
        else:
            raise ValueError("state or is_connected must be provided")

        self._is_feed_connected = conn
        if not conn:
            for key, rec in list(self._position_valuations.items()):
                if rec.last_valid_mark_price is not None:
                    self._position_valuations[key] = PositionValuationRecord(
                        position_key=key,
                        state=ValuationState.STALE,
                        last_valid_mark_price=rec.last_valid_mark_price,
                        last_valid_mark_timestamp=rec.last_valid_mark_timestamp,
                        latest_quote_timestamp=rec.latest_quote_timestamp,
                        reason="feed_disconnected",
                    )
                else:
                    self._position_valuations[key] = PositionValuationRecord(
                        position_key=key,
                        state=ValuationState.UNAVAILABLE,
                        last_valid_mark_price=None,
                        last_valid_mark_timestamp=None,
                        latest_quote_timestamp=rec.latest_quote_timestamp,
                        reason="feed_disconnected",
                    )

    # ------------------------------------------------------------------
    # Entry Runtime Context Provider Gate (VA-11C)
    # ------------------------------------------------------------------

    def get_entry_runtime_context(
        self,
        decision_time: datetime,
        *,
        risk_day: RiskDay | None = None,
        protective_book: ProtectiveExitBook | None = None,
        prior_risk_state: Any = None,
        pending_risk_commitments: tuple[PendingRiskCommitment, ...] = (),
        cost_projection: Any = None,
    ) -> Any:
        """Provide fresh EntryRuntimeContext only when valuation is strictly LIVE."""
        if self._accounting_integrity_breached:
            raise VirtualAccountInvariantError("Accounting integrity is breached; entries blocked")

        if self.valuation_state is not ValuationState.LIVE:
            raise ValuationUnavailableError(
                f"Account valuation is {self.valuation_state.value}; entries blocked"
            )

        from engine.paper.coordinator import EntryRuntimeContext
        from engine.protective.runtime import ProtectiveExitBook
        from engine.risk.risk_manager import RiskDay

        rd = risk_day if risk_day is not None else RiskDay("NSE", decision_time.date())
        pb = protective_book if protective_book is not None else ProtectiveExitBook()

        return EntryRuntimeContext(
            risk_day=rd,
            snapshot=self._snapshot,
            protective_book=pb,
            current_net_equity=self.cost_adjusted_equity,
            starting_capital=self._snapshot.starting_capital,
            prior_risk_state=prior_risk_state,
            pending_commitments=pending_risk_commitments,
            cost_projection=cost_projection,
        )

