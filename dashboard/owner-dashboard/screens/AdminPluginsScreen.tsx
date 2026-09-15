import { LiveReadinessRuntime } from "../../shared/components/LiveReadinessRuntime";
import { OwnerConnectionsDeployments } from "../../shared/components/OwnerConnectionsDeployments";
import React, { useState, useMemo, useRef, useEffect } from "react";
import { Icon } from "../../shared/icons/V3Icons";
import { Panel, Drawer, KV, TruthChip, Dot } from "../../shared/utilities/V3Chrome";
import {
  getStoredOwnerConnections,
  updateOwnerConnectionAllowance,
  updateCapabilityAllowance,
  getStoredOwnerDatasets,
  updateDatasetApproval,
  simulateDatasetVerification,
  simulateDatasetGapRepair,
  getStoredOwnerPlugins,
  updateOwnerPluginAllowance,
  computeCapabilityEffective,
  computeDatasetEffectiveReadiness,
  computePluginEffective,
  type OwnerConnectionRow,
  type OwnerDatasetRow,
  type OwnerPluginRow,
  type ConnectionCapability,
  type ConnectionOwnerAllowance,
  type CapabilityOwnerAllowance,
  type DatasetOwnerApproval,
  type PluginOwnerAllowance,
} from "../../sampleData";
import {
  queryOwnerConnections,
  updateBackendConnectionAllowance,
  updateBackendCapabilityAllowance,
  queryOwnerDatasets,
  updateBackendDatasetApproval,
  manualHistoricalSync,
  repairHistoricalGaps,
  type IntegrationResult,
} from "../../shared/services/integrationClient";

