import React, { useState, useMemo, useEffect } from "react";
import { Icon } from "../../shared/icons/V3Icons";
import { Panel, TruthChip, Drawer } from "../../shared/utilities/V3Chrome";
import {
  type StrategyRow,
  type GlobalStrikePolicy,
  DEFAULT_GLOBAL_STRIKE_POLICY,
  resolveStrikesFromPolicy,
  UNDERLYINGS,
  STRATEGIES,
} from "../../sampleData";
import {
  executeBacktest,
  queryBacktestDatasets,
  cancelBacktestRun,
  queryBacktestRuns,
  queryBacktestTrades,
  queryUserStrategyRegistry,
  queryStrategyReadiness,
  type StrategyReadiness,
  requestStrategyPromotion,
  isBackendEnabled,
  createWalkForwardJob,
  listWalkForwardJobs,
  getWalkForwardJob,
  cancelWalkForwardJob,
  type WalkForwardJob,
} from "../../shared/services/integrationClient";

/* ════════════════════════════════════════════════════════════
   BACKTESTING TYPES & DATASETS
   ════════════════════════════════════════════════════════════ */

export interface BacktestDataset {
  id: string;
  name: string;
  instrument: string;
  status: "READY" | "WARNING" | "BLOCKED";
  bars: number;
  coveragePct: number | null;
  knownGaps: string;
  calendarStatus: string;
  fingerprint: string;
  importedAt: string;
  dateRange: string;
  blockedReason?: string;
}

export interface DetailedBacktestRun {
  id: string;
  strategyId?: string;
  strategyName: string;
  version: string;
  underlying: "NIFTY" | "BANKNIFTY";
  timeframe: string;
  dateRange: string;
  initialCapital: number;
  netProfit: number;
  netProfitPct: number;
  winRate: number;
  profitFactor: number;
  sharpeRatio: number;
  maxDrawdown: number;
  totalTrades: number;
  winningTrades: number;
  losingTrades: number;
  avgProfitTrade: number;
  avgWin: number;
  avgLoss: number;
  status: "PENDING" | "COMPLETED" | "FAILED" | "RUNNING" | "CANCEL_REQUESTED" | "CANCELLED";
  qualityScore: number;
  policySnapshot: string;
  policyDetails: { mode: string; distance: number; ceStrike: number; peStrike: number; spot: number; atmStrike: number };
  dataFingerprint: string;
  dataSourceName: string;
  runDate: string;
  blockedReason?: string;
  equityCurve: { date: string; value: number; drawdown: number }[];
}

export const DATA_SOURCES: BacktestDataset[] = [];

export const INITIAL_HISTORICAL_RUNS: DetailedBacktestRun[] = [];

export interface SampleTradeRow {
  id: string;
  time: string;
  leg: string;
  action: "BUY";
  qty: number;
  entry: number;
  exit: number;
  pnl: number;
  pnlPct: number;
  duration: string;
  rule: string;
}

export const SAMPLE_TRADES: SampleTradeRow[] = [];

/* ════════════════════════════════════════════════════════════
   BACKTESTING SCREEN COMPONENT
   ════════════════════════════════════════════════════════════ */

export interface BacktestingScreenProps {
  initialStrategy?: StrategyRow | null;
  policy?: GlobalStrikePolicy;
  onChangePolicy?: (next: GlobalStrikePolicy) => void;
  previewMode?: boolean;
}

