import React, { useState, useMemo, useRef, useEffect } from "react";
import { Icon } from "../../shared/icons/V3Icons";
import { Panel, Drawer, KV, TruthChip, Dot } from "../../shared/utilities/V3Chrome";
import {
  getStoredOwnerStrategies,
  updateOwnerSandboxAllowance,
  suspendStrategy,
  restoreStrategy,
  computeEffectiveEligibility,
  getStrategyGovernance,
  type StrategyRow,
  type StrategyConformance,
  type StrategyAdminStatus,
  type OwnerAllowanceStatus,
} from "../../sampleData";
import {
  queryOwnerStrategies,
  updateBackendStrategyAllowance,
  updateBackendStrategyVisibility,
  suspendBackendStrategy,
  restoreBackendStrategy,
  queryPendingPromotions,
  approveStrategyPromotion,
  type IntegrationResult,
  type PendingPromotionRow,
} from "../../shared/services/integrationClient";

const CONFORMANCE_TONE: Record<StrategyConformance, "ok" | "neg" | "warn"> = {
  CONFORMANT: "ok",
  NON_CONFORMANT: "neg",
  PENDING_SCAN: "warn",
};

const ADMIN_STATUS_TONE: Record<StrategyAdminStatus, "ok" | "neg" | "dim"> = {
  ACTIVE: "ok",
  SUSPENDED: "neg",
  DEPRECATED: "dim",
};

