import { LiveReadinessRuntime } from "../../shared/components/LiveReadinessRuntime";
import { productRuntimeMode } from "../../shared/services/runtimeConfig";
import React, { useState, useMemo, useEffect } from "react";
import { Icon, type IconName } from "../../shared/icons/V3Icons";
import { Panel, Drawer, KV, TruthChip, Dot, fmtINR, fmtSignedINR, fmtSignedPct } from "../../shared/utilities/V3Chrome";
import { AddStrategyModal } from "../components/AddStrategyModal";
import { ProfessionalChart } from "../../shared/components/ProfessionalChart";
import { OrdersPortfolioRuntime } from "../../shared/components/OrdersPortfolioRuntime";
import { queryCurrentUserProfile, queryUserStrategyRegistry, revokeCurrentUserSession, queryPaperSessions, queryPaperPositions, queryPaperEvents, createPaperSession, startPaperSession, stopPaperSession, isBackendEnabled, queryReports, requestStrategyPromotion, type UserProfileData, type UserStrategyEntry, type AuthoritativePaperSession, type PaperSessionCreateRequest, type AuthoritativeReportItem } from "../../shared/services/integrationClient";
import {
  STRATEGIES as INITIAL_STRATEGIES,
  LIVE_ORDERS,
  liveOrderRealizedPnl,
  BACKTEST_RUNS,
  EQUITY_CURVE_SAMPLE,
  PAPER_POSITIONS,
  PORTFOLIO_HOLDINGS,
  REPORTS_LIST,
  SECURITY_SESSIONS,
  WEBAUTHN_KEYS,
  UNDERLYINGS,
  resolveAtmStrike,
  resolveStrikesFromPolicy,
  DEFAULT_GLOBAL_STRIKE_POLICY,
  type GlobalStrikePolicy,
  type MoneynessMode,
  type StrikeDistance,
  type OptionMoneyness,
  type StrategyRow,
  type StrategyStage,
  type OrderRow,
  type LiveOrderRow,
  type LiveOrderStatus,
  type SelectedOptionContract,
  type BacktestRun,
  type PaperPosition,
  LIVE_POSITIONS,
  LIVE_CLOSED_POSITIONS,
  type LivePosition,
  type LiveClosedPosition,
  type StrategyAttributionRow,
} from "../../sampleData";

const STAGE_TONE: Record<StrategyStage, "ok" | "warn" | "dim" | "live"> = {
  LIVE: "ok",
  PAPER: "live",
  BACKTEST_ELIGIBLE: "warn",
  BACKTEST: "dim",
};

/* ════════════════════════════════════════════════════════════
   GOVERNED LIVE READINESS & ELIGIBILITY MODAL
   ============================================================ */
export interface LiveReadinessModalProps {
  open: boolean;
  strategy: StrategyRow | null;
  policy?: GlobalStrikePolicy;
  onClose: () => void;
  onNavigateToDesk?: (s: StrategyRow) => void;
}

export const LiveReadinessModal: React.FC<LiveReadinessModalProps> = ({
  open,
  strategy,
  policy = DEFAULT_GLOBAL_STRIKE_POLICY,
  onClose,
  onNavigateToDesk,
}) => {
  if (!open || !strategy) return null;

  const niftyRes = resolveStrikesFromPolicy(UNDERLYINGS.NIFTY.spot, UNDERLYINGS.NIFTY.step, policy);
  const bnfRes = resolveStrikesFromPolicy(UNDERLYINGS.BANKNIFTY.spot, UNDERLYINGS.BANKNIFTY.step, policy);

  return (
    <div className="v3-modal-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-label="Live Readiness Check">
      <div className="v3-modal" style={{ maxWidth: 640 }} onClick={(e) => e.stopPropagation()}>
        <div className="v3-modal-head">
          <div>
            <div className="v3-modal-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Icon name="shield" size={18} /> Live Deployment Readiness
            </div>
            <div className="v3-modal-sub">
              Governed Eligibility Verification for <b>{strategy.name}</b> <span className="v3-mono v3-dim">({strategy.version})</span>
            </div>
          </div>
          <button className="v3-btn ghost mini" onClick={onClose} aria-label="Close modal">
            <Icon name="close" size={14} />
          </button>
        </div>

        <div className="v3-modal-body" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {/* Governed Safety Protocol Notice */}
          <div className="v3-governed-note">
            <Dot tone="ok" />
            <span>
              <b>Governed Safety Protocol:</b> LIVE action does not automatically start real execution.
              Real execution remains subject to deliberate operator confirmation, broker connectivity, and the AlgoFortis pre-trade risk envelope.
            </span>
          </div>

          {/* Active Global Option Strike Policy Envelope */}
          <div style={{ padding: "10px 14px", background: "var(--v3-surface-1)", borderRadius: 8, border: "1px solid var(--v3-line)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <span className="v3-field-label" style={{ margin: 0 }}>Governed Option Strike Policy</span>
              <span className="v3-chip" style={{ fontSize: 9.5, padding: "1px 6px", color: "var(--v3-profit-text)", background: "rgba(16, 185, 129, 0.12)" }}>
                GLOBAL · APPLIES TO ALL STRATEGIES
              </span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 11.5 }}>
              <div>Active Mode: <b className="v3-mono" style={{ color: "var(--v3-profit-text)" }}>{policy.mode} ({policy.mode === "ATM" ? "0 strikes" : `${policy.distance} strike(s)`})</b></div>
              <div>Strategy Override: <b className="v3-mono">DISABLED (Uniform Global Policy)</b></div>
              <div>NIFTY Target: <b className="v3-mono">{niftyRes.ceStrike} CE / {niftyRes.peStrike} PE</b></div>
              <div>BANKNIFTY Target: <b className="v3-mono">{bnfRes.ceStrike} CE / {bnfRes.peStrike} PE</b></div>
            </div>
          </div>

          {/* 5-Stage Verification Evidence Chain */}
          <div>
            <span className="v3-field-label" style={{ marginBottom: 8, display: "block" }}>
              Governed Lifecycle Verification Evidence Chain
            </span>
            <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 12px", background: "var(--v3-surface-2)", borderRadius: 8, border: "1px solid var(--v3-line)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Icon name="check" size={14} className="v3-profit-text" />
                  <span style={{ fontSize: 12.5, fontWeight: 600, color: "var(--v3-ink)" }}>1. Static AST Scan</span>
                </div>
                <span className="v3-mono v3-profit-text" style={{ fontSize: 11 }}>0 Prohibited AST Imports</span>
              </div>

              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 12px", background: "var(--v3-surface-2)", borderRadius: 8, border: "1px solid var(--v3-line)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Icon name="check" size={14} className="v3-profit-text" />
                  <span style={{ fontSize: 12.5, fontWeight: 600, color: "var(--v3-ink)" }}>2. Conformance Contract</span>
                </div>
                <span className="v3-mono v3-profit-text" style={{ fontSize: 11 }}>BaseStrategy Callbacks Verified</span>
              </div>

              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 12px", background: "var(--v3-surface-2)", borderRadius: 8, border: "1px solid var(--v3-line)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Icon name="check" size={14} className="v3-profit-text" />
                  <span style={{ fontSize: 12.5, fontWeight: 600, color: "var(--v3-ink)" }}>3. Backtest Evidence</span>
                </div>
                <span className="v3-mono v3-profit-text" style={{ fontSize: 11 }}>Quality {strategy.quality}/100 · 30d Replay</span>
              </div>

              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 12px", background: "var(--v3-surface-2)", borderRadius: 8, border: "1px solid var(--v3-line)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Icon name="check" size={14} className="v3-profit-text" />
                  <span style={{ fontSize: 12.5, fontWeight: 600, color: "var(--v3-ink)" }}>4. Paper Evaluation</span>
                </div>
                <span className="v3-mono v3-profit-text" style={{ fontSize: 11 }}>100+ Forward Cycles Passed</span>
              </div>

              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 12px", background: "var(--v3-surface-2)", borderRadius: 8, border: "1px solid var(--v3-line)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Icon name="check" size={14} className="v3-profit-text" />
                  <span style={{ fontSize: 12.5, fontWeight: 600, color: "var(--v3-ink)" }}>5. Explicit LIVE_ELIGIBLE Promotion</span>
                </div>
                <span className="v3-profit-badge">PROMOTED &amp; SEALED</span>
              </div>
            </div>
          </div>

          {/* Pre-Trade Risk Sentinel Guardrails */}
          <div style={{ padding: "10px 14px", background: "var(--v3-surface-1)", borderRadius: 8, border: "1px solid var(--v3-line)" }}>
            <span className="v3-field-label" style={{ marginBottom: 6, display: "block" }}>Active Pre-Trade Risk Sentinel Guardrails</span>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 11.5 }}>
              <div>Max Single Order: <b className="v3-mono">₹1,00,000</b></div>
              <div>Max Day Loss Limit: <b className="v3-mono v3-loss-text">-₹25,000</b></div>
              <div>Slippage Threshold: <b className="v3-mono">0.20%</b></div>
              <div>Killswitch Status: <b className="v3-mono v3-profit-text">ARMED &amp; READY</b></div>
            </div>
          </div>
        </div>

        <div className="v3-modal-foot" style={{ display: "flex", justifyContent: "space-between" }}>
          <button className="v3-btn ghost" onClick={onClose}>
            Close Readiness Check
          </button>
          <button
            className="v3-btn primary"
            id="v3-open-live-desk-btn"
            onClick={() => {
              onClose();
              if (onNavigateToDesk) onNavigateToDesk(strategy);
            }}
          >
            <Icon name="trade" size={13} /> Open Live Execution Desk (Governed Context)
          </button>
        </div>
      </div>
    </div>
  );
};

/* ════════════════════════════════════════════════════════════
   GLOBAL OPTION STRIKE POLICY CONTROL CARD
   ============================================================ */
export interface GlobalStrikePolicyCardProps {
  policy: GlobalStrikePolicy;
  onChangePolicy: (next: GlobalStrikePolicy) => void;
  compact?: boolean;
}

export const GlobalStrikePolicyCard: React.FC<GlobalStrikePolicyCardProps> = ({
  policy,
  onChangePolicy,
  compact = false,
}) => {
  const niftyCfg = UNDERLYINGS.NIFTY;
  const bankNiftyCfg = UNDERLYINGS.BANKNIFTY;

  const niftyRes = resolveStrikesFromPolicy(niftyCfg.spot, niftyCfg.step, policy);
  const bnfRes = resolveStrikesFromPolicy(bankNiftyCfg.spot, bankNiftyCfg.step, policy);

  const setMode = (mode: MoneynessMode) => {
    if (mode === "ATM") {
      onChangePolicy({ mode, distance: 0 });
    } else {
      onChangePolicy({ mode, distance: policy.distance === 0 ? 1 : policy.distance });
    }
  };

  const setDist = (distance: StrikeDistance) => {
    onChangePolicy({ ...policy, distance });
  };

  return (
    <div
      className="v3-panel v3-strike-policy-card"
      style={{
        marginBottom: 16,
        padding: "14px 18px",
        background: "var(--v3-surface-1)",
        border: "1px solid var(--v3-line-strong)",
        borderRadius: 10,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Icon name="layers" size={15} style={{ color: "var(--v3-profit)" }} />
            <h3 style={{ fontSize: 13.5, fontWeight: 700, margin: 0, letterSpacing: "0.02em", color: "var(--v3-ink)" }}>
              GLOBAL OPTION STRIKE POLICY
            </h3>
            <span
              className="v3-chip"
              style={{
                background: "rgba(16, 185, 129, 0.12)",
                color: "var(--v3-profit-text)",
                borderColor: "rgba(16, 185, 129, 0.35)",
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: "0.04em",
              }}
            >
              GLOBAL · APPLIES TO ALL STRATEGIES
            </span>
          </div>
          <p style={{ fontSize: 11.5, color: "var(--v3-ink-3)", margin: "4px 0 0", lineHeight: 1.4 }}>
            Single unified moneyness policy governing all strategies, backtests, paper trading, and order tickets. No strategy-level moneyness override in this prototype.
          </p>
        </div>
        <TruthChip kind="REAL" title="Controls active global option strike target across the entire dashboard." />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: compact ? "1fr" : "1fr 1.2fr 1.8fr", gap: 14, alignItems: "center" }}>
        {/* MODE Selector */}
        <div>
          <label className="v3-field-label" style={{ marginBottom: 5 }}>
            POLICY MODE
          </label>
          <div style={{ display: "flex", gap: 4 }}>
            {(["ATM", "OTM", "ITM"] as const).map((m) => (
              <button
                key={m}
                type="button"
                className={`v3-tf-btn ${policy.mode === m ? "active" : ""}`}
                onClick={() => setMode(m)}
                style={{
                  flex: 1,
                  padding: "6px 0",
                  fontWeight: 700,
                  fontSize: 11.5,
                }}
              >
                {m}
              </button>
            ))}
          </div>
        </div>

        {/* DISTANCE Selector */}
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
            <label className="v3-field-label" style={{ margin: 0 }}>
              STRIKE DISTANCE
            </label>
            {policy.mode === "ATM" && (
              <span className="v3-mono v3-dim" style={{ fontSize: 9.5 }}>Auto-fixed at 0 for ATM</span>
            )}
          </div>
          <div style={{ display: "flex", gap: 3 }}>
            {([0, 1, 2, 3, 4] as const).map((d) => {
              const disabled = (policy.mode === "ATM" && d > 0) || (policy.mode !== "ATM" && d === 0);
              const isSelected = policy.mode === "ATM" ? d === 0 : policy.distance === d;
              return (
                <button
                  key={d}
                  type="button"
                  disabled={disabled}
                  className={`v3-tf-btn ${isSelected ? "active" : ""}`}
                  onClick={() => setDist(d)}
                  style={{
                    flex: 1,
                    padding: "6px 0",
                    fontWeight: 600,
                    fontSize: 11,
                    opacity: disabled ? 0.35 : 1,
                    cursor: disabled ? "not-allowed" : "pointer",
                  }}
                  title={disabled ? (policy.mode === "ATM" ? "ATM mode is always 0 strikes distance (disabled)" : "Select 1-4 strikes for OTM/ITM moneyness") : `${d} strike${d === 1 ? "" : "s"} away from ATM`}
                >
                  {d} {d === 1 ? "stk" : "stks"}
                </button>
              );
            })}
          </div>
        </div>

        {/* Live Resolved Strike Targets Display */}
        <div
          style={{
            padding: "8px 12px",
            background: "var(--v3-surface-2)",
            border: "1px solid var(--v3-line)",
            borderRadius: 8,
            display: "flex",
            flexDirection: "column",
            gap: 4,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 10, color: "var(--v3-ink-dim)", letterSpacing: "0.05em", textTransform: "uppercase" }}>
            <span>Resolved Execution Strikes</span>
            <span className="v3-mono" style={{ color: "var(--v3-profit-text)", fontWeight: 700 }}>
              {policy.mode} {policy.mode === "ATM" ? "(0 strikes)" : `(+${policy.distance} strike${policy.distance === 1 ? "" : "s"})`}
            </span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 11 }}>
            <div>
              <span className="v3-dim">NIFTY: </span>
              <b className="v3-mono" style={{ color: "var(--v3-ink)" }}>
                {niftyRes.ceStrike} CE / {niftyRes.peStrike} PE
              </b>
            </div>
            <div>
              <span className="v3-dim">BANKNIFTY: </span>
              <b className="v3-mono" style={{ color: "var(--v3-ink)" }}>
                {bnfRes.ceStrike} CE / {bnfRes.peStrike} PE
              </b>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

/* ════════════════════════════════════════════════════════════
   1. STRATEGIES WORKSPACE
   ============================================================ */
export interface StrategiesScreenProps {
  onNavigate?: (screen: string, strat?: StrategyRow) => void;
  policy?: GlobalStrikePolicy;
  onChangePolicy?: (next: GlobalStrikePolicy) => void;
}

export const StrategiesScreen: React.FC<StrategiesScreenProps> = ({
  onNavigate,
  policy = DEFAULT_GLOBAL_STRIKE_POLICY,
  onChangePolicy,
}) => {
  const [strategies, setStrategies] = useState<StrategyRow[]>(INITIAL_STRATEGIES);
  const [strategySource, setStrategySource] = useState<"BACKEND" | "SAMPLE">("SAMPLE");
  const [filter, setFilter] = useState<"ALL" | "LIVE" | "PAPER" | "BACKTEST">("ALL");
  const [openDetailId, setOpenDetailId] = useState<string | null>(null);
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [liveReadinessStrat, setLiveReadinessStrat] = useState<StrategyRow | null>(null);
  const [toastMsg, setToastMsg] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    queryUserStrategyRegistry().then((res) => {
      if (!active) return;
      if (res.source === "BACKEND") {
        const list = res.data || [];
        const mapped: StrategyRow[] = list.map((b, idx) => ({
          id: b.strategy_id || `strat-${idx}`,
          strategyId: b.strategy_id,
          name: `Strategy ${b.strategy_id.slice(0, 8)}`,
          version: "v1.0",
          language: "Python",
          stage: (b.stage as any) || "BACKTEST_ELIGIBLE",
          quality: 75,
          evidenceAttached: Boolean(b.source_sha256),
          pnl: "n/a",
          isProfit: true,
          note: `Governed protective policy: ${b.protective_policy || "ACTIVE"}`,
          description: "Governed Python strategy registered in user workspace.",
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
          visibility: (b as any).visibility || "PRIVATE",
        }));
        setStrategies(mapped);
        setStrategySource("BACKEND");
      } else {
        setStrategySource("SAMPLE");
      }
    });
    return () => { active = false; };
  }, []);

  const niftyRes = useMemo(() => {
    return resolveStrikesFromPolicy(UNDERLYINGS.NIFTY.spot, UNDERLYINGS.NIFTY.step, policy);
  }, [policy]);

  const sel = strategies.find((s) => s.id === openDetailId) ?? null;

  const showToast = (msg: string) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 4000);
  };

  const handleAddStrategy = (newStrat: StrategyRow) => {
    setStrategies((prev) => [newStrat, ...prev]);
    showToast(`Strategy "${newStrat.name}" registered successfully.`);
  };

  const filtered = strategies.filter((s) => {
    if (filter === "ALL") return true;
    if (filter === "LIVE") return s.stage === "LIVE";
    if (filter === "PAPER") return s.stage === "PAPER";
    if (filter === "BACKTEST") return s.stage === "BACKTEST_ELIGIBLE" || s.stage === "BACKTEST";
    return true;
  });

  return (
    <>
      <div className="v3-screen-head">
        <div>
          <h2 className="v3-screen-title">Strategies</h2>
          <p className="v3-screen-sub">
            Your Python strategy versions · governed lifecycle, evidence-based promotion
          </p>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <TruthChip kind="SAMPLE" title="DEV SAMPLE · Python Strategy Templates & Envelope Definitions" />
          <button
            className="v3-btn primary"
            onClick={() => setAddModalOpen(true)}
            id="v3-add-strategy-btn"
          >
            <Icon name="plus" size={14} /> Add Strategy
          </button>
        </div>
      </div>

      {toastMsg && (
        <div className="v3-toast" role="status">
          <Icon name="check" size={15} /> {toastMsg}
        </div>
      )}

      {/* ── Global Option Strike Policy Control Panel ── */}
      <GlobalStrikePolicyCard
        policy={policy}
        onChangePolicy={onChangePolicy || (() => {})}
      />

      {/* ── Summary & Filter Tabs ── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14, flexWrap: "wrap", gap: 10 }}>
        <div className="v3-tabs">
          <button className={`v3-tab ${filter === "ALL" ? "active" : ""}`} onClick={() => setFilter("ALL")}>
            All ({strategies.length})
          </button>
          <button className={`v3-tab ${filter === "LIVE" ? "active" : ""}`} onClick={() => setFilter("LIVE")}>
            Live ({strategies.filter((s) => s.stage === "LIVE").length})
          </button>
          <button className={`v3-tab ${filter === "PAPER" ? "active" : ""}`} onClick={() => setFilter("PAPER")}>
            Paper ({strategies.filter((s) => s.stage === "PAPER").length})
          </button>
          <button className={`v3-tab ${filter === "BACKTEST" ? "active" : ""}`} onClick={() => setFilter("BACKTEST")}>
            Backtest ({strategies.filter((s) => s.stage === "BACKTEST_ELIGIBLE" || s.stage === "BACKTEST").length})
          </button>
        </div>
        <span className="v3-mono v3-dim" style={{ fontSize: 11.5 }}>
          {strategies.length} governed algorithms registered
        </span>
      </div>

      <div className="v3-grid">
        <Panel label="Registered Strategy Portfolio" meta="Live / Paper / Backtesting Stages" className="v3-sp12">
          <div className="v3-rows">
            {filtered.length === 0 ? (
              <p role="status" style={{ padding: "24px 16px", color: "var(--v3-ink-dim)", textAlign: "center", margin: 0 }}>
                No strategies assigned
              </p>
            ) : (
              filtered.map((s) => (
                <div
                className="v3-row"
                key={s.id}
                style={{ padding: "14px 4px", borderBottom: "1px solid var(--v3-line)", flexWrap: "wrap" }}
              >
                {/* Main Info */}
                <div style={{ minWidth: 260, flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontWeight: 700, fontSize: 14.5, color: "var(--v3-ink)" }}>
                      {s.name}
                    </span>
                    <span className="v3-mono v3-dim" style={{ fontSize: 11 }}>{s.version}</span>
                    <span className="v3-py-badge"><Icon name="code" size={10} /> Python</span>
                    <span
                      className={
                        s.stage === "LIVE"
                          ? "v3-profit-badge"
                          : s.stage === "PAPER"
                          ? "v3-itm-badge"
                          : s.stage === "BACKTEST_ELIGIBLE"
                          ? "v3-atm-badge"
                          : "v3-otm-badge"
                      }
                    >
                      {s.stage}
                    </span>
                  </div>

                  <div className="v3-row-sub" style={{ marginTop: 4, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                    <span>{s.note}</span>
                    <span className="v3-dim">·</span>
                    <span>Quality: <b>{s.quality}/100</b> {s.evidenceAttached ? "(Evidence Attached)" : "(No Evidence)"}</span>
                    <span className="v3-dim">·</span>
                    <span className="v3-mono v3-dim" style={{ fontSize: 10.5 }}>Updated {s.lastUpdated}</span>
                  </div>

                  {/* Quick Metric Bar */}
                  <div style={{ display: "flex", gap: 14, marginTop: 8, font: "11px var(--v3-mono)", color: "var(--v3-ink-3)", flexWrap: "wrap" }}>
                    <span>Win Rate: <b style={{ color: "var(--v3-ink)" }}>{s.winRate}%</b></span>
                    <span>Max DD: <b style={{ color: "var(--v3-loss-text)" }}>{s.maxDrawdown}%</b></span>
                    <span>Profit Factor: <b style={{ color: "var(--v3-ink)" }}>{s.profitFactor}</b></span>
                    <span>Sharpe: <b style={{ color: "var(--v3-ink)" }}>{s.sharpeRatio}</b></span>
                    <span>Trades: <b style={{ color: "var(--v3-ink)" }}>{s.totalTrades}</b></span>
                  </div>

                  {/* Global Option Target Indicator */}
                  <div style={{ marginTop: 6, display: "flex", alignItems: "center", gap: 8, fontSize: 11, color: "var(--v3-ink-3)", flexWrap: "wrap" }}>
                    <span className="v3-dim">Global Option Target:</span>
                    <b className="v3-mono" style={{ color: "var(--v3-ink)" }}>{niftyRes.ceStrike} CE / {niftyRes.peStrike} PE</b>
                    <span
                      className="v3-chip"
                      style={{
                        fontSize: 9.5,
                        padding: "1px 6px",
                        background: "var(--v3-surface-2)",
                        borderColor: "var(--v3-line)",
                        color: "var(--v3-profit-text)",
                        fontWeight: 700,
                      }}
                    >
                      GLOBAL POLICY ({policy.mode} {policy.mode === "ATM" ? "0 stks" : `+${policy.distance} stk${policy.distance === 1 ? "" : "s"}`})
                    </span>
                  </div>
                </div>

                {/* Quick Mode Actions & PnL */}
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0, flexWrap: "wrap" }}>
                  <span className={s.isProfit ? "v3-profit-text" : "v3-loss-text"} style={{ font: "700 13px var(--v3-mono)", minWidth: 70, textAlign: "right", marginRight: 4 }}>
                    {s.pnl}
                  </span>
                  <Dot tone={STAGE_TONE[s.stage]} />

                  {/* 1. OPEN */}
                  <button
                    className="v3-btn ghost mini"
                    onClick={() => setOpenDetailId(s.id)}
                    title={`Open ${s.name} detail & evidence workspace`}
                  >
                    Open
                  </button>

                  {/* 2. BACKTEST */}
                  <button
                    className="v3-btn ghost mini"
                    onClick={() => {
                      if (onNavigate) onNavigate("backtest", s);
                      else showToast(`Navigating to Backtesting with ${s.name} preselected.`);
                    }}
                    title={`Run historical backtest on ${s.name} ${s.version}`}
                  >
                    <Icon name="play" size={11} /> Backtest
                  </button>

                  {/* 3. PAPER */}
                  <button
                    className="v3-btn ghost mini"
                    onClick={() => {
                      if (onNavigate) onNavigate("paper", s);
                      else showToast(`Navigating to Paper Trading with ${s.name} preselected.`);
                    }}
                    title={`Forward test ${s.name} ${s.version} in Paper Simulation`}
                  >
                    <Icon name="layers" size={11} /> Paper
                  </button>

                  {/* 4. LIVE (Opens Governed Readiness Workspace) */}
                  {s.stage === "LIVE" ? (
                    <button
                      className="v3-btn ghost mini v3-profit-text"
                      onClick={() => {
                        setLiveReadinessStrat(s);
                      }}
                      title={`Open Governed Live Readiness Check for ${s.name}`}
                    >
                      <Icon name="trade" size={11} /> Live
                    </button>
                  ) : (
                    <button
                      className="v3-btn ghost mini"
                      onClick={() => {
                        showToast(`LIVE LOCKED for "${s.name}": Currently in ${s.stage} stage. Direct live promotion is prohibited. Required promotion chain: Static Scan → Conformance → Backtest Evidence → Paper Evaluation → Explicit LIVE_ELIGIBLE Promotion.`);
                      }}
                      title={`LIVE LOCKED: Stage is ${s.stage}. Requires: Static Scan → Conformance → Backtest Evidence → Paper Evaluation → Explicit LIVE_ELIGIBLE Promotion.`}
                      style={{ opacity: 0.7, color: "var(--v3-ink-dim)" }}
                    >
                      <Icon name="lock" size={10} /> Live <span style={{ fontSize: 9.5 }}>(Locked)</span>
                    </button>
                  )}

                  {/* 5. MORE (...) Secondary Actions */}
                  <div style={{ position: "relative" }}>
                    <button
                      className="v3-btn ghost mini"
                      style={{ padding: "4px 7px" }}
                      onClick={() => setActiveMenuId((curr) => (curr === s.id ? null : s.id))}
                      aria-label={`More actions for ${s.name}`}
                      title="Secondary actions"
                    >
                      <Icon name="more" size={14} />
                    </button>

                    {activeMenuId === s.id && (
                      <div className="v3-context-menu" role="menu">
                        <button role="menuitem" onClick={() => { setActiveMenuId(null); showToast(`Draft version created for ${s.name}.`); }}>
                          <Icon name="plus" size={12} /> New Version
                        </button>
                        <button role="menuitem" onClick={() => { setActiveMenuId(null); setOpenDetailId(s.id); }}>
                          <Icon name="file" size={12} /> Edit Metadata
                        </button>
                        <button role="menuitem" onClick={() => { setActiveMenuId(null); setOpenDetailId(s.id); }}>
                          <Icon name="shield" size={12} /> View Validation Report
                        </button>
                        <button role="menuitem" onClick={() => { setActiveMenuId(null); showToast(`Strategy ${s.name} disabled.`); }}>
                          <Icon name="pause" size={12} /> Disable
                        </button>
                        <button role="menuitem" onClick={() => { setActiveMenuId(null); showToast(`Strategy ${s.name} archived.`); }} style={{ color: "var(--v3-ink-dim)" }}>
                          <Icon name="lock" size={12} /> Archive (No Delete)
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )))}
          </div>
        </Panel>
      </div>

      {/* ── Strategy Detail Drawer ── */}
      <Drawer
        open={sel !== null}
        title={sel ? `${sel.name} ${sel.version}` : ""}
        sub="Governed Promotion Evidence & Audit Details"
        onClose={() => setOpenDetailId(null)}
      >
        {sel && (
          <>
            <div className="v3-lifecycle-diagram" style={{ margin: "0 0 16px" }}>
              <div className="v3-lifecycle-step done"><span className="step-num">1</span><span>Scan</span></div>
              <span className="step-arrow">→</span>
              <div className="v3-lifecycle-step done"><span className="step-num">2</span><span>Conformance</span></div>
              <span className="step-arrow">→</span>
              <div className={`v3-lifecycle-step ${sel.stage !== "BACKTEST_ELIGIBLE" ? "done" : "active"}`}><span className="step-num">3</span><span>Backtest</span></div>
              <span className="step-arrow">→</span>
              <div className={`v3-lifecycle-step ${sel.stage === "LIVE" ? "done" : sel.stage === "PAPER" ? "active" : ""}`}><span className="step-num">4</span><span>Paper</span></div>
              <span className="step-arrow">→</span>
              <div className={`v3-lifecycle-step ${sel.stage === "LIVE" ? "done" : ""}`}><span className="step-num">5</span><span>LIVE_ELIGIBLE</span></div>
            </div>

            <dl style={{ margin: "0 0 18px" }}>
              <KV k="Language" v="Python (algofortis.strategy.BaseStrategy)" />
              <KV k="Lifecycle Stage" v={sel.stage} />
              <KV
                k="Global Option Strike Policy"
                v={`GLOBAL · ${policy.mode} (${policy.mode === "ATM" ? "0 strikes" : `${policy.distance} strike(s)`}) -> ${niftyRes.ceStrike} CE / ${niftyRes.peStrike} PE`}
                vClass="v3-profit-text"
              />
              <KV k="Strategy Moneyness Override" v="Disabled (Uniform Global Policy Enforced Across All Strategies)" />
              <KV k="Quality Score" v={`${sel.quality}/100 · Conformance verified`} />
              <KV k="Win Rate" v={sel.winRate !== undefined ? `${sel.winRate}%` : "—"} />
              <KV k="Max Drawdown" v={sel.maxDrawdown !== undefined ? `${sel.maxDrawdown}%` : "—"} vClass="v3-loss-text" />
              <KV k="Profit Factor" v={sel.profitFactor?.toString() ?? "—"} />
              <KV k="Sharpe Ratio" v={sel.sharpeRatio?.toString() ?? "—"} />
              <KV k="Total Trades" v={sel.totalTrades?.toString() ?? "—"} />
              <KV k="Static AST Scan" v={sel.scanStatus} vClass="v3-profit-text" />
              <KV k="Author" v={sel.author} />
              <KV k="Updated" v={sel.lastUpdated} />
              <KV k="Description" v={sel.description} />
            </dl>

            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {sel.stage === "BACKTEST_ELIGIBLE" && (
                <div style={{ fontSize: 12, color: "var(--v3-ink-2)", padding: "8px 12px", border: "1px solid var(--v3-line)", borderRadius: 6 }}>
                  Backtest and Paper are self-service on this validated strategy — no owner approval needed for ordinary runs.
                  Use Backtesting and Paper Trading directly.
                </div>
              )}
              {sel.stage === "PAPER" && (
                <button
                  className="v3-btn secondary"
                  disabled
                  title="Live promotion is future functionality and remains disabled while live execution is disarmed."
                >
                  <Icon name="lock" size={13} /> Request LIVE Promotion — Future / Disabled While Disarmed
                </button>
              )}
              <button className="v3-btn ghost" onClick={() => showToast(`Exported report for ${sel.name}.`)}>
                <Icon name="file" size={13} /> Export AST &amp; Quality Audit
              </button>
            </div>
          </>
        )}
      </Drawer>

      <AddStrategyModal open={addModalOpen} onClose={() => setAddModalOpen(false)} onAddStrategy={handleAddStrategy} />

      {/* Governed Live Readiness Workspace Modal */}
      <LiveReadinessModal
        open={liveReadinessStrat !== null}
        strategy={liveReadinessStrat}
        policy={policy}
        onClose={() => setLiveReadinessStrat(null)}
        onNavigateToDesk={(strat) => {
          if (onNavigate) onNavigate("trading", strat);
          else showToast(`Navigating to Live Trading desk for ${strat.name} (Governed Risk Guardrails Active).`);
        }}
      />
    </>
  );
};

