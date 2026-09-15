"""Phase 5 OD-7 Item 15 — Minimal Live Paper Trading Runner & Harness.

Orchestrates the existing Phase-5 production paper-trading pipeline against
Upstox V3 Market Data Feed using virtual/demo money only.

Guarantees:
- Execution authority is strictly SimulatedPaperBroker with VirtualPaperAccount.
- Zero real broker execution reachability (zero real broker execution endpoints).
- Canonical token variable: UPSTOX_ACCESS_TOKEN (resolved at runtime, never logged/persisted).
- Zero network or side effects on import.
- Strict startup order: Config -> Catalog -> SQLite Schema V4 -> VirtualAccount ->
  Startup Reconciliation Gate -> Coordinator Composition -> Feed Authorization ->
  WebSocket Connection -> Live Synchronization.
- Preserves Item-14 4-stage quote causality (Q_ENTRY_WAKE vs Q_ENTRY_FILL).
- Preserves completed-bar-only strategy evaluation via LiveBarBuilder.
- Graceful shutdown preserves positions and state without fake liquidation or session close.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
import logging
import os
from pathlib import Path
import re
import sys
import threading
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from engine.audit.model import (
    AuditEvent,
    AuditEventFamily,
    AuditEventType,
    canonical_json_dumps,
    derive_audit_event_id,
    recorded_at_utc_now,
)
from engine.audit.log import (
    build_q89_error_record,
    record as record_rule7_strategy_error,
    record_runtime_error as record_runtime_error_via_facade,
    register_durable_error_sink,
    register_error_file_sink,
    sanitize_error_class,
    sanitized_message_fingerprint,
)
from engine.audit.sinks import (
    LoggingConfigError,
    NonDeletingJsonlWriter,
    clear_registered_secret_values,
    load_logging_config,
    read_jsonl_records,
    register_secret_value,
)
from engine.reporting.paper_summaries import (
    build_monthly_strategy_summaries,
    publish_q93_monthly_summary,
)
from engine.execution.paper_broker import SimulatedPaperBroker
from engine.execution.paper_fill import (
    PaperFillAdapter,
)
from engine.data.feeds.live_bar_builder import (
    IngestionMode,
    LiveBarBuilder,
    LiveProviderBar,
    MarketTimeEvent,
)
from engine.data.feeds.live_feed import (
    FeedConnectionState,
    LiveQuoteEvent,
    SubscriptionOwnerKey,
)
from engine.data.feeds.provider_mapping import (
    InMemoryProviderInstrumentMapper,
    ProviderInstrumentMapper,
)
from engine.data.feeds.quote_cache import LatestQuoteCache
from engine.data.feeds.subscription import OptionSubscriptionManager
from engine.data.feeds.upstox.auth import (
    UpstoxAuthError,
    UpstoxV3AuthorizationClient,
)
from engine.data.feeds.upstox.catalog_loader import (
    UpstoxCatalogLoaderError,
    UpstoxInstrumentCatalogLoader,
)
from engine.data.feeds.upstox.feed import (
    UpstoxLiveMarketDataFeed,
    UpstoxStartupPhase,
)
from engine.orchestration.strategy_coordinator import LiveStrategyCoordinator
from engine.market.data import (
    BoundBarEvent,
    DataSubscription,
    MarketDataCoordinator,
    StreamKey,
    StreamProfileMap,
    StrategyDataRequirements,
)
from engine.market.profile import MarketSessionBoundary, india_market_profile
from engine.options.catalog import InstrumentCatalog
from engine.options.live_catalog import LiveInstrumentCatalog
from engine.options.policy import (
    ExpiryPolicy,
    OptionSelectionPolicy,
    StrikeMode,
    StrikePolicy,
)
from engine.orchestration.entry_pipeline import StrategyBinding
from engine.orders.model import OrderType, TimeInForce
from engine.paper.coordinator import (
    CoordinatorEntryResult,
    LivePaperCoordinator,
    StrategyExitPendingClose,
)
from engine.paper.configuration import (
    PaperConfigurationError,
    ResolvedPaperConfiguration,
    load_paper_configuration,
)
from engine.paper.option_bridge import OptionEntryBridge
from engine.paper.protective_policy_registry import ProtectivePolicyRegistry
from engine.persistence.schema import SCHEMA_VERSION
from engine.persistence.sqlite_store import PaperHydratedState, SQLitePaperStateStore
from dateutil.relativedelta import relativedelta

from engine.portfolio.accounting import PortfolioAccount
from engine.portfolio.model import (
    InstrumentIdentity,
    InstrumentSpecification,
    PositionKey,
)
from engine.portfolio.virtual_account import VirtualPaperAccount
from engine.paper.promotion_tracking import (
    PromotionDisqualificationReason,
    PromotionMilestoneStatus,
    PromotionReportWriter,
    PromotionSessionRecord,
    PromotionSessionStatus,
    PromotionTrackingEngine,
    PromotionTrackingState,
    PromotionTrackingStatus,
)
from engine.protective.live import LiveProtectiveEvaluator, ProtectiveExitBook

from engine.reconciliation.paper.engine import (
    PaperReconciliationEngine,
    ReconciliationHealth,
    ReconciliationReport,
)
from engine.risk.risk_manager import RiskGate
from engine.safety.phase8_safety import Phase8SafetyController
from engine.safety.safety import KillSwitchState, SafetyManager, SafetyState
from engine.strategy.base import Signal, StrategySignalGenerator

__all__ = [
    "CANONICAL_TOKEN_ENV_VAR",
    "LivePaperRunnerConfig",
    "LivePaperRunnerResult",
    "LivePaperTradingRunner",
    "main",
]

logger = logging.getLogger(__name__)

CANONICAL_TOKEN_ENV_VAR = "UPSTOX_ACCESS_TOKEN"
DEFAULT_OBSERVATIONAL_STRATEGY_VERSION = "1.0"


# ======================================================================
# Default Observation-Only Strategy
# ======================================================================


class DefaultObservationalStrategy(StrategySignalGenerator):
    """Default non-invasive observational strategy that produces HOLD."""

    interface_version = "1.0"

    def __init__(self, strategy_id: str = "strat_live_paper_default") -> None:
        self.id = strategy_id

    def initial_state(self) -> dict:
        return {"step": 0}

    def generate_signal(self, data: Any, state: Any) -> Signal:
        if isinstance(state, dict):
            state["step"] = state.get("step", 0) + 1
        return Signal(action="HOLD", confidence=0.0)


# ======================================================================
# Runner Configuration & Result Types
# ======================================================================


@dataclass(frozen=True)
class LivePaperRunnerConfig:
    """Configuration for LivePaperTradingRunner."""

    paper_session_id: str
    paper_config_path: Path | str = Path("config/paper_config.yaml")
    stale_quote_threshold: timedelta = timedelta(seconds=60)
    instrument_master_path: Path | str | None = None
    instrument_records: Sequence[Mapping[str, Any]] | None = None
    snapshot_business_date: date | None = None
    session_boundary: MarketSessionBoundary | None = None
    declared_streams: Mapping[StreamKey, IngestionMode] | None = None
    strategy_bindings: Sequence[StrategyBinding] | None = None
    option_selection_policies: Mapping[SubscriptionOwnerKey, OptionSelectionPolicy] | None = None
    auth_url: str = UpstoxV3AuthorizationClient.DEFAULT_AUTH_URL
    q93_publication_destination_dir: Path | str | None = None
    logging_config_path: Path | str | None = None
    # Phase 8 / §128.3: required for every runnable production runner.  None
    # is retained only as the explicit unconfigured value so startup can fail
    # closed; no numeric default is invented.
    strategy_error_kill_threshold: int | None = None
    # Phase 8 / §128.11: reuses the existing heartbeat timeout authority.
    # None (unset) ⇒ stale-data escalation disabled; never a numeric default.
    heartbeat_timeout_seconds: float | int | None = None
    # Trusted strategy-owned protective policy registry.  When None the
    # production configuration resolver creates an empty registry (generic
    # fixed_percent / trailing_percent forms remain unsupported).  Tests
    # and application composition supply explicit registrations.
    protective_policy_registry: ProtectivePolicyRegistry | None = None


@dataclass(frozen=True)
class LivePaperRunnerResult:
    """Immutable result snapshot produced after a live paper run or validation."""

    session_id: str
    db_path: str
    status: str  # "completed", "validated", "stopped", "failed"
    frames_processed: int
    bars_completed: int
    quotes_processed: int
    initial_reconciliation: ReconciliationHealth
    final_reconciliation: ReconciliationHealth
    starting_capital: Decimal
    ending_cash: Decimal
    ending_available_cash: Decimal
    open_positions_count: int
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    error: str | None = None


def derive_strategy_exit_pending_closes(
    hydrated: PaperHydratedState,
) -> tuple[StrategyExitPendingClose, ...]:
    """Restore the generic strategy-exit close authority from durable evidence.

    A QUEUED ``ConcreteCloseInstruction`` broker_orders row that is not a
    protective pending close is an in-flight generic strategy close: manual
    closes are not persisted, entry orders are ConcreteOpenInstruction, and
    legitimate protective closes are excluded by their dedicated
    ``protective_pending_closes`` rows. No protective table is consulted for
    strategy exits.
    """
    protective_pending_order_ids = {
        pc.order_id for pc in hydrated.protective_pending_closes
    }
    return tuple(
        StrategyExitPendingClose(
            position_key=PositionKey(
                strategy_id=pending_order.original_order.strategy_id,
                strategy_version=pending_order.original_order.strategy_version,
                identity=pending_order.instrument_identity,
            ),
            order_id=pending_order.order_id,
            broker_order_identity=pending_order.broker_order_identity,
            requested_market_timestamp=pending_order.submission_market_timestamp,
        )
        for pending_order in hydrated.pending_broker_orders.values()
        if type(pending_order.original_order).__name__ == "ConcreteCloseInstruction"
        and pending_order.order_id not in protective_pending_order_ids
    )


@dataclass
class _TerminationOutcome:
    """Internal terminal authority for one ``run`` invocation.

    The public result remains deliberately small.  This private object keeps
    the first material failure separate from later shutdown diagnostics so a
    successful cleanup can never turn a failed runtime into a completion.
    """

    status: str = "completed"
    primary_stage: str | None = None
    primary_error: str | None = None
    secondary_stage: str | None = None
    secondary_error: str | None = None

    def fail(self, *, stage: str, error: str) -> None:
        if self.primary_error is None:
            self.status = "failed"
            self.primary_stage = stage
            self.primary_error = error

    def stop(self) -> None:
        if self.primary_error is None:
            self.status = "stopped"

    def add_secondary(self, *, stage: str, error: str) -> None:
        if self.secondary_error is None:
            self.secondary_stage = stage
            self.secondary_error = error

    def result_error(self) -> str | None:
        if self.primary_error is None:
            return None
        message = f"stage={self.primary_stage}; {self.primary_error}"
        if self.secondary_error is not None:
            message += f"; secondary_stage={self.secondary_stage}; {self.secondary_error}"
        return message


# ======================================================================
# LivePaperTradingRunner Implementation
# ======================================================================


class LivePaperTradingRunner:
    """Minimal operator runner wiring existing production components to Upstox Market Data."""

    # ------------------------------------------------------------------
    # Phase 6 / ADR §123.3(d): durable E21 ERROR evidence emission
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Phase 6 / ADR §124.3-§124.6 (R3/R5/R6): durable Q93 month finalization
    # ------------------------------------------------------------------

    def _finalize_q93_month(self, year: int, month: int) -> None:
        """Finalize one completed IST month exactly once for this session.

        Aggregates ONLY canonical trade/cost evidence via the journal's
        read APIs and publishes atomically to the caller-supplied
        destination directory. Fail-closed when no destination is configured
        (§124.8): mandatory Q92/Q93 evidence is never silently skipped.
        """
        if self._q93_publication_destination_dir is None:
            raise RuntimeError(
                "Q93 monthly finalization requires q93_publication_destination_dir "
                "to be explicitly configured (ADR §124.8 / OD-Y convention)"
            )
        store = getattr(self, "_store", None)
        if store is None:
            raise RuntimeError("Q93 monthly finalization requires the durable journal")
        rows = [
            row
            for row in build_monthly_strategy_summaries(
                store.load_all_completed_trades(),
                costs_by_trade_id=store.load_cost_totals_by_trade(),
            )
            if (row.year, row.month) == (year, month)
        ]
        outcome = publish_q93_monthly_summary(
            rows,
            paper_session_id=store.paper_session_id,
            year=year,
            month=month,
            destination_dir=self._q93_publication_destination_dir,
        )
        logger.info(
            "Q93 monthly %04d-%02d finalized for session %r: %s (%d strategy rows)",
            year,
            month,
            store.paper_session_id,
            outcome,
            len(rows),
        )

    def _guarded_durable_error_sink(
        self,
        kind: str,
        strategy_id: str | None,
        interface_version: str | None,
        exception: BaseException,
    ) -> None:
        """Registered Rule-7 sink wrapper. Never raises into the error path."""
        try:
            self._emit_durable_error_evidence(kind, strategy_id, interface_version, exception)
        except Exception as sink_exc:  # noqa: BLE001 - §114.12 paradox boundary
            logger.critical(
                "durable ERROR evidence not recorded (journal unavailable or rejected); "
                "kind=%r error_class=%r cause=%r",
                kind,
                sanitize_error_class(exception),
                sink_exc,
            )

    def _emit_durable_error_evidence(
        self,
        kind: str,
        strategy_id: str | None,
        interface_version: str | None,
        exception: BaseException,
    ) -> None:
        """Build and durably append ONE bounded E21 observational event.

        Contracts (§123.3(d)): state_generation stays NULL; payload is bounded
        and sanitized (class token + one-way message fingerprint only).
        Dedup per the frozen tuple (paper_session_id, strategy_id, error_class)
        — event_type excluded — is enforced ATOMICALLY by the journal owner via
        SQLitePaperStateStore.append_error_evidence_once (single exclusive
        transaction: check + insert), so it is restart-safe and concurrency-safe.
        """
        if kind not in ("strategy", "runtime"):
            raise ValueError(f"unknown durable-error kind: {kind!r}")
        store = getattr(self, "_store", None)
        if store is None or not store.is_healthy:
            # No fabricated evidence when the journal itself is absent/failing.
            return

        event_type = (
            AuditEventType.STRATEGY_EXCEPTION if kind == "strategy" else AuditEventType.RUNTIME_ERROR
        )
        error_class = sanitize_error_class(exception)

        payload_json = canonical_json_dumps(
            {
                "error_class": error_class,
                "message_fingerprint": sanitized_message_fingerprint(exception),
                "interface_version": interface_version,
            }
        )
        event = AuditEvent(
            event_id=derive_audit_event_id(
                event_family=AuditEventFamily.ERROR,
                event_type=event_type,
                aggregate_type="ERROR_CLASS",
                aggregate_identity=error_class,
                state_generation=None,
                transaction_event_ordinal=0,
                canonical_domain_identity=None,
                payload_json=payload_json,
            ),
            event_family=AuditEventFamily.ERROR.value,
            event_type=event_type.value,
            aggregate_type="ERROR_CLASS",
            aggregate_identity=error_class,
            recorded_at_utc=recorded_at_utc_now(),
            strategy_id=strategy_id,
            payload_json=payload_json,
        )
        store.append_error_evidence_once(event, error_class=error_class, strategy_id=strategy_id)

    def record_runtime_error(self, exception: BaseException) -> None:
        """Public seam for contained non-strategy runtime errors (§123.3(d)).

        Delegates to the frozen audit facade so the same registered sink,
        sanitization, dedup, and paradox rules apply. Original fail-closed
        handling at the call site remains the caller's responsibility.
        """
        record_runtime_error_via_facade(exception)

    # ------------------------------------------------------------------
    # Phase 6 Slice 4 / ADR §123.6 + §126.2: Q88/Q89/Q90 file sinks
    # ------------------------------------------------------------------

    def _setup_logging_sinks(self) -> None:
        """Load config/logging_config.yaml and activate the optional sinks.

        Fail-closed on an explicitly configured but missing/invalid logging
        configuration. When ``logging_config_path`` is None the sinks stay
        inactive and runtime behavior is byte-identical to Slice 3.
        Rotated segments are NEVER deleted or pruned (ADR §126.2 OD-B).
        """
        if self._logging_config_path is None:
            return
        if not self._logging_config_path.exists() or not self._logging_config_path.is_file():
            raise LoggingConfigError(
                f"configured logging config file does not exist: {self._logging_config_path}"
            )
        cfg = load_logging_config(self._logging_config_path)
        self._trade_log_writer = self._writer_for(cfg, "trade_log", "trade_log", 50 * 1024 * 1024)
        self._error_log_writer = self._writer_for(cfg, "error_log", "error_log", 10 * 1024 * 1024)
        self._strategy_log_writer = self._writer_for(cfg, "strategy_log", "strategy_log", 50 * 1024 * 1024)

        # Q89 error-file seam: paper/live production runtime ONLY (§126.1);
        # never registered inside backtest execution.
        if self._error_log_writer is not None:
            session_identity = self._store.paper_session_id
            error_writer = self._error_log_writer

            def _q89_file_sink(record: Mapping[str, Any]) -> bool:
                enriched = dict(record)
                enriched["runtime_environment"] = "paper"
                enriched["paper_session_identity"] = session_identity
                enriched["run_identity"] = session_identity
                # Explicit persistence evidence: the facade may attach this
                # occurrence's correlation_reference to the durable E21
                # payload ONLY when True (no dangling references).
                return error_writer.write_record(enriched) is True

            register_error_file_sink(_q89_file_sink)

        # Initial catch-up: regenerate any missing Q88 output from durable
        # canonical trade/cost records (restart idempotency by trade_id).
        self._maybe_emit_q88_trades(force=True)

    @staticmethod
    def _writer_for(cfg: Any, sink_name: str, base_name: str, default_bytes: int) -> NonDeletingJsonlWriter | None:
        destination = cfg.sinks.get(sink_name)
        if destination is None:
            return None
        max_bytes = cfg.rotation.get(sink_name, default_bytes)
        return NonDeletingJsonlWriter(destination, base_name, max_segment_bytes=max_bytes)

    def _make_q90_evaluation_observer(self) -> Callable[[Mapping[str, Any]], None] | None:
        """Return the Q90 observer bound to the strategy-log writer, or None."""
        writer = self._strategy_log_writer
        if writer is None:
            return None

        def _observer(record: Mapping[str, Any]) -> None:
            writer.write_record(record)

        return _observer

    def _maybe_emit_q88_trades(self, *, force: bool = False) -> None:
        """Derive-by-tail Q88 emission from durable canonical records.

        Canonical authority remains TradeRecord/TradeLeg/CostAssessment via
        the journal's read APIs (`load_all_completed_trades`,
        `load_cost_totals_by_trade`) — never audit_events for financial
        fields (§123.7(4)). Restart-idempotent keyed by trade_id: emitted
        identities are re-discovered from the non-authoritative output files
        themselves. Any failure is a critical diagnostic that leaves
        trading/accounting state untouched; the log is regenerable later.
        """
        writer = self._trade_log_writer
        store = self._store
        if writer is None or store is None:
            return
        account = self._virtual_account
        try:
            in_memory_count = (
                len(account.trade_ledger.completed_trades())
                if (account is not None and account.trade_ledger is not None)
                else 0
            )
        except Exception:  # noqa: BLE001 - cheap-trigger guard only
            in_memory_count = 0
        with self._q88_lock:
            if not force and in_memory_count == self._q88_last_seen_completed_count:
                return
            self._q88_last_seen_completed_count = in_memory_count
            try:
                records, malformed = read_jsonl_records(writer.directory, writer.base_name)
                emitted_ids = {
                    row.get("trade_id")
                    for row in records
                    if isinstance(row, dict) and isinstance(row.get("trade_id"), str)
                }
                trades = store.load_all_completed_trades()
                costs = store.load_cost_totals_by_trade()
                dropped = 0
                for trade in trades:  # durable order: exit_timestamp ASC, trade_id ASC
                    trade_id = trade.trade_id
                    if trade_id in emitted_ids:
                        continue
                    row = self._build_q88_row(trade, costs.get(trade_id))
                    if writer.write_record(row):
                        emitted_ids.add(trade_id)
                    else:
                        dropped += 1
                if malformed:
                    logger.warning(
                        "Q88 trade-log rebuild skipped %d malformed historical output line(s) "
                        "(diagnostic-only tail policy)",
                        malformed,
                    )
                if dropped:
                    logger.critical(
                        "Q88 trade-log dropped %d record(s) this cycle; regenerable from durable records",
                        dropped,
                    )
            except Exception as exc:  # noqa: BLE001 - §13 failure semantics
                logger.critical(
                    "Q88 trade-log emission failed; trading/accounting state unaffected; cause=%r",
                    exc,
                )

    @staticmethod
    def _build_q88_row(trade: Any, total_cost: Decimal | None) -> dict[str, Any]:
        """Build ONE bounded Q88 row from canonical trade + cost evidence.

        Average exit price derives from canonical exit legs. Exit reason is a
        DESCRIPTIVE canonical lifecycle token from the closing-leg provenance
        carried on the immutable TradeRecord — never Signal.metadata["reason"],
        never an execution/risk authority (§123.7).
        """
        gross_exit_qty = sum((leg.execution_quantity for leg in trade.exit_legs), Decimal("0"))
        average_exit_price = None
        if gross_exit_qty > 0:
            average_exit_price = sum(
                (leg.execution_price * leg.execution_quantity for leg in trade.exit_legs),
                Decimal("0"),
            ) / gross_exit_qty
        provenance = trade.provenance or {}
        exit_reason_token = provenance.get("source_exit_action") or provenance.get("action")
        ident = trade.instrument_identity
        identity_dict = {
            "market": getattr(ident, "market", None),
            "instrument": getattr(ident, "instrument", None),
            "segment": getattr(ident, "segment", None),
            "underlying": getattr(ident, "underlying", None),
            "expiry": getattr(ident, "expiry", None),
            "strike": getattr(ident, "strike", None),
            "option_type": getattr(ident, "option_type", None),
        }
        cost_value = total_cost if total_cost is not None else Decimal("0")
        return {
            "record_kind": "q88_trade",
            "trade_id": trade.trade_id,
            "account_id": trade.account_id,
            "strategy_id": trade.position_key.strategy_id,
            "strategy_version": trade.position_key.strategy_version,
            "instrument": identity_dict,
            "position_side": trade.position_side,
            "opened_at": trade.opened_at,
            "closed_at": trade.closed_at,
            "entry_quantity": trade.entry_quantity,
            "exit_quantity": trade.exit_quantity,
            "average_entry_price": trade.average_entry_price,
            "average_exit_price": average_exit_price,
            "gross_realized_pnl": trade.gross_realized_pnl,
            "total_cost": cost_value,
            "net_realized_pnl": trade.gross_realized_pnl - cost_value,
            "currency": trade.currency,
            "exit_reason": exit_reason_token,
        }

    def __init__(
        self,
        config: LivePaperRunnerConfig,
        *,
        access_token_provider: Callable[[], str] | None = None,
        auth_client: UpstoxV3AuthorizationClient | None = None,
        ws_connect_factory: Callable[[str], Any] | None = None,
        http_requester: Callable[[str, dict[str, str]], dict[str, Any]] | None = None,
    ) -> None:
        if not isinstance(config, LivePaperRunnerConfig):
            raise TypeError("config must be an instance of LivePaperRunnerConfig")
        self._validate_phase8_configuration(config)

        self._config = config
        self._access_token_provider = access_token_provider or (
            lambda: os.environ.get(CANONICAL_TOKEN_ENV_VAR, "")
        )
        self._injected_auth_client = auth_client
        self._ws_connect_factory = ws_connect_factory
        self._http_requester = http_requester

        # Phase 6 / ADR §124.3 (R3): durable Q93 month-rollover finalizer,
        # bound to this runner's journal readers and caller-supplied
        # destination directory (OD-Y convention; §124.8 fail-closed).
        self._q93_publication_destination_dir: Path | None = (
            Path(config.q93_publication_destination_dir)
            if config.q93_publication_destination_dir is not None
            else None
        )

        # Phase 6 Slice 4 / ADR §123.6 + §126.2: optional Q88/Q89/Q90 file
        # sinks. Inactive until initialize() loads config/logging_config.yaml;
        # never a trading/accounting authority; rotated segments are NEVER
        # auto-deleted (OD-B).
        self._logging_config_path: Path | None = (
            Path(config.logging_config_path)
            if config.logging_config_path is not None
            else None
        )
        self._trade_log_writer: NonDeletingJsonlWriter | None = None
        self._error_log_writer: NonDeletingJsonlWriter | None = None
        self._strategy_log_writer: NonDeletingJsonlWriter | None = None
        self._q88_emitted_trade_ids: set[str] = set()
        self._q88_last_seen_completed_count: int = -1
        self._q88_lock = threading.Lock()

        # Initialized state holders
        self._catalog: LiveInstrumentCatalog | None = None
        self._resolved_configuration: ResolvedPaperConfiguration | None = None
        self._mapper: ProviderInstrumentMapper | None = None
        self._store: SQLitePaperStateStore | None = None
        self._hydrated_state: PaperHydratedState | None = None
        self._virtual_account: VirtualPaperAccount | None = None
        self._broker: SimulatedPaperBroker | None = None
        self._paper_coordinator: LivePaperCoordinator | None = None
        self._bar_builder: LiveBarBuilder | None = None
        self._strategy_coordinator: LiveStrategyCoordinator | None = None
        self._feed: UpstoxLiveMarketDataFeed | None = None
        self._market_boundary: MarketSessionBoundary | None = None
        self._started_at_ist: datetime | None = None

        self._frames_processed_count = 0
        self._bars_completed_count = 0
        self._quotes_processed_count = 0

        self._is_initialized = False
        self._is_running = False
        self._stop_event = threading.Event()
        self._shutdown_completed = False
        self._shutdown_failure: tuple[str, str] | None = None
        self._active_termination: _TerminationOutcome | None = None
        self._redaction_values: set[str] = set()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def config(self) -> LivePaperRunnerConfig:
        return self._config

    @staticmethod
    def _validate_phase8_configuration(config: LivePaperRunnerConfig) -> None:
        """Reject an incomplete Phase-8 production configuration before startup."""
        threshold = config.strategy_error_kill_threshold
        if threshold is None:
            raise ValueError(
                "strategy_error_kill_threshold is required for runnable live-paper production"
            )
        if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold < 1:
            raise ValueError("strategy_error_kill_threshold must be a positive integer >= 1")

    @property
    def is_initialized(self) -> bool:
        return self._is_initialized

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def resolved_configuration(self) -> ResolvedPaperConfiguration:
        """The sole parsed authority for the initialized paper environment."""
        if self._resolved_configuration is None:
            raise RuntimeError("paper configuration has not been resolved")
        return self._resolved_configuration

    # ------------------------------------------------------------------
    # Token Resolution & Redaction Guards
    # ------------------------------------------------------------------

    def _resolve_token(self) -> str:
        """Resolve and validate the access token without exposing its value."""
        try:
            token = self._access_token_provider()
        except Exception:
            raise RuntimeError("Access token resolution failed") from None

        if not isinstance(token, str) or not token.strip():
            raise RuntimeError(
                f"Missing or empty {CANONICAL_TOKEN_ENV_VAR}; "
                f"must provide a valid non-empty access token before network connection"
            )
        clean_token = token.strip()
        self._redaction_values.add(clean_token)
        # Phase 6 Slice 4: shared non-disableable redaction registry so no
        # file sink can ever emit the live token value.
        register_secret_value(clean_token)
        return clean_token

    def _sanitize_exception(self, exc: Exception) -> str:
        """Return bounded diagnostics suitable for a public terminal result."""
        message = " ".join(str(exc).split())
        for value in self._redaction_values:
            if value:
                message = message.replace(value, "[REDACTED]")
        message = re.sub(r"(?i)(bearer\\s+)[^\\s,;]+", r"\\1[REDACTED]", message)
        message = re.sub(
            r"(?i)((?:access[_-]?token|api[_-]?key|authorization)\\s*[=:]\\s*)[^\\s,;]+",
            r"\\1[REDACTED]",
            message,
        )
        if not message:
            message = "unspecified error"
        return f"type={type(exc).__name__}; message={message[:512]}"

    def _record_runner_critical_failure(self, *, stage: str, exc: Exception) -> None:
        """Capture callback failures that the feed intentionally isolates."""
        if self._active_termination is not None:
            self._active_termination.fail(
                stage=stage,
                error=self._sanitize_exception(exc),
            )

    # ------------------------------------------------------------------
    # Instrument Master Loading
    # ------------------------------------------------------------------

    def _load_instrument_records(self) -> Sequence[Mapping[str, Any]]:
        """Load instrument master candidate records from config or file."""
        if self._config.instrument_records is not None:
            return self._config.instrument_records

        if self._config.instrument_master_path is not None:
            path = Path(self._config.instrument_master_path)
            if not path.exists():
                raise FileNotFoundError(f"Instrument master file not found: {path}")
            raw_text = path.read_text(encoding="utf-8")
            data = json.loads(raw_text)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
                return data["data"]
            else:
                raise ValueError("Instrument master JSON must contain a list of records")

        raise ValueError(
            "Must provide either 'instrument_records' or 'instrument_master_path' in config"
        )

    @staticmethod
    def _validate_runtime_strategy_bindings(
        bindings: Sequence[StrategyBinding],
        resolved: ResolvedPaperConfiguration,
    ) -> None:
        """Require runtime strategy instances to match declared owner bindings.

        Paper configuration declares each exact strategy identity, its relevant
        source stream, and whether it is actionable.  This prevents a runtime
        instance from silently inheriting a policy or activation class intended
        for a same-ID strategy at another version.
        """
        runtime_owners: set[SubscriptionOwnerKey] = set()
        for binding in bindings:
            owner = SubscriptionOwnerKey(
                binding.requirements.strategy_id,
                binding.requirements.strategy_version,
            )
            if owner in runtime_owners:
                raise ValueError(f"duplicate runtime strategy binding for {owner!r}")
            runtime_owners.add(owner)
            declaration = resolved.strategy_bindings.get(owner)
            if declaration is None:
                raise ValueError(
                    "runtime strategy has no exact paper configuration binding: "
                    f"{owner.strategy_id}/{owner.strategy_version}"
                )
            source_stream = binding.signal_source_stream
            if source_stream.timeframe != declaration.timeframe:
                raise ValueError(
                    "runtime strategy source timeframe differs from paper configuration: "
                    f"{owner.strategy_id}/{owner.strategy_version}"
                )
            if source_stream.identity.instrument.casefold() != declaration.instrument.casefold():
                raise ValueError(
                    "runtime strategy source instrument differs from paper configuration: "
                    f"{owner.strategy_id}/{owner.strategy_version}"
                )
            if declaration.activation == "actionable" and declaration.protective_policy is None:
                raise ValueError(
                    "actionable strategy is missing its required protective policy: "
                    f"{owner.strategy_id}/{owner.strategy_version}"
                )

    # ------------------------------------------------------------------
    # Component Initialization & Startup Sequence
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Perform strict deterministic startup initialization.

        Sequence:
        1. Config validation
        2. Token retrieval verification
        3. Instrument catalog readiness
        4. SQLite Schema V4 open/hydration
        5. VirtualPaperAccount setup
        6. Safety & Broker state setup
        7. Component composition (Bridge, Protective, Coordinator, BarBuilder)
        8. Feed initialization & wiring
        9. Startup reconciliation verification
        """
        if self._is_initialized:
            return

        cfg = self._config

        # 1. Resolve every paper authority before any stateful component exists.
        resolved = load_paper_configuration(
            cfg.paper_config_path,
            protective_policy_registry=cfg.protective_policy_registry,
        )
        self._resolved_configuration = resolved

        # 2. Validate Token (without printing)
        clean_token = self._resolve_token()

        # 3. Instrument Catalog & Mapper
        records = self._load_instrument_records()
        snap_date = (
            cfg.snapshot_business_date
            or recorded_at_utc_now().astimezone(ZoneInfo("Asia/Kolkata")).date()
        )
        catalog, mapper = UpstoxInstrumentCatalogLoader.load_catalog_and_mapper(
            records, snapshot_business_date=snap_date
        )
        self._catalog = catalog
        self._mapper = mapper

        # 4. Resolve runtime strategy instances against the declared owner keys
        # before store initialization to seed strategy_states on fresh databases.
        if resolved.calendar_snapshot is not None:
            session_boundary = cfg.session_boundary or MarketSessionBoundary(
                profile=india_market_profile(),
                calendar=resolved.calendar_snapshot.to_calendar(),
                calendar_snapshot=resolved.calendar_snapshot,
            )
        else:
            session_boundary = cfg.session_boundary or MarketSessionBoundary(profile=india_market_profile())
        self._market_boundary = session_boundary
        now_utc = recorded_at_utc_now()
        self._started_at_ist = now_utc.astimezone(session_boundary.profile.timezone)


        declared_streams = cfg.declared_streams
        bindings = cfg.strategy_bindings
        policies = cfg.option_selection_policies

        if declared_streams is None or bindings is None or policies is None:
            underlying_name = "NIFTY 50"
            for rec in records:
                if rec.get("segment") == "INDEX" or rec.get("instrument_type") == "INDEX":
                    underlying_name = rec.get("tradingsymbol", "NIFTY 50")
                    break

            default_underlying_ident = InstrumentIdentity(
                market="nse",
                instrument=underlying_name,
                segment="equity",
            )
            default_stream = StreamKey(identity=default_underlying_ident, timeframe="1m")
            declared_streams = declared_streams or {default_stream: IngestionMode.PROVIDER_BAR}

            strat = DefaultObservationalStrategy()
            req = StrategyDataRequirements(
                strategy_id=strat.id,
                strategy_version=DEFAULT_OBSERVATIONAL_STRATEGY_VERSION,
                subscriptions=(DataSubscription(stream=default_stream, minimum_history=1),),
                trigger_streams=frozenset([default_stream]),
            )
            binding = StrategyBinding(
                strategy=strat,
                requirements=req,
                signal_source_stream=default_stream,
            )
            bindings = bindings or [binding]
            owner_key = SubscriptionOwnerKey(req.strategy_id, req.strategy_version)
            policies = policies or {
                owner_key: OptionSelectionPolicy(
                    strategy_id=req.strategy_id,
                    strategy_version=req.strategy_version,
                    expiry=ExpiryPolicy(mode="NEAREST_LISTED", min_dte_days=0, allow_expiry_day=True),
                    strike=StrikePolicy(mode=StrikeMode.ATM, offset_steps=0),
                )
            }

        assert bindings is not None
        assert policies is not None
        self._validate_runtime_strategy_bindings(bindings, resolved)

        initial_strategy_states_map = {
            SubscriptionOwnerKey(
                b.requirements.strategy_id,
                b.requirements.strategy_version,
            ): deepcopy(b.strategy.initial_state())
            for b in bindings
        }

        now_utc = recorded_at_utc_now()
        initial_promotion_states_map = {
            owner: PromotionTrackingEngine.initial_state(
                strategy_id=owner.strategy_id,
                strategy_version=owner.strategy_version,
                paper_session_id=cfg.paper_session_id,
                configuration_identity=resolved.configuration_identity,
                upstream_fingerprint=binding_cfg.upstream_promotion_evidence_fingerprint,
                activation=binding_cfg.activation,
                promotion_eligible=resolved.promotion_eligible,
                tracking_activated_at=resolved.promotion_tracking_activated,
                upstream_promotable=getattr(binding_cfg, "upstream_promotion_evidence_promotable", True),
                now_utc=now_utc,
            )
            for owner, binding_cfg in resolved.strategy_bindings.items()
        }

        # 5. SQLite Schema V7 Store (P1-08 / ADR §122; audit context per ADR §123.1)
        store = SQLitePaperStateStore(
            resolved.database_path,
            account_id=resolved.account.account_id,
            currency=resolved.account.currency,
            starting_capital=resolved.account.starting_capital,
            monetary_quantum=resolved.account.monetary_quantum,
            paper_session_id=cfg.paper_session_id,
            risk_policy_identity=resolved.risk_policy_identity,
            cost_schedule_fingerprint=resolved.cost_profile_identity,
            execution_policy_identity=resolved.execution_policy_identity,
            configuration_identity=resolved.configuration_identity,
            initial_strategy_states=initial_strategy_states_map,
            initial_promotion_states=initial_promotion_states_map,
            # §123.1: resolver hard-requires environment == "paper" today;
            # live mode is a separately authorized future extension. The data
            # source is D1 historical replay until the live connector lands.
            audit_environment="paper",
            audit_source_identity="datasource/historical_replay",
        )
        self._store = store

        # Phase 6 / ADR §123.3(d): durable E21 ERROR evidence flows through
        # the frozen Rule-7 facade (engine/audit/log.py). Registration here is
        # paper/live-runtime-only; backtest execution never registers a sink,
        # so no D16 journal wiring reaches the backtest path (§123.4).
        register_durable_error_sink(self._guarded_durable_error_sink)

        # Phase 6 Slice 4 / ADR §123.6 + §126.1/§126.2: optional Q88/Q89/Q90
        # file sinks from config/logging_config.yaml (paper/live runtime only;
        # backtest production execution stays untouched).
        self._setup_logging_sinks()


        # 5b. Durable-state hydration (P1-05 / P1-07 / ADR §121).
        # Every runtime authority below is restored strictly from this
        # evidence.  A corrupt or cross-table-inconsistent durable state
        # raises here, before any token use, feed, or network acceptance.
        hydrated = store.load_state()
        self._hydrated_state = hydrated
        self._recover_offline_missed_promotion_sessions()

        # 6. Virtual Account (restored from durable evidence)
        portfolio_acc = PortfolioAccount(
            account_id=resolved.account.account_id,
            currency=resolved.account.currency,
            starting_capital=resolved.account.starting_capital,
            monetary_quantum=resolved.account.monetary_quantum,
        )
        specs = {entry.identity: entry.specification for entry in catalog.all_entries}
        virtual_account = VirtualPaperAccount.restore(
            portfolio_acc,
            snapshot=hydrated.account_snapshot,
            active_commitments=hydrated.active_commitments,
            processed_fills=hydrated.processed_fills,
            trade_ledger=hydrated.trade_ledger,
            cost_assessments=hydrated.cost_assessments,
            accounting_sequence=hydrated.accounting_sequence,
            accounting_integrity_breached=hydrated.accounting_integrity_breached,
            cost_schedules=resolved.cost_schedules,
            specifications=specs,
        )
        self._virtual_account = virtual_account

        # 7. Paper Broker (Simulated fills only; restored order ledger and
        # watermarks preserve duplicate-order and replay protection)
        fill_policy = resolved.paper_fill_policy
        broker = SimulatedPaperBroker.restore(
            adapter=PaperFillAdapter(fill_policy),
            stale_quote_threshold=cfg.stale_quote_threshold,
            latency=timedelta(seconds=0),
            pending_orders=hydrated.pending_broker_orders,
            terminal_orders=hydrated.terminal_broker_orders,
            last_exchange_timestamps=hydrated.broker_watermarks,
        )
        self._broker = broker

        # 8. Authorization Client
        if self._injected_auth_client is not None:
            auth_client = self._injected_auth_client
        else:
            auth_client = UpstoxV3AuthorizationClient(
                access_token_provider=lambda: clean_token,
                auth_url=cfg.auth_url,
                http_requester=self._http_requester,
            )
        self._auth_client = auth_client

        # 9. Feed Initialization
        feed = UpstoxLiveMarketDataFeed(
            auth_client=auth_client,
            provider_mapper=mapper,
        )
        self._feed = feed

        # 10. Protective & Option Entry Bridge.  Actionable strategies can only
        # be present when their exact declared owner has a resolved policy.
        actionable_owners = {
            owner
            for owner, declaration in resolved.strategy_bindings.items()
            if declaration.activation == "actionable"
        }
        active_owners = {
            SubscriptionOwnerKey(
                binding.requirements.strategy_id,
                binding.requirements.strategy_version,
            )
            for binding in bindings
        }
        active_actionable = actionable_owners & active_owners

        # Phase 8 P1-A (§128.1/§128.3): route STRATEGY-owned runtime-policy
        # callback failures (RuntimeTrailingPolicy / TargetReplacementPolicy /
        # StrategyExitPolicy) through the canonical authorities.  The closure
        # binds ``phase8_controller`` late (assigned below, before any trading
        # callback can fire).  Canonical durable ERROR evidence uses the
        # EXISTING Rule-7 seam with the exact owner identity; escalation then
        # flows through the ONE canonical per-session error count and the
        # frozen threshold arithmetic — no private counter anywhere.
        def _p1_route_strategy_callback_failure(failure: object) -> None:
            owner = getattr(failure, "strategy_owner", None)
            if not isinstance(owner, tuple) or len(owner) != 2:
                raise TypeError("strategy callback failure missing canonical owner identity")
            sid, sver = owner
            cause = getattr(failure, "__cause__", None)
            record_rule7_strategy_error(
                sid,
                sver,
                cause if isinstance(cause, BaseException) else failure,
            )
            phase8_controller.observe_strategy_exception(sid, sver)

        # Protective state restored from durable evidence (P1-05 / ADR 119 C).
        protective_evaluator = LiveProtectiveEvaluator(
            ProtectiveExitBook(tuple(hydrated.protective_exits)),
            pending_closes=tuple(hydrated.protective_pending_closes),
            runtime_trailing_policies={
                (owner.strategy_id, owner.strategy_version): policy
                for owner, policy in resolved.protective_plan_policies.items()
                if callable(getattr(policy, "trailing_decision", None))
            },
            strategy_exception_observer=_p1_route_strategy_callback_failure,
        )
        # Generic strategy-exit close authority restored strictly from durable
        # generic order evidence (see derive_strategy_exit_pending_closes).
        strategy_exit_pending_closes = derive_strategy_exit_pending_closes(hydrated)
        option_bridge = OptionEntryBridge(
            catalog=catalog,
            paper_fill_policy=fill_policy,
            risk_gate=RiskGate(resolved.risk_policy),
            protective_plan_policies=resolved.protective_plan_policies,
            allow_empty_protective_policies=not active_actionable,
            option_signal_to_order_type=OrderType.MARKET,
            option_time_in_force=TimeInForce.DAY,
        )

        quote_cache = LatestQuoteCache()
        sub_manager = OptionSubscriptionManager()

        # Phase 8 (§128): wire the EXISTING Phase8SafetyController into the
        # production LivePaperCoordinator so the frozen automatic escalation
        # bridges (RiskGate daily-loss breach; first ReconciliationHealth.
        # FAILED) become active.  The canonical GLOBAL kill-switch authority
        # remains the coordinator's activate_kill_switch; this controller
        # only ESCALATES through it.  Bridges below use late-bound closures
        # over the coordinator objects constructed in this method.
        phase8_controller = Phase8SafetyController(
            strategy_error_kill_threshold=cfg.strategy_error_kill_threshold,
            heartbeat_timeout_seconds=cfg.heartbeat_timeout_seconds,
            activate_global_kill_switch=lambda reason: paper_coordinator.activate_kill_switch(
                reason=reason, source="phase8_safety"
            ),
            global_kill_switch_active_probe=lambda: (
                paper_coordinator.safety_state == SafetyState.KILL_SWITCH_ACTIVE
            ),
            persist_halted_owners=store.save_halted_strategy_owners,
            resume_strategy_runtime=lambda sid, sver: strategy_coordinator.clear_strategy_halt(
                sid, sver
            ),
        )
        # §128.8 restart contract: hydrate the durable mirror BEFORE any
        # strategy eligibility/submission evaluation can occur.
        phase8_controller.hydrate_halted_owners(store.load_halted_strategy_owners())

        # 11. LivePaperCoordinator
        paper_coordinator = LivePaperCoordinator(
            catalog=catalog,
            live_feed=feed,
            quote_cache=quote_cache,
            subscription_manager=sub_manager,
            option_bridge=option_bridge,
            paper_broker=broker,
            virtual_account=virtual_account,
            protective_evaluator=protective_evaluator,
            persistence_store=store,
            # Durable restart evidence (P1-05 / ADR 119 D, 119.2, 119.3).
            kill_switch_state=hydrated.kill_switch_state,
            retained_protective_plans=hydrated.retained_protective_plans,
            intent_lifecycles=hydrated.entry_intents,
            strategy_exit_pending_closes=strategy_exit_pending_closes,
            pending_risk_commitments=hydrated.pending_risk_commitments,
            risk_gate_state=hydrated.risk_gate_state,
            q93_month_finalizer=self._finalize_q93_month,
            # P1-01 repair: hydrate the durable Q93 last-observed IST month
            # from paper_metadata (None = genuine bootstrap) and wire the
            # durable persister so marker commits precede in-memory advances.
            initial_q93_last_observed_ist_month=(
                store.load_q93_last_observed_ist_month()
            ),
            q93_month_persister=store.save_q93_last_observed_ist_month,
            phase8_safety=phase8_controller,
        )
        self._paper_coordinator = paper_coordinator

        # 12. Startup Reconciliation Gate (Must be MATCHED before live acceptance)
        if paper_coordinator.reconciliation_health != ReconciliationHealth.MATCHED:
            raise RuntimeError(
                f"Startup reconciliation check failed: health is "
                f"{paper_coordinator.reconciliation_health.value}; cannot proceed to live trading"
            )

        # 13. Bar Builder & Strategy Coordinator
        bar_builder = LiveBarBuilder(
            declared_streams=declared_streams,
            session_boundary=session_boundary,
        )
        self._bar_builder = bar_builder

        profile_map = StreamProfileMap(
            profiles={s: india_market_profile() for s in declared_streams}
        )
        market_coordinator = MarketDataCoordinator(
            requirements=[b.requirements for b in bindings],
            profiles=profile_map,
        )
        # Phase 8 / §128.8+§128.10: hydrate the durable per-strategy halt
        # latch BEFORE any strategy eligibility/submission evaluation, and
        # persist every NEW runtime halt through the existing store API so a
        # restart can never silently clear a strategy halt.  The coordinator
        # remains the SOLE runtime latch; the store remains the SOLE durable
        # authority; no second latch or store is created here.
        initial_halted_owner_records = store.load_halted_strategy_owners()
        strategy_coordinator = LiveStrategyCoordinator(
            market_coordinator=market_coordinator,
            strategy_bindings=bindings,
            paper_coordinator=paper_coordinator,
            option_selection_policies=policies,
            session_boundary=session_boundary,
            persistence_store=store,
            initial_strategy_states=hydrated.strategy_states,
            latest_evaluated_decision_times=hydrated.strategy_watermarks,
            evaluation_observer=self._make_q90_evaluation_observer(),
            initial_halted_owners=[
                SubscriptionOwnerKey(strategy_id=sid, strategy_version=sver)
                for sid, sver in initial_halted_owner_records
            ],
            strategy_halt_bridge=lambda sid, sver: store.save_halted_strategy_owners(
                tuple(
                    sorted(
                        (owner.strategy_id, owner.strategy_version)
                        for owner in strategy_coordinator.halted_owners
                    )
                )
            ),
            # Phase 8 P1-A (§128.3): every strategy callback exception escalates
            # through the canonical controller — count + threshold arithmetic.
            strategy_exception_observer=lambda sid, sver: phase8_controller.observe_strategy_exception(
                sid, sver
            ),
        )
        self._strategy_coordinator = strategy_coordinator

        # 14. Wire Feed Callbacks
        def _on_feed_bar(bar: LiveProviderBar) -> None:
            try:
                res = bar_builder.ingest_provider_bar(bar)
                if res.completed_events:
                    self._bars_completed_count += len(res.completed_events)
                    strategy_coordinator.process_bar_events(res.completed_events)
                    # Phase 6 Slice 4: derive-by-tail Q88 emission trigger
                    # (cheap in-memory count guard; canonical store read).
                    self._maybe_emit_q88_trades()
            except Exception as exc:
                # UpstoxLiveMarketDataFeed protects listener isolation.  This
                # callback is not optional: it is the runner's bar pipeline.
                self._record_runner_critical_failure(stage="bar_processing", exc=exc)

        def _on_feed_market_time(event: MarketTimeEvent) -> None:
            try:
                res = bar_builder.advance_market_time(event)
                if res.completed_events:
                    self._bars_completed_count += len(res.completed_events)
                    strategy_coordinator.process_bar_events(res.completed_events)
                    self._maybe_emit_q88_trades()
                strategy_coordinator.on_market_time_boundary(event.market_timestamp)
            except Exception as exc:
                self._record_runner_critical_failure(stage="market_time_processing", exc=exc)

        def _on_feed_quote(q_event: LiveQuoteEvent) -> None:
            try:
                self._quotes_processed_count += 1
            except Exception as exc:
                self._record_runner_critical_failure(stage="quote_processing", exc=exc)

        feed.add_bar_listener(_on_feed_bar)
        feed.add_market_time_listener(_on_feed_market_time)
        feed.add_quote_listener(_on_feed_quote)

        self._is_initialized = True

    # ------------------------------------------------------------------
    # Validation Only Mode
    # ------------------------------------------------------------------

    def validate_only(self) -> dict[str, Any]:
        """Perform validation of all configuration, tokens, and schemas with ZERO network calls."""
        self.initialize()

        assert self._catalog is not None
        assert self._paper_coordinator is not None

        return {
            "status": "VALIDATED",
            "token_present": bool(self._resolve_token()),
            "session_id": self._config.paper_session_id,
            "db_path": str(self.resolved_configuration.database_path),
            "catalog_entries_count": len(self._catalog.all_entries),
            "schema_version": SCHEMA_VERSION,
            "reconciliation_health": self._paper_coordinator.reconciliation_health.value,
            "starting_capital": str(self.resolved_configuration.account.starting_capital),
            "risk_policy_fingerprint": self.resolved_configuration.risk_policy_identity,
            "configuration_identity": self.resolved_configuration.configuration_identity,
            "promotion_eligible": self.resolved_configuration.promotion_eligible,
        }

    # ------------------------------------------------------------------
    # Observability & Status Inspection
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return safe operator status without exposing secrets or credentials."""
        if not self._is_initialized:
            return {"status": "UNINITIALIZED"}

        assert self._feed is not None
        assert self._paper_coordinator is not None
        assert self._virtual_account is not None
        assert self._broker is not None

        pending_orders = (
            self._broker.pending_orders.values()
            if isinstance(self._broker.pending_orders, dict)
            else (
                self._broker.pending_orders()
                if callable(self._broker.pending_orders)
                else ()
            )
        )

        return {
            "paper_session_id": self._config.paper_session_id,
            "db_path": str(self.resolved_configuration.database_path),
            "connection_state": self._feed.connection_state.value,
            "startup_phase": self._feed.startup_phase.value,
            "frames_processed": self._frames_processed_count,
            "bars_completed": self._bars_completed_count,
            "quotes_processed": self._quotes_processed_count,
            "active_subscriptions_count": self._feed.active_subscriptions_count,
            "pending_broker_orders_count": len(list(pending_orders)),
            "cash": str(self._virtual_account.cash),
            "reserved_cash": str(self._virtual_account.reserved_cash),
            "available_cash": str(self._virtual_account.available_cash),
            "open_positions_count": len(self._virtual_account.positions),
            "realized_pnl": str(self._virtual_account.realized_pnl),
            "unrealized_pnl": str(self._virtual_account.unrealized_pnl),
            "reconciliation_health": self._paper_coordinator.reconciliation_health.value,
        }

    # ------------------------------------------------------------------
    # Live Execution Loop
    # ------------------------------------------------------------------

    def run(
        self,
        *,
        max_frames: int | None = None,
        stop_event: threading.Event | None = None,
    ) -> LivePaperRunnerResult:
        """Run the live paper trading loop.

        Parameters
        ----------
        max_frames : int | None
            Maximum binary frames to receive before cleanly stopping (useful in tests).
        stop_event : threading.Event | None
            External cancellation event for graceful operator stopping.
        """
        self.initialize()

        assert self._feed is not None
        assert self._auth_client is not None
        assert self._paper_coordinator is not None
        assert self._virtual_account is not None
        assert self._store is not None

        active_stop_event = stop_event or self._stop_event
        active_stop_event.clear()
        self._is_running = True
        self._shutdown_completed = False
        self._shutdown_failure = None

        init_rec_health = self._paper_coordinator.reconciliation_health
        outcome = _TerminationOutcome()
        self._active_termination = outcome

        try:
            # 1. Fetch authorized WebSocket redirect URL
            auth_url = self._auth_client.get_authorized_websocket_url()

            # 2. Resolve WebSocket connect factory
            if self._ws_connect_factory is not None:
                ws_connect = self._ws_connect_factory
            else:
                try:
                    import websockets.sync.client as sync_ws
                    ws_connect = sync_ws.connect
                except ImportError:
                    raise RuntimeError("websockets library is required for live paper runner") from None

            # 3. Open WebSocket & Run Frame Ingress Loop
            with ws_connect(auth_url) as ws_client:
                self._feed._ws_client = ws_client
                self._feed.start_connection()

                while True:
                    if self._paper_coordinator.safety_state == SafetyState.KILL_SWITCH_ACTIVE:
                        outcome.stop()
                        break
                    if active_stop_event.is_set():
                        outcome.stop()
                        break
                    try:
                        # Non-blocking / timed receive
                        if hasattr(ws_client, "recv"):
                            try:
                                message = ws_client.recv(timeout=0.5)
                            except TypeError:
                                message = ws_client.recv()
                        else:
                            break

                        if isinstance(message, (bytes, bytearray, memoryview)):
                            self._feed.process_ingress_frame(bytes(message))
                            self._frames_processed_count += 1
                        elif isinstance(message, str):
                            self._feed.process_ingress_frame(message.encode("utf-8"))
                            self._frames_processed_count += 1

                        if outcome.primary_error is not None:
                            break

                        if max_frames is not None and self._frames_processed_count >= max_frames:
                            break

                    except TimeoutError:
                        continue
                    except Exception as exc:
                        if not active_stop_event.is_set():
                            sanitized = self._sanitize_exception(exc)
                            outcome.fail(stage="receive_or_ingress", error=sanitized)
                            logger.warning("WebSocket receive encountered exception: %s", sanitized)
                        else:
                            outcome.stop()
                        break

        except UpstoxAuthError:
            raise
        except Exception as exc:
            sanitized = self._sanitize_exception(exc)
            outcome.fail(stage="runner", error=sanitized)
            logger.error("Live paper runner encountered error: %s", sanitized)
        finally:
            cleanup_failure = self._shutdown_internal() or self._shutdown_failure
            if cleanup_failure is not None:
                cleanup_stage, cleanup_error = cleanup_failure
                if outcome.primary_error is None:
                    outcome.fail(stage=cleanup_stage, error=cleanup_error)
                else:
                    outcome.add_secondary(stage=cleanup_stage, error=cleanup_error)
            self._finalize_promotion_sessions(outcome)
            self._active_termination = None

        final_rec_health = self._paper_coordinator.reconciliation_health

        return LivePaperRunnerResult(
            session_id=self._config.paper_session_id,
            db_path=str(self.resolved_configuration.database_path),
            status=outcome.status,
            frames_processed=self._frames_processed_count,
            bars_completed=self._bars_completed_count,
            quotes_processed=self._quotes_processed_count,
            initial_reconciliation=init_rec_health,
            final_reconciliation=final_rec_health,
            starting_capital=self.resolved_configuration.account.starting_capital,
            ending_cash=self._virtual_account.cash,
            ending_available_cash=self._virtual_account.available_cash,
            open_positions_count=len(self._virtual_account.positions),
            realized_pnl=self._virtual_account.realized_pnl,
            unrealized_pnl=self._virtual_account.unrealized_pnl,
            error=outcome.result_error(),
        )

    def shutdown(self) -> None:
        """Signal the running loop to stop and execute clean shutdown."""
        self._stop_event.set()
        self._shutdown_internal()

    def _shutdown_internal(self) -> tuple[str, str] | None:
        """Run cleanup once and return its first sanitized failure, if any."""
        if self._shutdown_completed:
            return None
        self._shutdown_completed = True
        self._is_running = False
        cleanup_failure: tuple[str, str] | None = None

        # Phase 6 Slice 4: final Q88 derive-by-tail flush, then close the
        # file-sink writers. Sink failure is a diagnostic only; trading state
        # and durable evidence are unaffected (§13/§14/§15).
        try:
            self._maybe_emit_q88_trades(force=True)
        except Exception as exc:  # noqa: BLE001 - sink boundary
            logger.critical("Q88 final trade-log flush failed; cause=%r", exc)
        for writer in (self._trade_log_writer, self._error_log_writer, self._strategy_log_writer):
            if writer is not None:
                try:
                    writer.close()
                except Exception as exc:  # noqa: BLE001 - sink boundary
                    logger.critical("Q-sink writer close failed; base_name=%r cause=%r",
                                    getattr(writer, "base_name", "?"), exc)

        if self._feed is not None:
            try:
                if self._paper_coordinator is not None:
                    self._paper_coordinator.begin_shutdown()
                self._feed.close()
            except Exception as exc:
                cleanup_failure = ("feed_shutdown", self._sanitize_exception(exc))
        if self._paper_coordinator is not None:
            try:
                self._paper_coordinator.run_reconciliation(operator_requested=True)
            except Exception as exc:
                if cleanup_failure is None:
                    cleanup_failure = ("shutdown_reconciliation", self._sanitize_exception(exc))
        self._shutdown_failure = cleanup_failure
        return cleanup_failure

    def _recover_offline_missed_promotion_sessions(self, now_utc: datetime | None = None) -> None:
        """Detect and durably process scheduled NSE sessions missed while offline (ADR §122 / P1-08 / OD-AC)."""
        if self._store is None or self._resolved_configuration is None:
            return
        market_boundary = self._market_boundary or MarketSessionBoundary(profile=india_market_profile())
        now_utc = now_utc or recorded_at_utc_now()
        now_ist = now_utc.astimezone(market_boundary.profile.timezone)
        current_trade_date = now_ist.date()

        hydrated_states = self._store.load_promotion_tracking_states()
        for owner, current_state in hydrated_states.items():
            if current_state.tracking_status != PromotionTrackingStatus.TRACKING_ACTIVE:
                continue
            binding = self._resolved_configuration.strategy_bindings.get(owner)
            if binding is None:
                continue

            # Anchor determination (OD-AC)
            if current_state.last_evaluated_session_date is not None:
                anchor_date = current_state.last_evaluated_session_date
            elif current_state.activated_at is not None:
                act_ist = current_state.activated_at.astimezone(market_boundary.profile.timezone)
                anchor_date = act_ist.date() - timedelta(days=1)
            else:
                continue

            cursor_date = anchor_date + timedelta(days=1)
            if now_ist.timetz().replace(tzinfo=None) < market_boundary.profile.regular_session_close:
                end_date = current_trade_date - timedelta(days=1)
            else:
                end_date = current_trade_date

            while cursor_date <= end_date:
                if market_boundary.calendar_snapshot is not None:
                    if not market_boundary.calendar_snapshot.is_covered(cursor_date):
                        raise PaperConfigurationError(
                            f"offline recovery cursor_date {cursor_date} lies outside calendar closure snapshot coverage "
                            f"[{market_boundary.calendar_snapshot.coverage_start}, {market_boundary.calendar_snapshot.coverage_end}]"
                        )

                if market_boundary.calendar.is_tradable_date(cursor_date):
                    existing_records = self._store.load_promotion_session_records(owner)
                    if not any(r.session_date == cursor_date for r in existing_records):
                        reasons = [PromotionDisqualificationReason.OFFLINE_REQUIRED_SESSION.value]
                        if binding.activation == "observation_only":
                            reasons.append(PromotionDisqualificationReason.OBSERVATION_ONLY.value)
                        if current_state.activated_at is not None:
                            act_ist = current_state.activated_at.astimezone(market_boundary.profile.timezone)
                            if act_ist.date() == cursor_date and act_ist.timetz().replace(tzinfo=None) > market_boundary.profile.regular_session_open:
                                reasons.append(PromotionDisqualificationReason.PARTIAL_SESSION_AT_ACTIVATION.value)

                        next_state, record = PromotionTrackingEngine.evaluate_session_finalization(
                            current_state=current_state,
                            session_date=cursor_date,
                            is_clean=False,
                            disqualification_reasons=tuple(sorted(set(reasons))),
                            activation=binding.activation,
                            now_utc=now_utc,
                        )
                        self._store.save_promotion_session_finalization(owner, record, next_state)
                        current_state = next_state
                cursor_date += timedelta(days=1)

            if self._hydrated_state is not None and owner in self._hydrated_state.promotion_tracking_states:
                self._hydrated_state.promotion_tracking_states[owner] = current_state

    def _finalize_promotion_sessions(self, outcome: _TerminationOutcome, now_utc: datetime | None = None) -> None:
        """Authoritatively finalize and durably commit promotion session records for all active strategies (ADR §122 / OD-AB)."""
        if self._store is None or self._resolved_configuration is None:
            return

        market_boundary = self._market_boundary or MarketSessionBoundary(profile=india_market_profile())
        now_utc = now_utc or recorded_at_utc_now()
        now_ist = now_utc.astimezone(market_boundary.profile.timezone)
        session_date = now_ist.date()

        if market_boundary.calendar_snapshot is not None:
            if not market_boundary.calendar_snapshot.is_covered(session_date):
                raise PaperConfigurationError(
                    f"session_date {session_date} lies outside calendar closure snapshot coverage "
                    f"[{market_boundary.calendar_snapshot.coverage_start}, {market_boundary.calendar_snapshot.coverage_end}]"
                )

        if not market_boundary.calendar.is_tradable_date(session_date):
            return

        final_rec_health = None
        if self._paper_coordinator is not None:
            final_rec_health = self._paper_coordinator.reconciliation_health

        global_reasons: list[str] = []

        # 1. Start boundary observation check (OD-AB)
        if self._started_at_ist is not None:
            if self._started_at_ist.date() == session_date:
                if self._started_at_ist.timetz().replace(tzinfo=None) > market_boundary.profile.regular_session_open:
                    act_dt = self._resolved_configuration.promotion_tracking_activated
                    if act_dt is not None and act_dt.astimezone(market_boundary.profile.timezone).date() == session_date:
                        global_reasons.append(PromotionDisqualificationReason.PARTIAL_SESSION_AT_ACTIVATION.value)
                    else:
                        global_reasons.append(PromotionDisqualificationReason.INCOMPLETE_SESSION_OBSERVATION.value)
            elif self._started_at_ist.date() > session_date:
                global_reasons.append(PromotionDisqualificationReason.INCOMPLETE_SESSION_OBSERVATION.value)

        # 2. Close boundary observation check (OD-AB)
        if now_ist.timetz().replace(tzinfo=None) < market_boundary.profile.regular_session_close:
            if outcome.primary_error is not None or outcome.status == "failed":
                global_reasons.append(PromotionDisqualificationReason.RUNTIME_FAILURE.value)
            else:
                global_reasons.append(PromotionDisqualificationReason.INCOMPLETE_SESSION_OBSERVATION.value)
        else:
            if outcome.primary_error is not None or outcome.status == "failed":
                global_reasons.append(PromotionDisqualificationReason.RUNTIME_FAILURE.value)

        if final_rec_health == ReconciliationHealth.FAILED:
            global_reasons.append(PromotionDisqualificationReason.RECONCILIATION_FAILURE.value)
        if self._feed is not None and getattr(self._feed, "has_unresolved_data_gap", False):
            global_reasons.append(PromotionDisqualificationReason.DATA_GAP.value)

        act_dt = self._resolved_configuration.promotion_tracking_activated
        if act_dt is not None:
            act_ist = act_dt.astimezone(market_boundary.profile.timezone)
            if act_ist.date() == session_date and act_ist.timetz().replace(tzinfo=None) > market_boundary.profile.regular_session_open:
                if PromotionDisqualificationReason.PARTIAL_SESSION_AT_ACTIVATION.value not in global_reasons:
                    global_reasons.append(PromotionDisqualificationReason.PARTIAL_SESSION_AT_ACTIVATION.value)

        for owner, binding in self._resolved_configuration.strategy_bindings.items():
            owner_reasons = list(global_reasons)
            if binding.activation == "observation_only":
                owner_reasons.append(PromotionDisqualificationReason.OBSERVATION_ONLY.value)
            if not self._resolved_configuration.promotion_eligible:
                owner_reasons.extend(self._resolved_configuration.promotion_ineligibility_reasons or (PromotionDisqualificationReason.RESEARCH_ZERO_COST.value,))
            if binding.upstream_promotion_evidence_fingerprint is None:
                owner_reasons.append(PromotionDisqualificationReason.UPSTREAM_EVIDENCE_ABSENT.value)
            if not getattr(binding, "upstream_promotion_evidence_promotable", True):
                owner_reasons.append(PromotionDisqualificationReason.UPSTREAM_UNPROMOTABLE.value)

            current_states = self._store.load_promotion_tracking_states()
            current_state = current_states.get(owner)
            if current_state is None:
                continue

            if current_state.last_evaluated_session_date == session_date:
                continue

            is_clean = len(owner_reasons) == 0
            next_state, record = PromotionTrackingEngine.evaluate_session_finalization(
                current_state=current_state,
                session_date=session_date,
                is_clean=is_clean,
                disqualification_reasons=tuple(sorted(set(owner_reasons))),
                activation=binding.activation,
                now_utc=now_utc,
            )
            self._store.save_promotion_session_finalization(owner, record, next_state)
            if self._hydrated_state is not None and owner in self._hydrated_state.promotion_tracking_states:
                self._hydrated_state.promotion_tracking_states[owner] = next_state

            if next_state.window_start_date is not None and session_date >= next_state.window_start_date + relativedelta(months=6):
                self._evaluate_milestone_and_publish(owner, next_state, session_date)

    def _evaluate_milestone_and_publish(
        self,
        owner: SubscriptionOwnerKey,
        current_state: PromotionTrackingState,
        evaluation_date: date,
    ) -> None:
        """Evaluate milestone from authoritative store ledger and publish canonical report."""
        if self._store is None or self._resolved_configuration is None:
            return
        binding = self._resolved_configuration.strategy_bindings.get(owner)
        upstream_oos_ok = bool(getattr(binding, "upstream_promotion_evidence_promotable", True))
        report_dest = self._resolved_configuration.promotion_report_destination_dir
        next_state, report, report_path = PromotionTrackingEngine.evaluate_milestone_from_store(
            store=self._store,
            owner=owner,
            upstream_oos_profitable=upstream_oos_ok,
            evaluation_date=evaluation_date,
            now_utc=recorded_at_utc_now(),
            report_destination_dir=report_dest,
        )
        if self._hydrated_state is not None and owner in self._hydrated_state.promotion_tracking_states:
            self._hydrated_state.promotion_tracking_states[owner] = next_state





# ======================================================================
# CLI Entry Point
# ======================================================================


def _positive_strategy_error_threshold(raw: str) -> int:
    """Argparse validator for the required OD-3 threshold."""
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer >= 1") from exc
    if value < 1:
        raise argparse.ArgumentTypeError("must be a positive integer >= 1")
    return value


def _build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser for live paper trading runner."""
    parser = argparse.ArgumentParser(
        prog="python -m engine.paper.live_runner",
        description="SentinelX Live Market Paper Trading Runner (Virtual Money Only).",
    )
    parser.add_argument(
        "--paper-session-id",
        type=str,
        default=f"session_{recorded_at_utc_now().strftime('%Y%m%d_%H%M%S')}",
        help="Unique identifier for this paper trading session.",
    )
    parser.add_argument(
        "--paper-config",
        dest="paper_config_path",
        type=str,
        default="config/paper_config.yaml",
        help="Required root paper environment configuration file.",
    )
    parser.add_argument(
        "--instrument-master",
        dest="instrument_master_path",
        type=str,
        default=None,
        help="Path to Upstox BOD instrument master JSON file.",
    )
    parser.add_argument(
        "--strategy-error-kill-threshold",
        type=_positive_strategy_error_threshold,
        required=True,
        help="Required positive Phase 8 per-session strategy-error kill threshold.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Perform offline configuration and schema validation only without network connections.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI main entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    config = LivePaperRunnerConfig(
        paper_session_id=args.paper_session_id,
        paper_config_path=args.paper_config_path,
        instrument_master_path=args.instrument_master_path,
        strategy_error_kill_threshold=args.strategy_error_kill_threshold,
    )

    runner = LivePaperTradingRunner(config)

    if args.validate_only:
        try:
            val_result = runner.validate_only()
            print("SentinelX Live Paper Runner Validation: SUCCESS")
            for k, v in val_result.items():
                print(f"  {k}: {v}")
            return 0
        except Exception as exc:
            print(f"SentinelX Live Paper Runner Validation: FAILED - {exc}", file=sys.stderr)
            return 1

    try:
        print(f"Starting SentinelX Live Paper Session: {config.paper_session_id}")
        res = runner.run()
        print(f"Session finished with status: {res.status}")
        return 0 if res.status == "completed" else 1
    except KeyboardInterrupt:
        print("\nOperator interrupted. Gracefully shutting down...")
        runner.shutdown()
        return 0
    except Exception as exc:
        print(f"Error during live paper session: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
