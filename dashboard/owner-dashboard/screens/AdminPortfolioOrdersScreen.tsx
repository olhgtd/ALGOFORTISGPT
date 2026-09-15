import React, { useState, useMemo, useRef, useEffect } from "react";
import { Icon } from "../../shared/icons/V3Icons";
import { OrdersPortfolioRuntime } from "../../shared/components/OrdersPortfolioRuntime";
import { Panel, Drawer, KV, TruthChip, Dot } from "../../shared/utilities/V3Chrome";
import {
  getStoredOwnerPortfolios,
  updatePortfolioHold,
  getStoredOwnerPositions,
  getStoredOwnerOrders,
  requestOrderCancelSimulated,
  type OwnerPortfolioRow,
  type OwnerPositionRow,
  type OwnerOrderRow,
  type OwnerAllowanceStatus,
} from "../../sampleData";

interface AdminPortfolioOrdersProps {
  previewMode?: boolean;
  initialTab?: "portfolio" | "positions" | "orders";
  go?: (screen: string) => void;
}

export const AdminPortfolioOrdersScreen: React.FC<AdminPortfolioOrdersProps> = ({ initialTab = "portfolio", previewMode }) =>
  previewMode ? <AdminPortfolioOrdersPreview initialTab={initialTab} /> : <OrdersPortfolioRuntime owner initialTab={initialTab} />;