/* ════════════════════════════════════════════════════════════
   2. STRATEGY EXECUTION WORKSPACE (GOVERNED EXECUTION ENGINE)
   ============================================================ */
export interface StrategyExecutionScreenProps {
  previewMode?: boolean;
  initialStrategy?: StrategyRow | null;
  policy?: GlobalStrikePolicy;
  onChangePolicy?: (next: GlobalStrikePolicy) => void;
}

export interface ExecutionEvent {
  id: string;
  time: string;
  type: "SIGNAL" | "RISK" | "CONTRACT" | "ORDER" | "FILL" | "POSITION" | "PROTECT" | "REJECT";
  title: string;
  detail: string;
  tone: "ok" | "warn" | "neg" | "live";
}

const StrategyExecutionPreviewScreen: React.FC<StrategyExecutionScreenProps> = ({
  initialStrategy,
  policy = DEFAULT_GLOBAL_STRIKE_POLICY,
  onChangePolicy,
}) => {
  // Strategy profiles
  const [selectedStratId, setSelectedStratId] = useState<string>(() =>
    initialStrategy ? initialStrategy.id : "s1"
  );
  const [simulatedBlock, setSimulatedBlock] = useState(false);
  const [chartTarget, setChartTarget] = useState<"underlying" | "contract">("underlying");
  const [toastMsg, setToastMsg] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 3000);
  };

  // Determine current active strategy profile
  const stratMeta = useMemo(() => {
    const s = INITIAL_STRATEGIES.find((item) => item.id === selectedStratId) || INITIAL_STRATEGIES[0];
    const isBlocked = simulatedBlock || s.id === "s3";
    const isLiveReady = s.id === "s4";
    const underlying = s.name.toLowerCase().includes("bank") ? "BANKNIFTY" : "NIFTY";
    const uCfg = UNDERLYINGS[underlying];
    
    // Resolve dynamic strikes from global policy
    const policyRes = resolveStrikesFromPolicy(uCfg.spot, uCfg.step, policy);
    const resolvedAtm = resolveAtmStrike(uCfg.spot, uCfg.step);
    const optType: "CE" | "PE" = s.id === "s2" ? "CE" : "CE";
    const targetStrike = optType === "CE" ? policyRes.ceStrike : policyRes.peStrike;
    
    const moneyness: OptionMoneyness = policy.mode;
    const baseTimeVal = underlying === "BANKNIFTY" ? 350 : 140;
    const stepDecay = underlying === "BANKNIFTY" ? 0.042 : 0.12;
    const intrinsic = optType === "CE" ? Math.max(0, uCfg.spot - targetStrike) : Math.max(0, targetStrike - uCfg.spot);
    const timeVal = Math.max(16, baseTimeVal - Math.abs(targetStrike - resolvedAtm) * stepDecay);
    const estLtp = Number((intrinsic + timeVal).toFixed(2));

    const contractTag = `${underlying} · ${uCfg.expiries[0]} · ${targetStrike} ${optType} · ${policy.mode} (${policy.distance === 0 ? "0" : policy.distance})`;

    // Dynamic mathematical position calculation (Unrealized P&L = (LTP - Entry) * Qty, Return % = (LTP - Entry)/Entry * 100)
    const hasPosition = !isBlocked && !isLiveReady;
    const lots = underlying === "BANKNIFTY" ? 1.2 : 2;
    const qty = underlying === "BANKNIFTY" ? 60 : 100;
    const avgEntry = underlying === "BANKNIFTY" ? 310.20 : 128.00;
    const currentLtp = estLtp;
    const pnl = Number(((currentLtp - avgEntry) * qty).toFixed(2));
    const pnlPct = Number((((currentLtp - avgEntry) / avgEntry) * 100).toFixed(2));
    const stopLoss: number | null = null;
    const target: number | null = null;

    const position = hasPosition ? {
      symbol: `${underlying} ${targetStrike} ${optType} ${uCfg.expiries[0]}`,
      contractTag,
      lots,
      qty,
      avgEntry,
      currentLtp,
      pnl,
      pnlPct,
      stopLoss,
      target,
      trailingState: "Armed (0.50% Step / +5% Trigger)",
      protectiveStatus: "Protected by deterministic execution guard",
      entryTime: underlying === "BANKNIFTY" ? "09:30:18 IST" : "10:32:20 IST",
    } : null;

    // Pipeline states
    const pipeline = {
      signal: isLiveReady ? ("WAITING" as const) : ("PASSED" as const),
      risk: isBlocked ? ("REJECTED" as const) : ("PASSED" as const),
      strike: isBlocked ? ("WAITING" as const) : ("PASSED" as const),
      order: isBlocked ? ("REJECTED" as const) : isLiveReady ? ("WAITING" as const) : ("FILLED" as const),
      position: isBlocked ? ("REJECTED" as const) : isLiveReady ? ("WAITING" as const) : ("ACTIVE" as const),
      protective: isBlocked ? ("REJECTED" as const) : isLiveReady ? ("WAITING" as const) : ("ARMED" as const),
    };

    // Execution event logs
    const events: ExecutionEvent[] = isBlocked ? [
      { id: "e1", time: "11:15:02 IST", type: "REJECT", title: "FAIL-CLOSED ACTIVE", detail: "Execution halted to protect session capital. Pre-trade envelope sealed.", tone: "neg" },
      { id: "e2", time: "11:15:01 IST", type: "REJECT", title: "Risk Gate Rejected", detail: "Daily strategy frequency limit exceeded (10/10 trades executed). Order creation aborted.", tone: "neg" },
      { id: "e3", time: "11:15:00 IST", type: "SIGNAL", title: "Signal Generated", detail: "BUY Signal generated on Gap Fade Alpha (Z-Score +2.45)", tone: "ok" },
    ] : isLiveReady ? [
      { id: "e1", time: "11:40:00 IST", type: "RISK", title: "Governance Check Passed", detail: "Governed Live Readiness verified (Score 83/100). Standby for market open.", tone: "ok" },
      { id: "e2", time: "11:39:50 IST", type: "SIGNAL", title: "Monitoring Market", detail: "Tick-level evaluation active (12ms loop nominal). 0 orders queued.", tone: "live" },
    ] : [
      { id: "e1", time: position?.entryTime || "10:32:20 IST", type: "POSITION", title: "Position Opened & Protected", detail: `Active 2 Lots (${position?.qty} Qty) @ ₹${position?.avgEntry}. Stop-loss and Target armed.`, tone: "ok" },
      { id: "e2", time: "10:32:20 IST", type: "FILL", title: "Fill Simulated", detail: `Simulated fill @ ₹${position?.avgEntry} (Zero-Slippage Paper Model). Order ord-883925 filled.`, tone: "ok" },
      { id: "e3", time: "10:32:19 IST", type: "ORDER", title: "Paper Order Created", detail: `Limit order ord-883925 placed at ₹${position?.avgEntry} on ${underlying} ${targetStrike} ${optType}.`, tone: "ok" },
      { id: "e4", time: "10:32:19 IST", type: "CONTRACT", title: "Contract Resolved", detail: `Selected ${contractTag} via Global Option Strike Policy (${policy.mode} ${policy.distance} stks).`, tone: "ok" },
      { id: "e5", time: "10:32:18 IST", type: "RISK", title: "Risk Gate Passed", detail: "Pre-trade envelope checks OK: Margin nominal, drawdown limit nominal, killswitch armed.", tone: "ok" },
      { id: "e6", time: "10:32:18 IST", type: "SIGNAL", title: "Signal Generated: BUY", detail: `Algorithm emitted BUY signal on 15m Momentum Reversion (Z-Score +2.18).`, tone: "ok" },
    ];

    return {
      strategy: s,
      isBlocked,
      isLiveReady,
      underlying,
      uCfg,
      policyRes,
      resolvedAtm,
      optType,
      targetStrike,
      moneyness,
      estLtp,
      contractTag,
      position,
      pipeline,
      events,
    };
  }, [selectedStratId, simulatedBlock, policy]);

  // Selected Option Contract object for the Canvas Candlestick chart
  const activeSelectedContract: SelectedOptionContract = useMemo(() => ({
    underlying: stratMeta.underlying,
    expiry: stratMeta.uCfg.expiries[0],
    strike: stratMeta.targetStrike,
    optionType: stratMeta.optType,
    moneyness: stratMeta.moneyness,
    ltp: stratMeta.estLtp,
    change: 4.80,
    changePct: 3.90,
    bid: Number((stratMeta.estLtp - 0.20).toFixed(2)),
    ask: Number((stratMeta.estLtp + 0.20).toFixed(2)),
    volume: "85.2k",
    oi: "1.42M",
    oiChange: "+4.2%",
    iv: "13.8%",
    delta: stratMeta.optType === "CE" ? 0.44 : -0.44,
    theta: -14.2,
    gamma: 0.0018,
    vega: 12.5,
    lotSize: stratMeta.uCfg.lotSize,
    greeksAuthority: "DEV_SAMPLE_ESTIMATED",
  }), [stratMeta]);

  return (
    <>
      {/* ── 1. Strategy Execution Header ── */}
      <div className="v3-screen-head">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <h2 className="v3-screen-title">Trading & Execution</h2>
            <span
              className="v3-chip"
              style={{
                background: stratMeta.isBlocked ? "rgba(239, 68, 68, 0.12)" : "rgba(16, 185, 129, 0.12)",
                color: stratMeta.isBlocked ? "var(--v3-loss-text)" : "var(--v3-profit-text)",
                borderColor: stratMeta.isBlocked ? "rgba(239, 68, 68, 0.35)" : "rgba(16, 185, 129, 0.35)",
                fontWeight: 700,
              }}
            >
              {stratMeta.isBlocked ? "BLOCKED · FAIL-CLOSED ACTIVE" : stratMeta.isLiveReady ? "LIVE READINESS · VIEW ONLY" : "PAPER EXECUTION ACTIVE"}
            </span>
          </div>
          <p className="v3-screen-sub">
            Autonomous algorithmic execution pipeline · governed signals, pre-trade risk gates, protective state
          </p>
        </div>

        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <TruthChip kind="SAMPLE" title="Strategy signals and executions are simulated in safe prototype state." />
          
          {/* Strategy Selector Dropdown */}
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <label className="v3-field-label" style={{ margin: 0, fontSize: 11 }}>Active Strategy:</label>
            <select
              className="v3-input"
              style={{ padding: "5px 10px", height: 32, fontSize: 12, minWidth: 220 }}
              value={selectedStratId}
              onChange={(e) => {
                setSelectedStratId(e.target.value);
                setSimulatedBlock(false);
              }}
              id="v3-strategy-selector"
            >
              {INITIAL_STRATEGIES.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.version}) — {s.stage}
                </option>
              ))}
            </select>
          </div>

          {/* Simulate Block / Reset Button for Demo Testing */}
          <button
            className={`v3-btn mini ${stratMeta.isBlocked ? "primary" : "ghost"}`}
            onClick={() => {
              setSimulatedBlock((prev) => !prev);
              showToast(simulatedBlock ? "Restored nominal risk envelope state." : "Simulated Pre-Trade Risk Gate Rejection (Fail-Closed).");
            }}
            id="v3-simulate-block-btn"
            title="Demonstrate AlgoFortis fail-closed risk gate behavior"
          >
            <Icon name={stratMeta.isBlocked ? "refresh" : "alert"} size={13} />
            {stratMeta.isBlocked ? "Reset to Nominal" : "Simulate Risk Block"}
          </button>
        </div>
      </div>

      {toastMsg && (
        <div className="v3-toast" role="status">
          <Icon name="check" size={15} /> {toastMsg}
        </div>
      )}

      {/* ── 2. Top Status Cards: Active Strategy Summary & Global Policy ── */}
      <div className="v3-grid" style={{ marginBottom: 16 }}>
        {/* Active Strategy Status Block */}
        <div className="v3-panel v3-sp6" style={{ margin: 0 }}>
          <div className="v3-panel-head">
            <span className="v3-panel-label">Active Strategy Summary</span>
            <span className="v3-mono" style={{ fontSize: 11, color: "var(--v3-profit-text)" }}>
              Quality: <b>{stratMeta.strategy.quality}/100</b> (Evidence Sealed)
            </span>
          </div>
          <div className="v3-exec-split-card">
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                <span style={{ fontSize: 16, fontWeight: 700, color: "var(--v3-ink)" }}>
                  {stratMeta.strategy.name}
                </span>
                <span className="v3-mono v3-dim" style={{ fontSize: 11.5 }}>
                  {stratMeta.strategy.version}
                </span>
              </div>
              <div style={{ fontSize: 11.5, color: "var(--v3-ink-3)" }}>
                {stratMeta.strategy.description}
              </div>
              <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 4 }}>
                <span className={stratMeta.strategy.stage === "LIVE" ? "v3-profit-badge" : "v3-itm-badge"}>
                  {stratMeta.strategy.stage}
                </span>
                <span className="v3-py-badge">
                  <Icon name="code" size={10} /> Python 3.12
                </span>
                <span className="v3-chip" style={{ fontSize: 9.5 }}>
                  Execution Guard: Enforced
                </span>
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 11, background: "var(--v3-surface-2)", padding: "8px 12px", borderRadius: 8, border: "1px solid var(--v3-line)" }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span className="v3-dim">Execution State:</span>
                <b className="v3-mono" style={{ color: stratMeta.isBlocked ? "var(--v3-loss-text)" : "var(--v3-profit-text)" }}>
                  {stratMeta.isBlocked ? "BLOCKED (FAIL-CLOSED)" : stratMeta.isLiveReady ? "READY (WAITING)" : "RUNNING NOMINAL"}
                </b>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span className="v3-dim">Last Signal:</span>
                <b className="v3-mono">{stratMeta.isLiveReady ? "MONITORING" : "BUY / LONG"}</b>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span className="v3-dim">Signal Time:</span>
                <span className="v3-mono">{stratMeta.isBlocked ? "11:15:00 IST" : "10:32:18 IST"}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span className="v3-dim">Risk Gate:</span>
                <b className="v3-mono" style={{ color: stratMeta.isBlocked ? "var(--v3-loss-text)" : "var(--v3-profit-text)" }}>
                  {stratMeta.isBlocked ? "REJECTED" : "PASSED (All Green)"}
                </b>
              </div>
            </div>
          </div>
        </div>

        {/* Global Option Strike Policy Card */}
        <div className="v3-panel v3-sp6" style={{ margin: 0 }}>
          <div className="v3-panel-head">
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Icon name="layers" size={13} style={{ color: "var(--v3-profit)" }} />
              <span className="v3-panel-label">Global Option Strike Policy</span>
            </div>
            <span
              className="v3-chip"
              style={{
                background: "rgba(16, 185, 129, 0.12)",
                color: "var(--v3-profit-text)",
                borderColor: "rgba(16, 185, 129, 0.35)",
                fontSize: 9.5,
                fontWeight: 700,
              }}
            >
              GLOBAL · APPLIES TO ALL STRATEGIES
            </span>
          </div>

          <div className="v3-exec-split-card" style={{ alignItems: "center" }}>
            <div>
              <div style={{ fontSize: 11, color: "var(--v3-ink-3)", marginBottom: 4 }}>
                Active Moneyness Policy:
              </div>
              <div style={{ fontSize: 15, fontWeight: 700, color: "var(--v3-profit-text)", fontFamily: "var(--v3-mono)" }}>
                {policy.mode} · {policy.mode === "ATM" ? "0 STRIKES" : `${policy.distance} STRIKE${policy.distance === 1 ? "" : "S"}`}
              </div>
              <div style={{ fontSize: 10.5, color: "var(--v3-ink-dim)", marginTop: 2 }}>
                No strategy-level moneyness override.
              </div>
            </div>

            <div style={{ padding: "8px 12px", background: "var(--v3-surface-2)", borderRadius: 8, border: "1px solid var(--v3-line)", fontSize: 11 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                <span className="v3-dim">Resolved ATM:</span>
                <b className="v3-mono">{stratMeta.resolvedAtm}</b>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                <span className="v3-dim">CE Target:</span>
                <b className="v3-mono" style={{ color: "var(--v3-ink)" }}>{stratMeta.policyRes.ceStrike} CE</b>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span className="v3-dim">PE Target:</span>
                <b className="v3-mono" style={{ color: "var(--v3-ink)" }}>{stratMeta.policyRes.peStrike} PE</b>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── 3. Signal → Execution Pipeline ── */}
      <div className="v3-panel" style={{ marginBottom: 16 }}>
        <div className="v3-panel-head">
          <span className="v3-panel-label">Autonomous Signal → Execution Pipeline</span>
          <span className="v3-panel-meta">End-to-end governed order lifecycle</span>
        </div>

        <div className="v3-exec-pipeline">
          {/* Step 1: Signal */}
          <div className={`v3-pipeline-card ${stratMeta.pipeline.signal.toLowerCase()}`}>
            <div className="v3-pipeline-step-head">
              <span className="v3-pipeline-step-name">1. Signal</span>
              <Icon name={stratMeta.pipeline.signal === "PASSED" ? "check" : "clock"} size={13} className={stratMeta.pipeline.signal === "PASSED" ? "v3-profit-text" : "v3-dim"} />
            </div>
            <div className="v3-pipeline-step-val">{stratMeta.isLiveReady ? "Monitoring Tick" : "BUY / LONG"}</div>
            <div className="v3-pipeline-step-sub">{stratMeta.isBlocked ? "11:15:00 IST" : "10:32:18 IST"}</div>
          </div>

          {/* Step 2: Risk Check */}
          <div className={`v3-pipeline-card ${stratMeta.pipeline.risk.toLowerCase()}`}>
            <div className="v3-pipeline-step-head">
              <span className="v3-pipeline-step-name">2. Risk Check</span>
              <Icon name={stratMeta.pipeline.risk === "PASSED" ? "check" : "alert"} size={13} className={stratMeta.pipeline.risk === "PASSED" ? "v3-profit-text" : "v3-loss-text"} />
            </div>
            <div className="v3-pipeline-step-val">{stratMeta.isBlocked ? "REJECTED (Cap)" : "PASSED (Green)"}</div>
            <div className="v3-pipeline-step-sub">{stratMeta.isBlocked ? "Daily limit hit" : "6/6 Envelopes OK"}</div>
          </div>

          {/* Step 3: Contract Resolution */}
          <div className={`v3-pipeline-card ${stratMeta.pipeline.strike.toLowerCase()}`}>
            <div className="v3-pipeline-step-head">
              <span className="v3-pipeline-step-name">3. Strike Policy</span>
              <Icon name={stratMeta.pipeline.strike === "PASSED" ? "check" : "clock"} size={13} className={stratMeta.pipeline.strike === "PASSED" ? "v3-profit-text" : "v3-dim"} />
            </div>
            <div className="v3-pipeline-step-val">{stratMeta.isBlocked ? "ABORTED" : `${stratMeta.targetStrike} ${stratMeta.optType}`}</div>
            <div className="v3-pipeline-step-sub">{policy.mode} {policy.distance} stks</div>
          </div>

          {/* Step 4: Order Created */}
          <div className={`v3-pipeline-card ${stratMeta.pipeline.order.toLowerCase()}`}>
            <div className="v3-pipeline-step-head">
              <span className="v3-pipeline-step-name">4. Order Created</span>
              <Icon name={stratMeta.pipeline.order === "FILLED" ? "check" : stratMeta.pipeline.order === "REJECTED" ? "alert" : "clock"} size={13} className={stratMeta.pipeline.order === "FILLED" ? "v3-profit-text" : stratMeta.pipeline.order === "REJECTED" ? "v3-loss-text" : "v3-dim"} />
            </div>
            <div className="v3-pipeline-step-val">{stratMeta.isBlocked ? "BLOCKED" : stratMeta.isLiveReady ? "STANDBY" : "FILLED (ord-88)"}</div>
            <div className="v3-pipeline-step-sub">{stratMeta.position ? `Limit ₹${stratMeta.position.avgEntry}` : "No order queued"}</div>
          </div>

          {/* Step 5: Position Active */}
          <div className={`v3-pipeline-card ${stratMeta.pipeline.position.toLowerCase()}`}>
            <div className="v3-pipeline-step-head">
              <span className="v3-pipeline-step-name">5. Position</span>
              <Icon name={stratMeta.pipeline.position === "ACTIVE" ? "check" : stratMeta.pipeline.position === "REJECTED" ? "alert" : "clock"} size={13} className={stratMeta.pipeline.position === "ACTIVE" ? "v3-profit-text" : "v3-dim"} />
            </div>
            <div className="v3-pipeline-step-val">{stratMeta.position ? "ACTIVE (Open)" : "NONE"}</div>
            <div className="v3-pipeline-step-sub">{stratMeta.position ? `${stratMeta.position.lots} Lots (${stratMeta.position.qty} Q)` : "0 open units"}</div>
          </div>

          {/* Step 6: Protective State */}
          <div className={`v3-pipeline-card ${stratMeta.pipeline.protective.toLowerCase()}`}>
            <div className="v3-pipeline-step-head">
              <span className="v3-pipeline-step-name">6. Protection</span>
              <Icon name={stratMeta.pipeline.protective === "ARMED" ? "shield" : stratMeta.pipeline.protective === "REJECTED" ? "alert" : "clock"} size={13} className={stratMeta.pipeline.protective === "ARMED" ? "v3-profit-text" : "v3-dim"} />
            </div>
            <div className="v3-pipeline-step-val">{stratMeta.position ? "ARMED (SL/Tgt)" : stratMeta.isBlocked ? "FAIL-CLOSED" : "STANDBY"}</div>
            <div className="v3-pipeline-step-sub">{stratMeta.position ? (stratMeta.position.stopLoss != null ? `SL: ₹${stratMeta.position.stopLoss}` : "SL: UNAVAILABLE") : "Protective ready"}</div>
          </div>
        </div>
      </div>

      {/* ── 4. Blocked / Rejected State Banner (if applicable) ── */}
      {stratMeta.isBlocked && (
        <div className="v3-failclosed-card" role="alert">
          <div className="v3-failclosed-head">
            <div className="v3-failclosed-title">
              <Icon name="alert" size={18} />
              PRE-TRADE RISK GATE REJECTED · FAIL-CLOSED ACTIVE
            </div>
            <span className="v3-chip" style={{ background: "rgba(239, 68, 68, 0.2)", color: "var(--v3-loss-text)", borderColor: "rgba(239, 68, 68, 0.4)", fontWeight: 700 }}>
              EXECUTION HALTED
            </span>
          </div>
          <p style={{ fontSize: 12.5, color: "var(--v3-ink)", margin: "4px 0 8px", lineHeight: 1.4 }}>
            <b>Reason:</b> Daily strategy trade frequency limit reached (10/10 trades executed). AlgoFortis Pre-Trade Risk Watchdog intercepted and rejected order creation to protect account drawdown envelopes.
          </p>
          <div style={{ display: "flex", gap: 16, fontSize: 11.5, color: "var(--v3-ink-3)", flexWrap: "wrap" }}>
            <span>Policy: <b>Fail-Closed Invariant Maintained</b></span>
            <span>Broker Communication: <b>0 Orders Emitted</b></span>
            <span>Action Required: <b>Awaiting Risk Manager reset or next daily session window</b></span>
          </div>
        </div>
      )}

      {/* ── 5. Main Execution Grid: Chart (Left) + Contract & Position (Right) ── */}
      <div className="v3-exec-grid">
        {/* Left: Professional Interactive Candlestick Chart */}
        <div>
          <div className="v3-panel" style={{ padding: 0, overflow: "hidden", margin: 0 }}>
            <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--v3-line)", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span className="v3-panel-label" style={{ margin: 0 }}>Execution Canvas Chart</span>
                <span className="v3-chip sample" style={{ fontSize: 9.5 }}>HIGH-DPI CANDLESTICK</span>
              </div>
              <div style={{ display: "flex", gap: 4 }}>
                <button
                  type="button"
                  className={`v3-btn ghost mini ${chartTarget === "underlying" ? "active" : ""}`}
                  onClick={() => setChartTarget("underlying")}
                  style={{ fontSize: 11 }}
                >
                  Underlying ({stratMeta.underlying})
                </button>
                <button
                  type="button"
                  className={`v3-btn ghost mini ${chartTarget === "contract" ? "active" : ""}`}
                  onClick={() => setChartTarget("contract")}
                  style={{ fontSize: 11 }}
                >
                  Option ({stratMeta.targetStrike} {stratMeta.optType})
                </button>
              </div>
            </div>

            <ProfessionalChart
              underlying={stratMeta.underlying}
              selectedContract={chartTarget === "contract" ? activeSelectedContract : null}
              chartTarget={chartTarget}
              onToggleTarget={(target) => setChartTarget(target)}
            />
          </div>
        </div>

        {/* Right Column: Resolved Contract & Open Position / Protective State */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {/* Card A: Exact Resolved Option Contract Details */}
          <div className="v3-panel" style={{ margin: 0 }}>
            <div className="v3-panel-head">
              <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                <span className="v3-panel-label">Resolved Option Contract</span>
                <TruthChip kind="SAMPLE" title="Greeks, IV, OI & Bid/Ask are estimated prototype values (non-authoritative)." />
              </div>
              <span className={stratMeta.moneyness === "ATM" ? "v3-atm-badge" : stratMeta.moneyness === "ITM" ? "v3-itm-badge" : "v3-otm-badge"}>
                {stratMeta.moneyness}
              </span>
            </div>

            <div style={{ padding: "10px 12px", background: "var(--v3-surface-2)", borderRadius: 8, border: "1px solid var(--v3-line)", marginBottom: 10 }}>
              <div style={{ fontSize: 13.5, fontWeight: 700, color: "var(--v3-ink)", fontFamily: "var(--v3-mono)", letterSpacing: "0.02em" }}>
                {stratMeta.contractTag}
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 8, fontSize: 11 }}>
                <div>Underlying Spot: <b className="v3-mono">₹{stratMeta.uCfg.spot.toFixed(2)}</b></div>
                <div>Resolved ATM: <b className="v3-mono">{stratMeta.resolvedAtm}</b></div>
                <div>Target Strike: <b className="v3-mono">{stratMeta.targetStrike} {stratMeta.optType}</b></div>
                <div>Expiry: <b className="v3-mono">{stratMeta.uCfg.expiries[0]}</b></div>
              </div>
            </div>

            {/* Greeks & Real-time Depth */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 6, fontSize: 11, background: "var(--v3-surface-1)", padding: "8px 10px", borderRadius: 8, border: "1px solid var(--v3-line)" }}>
              <div>LTP: <b className="v3-mono">₹{stratMeta.estLtp.toFixed(2)}</b></div>
              <div>Delta: <b className="v3-mono">{stratMeta.optType === "CE" ? "+0.44" : "-0.44"}</b></div>
              <div>IV: <b className="v3-mono">13.8%</b></div>
              <div>Theta: <b className="v3-mono v3-loss-text">-14.2</b></div>
              <div>Vega: <b className="v3-mono">12.5</b></div>
              <div>OI: <b className="v3-mono">1.42M</b></div>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 6, fontSize: 9.5, color: "var(--v3-ink-dim)" }}>
              <span>Bid/Ask: <b className="v3-mono" style={{ color: "var(--v3-ink-3)" }}>₹{(stratMeta.estLtp - 0.20).toFixed(2)} / ₹{(stratMeta.estLtp + 0.20).toFixed(2)}</b></span>
              <span>GREEKS: DEV SAMPLE · ESTIMATED</span>
            </div>
          </div>

          
          {/* Card C: Active Order Ticket Policy Synchronization */}
          <div className="v3-panel v3-order-ticket" style={{ margin: 0 }}>
            <div className="v3-panel-head">
              <span className="v3-panel-label">Live Order Ticket Envelope</span>
              <span className="v3-chip sample" style={{ fontSize: 9.5 }}>GOVERNED TICKET</span>
            </div>
            <div style={{ padding: "10px 12px", background: "var(--v3-surface-2)", borderRadius: 8, border: "1px solid var(--v3-line)", fontSize: 11.5 }}>
              <div style={{ fontWeight: 650, color: "var(--v3-ink)", marginBottom: 4 }}>
                Global Strike Policy: {policy.mode === "ATM" ? "ATM (0 strikes)" : `${policy.mode} (+${policy.distance} strike${policy.distance === 1 ? "" : "s"})`}
              </div>
              <div style={{ color: "var(--v3-ink-2)", fontSize: 11 }}>
                Order blotter resolves strikes dynamically per active Global Strike Policy.
              </div>
            </div>
          </div>

          {/* Card B: Open Position & Protective State (or Idle / Live Standby) */}
          <div className="v3-panel" style={{ margin: 0 }}>
            <div className="v3-panel-head">
              <span className="v3-panel-label">Open Position &amp; Protection</span>
              {stratMeta.position && (
                <span className="v3-profit-badge">POSITION ACTIVE</span>
              )}
            </div>

            {stratMeta.position ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {/* Active Position Info */}
                <div style={{ padding: "10px 12px", background: "var(--v3-surface-2)", borderRadius: 8, border: "1px solid var(--v3-line)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
                    <span style={{ fontWeight: 700, fontSize: 13, color: "var(--v3-ink)" }}>
                      {stratMeta.position.symbol}
                    </span>
                    <span style={{ font: "700 13px var(--v3-mono)", color: stratMeta.position.pnl >= 0 ? "var(--v3-profit-text)" : "var(--v3-loss-text)" }}>
                      {fmtSignedINR(stratMeta.position.pnl, 2)}
                    </span>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(90px, 1fr))", gap: 6, fontSize: 11 }}>
                    <div>Qty: <b className="v3-mono">{stratMeta.position.lots} Lots ({stratMeta.position.qty} Q)</b></div>
                    <div>Avg Entry: <b className="v3-mono">₹{stratMeta.position.avgEntry.toFixed(2)}</b></div>
                    <div>LTP: <b className="v3-mono">₹{stratMeta.position.currentLtp.toFixed(2)}</b></div>
                    <div>Position Return %: <b className="v3-mono" style={{ color: stratMeta.position.pnl >= 0 ? "var(--v3-profit-text)" : "var(--v3-loss-text)" }}>{fmtSignedPct(stratMeta.position.pnlPct)}</b></div>
                  </div>
                </div>

                {/* Protective State Box */}
                <div>
                  <div style={{ fontSize: 10, color: "var(--v3-ink-dim)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 4 }}>
                    Strategy Protective Envelope
                  </div>
                  <div className="v3-protective-state-card">
                    <div>
                      <div className="v3-dim" style={{ fontSize: 10 }}>Stop Loss</div>
                      <div className="v3-mono v3-loss-text" style={{ fontWeight: 700, fontSize: 12 }}>
                        {stratMeta.position.stopLoss != null ? `₹${Number(stratMeta.position.stopLoss).toFixed(2)}` : "UNAVAILABLE"}
                      </div>
                    </div>
                    <div>
                      <div className="v3-dim" style={{ fontSize: 10 }}>Target</div>
                      <div className="v3-mono v3-profit-text" style={{ fontWeight: 700, fontSize: 12 }}>
                        {stratMeta.position.target != null ? `₹${Number(stratMeta.position.target).toFixed(2)}` : "UNAVAILABLE"}
                      </div>
                    </div>
                    <div>
                      <div className="v3-dim" style={{ fontSize: 10 }}>Trailing SL</div>
                      <div className="v3-mono" style={{ fontWeight: 600, fontSize: 11 }}>
                        Armed
                      </div>
                    </div>
                    <div>
                      <div className="v3-dim" style={{ fontSize: 10 }}>Status</div>
                      <div className="v3-mono v3-profit-text" style={{ fontWeight: 600, fontSize: 11 }}>
                        Protected
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ) : stratMeta.isBlocked ? (
              <div style={{ padding: "14px 12px", background: "var(--v3-surface-2)", borderRadius: 8, textAlign: "center", color: "var(--v3-loss-text)", fontSize: 12 }}>
                <b>No Position Allowed</b>: Pre-trade risk envelope blocked new orders.
              </div>
            ) : (
              <div style={{ padding: "14px 12px", background: "var(--v3-surface-2)", borderRadius: 8, textAlign: "center", color: "var(--v3-ink-3)", fontSize: 12 }}>
                <b>No Active Open Position</b>: Algorithm is monitoring market ticks.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── 6. Execution Events & Audit Timeline ── */}
      <Panel label="Strategy Execution Audit Ledger" meta={`${stratMeta.events.length} real-time pipeline events`} className="v3-sp12">
        <div className="v3-table-wrap">
          <table className="v3-table">
            <thead>
              <tr>
                <th style={{ width: 120 }}>Time (IST)</th>
                <th style={{ width: 100 }}>Type</th>
                <th>Event Title</th>
                <th>Audit &amp; Governance Details</th>
                <th style={{ width: 100, textAlign: "right" }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {stratMeta.events.map((evt) => (
                <tr key={evt.id}>
                  <td className="v3-mono v3-dim">{evt.time}</td>
                  <td>
                    <span className={`v3-tag ${evt.tone === "neg" ? "neg" : evt.tone === "ok" ? "ok" : ""}`}>
                      {evt.type}
                    </span>
                  </td>
                  <td style={{ fontWeight: 600, color: evt.tone === "neg" ? "var(--v3-loss-text)" : "var(--v3-ink)" }}>
                    {evt.title}
                  </td>
                  <td style={{ color: "var(--v3-ink-2)", fontSize: 12 }}>
                    {evt.detail}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <span className="v3-mono" style={{ fontSize: 11, color: evt.tone === "neg" ? "var(--v3-loss-text)" : "var(--v3-profit-text)" }}>
                      {evt.tone === "neg" ? "BLOCKED" : "VERIFIED"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
};

// Export TradingScreen as an alias for seamless backward compatibility
export const StrategyExecutionScreen: React.FC<StrategyExecutionScreenProps> = props => props.previewMode ? <StrategyExecutionPreviewScreen {...props} /> : <LiveReadinessRuntime />;
export const TradingScreen = StrategyExecutionScreen;

/* ════════════════════════════════════════════════════════════
   3. BACKTESTING LAB WORKSPACE (RESEARCH & EVIDENCE)
   ============================================================ */
export { BacktestingScreen, type BacktestingScreenProps } from "./BacktestingScreen";


/* ════════════════════════════════════════════════════════════
   4. PAPER TRADING WORKSPACE (USER-DEFINED CAPITAL ENVELOPE)
   ============================================================ */
export interface PaperTradingScreenProps {
  initialStrategy?: StrategyRow | null;
  policy?: GlobalStrikePolicy;
  onChangePolicy?: (next: GlobalStrikePolicy) => void;
  previewMode?: boolean;
}

export interface PaperSessionRecord {
  id: string;
  startDate: string;
  initialCapital: number;
  finalEquity: number;
  totalPnl: number;
  returnPct: number;
  tradesCount: number;
  strategyName: string;
  strategyVersion: string;
  policySnapshot: string;
  status: "ARCHIVED" | "COMPLETED";
}

export interface PaperSimulationEvent {
  id: string;
  time: string;
  title: string;
  detail: string;
  source: string;
  status: "PASS" | "BLOCKED" | "INFO";
  badge?: string;
}

const INITIAL_PAPER_HISTORY: PaperSessionRecord[] = [];

const INITIAL_PAPER_EVENTS: PaperSimulationEvent[] = [];

function mapAuthoritativePosition(raw: any): PaperPosition {
  const avgPrice = Number(raw.avg_price ?? raw.avgPrice ?? 0);
  const ltp = Number(raw.ltp ?? avgPrice);
  const qty = Number(raw.qty ?? 0);
  const entryCost = Number(raw.entry_cost ?? (avgPrice * qty));
  const currentValue = Number(raw.current_value ?? (ltp * qty));
  const unPnl = Number(raw.unrealized_pnl ?? (currentValue - entryCost));
  const retPct = Number(raw.return_pct ?? (entryCost > 0 ? (unPnl / entryCost) * 100 : 0));
  const symbol = String(raw.symbol ?? "NIFTY");
  const resolvedContract = String(raw.resolved_contract ?? raw.resolvedContract ?? symbol);
  const pType = String(raw.position_type ?? raw.type ?? (resolvedContract.endsWith("PE") ? "PE" : "CE"));
  const stopLoss = raw.stop_loss != null
    ? Number(raw.stop_loss)
    : (raw.stopLoss != null ? Number(raw.stopLoss) : null);
  const target = raw.target != null
    ? Number(raw.target)
    : (raw.target_price != null ? Number(raw.target_price) : null);
  const trailStop = raw.trail_stop != null
    ? Number(raw.trail_stop)
    : (raw.trailStop != null ? Number(raw.trailStop) : null);

  return {
    id: String(raw.position_id ?? raw.id ?? `pos-${Math.random().toString(36).slice(2, 7)}`),
    symbol,
    type: pType,
    qty,
    avgPrice,
    ltp,
    resolvedContract,
    strategySource: String(raw.strategy_source ?? raw.strategySource ?? "Paper Engine (SX-STRAT-001)"),
    entrySpot: Number(raw.entry_spot ?? raw.entrySpot ?? 0),
    entryAtm: Number(raw.entry_atm ?? raw.entryAtm ?? 0),
    strikeInterval: Number(raw.strike_interval ?? raw.strikeInterval ?? (symbol.includes("BANKNIFTY") ? 100 : 50)),
    policyMode: String(raw.policy_mode ?? raw.policyMode ?? "OTM"),
    policyDistance: Number(raw.policy_distance ?? raw.policyDistance ?? 1),
    stopLoss,
    target,
    trailStop,
    entryReason: String(raw.entry_reason ?? raw.entryReason ?? "Authoritative Paper Execution Fill (SimulatedPaperBroker)"),
    pnl: unPnl,
    isProfit: unPnl >= 0,
    contract: resolvedContract,
    underlying: symbol,
    avgEntry: avgPrice,
    currentValue,
    unrealizedPnl: unPnl,
    returnPct: retPct,
    entryTime: String(raw.opened_at_utc ?? raw.entryTime ?? new Date().toLocaleTimeString("en-IN") + " IST"),
    strategy: String(raw.strategy_source ?? raw.strategy ?? "Authoritative Paper"),
  };
}

function mapAuthoritativeEvent(raw: any): PaperSimulationEvent {
  return {
    id: String(raw.event_id ?? raw.id ?? `evt-${Math.random().toString(36).slice(2, 7)}`),
    time: String(raw.event_time ?? raw.time ?? new Date().toLocaleTimeString("en-IN") + " IST"),
    title: String(raw.title ?? "Paper Event"),
    detail: String(raw.detail ?? ""),
    source: String(raw.source ?? "Paper Fill Engine"),
    status: (raw.status === "BLOCKED" || raw.status === "PASS" || raw.status === "INFO") ? raw.status : "INFO",
    badge: raw.badge ? String(raw.badge) : undefined,
  };
}

function mapAuthoritativeSessionRecord(raw: any): PaperSessionRecord {
  const initCap = Number(raw.initial_capital ?? raw.initialCapital ?? 50000);
  const totalPnl = Number(raw.total_pnl ?? raw.realized_pnl ?? raw.totalPnl ?? 0);
  const finalEquity = Number(raw.current_capital ?? raw.finalEquity ?? (initCap + totalPnl));
  const retPct = Number(raw.return_pct ?? (initCap > 0 ? (totalPnl / initCap) * 100 : 0));
  const rawDate = raw.created_at_utc || raw.startDate;
  let formattedDate = "TODAY";
  if (rawDate) {
    try {
      formattedDate = new Date(rawDate).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }).toUpperCase();
    } catch {
      formattedDate = String(rawDate);
    }
  }

  return {
    id: String(raw.session_id ?? raw.id),
    startDate: formattedDate,
    initialCapital: initCap,
    finalEquity,
    totalPnl,
    returnPct: Number(retPct.toFixed(2)),
    tradesCount: Number(raw.trades_count ?? raw.tradesCount ?? 0),
    strategyName: String(raw.strategy_name ?? raw.strategyName ?? "NIFTY Momentum"),
    strategyVersion: String(raw.strategy_version ?? raw.strategyVersion ?? "v2.3"),
    policySnapshot: String(raw.policy_snapshot ?? raw.policySnapshot ?? "OTM (1 strike)"),
    status: raw.status === "COMPLETED" ? "COMPLETED" : "ARCHIVED",
  };
}

export const PaperTradingScreen: React.FC<PaperTradingScreenProps> = ({
  initialStrategy,
  policy = DEFAULT_GLOBAL_STRIKE_POLICY,
  onChangePolicy,
  previewMode = false,
}) => {
  // ── 1. SESSION STATE (ONE SOURCE OF TRUTH) ──
  const [sessionId, setSessionId] = useState("");
  const [initialCapital, setInitialCapital] = useState(0);
  const [realizedPnl, setRealizedPnl] = useState(0);
  const [dayStartEquity, setDayStartEquity] = useState(0);
  const [sessionStartTime, setSessionStartTime] = useState("—");
  
  // Snapshotted policy frozen at session start (Requirement 5 & 10)
  const [sessionPolicySnapshot, setSessionPolicySnapshot] = useState("—");
  const [sessionTargetStrategy, setSessionTargetStrategy] = useState(
    initialStrategy ? { name: initialStrategy.name, version: initialStrategy.version } : { name: "No strategy assigned", version: "—" }
  );

  // Positions array (Requirement 1 & 2)
  const [positions, setPositions] = useState<PaperPosition[]>([]);
  const [sessionsHistory, setSessionsHistory] = useState<PaperSessionRecord[]>([]);
  const [eventsList, setEventsList] = useState<PaperSimulationEvent[]>([]);

  // Inspection Drawer for Position Entry Resolution Evidence (Requirement 6 & 11)
  const [selectedEntryPosition, setSelectedEntryPosition] = useState<PaperPosition | null>(null);

  // Modals & User-defined capital inputs
  const [newSessionModalOpen, setNewSessionModalOpen] = useState(false);
  const [resetModalOpen, setResetModalOpen] = useState(false);
  const [inputCapitalStr, setInputCapitalStr] = useState("0");
  const [inputMode, setInputMode] = useState<"HISTORICAL_REPLAY" | "LIVE_MARKET">("HISTORICAL_REPLAY");
  const [toastMsg, setToastMsg] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 3500);
  };

  // ── 1b. AUTHORITATIVE BACKEND WIRING (BI-2 Slice 5 Step 2) ──
  // In authenticated runtime the Paper Desk is fed exclusively by the
  // authoritative PaperService (SimulatedPaperBroker · zero real-broker routing).
  // In DEV PREVIEW / SAMPLE, or when the backend is offline, the screen stays a
  // non-authoritative preview and can NEVER mutate authoritative state.
  const [authoritativeSession, setAuthoritativeSession] = useState<AuthoritativePaperSession | null>(null);
  const [authoritativeStatus, setAuthoritativeStatus] = useState<string | null>(null);

  // P1-A (R-03 self-service): resolve the paper strategy from the
  // backend-registered strategy registry when no navigation-provided
  // initialStrategy exists. Never fall back to a hardcoded seed id.
  const [registryStrategyId, setRegistryStrategyId] = useState<string | null>(null);
  useEffect(() => {
    if (previewMode || !isBackendEnabled() || initialStrategy) return;
    void queryUserStrategyRegistry().then((res) => {
      if (res.source === "BACKEND" && res.data && res.data.length > 0) {
        // Default to the first usable strategy: never auto-target an
        // archived or Owner-suspended strategy for new sessions.
        const first = res.data.find((e) => !e.archived && (e.admin_status || "ACTIVE") === "ACTIVE")
          || res.data.find((e) => !e.archived) || res.data[0];
        setRegistryStrategyId(first.strategy_id);
      } else {
        setRegistryStrategyId(null);
      }
    });
  }, [previewMode, initialStrategy]);

  useEffect(() => {
    if (previewMode || !isBackendEnabled()) return;
    void queryPaperSessions(10).then((res) => {
      if (!res.data || res.data.length === 0) {
        setAuthoritativeSession(null);
        setAuthoritativeStatus(null);
        setSessionId("");
        setInitialCapital(0);
        setRealizedPnl(0);
        setDayStartEquity(0);
        setSessionsHistory([]);
        setPositions([]);
        setEventsList([]);
        return;
      }
      const latest = res.data[0];
      setAuthoritativeSession(latest);
      setAuthoritativeStatus(latest.status);
      setSessionId(latest.session_id);
      setInitialCapital(Number(latest.initial_capital));
      setRealizedPnl(Number(latest.realized_pnl || 0));
      setDayStartEquity(Number(latest.initial_capital));
      if (latest.policy_snapshot) setSessionPolicySnapshot(latest.policy_snapshot);
      if (latest.strategy_name) {
        setSessionTargetStrategy({
          name: latest.strategy_name,
          version: latest.strategy_version || "v1.0",
        });
      }
      if (res.data.length === 1 && Number(latest.trades_count) === 0) {
        setRealizedPnl(0);
      }
      setSessionsHistory(res.data.map(mapAuthoritativeSessionRecord));
      void queryPaperPositions(latest.session_id).then((pres) => {
        if (pres.data && pres.data.length > 0) setPositions(pres.data.map(mapAuthoritativePosition));
      });
      void queryPaperEvents(latest.session_id, 8).then((eres) => {
        if (eres.data && eres.data.length > 0) setEventsList(eres.data.map(mapAuthoritativeEvent));
      });
    }).catch(() => { /* authoritative runtime unavailable -> remain SAMPLE */ });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewMode]);

  const isAuthoritativeRuntime = (): boolean => !previewMode && isBackendEnabled();

  // ── 2. EXACT ONE-SOURCE-OF-TRUTH ACCOUNTING CALCULATIONS (Section 1 & 2) ──
  const computedPositions = useMemo(() => {
    return positions.map((p) => {
      const entryCost = p.avgPrice * p.qty;
      const currentValue = p.ltp * p.qty;
      const unPnl = (p.ltp - p.avgPrice) * p.qty;
      const retPct = p.avgPrice > 0 ? ((p.ltp - p.avgPrice) / p.avgPrice) * 100 : 0;
      return {
        ...p,
        entryCost,
        currentValue,
        computedUnrealizedPnl: unPnl,
        computedReturnPct: retPct,
      };
    });
  }, [positions]);

  // Session aggregations (All dynamically derived):
  const capitalCommitted = useMemo(() => {
    return computedPositions.reduce((acc, p) => acc + p.entryCost, 0);
  }, [computedPositions]);

  const openPositionMarketValue = useMemo(() => {
    return computedPositions.reduce((acc, p) => acc + p.currentValue, 0);
  }, [computedPositions]);

  const unrealizedPnlTotal = useMemo(() => {
    return computedPositions.reduce((acc, p) => acc + p.computedUnrealizedPnl, 0);
  }, [computedPositions]);

  const availableCash = useMemo(() => {
    return initialCapital + realizedPnl - capitalCommitted;
  }, [initialCapital, realizedPnl, capitalCommitted]);

  const currentEquity = useMemo(() => {
    return availableCash + openPositionMarketValue;
  }, [availableCash, openPositionMarketValue]);

  const totalPnl = useMemo(() => {
    return realizedPnl + unrealizedPnlTotal;
  }, [realizedPnl, unrealizedPnlTotal]);

  const sessionReturnPct = useMemo(() => {
    return initialCapital > 0 ? (totalPnl / initialCapital) * 100 : 0;
  }, [totalPnl, initialCapital]);

  // Day P&L Formula (Section 4): Day P&L = Current Equity - Day Start Equity
  const dayPnl = useMemo(() => {
    return currentEquity - dayStartEquity;
  }, [currentEquity, dayStartEquity]);

  // ── 3. SESSION LIFECYCLE HANDLERS (Section 9 & 10) ──
  const handleLaunchNewSession = () => {
    const num = Math.max(1000, parseInt(inputCapitalStr.replace(/[^0-9]/g, ""), 10) || 50000);

    // Freeze policy snapshot for the new session from current policy
    const newPolicySnap = policy.mode === "ATM" ? "ATM · 0 STRIKES" : `${policy.mode} · ${policy.distance} STRIKE${policy.distance === 1 ? "" : "S"}`;

    // ── AUTHORITATIVE PATH: create via PaperService (fail-closed, no fabrication) ──
    if (isAuthoritativeRuntime()) {
      const resolvedStrategyId = initialStrategy
        ? String(initialStrategy.id)
        : registryStrategyId;
      if (!resolvedStrategyId) {
        showToast("No registered strategy available for paper trading. Register a strategy first.");
        return;
      }
      const payload: PaperSessionCreateRequest = {
        strategy_id: resolvedStrategyId,
        instrument: "NIFTY",
        timeframe: "1m",
        initial_capital: num,
        policy: { mode: policy.mode, distance: policy.distance },
        data_source_mode: inputMode,
      };
      void createPaperSession(payload).then((res) => {
        setNewSessionModalOpen(false);
        if (res.ok && res.data) {
          setAuthoritativeSession(res.data);
          setAuthoritativeStatus(res.data.status);
          setSessionId(res.data.session_id);
          setInitialCapital(Number(res.data.initial_capital));
          setRealizedPnl(Number(res.data.realized_pnl || 0));
          setDayStartEquity(Number(res.data.initial_capital));
          setSessionPolicySnapshot(res.data.policy_snapshot || newPolicySnap);
          if (res.data.strategy_name) {
            setSessionTargetStrategy({
              name: res.data.strategy_name,
              version: res.data.strategy_version || "v1.0",
            });
          }
          setPositions([]);
          setEventsList([]);
          void queryPaperSessions(10).then((sres) => {
            if (sres.data && sres.data.length > 0) {
              setSessionsHistory(sres.data.map(mapAuthoritativeSessionRecord));
            }
          });
          const modeStr = res.data.data_source_mode === "LIVE_MARKET" ? "Live Market (SimulatedPaperBroker)" : "Historical Replay";
          showToast(`Authoritative paper session ${res.data.session_id} created (${res.data.status}) [${modeStr}]. Start execution to begin simulation.`);
        } else {
          showToast(`Paper session creation blocked by authority (no state mutated): ${res.error}`);
        }
      });
      return;
    }

    // Archive current active session into historical ledger
    const archived: PaperSessionRecord = {
      id: sessionId,
      startDate: "31 AUG 2026",
      initialCapital,
      finalEquity: Math.round(currentEquity),
      totalPnl: Math.round(totalPnl),
      returnPct: Number(sessionReturnPct.toFixed(2)),
      tradesCount: computedPositions.length,
      strategyName: sessionTargetStrategy.name,
      strategyVersion: sessionTargetStrategy.version,
      policySnapshot: sessionPolicySnapshot,
      status: "ARCHIVED",
    };
    setSessionsHistory((prev) => [archived, ...prev]);

    // Setup new session ID & starting state
    const nextSessionNum = String(sessionsHistory.length + 4).padStart(3, "0");
    const nextId = `PAPER-SES-${nextSessionNum}`;
    setSessionId(nextId);
    setInitialCapital(num);
    setRealizedPnl(0);
    setDayStartEquity(num);
    setSessionStartTime(new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) + " IST");
    setSessionPolicySnapshot(newPolicySnap);
    if (initialStrategy) {
      setSessionTargetStrategy({ name: initialStrategy.name, version: initialStrategy.version });
    }

    setNewSessionModalOpen(false);
    showToast(`New Paper Session ${nextId} initialized with ₹${num.toLocaleString("en-IN")} starting capital (Snapshotted Policy: ${newPolicySnap}).`);
  };

  const handleStartSession = () => {
    if (isAuthoritativeRuntime() && sessionId) {
      void startPaperSession(sessionId).then((res) => {
        if (res.ok && res.data) {
          setAuthoritativeSession(res.data);
          setAuthoritativeStatus(res.data.status);
          setInitialCapital(Number(res.data.initial_capital));
          setRealizedPnl(Number(res.data.realized_pnl || 0));
          setDayStartEquity(Number(res.data.initial_capital));
          void queryPaperPositions(sessionId).then((pres) => {
            if (pres.data && pres.data.length > 0) {
              setPositions(pres.data.map(mapAuthoritativePosition));
            }
          });
          void queryPaperEvents(sessionId, 8).then((eres) => {
            if (eres.data && eres.data.length > 0) {
              setEventsList(eres.data.map(mapAuthoritativeEvent));
            }
          });
          void queryPaperSessions(10).then((sres) => {
            if (sres.data && sres.data.length > 0) {
              setSessionsHistory(sres.data.map(mapAuthoritativeSessionRecord));
            }
          });
          showToast(`Authoritative paper session ${sessionId} is ${res.data.status}. Ready for execution.`);
        } else {
          if (res.status === 424 || (res.error && res.error.includes("EXTERNAL LIVE DATA SOURCE REQUIRED"))) {
            showToast("LIVE DATA SOURCE REQUIRED: add your own broker connection with a credential reference before starting a live-market paper session.");
          } else {
            showToast(`Paper session start blocked by authority: ${res.error}`);
          }
        }
      });
      return;
    }
    showToast("DEV PREVIEW: forward execution is simulated locally and cannot mutate authoritative state.");
  };

  const handleStopSession = () => {
    if (isAuthoritativeRuntime() && sessionId) {
      void stopPaperSession(sessionId).then((res) => {
        if (res.ok && res.data) {
          setAuthoritativeSession(res.data);
          setAuthoritativeStatus(res.data.status);
          void queryPaperPositions(sessionId).then((pres) => {
            if (pres.data && pres.data.length > 0) {
              setPositions(pres.data.map(mapAuthoritativePosition));
            }
          });
          void queryPaperEvents(sessionId, 8).then((eres) => {
            if (eres.data && eres.data.length > 0) {
              setEventsList(eres.data.map(mapAuthoritativeEvent));
            }
          });
          void queryPaperSessions(10).then((sres) => {
            if (sres.data && sres.data.length > 0) {
              setSessionsHistory(sres.data.map(mapAuthoritativeSessionRecord));
            }
          });
          showToast(`Authoritative paper session ${sessionId} stopped. Forward execution halted.`);
        } else {
          showToast(`Paper session stop blocked by authority: ${res.error}`);
        }
      });
      return;
    }
    showToast("DEV PREVIEW: stop is simulated locally and cannot mutate authoritative state.");
  };

  const handleConfirmReset = () => {
    if (isAuthoritativeRuntime()) {
      // Authoritative sessions cannot be silently reset; the honest operation is
      // to stop forward execution (no fabricated zeroing of persisted P&L).
      setResetModalOpen(false);
      handleStopSession();
      return;
    }
    setRealizedPnl(0);
    setPositions([]);
    setDayStartEquity(initialCapital);
    setResetModalOpen(false);
    showToast(`Paper Account ${sessionId} reset. P&L zeroed to starting capital ₹${initialCapital.toLocaleString("en-IN")}.`);
  };

  return (
    <>
      {/* ── Screen Header ── */}
      <div className="v3-screen-head">
        <div>
          <h2 className="v3-screen-title">Paper Trading Desk</h2>
          <p className="v3-screen-sub">
            Simulated forward trading desk · user-defined capital envelope ({sessionId})
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <TruthChip kind="REAL" title="REAL + WORKING — Authoritative Paper Trading Runtime (SimulatedPaperBroker · zero real-broker routing)" />
          <span
            className="v3-chip online"
            style={{ fontWeight: 700, letterSpacing: "0.06em", color: "var(--v3-profit-text)" }}
            id="paper-authoritative-badge"
          >
            AUTHORITATIVE RUNTIME · {authoritativeStatus || (authoritativeSession ? authoritativeSession.status : "IDLE")}
          </span>
          {authoritativeSession && (
            <span
              className={`v3-chip ${authoritativeSession.data_source_mode === "LIVE_MARKET" ? "online" : "sample"}`}
              style={{ fontWeight: 700, letterSpacing: "0.06em" }}
              id="paper-mode-badge"
            >
              MODE: {authoritativeSession.data_source_mode === "LIVE_MARKET" ? "LIVE MARKET" : "HISTORICAL REPLAY"}
            </span>
          )}
          {authoritativeSession && authoritativeSession.data_source_mode === "LIVE_MARKET" && (
            <span
              className={`v3-chip ${authoritativeSession.feed_status === "CONNECTED" ? "online" : authoritativeSession.feed_status === "RECONNECTING" ? "warn" : "sample"}`}
              style={{ fontWeight: 700, letterSpacing: "0.06em" }}
              id="paper-feed-status-badge"
            >
              FEED: {authoritativeSession.feed_status || "DISCONNECTED"}
            </span>
          )}
          <button
            className="v3-btn ghost mini"
            onClick={() => {
              setInputCapitalStr(initialCapital.toString());
              setNewSessionModalOpen(true);
            }}
            id="v3-new-paper-session-btn"
          >
            <Icon name="plus" size={13} /> New Paper Session
          </button>
          <button
            className="v3-btn ghost mini"
            onClick={() => setResetModalOpen(true)}
            id="v3-reset-paper-account-btn"
          >
            <Icon name="refresh" size={13} /> Reset Paper Account
          </button>
          {authoritativeSession && (
            <button
              className="v3-btn primary mini"
              onClick={handleStartSession}
              id="v3-start-paper-session-btn"
            >
              <Icon name="play" size={13} /> {authoritativeStatus === "ACTIVE" ? "Re-run" : "Start Execution"}
            </button>
          )}
          {authoritativeSession && (
            <button
              className="v3-btn ghost mini"
              onClick={handleStopSession}
              id="v3-stop-paper-session-btn"
            >
              <Icon name="pause" size={13} /> Stop
            </button>
          )}
        </div>
      </div>

      {toastMsg && (
        <div className="v3-toast" role="status">
          <Icon name="check" size={15} /> {toastMsg}
        </div>
      )}

      {/* ── SESSION STRIKE POLICY SNAPSHOT Context Banner (Requirement 5) ── */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          padding: "10px 16px",
          border: "1px solid var(--v3-line-strong)",
          borderRadius: 10,
          background: "var(--v3-surface-2)",
          marginBottom: 14,
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <Icon name="layers" size={15} style={{ color: "var(--v3-profit)" }} />
          <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: "0.04em", color: "var(--v3-ink)" }}>
            SESSION STRIKE POLICY SNAPSHOT:
          </span>
          <span
            className="v3-chip"
            style={{
              background: "rgba(16, 185, 129, 0.12)",
              color: "var(--v3-profit-text)",
              borderColor: "rgba(16, 185, 129, 0.35)",
              fontSize: 10.5,
              fontWeight: 700,
            }}
          >
            {sessionPolicySnapshot} · SNAPSHOT AT SESSION START
          </span>
          <span className="v3-chip sample" style={{ fontSize: 9.5 }}>
            GLOBAL · NO STRATEGY OVERRIDE
          </span>
        </div>
        <div style={{ fontSize: 11, color: "var(--v3-ink-3)" }}>
          <span className="v3-mono">The Paper Session preserves this snapshot until it ends.</span>
        </div>
      </div>

      {/* Preselected Strategy Context Banner */}
      {initialStrategy && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 10,
            padding: "8px 14px",
            border: "1px solid var(--v3-line-strong)",
            borderRadius: 10,
            background: "var(--v3-surface-2)",
            marginBottom: 14,
            flexWrap: "wrap",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Icon name="layers" size={14} />
            <span style={{ fontSize: 12, color: "var(--v3-ink)" }}>
              Active Forward Paper Target: <b>{initialStrategy.name}</b> <span className="v3-mono v3-dim">({initialStrategy.version})</span>
            </span>
            <span className="v3-itm-badge">Paper Cycle Active</span>
          </div>
          <span className="v3-mono v3-dim" style={{ fontSize: 11 }}>Forward Evidence Attaching</span>
        </div>
      )}

      {/* ── 9 EXACT USER-DEFINED PAPER CAPITAL KPI CARDS (Requirements 1, 2, 3, 4, 15) ── */}
      <div className="v3-kpi-grid nine-col" id="v3-paper-kpi-grid">
        {/* 1. Initial Capital */}
        <div className="v3-kpi-card">
          <div className="v3-kpi-title">Initial Capital</div>
          <div className="v3-kpi-val">₹{initialCapital.toLocaleString("en-IN")}</div>
          <div className="v3-kpi-sub">User-configured starting base</div>
        </div>

        {/* 2. Current Equity */}
        <div className="v3-kpi-card">
          <div className="v3-kpi-title">Current Equity</div>
          <div className="v3-kpi-val v3-profit-text">₹{Math.round(currentEquity).toLocaleString("en-IN")}</div>
          <div className="v3-kpi-sub">Available Cash + Market Value</div>
        </div>

        {/* 3. Available Cash */}
        <div className="v3-kpi-card">
          <div className="v3-kpi-title">Available Cash</div>
          <div className="v3-kpi-val">₹{Math.round(availableCash).toLocaleString("en-IN")}</div>
          <div className="v3-kpi-sub">Uncommitted virtual cash</div>
        </div>

        {/* 4. Used Capital */}
        <div className="v3-kpi-card">
          <div className="v3-kpi-title">Used Capital</div>
          <div className="v3-kpi-val">₹{Math.round(capitalCommitted).toLocaleString("en-IN")}</div>
          <div className="v3-kpi-sub">Premium committed to open option positions</div>
        </div>

        {/* 5. Realized P&L */}
        <div className="v3-kpi-card">
          <div className="v3-kpi-title">Realized P&amp;L</div>
          <div className={`v3-kpi-val ${realizedPnl >= 0 ? "v3-profit-text" : "v3-loss-text"}`}>
            {fmtSignedINR(realizedPnl, 0)}
          </div>
          <div className="v3-kpi-sub">Closed trade profits</div>
        </div>

        {/* 6. Unrealized P&L */}
        <div className="v3-kpi-card">
          <div className="v3-kpi-title">Unrealized P&amp;L</div>
          <div className={`v3-kpi-val ${unrealizedPnlTotal >= 0 ? "v3-profit-text" : "v3-loss-text"}`}>
            {fmtSignedINR(unrealizedPnlTotal, 0)}
          </div>
          <div className="v3-kpi-sub">Floating open positions</div>
        </div>

        {/* 7. Day P&L (Requirement 4) */}
        <div className="v3-kpi-card">
          <div className="v3-kpi-title">Day P&amp;L</div>
          <div className={`v3-kpi-val ${dayPnl >= 0 ? "v3-profit-text" : "v3-loss-text"}`}>
            {fmtSignedINR(dayPnl, 0)}
          </div>
          <div className="v3-kpi-sub">Change since paper-session day start</div>
        </div>

        {/* 8. Total P&L */}
        <div className="v3-kpi-card">
          <div className="v3-kpi-title">Total P&amp;L</div>
          <div className={`v3-kpi-val ${totalPnl >= 0 ? "v3-profit-text" : "v3-loss-text"}`}>
            {fmtSignedINR(totalPnl, 0)}
          </div>
          <div className="v3-kpi-sub">Realized + Unrealized</div>
        </div>

        {/* 9. Return % */}
        <div className="v3-kpi-card">
          <div className="v3-kpi-title">Return %</div>
          <div className={`v3-kpi-val ${sessionReturnPct >= 0 ? "v3-profit-text" : "v3-loss-text"}`}>
            {fmtSignedPct(sessionReturnPct)}
          </div>
          <div className="v3-kpi-sub">ROI on initial capital</div>
        </div>
      </div>

      {/* ── Active Positions Table (Requirements 2, 6, 8, 11) ── */}
      <div className="v3-table-wrap" style={{ marginBottom: 18 }}>
        <div
          style={{
            padding: "12px 16px",
            borderBottom: "1px solid var(--v3-line)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: 10,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontWeight: 700, fontSize: 13, color: "var(--v3-ink)" }}>
              Active Paper Positions ({computedPositions.length})
            </span>
            <span className="v3-chip online" style={{ fontSize: 9.5 }}>
              AUTHORITATIVE POSITIONS
            </span>
          </div>
          <span className="v3-mono v3-dim" style={{ fontSize: 11 }}>
            AUTHORITATIVE PAPER RUNTIME · SimulatedPaperBroker · Canonical Market Replay
          </span>
        </div>
        <table className="v3-table" id="v3-paper-positions-table">
          <thead>
            <tr>
              <th>Paper Position</th>
              <th>Type</th>
              <th>Qty</th>
              <th>Avg Buy</th>
              <th>LTP</th>
              <th>Entry Cost</th>
              <th>Current Value</th>
              <th>Unrealized P&amp;L</th>
              <th>Return %</th>
              <th>Strategy Driver</th>
              <th>Entry Evidence</th>
            </tr>
          </thead>
          <tbody>
            {computedPositions.length === 0 ? (
              <tr>
                <td colSpan={11} style={{ textAlign: "center", padding: "24px 12px", color: "var(--v3-ink-3)" }}>
                  No positions
                </td>
              </tr>
            ) : (
              computedPositions.map((pos) => (
                <tr key={pos.id} style={{ cursor: "pointer" }} onClick={() => setSelectedEntryPosition(pos)}>
                  <td style={{ fontWeight: 600 }}>
                    <div style={{ display: "flex", flexDirection: "column" }}>
                      <span>{pos.symbol}</span>
                      <span className="v3-mono v3-dim" style={{ fontSize: 10.5 }}>
                        Resolved: {pos.resolvedContract || pos.symbol}
                      </span>
                    </div>
                  </td>
                  <td>
                    <span className={pos.type === "CE" ? "v3-profit-badge" : "v3-loss-badge"}>{pos.type}</span>
                  </td>
                  <td className="v3-mono">{pos.qty / (pos.symbol.includes("BANKNIFTY") ? 15 : 50)} Lots ({pos.qty} Qty)</td>
                  <td className="v3-mono">₹{pos.avgPrice.toFixed(2)}</td>
                  <td className="v3-mono">₹{pos.ltp.toFixed(2)}</td>
                  <td className="v3-mono">₹{Math.round(pos.entryCost).toLocaleString("en-IN")}</td>
                  <td className="v3-mono">₹{Math.round(pos.currentValue).toLocaleString("en-IN")}</td>
                  <td className={`v3-mono ${pos.computedUnrealizedPnl >= 0 ? "v3-profit-text" : "v3-loss-text"}`} style={{ fontWeight: 700 }}>
                    {fmtSignedINR(pos.computedUnrealizedPnl, 2)}
                  </td>
                  <td className={`v3-mono ${pos.computedReturnPct >= 0 ? "v3-profit-text" : "v3-loss-text"}`} style={{ fontWeight: 700 }}>
                    {fmtSignedPct(pos.computedReturnPct)}
                  </td>
                  <td style={{ color: "var(--v3-ink-3)" }}>{pos.strategySource}</td>
                  <td>
                    <button
                      className="v3-btn ghost mini"
                      style={{ fontSize: 10, padding: "3px 8px" }}
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedEntryPosition(pos);
                      }}
                      title="Inspect Entry Policy Snapshot & Strike Resolution"
                    >
                      <Icon name="shield" size={11} /> Entry Snapshot
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* ── Recent Paper Simulation & Risk Events (Requirement 12) ── */}
      <Panel
        label="Recent Paper Simulation & Risk Events"
        meta="Execution audit & risk gate telemetry (8 events logged)"
        className="v3-sp12"
        id="v3-recent-paper-events-panel"
      >
        <div className="v3-rows">
          {eventsList.length === 0 ? (
            <div style={{ padding: "20px", textAlign: "center", color: "var(--v3-ink-3)" }}>
              No paper simulation events
            </div>
          ) : (
            eventsList.map((evt) => (
              <div key={evt.id} className="v3-row" style={{ padding: "8px 4px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 120 }}>
                  <Dot tone={evt.status === "BLOCKED" ? "neg" : evt.status === "PASS" ? "ok" : "dim"} />
                  <span className="v3-mono v3-dim" style={{ fontSize: 11 }}>{evt.time}</span>
                </div>
                <div className="v3-row-main">
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span
                      className="v3-row-title"
                      style={{
                        fontSize: 12.5,
                        fontWeight: 700,
                        color: evt.status === "BLOCKED" ? "var(--v3-loss-text)" : "var(--v3-ink)",
                      }}
                    >
                      {evt.title}
                    </span>
                    {evt.badge && (
                      <span
                        className={`v3-chip ${evt.status === "BLOCKED" ? "v3-loss-badge" : "sample"}`}
                        style={{ fontSize: 9.5, padding: "1px 6px" }}
                      >
                        {evt.badge}
                      </span>
                    )}
                  </div>
                  <div className="v3-row-sub" style={{ fontSize: 11.5 }}>
                    {evt.detail}
                  </div>
                </div>
                <div className="v3-row-side">
                  <span className="v3-mono v3-dim" style={{ fontSize: 11 }}>{evt.source}</span>
                </div>
              </div>
            ))
          )}
        </div>
      </Panel>

      <div style={{ height: 14 }} />

      {/* ── Historical Paper Sessions Ledger (Requirement 13) ── */}
      <Panel
        label="Historical Paper Sessions Ledger"
        meta={`${sessionsHistory.length} prior sessions preserved in immutable ledger`}
        className="v3-sp12"
        id="v3-historical-paper-ledger"
      >
        <div className="v3-table-wrap">
          <table className="v3-table">
            <thead>
              <tr>
                <th>Session ID</th>
                <th>Date</th>
                <th>Strategy / Version</th>
                <th>Initial Capital</th>
                <th>Final Equity</th>
                <th>Total P&amp;L</th>
                <th>Return %</th>
                <th>Trades</th>
                <th>Policy Snapshot</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {sessionsHistory.length === 0 ? (
                <tr>
                  <td colSpan={10} style={{ textAlign: "center", padding: "24px 12px", color: "var(--v3-ink-3)" }}>
                    No paper sessions
                  </td>
                </tr>
              ) : (
                sessionsHistory.map((h) => (
                  <tr key={h.id}>
                    <td className="v3-mono" style={{ fontWeight: 600 }}>{h.id}</td>
                    <td>{h.startDate}</td>
                    <td>
                      <span>{h.strategyName}</span> <span className="v3-mono v3-dim">({h.strategyVersion})</span>
                    </td>
                    <td className="v3-mono">₹{h.initialCapital.toLocaleString("en-IN")}</td>
                    <td className="v3-mono">₹{h.finalEquity.toLocaleString("en-IN")}</td>
                    <td className={`v3-mono ${h.totalPnl >= 0 ? "v3-profit-text" : "v3-loss-text"}`} style={{ fontWeight: 700 }}>
                      {fmtSignedINR(h.totalPnl, 0)}
                    </td>
                    <td className={`v3-mono ${h.returnPct >= 0 ? "v3-profit-text" : "v3-loss-text"}`} style={{ fontWeight: 700 }}>
                      {fmtSignedPct(h.returnPct)}
                    </td>
                    <td className="v3-mono">{h.tradesCount}</td>
                    <td>
                      <span className="v3-chip" style={{ fontSize: 9.5, padding: "1px 6px", background: "var(--v3-surface-2)" }}>
                        {h.policySnapshot || "OTM (1 strike)"}
                      </span>
                    </td>
                    <td>
                      <span className="v3-chip real" style={{ fontSize: 9.5 }}>{h.status}</span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      {/* ── DRAWER: POSITION ENTRY POLICY SNAPSHOT (Requirements 6 & 11) ── */}
      <Drawer
        open={selectedEntryPosition !== null}
        title={selectedEntryPosition ? `${selectedEntryPosition.symbol} · Entry Snapshot` : "Entry Policy Snapshot"}
        sub="Immutable contract resolution evidence captured at execution time"
        onClose={() => setSelectedEntryPosition(null)}
      >
        {selectedEntryPosition && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div className="v3-governed-note">
              <Dot tone="ok" />
              <span>
                <b>Entry Resolution Invariant:</b> Open position contracts are fixed at entry time and do <b>NOT</b> mutate when live market ATM drifts.
              </span>
            </div>

            <dl style={{ margin: 0 }}>
              <KV k="Position ID" v={selectedEntryPosition.id} />
              <KV k="Resolved Contract" v={<b>{selectedEntryPosition.resolvedContract || selectedEntryPosition.symbol}</b>} />
              <KV k="Option Type" v={<span className={selectedEntryPosition.type === "CE" ? "v3-profit-badge" : "v3-loss-badge"}>{selectedEntryPosition.type}</span>} />
              <KV k="Entry Timestamp" v={selectedEntryPosition.entryTime || "28 AUG 2026 09:34:12 IST"} />
              <KV k="Strategy Driver" v={selectedEntryPosition.strategySource} />
              <KV k="Entry Underlying Spot" v={selectedEntryPosition.entrySpot ? `₹${selectedEntryPosition.entrySpot.toFixed(2)}` : "UNAVAILABLE"} />
              <KV k="Entry ATM Strike" v={selectedEntryPosition.entryAtm ? `₹${selectedEntryPosition.entryAtm.toLocaleString("en-IN")}` : "UNAVAILABLE"} />
              <KV k="Strike Interval" v={`${selectedEntryPosition.strikeInterval ?? 50} pts`} />
              <KV k="Policy Snapshot Mode" v={<span className="v3-chip sample">{selectedEntryPosition.policyMode ?? "OTM"} (+{selectedEntryPosition.policyDistance ?? 1} strike)</span>} />
              <KV k="Average Entry Price" v={`₹${selectedEntryPosition.avgPrice.toFixed(2)}`} />
              <KV k="Current LTP" v={`₹${selectedEntryPosition.ltp.toFixed(2)}`} />
              <KV k="Quantity" v={`${selectedEntryPosition.qty} Units`} />
              <KV k="Stop Loss Target" v={selectedEntryPosition.stopLoss != null ? `₹${selectedEntryPosition.stopLoss.toFixed(2)}` : "UNAVAILABLE"} />
              <KV k="Take Profit Target" v={selectedEntryPosition.target != null ? `₹${selectedEntryPosition.target.toFixed(2)}` : "UNAVAILABLE"} />
              <KV k="Trailing Stop Level" v={selectedEntryPosition.trailStop != null ? `₹${selectedEntryPosition.trailStop.toFixed(2)}` : "UNAVAILABLE"} />
            </dl>

            <div style={{ padding: "12px 14px", borderRadius: 10, background: "var(--v3-surface-2)", border: "1px solid var(--v3-line)" }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: "var(--v3-ink-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>
                Resolution Audit Trail
              </div>
              <p style={{ margin: 0, fontSize: 12, lineHeight: 1.5, color: "var(--v3-ink-2)" }}>
                {selectedEntryPosition.entryReason || "Contract resolved at order execution time. Open contracts preserve exact entry strikes throughout the lifecycle."}
              </p>
            </div>
          </div>
        )}
      </Drawer>

      {/* ── MODAL 1: NEW PAPER SESSION (USER-DEFINED CAPITAL & SNAPSHOT) (Requirements 9 & 10) ── */}
      {newSessionModalOpen && (
        <div className="v3-modal-overlay" onClick={() => setNewSessionModalOpen(false)} role="dialog" aria-modal="true" aria-label="Start New Paper Session">
          <div className="v3-modal" onClick={(e) => e.stopPropagation()}>
            <div className="v3-modal-head">
              <div>
                <div className="v3-modal-title">Launch New Paper Session</div>
                <div className="v3-modal-sub">Set starting capital &amp; freeze simulation parameters for new session</div>
              </div>
              <button className="v3-btn ghost mini" onClick={() => setNewSessionModalOpen(false)}>
                <Icon name="close" size={14} />
              </button>
            </div>

            <div className="v3-modal-body" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div className="v3-governed-note">
                <Dot tone="ok" />
                <span>
                  <b>Session Ledger Invariant:</b> Active session <b>{sessionId}</b> will be archived with full trade history preserved in the historical ledger.
                </span>
              </div>

              <div>
                <label className="v3-field-label">Market Data Mode</label>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                  <button
                    type="button"
                    className={`v3-preset-btn ${inputMode === "HISTORICAL_REPLAY" ? "active" : ""}`}
                    onClick={() => setInputMode("HISTORICAL_REPLAY")}
                    id="v3-paper-mode-replay-btn"
                    style={{
                      padding: "10px 12px",
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "flex-start",
                      gap: 4,
                      textAlign: "left",
                      height: "auto",
                      borderRadius: 8,
                      border: inputMode === "HISTORICAL_REPLAY" ? "1px solid var(--v3-brand)" : "1px solid var(--v3-line)"
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 700, fontSize: 13 }}>
                      <Icon name="clock" size={14} /> Historical Replay
                    </div>
                    <div style={{ fontSize: 11, color: "var(--v3-ink-3)", lineHeight: 1.3 }}>
                      Canonical parquet 1m bars with deterministic simulated replay
                    </div>
                  </button>

                  <button
                    type="button"
                    className={`v3-preset-btn ${inputMode === "LIVE_MARKET" ? "active" : ""}`}
                    onClick={() => setInputMode("LIVE_MARKET")}
                    id="v3-paper-mode-live-btn"
                    style={{
                      padding: "10px 12px",
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "flex-start",
                      gap: 4,
                      textAlign: "left",
                      height: "auto",
                      borderRadius: 8,
                      border: inputMode === "LIVE_MARKET" ? "1px solid var(--v3-live)" : "1px solid var(--v3-line)"
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 700, fontSize: 13, color: inputMode === "LIVE_MARKET" ? "var(--v3-live)" : undefined }}>
                      <Icon name="activity" size={14} /> Live Market
                    </div>
                    <div style={{ fontSize: 11, color: "var(--v3-ink-3)", lineHeight: 1.3 }}>
                      Real market quotes via Upstox; paper simulated broker
                    </div>
                  </button>
                </div>
                {inputMode === "LIVE_MARKET" && (
                  <div style={{ marginTop: 8, padding: "8px 10px", borderRadius: 6, background: "rgba(59, 130, 246, 0.08)", border: "1px solid rgba(59, 130, 246, 0.25)", fontSize: 11, color: "var(--v3-ink-2)", lineHeight: 1.4 }}>
                    <span style={{ fontWeight: 600, color: "var(--v3-brand)" }}>Live Market Invariant:</span> Requires your own broker connection with a credential reference. Fails closed (HTTP 424) without one. Zero real-money broker execution reachability.
                  </div>
                )}
              </div>

              <div>
                <label className="v3-field-label">Starting Capital (₹)</label>
                <div style={{ position: "relative" }}>
                  <input
                    className="v3-input"
                    type="number"
                    min={1000}
                    step={1000}
                    value={inputCapitalStr}
                    onChange={(e) => setInputCapitalStr(e.target.value)}
                    style={{ fontSize: 16, fontWeight: 700, paddingLeft: 28 }}
                    id="v3-paper-capital-input"
                  />
                  <span style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--v3-ink-dim)", fontWeight: 700 }}>
                    ₹
                  </span>
                </div>
              </div>

              {/* Quick Preset Buttons */}
              <div>
                <span className="v3-field-label" style={{ marginBottom: 6, display: "block" }}>Quick Capital Presets</span>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {[5000, 10000, 50000, 100000, 500000].map((amt) => (
                    <button
                      key={amt}
                      type="button"
                      className={`v3-preset-btn ${inputCapitalStr === amt.toString() ? "active" : ""}`}
                      onClick={() => setInputCapitalStr(amt.toString())}
                    >
                      ₹{amt >= 100000 ? `${amt / 100000}L` : `${amt / 1000}k`} ({amt.toLocaleString("en-IN")})
                    </button>
                  ))}
                </div>
              </div>

              {/* Snapshot Preview for the New Session */}
              <div style={{ padding: "10px 12px", borderRadius: 10, background: "var(--v3-surface-2)", border: "1px solid var(--v3-line)" }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "var(--v3-ink-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>
                  Immutable Session Snapshot Preview
                </div>
                <dl style={{ margin: 0, fontSize: 11.5 }}>
                  <KV k="Market Data Mode" v={inputMode === "LIVE_MARKET" ? "LIVE MARKET (Real-Time Upstox Feed)" : "HISTORICAL REPLAY (Canonical Parquet)"} />
                  <KV k="Target Strategy" v={`${sessionTargetStrategy.name} (${sessionTargetStrategy.version})`} />
                  <KV k="Global Policy Snapshot" v={policy.mode === "ATM" ? "ATM (0 strikes)" : `${policy.mode} (${policy.distance} strike${policy.distance === 1 ? "" : "s"})`} />
                  <KV k="Fill Assumptions" v="Instant Fill · Zero Slippage Assumption" />
                  <KV k="Execution Mode" v="Long-Only Options Simulation" />
                </dl>
              </div>
            </div>

            <div className="v3-modal-foot">
              <button className="v3-btn ghost" onClick={() => setNewSessionModalOpen(false)}>
                Cancel
              </button>
              <button className="v3-btn primary" onClick={handleLaunchNewSession} id="v3-confirm-launch-session-btn">
                <Icon name="play" size={13} /> Launch Session with ₹{parseInt(inputCapitalStr || "0", 10).toLocaleString("en-IN")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── MODAL 2: RESET PAPER ACCOUNT ── */}
      {resetModalOpen && (
        <div className="v3-modal-overlay" onClick={() => setResetModalOpen(false)} role="dialog" aria-modal="true" aria-label="Reset Paper Account">
          <div className="v3-modal" onClick={(e) => e.stopPropagation()}>
            <div className="v3-modal-head">
              <div>
                <div className="v3-modal-title" style={{ color: "var(--v3-loss-text)" }}>Reset Paper Account</div>
                <div className="v3-modal-sub">Zero out P&amp;L for session {sessionId}</div>
              </div>
              <button className="v3-btn ghost mini" onClick={() => setResetModalOpen(false)}>
                <Icon name="close" size={14} />
              </button>
            </div>

            <div className="v3-modal-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div className="v3-governed-note">
                <Dot tone="warn" />
                <span>
                  <b>Warning:</b> This will reset current unrealized and realized P&amp;L back to ₹0, restoring equity to initial starting capital <b>₹{initialCapital.toLocaleString("en-IN")}</b>.
                </span>
              </div>
              <p className="v3-row-sub" style={{ lineHeight: 1.5, margin: 0 }}>
                Historical session logs will remain saved in the ledger. Are you sure you want to reset this paper account?
              </p>
            </div>

            <div className="v3-modal-foot">
              <button className="v3-btn ghost" onClick={() => setResetModalOpen(false)}>
                Cancel
              </button>
              <button className="v3-btn primary" style={{ background: "var(--v3-loss)", borderColor: "var(--v3-loss)" }} onClick={handleConfirmReset} id="v3-confirm-reset-btn">
                Confirm Account Reset
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

/* ════════════════════════════════════════════════════════════
   5. PORTFOLIO WORKSPACE (LIVE-SIDE MONITORING ONLY)
   ============================================================ */
export const PortfolioScreen: React.FC<{ previewMode?: boolean }> = ({ previewMode }) =>
  previewMode ? <PortfolioPreviewScreen /> : <OrdersPortfolioRuntime initialTab="portfolio" />;

const PortfolioPreviewScreen: React.FC = () => {
  // Live-side sample positions state
  const [openPositions] = useState<LivePosition[]>(LIVE_POSITIONS);
  const [closedPositions] = useState<LiveClosedPosition[]>(LIVE_CLOSED_POSITIONS);

  // Filters State
  const [statusFilter, setStatusFilter] = useState<"ALL" | "OPEN" | "CLOSED">("ALL");
  const [underlyingFilter, setUnderlyingFilter] = useState<"ALL" | "NIFTY" | "BANKNIFTY">("ALL");
  const [typeFilter, setTypeFilter] = useState<"ALL" | "CE" | "PE">("ALL");
  const [strategyFilter, setStrategyFilter] = useState<string>("ALL");

  // Position detail inspection drawer state
  const [inspectingPosition, setInspectingPosition] = useState<LivePosition | null>(null);

  // Dynamic Live Account Math (Derived from Single Source of Truth)
  const initialBaseCapital = 1200000; // ₹12,00,000 Live Readiness Capital Base

  const capitalCommitted = useMemo(() => {
    return openPositions.reduce((acc, p) => acc + p.avgEntry * p.qty, 0);
  }, [openPositions]);

  const openMarketValue = useMemo(() => {
    return openPositions.reduce((acc, p) => acc + p.ltp * p.qty, 0);
  }, [openPositions]);

  const totalUnrealizedPnl = useMemo(() => {
    return openPositions.reduce((acc, p) => acc + (p.ltp - p.avgEntry) * p.qty, 0);
  }, [openPositions]);

  const totalRealizedPnl = useMemo(() => {
    return closedPositions.reduce((acc, p) => acc + p.realizedPnl, 0);
  }, [closedPositions]);

  const availableCash = useMemo(() => {
    return initialBaseCapital + totalRealizedPnl - capitalCommitted;
  }, [initialBaseCapital, totalRealizedPnl, capitalCommitted]);

  const totalEquity = useMemo(() => {
    return availableCash + openMarketValue;
  }, [availableCash, openMarketValue]);

  const totalPnl = useMemo(() => {
    return totalRealizedPnl + totalUnrealizedPnl;
  }, [totalRealizedPnl, totalUnrealizedPnl]);

  const totalReturnPct = useMemo(() => {
    return Number(((totalPnl / initialBaseCapital) * 100).toFixed(2));
  }, [totalPnl, initialBaseCapital]);

  // Filtered Open Positions
  const filteredOpenPositions = useMemo(() => {
    return openPositions.filter((p) => {
      if (underlyingFilter !== "ALL" && p.underlying !== underlyingFilter) return false;
      if (typeFilter !== "ALL" && p.optionType !== typeFilter) return false;
      if (strategyFilter !== "ALL" && p.strategy !== strategyFilter) return false;
      return true;
    });
  }, [openPositions, underlyingFilter, typeFilter, strategyFilter]);

  // Filtered Closed Positions
  const filteredClosedPositions = useMemo(() => {
    return closedPositions.filter((p) => {
      if (underlyingFilter !== "ALL" && p.underlying !== underlyingFilter) return false;
      if (typeFilter !== "ALL" && p.optionType !== typeFilter) return false;
      if (strategyFilter !== "ALL" && p.strategy !== strategyFilter) return false;
      return true;
    });
  }, [closedPositions, underlyingFilter, typeFilter, strategyFilter]);

  // Live-side Strategy Attribution Breakdown
  const strategyAttributions: StrategyAttributionRow[] = useMemo(() => {
    const map = new Map<string, StrategyAttributionRow>();

    // Seed known live-side strategies
    map.set("NIFTY Momentum v2.3", {
      strategyName: "NIFTY Momentum",
      version: "v2.3",
      activePositionsCount: 0,
      capitalCommitted: 0,
      unrealizedPnl: 0,
      realizedPnl: 0,
      totalPnl: 0,
      winRatePct: 75.0,
      status: "LIVE_READINESS",
    });
    map.set("BankNifty Straddle v1.8", {
      strategyName: "BankNifty Straddle",
      version: "v1.8",
      activePositionsCount: 0,
      capitalCommitted: 0,
      unrealizedPnl: 0,
      realizedPnl: 0,
      totalPnl: 0,
      winRatePct: 60.0,
      status: "LIVE_READINESS",
    });
    map.set("NIFTY ORB v1.2", {
      strategyName: "NIFTY ORB",
      version: "v1.2",
      activePositionsCount: 0,
      capitalCommitted: 0,
      unrealizedPnl: 0,
      realizedPnl: 0,
      totalPnl: 0,
      winRatePct: 80.0,
      status: "LIVE_READINESS",
    });

    openPositions.forEach((p) => {
      const existing = map.get(p.strategy);
      if (existing) {
        existing.activePositionsCount += 1;
        existing.capitalCommitted += p.avgEntry * p.qty;
        existing.unrealizedPnl += (p.ltp - p.avgEntry) * p.qty;
        existing.totalPnl += (p.ltp - p.avgEntry) * p.qty;
      }
    });

    closedPositions.forEach((p) => {
      const existing = map.get(p.strategy);
      if (existing) {
        existing.realizedPnl += p.realizedPnl;
        existing.totalPnl += p.realizedPnl;
      }
    });

    return Array.from(map.values());
  }, [openPositions, closedPositions]);

  return (
    <div className="portfolio-workspace" id="portfolio-workspace-root">
      {/* ── Screen Header ── */}
      <div className="v3-screen-head">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <h2 className="v3-screen-title" style={{ letterSpacing: "0.04em" }}>
              PORTFOLIO
            </h2>
            <span className="v3-tag online" style={{ fontSize: 11, fontWeight: 700 }}>
              LIVE MONITORING PREVIEW
            </span>
          </div>
          <p className="v3-screen-sub">
            Live account equity · Open option contracts · Real-time mark-to-market reconciliation
          </p>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <TruthChip kind="SAMPLE" title="DEV PREVIEW · Live portfolio view. Production broker execution not yet wired." />
        </div>
      </div>

      {/* ── Live Monitoring Notice Banner ── */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          padding: "10px 16px",
          border: "1px solid rgba(56, 189, 248, 0.3)",
          borderRadius: 8,
          background: "rgba(56, 189, 248, 0.06)",
          marginBottom: 16,
          flexWrap: "wrap",
        }}
        id="live-portfolio-truth-banner"
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Icon name="shield" size={15} />
          <span style={{ fontSize: 12, color: "var(--v3-ink-2)" }}>
            <strong>LIVE MONITORING PREVIEW · DEV PREVIEW · DEV SAMPLE:</strong> Live broker gateway is not yet wired. Values and execution telemetry are simulated live-side sample records. Capital exposure controls are active.
          </span>
        </div>
        <span className="v3-tag" style={{ background: "rgba(56, 189, 248, 0.12)", color: "#38bdf8", border: "1px solid rgba(56, 189, 248, 0.3)", fontSize: 10, fontWeight: 750 }}>
          LIVE READINESS ENVELOPE
        </span>
      </div>

      {/* ── Top Summary KPI Bar (100% Derived from Single Source of Truth) ── */}
      <div className="v3-kpi-grid" id="v3-portfolio-kpi-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", marginBottom: 16 }}>
        <div className="v3-kpi-card" id="portfolio-kpi-equity">
          <div className="v3-kpi-title">Portfolio Value</div>
          <div className="v3-kpi-val" style={{ color: "#38bdf8" }}>
            ₹{fmtINR(totalEquity)}
          </div>
          <div className="v3-kpi-sub">Available Cash + Market Value</div>
        </div>

        <div className="v3-kpi-card" id="portfolio-kpi-cash">
          <div className="v3-kpi-title">Available Cash</div>
          <div className="v3-kpi-val">
            ₹{fmtINR(availableCash)}
          </div>
          <div className="v3-kpi-sub">Uncommitted live-side capital</div>
        </div>

        <div className="v3-kpi-card" id="portfolio-kpi-committed">
          <div className="v3-kpi-title">Capital Committed</div>
          <div className="v3-kpi-val">
            ₹{fmtINR(capitalCommitted)}
          </div>
          <div className="v3-kpi-sub">Premium in open option positions</div>
        </div>

        <div className="v3-kpi-card" id="portfolio-kpi-realized">
          <div className="v3-kpi-title">Realized P&amp;L</div>
          <div className={`v3-kpi-val ${totalRealizedPnl >= 0 ? "v3-profit-text" : "v3-loss-text"}`}>
            {fmtSignedINR(totalRealizedPnl, 0)}
          </div>
          <div className="v3-kpi-sub">Closed trade profits</div>
        </div>

        <div className="v3-kpi-card" id="portfolio-kpi-unrealized">
          <div className="v3-kpi-title">Unrealized P&amp;L</div>
          <div className={`v3-kpi-val ${totalUnrealizedPnl >= 0 ? "v3-profit-text" : "v3-loss-text"}`}>
            {fmtSignedINR(totalUnrealizedPnl, 0)}
          </div>
          <div className="v3-kpi-sub">Floating open positions</div>
        </div>

        <div className="v3-kpi-card" id="portfolio-kpi-day-pnl">
          <div className="v3-kpi-title">Day P&amp;L</div>
          <div className={`v3-kpi-val ${totalUnrealizedPnl >= 0 ? "v3-profit-text" : "v3-loss-text"}`}>
            {fmtSignedINR(totalUnrealizedPnl, 0)}
          </div>
          <div className="v3-kpi-sub">Change since session start</div>
        </div>

        <div className="v3-kpi-card" id="portfolio-kpi-total-pnl">
          <div className="v3-kpi-title">Total P&amp;L</div>
          <div className={`v3-kpi-val ${totalPnl >= 0 ? "v3-profit-text" : "v3-loss-text"}`}>
            {fmtSignedINR(totalPnl, 0)}
          </div>
          <div className="v3-kpi-sub">+{totalReturnPct}% on capital base</div>
        </div>
      </div>

      {/* ── Interactive Filters Bar ── */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 12,
          padding: "10px 14px",
          background: "var(--v3-surface-1)",
          borderRadius: 8,
          border: "1px solid var(--v3-line)",
          marginBottom: 16,
          flexWrap: "wrap",
        }}
        id="portfolio-filters-bar"
      >
        <div className="v3-tabs" role="tablist" style={{ margin: 0 }}>
          <button
            type="button"
            className={`v3-tab ${statusFilter === "ALL" ? "active" : ""}`}
            onClick={() => setStatusFilter("ALL")}
            id="filter-all-btn"
          >
            ALL POSITIONS ({openPositions.length + closedPositions.length})
          </button>
          <button
            type="button"
            className={`v3-tab ${statusFilter === "OPEN" ? "active" : ""}`}
            onClick={() => setStatusFilter("OPEN")}
            id="filter-open-btn"
          >
            OPEN ({openPositions.length})
          </button>
          <button
            type="button"
            className={`v3-tab ${statusFilter === "CLOSED" ? "active" : ""}`}
            onClick={() => setStatusFilter("CLOSED")}
            id="filter-closed-btn"
          >
            CLOSED ({closedPositions.length})
          </button>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <select
            className="v3-input"
            style={{ width: "auto", padding: "4px 8px", fontSize: 11.5 }}
            value={underlyingFilter}
            onChange={(e) => setUnderlyingFilter(e.target.value as "ALL" | "NIFTY" | "BANKNIFTY")}
            id="underlying-filter-select"
          >
            <option value="ALL">Underlying: ALL</option>
            <option value="NIFTY">NIFTY</option>
            <option value="BANKNIFTY">BANKNIFTY</option>
          </select>

          <select
            className="v3-input"
            style={{ width: "auto", padding: "4px 8px", fontSize: 11.5 }}
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value as "ALL" | "CE" | "PE")}
            id="type-filter-select"
          >
            <option value="ALL">Option Type: ALL</option>
            <option value="CE">Calls (CE)</option>
            <option value="PE">Puts (PE)</option>
          </select>

          <select
            className="v3-input"
            style={{ width: "auto", padding: "4px 8px", fontSize: 11.5 }}
            value={strategyFilter}
            onChange={(e) => setStrategyFilter(e.target.value)}
            id="strategy-filter-select"
          >
            <option value="ALL">Strategy: ALL</option>
            <option value="NIFTY Momentum v2.3">NIFTY Momentum v2.3</option>
            <option value="BankNifty Straddle v1.8">BankNifty Straddle v1.8</option>
            <option value="NIFTY ORB v1.2">NIFTY ORB v1.2</option>
          </select>
        </div>
      </div>

      <div className="v3-grid">
        {/* ── Open Positions Table (when ALL or OPEN selected) ── */}
        {(statusFilter === "ALL" || statusFilter === "OPEN") && (
          <div className="v3-sp12">
            <Panel
              label={`Live Open Positions (${filteredOpenPositions.length})`}
              className="v3-sp12"
              meta={
                <span className="v3-chip sample" style={{ fontSize: 9.5 }}>
                  LONG-ONLY OPTIONS · LIVE READINESS
                </span>
              }
              id="live-open-positions-panel"
            >
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div className="v3-table-wrap">
                  <table className="v3-table" id="live-open-positions-table">
                    <thead>
                      <tr>
                        <th>CONTRACT</th>
                        <th>UNDERLYING</th>
                        <th>TYPE</th>
                        <th>QTY</th>
                        <th>AVG ENTRY</th>
                        <th>LTP</th>
                        <th>CURRENT VALUE</th>
                        <th>UNREALIZED P&amp;L</th>
                        <th>RETURN %</th>
                        <th>STRATEGY</th>
                        <th>ENTRY TIME</th>
                        <th>STATUS</th>
                        <th>ACTIONS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredOpenPositions.map((p) => (
                        <tr
                          key={p.id}
                          style={{ cursor: "pointer" }}
                          onClick={() => setInspectingPosition(p)}
                        >
                          <td className="v3-mono font-bold" style={{ color: "#38bdf8" }}>
                            {p.contract}
                          </td>
                          <td className="v3-mono font-semibold">{p.underlying}</td>
                          <td>
                            <span className={`v3-tag ${p.optionType === "CE" ? "online" : "warning"}`} style={{ fontSize: 9.5 }}>
                              {p.optionType}
                            </span>
                          </td>
                          <td className="v3-mono">{p.qty}</td>
                          <td className="v3-mono">₹{p.avgEntry.toFixed(2)}</td>
                          <td className="v3-mono font-bold">₹{p.ltp.toFixed(2)}</td>
                          <td className="v3-mono">₹{p.currentValue.toLocaleString()}</td>
                          <td className={`v3-mono font-bold ${p.unrealizedPnl >= 0 ? "v3-profit-text" : "v3-loss-text"}`}>
                            {p.unrealizedPnl >= 0 ? `+₹${p.unrealizedPnl.toLocaleString()}` : `-₹${Math.abs(p.unrealizedPnl).toLocaleString()}`}
                          </td>
                          <td className={`v3-mono font-bold ${p.returnPct >= 0 ? "v3-profit-text" : "v3-loss-text"}`}>
                            {p.returnPct >= 0 ? `+${p.returnPct.toFixed(2)}%` : `${p.returnPct.toFixed(2)}%`}
                          </td>
                          <td style={{ fontSize: 11.5 }}>{p.strategy}</td>
                          <td className="v3-cell-date">{p.entryTime}</td>
                          <td>
                            <span className="v3-tag online" style={{ fontSize: 9.5 }}>
                              {p.status}
                            </span>
                          </td>
                          <td>
                            <button
                              type="button"
                              className="v3-btn ghost mini"
                              onClick={(e) => {
                                e.stopPropagation();
                                setInspectingPosition(p);
                              }}
                              id={`inspect-pos-${p.id}`}
                            >
                              Inspect
                            </button>
                          </td>
                        </tr>
                      ))}
                      {filteredOpenPositions.length === 0 && (
                        <tr>
                          <td colSpan={13} style={{ textAlign: "center", padding: "24px", color: "var(--v3-ink-3)" }}>
                            No open positions matching current filters.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </Panel>
          </div>
        )}

        {/* ── Live-Side Strategy Attribution Breakdown ── */}
        <div className="v3-sp12">
          <Panel
            label="Live-Side Strategy Attribution Breakdown"
            className="v3-sp12"
            meta={
              <span className="v3-mono text-xs v3-dim">
                Real-time capital &amp; P&amp;L allocation
              </span>
            }
            id="strategy-attribution-panel"
          >
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="v3-table-wrap">
                <table className="v3-table" id="strategy-attribution-table">
                  <thead>
                    <tr>
                      <th>STRATEGY</th>
                      <th>SPEC VERSION</th>
                      <th>ACTIVE POSITIONS</th>
                      <th>COMMITTED CAPITAL</th>
                      <th>UNREALIZED P&amp;L</th>
                      <th>REALIZED P&amp;L</th>
                      <th>TOTAL P&amp;L</th>
                      <th>STATUS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {strategyAttributions.map((s, idx) => (
                      <tr key={idx}>
                        <td className="font-semibold">{s.strategyName}</td>
                        <td className="v3-mono">{s.version}</td>
                        <td className="v3-mono font-bold">{s.activePositionsCount}</td>
                        <td className="v3-mono">₹{s.capitalCommitted.toLocaleString()}</td>
                        <td className={`v3-mono font-bold ${s.unrealizedPnl >= 0 ? "v3-profit-text" : "v3-loss-text"}`}>
                          {s.unrealizedPnl !== 0 ? (s.unrealizedPnl >= 0 ? `+₹${s.unrealizedPnl.toLocaleString()}` : `-₹${Math.abs(s.unrealizedPnl).toLocaleString()}`) : "₹0.00"}
                        </td>
                        <td className={`v3-mono font-bold ${s.realizedPnl >= 0 ? "v3-profit-text" : "v3-loss-text"}`}>
                          {s.realizedPnl !== 0 ? (s.realizedPnl >= 0 ? `+₹${s.realizedPnl.toLocaleString()}` : `-₹${Math.abs(s.realizedPnl).toLocaleString()}`) : "₹0.00"}
                        </td>
                        <td className={`v3-mono font-bold ${s.totalPnl >= 0 ? "v3-profit-text" : "v3-loss-text"}`}>
                          {s.totalPnl >= 0 ? `+₹${s.totalPnl.toLocaleString()}` : `-₹${Math.abs(s.totalPnl).toLocaleString()}`}
                        </td>
                        <td>
                          <span className="v3-tag online" style={{ fontSize: 9.5 }}>
                            {s.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </Panel>
        </div>

        {/* ── Closed Live-Side Positions Ledger (when ALL or CLOSED selected) ── */}
        {(statusFilter === "ALL" || statusFilter === "CLOSED") && (
          <div className="v3-sp12">
            <Panel
              label={`Closed Live-Side Positions Ledger (${filteredClosedPositions.length})`}
              className="v3-sp12"
              meta={
                <span className="v3-chip sample" style={{ fontSize: 9.5 }}>
                  SAMPLE TRADES LEDGER
                </span>
              }
              id="live-closed-positions-panel"
            >
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div className="v3-table-wrap">
                  <table className="v3-table" id="live-closed-positions-table">
                    <thead>
                      <tr>
                        <th>CONTRACT</th>
                        <th>STRATEGY</th>
                        <th>QTY</th>
                        <th>ENTRY PRICE</th>
                        <th>EXIT PRICE</th>
                        <th>REALIZED P&amp;L</th>
                        <th>RETURN %</th>
                        <th>OPENED</th>
                        <th>CLOSED</th>
                        <th>EXIT REASON</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredClosedPositions.map((p) => (
                        <tr key={p.id}>
                          <td className="v3-mono font-bold">{p.contract}</td>
                          <td style={{ fontSize: 11.5 }}>{p.strategy}</td>
                          <td className="v3-mono">{p.qty}</td>
                          <td className="v3-mono">₹{p.entryPrice.toFixed(2)}</td>
                          <td className="v3-mono font-bold">₹{p.exitPrice.toFixed(2)}</td>
                          <td className={`v3-mono font-bold ${p.realizedPnl >= 0 ? "v3-profit-text" : "v3-loss-text"}`}>
                            {p.realizedPnl >= 0 ? `+₹${p.realizedPnl.toLocaleString()}` : `-₹${Math.abs(p.realizedPnl).toLocaleString()}`}
                          </td>
                          <td className={`v3-mono font-bold ${p.returnPct >= 0 ? "v3-profit-text" : "v3-loss-text"}`}>
                            {p.returnPct >= 0 ? `+${p.returnPct.toFixed(2)}%` : `${p.returnPct.toFixed(2)}%`}
                          </td>
                          <td className="v3-cell-date">{p.openedAt}</td>
                          <td className="v3-cell-date">{p.closedAt}</td>
                          <td>
                            <span className={`v3-tag ${p.realizedPnl >= 0 ? "online" : "warning"}`} style={{ fontSize: 9.5 }}>
                              {p.exitReason}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </Panel>
          </div>
        )}
      </div>

      {/* ── Position Detail Inspection Drawer ── */}
      {inspectingPosition && (
        <Drawer
          open={Boolean(inspectingPosition)}
          title={`${inspectingPosition.contract} · Position Details`}
          sub="Live-side telemetry &amp; execution parameter inspection"
          onClose={() => setInspectingPosition(null)}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }} id="position-inspection-drawer-body">
            <div className="dev-preview-banner">
              <span className="banner-tag">LIVE READINESS</span>
              <span>LIVE MONITORING PREVIEW · NOT YET AUTHORITATIVE · DEV SAMPLE</span>
            </div>

            <div style={{ padding: "10px 12px", background: "var(--v3-surface-1)", borderRadius: 6, border: "1px solid var(--v3-line)" }}>
              <div style={{ fontSize: 11, color: "var(--v3-ink-3)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 6 }}>
                Execution Resolution Evidence
              </div>
              <div className="v3-rows">
                <div className="v3-row">
                  <span className="v3-row-sub">Contract Symbol</span>
                  <span className="v3-mono font-bold" style={{ color: "#38bdf8" }}>{inspectingPosition.contract}</span>
                </div>
                <div className="v3-row">
                  <span className="v3-row-sub">Strategy Driver</span>
                  <span className="font-semibold">{inspectingPosition.strategy}</span>
                </div>
                <div className="v3-row">
                  <span className="v3-row-sub">Entry Timestamp</span>
                  <span className="v3-mono">{inspectingPosition.entryTime}</span>
                </div>
                <div className="v3-row">
                  <span className="v3-row-sub">Entry Spot / ATM Reference</span>
                  <span className="v3-mono">₹{inspectingPosition.entrySpot.toFixed(2)} (ATM {inspectingPosition.entryAtm})</span>
                </div>
              </div>
            </div>

            <div style={{ padding: "10px 12px", background: "var(--v3-surface-1)", borderRadius: 6, border: "1px solid var(--v3-line)" }}>
              <div style={{ fontSize: 11, color: "var(--v3-ink-3)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 6 }}>
                Financial Accounting &amp; Pricing
              </div>
              <div className="v3-rows">
                <div className="v3-row">
                  <span className="v3-row-sub">Average Entry Price</span>
                  <span className="v3-mono">₹{inspectingPosition.avgEntry.toFixed(2)}</span>
                </div>
                <div className="v3-row">
                  <span className="v3-row-sub">Current LTP</span>
                  <span className="v3-mono font-bold">₹{inspectingPosition.ltp.toFixed(2)}</span>
                </div>
                <div className="v3-row">
                  <span className="v3-row-sub">Quantity</span>
                  <span className="v3-mono">{inspectingPosition.qty} units ({inspectingPosition.underlying === "NIFTY" ? inspectingPosition.qty / 75 : inspectingPosition.qty / 15} lots)</span>
                </div>
                <div className="v3-row">
                  <span className="v3-row-sub">Capital Committed</span>
                  <span className="v3-mono">₹{(inspectingPosition.avgEntry * inspectingPosition.qty).toLocaleString()}</span>
                </div>
                <div className="v3-row">
                  <span className="v3-row-sub">Current Market Value</span>
                  <span className="v3-mono">₹{inspectingPosition.currentValue.toLocaleString()}</span>
                </div>
                <div className="v3-row">
                  <span className="v3-row-sub">Floating Unrealized P&amp;L</span>
                  <span className={`v3-mono font-bold ${inspectingPosition.unrealizedPnl >= 0 ? "v3-profit-text" : "v3-loss-text"}`}>
                    {inspectingPosition.unrealizedPnl >= 0 ? `+₹${inspectingPosition.unrealizedPnl.toLocaleString()}` : `-₹${Math.abs(inspectingPosition.unrealizedPnl).toLocaleString()}`} ({inspectingPosition.returnPct >= 0 ? `+${inspectingPosition.returnPct.toFixed(2)}%` : `${inspectingPosition.returnPct.toFixed(2)}%`})
                  </span>
                </div>
              </div>
            </div>

            <div style={{ padding: "10px 12px", background: "var(--v3-surface-1)", borderRadius: 6, border: "1px solid var(--v3-line)" }}>
              <div style={{ fontSize: 11, color: "var(--v3-ink-3)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 6 }}>
                Active Risk &amp; Exit Targets
              </div>
              <div className="v3-rows">
                <div className="v3-row">
                  <span className="v3-row-sub">Stop Loss Level</span>
                  <span className="v3-mono v3-loss-text">{inspectingPosition.stopLoss != null ? `₹${inspectingPosition.stopLoss.toFixed(2)}` : "UNAVAILABLE"}</span>
                </div>
                <div className="v3-row">
                  <span className="v3-row-sub">Take Profit Target</span>
                  <span className="v3-mono v3-profit-text">{inspectingPosition.target != null ? `₹${inspectingPosition.target.toFixed(2)}` : "UNAVAILABLE"}</span>
                </div>
                <div className="v3-row">
                  <span className="v3-row-sub">Active Trailing Stop</span>
                  <span className="v3-mono" style={{ color: "var(--v3-amber)" }}>{inspectingPosition.trailStop != null ? `₹${inspectingPosition.trailStop.toFixed(2)}` : "UNAVAILABLE"}</span>
                </div>
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 4 }}>
              <button
                type="button"
                className="v3-btn secondary"
                onClick={() => setInspectingPosition(null)}
                id="close-position-drawer-btn"
              >
                Close Inspection
              </button>
            </div>
          </div>
        </Drawer>
      )}
    </div>
  );
};

/* ════════════════════════════════════════════════════════════
   6. ORDERS SCREEN — LIVE-SIDE ORDER LIFECYCLE / MONITORING ONLY
   OWNER DECISION (V1): Orders never shows Paper Trading orders,
   Backtest simulation orders, or paper session state. Live-side
   prototype sample state only (hard isolation invariant).
   Buy-only opening model: BUY opens exposure; SELL TO CLOSE closes
   an existing long option. No SELL SHORT / SELL TO OPEN.
   Orders originate from governed strategy / risk / protective
   context only — no manual order entry. Monitoring only.
   BROKER EXECUTION NOT YET WIRED — DEV SAMPLE, non-authoritative.
   ============================================================ */
type OrdersFilter = "ALL" | "FILLED" | "OPEN" | "CANCELLED" | "REJECTED";

const OPEN_LIKE_STATUSES: LiveOrderStatus[] = ["OPEN", "ACCEPTED", "PENDING", "PARTIALLY FILLED"];

const fmtRealizedPnl = (v: number): string =>
  `${v < 0 ? "−" : "+"}₹${Math.abs(v).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const OrderStatusBadge: React.FC<{ status: LiveOrderStatus }> = ({ status }) => {
  switch (status) {
    case "FILLED": return <span className="v3-profit-badge">{status}</span>;
    case "REJECTED": return <span className="v3-loss-badge">{status}</span>;
    case "PENDING": case "PARTIALLY FILLED": return <span className="v3-atm-badge">{status}</span>;
    case "CANCELLED": case "EXPIRED": return <span className="v3-otm-badge">{status}</span>;
    default: return <span className="v3-py-badge">{status}</span>; /* OPEN / ACCEPTED */
  }
};

const OrderSideBadge: React.FC<{ side: LiveOrderRow["side"] }> = ({ side }) =>
  side === "BUY"
    ? <span className="v3-profit-badge">BUY</span>
    : <span className="v3-py-badge">SELL TO CLOSE</span>;

/* Lifecycle timeline — truth-labeled sample events (no fabricated backend authority) */
const OrderLifecycleTimeline: React.FC<{ order: LiveOrderRow }> = ({ order }) => (
  <div className="v3-order-timeline">
    {order.lifecycle.map((e, i) => (
      <div className="v3-order-tl-row" key={i}>
        <Dot tone={e.tone} />
        <span className="v3-order-tl-label">{e.label}</span>
        <span className="v3-mono v3-dim v3-order-tl-time">{e.time}</span>
      </div>
    ))}
  </div>
);

export const OrdersScreen: React.FC<{ previewMode?: boolean }> = ({ previewMode }) =>
  previewMode ? <OrdersPreviewScreen /> : <OrdersPortfolioRuntime initialTab="orders" />;

const OrdersPreviewScreen: React.FC = () => {
  /* Live-side prototype state — fully isolated from Paper Trading and Backtesting. */
  const [orders] = useState<LiveOrderRow[]>(() => LIVE_ORDERS.map((o) => ({ ...o, lifecycle: [...o.lifecycle] })));
  const [filter, setFilter] = useState<OrdersFilter>("ALL");
  const [openId, setOpenId] = useState<string | null>(null);

  const filtered = orders.filter((o) => {
    if (filter === "ALL") return true;
    if (filter === "OPEN") return OPEN_LIKE_STATUSES.includes(o.status);
    return o.status === filter;
  });
  const selected = orders.find((o) => o.id === openId) ?? null;
  const countBy = (fn: (o: LiveOrderRow) => boolean) => orders.filter(fn).length;

  const realizedCell = (o: LiveOrderRow) => {
    const v = liveOrderRealizedPnl(o);
    if (v === null) return <span className="v3-dim v3-mono">—</span>;
    return <span className={`v3-mono ${v >= 0 ? "v3-profit-text" : "v3-loss-text"}`}>{fmtRealizedPnl(v)}</span>;
  };

  return (
    <>
      <div className="v3-screen-head">
        <div>
          <h2 className="v3-screen-title">Orders</h2>
          <p className="v3-screen-sub">Live-side order lifecycle monitoring · strategy-driven sources only</p>
        </div>
        <TruthChip kind="SAMPLE" title="LIVE ORDER MONITORING PREVIEW · DEV SAMPLE — no broker-connected order state" />
      </div>

      <div className="dev-preview-banner" style={{ marginBottom: 14 }}>
        <span className="banner-tag">LIVE ORDER MONITORING PREVIEW</span>
        <span>
          DEV PREVIEW · DEV SAMPLE · BROKER EXECUTION NOT YET WIRED · Live-side strategy-driven order lifecycle only ·
          Buy-only opening model (BUY / SELL TO CLOSE) · Inspection UI — no order-entry controls.
        </span>
      </div>

      {/* Orders summary */}
      <div style={{ display: "flex", gap: 18, flexWrap: "wrap", marginBottom: 12 }}>
        <span className="v3-stat-line"><Dot tone="ok" /> {countBy((o) => o.status === "FILLED")} Filled</span>
        <span className="v3-stat-line"><Dot tone="live" /> {countBy((o) => OPEN_LIKE_STATUSES.includes(o.status))} Working</span>
        <span className="v3-stat-line"><Dot tone="warn" /> {countBy((o) => o.status === "REJECTED")} Rejected (fail-closed)</span>
        <span className="v3-stat-line"><Dot tone="dim" /> {countBy((o) => o.status === "CANCELLED" || o.status === "EXPIRED")} Cancelled / Expired</span>
      </div>

      {/* Status filters — REAL + WORKING within the prototype */}
      <div className="v3-tabs" style={{ marginBottom: 12 }}>
        {([
          ["ALL", "All"],
          ["FILLED", "Filled"],
          ["OPEN", "Open"],
          ["CANCELLED", "Cancelled"],
          ["REJECTED", "Rejected"],
        ] as [OrdersFilter, string][]).map(([id, label]) => (
          <button key={id} className={`v3-tab ${filter === id ? "active" : ""}`} onClick={() => setFilter(id)} id={`orders-filter-${id.toLowerCase()}`}>
            {label} ({id === "OPEN" ? countBy((o) => OPEN_LIKE_STATUSES.includes(o.status)) : id === "ALL" ? orders.length : countBy((o) => o.status === (id as LiveOrderStatus))})
          </button>
        ))}
      </div>

      {/* Desktop blotter — compact professional table (REALIZED P&L only where a
          completed SELL TO CLOSE round trip exists; everything else "—") */}
      <div className="v3-table-wrap v3-orders-desktop">
        <table className="v3-table">
          <thead>
            <tr>
              <th>Order ID</th>
              <th>Time</th>
              <th>Instrument</th>
              <th>Side</th>
              <th>Order Type</th>
              <th>Qty</th>
              <th>Price</th>
              <th>Status</th>
              <th>Source</th>
              <th>Realized P&amp;L</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((o) => (
              <tr key={o.id} style={{ cursor: "pointer" }} onClick={() => setOpenId(o.id)} id={`orders-row-${o.id}`}>
                <td className="v3-mono v3-dim">{o.id}</td>
                <td className="v3-mono">{o.createdAt}</td>
                <td style={{ fontWeight: 600 }}>{o.instrument}</td>
                <td><OrderSideBadge side={o.side} /></td>
                <td className="v3-mono">{o.orderType}</td>
                <td className="v3-mono">{o.qty}</td>
                <td className="v3-mono">₹{o.price}</td>
                <td><OrderStatusBadge status={o.status} /></td>
                <td style={{ color: "var(--v3-ink-3)", whiteSpace: "nowrap" }}>{o.source}</td>
                <td>{realizedCell(o)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile order cards — summary → filters → cards → detail drawer. No horizontal overflow. */}
      <div className="v3-order-cards">
        {filtered.map((o) => (
          <button key={o.id} className="v3-order-card" onClick={() => setOpenId(o.id)} id={`orders-card-${o.id}`}>
            <span className="v3-order-card-top">
              <span className="v3-mono v3-dim">{o.id}</span>
              <OrderStatusBadge status={o.status} />
            </span>
            <span className="v3-order-card-mid">
              <span style={{ fontWeight: 650 }}>{o.instrument}</span>
              <OrderSideBadge side={o.side} />
            </span>
            <span className="v3-order-card-sub">
              {o.orderType} · {o.qty} @ ₹{o.price} · {o.createdAt}
            </span>
            <span className="v3-order-card-src">
              <span className="v3-ink3">{o.source}</span>
              <span className="v3-mono" style={{ fontSize: 11.5 }}>R.P&amp;L: {realizedCell(o)}</span>
            </span>
          </button>
        ))}
      </div>

      {/* Order detail drawer — inspection only, no order-entry or modify actions */}
      <Drawer
        open={selected !== null}
        title={selected ? `Order ${selected.id}` : ""}
        sub="LIVE MONITORING PREVIEW · DEV SAMPLE — sample lifecycle events, non-authoritative"
        onClose={() => setOpenId(null)}
      >
        {selected && (
          <>
            <dl style={{ margin: 0 }}>
              <KV k="Order ID" v={selected.id} />
              <KV k="Strategy" v={selected.strategyName ? `${selected.strategyName} ${selected.strategyVersion ?? ""}`.trim() : "—"} />
              <KV k="Instrument" v={selected.instrument} />
              <KV k="Underlying" v={`${selected.underlying} · ${selected.optionType}`} />
              <KV k="Side" v={selected.side} />
              <KV k="Order Type" v={selected.orderType} />
              <KV k="Qty" v={String(selected.qty)} />
              <KV k="Requested Price" v={`₹${selected.price}`} />
              <KV k="Fill Price" v={selected.fillPrice ? `₹${selected.fillPrice}` : "—"} />
              <KV k="Filled Qty" v={selected.filledQty != null ? String(selected.filledQty) : "—"} />
              <KV k="Status" v={selected.status} />
              <KV k="Created Time" v={selected.createdAt} />
              <KV k="Updated Time" v={selected.updatedAt} />
              <KV k="Source" v={selected.source} />
              <KV k="Contract Resolution" v={selected.contractContext} />
              <KV
                k="Risk Decision"
                v={selected.riskDecision}
                vClass={selected.status === "REJECTED" ? "v3-loss-text" : "v3-profit-text"}
              />
              {selected.rejectReason && <KV k="Rejection Reason (fail-closed)" v={selected.rejectReason} vClass="v3-loss-text" />}
              {selected.cancelReason && <KV k="Cancellation Reason" v={selected.cancelReason} />}
              {(() => {
                const v = liveOrderRealizedPnl(selected);
                return v !== null ? (
                  <KV
                    k="Realized P&L (SELL TO CLOSE · FILLED)"
                    v={fmtRealizedPnl(v)}
                    vClass={v >= 0 ? "v3-profit-text" : "v3-loss-text"}
                  />
                ) : null;
              })()}
            </dl>

            <div className="v3-field-label" style={{ marginTop: 16 }}>Lifecycle Events</div>
            <OrderLifecycleTimeline order={selected} />
            <div className="v3-row-sub" style={{ marginTop: 8 }}>
              Sample events for prototype inspection — no production backend authority is implied.
            </div>
          </>
        )}
      </Drawer>
    </>
  );
};

/* ════════════════════════════════════════════════════════════
   7. REPORTS & DIGESTS — REPORTING PREVIEW · DEV SAMPLE
   Truth state: DEV SAMPLE. Production report generation and export
   are NOT wired. No cryptographic or regulatory verification is
   performed or implied. Exports show an explicit unwired status.
   ============================================================ */
export const ReportsScreen: React.FC<{ previewMode?: boolean }> = ({ previewMode = false }) => {
  const [evidenceId, setEvidenceId] = useState<string | null>(null);
  const [exportNote, setExportNote] = useState<string | null>(null);
  const [reports, setReports] = useState<AuthoritativeReportItem[]>([]);
  const [isLoaded, setIsLoaded] = useState<boolean>(false);

  useEffect(() => {
    let active = true;
    queryReports().then((res) => {
      if (active) {
        setReports(res.data || []);
        setIsLoaded(true);
      }
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!exportNote) return;
    const t = window.setTimeout(() => setExportNote(null), 5000);
    return () => window.clearTimeout(t);
  }, [exportNote]);

  const selected = reports.find((r) => r.id === evidenceId) ?? null;

  return (
    <>
      <div className="v3-screen-head">
        <div>
          <h2 className="v3-screen-title">Reports &amp; Digests</h2>
          <p className="v3-screen-sub">Authoritative backtest performance, paper ledger, and shadow execution digests</p>
        </div>
        <TruthChip kind={previewMode ? "SAMPLE" : "REAL"} title={previewMode ? "DEV PREVIEW / SAMPLE" : "Authoritative AlgoFortis Reports"} />
      </div>

      <div className="v3-grid">
        {reports.length === 0 ? (
          <div className="v3-panel v3-sp12" style={{ padding: 48, textAlign: "center", color: "var(--v3-dim)" }} id="empty-reports-state">
            <Icon name="file" size={32} style={{ marginBottom: 12, opacity: 0.5 }} />
            <div style={{ fontSize: 15, fontWeight: 600, color: "var(--v3-ink)" }}>No reports yet</div>
            <div className="v3-row-sub" style={{ marginTop: 4 }}>Completed backtests, paper trading sessions, and shadow execution dry-runs will appear here as authoritative reports.</div>
          </div>
        ) : (
          reports.map((rep) => (
            <div key={rep.id} className="v3-panel v3-sp6" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                <div style={{ minWidth: 0 }}>
                  <span style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 6 }}>
                    <span className="v3-itm-badge">{rep.category}</span>
                    <span
                      className="v3-itm-badge"
                      style={{
                        color: rep.status === "AVAILABLE" || rep.status === "READY" || rep.status === "COMPLETED" ? "#22c55e" : rep.status === "FAILED" || rep.status === "ARTIFACT_MISSING" ? "#ef4444" : "#eab308",
                        borderColor: rep.status === "AVAILABLE" || rep.status === "READY" || rep.status === "COMPLETED" ? "rgba(34,197,94,0.3)" : rep.status === "FAILED" || rep.status === "ARTIFACT_MISSING" ? "rgba(239,68,68,0.3)" : "rgba(234,179,8,0.3)",
                      }}
                    >
                      {rep.status}
                    </span>
                  </span>
                  <div style={{ fontWeight: 700, fontSize: 14, color: "var(--v3-ink)" }}>{rep.title}</div>
                  <div className="v3-row-sub">Period: {rep.period} · Generated {rep.generatedAt}</div>
                  {rep.summary && <div className="v3-row-sub" style={{ marginTop: 4, color: "var(--v3-ink-2)" }}>{rep.summary}</div>}
                </div>
                <span className="v3-mono v3-dim" style={{ fontSize: 11, whiteSpace: "nowrap" }}>{rep.fileSize} · {rep.format}</span>
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: "auto", paddingTop: 8, borderTop: "1px solid var(--v3-line)", flexWrap: "wrap" }}>
                <button
                  className="v3-btn ghost mini"
                  id={`report-export-${rep.id}`}
                  aria-label={`Download ${rep.title} (${rep.format})`}
                  onClick={() => {
                    const blob = new Blob([JSON.stringify(rep.data || rep, null, 2)], { type: "application/json" });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = `${rep.id}.json`;
                    a.click();
                    URL.revokeObjectURL(url);
                    setExportNote(`Downloaded ${rep.title} (${rep.format})`);
                  }}
                >
                  <Icon name="file" size={12} /> Download {rep.format}
                </button>
                <button
                  className="v3-btn ghost mini"
                  id={`report-evidence-${rep.id}`}
                  aria-label={`View evidence details for ${rep.title}`}
                  onClick={() => setEvidenceId(rep.id)}
                >
                  <Icon name="shield" size={12} /> View Evidence
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {exportNote && (
        <div
          id="reports-export-status"
          role="status"
          aria-live="polite"
          style={{
            position: "fixed", bottom: 18, right: 18, zIndex: 60, maxWidth: 360,
            background: "var(--v3-surface-2)", border: "1px solid var(--v3-line)", borderRadius: 10,
            padding: "10px 14px", fontSize: 12.5, color: "var(--v3-ink)", boxShadow: "0 8px 24px rgba(0,0,0,0.25)",
          }}
        >
          <Dot tone="ok" /> {exportNote}
        </div>
      )}

      <Drawer
        open={selected !== null}
        title={selected ? `Evidence — ${selected.title}` : ""}
        sub="Authoritative AlgoFortis Report Verification"
        onClose={() => setEvidenceId(null)}
      >
        {selected && (
          <>
            <dl style={{ margin: 0 }}>
              <KV k="Report Title" v={selected.title} />
              <KV k="Category" v={selected.category} />
              <KV k="Period" v={selected.period} />
              <KV k="Generated At" v={selected.generatedAt} />
              <KV k="Format" v={selected.format} />
              <KV k="Estimated Size" v={selected.fileSize} />
              <KV k="Summary" v={selected.summary} />
            </dl>
            <div style={{ marginTop: 14, padding: "10px 12px", background: "var(--v3-surface-2)", border: "1px solid var(--v3-line)", borderRadius: 8 }}>
              <span className="v3-itm-badge" style={{ color: "#22c55e", borderColor: "rgba(34,197,94,0.3)" }}>AUTHORITATIVE SNAPSHOT</span>
              <div className="v3-row-sub" style={{ marginTop: 8 }}>
                Synthesized directly from AlgoFortis authoritative execution runtime stores. No external broker mutation is permitted or configured.
              </div>
            </div>
          </>
        )}
      </Drawer>
    </>
  );
};

/* ════════════════════════════════════════════════════════════
   8. SECURITY WORKSPACE — SECURITY PREVIEW · DEV SAMPLE
   Truth state: DEV SAMPLE. Production security/session enforcement
   and the auth service are NOT wired in this V1 preview. No
   credential material, private keys, or tokens are ever displayed.
   Enrollment/revocation controls show explicit not-wired status.
   ============================================================ */
export const SecurityScreen: React.FC = () => {
  const [statusNote, setStatusNote] = useState<string | null>(null);
  const [profileData, setProfileData] = useState<UserProfileData | null>(null);
  const [source, setSource] = useState<"BACKEND" | "SAMPLE">("SAMPLE");

  useEffect(() => {
    let active = true;
    queryCurrentUserProfile().then((res) => {
      if (active && res.data) {
        setProfileData(res.data);
        setSource(res.source === "BACKEND" ? "BACKEND" : "SAMPLE");
      }
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!statusNote) return;
    const t = window.setTimeout(() => setStatusNote(null), 5000);
    return () => window.clearTimeout(t);
  }, [statusNote]);

  const handleRevokeCurrentSession = async () => {
    const res = await revokeCurrentUserSession();
    if (res.success) {
      setStatusNote("Active session revoked on AlgoFortis backend authority. Reloading...");
      setTimeout(() => {
        window.location.reload();
      }, 1200);
    } else {
      setStatusNote(res.error || "Failed to revoke session");
    }
  };

  return (
    <>
      <div className="v3-screen-head">
        <div>
          <h2 className="v3-screen-title">Security &amp; Passkeys</h2>
          <p className="v3-screen-sub">Session security, optional WebAuthn passkeys, device sessions</p>
        </div>
        <TruthChip
          kind={source === "BACKEND" ? "REAL" : "SAMPLE"}
          title={source === "BACKEND" ? "Authoritative operator session and authenticator profile from AlgoFortis backend." : "SECURITY PREVIEW · DEV SAMPLE — production security/session enforcement not yet wired."}
        />
      </div>

      {source === "BACKEND" ? (
        <div className="security-notice-box" style={{ marginBottom: 14 }}>
          <span className="sec-notice-icon">🛡</span>
          <span>
            <strong>Authoritative Security Active:</strong> Enforcing fail-closed session validation for <code>{profileData?.sx_id}</code> ({profileData?.role}). Lifecycle: <code>{profileData?.lifecycle}</code>. Service status: <code>{profileData?.service_status}</code>.
          </span>
        </div>
      ) : (
        <div className="dev-preview-banner" style={{ marginBottom: 14 }}>
          <span className="banner-tag">SECURITY PREVIEW</span>
          <span>
            DEV SAMPLE · AUTH SERVICE NOT WIRED · Production-grade security/session enforcement not yet wired ·
            Credential material is not displayed in this prototype · Sample metadata only.
          </span>
        </div>
      )}

      <div className="v3-grid">
        <Panel label="Registered Passkeys &amp; Authenticators (Optional)" meta="Passkeys / WebAuthn · Optional factor" className="v3-sp6">
          <div style={{ padding: "8px 10px", background: "var(--v3-surface-2)", borderRadius: 8, fontSize: 11.5, color: "var(--v3-ink-3)", marginBottom: 12, lineHeight: 1.4 }}>
            <Dot tone={source === "BACKEND" ? "ok" : "dim"} /> Standard login uses session-based secure entry. Passkeys / WebAuthn are an
            additional account security factor where supported — optional, not mandatory.
            {source === "BACKEND" ? (
              <span> FIDO2 WebAuthn baseline active for operator <strong>{profileData?.sx_id}</strong>.</span>
            ) : (
              <span> Sample credential metadata shown; production enrollment not yet wired.</span>
            )}
          </div>
          <div className="v3-rows">
            {source === "BACKEND" ? (
              <div className="v3-row">
                <div className="v3-row-main">
                  <div className="v3-row-title"><Icon name="key" size={13} style={{ marginRight: 6 }} /> Primary Authenticator Passkey</div>
                  <div className="v3-row-sub">Registered via WebAuthn ceremony · Active authenticator bound to {profileData?.sx_id}</div>
                </div>
                <span className="v3-itm-badge" style={{ fontSize: 10 }}>FIDO2 · ACTIVE</span>
              </div>
            ) : (
              WEBAUTHN_KEYS.map((k) => (
                <div className="v3-row" key={k.id}>
                  <div className="v3-row-main">
                    <div className="v3-row-title"><Icon name="key" size={13} style={{ marginRight: 6 }} /> {k.label}</div>
                    <div className="v3-row-sub">Registered {k.registeredAt} · Last used {k.lastUsed} · Optional Passkey · Sample metadata</div>
                  </div>
                  <span className="v3-itm-badge" style={{ fontSize: 10 }}>REGISTERED · SAMPLE</span>
                </div>
              ))
            )}
          </div>
          <button
            className="v3-btn ghost mini"
            style={{ marginTop: 12 }}
            id="security-add-passkey"
            aria-label="Add optional passkey — enrollment is not wired in this V1 preview"
            onClick={() => setStatusNote(source === "BACKEND" ? "Passkey management requires Owner or Setup authorization." : "Passkey enrollment is not wired in this V1 preview.")}
          >
            <Icon name="plus" size={12} /> Add Optional Passkey / Key
          </button>
        </Panel>

        <Panel label="Active Authorized Sessions" meta={source === "BACKEND" ? "Authoritative Sessions" : "Session security preview · DEV SAMPLE"} className="v3-sp6">
          <div className="v3-rows">
            {source === "BACKEND" ? (
              <div className="v3-row">
                <div className="v3-row-main">
                  <div className="v3-row-title">Current Terminal / Browser Session <span className="v3-profit-badge" style={{ fontSize: 9.5 }}>CURRENT</span></div>
                  <div className="v3-row-sub">Session token active · Operator: {profileData?.sx_id} ({profileData?.role}) · Service: {profileData?.service_status}</div>
                </div>
                <button
                  className="v3-btn ghost mini"
                  id="security-revoke-current"
                  aria-label="Revoke current session"
                  onClick={handleRevokeCurrentSession}
                >
                  Revoke
                </button>
              </div>
            ) : (
              SECURITY_SESSIONS.map((s) => (
                <div className="v3-row" key={s.id}>
                  <div className="v3-row-main">
                    <div className="v3-row-title">{s.device} {s.isCurrent && <span className="v3-profit-badge" style={{ fontSize: 9.5 }}>CURRENT</span>}</div>
                    <div className="v3-row-sub">{s.browser} · Sample IP: {s.ip} · Approx. location: {s.location} · Last active: {s.lastActive}</div>
                  </div>
                  {s.isCurrent ? (
                    <span className="v3-mono v3-dim" style={{ fontSize: 11 }}>{s.lastActive}</span>
                  ) : (
                    <button
                      className="v3-btn ghost mini"
                      id={`security-revoke-${s.id}`}
                      aria-label={`Revoke session on ${s.device} — revocation is not wired in this V1 preview`}
                      onClick={() => setStatusNote("Session revocation is not wired in this V1 preview.")}
                    >
                      Revoke
                    </button>
                  )}
                </div>
              ))
            )}
          </div>
          <div className="v3-row-sub" style={{ marginTop: 10 }}>
            {source === "BACKEND" ? (
              "AUTHORITATIVE SESSION ACTIVE · Backed by SQLiteSecurityStore token validation. Revocation destroys the authoritative bearer token."
            ) : (
              "SESSION PREVIEW · DEV SAMPLE — sample session metadata, non-authoritative. Production session enforcement not yet wired; if session data were unavailable this screen would report SESSION DATA UNAVAILABLE rather than display fake healthy state."
            )}
          </div>
        </Panel>
      </div>

      {/* Explicit preview-status toast — no dead controls, no fake revocation/enrollment */}
      {statusNote && (
        <div
          id="security-status-note"
          role="status"
          aria-live="polite"
          style={{
            position: "fixed", bottom: 18, right: 18, zIndex: 60, maxWidth: 360,
            background: "var(--v3-surface-2)", border: "1px solid var(--v3-line)", borderRadius: 10,
            padding: "10px 14px", fontSize: 12.5, color: "var(--v3-ink)", boxShadow: "0 8px 24px rgba(0,0,0,0.25)",
          }}
        >
          <Dot tone="warn" /> {statusNote}
        </div>
      )}
    </>
  );
};

/* ════════════════════════════════════════════════════════════
   9. ACCOUNT & IDENTITY — ACCOUNT PREVIEW · DEV SAMPLE
   Truth state: DEV SAMPLE. Production account/profile persistence
   is not yet fully wired. All operator profile data is simulated
   sample metadata. Strict Owner / User separation: normal USER
   cannot self-promote, change role, or bypass invite-only governance.
   No raw passwords, API keys, or tokens are exposed. All actions
   communicate explicit preview / not-wired feedback with zero dead controls.
   ============================================================ */
export const AccountScreen: React.FC<{ isUnavailable?: boolean }> = ({ isUnavailable = false }) => {
  const [statusNote, setStatusNote] = useState<string | null>(null);
  const [profileData, setProfileData] = useState<UserProfileData | null>(null);
  const [source, setSource] = useState<"BACKEND" | "SAMPLE">("SAMPLE");

  useEffect(() => {
    let active = true;
    queryCurrentUserProfile().then((res) => {
      if (active && res.data) {
        setProfileData(res.data);
        setSource(res.source === "BACKEND" ? "BACKEND" : "SAMPLE");
      }
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!statusNote) return;
    const t = window.setTimeout(() => setStatusNote(null), 5000);
    return () => window.clearTimeout(t);
  }, [statusNote]);

  // Check URL query param or hash ?unavailable=account for testing fail-closed handling
  const checkUnavailable =
    (Boolean(productRuntimeMode()) && !profileData) ||
    isUnavailable ||
    (typeof window !== "undefined" &&
      (new URLSearchParams(window.location.search).get("unavailable") === "account" ||
        window.location.hash.includes("unavailable=account")));

  if (checkUnavailable) {
    return (
      <>
        <div className="v3-screen-head">
          <div>
            <h2 className="v3-screen-title">Account &amp; Identity</h2>
            <p className="v3-screen-sub">Operator profile, invite-only access model, governed role permissions</p>
          </div>
          <TruthChip kind="SAMPLE" title="ACCOUNT DATA UNAVAILABLE" />
        </div>
        <div className="v3-panel v3-sp12" id="account-unavailable-state" style={{ padding: 24, textAlign: "center" }}>
          <div style={{ fontWeight: 700, fontSize: 16, color: "var(--v3-neg)", marginBottom: 8 }}>
            ACCOUNT DATA UNAVAILABLE
          </div>
          <p className="v3-row-sub" style={{ maxWidth: 520, margin: "0 auto" }}>
            Unable to retrieve account or operator profile from backend service. Fail-closed: No fake production data is populated.
          </p>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="v3-screen-head">
        <div>
          <h2 className="v3-screen-title">Account &amp; Identity</h2>
          <p className="v3-screen-sub">Operator profile, invite-only access model, governed role permissions</p>
        </div>
        <TruthChip
          kind={source === "BACKEND" ? "REAL" : "SAMPLE"}
          title={source === "BACKEND" ? "Authoritative operator profile and service entitlement verified from AlgoFortis backend." : "ACCOUNT PREVIEW · DEV SAMPLE — Production account/profile persistence is not yet fully wired."}
        />
      </div>

      {source === "BACKEND" ? (
        <div className="security-notice-box" style={{ marginBottom: 14 }}>
          <span className="sec-notice-icon">🛡</span>
          <span>
            <strong>Authoritative Session Connected:</strong> Verified session for <code>{profileData?.sx_id}</code> ({profileData?.role}). Service status: <code>{profileData?.service_status}</code>. Workspace role permissions enforced by backend security store.
          </span>
        </div>
      ) : (
        <div className="dev-preview-banner" style={{ marginBottom: 14 }}>
          <span className="banner-tag">ACCOUNT PREVIEW</span>
          <span>
            DEV SAMPLE · Production account/profile persistence is not yet fully wired ·
            Sample operator metadata · Invite-only access model · Owner governance enforced ·
            API access not wired in this V1 preview.
          </span>
        </div>
      )}

      <div className="v3-grid">
        <Panel
          label="Operator Identity &amp; Profile"
          meta={source === "BACKEND" ? `AUTHORITATIVE · ${profileData?.sx_id || "SX-0009-ALPHA"}` : `DEV SAMPLE · ${profileData?.sx_id || "SX-0009-ALPHA"}`}
          className="v3-sp6"
          id="account-operator-panel"
        >
          <dl style={{ margin: 0 }}>
            <KV k="Operator Name" v={profileData?.display_name || "Alexander Vance"} />
            <KV k="Account ID" v={profileData?.sx_id || "SX-0009-ALPHA"} />
            <KV k="Email Address" v={profileData ? `${profileData.namespace || "user"}@algofortis.internal` : "alexander.v@quantfund.internal"} />
            <KV k="Account Role" v={profileData?.role === "OWNER" ? "Owner (OWNER)" : "Standard User (USER)"} />
            <KV k="Access Plan" v={profileData?.service_term_type ? `AlgoFortis ${profileData.service_term_type.replace(/_/g, " ")}` : "AlgoFortis V1 Access"} vClass="v3-profit-text" />
            <KV k="Account Status" v={profileData ? `${profileData.account_status || profileData.lifecycle} ${source === "BACKEND" ? "· AUTHORITATIVE" : "· DEV SAMPLE"}` : "ACTIVE · DEV SAMPLE"} />
            <KV k="Access Model" v={profileData ? `Invite-Only (${profileData.activation_status || "REDEEMED"} → ${profileData.account_status || "ACTIVE"})` : "Invite-Only (INVITED → REDEEMED → ACTIVE)"} />
            <KV k="Service Entitlement" v={profileData?.service_status ? `${profileData.service_status}${profileData.service_expires_at ? ` (Expires: ${new Date(profileData.service_expires_at).toISOString().slice(0, 10)})` : ""}` : "ACTIVE (DEV SAMPLE)"} vClass="v3-profit-text" />
            <KV k="Authentication Method" v="Authoritative FIDO2 / WebAuthn Passkey" />
            <KV k="Created Date" v={profileData?.service_started_at ? new Date(profileData.service_started_at).toISOString().slice(0, 10) : "2026-08-30 (DEV SAMPLE)"} />
          </dl>
          <div className="v3-row-sub" style={{ marginTop: 10 }}>
            {source === "BACKEND"
              ? "AUTHORITATIVE SESSION — Operator profile projected from backend security store and active session token."
              : "ACCOUNT PREVIEW · DEV SAMPLE — Sample operator identity. No KYC verification, broker verification, or production profile persistence is performed or implied."}
          </div>
        </Panel>

        <Panel label="Workspace Governance &amp; Permissions" meta="Role: Standard User (USER)" className="v3-sp6" id="account-permissions-panel">
          <dl style={{ margin: 0 }}>
            <KV k="Role Authorization" v="Standard User (USER)" />
            <KV k="Role Self-Promotion" v="Disabled · User cannot self-promote or alter role" />
            <KV k="Live Promotion Authority" v="Governed Promotion Only (Owner sign-off required · User cannot self-promote)" />
            <KV k="Strategy Development" v="Backtesting & Paper Simulation" vClass="v3-profit-text" />
            <KV k="Order Execution" v="Paper Simulation Only (Governed Live Preview)" />
            <KV k="Broker Connector Access" v="DEV PREVIEW · Mock Connectors (API access not wired in this V1 preview)" />
            <KV k="Audit Trail Access" v="Read-Only System Audit" />
            <KV k="Owner / Admin Controls" v="Separation Enforced · Normal USER cannot access Owner Console" />
          </dl>
          <div className="v3-row-sub" style={{ marginTop: 10 }}>
            GOVERNANCE INVARIANT — Strict Owner / User separation. Normal users cannot alter access permissions, grant owner privileges, or bypass invite-only registration.
          </div>
        </Panel>

        <Panel label="Account Management &amp; Actions" meta="Preview Operations" className="v3-sp12" id="account-actions-panel">
          <div style={{ padding: "8px 10px", background: "var(--v3-surface-2)", borderRadius: 8, fontSize: 11.5, color: "var(--v3-ink-3)", marginBottom: 12, lineHeight: 1.4 }}>
            <Dot tone="dim" /> Account actions in this V1 preview communicate truthful state without fake mutations or silent no-ops. Production account-management backend is not yet fully wired.
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
            <button
              className="v3-btn ghost mini"
              id="account-edit-profile-btn"
              aria-label="Edit Profile — profile editing is not wired in this V1 preview"
              onClick={() => setStatusNote("Profile editing is not wired in this V1 preview.")}
            >
              <Icon name="users" size={13} style={{ marginRight: 5 }} /> Edit Profile
            </button>
            <button
              className="v3-btn ghost mini"
              id="account-change-email-btn"
              aria-label="Change Email — email modification is not wired in this V1 preview"
              onClick={() => setStatusNote("Email modification is not wired in this V1 preview.")}
            >
              <Icon name="file" size={13} style={{ marginRight: 5 }} /> Change Email
            </button>
            <button
              className="v3-btn ghost mini"
              id="account-manage-api-btn"
              aria-label="Manage API Access — API access is not wired in this V1 preview"
              onClick={() => setStatusNote("API access not wired in this V1 preview.")}
            >
              <Icon name="plug" size={13} style={{ marginRight: 5 }} /> Manage API Access
            </button>
            <button
              className="v3-btn ghost mini"
              id="account-request-live-btn"
              aria-label="Request Live Promotion — Governed Promotion Only: Owner sign-off required"
              onClick={() => setStatusNote("Governed Promotion Only — Owner sign-off required. User cannot self-promote to live execution.")}
            >
              <Icon name="shield" size={13} style={{ marginRight: 5 }} /> Request Live Promotion
            </button>
            <button
              className="v3-btn ghost mini"
              id="account-export-data-btn"
              aria-label="Export Account Digest — data export is not wired in this V1 preview"
              onClick={() => setStatusNote("Account data export is not wired in this V1 preview.")}
            >
              <Icon name="chart" size={13} style={{ marginRight: 5 }} /> Export Account Digest
            </button>
            <button
              className="v3-btn danger mini"
              id="account-deactivate-btn"
              aria-label="Deactivate Account — account deactivation is not wired in this V1 preview"
              onClick={() => setStatusNote("Account deactivation is not wired in this V1 preview.")}
            >
              <Icon name="close" size={13} style={{ marginRight: 5 }} /> Deactivate Account
            </button>
          </div>
        </Panel>

        <Panel label="System State &amp; Failure Invariants" meta="Fail-Closed Architecture" className="v3-sp12" id="account-invariants-panel">
          <div className="v3-row-sub" style={{ lineHeight: 1.6 }}>
            <div>• <strong>Production Account Persistence:</strong> Not yet fully wired in this V1 prototype.</div>
            <div>• <strong>Invite-Only Access Model:</strong> Enforced through OWNER token issuance (INVITED → REDEEMED → ACTIVE). Public registration is disabled.</div>
            <div>• <strong>Credential &amp; Secret Protection:</strong> No raw passwords, API keys, tokens, or private secrets are displayed or stored in unencrypted form.</div>
            <div>• <strong>Unavailable State Policy:</strong> If account or profile services are unreachable, this workstation displays <code>ACCOUNT DATA UNAVAILABLE</code> rather than populating simulated healthy production claims.</div>
          </div>
        </Panel>
      </div>

      {/* Explicit preview-status toast — no dead controls, accessible status announcement */}
      {statusNote && (
        <div
          id="account-status-note"
          role="status"
          aria-live="polite"
          style={{
            position: "fixed", bottom: 18, right: 18, zIndex: 60, maxWidth: 380,
            background: "var(--v3-surface-2)", border: "1px solid var(--v3-line)", borderRadius: 10,
            padding: "10px 14px", fontSize: 12.5, color: "var(--v3-ink)", boxShadow: "0 8px 24px rgba(0,0,0,0.25)",
          }}
        >
          <Dot tone="warn" /> {statusNote}
        </div>
      )}
    </>
  );
};

/* ════════════════════════════════════════════════════════════
   10. HELP & DOCUMENTATION — LOCAL V1 DOCUMENTATION PREVIEW
   Truth state: DEV SAMPLE / PREVIEW. Static in-app reference runbooks.
   Zero external dependencies. Covers all 16 verified V1 workflows,
   Global Option Strike Policy, Paper/Backtest/Live isolation,
   deterministic risk governance, and actionable troubleshooting runbooks.
   All interactive buttons open detailed in-app guidance drawers.
   ============================================================ */

export interface HelpTopic {
  id: string;
  number: number;
  title: string;
  category: "CORE ARCHITECTURE" | "WORKFLOWS" | "POLICIES & ISOLATION" | "TROUBLESHOOTING";
  icon: IconName;
  summary: string;
  keyPoints: string[];
  details: {
    heading: string;
    body: string;
  }[];
  codeSnippet?: string;
  invariant?: string;
}

export const V1_HELP_TOPICS: HelpTopic[] = [
  {
    id: "access",
    number: 1,
    title: "Access Gate & Secure Entry",
    category: "CORE ARCHITECTURE",
    icon: "shield",
    summary: "Invite-only access model, owner-issued token validation, single-use redemption, session management.",
    keyPoints: [
      "Strictly invite-only model — public registration is disabled",
      "4-Stage Gate: Token Verification → Identity Match → Security Ceremony → Workspace Admission",
      "One-time token transition: INVITED → REDEEMED → ACTIVE",
      "Expired or invalid tokens fail closed with zero identity leakage",
    ],
    details: [
      {
        heading: "Invite-Only Token Provisioning",
        body: "Access to AlgoFortis is restricted exclusively to authorized operators provisioned by the Owner. Each token is cryptographically generated with the format SX-XXXX-XXXX and bound to a specific email/phone reference.",
      },
      {
        heading: "Token Lifecycle & Fail-Closed Gate",
        body: "Tokens can only be redeemed once. Upon successful activation, the access record transitions to ACTIVE status. Attempts to reuse or brute-force expired tokens result in silent fail-closed rejection.",
      },
    ],
    invariant: "Fail-Closed Access Gate — No anonymous or public registration exists in AlgoFortis V1.",
  },
  {
    id: "overview",
    number: 2,
    title: "Workstation Overview & Navigation",
    category: "WORKFLOWS",
    icon: "home",
    summary: "Layered card navigation, live real-time wall clock, quick strategy actions, dual-theme support.",
    keyPoints: [
      "Deterministic left-rail navigation with fixed 20px icon column and 0 horizontal jitter",
      "Live IST wall-clock synchronized per-second with background sleep recovery",
      "Quick action mode selectors: Open, Backtest, Paper, and Governed Live",
      "High-contrast dual-theme tokens (--v3-*) for Dark and Light environments",
    ],
    details: [
      {
        heading: "Workstation Navigation Hierarchy",
        body: "The workstation is organized into 4 primary functional regions: WORKSPACE (Overview, Strategies, Strategy Execution, Connections), VERIFICATION (Backtesting, Paper Trading), OPERATIONS (Portfolio, Orders, Reports), and SYSTEM (Security, Account, Help & Docs).",
      },
      {
        heading: "Truth Classification Badges",
        body: "Every visible dashboard region carries a fail-closed TruthChip: REAL + WORKING for active contracts, DEV PREVIEW / SAMPLE for prototype simulations, and DISABLED / UNAVAILABLE for unwired controls.",
      },
    ],
  },
  {
    id: "strategies",
    number: 3,
    title: "Strategies Fleet & BaseStrategy",
    category: "WORKFLOWS",
    icon: "code",
    summary: "Python strategy definition, BaseStrategy callback lifecycle, 5-stage promotion pipeline.",
    keyPoints: [
      "Inherit from algofortis.strategy.BaseStrategy for deterministic execution",
      "Core lifecycle callbacks: on_tick(), on_bar(), on_order_status(), and on_risk_halt()",
      "Strict 5-stage promotion chain from Draft to Live Readiness",
      "Runtime memory and frequency quotas enforced by execution supervisor",
    ],
    details: [
      {
        heading: "BaseStrategy Interface Contract",
        body: "Strategies subclass BaseStrategy and register event listeners for market ticks and candle completions. All order generation calls are checked against pre-trade risk envelopes before transmission.",
      },
      {
        heading: "5-Stage Governance Lifecycle",
        body: "Strategies advance sequentially: 1. Static AST Scan → 2. Conformance Verification → 3. Backtest Evidence Generation → 4. Paper Forward Evaluation → 5. Explicit LIVE_ELIGIBLE Owner Sign-Off.",
      },
    ],
    codeSnippet: `from algofortis.strategy import BaseStrategy, Signal

class MomentumBreakout(BaseStrategy):
    def on_tick(self, tick):
        if tick.price > self.upper_barrier and not self.has_position:
            return Signal.buy(symbol="NIFTY26AUG22500CE", qty=50)
        return None`,
    invariant: "Deterministic Promotion — No strategy can bypass the 5-stage governance sequence.",
  },
  {
    id: "strike-policy",
    number: 4,
    title: "Global Option Strike Policy",
    category: "POLICIES & ISOLATION",
    icon: "puzzle",
    summary: "Owner-frozen global strike selection rule: ATM (0 distance) vs OTM/ITM (1–4 strikes), universal application.",
    keyPoints: [
      "Global workstation-wide rule — applies universally to all strategies and backtests",
      "Mode ATM (At-The-Money): Distance is strictly forced to 0 strikes",
      "Mode OTM (Out-of-The-Money): Distance must be an integer between 1 and 4 strikes",
      "Mode ITM (In-The-Money): Distance must be an integer between 1 and 4 strikes",
      "Zero per-strategy overrides — no local strategy instance can deviate from global policy",
    ],
    details: [
      {
        heading: "Frozen Policy Rules",
        body: "The Global Option Strike Policy is locked by Owner architecture decisions: 1. Mode can be ATM, OTM, or ITM; 2. Distance range is 0 to 4 strikes; 3. ATM mode strictly forces distance to 0; 4. OTM and ITM modes require distance between 1 and 4; 5. Policy is global and overrides all local strategy settings.",
      },
      {
        heading: "Option Chain Resolution",
        body: "When a strategy generates an option trade signal, the execution engine maps the underlying spot price (e.g. NIFTY 22,514.80) to the nearest strike step (50 pts) and selects the exact strike corresponding to the global policy.",
      },
    ],
    invariant: "Universal Strike Lock — ATM = 0 distance; OTM/ITM = 1–4 distance. No per-strategy overrides.",
  },
  {
    id: "strategy-execution",
    number: 5,
    title: "Strategy Execution & Live Readiness",
    category: "WORKFLOWS",
    icon: "trade",
    summary: "Live-side monitoring, position tracker, market options desk, governed promotion readiness.",
    keyPoints: [
      "Live-side monitoring with real-time contract leg resolution (monitoring and readiness only in V1)",
      "Opening exposure = BUY; closing existing long option = SELL TO CLOSE",
      "Short / naked option selling is strictly disabled in V1",
      "Governed Live Readiness workspace with mandatory Owner sign-off (no real-money user execution controls in V1)",
      "Emergency Flatten / manual trade interventions are unavailable in V1 user workspace",
    ],
    details: [
      {
        heading: "Option Desk Monitoring & Readiness",
        body: "The execution desk displays live option legs, entry/current premium prices, contract quantities, and position return percentages. In V1, the live-side operates strictly in monitoring and readiness mode; user-operational real-money trade routing is not enabled.",
      },
      {
        heading: "Live Readiness Governance",
        body: "Viewing 'LIVE' surfaces the Governed Live Readiness workspace. Activating live execution requires formal Owner sign-off and backend clearance; normal operators cannot activate live trade dispatch.",
      },
    ],
  },
  {
    id: "connections",
    number: 6,
    title: "Broker Connectors & API Gateways",
    category: "WORKFLOWS",
    icon: "plug",
    summary: "Angel One, Zerodha broker connectors; sealed credentials; simulated connection tests; telemetry states.",
    keyPoints: [
      "Multi-broker connectivity support (Angel One SmartAPI, Zerodha Kite Connect)",
      "Sealed credential references — raw API keys, secrets, and tokens are never shown",
      "Connection telemetry: FRESH, STALE, or UNKNOWN based on data-freshness policy",
      "Simulated connection handshakes in V1 prototype preview",
    ],
    details: [
      {
        heading: "Broker Connector Architecture",
        body: "Connectors handle market tick ingestion and order routing. In the V1 preview, connection tests execute simulated latency handshakes (DEV PREVIEW · Mock Handshake).",
      },
      {
        heading: "Fail-Closed Stale Telemetry",
        body: "If market tick telemetry exceeds the staleness threshold defined by the active connection/data-freshness policy without heartbeat confirmation, the connector status transitions to STALE and order dispatch is paused.",
      },
    ],
  },
  {
    id: "backtesting",
    number: 7,
    title: "Backtesting Engine & Historical Replay",
    category: "WORKFLOWS",
    icon: "play",
    summary: "Historical replay simulation, market calendar alignment, quality scoring, zero lookahead.",
    keyPoints: [
      "High-precision historical bar and tick replay with verified zero lookahead bias",
      "Structured promotion evidence digests generated for promotion audit",
      "Historical market calendar alignment across derivative trading sessions",
      "Deterministic Quality Score (0–100) evaluating risk-adjusted metrics",
    ],
    details: [
      {
        heading: "Simulation Accuracy & Slippage",
        body: "The backtest engine applies spread models and conservative execution slippage across historical data partitions to eliminate optimistic curve fitting.",
      },
      {
        heading: "Quality Scoring & Promotion Evidence",
        body: "Quality Score evaluates trade sample size, profit factor, win rate, expectancy, and max drawdown. Qualifying backtests generate structured promotion evidence records required before paper evaluation.",
      },
    ],
  },
  {
    id: "paper-trading",
    number: 8,
    title: "Paper Trading Desk & Forward Simulation",
    category: "WORKFLOWS",
    icon: "layers",
    summary: "Virtual forward simulation, customizable starting capital presets, 9 KPI cards, ledger continuity.",
    keyPoints: [
      "Virtual forward simulation; market-feed authority may remain DEV PREVIEW / SAMPLE until live feed wiring is complete",
      "Simulated virtual fills without risking real capital or routing live exchange orders",
      "Selectable starting capital presets: ₹5k, ₹10k, ₹50k, ₹100k, ₹500k, or custom balance",
      "Session change and capital reset maintain complete historical ledger continuity",
    ],
    details: [
      {
        heading: "Virtual Forward Simulation Loop",
        body: "Paper trading provides virtual forward simulation. Market-feed authority may remain DEV PREVIEW / SAMPLE until live feed wiring is complete. Fills and execution latencies are simulated locally with zero live broker risk.",
      },
      {
        heading: "Capital Modification & Ledger Integrity",
        body: "Operators can adjust or reset virtual capital balance at any time. All prior executed paper trades remain preserved in the persistent trade journal.",
      },
    ],
  },
  {
    id: "portfolio",
    number: 9,
    title: "Portfolio & Exposure Oversight",
    category: "WORKFLOWS",
    icon: "wallet",
    summary: "Current equity balance, capital committed exposure, margin utilization, live-side monitoring.",
    keyPoints: [
      "Mathematical equity balance: Current Equity = Available Cash + Open Market Value",
      "Capital Committed tracked separately as exposure / entry-cost context (never added twice to equity)",
      "Exposure concentration monitoring across index derivative underlyings",
      "Clean fail-closed state if portfolio calculation telemetry is unavailable",
    ],
    details: [
      {
        heading: "Equity Balance & Capital Accounting",
        body: "Current Equity equals Available Cash plus Open Market Value (marked-to-market value of open positions). Capital Committed represents the cumulative entry cost/margin locked in open positions and is tracked separately for exposure oversight rather than being double-counted in total equity.",
      },
      {
        heading: "Exposure Safety Limits",
        body: "Monitors gross contract exposure and committed capital against pre-configured risk envelope thresholds, alerting operators before margin exhaustion halts execution.",
      },
    ],
  },
  {
    id: "orders",
    number: 10,
    title: "Orders Lifecycle & Blotter",
    category: "WORKFLOWS",
    icon: "file",
    summary: "Live-side order lifecycle monitoring, strategy-driven sources, BUY / SELL TO CLOSE only, realized P&L.",
    keyPoints: [
      "Actual V1 lifecycle states: PENDING, ACCEPTED, OPEN, PARTIALLY FILLED, FILLED, CANCELLED, REJECTED, EXPIRED",
      "Opening exposure = BUY; closing existing long option = SELL TO CLOSE",
      "Short / naked option selling is strictly disabled in V1",
      "Realized P&L calculated strictly for filled SELL TO CLOSE executions",
    ],
    details: [
      {
        heading: "Order Lifecycle States",
        body: "Orders transition through deterministic states: PENDING → ACCEPTED → OPEN → PARTIALLY FILLED → FILLED, or terminate as CANCELLED, REJECTED, or EXPIRED. Opening exposure is strictly BUY; closing existing long options is strictly SELL TO CLOSE.",
      },
      {
        heading: "Order Blotter Oversight & Detail Drawer",
        body: "The Orders blotter provides real-time tracking of all live-side order submissions. Clicking any order opens the Lifecycle Timeline drawer detailing pre-trade risk evaluation checks, contract resolution, fill timestamp, and realized profit/loss.",
      },
    ],
  },
  {
    id: "reports",
    number: 11,
    title: "Reports & Compliance Digests",
    category: "WORKFLOWS",
    icon: "chart",
    summary: "Performance, Trade Ledger, System Audit, and Risk digests with evidence metadata.",
    keyPoints: [
      "4 standardized digest categories: Performance, Trade Ledger, System Audit, Risk Incidents",
      "In-app 'View Evidence' drawer displaying complete metadata and data source scope",
      "Truthful preview state — report export files communicate explicit preview status",
      "Zero unsupported regulatory certification or cryptographic verification claims",
    ],
    details: [
      {
        heading: "Digest Inspection Workflow",
        body: "Operators can inspect report digest metadata (period covered, generated timestamp, format, estimated size, evidence scope) directly in the workstation.",
      },
      {
        heading: "Export State Transparency",
        body: "Because production report generation is a preview feature in V1, clicking export controls displays a truthful toast informing the operator of preview status.",
      },
    ],
  },
  {
    id: "security",
    number: 12,
    title: "Security & Session Protection",
    category: "CORE ARCHITECTURE",
    icon: "lock",
    summary: "Standard session security, optional WebAuthn passkeys, authorized device tracking.",
    keyPoints: [
      "Standard login utilizes secure cookie/session authentication",
      "WebAuthn / FIDO2 passkeys are supported as optional account security factors",
      "Authorized active device session tracking with IP and last active metadata",
      "Fail-closed lockdown if session or authentication services are unreachable",
    ],
    details: [
      {
        heading: "Authentication Factor Architecture",
        body: "AlgoFortis employs session-based authentication for day-to-day operations. Passkeys are an optional hardware-backed layer and are never mandatory for normal workstation access.",
      },
      {
        heading: "Session Monitoring & Revocation",
        body: "The Security desk displays active sessions. In the V1 preview, revocation controls communicate explicit not-wired preview status.",
      },
    ],
  },
  {
    id: "account",
    number: 13,
    title: "Account Profile & Governance Invariants",
    category: "CORE ARCHITECTURE",
    icon: "users",
    summary: "Sample operator identity, AlgoFortis V1 Access tier, USER role, governed promotion restrictions.",
    keyPoints: [
      "Sample operator identity and profile metadata for AlgoFortis V1 Access",
      "Standardized plan taxonomy: AlgoFortis V1 Access",
      "Governed role authorization: Standard User (USER) with zero self-promotion controls",
      "Preview actions (Edit Profile, Change Email, Manage API) communicate non-dead preview feedback",
    ],
    details: [
      {
        heading: "Operator Profile & Plan Taxonomy",
        body: "Displays sample operator identity metadata under the unified AlgoFortis V1 Access plan tier. Account status reflects active prototype session state with zero unpersisted mutations.",
      },
      {
        heading: "Operator Role Boundaries & Governance",
        body: "Standard USER accounts have access to strategy development, backtesting, paper trading, and portfolio monitoring. Normal users cannot self-promote, change role, or access Owner console surfaces.",
      },
      {
        heading: "Fail-Closed Account State",
        body: "If account or profile backend services are unavailable, the workstation renders ACCOUNT DATA UNAVAILABLE rather than populating simulated healthy production data.",
      },
    ],
  },
  {
    id: "risk-governance",
    number: 14,
    title: "Deterministic Risk Authority & Governance",
    category: "POLICIES & ISOLATION",
    icon: "shield",
    summary: "Pre-trade risk envelopes, fail-closed halts, audit journaling.",
    keyPoints: [
      "Deterministic pre-trade risk evaluation on 100% of order signals",
      "Immutable append-only audit journal logging every risk event and decision",
      "Instant risk halts: Max Daily Drawdown, Max Order Size, Margin Limit breaches",
      "AI agents do not control risk in V1 — Agents are reserved for V2 only",
    ],
    details: [
      {
        heading: "Pre-Trade Risk Envelopes",
        body: "Every trade signal generated by an algorithm is validated against deterministic risk checks before broker transmission. Violations immediately reject the order.",
      },
      {
        heading: "Emergency Risk Halt Protocols",
        body: "If market volatility causes portfolio loss to approach the hard daily loss threshold, the risk supervisor triggers immediate strategy suspension and fail-closed halt.",
      },
    ],
    invariant: "Deterministic Risk Authority — Pre-trade risk envelope checks are mandatory and immutable.",
  },
  {
    id: "isolation",
    number: 15,
    title: "Paper / Backtest / Live Domain Isolation",
    category: "POLICIES & ISOLATION",
    icon: "layers",
    summary: "Strict boundary separation: Backtest historical, Paper virtual, Live monitoring; zero cross-domain state bleed.",
    keyPoints: [
      "Backtesting domain operates strictly on historical archives (zero forward impact)",
      "Paper Trading domain operates on virtual accounts with virtual fills (zero broker routing)",
      "Live Execution domain provides live-side monitoring and governed readiness",
      "Zero State Bleed: Resetting paper trading never alters live holdings or backtest evidence",
      "No real-money live order execution is active in this V1 preview",
    ],
    details: [
      {
        heading: "Domain Boundary Guarantees",
        body: "The AlgoFortis architecture strictly isolates state storage between testing and operations: 1. Backtests use immutable historical partitions; 2. Paper trading maintains an isolated virtual ledger; 3. Live monitoring reflects broker connection telemetry.",
      },
      {
        heading: "Zero State Bleed Invariant",
        body: "Modifying paper starting capital, simulating paper drawdowns, or executing virtual orders has zero effect on the live portfolio or historical backtest logs.",
      },
    ],
    invariant: "Domain Isolation — Backtest, Paper, and Live domains maintain strictly separated state stores.",
  },
  {
    id: "troubleshooting",
    number: 16,
    title: "Troubleshooting & Operational Runbook",
    category: "TROUBLESHOOTING",
    icon: "help",
    summary: "Actionable solutions for rejected access tokens, stale connections, risk envelope halts, and unwired preview actions.",
    keyPoints: [
      "Access ID Rejected: Verify token format (SX-XXXX-XXXX) and check if already redeemed",
      "Connection State Stale / Unknown: Re-run simulated connection test or verify broker API feed",
      "Backtest Insufficient Data: Adjust date range to cover full lookback period",
      "Paper Session Fail-Closed: Drawdown reached virtual risk limit; review logs or reset capital",
      "Orders Rejected: Inspect error details in Order Lifecycle Drawer for pre-trade risk rule hit",
      "Report / Action Unwired: Production backend is preview-only in V1; metadata displayed in-app",
    ],
    details: [
      {
        heading: "1. Access ID Rejected on Secure Entry",
        body: "Tokens are single-use and case-sensitive (format: SX-XXXX-XXXX). If a token has already been redeemed or revoked by the Owner, the access gate rejects it fail-closed. Contact your workstation Owner for a new invitation token.",
      },
      {
        heading: "2. Broker Connection Shows STALE / UNKNOWN",
        body: "If market tick telemetry exceeds the staleness threshold defined by the active connection/data-freshness policy, connector status transitions to STALE. Re-run simulated connection test on the Connections screen.",
      },
      {
        heading: "3. Backtest Fails with Insufficient Candle History",
        body: "Ensure selected date range provides sufficient trading days for indicators (e.g. 50-period EMA requires at least 50 historical bars). Adjust start date backward to allow warmup period.",
      },
      {
        heading: "4. Paper Trading Session Halted",
        body: "If cumulative simulated loss exceeds the virtual daily loss limit, the paper session halts fail-closed. Open Paper Trading Desk, review the executed blotter, and use 'Reset Session' or 'Change Capital' to restart.",
      },
      {
        heading: "5. Orders Rejected by Risk Supervisor",
        body: "Click on the rejected order in the Orders screen to inspect the Lifecycle Timeline. The drawer displays the exact risk envelope rule triggered (e.g. Max Order Quantity or Strike Restriction).",
      },
      {
        heading: "6. Preview Actions Show 'Not Wired' Status Note",
        body: "Certain administrative actions (Edit Profile, Report File Export, Passkey Enrollment) are intentionally simulated in the V1 prototype. These actions display an accessible preview status note rather than performing fake mutations.",
      },
    ],
  },
];

export const HelpScreen: React.FC = () => {
  const [selectedCategory, setSelectedCategory] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedTopic, setSelectedTopic] = useState<HelpTopic | null>(null);

  const categories = ["ALL", "CORE ARCHITECTURE", "WORKFLOWS", "POLICIES & ISOLATION", "TROUBLESHOOTING"];

  const filteredTopics = useMemo(() => {
    return V1_HELP_TOPICS.filter((t) => {
      const matchCat = selectedCategory === "ALL" || t.category === selectedCategory;
      const q = searchQuery.toLowerCase().trim();
      const matchSearch =
        !q ||
        t.title.toLowerCase().includes(q) ||
        t.summary.toLowerCase().includes(q) ||
        t.keyPoints.some((p) => p.toLowerCase().includes(q)) ||
        t.details.some((d) => d.heading.toLowerCase().includes(q) || d.body.toLowerCase().includes(q));
      return matchCat && matchSearch;
    });
  }, [selectedCategory, searchQuery]);

  return (
    <>
      <div className="v3-screen-head">
        <div>
          <h2 className="v3-screen-title">Help &amp; Strategy Architecture</h2>
          <p className="v3-screen-sub">V1 workflow guides, global option strike policy, domain isolation, error runbooks</p>
        </div>
        <TruthChip kind="SAMPLE" title="HELP & DOCS PREVIEW · DEV SAMPLE — Local in-app documentation reference." />
      </div>

      <div className="dev-preview-banner" style={{ marginBottom: 14 }}>
        <span className="banner-tag">HELP &amp; DOCS PREVIEW</span>
        <span>
          DEV SAMPLE · LOCAL V1 DOCUMENTATION PREVIEW · Static in-app reference runbooks ·
          Zero external documentation dependencies · All topics cover verified V1 workflows ·
          AI / Agents are reserved for V2.
        </span>
      </div>

      {/* Quick Architecture & Runbook Action Highlights */}
      <div className="v3-grid" style={{ marginBottom: 16 }}>
        <div className="v3-panel v3-sp4" id="help-quick-strike-panel">
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <Icon name="puzzle" size={16} />
            <span style={{ fontWeight: 700, fontSize: 13.5, color: "var(--v3-ink)" }}>Global Option Strike Policy</span>
          </div>
          <p className="v3-row-sub" style={{ lineHeight: 1.5, whiteSpace: "normal" }}>
            Frozen global rule: ATM forces 0 distance, OTM/ITM require 1–4 strikes. Applies universally to all strategies with zero per-strategy overrides.
          </p>
          <button
            className="v3-btn ghost mini"
            id="help-quick-strike-btn"
            style={{ marginTop: 10 }}
            onClick={() => setSelectedTopic(V1_HELP_TOPICS.find((t) => t.id === "strike-policy") || null)}
          >
            <Icon name="puzzle" size={12} style={{ marginRight: 5 }} /> View Strike Policy
          </button>
        </div>

        <div className="v3-panel v3-sp4" id="help-quick-isolation-panel">
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <Icon name="layers" size={16} />
            <span style={{ fontWeight: 700, fontSize: 13.5, color: "var(--v3-ink)" }}>Paper / Live Domain Isolation</span>
          </div>
          <p className="v3-row-sub" style={{ lineHeight: 1.5, whiteSpace: "normal" }}>
            Strict boundary isolation: Backtest is historical only, Paper is virtual fills only, Live is monitoring/readiness only. Zero cross-domain state bleed.
          </p>
          <button
            className="v3-btn ghost mini"
            id="help-quick-isolation-btn"
            style={{ marginTop: 10 }}
            onClick={() => setSelectedTopic(V1_HELP_TOPICS.find((t) => t.id === "isolation") || null)}
          >
            <Icon name="layers" size={12} style={{ marginRight: 5 }} /> View Isolation Spec
          </button>
        </div>

        <div className="v3-panel v3-sp4" id="help-quick-trouble-panel">
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <Icon name="help" size={16} />
            <span style={{ fontWeight: 700, fontSize: 13.5, color: "var(--v3-ink)" }}>Troubleshooting &amp; Runbook</span>
          </div>
          <p className="v3-row-sub" style={{ lineHeight: 1.5, whiteSpace: "normal" }}>
            Fast resolution runbook for rejected access tokens, stale connections, risk envelope halts, and unwired preview actions.
          </p>
          <button
            className="v3-btn danger mini"
            id="help-quick-trouble-btn"
            style={{ marginTop: 10 }}
            onClick={() => setSelectedTopic(V1_HELP_TOPICS.find((t) => t.id === "troubleshooting") || null)}
          >
            <Icon name="help" size={12} style={{ marginRight: 5 }} /> Emergency Runbook
          </button>
        </div>
      </div>

      {/* Filter & Search Bar */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 10,
          marginBottom: 14,
          padding: "10px 14px",
          background: "var(--v3-surface-1)",
          border: "1px solid var(--v3-line)",
          borderRadius: 8,
        }}
      >
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
          {categories.map((c) => (
            <button
              key={c}
              className={`v3-btn mini ${selectedCategory === c ? "primary" : "ghost"}`}
              id={`help-cat-${c.toLowerCase().replace(/[^a-z0-9]/g, "-")}`}
              onClick={() => setSelectedCategory(c)}
            >
              {c}
            </button>
          ))}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <input
            type="text"
            id="help-search-input"
            placeholder="Search V1 topics, policies, runbooks..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              background: "var(--v3-surface-2)",
              border: "1px solid var(--v3-line)",
              color: "var(--v3-ink)",
              padding: "6px 10px",
              borderRadius: 6,
              fontSize: 12,
              minWidth: 220,
            }}
          />
          {searchQuery && (
            <button className="v3-btn ghost mini" onClick={() => setSearchQuery("")}>
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Topics Grid */}
      <div className="v3-grid" id="help-topics-grid">
        {filteredTopics.map((topic) => (
          <div className="v3-panel v3-sp4" key={topic.id} id={`help-card-${topic.id}`}>
            <div className="v3-panel-head" style={{ marginBottom: 6 }}>
              <span style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 700, fontSize: 13 }}>
                <Icon name={topic.icon} size={15} />
                <span>{topic.title}</span>
              </span>
              <span className="v3-itm-badge" style={{ fontSize: 9.5 }}>{topic.category}</span>
            </div>

            <p className="v3-row-sub" style={{ lineHeight: 1.45, minHeight: 38, marginBottom: 10, whiteSpace: "normal" }}>
              {topic.summary}
            </p>

            <div style={{ fontSize: 11, color: "var(--v3-ink-3)", marginBottom: 12, lineHeight: 1.4 }}>
              <ul style={{ margin: 0, paddingLeft: 16 }}>
                {topic.keyPoints.slice(0, 2).map((kp, idx) => (
                  <li key={idx} style={{ marginBottom: 3 }}>{kp}</li>
                ))}
              </ul>
            </div>

            <button
              className="v3-btn ghost mini"
              id={`help-open-${topic.id}`}
              aria-label={`Open Guide: ${topic.title}`}
              style={{ width: "100%", justifyContent: "center" }}
              onClick={() => setSelectedTopic(topic)}
            >
              Open Guide <Icon name="chevron" size={12} style={{ marginLeft: 4 }} />
            </button>
          </div>
        ))}
      </div>

      {filteredTopics.length === 0 && (
        <div className="v3-panel v3-sp12" style={{ padding: 24, textAlign: "center" }}>
          <div style={{ fontWeight: 700, fontSize: 14, color: "var(--v3-ink-3)", marginBottom: 6 }}>
            No matching topics found for "{searchQuery}"
          </div>
          <button className="v3-btn ghost mini" onClick={() => { setSearchQuery(""); setSelectedCategory("ALL"); }}>
            Reset Filters
          </button>
        </div>
      )}

      {/* In-App Topic Detail Drawer — Zero dead buttons, comprehensive local documentation */}
      {selectedTopic && (
        <Drawer
          open={!!selectedTopic}
          title={selectedTopic.title}
          sub={selectedTopic.summary}
          onClose={() => setSelectedTopic(null)}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
            <span className="v3-itm-badge">{selectedTopic.category}</span>
            <span className="v3-mono v3-dim" style={{ fontSize: 11 }}>TOPIC #{selectedTopic.number}</span>
          </div>

          <div style={{ marginBottom: 14 }}>
            <div style={{ fontWeight: 700, fontSize: 12.5, color: "var(--v3-ink)", marginBottom: 6 }}>
              Key Principles &amp; Invariants:
            </div>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, lineHeight: 1.5, color: "var(--v3-ink-2)" }}>
              {selectedTopic.keyPoints.map((kp, idx) => (
                <li key={idx} style={{ marginBottom: 4 }}>{kp}</li>
              ))}
            </ul>
          </div>

          {selectedTopic.details.map((det, idx) => (
            <div key={idx} style={{ marginBottom: 14, padding: "10px 12px", background: "var(--v3-surface-2)", borderRadius: 8, border: "1px solid var(--v3-line)" }}>
              <div style={{ fontWeight: 700, fontSize: 12.5, color: "var(--v3-ink)", marginBottom: 4 }}>
                {det.heading}
              </div>
              <div className="v3-row-sub" style={{ lineHeight: 1.5, fontSize: 11.5, color: "var(--v3-ink-2)", whiteSpace: "normal" }}>
                {det.body}
              </div>
            </div>
          ))}

          {selectedTopic.codeSnippet && (
            <div style={{ marginBottom: 14 }}>
              <div style={{ fontWeight: 700, fontSize: 12, color: "var(--v3-ink)", marginBottom: 4 }}>
                Code Reference:
              </div>
              <pre
                style={{
                  background: "var(--v3-canvas-deep)",
                  border: "1px solid var(--v3-line)",
                  borderRadius: 6,
                  padding: "10px 12px",
                  fontSize: 11.5,
                  fontFamily: "var(--v3-mono)",
                  color: "var(--v3-profit-text)",
                  overflowX: "auto",
                  lineHeight: 1.4,
                  margin: 0,
                }}
              >
                {selectedTopic.codeSnippet}
              </pre>
            </div>
          )}

          {selectedTopic.invariant && (
            <div style={{ padding: "10px 12px", background: "var(--v3-profit-bg)", border: "1px solid var(--v3-profit-glow)", borderRadius: 8, fontSize: 11.5, color: "var(--v3-profit-text)", marginBottom: 14 }}>
              <Dot tone="ok" /> <strong>INVARIANT:</strong> {selectedTopic.invariant}
            </div>
          )}

          <div style={{ marginTop: 18, paddingTop: 12, borderTop: "1px solid var(--v3-line)", display: "flex", justifyContent: "flex-end" }}>
            <button className="v3-btn ghost mini" id="help-drawer-close-btn" onClick={() => setSelectedTopic(null)}>
              Close Guide
            </button>
          </div>
        </Drawer>
      )}
    </>
  );
};

/* ── Mobile More Drawer Secondary Sheet ── */
export interface MoreItem { id: string; label: string; icon: IconName; desc: string; }

export const MORE_USER_ITEMS: MoreItem[] = [
  { id: "backtest", label: "Backtesting", icon: "layers", desc: "Quantitative backtest engine" },
  { id: "paper", label: "Paper Trading", icon: "file", desc: "Forward simulation loop" },
  { id: "portfolio", label: "Portfolio", icon: "wallet", desc: "Holdings & NAV breakdown" },
  { id: "orders", label: "Orders", icon: "trade", desc: "Execution blotter" },
  { id: "reports", label: "Reports", icon: "chart", desc: "Tax & audit digests" },
  { id: "security", label: "Security", icon: "lock", desc: "WebAuthn & sessions" },
  { id: "account", label: "Account", icon: "users", desc: "Operator identity" },
  { id: "help", label: "Help", icon: "help", desc: "Documentation & runbooks" },
];

export const MORE_OWNER_ITEMS: MoreItem[] = [
  { id: "control", label: "Overview", icon: "home", desc: "Owner operational summary" },
  { id: "users", label: "Users Oversight", icon: "users", desc: "User management & inspection" },
  { id: "access-registry", label: "Access Registry", icon: "shield", desc: "Invite-only access IDs" },
  { id: "strategies", label: "Strategies", icon: "code", desc: "Strategy fleet governance" },
  { id: "plugins", label: "Plugins & Connectors", icon: "plug", desc: "Broker connection fleet" },
  // V2_ONLY_AGENTS: Agents entry removed from V1 owner mobile More sheet.
  { id: "backtests", label: "Backtests Oversight", icon: "play", desc: "Multi-user backtest logs" },
  { id: "paper", label: "Paper Sessions", icon: "layers", desc: "Active paper trading fleet" },
  { id: "portfolio-oversight", label: "Portfolio & Orders", icon: "chart", desc: "Fleet margin & exposure" },
  { id: "reports", label: "Reports", icon: "file", desc: "Compliance & tax archives" },
  { id: "system", label: "System Health", icon: "activity", desc: "Subsystem health & metrics" },
  { id: "security", label: "Security Authority", icon: "shield", desc: "Policies & session limits" },
];

export const MORE_ITEMS = MORE_USER_ITEMS;

export const MoreSheet: React.FC<{
  isMobile?: boolean;
  workspace?: "user" | "owner";
  currentScreen?: string;
  onOpen: (id: string) => void;
  onClose: () => void;
}> = ({ workspace = "user", currentScreen, onOpen, onClose }) => {
  const items = workspace === "owner" ? MORE_OWNER_ITEMS : MORE_USER_ITEMS;

  return (
    <>
      <button className="v3-backdrop" aria-label="Close More menu" onClick={onClose} />
      <div className="v3-more-mobile-sheet" role="dialog" aria-modal="true" aria-label="More Destinations">
        <div className="v3-drawer-head" style={{ padding: "0 0 10px", borderBottom: "1px solid var(--v3-line)" }}>
          <h3 className="v3-drawer-title" style={{ fontSize: 15 }}>
            {workspace === "owner" ? "Owner Control Navigation" : "More Tools"}
          </h3>
          <button className="v3-btn ghost mini" onClick={onClose}><Icon name="close" size={14} /></button>
        </div>
        <div className="v3-more-mobile-grid">
          {items.map((m) => (
            <button
              key={m.id}
              className={`v3-more-mobile-item ${currentScreen === m.id ? "active" : ""}`}
              onClick={() => { onOpen(m.id); onClose(); }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                <Icon name={m.icon} size={15} />
                <span>{m.label}</span>
              </div>
              <span className="v3-row-sub" style={{ marginTop: 2, fontSize: 10 }}>{m.desc}</span>
            </button>
          ))}
        </div>
      </div>
    </>
  );
};

