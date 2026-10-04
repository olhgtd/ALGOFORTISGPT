"""Authoritative Paper Trading Service for AlgoFortis.

Orchestrates the authoritative paper trading pipeline:
1. Enforces fail-closed strategy governance (HTTP 403 on admin suspension or owner hold).
2. Manages paper session lifecycle: create, start, stop, query.
3. Coordinates market-data replay via canonical HistoricalDataFeed.
4. Validates entries through pre-order RiskGate (per-trade risk, daily loss, max open positions, capital envelope).
5. Submits orders to SimulatedPaperBroker with PaperFillAdapter and realistic slippage.
6. Updates VirtualPaperAccount with exact fill accounting and MTM position valuation.
7. Persists sessions, positions, orders, and events into SQLiteSecurityStore.
8. Emits canonical AuditEvent evidence for full governance and oversight traceability.
"""

from __future__ import annotations

import json
import logging
import math
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import pandas as pd

from engine.audit.model import (
    AUDIT_ENVELOPE_SCHEMA_VERSION,
    AuditEvent,
    AuditEventFamily,
    AuditEventType,
    recorded_at_utc_now,
)
from engine.data.feeds.historical_feed import HistoricalDataFeed
from engine.data.feeds.live_feed import (
    FeedConnectionState,
    LiveMarketDataFeed,
    LiveQuoteEvent,
    deterministic_live_quote_event_id,
)
from engine.data.feeds.quote_cache import (
    LatestQuoteCache,
    QuoteCacheResult,
    QuoteCacheStatus,
)
from engine.execution.model import ExecutableOrder, ExecutionResult
from engine.execution.paper_broker import (
    BrokerQuoteEvent,
    BrokerSubmissionResult,
    BrokerTerminalEvent,
    SimulatedPaperBroker,
)
from engine.execution.paper_fill import (
    FixedBasisPointsSlippage,
    PaperFillAdapter,
    PaperFillPolicy,
)
from engine.execution.quote import QuoteSnapshot
from .backtest_datasets import ApprovedDatasetFiles, DatasetUnavailable
from engine.orders.lifecycle import OrderLifecycleState
from engine.orders.model import (
    ConcreteCloseInstruction,
    ConcreteOpenInstruction,
    OrderRequest,
    OrderType,
    SignalIntent,
    TimeInForce,
)
from engine.portfolio.model import (
    AccountSnapshot,
    InstrumentIdentity,
    InstrumentSpecification,
    PositionKey,
    PositionSnapshot,
)
from engine.portfolio.virtual_account import (
    ValuationState,
    VirtualAccountInvariantError,
    VirtualPaperAccount,
)
from engine.protective.plan import PreEntryProtectivePlan
from engine.protective.runtime import (
    ProtectiveExit,
    ProtectiveExitBook,
    ProtectiveExitKind,
    ProtectiveExitState,
)
from engine.risk.risk_manager import (
    PositionDirection,
    RiskDay,
    RiskGate,
    RiskGateResult,
    RiskGateState,
    RiskOutcome,
    RiskPolicy,
    RISK_POLICY_VERSION_V3,
    SUPPORTED_RISK_POLICY_VERSIONS,
)
from dashboard.backend.backtest_service import GovernanceRejectionError
from dashboard.backend.governance_store import SQLiteGovernanceStore, GovernanceStoreError
from dashboard.backend.security_store import SQLiteSecurityStore
from dashboard.backend.strategy_execution import BoundedStrategy
from dashboard.backend.strategy_validation import StrategyValidationError
from engine.portfolio.accounting import PortfolioAccount


# N-P2-01 deterministic replay pricing model (historical paper only).
#
# Historical bars carry no exchange bid/ask, so replay prices are MODELED
# (never claimed as observed exchange quotes):
# - entry premium: quantitative Black-Scholes model_option_premium;
# - modeled spread: fixed half-spread around the premium (both sides);
# - exit/MTM premium: entry premium adjusted by REPLAY_EXIT_DELTA_FACTOR of
#   the underlying spot move since entry, floored at REPLAY_PREMIUM_FLOOR.
# All three constants are pure functions of replay inputs (deterministic),
# persisted in fill/close evidence, and traceable here (single definition).
REPLAY_MODELED_SPREAD_HALF = Decimal("0.05")
REPLAY_EXIT_DELTA_FACTOR = 0.45
REPLAY_PREMIUM_FLOOR = 5.0
REPLAY_PRICING_BASIS = (
    "Black-Scholes modeled premium, +/-0.05 modeled spread, "
    "exit/MTM via 0.45 spot-delta model floored at 5.0; provenance MODELED"
)


def resolve_option_strike(
    spot_price: float,
    instrument: str,
    option_type: str = "CE",
    moneyness_mode: str = "OTM",
    moneyness_distance: int = 1,
) -> int:
    """Resolve realistic option strike. BANKNIFTY strike step is 100, NIFTY is 50."""
    step = 50 if instrument.upper() == "NIFTY" else 100
    atm = int(round(spot_price / step) * step)
    mode = (moneyness_mode or "OTM").upper().strip()
    dist = max(0, int(moneyness_distance or 0))
    if mode == "ATM" or dist == 0:
        return atm
    if mode == "OTM":
        offset = step * dist
        return atm + offset if option_type.upper() == "CE" else atm - offset
    if mode == "ITM":
        offset = step * dist
        return atm - offset if option_type.upper() == "CE" else atm + offset
    return atm


def resolve_nearest_weekly_expiry(reference_date: date) -> date:
    """Resolve nearest Thursday weekly expiry date."""
    weekday = reference_date.weekday()  # Monday is 0, Thursday is 3
    days_ahead = (3 - weekday) % 7
    return reference_date + timedelta(days=days_ahead)


def model_option_premium(
    spot: float,
    strike: float,
    reference_dt: datetime,
    expiry_dt: date,
    instrument: str,
    option_type: str = "CE",
    implied_vol: float | None = None,
    risk_free_rate: float = 0.065,
) -> Decimal:
    """Model realistic Black-Scholes option premium without synthetic fixed scalars."""
    ref_date = reference_dt.date() if isinstance(reference_dt, datetime) else reference_dt
    days_to_expiry = max(1, (expiry_dt - ref_date).days)
    t_years = days_to_expiry / 365.0
    sigma = implied_vol if implied_vol is not None else (0.15 if instrument.upper() == "NIFTY" else 0.18)

    s = max(0.01, float(spot))
    k = max(0.01, float(strike))

    d1 = (math.log(s / k) + (risk_free_rate + 0.5 * sigma ** 2) * t_years) / (sigma * math.sqrt(t_years))
    d2 = d1 - sigma * math.sqrt(t_years)
    norm_d1 = 0.5 * (1.0 + math.erf(d1 / math.sqrt(2.0)))
    norm_d2 = 0.5 * (1.0 + math.erf(d2 / math.sqrt(2.0)))

    if option_type.upper() == "CE":
        call_price = s * norm_d1 - k * math.exp(-risk_free_rate * t_years) * norm_d2
        price = max(5.0, round(call_price, 2))
    else:
        norm_neg_d1 = 0.5 * (1.0 + math.erf(-d1 / math.sqrt(2.0)))
        norm_neg_d2 = 0.5 * (1.0 + math.erf(-d2 / math.sqrt(2.0)))
        put_price = k * math.exp(-risk_free_rate * t_years) * norm_neg_d2 - s * norm_neg_d1
        price = max(5.0, round(put_price, 2))

    return Decimal(str(price)).quantize(Decimal("0.05"))


def create_candidate_protective_plan(
    intended_position_key: PositionKey,
    originating_timestamp: datetime,
    timeframe: str,
    entry_price: Decimal,
    capital: Decimal,
    lot_size: int,
    per_trade_risk_pct: Decimal = Decimal("0.005"),
    policy_version: str = "risk-policy/v3",
) -> PreEntryProtectivePlan:
    """Create a validated candidate PreEntryProtectivePlan for RiskGate evaluation."""
    ts = originating_timestamp if originating_timestamp.tzinfo is not None else originating_timestamp.replace(tzinfo=IST)
    target_lot_dist = (capital * per_trade_risk_pct) / Decimal(str(lot_size))
    if entry_price > target_lot_dist:
        stop_dist = target_lot_dist.quantize(Decimal("0.05"))
    else:
        stop_dist = min(target_lot_dist, (entry_price * Decimal("0.5")).quantize(Decimal("0.05")))
    stop_dist = max(Decimal("0.05"), stop_dist.quantize(Decimal("0.05")))

    stop_price = (entry_price - stop_dist).quantize(Decimal("0.05"))
    target_dist = (stop_dist * Decimal("2.0")).quantize(Decimal("0.05"))
    target_price = (entry_price + target_dist).quantize(Decimal("0.05"))

    return PreEntryProtectivePlan(
        intended_position_key=intended_position_key,
        originating_timestamp=ts,
        timeframe=timeframe,
        protective_plan_policy_identity=policy_version,
        stop_price=stop_price,
        target_price=target_price,
    )

logger = logging.getLogger(__name__)
UTC = timezone.utc
IST = ZoneInfo("Asia/Kolkata")

SUPPORTED_INSTRUMENTS = {"NIFTY", "BANKNIFTY"}
SUPPORTED_TIMEFRAMES = {"1m", "5m", "15m", "30m", "1H"}
SUPPORTED_DATA_SOURCE_MODES = {"HISTORICAL_REPLAY", "LIVE_MARKET"}


class InvalidPaperParameterError(Exception):
    """Raised when paper trading parameters fail validation or constraints."""
    pass


class PaperSessionNotFoundError(Exception):
    """Raised when a requested paper session does not exist or belongs to another user."""
    pass


class ExternalLiveDataSourceRequiredError(Exception):
    """Raised when LIVE_MARKET paper trading is initiated without external data credentials."""
    pass


class LiveOptionQuoteUnavailableError(Exception):
    """Raised when real option quote authority is unavailable in LIVE_MARKET mode."""
    pass


class FeedNotConnectedError(Exception):
    """Raised when paper orders/quotes cannot be processed because live feed is not connected."""
    pass


class StaleQuoteError(Exception):
    """Raised when an incoming live quote violates freshness/staleness thresholds."""
    pass


class OutOfOrderQuoteError(Exception):
    """Raised when an incoming live quote has an out-of-order exchange timestamp."""
    pass


class WrongInstrumentError(Exception):
    """Raised when an incoming live quote does not match the session instrument."""
    pass