const AdminPortfolioOrdersPreview: React.FC<AdminPortfolioOrdersProps> = ({ initialTab = "portfolio", go }) => {
  const [activeTab, setActiveTab] = useState<"portfolio" | "positions" | "orders">(initialTab);

  useEffect(() => {
    if (initialTab) {
      setActiveTab(initialTab);
    }
  }, [initialTab]);

  // State collections
  const [portfolios, setPortfolios] = useState<OwnerPortfolioRow[]>(() => getStoredOwnerPortfolios());
  const [positions, setPositions] = useState<OwnerPositionRow[]>(() => getStoredOwnerPositions());
  const [orders, setOrders] = useState<OwnerOrderRow[]>(() => getStoredOwnerOrders());

  // Filter & Search states
  const [envFilter, setEnvFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  // Inspection Drawer states
  const [selectedPortfolio, setSelectedPortfolio] = useState<OwnerPortfolioRow | null>(null);
  const [selectedPosition, setSelectedPosition] = useState<OwnerPositionRow | null>(null);
  const [selectedOrder, setSelectedOrder] = useState<OwnerOrderRow | null>(null);

  // Feedback Banner
  const [feedback, setFeedback] = useState<{ message: string; type: "ok" | "warn" | "error" } | null>(null);
  const feedbackTimerRef = useRef<any>(null);

  const showFeedback = (message: string, type: "ok" | "warn" | "error" = "ok") => {
    if (feedbackTimerRef.current) clearTimeout(feedbackTimerRef.current);
    setFeedback({ message, type });
    feedbackTimerRef.current = setTimeout(() => setFeedback(null), 5000);
  };

  const refreshAll = () => {
    const updatedPorts = getStoredOwnerPortfolios();
    const updatedPositions = getStoredOwnerPositions();
    const updatedOrders = getStoredOwnerOrders();
    setPortfolios(updatedPorts);
    setPositions(updatedPositions);
    setOrders(updatedOrders);

    if (selectedPortfolio) {
      const u = updatedPorts.find((p) => p.id === selectedPortfolio.id || p.portfolioId === selectedPortfolio.portfolioId);
      if (u) setSelectedPortfolio(u);
    }
    if (selectedPosition) {
      const u = updatedPositions.find((pos) => pos.id === selectedPosition.id || pos.positionId === selectedPosition.positionId);
      if (u) setSelectedPosition(u);
    }
    if (selectedOrder) {
      const u = updatedOrders.find((o) => o.id === selectedOrder.id || o.orderId === selectedOrder.orderId);
      if (u) setSelectedOrder(u);
    }
  };

  // Filtered Portfolios
  const filteredPortfolios = useMemo(() => {
    return portfolios.filter((p) => {
      if (envFilter === "LIVE" && p.environment !== "LIVE / SAMPLE") return false;
      if (envFilter === "PAPER" && p.environment !== "PAPER") return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          p.portfolioId.toLowerCase().includes(q) ||
          p.accountRef.toLowerCase().includes(q) ||
          p.brokerConnection.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [portfolios, envFilter, searchQuery]);

  // Filtered Positions
  const filteredPositions = useMemo(() => {
    return positions.filter((pos) => {
      if (envFilter === "LIVE" && pos.environment !== "LIVE / SAMPLE") return false;
      if (envFilter === "PAPER" && pos.environment !== "PAPER") return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          pos.positionId.toLowerCase().includes(q) ||
          pos.strategyName.toLowerCase().includes(q) ||
          pos.strategyId.toLowerCase().includes(q) ||
          pos.instrument.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [positions, envFilter, searchQuery]);

  // Filtered Orders
  const filteredOrders = useMemo(() => {
    return orders.filter((o) => {
      if (envFilter === "LIVE" && o.environment !== "LIVE / SAMPLE") return false;
      if (envFilter === "PAPER" && o.environment !== "PAPER") return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          o.orderId.toLowerCase().includes(q) ||
          o.strategyName.toLowerCase().includes(q) ||
          o.strategyId.toLowerCase().includes(q) ||
          o.instrument.toLowerCase().includes(q) ||
          o.clientOrderId.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [orders, envFilter, searchQuery]);

  // Actions
  const handleTogglePortfolioHold = (id: string, currentAllowance: OwnerAllowanceStatus) => {
    const next: OwnerAllowanceStatus = currentAllowance === "ALLOWED" ? "HOLD" : "ALLOWED";
    const res = updatePortfolioHold(id, next, undefined, "OWNER-001");
    refreshAll();
    showFeedback(res.message, next === "HOLD" ? "warn" : "ok");
  };

  const handleRequestCancelOrder = (id: string) => {
    const res = requestOrderCancelSimulated(id, "OWNER-001");
    refreshAll();
    showFeedback(res.message, res.success ? "warn" : "error");
  };

  return (
    <>
      {/* Screen Header */}
      <div className="v3-screen-head" id="portfolio-orders-header">
        <div>
          <h2 className="v3-screen-title">Portfolio &amp; Orders Oversight</h2>
          <p className="v3-screen-sub">
            Observation &amp; Governance Console · Portfolio NAV, Active Positions, Multi-Axis Order Lifecycle &amp; Fill Evidence
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <TruthChip kind="SAMPLE" title="DEV PREVIEW / SAMPLE — Observation Console" />
          <button
            type="button"
            className="v3-btn ghost mini"
            onClick={refreshAll}
            id="refresh-portfolio-orders-btn"
            title="Refresh portfolio & orders telemetry"
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
          id="portfolio-orders-feedback-banner"
          style={{ marginBottom: 14 }}
        >
          {feedback.type === "ok" ? "✓" : "⚠️"} {feedback.message}
        </div>
      )}

      {/* Architecture & Authority Boundary Banner */}
      <div
        className="security-notice-box"
        id="portfolio-orders-authority-banner"
        style={{
          marginBottom: 16,
          borderColor: "rgba(59, 130, 246, 0.4)",
          background: "rgba(59, 130, 246, 0.06)",
        }}
      >
        <span className="sec-notice-icon" style={{ fontSize: 18 }}>🛡️</span>
        <div>
          <div style={{ fontWeight: 600, color: "var(--v3-sky-text)", fontSize: 12, marginBottom: 2 }}>
            OBSERVATION + GOVERNANCE BOUNDARY
          </div>
          <span style={{ fontSize: 11.5, color: "var(--v3-ink-2)" }}>
            Historical and runtime execution truth is authoritative to the engine, broker, and reconciliation subsystems.{" "}
            <strong>Zero trade entry, force fill, position mutation, or risk override controls</strong> are exposed on this surface.{" "}
            <strong>Owner Hold</strong> acts solely as an administrative ceiling on new order permissions without altering past accounting truth.
          </span>
        </div>
      </div>

      {/* Section Navigation Tabs */}
      <div className="v3-card" style={{ padding: "6px 12px", marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }} id="portfolio-orders-nav-bar">
        <div style={{ display: "flex", gap: 8 }}>
          <button
            type="button"
            className={`v3-btn mini ${activeTab === "portfolio" ? "primary" : "ghost"}`}
            onClick={() => {
              setActiveTab("portfolio");
              setSearchQuery("");
            }}
            id="tab-btn-portfolio-oversight"
          >
            1. Portfolios &amp; Accounts ({portfolios.length})
          </button>
          <button
            type="button"
            className={`v3-btn mini ${activeTab === "positions" ? "primary" : "ghost"}`}
            onClick={() => {
              setActiveTab("positions");
              setSearchQuery("");
            }}
            id="tab-btn-positions-oversight"
          >
            2. Active Positions ({positions.length})
          </button>
          <button
            type="button"
            className={`v3-btn mini ${activeTab === "orders" ? "primary" : "ghost"}`}
            onClick={() => {
              setActiveTab("orders");
              setSearchQuery("");
            }}
            id="tab-btn-orders-oversight"
          >
            3. Orders &amp; Executions ({orders.length})
          </button>
        </div>

        {/* Environment Filter Pill */}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span className="v3-dim text-xs">ENV:</span>
          <button
            type="button"
            className={`v3-btn mini ${envFilter === "ALL" ? "primary" : "ghost"}`}
            onClick={() => setEnvFilter("ALL")}
            id="filter-env-all-btn"
          >
            All
          </button>
          <button
            type="button"
            className={`v3-btn mini ${envFilter === "LIVE" ? "primary" : "ghost"}`}
            onClick={() => setEnvFilter("LIVE")}
            id="filter-env-live-btn"
          >
            Live Only
          </button>
          <button
            type="button"
            className={`v3-btn mini ${envFilter === "PAPER" ? "primary" : "ghost"}`}
            onClick={() => setEnvFilter("PAPER")}
            id="filter-env-paper-btn"
          >
            Paper Only
          </button>
        </div>
      </div>

      {/* ════════════════════════════════════════════════════════════
         TAB 1: PORTFOLIOS & ACCOUNTS
         ════════════════════════════════════════════════════════════ */}
      {activeTab === "portfolio" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }} id="section-portfolios-oversight">
          {/* KPI Deck */}
          <div className="v3-kpi-deck" id="portfolios-kpi-deck" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 12 }}>
            <div className="v3-card" style={{ padding: 14 }}>
              <div className="v3-dim text-xs">TOTAL MANAGED ACCOUNTS</div>
              <div className="v3-stat-big" style={{ fontSize: 24, fontWeight: 700, marginTop: 4 }}>{portfolios.length}</div>
              <div className="v3-cell-sub text-xs">Live &amp; Paper portfolio fleet</div>
            </div>
            <div className="v3-card" style={{ padding: 14 }}>
              <div className="v3-dim text-xs">TOTAL CAPITAL BASIS</div>
              <div className="v3-stat-big" style={{ fontSize: 24, fontWeight: 700, marginTop: 4, color: "var(--v3-sky-text)" }}>
                ₹{(portfolios.reduce((acc, p) => acc + p.cash, 0)).toLocaleString()}
              </div>
              <div className="v3-cell-sub text-xs">Simulated &amp; sample capital</div>
            </div>
            <div className="v3-card" style={{ padding: 14 }}>
              <div className="v3-dim text-xs">TOTAL EXPOSURE</div>
              <div className="v3-stat-big" style={{ fontSize: 24, fontWeight: 700, marginTop: 4, color: "var(--v3-profit)" }}>
                ₹{(portfolios.reduce((acc, p) => acc + p.exposure, 0)).toLocaleString()}
              </div>
              <div className="v3-cell-sub text-xs">Active market allocation</div>
            </div>
            <div className="v3-card" style={{ padding: 14 }}>
              <div className="v3-dim text-xs">RECONCILIATION CLEAN</div>
              <div className="v3-stat-big" style={{ fontSize: 24, fontWeight: 700, marginTop: 4, color: "var(--v3-profit)" }}>
                {portfolios.filter((p) => p.reconciliationState === "MATCH_HEALTHY").length} / {portfolios.length}
              </div>
              <div className="v3-cell-sub text-xs">0 ledger discrepancies</div>
            </div>
          </div>

          {/* Portfolios Table */}
          <Panel label="Portfolio &amp; Account Inventory (DEV PREVIEW / SAMPLE)" meta={`${filteredPortfolios.length} accounts`} className="v3-sp12">
            <div className="v3-table-wrap">
              <table className="v3-table" id="owner-portfolios-table">
                <thead>
                  <tr>
                    <th style={{ whiteSpace: "nowrap" }}>PORTFOLIO ID &amp; ACCOUNT</th>
                    <th style={{ whiteSpace: "nowrap" }}>ENVIRONMENT</th>
                    <th style={{ whiteSpace: "nowrap" }}>CASH &amp; EXPOSURE</th>
                    <th style={{ whiteSpace: "nowrap" }}>REALIZED / UNREALIZED P&amp;L</th>
                    <th style={{ whiteSpace: "nowrap" }}>RECONCILIATION</th>
                    <th style={{ whiteSpace: "nowrap" }}>OWNER ALLOWANCE</th>
                    <th style={{ whiteSpace: "nowrap" }}>EFFECTIVE PERMISSION</th>
                    <th style={{ textAlign: "right", whiteSpace: "nowrap" }}>ACTIONS</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredPortfolios.length === 0 ? (
                    <tr>
                      <td colSpan={8} style={{ textAlign: "center", padding: "28px", color: "var(--v3-ink-dim)" }}>
                        No portfolios match filter.
                      </td>
                    </tr>
                  ) : (
                    filteredPortfolios.map((p) => {
                      const isHeld = p.ownerAllowance === "HOLD";
                      const isCleanRecon = p.reconciliationState === "MATCH_HEALTHY";
                      const isLive = p.environment === "LIVE / SAMPLE";

                      return (
                        <tr
                          key={p.id}
                          className="v3-table-row"
                          id={`port-row-${p.id}`}
                          style={{ cursor: "pointer" }}
                          onClick={() => setSelectedPortfolio(p)}
                        >
                          {/* ID & Account */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className="v3-mono font-bold text-xs text-sky-400">{p.portfolioId}</span>
                              <span className="v3-cell-sub text-xs font-semibold">{p.accountRef.split(" ")[0]}</span>
                            </div>
                          </td>

                          {/* Environment */}
                          <td>
                            <span className={`v3-chip ${isLive ? "warn" : "ok"}`} style={{ fontSize: 9.5 }}>
                              {p.environment}
                            </span>
                          </td>

                          {/* Cash & Exposure */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className="v3-mono text-xs font-bold">₹{p.cash.toLocaleString()}</span>
                              <span className="v3-mono v3-dim text-xs" style={{ fontSize: 9.5 }}>Exposure: ₹{p.exposure.toLocaleString()} ({p.marginUtilizationPct}%)</span>
                            </div>
                          </td>

                          {/* P&L */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className="v3-mono font-bold text-xs" style={{ color: p.realizedPnl.startsWith("+") ? "var(--v3-profit)" : "var(--v3-loss-text)" }}>
                                {p.realizedPnl} real
                              </span>
                              <span className="v3-mono v3-dim text-xs" style={{ fontSize: 9.5 }}>{p.unrealizedPnl} unreal</span>
                            </div>
                          </td>

                          {/* Reconciliation */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className={`v3-status-badge ${isCleanRecon ? "ok" : "warn"}`}>
                                <Dot tone={isCleanRecon ? "ok" : "warn"} />
                                {p.reconciliationState.replace("_", " ")}
                              </span>
                              <span className="v3-mono v3-dim text-xs" style={{ fontSize: 9.5 }}>{p.lastReconciliationAt}</span>
                            </div>
                          </td>

                          {/* Owner Allowance */}
                          <td>
                            <span className={`v3-status-badge ${isHeld ? "warn" : "ok"}`}>
                              <Dot tone={isHeld ? "warn" : "ok"} />
                              {p.ownerAllowance}
                            </span>
                          </td>

                          {/* Effective Permission */}
                          <td>
                            <span className={`v3-status-badge ${p.effectiveOrderPermission === "OPERATIONAL" ? "ok" : "warn"}`}>
                              <Dot tone={p.effectiveOrderPermission === "OPERATIONAL" ? "ok" : "warn"} />
                              {p.effectiveOrderPermission}
                            </span>
                          </td>

                          {/* Actions */}
                          <td style={{ textAlign: "right" }} onClick={(e) => e.stopPropagation()}>
                            <div style={{ display: "inline-flex", gap: 6 }}>
                              <button
                                type="button"
                                className="v3-btn ghost mini"
                                onClick={() => setSelectedPortfolio(p)}
                                id={`inspect-port-btn-${p.id}`}
                                title="Inspect portfolio telemetry"
                              >
                                Inspect
                              </button>
                              <button
                                type="button"
                                className={`v3-btn mini ${isHeld ? "ghost" : "danger-ghost"}`}
                                onClick={() => handleTogglePortfolioHold(p.id, p.ownerAllowance)}
                                id={`toggle-hold-port-btn-${p.id}`}
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
         TAB 2: ACTIVE POSITIONS
         ════════════════════════════════════════════════════════════ */}
      {activeTab === "positions" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }} id="section-positions-oversight">
          <Panel label="Active Market Positions Ledger (Read-Only Observation)" meta={`${filteredPositions.length} positions`} className="v3-sp12">
            <div className="v3-table-wrap">
              <table className="v3-table" id="owner-positions-table">
                <thead>
                  <tr>
                    <th style={{ whiteSpace: "nowrap" }}>POSITION ID &amp; STRATEGY</th>
                    <th style={{ whiteSpace: "nowrap" }}>ENV</th>
                    <th style={{ whiteSpace: "nowrap" }}>INSTRUMENT</th>
                    <th style={{ whiteSpace: "nowrap" }}>SIDE &amp; QTY</th>
                    <th style={{ whiteSpace: "nowrap" }}>AVG ENTRY · MARK</th>
                    <th style={{ whiteSpace: "nowrap" }}>UNREALIZED P&amp;L</th>
                    <th style={{ whiteSpace: "nowrap" }}>PROTECTIVE POLICY &amp; TRAIL</th>
                    <th style={{ whiteSpace: "nowrap" }}>RECONCILIATION</th>
                    <th style={{ textAlign: "right", whiteSpace: "nowrap" }}>ACTIONS</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredPositions.length === 0 ? (
                    <tr>
                      <td colSpan={9} style={{ textAlign: "center", padding: "28px", color: "var(--v3-ink-dim)" }}>
                        No active positions match filter.
                      </td>
                    </tr>
                  ) : (
                    filteredPositions.map((pos) => {
                      const isLive = pos.environment === "LIVE / SAMPLE";
                      const isProfit = pos.unrealizedPnl.startsWith("+");
                      const isCleanRecon = pos.reconciliationState === "MATCH_HEALTHY";

                      return (
                        <tr
                          key={pos.id}
                          className="v3-table-row"
                          id={`pos-row-${pos.id}`}
                          style={{ cursor: "pointer" }}
                          onClick={() => setSelectedPosition(pos)}
                        >
                          {/* ID & Strategy */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className="v3-mono font-bold text-xs text-sky-400">{pos.positionId}</span>
                              <span className="font-semibold text-xs">{pos.strategyName} ({pos.strategyId})</span>
                            </div>
                          </td>

                          {/* Env */}
                          <td>
                            <span className={`v3-chip ${isLive ? "warn" : "ok"}`} style={{ fontSize: 9 }}>
                              {pos.environment}
                            </span>
                          </td>

                          {/* Instrument */}
                          <td>
                            <span className="v3-mono font-bold text-xs">{pos.instrument}</span>
                          </td>

                          {/* Side & Qty */}
                          <td>
                            <span className="v3-mono font-bold text-xs">{pos.side} {pos.quantity}</span>
                          </td>

                          {/* Entry / Mark */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className="v3-mono text-xs">Entry: ₹{pos.avgEntryPrice.toFixed(2)}</span>
                              <span className="v3-mono v3-dim text-xs" style={{ fontSize: 9.5 }}>Mark: ₹{pos.markPrice.toFixed(2)}</span>
                            </div>
                          </td>

                          {/* Unrealized P&L */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className="v3-mono font-bold text-xs" style={{ color: isProfit ? "var(--v3-profit)" : "var(--v3-loss-text)" }}>
                                {pos.unrealizedPnl}
                              </span>
                              <span className="v3-mono v3-dim text-xs" style={{ fontSize: 9.5 }}>({pos.unrealizedPnlPct > 0 ? "+" : ""}{pos.unrealizedPnlPct}%)</span>
                            </div>
                          </td>

                          {/* Protective Policy */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className="v3-mono text-xs font-semibold">{pos.protectivePolicyId.split(" ")[0]}</span>
                              <span className="v3-cell-sub text-xs" style={{ fontSize: 9.5 }}>{pos.trailState}</span>
                            </div>
                          </td>

                          {/* Reconciliation */}
                          <td>
                            <span className={`v3-status-badge ${isCleanRecon ? "ok" : "warn"}`}>
                              <Dot tone={isCleanRecon ? "ok" : "warn"} />
                              {pos.reconciliationState.replace("_", " ")}
                            </span>
                          </td>

                          {/* Actions */}
                          <td style={{ textAlign: "right" }} onClick={(e) => e.stopPropagation()}>
                            <button
                              type="button"
                              className="v3-btn ghost mini"
                              onClick={() => setSelectedPosition(pos)}
                              id={`inspect-pos-btn-${pos.id}`}
                              title="Inspect position details"
                            >
                              Inspect
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
         TAB 3: ORDERS & EXECUTIONS
         ════════════════════════════════════════════════════════════ */}
      {activeTab === "orders" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }} id="section-orders-oversight">
          <Panel label="Order Lifecycle &amp; Fill Evidence Ledger (Multi-Axis Separation)" meta={`${filteredOrders.length} orders`} className="v3-sp12">
            <div className="v3-table-wrap">
              <table className="v3-table" id="owner-orders-table">
                <thead>
                  <tr>
                    <th style={{ whiteSpace: "nowrap" }}>ORDER ID &amp; STRATEGY</th>
                    <th style={{ whiteSpace: "nowrap" }}>ENV</th>
                    <th style={{ whiteSpace: "nowrap" }}>INTENT (SIDE · QTY · PRICE)</th>
                    <th style={{ whiteSpace: "nowrap" }}>RISK DECISION</th>
                    <th style={{ whiteSpace: "nowrap" }}>ROUTING STATE</th>
                    <th style={{ whiteSpace: "nowrap" }}>EXECUTION STATE</th>
                    <th style={{ whiteSpace: "nowrap" }}>FILL SUMMARY</th>
                    <th style={{ whiteSpace: "nowrap" }}>RECONCILIATION</th>
                    <th style={{ textAlign: "right", whiteSpace: "nowrap" }}>ACTIONS</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredOrders.length === 0 ? (
                    <tr>
                      <td colSpan={9} style={{ textAlign: "center", padding: "28px", color: "var(--v3-ink-dim)" }}>
                        No orders match filter.
                      </td>
                    </tr>
                  ) : (
                    filteredOrders.map((o) => {
                      const isLive = o.environment === "LIVE / SAMPLE";
                      const isFilled = o.executionState === "FILLED";
                      const isRiskApproved = o.riskOutcome === "APPROVED";
                      const isCleanRecon = o.reconciliationState === "MATCH_HEALTHY";

                      return (
                        <tr
                          key={o.id}
                          className="v3-table-row"
                          id={`order-row-${o.id}`}
                          style={{ cursor: "pointer" }}
                          onClick={() => setSelectedOrder(o)}
                        >
                          {/* ID & Strategy */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className="v3-mono font-bold text-xs text-sky-400">{o.orderId}</span>
                              <span className="font-semibold text-xs">{o.strategyName}</span>
                            </div>
                          </td>

                          {/* Env */}
                          <td>
                            <span className={`v3-chip ${isLive ? "warn" : "ok"}`} style={{ fontSize: 9 }}>
                              {o.environment}
                            </span>
                          </td>

                          {/* Intent */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className="v3-mono font-bold text-xs">{o.side} {o.requestedQty} @ ₹{o.requestedPrice.toFixed(2)}</span>
                              <span className="v3-mono v3-dim text-xs" style={{ fontSize: 9.5 }}>{o.instrument} ({o.orderType})</span>
                            </div>
                          </td>

                          {/* Risk Decision */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className={`v3-status-badge ${isRiskApproved ? "ok" : "neg"}`}>
                                <Dot tone={isRiskApproved ? "ok" : "neg"} />
                                {o.riskOutcome}
                              </span>
                              {o.riskReason && (
                                <span className="v3-cell-sub text-xs" style={{ fontSize: 9, color: "var(--v3-loss-text)", maxWidth: 140 }}>
                                  {o.riskReason.split(":")[0]}
                                </span>
                              )}
                            </div>
                          </td>

                          {/* Routing State */}
                          <td>
                            <span className="v3-mono text-xs font-semibold">{o.routingState}</span>
                          </td>

                          {/* Execution State */}
                          <td>
                            <span className={`v3-status-badge ${isFilled ? "ok" : o.executionState === "QUEUED" ? "warn" : "neg"}`}>
                              <Dot tone={isFilled ? "ok" : o.executionState === "QUEUED" ? "warn" : "neg"} />
                              {o.executionState}
                            </span>
                          </td>

                          {/* Fill Summary */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className="v3-mono font-bold text-xs">{o.filledQty} / {o.requestedQty} filled</span>
                              {o.avgFillPrice && (
                                <span className="v3-mono v3-dim text-xs" style={{ fontSize: 9.5 }}>Avg: ₹{o.avgFillPrice.toFixed(2)}</span>
                              )}
                            </div>
                          </td>

                          {/* Reconciliation */}
                          <td>
                            <span className={`v3-status-badge ${isCleanRecon ? "ok" : "warn"}`}>
                              <Dot tone={isCleanRecon ? "ok" : "warn"} />
                              {o.reconciliationState.replace("_", " ")}
                            </span>
                          </td>

                          {/* Actions */}
                          <td style={{ textAlign: "right" }} onClick={(e) => e.stopPropagation()}>
                            <div style={{ display: "inline-flex", gap: 6 }}>
                              <button
                                type="button"
                                className="v3-btn ghost mini"
                                onClick={() => setSelectedOrder(o)}
                                id={`inspect-order-btn-${o.id}`}
                                title="Inspect multi-axis order lifecycle"
                              >
                                Inspect
                              </button>
                              {o.executionState === "QUEUED" && (
                                <button
                                  type="button"
                                  className="v3-btn mini danger-ghost"
                                  onClick={() => handleRequestCancelOrder(o.id)}
                                  id={`request-cancel-order-btn-${o.id}`}
                                  title="Simulated cancel request (Dev Preview)"
                                >
                                  {o.cancelRequested ? "Cancel Requested" : "Cancel"}
                                </button>
                              )}
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
         INSPECTION DRAWERS
         ════════════════════════════════════════════════════════════ */}

      {/* 1. Portfolio Drawer */}
      {selectedPortfolio && (
        <Drawer
          open={Boolean(selectedPortfolio)}
          title={selectedPortfolio.portfolioId}
          sub={`${selectedPortfolio.accountRef} · ${selectedPortfolio.environment}`}
          onClose={() => setSelectedPortfolio(null)}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <Panel label="Portfolio Identity &amp; Connection Context">
              <dl style={{ margin: 0 }}>
                <KV k="Portfolio ID" v={<span className="v3-mono font-bold">{selectedPortfolio.portfolioId}</span>} />
                <KV k="Account Reference" v={<span className="v3-mono">{selectedPortfolio.accountRef}</span>} />
                <KV k="Environment" v={<span className="v3-chip ok" style={{ fontSize: 9.5 }}>{selectedPortfolio.environment}</span>} />
                <KV k="Broker Connector Binding" v={<span className="v3-mono">{selectedPortfolio.brokerConnection}</span>} />
                <KV k="Currency Base" v={selectedPortfolio.currency} />
              </dl>
            </Panel>

            <Panel label="Capital, Exposure &amp; Margin Allocation">
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <KV k="Cash Basis" v={<span className="v3-mono font-bold">₹{selectedPortfolio.cash.toLocaleString()}</span>} />
                <KV k="Reserved Capital" v={<span className="v3-mono font-bold">₹{selectedPortfolio.reservedCapital.toLocaleString()}</span>} />
                <KV k="Market Exposure" v={<span className="v3-mono font-bold text-sky-400">₹{selectedPortfolio.exposure.toLocaleString()}</span>} />
                <KV k="Margin Utilization" v={<span className="v3-mono font-bold">{selectedPortfolio.marginUtilizationPct}%</span>} />
                <KV k="Realized P&L" v={<span className="v3-mono font-bold text-emerald-400">{selectedPortfolio.realizedPnl}</span>} />
                <KV k="Unrealized P&L" v={<span className="v3-mono font-bold">{selectedPortfolio.unrealizedPnl}</span>} />
              </div>
            </Panel>

            <Panel label="Reconciliation &amp; Engine Health">
              <dl style={{ margin: 0 }}>
                <KV
                  k="Reconciliation Status"
                  v={
                    <span className={`v3-status-badge ${selectedPortfolio.reconciliationState === "MATCH_HEALTHY" ? "ok" : "warn"}`}>
                      <Dot tone={selectedPortfolio.reconciliationState === "MATCH_HEALTHY" ? "ok" : "warn"} />
                      {selectedPortfolio.reconciliationState}
                    </span>
                  }
                />
                {selectedPortfolio.reconciliationDetails && (
                  <KV k="Discrepancy Details" v={<span style={{ color: "var(--v3-warn-text)", fontWeight: 600 }}>{selectedPortfolio.reconciliationDetails}</span>} />
                )}
                <KV k="Last Scan Timestamp" v={<span className="v3-mono">{selectedPortfolio.lastReconciliationAt}</span>} />
              </dl>
            </Panel>

            <Panel label="Owner Administrative Governance">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div className="font-semibold text-xs">Portfolio Administrative Hold</div>
                  <div className="v3-dim text-xs">Governs new order submission ceiling (Past balances untouched)</div>
                </div>
                <button
                  type="button"
                  className={`v3-btn mini ${selectedPortfolio.ownerAllowance === "HOLD" ? "primary" : "danger-ghost"}`}
                  onClick={() => handleTogglePortfolioHold(selectedPortfolio.id, selectedPortfolio.ownerAllowance)}
                  id="drawer-toggle-port-hold-btn"
                  title="Interactive Prototype — Local State"
                >
                  {selectedPortfolio.ownerAllowance === "HOLD" ? "Allow Portfolio" : "Place Hold"}
                </button>
              </div>
            </Panel>

            <Panel label="Audit Ledger">
              <div className="v3-rows">
                {selectedPortfolio.auditEvents.map((ev, idx) => (
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

      {/* 2. Position Drawer */}
      {selectedPosition && (
        <Drawer
          open={Boolean(selectedPosition)}
          title={selectedPosition.positionId}
          sub={`${selectedPosition.instrument} · ${selectedPosition.strategyName}`}
          onClose={() => setSelectedPosition(null)}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <Panel label="Position Specification &amp; Strategy Provenance">
              <dl style={{ margin: 0 }}>
                <KV k="Position ID" v={<span className="v3-mono font-bold">{selectedPosition.positionId}</span>} />
                <KV k="Portfolio / Account" v={<span className="v3-mono">{selectedPosition.portfolioId}</span>} />
                <KV k="Strategy Binding" v={<span className="v3-mono">{selectedPosition.strategyId} ({selectedPosition.strategyName})</span>} />
                <KV k="Instrument / Underlying" v={<span className="v3-mono font-bold">{selectedPosition.instrument} ({selectedPosition.underlying})</span>} />
                <KV k="Direction / Quantity" v={<span className="v3-mono font-bold">{selectedPosition.side} {selectedPosition.quantity} contracts</span>} />
                <KV k="Average Entry Price" v={<span className="v3-mono">₹{selectedPosition.avgEntryPrice.toFixed(2)}</span>} />
                <KV k="Current Mark Price" v={<span className="v3-mono font-bold">₹{selectedPosition.markPrice.toFixed(2)}</span>} />
                <KV k="Unrealized P&L" v={<span className="v3-mono font-bold text-emerald-400">{selectedPosition.unrealizedPnl} ({selectedPosition.unrealizedPnlPct}%)</span>} />
              </dl>
            </Panel>

            <Panel label="Protective Plan &amp; Risk Envelope Execution" meta="Non-Bypassable">
              <dl style={{ margin: 0 }}>
                <KV k="Protective Policy ID" v={<span className="v3-mono font-bold">{selectedPosition.protectivePolicyId}</span>} />
                <KV k="Stop Loss Level" v={<span className="v3-mono font-bold text-rose-400">₹{selectedPosition.stopLossPrice.toFixed(2)}</span>} />
                {selectedPosition.targetPrice && (
                  <KV k="Profit Target Level" v={<span className="v3-mono font-bold text-emerald-400">₹{selectedPosition.targetPrice.toFixed(2)}</span>} />
                )}
                <KV k="Trailing Stop Lifecycle State" v={<span className="v3-mono">{selectedPosition.trailState}</span>} />
              </dl>
            </Panel>

            <Panel label="Reconciliation &amp; Ledger State">
              <dl style={{ margin: 0 }}>
                <KV
                  k="Reconciliation State"
                  v={
                    <span className={`v3-status-badge ${selectedPosition.reconciliationState === "MATCH_HEALTHY" ? "ok" : "warn"}`}>
                      <Dot tone={selectedPosition.reconciliationState === "MATCH_HEALTHY" ? "ok" : "warn"} />
                      {selectedPosition.reconciliationState}
                    </span>
                  }
                />
                <KV k="Position Lifecycle" v={selectedPosition.positionState} />
                <KV k="Opened Timestamp" v={<span className="v3-mono">{selectedPosition.openedAt}</span>} />
                <KV k="Last Telemetry Update" v={<span className="v3-mono">{selectedPosition.updatedAt}</span>} />
              </dl>
            </Panel>
          </div>
        </Drawer>
      )}

      {/* 3. Order Drawer (Multi-Axis Lifecycle Breakdown) */}
      {selectedOrder && (
        <Drawer
          open={Boolean(selectedOrder)}
          title={selectedOrder.orderId}
          sub={`${selectedOrder.side} ${selectedOrder.requestedQty} ${selectedOrder.instrument} (${selectedOrder.strategyName})`}
          onClose={() => setSelectedOrder(null)}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {/* Multi-Axis Summary Strip */}
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
                <div className="v3-dim text-xs">RISK DECISION</div>
                <div style={{ marginTop: 2 }}>
                  <span className={`v3-status-badge ${selectedOrder.riskOutcome === "APPROVED" ? "ok" : "neg"}`}>
                    <Dot tone={selectedOrder.riskOutcome === "APPROVED" ? "ok" : "neg"} />
                    {selectedOrder.riskOutcome}
                  </span>
                </div>
              </div>
              <div>
                <div className="v3-dim text-xs">ROUTING STATE</div>
                <div style={{ marginTop: 2 }}>
                  <span className="v3-mono text-xs font-semibold">{selectedOrder.routingState}</span>
                </div>
              </div>
              <div>
                <div className="v3-dim text-xs">EXECUTION STATE</div>
                <div style={{ marginTop: 2 }}>
                  <span className={`v3-status-badge ${selectedOrder.executionState === "FILLED" ? "ok" : selectedOrder.executionState === "QUEUED" ? "warn" : "neg"}`}>
                    <Dot tone={selectedOrder.executionState === "FILLED" ? "ok" : selectedOrder.executionState === "QUEUED" ? "warn" : "neg"} />
                    {selectedOrder.executionState}
                  </span>
                </div>
              </div>
              <div>
                <div className="v3-dim text-xs">RECONCILIATION</div>
                <div style={{ marginTop: 2 }}>
                  <span className={`v3-status-badge ${selectedOrder.reconciliationState === "MATCH_HEALTHY" ? "ok" : "warn"}`}>
                    <Dot tone={selectedOrder.reconciliationState === "MATCH_HEALTHY" ? "ok" : "warn"} />
                    {selectedOrder.reconciliationState.replace("_", " ")}
                  </span>
                </div>
              </div>
            </div>

            {/* 1. Order Intent Specification */}
            <Panel label="1. Order Intent &amp; Strategy Sizing Request">
              <dl style={{ margin: 0 }}>
                <KV k="Order ID / Client ID" v={<span className="v3-mono font-bold">{selectedOrder.orderId} ({selectedOrder.clientOrderId})</span>} />
                <KV k="Strategy / Version" v={<span className="v3-mono">{selectedOrder.strategyId} ({selectedOrder.strategyName} · {selectedOrder.strategyVersion})</span>} />
                <KV k="Target Portfolio" v={<span className="v3-mono">{selectedOrder.portfolioId}</span>} />
                <KV k="Side / Order Type" v={<span className="v3-mono font-bold">{selectedOrder.side} ({selectedOrder.orderType})</span>} />
                <KV k="Requested Quantity" v={<span className="v3-mono">{selectedOrder.requestedQty} contracts</span>} />
                <KV k="Requested Price" v={<span className="v3-mono">₹{selectedOrder.requestedPrice.toFixed(2)}</span>} />
                <KV k="Time In Force" v={<span className="v3-mono">{selectedOrder.timeInForce}</span>} />
              </dl>
            </Panel>

            {/* 2. Risk Gate Outcome */}
            <Panel label="2. Pre-Trade Risk Gate Outcome" meta="Non-Bypassable">
              <dl style={{ margin: 0 }}>
                <KV
                  k="Risk Outcome"
                  v={
                    <span className={`v3-status-badge ${selectedOrder.riskOutcome === "APPROVED" ? "ok" : "neg"}`}>
                      <Dot tone={selectedOrder.riskOutcome === "APPROVED" ? "ok" : "neg"} />
                      {selectedOrder.riskOutcome}
                    </span>
                  }
                />
                {selectedOrder.riskReason && (
                  <KV k="Rejection Reason" v={<span style={{ color: "var(--v3-loss-text)", fontWeight: 600 }}>{selectedOrder.riskReason}</span>} />
                )}
                <KV k="Risk Capital Committed" v={<span className="v3-mono font-bold">₹{selectedOrder.riskCapitalAllocated.toLocaleString()}</span>} />
              </dl>
            </Panel>

            {/* 3. Protective / OCO Relationships */}
            <Panel label="3. Protective Plan &amp; OCO Relationship">
              <dl style={{ margin: 0 }}>
                <KV k="Protective Policy ID" v={<span className="v3-mono font-bold">{selectedOrder.protectivePolicyId}</span>} />
                {selectedOrder.ocoGroupId && (
                  <KV k="OCO Group ID" v={<span className="v3-mono font-bold text-sky-400">{selectedOrder.ocoGroupId}</span>} />
                )}
                {selectedOrder.stopLossRef && (
                  <KV k="Linked Stop Loss Level" v={<span className="v3-mono text-rose-400">₹{selectedOrder.stopLossRef.toFixed(2)}</span>} />
                )}
                {selectedOrder.targetRef && (
                  <KV k="Linked Target Level" v={<span className="v3-mono text-emerald-400">₹{selectedOrder.targetRef.toFixed(2)}</span>} />
                )}
              </dl>
            </Panel>

            {/* 4. Execution Fills Ledger (Read-Only) */}
            <Panel label="4. Execution Fill Evidence Ledger (Read-Only)">
              {selectedOrder.fills.length === 0 ? (
                <div className="v3-dim text-xs" style={{ padding: "10px 0" }}>No execution fills logged yet (Order state: {selectedOrder.executionState}).</div>
              ) : (
                <div className="v3-table-wrap">
                  <table className="v3-table" style={{ fontSize: 11 }}>
                    <thead>
                      <tr>
                        <th>FILL ID</th>
                        <th>QTY</th>
                        <th>PRICE</th>
                        <th>VENUE</th>
                        <th>FEES</th>
                        <th>TIMESTAMP</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedOrder.fills.map((f) => (
                        <tr key={f.fillId}>
                          <td className="v3-mono font-bold">{f.fillId}</td>
                          <td className="v3-mono">{f.quantity}</td>
                          <td className="v3-mono">₹{f.price.toFixed(2)}</td>
                          <td className="v3-mono">{f.executionVenue}</td>
                          <td className="v3-dim">{f.feesEstimated}</td>
                          <td className="v3-mono v3-dim text-xs">{f.timestamp}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>

            {/* 5. Cancellation Request Actions */}
            {selectedOrder.executionState === "QUEUED" && (
              <Panel label="5. Simulated Cancel Request Action">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <div className="font-semibold text-xs">Request Order Cancellation</div>
                    <div className="v3-dim text-xs">Simulate cancel submission (Execution state updates only upon broker acknowledgment)</div>
                  </div>
                  <button
                    type="button"
                    className="v3-btn mini danger-ghost"
                    onClick={() => handleRequestCancelOrder(selectedOrder.id)}
                    id="drawer-request-cancel-order-btn"
                    title="Simulated cancel request (Dev Preview)"
                  >
                    {selectedOrder.cancelRequested ? "Cancel Requested" : "Submit Cancel Request"}
                  </button>
                </div>
              </Panel>
            )}

            {/* 6. Order Audit Trail */}
            <Panel label="6. Order Lifecycle Audit Stream">
              <div className="v3-rows">
                {selectedOrder.auditEvents.map((ev, idx) => (
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
