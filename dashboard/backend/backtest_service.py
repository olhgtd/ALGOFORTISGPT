"""Authoritative Backtest Service for SentinelX.

Orchestrates the authoritative backtest pipeline:
1. Validates caller and strategy governance in SQLiteSecurityStore (fail-closed HTTP 403 on suspension/hold)
2. Loads canonical historical data through HistoricalDataFeed
3. Configures reproducibility manifest, bindings, and BacktestOrchestrator
4. Executes the deterministic backtest engine on real historical events
5. Calculates authoritative metrics via MetricsCalculator
6. Formats executed trades and equity curve
7. Persists the completed run to SQLiteSecurityStore for user and owner inspection
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import pandas as pd

from engine.backtest.engine import BarEvent
from engine.backtest.metrics import (
    EquityObservation,
    MetricCalculationPolicy,
    MetricScope,
    MetricScopeKind,
    MetricsCalculator,
)
from engine.backtest.regime import REGIME_POLICY_ID
from engine.costs import CostBasis, CostComponentRule, CostSchedule, CostSide
from dashboard.backend.backtest_datasets import ApprovedDatasetFiles, DatasetUnavailable
from dashboard.backend.backtest_jobs import BacktestJobs, BacktestCancelled, CancellableStrategy
from engine.market import BoundBarEvent, DataSubscription, StreamKey, StreamProfileMap, StrategyDataRequirements
from engine.market.profile import india_market_profile
from engine.orchestration.entry_pipeline import (
    BacktestOrchestrator,
    SignalToOrderPolicy,
    SignalToOrderRule,
    StrategyBinding,
)
from engine.orders import OrderType, TimeInForce
from engine.portfolio import AccountingOutcome, InstrumentIdentity, InstrumentSpecification, PortfolioAccount
from engine.reproducibility import (
    MarketDataPolicy,
    MarketDataSnapshot,
    MarketDataStream,
    ReproducibilityManifest,
    RuntimeConfigurationSnapshot,
    RuntimeDependencyClosure,
    RuntimeIdentity,
    SourceIdentityPolicy,
)
from engine.reproducibility.dependencies import RuntimeDependency
from engine.reproducibility.source import SourceFileIdentity
from dashboard.backend.backtest_strategies import resolve_registered_artifact
from dashboard.backend.strategy_execution import ADAPTER_VERSION
from dashboard.backend.strategy_validation import StrategyValidationError
import hashlib
import json
import math
import platform
from importlib.metadata import version as package_version
from pathlib import Path
from uuid import UUID
from dashboard.backend.security_store import SQLiteSecurityStore

logger = logging.getLogger(__name__)
UTC = timezone.utc
IST = ZoneInfo("Asia/Kolkata")

SUPPORTED_INSTRUMENTS = {"NIFTY", "BANKNIFTY"}
SUPPORTED_TIMEFRAMES = {"1m", "5m", "15m", "30m", "1H"}


class GovernanceRejectionError(Exception):
    """Raised when a strategy is suspended or on hold by Owner governance."""
    pass


class InvalidBacktestParameterError(Exception):
    """Raised when backtest parameters fail schema or availability constraints."""
    pass


class BacktestService:
    """Exact artifact replay with explicit modeled execution and persisted evidence."""
    def __init__(self, security_store, feed=None, *, governance_store=None, artifact_root=None, dataset_root=None):
        self._security_store = security_store
        self._feed = feed or (ApprovedDatasetFiles(dataset_root) if dataset_root is not None else None)
        self.configure_artifacts(governance_store, artifact_root)
        self.jobs = BacktestJobs(self)

    def configure_artifacts(self, governance_store, artifact_root):
        self._governance_store = governance_store
        self._artifact_root = Path(artifact_root) if artifact_root is not None else None

    def run_backtest(self, **request):
        """Explicit synchronous compatibility API; HTTP uses submit_backtest."""
        prepared = self._prepare_backtest(**request)
        self._security_store.save_backtest_run(prepared[0])
        return self._run_prepared(prepared)

    def submit_backtest(self, **request):
        return self.jobs.submit(self._prepare_backtest(**request))

    def _prepare_backtest(self, *, user_id, strategy_id, version_id=None, instrument="NIFTY", timeframe="1m",
                     initial_capital=500000.0, policy=None, date_range="2026-01-05", dataset_id="nse-tick-primary"):
        inst, tf = instrument.upper().strip(), timeframe.strip()
        if inst not in SUPPORTED_INSTRUMENTS or tf not in SUPPORTED_TIMEFRAMES:
            raise InvalidBacktestParameterError("Unsupported instrument or timeframe")
        if not math.isfinite(initial_capital) or initial_capital <= 0:
            raise InvalidBacktestParameterError("Initial capital must be finite and positive")
        user = self._security_store.get_user(user_id)
        if user is None or user["lifecycle"] != "ACTIVE" or user["account_status"] != "ACTIVE":
            raise GovernanceRejectionError("Active authenticated User required")
        # Retain existing explicit Owner hold diagnostics before artifact loading.
        registered = self._security_store.get_owner_strategy(strategy_id)
        if registered is not None:
            if registered["adminStatus"] != "ACTIVE":
                raise GovernanceRejectionError("Strategy " + registered["adminStatus"])
            if registered["governance"]["backtest"]["ownerAllowance"] != "ALLOWED":
                raise GovernanceRejectionError("Strategy backtest HOLD")
        try:
            artifact, registered, generator = resolve_registered_artifact(
                governance_store=self._governance_store, security_store=self._security_store,
                artifact_root=self._artifact_root, user_id=user_id, strategy_id=strategy_id, version_id=version_id)
        except PermissionError as exc:
            raise GovernanceRejectionError(str(exc)) from exc
        except StrategyValidationError as exc:
            raise InvalidBacktestParameterError(str(exc)) from exc
        gate = self._security_store.check_backtest_gate(strategy_id, dataset_id, user_id=user_id,
                                                        instrument=inst, timeframe=tf)
        if not gate["permitted"]:
            raise GovernanceRejectionError(gate["code"] + ": " + gate["reason"])
        dataset = gate["dataset"]
        if self._feed is None or not hasattr(self._feed, "fetch_dataset"):
            raise InvalidBacktestParameterError("DATASET_BINDING_UNAVAILABLE")
        try:
            df, file_digest = self._feed.fetch_dataset(dataset)
            df = df.copy()
        except DatasetUnavailable as exc:
            raise InvalidBacktestParameterError(str(exc)) from None
        if file_digest != dataset["hashSha256"].removeprefix("sha256:"):
            raise InvalidBacktestParameterError("DATASET_HASH_MISMATCH")
        if not {"timestamp", "open", "high", "low", "close", "volume"}.issubset(df.columns):
            raise InvalidBacktestParameterError("DATASET_COLUMNS_INVALID")
        for column, expected in (("instrument", inst), ("timeframe", tf)):
            if column in df and not df[column].eq(expected).all():
                raise InvalidBacktestParameterError("DATASET_CONTENT_IDENTITY_MISMATCH")
        if df.empty or "timestamp" not in df:
            raise InvalidBacktestParameterError("Historical dataset is empty or lacks timestamps")
        try:
            timestamps = pd.to_datetime(df["timestamp"], utc=True)
            parts = date_range.split("/")
            if len(parts) not in (1, 2): raise ValueError()
            from datetime import date
            start, end = date.fromisoformat(parts[0]), date.fromisoformat(parts[-1])
            if start.isoformat() != parts[0] or end.isoformat() != parts[-1] or start > end: raise ValueError()
            dates = timestamps.dt.tz_convert(IST).dt.date
            if start < date.fromisoformat(dataset["startDate"]) or end > date.fromisoformat(dataset["endDate"]):
                raise InvalidBacktestParameterError("DATASET_RANGE_UNAPPROVED: Requested date range exceeds available dataset coverage")
            interval = {"1m":60,"5m":300,"15m":900,"30m":1800,"1H":3600}[tf]
            deltas = timestamps.diff().dropna().dt.total_seconds()
            if timestamps.isna().any() or (deltas < interval).any():
                raise InvalidBacktestParameterError("DATASET_BAR_INTERVAL_INVALID")
            if start < dates.min() or end > dates.max():
                raise InvalidBacktestParameterError("Requested date range exceeds available dataset coverage")
            df = df.loc[(dates >= start) & (dates <= end)].copy()
            if df.empty: raise InvalidBacktestParameterError("No bars in requested date range")
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            if not df["timestamp"].is_monotonic_increasing or df["timestamp"].duplicated().any(): raise ValueError()
        except (ValueError, TypeError):
            raise InvalidBacktestParameterError("date_range must be YYYY-MM-DD or YYYY-MM-DD/YYYY-MM-DD with ordered, unambiguous bars") from None
        now = datetime.now(UTC).isoformat()
        metadata = {"strategy_id":strategy_id,"strategy_version":artifact["version_id"],
                    "artifact_sha256":artifact["source_sha256"],"adapter_version":ADAPTER_VERSION,
                    "dataset_id":dataset["datasetId"],"instrument":inst,"timeframe":tf,
                    "dataset_file_sha256":file_digest,
                    "gate_decision":{"id":"gate-"+uuid.uuid4().hex,"code":"GATE_PASS","subject":user_id,
                        "dataset_id":dataset["datasetId"],"approval":dataset["ownerApproval"],
                        "dataset_revision":dataset["lastUpdated"],"evaluated_at_utc":now,"override_used":False},"requested_date_range":date_range,
                    "effective_date_range":{"start":df["timestamp"].iloc[0].isoformat(),"end":df["timestamp"].iloc[-1].isoformat()},
                    "bars_consumed":len(df),"financial_provenance":"COMPUTED_FROM_MODELED_EXECUTION",
                    "execution_model":{"instrument":"index units (not option contracts)","quantity":1,"fills":"engine next-bar market fills","costs":"MODELED_ZERO","slippage":"MODELED_ZERO","risk_gate":"UNAVAILABLE"},
                    "requested_option_policy":policy,"option_policy_status":"UNAVAILABLE_NOT_EXECUTED"}
        record = {"run_id":"bt-"+uuid.uuid4().hex,"user_id":user_id,"strategy_id":strategy_id,
                  "strategy_name":registered["name"],"version":artifact["version_id"],"instrument":inst,"timeframe":tf,
                  "date_range":date_range,"initial_capital":initial_capital,"status":"RUNNING","policy_snapshot":"UNAVAILABLE: option strike policy is not executed",
                  "policy_details":{},"data_source_name":"Approved dataset: " + dataset["datasetId"] + " (" + inst + "/" + tf + ")",
                  "execution_metadata":metadata,"equity_curve":[],"trades":[],"created_at_utc":now,"completed_at_utc":None}
        metadata["bars_available"] = metadata.pop("bars_consumed")
        metadata["bars_consumed"] = None
        metadata["metric_status"] = "UNAVAILABLE_PENDING"
        metadata.pop("financial_provenance", None)
        return record, df, artifact, generator

    def _run_prepared(self, prepared):
        record, df, artifact, generator = prepared
        def check():
            current = self._security_store.get_backtest_run(record["run_id"])
            if current is None or current["status"] in {"CANCEL_REQUESTED", "CANCELLED"}:
                raise BacktestCancelled()
            if current["status"] != "RUNNING":
                raise RuntimeError("BACKTEST_JOB_NOT_RUNNING")
        try:
            check()
            self._recheck_dataset(record)
            resolve_registered_artifact(governance_store=self._governance_store, security_store=self._security_store,
                artifact_root=self._artifact_root, user_id=record["user_id"], strategy_id=record["strategy_id"], version_id=artifact["version_id"])
            record = self._execute(record, df, artifact, CancellableStrategy(generator, check))
            check()
        except BacktestCancelled:
            record = self._security_store._cancelled_record(record)
        except Exception:
            logger.exception("Backtest job execution failed")
            record = self._security_store._cancelled_record(record)
            record.update(status="FAILED", error_message=getattr(generator, "failure", None) or "BACKTEST_EXECUTION_FAILED",
                          equity_curve=[],trades=[],completed_at_utc=datetime.now(UTC).isoformat())
            record["execution_metadata"]["metric_status"] = "UNAVAILABLE_EXECUTION_FAILED"
        return self._security_store.save_backtest_run(record, expected_status={"RUNNING", "CANCEL_REQUESTED"})

    def _execute(self, record, df, artifact, strat_generator):
        inst, tf, strategy_id, initial_capital = record["instrument"], record["timeframe"], record["strategy_id"], record["initial_capital"]
        ident = InstrumentIdentity("NSE", inst, "index")
        sk = StreamKey(ident, tf)

        bars = tuple(
            BarEvent(inst, row.timestamp, tf, row.open, row.high, row.low, row.close, row.volume, False, seq)
            for seq, row in enumerate(df.itertuples(index=False))
        )
        mdp = MarketDataPolicy("data/v1", "normalization/v1", "sentinelx-backtest")
        stream_data = MarketDataStream(sk, bars, mdp)
        snapshot = MarketDataSnapshot(mdp, (stream_data,))
        events = tuple(BoundBarEvent(b, sk) for b in bars)

        source = SourceIdentityPolicy.compose(
            "SourceIdentityPolicy/v1",
            (SourceFileIdentity("artifact/strategy.py", artifact["source_sha256"]),
             SourceFileIdentity("adapter/strategy_execution.py", hashlib.sha256(Path(__file__).with_name("strategy_execution.py").read_bytes()).hexdigest()),
             SourceFileIdentity("adapter/backtest_service.py", hashlib.sha256(Path(__file__).read_bytes()).hexdigest())),
        )
        config = RuntimeConfigurationSnapshot(
            "config/v1", json.dumps({"id":strategy_id,"version":artifact["version_id"],"hash":artifact["source_sha256"]},sort_keys=True), "risk-deferred",
            json.dumps({"adapter":ADAPTER_VERSION,"quantity":1,"capital":initial_capital,"date_range":record["date_range"]},sort_keys=True),
            "MODELED_INDEX_UNIT_MARKET_FILL", "MODELED_ZERO_SLIPPAGE", "backtest"
        )
        closure = RuntimeDependencyClosure(
            "runtime/v1", (RuntimeDependency("pandas", package_version("pandas")),), RuntimeDependency("pyarrow", package_version("pyarrow"))
        )
        policy_rules = (
            SignalToOrderRule("BUY", OrderType.MARKET, TimeInForce.GTC, 1),
            SignalToOrderRule("SELL", OrderType.MARKET, TimeInForce.GTC, 1),
            SignalToOrderRule("EXIT", OrderType.MARKET, TimeInForce.GTC, 1),
        )
        orch_policy = SignalToOrderPolicy("slice5-execution-policy", "v1", policy_rules)

        manifest = ReproducibilityManifest(
            "manifest/v2", source, snapshot, config,
            RuntimeIdentity(platform.python_implementation(), platform.python_version(), "tzdata/" + package_version("tzdata")), closure,
            orch_policy.tier1_identity, "cost/v1", "validation/v1", "seed/v1",
            regime_policy_identity=REGIME_POLICY_ID,
        )

        reqs = StrategyDataRequirements(strategy_id, artifact["version_id"], (DataSubscription(sk),), frozenset({sk}))
        binding = StrategyBinding(strat_generator, reqs)

        profile_map = StreamProfileMap({sk: india_market_profile()})
        spec = InstrumentSpecification(ident, datetime(2020, 1, 1).date(), 1, 1, 1, "INR", "0.01")
        account = PortfolioAccount("account", "INR", Decimal(str(initial_capital)), "0.01")

        cost_schedule = CostSchedule(
            "cost-zero", "v1", "INR", datetime(2020, 1, 1, tzinfo=ZoneInfo("UTC")), None,
            (CostComponentRule("commission", CostBasis.FIXED, 0, CostSide.BOTH, rounding_quantum="0.01"),),
        )

        engine = BacktestOrchestrator(
            bindings=(binding,),
            profiles=profile_map,
            policies={strategy_id: orch_policy},
            account=account,
            specifications={ident: spec},
            manifest=manifest,
            cost_schedules=(cost_schedule,),
            regime_enabled=False,
        )


        result = engine.run(events)
        if strat_generator.failure or result.failure is not None:
            raise RuntimeError("Strategy or engine failed")
        # Recheck governance and artifact integrity before committing successful evidence.
        resolve_registered_artifact(governance_store=self._governance_store,security_store=self._security_store,
            artifact_root=self._artifact_root,user_id=record["user_id"],strategy_id=strategy_id,version_id=artifact["version_id"])
        self._recheck_dataset(record)
        observations = tuple(
            EquityObservation(a.source_evidence.execution_bar_timestamp,
                a.source_evidence.execution_bar_timestamp.astimezone(IST).date().isoformat(),
                a.resulting_snapshot.equity, Decimal("0"), f"accounting-{i}",
                result.manifest.manifest_fingerprint,a.resulting_snapshot.account_id)
            for i,a in enumerate(result.accounting) if a.outcome is AccountingOutcome.ACCEPTED
            and getattr(a.source_evidence,"execution_bar_timestamp",None) is not None)
        summary = MetricsCalculator().calculate(
            MetricScope(MetricScopeKind.RUN_ACCOUNT,result.manifest.manifest_fingerprint,"account"),
            MetricCalculationPolicy("registered-artifact-accounting","v1",250,("india",)),
            observations,result.trades,result.costs,regime_aware=False)
        def metric(key, scale=1):
            v=summary.metrics[key].value
            return float(v)*scale if v is not None else None
        trades=[]
        for tr in result.trades:
            exit_price = sum(leg.execution_price*leg.execution_quantity for leg in tr.exit_legs)/tr.exit_quantity
            basis = tr.average_entry_price * tr.entry_quantity * tr.contract_multiplier
            trades.append({"id":tr.trade_id,"time":tr.opened_at.isoformat(),"closed_at":tr.closed_at.isoformat(),
                "leg":tr.instrument_identity.instrument,"action":tr.position_side,"qty":float(tr.entry_quantity),
                "entry":float(tr.average_entry_price),"exit":float(exit_price),"pnl":float(tr.gross_realized_pnl),
                "pnlPct":float(tr.gross_realized_pnl/basis*100) if basis else None,
                "duration":str(tr.holding_duration),"rule":None,"provenance":"COMPUTED_FROM_MODELED_EXECUTION"})
        curve=[]; peak=initial_capital
        for obs in observations:
            value=float(obs.net_equity); peak=max(peak,value)
            curve.append({"date":obs.timestamp.isoformat(),"value":value,"drawdown":(value-peak)/peak*100 if peak else None})
        # No fallback curve: these are accounting snapshots, not a full MTM series.
        net = sum((tr.gross_realized_pnl for tr in result.trades),Decimal("0"))
        winning=sum(tr.gross_realized_pnl>0 for tr in result.trades)
        losing=sum(tr.gross_realized_pnl<0 for tr in result.trades)
        dd=summary.metrics["max_drawdown"]
        record.update(net_profit=float(net),net_profit_pct=float(net)/initial_capital*100,
            win_rate=metric("win_rate",100),profit_factor=metric("profit_factor"),sharpe_ratio=metric("sharpe"),
            max_drawdown=-float(dd.provenance["drawdown_fraction"])*100 if dd.value is not None else None,
            total_trades=len(trades),winning_trades=winning,losing_trades=losing,
            avg_profit_trade=metric("expectancy"),avg_win=metric("average_win"),avg_loss=metric("average_loss"),quality_score=None,
            status="COMPLETED",equity_curve=curve,trades=trades,error_message=None,
            data_fingerprint="sha256:"+snapshot.fingerprint,manifest_fingerprint=manifest.manifest_fingerprint,
            completed_at_utc=datetime.now(UTC).isoformat())
        record["execution_metadata"].update(bars_consumed=len(df), financial_provenance="COMPUTED_FROM_MODELED_EXECUTION", dataset_fingerprint=snapshot.fingerprint,
            manifest_fingerprint=manifest.manifest_fingerprint,signal_evidence=strat_generator.signals,
            metric_evidence_id=summary.evidence_id,
            metric_status={k:{"status":v.status.value,"reason":v.reason} for k,v in summary.metrics.items()},
            equity_basis="ACTUAL_ENGINE_ACCOUNTING_SNAPSHOTS_NOT_FULL_MTM",
            profit_basis="COMPUTED_REALIZED_PNL_FROM_COMPLETED_MODELED_TRADES",
            quality_status="UNAVAILABLE",python_version=platform.python_version(),
            dependencies={"pandas":package_version("pandas"),"pyarrow":package_version("pyarrow"),"tzdata":package_version("tzdata")})
        return record

    def _recheck_dataset(self, record):
        meta = record["execution_metadata"]
        gate = self._security_store.check_backtest_gate(record["strategy_id"], meta["dataset_id"],
            user_id=record["user_id"], instrument=record["instrument"], timeframe=record["timeframe"])
        if not gate["permitted"] or gate["dataset"]["hashSha256"].removeprefix("sha256:") != meta["dataset_file_sha256"] or gate["dataset"]["lastUpdated"] != meta["gate_decision"]["dataset_revision"]:
            raise GovernanceRejectionError("DATASET_GOVERNANCE_CHANGED")

    def get_run(self, run_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        """Fetch backtest run details (user-scoped if user_id is provided)."""
        return self._security_store.get_backtest_run(run_id, user_id=user_id)

    def list_runs(self, user_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """List backtest runs (user-scoped if user_id is provided; all runs if user_id is None)."""
        return self._security_store.list_backtest_runs(user_id=user_id, limit=limit)

    def get_trades(self, run_id: str, user_id: str | None = None) -> list[dict[str, Any]] | None:
        """Fetch trade list for a run (user-scoped if user_id is provided)."""
        return self._security_store.get_backtest_trades(run_id, user_id=user_id)

    def cancel_run(self, run_id: str, user_id: str | None = None) -> bool:
        """Cancel a running backtest."""
        return self._security_store.cancel_backtest_run(run_id, user_id=user_id)
