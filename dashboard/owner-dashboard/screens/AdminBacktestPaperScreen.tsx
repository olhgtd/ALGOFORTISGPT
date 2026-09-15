import React, { useState, useMemo, useRef, useEffect } from "react";
import { Icon } from "../../shared/icons/V3Icons";
import { Panel, Drawer, KV, TruthChip, Dot } from "../../shared/utilities/V3Chrome";
import {
  getStoredOwnerBacktests,
  getStoredOwnerPaperSessions,
  updatePaperSessionHold,
  getStoredOwnerDatasets,
  getStoredOwnerStrategies,
  updateOwnerSandboxAllowance,
  getStrategyGovernance,
  computeEffectiveEligibility,
  computePaperEffectiveStatus,
  type OwnerBacktestRunRow,
  type OwnerPaperSessionRow,
  type PaperMarketDataReadiness,
  type PaperPersistenceHealth,
  type PaperReconciliationStatus,
  type OwnerDatasetRow,
  type StrategyRow,
  type OwnerAllowanceStatus,
} from "../../sampleData";
import {
  checkBackendBacktestGate,
  updateBackendStrategyAllowance,
  queryOwnerBacktestRuns,
  queryOwnerPaperSessions,
  setOwnerPaperHold,
  isBackendEnabled,
  type AuthoritativePaperSession,
} from "../../shared/services/integrationClient";

interface AdminBacktestPaperProps {
  initialTab?: "backtest" | "paper";
  go?: (screen: string) => void;
  previewMode?: boolean;
}