const ExistingPluginsScreen: React.FC<{ previewMode?: boolean }> = ({ previewMode = false }) => {
  const [activeMainTab, setActiveMainTab] = useState<"connections" | "historical" | "plugins">("connections");

  // State collections
  const [connections, setConnections] = useState<OwnerConnectionRow[]>(() => getStoredOwnerConnections());
  const [connectionsIntegration, setConnectionsIntegration] = useState<IntegrationResult<OwnerConnectionRow[]>>({
    data: getStoredOwnerConnections(),
    source: "SAMPLE_FALLBACK",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: true,
  });

  const [datasets, setDatasets] = useState<OwnerDatasetRow[]>(() => getStoredOwnerDatasets());
  const [datasetsIntegration, setDatasetsIntegration] = useState<IntegrationResult<OwnerDatasetRow[]>>({
    data: getStoredOwnerDatasets(),
    source: "SAMPLE_FALLBACK",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: true,
  });

  const [plugins, setPlugins] = useState<OwnerPluginRow[]>(() => getStoredOwnerPlugins());

  // Filter & Search states
  const [connFilter, setConnFilter] = useState<string>("ALL");
  const [datasetFilter, setDatasetFilter] = useState<string>("ALL");
  const [pluginFilter, setPluginFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  // Inspection Drawer states
  const [selectedConnection, setSelectedConnection] = useState<OwnerConnectionRow | null>(null);
  const [selectedDataset, setSelectedDataset] = useState<OwnerDatasetRow | null>(null);
  const [selectedPlugin, setSelectedPlugin] = useState<OwnerPluginRow | null>(null);
  const [drawerTab, setDrawerTab] = useState<string>("overview");

  // Prototype Acquisition Form State
  const [acqSource, setAcqSource] = useState("SX-CONN-TRUEDATA-01");
  const [acqMarket, setAcqMarket] = useState("NSE_INDEX");
  const [acqInstrument, setAcqInstrument] = useState("NIFTY");
  const [acqSegment, setAcqSegment] = useState("Index Spot");
  const [acqTimeframe, setAcqTimeframe] = useState("5m");
  const [acqStartDate, setAcqStartDate] = useState("2024-01-01");
  const [acqEndDate, setAcqEndDate] = useState("2026-08-31");
  const [acqDataType, setAcqDataType] = useState("OHLCV Candles");
  const [acqMode, setAcqMode] = useState("Full Range Acquisition");

  // Feedback Notification Banner
  const [feedback, setFeedback] = useState<{ message: string; type: "ok" | "warn" | "error" } | null>(null);
  const feedbackTimerRef = useRef<any>(null);

  const showFeedback = (message: string, type: "ok" | "warn" | "error" = "ok") => {
    if (feedbackTimerRef.current) clearTimeout(feedbackTimerRef.current);
    setFeedback({ message, type });
    feedbackTimerRef.current = setTimeout(() => setFeedback(null), 5000);
  };

  const loadData = async () => {
    if (previewMode) { refreshAll(); return; }
    try {
      const [connRes, dsRes] = await Promise.all([
        queryOwnerConnections(),
        queryOwnerDatasets(),
      ]);
      setConnectionsIntegration(connRes);
      setConnections(connRes.data);
      setDatasetsIntegration(dsRes);
      setDatasets(dsRes.data);

      if (selectedConnection) {
        const u = connRes.data.find((c) => c.id === selectedConnection.id || c.connectionId === selectedConnection.connectionId);
        if (u) setSelectedConnection(u);
      }
      if (selectedDataset) {
        const u = dsRes.data.find((d) => d.id === selectedDataset.id || d.datasetId === selectedDataset.datasetId);
        if (u) setSelectedDataset(u);
      }
    } catch {
      refreshAll();
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const refreshAll = () => {
    const updatedConns = getStoredOwnerConnections();
    const updatedDatasets = getStoredOwnerDatasets();
    const updatedPlugins = getStoredOwnerPlugins();

    setConnections(updatedConns);
    setDatasets(updatedDatasets);
    setPlugins(updatedPlugins);

    if (selectedConnection) {
      const u = updatedConns.find((c) => c.id === selectedConnection.id || c.connectionId === selectedConnection.connectionId);
      if (u) setSelectedConnection(u);
    }
    if (selectedDataset) {
      const u = updatedDatasets.find((d) => d.id === selectedDataset.id || d.datasetId === selectedDataset.datasetId);
      if (u) setSelectedDataset(u);
    }
    if (selectedPlugin) {
      const u = updatedPlugins.find((p) => p.id === selectedPlugin.id || p.pluginId === selectedPlugin.pluginId);
      if (u) setSelectedPlugin(u);
    }
  };

  // 1. Filtered Connections
  const filteredConnections = useMemo(() => {
    return connections.filter((c) => {
      const hasAvailable = c.capabilities.some((cap) => cap.effectiveStatus === "AVAILABLE");
      if (connFilter === "HEALTHY" && c.healthState !== "HEALTHY") return false;
      if (connFilter === "DEGRADED" && c.healthState !== "DEGRADED") return false;
      if (connFilter === "EXPIRED" && c.authState !== "EXPIRED") return false;
      if (connFilter === "OFFLINE" && c.healthState !== "OFFLINE") return false;
      if (connFilter === "HELD" && c.ownerAllowance !== "HOLD") return false;
      if (connFilter === "ACTIVE" && !hasAvailable) return false;

      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          c.name.toLowerCase().includes(q) ||
          c.connectionId.toLowerCase().includes(q) ||
          c.provider.toLowerCase().includes(q) ||
          c.accountAlias.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [connections, connFilter, searchQuery]);

  // 2. Filtered Datasets
  const filteredDatasets = useMemo(() => {
    return datasets.filter((d) => {
      const isBacktestReady = d.effectiveBacktestReadiness === "READY_FOR_BACKTEST";
      if (datasetFilter === "READY_FOR_BACKTEST" && !isBacktestReady) return false;
      if (datasetFilter === "SYSTEM_BLOCKED" && d.systemReadiness !== "BLOCKED") return false;
      if (datasetFilter === "GAPS" && d.gapStatus !== "GAPS_DETECTED") return false;
      if (datasetFilter === "HELD" && d.ownerApproval !== "HOLD") return false;
      if (datasetFilter === "REJECTED" && d.ownerApproval !== "REJECTED") return false;

      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          d.datasetId.toLowerCase().includes(q) ||
          d.instrument.toLowerCase().includes(q) ||
          d.source.toLowerCase().includes(q) ||
          d.timeframe.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [datasets, datasetFilter, searchQuery]);

  // 3. Filtered Plugins
  const filteredPlugins = useMemo(() => {
    return plugins.filter((p) => {
      const eff = computePluginEffective(p.compatibilityStatus, p.permissionReadiness, p.ownerAllowance);
      if (pluginFilter === "COMPATIBLE" && p.compatibilityStatus !== "COMPATIBLE") return false;
      if (pluginFilter === "INCOMPATIBLE" && p.compatibilityStatus !== "INCOMPATIBLE") return false;
      if (pluginFilter === "HELD" && p.ownerAllowance !== "HOLD") return false;
      if (pluginFilter === "ACTIVE" && eff.status !== "ACTIVE") return false;
      if (pluginFilter === "BUILTIN" && p.discoveryState !== "BUILTIN") return false;

      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          p.name.toLowerCase().includes(q) ||
          p.pluginId.toLowerCase().includes(q) ||
          p.category.toLowerCase().includes(q) ||
          p.author.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [plugins, pluginFilter, searchQuery]);

  // Actions: Connections
  const handleToggleConnectionAllowance = async (id: string, currentAllowance: ConnectionOwnerAllowance) => {
    if (previewMode) { showFeedback("DEV PREVIEW — connection governance is read-only", "warn"); return; }
    const next: ConnectionOwnerAllowance = currentAllowance === "ALLOWED" ? "HOLD" : "ALLOWED";
    const res = await updateBackendConnectionAllowance(id, next, undefined);
    if (res.success) {
      await loadData();
      showFeedback(res.data?.message || `Connection allowance set to ${next}.`, next === "ALLOWED" ? "ok" : "warn");
    } else {
      showFeedback(res.error || "Action blocked.", "error");
    }
  };

  const handleToggleCapabilityAllowance = async (connId: string, capKey: ConnectionCapability, currentAllowance: CapabilityOwnerAllowance) => {
    if (previewMode) { showFeedback("DEV PREVIEW — capability governance is read-only", "warn"); return; }
    const next: CapabilityOwnerAllowance = currentAllowance === "ALLOWED" ? "HOLD" : "ALLOWED";
    const res = await updateBackendCapabilityAllowance(connId, capKey, next, undefined);
    if (res.success) {
      await loadData();
      showFeedback(res.data?.message || `Capability ${capKey} allowance set to ${next}.`, next === "ALLOWED" ? "ok" : "warn");
    } else {
      showFeedback(res.error || "Action blocked.", "error");
    }
  };

  const handleTestConnection = (name: string) => {
    showFeedback(`Simulated latency probe for "${name}": 14ms (HTTP 200 OK · SIMULATED ACTION)`, "ok");
  };

  // Actions: Datasets
  const handleToggleDatasetApproval = async (id: string, currentApproval: DatasetOwnerApproval) => {
    if (previewMode) { showFeedback("DEV PREVIEW — dataset governance is read-only", "warn"); return; }
    const next: DatasetOwnerApproval = currentApproval === "APPROVED" ? "HOLD" : "APPROVED";
    const res = await updateBackendDatasetApproval(id, next, undefined);
    if (res.success) {
      await loadData();
      if (res.data?.effective === "READY_FOR_BACKTEST") {
        showFeedback(res.data?.message || "Dataset approved for backtesting.", "ok");
      } else {
        showFeedback(res.data?.message || "Dataset placed on hold / rejected.", "warn");
      }
    } else {
      showFeedback(res.error || "Action blocked.", "error");
    }
  };

  const handleAcquireDataset = async (e: React.FormEvent) => {
    e.preventDefault();
    if (previewMode) {
      showFeedback(
        `Acquisition request scheduled for ${acqInstrument} (${acqTimeframe} · ${acqStartDate} to ${acqEndDate}) via ${acqSource}. (DEV PREVIEW · SIMULATED)`,
        "ok"
      );
      return;
    }
    const res = await manualHistoricalSync(acqInstrument, acqTimeframe, acqStartDate, acqEndDate, undefined, false);
    if (res.success) {
      await loadData();
      showFeedback(`Historical synchronization completed for ${acqInstrument} (${acqTimeframe}). Job ID: ${res.data?.job?.job_id || "DONE"}`, "ok");
    } else {
      showFeedback(res.error || "Historical synchronization failed.", "error");
    }
  };

  const handleRepairGaps = async (datasetId: string) => {
    if (previewMode) {
      const res = simulateDatasetGapRepair(datasetId);
      refreshAll();
      showFeedback(res.message, "ok");
      return;
    }
    const res = await repairHistoricalGaps(datasetId);
    if (res.success) {
      await loadData();
      showFeedback(`Gap repair complete for dataset ${datasetId}. Status: GAPS_CLEAR`, "ok");
    } else {
      showFeedback(res.error || "Gap repair failed.", "error");
    }
  };

  const handleReverifySimulated = (datasetId: string) => {
    const res = simulateDatasetVerification(datasetId);
    refreshAll();
    showFeedback(res.message, "ok");
  };

  // Actions: Plugins
  const handleTogglePluginAllowance = (id: string, currentAllowance: PluginOwnerAllowance) => {
    const next: PluginOwnerAllowance = currentAllowance === "ALLOWED" ? "HOLD" : "ALLOWED";
    const res = updateOwnerPluginAllowance(id, next, undefined, "OWNER-001");
    refreshAll();
    showFeedback(res.message, res.effective === "ACTIVE" ? "ok" : "warn");
  };

  return (
    <>
      {/* Screen Header */}
      <div className="v3-screen-head" id="connections-plugins-header">
        <div>
          <h2 className="v3-screen-title">Connections, Plugins &amp; Market Data</h2>
          <p className="v3-screen-sub">
            Institutional Gateway Management · Broker APIs, Market Feeds, Historical Data Engine &amp; Plugin Extensions
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <TruthChip
            kind={connectionsIntegration.source === "BACKEND" && datasetsIntegration.source === "BACKEND" ? "REAL" : "SAMPLE"}
            title={connectionsIntegration.source === "BACKEND" && datasetsIntegration.source === "BACKEND" ? "Authoritative Broker Connectors & Datasets (Backend SQLite)" : "DEV PREVIEW / SAMPLE — Prototype Configuration Oversight"}
          />
          <button
            type="button"
            className="v3-btn ghost mini"
            onClick={loadData}
            id="refresh-plugins-screen-btn"
            title="Refresh connections & plugins fleet"
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
          id="connections-feedback-banner"
          style={{ marginBottom: 14 }}
        >
          {feedback.type === "ok" ? "✓" : "⚠️"} {feedback.message}
        </div>
      )}

      {/* Architecture & Authority Boundary Notice */}
      <div
        className="security-notice-box"
        id="connections-authority-banner"
        style={{
          marginBottom: 16,
          borderColor: "rgba(2, 132, 199, 0.4)",
          background: "rgba(2, 132, 199, 0.06)",
        }}
      >
        <span className="sec-notice-icon" style={{ fontSize: 18 }}>🛡️</span>
        <div>
          <div style={{ fontWeight: 600, color: "var(--v3-sky-text)", fontSize: 12, marginBottom: 2 }}>
            GRANULAR CAPABILITY READINESS, DATASET GOVERNANCE &amp; SECRET-BOUNDARY SEPARATION
          </div>
          <span style={{ fontSize: 11.5, color: "var(--v3-ink-2)" }}>
            A healthy connection does not imply trading execution authority. Effective availability is computed independently per capability:{" "}
            <strong>System Readiness</strong> ∧ <strong>Auth/Permission State</strong> ∧ <strong>Owner Allowance</strong>.{" "}
            All credential values are masked references (<code className="v3-mono">ak •••• ••7f</code>). Frontend prototype does not store production secrets.
          </span>
        </div>
      </div>

      {/* Main Section Navigation Bar */}
      <div className="v3-card" style={{ padding: "6px 12px", marginBottom: 16, display: "flex", gap: 8 }} id="connections-nav-bar">
        <button
          type="button"
          className={`v3-btn mini ${activeMainTab === "connections" ? "primary" : "ghost"}`}
          onClick={() => {
            setActiveMainTab("connections");
            setSearchQuery("");
          }}
          id="tab-btn-connections"
        >
          1. Broker &amp; API Connections ({connections.length})
        </button>
        <button
          type="button"
          className={`v3-btn mini ${activeMainTab === "historical" ? "primary" : "ghost"}`}
          onClick={() => {
            setActiveMainTab("historical");
            setSearchQuery("");
          }}
          id="tab-btn-historical-data"
        >
          2. Historical Data Manager ({datasets.length} Datasets)
        </button>
        <button
          type="button"
          className={`v3-btn mini ${activeMainTab === "plugins" ? "primary" : "ghost"}`}
          onClick={() => {
            setActiveMainTab("plugins");
            setSearchQuery("");
          }}
          id="tab-btn-plugin-registry"
        >
          3. Plugin Registry &amp; Extensions ({plugins.length})
        </button>
      </div>

      {/* ════════════════════════════════════════════════════════════
         SECTION 1: BROKER & API CONNECTIONS
         ════════════════════════════════════════════════════════════ */}
      {activeMainTab === "connections" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }} id="section-broker-connections">
          {/* KPI Deck */}
          <div className="v3-kpi-deck" id="connections-kpi-deck" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 12 }}>
            <div className="v3-card" style={{ padding: 14 }}>
              <div className="v3-dim text-xs">TOTAL CONNECTORS</div>
              <div className="v3-stat-big" style={{ fontSize: 24, fontWeight: 700, marginTop: 4 }}>{connections.length}</div>
              <div className="v3-cell-sub text-xs">Configured fleet</div>
            </div>
            <div className="v3-card" style={{ padding: 14 }}>
              <div className="v3-dim text-xs">HEALTHY TRANSPORT</div>
              <div className="v3-stat-big" style={{ fontSize: 24, fontWeight: 700, marginTop: 4, color: "var(--v3-profit)" }}>
                {connections.filter((c) => c.healthState === "HEALTHY").length}
              </div>
              <div className="v3-cell-sub text-xs">Transport reachable (&lt;20ms)</div>
            </div>
            <div className="v3-card" style={{ padding: 14 }}>
              <div className="v3-dim text-xs">EXPIRED / DEGRADED</div>
              <div className="v3-stat-big" style={{ fontSize: 24, fontWeight: 700, marginTop: 4, color: "var(--v3-warn-text)" }}>
                {connections.filter((c) => c.healthState === "DEGRADED" || c.authState === "EXPIRED").length}
              </div>
              <div className="v3-cell-sub text-xs">Requires token re-auth</div>
            </div>
            <div className="v3-card" style={{ padding: 14 }}>
              <div className="v3-dim text-xs">OFFLINE / HELD</div>
              <div className="v3-stat-big" style={{ fontSize: 24, fontWeight: 700, marginTop: 4, color: "var(--v3-loss-text)" }}>
                {connections.filter((c) => c.healthState === "OFFLINE" || c.ownerAllowance === "HOLD").length}
              </div>
              <div className="v3-cell-sub text-xs">Transport stopped / hold</div>
            </div>
          </div>

          {/* Filter Toolbar */}
          <div className="v3-card" style={{ padding: 10, display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 10 }} id="connections-toolbar">
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <button
                type="button"
                className={`v3-btn mini ${connFilter === "ALL" ? "primary" : "ghost"}`}
                onClick={() => setConnFilter("ALL")}
                id="filter-conn-all-btn"
              >
                All ({connections.length})
              </button>
              <button
                type="button"
                className={`v3-btn mini ${connFilter === "ACTIVE" ? "primary" : "ghost"}`}
                onClick={() => setConnFilter("ACTIVE")}
                id="filter-conn-active-btn"
              >
                Has Available Capabilities
              </button>
              <button
                type="button"
                className={`v3-btn mini ${connFilter === "HEALTHY" ? "primary" : "ghost"}`}
                onClick={() => setConnFilter("HEALTHY")}
                id="filter-conn-healthy-btn"
              >
                Healthy Transport
              </button>
              <button
                type="button"
                className={`v3-btn mini ${connFilter === "EXPIRED" ? "primary" : "ghost"}`}
                onClick={() => setConnFilter("EXPIRED")}
                id="filter-conn-expired-btn"
              >
                Expired Auth
              </button>
              <button
                type="button"
                className={`v3-btn mini ${connFilter === "HELD" ? "primary" : "ghost"}`}
                onClick={() => setConnFilter("HELD")}
                id="filter-conn-held-btn"
              >
                Owner Hold
              </button>
            </div>
            <div style={{ position: "relative", minWidth: 240 }}>
              <input
                type="text"
                placeholder="Search connections..."
                className="v3-input"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                id="conn-search-input"
                style={{ paddingLeft: 26, fontSize: 12, height: 30 }}
              />
              <span style={{ position: "absolute", left: 8, top: 6, color: "var(--v3-ink-dim)", fontSize: 12 }}>🔍</span>
            </div>
          </div>

          {/* Connections Table */}
          <Panel label="Configured Gateway &amp; Connector Inventory" meta={`${filteredConnections.length} endpoints`} className="v3-sp12">
            <div className="v3-table-wrap">
              <table className="v3-table" id="owner-connections-table">
                <thead>
                  <tr>
                    <th style={{ whiteSpace: "nowrap" }}>CONNECTION / PROVIDER</th>
                    <th style={{ whiteSpace: "nowrap" }}>ACCOUNT &amp; SECRET REF</th>
                    <th style={{ whiteSpace: "nowrap" }}>TRANSPORT HEALTH</th>
                    <th style={{ whiteSpace: "nowrap" }}>AUTH STATE</th>
                    <th style={{ whiteSpace: "nowrap" }}>OWNER ALLOWANCE</th>
                    <th style={{ whiteSpace: "nowrap" }}>GRANULAR CAPABILITIES (READINESS &amp; EFFECTIVE)</th>
                    <th style={{ textAlign: "right", whiteSpace: "nowrap" }}>ACTIONS</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredConnections.length === 0 ? (
                    <tr>
                      <td colSpan={7} style={{ textAlign: "center", padding: "28px", color: "var(--v3-ink-dim)" }}>
                        {connections.length === 0 ? "No broker connected" : "No connections match filter."}
                      </td>
                    </tr>
                  ) : (
                    filteredConnections.map((c) => {
                      const isHeld = c.ownerAllowance === "HOLD";

                      return (
                        <tr
                          key={c.id}
                          className="v3-table-row"
                          id={`conn-row-${c.id}`}
                          style={{ cursor: "pointer" }}
                          onClick={() => {
                            setSelectedConnection(c);
                            setDrawerTab("overview");
                          }}
                        >
                          {/* Connection & Provider */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className="font-semibold text-xs">{c.name}</span>
                              <div className="v3-cell-sub v3-mono text-xs" style={{ display: "flex", gap: 6 }}>
                                <span className="font-bold text-sky-400">{c.connectionId}</span>
                                <span>·</span>
                                <span>{c.environment}</span>
                              </div>
                            </div>
                          </td>

                          {/* Account & Masked Secret */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className="v3-mono text-xs font-semibold">{c.accountAlias}</span>
                              <div className="v3-cell-sub v3-mono text-xs">
                                <code>{c.secretRef}</code> <span className="v3-dim text-xs">(masked reference)</span>
                              </div>
                            </div>
                          </td>

                          {/* Transport Health */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className={`v3-status-badge ${c.healthState === "HEALTHY" ? "ok" : c.healthState === "DEGRADED" ? "warn" : "neg"}`}>
                                <Dot tone={c.healthState === "HEALTHY" ? "ok" : c.healthState === "DEGRADED" ? "warn" : "neg"} />
                                {c.healthState}
                              </span>
                              {c.healthState !== "OFFLINE" && (
                                <span className="v3-mono v3-dim text-xs" style={{ fontSize: 9.5 }}>
                                  {c.latencyMs}ms latency
                                </span>
                              )}
                            </div>
                          </td>

                          {/* Auth State */}
                          <td>
                            <span className={`v3-status-badge ${c.authState === "CONFIGURED" ? "ok" : c.authState === "EXPIRED" ? "warn" : "neg"}`}>
                              <Dot tone={c.authState === "CONFIGURED" ? "ok" : c.authState === "EXPIRED" ? "warn" : "neg"} />
                              {c.authState.replace("_", " ")}
                            </span>
                          </td>

                          {/* Owner Allowance */}
                          <td>
                            <span className={`v3-status-badge ${isHeld ? "warn" : "ok"}`}>
                              <Dot tone={isHeld ? "warn" : "ok"} />
                              {c.ownerAllowance}
                            </span>
                          </td>

                          {/* Granular Capabilities Matrix in Table */}
                          <td>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: 4, maxWidth: 320 }}>
                              {c.capabilities.map((cap) => {
                                const eff = computeCapabilityEffective(c.healthState, c.ownerAllowance, cap);
                                return (
                                  <span
                                    key={cap.capability}
                                    className="v3-mono text-xs"
                                    title={eff.blocker ? `Blocker: ${eff.blocker}` : `${cap.name}: ${eff.label}`}
                                    style={{
                                      fontSize: 9.5,
                                      padding: "1px 6px",
                                      borderRadius: 3,
                                      background: eff.status === "AVAILABLE" ? "rgba(16, 185, 129, 0.1)" : "rgba(239, 68, 68, 0.08)",
                                      border: eff.status === "AVAILABLE" ? "1px solid rgba(16, 185, 129, 0.3)" : "1px solid rgba(239, 68, 68, 0.25)",
                                      color: eff.status === "AVAILABLE" ? "var(--v3-profit)" : "var(--v3-loss-text)",
                                      display: "inline-flex",
                                      alignItems: "center",
                                      gap: 4,
                                    }}
                                  >
                                    <Dot tone={eff.tone} />
                                    <span>{cap.name}</span>
                                    {eff.status !== "AVAILABLE" && <span style={{ opacity: 0.8 }}>({eff.label.replace("BLOCKED ", "")})</span>}
                                  </span>
                                );
                              })}
                            </div>
                          </td>

                          {/* Actions */}
                          <td style={{ textAlign: "right" }} onClick={(e) => e.stopPropagation()}>
                            <div style={{ display: "inline-flex", gap: 6 }}>
                              <button
                                type="button"
                                className="v3-btn ghost mini"
                                onClick={() => {
                                  setSelectedConnection(c);
                                  setDrawerTab("overview");
                                }}
                                id={`inspect-conn-btn-${c.id}`}
                                title="Inspect granular capabilities and auth state"
                              >
                                Inspect
                              </button>
                              <button
                                type="button"
                                className={`v3-btn mini ${isHeld ? "ghost" : "danger-ghost"}`}
                                onClick={() => handleToggleConnectionAllowance(c.id, c.ownerAllowance)}
                                id={`toggle-allowance-conn-btn-${c.id}`}
                                title="Interactive Prototype — Local State"
                              >
                                {isHeld ? "Allow" : "Place Hold"}
                              </button>
                              <button
                                type="button"
                                className="v3-btn ghost mini"
                                onClick={() => handleTestConnection(c.name)}
                                id={`test-conn-btn-${c.id}`}
                                title="Simulated Action"
                              >
                                Ping
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
         SECTION 2: HISTORICAL DATA MANAGER
         ════════════════════════════════════════════════════════════ */}
      {activeMainTab === "historical" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }} id="section-historical-data">
          {/* Architecture Pipeline Flow Banner */}
          <div className="v3-card" style={{ padding: 12, background: "var(--v3-surface-2)" }} id="historical-pipeline-banner">
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 16 }}>📊</span>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 12 }}>HISTORICAL DATA PIPELINE · 4-AXIS DATASET GOVERNANCE</div>
                  <div className="v3-dim text-xs">
                    1. Acquisition State → 2. System Data Readiness (Format + Calendar Gaps + Hash) → 3. Owner Approval → 4. Effective Backtest Readiness
                  </div>
                </div>
              </div>
              <div className="v3-mono text-xs" style={{ color: "var(--v3-sky-text)" }}>
                Storage Authority: <code>data/parquet/</code>
              </div>
            </div>
          </div>

          {/* Acquisition & Ingestion Form Panel (Prototype Console) */}
          <Panel label="Historical Data Ingestion Console" meta="Simulated Action · No Real Network Fetch" className="v3-sp12">
            <form onSubmit={handleAcquireDataset} id="historical-acq-form">
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12, marginBottom: 14 }}>
                <div>
                  <label className="v3-dim text-xs font-semibold" style={{ display: "block", marginBottom: 4 }}>
                    Data Source / Connection
                  </label>
                  <select
                    className="v3-input"
                    value={acqSource}
                    onChange={(e) => setAcqSource(e.target.value)}
                    id="acq-source-select"
                    style={{ height: 32, fontSize: 12 }}
                  >
                    <option value="SX-CONN-TRUEDATA-01">NSE Official TrueData Feed (Direct API)</option>
                    <option value="SX-CONN-ANGEL-01">Angel One Historical API Gateway</option>
                    <option value="AUTO_IMPORTER_CSV">Auto Importer (data/incoming/ CSV/XLSX)</option>
                    <option value="NSE_PARQUET_MASTER">NSE Parquet Master Archive</option>
                  </select>
                </div>

                <div>
                  <label className="v3-dim text-xs font-semibold" style={{ display: "block", marginBottom: 4 }}>
                    Market / Exchange
                  </label>
                  <select
                    className="v3-input"
                    value={acqMarket}
                    onChange={(e) => setAcqMarket(e.target.value)}
                    id="acq-market-select"
                    style={{ height: 32, fontSize: 12 }}
                  >
                    <option value="NSE_INDEX">NSE Index Options &amp; Spot</option>
                    <option value="NSE_EQUITY">NSE Cash Equities</option>
                    <option value="NSE_FNO">NSE Stock &amp; Index Derivatives</option>
                    <option value="BSE_INDEX">BSE Indices (SENSEX/BANKEX)</option>
                    <option value="MCX_COMMODITY">MCX Commodities</option>
                  </select>
                </div>

                <div>
                  <label className="v3-dim text-xs font-semibold" style={{ display: "block", marginBottom: 4 }}>
                    Instrument / Symbol
                  </label>
                  <select
                    className="v3-input"
                    value={acqInstrument}
                    onChange={(e) => setAcqInstrument(e.target.value)}
                    id="acq-instrument-select"
                    style={{ height: 32, fontSize: 12 }}
                  >
                    <option value="NIFTY">NIFTY 50</option>
                    <option value="BANKNIFTY">BANKNIFTY</option>
                    <option value="FINNIFTY">FINNIFTY</option>
                    <option value="MIDCPNIFTY">MIDCPNIFTY</option>
                    <option value="SENSEX">SENSEX</option>
                    <option value="RELIANCE">RELIANCE</option>
                  </select>
                </div>

                <div>
                  <label className="v3-dim text-xs font-semibold" style={{ display: "block", marginBottom: 4 }}>
                    Timeframe
                  </label>
                  <select
                    className="v3-input"
                    value={acqTimeframe}
                    onChange={(e) => setAcqTimeframe(e.target.value)}
                    id="acq-timeframe-select"
                    style={{ height: 32, fontSize: 12 }}
                  >
                    <option value="tick">Tick Replay (Sub-second)</option>
                    <option value="1m">1-Minute Candles</option>
                    <option value="5m">5-Minute Candles</option>
                    <option value="15m">15-Minute Candles</option>
                    <option value="1h">1-Hour Candles</option>
                    <option value="1d">1-Day Daily Bars</option>
                  </select>
                </div>

                <div>
                  <label className="v3-dim text-xs font-semibold" style={{ display: "block", marginBottom: 4 }}>
                    Date Range (Start → End)
                  </label>
                  <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <input
                      type="date"
                      className="v3-input"
                      value={acqStartDate}
                      onChange={(e) => setAcqStartDate(e.target.value)}
                      id="acq-start-date"
                      style={{ height: 32, fontSize: 12, width: "50%" }}
                    />
                    <span className="v3-dim text-xs">→</span>
                    <input
                      type="date"
                      className="v3-input"
                      value={acqEndDate}
                      onChange={(e) => setAcqEndDate(e.target.value)}
                      id="acq-end-date"
                      style={{ height: 32, fontSize: 12, width: "50%" }}
                    />
                  </div>
                </div>

                <div>
                  <label className="v3-dim text-xs font-semibold" style={{ display: "block", marginBottom: 4 }}>
                    Acquisition Mode
                  </label>
                  <select
                    className="v3-input"
                    value={acqMode}
                    onChange={(e) => setAcqMode(e.target.value)}
                    id="acq-mode-select"
                    style={{ height: 32, fontSize: 12 }}
                  >
                    <option value="Full Range Acquisition">Full Range Ingest &amp; Normalization</option>
                    <option value="Incremental Update">Incremental Catch-up (Latest)</option>
                    <option value="Gap Backfill">Targeted Gap Backfill (Calendar-Aligned)</option>
                  </select>
                </div>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderTop: "1px solid var(--v3-line)", paddingTop: 10 }}>
                <span className="v3-dim text-xs">
                  Timezone Authority: <code>Asia/Kolkata</code> · Storage Layout: <code>data/parquet/{acqMarket.toLowerCase()}/{acqInstrument.toLowerCase()}/{acqTimeframe}/</code>
                </span>
                <div style={{ display: "flex", gap: 8 }}>
                  <button type="submit" className="v3-btn primary mini" id="acq-submit-btn">
                    <Icon name="play" size={12} /> Acquire / Download (Simulated Action)
                  </button>
                </div>
              </div>
            </form>
          </Panel>

          {/* Filter Toolbar for Datasets */}
          <div className="v3-card" style={{ padding: 10, display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <button
                type="button"
                className={`v3-btn mini ${datasetFilter === "ALL" ? "primary" : "ghost"}`}
                onClick={() => setDatasetFilter("ALL")}
                id="filter-ds-all-btn"
              >
                All ({datasets.length})
              </button>
              <button
                type="button"
                className={`v3-btn mini ${datasetFilter === "READY_FOR_BACKTEST" ? "primary" : "ghost"}`}
                onClick={() => setDatasetFilter("READY_FOR_BACKTEST")}
                id="filter-ds-approved-btn"
              >
                Ready for Backtest
              </button>
              <button
                type="button"
                className={`v3-btn mini ${datasetFilter === "SYSTEM_BLOCKED" ? "primary" : "ghost"}`}
                onClick={() => setDatasetFilter("SYSTEM_BLOCKED")}
                id="filter-ds-unverified-btn"
              >
                System Blocked / Gaps
              </button>
              <button
                type="button"
                className={`v3-btn mini ${datasetFilter === "HELD" ? "primary" : "ghost"}`}
                onClick={() => setDatasetFilter("HELD")}
                id="filter-ds-held-btn"
              >
                Owner Hold
              </button>
            </div>
            <div style={{ position: "relative", minWidth: 240 }}>
              <input
                type="text"
                placeholder="Search datasets by symbol, ID..."
                className="v3-input"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                id="ds-search-input"
                style={{ paddingLeft: 26, fontSize: 12, height: 30 }}
              />
              <span style={{ position: "absolute", left: 8, top: 6, color: "var(--v3-ink-dim)", fontSize: 12 }}>🔍</span>
            </div>
          </div>

          {/* Local Dataset Inventory Table */}
          <Panel label="Local Dataset Store &amp; Governance Matrix" meta={`${filteredDatasets.length} datasets`} className="v3-sp12">
            <div className="v3-table-wrap">
              <table className="v3-table" id="owner-datasets-table">
                <thead>
                  <tr>
                    <th style={{ whiteSpace: "nowrap" }}>DATASET ID &amp; INSTRUMENT</th>
                    <th style={{ whiteSpace: "nowrap" }}>COVERAGE (RANGE · SESSIONS)</th>
                    <th style={{ whiteSpace: "nowrap" }}>BARS / FORMAT</th>
                    <th style={{ whiteSpace: "nowrap" }}>SYSTEM DATA READINESS</th>
                    <th style={{ whiteSpace: "nowrap" }}>OWNER APPROVAL</th>
                    <th style={{ whiteSpace: "nowrap" }}>EFFECTIVE BACKTEST READINESS</th>
                    <th style={{ textAlign: "right", whiteSpace: "nowrap" }}>ACTIONS</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredDatasets.length === 0 ? (
                    <tr>
                      <td colSpan={7} style={{ textAlign: "center", padding: "28px", color: "var(--v3-ink-dim)" }}>
                        {datasets.length === 0 ? "No datasets registered yet" : "No datasets match filter."}
                      </td>
                    </tr>
                  ) : (
                    filteredDatasets.map((d) => {
                      const eff = computeDatasetEffectiveReadiness(d.systemReadiness, d.ownerApproval, d.systemBlockerReason);
                      const isOwnerApproved = d.ownerApproval === "APPROVED";
                      const isSystemReady = d.systemReadiness === "SYSTEM_READY";

                      return (
                        <tr
                          key={d.id}
                          className="v3-table-row"
                          id={`ds-row-${d.id}`}
                          style={{ cursor: "pointer" }}
                          onClick={() => {
                            setSelectedDataset(d);
                            setDrawerTab("summary");
                          }}
                        >
                          {/* Dataset ID & Instrument */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className="font-semibold text-xs">{d.instrument} · {d.timeframe}</span>
                              <div className="v3-cell-sub v3-mono text-xs" style={{ display: "flex", gap: 6 }}>
                                <span className="font-bold text-sky-400">{d.datasetId}</span>
                                <span>·</span>
                                <span>{d.segment}</span>
                              </div>
                            </div>
                          </td>

                          {/* Coverage */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className="v3-mono text-xs">{d.startDate} → {d.endDate}</span>
                              <div className="v3-cell-sub text-xs">{d.tradingDays} trading sessions</div>
                            </div>
                          </td>

                          {/* Bars & Format */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className="v3-mono font-bold text-xs">{d.rowCount.toLocaleString()} bars</span>
                              <span className="v3-mono v3-dim text-xs" style={{ fontSize: 9.5 }}>{d.format}</span>
                            </div>
                          </td>

                          {/* System Data Readiness */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className={`v3-status-badge ${isSystemReady ? "ok" : "neg"}`}>
                                <Dot tone={isSystemReady ? "ok" : "neg"} />
                                {d.systemReadiness.replace("_", " ")}
                              </span>
                              <span className="v3-cell-sub text-xs" style={{ fontSize: 9.5 }}>
                                {d.gapStatus === "GAPS_CLEAR" ? "0 Calendar Gaps" : "Gaps Detected"}
                              </span>
                            </div>
                          </td>

                          {/* Owner Approval */}
                          <td>
                            <span className={`v3-status-badge ${isOwnerApproved ? "ok" : d.ownerApproval === "HOLD" ? "warn" : "neg"}`}>
                              <Dot tone={isOwnerApproved ? "ok" : d.ownerApproval === "HOLD" ? "warn" : "neg"} />
                              {d.ownerApproval}
                            </span>
                          </td>

                          {/* Effective Backtest Readiness */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className={`v3-status-badge ${eff.tone}`} style={{ fontWeight: eff.status === "READY_FOR_BACKTEST" ? 700 : 400 }}>
                                <Dot tone={eff.tone} />
                                {eff.label}
                              </span>
                              {eff.blocker && (
                                <span className="v3-cell-sub text-xs" style={{ fontSize: 9, color: "var(--v3-loss-text)", maxWidth: 180 }}>
                                  {eff.blocker}
                                </span>
                              )}
                            </div>
                          </td>

                          {/* Actions */}
                          <td style={{ textAlign: "right" }} onClick={(e) => e.stopPropagation()}>
                            <div style={{ display: "inline-flex", gap: 6 }}>
                              <button
                                type="button"
                                className="v3-btn ghost mini"
                                onClick={() => {
                                  setSelectedDataset(d);
                                  setDrawerTab("summary");
                                }}
                                id={`inspect-ds-btn-${d.id}`}
                                title="Inspect dataset coverage & calendar analysis"
                              >
                                Inspect
                              </button>
                              <button
                                type="button"
                                className={`v3-btn mini ${isOwnerApproved ? "ghost" : "primary"}`}
                                onClick={() => handleToggleDatasetApproval(d.id, d.ownerApproval)}
                                id={`toggle-approval-ds-btn-${d.id}`}
                                title="Interactive Prototype — Local State"
                              >
                                {isOwnerApproved ? "Place Hold" : "Approve"}
                              </button>
                              {d.gapStatus === "GAPS_DETECTED" && (
                                <button
                                  type="button"
                                  className="v3-btn ghost mini"
                                  onClick={() => handleRepairGaps(d.datasetId)}
                                  id={`repair-gaps-btn-${d.id}`}
                                  title="Simulated Action"
                                >
                                  Repair
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
         SECTION 3: PLUGIN REGISTRY & EXTENSIONS
         ════════════════════════════════════════════════════════════ */}
      {activeMainTab === "plugins" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }} id="section-plugin-registry">
          {/* KPI Deck */}
          <div className="v3-kpi-deck" id="plugins-kpi-deck" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 12 }}>
            <div className="v3-card" style={{ padding: 14 }}>
              <div className="v3-dim text-xs">REGISTERED PLUGINS</div>
              <div className="v3-stat-big" style={{ fontSize: 24, fontWeight: 700, marginTop: 4 }}>{plugins.length}</div>
              <div className="v3-cell-sub text-xs">Installed extensions</div>
            </div>
            <div className="v3-card" style={{ padding: 14 }}>
              <div className="v3-dim text-xs">COMPATIBLE PLUGINS</div>
              <div className="v3-stat-big" style={{ fontSize: 24, fontWeight: 700, marginTop: 4, color: "var(--v3-profit)" }}>
                {plugins.filter((p) => p.compatibilityStatus === "COMPATIBLE").length}
              </div>
              <div className="v3-cell-sub text-xs">Pass ABI Interface v1.0</div>
            </div>
            <div className="v3-card" style={{ padding: 14 }}>
              <div className="v3-dim text-xs">INCOMPATIBLE / ABI FAIL</div>
              <div className="v3-stat-big" style={{ fontSize: 24, fontWeight: 700, marginTop: 4, color: "var(--v3-loss-text)" }}>
                {plugins.filter((p) => p.compatibilityStatus === "INCOMPATIBLE").length}
              </div>
              <div className="v3-cell-sub text-xs">Fail-Closed Blocked</div>
            </div>
            <div className="v3-card" style={{ padding: 14 }}>
              <div className="v3-dim text-xs">OWNER HELD</div>
              <div className="v3-stat-big" style={{ fontSize: 24, fontWeight: 700, marginTop: 4, color: "var(--v3-warn-text)" }}>
                {plugins.filter((p) => p.ownerAllowance === "HOLD").length}
              </div>
              <div className="v3-cell-sub text-xs">Administrative Hold</div>
            </div>
          </div>

          {/* Filter Toolbar */}
          <div className="v3-card" style={{ padding: 10, display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 10 }} id="plugins-toolbar">
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <button
                type="button"
                className={`v3-btn mini ${pluginFilter === "ALL" ? "primary" : "ghost"}`}
                onClick={() => setPluginFilter("ALL")}
                id="filter-plug-all-btn"
              >
                All ({plugins.length})
              </button>
              <button
                type="button"
                className={`v3-btn mini ${pluginFilter === "ACTIVE" ? "primary" : "ghost"}`}
                onClick={() => setPluginFilter("ACTIVE")}
                id="filter-plug-active-btn"
              >
                Effective Active
              </button>
              <button
                type="button"
                className={`v3-btn mini ${pluginFilter === "COMPATIBLE" ? "primary" : "ghost"}`}
                onClick={() => setPluginFilter("COMPATIBLE")}
                id="filter-plug-compatible-btn"
              >
                Compatible
              </button>
              <button
                type="button"
                className={`v3-btn mini ${pluginFilter === "INCOMPATIBLE" ? "primary" : "ghost"}`}
                onClick={() => setPluginFilter("INCOMPATIBLE")}
                id="filter-plug-incompatible-btn"
              >
                Incompatible
              </button>
              <button
                type="button"
                className={`v3-btn mini ${pluginFilter === "HELD" ? "primary" : "ghost"}`}
                onClick={() => setPluginFilter("HELD")}
                id="filter-plug-held-btn"
              >
                Owner Hold
              </button>
            </div>
            <div style={{ position: "relative", minWidth: 240 }}>
              <input
                type="text"
                placeholder="Search plugins..."
                className="v3-input"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                id="plug-search-input"
                style={{ paddingLeft: 26, fontSize: 12, height: 30 }}
              />
              <span style={{ position: "absolute", left: 8, top: 6, color: "var(--v3-ink-dim)", fontSize: 12 }}>🔍</span>
            </div>
          </div>

          {/* Plugins Table */}
          <Panel label="Extensibility &amp; Plugin Registry Fleet" meta={`${filteredPlugins.length} modules`} className="v3-sp12">
            <div className="v3-table-wrap">
              <table className="v3-table" id="owner-plugins-table">
                <thead>
                  <tr>
                    <th style={{ whiteSpace: "nowrap" }}>PLUGIN / IDENTITY</th>
                    <th style={{ whiteSpace: "nowrap" }}>CATEGORY &amp; AUTHOR</th>
                    <th style={{ whiteSpace: "nowrap" }}>ORIGIN</th>
                    <th style={{ whiteSpace: "nowrap" }}>COMPATIBILITY / ABI</th>
                    <th style={{ whiteSpace: "nowrap" }}>PERMISSION READINESS</th>
                    <th style={{ whiteSpace: "nowrap" }}>OWNER ALLOWANCE</th>
                    <th style={{ whiteSpace: "nowrap" }}>EFFECTIVE AVAILABILITY</th>
                    <th style={{ textAlign: "right", whiteSpace: "nowrap" }}>ACTIONS</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredPlugins.length === 0 ? (
                    <tr>
                      <td colSpan={8} style={{ textAlign: "center", padding: "28px", color: "var(--v3-ink-dim)" }}>
                        {plugins.length === 0 ? "No plugins registered yet" : "No plugins match filter."}
                      </td>
                    </tr>
                  ) : (
                    filteredPlugins.map((p) => {
                      const eff = computePluginEffective(p.compatibilityStatus, p.permissionReadiness, p.ownerAllowance);
                      const isHeld = p.ownerAllowance === "HOLD";
                      const isCompatible = p.compatibilityStatus === "COMPATIBLE";
                      const isPermReady = p.permissionReadiness === "PERMISSIONS_READY";

                      return (
                        <tr
                          key={p.id}
                          className="v3-table-row"
                          id={`plug-row-${p.id}`}
                          style={{ cursor: "pointer" }}
                          onClick={() => {
                            setSelectedPlugin(p);
                            setDrawerTab("overview");
                          }}
                        >
                          {/* Name & ID */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className="font-semibold text-xs">{p.name}</span>
                              <div className="v3-cell-sub v3-mono text-xs" style={{ display: "flex", gap: 6 }}>
                                <span className="font-bold text-sky-400">{p.pluginId}</span>
                                <span>·</span>
                                <span>{p.version}</span>
                              </div>
                            </div>
                          </td>

                          {/* Category & Author */}
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                              <span className="text-xs">{p.category}</span>
                              <span className="v3-cell-sub text-xs">By {p.author}</span>
                            </div>
                          </td>

                          {/* Origin */}
                          <td>
                            <span className="v3-mono text-xs font-semibold">{p.discoveryState}</span>
                          </td>

                          {/* Compatibility */}
                          <td>
                            <span className={`v3-status-badge ${isCompatible ? "ok" : "neg"}`}>
                              <Dot tone={isCompatible ? "ok" : "neg"} />
                              {isCompatible ? "COMPATIBLE" : "INCOMPATIBLE"}
                            </span>
                          </td>

                          {/* Permission Readiness */}
                          <td>
                            <span className={`v3-status-badge ${isPermReady ? "ok" : "neg"}`}>
                              <Dot tone={isPermReady ? "ok" : "neg"} />
                              {isPermReady ? "PERMISSIONS READY" : "PERMISSION BLOCKED"}
                            </span>
                          </td>

                          {/* Owner Allowance */}
                          <td>
                            <span className={`v3-status-badge ${isHeld ? "warn" : "ok"}`}>
                              <Dot tone={isHeld ? "warn" : "ok"} />
                              {p.ownerAllowance}
                            </span>
                          </td>

                          {/* Effective */}
                          <td>
                            <span className={`v3-status-badge ${eff.tone}`} style={{ fontWeight: eff.status === "ACTIVE" ? 700 : 400 }}>
                              <Dot tone={eff.tone} />
                              {eff.label}
                            </span>
                          </td>

                          {/* Actions */}
                          <td style={{ textAlign: "right" }} onClick={(e) => e.stopPropagation()}>
                            <div style={{ display: "inline-flex", gap: 6 }}>
                              <button
                                type="button"
                                className="v3-btn ghost mini"
                                onClick={() => {
                                  setSelectedPlugin(p);
                                  setDrawerTab("overview");
                                }}
                                id={`inspect-plug-btn-${p.id}`}
                                title="Inspect plugin contract & capabilities"
                              >
                                Inspect
                              </button>
                              <button
                                type="button"
                                className={`v3-btn mini ${isHeld ? "ghost" : "danger-ghost"}`}
                                onClick={() => handleTogglePluginAllowance(p.id, p.ownerAllowance)}
                                id={`toggle-allowance-plug-btn-${p.id}`}
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
         DETAILS & INSPECTION DRAWER (CONNECTIONS, DATASETS, PLUGINS)
         ════════════════════════════════════════════════════════════ */}

      {/* 1. Connection Detail Drawer */}
      {selectedConnection && (
        <Drawer
          open={Boolean(selectedConnection)}
          title={selectedConnection.name}
          sub={`${selectedConnection.connectionId} · ${selectedConnection.provider} · ${selectedConnection.environment}`}
          onClose={() => setSelectedConnection(null)}
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
                <div className="v3-dim text-xs">TRANSPORT HEALTH</div>
                <div style={{ marginTop: 2 }}>
                  <span className={`v3-status-badge ${selectedConnection.healthState === "HEALTHY" ? "ok" : selectedConnection.healthState === "DEGRADED" ? "warn" : "neg"}`}>
                    <Dot tone={selectedConnection.healthState === "HEALTHY" ? "ok" : selectedConnection.healthState === "DEGRADED" ? "warn" : "neg"} />
                    {selectedConnection.healthState}
                  </span>
                </div>
              </div>
              <div>
                <div className="v3-dim text-xs">AUTH STATE</div>
                <div className="v3-mono font-bold text-xs" style={{ marginTop: 4 }}>
                  {selectedConnection.authState.replace("_", " ")}
                </div>
              </div>
              <div>
                <div className="v3-dim text-xs">OWNER ALLOWANCE</div>
                <div style={{ marginTop: 2 }}>
                  <span className={`v3-status-badge ${selectedConnection.ownerAllowance === "ALLOWED" ? "ok" : "warn"}`}>
                    <Dot tone={selectedConnection.ownerAllowance === "ALLOWED" ? "ok" : "warn"} />
                    {selectedConnection.ownerAllowance}
                  </span>
                </div>
              </div>
              <div>
                <div className="v3-dim text-xs">LATENCY</div>
                <div className="v3-mono font-bold text-xs" style={{ marginTop: 4, color: "var(--v3-profit)" }}>
                  {selectedConnection.latencyMs}ms
                </div>
              </div>
            </div>

            {/* Panel: Overview & Specification */}
            <Panel label="Connection Identity &amp; Secret Reference">
              <dl style={{ margin: 0 }}>
                <KV k="Connection Name" v={selectedConnection.name} />
                <KV k="Connection ID" v={<span className="v3-mono font-bold">{selectedConnection.connectionId}</span>} />
                <KV k="Provider Adapter" v={selectedConnection.provider} />
                <KV k="Type" v={selectedConnection.type} />
                <KV k="Account Alias" v={<span className="v3-mono">{selectedConnection.accountAlias}</span>} />
                <KV
                  k="Secret Reference"
                  v={
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <code className="v3-mono">{selectedConnection.secretRef}</code>
                      <span className="v3-chip disabled" style={{ fontSize: 9 }}>MASKED CREDENTIAL REFERENCE</span>
                    </div>
                  }
                />
                <KV k="Environment" v={selectedConnection.environment} />
                <KV k="Last Health Check" v={selectedConnection.lastCheck} />
              </dl>
            </Panel>

            {/* Panel: Granular Capabilities Matrix */}
            <Panel label="Granular Capability Availability Matrix" meta="Independent Evaluation">
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {selectedConnection.capabilities.map((cap) => {
                  const eff = computeCapabilityEffective(selectedConnection.healthState, selectedConnection.ownerAllowance, cap);
                  const isCapHeld = cap.ownerAllowance === "HOLD";

                  return (
                    <div
                      key={cap.capability}
                      style={{
                        padding: 10,
                        borderRadius: 4,
                        background: "var(--v3-surface-2)",
                        border: "1px solid var(--v3-line)",
                        display: "flex",
                        flexDirection: "column",
                        gap: 6,
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <span className="font-semibold text-xs">{cap.name}</span>
                          <span className={`v3-status-badge ${eff.tone}`}>
                            <Dot tone={eff.tone} />
                            {eff.label}
                          </span>
                        </div>
                        <button
                          type="button"
                          className={`v3-btn mini ${isCapHeld ? "ghost" : "danger-ghost"}`}
                          onClick={() => handleToggleCapabilityAllowance(selectedConnection.id, cap.capability, cap.ownerAllowance)}
                          id={`toggle-cap-allowance-${cap.capability}`}
                          title="Interactive Prototype — Local State"
                        >
                          {isCapHeld ? "Allow Capability" : "Hold Capability"}
                        </button>
                      </div>

                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, fontSize: 11 }}>
                        <div>
                          <span className="v3-dim">Provider: </span>
                          <span className="v3-mono">{cap.systemStatus}</span>
                        </div>
                        <div>
                          <span className="v3-dim">Auth/Permission: </span>
                          <span className="v3-mono">{cap.authStatus.replace("BLOCKED_", "")}</span>
                        </div>
                        <div>
                          <span className="v3-dim">Owner Allowance: </span>
                          <span className="v3-mono">{cap.ownerAllowance}</span>
                        </div>
                      </div>

                      {eff.blocker && (
                        <div style={{ fontSize: 11, color: "var(--v3-loss-text)", paddingTop: 4, borderTop: "1px solid var(--v3-line)" }}>
                          <strong>Blocker:</strong> {eff.blocker}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </Panel>

            {/* Panel: Connection Governance Actions */}
            <Panel label="Connection-Wide Governance Actions">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div className="font-semibold text-xs">Connection-Wide Hold Toggle</div>
                  <div className="v3-dim text-xs">Override and disable all capabilities on this connection</div>
                </div>
                <button
                  type="button"
                  className={`v3-btn mini ${selectedConnection.ownerAllowance === "ALLOWED" ? "danger-ghost" : "primary"}`}
                  onClick={() => handleToggleConnectionAllowance(selectedConnection.id, selectedConnection.ownerAllowance)}
                  id="drawer-toggle-conn-allowance-btn"
                  title="Interactive Prototype — Local State"
                >
                  {selectedConnection.ownerAllowance === "ALLOWED" ? "Place Hold on Connection" : "Allow Connection"}
                </button>
              </div>
            </Panel>

            {/* Panel: Event History */}
            <Panel label="Recent Connection Events">
              <div className="v3-rows">
                {selectedConnection.events.map((ev, idx) => (
                  <div className="v3-row" key={idx}>
                    <div className="v3-row-main">
                      <div className="v3-row-title" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <Dot tone={ev.tone || "ok"} />
                        <span>{ev.text}</span>
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

      {/* 2. Dataset Detail Drawer */}
      {selectedDataset && (
        <Drawer
          open={Boolean(selectedDataset)}
          title={selectedDataset.datasetId}
          sub={`${selectedDataset.instrument} · ${selectedDataset.timeframe} · ${selectedDataset.source}`}
          onClose={() => setSelectedDataset(null)}
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
                <div className="v3-dim text-xs">ACQUISITION</div>
                <div style={{ marginTop: 2 }}>
                  <span className={`v3-status-badge ${selectedDataset.acquisitionState === "ACQUIRED" ? "ok" : "warn"}`}>
                    <Dot tone={selectedDataset.acquisitionState === "ACQUIRED" ? "ok" : "warn"} />
                    {selectedDataset.acquisitionState}
                  </span>
                </div>
              </div>
              <div>
                <div className="v3-dim text-xs">SYSTEM READINESS</div>
                <div style={{ marginTop: 2 }}>
                  <span className={`v3-status-badge ${selectedDataset.systemReadiness === "SYSTEM_READY" ? "ok" : "neg"}`}>
                    <Dot tone={selectedDataset.systemReadiness === "SYSTEM_READY" ? "ok" : "neg"} />
                    {selectedDataset.systemReadiness.replace("_", " ")}
                  </span>
                </div>
              </div>
              <div>
                <div className="v3-dim text-xs">OWNER APPROVAL</div>
                <div style={{ marginTop: 2 }}>
                  <span className={`v3-status-badge ${selectedDataset.ownerApproval === "APPROVED" ? "ok" : "warn"}`}>
                    <Dot tone={selectedDataset.ownerApproval === "APPROVED" ? "ok" : "warn"} />
                    {selectedDataset.ownerApproval}
                  </span>
                </div>
              </div>
              <div>
                <div className="v3-dim text-xs">EFFECTIVE READINESS</div>
                <div style={{ marginTop: 2 }}>
                  {(() => {
                    const eff = computeDatasetEffectiveReadiness(selectedDataset.systemReadiness, selectedDataset.ownerApproval, selectedDataset.systemBlockerReason);
                    return (
                      <span className={`v3-status-badge ${eff.tone}`} style={{ fontWeight: eff.status === "READY_FOR_BACKTEST" ? 700 : 400 }}>
                        <Dot tone={eff.tone} />
                        {eff.label}
                      </span>
                    );
                  })()}
                </div>
              </div>
            </div>

            {/* Panel: Specification */}
            <Panel label="Dataset Identity &amp; System Validation Evidence">
              <dl style={{ margin: 0 }}>
                <KV k="Dataset ID" v={<span className="v3-mono font-bold">{selectedDataset.datasetId}</span>} />
                <KV k="Instrument / Symbol" v={selectedDataset.instrument} />
                <KV k="Market &amp; Segment" v={`${selectedDataset.market} · ${selectedDataset.segment}`} />
                <KV k="Timeframe" v={selectedDataset.timeframe} />
                <KV k="Date Range" v={`${selectedDataset.startDate} to ${selectedDataset.endDate} (${selectedDataset.tradingDays} trading days)`} />
                <KV k="Total Bars / Rows" v={selectedDataset.rowCount.toLocaleString()} />
                <KV k="Storage Format" v={<span className="v3-mono">{selectedDataset.format}</span>} />
                <KV k="Logical Path" v={<code className="v3-mono">{selectedDataset.logicalPath}</code>} />
                <KV k="Timezone Authority" v={selectedDataset.sourceTimezone} />
                <KV k="Cryptographic Hash (SHA-256)" v={<code className="v3-mono" style={{ fontSize: 10 }}>{selectedDataset.hashSha256}</code>} />
                <KV k="System Verification Evidence" v={selectedDataset.verificationDetails} />
                {selectedDataset.systemBlockerReason && (
                  <KV
                    k="System Blocker Reason"
                    v={<span style={{ color: "var(--v3-loss-text)", fontWeight: 600 }}>{selectedDataset.systemBlockerReason}</span>}
                  />
                )}
              </dl>
            </Panel>

            {/* Panel: Governance Actions */}
            <Panel label="Owner Approval &amp; Simulation Controls">
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <div className="font-semibold text-xs">Owner Backtest Approval Toggle</div>
                    <div className="v3-dim text-xs">
                      {selectedDataset.systemReadiness === "SYSTEM_READY"
                        ? "Approve or hold this dataset for backtest engine replay"
                        : "System Blocked: Owner approval alone cannot bypass failed schema or calendar gaps"}
                    </div>
                  </div>
                  <button
                    type="button"
                    className={`v3-btn mini ${selectedDataset.ownerApproval === "APPROVED" ? "danger-ghost" : "primary"}`}
                    onClick={() => handleToggleDatasetApproval(selectedDataset.id, selectedDataset.ownerApproval)}
                    id="drawer-toggle-ds-approval-btn"
                    title="Interactive Prototype — Local State"
                  >
                    {selectedDataset.ownerApproval === "APPROVED" ? "Place Hold on Dataset" : "Approve for Backtests"}
                  </button>
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: 8, borderTop: "1px solid var(--v3-line)" }}>
                  <div>
                    <div className="font-semibold text-xs">Simulate Verification / Re-check</div>
                    <div className="v3-dim text-xs">Re-scan Parquet format and NSE trading calendar consistency</div>
                  </div>
                  <button
                    type="button"
                    className="v3-btn ghost mini"
                    onClick={() => handleReverifySimulated(selectedDataset.datasetId)}
                    id="drawer-reverify-ds-btn"
                    title="Simulated Action"
                  >
                    Run Re-verify
                  </button>
                </div>

                {selectedDataset.gapStatus === "GAPS_DETECTED" && (
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: 8, borderTop: "1px solid var(--v3-line)" }}>
                    <div>
                      <div className="font-semibold text-xs">Gap Repair Trigger (Simulated)</div>
                      <div className="v3-dim text-xs">Fetch missing market sessions and re-normalize Parquet file</div>
                    </div>
                    <button
                      type="button"
                      className="v3-btn ghost mini"
                      onClick={() => handleRepairGaps(selectedDataset.datasetId)}
                      id="drawer-repair-ds-gaps-btn"
                      title="Simulated Action"
                    >
                      Run Gap Repair
                    </button>
                  </div>
                )}
              </div>
            </Panel>

            {/* Panel: Import History (Preserved without erasure) */}
            <Panel label="Dataset Lifecycle &amp; Historical Evidence" meta={`${selectedDataset.history.length} logged entries`}>
              <div className="v3-rows">
                {selectedDataset.history.map((ev, idx) => (
                  <div className="v3-row" key={idx}>
                    <div className="v3-row-main">
                      <div className="v3-row-title" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <Dot tone={ev.tone || "ok"} />
                        <span className="v3-mono font-bold text-xs">{ev.action}</span>
                        <span className="v3-dim text-xs">by {ev.actor}</span>
                      </div>
                      <div className="v3-row-sub">{ev.note}</div>
                    </div>
                    <span className="v3-mono v3-dim text-xs" style={{ fontSize: 10 }}>{ev.time}</span>
                  </div>
                ))}
              </div>
            </Panel>
          </div>
        </Drawer>
      )}

      {/* 3. Plugin Detail Drawer */}
      {selectedPlugin && (
        <Drawer
          open={Boolean(selectedPlugin)}
          title={selectedPlugin.name}
          sub={`${selectedPlugin.pluginId} · ${selectedPlugin.version} · ${selectedPlugin.category}`}
          onClose={() => setSelectedPlugin(null)}
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
                <div className="v3-dim text-xs">COMPATIBILITY</div>
                <div style={{ marginTop: 2 }}>
                  <span className={`v3-status-badge ${selectedPlugin.compatibilityStatus === "COMPATIBLE" ? "ok" : "neg"}`}>
                    <Dot tone={selectedPlugin.compatibilityStatus === "COMPATIBLE" ? "ok" : "neg"} />
                    {selectedPlugin.compatibilityStatus}
                  </span>
                </div>
              </div>
              <div>
                <div className="v3-dim text-xs">PERMISSION READINESS</div>
                <div style={{ marginTop: 2 }}>
                  <span className={`v3-status-badge ${selectedPlugin.permissionReadiness === "PERMISSIONS_READY" ? "ok" : "neg"}`}>
                    <Dot tone={selectedPlugin.permissionReadiness === "PERMISSIONS_READY" ? "ok" : "neg"} />
                    {selectedPlugin.permissionReadiness.replace("_", " ")}
                  </span>
                </div>
              </div>
              <div>
                <div className="v3-dim text-xs">OWNER ALLOWANCE</div>
                <div style={{ marginTop: 2 }}>
                  <span className={`v3-status-badge ${selectedPlugin.ownerAllowance === "ALLOWED" ? "ok" : "warn"}`}>
                    <Dot tone={selectedPlugin.ownerAllowance === "ALLOWED" ? "ok" : "warn"} />
                    {selectedPlugin.ownerAllowance}
                  </span>
                </div>
              </div>
              <div>
                <div className="v3-dim text-xs">EFFECTIVE</div>
                <div style={{ marginTop: 2 }}>
                  {(() => {
                    const eff = computePluginEffective(selectedPlugin.compatibilityStatus, selectedPlugin.permissionReadiness, selectedPlugin.ownerAllowance);
                    return (
                      <span className={`v3-status-badge ${eff.tone}`} style={{ fontWeight: eff.status === "ACTIVE" ? 700 : 400 }}>
                        <Dot tone={eff.tone} />
                        {eff.label}
                      </span>
                    );
                  })()}
                </div>
              </div>
            </div>

            {/* Panel: Overview & Specification */}
            <Panel label="Plugin Identity &amp; Contract Conformance">
              <dl style={{ margin: 0 }}>
                <KV k="Plugin Name" v={selectedPlugin.name} />
                <KV k="Plugin ID" v={<span className="v3-mono font-bold">{selectedPlugin.pluginId}</span>} />
                <KV k="Version" v={<span className="v3-mono">{selectedPlugin.version}</span>} />
                <KV k="Category" v={selectedPlugin.category} />
                <KV k="Author / Vendor" v={selectedPlugin.author} />
                <KV k="Description" v={selectedPlugin.description} />
                <KV k="ABI Compatibility Details" v={selectedPlugin.compatibilityDetails || "Verified against Rule 6 interface contract."} />
                {selectedPlugin.permissionBlockerReason && (
                  <KV k="Permission Blocker" v={<span style={{ color: "var(--v3-loss-text)", fontWeight: 600 }}>{selectedPlugin.permissionBlockerReason}</span>} />
                )}
                <KV k="Last ABI Validation" v={selectedPlugin.lastValidation} />
              </dl>
            </Panel>

            {/* Panel: Permissions & Sandbox Security */}
            <Panel label="Declared Capabilities &amp; Sandbox Security Envelopes">
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div>
                  <div className="v3-dim text-xs font-semibold" style={{ marginBottom: 4 }}>Declared Capabilities:</div>
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 11.5 }}>
                    {selectedPlugin.capabilities.map((c, i) => (
                      <li key={i} style={{ marginBottom: 2 }}>{c}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <div className="v3-dim text-xs font-semibold" style={{ marginBottom: 4 }}>Security Sandbox Permissions:</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {selectedPlugin.permissions.map((perm, i) => (
                      <span key={i} className="v3-chip" style={{ fontSize: 10 }}>🔒 {perm}</span>
                    ))}
                  </div>
                </div>
              </div>
            </Panel>

            {/* Panel: Owner Controls */}
            <Panel label="Owner Allowance Control">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div className="font-semibold text-xs">Owner Allowance Toggle</div>
                  <div className="v3-dim text-xs">
                    {selectedPlugin.compatibilityStatus === "COMPATIBLE" && selectedPlugin.permissionReadiness === "PERMISSIONS_READY"
                      ? "Control whether this extension is active in the engine"
                      : "Incompatible / permission-blocked plugin: Owner allowance cannot bypass security gates"}
                  </div>
                </div>
                <button
                  type="button"
                  className={`v3-btn mini ${selectedPlugin.ownerAllowance === "ALLOWED" ? "danger-ghost" : "primary"}`}
                  onClick={() => handleTogglePluginAllowance(selectedPlugin.id, selectedPlugin.ownerAllowance)}
                  id="drawer-toggle-plug-allowance-btn"
                >
                  {selectedPlugin.ownerAllowance === "ALLOWED" ? "Place Hold on Plugin" : "Allow Plugin"}
                </button>
              </div>
            </Panel>

            {/* Panel: Audit History */}
            <Panel label="Plugin Audit &amp; Verification Trail">
              <div className="v3-rows">
                {selectedPlugin.auditHistory.map((ev, idx) => (
                  <div className="v3-row" key={idx}>
                    <div className="v3-row-main">
                      <div className="v3-row-title" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <Dot tone={ev.tone || "ok"} />
                        <span className="v3-mono font-bold text-xs">{ev.action}</span>
                        <span className="v3-dim text-xs">by {ev.actor}</span>
                      </div>
                      <div className="v3-row-sub">{ev.note}</div>
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

export const AdminPluginsScreen: React.FC<{ previewMode?: boolean }> = () => {
  const [live, setLive] = useState(false);
  return (
    <>
      <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
        <button className="v3-btn ghost" onClick={() => setLive(false)}>Connections governance</button>
        <button id="live-readiness-owner-tab" className="v3-btn ghost" onClick={() => setLive(true)}>Live Readiness</button>
      </div>
      {live ? <LiveReadinessRuntime view="owner" /> : (
        <>
          <ExistingPluginsScreen />
          <OwnerConnectionsDeployments />
        </>
      )}
    </>
  );
};