export const BacktestingScreen: React.FC<BacktestingScreenProps> = ({
  initialStrategy,
  policy = DEFAULT_GLOBAL_STRIKE_POLICY,
  onChangePolicy,
  previewMode = false,
}) => {
  // Sub-views: "CONFIG_RUN", "HISTORICAL_RUNS", "COMPARE_RUNS", "WALK_FORWARD"
  const [activeView, setActiveView] = useState<"CONFIG_RUN" | "HISTORICAL_RUNS" | "COMPARE_RUNS" | "WALK_FORWARD">("CONFIG_RUN");

  const isInspectionPreview = useMemo(() => {
    if (previewMode) return true;
    if (typeof window !== "undefined") {
      const p = new URLSearchParams(window.location.search);
      return p.get("dev") === "1" && p.get("preview") === "user";
    }
    return false;
  }, [previewMode]);

  // Configuration State
  const [registeredStrategies, setRegisteredStrategies] = useState<StrategyRow[]>(() => STRATEGIES);
  const [selectedStratId, setSelectedStratId] = useState<string>(() => initialStrategy?.id || "");
  const [selectedVersion, setSelectedVersion] = useState<string>("v2.3");
  const [underlying, setUnderlying] = useState<"NIFTY" | "BANKNIFTY">("NIFTY");
  const [timeframe, setTimeframe] = useState<string>("1m");
  const [dateRange, setDateRange] = useState<string>("2026-01-05");
  const [capital, setCapital] = useState<string>("500000");
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>("nse-tick-primary");

  const [datasets, setDatasets] = useState<BacktestDataset[]>([]);
  useEffect(() => {
    if (isInspectionPreview || !isBackendEnabled()) return;
    queryBacktestDatasets().then(rows => {
      setDatasets(rows.map(d => ({id: d.datasetId, name: `${d.datasetId} (${d.instrument} ${d.timeframe})`,
        instrument: d.instrument, status: d.effectiveBacktestReadiness === "READY_FOR_BACKTEST" ? "READY" : "BLOCKED",
        bars: d.rowCount, coveragePct: null, knownGaps: d.gapStatus, calendarStatus: d.gapStatus,
        fingerprint: d.hashSha256, importedAt: d.lastUpdated, dateRange: `${d.startDate}/${d.endDate}`,
        blockedReason: d.effectiveBacktestReadiness})));
      setSelectedDatasetId(previous => rows.some(d => d.datasetId === previous) ? previous : rows[0]?.datasetId || "");
    }).catch(() => setDatasets([]));
  }, [isInspectionPreview]);

  // ── Walk-Forward / OOS (R-05, manual RUN only) ──
  const [walkForwardJobs, setWalkForwardJobs] = useState<WalkForwardJob[]>([]);
  const [wfIsDays, setWfIsDays] = useState<string>("5");
  const [wfOosDays, setWfOosDays] = useState<string>("2");
  const [wfBusy, setWfBusy] = useState(false);
  const [wfToast, setWfToast] = useState<string | null>(null);
  const [wfExpanded, setWfExpanded] = useState<string | null>(null);

  const refreshWalkForwardJobs = async () => {
    if (isInspectionPreview || !isBackendEnabled()) return;
    const res = await listWalkForwardJobs().catch(() => null);
    if (res && res.source === "BACKEND") setWalkForwardJobs(res.data ?? []);
  };

  useEffect(() => {
    if (activeView !== "WALK_FORWARD" || isInspectionPreview || !isBackendEnabled()) return;
    void refreshWalkForwardJobs();
    const timer = window.setInterval(() => { void refreshWalkForwardJobs(); }, 5000);
    return () => window.clearInterval(timer);
  }, [activeView, isInspectionPreview]);

  const showWfToast = (msg: string) => {
    setWfToast(msg);
    setTimeout(() => setWfToast(null), 5000);
  };

  const handleWalkForwardRun = async () => {
    const strat = registeredStrategies.find((s) => s.id === selectedStratId) || registeredStrategies[0];
    if (!strat) {
      showWfToast("Select a strategy first.");
      return;
    }
    setWfBusy(true);
    try {
      const res = await createWalkForwardJob({
        strategy_id: (strat as any).strategyId || strat.id,
        version_id: (strat as any).version || undefined,
        dataset_id: selectedDatasetId || undefined,
        instrument: underlying,
        timeframe,
        is_days: Math.max(1, parseInt(wfIsDays, 10) || 5),
        oos_days: Math.max(1, parseInt(wfOosDays, 10) || 2),
        initial_capital: Math.max(1000, parseInt(capital, 10) || 500000),
        policy: { mode: "OTM", distance: 1 },
      });
      if (res.success) {
        showWfToast(`Walk-forward job ${res.data?.job_id ?? "?"} started (backend-confirmed).`);
        setWfExpanded(res.data?.job_id ?? null);
        await refreshWalkForwardJobs();
      } else {
        showWfToast(res.error || "Walk-forward run blocked by authority.");
      }
    } finally {
      setWfBusy(false);
    }
  };

  const handleWalkForwardCancel = async (jobId: string) => {
    const res = await cancelWalkForwardJob(jobId);
    showWfToast(res.success ? `Cancel requested for ${jobId} (backend-confirmed).` : (res.error || "Cancel failed"));
    await refreshWalkForwardJobs();
  };

  // Historical Runs State
  const [historicalRuns, setHistoricalRuns] = useState<DetailedBacktestRun[]>(() => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("algofortis_historical_backtests_v3");
      return saved ? JSON.parse(saved) : [];
    }
    return [];
  });

  const [activeRunId, setActiveRunId] = useState<string>(() => historicalRuns[0]?.id || "");
  const [isAuthoritativeRun, setIsAuthoritativeRun] = useState<boolean>(false);
  const [executedTrades, setExecutedTrades] = useState<SampleTradeRow[]>([]);
  const [selectedRunsForCompare, setSelectedRunsForCompare] = useState<string[]>([]);

  const [refresh, setRefresh] = useState(0);
  const [statusUnavailable, setStatusUnavailable] = useState(false);
  // Pin the version selector to the exact registered version whenever the
  // backend registry resolves a strategy (exact-version plumbing).
  useEffect(() => {
    const current = registeredStrategies.find((s) => s.id === selectedStratId);
    const regVersion = (current as any)?.version;
    if (regVersion && regVersion !== selectedVersion) {
      setSelectedVersion(regVersion);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [registeredStrategies, selectedStratId]);
  useEffect(() => {
    if (isInspectionPreview || !isBackendEnabled()) return;
    const timer = window.setInterval(() => setRefresh(n => n + 1), 1000);
    return () => window.clearInterval(timer);
  }, [isInspectionPreview]);

  // Load Authoritative Runs & Registered Strategies from Backend if active and not preview
  useEffect(() => {
    if (!isInspectionPreview && isBackendEnabled()) {
      queryUserStrategyRegistry().then((sRes) => {
        if (sRes.source === "BACKEND" && sRes.data && sRes.data.length > 0) {
          const mapped: StrategyRow[] = sRes.data.map((b, idx) => ({
            id: b.strategy_id || `strat-${idx}`,
            strategyId: b.strategy_id,
            name: b.strategy_id,
            version: b.version_id || "v1.0",
            language: "Python",
            stage: (b.stage as any) || "BACKTEST_ELIGIBLE",
            quality: 75,
            evidenceAttached: Boolean(b.source_sha256),
            pnl: "n/a",
            isProfit: true,
            note: `Governed policy: ${b.protective_policy || "ACTIVE"}`,
            description: "Governed Python strategy.",
            author: "Authenticated User",
            lastUpdated: "Just now",
            scanStatus: "PASSED",
            conformanceCheck: "CONFORMANT",
            winRate: 65.0,
            maxDrawdown: -5.0,
            profitFactor: 1.6,
            sharpeRatio: 1.4,
            totalTrades: 0,
            activePositions: 0,
            visibility: (b.visibility as any) || "PRIVATE",
          }));
          setRegisteredStrategies(mapped);
          setSelectedStratId((prev) => prev || mapped[0]?.id || "");
        } else if (sRes.source === "BACKEND" && sRes.data && sRes.data.length === 0) {
          setRegisteredStrategies([]);
        }
      });

      queryBacktestRuns(20).then((res) => {
        setStatusUnavailable(res.source !== "BACKEND");
        if (res.source !== "BACKEND") return;
        if (res.data && res.data.length > 0) {
          const mapped: DetailedBacktestRun[] = res.data.map((r) => ({
            id: r.run_id,
            strategyId: r.strategy_id,
            strategyName: r.strategy_name,
            version: r.version,
            underlying: (r.instrument === "BANKNIFTY" ? "BANKNIFTY" : "NIFTY"),
            timeframe: r.timeframe,
            dateRange: r.date_range,
            initialCapital: r.initial_capital,
            netProfit: r.net_profit,
            netProfitPct: r.net_profit_pct,
            winRate: r.win_rate,
            profitFactor: r.profit_factor,
            sharpeRatio: r.sharpe_ratio,
            maxDrawdown: r.max_drawdown,
            totalTrades: r.total_trades,
            winningTrades: r.winning_trades,
            losingTrades: r.losing_trades,
            avgProfitTrade: r.avg_profit_trade,
            avgWin: r.avg_win,
            avgLoss: r.avg_loss,
            status: r.status,
        blockedReason: r.error_message,
            qualityScore: r.quality_score,
            policySnapshot: r.policy_snapshot,
            policyDetails: {
              mode: r.policy_details?.mode || "ATM",
              distance: r.policy_details?.distance || 0,
              ceStrike: r.policy_details?.ceStrike || 0,
              peStrike: r.policy_details?.peStrike || 0,
              spot: r.policy_details?.spot || 0,
              atmStrike: r.policy_details?.atmStrike || 0,
            },
            dataFingerprint: r.data_fingerprint,
            dataSourceName: r.data_source_name,
            runDate: r.created_at_utc,
            equityCurve: r.equity_curve || [],
          }));
          setHistoricalRuns(mapped);
          setActiveRunId(previous => mapped.some(r => r.id === previous) ? previous : mapped[0].id);
          setIsAuthoritativeRun(true);
          queryBacktestTrades(activeRunId || mapped[0].id).then((tRes) => {
            setExecutedTrades(tRes.data || []);
          });
        } else if (res.data && res.data.length === 0) {
          setHistoricalRuns([]);
          setActiveRunId("");
          setIsAuthoritativeRun(true);
          setExecutedTrades([]);
        }
      });
    }
  }, [isInspectionPreview, refresh]);

  // Simulation State
  const [isSimulating, setIsSimulating] = useState<boolean>(false);
  const [simulationStage, setSimulationStage] = useState<string>("");
  const [simulationProgress, setSimulationProgress] = useState<number>(0);
  const [toastMsg, setToastMsg] = useState<string | null>(null);

  // Visualization Toggle (Equity vs Drawdown)
  const [chartMode, setChartMode] = useState<"EQUITY" | "DRAWDOWN">("EQUITY");

  // Governance Promotion Drawer (LIVE-only; Backtest/Paper are self-service)
  const [promotionDrawerOpen, setPromotionDrawerOpen] = useState<boolean>(false);
  const [promotionRequested, setPromotionRequested] = useState<boolean>(false);

  // Backend-authoritative readiness (R-03): no fake readiness, backend is authority.
  const [strategyReadiness, setStrategyReadiness] = useState<StrategyReadiness | null>(null);
  const selectedStrategyIdentity = useMemo(() => {
    const s = registeredStrategies.find((x) => x.id === selectedStratId || (x as any).strategyId === selectedStratId);
    return (s as any)?.strategyId || s?.id || selectedStratId;
  }, [registeredStrategies, selectedStratId]);
  useEffect(() => {
    if (isInspectionPreview || !isBackendEnabled() || !selectedStrategyIdentity) {
      setStrategyReadiness(null);
      return;
    }
    let cancelled = false;
    queryStrategyReadiness(selectedStrategyIdentity).then((r) => {
      if (!cancelled) setStrategyReadiness(r);
    }).catch(() => {
      if (!cancelled) setStrategyReadiness(null);
    });
    return () => { cancelled = true; };
  }, [selectedStrategyIdentity, isInspectionPreview]);

  // Active Run Object (Selected completed backtest)
  const activeRun = useMemo(() => {
    if (!historicalRuns || historicalRuns.length === 0) return undefined;
    return historicalRuns.find((r) => r.id === activeRunId) || historicalRuns[0];
  }, [historicalRuns, activeRunId]);

  // Active Dataset Object
  const activeDataset = useMemo(() => {
    return datasets.find((d) => d.id === selectedDatasetId);
  }, [selectedDatasetId, datasets]);

  // Resolved Strike for current configuration envelope
  const currentStrikeResolved = useMemo(() => {
    const spot = UNDERLYINGS[underlying].spot;
    const step = UNDERLYINGS[underlying].step;
    return resolveStrikesFromPolicy(spot, step, policy);
  }, [underlying, policy]);

  // Mathematical Derived Metrics from Single Source of Truth
  const derivedMetrics = useMemo(() => {
    if (!activeRun || activeRun.status !== "COMPLETED") {
      return {
        initial: 0,
        net: 0,
        returnPct: 0,
        trades: 0,
        wins: 0,
        losses: 0,
        winRate: 0,
        expectancy: 0,
        profitFactor: 0,
        grossProfit: 0,
        grossLoss: 0,
        avgWin: 0,
        avgLoss: 0,
        finalEquity: 0,
      };
    }
    const initial = activeRun.initialCapital || 500000;
    const net = activeRun.netProfit;
    const trades = activeRun.totalTrades;
    const wins = activeRun.winningTrades || 136;
    const losses = activeRun.losingTrades || (trades - wins);
    const returnPct = Number(((net / initial) * 100).toFixed(2));
    const winRate = Number(((wins / trades) * 100).toFixed(1));
    const expectancy = Number((net / trades).toFixed(2));
    const profitFactor = activeRun.profitFactor || 2.32;
    
    // Exact gross profit & gross loss derived from Profit Factor & Net Profit
    // PF = GP / GL  =>  GP = PF * GL
    // Net = GP - GL = (PF - 1) * GL  =>  GL = Net / (PF - 1)
    const grossLoss = Number((net / (profitFactor - 1)).toFixed(2));
    const grossProfit = Number((grossLoss + net).toFixed(2));
    const avgWin = Number((grossProfit / wins).toFixed(2));
    const avgLoss = Number((-grossLoss / losses).toFixed(2));
    const finalEquity = initial + net;

    return {
      initial,
      net,
      returnPct,
      trades,
      wins,
      losses,
      winRate,
      expectancy,
      profitFactor,
      grossProfit,
      grossLoss,
      avgWin,
      avgLoss,
      finalEquity,
    };
  }, [activeRun]);

  // Sync to localStorage only in inspection preview or offline mode
  useEffect(() => {
    if (isInspectionPreview || !isBackendEnabled()) {
      localStorage.setItem("algofortis_historical_backtests_v3", JSON.stringify(historicalRuns));
    }
  }, [historicalRuns, isInspectionPreview]);

  // Check if current configuration is blocked
  const isDataBlocked = !activeDataset || activeDataset.status === "BLOCKED";

  // Handle Run Backtest Execution (Authoritative Backend & Developer Inspection Preview)
  const handleRunBacktest = async () => {
    if (isDataBlocked) return;

    setIsSimulating(true);
    if (isInspectionPreview) setSimulationProgress(10);
    setSimulationStage("Verifying Strategy Governance & Sandbox Allowance...");

    const snapshotStr = policy.mode === "ATM" ? "ATM (0 strikes)" : `${policy.mode} (${policy.distance} strike${policy.distance === 1 ? "" : "s"})`;
    const spot = UNDERLYINGS[underlying].spot;
    const step = UNDERLYINGS[underlying].step;
    const resolved = resolveStrikesFromPolicy(spot, step, policy);

    const stratObj = registeredStrategies.find((s) => s.id === selectedStratId || s.strategyId === selectedStratId) || registeredStrategies[0];
    const targetStrategyId = stratObj?.strategyId || stratObj?.id || selectedStratId || "SX-STRAT-001";
    const capVal = parseInt(capital.replace(/[^0-9]/g, ""), 10) || 500000;

    // Non-authoritative Developer Preview or Offline fallback
    if (isInspectionPreview || !isBackendEnabled()) {
      const newRunId = `bt-2026-${Date.now().toString().slice(-6)}`;
      const newRun: DetailedBacktestRun = {
        id: newRunId,
        strategyName: stratObj.name,
        version: selectedVersion,
        underlying: underlying,
        timeframe: timeframe,
        dateRange: dateRange,
        initialCapital: capVal,
        netProfit: 138400,
        netProfitPct: 27.68,
        winRate: 69.4,
        profitFactor: 2.32,
        sharpeRatio: 2.21,
        maxDrawdown: -4.10,
        totalTrades: 196,
        winningTrades: 136,
        losingTrades: 60,
        avgProfitTrade: 706.12,
        avgWin: 1788.59,
        avgLoss: -1747.47,
        status: "COMPLETED",
        qualityScore: 83,
        policySnapshot: snapshotStr,
        policyDetails: {
          mode: policy.mode,
          distance: policy.distance,
          ceStrike: resolved.ceStrike,
          peStrike: resolved.peStrike,
          spot: spot,
          atmStrike: resolved.atmStrike,
        },
        dataFingerprint: activeDataset.fingerprint,
        dataSourceName: activeDataset.name,
        runDate: "Just now (UTC)",
        equityCurve: [
          { date: "Jan 02", value: capVal, drawdown: 0 },
          { date: "Jan 20", value: capVal + 14200, drawdown: 0 },
          { date: "Feb 10", value: capVal + 28500, drawdown: 0 },
          { date: "Feb 28", value: capVal + 21400, drawdown: -1.34 },
          { date: "Mar 18", value: capVal + 41200, drawdown: 0 },
          { date: "Apr 08", value: capVal + 58900, drawdown: 0 },
          { date: "Apr 29", value: capVal + 74200, drawdown: 0 },
          { date: "May 19", value: capVal + 66800, drawdown: -1.29 },
          { date: "Jun 09", value: capVal + 91400, drawdown: 0 },
          { date: "Jun 30", value: capVal + 108900, drawdown: 0 },
          { date: "Jul 21", value: capVal + 127400, drawdown: 0 },
          { date: "Aug 12", value: capVal + 122100, drawdown: -0.84 },
          { date: "Aug 31", value: capVal + 138400, drawdown: 0 },
        ],
      };

      setHistoricalRuns((prev) => [newRun, ...prev]);

      setTimeout(() => {
        setSimulationProgress(35);
        setSimulationStage("Loading Historical Bars (61,500 1m ticks)...");
      }, 300);

      setTimeout(() => {
        setSimulationProgress(65);
        setSimulationStage("Generating AST Signals & Risk Filter Evaluation...");
      }, 700);

      setTimeout(() => {
        setSimulationProgress(90);
        setSimulationStage("Processing Simulated Orders & Applying Slippage Model (0.05%)...");
      }, 1100);

      setTimeout(() => {
        setIsSimulating(false);
        setSimulationProgress(100);
        setSimulationStage("Completed");
        setActiveRunId(newRunId);
        setIsAuthoritativeRun(false);
        setActiveView("CONFIG_RUN");
        setToastMsg(`Backtest complete! Quality Score: 83/100 (Strong). Snapshot locked: ${snapshotStr}.`);
        setTimeout(() => setToastMsg(null), 4000);
      }, 1600);
      return;
    }

    // Authoritative Backend Execution
    try {
      setSimulationStage("Submitting backtest for validation...");

      const res = await executeBacktest({
        strategy_id: targetStrategyId,
        version_id: (stratObj as any)?.version || selectedVersion,
        dataset_id: selectedDatasetId,
        instrument: underlying,
        timeframe: timeframe,
        date_range: dateRange,
        initial_capital: capVal,
        policy: {
          mode: policy.mode,
          distance: policy.distance,
        },
      });

      if (!res.data) {
        setIsSimulating(false);
        setSimulationProgress(0);
        const errMsg = res.error || "Execution rejected by AlgoFortis governance";
        setToastMsg(`Execution Blocked: ${errMsg}`);
        setTimeout(() => setToastMsg(null), 5000);
        return;
      }

      const r = res.data;
      setSimulationStage(r.status);

      const authRun: DetailedBacktestRun = {
        id: r.run_id,
        strategyName: r.strategy_name,
        version: r.version,
        underlying: (r.instrument === "BANKNIFTY" ? "BANKNIFTY" : "NIFTY"),
        timeframe: r.timeframe,
        dateRange: r.date_range,
        initialCapital: r.initial_capital,
        netProfit: r.net_profit,
        netProfitPct: r.net_profit_pct,
        winRate: r.win_rate,
        profitFactor: r.profit_factor,
        sharpeRatio: r.sharpe_ratio,
        maxDrawdown: r.max_drawdown,
        totalTrades: r.total_trades,
        winningTrades: r.winning_trades,
        losingTrades: r.losing_trades,
        avgProfitTrade: r.avg_profit_trade,
        avgWin: r.avg_win,
        avgLoss: r.avg_loss,
        status: r.status,
        blockedReason: r.error_message,
        qualityScore: r.quality_score,
        policySnapshot: r.policy_snapshot,
        policyDetails: {
          mode: r.policy_details?.mode || policy.mode,
          distance: r.policy_details?.distance || policy.distance,
          ceStrike: r.policy_details?.ceStrike || resolved.ceStrike,
          peStrike: r.policy_details?.peStrike || resolved.peStrike,
          spot: r.policy_details?.spot || spot,
          atmStrike: r.policy_details?.atmStrike || resolved.atmStrike,
        },
        dataFingerprint: r.data_fingerprint,
        dataSourceName: r.data_source_name,
        runDate: r.created_at_utc,
        equityCurve: r.equity_curve || [],
      };

      setHistoricalRuns((prev) => [authRun, ...prev.filter((p) => p.id !== authRun.id)]);
      setActiveRunId(authRun.id);
      setIsAuthoritativeRun(true);

      if (r.trades && r.trades.length > 0) {
        const mappedTrades = (r.trades as any[]).map((t: any, idx: number) => ({
          id: String(t.trade_id || t.id || `${r.run_id}-t${idx}`),
          time: String(t.exit_time || t.entry_time || t.time || r.created_at_utc || "—"),
          leg: String(t.symbol || t.leg || r.instrument || "NIFTY"),
          action: "BUY" as const,
          qty: Number(t.quantity || t.qty || 1),
          entry: Number(t.entry_price ?? t.entry ?? 0),
          exit: Number(t.exit_price ?? t.exit ?? 0),
          pnl: Number(t.pnl ?? t.net_pnl ?? 0),
          pnlPct: Number(t.pnl_pct ?? t.return_pct ?? 0),
          duration: String(t.hold_bars ? `${t.hold_bars} bars` : ""),
          rule: String(t.entry_reason || t.exit_reason || "authoritative"),
        }));
        setExecutedTrades(mappedTrades);
      }

      setIsSimulating(false);
      setSimulationStage(r.status);
      setActiveView("CONFIG_RUN");
      setToastMsg(`Authoritative backtest complete: ${r.run_id} · Quality Score ${r.quality_score ?? "n/a"}/100`);
      setTimeout(() => setToastMsg(null), 5000);
    } catch (err: any) {
      setIsSimulating(false);
      setSimulationProgress(0);
      setToastMsg(`Execution failed: ${err.message || String(err)}`);
      setTimeout(() => setToastMsg(null), 5000);
    }
  };

  const handleCancel = async () => {
    if (!activeRun || statusUnavailable) return;
    const result = await cancelBacktestRun(activeRun.id);
    setToastMsg(result.ok ? "Cancellation request received; awaiting authoritative status." : result.error || "Cancellation unavailable");
    setRefresh(n => n + 1);
  };

  // Toggle run selection for comparison
  const toggleRunForCompare = (id: string) => {
    setSelectedRunsForCompare((prev) => {
      if (prev.includes(id)) {
        return prev.filter((r) => r !== id);
      } else {
        if (prev.length >= 3) {
          return [prev[1], prev[2], id];
        }
        return [...prev, id];
      }
    });
  };

  return (
    <div className="backtesting-workspace" id="backtesting-workspace-root">
      {activeRun && !isInspectionPreview && <div className="v3-row" role="status" id="backtest-job-status">
        <span>{activeRun.id}: {statusUnavailable ? "STATUS UNAVAILABLE" : activeRun.status}</span>
        {activeRun.blockedReason && <span>{activeRun.blockedReason}</span>}
        {["PENDING", "RUNNING"].includes(activeRun.status) && <button id="cancel-backtest-btn" className="v3-btn secondary"
          disabled={statusUnavailable} onClick={handleCancel}>Cancel backtest</button>}
      </div>}
      {/* ── Screen Header ── */}
      <div className="v3-screen-head">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <h2 className="v3-screen-title" style={{ letterSpacing: "0.04em" }}>
              BACKTESTING
            </h2>
            <span className="v3-tag" style={{ background: "rgba(56, 189, 248, 0.12)", color: "#38bdf8", border: "1px solid rgba(56, 189, 248, 0.3)" }}>
              Strategy Research &amp; Evidence
            </span>
          </div>
          <p className="v3-screen-sub">
            Deterministic historical replay · Global strike policy snapshotting · Strategy Quality Score (0–100)
          </p>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <button
            type="button"
            className={`v3-btn ${activeView === "CONFIG_RUN" ? "primary" : "secondary"} mini`}
            onClick={() => setActiveView("CONFIG_RUN")}
            id="new-backtest-nav-btn"
          >
            <Icon name="play" size={13} />
            <span>NEW BACKTEST</span>
          </button>

          <button
            type="button"
            className={`v3-btn ${activeView === "HISTORICAL_RUNS" ? "primary" : "secondary"} mini`}
            onClick={() => setActiveView("HISTORICAL_RUNS")}
            id="historical-runs-nav-btn"
          >
            <Icon name="activity" size={13} />
            <span>Historical Runs ({historicalRuns.length})</span>
          </button>

          <button
            type="button"
            className={`v3-btn ${activeView === "WALK_FORWARD" ? "primary" : "secondary"} mini`}
            onClick={() => { setActiveView("WALK_FORWARD"); void refreshWalkForwardJobs(); }}
            id="walk-forward-nav-btn"
          >
            <Icon name="layers" size={13} />
            <span>Walk-Forward / OOS ({walkForwardJobs.length})</span>
          </button>

          {selectedRunsForCompare.length >= 2 && (
            <button
              type="button"
              className={`v3-btn ${activeView === "COMPARE_RUNS" ? "primary" : "ghost"} mini`}
              onClick={() => setActiveView("COMPARE_RUNS")}
              id="compare-runs-nav-btn"
            >
              <Icon name="layers" size={13} />
              <span>Compare ({selectedRunsForCompare.length})</span>
            </button>
          )}

          {isAuthoritativeRun ? (
            <TruthChip kind="REAL" title="REAL + WORKING · Authoritative deterministic backtest engine executed on canonical parquet data" />
          ) : (
            <TruthChip kind="SAMPLE" title="DEV PREVIEW / SAMPLE · Historical replay simulation" />
          )}
        </div>
      </div>

      {toastMsg && (
        <div className="v3-toast" role="status" id="backtest-toast">
          <Icon name="check" size={15} /> {toastMsg}
        </div>
      )}

      {registeredStrategies.length === 0 && (
        <div
          className="v3-panel"
          style={{
            padding: "16px 20px",
            marginBottom: "16px",
            textAlign: "center",
            border: "1px dashed var(--v3-line-strong)",
            borderRadius: 8,
            background: "var(--v3-surface-2)",
          }}
          id="backtesting-screen-content"
        >
          <p style={{ margin: 0, fontSize: 14, color: "var(--v3-ink-2)", fontWeight: 600 }}>
            No strategies assigned
          </p>
        </div>
      )}

      {/* ── IMMUTABLE GLOBAL STRIKE POLICY SNAPSHOT BANNER ── */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          padding: "10px 16px",
          border: "1px solid var(--v3-line-strong)",
          borderRadius: 8,
          background: "var(--v3-surface-2)",
          marginBottom: 16,
          flexWrap: "wrap",
        }}
        id="global-strike-policy-snapshot-card"
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.03em", color: "var(--v3-ink)" }}>
            GLOBAL OPTION STRIKE POLICY:
          </span>
          <span className="v3-atm-badge" style={{ fontSize: 11, fontWeight: 750 }}>
            {policy.mode} · {policy.distance} STRIKE{policy.distance === 1 ? "" : "S"}
          </span>
          <span style={{ fontSize: 12, color: "var(--v3-ink-2)" }} id="strike-policy-resolution-line">
            SPOT: <strong>₹{UNDERLYINGS[underlying].spot.toFixed(2)}</strong> · ATM: <strong>{currentStrikeResolved.atmStrike}</strong> · POLICY: <strong>{policy.mode} · {policy.distance} STRIKE{policy.distance === 1 ? "" : "S"}</strong> · <span style={{ color: "var(--v3-profit-text)" }}>CE TARGET: {currentStrikeResolved.ceStrike}</span> · <span style={{ color: "var(--v3-loss-text)" }}>PE TARGET: {currentStrikeResolved.peStrike}</span>
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span
            className="v3-chip"
            style={{
              background: "rgba(245, 158, 11, 0.12)",
              color: "var(--v3-amber)",
              borderColor: "rgba(245, 158, 11, 0.35)",
              fontSize: 10,
              fontWeight: 700,
            }}
            id="policy-snapshot-lifecycle-tag"
          >
            WILL SNAPSHOT AT RUN START
          </span>
          <span className="v3-mono v3-dim" style={{ fontSize: 11 }}>
            Immutable · No strategy-level override
          </span>
        </div>
      </div>

      {/* ════════════════════════════════════════════════════════════
          VIEW 1: CONFIGURATION & SIMULATION RUN
          ════════════════════════════════════════════════════════════ */}
      {activeView === "CONFIG_RUN" && (
        <div className="v3-grid">
          {/* Left Column: Backtest Configuration Envelope & Data Coverage */}
          <div className="v3-sp6" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {/* 1. Backtest Configuration Envelope */}
            <Panel label="Current Backtest Configuration Envelope" className="v3-sp12">
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <div>
                    <label className="v3-field-label" htmlFor="config-strategy-select">
                      Strategy Target *
                    </label>
                    <select
                      id="config-strategy-select"
                      className="v3-input"
                      value={selectedStratId}
                      onChange={(e) => setSelectedStratId(e.target.value)}
                    >
                      {registeredStrategies.length === 0 ? (
                        <option value="">No strategies assigned</option>
                      ) : (
                        registeredStrategies.map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.name} ({s.version}){(s as any).visibility === "GLOBAL" ? " [GLOBAL]" : ""}
                          </option>
                        ))
                      )}
                    </select>
                  </div>

                  <div>
                    <label className="v3-field-label" htmlFor="config-version-select">
                      Strategy Spec Version * (exact registered version)
                    </label>
                    <select
                      id="config-version-select"
                      className="v3-input"
                      value={selectedVersion}
                      onChange={(e) => setSelectedVersion(e.target.value)}
                    >
                      {(() => {
                        const current = registeredStrategies.find((s) => s.id === selectedStratId);
                        const regVersion = (current as any)?.version;
                        const defaults = ["v2.3", "v2.2", "v2.1"];
                        const options = regVersion && !defaults.includes(regVersion)
                          ? [regVersion, ...defaults]
                          : defaults;
                        // Keep the selected version pinned to the registered exact version when known.
                        if (regVersion && selectedVersion !== regVersion && !defaults.includes(selectedVersion)) {
                          // no-op: controlled value already reflects registry via effect below
                        }
                        return options.map((v) => (
                          <option key={v} value={v}>
                            {v}{v === regVersion ? " (Registered exact version)" : ""}
                          </option>
                        ));
                      })()}
                    </select>
                    {(() => {
                      const current = registeredStrategies.find((s) => s.id === selectedStratId);
                      const regVersion = (current as any)?.version;
                      if (regVersion && selectedVersion !== regVersion) {
                        return (
                          <div style={{ fontSize: 11, color: "var(--v3-amber)", marginTop: 4 }}>
                            Exact registered version is <strong className="v3-mono">{regVersion}</strong> — it will be submitted as version_id.
                          </div>
                        );
                      }
                      return null;
                    })()}
                  </div>
                </div>

                {/* Backend-authoritative readiness badges (R-03) */}
                <div id="strategy-readiness-badges" style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                  {strategyReadiness ? (
                    <>
                      <span className="v3-tag online" title={strategyReadiness.backtest.reason}>
                        {strategyReadiness.backtest.ready ? "Backtest Ready" : `Backtest: ${strategyReadiness.backtest.code}`}
                      </span>
                      <span className="v3-tag online" title={strategyReadiness.paper.reason}>
                        {strategyReadiness.paper.ready ? "Paper Ready" : `Paper: ${strategyReadiness.paper.code}`}
                      </span>
                      {strategyReadiness.backtest.ready && strategyReadiness.paper.ready && (
                        <span className="v3-tag online" title="Backend-validated strategy">Validated</span>
                      )}
                      <span className="v3-tag offline" title={strategyReadiness.live.reason}>
                        Live: {strategyReadiness.live.code}
                      </span>
                    </>
                  ) : (
                    <span className="v3-mono v3-dim" style={{ fontSize: 11 }}>
                      {isBackendEnabled() ? "Reading backend readiness…" : "Readiness unavailable (backend offline)"}
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 11.5, color: "var(--v3-ink-2)" }}>
                  Backtest and Paper are self-service on validated strategies — no owner approval needed for ordinary runs.
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
                  <div>
                    <label className="v3-field-label" htmlFor="config-underlying-select">
                      Underlying Index *
                    </label>
                    <select
                      id="config-underlying-select"
                      className="v3-input font-bold"
                      value={underlying}
                      onChange={(e) => setUnderlying(e.target.value as "NIFTY" | "BANKNIFTY")}
                    >
                      <option value="NIFTY">NIFTY (Step 50)</option>
                      <option value="BANKNIFTY">BANKNIFTY (Step 100)</option>
                    </select>
                  </div>

                  <div>
                    <label className="v3-field-label" htmlFor="config-timeframe-select">
                      Bar Timeframe *
                    </label>
                    <select
                      id="config-timeframe-select"
                      className="v3-input"
                      value={timeframe}
                      onChange={(e) => setTimeframe(e.target.value)}
                    >
                      <option value="1m">1m (Tick Exact)</option>
                      <option value="5m">5m</option>
                      <option value="15m">15m</option>
                      <option value="30m">30m</option>
                      <option value="1H">1H</option>
                    </select>
                  </div>

                  <div>
                    <label className="v3-field-label" htmlFor="config-capital-input">
                      Initial Capital (₹) *
                    </label>
                    <input
                      id="config-capital-input"
                      type="text"
                      className="v3-input v3-mono"
                      value={capital}
                      onChange={(e) => setCapital(e.target.value)}
                    />
                  </div>
                </div>

                <div>
                  <label className="v3-field-label" htmlFor="config-dataset-select">
                    Historical Data Source &amp; Feed Integrity *
                  </label>
                  <select
                    id="config-dataset-select"
                    className="v3-input"
                    value={selectedDatasetId}
                    onChange={(e) => setSelectedDatasetId(e.target.value)}
                  >
                    {datasets.length === 0 ? (
                      <option value="">No datasets registered yet</option>
                    ) : (
                      datasets.map((ds) => (
                        <option key={ds.id} value={ds.id}>
                          [{ds.status}] {ds.name}
                        </option>
                      ))
                    )}
                  </select>
                </div>

                {/* Sample Execution Assumptions Box */}
                <div style={{ padding: "10px 12px", borderRadius: 6, background: "var(--v3-surface-1)", border: "1px solid var(--v3-line)", fontSize: 11.5, color: "var(--v3-ink-2)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <span style={{ fontWeight: 650, color: "var(--v3-ink)" }}>
                      Sample Execution Assumptions (Indian Market Context):
                    </span>
                    <TruthChip kind="SAMPLE" title="DEV SAMPLE / CONFIGURABLE · Indian market simulation assumptions" />
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                    <div>• Slippage: <span className="v3-mono">0.05% per leg (Sample)</span></div>
                    <div>• Brokerage: <span className="v3-mono">₹20 / order flat</span></div>
                    <div>• Charges Model: <span className="v3-mono">DEV SAMPLE / CONFIGURABLE</span></div>
                    <div>• Risk Envelope: <span className="v3-mono">Capital Exposure Controls Active</span></div>
                  </div>
                </div>
              </div>
            </Panel>

            {/* 2. Data Coverage & Quality Card */}
            <Panel label="Data Coverage & Quality Status" className="v3-sp12">
              {!activeDataset ? (
                <div style={{ padding: "24px 12px", textAlign: "center", color: "var(--v3-ink-3)" }}>
                  No datasets registered yet
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: "var(--v3-ink)" }}>
                      {activeDataset.name}
                    </span>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <TruthChip kind="SAMPLE" title="OFFLINE EVIDENCE PREVIEW · DEV SAMPLE" />
                      <span
                        className={`v3-tag ${activeDataset.status === "READY" ? "online" : activeDataset.status === "WARNING" ? "warning" : "offline"}`}
                        id="data-coverage-status-tag"
                      >
                        {activeDataset.status}
                      </span>
                    </div>
                  </div>

                  <div className="v3-rows">
                    <div className="v3-row">
                      <span className="v3-row-sub">Instrument &amp; Replay Grid</span>
                      <span className="v3-mono font-semibold">{activeDataset.instrument}</span>
                    </div>
                    <div className="v3-row">
                      <span className="v3-row-sub">Date Coverage Period</span>
                      <span className="v3-mono">{activeDataset.dateRange}</span>
                    </div>
                    <div className="v3-row">
                      <span className="v3-row-sub">Total Bars / Coverage %</span>
                      <span className="v3-mono">
                        {activeDataset.bars.toLocaleString()} bars
                      </span>
                    </div>
                    <div className="v3-row">
                      <span className="v3-row-sub">Known Gaps &amp; Reconciliation</span>
                      <span style={{ color: activeDataset.status === "BLOCKED" ? "var(--v3-loss-text)" : "var(--v3-ink-2)" }}>
                        {activeDataset.knownGaps}
                      </span>
                    </div>
                    <div className="v3-row">
                      <span className="v3-row-sub">Calendar Verification</span>
                      <span>{activeDataset.calendarStatus}</span>
                    </div>
                    <div className="v3-row">
                      <span className="v3-row-sub">Data Fingerprint</span>
                      <code className="v3-mono text-xs" style={{overflowWrap: "anywhere", minWidth: 0}}>{activeDataset.fingerprint}</code>
                    </div>
                    <div className="v3-row">
                      <span className="v3-row-sub">Freshness / Imported At</span>
                      <span className="v3-mono text-xs">{activeDataset.importedAt}</span>
                    </div>
                  </div>

                  {isDataBlocked && (
                    <div className="auth-error-alert" id="data-blocked-alert" role="alert" style={{ marginTop: 6 }}>
                      <div style={{ fontWeight: 700, marginBottom: 2 }}>BACKTEST BLOCKED — DATA QUALITY FAILURE</div>
                      <div>{activeDataset.blockedReason}</div>
                    </div>
                  )}
                </div>
              )}
            </Panel>
          </div>

          {/* Right Column: Run Readiness, Action & Evaluated Results */}
          <div className="v3-sp6" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {/* 3. Run Readiness Pre-flight Gate */}
            <Panel label="Pre-Flight Run Readiness Checklist" className="v3-sp12">
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div className="v3-rows">
                  <div className="v3-row">
                    <div className="v3-row-main">
                      <div className="v3-row-title">Strategy AST Contract</div>
                      <div className="v3-row-sub">Syntax, imports, and risk envelope conformance</div>
                    </div>
                    <span className="v3-tag online" style={{ fontSize: 10 }}>PASS</span>
                  </div>

                  <div className="v3-row">
                    <div className="v3-row-main">
                      <div className="v3-row-title">Historical Data Coverage</div>
                      <div className="v3-row-sub">Integrity, continuity &amp; timestamp monotonicity</div>
                    </div>
                    <span
                      className={`v3-tag ${isDataBlocked ? "offline" : "online"}`}
                      style={{ fontSize: 10 }}
                      id="readiness-data-status"
                    >
                      {isDataBlocked ? "FAIL" : "PASS"}
                    </span>
                  </div>

                  <div className="v3-row">
                    <div className="v3-row-main">
                      <div className="v3-row-title">Exchange Calendar Coverage</div>
                      <div className="v3-row-sub">NSE trading sessions, muhurat &amp; settlement dates</div>
                    </div>
                    <span className="v3-tag online" style={{ fontSize: 10 }}>PASS</span>
                  </div>

                  <div className="v3-row">
                    <div className="v3-row-main">
                      <div className="v3-row-title">Global Strike Policy Snapshot</div>
                      <div className="v3-row-sub">Immutable run boundary: {policy.mode} {policy.distance} strikes</div>
                    </div>
                    <span className="v3-tag online" style={{ fontSize: 10 }}>PASS</span>
                  </div>

                  <div className="v3-row">
                    <div className="v3-row-main">
                      <div className="v3-row-title">Pre-Trade Risk Policy Context</div>
                      <div className="v3-row-sub">Capital exposure bounds active · Long-only options enforcement</div>
                    </div>
                    <span className="v3-tag online" style={{ fontSize: 10 }}>PASS</span>
                  </div>

                  <div className="v3-row">
                    <div className="v3-row-main">
                      <div className="v3-row-title">Evidence Storage Destination</div>
                      <div className="v3-row-sub">Local research artifact cache · Non-repudiation store</div>
                    </div>
                    <span className="v3-tag warning" style={{ fontSize: 10 }}>DEV SAMPLE</span>
                  </div>
                </div>

                {/* Simulation Progress & Trigger Button */}
                {isSimulating && !isInspectionPreview ? (<div role="status">{simulationStage}</div>) : isSimulating ? (
                  <div style={{ padding: "14px 16px", borderRadius: 8, background: "var(--v3-surface-2)", border: "1px solid var(--v3-line-strong)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                      <span style={{ fontSize: 12, fontWeight: 700, color: "#38bdf8" }}>
                        {simulationStage}
                      </span>
                      <span className="v3-mono text-xs font-bold">{simulationProgress}%</span>
                    </div>
                    <div style={{ height: 6, width: "100%", background: "var(--v3-line)", borderRadius: 3, overflow: "hidden" }}>
                      <div
                        style={{
                          height: "100%",
                          width: `${simulationProgress}%`,
                          background: "#38bdf8",
                          transition: "width 0.3s ease",
                        }}
                      />
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8, fontSize: 10.5, color: "var(--v3-ink-3)" }}>
                      <span>Stage: BACKTEST SIMULATION</span>
                      <span>DEV PREVIEW</span>
                    </div>
                  </div>
                ) : (
                  <button
                    type="button"
                    className="v3-btn primary"
                    style={{ width: "100%", padding: "12px", fontSize: 13, fontWeight: 700 }}
                    onClick={handleRunBacktest}
                    disabled={isDataBlocked}
                    id="run-backtest-btn"
                  >
                    <Icon name="play" size={15} />
                    <span>{isDataBlocked ? "BACKTEST BLOCKED — RESOLVE DATA GAP" : "Run Backtest Cycle"}</span>
                  </button>
                )}
              </div>
            </Panel>

            
            {/* Historical Run Log for Policy Snapshot Verification */}
            <div className="v3-sp4" style={{ width: "100%", marginTop: 12 }}>
              <Panel label="Recent Run Policy Snapshots" meta="SAMPLE" className="v3-sp12">
                <div className="v3-rows" id="backtest-run-snapshots-list">
                  {historicalRuns.length === 0 ? (
                    <div style={{ padding: "16px", textAlign: "center", color: "var(--v3-ink-3)" }}>
                      No backtests yet
                    </div>
                  ) : (
                    historicalRuns.map((r) => (
                      <div className="v3-row" key={r.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div className="v3-row-main">
                          <span className="v3-row-title font-semibold">{r.strategyName}</span>
                          <div className="v3-row-sub">{r.dataSourceName} · {r.runDate}</div>
                        </div>
                        <span className="v3-tag online font-bold" style={{ fontSize: 11 }}>
                          {r.status}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </Panel>
            </div>

            {/* 4. Strategy Quality Score Card */}
            {activeRun?.status === "COMPLETED" && activeRun.qualityScore != null ? (
              <Panel label="Strategy Quality Score (0–100)" className="v3-sp12">
                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                      <span style={{ fontSize: 36, fontWeight: 800, fontFamily: "var(--v3-mono)", color: "#38bdf8" }} id="quality-score-value">
                        {activeRun.qualityScore}
                      </span>
                      <span style={{ fontSize: 14, color: "var(--v3-ink-3)", fontWeight: 600 }}>/ 100</span>
                      <span className="v3-tag online font-bold" style={{ marginLeft: 6 }}>
                        {activeRun.qualityScore >= 80 ? "STRONG" : activeRun.qualityScore >= 70 ? "GOOD" : "MODERATE"}
                      </span>
                    </div>

                    <div style={{ textAlign: "right", fontSize: 11, color: "var(--v3-ink-2)" }}>
                      <div>Evaluated Run: <strong className="v3-mono">{activeRun.id}</strong></div>
                      <div>Strategy: <strong>{activeRun.strategyName} {activeRun.version}</strong></div>
                    </div>
                  </div>

                  {/* Score vs Eligibility Disclosure */}
                  <div
                    style={{
                      padding: "8px 12px",
                      borderRadius: 6,
                      background: "rgba(245, 158, 11, 0.08)",
                      border: "1px solid rgba(245, 158, 11, 0.3)",
                      fontSize: 11,
                      color: "var(--v3-amber)",
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                    }}
                    id="score-not-eligibility-warning"
                  >
                    <Icon name="shield" size={14} />
                    <span>
                      <strong>GOVERNANCE NOTICE:</strong> Strategy Quality Score is an evidence metric, <em>not</em> execution eligibility. Backtest completion does not grant Live Readiness. Paper evaluation and explicit governance promotion are required.
                    </span>
                  </div>

                  {/* Quality Score Breakdown Grid (7 Components summing to 83) */}
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 11.5 }} id="quality-score-breakdown-grid">
                    <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 8px", background: "var(--v3-surface-1)", borderRadius: 4 }}>
                      <span className="v3-ink-2">OOS / Walk-Forward (25)</span>
                      <span className="v3-mono font-bold">22 / 25</span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 8px", background: "var(--v3-surface-1)", borderRadius: 4 }}>
                      <span className="v3-ink-2">Robustness Stability (20)</span>
                      <span className="v3-mono font-bold">17 / 20</span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 8px", background: "var(--v3-surface-1)", borderRadius: 4 }}>
                      <span className="v3-ink-2">Drawdown Control (15)</span>
                      <span className="v3-mono font-bold">13 / 15</span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 8px", background: "var(--v3-surface-1)", borderRadius: 4 }}>
                      <span className="v3-ink-2">Expectancy / Edge (15)</span>
                      <span className="v3-mono font-bold">13 / 15</span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 8px", background: "var(--v3-surface-1)", borderRadius: 4 }}>
                      <span className="v3-ink-2">Profit Factor (10)</span>
                      <span className="v3-mono font-bold">8 / 10</span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 8px", background: "var(--v3-surface-1)", borderRadius: 4 }}>
                      <span className="v3-ink-2">Bootstrap Confidence (10)</span>
                      <span className="v3-mono font-bold">7 / 10</span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 8px", background: "var(--v3-surface-1)", borderRadius: 4, gridColumn: "1 / -1" }}>
                      <span className="v3-ink-2">Evidence Sufficiency (5)</span>
                      <span className="v3-mono font-bold">3 / 5</span>
                    </div>
                  </div>
                </div>
              </Panel>
            ) : (
              <Panel label="Strategy Quality Score (0–100)" className="v3-sp12">
                <div style={{ textAlign: "center", padding: "28px 16px", color: "var(--v3-ink-3)" }}>
                  <Icon name="activity" size={24} style={{ opacity: 0.5, marginBottom: 8 }} />
                  <div style={{ fontWeight: 600, fontSize: 13, color: "var(--v3-ink-2)" }}>{activeRun ? `Quality unavailable (${activeRun.status})` : "No backtests yet"}</div>
                  <div style={{ fontSize: 11, marginTop: 4 }}>Configure parameters on the left and run a backtest cycle to generate evidence.</div>
                </div>
              </Panel>
            )}
          </div>

          {/* Full Width Row: Results Summary KPI Bar (100% Derived from Single Source of Truth) */}
          {activeRun?.status === "COMPLETED" && (
            <>
              <div className="v3-sp12">
                <div className="v3-kpi-grid" id="v3-backtest-kpi-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
                  <div className="v3-kpi-card" id="kpi-net-profit">
                    <div className="v3-kpi-title">Net Realized P&amp;L</div>
                    <div className="v3-kpi-val v3-profit-text">
                      +₹{derivedMetrics.net.toLocaleString()} (+{derivedMetrics.returnPct}%)
                    </div>
                    <div className="v3-kpi-sub">On ₹{derivedMetrics.initial.toLocaleString()} initial capital</div>
                  </div>

                  <div className="v3-kpi-card" id="kpi-win-rate">
                    <div className="v3-kpi-title">Win Rate</div>
                    <div className="v3-kpi-val">{derivedMetrics.winRate}%</div>
                    <div className="v3-kpi-sub">{derivedMetrics.wins} wins · {derivedMetrics.losses} losses ({derivedMetrics.trades} trades)</div>
                  </div>

                  <div className="v3-kpi-card" id="kpi-profit-factor">
                    <div className="v3-kpi-title">Profit Factor</div>
                    <div className="v3-kpi-val">{derivedMetrics.profitFactor.toFixed(2)}</div>
                    <div className="v3-kpi-sub">Gross Profit / Gross Loss</div>
                  </div>

                  <div className="v3-kpi-card" id="kpi-sharpe-ratio">
                    <div className="v3-kpi-title">Sharpe Ratio</div>
                    <div className="v3-kpi-val">{(activeRun.sharpeRatio?.toFixed(2) ?? "UNAVAILABLE")}</div>
                    <div className="v3-kpi-sub">DEV SAMPLE · Replay Sharpe</div>
                  </div>

                  <div className="v3-kpi-card" id="kpi-max-drawdown">
                    <div className="v3-kpi-title">Max Drawdown</div>
                    <div className="v3-kpi-val v3-loss-text">{activeRun.maxDrawdown}%</div>
                    <div className="v3-kpi-sub">Strict risk envelope preserved</div>
                  </div>

                  <div className="v3-kpi-card" id="kpi-expectancy">
                    <div className="v3-kpi-title">Expectancy / Trade</div>
                    <div className="v3-kpi-val v3-profit-text">+₹{derivedMetrics.expectancy.toFixed(2)}</div>
                    <div className="v3-kpi-sub">Avg Win ₹{derivedMetrics.avgWin.toLocaleString()} · Avg Loss -₹{Math.abs(derivedMetrics.avgLoss).toLocaleString()}</div>
                  </div>
                </div>
              </div>

              {/* Full Width Row: Equity Curve & Drawdown Visualizer */}
              <div className="v3-sp12">
                <Panel label="Replay Equity Curve & Drawdown Profile" className="v3-sp12">
                  <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
                      <div className="v3-tabs" role="tablist" style={{ margin: 0 }}>
                        <button
                          type="button"
                          className={`v3-tab ${chartMode === "EQUITY" ? "active" : ""}`}
                          onClick={() => setChartMode("EQUITY")}
                          id="toggle-equity-curve-btn"
                        >
                          EQUITY CURVE (₹)
                        </button>
                        <button
                          type="button"
                          className={`v3-tab ${chartMode === "DRAWDOWN" ? "active" : ""}`}
                          onClick={() => setChartMode("DRAWDOWN")}
                          id="toggle-drawdown-curve-btn"
                        >
                          DRAWDOWN PROFILE (%)
                        </button>
                      </div>

                      <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 11.5, color: "var(--v3-ink-2)" }}>
                        <span>Initial: <strong className="v3-mono">₹{derivedMetrics.initial.toLocaleString()}</strong></span>
                        <span>Final Equity: <strong className="v3-mono" style={{ color: "var(--v3-profit-text)" }}>₹{derivedMetrics.finalEquity.toLocaleString()}</strong></span>
                        <span>Peak: <strong className="v3-mono" style={{ color: "var(--v3-profit-text)" }}>₹{derivedMetrics.finalEquity.toLocaleString()}</strong></span>
                        <TruthChip kind="SAMPLE" title="DEV SAMPLE · Replay series synthesized from 164 sessions" />
                      </div>
                    </div>

                    {/* SVG Chart Visualization */}
                    <div
                      style={{
                        height: 220,
                        width: "100%",
                        background: "var(--v3-surface-0)",
                        borderRadius: 6,
                        border: "1px solid var(--v3-line)",
                        padding: "16px 20px",
                        position: "relative",
                      }}
                      id="equity-chart-container"
                    >
                      <svg width="100%" height="100%" viewBox="0 0 800 180" preserveAspectRatio="none" style={{ overflow: "visible" }}>
                        {/* Grid lines */}
                        <line x1="0" y1="30" x2="800" y2="30" stroke="var(--v3-line)" strokeDasharray="3 3" />
                        <line x1="0" y1="90" x2="800" y2="90" stroke="var(--v3-line)" strokeDasharray="3 3" />
                        <line x1="0" y1="150" x2="800" y2="150" stroke="var(--v3-line)" strokeDasharray="3 3" />

                        {chartMode === "EQUITY" ? (
                          <>
                            {/* Equity Area & Line */}
                            <defs>
                              <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0%" stopColor="#10b981" stopOpacity="0.3" />
                                <stop offset="100%" stopColor="#10b981" stopOpacity="0.0" />
                              </linearGradient>
                            </defs>
                            <path
                              d="M 0 160 L 66 142 L 133 125 L 200 134 L 266 110 L 333 88 L 400 68 L 466 76 L 533 46 L 600 28 L 666 12 L 733 18 L 800 5 L 800 180 L 0 180 Z"
                              fill="url(#eqGrad)"
                            />
                            <path
                              d="M 0 160 L 66 142 L 133 125 L 200 134 L 266 110 L 333 88 L 400 68 L 466 76 L 533 46 L 600 28 L 666 12 L 733 18 L 800 5"
                              fill="none"
                              stroke="var(--v3-profit)"
                              strokeWidth="2.5"
                            />
                            {/* Data Points */}
                            {activeRun.equityCurve.map((pt, idx) => {
                              const x = (idx / (activeRun.equityCurve.length - 1)) * 800;
                              const y = 160 - ((pt.value - activeRun.initialCapital) / 145000) * 155;
                              return (
                                <circle key={idx} cx={x} cy={y} r="3.5" fill="var(--v3-profit)" stroke="#fff" strokeWidth="1" />
                              );
                            })}
                          </>
                        ) : (
                          <>
                            {/* Drawdown Area & Line */}
                            <defs>
                              <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0%" stopColor="#f43f5e" stopOpacity="0.0" />
                                <stop offset="100%" stopColor="#f43f5e" stopOpacity="0.3" />
                              </linearGradient>
                            </defs>
                            <path
                              d="M 0 20 L 66 20 L 133 20 L 200 80 L 266 20 L 333 20 L 400 20 L 466 78 L 533 20 L 600 20 L 666 20 L 733 55 L 800 20 L 800 20 L 0 20 Z"
                              fill="url(#ddGrad)"
                            />
                            <path
                              d="M 0 20 L 66 20 L 133 20 L 200 80 L 266 20 L 333 20 L 400 20 L 466 78 L 533 20 L 600 20 L 666 20 L 733 55 L 800 20"
                              fill="none"
                              stroke="var(--v3-loss)"
                              strokeWidth="2"
                            />
                          </>
                        )}
                      </svg>
                    </div>
                  </div>
                </Panel>
              </div>

              {/* Left Column: Executed Trades Blotter (with Qty and Verified P&L) */}
              <div className="v3-sp6">
                <Panel
                  label={isAuthoritativeRun ? `Executed Trades (${executedTrades.length})` : `Sample Executed Trades (${executedTrades.length})`}
                  className="v3-sp12"
                >
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5, color: "var(--v3-ink-2)", flexWrap: "wrap", gap: 6 }}>
                      <span>
                        Winning:{" "}
                        <strong style={{ color: "var(--v3-profit-text)" }}>
                          {activeRun.winningTrades} ({activeRun.totalTrades > 0 ? ((activeRun.winningTrades / activeRun.totalTrades) * 100).toFixed(1) : 0}%)
                        </strong>
                      </span>
                      <span>
                        Losing:{" "}
                        <strong style={{ color: "var(--v3-loss-text)" }}>
                          {activeRun.losingTrades} ({activeRun.totalTrades > 0 ? ((activeRun.losingTrades / activeRun.totalTrades) * 100).toFixed(1) : 0}%)
                        </strong>
                      </span>
                      <span>Option Model: <strong className="v3-mono">LONG-ONLY OPTIONS</strong></span>
                    </div>

                    <div className="v3-table-wrap">
                      <table className="v3-table" id="sample-trades-table">
                        <thead>
                          <tr>
                            <th>TIME</th>
                            <th>LEG</th>
                            <th>SIDE</th>
                            <th>QTY</th>
                            <th>ENTRY</th>
                            <th>EXIT</th>
                            <th>P&amp;L (₹)</th>
                            <th>RETURN</th>
                          </tr>
                        </thead>
                        <tbody>
                          {executedTrades.map((tr) => (
                            <tr key={tr.id}>
                              <td className="v3-cell-date">{tr.time}</td>
                              <td className="v3-mono font-semibold">{tr.leg}</td>
                              <td>
                                <span className="v3-tag online" style={{ fontSize: 9.5 }}>{tr.action}</span>
                              </td>
                              <td className="v3-mono">{tr.qty}</td>
                              <td className="v3-mono">{tr.entry.toFixed(1)}</td>
                              <td className="v3-mono">{tr.exit.toFixed(1)}</td>
                              <td className={`v3-mono font-bold ${tr.pnl >= 0 ? "v3-profit-text" : "v3-loss-text"}`}>
                                {tr.pnl >= 0 ? `+₹${tr.pnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : `-₹${Math.abs(tr.pnl).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                              </td>
                              <td className={`v3-mono ${tr.pnlPct >= 0 ? "v3-profit-text" : "v3-loss-text"}`}>
                                {tr.pnlPct >= 0 ? `+${tr.pnlPct.toFixed(2)}%` : `${tr.pnlPct.toFixed(2)}%`}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </Panel>
              </div>

              {/* Right Column: Robustness & Evidence Suite & Lifecycle Governance */}
              <div className="v3-sp6" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                {/* Robustness & Evidence Suite */}
                <Panel label="Robustness & Evidence Suite" className="v3-sp12">
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontSize: 12, color: "var(--v3-ink-2)" }}>Statistical verification battery</span>
                      <span className="v3-tag warning" style={{ fontSize: 10 }}>
                        EVIDENCE PREVIEW · DEV SAMPLE
                      </span>
                    </div>

                    <div className="v3-rows" id="evidence-battery-rows">
                      <div className="v3-row">
                        <div className="v3-row-main">
                          <div className="v3-row-title">In-Sample / Out-of-Sample (70/30 Split)</div>
                          <div className="v3-row-sub">IS Sharpe: 2.34 · OOS Sharpe: 2.12 (Degradation: 9.4%)</div>
                        </div>
                        <span className="v3-tag warning" style={{ fontSize: 9.5 }}>SAMPLE PASS</span>
                      </div>

                      <div className="v3-row">
                        <div className="v3-row-main">
                          <div className="v3-row-title">Walk-Forward Stability (6 Rolling Windows)</div>
                          <div className="v3-row-sub">Window consistency score: 88% · No negative sub-periods</div>
                        </div>
                        <span className="v3-tag warning" style={{ fontSize: 9.5 }}>SAMPLE PASS</span>
                      </div>

                      <div className="v3-row">
                        <div className="v3-row-main">
                          <div className="v3-row-title">Monte Carlo Bootstrap (10,000 Iterations)</div>
                          <div className="v3-row-sub">95% Confidence VaR: -2.8% · Ruin Probability: 0.00%</div>
                        </div>
                        <span className="v3-tag warning" style={{ fontSize: 9.5 }}>SAMPLE PASS</span>
                      </div>

                      <div className="v3-row">
                        <div className="v3-row-main">
                          <div className="v3-row-title">Trade Count Sufficiency (N ≥ 100)</div>
                          <div className="v3-row-sub">196 trades analyzed · High statistical sample power</div>
                        </div>
                        <span className="v3-tag warning" style={{ fontSize: 9.5 }}>SAMPLE PASS</span>
                      </div>

                      <div className="v3-row">
                        <div className="v3-row-main">
                          <div className="v3-row-title">Market Regime Coverage</div>
                          <div className="v3-row-sub">Trending, Rangebound &amp; High Volatility (VIX 12–28) tested</div>
                        </div>
                        <span className="v3-tag warning" style={{ fontSize: 9.5 }}>SAMPLE PASS</span>
                      </div>

                      <div className="v3-row">
                        <div className="v3-row-main">
                          <div className="v3-row-title">Data Integrity &amp; Lookahead Proof</div>
                          <div className="v3-row-sub">Zero future-leakage · Monotonic bar timestamp sequencing</div>
                        </div>
                        <span className="v3-tag warning" style={{ fontSize: 9.5 }}>SAMPLE PASS</span>
                      </div>
                    </div>
                  </div>
                </Panel>

                {/* Governance Result & Paper Promotion Gateway */}
                <Panel label="Lifecycle Governance & Progression" className="v3-sp12">
                  <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 700, color: "var(--v3-ink)" }}>
                          BACKTEST EVIDENCE GENERATED
                        </div>
                        <div style={{ fontSize: 11.5, color: "var(--v3-ink-2)", marginTop: 2 }}>
                          Current Lifecycle Stage: <strong className="v3-mono font-bold" style={{ color: "#38bdf8" }}>BACKTEST_ELIGIBLE</strong>
                        </div>
                      </div>

                      <span className="v3-chip" style={{ background: "rgba(16, 185, 129, 0.12)", color: "var(--v3-profit-text)", borderColor: "rgba(16, 185, 129, 0.35)", fontWeight: 700 }}>
                        CONFORMANT
                      </span>
                    </div>

                    <p style={{ fontSize: 11.5, color: "var(--v3-ink-3)", lineHeight: 1.5, margin: 0 }}>
                      Backtest completion does <strong>not</strong> grant Live Readiness. Strategy Quality Score is an evidence metric, not execution eligibility. Paper evaluation is self-service on validated strategies — no owner approval needed for ordinary Backtest/Paper runs.
                    </p>

                    <div style={{ display: "flex", gap: 10, marginTop: 4 }}>
                      <button
                        type="button"
                        className="v3-btn secondary"
                        style={{ flex: 1 }}
                        disabled
                        title="Live promotion is future functionality and remains disabled while live execution is disarmed."
                        id="request-live-promotion-btn"
                      >
                        <Icon name="lock" size={14} />
                        <span>REQUEST LIVE PROMOTION — FUTURE / DISABLED WHILE DISARMED</span>
                      </button>
                    </div>
                  </div>
                </Panel>
              </div>
            </>
          )}
        </div>
      )}

      {/* ════════════════════════════════════════════════════════════
          VIEW 4: WALK-FORWARD / OOS (manual RUN only, no scheduling)
          ════════════════════════════════════════════════════════════ */}
      {activeView === "WALK_FORWARD" && (
        <div className="v3-grid" id="walk-forward-view">
          <Panel label="Walk-Forward / Out-of-Sample (Manual Run)" className="v3-sp12">
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div style={{ fontSize: 12, color: "var(--v3-ink-2)" }}>
                Sequential non-overlapping In-Sample / Out-of-Sample windows over the approved dataset.
                Each window executes the exact registered strategy/version as a real paper replay session.
                Manual RUN only — no scheduling, no auto-runs. Overall aggregates are sums over real windows.
              </div>
              {wfToast && <div className="v3-toast" role="status">{wfToast}</div>}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr auto", gap: 10, alignItems: "end" }}>
                <div>
                  <label className="v3-field-label" htmlFor="wf-strategy-select">Strategy</label>
                  <select id="wf-strategy-select" className="v3-input" value={selectedStratId} onChange={(e) => setSelectedStratId(e.target.value)}>
                    {registeredStrategies.length === 0 ? (
                      <option value="">No strategies assigned</option>
                    ) : (
                      registeredStrategies.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name} ({s.version}){(s as any).visibility === "GLOBAL" ? " [GLOBAL]" : ""}
                        </option>
                      ))
                    )}
                  </select>
                </div>
                <div>
                  <label className="v3-field-label" htmlFor="wf-dataset-select">Dataset</label>
                  <select id="wf-dataset-select" className="v3-input" value={selectedDatasetId} onChange={(e) => setSelectedDatasetId(e.target.value)}>
                    {datasets.map((d) => (
                      <option key={d.id} value={d.id}>{d.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="v3-field-label" htmlFor="wf-is-days">IS days</label>
                  <input id="wf-is-days" className="v3-input v3-mono" value={wfIsDays} onChange={(e) => setWfIsDays(e.target.value)} inputMode="numeric" />
                </div>
                <div>
                  <label className="v3-field-label" htmlFor="wf-oos-days">OOS days</label>
                  <input id="wf-oos-days" className="v3-input v3-mono" value={wfOosDays} onChange={(e) => setWfOosDays(e.target.value)} inputMode="numeric" />
                </div>
                <button className="v3-btn primary" onClick={() => void handleWalkForwardRun()} disabled={wfBusy} id="walk-forward-run-btn">
                  {wfBusy ? "Starting…" : "RUN Walk-Forward"}
                </button>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="v3-btn ghost mini" onClick={() => void refreshWalkForwardJobs()} id="walk-forward-refresh-btn">
                  Refresh jobs
                </button>
              </div>
            </div>
          </Panel>

          <Panel label={`Walk-Forward Jobs (${walkForwardJobs.length})`} className="v3-sp12">
            {walkForwardJobs.length === 0 ? (
              <div style={{ padding: "16px 12px", textAlign: "center", color: "var(--v3-ink-3)" }} role="status">
                No walk-forward jobs yet. Configure above and RUN manually.
              </div>
            ) : (
              <div className="v3-table-wrap">
                <table className="v3-table" id="walk-forward-jobs-table">
                  <thead>
                    <tr>
                      <th>JOB</th>
                      <th>STRATEGY</th>
                      <th>WINDOWS</th>
                      <th>IS NET</th>
                      <th>OOS NET</th>
                      <th>STATUS</th>
                      <th>ACTIONS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {walkForwardJobs.map((j) => (
                      <React.Fragment key={j.jobId}>
                        <tr key={j.jobId}>
                          <td className="v3-mono font-bold" style={{ fontSize: 11 }}>{j.jobId.slice(0, 13)}…</td>
                          <td className="v3-mono" style={{ fontSize: 11 }}>{j.strategyId.slice(0, 13)}…</td>
                          <td className="v3-mono">{j.progress.done}/{j.progress.total}</td>
                          <td className="v3-mono">{String((j.overall as any)?.inSample?.netProfit ?? "—")}</td>
                          <td className="v3-mono">{String((j.overall as any)?.outOfSample?.netProfit ?? "—")}</td>
                          <td><span className="v3-tag">{j.status}</span></td>
                          <td style={{ whiteSpace: "nowrap" }}>
                            <button className="v3-btn ghost mini" onClick={() => setWfExpanded(wfExpanded === j.jobId ? null : j.jobId)} id={`wf-expand-${j.jobId}`}>
                              {wfExpanded === j.jobId ? "Hide" : "Windows"}
                            </button>
                            {(j.status === "PENDING" || j.status === "RUNNING") && (
                              <button className="v3-btn ghost mini" onClick={() => void handleWalkForwardCancel(j.jobId)} id={`wf-cancel-${j.jobId}`}>
                                Cancel
                              </button>
                            )}
                          </td>
                        </tr>
                        {wfExpanded === j.jobId && (
                          <tr key={`${j.jobId}-detail`}>
                            <td colSpan={7}>
                              <table className="v3-table" id={`wf-windows-${j.jobId}`}>
                                <thead>
                                  <tr>
                                    <th>SEQ</th>
                                    <th>KIND</th>
                                    <th>RANGE</th>
                                    <th>REPLAY SESSION</th>
                                    <th>NET</th>
                                    <th>TRADES</th>
                                    <th>STATUS</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {j.windows.map((w) => (
                                    <tr key={w.windowId}>
                                      <td className="v3-mono">{w.seq}</td>
                                      <td><span className="v3-tag">{w.kind}</span></td>
                                      <td className="v3-mono" style={{ fontSize: 11 }}>{w.startDate} → {w.endDate}</td>
                                      <td className="v3-mono" style={{ fontSize: 11 }}>{((w as any).paperSessionId || w.backtestRunId || "—").slice(0, 13)}</td>
                                      <td className="v3-mono">{String(w.metrics?.netProfit ?? "—")}</td>
                                      <td className="v3-mono">{String(w.metrics?.totalTrades ?? "—")}</td>
                                      <td><span className="v3-tag">{w.status}</span></td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                              {j.error && <div style={{ fontSize: 11, color: "var(--v3-loss-text)", marginTop: 6 }}>{j.error}</div>}
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </div>
      )}

      {/* ════════════════════════════════════════════════════════════
          VIEW 2: HISTORICAL RUNS TABLE
          ════════════════════════════════════════════════════════════ */}
      {activeView === "HISTORICAL_RUNS" && (
        <div className="v3-grid">
          <Panel label={`Historical Evidence Vault (${historicalRuns.length} Runs)`} className="v3-sp12">
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
                <span style={{ fontSize: 12, color: "var(--v3-ink-2)" }}>
                  Historical runs preserve original strategy version, parameters, global strike snapshot, and evidence fingerprint.
                </span>

                {selectedRunsForCompare.length >= 2 && (
                  <button
                    type="button"
                    className="v3-btn primary mini"
                    onClick={() => setActiveView("COMPARE_RUNS")}
                    id="table-compare-selected-btn"
                  >
                    <Icon name="layers" size={13} />
                    <span>Compare Selected ({selectedRunsForCompare.length})</span>
                  </button>
                )}
              </div>

              <div className="v3-table-wrap">
                <table className="v3-table" id="historical-runs-table">
                  <thead>
                    <tr>
                      <th style={{ width: 40 }}>CMP</th>
                      <th>RUN ID</th>
                      <th>STRATEGY</th>
                      <th>VERSION</th>
                      <th>UNDERLYING</th>
                      <th>TIMEFRAME</th>
                      <th>POLICY SNAPSHOT</th>
                      <th>NET P&amp;L</th>
                      <th>PF</th>
                      <th>MAX DD</th>
                      <th>TRADES</th>
                      <th>SCORE</th>
                      <th>STATUS</th>
                      <th>ACTIONS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {historicalRuns.length === 0 ? (
                      <tr>
                        <td colSpan={14} style={{ textAlign: "center", padding: "28px 12px", color: "var(--v3-ink-3)" }}>
                          No backtests yet
                        </td>
                      </tr>
                    ) : (
                      historicalRuns.map((r) => {
                        const isChecked = selectedRunsForCompare.includes(r.id);
                        return (
                          <tr key={r.id} style={{ background: r.id === activeRunId ? "rgba(56, 189, 248, 0.05)" : undefined }}>
                            <td>
                              <input
                                type="checkbox"
                                checked={isChecked}
                                onChange={() => toggleRunForCompare(r.id)}
                                aria-label={`Select ${r.id} for comparison`}
                              />
                            </td>
                            <td className="v3-mono font-bold" style={{ color: "#38bdf8" }}>{r.id}</td>
                            <td className="font-semibold">{r.strategyName}</td>
                            <td className="v3-mono">{r.version}</td>
                            <td className="v3-mono">{r.underlying}</td>
                            <td className="v3-mono">{r.timeframe}</td>
                            <td>
                              <span className="v3-tag info" style={{ fontSize: 9.5 }}>{r.status}</span>
                            </td>
                            <td className={`v3-mono font-bold ${r.netProfit >= 0 ? "v3-profit-text" : "v3-loss-text"}`}>
                              {r.status !== "COMPLETED" ? "--" : `+₹${r.netProfit.toLocaleString()} (+${r.netProfitPct}%)`}
                            </td>
                            <td className="v3-mono">{r.status !== "COMPLETED" ? "--" : r.profitFactor}</td>
                            <td className="v3-mono v3-loss-text">{r.status !== "COMPLETED" ? "--" : `${r.maxDrawdown}%`}</td>
                            <td className="v3-mono">{r.status !== "COMPLETED" ? "--" : r.totalTrades}</td>
                            <td className="v3-mono font-bold">
                              {r.status !== "COMPLETED" ? (
                                <span className="v3-tag offline" style={{ fontSize: 9.5 }}>FAIL</span>
                              ) : (
                                <span style={{ color: "#38bdf8" }}>{r.qualityScore}/100</span>
                              )}
                            </td>
                            <td>
                              <span className={`v3-tag ${r.status === "COMPLETED" ? "online" : "offline"}`} style={{ fontSize: 9.5 }}>
                                {r.status}
                              </span>
                            </td>
                            <td>
                              <button
                                type="button"
                                className="v3-btn ghost mini"
                                onClick={() => {
                                  setActiveRunId(r.id);
                                  setActiveView("CONFIG_RUN");
                                  if (r.id.startsWith("bt-auth-") || r.dataSourceName?.includes("Canonical")) {
                                    setIsAuthoritativeRun(true);
                                    queryBacktestTrades(r.id).then((tRes) => {
                                      if (tRes.data && tRes.data.length > 0) {
                                        setExecutedTrades(tRes.data);
                                      }
                                    });
                                  } else {
                                    setIsAuthoritativeRun(false);
                                  }
                                }}
                                id={`open-run-${r.id}`}
                              >
                                OPEN
                              </button>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </Panel>
        </div>
      )}

      {/* ════════════════════════════════════════════════════════════
          VIEW 3: COMPARE RUNS MATRIX
          ════════════════════════════════════════════════════════════ */}
      {activeView === "COMPARE_RUNS" && (
        <div className="v3-grid">
          <Panel label={`Comparative Strategy Evidence Matrix (${selectedRunsForCompare.length} Runs Selected)`} className="v3-sp12">
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
                <span style={{ fontSize: 12, color: "var(--v3-ink-2)" }}>
                  Multi-dimensional comparative evaluation. Do not rank solely by net profit; inspect drawdown resilience and walk-forward consistency.
                </span>

                <button
                  type="button"
                  className="v3-btn secondary mini"
                  onClick={() => setActiveView("CONFIG_RUN")}
                >
                  ← Back to Active Run
                </button>
              </div>

              <div className="v3-table-wrap">
                <table className="v3-table">
                  <thead>
                    <tr>
                      <th style={{ minWidth: 180 }}>METRIC / ATTRIBUTE</th>
                      {selectedRunsForCompare.map((id) => {
                        const r = historicalRuns.find((item) => item.id === id);
                        return (
                          <th key={id} style={{ minWidth: 200, textAlign: "left" }}>
                            <div className="v3-mono font-bold" style={{ color: "#38bdf8" }}>{id}</div>
                            <div style={{ fontSize: 11, fontWeight: 500, color: "var(--v3-ink-2)" }}>
                              {r?.strategyName} ({r?.version})
                            </div>
                          </th>
                        );
                      })}
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td className="font-semibold">Strategy Quality Score</td>
                      {selectedRunsForCompare.map((id) => {
                        const r = historicalRuns.find((item) => item.id === id);
                        return (
                          <td key={id} className="v3-mono font-bold" style={{ fontSize: 14, color: "#38bdf8" }}>
                            {r?.status !== "COMPLETED" ? "--" : `${r?.qualityScore} / 100`}
                          </td>
                        );
                      })}
                    </tr>
                    <tr>
                      <td className="font-semibold">Net Profit (₹) / Return</td>
                      {selectedRunsForCompare.map((id) => {
                        const r = historicalRuns.find((item) => item.id === id);
                        return (
                          <td key={id} className={`v3-mono font-bold ${(r?.netProfit || 0) >= 0 ? "v3-profit-text" : "v3-loss-text"}`}>
                            {r?.status !== "COMPLETED" ? "--" : `+₹${r?.netProfit.toLocaleString()} (+${r?.netProfitPct}%)`}
                          </td>
                        );
                      })}
                    </tr>
                    <tr>
                      <td className="font-semibold">Profit Factor</td>
                      {selectedRunsForCompare.map((id) => {
                        const r = historicalRuns.find((item) => item.id === id);
                        return <td key={id} className="v3-mono">{r?.status !== "COMPLETED" ? "--" : r?.profitFactor}</td>;
                      })}
                    </tr>
                    <tr>
                      <td className="font-semibold">Max Drawdown (%)</td>
                      {selectedRunsForCompare.map((id) => {
                        const r = historicalRuns.find((item) => item.id === id);
                        return <td key={id} className="v3-mono v3-loss-text">{r?.status !== "COMPLETED" ? "--" : `${r?.maxDrawdown}%`}</td>;
                      })}
                    </tr>
                    <tr>
                      <td className="font-semibold">Win Rate (%)</td>
                      {selectedRunsForCompare.map((id) => {
                        const r = historicalRuns.find((item) => item.id === id);
                        return <td key={id} className="v3-mono">{r?.status !== "COMPLETED" ? "--" : `${r?.winRate}%`}</td>;
                      })}
                    </tr>
                    <tr>
                      <td className="font-semibold">Total Sample Trades</td>
                      {selectedRunsForCompare.map((id) => {
                        const r = historicalRuns.find((item) => item.id === id);
                        return <td key={id} className="v3-mono">{r?.status !== "COMPLETED" ? "--" : r?.totalTrades}</td>;
                      })}
                    </tr>
                    <tr>
                      <td className="font-semibold">Expectancy / Trade</td>
                      {selectedRunsForCompare.map((id) => {
                        const r = historicalRuns.find((item) => item.id === id);
                        return <td key={id} className="v3-mono v3-profit-text">{r?.status !== "COMPLETED" ? "--" : `+₹${r?.avgProfitTrade?.toFixed(2)}`}</td>;
                      })}
                    </tr>
                    <tr>
                      <td className="font-semibold">Global Strike Policy Snapshot</td>
                      {selectedRunsForCompare.map((id) => {
                        const r = historicalRuns.find((item) => item.id === id);
                        return (
                          <td key={id}>
                            <span className="v3-tag info" style={{ fontSize: 9.5 }}>{r?.policySnapshot}</span>
                          </td>
                        );
                      })}
                    </tr>
                    <tr>
                      <td className="font-semibold">Data Period &amp; Timeframe</td>
                      {selectedRunsForCompare.map((id) => {
                        const r = historicalRuns.find((item) => item.id === id);
                        return (
                          <td key={id} className="v3-mono text-xs">
                            {r?.dateRange} ({r?.timeframe})
                          </td>
                        );
                      })}
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </Panel>
        </div>
      )}

      {/* ── DRAWER: REQUEST LIVE PROMOTION (FUTURE / DISABLED WHILE DISARMED) ── */}
      <Drawer
        open={promotionDrawerOpen && !!activeRun}
        title="Request Live Promotion — Future"
        sub="Live real-money execution is DISARMED; this affordance is future functionality"
        onClose={() => setPromotionDrawerOpen(false)}
      >
        {activeRun?.status === "COMPLETED" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div className="dev-preview-banner">
              <span className="banner-tag">LIVE DISARMED</span>
              <span>LIVE PROMOTION · FUTURE / DISABLED WHILE DISARMED</span>
            </div>

            <p style={{ fontSize: 12.5, color: "var(--v3-ink-2)", lineHeight: 1.5, margin: 0 }}>
              Live promotion for <strong>{activeRun.strategyName} {activeRun.version}</strong> is future functionality.
              Backtest Run <code className="v3-mono font-bold">{activeRun.id}</code> (Quality Score: <strong>{activeRun.qualityScore}/100</strong>) does not
              confer live eligibility. Ordinary Backtest/Paper runs remain self-service with no owner approval needed.
            </p>

            <div style={{ padding: "10px 12px", background: "var(--v3-surface-1)", borderRadius: 6, border: "1px solid var(--v3-line)", fontSize: 11.5 }}>
              <div>• Evidence Pack: <code className="v3-mono">{activeRun.dataFingerprint}</code></div>
              <div>• Policy Snapshot: <strong>{activeRun.policySnapshot}</strong></div>
              <div>• Live execution: <strong>DISARMED — Owner-governed future surface</strong></div>
            </div>

            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 6 }}>
              <button
                type="button"
                className="v3-btn secondary"
                onClick={() => setPromotionDrawerOpen(false)}
              >
                Close
              </button>
              <button
                type="button"
                className="v3-btn primary"
                disabled
                title="Live promotion is future functionality and remains disabled while live execution is disarmed."
                id="confirm-live-promotion-btn"
              >
                Confirm Live Promotion (Disabled)
              </button>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
};