export const AdminStrategiesScreen: React.FC = () => {
  const [strategies, setStrategies] = useState<StrategyRow[]>(() => getStoredOwnerStrategies());
  const [strategiesIntegration, setStrategiesIntegration] = useState<IntegrationResult<StrategyRow[]>>({
    data: getStoredOwnerStrategies(),
    source: "SAMPLE_FALLBACK",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: true,
  });
  const [filter, setFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedStrategy, setSelectedStrategy] = useState<StrategyRow | null>(null);
  const [activeDrawerTab, setActiveDrawerTab] = useState<"overview" | "eligibility" | "evidence" | "risk" | "audit">("overview");
  const [feedback, setFeedback] = useState<{ message: string; type: "ok" | "warn" | "error" } | null>(null);
  const [pendingPromotions, setPendingPromotions] = useState<PendingPromotionRow[]>([]);
  const [promotionsSource, setPromotionsSource] = useState<"BACKEND" | "UNAVAILABLE">("UNAVAILABLE");

  const feedbackTimerRef = useRef<any>(null);

  const showFeedback = (message: string, type: "ok" | "warn" | "error" = "ok") => {
    if (feedbackTimerRef.current) clearTimeout(feedbackTimerRef.current);
    setFeedback({ message, type });
    feedbackTimerRef.current = setTimeout(() => setFeedback(null), 5000);
  };

  const loadStrategies = async () => {
    try {
      const res = await queryOwnerStrategies();
      setStrategiesIntegration(res);
      setStrategies(res.data);
      if (selectedStrategy) {
        const refreshed = res.data.find((s) => s.id === selectedStrategy.id || s.strategyId === selectedStrategy.strategyId);
        if (refreshed) setSelectedStrategy(refreshed);
      }
    } catch {
      refreshStrategies();
    }
    try {
      const promos = await queryPendingPromotions();
      if (promos.success && promos.data) {
        setPendingPromotions(promos.data);
        setPromotionsSource("BACKEND");
      } else {
        setPendingPromotions([]);
        setPromotionsSource("UNAVAILABLE");
      }
    } catch {
      setPendingPromotions([]);
      setPromotionsSource("UNAVAILABLE");
    }
  };

  const handleApprovePromotion = async (row: PendingPromotionRow) => {
    const target = strategies.find((s) => s.strategyId === row.strategy_id || s.id === row.strategy_id);
    const res = await approveStrategyPromotion(row.strategy_id, {
      target_stage: row.target_stage,
      version: target?.version,
      run_id: row.run_id || undefined,
    });
    if (res.success) {
      showFeedback(`Promoted ${row.strategy_id} to ${row.target_stage} (persisted, verified).`, "ok");
      await loadStrategies();
    } else {
      showFeedback(`Promotion rejected by authority (no state mutated): ${res.error}`, "error");
    }
  };

  useEffect(() => {
    loadStrategies();
  }, []);

  const refreshStrategies = () => {
    const updated = getStoredOwnerStrategies();
    setStrategies(updated);
    if (selectedStrategy) {
      const refreshed = updated.find((s) => s.id === selectedStrategy.id || s.strategyId === selectedStrategy.strategyId);
      if (refreshed) setSelectedStrategy(refreshed);
    }
  };

  const filtered = useMemo(() => {
    return strategies.filter((s) => {
      const isSuspended = s.adminStatus === "SUSPENDED";
      const gov = getStrategyGovernance(s);
      const bEff = computeEffectiveEligibility(gov.backtest.systemReadiness, gov.backtest.ownerAllowance, isSuspended).status;
      const pEff = computeEffectiveEligibility(gov.paper.systemReadiness, gov.paper.ownerAllowance, isSuspended).status;
      const lEff = computeEffectiveEligibility(gov.live.systemReadiness, gov.live.ownerAllowance, isSuspended).status;

      if (filter === "CONFORMANT" && s.conformanceStatus !== "CONFORMANT" && s.conformanceCheck !== "CONFORMANT") return false;
      if (filter === "NON_CONFORMANT" && s.conformanceStatus !== "NON_CONFORMANT" && s.conformanceCheck !== "NON_CONFORMANT") return false;
      if (filter === "BACKTEST_ELIGIBLE" && bEff !== "ELIGIBLE") return false;
      if (filter === "PAPER_ELIGIBLE" && pEff !== "ELIGIBLE") return false;
      if (filter === "LIVE_ELIGIBLE" && lEff !== "ELIGIBLE") return false;
      if (filter === "SUSPENDED" && s.adminStatus !== "SUSPENDED") return false;

      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          s.name.toLowerCase().includes(q) ||
          (s.strategyId && s.strategyId.toLowerCase().includes(q)) ||
          s.id.toLowerCase().includes(q) ||
          s.version.toLowerCase().includes(q) ||
          (s.interfaceVersion && s.interfaceVersion.toLowerCase().includes(q)) ||
          s.author.toLowerCase().includes(q) ||
          (s.category && s.category.toLowerCase().includes(q)) ||
          s.description.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [strategies, filter, searchQuery]);

  const counts = useMemo(() => {
    const total = strategies.length;
    const conformant = strategies.filter((s) => s.conformanceStatus === "CONFORMANT" || s.conformanceCheck === "CONFORMANT").length;
    const nonConformant = strategies.filter((s) => s.conformanceStatus === "NON_CONFORMANT" || s.conformanceCheck === "NON_CONFORMANT").length;
    const backtestEligible = strategies.filter((s) => {
      const gov = getStrategyGovernance(s);
      return computeEffectiveEligibility(gov.backtest.systemReadiness, gov.backtest.ownerAllowance, s.adminStatus === "SUSPENDED").status === "ELIGIBLE";
    }).length;
    const paperEligible = strategies.filter((s) => {
      const gov = getStrategyGovernance(s);
      return computeEffectiveEligibility(gov.paper.systemReadiness, gov.paper.ownerAllowance, s.adminStatus === "SUSPENDED").status === "ELIGIBLE";
    }).length;
    const liveEligible = strategies.filter((s) => {
      const gov = getStrategyGovernance(s);
      return computeEffectiveEligibility(gov.live.systemReadiness, gov.live.ownerAllowance, s.adminStatus === "SUSPENDED").status === "ELIGIBLE";
    }).length;
    const suspended = strategies.filter((s) => s.adminStatus === "SUSPENDED").length;
    return { total, conformant, nonConformant, backtestEligible, paperEligible, liveEligible, suspended };
  }, [strategies]);

  const handleToggleOwnerAllowance = async (strategyId: string, sandbox: "backtest" | "paper" | "live", currentAllowance: OwnerAllowanceStatus) => {
    const newAllowance: OwnerAllowanceStatus = currentAllowance === "ALLOWED" ? "HOLD" : "ALLOWED";
    const res = await updateBackendStrategyAllowance(strategyId, sandbox, newAllowance, undefined);
    if (res.success) {
      await loadStrategies();
      showFeedback(res.data?.message || "Strategy allowance updated.", res.data?.effective === "ELIGIBLE" ? "ok" : "warn");
    } else {
      showFeedback(res.error || "Action blocked.", "error");
    }
  };

  const handleSuspend = async (strategyId: string, name: string) => {
    const res = await suspendBackendStrategy(strategyId, "Owner administrative hold");
    if (res.success) {
      await loadStrategies();
      showFeedback(`Strategy "${name}" placed on global SUSPENSION. All effective execution sandboxes held.`, "warn");
    } else {
      showFeedback(res.error || `Failed to suspend strategy "${name}".`, "error");
    }
  };

  const handleRestore = async (strategyId: string, name: string) => {
    const res = await restoreBackendStrategy(strategyId, "Restored to active by owner");
    if (res.success) {
      await loadStrategies();
      showFeedback(`Strategy "${name}" restored to ACTIVE. Effective eligibility restored to existing system/allowance permits.`, "ok");
    } else {
      showFeedback(res.error || `Failed to restore strategy "${name}".`, "error");
    }
  };

  const handleToggleVisibility = async (strategyId: string, name: string, current: string | undefined) => {
    const next = current === "GLOBAL" ? "OWNER_PRIVATE" : "GLOBAL";
    const res = await updateBackendStrategyVisibility(strategyId, next);
    if (res.success) {
      await loadStrategies();
      showFeedback(
        next === "GLOBAL"
          ? `Strategy "${name}" published to the GLOBAL catalog.`
          : `Strategy "${name}" unpublished to OWNER_PRIVATE. Historical runs preserved; new user starts fail closed.`,
        next === "GLOBAL" ? "ok" : "warn"
      );
    } else {
      showFeedback(res.error || `Failed to update catalog visibility for "${name}".`, "error");
    }
  };

  return (
    <>
      {/* Screen Header */}
      <div className="v3-screen-head" id="strategies-governance-header">
        <div>
          <h2 className="v3-screen-title">Strategies Governance</h2>
          <p className="v3-screen-sub">
            Institutional Strategy Registry · Conformance verification, sandbox eligibility &amp; promotion authority
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <TruthChip
            kind={strategiesIntegration.source === "BACKEND" ? "REAL" : "SAMPLE"}
            title={strategiesIntegration.source === "BACKEND" ? "Authoritative Owner Strategy Governance (Backend SQLite)" : "Prototype Owner Strategy Governance"}
          />
          <button
            type="button"
            className="v3-btn ghost mini"
            onClick={loadStrategies}
            id="refresh-strategies-btn"
            title="Refresh strategy registry"
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
          id="strategies-feedback-banner"
          style={{ marginBottom: 14 }}
        >
          {feedback.type === "ok" ? "✓" : "⚠️"} {feedback.message}
        </div>
      )}

      {/* Governance & Authority Boundary Warning */}
      <div
        className="security-notice-box"
        id="strategies-authority-banner"
        style={{
          marginBottom: 16,
          borderColor: "rgba(2, 132, 199, 0.4)",
          background: "rgba(2, 132, 199, 0.06)",
        }}
      >
        <span className="sec-notice-icon" style={{ fontSize: 18 }}>🛡️</span>
        <div>
          <div style={{ fontWeight: 600, color: "var(--v3-sky-text)", fontSize: 12, marginBottom: 2 }}>
            OWNER ALLOWANCE vs ENGINE READINESS SEPARATION · FAIL-CLOSED ARCHITECTURE
          </div>
          <span style={{ fontSize: 11.5, color: "var(--v3-ink-2)" }}>
            Effective Sandbox Eligibility = <strong>System Readiness</strong> ∧ <strong>Owner Allowance</strong> ∧ <strong>!Global Suspension</strong>.
            Owner allowance operates as a <strong>restriction ceiling</strong> and can never bypass system conformance, validation reports, ADR §122 paper promotion evidence, or pre-trade risk gates.
          </span>
        </div>
      </div>

      {/* Summary KPI Cards */}
      <div className="v3-kpi-deck" id="strategies-kpi-deck" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginBottom: 16 }}>
        <div className="v3-card" style={{ padding: 14 }}>
          <div className="v3-kpi-title" style={{ fontSize: 11, color: "var(--v3-ink-3)" }}>TOTAL REGISTERED</div>
          <div className="v3-stat-big" style={{ fontSize: 24, fontWeight: 700, marginTop: 4 }}>{counts.total}</div>
          <div className="v3-cell-sub text-xs" style={{ marginTop: 2 }}>Governed algorithms</div>
        </div>
        <div className="v3-card" style={{ padding: 14 }}>
          <div className="v3-kpi-title" style={{ fontSize: 11, color: "var(--v3-ink-3)" }}>CONFORMANCE RATE</div>
          <div className="v3-stat-big" style={{ fontSize: 24, fontWeight: 700, marginTop: 4, color: "var(--v3-profit)" }}>
            {counts.total > 0 ? `${Math.round((counts.conformant / counts.total) * 100)}%` : "0%"}
          </div>
          <div className="v3-cell-sub text-xs" style={{ marginTop: 2 }}>{counts.conformant} pass · {counts.nonConformant} blocked</div>
        </div>
        <div className="v3-card" style={{ padding: 14 }}>
          <div className="v3-kpi-title" style={{ fontSize: 11, color: "var(--v3-ink-3)" }}>LIVE EFFECTIVE</div>
          <div className="v3-stat-big" style={{ fontSize: 24, fontWeight: 700, marginTop: 4, color: "var(--v3-profit)" }}>
            {counts.liveEligible}
          </div>
          <div className="v3-cell-sub text-xs" style={{ marginTop: 2 }}>System Ready ∧ Owner Allowed</div>
        </div>
        <div className="v3-card" style={{ padding: 14 }}>
          <div className="v3-kpi-title" style={{ fontSize: 11, color: "var(--v3-ink-3)" }}>PAPER &amp; BACKTEST</div>
          <div className="v3-stat-big" style={{ fontSize: 24, fontWeight: 700, marginTop: 4 }}>
            {counts.paperEligible} / {counts.backtestEligible}
          </div>
          <div className="v3-cell-sub text-xs" style={{ marginTop: 2 }}>Effective Paper / Backtest</div>
        </div>
        <div className="v3-card" style={{ padding: 14 }}>
          <div className="v3-kpi-title" style={{ fontSize: 11, color: "var(--v3-ink-3)" }}>ADMIN SUSPENDED</div>
          <div className="v3-stat-big" style={{ fontSize: 24, fontWeight: 700, marginTop: 4, color: counts.suspended > 0 ? "var(--v3-warn-text)" : "var(--v3-ink)" }}>
            {counts.suspended}
          </div>
          <div className="v3-cell-sub text-xs" style={{ marginTop: 2 }}>Owner administrative hold</div>
        </div>
      </div>

      {/* Filter Tabs & Search Bar */}
      <div className="v3-card" style={{ padding: 12, marginBottom: 14 }} id="promotion-requests-panel">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 8 }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 13 }}>Promotion Requests · PENDING_OWNER_REVIEW</div>
            <div className="v3-cell-sub text-xs">
              {promotionsSource === "BACKEND"
                ? `${pendingPromotions.length} persisted request(s) from backend authority. Approval validates version, evidence and state before persisting.`
                : "Backend promotion queue unavailable — no request can be approved from this view."}
            </div>
          </div>
          <TruthChip kind={promotionsSource === "BACKEND" ? "REAL" : "DISABLED"} title="Promotion request queue provenance" />
        </div>
        {pendingPromotions.length === 0 ? (
          <div className="v3-cell-sub text-xs">No pending promotion requests.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {pendingPromotions.map((row) => (
              <div key={`${row.strategy_id}:${row.requested_at_utc}`} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, padding: "8px 10px", border: "1px solid var(--v3-line)", borderRadius: 6 }}>
                <div style={{ fontSize: 12 }}>
                  <strong>{row.strategy_id}</strong>
                  <span className="v3-cell-sub"> · {row.current_stage} → {row.target_stage} · run {row.run_id || "—"} · user {String(row.user_id).slice(0, 8)}</span>
                </div>
                <button
                  type="button"
                  className="v3-btn mini primary"
                  id={`approve-promotion-${row.strategy_id}`}
                  onClick={() => handleApprovePromotion(row)}
                >
                  Approve {row.target_stage}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Filter Tabs & Search Bar */}
      <div className="v3-card" style={{ padding: 12, marginBottom: 14 }} id="strategies-filter-toolbar">
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          {/* Quick Filter Buttons */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }} role="tablist" aria-label="Strategy filters">
            <button
              type="button"
              className={`v3-btn mini ${filter === "ALL" ? "primary" : "ghost"}`}
              onClick={() => setFilter("ALL")}
              id="filter-all-strategies-btn"
            >
              All ({counts.total})
            </button>
            <button
              type="button"
              className={`v3-btn mini ${filter === "LIVE_ELIGIBLE" ? "primary" : "ghost"}`}
              onClick={() => setFilter("LIVE_ELIGIBLE")}
              id="filter-live-eligible-btn"
            >
              Live Eligible ({counts.liveEligible})
            </button>
            <button
              type="button"
              className={`v3-btn mini ${filter === "PAPER_ELIGIBLE" ? "primary" : "ghost"}`}
              onClick={() => setFilter("PAPER_ELIGIBLE")}
              id="filter-paper-eligible-btn"
            >
              Paper Eligible ({counts.paperEligible})
            </button>
            <button
              type="button"
              className={`v3-btn mini ${filter === "BACKTEST_ELIGIBLE" ? "primary" : "ghost"}`}
              onClick={() => setFilter("BACKTEST_ELIGIBLE")}
              id="filter-backtest-eligible-btn"
            >
              Backtest Eligible ({counts.backtestEligible})
            </button>
            <button
              type="button"
              className={`v3-btn mini ${filter === "CONFORMANT" ? "primary" : "ghost"}`}
              onClick={() => setFilter("CONFORMANT")}
              id="filter-conformant-btn"
            >
              Conformant ({counts.conformant})
            </button>
            <button
              type="button"
              className={`v3-btn mini ${filter === "NON_CONFORMANT" ? "primary" : "ghost"}`}
              onClick={() => setFilter("NON_CONFORMANT")}
              id="filter-non-conformant-btn"
            >
              Non-Conformant ({counts.nonConformant})
            </button>
            <button
              type="button"
              className={`v3-btn mini ${filter === "SUSPENDED" ? "primary" : "ghost"}`}
              onClick={() => setFilter("SUSPENDED")}
              id="filter-suspended-btn"
            >
              Suspended ({counts.suspended})
            </button>
          </div>

          {/* Search Input */}
          <div style={{ position: "relative", minWidth: 260 }}>
            <input
              type="text"
              placeholder="Search by name, ID, version, or author..."
              className="v3-input"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              id="strategy-search-input"
              style={{ paddingLeft: 28, fontSize: 12, height: 32 }}
            />
            <span style={{ position: "absolute", left: 8, top: 7, color: "var(--v3-ink-dim)", fontSize: 13 }}>
              🔍
            </span>
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                style={{
                  position: "absolute",
                  right: 8,
                  top: 6,
                  background: "transparent",
                  border: "none",
                  color: "var(--v3-ink-dim)",
                  cursor: "pointer",
                }}
              >
                ✕
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Authoritative Strategy Inventory Table */}
      <Panel
        label="Governed Strategy Inventory"
        meta={`${filtered.length} of ${strategies.length} algorithms`}
        className="v3-sp12"
        id="owner-strategies-table-panel"
      >
        <div className="v3-table-wrap">
          <table className="v3-table" id="owner-strategies-table">
            <thead>
              <tr>
                <th style={{ whiteSpace: "nowrap" }}>STRATEGY / IDENTITY</th>
                <th style={{ whiteSpace: "nowrap" }}>VERSIONS (ALG · INTERFACE)</th>
                <th style={{ whiteSpace: "nowrap" }}>CONFORMANCE</th>
                <th style={{ whiteSpace: "nowrap" }}>VALIDATION EVIDENCE</th>
                <th style={{ whiteSpace: "nowrap" }}>BACKTEST (EFFECTIVE)</th>
                <th style={{ whiteSpace: "nowrap" }}>PAPER (EFFECTIVE)</th>
                <th style={{ whiteSpace: "nowrap" }}>LIVE (EFFECTIVE)</th>
                <th style={{ whiteSpace: "nowrap" }}>GOVERNANCE</th>
                <th style={{ textAlign: "right", whiteSpace: "nowrap" }}>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={9} style={{ textAlign: "center", padding: "32px 16px", color: "var(--v3-ink-dim)" }}>
                    {strategies.length === 0 ? "No strategies assigned" : "No strategies match the selected filter criteria."}
                  </td>
                </tr>
              ) : (
                filtered.map((s) => {
                  const isConformant = s.conformanceStatus === "CONFORMANT" || s.conformanceCheck === "CONFORMANT";
                  const isSuspended = s.adminStatus === "SUSPENDED";
                  const gov = getStrategyGovernance(s);

                  const bEff = computeEffectiveEligibility(gov.backtest.systemReadiness, gov.backtest.ownerAllowance, isSuspended);
                  const pEff = computeEffectiveEligibility(gov.paper.systemReadiness, gov.paper.ownerAllowance, isSuspended);
                  const lEff = computeEffectiveEligibility(gov.live.systemReadiness, gov.live.ownerAllowance, isSuspended);

                  return (
                    <tr
                      key={s.id}
                      className="v3-table-row"
                      id={`strategy-row-${s.id}`}
                      style={{ cursor: "pointer" }}
                      onClick={() => {
                        setSelectedStrategy(s);
                        setActiveDrawerTab("overview");
                      }}
                    >
                      {/* Strategy Identity */}
                      <td>
                        <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                          <div
                            className="v3-avatar"
                            style={{
                              background: isConformant ? "rgba(16, 185, 129, 0.12)" : "rgba(239, 68, 68, 0.12)",
                              color: isConformant ? "var(--v3-profit-text)" : "var(--v3-loss-text)",
                              fontWeight: 700,
                              fontSize: 11,
                            }}
                          >
                            {s.category ? s.category.substring(0, 2).toUpperCase() : "ST"}
                          </div>
                          <div>
                            <div className="v3-cell-main font-semibold" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                              <span>{s.name}</span>
                              {s.category && (
                                <span className="v3-mono text-xs v3-dim" style={{ fontSize: 10 }}>
                                  [{s.category}]
                                </span>
                              )}
                              {(s.visibility || "OWNER_PRIVATE") === "GLOBAL" ? (
                                <span className="v3-status-badge ok" style={{ fontSize: 9.5 }} title="Published to the global user catalog">
                                  GLOBAL
                                </span>
                              ) : (
                                <span className="v3-status-badge" style={{ fontSize: 9.5 }} title="Private to the authoring scope">
                                  {s.visibility || "OWNER_PRIVATE"}
                                </span>
                              )}
                            </div>
                            <div className="v3-cell-sub v3-mono text-xs" style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 2 }}>
                              <span className="font-bold text-sky-400">{s.strategyId || s.id}</span>
                              <span>·</span>
                              <span>By {s.author}</span>
                            </div>
                          </div>
                        </div>
                      </td>

                      {/* Versions */}
                      <td>
                        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <span className="v3-dim text-xs">Alg:</span>
                            <span className="v3-mono font-bold text-xs">{s.version}</span>
                          </div>
                          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <span className="v3-dim text-xs">IF:</span>
                            <span className="v3-mono text-xs v3-dim">{s.interfaceVersion || "1.0"}</span>
                          </div>
                        </div>
                      </td>

                      {/* Conformance */}
                      <td>
                        <span className={`v3-status-badge ${isConformant ? "ok" : "neg"}`} style={{ whiteSpace: "nowrap" }}>
                          <Dot tone={isConformant ? "ok" : "neg"} />
                          {isConformant ? "CONFORMANT" : "NON_CONFORMANT"}
                        </span>
                        <div className="v3-cell-sub text-xs" style={{ marginTop: 2 }}>
                          AST: {s.scanStatus}
                        </div>
                      </td>

                      {/* Validation Evidence */}
                      <td>
                        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <span className="v3-mono font-bold text-xs">Sharpe: {s.sharpeRatio}</span>
                            <span className="v3-mono text-xs" style={{ color: "var(--v3-loss-text)" }}>DD: {s.maxDrawdown}%</span>
                          </div>
                          <div className="v3-cell-sub text-xs">
                            Win Rate: {s.winRate}% · {s.totalTrades} trades
                          </div>
                        </div>
                      </td>

                      {/* Backtest Eligibility (Effective) */}
                      <td>
                        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                          <span className={`v3-status-badge ${bEff.tone}`} style={{ fontSize: 10.5 }}>
                            <Dot tone={bEff.tone} />
                            {bEff.label}
                          </span>
                          <span className="v3-mono text-xs v3-dim" style={{ fontSize: 9.5 }}>
                            Sys: {gov.backtest.systemReadiness} · Own: {gov.backtest.ownerAllowance}
                          </span>
                        </div>
                      </td>

                      {/* Paper Eligibility (Effective) */}
                      <td>
                        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                          <span className={`v3-status-badge ${pEff.tone}`} style={{ fontSize: 10.5 }}>
                            <Dot tone={pEff.tone} />
                            {pEff.label}
                          </span>
                          <span className="v3-mono text-xs v3-dim" style={{ fontSize: 9.5 }}>
                            Sys: {gov.paper.systemReadiness} · Own: {gov.paper.ownerAllowance}
                          </span>
                        </div>
                      </td>

                      {/* Live Eligibility (Effective) */}
                      <td>
                        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                          <span className={`v3-status-badge ${lEff.tone}`} style={{ fontSize: 10.5, fontWeight: lEff.status === "ELIGIBLE" ? 700 : 400 }}>
                            <Dot tone={lEff.tone} />
                            {lEff.label}
                          </span>
                          <span className="v3-mono text-xs v3-dim" style={{ fontSize: 9.5 }}>
                            Sys: {gov.live.systemReadiness} · Own: {gov.live.ownerAllowance}
                          </span>
                        </div>
                      </td>

                      {/* Governance Status */}
                      <td>
                        <span className={`v3-status-badge ${isSuspended ? "neg" : "ok"}`}>
                          <Dot tone={isSuspended ? "neg" : "ok"} />
                          {s.adminStatus || "ACTIVE"}
                        </span>
                      </td>

                      {/* Actions */}
                      <td style={{ textAlign: "right" }} onClick={(e) => e.stopPropagation()}>
                        <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                          <button
                            type="button"
                            className="v3-btn ghost mini"
                            onClick={() => {
                              setSelectedStrategy(s);
                              setActiveDrawerTab("overview");
                            }}
                            id={`inspect-strategy-btn-${s.id}`}
                            title="Inspect strategy details & governance parameters"
                          >
                            Inspect
                          </button>

                          {isSuspended ? (
                            <button
                              type="button"
                              className="v3-btn ghost mini"
                              onClick={() => handleRestore(s.id, s.name)}
                              id={`restore-strategy-btn-${s.id}`}
                              title="Restore strategy availability"
                            >
                              Restore
                            </button>
                          ) : (
                            <button
                              type="button"
                              className="v3-btn danger-ghost mini"
                              onClick={() => handleSuspend(s.id, s.name)}
                              id={`suspend-strategy-btn-${s.id}`}
                              title="Suspend strategy availability"
                            >
                              Suspend
                            </button>
                          )}
                          <button
                            type="button"
                            className="v3-btn ghost mini"
                            onClick={() => handleToggleVisibility(s.strategyId || s.id, s.name, s.visibility)}
                            id={`visibility-strategy-btn-${s.id}`}
                            title={(s.visibility || "OWNER_PRIVATE") === "GLOBAL" ? "Unpublish from the global catalog (history preserved)" : "Publish to the global user catalog"}
                          >
                            {(s.visibility || "OWNER_PRIVATE") === "GLOBAL" ? "Unpublish" : "Publish"}
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

      {/* Strategy Detail / Inspection Drawer */}
      {selectedStrategy && (
        <Drawer
          open={Boolean(selectedStrategy)}
          title={selectedStrategy.name}
          sub={`${selectedStrategy.strategyId || selectedStrategy.id} · Algorithm Version ${selectedStrategy.version} · By ${selectedStrategy.author}`}
          onClose={() => setSelectedStrategy(null)}
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
                <div className="v3-dim text-xs">CONFORMANCE</div>
                <div style={{ marginTop: 2 }}>
                  <span className={`v3-status-badge ${selectedStrategy.conformanceStatus === "CONFORMANT" || selectedStrategy.conformanceCheck === "CONFORMANT" ? "ok" : "neg"}`}>
                    <Dot tone={selectedStrategy.conformanceStatus === "CONFORMANT" || selectedStrategy.conformanceCheck === "CONFORMANT" ? "ok" : "neg"} />
                    {selectedStrategy.conformanceStatus || selectedStrategy.conformanceCheck}
                  </span>
                </div>
              </div>
              <div>
                <div className="v3-dim text-xs">STAGE</div>
                <div className="v3-mono font-bold text-xs" style={{ marginTop: 4 }}>
                  {selectedStrategy.stage}
                </div>
              </div>
              <div>
                <div className="v3-dim text-xs">GOVERNANCE</div>
                <div style={{ marginTop: 2 }}>
                  <span className={`v3-status-badge ${selectedStrategy.adminStatus === "SUSPENDED" ? "neg" : "ok"}`}>
                    <Dot tone={selectedStrategy.adminStatus === "SUSPENDED" ? "neg" : "ok"} />
                    {selectedStrategy.adminStatus || "ACTIVE"}
                  </span>
                </div>
              </div>
              <div>
                <div className="v3-dim text-xs">QUALITY SCORE</div>
                <div className="v3-mono font-bold text-xs" style={{ marginTop: 4, color: "var(--v3-profit)" }}>
                  {selectedStrategy.quality}/100
                </div>
              </div>
            </div>

            {/* Drawer Navigation Tabs */}
            <div style={{ display: "flex", borderBottom: "1px solid var(--v3-line)", gap: 4 }}>
              <button
                type="button"
                className={`v3-btn ghost mini ${activeDrawerTab === "overview" ? "primary" : ""}`}
                style={{ borderRadius: "4px 4px 0 0", borderBottom: activeDrawerTab === "overview" ? "2px solid var(--v3-profit)" : "none" }}
                onClick={() => setActiveDrawerTab("overview")}
                id="drawer-tab-overview"
              >
                Overview &amp; Contract
              </button>
              <button
                type="button"
                className={`v3-btn ghost mini ${activeDrawerTab === "eligibility" ? "primary" : ""}`}
                style={{ borderRadius: "4px 4px 0 0", borderBottom: activeDrawerTab === "eligibility" ? "2px solid var(--v3-profit)" : "none" }}
                onClick={() => setActiveDrawerTab("eligibility")}
                id="drawer-tab-eligibility"
              >
                Sandbox Eligibility
              </button>
              <button
                type="button"
                className={`v3-btn ghost mini ${activeDrawerTab === "evidence" ? "primary" : ""}`}
                style={{ borderRadius: "4px 4px 0 0", borderBottom: activeDrawerTab === "evidence" ? "2px solid var(--v3-profit)" : "none" }}
                onClick={() => setActiveDrawerTab("evidence")}
                id="drawer-tab-evidence"
              >
                Validation Evidence
              </button>
              <button
                type="button"
                className={`v3-btn ghost mini ${activeDrawerTab === "risk" ? "primary" : ""}`}
                style={{ borderRadius: "4px 4px 0 0", borderBottom: activeDrawerTab === "risk" ? "2px solid var(--v3-profit)" : "none" }}
                onClick={() => setActiveDrawerTab("risk")}
                id="drawer-tab-risk"
              >
                Risk Envelopes
              </button>
              <button
                type="button"
                className={`v3-btn ghost mini ${activeDrawerTab === "audit" ? "primary" : ""}`}
                style={{ borderRadius: "4px 4px 0 0", borderBottom: activeDrawerTab === "audit" ? "2px solid var(--v3-profit)" : "none" }}
                onClick={() => setActiveDrawerTab("audit")}
                id="drawer-tab-audit"
              >
                Audit Trail
              </button>
            </div>

            {/* Tab 1: Overview & Contract */}
            {activeDrawerTab === "overview" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                <Panel label="Strategy Identity &amp; Version Specifications">
                  <dl style={{ margin: 0 }}>
                    <KV k="Strategy Name" v={selectedStrategy.name} />
                    <KV k="Strategy ID" v={<span className="v3-mono font-bold">{selectedStrategy.strategyId || selectedStrategy.id}</span>} />
                    <KV k="Algorithm Semantic Version" v={<span className="v3-mono font-bold">{selectedStrategy.version}</span>} />
                    <KV k="Engine Interface Version" v={<span className="v3-mono">{selectedStrategy.interfaceVersion || "1.0"} (Rule 6)</span>} />
                    <KV k="Author / Lead Quant" v={`${selectedStrategy.author} (${selectedStrategy.authorSxId || "SX-0009-ALPHA"})`} />
                    <KV k="Language &amp; Runtime" v={`${selectedStrategy.language} 3.12 · BaseStrategy subclass`} />
                    <KV k="Category" v={selectedStrategy.category || "Options Quantitative"} />
                    <KV k="Target Instruments" v={(selectedStrategy.instruments || ["NIFTY"]).join(", ")} />
                    <KV k="Required Timeframes" v={(selectedStrategy.timeframes || ["5m"]).join(", ")} />
                    <KV k="Description" v={selectedStrategy.description} />
                  </dl>
                </Panel>

                <Panel label="Contract &amp; Static AST Conformance">
                  <dl style={{ margin: 0 }}>
                    <KV
                      k="AST Scan Status"
                      v={
                        <span className={`v3-status-badge ${selectedStrategy.scanStatus === "PASSED" ? "ok" : "neg"}`}>
                          <Dot tone={selectedStrategy.scanStatus === "PASSED" ? "ok" : "neg"} />
                          {selectedStrategy.scanStatus}
                        </span>
                      }
                    />
                    <KV
                      k="Rule 1: Signal Generator Contract"
                      v={selectedStrategy.conformanceCheck === "CONFORMANT" ? "VERIFIED (generate_signal() isolated)" : "VIOLATION DETECTED"}
                    />
                    <KV
                      k="Rule 2: Runtime State Schema"
                      v={selectedStrategy.stateSchemaDeclared !== false ? "DECLARED (Runtime context only)" : "VIOLATION (Model weights embedded in state)"}
                    />
                    <KV
                      k="Rule 5: get_data() Feed Wrapper"
                      v={selectedStrategy.dataAccessWrapper !== false ? "CONFORMANT (Single data wrapper)" : "VIOLATION (Direct feed.fetch call)"}
                    />
                    <KV
                      k="Rule 7: Safe Exception Handling"
                      v="ACTIVE (safe_generate_signal wrapper)"
                    />
                    <KV
                      k="AST Analysis Summary"
                      v={selectedStrategy.astScanDetails || "Static scan passed all frozen architecture invariants."}
                    />
                  </dl>
                </Panel>
              </div>
            )}

            {/* Tab 2: Sandbox Execution Eligibility (Separated System Readiness, Owner Allowance & Effective) */}
            {activeDrawerTab === "eligibility" && (() => {
              const isSuspended = selectedStrategy.adminStatus === "SUSPENDED";
              const gov = getStrategyGovernance(selectedStrategy);
              const bGov = gov.backtest;
              const pGov = gov.paper;
              const lGov = gov.live;
              const bEff = computeEffectiveEligibility(bGov.systemReadiness, bGov.ownerAllowance, isSuspended);
              const pEff = computeEffectiveEligibility(pGov.systemReadiness, pGov.ownerAllowance, isSuspended);
              const lEff = computeEffectiveEligibility(lGov.systemReadiness, lGov.ownerAllowance, isSuspended);

              return (
                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  {/* Global Suspension Warning Banner */}
                  {isSuspended && (
                    <div className="v3-feedback-banner neg" role="alert" style={{ fontSize: 12 }}>
                      ⚠️ <strong>GLOBAL ADMINISTRATIVE SUSPENSION ACTIVE:</strong> This strategy is suspended by the Owner. All sandboxes are held in fail-closed BLOCKED state regardless of individual allowances.
                    </div>
                  )}

                  {/* 1. Backtest Sandbox Governance */}
                  <Panel label="1. Backtest Historical Simulation Sandbox">
                    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                      {/* 3-Way Grid */}
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
                        <div className="v3-card" style={{ padding: 8 }}>
                          <div className="v3-dim text-xs">SYSTEM READINESS</div>
                          <div style={{ marginTop: 4 }}>
                            <span className={`v3-status-badge ${bGov.systemReadiness === "READY" ? "ok" : "neg"}`}>
                              <Dot tone={bGov.systemReadiness === "READY" ? "ok" : "neg"} />
                              {bGov.systemReadiness}
                            </span>
                          </div>
                        </div>

                        <div className="v3-card" style={{ padding: 8 }}>
                          <div className="v3-dim text-xs">OWNER ALLOWANCE</div>
                          <div style={{ marginTop: 4 }}>
                            <span className={`v3-status-badge ${bGov.ownerAllowance === "ALLOWED" ? "ok" : "warn"}`}>
                              <Dot tone={bGov.ownerAllowance === "ALLOWED" ? "ok" : "warn"} />
                              {bGov.ownerAllowance}
                            </span>
                          </div>
                        </div>

                        <div className="v3-card" style={{ padding: 8 }}>
                          <div className="v3-dim text-xs">EFFECTIVE ELIGIBILITY</div>
                          <div style={{ marginTop: 4 }}>
                            <span className={`v3-status-badge ${bEff.tone}`}>
                              <Dot tone={bEff.tone} />
                              {bEff.label}
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Blocker / Status explanation */}
                      {bGov.systemReadiness !== "READY" && (
                        <div className="v3-cell-sub text-xs" style={{ color: "var(--v3-loss-text)" }}>
                          ⛔ <strong>System Gate Blocker:</strong> {bGov.systemBlockerReason || "Strategy fails AST static analysis."}
                        </div>
                      )}

                      {/* Action Toolbar */}
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: 4, borderTop: "1px solid var(--v3-line)" }}>
                        <span className="v3-cell-sub text-xs">
                          Rule: Effective = System ({bGov.systemReadiness}) ∧ Owner ({bGov.ownerAllowance})
                        </span>
                        <button
                          type="button"
                          className={`v3-btn mini ${bGov.ownerAllowance === "ALLOWED" ? "ghost" : "primary"}`}
                          onClick={() => handleToggleOwnerAllowance(selectedStrategy.id, "backtest", bGov.ownerAllowance)}
                          id="toggle-backtest-eligibility-btn"
                        >
                          {bGov.ownerAllowance === "ALLOWED" ? "Place Backtest Hold" : "Allow Backtest"}
                        </button>
                      </div>
                    </div>
                  </Panel>

                  {/* 2. Paper Trading Sandbox Governance */}
                  <Panel label="2. Paper Forward Trading Sandbox">
                    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                      {/* 3-Way Grid */}
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
                        <div className="v3-card" style={{ padding: 8 }}>
                          <div className="v3-dim text-xs">SYSTEM READINESS</div>
                          <div style={{ marginTop: 4 }}>
                            <span className={`v3-status-badge ${pGov.systemReadiness === "READY" ? "ok" : "neg"}`}>
                              <Dot tone={pGov.systemReadiness === "READY" ? "ok" : "neg"} />
                              {pGov.systemReadiness}
                            </span>
                          </div>
                        </div>

                        <div className="v3-card" style={{ padding: 8 }}>
                          <div className="v3-dim text-xs">OWNER ALLOWANCE</div>
                          <div style={{ marginTop: 4 }}>
                            <span className={`v3-status-badge ${pGov.ownerAllowance === "ALLOWED" ? "ok" : "warn"}`}>
                              <Dot tone={pGov.ownerAllowance === "ALLOWED" ? "ok" : "warn"} />
                              {pGov.ownerAllowance}
                            </span>
                          </div>
                        </div>

                        <div className="v3-card" style={{ padding: 8 }}>
                          <div className="v3-dim text-xs">EFFECTIVE ELIGIBILITY</div>
                          <div style={{ marginTop: 4 }}>
                            <span className={`v3-status-badge ${pEff.tone}`}>
                              <Dot tone={pEff.tone} />
                              {pEff.label}
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Blocker / Status explanation */}
                      {pGov.systemReadiness !== "READY" && (
                        <div className="v3-cell-sub text-xs" style={{ color: "var(--v3-loss-text)" }}>
                          ⛔ <strong>System Gate Blocker:</strong> {pGov.systemBlockerReason || "Backtest milestone report unattached."}
                        </div>
                      )}

                      {/* Action Toolbar */}
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: 4, borderTop: "1px solid var(--v3-line)" }}>
                        <span className="v3-cell-sub text-xs">
                          Rule: Effective = System ({pGov.systemReadiness}) ∧ Owner ({pGov.ownerAllowance})
                        </span>
                        <button
                          type="button"
                          className={`v3-btn mini ${pGov.ownerAllowance === "ALLOWED" ? "ghost" : "primary"}`}
                          onClick={() => handleToggleOwnerAllowance(selectedStrategy.id, "paper", pGov.ownerAllowance)}
                          id="toggle-paper-eligibility-btn"
                        >
                          {pGov.ownerAllowance === "ALLOWED" ? "Place Paper Hold" : "Allow Paper"}
                        </button>
                      </div>
                    </div>
                  </Panel>

                  {/* 3. Live Execution Sandbox Governance (Strictest Tier) */}
                  <Panel label="3. Live Execution Sandbox (Strictest Governance Tier)">
                    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                      {/* 3-Way Grid */}
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
                        <div className="v3-card" style={{ padding: 8 }}>
                          <div className="v3-dim text-xs">SYSTEM READINESS</div>
                          <div style={{ marginTop: 4 }}>
                            <span className={`v3-status-badge ${lGov.systemReadiness === "READY" ? "ok" : "neg"}`}>
                              <Dot tone={lGov.systemReadiness === "READY" ? "ok" : "neg"} />
                              {lGov.systemReadiness}
                            </span>
                          </div>
                        </div>

                        <div className="v3-card" style={{ padding: 8 }}>
                          <div className="v3-dim text-xs">OWNER ALLOWANCE</div>
                          <div style={{ marginTop: 4 }}>
                            <span className={`v3-status-badge ${lGov.ownerAllowance === "ALLOWED" ? "ok" : "warn"}`}>
                              <Dot tone={lGov.ownerAllowance === "ALLOWED" ? "ok" : "warn"} />
                              {lGov.ownerAllowance}
                            </span>
                          </div>
                        </div>

                        <div className="v3-card" style={{ padding: 8 }}>
                          <div className="v3-dim text-xs">EFFECTIVE ELIGIBILITY</div>
                          <div style={{ marginTop: 4 }}>
                            <span className={`v3-status-badge ${lEff.tone}`} style={{ fontWeight: lEff.status === "ELIGIBLE" ? 700 : 400 }}>
                              <Dot tone={lEff.tone} />
                              {lEff.label}
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Blocker / Status explanation */}
                      {lGov.systemReadiness !== "READY" ? (
                        <div className="v3-cell-sub text-xs" style={{ color: "var(--v3-loss-text)" }}>
                          ⛔ <strong>System Gate Blocker:</strong> {lGov.systemBlockerReason || "ADR §122 paper forward evaluation tracking incomplete."}
                        </div>
                      ) : (
                        <div className="v3-cell-sub text-xs" style={{ color: "var(--v3-profit-text)" }}>
                          ✓ <strong>System Ready:</strong> Contiguous 30-day paper verification report verified. Risk envelopes active.
                        </div>
                      )}

                      {/* Action Toolbar */}
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: 4, borderTop: "1px solid var(--v3-line)" }}>
                        <span className="v3-cell-sub text-xs">
                          Rule: Effective = System ({lGov.systemReadiness}) ∧ Owner ({lGov.ownerAllowance})
                        </span>
                        <button
                          type="button"
                          className={`v3-btn mini ${lGov.ownerAllowance === "ALLOWED" ? "ghost" : "primary"}`}
                          onClick={() => handleToggleOwnerAllowance(selectedStrategy.id, "live", lGov.ownerAllowance)}
                          id="toggle-live-eligibility-btn"
                        >
                          {lGov.ownerAllowance === "ALLOWED" ? "Place Live Hold" : "Allow Live"}
                        </button>
                      </div>
                    </div>
                  </Panel>

                  {/* Fail-Closed Architecture Reminder */}
                  <div className="security-notice-box" style={{ fontSize: 11.5 }}>
                    <span className="sec-notice-icon">🔒</span>
                    <span>
                      <strong>Fail-Closed Safety Invariant:</strong> Even if Owner Allowance is marked <code>ALLOWED</code>, effective live execution remains strictly <code>BLOCKED</code> unless the AlgoFortis engine confirms that all promotion evidence, protective policies, and risk watchdog criteria are satisfied.
                    </span>
                  </div>
                </div>
              );
            })()}

            {/* Tab 3: Validation Metrics & Evidence */}
            {activeDrawerTab === "evidence" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                <Panel label="Performance Metrics &amp; Statistical Bounds">
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 10 }}>
                    <div className="v3-card" style={{ padding: 10 }}>
                      <div className="v3-dim text-xs">SHARPE RATIO</div>
                      <div className="v3-stat-big" style={{ fontSize: 20, fontWeight: 700, marginTop: 2 }}>
                        {selectedStrategy.sharpeRatio}
                      </div>
                      <div className="v3-cell-sub text-xs">Target &gt;= 1.20</div>
                    </div>
                    <div className="v3-card" style={{ padding: 10 }}>
                      <div className="v3-dim text-xs">MAX DRAWDOWN</div>
                      <div className="v3-stat-big" style={{ fontSize: 20, fontWeight: 700, marginTop: 2, color: "var(--v3-loss-text)" }}>
                        {selectedStrategy.maxDrawdown}%
                      </div>
                      <div className="v3-cell-sub text-xs">Ceiling &lt; 15.0%</div>
                    </div>
                    <div className="v3-card" style={{ padding: 10 }}>
                      <div className="v3-dim text-xs">WIN RATE</div>
                      <div className="v3-stat-big" style={{ fontSize: 20, fontWeight: 700, marginTop: 2 }}>
                        {selectedStrategy.winRate}%
                      </div>
                      <div className="v3-cell-sub text-xs">{selectedStrategy.totalTrades} total trades</div>
                    </div>
                    <div className="v3-card" style={{ padding: 10 }}>
                      <div className="v3-dim text-xs">PROFIT FACTOR</div>
                      <div className="v3-stat-big" style={{ fontSize: 20, fontWeight: 700, marginTop: 2, color: "var(--v3-profit-text)" }}>
                        {selectedStrategy.profitFactor}
                      </div>
                      <div className="v3-cell-sub text-xs">Gross profit / loss ratio</div>
                    </div>
                  </div>
                </Panel>

                <Panel label="Promotion &amp; Verification State">
                  <dl style={{ margin: 0 }}>
                    <KV k="Validation Stage" v={selectedStrategy.validationStage || "UNTESTED"} />
                    <KV k="Evidence Package Attached" v={selectedStrategy.evidenceAttached ? "YES (Immutable Hash Verified)" : "NO"} />
                    <KV k="Sample P&L Performance" v={selectedStrategy.pnl} />
                    <KV k="Operational Note" v={selectedStrategy.note} />
                    <KV k="Last Updated" v={selectedStrategy.lastUpdated} />
                  </dl>
                </Panel>
              </div>
            )}

            {/* Tab 4: Pre-Trade Risk & Safety Envelopes */}
            {activeDrawerTab === "risk" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                <Panel label="Pre-Trade Risk Watchdog Binding">
                  <dl style={{ margin: 0 }}>
                    <KV k="Risk Engine Enforcement" v="Hardware Watchdog (Warden) · Active" />
                    <KV k="Risk Envelope Parameters" v={selectedStrategy.riskEnvelope || "ACTIVE · Max loss ₹20k"} />
                    <KV k="Option Strike Policy" v="Unified Global Policy Active (ATM ± 4 strikes)" />
                    <KV k="Circuit Breaker Threshold" v="Trips on 3 consecutive rejected orders" />
                    <KV k="Owner Risk Bypass Permitted" v={<span style={{ color: "var(--v3-loss-text)", fontWeight: 700 }}>NO — FAIL-CLOSED INVARIANT</span>} />
                  </dl>
                </Panel>

                <div className="security-notice-box">
                  <span className="sec-notice-icon">🔒</span>
                  <span>
                    <strong>Risk Envelope Protection:</strong> Regardless of Owner eligibility flags, all order emissions from this strategy pass through deterministic pre-trade risk envelopes prior to broker transmission.
                  </span>
                </div>
              </div>
            )}

            {/* Tab 5: Governance Audit Trail */}
            {activeDrawerTab === "audit" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                <Panel label="Governance Event History">
                  <div className="v3-rows">
                    {selectedStrategy.governanceHistory && selectedStrategy.governanceHistory.length > 0 ? (
                      selectedStrategy.governanceHistory.map((ev) => (
                        <div className="v3-row" key={ev.id}>
                          <div className="v3-row-main">
                            <div className="v3-row-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <Dot tone={ev.tone || "ok"} />
                              <span className="v3-mono font-bold text-xs">{ev.action}</span>
                              <span className="v3-dim text-xs">by {ev.actor}</span>
                            </div>
                            <div className="v3-row-sub" style={{ marginTop: 2 }}>{ev.note}</div>
                          </div>
                          <span className="v3-mono v3-dim text-xs" style={{ fontSize: 10.5, flexShrink: 0 }}>
                            {ev.timestamp}
                          </span>
                        </div>
                      ))
                    ) : (
                      <div className="v3-dim text-xs" style={{ padding: 12 }}>
                        No governance events recorded yet.
                      </div>
                    )}
                  </div>
                </Panel>
              </div>
            )}
          </div>
        </Drawer>
      )}
    </>
  );
};
