"""Phase 5 Slice 4B — Live paper trading coordinator.

Wires provider-neutral live feeds, quote caching, subscription management,
option contract selection, option entry risk bridging, and paper broker execution.

Key responsibilities:
- Pure preselection for dynamic option contract subscription.
- Immediate entry evaluation when live quotes are present in cache.
- Bar-bound pending entry attempt registration when quotes are missing.
- Fresh runtime risk-state sampling at execution / deferred resume time.
- Deterministic multi-attempt processing order on accepted quotes.
- Safe coordinator-local multi-intent subscription claim groups.
- Layer 1 deduplication preservation (no duplicate broker event dispatch).
- Complete fail-closed handling on feed disconnects, catalog drift, and expiry.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from engine.audit.model import (
    AUDIT_ENVELOPE_SCHEMA_VERSION,
    AuditEvent,
    AuditEventFamily,
    AuditEventType,
    canonical_json_dumps,
    derive_audit_event_id,
    recorded_at_utc_now,
)
from engine.audit.log import record_runtime_error
from engine.reconciliation.paper.engine import (
    PaperReconciliationEngine,
    ReconciliationFinding,
    ReconciliationHealth,
    ReconciliationPersistedSnapshot,
    ReconciliationReport,
    ReconciliationRuntimeSnapshot,
    ReconciliationSeverity,
    ReconciliationStatus,
)
from engine.execution.paper_broker import (
    BrokerCancelResult,
    BrokerOrderRecord,
    BrokerQuoteEvent,
    BrokerSubmissionResult,
    BrokerTerminalEvent,
    SimulatedPaperBroker,
)

from engine.execution.quote import QuoteSnapshot
from engine.data.feeds.live_feed import (
    FeedConnectionState,
    LiveMarketDataFeed,
    LiveQuoteEvent,
    SubscriptionOwnerKey,
)
from engine.data.feeds.quote_cache import (
    LatestQuoteCache,
    QuoteCacheResult,
    QuoteCacheStatus,
)
from engine.data.feeds.subscription import (
    OptionSubscriptionManager,
    deterministic_subscription_order,
)
from engine.core.numeric import as_decimal
from engine.options.catalog import InstrumentCatalog
from engine.reporting.paper_summaries import IST_CALENDAR
from engine.options.policy import OptionSelectionPolicy
from engine.options.selector import (
    OptionSelectionRejection,
    OptionSelector,
    ResolvedOptionEntry,
)
from engine.orders.lifecycle import OrderLifecycleState
from engine.orders.model import ConcreteCloseInstruction, OrderRequest, OrderType, TimeInForce
from engine.paper.option_bridge import (
    OptionEntryBridge,
    OptionEntryRejection,
    OptionEntryResult,
)
from engine.portfolio.accounting import PortfolioAccount
from engine.portfolio.model import AccountSnapshot, InstrumentIdentity, InstrumentSpecification, PositionKey
from engine.portfolio.virtual_account import (
    ValuationState,
    ValuationUnavailableError,
    VirtualAccountInvariantError,
    VirtualPaperAccount,
)
from engine.persistence.sqlite_store import (
    PersistenceHealth,
    StrategyStateTransition,
    _identity_canonical_key,
    _position_key_to_dict,
)
from engine.protective.runtime import ProtectiveExitBook
from engine.protective.live import (
    LiveProtectiveEvaluator,
    LiveProtectivePendingClose,
    LiveProtectiveTrigger,
    StrategyCallbackFailure,
)
from engine.protective.plan import PreEntryProtectivePlan, materialize_protective_plan
from engine.protective.runtime_policy import StrategyExitEvidence, StrategyExitDecision
from engine.risk.risk_manager import (
    PendingRiskCommitment,
    RiskDay,
    RiskGateState,
    RiskOutcome,
    entry_intent_identity,
)
from engine.safety.safety import (
    KillSwitchState,
    SafetyAlert,
    SafetyManager,
    SafetyResumeResult,
    SafetyState,
    SafetyTransitionResult,
)
from engine.orchestration.signal_intake import SignalIntent, signal_intent_identity

logger = logging.getLogger(__name__)

__all__ = [
    "EntryRuntimeContext",
    "EntryRuntimeContextProvider",
    "CoordinatorOutcome",
    "CoordinatorEntryResult",
    "LiveQuoteProcessingResult",
    "PendingOptionEntryAttempt",
    "StrategyExitPendingClose",
    "LivePaperCoordinator",
]


# ======================================================================
# 1. Runtime Context & Types
# ======================================================================


@dataclass(frozen=True)
class EntryRuntimeContext:
    """Fresh snapshot of mutable account and risk state required for pre-order risk gate evaluation."""

    risk_day: RiskDay
    snapshot: AccountSnapshot
    protective_book: ProtectiveExitBook
    current_net_equity: Decimal
    starting_capital: Decimal
    prior_risk_state: Any = None
    pending_commitments: tuple[Any, ...] = ()
    cost_projection: Any = None

    def __post_init__(self) -> None:
        if not isinstance(self.risk_day, RiskDay):
            raise TypeError("risk_day must be a RiskDay")
        if not isinstance(self.snapshot, AccountSnapshot):
            raise TypeError("snapshot must be an AccountSnapshot")
        if not isinstance(self.protective_book, ProtectiveExitBook):
            raise TypeError("protective_book must be a ProtectiveExitBook")
        for name in ("current_net_equity", "starting_capital"):
            val = as_decimal(getattr(self, name), name)
            if val <= 0:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, val)


EntryRuntimeContextProvider = Callable[[datetime], EntryRuntimeContext]


class CoordinatorOutcome(str, Enum):
    """Outcome of processing a signal through LivePaperCoordinator."""

    SUBMITTED = "SUBMITTED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class CoordinatorEntryResult:
    """Immutable public result of processing a signal through LivePaperCoordinator."""

    outcome: CoordinatorOutcome
    intent_id: str
    selected_identity: InstrumentIdentity | None = None
    submission_result: BrokerSubmissionResult | None = None
    bridge_result: OptionEntryResult | None = None
    rejection_reason: str | None = None
    rejection_evidence: Any = None


@dataclass(frozen=True)
class LiveQuoteProcessingResult:
    """Immutable result of processing one incoming live quote event through the coordinator."""

    quote_result: QuoteCacheResult
    broker_events: tuple[BrokerTerminalEvent, ...]
    entry_results: tuple[CoordinatorEntryResult, ...]
    protective_triggers: tuple[LiveProtectiveTrigger, ...] = ()


@dataclass(frozen=True)
class PendingOptionEntryAttempt:
    """Immutable pre-order entry attempt awaiting first authoritative live quote."""

    intent: SignalIntent
    policy: OptionSelectionPolicy
    underlying_price: Decimal
    selection_timestamp: datetime
    selected_entry: ResolvedOptionEntry
    owner: SubscriptionOwnerKey
    expiry_boundary: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.intent, SignalIntent):
            raise TypeError("intent must be a SignalIntent")
        if not isinstance(self.policy, OptionSelectionPolicy):
            raise TypeError("policy must be an OptionSelectionPolicy")
        price = as_decimal(self.underlying_price, "underlying_price")
        if price <= 0:
            raise ValueError("underlying_price must be positive")
        object.__setattr__(self, "underlying_price", price)
        if not isinstance(self.selection_timestamp, datetime) or self.selection_timestamp.tzinfo is None:
            raise ValueError("selection_timestamp must be a timezone-aware datetime")
        if not isinstance(self.selected_entry, ResolvedOptionEntry):
            raise TypeError("selected_entry must be a ResolvedOptionEntry")
        if not isinstance(self.owner, SubscriptionOwnerKey):
            raise TypeError("owner must be a SubscriptionOwnerKey")
        if not isinstance(self.expiry_boundary, datetime) or self.expiry_boundary.tzinfo is None:
            raise ValueError("expiry_boundary must be a timezone-aware datetime")
        if self.expiry_boundary <= self.selection_timestamp:
            raise ValueError("expiry_boundary must be strictly after selection_timestamp")


class _IntentLifecycle(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    TERMINAL_REJECTED = "TERMINAL_REJECTED"


@dataclass(frozen=True)
class StrategyExitPendingClose:
    """Immutable record of an in-flight GENERIC (non-protective) strategy close order.

    This is the generic close-provenance authority for STRATEGY_EXIT. It carries
    only canonical identity: exact PositionKey, broker order linkage, and the
    authoritative market timestamp of the exit decision. It deliberately has NO
    protective semantics — no ProtectiveExitKind, no protective_id, no trigger
    price — and never touches ``protective_pending_closes``.

    Durable persistence is the generic ``broker_orders`` row (QUEUED EXIT order
    with full owner provenance in ``original_order_json``); this in-memory
    record is the duplicate-close lock and terminal-routing key.
    """

    position_key: PositionKey
    order_id: str
    broker_order_identity: str
    requested_market_timestamp: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")
        if not isinstance(self.order_id, str) or not self.order_id.strip():
            raise ValueError("order_id must be a non-empty string")
        if not isinstance(self.broker_order_identity, str) or not self.broker_order_identity.strip():
            raise ValueError("broker_order_identity must be a non-empty string")
        if (
            not isinstance(self.requested_market_timestamp, datetime)
            or self.requested_market_timestamp.tzinfo is None
        ):
            raise ValueError("requested_market_timestamp must be a timezone-aware datetime")


def _coerce_intent_lifecycle(value: object) -> _IntentLifecycle:
    """Map durable entry-intent lifecycle evidence onto the runtime vocabulary.

    P1-05 / ADR §119: hydrated ``entry_intents`` carry the persisted broker
    lifecycle (``SUBMITTED``, ``FILLED``, ``CANCELLED``, ``EXPIRED``,
    ``REJECTED``).  Only the in-flight states have a runtime meaning; every
    already-terminal durable state restores as terminal so D11 duplicate
    protection still recognises the intent without reviving it.
    """
    if isinstance(value, _IntentLifecycle):
        return value
    text = str(value).strip().upper()
    if text in ("PENDING", "SUBMITTED"):
        return _IntentLifecycle(text)
    return _IntentLifecycle.TERMINAL_REJECTED


@dataclass
class _SubscriptionClaimGroup:
    dependent_intent_ids: set[str]
    manager_owner_preexisting: bool


# ======================================================================
# 2. LivePaperCoordinator Implementation
# ======================================================================


class LivePaperCoordinator:
    """Live paper trading coordinator wiring feed, cache, selector, bridge, broker, and virtual account."""

    def __init__(
        self,
        *,
        catalog: InstrumentCatalog,
        live_feed: LiveMarketDataFeed,
        quote_cache: LatestQuoteCache,
        subscription_manager: OptionSubscriptionManager,
        option_bridge: OptionEntryBridge,
        paper_broker: SimulatedPaperBroker,
        runtime_context_provider: EntryRuntimeContextProvider | None = None,
        virtual_account: VirtualPaperAccount | None = None,
        protective_evaluator: LiveProtectiveEvaluator | None = None,
        protective_book: ProtectiveExitBook | None = None,
        persistence_store: Any | None = None,
        retained_protective_plans: Mapping[str, tuple[PreEntryProtectivePlan, Decimal, str | None]] | None = None,
        intent_lifecycles: Mapping[str, _IntentLifecycle | str] | None = None,
        strategy_exit_pending_closes: Sequence[StrategyExitPendingClose] | None = None,
        safety_manager: SafetyManager | None = None,
        on_safety_alert: Callable[[SafetyAlert], None] | None = None,
        kill_switch_state: KillSwitchState | None = None,
        pending_risk_commitments: Sequence[PendingRiskCommitment] | None = None,
        risk_gate_state: RiskGateState | None = None,
        q93_month_finalizer: Callable[[int, int], None] | None = None,
        initial_q93_last_observed_ist_month: tuple[int, int] | None = None,
        q93_month_persister: Callable[[int, int], None] | None = None,
        phase8_safety: Any | None = None,
    ) -> None:
        if not isinstance(catalog, InstrumentCatalog):
            raise TypeError("catalog must be an InstrumentCatalog")
        if not isinstance(live_feed, LiveMarketDataFeed):
            raise TypeError("live_feed must implement LiveMarketDataFeed")
        if not isinstance(quote_cache, LatestQuoteCache):
            raise TypeError("quote_cache must be a LatestQuoteCache")
        if not isinstance(subscription_manager, OptionSubscriptionManager):
            raise TypeError("subscription_manager must be an OptionSubscriptionManager")
        if not isinstance(option_bridge, OptionEntryBridge):
            raise TypeError("option_bridge must be an OptionEntryBridge")
        if not isinstance(paper_broker, SimulatedPaperBroker):
            raise TypeError("paper_broker must be a SimulatedPaperBroker")
        if virtual_account is not None and not isinstance(virtual_account, VirtualPaperAccount):
            raise TypeError("virtual_account must be a VirtualPaperAccount")

        # Phase 8 / ADR §128.1/§128.4: optional auto-halt bridge.  When wired,
        # authoritative daily-loss gate outcomes and the FIRST authoritative
        # ReconciliationHealth.FAILED escalate through this controller to the
        # canonical global kill switch (§128.7 unified authority).
        self._phase8_safety = phase8_safety
        self._shutdown_in_progress = False

        if protective_evaluator is not None:
            if not isinstance(protective_evaluator, LiveProtectiveEvaluator):
                raise TypeError("protective_evaluator must be a LiveProtectiveEvaluator")
            self._protective_evaluator = protective_evaluator
        elif protective_book is not None:
            if not isinstance(protective_book, ProtectiveExitBook):
                raise TypeError("protective_book must be a ProtectiveExitBook")
            self._protective_evaluator = LiveProtectiveEvaluator(protective_book)
        else:
            self._protective_evaluator = LiveProtectiveEvaluator()

        self._retained_plans: dict[str, tuple[PreEntryProtectivePlan, Decimal, str | None]] = (
            dict(retained_protective_plans) if retained_protective_plans else {}
        )
        # Generic (non-protective) strategy-exit pending-close authority.
        # Duplicate-close lock keyed by PositionKey + terminal-routing key by
        # order_id. Hydrated at restart from durable broker_orders evidence
        # (QUEUED EXIT rows) by the runner — never from protective tables.
        self._strategy_pending_by_position: dict[PositionKey, StrategyExitPendingClose] = {}
        self._strategy_pending_by_order_id: dict[str, StrategyExitPendingClose] = {}
        if strategy_exit_pending_closes is not None:
            for sp in strategy_exit_pending_closes:
                if not isinstance(sp, StrategyExitPendingClose):
                    raise TypeError("strategy_exit_pending_closes must contain StrategyExitPendingClose values")
                if sp.position_key in self._strategy_pending_by_position:
                    raise ValueError(f"duplicate strategy exit pending close for position: {sp.position_key}")
                if sp.order_id in self._strategy_pending_by_order_id:
                    raise ValueError(f"duplicate strategy exit pending close order_id: {sp.order_id}")
                self._strategy_pending_by_position[sp.position_key] = sp
                self._strategy_pending_by_order_id[sp.order_id] = sp
        # Exact RiskGate evidence for approved opening entries that have not
        # reached a terminal broker outcome.  This is deliberately separate
        # from VirtualPaperAccount's premium-cash commitments: Q59/Q60 require
        # the gate-produced nominal stop risk, which cash reservations do not
        # own or derive.
        self._pending_risk_commitments_by_intent: dict[str, PendingRiskCommitment] = {}
        if pending_risk_commitments:
            for commitment in pending_risk_commitments:
                if not isinstance(commitment, PendingRiskCommitment):
                    raise TypeError("pending_risk_commitments must contain PendingRiskCommitment values")
                existing = self._pending_risk_commitments_by_intent.get(commitment.entry_identity)
                if existing is not None and existing != commitment:
                    raise ValueError("conflicting hydrated PendingRiskCommitment for entry intent")
                self._pending_risk_commitments_by_intent[commitment.entry_identity] = commitment
        # P1-05 / ADR §119.2 (OD-B): durable daily risk evidence restored from
        # persistence and supplied back to the gate as ``prior_risk_state``.
        if risk_gate_state is not None and not isinstance(risk_gate_state, RiskGateState):
            raise TypeError("risk_gate_state must be a RiskGateState")
        self._risk_gate_state: RiskGateState | None = risk_gate_state
        self._persistence_store = persistence_store
        self._persistence_failed = False
        # P1-05 / ADR §119.1 (OD-A): once the durable breach flag is already
        # true there is nothing further to write; a hydrated breach must not
        # be re-persisted on every subsequent event.
        self._integrity_breach_persisted: bool = bool(
            virtual_account is not None and virtual_account.accounting_integrity_breached
        )
        self._latest_market_timestamp: datetime | None = None
        # Phase 8 P1 (§128.11): latest MARKET-DATA evidence timestamp
        # (accepted quotes), tracked separately from the advancing market
        # clock so deterministic staleness evaluation compares a TRUE data
        # age against heartbeat_timeout_seconds.
        self._latest_quote_market_timestamp: datetime | None = None
        self._last_canonical_session_date: datetime.date | None = None
        # Phase 6 / ADR §124.3/§124.5 (P1-01 repair): last observed IST
        # (year, month) is HYDRATED from the durable paper_metadata marker via
        # the runner; None only when no marker exists yet (bootstrap). The
        # persister callback durably commits markers BEFORE in-memory advance.
        self._q93_last_observed_ist_month: tuple[int, int] | None = (
            initial_q93_last_observed_ist_month
        )
        self._q93_month_finalizer = q93_month_finalizer
        self._q93_month_persister = q93_month_persister
        self._has_received_quote: bool = False
        self._reconnected_waiting_for_quote: bool = False
        self._feed_ever_disconnected: bool = (live_feed.connection_state is FeedConnectionState.DISCONNECTED)
        self._feed_connected_once: bool = (
            live_feed.connection_state is FeedConnectionState.CONNECTED
        )
        self._catalog = catalog
        self._live_feed = live_feed
        self._quote_cache = quote_cache
        self._subscription_manager = subscription_manager
        self._option_bridge = option_bridge
        self._paper_broker = paper_broker
        self._virtual_account = virtual_account

        self._reconciliation_engine = PaperReconciliationEngine()
        self._reconciliation_health: ReconciliationHealth = ReconciliationHealth.UNKNOWN
        self._latest_reconciliation_report: ReconciliationReport | None = None

        self._safety = safety_manager or SafetyManager(
            initial_kill_state=kill_switch_state,
            on_alert=on_safety_alert,
        )
        if kill_switch_state is not None:
            self._safety.restore_kill_state(kill_switch_state)
            if kill_switch_state.active:
                pending_objs = (
                    self._paper_broker.pending_orders.values()
                    if isinstance(self._paper_broker.pending_orders, dict)
                    else (
                        self._paper_broker.pending_orders()
                        if callable(self._paper_broker.pending_orders)
                        else self._paper_broker.pending_orders.values()
                    )
                )
                cleaned_count = 0
                for po in list(pending_objs):
                    ts = self._latest_market_timestamp or po.submission_market_timestamp
                    self.cancel_order(po.order_id, ts)
                    cleaned_count += 1

                if cleaned_count > 0 and self._persistence_store is not None and self.is_persistence_healthy:
                    try:
                        acc_ident = self._virtual_account.account_id if self._virtual_account else "unknown"
                        cleanup_ev = AuditEvent(
                            event_id=derive_audit_event_id(
                                event_family=AuditEventFamily.RESTART_HYDRATION,
                                event_type=AuditEventType.STARTUP_KILL_CLEANUP_COMPLETED,
                                aggregate_type="SAFETY",
                                aggregate_identity=acc_ident,
                                state_generation=None,
                                transaction_event_ordinal=0,
                            ),
                            event_family=AuditEventFamily.RESTART_HYDRATION.value,
                            event_type=AuditEventType.STARTUP_KILL_CLEANUP_COMPLETED.value,
                            aggregate_type="SAFETY",
                            aggregate_identity=acc_ident,
                            market_timestamp=self._latest_market_timestamp,
                            recorded_at_utc=recorded_at_utc_now(),
                            payload_json=canonical_json_dumps({
                                "cleaned_orders_count": cleaned_count,
                            }),
                        )
                        self._persistence_store.append_audit_events([cleanup_ev])
                    except Exception:
                        pass

        # Single-authority runtime context resolution
        if virtual_account is not None:
            if runtime_context_provider is not None:
                if (
                    getattr(runtime_context_provider, "__self__", None) is not virtual_account
                    and runtime_context_provider != virtual_account.get_entry_runtime_context
                ):
                    raise ValueError(
                        "Conflicting runtime_context_provider supplied with virtual_account. "
                        "When virtual_account is provided, runtime context must be derived solely from virtual_account."
                    )
            self._runtime_context_provider = virtual_account.get_entry_runtime_context
        else:
            if runtime_context_provider is None or not callable(runtime_context_provider):
                raise TypeError("runtime_context_provider must be callable when virtual_account is None")
            self._runtime_context_provider = runtime_context_provider

        # Coordinator-local state
        self._subscription_claims: dict[tuple[SubscriptionOwnerKey, InstrumentIdentity], _SubscriptionClaimGroup] = {}
        self._pending_by_intent: dict[str, PendingOptionEntryAttempt] = {}
        self._pending_intents_by_identity: dict[InstrumentIdentity, set[str]] = {}
        self._intent_lifecycle: dict[str, _IntentLifecycle] = (
            {k: _coerce_intent_lifecycle(v) for k, v in intent_lifecycles.items()}
            if intent_lifecycles
            else {}
        )

        # B2: runtime strategy-state generation tracking for atomic coupling.
        # Initialized from hydrated state_generation values; updated after each
        # successful atomic persistence that includes a strategy-state advance.
        self._strategy_state_generation: dict[tuple[str, str], int] = {}
        if persistence_store is not None and hasattr(persistence_store, 'load_state'):
            try:
                hydrated_state = persistence_store.load_state()
                for owner, durable in hydrated_state.strategy_states.items():
                    self._strategy_state_generation[
                        (owner.strategy_id, owner.strategy_version)
                    ] = durable.state_generation
            except Exception:
                pass

        # Register live quote consumer listener & optional feed listeners
        self._live_feed.add_quote_listener(self.on_live_quote)
        if hasattr(self._live_feed, "add_market_time_listener"):
            self._live_feed.add_market_time_listener(self._on_market_time_event)
        if hasattr(self._live_feed, "add_state_listener"):
            self._live_feed.add_state_listener(self.on_feed_state_change)

        # Execute initial startup reconciliation
        try:
            self._run_reconciliation_internal(is_restart_hydration=True, operator_requested=False)
        except Exception as exc:
            logger.warning("Startup reconciliation check failed: %s", exc)

    @property
    def reconciliation_health(self) -> ReconciliationHealth:
        """Active coordinator-level reconciliation health state."""
        return self._reconciliation_health

    @property
    def latest_reconciliation_report(self) -> ReconciliationReport | None:
        """Most recent reconciliation evaluation report."""
        return self._latest_reconciliation_report

    @property
    def is_reconciliation_healthy(self) -> bool:
        """Return True if and only if reconciliation health is MATCHED."""
        return self._reconciliation_health == ReconciliationHealth.MATCHED

    def run_reconciliation(self, *, operator_requested: bool = True) -> ReconciliationReport:
        """Public operator execution of independent reconciliation."""
        return self._run_reconciliation_internal(operator_requested=operator_requested)

    def _on_state_transition_committed(self) -> None:
        """Trigger post-transaction reconciliation after a state-modifying transaction commits."""
        if self._reconciliation_health != ReconciliationHealth.FAILED:
            self._reconciliation_health = ReconciliationHealth.DIRTY
        try:
            self._run_reconciliation_internal(operator_requested=False)
        except Exception as exc:
            logger.error("Post-transaction reconciliation failed: %s", exc)

    def _run_reconciliation_internal(
        self,
        *,
        is_restart_hydration: bool = False,
        operator_requested: bool = False,
    ) -> ReconciliationReport:
        """Execute reconciliation inside coordinator and update reconciliation health state."""
        pending_orders, terminal_orders = self._paper_broker.get_order_snapshots()
        account_snapshot = self._virtual_account.snapshot if self._virtual_account else AccountSnapshot(
            account_id="unknown",
            currency="INR",
            starting_capital=Decimal("0"),
            cash=Decimal("0"),
            realized_pnl=Decimal("0"),
            positions={},
            aggregate_exposure={},
            as_of_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            monetary_quantum=Decimal("0.01"),
        )
        positions = self._virtual_account.positions if self._virtual_account else {}
        active_commitments = self._virtual_account.active_commitments if self._virtual_account else ()
        processed_fills = self._virtual_account.processed_fills if self._virtual_account else {}
        completed_trades = self._virtual_account.trade_ledger.completed_trades() if (self._virtual_account and self._virtual_account.trade_ledger) else ()
        cost_assessments = self._virtual_account.cost_assessments if self._virtual_account else ()
        protective_exits = tuple(self._protective_evaluator.book.exits.values()) if (self._protective_evaluator and self._protective_evaluator.book) else ()
        protective_pending_closes = tuple(self._protective_evaluator.pending_closes.values()) if self._protective_evaluator else ()

        acc_id = self._virtual_account.account_id if self._virtual_account else "unknown"
        sess_id = getattr(self._persistence_store, "paper_session_id", "session_unknown") if self._persistence_store else "session_in_memory"
        state_gen = self._persistence_store.state_generation if self._persistence_store else 0

        # Reconciliation receives the same exact RiskGate evidence used by
        # runtime Q59/Q60, never an approximation reconstructed from premium
        # cash reservation data.
        pending_risk_commitments = tuple(self._pending_risk_commitments_by_intent.values())

        runtime_snapshot = ReconciliationRuntimeSnapshot(
            account_id=acc_id,
            paper_session_id=sess_id,
            state_generation=state_gen,
            market_timestamp=self._latest_market_timestamp,
            is_restart_hydration=is_restart_hydration,
            broker_pending_orders=pending_orders,
            broker_terminal_orders=terminal_orders,
            account_snapshot=account_snapshot,
            positions=positions,
            active_commitments=active_commitments,
            processed_fills=processed_fills,
            completed_trades=completed_trades,
            cost_assessments=cost_assessments,
            protective_exits=protective_exits,
            protective_pending_closes=protective_pending_closes,
            pending_risk_commitments=pending_risk_commitments,
        )

        if self._persistence_store is not None and self.is_persistence_healthy:
            persisted_snapshot = self._persistence_store.get_reconciliation_snapshot()
        else:
            fills_tuples = []
            if self._virtual_account:
                for k, v in self._virtual_account.processed_fills.items():
                    term_ev, acc_res = v
                    ex_res = term_ev.execution_result
                    fp = getattr(term_ev, "broker_order_identity", k)
                    fills_tuples.append((
                        k,
                        term_ev.order_id,
                        term_ev.lifecycle_state.value,
                        getattr(term_ev.instrument_identity, "instrument", str(term_ev.instrument_identity)),
                        ex_res.fill_price if ex_res and ex_res.fill_price is not None else Decimal("0"),
                        ex_res.filled_quantity if ex_res and ex_res.filled_quantity is not None else Decimal("0"),
                        getattr(ex_res, "fee", Decimal("0")) if ex_res else Decimal("0"),
                        term_ev.market_timestamp,
                        fp,
                    ))
            persisted_snapshot = ReconciliationPersistedSnapshot(
                state_generation=state_gen,
                account_state=account_snapshot,
                positions=positions,
                premium_commitments=active_commitments,
                broker_orders=pending_orders + tuple(
                    BrokerOrderRecord(
                        order_id=te.order_id,
                        broker_order_identity=te.broker_order_identity,
                        original_order=te.original_order,
                        instrument_identity=te.instrument_identity,
                        lifecycle_state=te.lifecycle_state,
                        submission_market_timestamp=te.market_timestamp,
                        eligibility_timestamp=te.market_timestamp,
                        reference_price=te.execution_result.fill_price if te.execution_result and te.execution_result.fill_price else Decimal("0"),
                        stop_triggered=False,
                        stop_limit_activated=False,
                    )
                    for te in terminal_orders
                ),
                processed_fills=tuple(fills_tuples),
                protective_exits=protective_exits,
                protective_pending_closes=protective_pending_closes,
                trade_records=completed_trades,
                cost_assessments=cost_assessments,
            )

        report_id = str(uuid.uuid4())
        evaluated_utc = recorded_at_utc_now()
        report = self._reconciliation_engine.reconcile(
            runtime_snapshot,
            persisted_snapshot,
            report_id=report_id,
            evaluated_at_utc=evaluated_utc,
        )

        if self._persistence_store is not None and self.is_persistence_healthy:
            try:
                self._persistence_store.save_reconciliation_report(report)
            except Exception as exc:
                self._persistence_failed = True
                logger.critical("Failed to persist reconciliation report: %s", exc, exc_info=True)
                self._reconciliation_health = ReconciliationHealth.FAILED
                self._notify_phase8_reconciliation_failed()
                raise

        self._latest_reconciliation_report = report

        if report.status != ReconciliationStatus.MATCHED:
            if self._reconciliation_health != ReconciliationHealth.FAILED:
                self._reconciliation_health = ReconciliationHealth.FAILED
                # ADR §128.4 (OD-4): first authoritative FAILED escalates to
                # the global kill switch immediately — no grace counter.
                self._notify_phase8_reconciliation_failed()
        else:
            if self._reconciliation_health == ReconciliationHealth.FAILED:
                if operator_requested:
                    self._reconciliation_health = ReconciliationHealth.MATCHED
                    if self._phase8_safety is not None:
                        # A clean authoritative reconciliation establishes
                        # eligibility only; the canonical global latch still
                        # requires the explicit unified resume below.
                        self._phase8_safety.observe_reconciliation_resolved()
                else:
                    pass
            else:
                self._reconciliation_health = ReconciliationHealth.MATCHED

        return report

    def can_execute_protective_exit(self, position_key: PositionKey) -> bool:
        """Check if autonomous protective execution is permitted for a specific PositionKey."""
        if self._reconciliation_health == ReconciliationHealth.FAILED and self._latest_reconciliation_report:
            pkey_ident = _identity_canonical_key(position_key.identity)
            return not any(
                (f.severity == ReconciliationSeverity.CRITICAL and (
                    f.aggregate_identity in (pkey_ident, str(position_key), position_key.identity.instrument)
                ))
                for f in self._latest_reconciliation_report.findings
            )
        return True

    # ------------------------------------------------------------------
    # Generic Strategy-Exit Pending-Close Authority
    # ------------------------------------------------------------------

    @property
    def strategy_exit_pending_closes(self) -> Mapping[PositionKey, StrategyExitPendingClose]:
        """Active in-flight generic strategy close orders keyed by PositionKey."""
        return dict(self._strategy_pending_by_position)

    def has_pending_strategy_exit(self, position_key: PositionKey) -> bool:
        """Check if an in-flight generic strategy close exists for the PositionKey."""
        if not isinstance(position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")
        return position_key in self._strategy_pending_by_position

    def get_pending_strategy_exit(self, position_key: PositionKey) -> StrategyExitPendingClose | None:
        """Retrieve the in-flight generic strategy close for the PositionKey if one exists."""
        if not isinstance(position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")
        return self._strategy_pending_by_position.get(position_key)

    def _register_strategy_pending_close(self, pending: StrategyExitPendingClose) -> None:
        """Register a newly submitted generic strategy close order (duplicate lock)."""
        if not isinstance(pending, StrategyExitPendingClose):
            raise TypeError("pending must be a StrategyExitPendingClose")
        if pending.position_key in self._strategy_pending_by_position:
            raise ValueError(f"strategy exit close already active for position: {pending.position_key}")
        if pending.order_id in self._strategy_pending_by_order_id:
            raise ValueError(f"duplicate strategy exit close order_id: {pending.order_id}")
        self._strategy_pending_by_position[pending.position_key] = pending
        self._strategy_pending_by_order_id[pending.order_id] = pending

    def _clear_strategy_pending_by_order_id(self, order_id: str) -> StrategyExitPendingClose | None:
        """Clear the generic strategy close record for a terminal order_id."""
        if not isinstance(order_id, str) or not order_id.strip():
            raise ValueError("order_id must be a non-empty string")
        pending = self._strategy_pending_by_order_id.pop(order_id, None)
        if pending is not None:
            self._strategy_pending_by_position.pop(pending.position_key, None)
        return pending

    @property
    def safety_state(self) -> SafetyState:
        """Derived effective safety state per frozen precedence."""
        feed_state = self._live_feed.connection_state
        persistence_health = (
            self._persistence_store.health
            if self._persistence_store is not None
            else PersistenceHealth.HEALTHY
        )
        if self._persistence_failed:
            persistence_health = PersistenceHealth.FAILED
        breached = (
            getattr(self._virtual_account, "accounting_integrity_breached", False)
            if self._virtual_account is not None
            else False
        )
        has_fresh = True
        if self._virtual_account is not None and self._virtual_account.positions:
            has_fresh = (self._virtual_account.valuation_state == ValuationState.LIVE)
        elif self._reconnected_waiting_for_quote:
            has_fresh = self._has_received_quote
        return self._safety.derive_effective_state(
            feed_state=feed_state,
            persistence_health=persistence_health,
            accounting_integrity_breached=breached,
            has_fresh_market_evidence=has_fresh,
        )

    @property
    def safety_manager(self) -> SafetyManager:
        """Active encapsulated SafetyManager."""
        return self._safety

    @property
    def latest_market_timestamp(self) -> datetime | None:
        """Latest authoritative market timestamp observed."""
        return self._latest_market_timestamp

    @property
    def persistence_store(self) -> Any | None:
        """Active SQLite paper state persistence store."""
        return self._persistence_store

    @property
    def is_persistence_healthy(self) -> bool:
        """Check if persistence is healthy (or unconfigured)."""
        if self._persistence_failed:
            return False
        if self._persistence_store is not None:
            return getattr(self._persistence_store, "is_healthy", True)
        return True

    @property
    def retained_plans(self) -> Mapping[str, tuple[PreEntryProtectivePlan, Decimal, str | None]]:
        """Active retained pre-entry protective plans keyed by broker order_id."""
        return dict(self._retained_plans)

    @property
    def intent_lifecycles(self) -> Mapping[str, _IntentLifecycle]:
        """Entry intent lifecycle states."""
        return dict(self._intent_lifecycle)

    @property
    def protective_evaluator(self) -> LiveProtectiveEvaluator:
        """Active live protective evaluator."""
        return self._protective_evaluator

    @property
    def protective_book(self) -> ProtectiveExitBook:
        """Underlying protective exit book."""
        return self._protective_evaluator.book

    @property
    def pending_risk_commitments(self) -> Mapping[str, PendingRiskCommitment]:
        """Exact live RiskGate commitments, keyed by entry-intent identity."""
        return dict(self._pending_risk_commitments_by_intent)

    @staticmethod
    def _pending_risk_commitment_from_approval(
        *,
        entry_identity: str,
        bridge_result: OptionEntryResult,
    ) -> PendingRiskCommitment:
        """Freeze the exact RiskGate approval evidence without recomputation."""
        gate_result = bridge_result.gate_result
        if gate_result.nominal_stop_risk is None:
            raise ValueError("approved option entry is missing nominal stop-risk evidence")
        return PendingRiskCommitment(
            entry_identity=entry_identity,
            intended_position_key=bridge_result.plan.intended_position_key,
            approved_quantity=bridge_result.instruction.quantity,
            nominal_stop_risk=gate_result.nominal_stop_risk,
        )

    def _retain_pending_risk_commitment(self, commitment: PendingRiskCommitment) -> None:
        """Retain one exact pending-risk commitment by its canonical identity."""
        existing = self._pending_risk_commitments_by_intent.get(commitment.entry_identity)
        if existing is not None:
            if existing != commitment:
                raise ValueError("conflicting PendingRiskCommitment for entry intent")
            return
        self._pending_risk_commitments_by_intent[commitment.entry_identity] = commitment

    def _release_pending_risk_commitment(self, entry_identity: str) -> None:
        """Idempotently remove only the matching terminal opening commitment."""
        self._pending_risk_commitments_by_intent.pop(entry_identity, None)

    @staticmethod
    def _entry_identity_for_terminal_event(terminal_event: BrokerTerminalEvent) -> str:
        """Recover the canonical opening-entry identity from terminal evidence."""
        order = terminal_event.original_order
        return entry_intent_identity(
            strategy_id=order.strategy_id,
            strategy_version=order.strategy_version,
            identity=terminal_event.instrument_identity,
            timeframe=order.timeframe,
            originating_timestamp=order.originating_timestamp,
        )

    def _get_runtime_context(self, decision_time: datetime) -> EntryRuntimeContext:
        """Sample fresh runtime context with exact currently pending risk evidence."""
        pending = tuple(self._pending_risk_commitments_by_intent.values())
        try:
            return self._runtime_context_provider(
                decision_time,
                protective_book=self.protective_book,
                pending_risk_commitments=pending,
                prior_risk_state=self._risk_gate_state,
            )
        except TypeError:
            try:
                return self._runtime_context_provider(
                    decision_time,
                    protective_book=self.protective_book,
                    pending_risk_commitments=pending,
                )
            except TypeError:
                try:
                    return self._runtime_context_provider(decision_time, protective_book=self.protective_book)
                except TypeError:
                    return self._runtime_context_provider(decision_time)

    def _record_risk_gate_state(self, bridge_result: Any) -> None:
        """Retain the gate-produced daily risk state (ADR §119.2 / OD-B).

        The RiskGate remains the sole author of ``RiskGateState``; the
        coordinator only carries the state forward so the next evaluation and
        the durable T2 commit observe continuous RiskDay/daily evidence.
        """
        gate_result = getattr(bridge_result, "gate_result", None)
        state = getattr(gate_result, "state", None)
        if isinstance(state, RiskGateState):
            self._risk_gate_state = state
        # ADR §128.1 (OD-1A): consume the EXISTING authoritative RiskGate
        # outcome — the authoritative daily-loss breach escalates through the
        # Phase-8 controller to the global kill switch.  No recalculation.
        if self._phase8_safety is not None and gate_result is not None:
            outcome = getattr(gate_result, "outcome", None)
            reason = getattr(gate_result, "reason", None)
            if (
                getattr(outcome, "name", "") == "REJECTED"
                and reason == "daily_loss_limit_exceeded"
            ):
                self._phase8_safety.observe_daily_loss_breach()

    def _notify_phase8_reconciliation_failed(self) -> None:
        """Route the FIRST authoritative reconciliation FAILED to Phase 8."""
        if self._phase8_safety is not None:
            self._phase8_safety.observe_reconciliation_failed()

    def _sync_risk_gate_equity(self) -> None:
        """Keep in-memory risk_gate_state.current_net_equity aligned with virtual account."""
        if self._risk_gate_state is not None and self._virtual_account is not None:
            eq = self._virtual_account.cost_adjusted_equity
            if self._risk_gate_state.current_net_equity != eq:
                self._risk_gate_state = RiskGateState(
                    risk_day=self._risk_gate_state.risk_day,
                    start_of_day_net_equity=self._risk_gate_state.start_of_day_net_equity,
                    current_net_equity=eq,
                    daily_trade_count=self._risk_gate_state.daily_trade_count,
                    _filled_entry_identities=self._risk_gate_state._filled_entry_identities,
                )

    def _handle_session_rollover(self, market_time: datetime) -> None:
        """Advance and persist RiskGateState on canonical session / RiskDay rollover."""
        if self._virtual_account is None or self._option_bridge is None:
            return
        self._sync_risk_gate_equity()
        calendar_id = (
            self._risk_gate_state.risk_day.calendar_identity
            if self._risk_gate_state is not None
            else "NSE"
        )
        new_risk_day = RiskDay(calendar_identity=calendar_id, session_date=market_time.date())
        current_equity = self._virtual_account.cost_adjusted_equity
        starting_cap = self._virtual_account.snapshot.starting_capital

        try:
            self._risk_gate_state = self._option_bridge.risk_gate.advance_state(
                risk_day=new_risk_day,
                current_net_equity=current_equity,
                starting_capital=starting_cap,
                prior_state=self._risk_gate_state,
            )
        except Exception as exc:
            logger.error("Failed to advance risk gate state on session rollover: %s", exc)
            return

        if self._persistence_store is not None and self.is_persistence_healthy:
            try:
                self._persistence_store.save_session_rollover(self._risk_gate_state)
            except Exception as exc:  # pragma: no cover - defensive fail-closed path
                self._persistence_failed = True
                logger.critical("Failed to persist session rollover: %s", exc, exc_info=True)

    def _apply_broker_terminal_event(self, terminal_event: Any) -> None:
        """Deliver one terminal event to the account and persist any breach.

        ADR §119.1 (OD-A): ``accounting_integrity_breached`` is durably
        recorded whenever the production runtime actually enters that state,
        including the paths where the account raises after flagging it.
        """
        try:
            self._virtual_account.on_broker_terminal_event(terminal_event)
        finally:
            self._persist_accounting_integrity_breach()
            self._sync_risk_gate_equity()

    def _persist_accounting_integrity_breach(self) -> None:
        """Durably persist an accounting-integrity breach exactly once."""
        if self._integrity_breach_persisted or self._virtual_account is None:
            return
        if not self._virtual_account.accounting_integrity_breached:
            return
        if self._persistence_store is None or not self.is_persistence_healthy:
            return
        try:
            self._persistence_store.save_accounting_integrity_breached(True)
            self._integrity_breach_persisted = True
        except Exception as exc:  # pragma: no cover - defensive fail-closed path
            self._persistence_failed = True
            logger.critical(
                "Failed to persist accounting integrity breach: %s", exc, exc_info=True
            )

    def _find_specification_for_identity(
        self,
        identity: InstrumentIdentity,
        as_of: date,
    ) -> InstrumentSpecification | None:
        """Look up authoritative instrument specification from catalog for a given identity and date."""
        entries = self._catalog.list_entries(underlying=identity.underlying, as_of=as_of)
        for entry in entries:
            if entry.identity == identity:
                return entry.specification
        return None

    def _on_market_time_event(self, event: Any) -> None:
        """Internal callback for MarketTimeEvent from feed."""
        ts = getattr(event, "market_timestamp", None)
        if ts is not None:
            self.on_market_time(ts)

    def _get_broker_pending_order(self, order_id: str) -> Any | None:
        """Safely retrieve a pending order from paper_broker across property or method accessors."""
        if self._paper_broker is None:
            return None
        if hasattr(self._paper_broker, "_pending") and isinstance(self._paper_broker._pending, Mapping):
            po = self._paper_broker._pending.get(order_id)
            if po is not None:
                return po
        po_attr = getattr(self._paper_broker, "pending_orders", None)
        if callable(po_attr):
            res = po_attr()
            if isinstance(res, Mapping):
                return res.get(order_id)
            elif isinstance(res, (list, tuple)):
                for o in res:
                    if getattr(o, "order_id", None) == order_id:
                        return o
        elif isinstance(po_attr, Mapping):
            return po_attr.get(order_id)
        return None

    def on_market_time(self, market_timestamp: datetime) -> None:
        """Handle authoritative market time update."""
        if not isinstance(market_timestamp, datetime) or market_timestamp.tzinfo is None:
            raise ValueError("market_timestamp must be a timezone-aware datetime")
        self._latest_market_timestamp = market_timestamp
        self._has_received_quote = True


    # ------------------------------------------------------------------
    # Claim Management Helpers
    # ------------------------------------------------------------------

    def _add_claim(self, owner: SubscriptionOwnerKey, identity: InstrumentIdentity, intent_id: str) -> None:
        claim_key = (owner, identity)
        if claim_key not in self._subscription_claims:
            manager_owner_preexisting = owner in self._subscription_manager.owners_for(identity)
            if not manager_owner_preexisting:
                need_sub = self._subscription_manager.acquire(owner, identity)
                if need_sub:
                    self._live_feed.subscribe(identity)
            self._subscription_claims[claim_key] = _SubscriptionClaimGroup(
                dependent_intent_ids={intent_id},
                manager_owner_preexisting=manager_owner_preexisting,
            )
        else:
            self._subscription_claims[claim_key].dependent_intent_ids.add(intent_id)

    def _remove_claim(self, owner: SubscriptionOwnerKey, identity: InstrumentIdentity, intent_id: str) -> None:
        claim_key = (owner, identity)
        group = self._subscription_claims.get(claim_key)
        if group is None:
            return
        group.dependent_intent_ids.discard(intent_id)
        if not group.dependent_intent_ids:
            del self._subscription_claims[claim_key]
            if not group.manager_owner_preexisting:
                need_unsub = self._subscription_manager.release(owner, identity)
                if need_unsub:
                    self._live_feed.unsubscribe(identity)

    # ------------------------------------------------------------------
    # Audit Event Construction Helpers
    # ------------------------------------------------------------------

    def _emit_signal_audit(self, intent: SignalIntent) -> None:
        if self._persistence_store is None or not self.is_persistence_healthy:
            return
        try:
            sig_id = signal_intent_identity(intent)
            ev = AuditEvent(
                event_id=derive_audit_event_id(
                    event_family=AuditEventFamily.STRATEGY_SIGNAL,
                    event_type=AuditEventType.SIGNAL_EMITTED,
                    aggregate_type="SIGNAL",
                    aggregate_identity=sig_id,
                    state_generation=None,
                    transaction_event_ordinal=0,
                    canonical_domain_identity=sig_id,
                ),
                event_family=AuditEventFamily.STRATEGY_SIGNAL.value,
                event_type=AuditEventType.SIGNAL_EMITTED.value,
                aggregate_type="SIGNAL",
                aggregate_identity=sig_id,
                market_timestamp=intent.originating_timestamp,
                recorded_at_utc=recorded_at_utc_now(),
                transaction_event_ordinal=0,
                strategy_id=intent.strategy_id,
                strategy_version=intent.strategy_version,
                payload_json=canonical_json_dumps({
                    "strategy_id": intent.strategy_id,
                    "strategy_version": intent.strategy_version,
                    "action": intent.action,
                    "symbol": intent.symbol,
                    "timeframe": intent.timeframe,
                    "originating_timestamp": intent.originating_timestamp.isoformat(),
                    "confidence": str(intent.confidence) if intent.confidence is not None else None,
                }),
            )
            self._persistence_store.append_audit_events([ev])
        except Exception as exc:
            self._persistence_failed = True
            logger.critical("Failed to persist SIGNAL_EMITTED audit event: %s", exc, exc_info=True)
            raise

    def _emit_option_selected_audit(self, intent: SignalIntent, selected_entry: ResolvedOptionEntry) -> None:
        if self._persistence_store is None or not self.is_persistence_healthy:
            return
        try:
            ident = selected_entry.selected_identity
            sig_id = signal_intent_identity(intent)
            ev = AuditEvent(
                event_id=derive_audit_event_id(
                    event_family=AuditEventFamily.OPTION_SELECTION,
                    event_type=AuditEventType.OPTION_SELECTED,
                    aggregate_type="OPTION_CONTRACT",
                    aggregate_identity=_identity_canonical_key(ident),
                    state_generation=None,
                    transaction_event_ordinal=0,
                    canonical_domain_identity=f"{sig_id}:{_identity_canonical_key(ident)}",
                ),
                event_family=AuditEventFamily.OPTION_SELECTION.value,
                event_type=AuditEventType.OPTION_SELECTED.value,
                aggregate_type="OPTION_CONTRACT",
                aggregate_identity=_identity_canonical_key(ident),
                market_timestamp=intent.originating_timestamp,
                recorded_at_utc=recorded_at_utc_now(),
                transaction_event_ordinal=0,
                strategy_id=intent.strategy_id,
                strategy_version=intent.strategy_version,
                instrument_key=_identity_canonical_key(ident),
                payload_json=canonical_json_dumps({
                    "strategy_id": intent.strategy_id,
                    "strategy_version": intent.strategy_version,
                    "instrument": ident.instrument,
                    "expiry": ident.expiry.isoformat(),
                    "strike": str(ident.strike),
                    "option_type": ident.option_type,
                }),
            )
            self._persistence_store.append_audit_events([ev])
        except Exception as exc:
            self._persistence_failed = True
            logger.critical("Failed to persist OPTION_SELECTED audit event: %s", exc, exc_info=True)
            raise

    def _emit_option_selection_rejected_audit(self, intent: SignalIntent, reason: str) -> None:
        if self._persistence_store is None or not self.is_persistence_healthy:
            return
        try:
            sig_id = signal_intent_identity(intent)
            ev = AuditEvent(
                event_id=derive_audit_event_id(
                    event_family=AuditEventFamily.OPTION_SELECTION,
                    event_type=AuditEventType.OPTION_SELECTION_REJECTED,
                    aggregate_type="OPTION_SELECTION",
                    aggregate_identity=sig_id,
                    state_generation=None,
                    transaction_event_ordinal=0,
                    canonical_domain_identity=f"{sig_id}:{reason}",
                ),
                event_family=AuditEventFamily.OPTION_SELECTION.value,
                event_type=AuditEventType.OPTION_SELECTION_REJECTED.value,
                aggregate_type="OPTION_SELECTION",
                aggregate_identity=sig_id,
                market_timestamp=intent.originating_timestamp,
                recorded_at_utc=recorded_at_utc_now(),
                transaction_event_ordinal=0,
                strategy_id=intent.strategy_id,
                strategy_version=intent.strategy_version,
                payload_json=canonical_json_dumps({
                    "strategy_id": intent.strategy_id,
                    "strategy_version": intent.strategy_version,
                    "reason": reason,
                }),
            )
            self._persistence_store.append_audit_events([ev])
        except Exception as exc:
            self._persistence_failed = True
            logger.critical("Failed to persist OPTION_SELECTION_REJECTED audit event: %s", exc, exc_info=True)
            raise

    def _emit_duplicate_signal_rejection_audit(
        self,
        intent: SignalIntent,
        intent_id: str,
        selected_identity: InstrumentIdentity | None,
    ) -> None:
        if self._persistence_store is None or not self.is_persistence_healthy:
            return
        try:
            ident_key = _identity_canonical_key(selected_identity) if selected_identity else intent.symbol
            ev = AuditEvent(
                event_id=derive_audit_event_id(
                    event_family=AuditEventFamily.STRATEGY_SIGNAL,
                    event_type=AuditEventType.SIGNAL_REJECTED_DUPLICATE,
                    aggregate_type="ENTRY_INTENT",
                    aggregate_identity=intent_id,
                    state_generation=None,
                    transaction_event_ordinal=0,
                    canonical_domain_identity=f"{intent_id}:duplicate",
                ),
                event_family=AuditEventFamily.STRATEGY_SIGNAL.value,
                event_type=AuditEventType.SIGNAL_REJECTED_DUPLICATE.value,
                aggregate_type="ENTRY_INTENT",
                aggregate_identity=intent_id,
                market_timestamp=intent.originating_timestamp,
                recorded_at_utc=recorded_at_utc_now(),
                transaction_event_ordinal=0,
                strategy_id=intent.strategy_id,
                strategy_version=intent.strategy_version,
                instrument_key=ident_key,
                entry_intent_identity=intent_id,
                payload_json=canonical_json_dumps({
                    "strategy_id": intent.strategy_id,
                    "strategy_version": intent.strategy_version,
                    "intent_id": intent_id,
                    "reason": "duplicate_signal_intent",
                }),
            )
            self._persistence_store.append_audit_events([ev])
        except Exception as exc:
            self._persistence_failed = True
            logger.critical("Failed to persist SIGNAL_REJECTED_DUPLICATE audit event: %s", exc, exc_info=True)
            raise

    def _emit_risk_approved_audit(
        self,
        intent: SignalIntent,
        selected_identity: InstrumentIdentity,
        bridge_result: OptionEntryResult,
        risk_day: Any,
    ) -> None:
        if self._persistence_store is None or not self.is_persistence_healthy:
            return
        try:
            sig_id = signal_intent_identity(intent)
            ident_key = _identity_canonical_key(selected_identity)
            nom_risk = "0"
            if hasattr(bridge_result.gate_result, "nominal_stop_risk"):
                nom_risk = str(bridge_result.gate_result.nominal_stop_risk)
            ev = AuditEvent(
                event_id=derive_audit_event_id(
                    event_family=AuditEventFamily.RISK_DECISION,
                    event_type=AuditEventType.RISK_EVALUATED_APPROVED,
                    aggregate_type="RISK_GATE",
                    aggregate_identity=f"{intent.strategy_id}:{intent.strategy_version}:{ident_key}",
                    state_generation=None,
                    transaction_event_ordinal=0,
                    canonical_domain_identity=f"{sig_id}:{ident_key}:APPROVED",
                ),
                event_family=AuditEventFamily.RISK_DECISION.value,
                event_type=AuditEventType.RISK_EVALUATED_APPROVED.value,
                aggregate_type="RISK_GATE",
                aggregate_identity=f"{intent.strategy_id}:{intent.strategy_version}:{ident_key}",
                market_timestamp=intent.originating_timestamp,
                recorded_at_utc=recorded_at_utc_now(),
                transaction_event_ordinal=0,
                strategy_id=intent.strategy_id,
                strategy_version=intent.strategy_version,
                instrument_key=ident_key,
                payload_json=canonical_json_dumps({
                    "strategy_id": intent.strategy_id,
                    "strategy_version": intent.strategy_version,
                    "decision": "APPROVED",
                    "approved_quantity": str(bridge_result.instruction.quantity),
                    "nominal_stop_risk": nom_risk,
                    "risk_day": str(risk_day),
                }),
            )
            self._persistence_store.append_audit_events([ev])
        except Exception as exc:
            self._persistence_failed = True
            logger.critical("Failed to persist RISK_EVALUATED_APPROVED audit event: %s", exc, exc_info=True)
            raise

    def _emit_risk_rejected_audit(
        self,
        intent: SignalIntent,
        selected_identity: InstrumentIdentity | None,
        reason: str,
    ) -> None:
        if self._persistence_store is None or not self.is_persistence_healthy:
            return
        try:
            sig_id = signal_intent_identity(intent)
            ident_key = _identity_canonical_key(selected_identity) if selected_identity else intent.symbol
            ev = AuditEvent(
                event_id=derive_audit_event_id(
                    event_family=AuditEventFamily.RISK_DECISION,
                    event_type=AuditEventType.RISK_EVALUATED_REJECTED,
                    aggregate_type="RISK_GATE",
                    aggregate_identity=f"{intent.strategy_id}:{intent.strategy_version}:{ident_key}",
                    state_generation=None,
                    transaction_event_ordinal=0,
                    canonical_domain_identity=f"{sig_id}:{ident_key}:{reason}",
                ),
                event_family=AuditEventFamily.RISK_DECISION.value,
                event_type=AuditEventType.RISK_EVALUATED_REJECTED.value,
                aggregate_type="RISK_GATE",
                aggregate_identity=f"{intent.strategy_id}:{intent.strategy_version}:{ident_key}",
                market_timestamp=intent.originating_timestamp,
                recorded_at_utc=recorded_at_utc_now(),
                transaction_event_ordinal=0,
                strategy_id=intent.strategy_id,
                strategy_version=intent.strategy_version,
                instrument_key=_identity_canonical_key(selected_identity) if selected_identity else None,
                payload_json=canonical_json_dumps({
                    "strategy_id": intent.strategy_id,
                    "strategy_version": intent.strategy_version,
                    "decision": "REJECTED",
                    "reason": reason,
                }),
            )
            self._persistence_store.append_audit_events([ev])
        except Exception as exc:
            self._persistence_failed = True
            logger.critical("Failed to persist RISK_EVALUATED_REJECTED audit event: %s", exc, exc_info=True)
            raise

    def _build_t1_audit_events(
        self,
        *,
        intent_id: str,
        strategy_id: str,
        strategy_version: str,
        instrument_key: str,
        order_id: str,
        broker_order_identity: str,
        commitment: PremiumCommitmentRecord,
        order: _PendingOrder,
        plan: PreEntryProtectivePlan,
        market_timestamp: datetime,
    ) -> tuple[AuditEvent, ...]:
        acc_id = self._virtual_account.account_id if self._virtual_account else "unknown"
        ev_submitted = AuditEvent(
            event_id=derive_audit_event_id(
                event_family=AuditEventFamily.ENTRY_INTENT,
                event_type=AuditEventType.INTENT_SUBMITTED,
                aggregate_type="ENTRY_INTENT",
                aggregate_identity=intent_id,
                state_generation=None,
                transaction_event_ordinal=0,
                canonical_domain_identity=intent_id,
            ),
            event_family=AuditEventFamily.ENTRY_INTENT.value,
            event_type=AuditEventType.INTENT_SUBMITTED.value,
            aggregate_type="ENTRY_INTENT",
            aggregate_identity=intent_id,
            market_timestamp=market_timestamp,
            recorded_at_utc=recorded_at_utc_now(),
            transaction_event_ordinal=0,
            correlation_id=intent_id,
            entry_intent_identity=intent_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            instrument_key=instrument_key,
            payload_json=canonical_json_dumps({
                "intent_id": intent_id,
                "strategy_id": strategy_id,
                "strategy_version": strategy_version,
                "lifecycle_state": "SUBMITTED",
            }),
        )
        ev_reserved = AuditEvent(
            event_id=derive_audit_event_id(
                event_family=AuditEventFamily.CAPITAL_RESERVATION,
                event_type=AuditEventType.PREMIUM_RESERVED,
                aggregate_type="ACCOUNT",
                aggregate_identity=acc_id,
                state_generation=None,
                transaction_event_ordinal=1,
                canonical_domain_identity=commitment.reservation_key,
            ),
            event_family=AuditEventFamily.CAPITAL_RESERVATION.value,
            event_type=AuditEventType.PREMIUM_RESERVED.value,
            aggregate_type="ACCOUNT",
            aggregate_identity=acc_id,
            market_timestamp=market_timestamp,
            recorded_at_utc=recorded_at_utc_now(),
            transaction_event_ordinal=1,
            correlation_id=intent_id,
            entry_intent_identity=intent_id,
            broker_order_identity=broker_order_identity,
            instrument_key=instrument_key,
            payload_json=canonical_json_dumps({
                "reservation_key": commitment.reservation_key,
                "required_cash": str(commitment.required_cash),
                "approved_quantity": str(commitment.approved_quantity),
                "worst_permitted_fill_price": str(commitment.worst_permitted_fill_price),
            }),
        )
        ev_queued = AuditEvent(
            event_id=derive_audit_event_id(
                event_family=AuditEventFamily.ORDER_LIFECYCLE,
                event_type=AuditEventType.ORDER_QUEUED,
                aggregate_type="ORDER",
                aggregate_identity=order_id,
                state_generation=None,
                transaction_event_ordinal=2,
                canonical_domain_identity=f"{broker_order_identity}:QUEUED",
            ),
            event_family=AuditEventFamily.ORDER_LIFECYCLE.value,
            event_type=AuditEventType.ORDER_QUEUED.value,
            aggregate_type="ORDER",
            aggregate_identity=order_id,
            market_timestamp=market_timestamp,
            recorded_at_utc=recorded_at_utc_now(),
            transaction_event_ordinal=2,
            correlation_id=intent_id,
            entry_intent_identity=intent_id,
            broker_order_identity=broker_order_identity,
            instrument_key=instrument_key,
            payload_json=canonical_json_dumps({
                "order_id": order_id,
                "broker_order_identity": broker_order_identity,
                "action": order.original_order.action,
                "quantity": str(order.original_order.quantity),
                "order_type": order.original_order.order_type.value,
                "lifecycle_state": "QUEUED",
            }),
        )
        ev_plan = AuditEvent(
            event_id=derive_audit_event_id(
                event_family=AuditEventFamily.PROTECTIVE_LIFECYCLE,
                event_type=AuditEventType.PLAN_RETAINED,
                aggregate_type="PROTECTIVE",
                aggregate_identity=order_id,
                state_generation=None,
                transaction_event_ordinal=3,
                canonical_domain_identity=order_id,
            ),
            event_family=AuditEventFamily.PROTECTIVE_LIFECYCLE.value,
            event_type=AuditEventType.PLAN_RETAINED.value,
            aggregate_type="PROTECTIVE",
            aggregate_identity=order_id,
            market_timestamp=market_timestamp,
            recorded_at_utc=recorded_at_utc_now(),
            transaction_event_ordinal=3,
            correlation_id=intent_id,
            entry_intent_identity=intent_id,
            broker_order_identity=broker_order_identity,
            instrument_key=instrument_key,
            payload_json=canonical_json_dumps({
                "order_id": order_id,
                "plan_type": "PreEntryProtectivePlan",
                "stop_price": str(plan.stop_price),
                "target_price": str(plan.target_price) if plan.target_price is not None else None,
            }),
        )
        return (ev_submitted, ev_reserved, ev_queued, ev_plan)

    def _build_t2_audit_events(
        self,
        *,
        terminal_event: BrokerTerminalEvent,
        accounting_result: AccountingResult,
        account_snapshot: AccountSnapshot,
        accounting_sequence: int,
        materialized_exits: Sequence[ProtectiveExit],
        entry_intent_id: str | None = None,
        cost_assessment: Any | None = None,
    ) -> tuple[AuditEvent, ...]:
        acc_id = account_snapshot.account_id
        order_id = terminal_event.order_id
        exec_res = terminal_event.execution_result
        m_ts = terminal_event.market_timestamp
        events: list[AuditEvent] = []
        ord_idx = 0

        # 0. FILL_EXECUTED
        fill_price_str = str(exec_res.fill_price) if exec_res else "0"
        filled_qty_str = str(exec_res.filled_quantity) if exec_res else "0"
        fee_str = str(getattr(exec_res, "fee", Decimal("0"))) if exec_res else "0"
        events.append(
            AuditEvent(
                event_id=derive_audit_event_id(
                    event_family=AuditEventFamily.FILL,
                    event_type=AuditEventType.FILL_EXECUTED,
                    aggregate_type="ORDER",
                    aggregate_identity=order_id,
                    state_generation=None,
                    transaction_event_ordinal=ord_idx,
                    canonical_domain_identity=f"{terminal_event.broker_order_identity}:FILLED",
                ),
                event_family=AuditEventFamily.FILL.value,
                event_type=AuditEventType.FILL_EXECUTED.value,
                aggregate_type="ORDER",
                aggregate_identity=order_id,
                market_timestamp=m_ts,
                recorded_at_utc=recorded_at_utc_now(),
                transaction_event_ordinal=ord_idx,
                correlation_id=entry_intent_id or order_id,
                entry_intent_identity=entry_intent_id,
                broker_order_identity=terminal_event.broker_order_identity,
                payload_json=canonical_json_dumps({
                    "order_id": order_id,
                    "broker_order_identity": terminal_event.broker_order_identity,
                    "fill_price": fill_price_str,
                    "filled_quantity": filled_qty_str,
                    "fee": fee_str,
                }),
            )
        )
        ord_idx += 1

        # 1. ACCOUNT_STATE_MUTATED
        prior = accounting_result.prior_snapshot
        res = accounting_result.resulting_snapshot
        cash_delta = res.cash - prior.cash
        pnl_delta = res.realized_pnl - prior.realized_pnl
        events.append(
            AuditEvent(
                event_id=derive_audit_event_id(
                    event_family=AuditEventFamily.ACCOUNTING,
                    event_type=AuditEventType.ACCOUNT_STATE_MUTATED,
                    aggregate_type="ACCOUNT",
                    aggregate_identity=acc_id,
                    state_generation=None,
                    transaction_event_ordinal=ord_idx,
                    canonical_domain_identity=f"{acc_id}:{accounting_sequence}",
                ),
                event_family=AuditEventFamily.ACCOUNTING.value,
                event_type=AuditEventType.ACCOUNT_STATE_MUTATED.value,
                aggregate_type="ACCOUNT",
                aggregate_identity=acc_id,
                market_timestamp=m_ts,
                recorded_at_utc=recorded_at_utc_now(),
                transaction_event_ordinal=ord_idx,
                correlation_id=entry_intent_id or order_id,
                entry_intent_identity=entry_intent_id,
                broker_order_identity=terminal_event.broker_order_identity,
                payload_json=canonical_json_dumps({
                    "accounting_sequence": accounting_sequence,
                    "cash_delta": str(cash_delta),
                    "realized_pnl_delta": str(pnl_delta),
                    "cash_after": str(res.cash),
                    "realized_pnl_after": str(res.realized_pnl),
                }),
            )
        )
        ord_idx += 1

        # 2. POSITION_MUTATED
        events.append(
            AuditEvent(
                event_id=derive_audit_event_id(
                    event_family=AuditEventFamily.ACCOUNTING,
                    event_type=AuditEventType.POSITION_MUTATED,
                    aggregate_type="ACCOUNT",
                    aggregate_identity=acc_id,
                    state_generation=None,
                    transaction_event_ordinal=ord_idx,
                    canonical_domain_identity=f"{acc_id}:positions:{accounting_sequence}",
                ),
                event_family=AuditEventFamily.ACCOUNTING.value,
                event_type=AuditEventType.POSITION_MUTATED.value,
                aggregate_type="ACCOUNT",
                aggregate_identity=acc_id,
                market_timestamp=m_ts,
                recorded_at_utc=recorded_at_utc_now(),
                transaction_event_ordinal=ord_idx,
                correlation_id=entry_intent_id or order_id,
                entry_intent_identity=entry_intent_id,
                broker_order_identity=terminal_event.broker_order_identity,
                payload_json=canonical_json_dumps({
                    "accounting_sequence": accounting_sequence,
                    "open_positions_count": len(res.positions),
                }),
            )
        )
        ord_idx += 1

        # 3. PREMIUM_RELEASED
        events.append(
            AuditEvent(
                event_id=derive_audit_event_id(
                    event_family=AuditEventFamily.CAPITAL_RESERVATION,
                    event_type=AuditEventType.PREMIUM_RELEASED,
                    aggregate_type="ACCOUNT",
                    aggregate_identity=acc_id,
                    state_generation=None,
                    transaction_event_ordinal=ord_idx,
                    canonical_domain_identity=order_id,
                ),
                event_family=AuditEventFamily.CAPITAL_RESERVATION.value,
                event_type=AuditEventType.PREMIUM_RELEASED.value,
                aggregate_type="ACCOUNT",
                aggregate_identity=acc_id,
                market_timestamp=m_ts,
                recorded_at_utc=recorded_at_utc_now(),
                transaction_event_ordinal=ord_idx,
                correlation_id=entry_intent_id or order_id,
                entry_intent_identity=entry_intent_id,
                broker_order_identity=terminal_event.broker_order_identity,
                payload_json=canonical_json_dumps({
                    "reservation_key": order_id,
                    "reason": "opening_order_filled",
                }),
            )
        )
        ord_idx += 1

        # 4..N PROTECTIVE_MATERIALIZED
        for ex in materialized_exits:
            events.append(
                AuditEvent(
                    event_id=derive_audit_event_id(
                        event_family=AuditEventFamily.PROTECTIVE_LIFECYCLE,
                        event_type=AuditEventType.PROTECTIVE_MATERIALIZED,
                        aggregate_type="PROTECTIVE",
                        aggregate_identity=ex.protective_id,
                        state_generation=None,
                        transaction_event_ordinal=ord_idx,
                        canonical_domain_identity=ex.protective_id,
                    ),
                    event_family=AuditEventFamily.PROTECTIVE_LIFECYCLE.value,
                    event_type=AuditEventType.PROTECTIVE_MATERIALIZED.value,
                    aggregate_type="PROTECTIVE",
                    aggregate_identity=ex.protective_id,
                    market_timestamp=m_ts,
                    recorded_at_utc=recorded_at_utc_now(),
                    transaction_event_ordinal=ord_idx,
                    correlation_id=entry_intent_id or order_id,
                    entry_intent_identity=entry_intent_id,
                    broker_order_identity=terminal_event.broker_order_identity,
                    protective_id=ex.protective_id,
                    payload_json=canonical_json_dumps({
                        "protective_id": ex.protective_id,
                        "kind": ex.kind.value,
                        "state": ex.state.value,
                    }),
                )
            )
            ord_idx += 1

        # N+1 INTENT_FILLED
        if entry_intent_id:
            events.append(
                AuditEvent(
                    event_id=derive_audit_event_id(
                        event_family=AuditEventFamily.ENTRY_INTENT,
                        event_type=AuditEventType.INTENT_FILLED,
                        aggregate_type="ENTRY_INTENT",
                        aggregate_identity=entry_intent_id,
                        state_generation=None,
                        transaction_event_ordinal=ord_idx,
                        canonical_domain_identity=entry_intent_id,
                    ),
                    event_family=AuditEventFamily.ENTRY_INTENT.value,
                    event_type=AuditEventType.INTENT_FILLED.value,
                    aggregate_type="ENTRY_INTENT",
                    aggregate_identity=entry_intent_id,
                    market_timestamp=m_ts,
                    recorded_at_utc=recorded_at_utc_now(),
                    transaction_event_ordinal=ord_idx,
                    correlation_id=entry_intent_id,
                    entry_intent_identity=entry_intent_id,
                    payload_json=canonical_json_dumps({
                        "intent_id": entry_intent_id,
                        "lifecycle_state": "FILLED",
                    }),
                )
            )
            ord_idx += 1

        # N+2 COST_ASSESSED
        if cost_assessment is not None:
            events.append(
                AuditEvent(
                    event_id=derive_audit_event_id(
                        event_family=AuditEventFamily.COST_ASSESSMENT,
                        event_type=AuditEventType.COST_ASSESSED,
                        aggregate_type="COST",
                        aggregate_identity=cost_assessment.assessment_id,
                        state_generation=None,
                        transaction_event_ordinal=ord_idx,
                        canonical_domain_identity=cost_assessment.assessment_id,
                    ),
                    event_family=AuditEventFamily.COST_ASSESSMENT.value,
                    event_type=AuditEventType.COST_ASSESSED.value,
                    aggregate_type="COST",
                    aggregate_identity=cost_assessment.assessment_id,
                    market_timestamp=m_ts,
                    recorded_at_utc=recorded_at_utc_now(),
                    transaction_event_ordinal=ord_idx,
                    correlation_id=entry_intent_id or order_id,
                    payload_json=canonical_json_dumps({
                        "assessment_id": cost_assessment.assessment_id,
                        "total_cost": str(cost_assessment.total_cost),
                    }),
                )
            )
            ord_idx += 1

        return tuple(events)

    def _build_t3_audit_events(
        self,
        *,
        pending_close: LiveProtectivePendingClose,
        close_order: _PendingOrder,
    ) -> tuple[AuditEvent, ...]:
        m_ts = pending_close.trigger_timestamp
        ev_trig = AuditEvent(
            event_id=derive_audit_event_id(
                event_family=AuditEventFamily.PROTECTIVE_LIFECYCLE,
                event_type=AuditEventType.PROTECTIVE_TRIGGERED,
                aggregate_type="PROTECTIVE",
                aggregate_identity=pending_close.protective_id,
                state_generation=None,
                transaction_event_ordinal=0,
                canonical_domain_identity=pending_close.protective_id,
            ),
            event_family=AuditEventFamily.PROTECTIVE_LIFECYCLE.value,
            event_type=AuditEventType.PROTECTIVE_TRIGGERED.value,
            aggregate_type="PROTECTIVE",
            aggregate_identity=pending_close.protective_id,
            market_timestamp=m_ts,
            recorded_at_utc=recorded_at_utc_now(),
            transaction_event_ordinal=0,
            protective_id=pending_close.protective_id,
            broker_order_identity=pending_close.broker_order_identity,
            payload_json=canonical_json_dumps({
                "protective_id": pending_close.protective_id,
                "kind": pending_close.kind.value,
                "trigger_price": str(pending_close.trigger_price),
            }),
        )
        ev_queued = AuditEvent(
            event_id=derive_audit_event_id(
                event_family=AuditEventFamily.ORDER_LIFECYCLE,
                event_type=AuditEventType.ORDER_QUEUED,
                aggregate_type="ORDER",
                aggregate_identity=close_order.order_id,
                state_generation=None,
                transaction_event_ordinal=1,
                canonical_domain_identity=f"{close_order.broker_order_identity}:QUEUED",
            ),
            event_family=AuditEventFamily.ORDER_LIFECYCLE.value,
            event_type=AuditEventType.ORDER_QUEUED.value,
            aggregate_type="ORDER",
            aggregate_identity=close_order.order_id,
            market_timestamp=m_ts,
            recorded_at_utc=recorded_at_utc_now(),
            transaction_event_ordinal=1,
            protective_id=pending_close.protective_id,
            broker_order_identity=close_order.broker_order_identity,
            payload_json=canonical_json_dumps({
                "order_id": close_order.order_id,
                "broker_order_identity": close_order.broker_order_identity,
                "action": close_order.original_order.action,
                "quantity": str(close_order.original_order.quantity),
                "order_type": close_order.original_order.order_type.value,
                "lifecycle_state": "QUEUED",
            }),
        )
        ev_close_queued = AuditEvent(
            event_id=derive_audit_event_id(
                event_family=AuditEventFamily.PROTECTIVE_LIFECYCLE,
                event_type=AuditEventType.PROTECTIVE_CLOSE_QUEUED,
                aggregate_type="PROTECTIVE",
                aggregate_identity=pending_close.protective_id,
                state_generation=None,
                transaction_event_ordinal=2,
                canonical_domain_identity=f"{pending_close.protective_id}:CLOSE_QUEUED",
            ),
            event_family=AuditEventFamily.PROTECTIVE_LIFECYCLE.value,
            event_type=AuditEventType.PROTECTIVE_CLOSE_QUEUED.value,
            aggregate_type="PROTECTIVE",
            aggregate_identity=pending_close.protective_id,
            market_timestamp=m_ts,
            recorded_at_utc=recorded_at_utc_now(),
            transaction_event_ordinal=2,
            protective_id=pending_close.protective_id,
            broker_order_identity=close_order.broker_order_identity,
            payload_json=canonical_json_dumps({
                "order_id": close_order.order_id,
                "protective_id": pending_close.protective_id,
            }),
        )
        return (ev_trig, ev_queued, ev_close_queued)

    def _build_t4_audit_events(
        self,
        *,
        terminal_event: BrokerTerminalEvent,
        accounting_result: AccountingResult,
        account_snapshot: AccountSnapshot,
        accounting_sequence: int,
        cleared_pending: LiveProtectivePendingClose | None,
        updated_exits: Sequence[ProtectiveExit],
        trade_record: Any | None = None,
        cost_assessment: Any | None = None,
    ) -> tuple[AuditEvent, ...]:
        acc_id = account_snapshot.account_id
        order_id = terminal_event.order_id
        exec_res = terminal_event.execution_result
        m_ts = terminal_event.market_timestamp
        events: list[AuditEvent] = []
        ord_idx = 0
        prot_id = cleared_pending.protective_id if cleared_pending else None

        # 0. FILL_EXECUTED
        fill_price_str = str(exec_res.fill_price) if exec_res else "0"
        filled_qty_str = str(exec_res.filled_quantity) if exec_res else "0"
        fee_str = str(getattr(exec_res, "fee", Decimal("0"))) if exec_res else "0"
        events.append(
            AuditEvent(
                event_id=derive_audit_event_id(
                    event_family=AuditEventFamily.FILL,
                    event_type=AuditEventType.FILL_EXECUTED,
                    aggregate_type="ORDER",
                    aggregate_identity=order_id,
                    state_generation=None,
                    transaction_event_ordinal=ord_idx,
                    canonical_domain_identity=f"{terminal_event.broker_order_identity}:FILLED",
                ),
                event_family=AuditEventFamily.FILL.value,
                event_type=AuditEventType.FILL_EXECUTED.value,
                aggregate_type="ORDER",
                aggregate_identity=order_id,
                market_timestamp=m_ts,
                recorded_at_utc=recorded_at_utc_now(),
                transaction_event_ordinal=ord_idx,
                broker_order_identity=terminal_event.broker_order_identity,
                protective_id=prot_id,
                payload_json=canonical_json_dumps({
                    "order_id": order_id,
                    "broker_order_identity": terminal_event.broker_order_identity,
                    "fill_price": fill_price_str,
                    "filled_quantity": filled_qty_str,
                    "fee": fee_str,
                }),
            )
        )
        ord_idx += 1

        # 1. ACCOUNT_STATE_MUTATED
        prior = accounting_result.prior_snapshot
        res = accounting_result.resulting_snapshot
        cash_delta = res.cash - prior.cash
        pnl_delta = res.realized_pnl - prior.realized_pnl
        events.append(
            AuditEvent(
                event_id=derive_audit_event_id(
                    event_family=AuditEventFamily.ACCOUNTING,
                    event_type=AuditEventType.ACCOUNT_STATE_MUTATED,
                    aggregate_type="ACCOUNT",
                    aggregate_identity=acc_id,
                    state_generation=None,
                    transaction_event_ordinal=ord_idx,
                    canonical_domain_identity=f"{acc_id}:{accounting_sequence}",
                ),
                event_family=AuditEventFamily.ACCOUNTING.value,
                event_type=AuditEventType.ACCOUNT_STATE_MUTATED.value,
                aggregate_type="ACCOUNT",
                aggregate_identity=acc_id,
                market_timestamp=m_ts,
                recorded_at_utc=recorded_at_utc_now(),
                transaction_event_ordinal=ord_idx,
                broker_order_identity=terminal_event.broker_order_identity,
                protective_id=prot_id,
                payload_json=canonical_json_dumps({
                    "accounting_sequence": accounting_sequence,
                    "cash_delta": str(cash_delta),
                    "realized_pnl_delta": str(pnl_delta),
                    "cash_after": str(res.cash),
                    "realized_pnl_after": str(res.realized_pnl),
                }),
            )
        )
        ord_idx += 1

        # 2. POSITION_MUTATED
        events.append(
            AuditEvent(
                event_id=derive_audit_event_id(
                    event_family=AuditEventFamily.ACCOUNTING,
                    event_type=AuditEventType.POSITION_MUTATED,
                    aggregate_type="ACCOUNT",
                    aggregate_identity=acc_id,
                    state_generation=None,
                    transaction_event_ordinal=ord_idx,
                    canonical_domain_identity=f"{acc_id}:positions:{accounting_sequence}",
                ),
                event_family=AuditEventFamily.ACCOUNTING.value,
                event_type=AuditEventType.POSITION_MUTATED.value,
                aggregate_type="ACCOUNT",
                aggregate_identity=acc_id,
                market_timestamp=m_ts,
                recorded_at_utc=recorded_at_utc_now(),
                transaction_event_ordinal=ord_idx,
                broker_order_identity=terminal_event.broker_order_identity,
                protective_id=prot_id,
                payload_json=canonical_json_dumps({
                    "accounting_sequence": accounting_sequence,
                    "open_positions_count": len(res.positions),
                }),
            )
        )
        ord_idx += 1

        # 3. PROTECTIVE_FILLED
        if prot_id:
            events.append(
                AuditEvent(
                    event_id=derive_audit_event_id(
                        event_family=AuditEventFamily.PROTECTIVE_LIFECYCLE,
                        event_type=AuditEventType.PROTECTIVE_FILLED,
                        aggregate_type="PROTECTIVE",
                        aggregate_identity=prot_id,
                        state_generation=None,
                        transaction_event_ordinal=ord_idx,
                        canonical_domain_identity=prot_id,
                    ),
                    event_family=AuditEventFamily.PROTECTIVE_LIFECYCLE.value,
                    event_type=AuditEventType.PROTECTIVE_FILLED.value,
                    aggregate_type="PROTECTIVE",
                    aggregate_identity=prot_id,
                    market_timestamp=m_ts,
                    recorded_at_utc=recorded_at_utc_now(),
                    transaction_event_ordinal=ord_idx,
                    protective_id=prot_id,
                    broker_order_identity=terminal_event.broker_order_identity,
                    payload_json=canonical_json_dumps({
                        "protective_id": prot_id,
                        "state": "FILLED",
                    }),
                )
            )
            ord_idx += 1

        # 4..N OCO_SIBLINGS_CANCELLED
        for ex in updated_exits:
            if ex.protective_id != prot_id and ex.state.value == "CANCELLED":
                events.append(
                    AuditEvent(
                        event_id=derive_audit_event_id(
                            event_family=AuditEventFamily.PROTECTIVE_LIFECYCLE,
                            event_type=AuditEventType.OCO_SIBLINGS_CANCELLED,
                            aggregate_type="PROTECTIVE",
                            aggregate_identity=ex.protective_id,
                            state_generation=None,
                            transaction_event_ordinal=ord_idx,
                            canonical_domain_identity=ex.protective_id,
                        ),
                        event_family=AuditEventFamily.PROTECTIVE_LIFECYCLE.value,
                        event_type=AuditEventType.OCO_SIBLINGS_CANCELLED.value,
                        aggregate_type="PROTECTIVE",
                        aggregate_identity=ex.protective_id,
                        market_timestamp=m_ts,
                        recorded_at_utc=recorded_at_utc_now(),
                        transaction_event_ordinal=ord_idx,
                        protective_id=ex.protective_id,
                        payload_json=canonical_json_dumps({
                            "protective_id": ex.protective_id,
                            "state": "CANCELLED",
                            "reason": "oco_sibling_filled",
                        }),
                    )
                )
                ord_idx += 1

        # TRADE_CLOSED
        if trade_record is not None:
            t_id = trade_record.trade_id
            events.append(
                AuditEvent(
                    event_id=derive_audit_event_id(
                        event_family=AuditEventFamily.TRADE_LEDGER,
                        event_type=AuditEventType.TRADE_CLOSED,
                        aggregate_type="TRADE",
                        aggregate_identity=t_id,
                        state_generation=None,
                        transaction_event_ordinal=ord_idx,
                        canonical_domain_identity=t_id,
                    ),
                    event_family=AuditEventFamily.TRADE_LEDGER.value,
                    event_type=AuditEventType.TRADE_CLOSED.value,
                    aggregate_type="TRADE",
                    aggregate_identity=t_id,
                    market_timestamp=m_ts,
                    recorded_at_utc=recorded_at_utc_now(),
                    transaction_event_ordinal=ord_idx,
                    trade_id=t_id,
                    payload_json=canonical_json_dumps({
                        "trade_id": t_id,
                        "gross_realized_pnl": str(trade_record.gross_realized_pnl),
                    }),
                )
            )
            ord_idx += 1

        # COST_ASSESSED
        if cost_assessment is not None:
            events.append(
                AuditEvent(
                    event_id=derive_audit_event_id(
                        event_family=AuditEventFamily.COST_ASSESSMENT,
                        event_type=AuditEventType.COST_ASSESSED,
                        aggregate_type="COST",
                        aggregate_identity=cost_assessment.assessment_id,
                        state_generation=None,
                        transaction_event_ordinal=ord_idx,
                        canonical_domain_identity=cost_assessment.assessment_id,
                    ),
                    event_family=AuditEventFamily.COST_ASSESSMENT.value,
                    event_type=AuditEventType.COST_ASSESSED.value,
                    aggregate_type="COST",
                    aggregate_identity=cost_assessment.assessment_id,
                    market_timestamp=m_ts,
                    recorded_at_utc=recorded_at_utc_now(),
                    transaction_event_ordinal=ord_idx,
                    payload_json=canonical_json_dumps({
                        "assessment_id": cost_assessment.assessment_id,
                        "total_cost": str(cost_assessment.total_cost),
                    }),
                )
            )
            ord_idx += 1

        return tuple(events)

    def _build_t5_audit_events(
        self,
        *,
        terminal_event: BrokerTerminalEvent,
        released_reservation_key: str | None = None,
        cleared_pending_close_position_key: PositionKey | None = None,
        entry_intent_id: str | None = None,
    ) -> tuple[AuditEvent, ...]:
        order_id = terminal_event.order_id
        m_ts = terminal_event.market_timestamp
        events: list[AuditEvent] = []
        ord_idx = 0

        state_val = terminal_event.lifecycle_state.value
        ev_type = (
            AuditEventType.ORDER_CANCELLED.value
            if state_val == "CANCELLED"
            else (
                AuditEventType.ORDER_EXPIRED.value
                if state_val == "EXPIRED"
                else AuditEventType.ORDER_REJECTED.value
            )
        )
        events.append(
            AuditEvent(
                event_id=derive_audit_event_id(
                    event_family=AuditEventFamily.ORDER_LIFECYCLE,
                    event_type=ev_type,
                    aggregate_type="ORDER",
                    aggregate_identity=order_id,
                    state_generation=None,
                    transaction_event_ordinal=ord_idx,
                    canonical_domain_identity=f"{terminal_event.broker_order_identity}:{state_val}",
                ),
                event_family=AuditEventFamily.ORDER_LIFECYCLE.value,
                event_type=ev_type,
                aggregate_type="ORDER",
                aggregate_identity=order_id,
                market_timestamp=m_ts,
                recorded_at_utc=recorded_at_utc_now(),
                transaction_event_ordinal=ord_idx,
                broker_order_identity=terminal_event.broker_order_identity,
                entry_intent_identity=entry_intent_id,
                payload_json=canonical_json_dumps({
                    "order_id": order_id,
                    "broker_order_identity": terminal_event.broker_order_identity,
                    "lifecycle_state": state_val,
                    "reason": terminal_event.reason,
                }),
            )
        )
        ord_idx += 1

        if released_reservation_key:
            acc_id = self._virtual_account.account_id if self._virtual_account else "unknown"
            events.append(
                AuditEvent(
                    event_id=derive_audit_event_id(
                        event_family=AuditEventFamily.CAPITAL_RESERVATION,
                        event_type=AuditEventType.PREMIUM_RELEASED,
                        aggregate_type="ACCOUNT",
                        aggregate_identity=acc_id,
                        state_generation=None,
                        transaction_event_ordinal=ord_idx,
                        canonical_domain_identity=released_reservation_key,
                    ),
                    event_family=AuditEventFamily.CAPITAL_RESERVATION.value,
                    event_type=AuditEventType.PREMIUM_RELEASED.value,
                    aggregate_type="ACCOUNT",
                    aggregate_identity=acc_id,
                    market_timestamp=m_ts,
                    recorded_at_utc=recorded_at_utc_now(),
                    transaction_event_ordinal=ord_idx,
                    broker_order_identity=terminal_event.broker_order_identity,
                    entry_intent_identity=entry_intent_id,
                    payload_json=canonical_json_dumps({
                        "reservation_key": released_reservation_key,
                        "reason": f"order_{state_val.lower()}",
                    }),
                )
            )
            ord_idx += 1

        if cleared_pending_close_position_key:
            events.append(
                AuditEvent(
                    event_id=derive_audit_event_id(
                        event_family=AuditEventFamily.PROTECTIVE_LIFECYCLE,
                        event_type=AuditEventType.PROTECTIVE_CLOSE_CANCELLED_REARMED,
                        aggregate_type="PROTECTIVE",
                        aggregate_identity=order_id,
                        state_generation=None,
                        transaction_event_ordinal=ord_idx,
                        canonical_domain_identity=f"{order_id}:REARMED",
                    ),
                    event_family=AuditEventFamily.PROTECTIVE_LIFECYCLE.value,
                    event_type=AuditEventType.PROTECTIVE_CLOSE_CANCELLED_REARMED.value,
                    aggregate_type="PROTECTIVE",
                    aggregate_identity=order_id,
                    market_timestamp=m_ts,
                    recorded_at_utc=recorded_at_utc_now(),
                    transaction_event_ordinal=ord_idx,
                    broker_order_identity=terminal_event.broker_order_identity,
                    position_key_json=canonical_json_dumps(_position_key_to_dict(cleared_pending_close_position_key)),
                    payload_json=canonical_json_dumps({
                        "order_id": order_id,
                        "reason": "protective_close_terminal_non_fill_rearmed",
                    }),
                )
            )
            ord_idx += 1

        if entry_intent_id:
            events.append(
                AuditEvent(
                    event_id=derive_audit_event_id(
                        event_family=AuditEventFamily.ENTRY_INTENT,
                        event_type=AuditEventType.INTENT_TERMINATED,
                        aggregate_type="ENTRY_INTENT",
                        aggregate_identity=entry_intent_id,
                        state_generation=None,
                        transaction_event_ordinal=ord_idx,
                        canonical_domain_identity=entry_intent_id,
                    ),
                    event_family=AuditEventFamily.ENTRY_INTENT.value,
                    event_type=AuditEventType.INTENT_TERMINATED.value,
                    aggregate_type="ENTRY_INTENT",
                    aggregate_identity=entry_intent_id,
                    market_timestamp=m_ts,
                    recorded_at_utc=recorded_at_utc_now(),
                    transaction_event_ordinal=ord_idx,
                    entry_intent_identity=entry_intent_id,
                    payload_json=canonical_json_dumps({
                        "intent_id": entry_intent_id,
                        "lifecycle_state": state_val,
                    }),
                )
            )
            ord_idx += 1

        return tuple(events)

    # ------------------------------------------------------------------
    # Signal Intake & Immediate/Deferred Dispatch
    # ------------------------------------------------------------------

    def process_signal(
        self,
        *,
        intent: SignalIntent,
        policy: OptionSelectionPolicy,
        underlying_price: Decimal | int | float | str,
        selection_timestamp: datetime,
        expiry_boundary: datetime,
        strategy_state: dict[str, Any] | None = None,
        evaluation_decision_time: datetime | None = None,
    ) -> CoordinatorEntryResult:
        """Process one Strategy SignalIntent through selection, bridge, gate, and broker."""
        if not self.is_persistence_healthy:
            raise RuntimeError("Persistence health is FAILED; signal intake blocked")
        if not isinstance(intent, SignalIntent):
            raise TypeError("intent must be a SignalIntent")
        if not isinstance(policy, OptionSelectionPolicy):
            raise TypeError("policy must be an OptionSelectionPolicy")
        price = as_decimal(underlying_price, "underlying_price")
        if price <= Decimal("0"):
            raise ValueError("underlying_price must be positive")
        if not isinstance(selection_timestamp, datetime) or selection_timestamp.tzinfo is None:
            raise ValueError("selection_timestamp must be a timezone-aware datetime")
        if not isinstance(expiry_boundary, datetime) or expiry_boundary.tzinfo is None:
            raise ValueError("expiry_boundary must be a timezone-aware datetime")
        if expiry_boundary <= selection_timestamp:
            raise ValueError("expiry_boundary must be strictly after selection_timestamp")


        if intent.action == "HOLD":
            return CoordinatorEntryResult(
                outcome=CoordinatorOutcome.REJECTED,
                intent_id=f"hold:{intent.strategy_id}:{intent.strategy_version}:{intent.symbol}:{intent.originating_timestamp.isoformat()}",
                rejection_reason="hold_signal_not_actionable",
            )

        # Emit actionable signal audit (BUY/SELL)
        self._emit_signal_audit(intent)

        # Step 1: Pure OptionSelector preselection
        selector = OptionSelector(self._catalog)
        selection = selector.select(
            intent=intent,
            policy=policy,
            underlying_price=price,
            selection_timestamp=selection_timestamp,
        )

        if isinstance(selection, OptionSelectionRejection):
            intent_id = f"unresolved:{intent.strategy_id}:{intent.strategy_version}:{intent.symbol}:{intent.originating_timestamp.isoformat()}"
            self._intent_lifecycle[intent_id] = _IntentLifecycle.TERMINAL_REJECTED
            self._emit_option_selection_rejected_audit(intent, selection.reason)
            return CoordinatorEntryResult(
                outcome=CoordinatorOutcome.REJECTED,
                intent_id=intent_id,
                rejection_reason=selection.reason,
                rejection_evidence=selection,
            )

        selected_entry = selection  # ResolvedOptionEntry
        selected_identity = selected_entry.selected_identity
        self._emit_option_selected_audit(intent, selected_entry)

        # Step 2: Compute canonical entry intent identity
        intent_id = entry_intent_identity(
            strategy_id=intent.strategy_id,
            strategy_version=intent.strategy_version,
            identity=selected_identity,
            timeframe=intent.timeframe,
            originating_timestamp=intent.originating_timestamp,
        )

        # Step 3: Check duplicate signal intent
        if intent_id in self._intent_lifecycle:
            self._emit_duplicate_signal_rejection_audit(intent, intent_id, selected_identity)
            return CoordinatorEntryResult(
                outcome=CoordinatorOutcome.REJECTED,
                intent_id=intent_id,
                selected_identity=selected_identity,
                rejection_reason="duplicate_signal_intent",
            )

        # Step 4: Check safety state and reconciliation health
        if self.safety_state != SafetyState.OPERATIONAL:
            self._intent_lifecycle[intent_id] = _IntentLifecycle.TERMINAL_REJECTED
            if self._virtual_account is not None and self._virtual_account.valuation_state != ValuationState.LIVE:
                reason = "valuation_stale_or_unavailable"
            elif self.safety_state == SafetyState.DISCONNECTED:
                reason = "feed_not_connected"
            else:
                reason = f"safety_state_{self.safety_state.value.lower()}"
            return CoordinatorEntryResult(
                outcome=CoordinatorOutcome.REJECTED,
                intent_id=intent_id,
                selected_identity=selected_identity,
                rejection_reason=reason,
            )

        if not self.is_reconciliation_healthy:
            self._intent_lifecycle[intent_id] = _IntentLifecycle.TERMINAL_REJECTED
            return CoordinatorEntryResult(
                outcome=CoordinatorOutcome.REJECTED,
                intent_id=intent_id,
                selected_identity=selected_identity,
                rejection_reason=f"reconciliation_{self._reconciliation_health.value.lower()}",
            )

        # Step 5: Register subscription claim group
        owner = SubscriptionOwnerKey(intent.strategy_id, intent.strategy_version)
        self._add_claim(owner, selected_identity, intent_id)

        # Step 6: Sample quote cache
        quote = self._quote_cache.get(selected_identity)

        if quote is None:
            # Cache miss: register pending attempt awaiting waking quote
            attempt = PendingOptionEntryAttempt(
                intent=intent,
                policy=policy,
                underlying_price=price,
                selection_timestamp=selection_timestamp,
                selected_entry=selected_entry,
                owner=owner,
                expiry_boundary=expiry_boundary,
            )
            self._pending_by_intent[intent_id] = attempt
            self._pending_intents_by_identity.setdefault(selected_identity, set()).add(intent_id)
            self._intent_lifecycle[intent_id] = _IntentLifecycle.PENDING
            return CoordinatorEntryResult(
                outcome=CoordinatorOutcome.PENDING,
                intent_id=intent_id,
                selected_identity=selected_identity,
            )


        # Step 7: Immediate bridge evaluation with fresh runtime context
        try:
            context = self._get_runtime_context(selection_timestamp)
        except (ValuationUnavailableError, VirtualAccountInvariantError) as exc:
            self._intent_lifecycle[intent_id] = _IntentLifecycle.TERMINAL_REJECTED
            self._remove_claim(owner, selected_identity, intent_id)
            return CoordinatorEntryResult(
                outcome=CoordinatorOutcome.REJECTED,
                intent_id=intent_id,
                selected_identity=selected_identity,
                rejection_reason="valuation_stale_or_unavailable",
                rejection_evidence=str(exc),
            )

        bridge_result = self._option_bridge.build_option_entry(
            intent=intent,
            policy=policy,
            underlying_price=price,
            selection_timestamp=selection_timestamp,
            option_quote=quote,
            specification=selected_entry.selected_specification,
            risk_day=context.risk_day,
            snapshot=context.snapshot,
            protective_book=context.protective_book,
            current_net_equity=context.current_net_equity,
            starting_capital=context.starting_capital,
            prior_risk_state=context.prior_risk_state,
            pending_commitments=context.pending_commitments,
            cost_projection=context.cost_projection,
        )

        if isinstance(bridge_result, (OptionSelectionRejection, OptionEntryRejection)):
            self._intent_lifecycle[intent_id] = _IntentLifecycle.TERMINAL_REJECTED
            self._remove_claim(owner, selected_identity, intent_id)
            if isinstance(bridge_result, OptionEntryRejection):
                self._emit_risk_rejected_audit(intent, selected_identity, bridge_result.reason)
            else:
                self._emit_option_selection_rejected_audit(intent, bridge_result.reason)
            return CoordinatorEntryResult(
                outcome=CoordinatorOutcome.REJECTED,
                intent_id=intent_id,
                selected_identity=selected_identity,
                rejection_reason=bridge_result.reason,
                rejection_evidence=bridge_result,
            )
        elif isinstance(bridge_result, OptionEntryResult):
            self._emit_risk_approved_audit(intent, selected_identity, bridge_result, context.risk_day)

        # Step 7.5: Premium cash reservation (VA-4 / VA-4A / VA-4B / VA-4C)
        res_key = entry_intent_identity(
            strategy_id=intent.strategy_id,
            strategy_version=intent.strategy_version,
            identity=selected_identity,
            timeframe=intent.timeframe,
            originating_timestamp=intent.originating_timestamp,
        )
        if self._virtual_account is not None:
            res_ok = self._virtual_account.reserve_premium(
                reservation_key=res_key,
                strategy_id=intent.strategy_id,
                strategy_version=intent.strategy_version,
                identity=selected_identity,
                approved_quantity=bridge_result.instruction.quantity,
                worst_permitted_fill_price=bridge_result.worst_permitted_fill,
                contract_multiplier=selected_entry.selected_specification.contract_multiplier,
                market_time=selection_timestamp,
            )
            if not res_ok:
                self._intent_lifecycle[intent_id] = _IntentLifecycle.TERMINAL_REJECTED
                self._remove_claim(owner, selected_identity, intent_id)
                return CoordinatorEntryResult(
                    outcome=CoordinatorOutcome.REJECTED,
                    intent_id=intent_id,
                    selected_identity=selected_identity,
                    bridge_result=bridge_result,
                    rejection_reason="insufficient_available_cash",
                )

        pending_risk_commitment = self._pending_risk_commitment_from_approval(
            entry_identity=res_key,
            bridge_result=bridge_result,
        )
        self._retain_pending_risk_commitment(pending_risk_commitment)
        self._record_risk_gate_state(bridge_result)

        # Step 8: Submit approved order to SimulatedPaperBroker (with rollback VA-4D)
        try:
            submission = self._paper_broker.submit(
                order=bridge_result.instruction,
                instrument_identity=selected_identity,
                specification=selected_entry.selected_specification,
                submission_quote=bridge_result.submission_quote,
                submission_market_timestamp=selection_timestamp,
            )
        except Exception:
            if self._virtual_account is not None:
                self._virtual_account.release_reservation(res_key, reason="broker_submit_exception")
            self._release_pending_risk_commitment(res_key)
            raise

        if submission.accepted:
            self._intent_lifecycle[intent_id] = _IntentLifecycle.SUBMITTED
            if submission.order_id is not None:
                self._retained_plans[submission.order_id] = (
                    bridge_result.plan,
                    bridge_result.instruction.quantity,
                    submission.broker_order_identity,
                )
                if self._persistence_store is not None:
                    po = self._get_broker_pending_order(submission.order_id)
                    commitment = next(
                        (c for c in (self._virtual_account.active_commitments if self._virtual_account else ()) if c.reservation_key == res_key),
                        None,
                    )
                    if po is not None and commitment is not None:
                        try:
                            t1_events = self._build_t1_audit_events(
                                intent_id=intent_id,
                                strategy_id=intent.strategy_id,
                                strategy_version=intent.strategy_version,
                                instrument_key=getattr(commitment, "instrument_key", getattr(commitment.identity, "instrument", str(commitment.identity))),
                                order_id=submission.order_id,
                                broker_order_identity=submission.broker_order_identity,
                                commitment=commitment,
                                order=po,
                                plan=bridge_result.plan,
                                market_timestamp=selection_timestamp,
                            )
                            st_trans = None
                            if strategy_state is not None:
                                st_trans = StrategyStateTransition(
                                    strategy_id=intent.strategy_id,
                                    strategy_version=intent.strategy_version,
                                    state=strategy_state,
                                    last_evaluated_decision_time=evaluation_decision_time or selection_timestamp,
                                )
                            self._persistence_store.save_t1_entry_submission(
                                intent_id=intent_id,
                                order=po,
                                commitment=commitment,
                                plan=bridge_result.plan,
                                nominal_stop_risk=pending_risk_commitment.nominal_stop_risk,
                                run_identity=f"live_{submission.order_id}",
                                strategy_state_transition=st_trans,
                                audit_events=t1_events,
                            )
                            self._on_state_transition_committed()
                        except Exception as p_err:
                            self._persistence_failed = True
                            logger.critical("Failed T1 persistence commit: %s", p_err, exc_info=True)
                            raise
            return CoordinatorEntryResult(
                outcome=CoordinatorOutcome.SUBMITTED,
                intent_id=intent_id,
                selected_identity=selected_identity,
                submission_result=submission,
                bridge_result=bridge_result,
            )
        else:
            if self._virtual_account is not None:
                self._virtual_account.release_reservation(res_key, reason=f"broker_rejected_{submission.reason}")
            self._release_pending_risk_commitment(res_key)
            self._intent_lifecycle[intent_id] = _IntentLifecycle.TERMINAL_REJECTED
            self._remove_claim(owner, selected_identity, intent_id)
            return CoordinatorEntryResult(
                outcome=CoordinatorOutcome.REJECTED,
                intent_id=intent_id,
                selected_identity=selected_identity,
                submission_result=submission,
                bridge_result=bridge_result,
                rejection_reason=submission.reason,
                rejection_evidence=submission,
            )

    # ------------------------------------------------------------------
    # Live Quote Processing & Deferred Resume
    # ------------------------------------------------------------------

    def _protective_book_snapshot(self) -> tuple:
        """Exact comparable pre-pass state of the canonical protective book.

        ``ProtectiveExit`` values are frozen dataclasses with structural
        equality, so this tuple comparison detects ANY mid-pass mutation
        (ratchet application, state change) deterministically.
        """
        return tuple(sorted(self._protective_evaluator.book.exits.items()))

    def _route_protective_evaluation_failure(
        self,
        exc: Exception,
        *,
        book_before: tuple,
    ) -> None:
        """Phase 8 P1-C protective/runtime failure routing (§128.5/§128.12).

        Classification uses ONLY the CURRENT canonical safety taxonomy:

        * ``StrategyCallbackFailure`` — a STRATEGY-owned runtime-policy
          callback raised.  Canonical Rule-7 ERROR evidence and the
          per-session error count were already recorded by the wired
          evaluator observer (§128.1/§128.3) BEFORE this failure
          propagated; no second count/evidence is emitted here.
        * Any other exception — an ENGINE-side protective evaluation
          failure: contained non-strategy runtime error evidence via the
          existing ``record_runtime_error`` seam, then §128.12 routing.

        Scope decision (§128.12 OD-8): if ownership is ambiguous OR
        integrity/accounting safety cannot be proven ⇒ GLOBAL fail closed.
        When the aborted pass left uncommitted book mutations behind,
        broader integrity safety cannot be proven ⇒ GLOBAL
        ``PROTECTIVE_AMBIGUITY`` escalation + GLOBAL human review through
        the existing controller API.  No new classification is invented.
        """
        logger.critical(
            "protective evaluation failed; routing through Phase-8 safety; "
            "cause=%r",
            exc,
            exc_info=True,
        )
        controller = self._phase8_safety
        if isinstance(exc, StrategyCallbackFailure):
            # Strategy-owned callback failure: evidence + count already done.
            if controller is not None:
                if tuple(sorted(self._protective_evaluator.book.exits.items())) != book_before:
                    # Aborted pass mutated the book mid-way; integrity unproven.
                    controller.observe_protective_failure(
                        strategy_id=None,
                        strategy_version=None,
                        integrity_proven_safe=False,
                    )
                else:
                    # Provably zero book mutations from the aborted pass;
                    # attributable owner already isolated by §128.1 path.
                    pass
            return
        # Engine-side failure: canonical ERROR evidence first.
        record_runtime_error(exc)
        if controller is not None:
            controller.observe_protective_failure(
                strategy_id=None,
                strategy_version=None,
                integrity_proven_safe=False,
            )

    def on_live_quote(self, event: LiveQuoteEvent) -> LiveQuoteProcessingResult:
        """Process incoming live quote, dispatch to broker, evaluate protective exits, and resume eligible pending attempts."""
        if not isinstance(event, LiveQuoteEvent):
            raise TypeError("event must be a LiveQuoteEvent")

        self._latest_market_timestamp = event.quote.exchange_timestamp
        # Phase 8 P1 (§128.11): canonical MARKET-DATA heartbeat evidence.
        self._latest_quote_market_timestamp = event.quote.exchange_timestamp
        self._has_received_quote = True
        q_date = event.quote.exchange_timestamp.date()
        if self._last_canonical_session_date is None or q_date > self._last_canonical_session_date:
            self._last_canonical_session_date = q_date

        if not self.is_persistence_healthy:
            raise RuntimeError("Persistence health is FAILED; quote processing blocked")

        quote_result = self._quote_cache.on_quote_event(event)

        # Dispatch downstream ONLY when quote was newly ACCEPTED
        if quote_result.status is not QuoteCacheStatus.ACCEPTED:
            return LiveQuoteProcessingResult(
                quote_result=quote_result,
                broker_events=(),
                entry_results=(),
                protective_triggers=(),
            )

        quote = event.quote
        ident = quote.instrument_identity

        # Phase 8 P1 (§128.11): a freshly ACCEPTED quote is canonical fresh-
        # market-evidence.  Recording it as a healthy heartbeat updates the
        # controller's health view ONLY — a fresh transition establishes
        # resume ELIGIBILITY and never clears a latch or auto-resumes.
        if self._phase8_safety is not None:
            self._phase8_safety.observe_market_data_timestamp(
                latest_market_timestamp=event.quote.exchange_timestamp,
                reference_timestamp=event.quote.exchange_timestamp,
            )


        # 1. Dispatch BrokerQuoteEvent to paper broker
        broker_event = BrokerQuoteEvent(
            event_id=event.event_id,
            quote=quote,
            authority_timestamp=quote.exchange_timestamp,
        )
        broker_terminal_events = tuple(self._paper_broker.on_quote_event(broker_event))

        # 2. Process terminal events delivered from broker
        for term_ev in broker_terminal_events:
            # 2.1 Deliver to VirtualPaperAccount first (VA-11 / VA-11A)
            if self._virtual_account is not None:
                self._apply_broker_terminal_event(term_ev)

            # 2.2 Handle opening entry plan lifecycle
            if term_ev.order_id in self._retained_plans:
                # The persistence transaction is the terminal accounting
                # record, but its reconciliation callback must observe the
                # post-terminal Q60 state.  Defer that callback until after
                # the exact pending-risk evidence has been released below.
                reconcile_after_pending_risk_release = False
                if term_ev.lifecycle_state == OrderLifecycleState.FILLED:
                    plan, qty, expected_ident = self._retained_plans.pop(term_ev.order_id)
                    if expected_ident is not None and term_ev.broker_order_identity != expected_ident:
                        raise ValueError(
                            f"broker_order_identity mismatch on opening fill: "
                            f"expected {expected_ident}, got {term_ev.broker_order_identity}"
                        )
                    materialize_protective_plan(
                        plan,
                        run_identity=f"live_{term_ev.order_id}",
                        quantity=qty,
                        book=self._protective_evaluator.book,
                    )
                    if self._persistence_store is not None:
                        try:
                            prev = (
                                self._virtual_account.processed_fills.get(term_ev.broker_order_identity)
                                if self._virtual_account
                                else None
                            )
                            acc_res = prev[1] if prev else None
                            if acc_res is not None and self._virtual_account is not None:
                                mat_exits = tuple(self._protective_evaluator.book.exits.values())
                                t2_events = self._build_t2_audit_events(
                                    terminal_event=term_ev,
                                    accounting_result=acc_res,
                                    account_snapshot=self._virtual_account.snapshot,
                                    accounting_sequence=self._virtual_account.accounting_sequence,
                                    materialized_exits=mat_exits,
                                )
                                orig_order = term_ev.original_order
                                res_key = entry_intent_identity(
                                    strategy_id=orig_order.strategy_id,
                                    strategy_version=orig_order.strategy_version,
                                    identity=term_ev.instrument_identity,
                                    timeframe=orig_order.timeframe,
                                    originating_timestamp=orig_order.originating_timestamp,
                                )
                                self._risk_gate_state = (
                                    self._risk_gate_state.record_entry_fill(res_key)
                                    if self._risk_gate_state is not None
                                    else None
                                )
                                self._sync_risk_gate_equity()
                                self._persistence_store.save_t2_opening_fill(
                                    terminal_event=term_ev,
                                    accounting_result=acc_res,
                                    account_snapshot=self._virtual_account.snapshot,
                                    accounting_sequence=self._virtual_account.accounting_sequence,
                                    released_reservation_key=res_key,
                                    materialized_exits=mat_exits,
                                    retained_order_id_to_remove=term_ev.order_id,
                                    risk_gate_state=self._risk_gate_state,
                                    audit_events=t2_events,
                                )
                                reconcile_after_pending_risk_release = True
                        except Exception as p_err:
                            self._persistence_failed = True
                            logger.critical("Failed T2 persistence commit: %s", p_err, exc_info=True)
                            raise
                elif term_ev.lifecycle_state in (
                    OrderLifecycleState.CANCELLED,
                    OrderLifecycleState.EXPIRED,
                    OrderLifecycleState.REJECTED,
                ):
                    self._retained_plans.pop(term_ev.order_id, None)
                    if self._persistence_store is not None:
                        try:
                            orig_order = term_ev.original_order
                            res_key = entry_intent_identity(
                                strategy_id=orig_order.strategy_id,
                                strategy_version=orig_order.strategy_version,
                                identity=term_ev.instrument_identity,
                                timeframe=orig_order.timeframe,
                                originating_timestamp=orig_order.originating_timestamp,
                            )
                            t5_events = self._build_t5_audit_events(
                                terminal_event=term_ev,
                                released_reservation_key=res_key,
                                entry_intent_id=res_key,
                            )
                            self._persistence_store.save_t5_terminal_non_fill(
                                terminal_event=term_ev,
                                released_reservation_key=res_key,
                                retained_order_id_to_remove=term_ev.order_id,
                                audit_events=t5_events,
                            )
                            reconcile_after_pending_risk_release = True
                        except Exception as p_err:
                            self._persistence_failed = True
                            logger.critical("Failed T5 opening persistence commit: %s", p_err, exc_info=True)
                            raise
                # VirtualPaperAccount has applied the accepted fill before this
                # release, so Q60 transitions directly from pending evidence to
                # the resulting open-position evidence without a gap.
                self._release_pending_risk_commitment(
                    self._entry_identity_for_terminal_event(term_ev)
                )
                if reconcile_after_pending_risk_release:
                    self._on_state_transition_committed()

            # 2.3 Handle protective close lifecycle
            if term_ev.order_id in self._protective_evaluator.pending_closes_by_order_id:
                pending = self._protective_evaluator.pending_closes_by_order_id.get(term_ev.order_id)
                if term_ev.lifecycle_state == OrderLifecycleState.FILLED:
                    self._protective_evaluator.on_external_fill(
                        term_ev.order_id, term_ev.broker_order_identity
                    )
                    if self._virtual_account is not None and pending is not None:
                        self._protective_evaluator.reconcile_position(
                            pending.position_key, self._virtual_account.snapshot
                        )
                    if self._persistence_store is not None:
                        try:
                            prev = (
                                self._virtual_account.processed_fills.get(term_ev.broker_order_identity)
                                if self._virtual_account
                                else None
                            )
                            acc_res = prev[1] if prev else None
                            if acc_res is not None and self._virtual_account is not None:
                                upd_exits = tuple(self._protective_evaluator.book.exits.values())
                                completed_trades = (
                                    self._virtual_account.trade_ledger.completed_trades()
                                    if (self._virtual_account and self._virtual_account.trade_ledger)
                                    else ()
                                )
                                last_trade = completed_trades[-1] if completed_trades else None
                                t4_events = self._build_t4_audit_events(
                                    terminal_event=term_ev,
                                    accounting_result=acc_res,
                                    account_snapshot=self._virtual_account.snapshot,
                                    accounting_sequence=self._virtual_account.accounting_sequence,
                                    cleared_pending=pending,
                                    updated_exits=upd_exits,
                                    trade_record=last_trade,
                                )
                                self._persistence_store.save_t4_protective_fill(
                                    terminal_event=term_ev,
                                    accounting_result=acc_res,
                                    account_snapshot=self._virtual_account.snapshot,
                                    accounting_sequence=self._virtual_account.accounting_sequence,
                                    cleared_pending_close_position_key=pending.position_key if pending else None,
                                    updated_exits=upd_exits,
                                    trade_ledger=self._virtual_account.trade_ledger,
                                    audit_events=t4_events,
                                )
                                self._on_state_transition_committed()
                        except Exception as p_err:
                            self._persistence_failed = True
                            logger.critical("Failed T4 persistence commit: %s", p_err, exc_info=True)
                            raise
                elif term_ev.lifecycle_state in (
                    OrderLifecycleState.CANCELLED,
                    OrderLifecycleState.EXPIRED,
                    OrderLifecycleState.REJECTED,
                ):
                    self._protective_evaluator.on_external_terminal_failure(
                        term_ev.order_id, reason=str(term_ev.lifecycle_state.value)
                    )
                    if self._persistence_store is not None:
                        try:
                            t5_events = self._build_t5_audit_events(
                                terminal_event=term_ev,
                                cleared_pending_close_position_key=pending.position_key if pending else None,
                            )
                            self._persistence_store.save_t5_terminal_non_fill(
                                terminal_event=term_ev,
                                cleared_pending_close_position_key=pending.position_key if pending else None,
                                audit_events=t5_events,
                            )
                            self._on_state_transition_committed()
                        except Exception as p_err:
                            self._persistence_failed = True
                            logger.critical("Failed T5 protective persistence commit: %s", p_err, exc_info=True)
                            raise

            # 2.4 Handle generic strategy-exit close lifecycle (non-protective).
            # Same normal order/accounting infrastructure as protective closes;
            # only the pending-close authority differs: no protective book
            # mutation at submission, no protective_pending_closes row, and the
            # confirmed fill reconciles obsolete protection through the
            # existing engine-owned reconcile_position path.
            if term_ev.order_id in self._strategy_pending_by_order_id:
                sp = self._strategy_pending_by_order_id.get(term_ev.order_id)
                if term_ev.lifecycle_state == OrderLifecycleState.FILLED:
                    self._clear_strategy_pending_by_order_id(term_ev.order_id)
                    if self._virtual_account is not None and sp is not None:
                        # Confirmed close fill: cancel obsolete protection for
                        # the now-closed position via the canonical book path.
                        self._protective_evaluator.reconcile_position(
                            sp.position_key, self._virtual_account.snapshot
                        )
                    if self._persistence_store is not None:
                        try:
                            prev = (
                                self._virtual_account.processed_fills.get(term_ev.broker_order_identity)
                                if self._virtual_account
                                else None
                            )
                            acc_res = prev[1] if prev else None
                            if acc_res is not None and self._virtual_account is not None:
                                upd_exits = tuple(self._protective_evaluator.book.exits.values())
                                completed_trades = (
                                    self._virtual_account.trade_ledger.completed_trades()
                                    if (self._virtual_account and self._virtual_account.trade_ledger)
                                    else ()
                                )
                                last_trade = completed_trades[-1] if completed_trades else None
                                t4_events = self._build_t4_audit_events(
                                    terminal_event=term_ev,
                                    accounting_result=acc_res,
                                    account_snapshot=self._virtual_account.snapshot,
                                    accounting_sequence=self._virtual_account.accounting_sequence,
                                    cleared_pending=None,
                                    updated_exits=upd_exits,
                                    trade_record=last_trade,
                                )
                                # cleared_pending_close_position_key stays None:
                                # nothing protective was ever queued for this
                                # order, so no protective row may be deleted.
                                self._persistence_store.save_t4_protective_fill(
                                    terminal_event=term_ev,
                                    accounting_result=acc_res,
                                    account_snapshot=self._virtual_account.snapshot,
                                    accounting_sequence=self._virtual_account.accounting_sequence,
                                    cleared_pending_close_position_key=None,
                                    updated_exits=upd_exits,
                                    trade_ledger=self._virtual_account.trade_ledger,
                                    audit_events=t4_events,
                                )
                                self._on_state_transition_committed()
                        except Exception as p_err:
                            self._persistence_failed = True
                            logger.critical("Failed strategy-exit fill persistence commit: %s", p_err, exc_info=True)
                            raise
                elif term_ev.lifecycle_state in (
                    OrderLifecycleState.CANCELLED,
                    OrderLifecycleState.EXPIRED,
                    OrderLifecycleState.REJECTED,
                ):
                    self._clear_strategy_pending_by_order_id(term_ev.order_id)
                    if self._persistence_store is not None:
                        try:
                            t5_events = self._build_t5_audit_events(
                                terminal_event=term_ev,
                            )
                            self._persistence_store.save_t5_terminal_non_fill(
                                terminal_event=term_ev,
                                audit_events=t5_events,
                            )
                            self._on_state_transition_committed()
                        except Exception as p_err:
                            self._persistence_failed = True
                            logger.critical("Failed strategy-exit non-fill persistence commit: %s", p_err, exc_info=True)
                            raise

        # 3. Deliver live quote to VirtualPaperAccount for live MTM (VA-6)
        if self._virtual_account is not None:
            self._virtual_account.on_quote(quote)

        # 4. Live Protective Evaluation (Protective Autonomy: active on fresh BID when not PERSISTENCE_FAILED or INTEGRITY_BREACHED)
        protective_triggers: list[LiveProtectiveTrigger] = []
        if (
            self._virtual_account is not None
            and self.safety_state not in (SafetyState.PERSISTENCE_FAILED, SafetyState.INTEGRITY_BREACHED)
        ):
            spec = self._find_specification_for_identity(ident, quote.exchange_timestamp.date())
            if spec is not None:
                # Phase 8 P1 (§128.12): integrity evidence for the aborted-
                # pass containment below — exact pre-pass book state.
                book_before = self._protective_book_snapshot()
                try:
                    triggers, ratchets = self._protective_evaluator.evaluate_quote_with_ratchets(
                        quote=quote,
                        snapshot=self._virtual_account.snapshot,
                        specification=spec,
                    )
                except Exception as exc:
                    # Phase 8 P1-C failure routing: canonical ERROR evidence
                    # + Phase8SafetyController observer + correct safety-state
                    # transition BEFORE any continuation decision.
                    self._route_protective_evaluation_failure(exc, book_before=book_before)
                    # Containment: the aborted pass yields ZERO orders /
                    # ratchets / target mutations from THIS quote.  Processing
                    # continues so unrelated strategies stay isolated (§128.1)
                    # and PROTECTIVE autonomy stays live (reduce-only authority
                    # is never blanket-disabled); the routed safety state gates
                    # everything else through the existing frozen precedence.
                    triggers, ratchets = (), ()
                if ratchets and self._persistence_store is not None:
                    t6_events = [
                        AuditEvent(
                            event_id=derive_audit_event_id(
                                event_family=AuditEventFamily.PROTECTIVE_LIFECYCLE,
                                event_type=AuditEventType.TRAILING_RATCHETED,
                                aggregate_type="PROTECTIVE",
                                aggregate_identity=r.protective_id,
                                state_generation=None,
                                transaction_event_ordinal=ord_idx,
                                canonical_domain_identity=f"{r.protective_id}:{str(r.new_stop)}",
                            ),
                            event_family=AuditEventFamily.PROTECTIVE_LIFECYCLE.value,
                            event_type=AuditEventType.TRAILING_RATCHETED.value,
                            aggregate_type="PROTECTIVE",
                            aggregate_identity=r.protective_id,
                            market_timestamp=r.market_timestamp,
                            recorded_at_utc=recorded_at_utc_now(),
                            transaction_event_ordinal=ord_idx,
                            protective_id=r.protective_id,
                            position_key_json=canonical_json_dumps(_position_key_to_dict(r.position_key)),
                            payload_json=canonical_json_dumps({
                                "protective_id": r.protective_id,
                                "old_stop": str(r.old_stop),
                                "new_stop": str(r.new_stop),
                                "old_reference_extreme": str(r.old_reference_extreme),
                                "new_reference_extreme": str(r.new_reference_extreme),
                                "effective_after": r.effective_after.isoformat(),
                            }),
                        )
                        for ord_idx, r in enumerate(ratchets)
                    ]
                    trailing_state_transitions = tuple(
                        r.state_transition for r in ratchets if r.state_transition is not None
                    )
                    trailing_expected_gens: dict[tuple[str, str], int] | None = None
                    if trailing_state_transitions:
                        trailing_expected_gens = {}
                        for st in trailing_state_transitions:
                            gen = self._strategy_state_generation.get(
                                (st.strategy_id, st.strategy_version)
                            )
                            trailing_expected_gens[(st.strategy_id, st.strategy_version)] = (
                                gen if gen is not None else 0
                            )
                    try:
                        advanced = self._persistence_store.save_t6_trailing_ratchet(
                            tuple(self._protective_evaluator.book.exits.values()),
                            audit_events=t6_events,
                            strategy_state_transitions=trailing_state_transitions,
                            expected_state_generations=trailing_expected_gens,
                        )
                        for (sid, sver), new_gen in advanced.items():
                            self._strategy_state_generation[(sid, sver)] = new_gen
                        self._on_state_transition_committed()
                    except Exception as p_err:
                        self._persistence_failed = True
                        record_runtime_error(p_err)
                        logger.critical("Failed T6 persistence commit: %s", p_err, exc_info=True)
                        raise

                for trigger in triggers:
                    if not self.can_execute_protective_exit(trigger.position_key):
                        continue
                    # One close in flight per authoritative position: a pending
                    # generic strategy close suppresses competing protective
                    # submissions (duplicate-close exposure guard).
                    if self.has_pending_strategy_exit(trigger.position_key):
                        continue

                    try:
                        submission = self._paper_broker.submit(
                            order=trigger.close_instruction,
                            instrument_identity=trigger.position_key.identity,
                            specification=spec,
                            submission_quote=quote,
                            submission_market_timestamp=quote.exchange_timestamp,
                        )
                    except Exception:
                        continue

                    if submission.accepted:
                        pending = LiveProtectivePendingClose(
                            position_key=trigger.position_key,
                            protective_id=trigger.protective.protective_id,
                            order_id=submission.order_id,
                            broker_order_identity=submission.broker_order_identity,
                            kind=trigger.kind,
                            trigger_price=trigger.trigger_price,
                            trigger_timestamp=trigger.trigger_timestamp,
                        )
                        self._protective_evaluator.register_pending_close(pending)
                        protective_triggers.append(trigger)
                        if self._persistence_store is not None and submission.order_id is not None:
                            # Internal pending-order view: carries the exact
                            # specification required for lossless hydration of
                            # the durable close row (the public record view
                            # lacks ``specification``).
                            close_order = self._get_broker_pending_order(submission.order_id)
                            if close_order is not None:
                                try:
                                    t3_events = self._build_t3_audit_events(
                                        pending_close=pending,
                                        close_order=close_order,
                                    )
                                    self._persistence_store.save_t3_protective_submission(
                                        pending_close=pending,
                                        close_order=close_order,
                                        updated_exits=tuple(self._protective_evaluator.book.exits.values()),
                                        audit_events=t3_events,
                                    )
                                    self._on_state_transition_committed()
                                except Exception as p_err:
                                    self._persistence_failed = True
                                    record_runtime_error(p_err)
                                    logger.critical("Failed T3 persistence commit: %s", p_err, exc_info=True)
                                    raise

        # 5. Check pending attempts for this identity (Gated strictly to OPERATIONAL safety state and healthy reconciliation)
        if self.safety_state != SafetyState.OPERATIONAL or not self.is_reconciliation_healthy:
            return LiveQuoteProcessingResult(
                quote_result=quote_result,
                broker_events=broker_terminal_events,
                entry_results=(),
                protective_triggers=tuple(protective_triggers),
            )

        intent_ids = list(self._pending_intents_by_identity.get(ident, ()))
        if not intent_ids:
            return LiveQuoteProcessingResult(
                quote_result=quote_result,
                broker_events=broker_terminal_events,
                entry_results=(),
                protective_triggers=tuple(protective_triggers),
            )

        expired_results: list[CoordinatorEntryResult] = []
        eligible_attempts: list[tuple[str, PendingOptionEntryAttempt]] = []

        # 6. Separate expired vs eligible attempts
        for intent_id in intent_ids:
            attempt = self._pending_by_intent.get(intent_id)
            if attempt is None:
                continue

            if quote.exchange_timestamp >= attempt.expiry_boundary:
                # Expired at boundary (>= rule: bar-bound expiry wins)
                self._intent_lifecycle[intent_id] = _IntentLifecycle.TERMINAL_REJECTED
                del self._pending_by_intent[intent_id]
                self._pending_intents_by_identity[ident].discard(intent_id)
                self._remove_claim(attempt.owner, ident, intent_id)
                expired_results.append(
                    CoordinatorEntryResult(
                        outcome=CoordinatorOutcome.REJECTED,
                        intent_id=intent_id,
                        selected_identity=ident,
                        rejection_reason="pending_attempt_expired_at_bar_boundary",
                    )
                )
            else:
                eligible_attempts.append((intent_id, attempt))

        # 7. Deterministic multi-attempt ordering
        # Sort by: (selection_timestamp, strategy_id, strategy_version, intent_id)
        eligible_attempts.sort(
            key=lambda x: (
                x[1].selection_timestamp,
                x[1].owner.strategy_id,
                x[1].owner.strategy_version,
                x[0],
            )
        )

        entry_results: list[CoordinatorEntryResult] = list(expired_results)

        # 8. Evaluate eligible pending attempts sequentially
        for intent_id, attempt in eligible_attempts:
            # Sample exact cached quote once
            cached_quote = self._quote_cache.get(ident)
            if cached_quote is None:
                # Ambiguous or invalid; remains unresumed
                continue

            # Fresh runtime context at waking quote exchange timestamp
            try:
                context = self._get_runtime_context(quote.exchange_timestamp)
            except (ValuationUnavailableError, VirtualAccountInvariantError) as exc:
                self._intent_lifecycle[intent_id] = _IntentLifecycle.TERMINAL_REJECTED
                del self._pending_by_intent[intent_id]
                self._pending_intents_by_identity[ident].discard(intent_id)
                self._remove_claim(attempt.owner, ident, intent_id)
                entry_results.append(
                    CoordinatorEntryResult(
                        outcome=CoordinatorOutcome.REJECTED,
                        intent_id=intent_id,
                        selected_identity=ident,
                        rejection_reason="valuation_stale_or_unavailable",
                        rejection_evidence=str(exc),
                    )
                )
                continue

            bridge_result = self._option_bridge.build_option_entry(
                intent=attempt.intent,
                policy=attempt.policy,
                underlying_price=attempt.underlying_price,
                selection_timestamp=attempt.selection_timestamp,
                option_quote=cached_quote,
                specification=attempt.selected_entry.selected_specification,
                risk_day=context.risk_day,
                snapshot=context.snapshot,
                protective_book=context.protective_book,
                current_net_equity=context.current_net_equity,
                starting_capital=context.starting_capital,
                prior_risk_state=context.prior_risk_state,
                pending_commitments=context.pending_commitments,
                cost_projection=context.cost_projection,
            )

            # Cleanup pending index regardless of bridge outcome
            del self._pending_by_intent[intent_id]
            self._pending_intents_by_identity[ident].discard(intent_id)

            if isinstance(bridge_result, (OptionSelectionRejection, OptionEntryRejection)):
                self._intent_lifecycle[intent_id] = _IntentLifecycle.TERMINAL_REJECTED
                self._remove_claim(attempt.owner, ident, intent_id)
                if isinstance(bridge_result, OptionEntryRejection):
                    self._emit_risk_rejected_audit(attempt.intent, ident, bridge_result.reason)
                else:
                    self._emit_option_selection_rejected_audit(attempt.intent, bridge_result.reason)
                entry_results.append(
                    CoordinatorEntryResult(
                        outcome=CoordinatorOutcome.REJECTED,
                        intent_id=intent_id,
                        selected_identity=ident,
                        rejection_reason=bridge_result.reason,
                        rejection_evidence=bridge_result,
                    )
                )
            elif isinstance(bridge_result, OptionEntryResult):
                self._emit_risk_approved_audit(attempt.intent, ident, bridge_result, context.risk_day)
                # Step 8.5: Premium cash reservation (VA-4 / VA-4A / VA-4B / VA-4C)
                res_key = entry_intent_identity(
                    strategy_id=attempt.intent.strategy_id,
                    strategy_version=attempt.intent.strategy_version,
                    identity=ident,
                    timeframe=attempt.intent.timeframe,
                    originating_timestamp=attempt.intent.originating_timestamp,
                )
                if self._virtual_account is not None:
                    res_ok = self._virtual_account.reserve_premium(
                        reservation_key=res_key,
                        strategy_id=attempt.intent.strategy_id,
                        strategy_version=attempt.intent.strategy_version,
                        identity=ident,
                        approved_quantity=bridge_result.instruction.quantity,
                        worst_permitted_fill_price=bridge_result.worst_permitted_fill,
                        contract_multiplier=attempt.selected_entry.selected_specification.contract_multiplier,
                        market_time=quote.exchange_timestamp,
                    )
                    if not res_ok:
                        self._intent_lifecycle[intent_id] = _IntentLifecycle.TERMINAL_REJECTED
                        self._remove_claim(attempt.owner, ident, intent_id)
                        entry_results.append(
                            CoordinatorEntryResult(
                                outcome=CoordinatorOutcome.REJECTED,
                                intent_id=intent_id,
                                selected_identity=ident,
                                bridge_result=bridge_result,
                                rejection_reason="insufficient_available_cash",
                            )
                        )
                        continue

                pending_risk_commitment = self._pending_risk_commitment_from_approval(
                    entry_identity=res_key,
                    bridge_result=bridge_result,
                )
                self._retain_pending_risk_commitment(pending_risk_commitment)
                self._record_risk_gate_state(bridge_result)

                # Step 8.6: Submit to broker with rollback (VA-4D)
                try:
                    submission = self._paper_broker.submit(
                        order=bridge_result.instruction,
                        instrument_identity=ident,
                        specification=attempt.selected_entry.selected_specification,
                        submission_quote=bridge_result.submission_quote,
                        submission_market_timestamp=quote.exchange_timestamp,
                    )
                except Exception:
                    if self._virtual_account is not None:
                        self._virtual_account.release_reservation(res_key, reason="broker_submit_exception")
                    self._release_pending_risk_commitment(res_key)
                    raise

                if submission.accepted:
                    self._intent_lifecycle[intent_id] = _IntentLifecycle.SUBMITTED
                    if submission.order_id is not None:
                        self._retained_plans[submission.order_id] = (
                            bridge_result.plan,
                            bridge_result.instruction.quantity,
                            submission.broker_order_identity,
                        )
                        if self._persistence_store is not None:
                            po = self._get_broker_pending_order(submission.order_id)
                            commitment = next(
                                (c for c in (self._virtual_account.active_commitments if self._virtual_account else ()) if c.reservation_key == res_key),
                                None,
                            )
                            if po is not None and commitment is not None:
                                try:
                                    t1_events = self._build_t1_audit_events(
                                        intent_id=intent_id,
                                        strategy_id=attempt.intent.strategy_id,
                                        strategy_version=attempt.intent.strategy_version,
                                        instrument_key=getattr(commitment, "instrument_key", getattr(commitment.identity, "instrument", str(commitment.identity))),
                                        order_id=submission.order_id,
                                        broker_order_identity=submission.broker_order_identity,
                                        commitment=commitment,
                                        order=po,
                                        plan=bridge_result.plan,
                                        market_timestamp=cached_quote.exchange_timestamp,
                                    )
                                    self._persistence_store.save_t1_entry_submission(
                                        intent_id=intent_id,
                                        order=po,
                                        commitment=commitment,
                                        plan=bridge_result.plan,
                                        nominal_stop_risk=pending_risk_commitment.nominal_stop_risk,
                                        run_identity=f"live_{submission.order_id}",
                                        audit_events=t1_events,
                                    )
                                    self._on_state_transition_committed()
                                except Exception as p_err:
                                    self._persistence_failed = True
                                    logger.critical("Failed T1 deferred persistence commit: %s", p_err, exc_info=True)
                                    raise
                    entry_results.append(
                        CoordinatorEntryResult(
                            outcome=CoordinatorOutcome.SUBMITTED,
                            intent_id=intent_id,
                            selected_identity=ident,
                            submission_result=submission,
                            bridge_result=bridge_result,
                        )
                    )
                else:
                    if self._virtual_account is not None:
                        self._virtual_account.release_reservation(res_key, reason=f"broker_rejected_{submission.reason}")
                    self._release_pending_risk_commitment(res_key)
                    self._intent_lifecycle[intent_id] = _IntentLifecycle.TERMINAL_REJECTED
                    self._remove_claim(attempt.owner, ident, intent_id)
                    entry_results.append(
                        CoordinatorEntryResult(
                            outcome=CoordinatorOutcome.REJECTED,
                            intent_id=intent_id,
                            selected_identity=ident,
                            submission_result=submission,
                            bridge_result=bridge_result,
                            rejection_reason=submission.reason,
                            rejection_evidence=submission,
                        )
                    )

        # 9. Watermark advance persistence
        if self._persistence_store is not None:
            try:
                # Save updated watermark
                if self._paper_broker.last_exchange_timestamps:
                    self._persistence_store.save_watermark_advance(
                        self._paper_broker.last_exchange_timestamps
                    )
            except Exception as p_err:
                self._persistence_failed = True
                logger.critical("Failed watermark persistence commit: %s", p_err, exc_info=True)
                raise

        return LiveQuoteProcessingResult(
            quote_result=quote_result,
            broker_events=broker_terminal_events,
            entry_results=tuple(entry_results),
            protective_triggers=tuple(protective_triggers),
        )

    # ------------------------------------------------------------------
    # Strategy Bar Boundary & Feed State Management
    # ------------------------------------------------------------------

    def on_market_time(self, market_time: datetime) -> None:
        """Advance market time across virtual account for authoritative staleness."""
        if not isinstance(market_time, datetime) or market_time.tzinfo is None:
            raise ValueError("market_time must be a timezone-aware datetime")
        self._latest_market_timestamp = market_time
        self._has_received_quote = True
        # Phase 8 P1 (§128.11): deterministic heartbeat/staleness observation.
        # Reference = the authoritative advancing market time; latest = the
        # last MARKET-DATA evidence (accepted quotes).  With
        # heartbeat_timeout_seconds unset (None) NO stale escalation ever
        # occurs; a stale transition escalates through the controller exactly
        # once; a fresh transition establishes resume ELIGIBILITY ONLY.
        if self._phase8_safety is not None:
            self._phase8_safety.observe_market_data_timestamp(
                latest_market_timestamp=self._latest_quote_market_timestamp,
                reference_timestamp=market_time,
            )
        m_date = market_time.date()
        date_rolled = (
            (self._last_canonical_session_date is not None and m_date > self._last_canonical_session_date)
            or (self._risk_gate_state is not None and m_date > self._risk_gate_state.risk_day.session_date)
        )
        if self._last_canonical_session_date is None or m_date > self._last_canonical_session_date:
            self._last_canonical_session_date = m_date
        if self._virtual_account is not None:
            try:
                self._virtual_account.on_market_time(market_time)
            finally:
                self._persist_accounting_integrity_breach()
        if date_rolled:
            self._handle_session_rollover(market_time)
        else:
            self._sync_risk_gate_equity()
        self._advance_q93_month_rollover(market_time)
    def _advance_q93_month_rollover(self, market_time: datetime) -> None:
        """ADR §124.3/§124.5 (R3/R5) + P1-01 repair: durable month progression.

        Ordering is mandatory and fail-closed:
          1. bootstrap/rollover FINALIZATIONS (in chronological order);
          2. durable marker persistence of the current month;
          3. in-memory marker advance.

        A persistence callback that is not wired (None) leaves the pre-P1-01
        in-memory-only behavior for pure-unit callers; the production runner
        always wires the durable paper_metadata persister.
        """
        if self._q93_month_finalizer is None:
            return
        local_stamp = market_time.astimezone(IST_CALENDAR)
        current: tuple[int, int] = (local_stamp.year, local_stamp.month)
        last = self._q93_last_observed_ist_month

        if last is None:
            # §P1-01 step 6: persist the first observed month durably BEFORE
            # any in-memory advance; a failed write propagates and the
            # runtime must not pretend the observation was recorded.
            if self._q93_month_persister is not None:
                self._q93_month_persister(*current)
            self._q93_last_observed_ist_month = current
            return

        if current <= last:
            return

        def _next_month(year: int, month: int) -> tuple[int, int]:
            return (year + 1, 1) if month == 12 else (year, month + 1)

        # Completed months = [last observed month, current month): the month
        # containing prior observations is itself fully elapsed once a newer
        # month is observed (§124.3 R3). All finalizations succeed BEFORE the
        # marker is durably advanced; any failure propagates and both markers
        # stay on `last` so the next accepted event retries.
        candidate = last
        while candidate < current:
            self._q93_month_finalizer(*candidate)
            candidate = _next_month(*candidate)
        if self._q93_month_persister is not None:
            self._q93_month_persister(*current)
        self._q93_last_observed_ist_month = current

    def on_strategy_evaluation_boundary(
        self,
        *,
        strategy_id: str,
        strategy_version: str,
        timeframe: str,
        boundary_timestamp: datetime,
    ) -> tuple[str, ...]:
        """Expire bar-bound pending attempts that reached their expiry boundary."""
        if not isinstance(strategy_id, str) or not strategy_id.strip():
            raise ValueError("strategy_id must be a non-empty string")
        if not isinstance(strategy_version, str) or not strategy_version.strip():
            raise ValueError("strategy_version must be a non-empty string")
        if not isinstance(timeframe, str) or not timeframe.strip():
            raise ValueError("timeframe must be a non-empty string")
        if not isinstance(boundary_timestamp, datetime) or boundary_timestamp.tzinfo is None:
            raise ValueError("boundary_timestamp must be a timezone-aware datetime")

        if self._virtual_account is not None:
            self._virtual_account.on_market_time(boundary_timestamp)

        expired_ids: list[str] = []
        for intent_id, attempt in list(self._pending_by_intent.items()):
            if (
                attempt.owner.strategy_id == strategy_id.strip()
                and attempt.owner.strategy_version == strategy_version.strip()
                and attempt.intent.timeframe == timeframe.strip()
                and attempt.expiry_boundary <= boundary_timestamp
            ):
                self._intent_lifecycle[intent_id] = _IntentLifecycle.TERMINAL_REJECTED
                del self._pending_by_intent[intent_id]
                ident = attempt.selected_entry.selected_identity
                if ident in self._pending_intents_by_identity:
                    self._pending_intents_by_identity[ident].discard(intent_id)
                self._remove_claim(attempt.owner, ident, intent_id)
                expired_ids.append(intent_id)

        return tuple(sorted(expired_ids))

    def on_feed_state_change(
        self,
        state: FeedConnectionState,
    ) -> tuple[CoordinatorEntryResult, ...]:
        """Handle feed connection transitions. Aborts pending attempts and cancels queued orders on disconnect, restores active subscriptions on connect."""
        if not isinstance(state, FeedConnectionState):
            raise TypeError("state must be a FeedConnectionState")

        if self._virtual_account is not None:
            self._virtual_account.on_feed_state_change(state is FeedConnectionState.CONNECTED)

        if state in (FeedConnectionState.DISCONNECTED, FeedConnectionState.RECONNECTING):
            if (
                self._phase8_safety is not None
                and not self._shutdown_in_progress
                and state is FeedConnectionState.DISCONNECTED
            ):
                # §128.2: the controller owns the unsafe-cause/manual-review
                # record and escalates through this coordinator's existing
                # global kill authority.  This is intentionally before any
                # cancellation so an opening order cannot survive the event.
                self._phase8_safety.observe_feed_disconnect()
            self._has_received_quote = False
            self._reconnected_waiting_for_quote = True
            self._feed_ever_disconnected = True
            if self._persistence_store is not None and self.is_persistence_healthy:
                try:
                    acc_id = self._virtual_account.account_id if self._virtual_account else "unknown"
                    disc_ev = AuditEvent(
                        event_id=derive_audit_event_id(
                            event_family=AuditEventFamily.FEED_CONNECTIVITY,
                            event_type=AuditEventType.FEED_DISCONNECTED,
                            aggregate_type="FEED",
                            aggregate_identity="live_feed",
                            state_generation=None,
                            transaction_event_ordinal=0,
                        ),
                        event_family=AuditEventFamily.FEED_CONNECTIVITY.value,
                        event_type=AuditEventType.FEED_DISCONNECTED.value,
                        aggregate_type="FEED",
                        aggregate_identity="live_feed",
                        market_timestamp=self._latest_market_timestamp,
                        recorded_at_utc=recorded_at_utc_now(),
                        payload_json=canonical_json_dumps({
                            "state": state.value,
                        }),
                    )
                    self._persistence_store.append_audit_events([disc_ev])
                except Exception:
                    pass

            aborted_results: list[CoordinatorEntryResult] = []
            for intent_id, attempt in list(self._pending_by_intent.items()):
                self._intent_lifecycle[intent_id] = _IntentLifecycle.TERMINAL_REJECTED
                del self._pending_by_intent[intent_id]
                ident = attempt.selected_entry.selected_identity
                if ident in self._pending_intents_by_identity:
                    self._pending_intents_by_identity[ident].discard(intent_id)
                self._remove_claim(attempt.owner, ident, intent_id)
                aborted_results.append(
                    CoordinatorEntryResult(
                        outcome=CoordinatorOutcome.REJECTED,
                        intent_id=intent_id,
                        selected_identity=ident,
                        rejection_reason="feed_disconnected_while_pending",
                    )
                )

            # Cancel all queued orders in paper broker upon confirmed disconnect (SAF-4 / SAF-5)
            for po in list(self._paper_broker.pending_orders()):
                ts = self._latest_market_timestamp or po.submission_market_timestamp
                self.cancel_order(po.order_id, ts)

            return tuple(aborted_results)
        elif state is FeedConnectionState.CONNECTED:
            self._feed_connected_once = True
            if self._phase8_safety is not None:
                # Reconnect proves transport only.  It does not clear the
                # GLOBAL review requirement or the coordinator kill switch.
                self._phase8_safety.observe_feed_reconnected()
            self._has_received_quote = False
            self._reconnected_waiting_for_quote = True
            ev_type = (
                AuditEventType.FEED_RECONNECTED
                if getattr(self, "_feed_ever_disconnected", False)
                else AuditEventType.FEED_CONNECTED
            )
            self._feed_ever_disconnected = False
            if self._persistence_store is not None and self.is_persistence_healthy:
                try:
                    acc_id = self._virtual_account.account_id if self._virtual_account else "unknown"
                    conn_ev = AuditEvent(
                        event_id=derive_audit_event_id(
                            event_family=AuditEventFamily.FEED_CONNECTIVITY,
                            event_type=ev_type,
                            aggregate_type="FEED",
                            aggregate_identity="live_feed",
                            state_generation=None,
                            transaction_event_ordinal=0,
                        ),
                        event_family=AuditEventFamily.FEED_CONNECTIVITY.value,
                        event_type=ev_type.value,
                        aggregate_type="FEED",
                        aggregate_identity="live_feed",
                        market_timestamp=self._latest_market_timestamp,
                        recorded_at_utc=recorded_at_utc_now(),
                        payload_json=canonical_json_dumps({
                            "state": state.value,
                        }),
                    )
                    self._persistence_store.append_audit_events([conn_ev])
                except Exception:
                    pass

            active = self._subscription_manager.active_subscriptions()
            ordered = deterministic_subscription_order(active)
            for identity in ordered:
                self._live_feed.subscribe(identity)
            return ()

        return ()

    def begin_shutdown(self) -> None:
        """Mark intentional runner shutdown so its transport close is not a safety incident."""
        self._shutdown_in_progress = True

    def cancel_order(
        self,
        order_id: str,
        cancel_market_timestamp: datetime,
    ) -> BrokerCancelResult:
        """Explicitly cancel a queued order in paper broker and notify VirtualPaperAccount."""
        pending_pc = self._protective_evaluator._pending_by_order_id.get(order_id)
        opening_pending = order_id in self._retained_plans
        res = self._paper_broker.cancel(order_id, cancel_market_timestamp)
        if res.cancelled:
            term_ev = self._paper_broker._terminal.get(order_id)
            rel_res_key = None
            entry_intent_id = None
            if term_ev is not None and term_ev.original_order is not None and term_ev.instrument_identity is not None:
                try:
                    from engine.risk.risk_manager import entry_intent_identity
                    orig_order = term_ev.original_order
                    res_key = entry_intent_identity(
                        strategy_id=orig_order.strategy_id,
                        strategy_version=orig_order.strategy_version,
                        identity=term_ev.instrument_identity,
                        timeframe=orig_order.timeframe,
                        originating_timestamp=orig_order.originating_timestamp,
                    )
                    active_comms = getattr(self._virtual_account, "_active_commitments", {}) if self._virtual_account else {}
                    if res_key in active_comms:
                        rel_res_key = res_key
                    if res_key in self._intent_lifecycle:
                        entry_intent_id = res_key
                except Exception:
                    pass

            if self._virtual_account is not None and term_ev is not None:
                self._apply_broker_terminal_event(term_ev)
            if opening_pending and term_ev is not None:
                self._release_pending_risk_commitment(
                    self._entry_identity_for_terminal_event(term_ev)
                )
            self._retained_plans.pop(order_id, None)
            self._protective_evaluator.on_external_terminal_failure(order_id, reason="cancelled")
            self._clear_strategy_pending_by_order_id(order_id)

            if self._persistence_store is not None and term_ev is not None:
                try:
                    t5_events = self._build_t5_audit_events(
                        terminal_event=term_ev,
                        released_reservation_key=rel_res_key,
                        cleared_pending_close_position_key=pending_pc.position_key if pending_pc else None,
                        entry_intent_id=entry_intent_id,
                    )
                    self._persistence_store.save_t5_terminal_non_fill(
                        terminal_event=term_ev,
                        cleared_pending_close_position_key=pending_pc.position_key if pending_pc else None,
                        audit_events=t5_events,
                    )
                    self._on_state_transition_committed()
                except Exception as p_err:
                    self._persistence_failed = True
                    logger.critical("Failed T5 cancel persistence commit: %s", p_err, exc_info=True)
                    raise
        return res

    def cancel_all_pending(
        self,
        cancel_market_timestamp: datetime | None = None,
    ) -> tuple[str, ...]:
        """Cancel all queued orders in paper broker."""
        cancelled_ids: list[str] = []
        pending_objs = (
            self._paper_broker.pending_orders.values()
            if isinstance(self._paper_broker.pending_orders, dict)
            else (
                self._paper_broker.pending_orders()
                if callable(self._paper_broker.pending_orders)
                else self._paper_broker.pending_orders.values()
            )
        )
        for rec in list(pending_objs):
            ts = cancel_market_timestamp or self._latest_market_timestamp or rec.submission_market_timestamp
            res = self.cancel_order(rec.order_id, ts)
            if res.cancelled:
                cancelled_ids.append(rec.order_id)
        return tuple(cancelled_ids)

    def activate_kill_switch(
        self,
        *,
        reason: str,
        source: str = "operator",
        market_timestamp: datetime | None = None,
    ) -> SafetyTransitionResult:
        """Activate emergency kill switch (SAF-8 / SAF-12)."""
        if not reason or not reason.strip():
            raise ValueError("reason is required to activate kill switch")
        if not source or not source.strip():
            raise ValueError("source is required to activate kill switch")

        prior_state = self.safety_state

        if self._safety.is_kill_switch_active:
            if self._persistence_store is not None and self.is_persistence_healthy:
                try:
                    acc_id = self._virtual_account.account_id if self._virtual_account else "unknown"
                    repeat_ev = AuditEvent(
                        event_id=derive_audit_event_id(
                            event_family=AuditEventFamily.SAFETY_KILL_SWITCH,
                            event_type=AuditEventType.KILL_SWITCH_IDEMPOTENT_REPEAT,
                            aggregate_type="SAFETY",
                            aggregate_identity=acc_id,
                            state_generation=None,
                            transaction_event_ordinal=0,
                        ),
                        event_family=AuditEventFamily.SAFETY_KILL_SWITCH.value,
                        event_type=AuditEventType.KILL_SWITCH_IDEMPOTENT_REPEAT.value,
                        aggregate_type="SAFETY",
                        aggregate_identity=acc_id,
                        market_timestamp=market_timestamp,
                        recorded_at_utc=recorded_at_utc_now(),
                        payload_json=canonical_json_dumps({
                            "reason": reason,
                            "source": source,
                        }),
                    )
                    self._persistence_store.append_audit_events([repeat_ev])
                except Exception:
                    pass
            return SafetyTransitionResult(
                success=True,
                prior_state=prior_state,
                current_state=SafetyState.KILL_SWITCH_ACTIVE,
                reason=reason,
                cancelled_order_ids=(),
            )

        # 1. Persist kill_switch_active = TRUE first with atomic audit event
        if self._persistence_store is not None:
            try:
                acc_id = self._virtual_account.account_id if self._virtual_account else "unknown"
                kill_ev = AuditEvent(
                    event_id=derive_audit_event_id(
                        event_family=AuditEventFamily.SAFETY_KILL_SWITCH,
                        event_type=AuditEventType.KILL_SWITCH_ACTIVATED,
                        aggregate_type="SAFETY",
                        aggregate_identity=acc_id,
                        state_generation=None,
                        transaction_event_ordinal=0,
                        canonical_domain_identity=f"{source}:{reason}",
                    ),
                    event_family=AuditEventFamily.SAFETY_KILL_SWITCH.value,
                    event_type=AuditEventType.KILL_SWITCH_ACTIVATED.value,
                    aggregate_type="SAFETY",
                    aggregate_identity=acc_id,
                    market_timestamp=market_timestamp,
                    recorded_at_utc=recorded_at_utc_now(),
                    transaction_event_ordinal=0,
                    payload_json=canonical_json_dumps({
                        "reason": reason,
                        "source": source,
                        "kill_switch_active": True,
                    }),
                )
                self._persistence_store.save_safety_state(
                    kill_switch_active=True,
                    kill_switch_reason=reason,
                    activation_source=source,
                    activation_market_timestamp=market_timestamp,
                    audit_events=(kill_ev,),
                )
            except Exception as exc:
                self._persistence_failed = True
                logger.critical("Failed to persist kill switch activation: %s", exc, exc_info=True)
                raise

        # 2. Update in-memory state
        self._safety.set_kill_switch(
            active=True,
            reason=reason,
            source=source,
            market_timestamp=market_timestamp,
        )

        # 3. Cancel pending simulated orders
        cancelled_ids = self.cancel_all_pending(market_timestamp)

        # 4. Create and deliver safety alert
        alert = SafetyAlert(
            alert_id=str(uuid.uuid4()),
            severity="CRITICAL",
            source=source,
            reason=reason,
            timestamp=market_timestamp,
            context={"cancelled_order_ids": cancelled_ids},
        )
        self._safety.emit_alert(alert)

        return SafetyTransitionResult(
            success=True,
            prior_state=prior_state,
            current_state=self.safety_state,
            reason=reason,
            cancelled_order_ids=cancelled_ids,
            alert=alert,
        )

    def resume_from_kill_switch(
        self,
        *,
        operator_id: str,
        reason: str = "operator_resumed",
    ) -> SafetyResumeResult:
        """Validate all safety prerequisites and resume operational paper trading (SAF-11 / SAF-32)."""
        if not operator_id or not operator_id.strip():
            raise ValueError("operator_id is required to resume from kill switch")

        if not self._safety.is_kill_switch_active:
            return SafetyResumeResult(
                success=True,
                current_state=self.safety_state,
                reason="already_inactive",
            )

        # Phase 8 §128.7 is the canonical unified global manual-review gate.
        # Consult it before local validation or persistence so no path can
        # clear the global latch while another Phase-8 cause remains unsafe.
        if self._phase8_safety is not None:
            decision = self._phase8_safety.request_global_resume(operator_id=operator_id)
            if not decision.approved:
                return SafetyResumeResult(
                    success=False,
                    current_state=self.safety_state,
                    reason=(
                        "Phase8 global resume rejected: "
                        f"{', '.join(decision.failed_prerequisites)}"
                    ),
                    failed_prerequisites=decision.failed_prerequisites,
                )

        failed_prereqs: list[str] = []

        # 1. Persistence health
        if not self.is_persistence_healthy:
            failed_prereqs.append("persistence_not_healthy")

        # 2. Accounting integrity
        if self._virtual_account is not None and self._virtual_account.accounting_integrity_breached:
            failed_prereqs.append("accounting_integrity_breached")

        # 3. Feed connection
        if self._live_feed.connection_state is not FeedConnectionState.CONNECTED:
            failed_prereqs.append("feed_not_connected")

        # 4. Pending broker simulated orders
        pending_list = (
            self._paper_broker.pending_orders()
            if callable(getattr(self._paper_broker, "pending_orders", None))
            else self._paper_broker.pending_orders
        )
        if len(pending_list) > 0:
            failed_prereqs.append("pending_broker_orders_exist")

        # 5. Market evidence & required subscription validation (Finding R1)
        if self._virtual_account is not None and self._virtual_account.positions:
            if self._virtual_account.valuation_state != ValuationState.LIVE:
                failed_prereqs.append("held_positions_valuation_not_live")
            # Verify each held position's exact contract has active fresh quote evidence
            for pos_key in self._virtual_account.positions.keys():
                q = self._quote_cache.get(pos_key.identity)
                if q is None or q.bid_price is None or q.bid_price <= Decimal("0"):
                    if "required_subscriptions_not_ready" not in failed_prereqs:
                        failed_prereqs.append("required_subscriptions_not_ready")
        else:
            if not self._has_received_quote or self._latest_market_timestamp is None:
                failed_prereqs.append("no_fresh_market_evidence")

        # 6. Session date regression validation (Finding R2)
        if self._latest_market_timestamp is not None:
            current_session_date = self._latest_market_timestamp.date()
            if self._last_canonical_session_date is not None and current_session_date < self._last_canonical_session_date:
                failed_prereqs.append("session_time_regression")
            if self._persistence_store is not None:
                try:
                    hyd = self._persistence_store.load_state()
                    if (
                        hyd.risk_gate_state is not None
                        and hyd.risk_gate_state.risk_day is not None
                        and current_session_date < hyd.risk_gate_state.risk_day.session_date
                    ):
                        if "session_time_regression" not in failed_prereqs:
                            failed_prereqs.append("session_time_regression")
                except Exception:
                    pass

        if failed_prereqs:
            if self._persistence_store is not None and self.is_persistence_healthy:
                try:
                    acc_id = self._virtual_account.account_id if self._virtual_account else "unknown"
                    rej_ev = AuditEvent(
                        event_id=derive_audit_event_id(
                            event_family=AuditEventFamily.SAFETY_KILL_SWITCH,
                            event_type=AuditEventType.RESUME_REJECTED,
                            aggregate_type="SAFETY",
                            aggregate_identity=acc_id,
                            state_generation=None,
                            transaction_event_ordinal=0,
                        ),
                        event_family=AuditEventFamily.SAFETY_KILL_SWITCH.value,
                        event_type=AuditEventType.RESUME_REJECTED.value,
                        aggregate_type="SAFETY",
                        aggregate_identity=acc_id,
                        market_timestamp=self._latest_market_timestamp,
                        recorded_at_utc=recorded_at_utc_now(),
                        payload_json=canonical_json_dumps({
                            "operator_id": operator_id,
                            "failed_prerequisites": failed_prereqs,
                        }),
                    )
                    self._persistence_store.append_audit_events([rej_ev])
                except Exception:
                    pass

            alert = SafetyAlert(
                alert_id=str(uuid.uuid4()),
                severity="WARNING",
                source=operator_id,
                reason=f"Resume rejected: {', '.join(failed_prereqs)}",
                timestamp=self._latest_market_timestamp,
                context={"failed_prerequisites": failed_prereqs},
            )
            self._safety.emit_alert(alert)
            return SafetyResumeResult(
                success=False,
                current_state=self.safety_state,
                reason=f"Failed prerequisites: {', '.join(failed_prereqs)}",
                failed_prerequisites=tuple(failed_prereqs),
                alert=alert,
            )

        # 7. Persist kill_switch_active = FALSE before clearing in-memory state
        if self._persistence_store is not None:
            try:
                acc_id = self._virtual_account.account_id if self._virtual_account else "unknown"
                res_ev = AuditEvent(
                    event_id=derive_audit_event_id(
                        event_family=AuditEventFamily.SAFETY_KILL_SWITCH,
                        event_type=AuditEventType.RESUME_SUCCEEDED,
                        aggregate_type="SAFETY",
                        aggregate_identity=acc_id,
                        state_generation=None,
                        transaction_event_ordinal=0,
                        canonical_domain_identity=f"{operator_id}:{reason}",
                    ),
                    event_family=AuditEventFamily.SAFETY_KILL_SWITCH.value,
                    event_type=AuditEventType.RESUME_SUCCEEDED.value,
                    aggregate_type="SAFETY",
                    aggregate_identity=acc_id,
                    market_timestamp=self._latest_market_timestamp,
                    recorded_at_utc=recorded_at_utc_now(),
                    transaction_event_ordinal=0,
                    payload_json=canonical_json_dumps({
                        "operator_id": operator_id,
                        "reason": reason,
                    }),
                )
                self._persistence_store.save_safety_state(
                    kill_switch_active=False,
                    kill_switch_reason=None,
                    activation_source=None,
                    activation_market_timestamp=None,
                    audit_events=(res_ev,),
                )
            except Exception as exc:
                self._persistence_failed = True
                logger.critical("Failed to persist kill switch resume: %s", exc, exc_info=True)
                alert = SafetyAlert(
                    alert_id=str(uuid.uuid4()),
                    severity="CRITICAL",
                    source=operator_id,
                    reason=f"Resume persistence commit failed: {exc}",
                    timestamp=self._latest_market_timestamp,
                )
                self._safety.emit_alert(alert)
                return SafetyResumeResult(
                    success=False,
                    current_state=self.safety_state,
                    reason=f"persistence_commit_failed: {exc}",
                    failed_prerequisites=("persistence_commit_failed",),
                    alert=alert,
                )

        # 8. ONLY AFTER durable commit: clear in-memory state and enable entry eligibility
        self._safety.set_kill_switch(active=False)
        if self._latest_market_timestamp is not None:
            self._last_canonical_session_date = self._latest_market_timestamp.date()

        alert = SafetyAlert(
            alert_id=str(uuid.uuid4()),
            severity="INFO",
            source=operator_id,
            reason=reason,
            timestamp=self._latest_market_timestamp,
        )
        self._safety.emit_alert(alert)

        if self._phase8_safety is not None:
            # Only notify after durable persistence and the actual
            # coordinator-owned kill switch transition both succeeded.
            self._phase8_safety.notify_global_resume_completed()

        return SafetyResumeResult(
            success=True,
            current_state=self.safety_state,
            reason=reason,
            alert=alert,
        )

    def manual_close_position(
        self,
        position_key: PositionKey,
        *,
        quantity: Decimal | None = None,
        market_timestamp: datetime | None = None,
    ) -> BrokerSubmissionResult:
        """Manually submit a reduce-only close order for a held position (SAF-14 / SAF-27)."""
        if not isinstance(position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")

        if self.safety_state in (SafetyState.PERSISTENCE_FAILED, SafetyState.INTEGRITY_BREACHED):
            raise ValueError(f"Manual close forbidden while safety state is {self.safety_state.value}")

        if self._virtual_account is None:
            raise ValueError("VirtualPaperAccount is required for manual close")

        pos = self._virtual_account.positions.get(position_key)
        if pos is None:
            raise ValueError(f"No held position found for {position_key}")

        close_qty = quantity if quantity is not None else pos.quantity
        if close_qty <= Decimal("0"):
            raise ValueError("Close quantity must be strictly positive")
        if close_qty > pos.quantity:
            raise ValueError(f"Close quantity {close_qty} exceeds held quantity {pos.quantity}")

        quote = self._quote_cache.get(position_key.identity)
        if quote is None or quote.bid_price is None or quote.bid_price <= Decimal("0"):
            raise ValueError(f"Fresh executable BID quote required for {position_key.identity}")

        spec = self._find_specification_for_identity(position_key.identity, quote.exchange_timestamp.date())
        if spec is None:
            raise ValueError(f"Instrument specification not found for {position_key.identity}")

        pa = PortfolioAccount(
            account_id=self._virtual_account.snapshot.account_id,
            currency=self._virtual_account.snapshot.currency,
            monetary_quantum=self._virtual_account.snapshot.monetary_quantum,
            starting_capital=self._virtual_account.snapshot.starting_capital,
        )
        exit_order = OrderRequest(
            source_intent=SignalIntent(
                action="EXIT",
                confidence=1.0,
                symbol=position_key.identity.instrument,
                timeframe=pos.valuation_timeframe,
                originating_timestamp=quote.exchange_timestamp,
                strategy_id=position_key.strategy_id,
                strategy_version=position_key.strategy_version,
                metadata={},
            ),
            order_type=OrderType.MARKET,
            quantity=close_qty,
            time_in_force=TimeInForce.DAY,
        )
        res = pa.resolve_exit(
            snapshot=self._virtual_account.snapshot,
            exit_order=exit_order,
            specification=spec,
            quantity=close_qty,
        )
        if res.close_instruction is None:
            raise ValueError(f"Failed to resolve concrete close instruction: {res.reason}")

        sub = self._paper_broker.submit(
            order=res.close_instruction,
            instrument_identity=position_key.identity,
            specification=spec,
            submission_quote=quote,
            submission_market_timestamp=quote.exchange_timestamp,
        )
        return sub

    def submit_strategy_exit(
        self,
        position_key: PositionKey,
        *,
        policy_callback: object | None = None,
    ) -> BrokerSubmissionResult | None:
        """Execute a generic strategy-owned exit through the normal close lifecycle.

        Lifecycle:
          1. Snapshot position state under locks
          2. Release locks → invoke strategy callback (outside lock)
          3. Validate decision (owner, position, staleness)
          4. Construct close order through normal path
          5. Submit through paper broker
          6. Persist + audit through normal lifecycle

        No strategy formula, no fake ProtectiveExit, no parallel execution path.
        The engine owns: validation, close construction, broker, accounting,
        persistence, audit, protective reconciliation.

        Returns BrokerSubmissionResult if close submitted, or None if no exit.
        """
        if not isinstance(position_key, PositionKey):
            raise TypeError("position_key must be a PositionKey")

        if self.safety_state in (SafetyState.PERSISTENCE_FAILED, SafetyState.INTEGRITY_BREACHED):
            raise ValueError(f"Strategy exit forbidden while safety state is {self.safety_state.value}")

        if self._virtual_account is None:
            raise ValueError("VirtualPaperAccount is required for strategy exit")

        pos = self._virtual_account.positions.get(position_key)
        if pos is None:
            return None

        quote = self._quote_cache.get(position_key.identity)
        if quote is None or quote.bid_price is None or quote.bid_price <= Decimal("0"):
            raise ValueError(f"Fresh executable BID quote required for {position_key.identity}")

        # Duplicate-close authority: while ANY close is in flight for this exact
        # authoritative position — a prior strategy exit OR a protective close —
        # a repeated decision or later callback must never create duplicate
        # close exposure. Deterministic idempotent no-op.
        if self.has_pending_strategy_exit(position_key):
            return None
        if (
            self._protective_evaluator is not None
            and self._protective_evaluator.has_pending_close(position_key)
        ):
            return None

        # Phase 1: snapshot under locks (informational protective state)
        evidence = StrategyExitEvidence(
            strategy_id=position_key.strategy_id,
            strategy_version=position_key.strategy_version,
            position_key=position_key,
            instrument_identity=position_key.identity,
            direction="LONG",
            open_quantity=pos.quantity,
            market_timestamp=quote.exchange_timestamp,
        )

        # Phase 2: strategy callback OUTSIDE locks
        decision = None
        if policy_callback is not None:
            if self._protective_evaluator is not None:
                decision = self._protective_evaluator.strategy_exit(
                    evidence, policy_callback=policy_callback,
                )
            else:
                # No protective evaluator — invoke callback directly (outside any lock)
                if not callable(getattr(policy_callback, "strategy_exit_decision", None)):
                    raise TypeError(
                        "policy_callback must provide strategy_exit_decision(evidence)"
                    )
                try:
                    decision = policy_callback.strategy_exit_decision(evidence)
                except Exception as error:
                    raise RuntimeError(
                        f"strategy exit decision failed for "
                        f"{position_key.strategy_id}/{position_key.strategy_version}"
                    ) from error
                if decision is not None and not isinstance(decision, StrategyExitDecision):
                    raise TypeError(
                        "policy strategy_exit_decision must return StrategyExitDecision or None"
                    )

        if decision is None:
            return None

        # Phase 3: validate decision (owner, position, staleness)
        # Owner validation: position must belong to the strategy that made the decision
        if position_key.strategy_id != evidence.strategy_id:
            raise ValueError("decision owner does not match position owner")
        if position_key.strategy_version != evidence.strategy_version:
            raise ValueError("decision owner version does not match position owner")

        # Position validation: must still exist with closable quantity
        pos_now = self._virtual_account.positions.get(position_key)
        if pos_now is None or pos_now.quantity <= Decimal("0"):
            return None

        # Staleness: market_timestamp must match current quote
        if quote.exchange_timestamp != evidence.market_timestamp:
            return None

        # Phase 4: construct close order through normal path (FULL CLOSE ONLY)
        close_qty = pos_now.quantity

        spec = self._find_specification_for_identity(position_key.identity, quote.exchange_timestamp.date())
        if spec is None:
            raise ValueError(f"Instrument specification not found for {position_key.identity}")

        pa = PortfolioAccount(
            account_id=self._virtual_account.snapshot.account_id,
            currency=self._virtual_account.snapshot.currency,
            monetary_quantum=self._virtual_account.snapshot.monetary_quantum,
            starting_capital=self._virtual_account.snapshot.starting_capital,
        )
        exit_order = OrderRequest(
            source_intent=SignalIntent(
                action="EXIT",
                confidence=1.0,
                symbol=position_key.identity.instrument,
                timeframe=pos_now.valuation_timeframe,
                originating_timestamp=quote.exchange_timestamp,
                strategy_id=position_key.strategy_id,
                strategy_version=position_key.strategy_version,
                metadata={},
            ),
            order_type=OrderType.MARKET,
            quantity=close_qty,
            time_in_force=TimeInForce.DAY,
        )
        res = pa.resolve_exit(
            snapshot=self._virtual_account.snapshot,
            exit_order=exit_order,
            specification=spec,
            quantity=close_qty,
        )
        if res.close_instruction is None:
            raise ValueError(f"Failed to resolve concrete close instruction: {res.reason}")

        # Phase 5: submit through normal paper broker path
        sub = self._paper_broker.submit(
            order=res.close_instruction,
            instrument_identity=position_key.identity,
            specification=spec,
            submission_quote=quote,
            submission_market_timestamp=quote.exchange_timestamp,
        )

        if not sub.accepted:
            # Broker rejection: normal rejection lifecycle only. No broker order
            # row, no pending close of any kind, no account mutation. The next
            # eligible decision may retry cleanly.
            return sub

        # Phase 6: register the GENERIC (non-protective) pending-close lock and
        # durably persist the submission through the normal order lifecycle.
        #
        # STRATEGY_EXIT is not STOP_LOSS/TARGET/TRAILING_STOP and never fakes
        # protective semantics: no ProtectiveExitKind placeholder, no synthetic
        # protective_id, no zero trigger_price, no protective_pending_closes row.
        # Durable identity is the broker_orders QUEUED EXIT row written atomically
        # with STRATEGY_EXIT_REQUESTED audit evidence; restart reconciliation and
        # duplicate-close authority restore from that generic evidence alone.
        self._register_strategy_pending_close(
            StrategyExitPendingClose(
                position_key=position_key,
                order_id=sub.order_id,
                broker_order_identity=sub.broker_order_identity,
                requested_market_timestamp=quote.exchange_timestamp,
            )
        )

        if self._persistence_store is not None:
            try:
                # Internal pending-order view: carries the exact specification
                # needed for lossless durable hydration of the close order.
                close_order = self._get_broker_pending_order(sub.order_id)
                if close_order is None:
                    raise RuntimeError(
                        f"strategy exit close order {sub.order_id} missing from paper broker"
                    )
                pk_identity_json = canonical_json_dumps(_position_key_to_dict(position_key))
                audit_event = AuditEvent(
                    event_id=derive_audit_event_id(
                        event_family=AuditEventFamily.PROTECTIVE_LIFECYCLE,
                        event_type=AuditEventType.STRATEGY_EXIT_REQUESTED,
                        aggregate_type="position",
                        aggregate_identity=pk_identity_json,
                        state_generation=self._persistence_store.state_generation,
                    ),
                    event_family=AuditEventFamily.PROTECTIVE_LIFECYCLE.value,
                    event_type=AuditEventType.STRATEGY_EXIT_REQUESTED.value,
                    aggregate_type="position",
                    aggregate_identity=pk_identity_json,
                    recorded_at_utc=recorded_at_utc_now(),
                    market_timestamp=quote.exchange_timestamp,
                    state_generation=self._persistence_store.state_generation,
                    strategy_id=position_key.strategy_id,
                    strategy_version=position_key.strategy_version,
                    position_key_json=pk_identity_json,
                    broker_order_identity=sub.broker_order_identity,
                    payload_json=canonical_json_dumps({
                        "action": "STRATEGY_EXIT",
                        "close_qty": str(close_qty),
                        "order_id": sub.order_id,
                        "broker_order_identity": sub.broker_order_identity,
                    }),
                )
                exit_state_transition = getattr(decision, "state_transition", None)
                exit_expected_gen: int | None = None
                if exit_state_transition is not None:
                    exit_expected_gen = self._strategy_state_generation.get(
                        (exit_state_transition.strategy_id, exit_state_transition.strategy_version),
                        0,
                    )
                new_gen = self._persistence_store.save_strategy_exit_submission(
                    close_order=close_order,
                    strategy_state_transition=exit_state_transition,
                    expected_state_generation=exit_expected_gen,
                    audit_events=(audit_event,),
                )
                if new_gen is not None and exit_state_transition is not None:
                    self._strategy_state_generation[
                        (exit_state_transition.strategy_id, exit_state_transition.strategy_version)
                    ] = new_gen
                self._on_state_transition_committed()
            except Exception as p_err:
                self._persistence_failed = True
                logger.critical("Failed strategy exit persistence commit: %s", p_err, exc_info=True)
                raise

        return sub

    def expire_day_session(
        self,
        session_end_market_timestamp: datetime,
    ) -> tuple[BrokerTerminalEvent, ...]:
        """Expire all DAY orders in paper broker and notify VirtualPaperAccount."""
        events = tuple(self._paper_broker.expire_day_session(session_end_market_timestamp))
        for ev in events:
            opening_pending = ev.order_id in self._retained_plans
            if self._virtual_account is not None:
                self._apply_broker_terminal_event(ev)
            if opening_pending:
                self._release_pending_risk_commitment(
                    self._entry_identity_for_terminal_event(ev)
                )
            self._retained_plans.pop(ev.order_id, None)
            self._protective_evaluator.on_external_terminal_failure(ev.order_id, reason="expired")
            self._clear_strategy_pending_by_order_id(ev.order_id)
        return events

    # ------------------------------------------------------------------
    # Introspection / Query Helpers
    # ------------------------------------------------------------------

    def get_quote(self, identity: InstrumentIdentity) -> QuoteSnapshot | None:
        """Query latest valid quote from cache."""
        if not isinstance(identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")
        return self._quote_cache.get(identity)

    def pending_attempt_count(self) -> int:
        """Return count of active un-resumed pending entry attempts."""
        return len(self._pending_by_intent)

    def active_claims_for(self, owner: SubscriptionOwnerKey, identity: InstrumentIdentity) -> frozenset[str]:
        """Return immutable set of active intent claims for an owner and instrument."""
        if not isinstance(owner, SubscriptionOwnerKey):
            raise TypeError("owner must be a SubscriptionOwnerKey")
        if not isinstance(identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")
        group = self._subscription_claims.get((owner, identity))
        if group is None:
            return frozenset()
        return frozenset(group.dependent_intent_ids)