export const AdminBacktestPaperScreen: React.FC<AdminBacktestPaperProps> = ({ initialTab = "backtest", go, previewMode = false }) => {
  const [activeTab, setActiveTab] = useState<"backtest" | "paper">(initialTab);

  useEffect(() => {
    if (initialTab) {
      setActiveTab(initialTab);
    }
  }, [initialTab]);

  // State collections (Single Source of Truth)
  const [backtests, setBacktests] = useState<OwnerBacktestRunRow[]>(() => previewMode ? getStoredOwnerBacktests() : []);
  const [strategies, setStrategies] = useState<StrategyRow[]>(() => getStoredOwnerStrategies());
  const [paperSessions, setPaperSessions] = useState<OwnerPaperSessionRow[]>(() => previewMode ? getStoredOwnerPaperSessions() : []);
  const [datasets] = useState<OwnerDatasetRow[]>(() => getStoredOwnerDatasets());
  const [hasAuthoritativeRuns, setHasAuthoritativeRuns] = useState<boolean>(false);
  const [hasAuthoritativePaper, setHasAuthoritativePaper] = useState<boolean>(false);

  // Filter & Search states
  const [btFilter, setBtFilter] = useState<string>("ALL");
  const [paperFilter, setPaperFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  // Inspection Drawer states
  const [selectedBacktest, setSelectedBacktest] = useState<OwnerBacktestRunRow | null>(null);
  const [selectedPaperSession, setSelectedPaperSession] = useState<OwnerPaperSessionRow | null>(null);
  const [gateCheckResult, setGateCheckResult] = useState<{ permitted: boolean; reason: string } | null>(null);

  useEffect(() => {
    if (selectedBacktest) {
      checkBackendBacktestGate(selectedBacktest.strategyId, selectedBacktest.datasetId).then((res) => {
        setGateCheckResult({ permitted: res.permitted, reason: res.reason });
      });
    } else {
      setGateCheckResult(null);
    }
  }, [selectedBacktest]);

  // ── Authoritative Backtest Mapping ──
  const mapAuthoritativeBacktests = (runs: any[]): OwnerBacktestRunRow[] => {
    return (runs || []).map((r: any) => ({
      id: r.run_id,
      runId: r.run_id,
      strategyId: r.strategy_id,
      strategyName: r.strategy_name,
      strategyVersion: r.version,
      engineInterfaceVersion: "1.0",
      datasetId: r.execution_metadata?.dataset_id || "UNAVAILABLE",
      datasetCoverage: r.date_range,
      datasetTimeframe: r.timeframe,
      executionStatus: r.status,
      executionFailureReason: r.error_message,
      validationQuality: r.status !== "COMPLETED" || r.quality_score == null ? "PENDING_AUDIT" : r.quality_score >= 70 ? "EVIDENCE_ACCEPTED" : "VALIDATION_FAILED",
      validationDetails: r.policy_snapshot,
      startedAt: r.created_at_utc,
      completedAt: r.completed_at_utc || "",
      durationSeconds: r.completed_at_utc ? (Date.parse(r.completed_at_utc) - Date.parse(r.created_at_utc)) / 1000 : 0,
      replayFingerprint: r.data_fingerprint,
      initialCapital: r.initial_capital,
      netProfit: r.net_profit,
      netProfitPct: r.net_profit_pct,
      winRatePct: r.win_rate,
      profitFactor: r.profit_factor,
      sharpeRatio: r.sharpe_ratio,
      maxDrawdownPct: r.max_drawdown,
      totalTrades: r.total_trades,
      avgProfitTrade: r.avg_profit_trade,
      promotionRelevance: r.quality_score >= 80 ? "PAPER_CANDIDATE" : "REVISE_PARAMETERS",
      auditEvents: [
        { time: r.created_at_utc, text: `Authoritative backtest run ${r.status} (${r.instrument} ${r.timeframe})`, actor: r.user_id, tone: "ok" },
      ],
    }));
  };

  // ── Authoritative Polling Lifecycle (P3-3) ──
  // - Chained timeouts prevent overlapping fetches
  // - Pauses when tab/document is hidden; resumes on visibility change
  // - Exponential backoff on errors / 429 / 503 up to 15s
  // - Monotonic fetchId prevents stale responses overwriting newer state
  // - Clean unmount cleanup
  useEffect(() => {
    if (previewMode || !isBackendEnabled()) return;

    let isMounted = true;
    let timerId: any = null;
    let inFlight = false;
    let failureCount = 0;
    let latestFetchId = 0;

    const BASE_POLL_MS = 2500;
    const MAX_BACKOFF_MS = 15000;

    const scheduleNext = (delayMs: number) => {
      if (!isMounted) return;
      if (timerId !== null) {
        clearTimeout(timerId);
      }
      timerId = setTimeout(pollTick, delayMs);
    };

    const pollTick = async () => {
      if (!isMounted) return;
      if (typeof document !== "undefined" && document.visibilityState === "hidden") {
        return;
      }
      if (inFlight) {
        return;
      }

      inFlight = true;
      const currentFetchId = ++latestFetchId;

      try {
        const res = await queryOwnerBacktestRuns(50);
        if (!isMounted || currentFetchId !== latestFetchId) {
          return;
        }

        if (res.source === "BACKEND" && Array.isArray(res.data)) {
          failureCount = 0;
          const authMapped = mapAuthoritativeBacktests(res.data);
          setBacktests(authMapped);
          setSelectedBacktest(previous => previous ? authMapped.find(r => r.id === previous.id) || previous : null);
          setHasAuthoritativeRuns(true);
          scheduleNext(BASE_POLL_MS);
        } else {
          failureCount++;
          const backoffDelay = Math.min(BASE_POLL_MS * Math.pow(1.5, failureCount), MAX_BACKOFF_MS);
          scheduleNext(backoffDelay);
        }
      } catch {
        if (!isMounted) return;
        failureCount++;
        const backoffDelay = Math.min(BASE_POLL_MS * Math.pow(1.5, failureCount), MAX_BACKOFF_MS);
        scheduleNext(backoffDelay);
      } finally {
        inFlight = false;
      }
    };

    const handleVisibilityChange = () => {
      if (typeof document !== "undefined" && document.visibilityState === "visible") {
        scheduleNext(0);
      }
    };

    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", handleVisibilityChange);
    }

    pollTick();

    return () => {
      isMounted = false;
      if (timerId !== null) {
        clearTimeout(timerId);
      }
      if (typeof document !== "undefined") {
        document.removeEventListener("visibilitychange", handleVisibilityChange);
      }
    };
  }, [previewMode]);

  // ── Authoritative Owner Paper Loading (BI-2 Slice 5 Step 2) ──
  const mapAuthoritativePaper = (sessions: AuthoritativePaperSession[]): OwnerPaperSessionRow[] => {
    return sessions.map((s) => {
      const status = s.status || "INITIALIZED";
      const sessionState: "ACTIVE" | "PAUSED" | "TERMINATED" | "FAILED" =
        status === "ACTIVE" ? "ACTIVE"
        : status === "FAILED" ? "FAILED"
        : status === "STOPPED" ? "TERMINATED"
        : "PAUSED";
      const ownerAllowance = s.owner_allowance === "HOLD" ? "HOLD" : "ALLOWED";
      return {
        id: s.session_id,
        sessionId: s.session_id,
        strategyId: s.strategy_id,
        strategyName: s.strategy_name,
        strategyVersion: s.strategy_version,
        environment: "Paper / Sandbox",
        startedAt: s.created_at_utc || new Date().toISOString(),
        lastHeartbeat: s.updated_at_utc || s.created_at_utc || new Date().toISOString(),
        sessionState,
        connectionRef: s.data_source_mode === "HISTORICAL_REPLAY" ? "SIMULATED_PAPER_BROKER" : "UNKNOWN",
        marketDataReadiness: (s.market_data_readiness as PaperMarketDataReadiness) || "UNKNOWN",
        persistenceHealth: (s.persistence_health as PaperPersistenceHealth) || "UNKNOWN",
        reconciliationState: (s.reconciliation_state as PaperReconciliationStatus) || "UNKNOWN",
        promotionEvidenceState: "UNKNOWN",
        promotionEvidenceNotes: "Authoritative backend session",
        protectivePolicyId: s.policy_snapshot || "UNKNOWN",
        riskEnvelopeState: "UNKNOWN",
        simulatedCapital: s.initial_capital,
        unrealizedPnl: `\u20b9${(s.unrealized_pnl || 0).toLocaleString("en-IN")}`,
        realizedPnl: `\u20b9${(s.realized_pnl || 0).toLocaleString("en-IN")}`,
        ordersCount: s.trades_count || 0,
        positionsCount: s.trades_count || 0,
        ownerAllowance,
        ownerHoldReason: s.owner_hold_reason || undefined,
        dataSourceMode: s.data_source_mode || "HISTORICAL_REPLAY",
        feedStatus: s.feed_status || "DISCONNECTED",
        lastMarketTimestamp: s.last_market_timestamp || null,
        auditEvents: [
          { time: s.updated_at_utc || s.created_at_utc || new Date().toISOString(), text: `Authoritative paper session ${status} (${s.instrument} ${s.timeframe}) · Mode: ${s.data_source_mode || "HISTORICAL_REPLAY"} · Feed: ${s.feed_status || "DISCONNECTED"}`, actor: s.user_id, tone: "ok" }
        ]
      };
    });
  };

  useEffect(() => {
    if (previewMode) return;
    if (isBackendEnabled()) {
      queryOwnerPaperSessions(100).then((res) => {
        if (res.source === "BACKEND") {
          const authMapped = mapAuthoritativePaper(res.data || []);
          setPaperSessions(authMapped);
          setHasAuthoritativePaper(true);
        } else {
          setPaperSessions([]);
          setHasAuthoritativePaper(false);
        }
      });
    }
  }, [previewMode]);

  useEffect(() => {
    if (previewMode) return;
    if (activeTab === "paper" && isBackendEnabled()) {
      queryOwnerPaperSessions(100).then((res) => {
        if (res.source === "BACKEND") {
          const authMapped = mapAuthoritativePaper(res.data || []);
          setPaperSessions(authMapped);
          setHasAuthoritativePaper(true);
        } else {
          setPaperSessions([]);
          setHasAuthoritativePaper(false);
        }
      });
    }
  }, [activeTab, previewMode]);

  // Feedback Banner
  const [feedback, setFeedback] = useState<{ message: string; type: "ok" | "warn" | "error" } | null>(null);
  const feedbackTimerRef = useRef<any>(null);

  const showFeedback = (message: string, type: "ok" | "warn" | "error" = "ok") => {
    if (feedbackTimerRef.current) clearTimeout(feedbackTimerRef.current);
    setFeedback({ message, type });
    feedbackTimerRef.current = setTimeout(() => setFeedback(null), 5000);
  };

  const refreshAll = () => {
    if (previewMode || !isBackendEnabled()) {
      const updatedBt = getStoredOwnerBacktests();
      const updatedStrats = getStoredOwnerStrategies();
      const updatedPaper = getStoredOwnerPaperSessions();
      setStrategies(updatedStrats);
      setPaperSessions(updatedPaper);
      setBacktests(updatedBt);
      setHasAuthoritativeRuns(false);
      setHasAuthoritativePaper(false);
      if (selectedBacktest) {
        const u = updatedBt.find((b) => b.id === selectedBacktest.id || b.runId === selectedBacktest.runId);
        if (u) setSelectedBacktest(u);
      }
      if (selectedPaperSession) {
        const u = updatedPaper.find((p) => p.id === selectedPaperSession.id || p.sessionId === selectedPaperSession.sessionId);
        if (u) setSelectedPaperSession(u);
      }
      return;
    }

    // Authoritative backend active: query backend only, never append local sample fixtures
    queryOwnerPaperSessions(100).then((res) => {
      if (res.source === "BACKEND") {
        const authMapped = mapAuthoritativePaper(res.data || []);
        setPaperSessions(authMapped);
        setHasAuthoritativePaper(true);
        if (selectedPaperSession) {
          const u = authMapped.find((p) => p.id === selectedPaperSession.id || p.sessionId === selectedPaperSession.sessionId);
          if (u) setSelectedPaperSession(u);
        }
      } else {
        setPaperSessions([]);
        setHasAuthoritativePaper(false);
      }
    });

    queryOwnerBacktestRuns(50).then((res) => {
      if (res.source === "BACKEND") {
        const authMapped = mapAuthoritativeBacktests(res.data || []);
        setBacktests(authMapped);
        setHasAuthoritativeRuns(true);
        if (selectedBacktest) {
          const u = authMapped.find((b) => b.id === selectedBacktest.id || b.runId === selectedBacktest.runId);
          if (u) setSelectedBacktest(u);
        }
      } else {
        setBacktests([]);
        setHasAuthoritativeRuns(false);
      }
    });
  };

  // Filtered Backtests
  const filteredBacktests = useMemo(() => {
    return backtests.filter((b) => {
      if (btFilter === "EVIDENCE_ACCEPTED" && b.validationQuality !== "EVIDENCE_ACCEPTED") return false;
      if (btFilter === "VALIDATION_FAILED" && b.validationQuality !== "VALIDATION_FAILED") return false;
      if (btFilter === "PAPER_CANDIDATE" && b.promotionRelevance !== "PAPER_CANDIDATE") return false;

      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          b.runId.toLowerCase().includes(q) ||
          b.strategyName.toLowerCase().includes(q) ||
          b.strategyId.toLowerCase().includes(q) ||
          b.datasetId.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [backtests, btFilter, searchQuery]);

  // Filtered Paper Sessions
  const filteredPaperSessions = useMemo(() => {
    return paperSessions.filter((p) => {
      if (paperFilter === "ACTIVE" && p.sessionState !== "ACTIVE") return false;
      if (paperFilter === "MATCH_HEALTHY" && p.reconciliationState !== "MATCH_HEALTHY") return false;
      if (paperFilter === "MISMATCH" && p.reconciliationState !== "MISMATCH_DETECTED") return false;
      if (paperFilter === "CRITERIA_MET" && p.promotionEvidenceState !== "CRITERIA_MET") return false;
      if (paperFilter === "HELD" && p.ownerAllowance !== "HOLD") return false;

      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          p.sessionId.toLowerCase().includes(q) ||
          p.strategyName.toLowerCase().includes(q) ||
          p.strategyId.toLowerCase().includes(q) ||
          p.connectionRef.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [paperSessions, paperFilter, searchQuery]);

  // Strategy Backtest Submission Policy Action (Backend Authority & Local Store Sync)
  const handleToggleStrategyBacktestHold = async (strategyId: string, currentAllowance: OwnerAllowanceStatus) => {
    const next: OwnerAllowanceStatus = currentAllowance === "ALLOWED" ? "HOLD" : "ALLOWED";
    const res = await updateBackendStrategyAllowance(strategyId, "backtest", next);
    refreshAll();
    showFeedback(res.data?.message || res.error || `Strategy backtest allowance set to ${next}`, next === "HOLD" ? "warn" : "ok");
  };

  // Paper Session Operational Hold Action (Authoritative via Owner endpoint when enabled)
  const handleTogglePaperHold = (id: string, currentAllowance: OwnerAllowanceStatus) => {
    const next: OwnerAllowanceStatus = currentAllowance === "ALLOWED" ? "HOLD" : "ALLOWED";
    if (isBackendEnabled()) {
      void setOwnerPaperHold(id, next === "HOLD", next === "HOLD" ? "Owner manual pause (paper)" : undefined).then((res) => {
        if (res.success) {
          refreshAll();
          showFeedback(`Paper session Owner Allowance set to ${next} (authoritative backend)`, next === "HOLD" ? "warn" : "ok");
        } else {
          showFeedback(`Owner hold blocked by authority: ${res.error}`, "error");
        }
      });
      return;
    }
    const res = updatePaperSessionHold(id, next, undefined, "OWNER-001");
    refreshAll();
    showFeedback(res.message, next === "HOLD" ? "warn" : "ok");
  };

  const readyDatasetsCount = datasets.filter((d) => d.effectiveBacktestReadiness === "READY_FOR_BACKTEST").length;

  return (
    <>
      {/* Screen Header */}
      <div className="v3-screen-head" id="backtest-paper-header">
        <div>
          <h2 className="v3-screen-title">Backtest &amp; Paper Oversight</h2>
          <p className="v3-screen-sub">
            Institutional Execution Sandboxes · Historical Deterministic Replays, Forward Simulation, Reconciliation &amp; Promotion Evidence
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span id="backtest-paper-truth-chip">
            {(!previewMode && (hasAuthoritativeRuns || hasAuthoritativePaper)) ? (
              <TruthChip kind="REAL" title="REAL + WORKING — Authoritative Execution Sandbox Audit & Governance" />
            ) : (
              <TruthChip kind="SAMPLE" title="DEV PREVIEW / SAMPLE — Prototype Execution Oversight" />
            )}
          </span>
          <button
            type="button"
            className="v3-btn ghost mini"
            onClick={refreshAll}
            id="refresh-backtest-paper-btn"
            title="Refresh runs & sessions"
          >
            <Icon name="play" size={12} /> Refresh
          </button>
        </div>
      </div>

      {/* Feedback Banner */}
      {feedback && (
        <div
          className={`v3-feedback-banner ${feedback.type === "ok" ? "ok" : feedback.type === "warn" ? "warn" : "neg"}`}
          role="status"
          id="backtest-paper-feedback-banner"
          style={{ marginBottom: 14 }}
        >
          {feedback.type === "ok" ? "✓" : "⚠️"} {feedback.message}
        </div>
      )}

      {/* Architecture & Governance Authority Boundary Banner */}
      <div
        className="security-notice-box"
        id="backtest-paper-authority-banner"
        style={{
          marginBottom: 16,
          borderColor: "rgba(59, 130, 246, 0.4)",
          background: "rgba(59, 130, 246, 0.06)",
        }}
      >
        <span className="sec-notice-icon" style={{ fontSize: 18 }}>🛡️</span>
        <div>
          <div style={{ fontWeight: 600, color: "var(--v3-sky-text)", fontSize: 12, marginBottom: 2 }}>
            HISTORICAL RUN LEDGER vs STEP 4 STRATEGY GOVERNANCE SINGLE SOURCE OF TRUTH
          </div>
          <span style={{ fontSize: 11.5, color: "var(--v3-ink-2)" }}>
            <strong>Historical Backtest Runs</strong> (COMPLETED, FAILED) are immutable replay records.{" "}
            <strong>Strategy Backtest Allowance</strong> is sourced directly from <strong>Step 4 Strategies Governance</strong> (`sandboxes.backtest`).{" "}
            <strong>Effective New Backtest Submission</strong> = Step 4 Strategy Backtest Eligibility ∧ Step 5 Dataset Readiness.
          </span>
        </div>
      </div>

      {/* Section Navigation Tabs */}
      <div className="v3-card" style={{ padding: "6px 12px", marginBottom: 16, display: "flex", gap: 8 }} id="backtest-paper-nav-bar">
        <button
          type="button"
          className={`v3-btn mini ${activeTab === "backtest" ? "primary" : "ghost"}`}
          onClick={() => {
            setActiveTab("backtest");
            setSearchQuery("");
          }}
          id="tab-btn-backtest-oversight"
        >
          1. Backtest Oversight ({backtests.length} Runs)
        </button>
        <button
          type="button"
          className={`v3-btn mini ${activeTab === "paper" ? "primary" : "ghost"}`}
          onClick={() => {
            setActiveTab("paper");
            setSearchQuery("");
          }}
          id="tab-btn-paper-oversight"
        >
          2. Paper Trading Sessions ({paperSessions.length} Sessions)
        </button>
      </div>

      {/* ════════════════════════════════════════════════════════════
         SECTION 1: BACKTEST OVERSIGHT
         ════════════════════════════════════════════════════════════ */}
      {activeTab === "backtest" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }} id="section-backtest-oversight">
          {/* KPI Deck */}
          <div className="v3-kpi-deck" id="backtests-kpi-deck" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 12 }}>
            <div className="v3-card" style={{ padding: 14 }}>
              <div className="v3-dim text-xs">TOTAL RUNS</div>
              <div className="v3-stat-big" style={{ fontSize: 24, fontWeight: 700, marginTop: 4 }}>{backtests.length}</div>
              <div className="v3-cell-sub text-xs">Historical execution ledger</div>
            </div>
            <div className="v3-card" style={{ padding: 14 }}>
              <div className="v3-dim text-xs">EVIDENCE ACCEPTED</div>
              <div className="v3-stat-big" style={{ fontSize: 24, fontWeight: 700, marginTop: 4, color: "var(--v3-profit)" }}>
                {backtests.filter((b) => b.validationQuality === "EVIDENCE_ACCEPTED").length}
              </div>
              <div className="v3-cell-sub text-xs">Sharpe &gt;= 1.20 verified</div>
            </div>
            <div className="v3-card" style={{ padding: 14 }}>
              <div className="v3-dim text-xs">FAILED / BLOCKED</div>
              <div className="v3-stat-big" style={{ fontSize: 24, fontWeight: 700, marginTop: 4, color: "var(--v3-loss-text)" }}>
                {backtests.filter((b) => b.executionStatus === "FAILED" || b.validationQuality === "VALIDATION_FAILED").length}
              </div>
              <div className="v3-cell-sub text-xs">Gaps / AST non-conformance</div>
            </div>
            <div className="v3-card" style={{ padding: 14 }}>
              <div className="v3-dim text-xs">APPROVED DATASETS</div>
              <div className="v3-stat-big" style={{ fontSize: 24, fontWeight: 700, marginTop: 4, color: "var(--v3-sky-text)" }}>
                {readyDatasetsCount} / {datasets.length}
              </div>
              <div className="v3-cell-sub text-xs">Ready for Backtest replay</div>
            </div>
          </div>

          {/* Strategy Backtest Submission Governance Panel (Consumed from Step 4 Single Source of Truth) */}
          <Panel
            label="Strategy Backtest Submission Governance (Step 4 Single Source of Truth)"
            meta="Governs authority for new backtest simulation requests"
            className="v3-sp12"
          >
            <div className="v3-table-wrap">
              <table className="v3-table" id="strategy-backtest-submission-table">
                <thead>
                  <tr>
                    <th style={{ whiteSpace: "nowrap" }}>STRATEGY ID &amp; NAME</th>
                    <th style={{ whiteSpace: "nowrap" }}>SYSTEM BACKTEST READINESS</th>
                    <th style={{ whiteSpace: "nowrap" }}>OWNER ALLOWANCE</th>
                    <th style={{ whiteSpace: "nowrap" }}>EFFECTIVE SUBMISSION GATE</th>
                    <th style={{ textAlign: "right", whiteSpace: "nowrap" }}>SUBMISSION ACTION</th>
                  </tr>
                </thead>
                <tbody>
                  {strategies.length === 0 ? (
                    <tr>
                      <td colSpan={5} style={{ textAlign: "center", padding: "28px", color: "var(--v3-ink-dim)" }}>
                        No strategies assigned
                      </td>
                    </tr>
                  ) : (
                    strategies.map((s) => {
                    const gov = getStrategyGovernance(s);
                    const eff = computeEffectiveEligibility(
                      gov.backtest.systemReadiness,
                      gov.backtest.ownerAllowance,
                      s.adminStatus === "SUSPENDED"
                    );
                    const isHeld = gov.backtest.ownerAllowance === "HOLD";
                    const isSystemReady = gov.backtest.systemReadiness === "READY";
                    const stratId = s.strategyId || s.id;

                    return (
                      <tr key={stratId} className="v3-table-row" id={`strat-policy-row-${stratId}`}>
                        {/* Strategy ID & Name */}
                        <td>
                          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                            <span className="v3-mono font-bold text-xs text-sky-400">{stratId}</span>
                            <span className="font-semibold text-xs">{s.name}</span>
                          </div>
                        </td>

                        {/* System Readiness */}
                        <td>
                          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                            <span className={`v3-status-badge ${isSystemReady ? "ok" : "dim"}`}>
                              <Dot tone={isSystemReady ? "ok" : "dim"} />
                              {gov.backtest.systemReadiness}
                            </span>
                            {gov.backtest.systemBlockerReason && (
                              <span className="v3-cell-sub text-xs" style={{ fontSize: 9.5, color: "var(--v3-loss-text)" }}>
                                {gov.backtest.systemBlockerReason}
                              </span>
                            )}
                          </div>
                        </td>

                        {/* Owner Allowance */}
                        <td>
                          <span className={`v3-status-badge ${isHeld ? "warn" : "ok"}`}>
                            <Dot tone={isHeld ? "warn" : "ok"} />
                            {gov.backtest.ownerAllowance}
                          </span>
                        </td>

                        {/* Effective Submission Gate */}
                        <td>
                          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                            <span className={`v3-status-badge ${eff.tone}`}>
                              <Dot tone={eff.tone} />
                              {eff.label}
                            </span>
                            <span className="v3-cell-sub text-xs" style={{ fontSize: 9.5 }}>{eff.reason}</span>
                          </div>
                        </td>

                        {/* Submission Action */}
                        <td style={{ textAlign: "right" }}>
                          <button
                            type="button"
                            className={`v3-btn mini ${isHeld ? "ghost" : "danger-ghost"}`}
                            onClick={() => handleToggleStrategyBacktestHold(s.id, gov.backtest.ownerAllowance)}
                            id={`toggle-strat-hold-btn-${stratId}`}
                            title="Directly updates Step 4 single source of truth"
                          >
                            {isHeld ? "Allow Submissions" : "Place Hold"}
                          </button>
                        </td>
                      </tr>
                    );
                  }))}
                </tbody>
              </table>
            </div>
          </Panel>

          {/* Approved Dataset Consumption Strip */}
          <div className="v3-card" style={{ padding: 12, background: "var(--v3-surface-2)", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }} id="approved-dataset-boundary-strip">
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 16 }}>📊</span>
              <div>
                <div style={{ fontWeight: 700, fontSize: 12 }}>APPROVED DATASET GOVERNANCE BOUNDARY</div>
                <div className="v3-dim text-xs">
                  Backtests execute strictly against datasets approved by Step 5 Historical Data Manager. Raw data acquisition controls are restricted to Step 5.
                </div>
              </div>
            </div>
            <a
              href="#plugins"
              className="v3-btn ghost mini"
              id="goto-historical-data-manager-link"
              onClick={(e) => {
                if (go) {
                  e.preventDefault();
                  go("plugins");
                }
              }}
            >
              Manage Historical Datasets (Step 5) →
            </a>
          </div>

          {/* Filter Toolbar */}
          <div className="v3-card" style={{ padding: 10, display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 10 }} id="backtests-toolbar">
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <button
                type="button"
                className={`v3-btn mini ${btFilter === "ALL" ? "primary" : "ghost"}`}
                onClick={() => setBtFilter("ALL")}
                id="filter-bt-all-btn"
              >
                All Historical Runs ({backtests.length})
              </button>
              <button
                type="button"
                className={`v3-btn mini ${btFilter === "EVIDENCE_ACCEPTED" ? "primary" : "ghost"}`}
                onClick={() => setBtFilter("EVIDENCE_ACCEPTED")}
                id="filter-bt-accepted-btn"
              >
                Evidence Accepted
              </button>
              <button
                type="button"
                className={`v3-btn mini ${btFilter === "VALIDATION_FAILED" ? "primary" : "ghost"}`}
                onClick={() => setBtFilter("VALIDATION_FAILED")}
                id="filter-bt-failed-btn"
              >
                Failed / Blocked
              </button>
              <button
                type="button"
                className={`v3-btn mini ${btFilter === "PAPER_CANDIDATE" ? "primary" : "ghost"}`}
                onClick={() => setBtFilter("PAPER_CANDIDATE")}
                id="filter-bt-candidate-btn"
              >
                Paper Candidates
              </button>
            </div>
            <div style={{ position: "relative", minWidth: 240 }}>
              <input
                type="text"
                placeholder="Search historical runs..."
                className="v3-input"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                id="bt-search-input"
                style={{ paddingLeft: 26, fontSize: 12, height: 30 }}
              />
              <span style={{ position: "absolute", left: 8, top: 6, color: "var(--v3-ink-dim)", fontSize: 12 }}>🔍</span>
            </div>
          </div>

          {/* Backtests Historical Run Inventory Table */}
          <Panel label="Historical Backtest Replay Run Ledger (Immutable Execution Truth)" meta={`${filteredBacktests.length} replay runs`} className="v3-sp12">
            <div className="v3-table-wrap">
              <table className="v3-table" id="owner-backtests-table">
                <thead>
                  <tr>
                    <th style={{ whiteSpace: "nowrap" }}>RUN ID &amp; STRATEGY</th>
                    <th style={{ whiteSpace: "nowrap" }}>DATASET ID &amp; COVERAGE</th>
                    <th style={{ whiteSpace: "nowrap" }}>EXECUTION STATUS</th>
                    <th style={{ whiteSpace: "nowrap" }}>EVIDENCE QUALITY</th>
                    <th style={{ whiteSpace: "nowrap" }}>METRICS (SHARPE · WIN · DD)</th>
                    <th style={{ whiteSpace: "nowrap" }}>DERIVED EVALUATION</th>
                    <th style={{ textAlign: "right", whiteSpace: "nowrap" }}>ACTIONS</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredBacktests.length === 0 ? (
                    <tr id="owner-backtest-empty-state">
                      <td colSpan={7} style={{ textAlign: "center", padding: "28px", color: "var(--v3-ink-dim)" }}>
                        {backtests.length === 0 ? (!previewMode && isBackendEnabled() ? "No authoritative backtest runs found." : "No backtests yet") : "No backtest runs match filter."}
                      </td>
                    </tr>
                  ) : (
                    filteredBacktests.map((b) => {
                      const isCompleted = b.executionStatus === "COMPLETED";
                      const isEvidenceAccepted = b.validationQuality === "EVIDENCE_ACCEPTED";

                      return (
                        <tr
                          key={b.id}
                          className="v3-table-row"
                          id={`bt-row-${b.id}`}
                          style={{ cursor: "pointer" }}
                          onClick={() => setSelectedBacktest(b)}
                        >
                          {/* Run ID & Strategy */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className="v3-mono font-bold text-xs text-sky-400">{b.runId}</span>
                              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                <span className="font-semibold text-xs">{b.strategyName}</span>
                                <span className="v3-mono v3-dim text-xs">({b.strategyId} · {b.strategyVersion})</span>
                              </div>
                            </div>
                          </td>

                          {/* Dataset & Coverage */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className="v3-mono font-bold text-xs">{b.datasetId}</span>
                              <span className="v3-cell-sub v3-mono text-xs">{b.datasetCoverage}</span>
                            </div>
                          </td>

                          {/* Execution Status */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className={`v3-status-badge ${isCompleted ? "ok" : "neg"}`}>
                                <Dot tone={isCompleted ? "ok" : "neg"} />
                                {b.executionStatus}
                              </span>
                              <span className="v3-mono v3-dim text-xs" style={{ fontSize: 9.5 }}>{b.durationSeconds}s duration</span>
                            </div>
                          </td>

                          {/* Evidence Quality */}
                          <td>
                            <span className={`v3-status-badge ${isEvidenceAccepted ? "ok" : "neg"}`}>
                              <Dot tone={isEvidenceAccepted ? "ok" : "neg"} />
                              {b.validationQuality.replace("_", " ")}
                            </span>
                          </td>

                          {/* Performance Metrics */}
                          <td>
                            {isCompleted ? (
                              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                <div style={{ display: "flex", gap: 8, fontSize: 11 }}>
                                  <span>Sharpe: <strong className="v3-mono">{b.sharpeRatio}</strong></span>
                                  <span>Win: <strong className="v3-mono">{b.winRatePct}%</strong></span>
                                  <span>DD: <strong className="v3-mono" style={{ color: "var(--v3-loss-text)" }}>{b.maxDrawdownPct}%</strong></span>
                                </div>
                                <span className="v3-mono v3-dim text-xs" style={{ fontSize: 9.5 }}>{b.totalTrades} trades · PF {b.profitFactor}</span>
                              </div>
                            ) : (
                              <span className="v3-dim text-xs">Execution Halted / No Metrics</span>
                            )}
                          </td>

                          {/* Derived Evaluation */}
                          <td>
                            <span className={`v3-status-badge ${b.promotionRelevance === "PAPER_CANDIDATE" ? "ok" : "neg"}`}>
                              <Dot tone={b.promotionRelevance === "PAPER_CANDIDATE" ? "ok" : "neg"} />
                              {b.promotionRelevance.replace("_", " ")}
                            </span>
                          </td>

                          {/* Actions */}
                          <td style={{ textAlign: "right" }} onClick={(e) => e.stopPropagation()}>
                            <button
                              type="button"
                              className="v3-btn ghost mini"
                              onClick={() => setSelectedBacktest(b)}
                              id={`inspect-bt-btn-${b.id}`}
                              title="Inspect backtest run evidence"
                            >
                              Inspect Run
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      )}

      {/* ════════════════════════════════════════════════════════════
         SECTION 2: PAPER TRADING SESSIONS
         ════════════════════════════════════════════════════════════ */}
      {activeTab === "paper" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }} id="section-paper-oversight">
          {/* Authority Truth Chip (Authoritative backend vs DEV PREVIEW / SAMPLE) */}
          <div className="v3-card" style={{ padding: 8, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }} id="paper-authority-truthchip">
            {(!previewMode && hasAuthoritativePaper) ? (
              <TruthChip kind="REAL" title="REAL + WORKING — Authoritative Owner Paper Oversight (PaperService live sessions)" />
            ) : (
              <TruthChip kind="SAMPLE" title="DEV PREVIEW / SAMPLE — Prototype paper oversight" />
            )}
            <span className="v3-dim text-xs">Sessions below reflect PaperService authoritative state when the backend is connected; otherwise they are a non-authoritative preview that can never mutate authoritative state.</span>
          </div>
          {/* KPI Deck */}
          <div className="v3-kpi-deck" id="paper-kpi-deck" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 12 }}>
            <div className="v3-card" style={{ padding: 14 }}>
              <div className="v3-dim text-xs">TOTAL PAPER SESSIONS</div>
              <div className="v3-stat-big" style={{ fontSize: 24, fontWeight: 700, marginTop: 4 }}>{paperSessions.length}</div>
              <div className="v3-cell-sub text-xs">Forward simulation sessions</div>
            </div>
            <div className="v3-card" style={{ padding: 14 }}>
              <div className="v3-dim text-xs">ACTIVE FORWARD SESSIONS</div>
              <div className="v3-stat-big" style={{ fontSize: 24, fontWeight: 700, marginTop: 4, color: "var(--v3-profit)" }}>
                {paperSessions.filter((p) => p.sessionState === "ACTIVE").length}
              </div>
              <div className="v3-cell-sub text-xs">Running forward engine loop</div>
            </div>
            <div className="v3-card" style={{ padding: 14 }}>
              <div className="v3-dim text-xs">RECONCILIATION CLEAN</div>
              <div className="v3-stat-big" style={{ fontSize: 24, fontWeight: 700, marginTop: 4, color: "var(--v3-profit)" }}>
                {paperSessions.filter((p) => p.reconciliationState === "MATCH_HEALTHY").length}
              </div>
              <div className="v3-cell-sub text-xs">0 position discrepancies</div>
            </div>
            <div className="v3-card" style={{ padding: 14 }}>
              <div className="v3-dim text-xs">MISMATCH / PAUSED</div>
              <div className="v3-stat-big" style={{ fontSize: 24, fontWeight: 700, marginTop: 4, color: "var(--v3-loss-text)" }}>
                {paperSessions.filter((p) => p.reconciliationState === "MISMATCH_DETECTED" || p.sessionState === "PAUSED" || p.sessionState === "TERMINATED").length}
              </div>
              <div className="v3-cell-sub text-xs">Requires operator audit</div>
            </div>
          </div>

          {/* Promotion & Non-Bypass Boundary Banner */}
          <div className="v3-card" style={{ padding: 12, background: "var(--v3-surface-2)", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }} id="paper-promotion-boundary-strip">
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 16 }}>📋</span>
              <div>
                <div style={{ fontWeight: 700, fontSize: 12 }}>FORWARD PROMOTION EVIDENCE BOUNDARY</div>
                <div className="v3-dim text-xs">
                  Paper trading generates forward verification evidence. Direct Live promotion is never triggered from this screen; all strategy promotion gates are enforced in Step 4.
                </div>
              </div>
            </div>
            <a
              href="#strategies"
              className="v3-btn ghost mini"
              id="goto-strategies-governance-link"
              onClick={(e) => {
                if (go) {
                  e.preventDefault();
                  go("strategies");
                }
              }}
            >
              Strategies Governance (Step 4) →
            </a>
          </div>

          {/* Filter Toolbar */}
          <div className="v3-card" style={{ padding: 10, display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 10 }} id="paper-toolbar">
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <button
                type="button"
                className={`v3-btn mini ${paperFilter === "ALL" ? "primary" : "ghost"}`}
                onClick={() => setPaperFilter("ALL")}
                id="filter-paper-all-btn"
              >
                All ({paperSessions.length})
              </button>
              <button
                type="button"
                className={`v3-btn mini ${paperFilter === "ACTIVE" ? "primary" : "ghost"}`}
                onClick={() => setPaperFilter("ACTIVE")}
                id="filter-paper-active-btn"
              >
                Active
              </button>
              <button
                type="button"
                className={`v3-btn mini ${paperFilter === "MATCH_HEALTHY" ? "primary" : "ghost"}`}
                onClick={() => setPaperFilter("MATCH_HEALTHY")}
                id="filter-paper-clean-btn"
              >
                Reconciliation Clean
              </button>
              <button
                type="button"
                className={`v3-btn mini ${paperFilter === "MISMATCH" ? "primary" : "ghost"}`}
                onClick={() => setPaperFilter("MISMATCH")}
                id="filter-paper-mismatch-btn"
              >
                Mismatch Flagged
              </button>
              <button
                type="button"
                className={`v3-btn mini ${paperFilter === "CRITERIA_MET" ? "primary" : "ghost"}`}
                onClick={() => setPaperFilter("CRITERIA_MET")}
                id="filter-paper-criteria-btn"
              >
                Criteria Met
              </button>
              <button
                type="button"
                className={`v3-btn mini ${paperFilter === "HELD" ? "primary" : "ghost"}`}
                onClick={() => setPaperFilter("HELD")}
                id="filter-paper-held-btn"
              >
                Owner Hold
              </button>
            </div>
            <div style={{ position: "relative", minWidth: 240 }}>
              <input
                type="text"
                placeholder="Search paper sessions..."
                className="v3-input"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                id="paper-search-input"
                style={{ paddingLeft: 26, fontSize: 12, height: 30 }}
              />
              <span style={{ position: "absolute", left: 8, top: 6, color: "var(--v3-ink-dim)", fontSize: 12 }}>🔍</span>
            </div>
          </div>

          {/* Paper Sessions Table */}
          <Panel label="Paper Forward Simulation Sessions Inventory" meta={`${filteredPaperSessions.length} sessions`} className="v3-sp12">
            <div className="v3-table-wrap">
              <table className="v3-table" id="owner-paper-table">
                <thead>
                  <tr>
                    <th style={{ whiteSpace: "nowrap" }}>SESSION ID &amp; STRATEGY</th>
                    <th style={{ whiteSpace: "nowrap" }}>FEED &amp; PERSISTENCE</th>
                    <th style={{ whiteSpace: "nowrap" }}>SESSION STATE</th>
                    <th style={{ whiteSpace: "nowrap" }}>OWNER ALLOWANCE</th>
                    <th style={{ whiteSpace: "nowrap" }}>RECONCILIATION</th>
                    <th style={{ whiteSpace: "nowrap" }}>EFFECTIVE ACTIVITY</th>
                    <th style={{ whiteSpace: "nowrap" }}>SIMULATED P&amp;L</th>
                    <th style={{ textAlign: "right", whiteSpace: "nowrap" }}>ACTIONS</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredPaperSessions.length === 0 ? (
                    <tr id="owner-paper-empty-state">
                      <td colSpan={8} style={{ textAlign: "center", padding: "28px", color: "var(--v3-ink-dim)" }}>
                        {paperSessions.length === 0 ? (!previewMode && isBackendEnabled() ? "No authoritative paper sessions found." : "No paper sessions yet") : "No paper sessions match filter."}
                      </td>
                    </tr>
                  ) : (
                    filteredPaperSessions.map((p) => {
                      const isActive = p.sessionState === "ACTIVE";
                      const isHeld = p.ownerAllowance === "HOLD";
                      const isCleanRecon = p.reconciliationState === "MATCH_HEALTHY";
                      const eff = computePaperEffectiveStatus(
                        p.sessionState,
                        p.marketDataReadiness,
                        p.persistenceHealth,
                        p.reconciliationState,
                        p.ownerAllowance
                      );

                      return (
                        <tr
                          key={p.id}
                          className="v3-table-row"
                          id={`paper-row-${p.id}`}
                          style={{ cursor: "pointer" }}
                          onClick={() => setSelectedPaperSession(p)}
                        >
                          {/* Session ID & Strategy */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className="v3-mono font-bold text-xs text-sky-400">{p.sessionId}</span>
                              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                <span className="font-semibold text-xs">{p.strategyName}</span>
                                <span className="v3-mono v3-dim text-xs">({p.strategyId} · {p.strategyVersion})</span>
                              </div>
                            </div>
                          </td>

                          {/* Feed & Persistence */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                <span className="v3-mono text-xs font-semibold">{p.connectionRef.split(" ")[0]}</span>
                                <span className={`v3-chip mini ${p.dataSourceMode === "LIVE_MARKET" ? "online" : "sample"}`} style={{ fontSize: 9.5, padding: "1px 5px" }}>
                                  {p.dataSourceMode === "LIVE_MARKET" ? "LIVE MARKET" : "HISTORICAL REPLAY"}
                                </span>
                              </div>
                              <div style={{ display: "flex", gap: 6, fontSize: 10 }} className="v3-mono">
                                <span>Feed: <strong className={p.feedStatus === "CONNECTED" ? "text-emerald-400" : p.feedStatus === "RECONNECTING" ? "text-amber-400" : "text-slate-400"}>{p.feedStatus || p.marketDataReadiness}</strong></span>
                                <span>·</span>
                                <span>Store: <strong className={p.persistenceHealth === "SEALED" ? "text-emerald-400" : "text-rose-400"}>{p.persistenceHealth}</strong></span>
                              </div>
                            </div>
                          </td>

                          {/* Session State */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className={`v3-status-badge ${isActive ? "ok" : p.sessionState === "PAUSED" ? "warn" : "neg"}`}>
                                <Dot tone={isActive ? "ok" : p.sessionState === "PAUSED" ? "warn" : "neg"} />
                                {p.sessionState}
                              </span>
                              <span className="v3-mono v3-dim text-xs" style={{ fontSize: 9.5 }}>{p.lastHeartbeat.split(" ")[0]}</span>
                            </div>
                          </td>

                          {/* Owner Allowance */}
                          <td>
                            <span className={`v3-status-badge ${isHeld ? "warn" : "ok"}`}>
                              <Dot tone={isHeld ? "warn" : "ok"} />
                              {p.ownerAllowance}
                            </span>
                          </td>

                          {/* Reconciliation */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className={`v3-status-badge ${isCleanRecon ? "ok" : "warn"}`}>
                                <Dot tone={isCleanRecon ? "ok" : "warn"} />
                                {p.reconciliationState.replace("_", " ")}
                              </span>
                              {p.reconciliationFinding && (
                                <span className="v3-cell-sub text-xs" style={{ fontSize: 9, color: "var(--v3-warn-text)", maxWidth: 160 }}>
                                  {p.reconciliationFinding.split(":")[0]}
                                </span>
                              )}
                            </div>
                          </td>

                          {/* Effective Activity */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className={`v3-status-badge ${eff.tone}`}>
                                <Dot tone={eff.tone} />
                                {eff.label}
                              </span>
                              {eff.blocker && (
                                <span className="v3-cell-sub text-xs" style={{ fontSize: 9, color: "var(--v3-loss-text)", maxWidth: 160 }}>
                                  {eff.blocker}
                                </span>
                              )}
                            </div>
                          </td>

                          {/* Simulated P&L */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className="v3-mono font-bold text-xs" style={{ color: p.realizedPnl.startsWith("+") ? "var(--v3-profit)" : "var(--v3-loss-text)" }}>
                                {p.realizedPnl}
                              </span>
                              <span className="v3-mono v3-dim text-xs" style={{ fontSize: 9.5 }}>{p.ordersCount} orders · {p.positionsCount} open pos</span>
                            </div>
                          </td>

                          {/* Actions */}
                          <td style={{ textAlign: "right" }} onClick={(e) => e.stopPropagation()}>
                            <div style={{ display: "inline-flex", gap: 6 }}>
                              <button
                                type="button"
                                className="v3-btn ghost mini"
                                onClick={() => setSelectedPaperSession(p)}
                                id={`inspect-paper-btn-${p.id}`}
                                title="Inspect paper session state"
                              >
                                Inspect
                              </button>
                              <button
                                type="button"
                                className={`v3-btn mini ${isHeld ? "ghost" : "danger-ghost"}`}
                                onClick={() => handleTogglePaperHold(p.id, p.ownerAllowance)}
                                id={`toggle-hold-paper-btn-${p.id}`}
                                title="Interactive Prototype — Local State"
                              >
                                {isHeld ? "Allow" : "Place Hold"}
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      )}

      {/* ════════════════════════════════════════════════════════════
         INSPECTION DRAWERS (BACKTEST & PAPER SESSIONS)
         ════════════════════════════════════════════════════════════ */}

      {/* 1. Backtest Run Inspection Drawer (Pure Historical Truth) */}
      {selectedBacktest && (
        <Drawer
          open={Boolean(selectedBacktest)}
          title={selectedBacktest.runId}
          sub={`${selectedBacktest.strategyName} (${selectedBacktest.strategyId} · ${selectedBacktest.strategyVersion})`}
          onClose={() => setSelectedBacktest(null)}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {/* Status Summary Strip */}
            <div
              className="v3-card"
              style={{
                padding: 12,
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
                gap: 10,
                background: "var(--v3-surface-2)",
              }}
            >
              <div>
                <div className="v3-dim text-xs">EXECUTION STATUS</div>
                <div style={{ marginTop: 2 }}>
                  <span className={`v3-status-badge ${selectedBacktest.executionStatus === "COMPLETED" ? "ok" : "neg"}`}>
                    <Dot tone={selectedBacktest.executionStatus === "COMPLETED" ? "ok" : "neg"} />
                    {selectedBacktest.executionStatus}
                  </span>
                </div>
              </div>
              <div>
                <div className="v3-dim text-xs">EVIDENCE QUALITY</div>
                <div style={{ marginTop: 2 }}>
                  <span className={`v3-status-badge ${selectedBacktest.validationQuality === "EVIDENCE_ACCEPTED" ? "ok" : "neg"}`}>
                    <Dot tone={selectedBacktest.validationQuality === "EVIDENCE_ACCEPTED" ? "ok" : "neg"} />
                    {selectedBacktest.validationQuality.replace("_", " ")}
                  </span>
                </div>
              </div>
              <div>
                <div className="v3-dim text-xs">DERIVED EVALUATION</div>
                <div style={{ marginTop: 2 }}>
                  <span className={`v3-status-badge ${selectedBacktest.promotionRelevance === "PAPER_CANDIDATE" ? "ok" : "neg"}`}>
                    <Dot tone={selectedBacktest.promotionRelevance === "PAPER_CANDIDATE" ? "ok" : "neg"} />
                    {selectedBacktest.promotionRelevance.replace("_", " ")}
                  </span>
                </div>
              </div>
            </div>

            {/* Panel: Run Specification & Provenance */}
            <Panel label="Historical Backtest Specification &amp; Dataset Provenance">
              <dl style={{ margin: 0 }}>
                <KV k="Run ID" v={<span className="v3-mono font-bold">{selectedBacktest.runId}</span>} />
                <KV k="Strategy ID / Version" v={<span className="v3-mono">{selectedBacktest.strategyId} · {selectedBacktest.strategyVersion}</span>} />
                <KV k="Engine Interface Version" v={<span className="v3-mono">{selectedBacktest.engineInterfaceVersion}</span>} />
                <KV k="Consumed Dataset ID" v={<span className="v3-mono font-bold">{selectedBacktest.datasetId}</span>} />
                <KV k="Dataset Coverage Range" v={selectedBacktest.datasetCoverage} />
                <KV k="Timeframe Resolution" v={<span className="v3-mono">{selectedBacktest.datasetTimeframe}</span>} />
                <KV k="Initial Capital Basis" v={`₹${selectedBacktest.initialCapital.toLocaleString()}`} />
                <KV k="Deterministic Replay Fingerprint" v={<code className="v3-mono" style={{ fontSize: 10 }}>{selectedBacktest.replayFingerprint}</code>} />
                <KV k="Validation Evidence Notes" v={selectedBacktest.validationDetails} />
                {selectedBacktest.executionFailureReason && (
                  <KV
                    k="Execution Failure Reason"
                    v={<span style={{ color: "var(--v3-loss-text)", fontWeight: 600 }}>{selectedBacktest.executionFailureReason}</span>}
                  />
                )}
                {gateCheckResult && (
                  <KV
                    k="Backend Governance Gate"
                    v={
                      <span className={`v3-status-badge ${gateCheckResult.permitted ? "ok" : "warn"}`}>
                        <Dot tone={gateCheckResult.permitted ? "ok" : "warn"} />
                        {gateCheckResult.permitted ? "ELIGIBLE" : "HELD"}: {gateCheckResult.reason}
                      </span>
                    }
                  />
                )}
              </dl>
            </Panel>

            {/* Panel: Performance Metrics */}
            {selectedBacktest.executionStatus === "COMPLETED" && (
              <Panel label="Deterministic Replay Performance Metrics">
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                  <KV k="Sharpe Ratio" v={<span className="v3-mono font-bold">{selectedBacktest.sharpeRatio}</span>} />
                  <KV k="Win Rate" v={<span className="v3-mono font-bold">{selectedBacktest.winRatePct}%</span>} />
                  <KV k="Profit Factor" v={<span className="v3-mono font-bold">{selectedBacktest.profitFactor}</span>} />
                  <KV k="Max Drawdown" v={<span className="v3-mono font-bold" style={{ color: "var(--v3-loss-text)" }}>{selectedBacktest.maxDrawdownPct}%</span>} />
                  <KV k="Total Trades Evaluated" v={<span className="v3-mono font-bold">{selectedBacktest.totalTrades}</span>} />
                  <KV k="Avg Trade Return" v={`₹${selectedBacktest.avgProfitTrade}`} />
                  <KV k="Net Simulated Profit" v={<span className="v3-mono font-bold text-emerald-400">+{selectedBacktest.netProfitPct}% (₹{selectedBacktest.netProfit?.toLocaleString() ?? "UNAVAILABLE"})</span>} />
                  <KV k="Execution Duration" v={`${selectedBacktest.durationSeconds}s (${selectedBacktest.startedAt} → ${selectedBacktest.completedAt})`} />
                </div>
              </Panel>
            )}

            {/* Panel: Promotion Boundary Notice */}
            <Panel label="Strategy Promotion Boundary Notice">
              <div style={{ fontSize: 11.5, color: "var(--v3-ink-2)", lineHeight: 1.5 }}>
                Completed backtest with accepted evidence qualifies strategy as a <strong>Paper Candidate</strong> (DEV PREVIEW / SAMPLE derived evaluation).{" "}
                Backtest completion does not automatically authorize forward Live deployment. Forward paper validation and final Live authorization are governed exclusively in <strong>Strategies Governance (Step 4)</strong>.
              </div>
            </Panel>

            {/* Panel: Audit Trail */}
            <Panel label="Backtest Execution Audit Trail">
              <div className="v3-rows">
                {selectedBacktest.auditEvents.map((ev, idx) => (
                  <div className="v3-row" key={idx}>
                    <div className="v3-row-main">
                      <div className="v3-row-title" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <Dot tone={ev.tone || "ok"} />
                        <span>{ev.text}</span>
                        <span className="v3-dim text-xs">by {ev.actor}</span>
                      </div>
                    </div>
                    <span className="v3-mono v3-dim text-xs" style={{ fontSize: 10 }}>{ev.time}</span>
                  </div>
                ))}
              </div>
            </Panel>
          </div>
        </Drawer>
      )}

      {/* 2. Paper Session Inspection Drawer */}
      {selectedPaperSession && (
        <Drawer
          open={Boolean(selectedPaperSession)}
          title={selectedPaperSession.sessionId}
          sub={`${selectedPaperSession.strategyName} (${selectedPaperSession.strategyId} · ${selectedPaperSession.strategyVersion})`}
          onClose={() => setSelectedPaperSession(null)}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {/* Status Summary Strip */}
            <div
              className="v3-card"
              style={{
                padding: 12,
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))",
                gap: 10,
                background: "var(--v3-surface-2)",
              }}
            >
              <div>
                <div className="v3-dim text-xs">SESSION STATE</div>
                <div style={{ marginTop: 2 }}>
                  <span className={`v3-status-badge ${selectedPaperSession.sessionState === "ACTIVE" ? "ok" : selectedPaperSession.sessionState === "PAUSED" ? "warn" : "neg"}`}>
                    <Dot tone={selectedPaperSession.sessionState === "ACTIVE" ? "ok" : selectedPaperSession.sessionState === "PAUSED" ? "warn" : "neg"} />
                    {selectedPaperSession.sessionState}
                  </span>
                </div>
              </div>
              <div>
                <div className="v3-dim text-xs">OWNER ALLOWANCE</div>
                <div style={{ marginTop: 2 }}>
                  <span className={`v3-status-badge ${selectedPaperSession.ownerAllowance === "HOLD" ? "warn" : "ok"}`}>
                    <Dot tone={selectedPaperSession.ownerAllowance === "HOLD" ? "warn" : "ok"} />
                    {selectedPaperSession.ownerAllowance}
                  </span>
                </div>
              </div>
              <div>
                <div className="v3-dim text-xs">FEED HEALTH</div>
                <div style={{ marginTop: 2 }}>
                  <span className={`v3-status-badge ${selectedPaperSession.marketDataReadiness === "READY" ? "ok" : "warn"}`}>
                    <Dot tone={selectedPaperSession.marketDataReadiness === "READY" ? "ok" : "warn"} />
                    {selectedPaperSession.marketDataReadiness}
                  </span>
                </div>
              </div>
              <div>
                <div className="v3-dim text-xs">RECONCILIATION</div>
                <div style={{ marginTop: 2 }}>
                  <span className={`v3-status-badge ${selectedPaperSession.reconciliationState === "MATCH_HEALTHY" ? "ok" : "warn"}`}>
                    <Dot tone={selectedPaperSession.reconciliationState === "MATCH_HEALTHY" ? "ok" : "warn"} />
                    {selectedPaperSession.reconciliationState.replace("_", " ")}
                  </span>
                </div>
              </div>
            </div>

            {/* Panel: Session Identity & Gateway Connection */}
            <Panel label="Session Identity &amp; Connection Binding">
              <dl style={{ margin: 0 }}>
                <KV k="Session ID" v={<span className="v3-mono font-bold">{selectedPaperSession.sessionId}</span>} />
                <KV k="Strategy ID / Version" v={<span className="v3-mono">{selectedPaperSession.strategyId} · {selectedPaperSession.strategyVersion}</span>} />
                <KV k="Environment" v={selectedPaperSession.environment} />
                <KV k="Started Timestamp" v={selectedPaperSession.startedAt} />
                <KV k="Last Engine Heartbeat" v={selectedPaperSession.lastHeartbeat} />
                <KV k="Connection Reference" v={<span className="v3-mono">{selectedPaperSession.connectionRef}</span>} />
                <KV k="Simulated Capital Basis" v={`₹${selectedPaperSession.simulatedCapital.toLocaleString()}`} />
                <KV k="Orders / Positions Summary" v={`${selectedPaperSession.ordersCount} total orders · ${selectedPaperSession.positionsCount} active positions`} />
                <KV k="Realized / Unrealized P&L" v={`${selectedPaperSession.realizedPnl} realized · ${selectedPaperSession.unrealizedPnl} unrealized`} />
              </dl>
            </Panel>

            {/* Panel: Risk & Protective Policy Enforcement */}
            <Panel label="Risk Gate &amp; Protective Policy Enforcement" meta="Non-Bypassable">
              <dl style={{ margin: 0 }}>
                <KV k="Active Protective Policy" v={<span className="v3-mono">{selectedPaperSession.protectivePolicyId}</span>} />
                <KV
                  k="Risk Envelope State"
                  v={
                    <span className={`v3-status-badge ${selectedPaperSession.riskEnvelopeState === "NOMINAL" ? "ok" : "neg"}`}>
                      <Dot tone={selectedPaperSession.riskEnvelopeState === "NOMINAL" ? "ok" : "neg"} />
                      {selectedPaperSession.riskEnvelopeState}
                    </span>
                  }
                />
                <KV
                  k="Safety Constraint Boundary"
                  v="Paper execution is strictly governed by pre-trade risk envelopes. Zero bypass controls exposed."
                />
              </dl>
            </Panel>

            {/* Panel: Reconciliation & Persistence Health */}
            <Panel label="Reconciliation Engine &amp; State Store Ledger">
              <dl style={{ margin: 0 }}>
                <KV
                  k="Persistence State Store"
                  v={
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <code className="v3-mono">SQLite SQLitePaperStateStore</code>
                      <span className={`v3-chip ${selectedPaperSession.persistenceHealth === "SEALED" ? "ok" : "warn"}`} style={{ fontSize: 9 }}>
                        {selectedPaperSession.persistenceHealth}
                      </span>
                    </div>
                  }
                />
                <KV
                  k="Reconciliation Finding"
                  v={selectedPaperSession.reconciliationFinding || "0 discrepancies detected between simulated order book and broker ledger."}
                />
                <KV
                  k="Promotion Tracking Evidence"
                  v={selectedPaperSession.promotionEvidenceNotes}
                />
              </dl>
            </Panel>

            {/* Panel: Owner Administrative Controls */}
            <Panel label="Owner Administrative Controls">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div className="font-semibold text-xs">Session Administrative Hold</div>
                  <div className="v3-dim text-xs">Control Owner allowance for this session (Session state preserved)</div>
                </div>
                <button
                  type="button"
                  className={`v3-btn mini ${selectedPaperSession.ownerAllowance === "HOLD" ? "primary" : "danger-ghost"}`}
                  onClick={() => handleTogglePaperHold(selectedPaperSession.id, selectedPaperSession.ownerAllowance)}
                  id="drawer-toggle-paper-hold-btn"
                  title="Interactive Prototype — Local State"
                >
                  {selectedPaperSession.ownerAllowance === "HOLD" ? "Allow Session" : "Place Hold on Session"}
                </button>
              </div>
            </Panel>

            {/* Panel: Coordinator Audit Trail */}
            <Panel label="Paper Coordinator Audit &amp; Event Ledger">
              <div className="v3-rows">
                {selectedPaperSession.auditEvents.map((ev, idx) => (
                  <div className="v3-row" key={idx}>
                    <div className="v3-row-main">
                      <div className="v3-row-title" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <Dot tone={ev.tone || "ok"} />
                        <span>{ev.text}</span>
                        <span className="v3-dim text-xs">by {ev.actor}</span>
                      </div>
                    </div>
                    <span className="v3-mono v3-dim text-xs" style={{ fontSize: 10 }}>{ev.time}</span>
                  </div>
                ))}
              </div>
            </Panel>
          </div>
        </Drawer>
      )}
    </>
  );
};