class PaperService:
    """Production paper trading execution and state management coordinator."""

    def __init__(
        self,
        security_store: SQLiteSecurityStore,
        governance_store: SQLiteGovernanceStore | None = None,
        artifact_root: str | Path | None = None,
        feed: HistoricalDataFeed | None = None,
        test_feed_mode: bool = False,
        dataset_feed: Any | None = None,
        dataset_root: str | Path | None = None,
    ) -> None:
        self._security_store = security_store
        self._governance_store = governance_store
        self._artifact_root = Path(artifact_root) if artifact_root is not None else None
        self._feed = feed or HistoricalDataFeed()
        self._live_contexts: dict[str, dict[str, Any]] = {}
        self._test_feeds: dict[str, Any] = {}
        # NF-06: authoritative dataset pin for historical replay. Mirrors the
        # backtest contract: ApprovedDatasetFiles-compatible authority
        # (fetch_dataset) or fail closed; never a raw feed fallback.
        self._dataset_feed = dataset_feed or (
            ApprovedDatasetFiles(Path(dataset_root)) if dataset_root is not None else None
        )
        # NF-R203-04: test-only live-feed injection is explicitly isolated.
        # Production wiring never passes test_feed_mode=True, so _test_feeds
        # stays empty and every live-market gate consults only the user's
        # canonical user_connections authority. No process-global credential
        # is ever consulted here.
        self._test_feed_mode = bool(test_feed_mode)
        try:
            self.auto_reattach_active_sessions()
        except Exception as exc:
            logger.warning("Error during initial paper session recovery: %s", exc)

    def create_session(
        self,
        *,
        user_id: str,
        strategy_id: str,
        instrument: str = "NIFTY",
        timeframe: str = "1m",
        initial_capital: float = 50000.0,
        policy: dict[str, Any] | None = None,
        data_source_mode: str = "HISTORICAL_REPLAY",
        date_range: str | None = None,
        dataset_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new paper trading session in INITIALIZED state."""
        # 0. Mode Validation
        mode = data_source_mode.upper().strip()
        if mode not in SUPPORTED_DATA_SOURCE_MODES:
            raise InvalidPaperParameterError(
                f"Unsupported data_source_mode '{data_source_mode}'. Supported: {sorted(SUPPORTED_DATA_SOURCE_MODES)}"
            )

        # 1. Parameter Normalization & Validation
        inst = instrument.upper().strip()
        if inst not in SUPPORTED_INSTRUMENTS:
            raise InvalidPaperParameterError(
                f"Unsupported instrument '{instrument}'. Supported: {sorted(SUPPORTED_INSTRUMENTS)}"
            )

        tf = timeframe.strip()
        if tf not in SUPPORTED_TIMEFRAMES:
            raise InvalidPaperParameterError(
                f"Unsupported timeframe '{timeframe}'. Supported: {sorted(SUPPORTED_TIMEFRAMES)}"
            )

        if initial_capital < 1000.0 or initial_capital > 100000000.0:
            raise InvalidPaperParameterError(
                f"initial_capital must be between 1,000 and 100,000,000 INR (got {initial_capital})"
            )

        # 1b. User Validation (DB-006: active user required for new paper session)
        user = self._security_store.get_user(user_id)
        if user is None:
            raise GovernanceRejectionError(f"User '{user_id}' does not exist")
        user_dict = dict(user) if hasattr(user, "keys") else user
        if user_dict.get("lifecycle") != "ACTIVE" or user_dict.get("account_status") != "ACTIVE":
            raise GovernanceRejectionError(f"Active authenticated User required (user '{user_id}')")

        # 2. Strategy Governance Check (Fail-Closed)
        gov = self._security_store.get_owner_strategy(strategy_id)
        if not gov:
            raise InvalidPaperParameterError(f"Strategy '{strategy_id}' not registered")

        admin_status = gov.get("adminStatus") or gov.get("admin_status") or "ACTIVE"
        if admin_status != "ACTIVE":
            raise GovernanceRejectionError(
                f"Strategy '{strategy_id}' is {admin_status} under Owner governance"
            )

        allowance = (
            gov.get("governance", {}).get("paper", {}).get("ownerAllowance")
            or gov.get("paper_owner_allowance")
            or "ALLOWED"
        )
        if allowance != "ALLOWED":
            hold_reason = (
                gov.get("governance", {}).get("paper", {}).get("ownerHoldReason")
                or gov.get("paper_owner_hold_reason")
                or "Owner execution hold active"
            )
            raise GovernanceRejectionError(
                f"Strategy '{strategy_id}' paper execution is on {allowance}: {hold_reason}"
            )

        # 2b. Persisted strategy authority (F-10): user-submitted strategies
        # (author is a real user identity) require authorship or an explicit
        # persisted assignment. Owner-published canonical catalog strategies
        # remain usable by active users under the allowance/hold gates above.
        access = self._security_store.check_user_strategy_access(user_id, strategy_id)
        if not access.get("permitted"):
            if access.get("reason") == "STRATEGY_NOT_ASSIGNED" and self._security_store.get_user(
                str(gov.get("author") or "")
            ) is None:
                pass
            else:
                raise GovernanceRejectionError(
                    f"Strategy '{strategy_id}' not available to user: {access.get('reason')}"
                )

        pol = policy or {"mode": "OTM", "distance": 1}
        risk_policy_ver = pol.get("risk_policy_version") or pol.get("version")
        if risk_policy_ver and risk_policy_ver not in SUPPORTED_RISK_POLICY_VERSIONS:
            raise InvalidPaperParameterError(
                f"Unsupported RiskPolicy version '{risk_policy_ver}'. Supported: {sorted(SUPPORTED_RISK_POLICY_VERSIONS)}"
            )

        # 3. Derive Session ID and Policy Snapshot
        # F-15: Collision-resistant paper session ID (full UUID4 entropy, restart-safe, concurrency-safe, independent of list length)
        session_id = None
        for _ in range(10):
            candidate_id = f"PAPER-SES-{uuid.uuid4().hex.upper()}"
            if self._security_store.get_paper_session(candidate_id) is None:
                session_id = candidate_id
                break
        if session_id is None:
            session_id = f"PAPER-SES-{uuid.uuid4().hex.upper()}"

        policy_mode = pol.get("mode", "OTM").upper()
        policy_distance = pol.get("distance", 1)
        if policy_mode == "ATM":
            policy_snapshot = "ATM · 0 STRIKES"
        else:
            plural = "S" if policy_distance > 1 else ""
            policy_snapshot = f"{policy_mode} · {policy_distance} STRIKE{plural}"

        data_source_name = "UPSTOX_V3_FEED" if mode == "LIVE_MARKET" else "HISTORICAL_REPLAY"

        # 4. Insert into Store
        session = self._security_store.create_paper_session(
            session_id=session_id,
            user_id=user_id,
            strategy_id=strategy_id,
            strategy_name=gov.get("name", strategy_id),
            strategy_version=gov.get("version", "1.0"),
            instrument=inst,
            timeframe=tf,
            initial_capital=float(initial_capital),
            policy_snapshot=policy_snapshot,
            policy_details=pol,
            data_source_name=data_source_name,
            data_source_mode=mode,
            feed_status="DISCONNECTED",
            date_range=date_range,
            dataset_id=dataset_id,
        )

        # 5. Record Initial Event
        now_ist = datetime.now(IST).strftime("%H:%M:%S IST")
        mode_label = "Live Market (Virtual Execution)" if mode == "LIVE_MARKET" else "Historical Replay"
        self._security_store.record_paper_event(
            event_id=f"pe-{uuid.uuid4().hex[:8]}",
            session_id=session_id,
            event_time=now_ist,
            title="Paper Session Initialized",
            detail=f"Desk initialized with ₹{initial_capital:,.0f} base capital on {inst} ({tf}). Mode: {mode_label}. Policy: {policy_snapshot}.",
            source="Paper Desk",
            status="INFO",
            badge="INITIALIZED",
        )

        return session

    def start_session(
        self,
        session_id: str,
        *,
        user_id: str,
    ) -> dict[str, Any]:
        """Start paper execution for an existing session."""
        session = self._security_store.get_paper_session(session_id, user_id=user_id)
        if not session:
            raise PaperSessionNotFoundError(f"Paper session '{session_id}' not found or access denied")

        strategy_id = session["strategy_id"]
        gov = self._security_store.get_owner_strategy(strategy_id)
        if not gov:
            raise GovernanceRejectionError(f"Strategy '{strategy_id}' not registered")
        admin_status = gov.get("adminStatus") or gov.get("admin_status") or "ACTIVE"
        if admin_status != "ACTIVE":
            raise GovernanceRejectionError(f"Strategy '{strategy_id}' is {admin_status} under Owner governance")
        allowance = (
            gov.get("governance", {}).get("paper", {}).get("ownerAllowance")
            or gov.get("paper_owner_allowance")
            or "ALLOWED"
        )
        if allowance != "ALLOWED":
            raise GovernanceRejectionError(f"Strategy '{strategy_id}' paper execution is on {allowance}")
        current_status = session.get("status")
        if current_status == "STOPPED":
            raise InvalidPaperParameterError(f"Paper session '{session_id}' is STOPPED and cannot be restarted")
        if current_status == "FAILED":
            raise InvalidPaperParameterError(f"Paper session '{session_id}' is FAILED and cannot be started: {session.get('error_message')}")

        mode = session.get("data_source_mode") or session.get("data_source_name", "HISTORICAL_REPLAY")
        if current_status == "ACTIVE":
            if mode == "LIVE_MARKET" and session_id in self._live_contexts:
                return session
            if mode != "LIVE_MARKET":
                raise InvalidPaperParameterError(f"Paper session '{session_id}' is already ACTIVE and cannot be restarted")

        if mode == "LIVE_MARKET":
            return self._start_live_market_session(session=session, user_id=user_id, gov=gov)

        return self._start_historical_replay_session(session=session, user_id=user_id, gov=gov)

    def _start_historical_replay_session(
        self,
        *,
        session: dict[str, Any],
        user_id: str,
        gov: dict[str, Any],
    ) -> dict[str, Any]:
        session_id = session["session_id"]
        strategy_id = session["strategy_id"]

        inst = session["instrument"]
        tf = session["timeframe"]
        initial_capital = float(session["initial_capital"])
        strategy_name = session["strategy_name"]
        strategy_version = session["strategy_version"]
        policy_snapshot = session["policy_snapshot"]

        # NF-06: authoritative dataset pin. Historical replay resolves the
        # approved dataset identity (strategy/dataset/instrument/timeframe/
        # range/hash) through the same governance used by backtests, and
        # fails closed when any requirement is unmet. No raw feed fallback.
        dataset_id = str(session.get("dataset_id") or "nse-tick-primary")
        gate = self._security_store.check_backtest_gate(
            strategy_id, dataset_id, user_id=user_id, instrument=inst, timeframe=tf)
        if not gate.get("permitted"):
            raise GovernanceRejectionError(str(gate.get("code")) + ": " + str(gate.get("reason")))
        dataset = gate["dataset"]
        if self._dataset_feed is None or not hasattr(self._dataset_feed, "fetch_dataset"):
            raise InvalidPaperParameterError("DATASET_BINDING_UNAVAILABLE")
        try:
            df, file_digest = self._dataset_feed.fetch_dataset(dataset)
            df = df.copy()
        except DatasetUnavailable as exc:
            raise InvalidPaperParameterError(str(exc)) from None
        if file_digest != dataset["hashSha256"].removeprefix("sha256:"):
            raise InvalidPaperParameterError("DATASET_HASH_MISMATCH")
        if not {"timestamp", "open", "high", "low", "close", "volume"}.issubset(df.columns):
            raise InvalidPaperParameterError("DATASET_COLUMNS_INVALID")
        for column, expected in (("instrument", inst), ("timeframe", tf)):
            if column in df and not df[column].eq(expected).all():
                raise InvalidPaperParameterError("DATASET_CONTENT_IDENTITY_MISMATCH")
        if df.empty or "timestamp" not in df:
            raise InvalidPaperParameterError("Historical dataset is empty or lacks timestamps")

        # Date range filtering if requested (F-4); the requested range must
        # sit inside the approved dataset coverage (mirror backtest).
        requested_date_range = session.get("date_range") or session.get("requested_date_range")
        if requested_date_range:
            req_str = str(requested_date_range).strip()
            parts = [p.strip() for p in re.split(r"[:/]|to", req_str) if p.strip()]
            try:
                if len(parts) == 1:
                    start_d = date.fromisoformat(parts[0])
                    end_d = start_d
                elif len(parts) >= 2:
                    start_d = date.fromisoformat(parts[0])
                    end_d = date.fromisoformat(parts[1])
                else:
                    raise ValueError(f"Invalid date_range: {req_str}")
            except Exception as exc:
                raise InvalidPaperParameterError(f"Invalid date_range format '{req_str}': {exc}") from exc
            if (start_d.isoformat() < str(dataset["startDate"])
                    or end_d.isoformat() > str(dataset["endDate"])):
                raise InvalidPaperParameterError(
                    "DATASET_RANGE_UNAPPROVED: Requested date range exceeds approved dataset coverage")

            ts_series = pd.to_datetime(df["timestamp"])
            if ts_series.dt.tz is not None:
                start_dt = datetime.combine(start_d, datetime.min.time(), tzinfo=IST)
                end_dt = datetime.combine(end_d, datetime.max.time(), tzinfo=IST)
            else:
                start_dt = datetime.combine(start_d, datetime.min.time())
                end_dt = datetime.combine(end_d, datetime.max.time())

            mask = (ts_series >= start_dt) & (ts_series <= end_dt)
            df = df.loc[mask]
            if df.empty:
                raise InvalidPaperParameterError(f"No market data available for {inst} {tf} in date range '{req_str}'")

        try:
            timestamps = pd.to_datetime(df["timestamp"], utc=True)
            if timestamps.isna().any() or not timestamps.is_monotonic_increasing or timestamps.duplicated().any():
                raise InvalidPaperParameterError("DATASET_BAR_ORDER_INVALID")
        except InvalidPaperParameterError:
            raise
        except Exception as exc:
            raise InvalidPaperParameterError(f"Invalid dataset timestamps: {exc}") from exc

        try:
            self._security_store.record_paper_event(
                event_id=f"pe-{uuid.uuid4().hex[:8]}",
                session_id=session_id,
                event_time=datetime.now(IST).strftime("%H:%M:%S IST"),
                title="Historical dataset pinned",
                detail=(f"dataset={dataset_id} instrument={inst} timeframe={tf} "
                        f"sha256={file_digest[:16]}... bars={len(df)}"),
                source="Dataset Authority",
                status="PASS",
                badge="DATASET_PINNED",
            )
        except Exception:
            pass

        replay_df = df
        total_bars = len(replay_df)
        first_consumed_ts = str(replay_df.iloc[0]["timestamp"])
        last_consumed_ts = str(replay_df.iloc[-1]["timestamp"])

        # Initialize Simulation Engine Components
        fill_policy = PaperFillPolicy(
            slippage_model=FixedBasisPointsSlippage(0),
            max_execution_tolerance_bps=Decimal("50"),
            max_slippage_bps=Decimal("20"),
        )
        fill_adapter = PaperFillAdapter(fill_policy)
        broker = SimulatedPaperBroker(adapter=fill_adapter)

        # Sizing and contract specs
        lot_size = 50 if inst == "NIFTY" else 15
        spec = InstrumentSpecification(
            identity=InstrumentIdentity(market="NSE", instrument=inst, segment="INDEX"),
            effective_from=datetime(2026, 1, 1).date(),
            price_increment=Decimal("0.05"),
            contract_multiplier=Decimal(str(lot_size)),
            minimum_quantity=Decimal(str(lot_size)),
            quantity_step=Decimal(str(lot_size)),
            currency="INR",
        )

        portfolio_acc = PortfolioAccount(
            account_id=f"ACC_PAPER_{session_id}",
            currency="INR",
            starting_capital=Decimal(str(initial_capital)),
            monetary_quantum=Decimal("0.01"),
        )
        account = VirtualPaperAccount(
            portfolio_account=portfolio_acc,
            specifications={spec.identity: spec},
            require_opening_reservation=False,
        )

        strat_gen = self._resolve_paper_strategy_artifact(user_id, strategy_id, strategy_version)
        current_state = strat_gen.initial_state()

        # Build Authoritative Engine RiskPolicy and RiskGate (F-24)
        policy_details = session.get("policy_details") or {}
        policy_version = policy_details.get("risk_policy_version") or policy_details.get("version") or RISK_POLICY_VERSION_V3
        if policy_version not in SUPPORTED_RISK_POLICY_VERSIONS:
            raise InvalidPaperParameterError(f"Unsupported RiskPolicy version '{policy_version}'")

        risk_policy_kwargs: dict[str, Any] = {"version": policy_version}
        for k in ("per_trade_risk_pct", "max_daily_loss_pct", "max_daily_trades", "max_open_positions", "max_portfolio_risk_pct"):
            if k in policy_details:
                risk_policy_kwargs[k] = policy_details[k]
        risk_policy = RiskPolicy(**risk_policy_kwargs)
        risk_gate = RiskGate(risk_policy)
        session_protective_book = ProtectiveExitBook()
        session_risk_state: RiskGateState | None = None

        open_positions: list[dict[str, Any]] = []

        # Replay ALL bars in replay_df (F-4: no tail(60) window!)
        for _, row in replay_df.iterrows():
            bar_ts = row["timestamp"]
            if hasattr(bar_ts, "to_pydatetime"):
                bar_dt = bar_ts.to_pydatetime()
            else:
                bar_dt = pd.to_datetime(bar_ts).to_pydatetime()
            if bar_dt.tzinfo is None:
                bar_dt = bar_dt.replace(tzinfo=IST)
            else:
                bar_dt = bar_dt.astimezone(IST)

            bar_close = Decimal(str(round(float(row["close"]), 2)))

            # Evaluate strategy signal
            bar_series = pd.Series({
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume", 1000)),
            })

            try:
                sig = strat_gen.generate_signal(bar_series, current_state)
            except Exception as exc:
                logger.warning("Strategy signal generation error: %s", exc)
                continue

            # Signal: BUY (Long Entry)
            sig_action = getattr(sig, "action", getattr(sig, "value", None))
            if sig_action == "BUY":
                # Resolve strike, expiry, symbol, and modeled premium (F-3)
                policy_mode = policy_details.get("mode", "OTM")
                policy_distance = policy_details.get("distance", 1)
                resolved_strike = resolve_option_strike(
                    float(bar_close),
                    inst,
                    option_type="CE",
                    moneyness_mode=policy_mode,
                    moneyness_distance=policy_distance,
                )
                expiry_date = resolve_nearest_weekly_expiry(bar_dt.date())
                resolved_symbol = f"{inst}{expiry_date.strftime('%y%m%d')}{resolved_strike}CE"

                # Quantitative Black-Scholes pricing (F-3: no fixed 0.0055/0.0065 scalars)
                opt_premium = model_option_premium(
                    spot=float(bar_close),
                    strike=float(resolved_strike),
                    reference_dt=bar_dt,
                    expiry_dt=expiry_date,
                    instrument=inst,
                    option_type="CE",
                )

                spec_opt = InstrumentSpecification(
                    identity=InstrumentIdentity(
                        market="NSE",
                        instrument=resolved_symbol,
                        segment="options",
                        underlying=inst,
                        expiry=expiry_date,
                        strike=Decimal(str(resolved_strike)),
                        option_type="CE",
                    ),
                    effective_from=datetime(2020, 1, 1).date(),
                    price_increment=Decimal("0.05"),
                    contract_multiplier=Decimal("1"),
                    minimum_quantity=Decimal(str(lot_size)),
                    quantity_step=Decimal(str(lot_size)),
                    currency="INR",
                )
                account.register_specification(spec_opt)

                intended_position_key = PositionKey(
                    strategy_id=strategy_id,
                    strategy_version=strategy_version,
                    identity=spec_opt.identity,
                )

                candidate_plan = create_candidate_protective_plan(
                    intended_position_key=intended_position_key,
                    originating_timestamp=bar_dt,
                    timeframe=tf,
                    entry_price=opt_premium,
                    capital=account.starting_capital,
                    lot_size=lot_size,
                    per_trade_risk_pct=risk_policy.per_trade_risk_pct,
                    policy_version=policy_version,
                )
                risk_day = RiskDay("NSE_TRADING_DAYS", bar_dt.date())

                # Authoritative Pre-Order RiskGate evaluation (F-24)
                gate_res = risk_gate.evaluate_pre_order(
                    direction=PositionDirection.LONG,
                    intended_position_key=intended_position_key,
                    capital=account.starting_capital,
                    entry_price=opt_premium,
                    specification=spec_opt,
                    snapshot=account.snapshot,
                    book=session_protective_book,
                    candidate_plan=candidate_plan,
                    risk_day=risk_day,
                    current_net_equity=account.equity,
                    starting_capital=account.starting_capital,
                    prior_state=session_risk_state,
                )

                if gate_res.outcome is not RiskOutcome.APPROVED:
                    time_str = bar_dt.strftime("%H:%M:%S IST")
                    self._security_store.record_paper_event(
                        event_id=f"pe-{uuid.uuid4().hex[:8]}",
                        session_id=session_id,
                        event_time=time_str,
                        title="PAPER ORDER BLOCKED",
                        detail=f"Risk gate rejected: {gate_res.reason}. Order blocked.",
                        source="Risk Sentinel",
                        status="BLOCKED",
                        badge="RISK GATE REJECTED",
                    )
                    continue

                session_risk_state = gate_res.state
                approved_qty = gate_res.quantity or Decimal(str(lot_size))

                # Passed Risk Gate -> Record events
                time_str = bar_dt.strftime("%H:%M:%S IST")
                self._security_store.record_paper_event(
                    event_id=f"pe-{uuid.uuid4().hex[:8]}",
                    session_id=session_id,
                    event_time=time_str,
                    title="Signal Detected",
                    detail=f"Strategy '{strategy_name} {strategy_version}' triggered LONG entry signal on {tf} breakout.",
                    source=f"{strategy_name} {strategy_version}",
                    status="INFO",
                    badge="SIGNAL DETECTED",
                )
                self._security_store.record_paper_event(
                    event_id=f"pe-{uuid.uuid4().hex[:8]}",
                    session_id=session_id,
                    event_time=time_str,
                    title="Risk Gate Passed",
                    detail=f"Risk gate approved: quantity={int(approved_qty)}, stop={candidate_plan.stop_price}, target={candidate_plan.target_price}.",
                    source="Risk Sentinel",
                    status="PASS",
                    badge="GATE 1-4 PASSED",
                )

                # Construct Order
                intent = SignalIntent(
                    strategy_id=strategy_id,
                    strategy_version=strategy_version,
                    symbol=inst,
                    timeframe=tf,
                    originating_timestamp=bar_dt,
                    action="BUY",
                    confidence=float(getattr(sig, "confidence", 1.0)),
                    metadata=dict(getattr(sig, "metadata", {})),
                )
                order_req = OrderRequest(
                    source_intent=intent,
                    order_type=OrderType.MARKET,
                    quantity=approved_qty,
                    time_in_force=TimeInForce.DAY,
                )

                quote = QuoteSnapshot(
                    instrument_identity=spec_opt.identity,
                    exchange_timestamp=bar_dt,
                    bid_price=opt_premium - REPLAY_MODELED_SPREAD_HALF,
                    ask_price=opt_premium + REPLAY_MODELED_SPREAD_HALF,
                    last_price=opt_premium,
                    source="MODELED",
                )
                quote_event = BrokerQuoteEvent(
                    event_id=f"qe-{uuid.uuid4().hex[:8]}",
                    quote=quote,
                    authority_timestamp=bar_dt,
                )

                open_instruction = ConcreteOpenInstruction(
                    source_entry_order=order_req,
                    opening_action="BUY",
                    execution_symbol=resolved_symbol,
                )

                # Submit to broker
                sub_res = broker.submit(
                    open_instruction,
                    instrument_identity=spec_opt.identity,
                    specification=spec_opt,
                    submission_quote=quote,
                    submission_market_timestamp=bar_dt,
                )

                if sub_res.accepted and sub_res.order_id:
                    self._security_store.record_paper_event(
                        event_id=f"pe-{uuid.uuid4().hex[:8]}",
                        session_id=session_id,
                        event_time=time_str,
                        title="Paper Order Accepted",
                        detail=f"Buy Market {sub_res.order_id} placed for {resolved_symbol} @ ₹{float(opt_premium):.2f} ({int(approved_qty)} Qty).",
                        source="Order Blotter",
                        status="PASS",
                        badge="ORDER ACCEPTED",
                    )

                    # Process quote to fill order
                    terminal_events = broker.on_quote_event(quote_event)
                    for term in terminal_events:
                        if term.lifecycle_state == OrderLifecycleState.FILLED and term.execution_result:
                            fill_res = term.execution_result
                            account.on_broker_terminal_event(term, specification=spec_opt)

                            fill_price = float(fill_res.fill_price)
                            qty_int = int(approved_qty)
                            entry_cost = fill_price * qty_int

                            # Record entry fill in protective exit book (F-24)
                            exit_intent = SignalIntent(
                                action="EXIT",
                                confidence=1.0,
                                symbol=resolved_symbol,
                                timeframe=tf,
                                originating_timestamp=bar_dt,
                                strategy_id=strategy_id,
                                strategy_version=strategy_version,
                                metadata={},
                            )
                            exit_order = OrderRequest(
                                source_intent=exit_intent,
                                order_type=OrderType.STOP,
                                quantity=approved_qty,
                                time_in_force=TimeInForce.DAY,
                                stop_price=candidate_plan.stop_price,
                            )
                            p_exit = ProtectiveExit(
                                protective_id=f"prot-{uuid.uuid4().hex[:8]}",
                                position_key=intended_position_key,
                                exit_order=exit_order,
                                kind=ProtectiveExitKind.STOP_LOSS,
                                quantity=approved_qty,
                            )
                            session_protective_book.add(p_exit)

                            # Advance risk state trade count (F-24)
                            if session_risk_state is not None:
                                session_risk_state = session_risk_state.record_entry_fill(f"entry-{sub_res.order_id}")

                            # Record order
                            self._security_store.record_paper_order(
                                order_id=sub_res.order_id,
                                session_id=session_id,
                                instrument=resolved_symbol,
                                order_type="MARKET",
                                side="BUY",
                                qty=qty_int,
                                fill_price=fill_price,
                                status="FILLED",
                                filled_at_utc=bar_dt.isoformat(),
                            )

                            pos_id = f"pos-{uuid.uuid4().hex[:8]}"
                            self._security_store.record_paper_position(
                                position_id=pos_id,
                                session_id=session_id,
                                symbol=inst,
                                resolved_contract=resolved_symbol,
                                position_type="CE",
                                qty=qty_int,
                                avg_price=fill_price,
                                ltp=fill_price,
                                entry_cost=entry_cost,
                                current_value=entry_cost,
                                unrealized_pnl=0.0,
                                return_pct=0.0,
                                strategy_source=f"{strategy_name} ({strategy_version})",
                                policy_snapshot=policy_snapshot,
                                status="OPEN",
                                price_provenance="MODELED",
                            )

                            open_positions.append({
                                "position_id": pos_id,
                                "symbol": inst,
                                "resolved_contract": resolved_symbol,
                                "position_key": intended_position_key,
                                "spec": spec_opt,
                                "candidate_plan": candidate_plan,
                                "qty": qty_int,
                                "avg_price": fill_price,
                                "entry_cost": entry_cost,
                                "entry_spot": float(bar_close),
                            })

                            self._security_store.record_paper_event(
                                event_id=f"pe-{uuid.uuid4().hex[:8]}",
                                session_id=session_id,
                                event_time=time_str,
                                title="Simulated Fill Executed",
                                detail=(f"Order {sub_res.order_id} filled {qty_int} Qty @ ₹{fill_price:.2f} "
                                        f"(Zero Slippage Model; {REPLAY_PRICING_BASIS})."),
                                source="Paper Fill Engine",
                                status="PASS",
                                badge="ZERO SLIPPAGE",
                            )
                            self._security_store.record_paper_event(
                                event_id=f"pe-{uuid.uuid4().hex[:8]}",
                                session_id=session_id,
                                event_time=time_str,
                                title="Position Opened",
                                detail=f"{resolved_symbol}: {qty_int} Qty @ ₹{fill_price:.2f} (Committed: ₹{entry_cost:,.0f}).",
                                source="Portfolio Ledger",
                                status="PASS",
                                badge="SIMULATED FILL",
                            )

            # Signal: SELL / EXIT (Exit Long)
            elif sig_action in ("SELL", "EXIT") and open_positions:
                target_pos = open_positions.pop(0)
                time_str = bar_dt.strftime("%H:%M:%S IST")
                delta_spot = float(bar_close) - target_pos.get("entry_spot", float(bar_close))
                exit_price = max(REPLAY_PREMIUM_FLOOR,
                                 round(target_pos["avg_price"] + delta_spot * REPLAY_EXIT_DELTA_FACTOR, 2))
                trade_pnl = (exit_price - target_pos["avg_price"]) * target_pos["qty"]

                # Reconcile protective book (F-24)
                session_protective_book.reconcile_position(target_pos["position_key"], account.snapshot)

                # Close position
                self._security_store.record_paper_position(
                    position_id=target_pos["position_id"],
                    session_id=session_id,
                    symbol=target_pos["symbol"],
                    resolved_contract=target_pos["resolved_contract"],
                    position_type="CE",
                    qty=target_pos["qty"],
                    avg_price=target_pos["avg_price"],
                    ltp=exit_price,
                    entry_cost=target_pos["entry_cost"],
                    current_value=exit_price * target_pos["qty"],
                    unrealized_pnl=0.0,
                    return_pct=((exit_price - target_pos["avg_price"]) / target_pos["avg_price"]) * 100.0 if target_pos["avg_price"] > 0 else 0.0,
                    strategy_source=f"{strategy_name} ({strategy_version})",
                    policy_snapshot=policy_snapshot,
                    status="CLOSED",
                    price_provenance="MODELED",
                )

                close_order_id = f"ord-{uuid.uuid4().hex[:8]}"
                self._security_store.record_paper_order(
                    order_id=close_order_id,
                    session_id=session_id,
                    instrument=target_pos["resolved_contract"],
                    order_type="MARKET",
                    side="SELL",
                    qty=target_pos["qty"],
                    fill_price=exit_price,
                    status="FILLED",
                    filled_at_utc=bar_dt.isoformat(),
                )

                self._security_store.record_paper_event(
                    event_id=f"pe-{uuid.uuid4().hex[:8]}",
                    session_id=session_id,
                    event_time=time_str,
                    title="Position Closed",
                    detail=(f"Closed {target_pos['resolved_contract']}: {target_pos['qty']} Qty @ ₹{exit_price:.2f} "
                            f"(P&L: ₹{trade_pnl:+,.0f}; {REPLAY_PRICING_BASIS})."),
                    source="Portfolio Ledger",
                    status="PASS",
                    badge="POSITION CLOSED",
                )

        # Update remaining open positions with last market price
        latest_spot = float(replay_df.iloc[-1]["close"])
        persisted_positions = self._security_store.get_paper_positions(session_id)
        open_db_positions = [p for p in persisted_positions if p["status"] == "OPEN"]

        total_entry_cost = 0.0
        total_market_value = 0.0
        total_unrealized = 0.0

        for p in open_db_positions:
            entry_c = float(p["entry_cost"])
            mem_pos = next((op for op in open_positions if op["position_id"] == p["position_id"]), None)
            entry_spot = mem_pos.get("entry_spot", latest_spot) if mem_pos else latest_spot
            delta_spot = latest_spot - entry_spot
            ltp = max(REPLAY_PREMIUM_FLOOR,
                      round(p["avg_price"] + delta_spot * REPLAY_EXIT_DELTA_FACTOR, 2))

            cur_val = ltp * p["qty"]
            unreal = (ltp - p["avg_price"]) * p["qty"]
            ret_pct = ((ltp - p["avg_price"]) / p["avg_price"]) * 100 if p["avg_price"] > 0 else 0.0

            total_entry_cost += entry_c
            total_market_value += cur_val
            total_unrealized += unreal

            self._security_store.record_paper_position(
                position_id=p["position_id"],
                session_id=session_id,
                symbol=p["symbol"],
                resolved_contract=p["resolved_contract"],
                position_type=p["position_type"],
                qty=p["qty"],
                avg_price=p["avg_price"],
                ltp=ltp,
                entry_cost=entry_c,
                current_value=cur_val,
                unrealized_pnl=unreal,
                return_pct=ret_pct,
                strategy_source=p["strategy_source"],
                policy_snapshot=p.get("policy_snapshot", policy_snapshot),
                status="OPEN",
                price_provenance="MODELED",
            )

        # Calculate Accounting Metrics
        all_persisted = self._security_store.get_paper_positions(session_id)
        realized_pnl = round(float(sum((p["ltp"] - p["avg_price"]) * p["qty"] for p in all_persisted if p["status"] == "CLOSED")), 2)
        available_cash = initial_capital + realized_pnl - total_entry_cost
        current_equity = available_cash + total_market_value
        total_pnl = realized_pnl + total_unrealized
        return_pct = (total_pnl / initial_capital) * 100 if initial_capital > 0 else 0.0

        effective_date_range_json = json.dumps({"start": first_consumed_ts, "end": last_consumed_ts})

        updated_session = self._security_store.update_paper_session(
            session_id=session_id,
            status="ACTIVE",
            current_equity=round(current_equity, 2),
            available_cash=round(available_cash, 2),
            used_capital=round(total_entry_cost, 2),
            realized_pnl=round(realized_pnl, 2),
            unrealized_pnl=round(total_unrealized, 2),
            day_pnl=round(total_pnl, 2),
            total_pnl=round(total_pnl, 2),
            return_pct=round(return_pct, 2),
            trades_count=len(all_persisted),
            bars_consumed=total_bars,
            first_consumed_timestamp=first_consumed_ts,
            last_consumed_timestamp=last_consumed_ts,
            requested_date_range=requested_date_range,
            effective_date_range_json=effective_date_range_json,
            price_provenance="MODELED",
            risk_gate_status="ENFORCED",
        )

        return updated_session or session

    def _start_live_market_session(
        self,
        *,
        session: dict[str, Any],
        user_id: str,
        gov: dict[str, Any],
    ) -> dict[str, Any]:
        session_id = session["session_id"]
        # External Live Data Source Rule (NF-R203-04): per-user canonical
        # connection authority or an explicitly registered TEST-mode feed.
        # A process-global credential NEVER authorizes any user's session.
        has_test_feed = self._has_test_feed(session_id)
        has_canonical_authority = self._has_canonical_connection_authority(user_id)

        if not has_test_feed and not has_canonical_authority:
            now_ist = datetime.now(IST).strftime("%H:%M:%S IST")
            self._security_store.update_paper_session(
                session_id=session_id,
                status="FAILED",
                feed_status="DISCONNECTED",
                error_message="EXTERNAL LIVE DATA SOURCE REQUIRED: connect your own canonical broker connection (credential reference) before starting a live-market paper session.",
            )
            self._security_store.record_paper_event(
                event_id=f"pe-{uuid.uuid4().hex[:8]}",
                session_id=session_id,
                event_time=now_ist,
                title="EXTERNAL LIVE DATA SOURCE REQUIRED",
                detail="No usable canonical connection for this user. Add your own broker connection with a credential reference; process-global credentials never apply.",
                source="Paper Live Feed",
                status="BLOCKED",
                badge="CREDENTIALS REQUIRED",
            )
            raise ExternalLiveDataSourceRequiredError(
                "EXTERNAL LIVE DATA SOURCE REQUIRED: connect your own canonical broker connection (credential reference) before starting a live-market paper session."
            )

        inst = session["instrument"]
        tf = session["timeframe"]
        initial_capital = float(session["initial_capital"])
        strategy_id = session["strategy_id"]
        strategy_name = session["strategy_name"]
        strategy_version = session["strategy_version"]
        policy_snapshot = session["policy_snapshot"]

        lot_size = 50 if inst == "NIFTY" else 15
        spec = InstrumentSpecification(
            identity=InstrumentIdentity(market="NSE", instrument=inst, segment="INDEX"),
            effective_from=datetime(2026, 1, 1).date(),
            price_increment=Decimal("0.05"),
            contract_multiplier=Decimal(str(lot_size)),
            minimum_quantity=Decimal(str(lot_size)),
            quantity_step=Decimal(str(lot_size)),
            currency="INR",
        )

        portfolio_acc = PortfolioAccount(
            account_id=f"ACC_PAPER_{session_id}",
            currency="INR",
            starting_capital=Decimal(str(initial_capital)),
            monetary_quantum=Decimal("0.01"),
        )
        account = VirtualPaperAccount(
            portfolio_account=portfolio_acc,
            specifications={spec.identity: spec},
            require_opening_reservation=False,
        )

        fill_policy = PaperFillPolicy(
            slippage_model=FixedBasisPointsSlippage(0),
            max_execution_tolerance_bps=Decimal("50"),
            max_slippage_bps=Decimal("20"),
        )
        broker = SimulatedPaperBroker(adapter=PaperFillAdapter(fill_policy))
        quote_cache = LatestQuoteCache()
        strat_gen = self._resolve_paper_strategy_artifact(user_id, strategy_id, strategy_version)
        current_state = strat_gen.initial_state()

        # Build Authoritative Engine RiskPolicy and RiskGate (F-24)
        policy_details = session.get("policy_details") or {}
        policy_version = policy_details.get("risk_policy_version") or policy_details.get("version") or RISK_POLICY_VERSION_V3
        if policy_version not in SUPPORTED_RISK_POLICY_VERSIONS:
            raise InvalidPaperParameterError(f"Unsupported RiskPolicy version '{policy_version}'")

        risk_policy_kwargs: dict[str, Any] = {"version": policy_version}
        for k in ("per_trade_risk_pct", "max_daily_loss_pct", "max_daily_trades", "max_open_positions", "max_portfolio_risk_pct"):
            if k in policy_details:
                risk_policy_kwargs[k] = policy_details[k]
        risk_policy = RiskPolicy(**risk_policy_kwargs)
        risk_gate = RiskGate(risk_policy)
        session_protective_book = ProtectiveExitBook()

        self._live_contexts[session_id] = {
            "session_id": session_id,
            "user_id": user_id,
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "strategy_version": strategy_version,
            "instrument": inst,
            "timeframe": tf,
            "initial_capital": initial_capital,
            "policy_snapshot": policy_snapshot,
            "policy_details": policy_details,
            "policy_version": policy_version,
            "lot_size": lot_size,
            "spec": spec,
            "account": account,
            "broker": broker,
            "quote_cache": quote_cache,
            "strat_gen": strat_gen,
            "current_state": current_state,
            "feed_status": "CONNECTED",
            "last_market_timestamp": None,
            "last_quote_received_at": None,
            "quote_count": 0,
            "risk_policy": risk_policy,
            "risk_gate": risk_gate,
            "session_protective_book": session_protective_book,
            "session_risk_state": None,
            "open_positions": {},
        }

        updated = self._security_store.update_paper_session(
            session_id=session_id,
            status="ACTIVE",
            feed_status="CONNECTED",
            feed_source="TEST_FEED" if has_test_feed else "MANUAL_INGEST",
            error_message="",
            risk_gate_status="ENFORCED",
        )

        now_ist = datetime.now(IST).strftime("%H:%M:%S IST")
        self._security_store.record_paper_event(
            event_id=f"pe-{uuid.uuid4().hex[:8]}",
            session_id=session_id,
            event_time=now_ist,
            title="Live Market Feed Connected",
            detail=f"Live paper session active on {inst} ({tf}). SimulatedPaperBroker connected to live market stream.",
            source="Paper Live Feed",
            status="PASS",
            badge="LIVE CONNECTED",
        )

        return updated or session

    def process_live_quote(
        self,
        session_id: str,
        quote_event: LiveQuoteEvent,
        *,
        allow_stale_for_testing: bool = False,
    ) -> dict[str, Any]:
        """Process an incoming LiveQuoteEvent for an active LIVE_MARKET session."""
        ctx = self._live_contexts.get(session_id)
        if not ctx:
            ses = self._security_store.get_paper_session(session_id)
            if not ses:
                raise PaperSessionNotFoundError(f"Paper session '{session_id}' not found")
            if ses.get("status") != "ACTIVE":
                raise InvalidPaperParameterError(f"Paper session '{session_id}' is not ACTIVE (status: {ses.get('status')})")
            if ses.get("data_source_mode") != "LIVE_MARKET":
                raise InvalidPaperParameterError(f"Paper session '{session_id}' is not in LIVE_MARKET mode")
            # Auto-reattach active session on demand
            try:
                self.reattach_live_session(session_id)
                ctx = self._live_contexts.get(session_id)
            except Exception as exc:
                raise InvalidPaperParameterError(f"Session '{session_id}' reattach failed: {exc}") from exc
            if not ctx:
                raise InvalidPaperParameterError(f"Session '{session_id}' runtime context not active")

        # Duplicate event ID check
        known_events = ctx.setdefault("known_event_ids", set())
        if quote_event.event_id in known_events:
            return self._security_store.get_paper_session(session_id) or {}
        known_events.add(quote_event.event_id)
        try:
            self._security_store.record_paper_quote_event_id(session_id, quote_event.event_id)
        except Exception as exc:
            logger.warning("Could not persist quote event id for %s: %s", session_id, exc)

        # Transition WAITING_FOR_MARKET_DATA / PROVIDER_UNAVAILABLE to CONNECTED
        # upon receiving live quotes (genuine provider data, never invented).
        if ctx.get("feed_status") in ("WAITING_FOR_MARKET_DATA", "PROVIDER_UNAVAILABLE"):
            ctx["feed_status"] = "CONNECTED"
            self._security_store.update_paper_session(session_id, feed_status="CONNECTED")

        now_ist = datetime.now(IST).strftime("%H:%M:%S IST")
        inst = ctx["instrument"]
        quote = quote_event.quote
        q_ident = quote.instrument_identity

        # Monotonic timestamp check against last accepted market timestamp
        if ctx.get("last_market_timestamp") is not None:
            last_ts = ctx["last_market_timestamp"]
            q_ts = quote.exchange_timestamp
            if getattr(last_ts, "tzinfo", None) is None:
                last_ts = last_ts.replace(tzinfo=UTC)
            if getattr(q_ts, "tzinfo", None) is None:
                q_ts = q_ts.replace(tzinfo=UTC)
            if q_ts <= last_ts:
                self._security_store.record_paper_event(
                    event_id=f"pe-{uuid.uuid4().hex[:8]}",
                    session_id=session_id,
                    event_time=now_ist,
                    title="OUT OF ORDER QUOTE REJECTED",
                    detail=f"Quote timestamp {quote.exchange_timestamp.isoformat()} rejected by monotonic ordering guard (prior: {last_ts.isoformat()}).",
                    source="Quote Cache",
                    status="BLOCKED",
                    badge="OUT OF ORDER",
                )
                raise OutOfOrderQuoteError(f"Out of order exchange timestamp {quote.exchange_timestamp}")

        # 1. Connection check (Fail-Closed)
        if ctx["feed_status"] in ("DISCONNECTED", "RECONNECTING"):
            self._security_store.record_paper_event(
                event_id=f"pe-{uuid.uuid4().hex[:8]}",
                session_id=session_id,
                event_time=now_ist,
                title="PAPER ORDER BLOCKED",
                detail=f"Feed not connected: feed status is {ctx['feed_status']}. Ingress rejected fail-closed.",
                source="Live Market Feed",
                status="BLOCKED",
                badge="FEED NOT CONNECTED",
            )
            raise FeedNotConnectedError(f"Feed is not connected (status: {ctx['feed_status']})")

        # 2. Instrument check
        is_index = (q_ident.instrument == inst or (q_ident.underlying == inst and q_ident.segment in ("INDEX", "EQUITY")))
        is_derivative = (q_ident.underlying == inst or q_ident.instrument.startswith(inst))
        if not is_index and not is_derivative:
            self._security_store.record_paper_event(
                event_id=f"pe-{uuid.uuid4().hex[:8]}",
                session_id=session_id,
                event_time=now_ist,
                title="WRONG INSTRUMENT REJECTED",
                detail=f"Quote instrument {q_ident.instrument} does not match session instrument {inst}.",
                source="Live Market Feed",
                status="BLOCKED",
                badge="WRONG INSTRUMENT",
            )
            raise WrongInstrumentError(f"Quote instrument {q_ident.instrument} does not match {inst}")

        # 3. Freshness / Staleness check
        age_seconds = (datetime.now(UTC) - quote.exchange_timestamp.astimezone(UTC)).total_seconds()
        is_stale = (age_seconds > 10.0 and not allow_stale_for_testing) or getattr(quote, "is_stale", False)
        if is_stale:
            ctx["feed_status"] = "STALE"
            self._security_store.update_paper_session(session_id, feed_status="STALE")
            self._security_store.record_paper_event(
                event_id=f"pe-{uuid.uuid4().hex[:8]}",
                session_id=session_id,
                event_time=now_ist,
                title="STALE QUOTE REJECTED",
                detail=f"Incoming quote marked as stale (> 10.0s age: {age_seconds:.1f}s). Order placement blocked fail-closed.",
                source="Risk Sentinel",
                status="BLOCKED",
                badge="STALE DATA",
            )
            raise StaleQuoteError(f"Quote is stale (> 10.0s age: {age_seconds:.1f}s)")

        # 4. Ingest into LatestQuoteCache (Monotonic ordering & conflict detection)
        cache_res = ctx["quote_cache"].on_quote_event(quote_event)

        if cache_res.status == QuoteCacheStatus.OUT_OF_ORDER_REJECTED:
            self._security_store.record_paper_event(
                event_id=f"pe-{uuid.uuid4().hex[:8]}",
                session_id=session_id,
                event_time=now_ist,
                title="OUT OF ORDER QUOTE REJECTED",
                detail=f"Quote timestamp {quote.exchange_timestamp.isoformat()} rejected by monotonic ordering guard.",
                source="Quote Cache",
                status="BLOCKED",
                badge="OUT OF ORDER",
            )
            raise OutOfOrderQuoteError(f"Out of order exchange timestamp {quote.exchange_timestamp}")

        if cache_res.status in (
            QuoteCacheStatus.AMBIGUOUS_CONFLICT_REJECTED,
            QuoteCacheStatus.CONFLICTED_TIMESTAMP_REJECTED,
            QuoteCacheStatus.REUSED_EVENT_ID_CONFLICT_REJECTED,
        ):
            self._security_store.record_paper_event(
                event_id=f"pe-{uuid.uuid4().hex[:8]}",
                session_id=session_id,
                event_time=now_ist,
                title="AMBIGUOUS QUOTE CONFLICT REJECTED",
                detail="Conflicting quote detected at same timestamp or reused event ID. Cache placed into fail-closed state.",
                source="Quote Cache",
                status="BLOCKED",
                badge="AMBIGUOUS CONFLICT",
            )
            return self._security_store.get_paper_session(session_id) or {}

        if cache_res.status == QuoteCacheStatus.DUPLICATE_IGNORED:
            return self._security_store.get_paper_session(session_id) or {}

        # 5. Accepted quote processing
        ctx["last_market_timestamp"] = quote.exchange_timestamp
        ctx["last_quote_received_at"] = datetime.now(UTC)
        ctx["quote_count"] += 1

        if is_index:
            self._handle_live_underlying_quote(ctx=ctx, quote_event=quote_event)
        else:
            self._handle_live_option_quote(ctx=ctx, quote_event=quote_event)

        updated = self._security_store.update_paper_session(
            session_id=session_id,
            feed_status=ctx["feed_status"],
            last_market_timestamp=quote.exchange_timestamp.isoformat(),
            last_quote_received_at=datetime.now(UTC).isoformat(),
            live_quote_count=ctx["quote_count"],
        )
        return updated or {}

    def _handle_live_underlying_quote(
        self,
        *,
        ctx: dict[str, Any],
        quote_event: LiveQuoteEvent,
    ) -> None:
        session_id = ctx["session_id"]
        quote = quote_event.quote
        spot_price = float(quote.last_price)
        inst = ctx["instrument"]
        now_ist = quote.exchange_timestamp.strftime("%H:%M:%S IST")

        bar_series = pd.Series({
            "open": spot_price,
            "high": spot_price,
            "low": spot_price,
            "close": spot_price,
            "volume": 1000.0,
        })
        try:
            sig = ctx["strat_gen"].generate_signal(bar_series, ctx["current_state"])
        except Exception as exc:
            logger.warning("Live strategy evaluation error: %s", exc)
            return

        sig_action = getattr(sig, "action", getattr(sig, "value", None))

        if sig_action == "BUY":
            policy_details = ctx.get("policy_details") or {}
            policy_mode = policy_details.get("mode", "OTM")
            policy_distance = policy_details.get("distance", 1)
            resolved_strike = resolve_option_strike(
                spot_price,
                inst,
                option_type="CE",
                moneyness_mode=policy_mode,
                moneyness_distance=policy_distance,
            )

            # NF-10: exact contract resolution only. The requested strike /
            # direction / underlying must resolve to exactly one live-quoted
            # contract. Any silent substitution of another cached/previous
            # contract (different strike or expiry) is prohibited: it fails
            # closed below instead of executing against the wrong contract.
            matches: list[tuple[Any, Any]] = []
            contract_symbol = None
            for cached_ident, q in getattr(ctx["quote_cache"], "_valid_quotes", {}).items():
                if (
                    getattr(cached_ident, "strike", None) == resolved_strike
                    and getattr(cached_ident, "option_type", None) == "CE"
                    and (getattr(cached_ident, "underlying", None) == inst or cached_ident.instrument.startswith(inst))
                ) or (f"{resolved_strike}CE" in cached_ident.instrument and cached_ident.instrument.startswith(inst)):
                    matches.append((cached_ident, q))
            distinct_contracts = {m[0].instrument for m in matches}

            if not contract_symbol:
                expiry_date = resolve_nearest_weekly_expiry(quote.exchange_timestamp.date())
                contract_symbol = f"{inst}{expiry_date.strftime('%y%m%d')}{resolved_strike}CE"

            self._security_store.record_paper_event(
                event_id=f"pe-{uuid.uuid4().hex[:8]}",
                session_id=session_id,
                event_time=now_ist,
                title="Signal Detected",
                detail=f"Strategy '{ctx['strategy_name']}' signaled LONG entry on {inst} @ ₹{spot_price:.2f}. Target contract: {contract_symbol}.",
                source=f"{ctx['strategy_name']} {ctx['strategy_version']}",
                status="INFO",
                badge="SIGNAL DETECTED",
            )

            # CRITICAL GOVERNANCE INVARIANT (NF-10):
            # Exactly one live-quoted contract must match. Zero matches,
            # ambiguous matches, expired contracts, or contracts with
            # unprovable expiry all fail closed. Synthetic fallback is
            # strictly prohibited in LIVE_MARKET mode.
            real_opt_quote = None
            opt_identity = None
            block_detail = (
                f"No live exchange quote for contract {contract_symbol} in quote cache. "
                "Paper order blocked fail-closed. Synthetic fallback strictly prohibited in LIVE_MARKET mode."
            )
            if len(distinct_contracts) > 1:
                block_detail = (
                    f"Ambiguous contract resolution for strike {resolved_strike}: "
                    f"{sorted(distinct_contracts)}. Paper order blocked fail-closed."
                )
            elif len(matches) == 1:
                cached_ident, q = matches[0]
                as_of = quote.exchange_timestamp.date()
                expiry = getattr(cached_ident, "expiry", None)
                if expiry is not None and expiry < as_of:
                    block_detail = (
                        f"Matched contract {cached_ident.instrument} expired on {expiry} "
                        f"(as of {as_of}). Paper order blocked fail-closed."
                    )
                elif expiry is None:
                    block_detail = (
                        f"Matched contract {cached_ident.instrument} has no provable expiry. "
                        "Paper order blocked fail-closed."
                    )
                else:
                    real_opt_quote = q
                    opt_identity = cached_ident
                    contract_symbol = cached_ident.instrument
            if real_opt_quote is None or opt_identity is None:
                # FAIL CLOSED! NEVER fabricate synthetic price in LIVE_MARKET!
                self._security_store.record_paper_event(
                    event_id=f"pe-{uuid.uuid4().hex[:8]}",
                    session_id=session_id,
                    event_time=now_ist,
                    title="LIVE OPTION QUOTE AUTHORITY UNAVAILABLE",
                    detail=block_detail,
                    source="Option Quote Authority",
                    status="BLOCKED",
                    badge="AUTHORITY UNAVAILABLE",
                )
                return

            lot_size = ctx["lot_size"]
            opt_premium = real_opt_quote.last_price

            spec_opt = InstrumentSpecification(
                identity=opt_identity,
                effective_from=datetime(2020, 1, 1).date(),
                price_increment=Decimal("0.05"),
                contract_multiplier=Decimal("1"),
                minimum_quantity=Decimal(str(lot_size)),
                quantity_step=Decimal(str(lot_size)),
                currency="INR",
            )
            ctx["account"].register_specification(spec_opt)

            intended_position_key = PositionKey(
                strategy_id=ctx["strategy_id"],
                strategy_version=ctx["strategy_version"],
                identity=opt_identity,
            )

            candidate_plan = create_candidate_protective_plan(
                intended_position_key=intended_position_key,
                originating_timestamp=quote.exchange_timestamp,
                timeframe=ctx["timeframe"],
                entry_price=opt_premium,
                capital=ctx["account"].starting_capital,
                lot_size=lot_size,
                per_trade_risk_pct=ctx["risk_policy"].per_trade_risk_pct,
                policy_version=ctx["policy_version"],
            )
            risk_day = RiskDay("NSE_TRADING_DAYS", quote.exchange_timestamp.date())

            # Authoritative Pre-Order RiskGate evaluation (F-24)
            gate_res = ctx["risk_gate"].evaluate_pre_order(
                direction=PositionDirection.LONG,
                intended_position_key=intended_position_key,
                capital=ctx["account"].starting_capital,
                entry_price=opt_premium,
                specification=spec_opt,
                snapshot=ctx["account"].snapshot,
                book=ctx["session_protective_book"],
                candidate_plan=candidate_plan,
                risk_day=risk_day,
                current_net_equity=ctx["account"].equity,
                starting_capital=ctx["account"].starting_capital,
                prior_state=ctx["session_risk_state"],
            )

            if gate_res.outcome is not RiskOutcome.APPROVED:
                self._security_store.record_paper_event(
                    event_id=f"pe-{uuid.uuid4().hex[:8]}",
                    session_id=session_id,
                    event_time=now_ist,
                    title="PAPER ORDER BLOCKED",
                    detail=f"Risk gate rejected: {gate_res.reason}. Order blocked.",
                    source="Risk Sentinel",
                    status="BLOCKED",
                    badge="RISK GATE REJECTED",
                )
                return

            ctx["session_risk_state"] = gate_res.state
            approved_qty = gate_res.quantity or Decimal(str(lot_size))

            self._security_store.record_paper_event(
                event_id=f"pe-{uuid.uuid4().hex[:8]}",
                session_id=session_id,
                event_time=now_ist,
                title="Risk Gate Passed",
                detail=f"Risk gate approved: quantity={int(approved_qty)}, stop={candidate_plan.stop_price}, target={candidate_plan.target_price}. Contract quote authority confirmed.",
                source="Risk Sentinel",
                status="PASS",
                badge="RISK GATE PASSED",
            )

            intent = SignalIntent(
                strategy_id=ctx["strategy_id"],
                strategy_version=ctx["strategy_version"],
                symbol=inst,
                timeframe=ctx["timeframe"],
                originating_timestamp=quote.exchange_timestamp,
                action="BUY",
                confidence=float(getattr(sig, "confidence", 1.0)),
                metadata=dict(getattr(sig, "metadata", {})),
            )
            order_req = OrderRequest(
                source_intent=intent,
                order_type=OrderType.MARKET,
                quantity=approved_qty,
                time_in_force=TimeInForce.DAY,
            )
            open_instruction = ConcreteOpenInstruction(
                source_entry_order=order_req,
                opening_action="BUY",
                execution_symbol=contract_symbol,
            )
            sub_res = ctx["broker"].submit(
                open_instruction,
                instrument_identity=opt_identity,
                specification=spec_opt,
                submission_quote=real_opt_quote,
                submission_market_timestamp=real_opt_quote.exchange_timestamp,
            )

            if sub_res.accepted and sub_res.order_id:
                self._security_store.record_paper_event(
                    event_id=f"pe-{uuid.uuid4().hex[:8]}",
                    session_id=session_id,
                    event_time=now_ist,
                    title="Paper Order Accepted",
                    detail=f"Buy Market {sub_res.order_id} placed for {contract_symbol} @ ₹{float(opt_premium):.2f} ({int(approved_qty)} Qty).",
                    source="Order Blotter",
                    status="PASS",
                    badge="ORDER ACCEPTED",
                )

                quote_event_opt = BrokerQuoteEvent(
                    event_id=f"qe-{uuid.uuid4().hex[:8]}",
                    quote=real_opt_quote,
                    authority_timestamp=real_opt_quote.exchange_timestamp,
                )
                term_events = ctx["broker"].on_quote_event(quote_event_opt)
                for term in term_events:
                    if term.lifecycle_state == OrderLifecycleState.FILLED and term.execution_result:
                        fill_res = term.execution_result
                        ctx["account"].on_broker_terminal_event(term, specification=spec_opt)
                        fill_price = float(fill_res.fill_price)
                        qty_int = int(approved_qty)
                        entry_cost = fill_price * qty_int

                        # Record protective exit (F-24)
                        exit_intent = SignalIntent(
                            action="EXIT",
                            confidence=1.0,
                            symbol=contract_symbol,
                            timeframe=ctx["timeframe"],
                            originating_timestamp=quote.exchange_timestamp,
                            strategy_id=ctx["strategy_id"],
                            strategy_version=ctx["strategy_version"],
                            metadata={},
                        )
                        exit_order = OrderRequest(
                            source_intent=exit_intent,
                            order_type=OrderType.STOP,
                            quantity=approved_qty,
                            time_in_force=TimeInForce.DAY,
                            stop_price=candidate_plan.stop_price,
                        )
                        p_exit = ProtectiveExit(
                            protective_id=f"prot-{uuid.uuid4().hex[:8]}",
                            position_key=intended_position_key,
                            exit_order=exit_order,
                            kind=ProtectiveExitKind.STOP_LOSS,
                            quantity=approved_qty,
                        )
                        ctx["session_protective_book"].add(p_exit)

                        # Advance risk state trade count (F-24)
                        if ctx["session_risk_state"] is not None:
                            ctx["session_risk_state"] = ctx["session_risk_state"].record_entry_fill(f"entry-{sub_res.order_id}")

                        self._security_store.record_paper_order(
                            order_id=sub_res.order_id,
                            session_id=session_id,
                            instrument=contract_symbol,
                            order_type="MARKET",
                            side="BUY",
                            qty=qty_int,
                            fill_price=fill_price,
                            status="FILLED",
                            filled_at_utc=quote.exchange_timestamp.isoformat(),
                        )

                        pos_id = f"pos-{uuid.uuid4().hex[:8]}"
                        self._security_store.record_paper_position(
                            position_id=pos_id,
                            session_id=session_id,
                            symbol=inst,
                            resolved_contract=contract_symbol,
                            position_type="CE",
                            qty=qty_int,
                            avg_price=fill_price,
                            ltp=fill_price,
                            entry_cost=entry_cost,
                            current_value=entry_cost,
                            unrealized_pnl=0.0,
                            return_pct=0.0,
                            strategy_source=f"{ctx['strategy_name']} ({ctx['strategy_version']})",
                            policy_snapshot=ctx["policy_snapshot"],
                            status="OPEN",
                            price_provenance="ACTUAL",
                        )

                        ctx["open_positions"][contract_symbol] = {
                            "position_id": pos_id,
                            "symbol": inst,
                            "resolved_contract": contract_symbol,
                            "position_key": intended_position_key,
                            "qty": qty_int,
                            "avg_price": fill_price,
                            "entry_cost": entry_cost,
                            "identity": opt_identity,
                            "spec": spec_opt,
                        }

                        self._security_store.record_paper_event(
                            event_id=f"pe-{uuid.uuid4().hex[:8]}",
                            session_id=session_id,
                            event_time=now_ist,
                            title="Simulated Fill Executed",
                            detail=f"Order {sub_res.order_id} filled {qty_int} Qty @ ₹{fill_price:.2f} using real live market option quote.",
                            source="Paper Fill Engine",
                            status="PASS",
                            badge="LIVE FILL",
                        )
                        self._recalculate_live_metrics(ctx)

        elif sig_action in ("SELL", "EXIT") and ctx["open_positions"]:
            contract_symbol, pos_info = next(iter(ctx["open_positions"].items()))
            del ctx["open_positions"][contract_symbol]

            opt_quote = ctx["quote_cache"].get(pos_info["identity"])
            exit_price = float(opt_quote.last_price) if opt_quote else pos_info["avg_price"]
            trade_pnl = (exit_price - pos_info["avg_price"]) * pos_info["qty"]

            # Reconcile protective book (F-24)
            ctx["session_protective_book"].reconcile_position(pos_info["position_key"], ctx["account"].snapshot)

            self._security_store.record_paper_position(
                position_id=pos_info["position_id"],
                session_id=session_id,
                symbol=pos_info["symbol"],
                resolved_contract=pos_info["resolved_contract"],
                position_type="CE",
                qty=pos_info["qty"],
                avg_price=pos_info["avg_price"],
                ltp=exit_price,
                entry_cost=pos_info["entry_cost"],
                current_value=exit_price * pos_info["qty"],
                unrealized_pnl=0.0,
                return_pct=((exit_price - pos_info["avg_price"]) / pos_info["avg_price"]) * 100.0 if pos_info["avg_price"] > 0 else 0.0,
                strategy_source=f"{ctx['strategy_name']} ({ctx['strategy_version']})",
                policy_snapshot=ctx["policy_snapshot"],
                status="CLOSED",
                price_provenance="ACTUAL",
            )

            close_order_id = f"ord-{uuid.uuid4().hex[:8]}"
            self._security_store.record_paper_order(
                order_id=close_order_id,
                session_id=session_id,
                instrument=pos_info["resolved_contract"],
                order_type="MARKET",
                side="SELL",
                qty=pos_info["qty"],
                fill_price=exit_price,
                status="FILLED",
                filled_at_utc=quote.exchange_timestamp.isoformat(),
            )

            self._security_store.record_paper_event(
                event_id=f"pe-{uuid.uuid4().hex[:8]}",
                session_id=session_id,
                event_time=now_ist,
                title="Position Closed",
                detail=f"Closed {pos_info['resolved_contract']}: {pos_info['qty']} Qty @ ₹{exit_price:.2f} (P&L: ₹{trade_pnl:+,.0f}).",
                source="Portfolio Ledger",
                status="PASS",
                badge="POSITION CLOSED",
            )
            self._recalculate_live_metrics(ctx)

    def _handle_live_option_quote(
        self,
        *,
        ctx: dict[str, Any],
        quote_event: LiveQuoteEvent,
    ) -> None:
        quote = quote_event.quote
        contract_symbol = quote.instrument_identity.instrument
        ltp = float(quote.last_price)

        if contract_symbol in ctx["open_positions"]:
            pos_info = ctx["open_positions"][contract_symbol]
            qty = pos_info["qty"]
            avg_price = pos_info["avg_price"]
            entry_cost = pos_info["entry_cost"]
            cur_val = ltp * qty
            unreal = (ltp - avg_price) * qty
            ret_pct = ((ltp - avg_price) / avg_price) * 100.0 if avg_price > 0 else 0.0

            self._security_store.record_paper_position(
                position_id=pos_info["position_id"],
                session_id=ctx["session_id"],
                symbol=pos_info["symbol"],
                resolved_contract=contract_symbol,
                position_type="CE",
                qty=qty,
                avg_price=avg_price,
                ltp=ltp,
                entry_cost=entry_cost,
                current_value=cur_val,
                unrealized_pnl=unreal,
                return_pct=ret_pct,
                strategy_source=f"{ctx['strategy_name']} ({ctx['strategy_version']})",
                policy_snapshot=ctx["policy_snapshot"],
                status="OPEN",
                price_provenance="ACTUAL",
            )
            self._recalculate_live_metrics(ctx)

    def _recalculate_live_metrics(self, ctx: dict[str, Any]) -> None:
        session_id = ctx["session_id"]
        positions = self._security_store.get_paper_positions(session_id)
        open_pos = [p for p in positions if p["status"] == "OPEN"]
        closed_pos = [p for p in positions if p["status"] == "CLOSED"]

        realized_pnl = round(float(sum((p["ltp"] - p["avg_price"]) * p["qty"] for p in closed_pos)), 2)
        total_entry_cost = sum(p["entry_cost"] for p in open_pos)
        total_market_val = sum(p["current_value"] for p in open_pos)
        total_unrealized = round(float(sum(p["unrealized_pnl"] for p in open_pos)), 2)

        initial_capital = ctx["initial_capital"]
        available_cash = round(initial_capital + realized_pnl - total_entry_cost, 2)
        current_equity = round(available_cash + total_market_val, 2)
        total_pnl = round(realized_pnl + total_unrealized, 2)
        return_pct = round((total_pnl / initial_capital) * 100.0, 2) if initial_capital > 0 else 0.0

        self._security_store.update_paper_session(
            session_id=session_id,
            current_equity=current_equity,
            available_cash=available_cash,
            used_capital=round(total_entry_cost, 2),
            realized_pnl=realized_pnl,
            unrealized_pnl=total_unrealized,
            day_pnl=total_pnl,
            total_pnl=total_pnl,
            return_pct=return_pct,
            trades_count=len(positions),
        )

    def set_live_feed_state(self, session_id: str, state: str | FeedConnectionState) -> dict[str, Any]:
        """Update the connection state of the live feed for a session."""
        st = state.value if isinstance(state, FeedConnectionState) else str(state).upper()
        # F-11 truthful provider states: WAITING_FOR_MARKET_DATA and
        # PROVIDER_UNAVAILABLE describe the provider, never invented data.
        if st not in ("CONNECTED", "RECONNECTING", "STALE", "DISCONNECTED", "ERROR",
                      "WAITING_FOR_MARKET_DATA", "PROVIDER_UNAVAILABLE"):
            raise ValueError(f"Invalid feed state '{state}'")

        ctx = self._live_contexts.get(session_id)
        if ctx:
            ctx["feed_status"] = st

        now_ist = datetime.now(IST).strftime("%H:%M:%S IST")
        self._security_store.record_paper_event(
            event_id=f"pe-{uuid.uuid4().hex[:8]}",
            session_id=session_id,
            event_time=now_ist,
            title=f"Feed State Changed: {st}",
            detail=f"Live feed connection transitioned to {st}.",
            source="Feed Supervisor",
            status="INFO" if st in ("CONNECTED", "RECONNECTING") else "BLOCKED",
            badge=f"FEED {st}",
        )
        updated = self._security_store.update_paper_session(session_id, feed_status=st)
        return updated or {}

    def _has_test_feed(self, session_id: str | None) -> bool:
        return bool(self._test_feed_mode) and session_id in self._test_feeds

    def _has_canonical_connection_authority(self, user_id: str | None) -> bool:
        """Per-user live-feed authority (NF-R203-04): the session owner's own
        usable canonical user_connections record. Fail closed on missing,
        ambiguous, unusable, or provider-less authority. Never consults any
        process-global credential."""
        if not user_id:
            return False
        try:
            return self._security_store.get_operational_connection(user_id) is not None
        except Exception:
            return False

    def register_test_live_feed(self, session_id: str, feed: Any) -> None:
        """Register a test live feed for testing/simulation purposes.

        Explicit TEST-mode isolation: raises unless the service was
        constructed with test_feed_mode=True."""
        if not self._test_feed_mode:
            raise InvalidPaperParameterError(
                "TEST_FEED_NOT_ENABLED: test live-feed injection requires explicit test_feed_mode")
        self._test_feeds[session_id] = feed

    def inject_live_quote_for_testing(
        self,
        session_id: str,
        quote: QuoteSnapshot,
        event_id: str | None = None,
        allow_stale: bool = False,
    ) -> dict[str, Any]:
        """Convenience method for tests to inject a live quote.

        Explicit TEST-mode isolation: raises unless the service was
        constructed with test_feed_mode=True."""
        if not self._test_feed_mode:
            raise InvalidPaperParameterError(
                "TEST_FEED_NOT_ENABLED: test live-quote injection requires explicit test_feed_mode")
        ev_id = event_id or f"lqe-{uuid.uuid4().hex[:8]}"
        quote_ev = LiveQuoteEvent(event_id=ev_id, quote=quote)
        return self.process_live_quote(session_id, quote_ev, allow_stale_for_testing=allow_stale)

    def stop_session(
        self,
        session_id: str,
        *,
        user_id: str,
    ) -> dict[str, Any]:
        """Stop an active paper trading session."""
        session = self._security_store.get_paper_session(session_id, user_id=user_id)
        if not session:
            raise PaperSessionNotFoundError(f"Paper session '{session_id}' not found or access denied")

        if session.get("status") == "STOPPED":
            return session

        now_str = datetime.now(UTC).isoformat()
        now_ist = datetime.now(IST).strftime("%H:%M:%S IST")

        if session_id in self._live_contexts:
            self._live_contexts[session_id]["feed_status"] = "DISCONNECTED"
            del self._live_contexts[session_id]

        updated = self._security_store.update_paper_session(
            session_id=session_id,
            status="STOPPED",
            feed_status="DISCONNECTED",
            stopped_at_utc=now_str,
        )

        self._security_store.record_paper_event(
            event_id=f"pe-{uuid.uuid4().hex[:8]}",
            session_id=session_id,
            event_time=now_ist,
            title="Paper Session Stopped",
            detail=f"Session {session_id} stopped by user. Forward execution halted.",
            source="Paper Desk",
            status="INFO",
            badge="STOPPED",
        )

        return updated or session

    def get_session(self, session_id: str, *, user_id: str | None = None) -> dict[str, Any] | None:
        return self._security_store.get_paper_session(session_id, user_id=user_id)

    def list_sessions(self, *, user_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        return self._security_store.list_paper_sessions(user_id=user_id, limit=limit)

    def get_positions(self, session_id: str, *, user_id: str | None = None) -> list[dict[str, Any]]:
        return self._security_store.get_paper_positions(session_id, user_id=user_id)

    def get_orders(self, session_id: str, *, user_id: str | None = None) -> list[dict[str, Any]]:
        return self._security_store.get_paper_orders(session_id, user_id=user_id)

    def get_events(self, session_id: str, *, user_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        return self._security_store.get_paper_events(session_id, user_id=user_id, limit=limit)

    def set_session_hold(self, session_id: str, hold: bool, reason: str | None = None) -> bool:
        return self._security_store.set_paper_session_hold(session_id, hold=hold, reason=reason)

    def _resolve_paper_strategy_artifact(
        self,
        user_id: str,
        strategy_id: str,
        version_id: str | None = None,
    ) -> BoundedStrategy:
        """Resolve the exact registered strategy artifact for paper execution.
        
        This mirrors the backtest_service's resolve_registered_artifact but checks
        PAPER_ELIGIBLE stage instead of BACKTEST_ELIGIBLE.
        
        Fail-closed on any governance, artifact, or hash verification failure.
        """
        if self._governance_store is None or self._artifact_root is None:
            raise GovernanceRejectionError("Registered artifact authority unavailable for paper execution")
        
        registered = self._security_store.get_owner_strategy(strategy_id)
        if not registered or registered["strategyId"] != strategy_id:
            raise GovernanceRejectionError(f"Strategy '{strategy_id}' not registered")
        
        admin_status = registered.get("adminStatus") or registered.get("admin_status") or "ACTIVE"
        if admin_status != "ACTIVE":
            raise GovernanceRejectionError(f"Strategy '{strategy_id}' is {admin_status} under Owner governance")
        
        paper_allowance = (
            registered.get("governance", {}).get("paper", {}).get("ownerAllowance")
            or registered.get("paper_owner_allowance")
            or "ALLOWED"
        )
        if paper_allowance != "ALLOWED":
            hold_reason = (
                registered.get("governance", {}).get("paper", {}).get("ownerHoldReason")
                or registered.get("paper_owner_hold_reason")
                or "Owner execution hold active"
            )
            raise GovernanceRejectionError(f"Strategy '{strategy_id}' paper execution is on {paper_allowance}: {hold_reason}")
        
        from uuid import UUID
        import hashlib
        
        rows = self._governance_store._conn.execute("SELECT * FROM strategy_versions WHERE strategy_id = ?", (strategy_id,)).fetchall()
        if version_id is not None:
            rows = [r for r in rows if r["version_id"] == version_id]
        if len(rows) != 1:
            raise GovernanceRejectionError("Exact registered strategy version required for paper execution")
        
        row = rows[0]
        if row["owner_id"] != user_id:
            has_assignment = False
            if hasattr(self._security_store, "get_strategy_assignment"):
                asgn = self._security_store.get_strategy_assignment(user_id, strategy_id)
                has_assignment = asgn is not None and asgn.get("assignment_status") == "ASSIGNED"
            if not has_assignment:
                # Explicit global catalog strategies are executable by any
                # active user (per-user session/account state stays isolated).
                visible = (registered.get("visibility") or "OWNER_PRIVATE") == "GLOBAL"
                if not visible:
                    raise GovernanceRejectionError("Cross-user strategy execution denied")
        
        if row["archived"]:
            raise GovernanceRejectionError("Strategy version is archived")

        if registered["version"] != row["version_id"]:
            raise GovernanceRejectionError("Governance version mismatch")

        # P1-A (R-03): self-service paper eligibility. REGISTERED + VALIDATED +
        # ACTIVE + ASSIGNED strategies may paper-trade subject to automatic
        # safety checks; Owner stage promotion (PAPER_ELIGIBLE) is no longer
        # required for ordinary paper workflows. Suspended / revoked / held
        # strategies still fail closed here; artifact integrity is verified below.
        # LIVE real-money eligibility remains under separate Owner governance.
        elig_fn = getattr(self._security_store, "check_self_service_paper_eligibility", None)
        if elig_fn is not None:
            elig = elig_fn(strategy_id, user_id=user_id)
            if not elig.get("permitted"):
                raise GovernanceRejectionError(str(elig.get("reason") or "Strategy is not eligible for paper execution"))
        else:
            if row["stage"] not in {"PAPER_ELIGIBLE", "LIVE_ELIGIBLE"}:
                raise GovernanceRejectionError("Strategy version is not paper eligible")
            held, reason = self._security_store.is_strategy_execution_held(strategy_id, "paper")
            if held:
                raise GovernanceRejectionError(reason)
        
        try:
            # Use the strategy owner's ID for artifact verification, not the executing user's ID
            strategy_owner_id = row["owner_id"]
            path = self._governance_store.verify_artifact(
                artifact_root=self._artifact_root,
                owner_id=UUID(strategy_owner_id),
                artifact_path=row["artifact_path"],
                digest=row["source_sha256"]
            )
            payload = path.read_bytes()
            if hashlib.sha256(payload).hexdigest() != row["source_sha256"]:
                raise GovernanceRejectionError("Artifact hash mismatch")
            strategy = BoundedStrategy(payload.decode("utf-8"), strategy_id)
        except (OSError, UnicodeError, GovernanceStoreError, StrategyValidationError) as exc:
            raise GovernanceRejectionError("Artifact missing, inaccessible, or hash mismatch") from exc
        
        return strategy

    def classify_session_for_recovery(self, session_or_id: str | dict[str, Any]) -> str:
        """Classify session for recovery and reattach lifecycle (F-11)."""
        if isinstance(session_or_id, str):
            session = self._security_store.get_paper_session(session_or_id)
            if not session:
                return "SESSION_NOT_FOUND"
        else:
            session = session_or_id

        mode = session.get("data_source_mode", "HISTORICAL_REPLAY")
        status = session.get("status", "")
        if mode == "HISTORICAL_REPLAY":
            return "HISTORICAL_TERMINAL"
        if status in ("STOPPED", "CLOSED", "CANCELLED", "COMPLETED", "FAILED"):
            return "LIVE_TERMINAL"
        # Owner-held sessions never auto-resume; explicit release required.
        if status == "HELD" or session.get("owner_allowance") == "HOLD":
            return "SESSION_HELD"
        if status == "ACTIVE" and mode == "LIVE_MARKET":
            required = ("instrument", "timeframe", "initial_capital", "strategy_id")
            if any(session.get(k) is None for k in required):
                return "INVALID_CORRUPT"
            has_feed = self._has_test_feed(session.get("session_id")) or self._has_canonical_connection_authority(session.get("user_id"))
            return "LIVE_ACTIVE_REATTACHABLE" if has_feed else "LIVE_ACTIVE_PROVIDER_UNAVAILABLE"
        return "INVALID_CORRUPT"

    def reattach_live_session(
        self,
        session_id: str,
        *,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Recover and reattach a persisted ACTIVE live-market-paper session (F-11)."""
        session = self._security_store.get_paper_session(session_id)
        if not session:
            raise PaperSessionNotFoundError(f"Paper session '{session_id}' not found")

        if user_id is not None and str(session.get("user_id")) != str(user_id):
            raise PermissionError("Access denied: user cannot reattach another user's session")

        classification = self.classify_session_for_recovery(session)
        if classification in ("HISTORICAL_TERMINAL", "LIVE_TERMINAL"):
            raise InvalidPaperParameterError(f"Cannot reattach terminal session ({classification})")
        if classification == "SESSION_HELD":
            raise GovernanceRejectionError(
                f"Paper session '{session_id}' is on Owner hold and cannot reattach until released")
        if classification == "INVALID_CORRUPT":
            raise InvalidPaperParameterError("Cannot reattach corrupt or invalid session")

        # Validate strategy governance under Owner authority
        strategy_id = session["strategy_id"]
        gov = self._security_store.get_owner_strategy(strategy_id)
        if not gov:
            raise GovernanceRejectionError(f"Strategy '{strategy_id}' not registered")
        admin_status = gov.get("adminStatus") or gov.get("admin_status") or "ACTIVE"
        if admin_status != "ACTIVE":
            raise GovernanceRejectionError(f"Strategy '{strategy_id}' is {admin_status} under Owner governance")
        allowance = (
            gov.get("governance", {}).get("paper", {}).get("ownerAllowance")
            or gov.get("paper_owner_allowance")
            or "ALLOWED"
        )
        if allowance == "HOLD":
            raise GovernanceRejectionError(f"Strategy '{strategy_id}' paper execution is on HOLD by Owner")

        # F-10: session owner must retain persisted strategy authority at reattach.
        session_user_id = str(session.get("user_id"))
        session_access = self._security_store.check_user_strategy_access(session_user_id, strategy_id)
        if not session_access.get("permitted"):
            if session_access.get("reason") == "STRATEGY_NOT_ASSIGNED" and self._security_store.get_user(
                str(gov.get("author") or "")
            ) is None:
                pass
            else:
                raise GovernanceRejectionError(
                    f"Strategy '{strategy_id}' not available to session user: {session_access.get('reason')}"
                )

        inst = session["instrument"]
        tf = session["timeframe"]
        initial_capital = float(session["initial_capital"])
        strategy_name = session["strategy_name"]
        strategy_version = session["strategy_version"]
        policy_snapshot = session["policy_snapshot"]

        lot_size = 50 if inst == "NIFTY" else 15
        spec = InstrumentSpecification(
            identity=InstrumentIdentity(market="NSE", instrument=inst, segment="INDEX"),
            effective_from=datetime(2026, 1, 1).date(),
            price_increment=Decimal("0.05"),
            contract_multiplier=Decimal(str(lot_size)),
            minimum_quantity=Decimal(str(lot_size)),
            quantity_step=Decimal(str(lot_size)),
            currency="INR",
        )

        portfolio_acc = PortfolioAccount(
            account_id=f"ACC_PAPER_{session_id}",
            currency="INR",
            starting_capital=Decimal(str(initial_capital)),
            monetary_quantum=Decimal("0.01"),
        )
        account = VirtualPaperAccount(
            portfolio_account=portfolio_acc,
            specifications={spec.identity: spec},
            require_opening_reservation=False,
        )

        fill_policy = PaperFillPolicy(
            slippage_model=FixedBasisPointsSlippage(0),
            max_execution_tolerance_bps=Decimal("50"),
            max_slippage_bps=Decimal("20"),
        )
        broker = SimulatedPaperBroker(adapter=PaperFillAdapter(fill_policy))
        quote_cache = LatestQuoteCache()
        session_user_id = str(session.get("user_id"))
        strat_gen = self._resolve_paper_strategy_artifact(session_user_id, strategy_id, strategy_version)
        current_state = strat_gen.initial_state()

        policy_details = session.get("policy_details") or {}
        policy_version = policy_details.get("risk_policy_version") or policy_details.get("version") or RISK_POLICY_VERSION_V3
        risk_policy_kwargs: dict[str, Any] = {"version": policy_version}
        for k in ("per_trade_risk_pct", "max_daily_loss_pct", "max_daily_trades", "max_open_positions", "max_portfolio_risk_pct"):
            if k in policy_details:
                risk_policy_kwargs[k] = policy_details[k]
        risk_policy = RiskPolicy(**risk_policy_kwargs)
        risk_gate = RiskGate(risk_policy)
        session_protective_book = ProtectiveExitBook()

        # Restore open positions from DB
        open_positions: dict[str, Any] = {}
        db_positions = self._security_store.get_paper_positions(session_id)
        for pos in db_positions:
            if pos.get("status") == "OPEN":
                c_symbol = pos["resolved_contract"]
                opt_ident = InstrumentIdentity(market="NSE", instrument=c_symbol, segment="OPTIONS", underlying=inst)
                spec_opt = InstrumentSpecification(
                    identity=opt_ident,
                    effective_from=datetime(2020, 1, 1).date(),
                    price_increment=Decimal("0.05"),
                    contract_multiplier=Decimal("1"),
                    minimum_quantity=Decimal(str(lot_size)),
                    quantity_step=Decimal(str(lot_size)),
                    currency="INR",
                )
                account.register_specification(spec_opt)
                pos_key = PositionKey(
                    strategy_id=strategy_id,
                    strategy_version=strategy_version,
                    identity=opt_ident,
                )
                open_positions[c_symbol] = {
                    "position_id": pos["position_id"],
                    "symbol": inst,
                    "resolved_contract": c_symbol,
                    "position_key": pos_key,
                    "qty": int(pos["qty"]),
                    "avg_price": float(pos["avg_price"]),
                    "entry_cost": float(pos["entry_cost"]),
                    "identity": opt_ident,
                    "spec": spec_opt,
                }

        last_ts = None
        if session.get("last_market_timestamp"):
            try:
                last_ts = datetime.fromisoformat(session["last_market_timestamp"])
            except Exception:
                last_ts = None

        # F-11: restore the last accepted quote/event cursor truthfully; a
        # missing cursor restores as None (never an invented timestamp).
        last_quote_at = session.get("last_quote_received_at")
        restored_quote_count = int(session.get("live_quote_count") or 0)
        restored_contract = session.get("contract_identity")

        known_events = set()
        db_events = self._security_store.get_paper_events(session_id, limit=500)
        for ev in db_events:
            if ev.get("event_id"):
                known_events.add(ev["event_id"])

        db_orders = self._security_store.get_paper_orders(session_id)
        for od in db_orders:
            if od.get("order_id"):
                known_events.add(od["order_id"])

        # F-11: restore durably recorded quote ids so duplicates stay rejected
        # across restarts (no duplicate positions/orders post-restart).
        try:
            for quote_id in self._security_store.get_paper_quote_event_ids(session_id):
                known_events.add(quote_id)
        except Exception as exc:
            logger.warning("Could not restore quote event ids for %s: %s", session_id, exc)

        has_feed = self._has_test_feed(session_id) or self._has_canonical_connection_authority(session.get("user_id"))
        feed_status = "CONNECTED" if has_feed else "WAITING_FOR_MARKET_DATA"

        self._live_contexts[session_id] = {
            "session_id": session_id,
            "user_id": session["user_id"],
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "strategy_version": strategy_version,
            "instrument": inst,
            "timeframe": tf,
            "initial_capital": initial_capital,
            "policy_snapshot": policy_snapshot,
            "policy_details": policy_details,
            "policy_version": policy_version,
            "lot_size": lot_size,
            "spec": spec,
            "account": account,
            "broker": broker,
            "quote_cache": quote_cache,
            "strat_gen": strat_gen,
            "current_state": current_state,
            "feed_status": feed_status,
            "last_market_timestamp": last_ts,
            "last_quote_received_at": last_quote_at,
            "contract_identity": restored_contract,
            "quote_count": restored_quote_count,
            "risk_policy": risk_policy,
            "risk_gate": risk_gate,
            "session_protective_book": session_protective_book,
            "session_risk_state": None,
            "open_positions": open_positions,
            "known_event_ids": known_events,
        }

        updated = self._security_store.update_paper_session(
            session_id=session_id,
            feed_status=feed_status,
            error_message="",
            risk_gate_status="ENFORCED",
            last_market_timestamp=session.get("last_market_timestamp"),
            last_quote_received_at=last_quote_at,
            contract_identity=restored_contract,
            live_quote_count=restored_quote_count,
        )

        now_ist = datetime.now(IST).strftime("%H:%M:%S IST")
        self._security_store.record_paper_event(
            event_id=f"pe-{uuid.uuid4().hex[:8]}",
            session_id=session_id,
            event_time=now_ist,
            title="Session Reattached After Restart",
            detail=f"Live paper session reattached. Positions: {len(open_positions)}, feed status: {feed_status}.",
            source="Runtime Recovery",
            status="PASS",
            badge="REATTACHED",
        )

        return updated or session

    def auto_reattach_active_sessions(self) -> list[str]:
        """Automatically scan and reattach active live sessions on startup (F-11)."""
        if not self._security_store:
            return []
        reattached = []
        try:
            sessions = self._security_store.list_paper_sessions(limit=500)
            for ses in sessions:
                if ses.get("status") == "ACTIVE" and ses.get("data_source_mode") == "LIVE_MARKET":
                    try:
                        self.reattach_live_session(ses["session_id"])
                        reattached.append(ses["session_id"])
                    except Exception as exc:
                        logger.warning("Could not auto-reattach live paper session %s: %s", ses.get("session_id"), exc)
        except Exception as exc:
            logger.warning("Error during live paper recovery scan: %s", exc)
        return reattached
