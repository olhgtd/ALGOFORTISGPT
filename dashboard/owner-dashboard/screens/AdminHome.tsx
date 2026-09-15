import React, { useEffect, useState } from "react";
import { Icon } from "../../shared/icons/V3Icons";
import { TruthChip, Dot, Panel } from "../../shared/utilities/V3Chrome";
import {
  getStoredOwnerUsers,
  getStoredAccessRecords,
  STRATEGIES,
  USER_CONNECTORS,
  PLUGIN_HEALTH,
  AUDIT_ITEMS,
} from "../../sampleData";
import {
  queryPersistenceHealth,
  queryAccessRecords,
  queryOwnerStrategies,
  queryOwnerConnections,
  isForceDemo,
  type BackendPersistenceHealth,
} from "../../shared/services/integrationClient";

/* ════════════════════════════════════════════════════════════
   OWNER CONTROL OVERVIEW — Concise Operational Summary
   Governed by Owner Control Center Architecture & DESIGN.md
   ════════════════════════════════════════════════════════════ */

interface Props {
  go: (screen: string) => void;
  previewMode?: boolean;
}

export const AdminHome: React.FC<Props> = ({ go, previewMode = false }) => {
  const [overviewSource, setOverviewSource] = useState<"BACKEND" | "SAMPLE" | "UNAVAILABLE">(previewMode ? "SAMPLE" : "UNAVAILABLE");
  const [liveAccessRecords, setLiveAccessRecords] = useState<any[] | null>(null);
  const [liveStrategies, setLiveStrategies] = useState<any[] | null>(null);
  const [liveConnections, setLiveConnections] = useState<any[] | null>(null);
  const [liveHealth, setLiveHealth] = useState<BackendPersistenceHealth | null>(null);

  useEffect(() => {
    let active = true;
    Promise.allSettled([
      queryPersistenceHealth(),
      queryAccessRecords(),
      queryOwnerStrategies(),
      queryOwnerConnections(),
    ]).then(([healthRes, accessRes, stratRes, connRes]) => {
      if (!active) return;
      const isAnyBackend =
        (healthRes.status === "fulfilled" && healthRes.value.source === "BACKEND") ||
        (accessRes.status === "fulfilled" && accessRes.value.source === "BACKEND") ||
        (stratRes.status === "fulfilled" && stratRes.value.source === "BACKEND") ||
        (connRes.status === "fulfilled" && connRes.value.source === "BACKEND");

      if (isAnyBackend) {
        setOverviewSource("BACKEND");
        if (healthRes.status === "fulfilled" && healthRes.value.data) setLiveHealth(healthRes.value.data);
        if (accessRes.status === "fulfilled" && accessRes.value.source === "BACKEND") setLiveAccessRecords(accessRes.value.data || []);
        if (stratRes.status === "fulfilled" && stratRes.value.source === "BACKEND") setLiveStrategies(stratRes.value.data || []);
        if (connRes.status === "fulfilled" && connRes.value.source === "BACKEND") setLiveConnections(connRes.value.data || []);
      } else if (previewMode || isForceDemo()) {
        setOverviewSource("SAMPLE");
        setLiveAccessRecords([]);
        setLiveStrategies([]);
        setLiveConnections([]);
      } else {
        setOverviewSource("UNAVAILABLE");
        setLiveAccessRecords([]);
        setLiveStrategies([]);
        setLiveConnections([]);
        setLiveHealth(null);
      }
    });
    return () => { active = false; };
  }, [previewMode]);

  const fallbackUsers: any[] = [];
  const fallbackAccessRecords: any[] = [];

  const accessRecords = liveAccessRecords !== null ? liveAccessRecords : fallbackAccessRecords;
  const totalEnrolled = liveAccessRecords !== null ? accessRecords.length : fallbackUsers.length;
  const usersActive = liveAccessRecords !== null
    ? accessRecords.filter((r: any) => r.accountStatus === "ACTIVE" || r.status === "ACTIVE" || r.status === "REDEEMED").length
    : fallbackUsers.filter((u) => u.accountStatus === "ACTIVE").length;
  const usersInvited = accessRecords.filter((r: any) => (r.status || r.activationStatus) === "INVITED").length;
  const usersSuspended = liveAccessRecords !== null
    ? accessRecords.filter((r: any) => r.accountStatus === "SUSPENDED" || r.status === "SUSPENDED").length
    : fallbackUsers.filter((u) => u.accountStatus === "SUSPENDED").length;

  // 2. Access IDs Summary
  const accessPending = accessRecords.filter((r: any) => (r.status || r.activationStatus) === "INVITED").length;
  const accessRedeemed = accessRecords.filter((r: any) => (r.status || r.activationStatus) === "REDEEMED" || (r.status || r.activationStatus) === "ACTIVE").length;
  const accessExpired = accessRecords.filter((r: any) => (r.status || r.activationStatus) === "EXPIRED").length;
  const accessRevoked = accessRecords.filter((r: any) => (r.status || r.activationStatus) === "REVOKED").length;

  // 3. Strategies Summary
  const stratsList = liveStrategies !== null ? liveStrategies : (previewMode ? STRATEGIES : []);
  const stratsRegistered = stratsList.length;
  const stratsBacktestEligible = stratsList.filter((s: any) => s.stage === "BACKTEST_ELIGIBLE" || s.stage === "BACKTEST" || s.backtestEligibility === "ALLOWED").length;
  const stratsPaperEligible = stratsList.filter((s: any) => s.stage === "PAPER" || s.paperEligibility === "ALLOWED").length;
  const stratsNeedsAttention = stratsList.filter((s: any) => s.scanStatus === "WARNING" || s.conformanceCheck === "NON_CONFORMANT" || s.backtestEligibility === "BLOCKED").length;

  // 4. Connections / Plugins Summary
  const connsList = liveConnections !== null ? liveConnections : (previewMode ? USER_CONNECTORS : []);
  const connHealthy = connsList.filter((c: any) => c.status === "CONNECTED" || c.ownerAllowance === "ALLOWED").length;
  const connNeedsAttention = connsList.filter((c: any) => c.status === "NEEDS_ATTENTION" || c.ownerAllowance === "HOLD").length;
  const connOffline = connsList.filter((c: any) => c.status === "OFFLINE" || c.status === "DISCONNECTED" || c.ownerAllowance === "REVOKED").length;

  // 5. System Health Summary
  const subsystemsList = liveHealth ? Object.entries(liveHealth.subsystems || {}) : [];
  const operationalSubsystemsCount = subsystemsList.filter(([_, v]) => v === "OPERATIONAL" || v === "ACTIVE" || v === "HEALTHY").length;
  const systemState = overviewSource === "UNAVAILABLE" || !liveHealth
    ? "UNAVAILABLE"
    : (liveHealth.databaseConnected && liveHealth.auditStoreOperational ? "Healthy" : "Degraded");

  return (
    <>
      <div className="v3-screen-head">
        <div>
          <h2 className="v3-screen-title">Owner Overview</h2>
          <p className="v3-screen-sub">
            AlgoFortis Owner Control Center · Authoritative institutional governance, access registry &amp; operational oversight
          </p>
        </div>
        <TruthChip
          kind={overviewSource === "BACKEND" ? "REAL" : (overviewSource === "SAMPLE" ? "SAMPLE" : "DISABLED")}
          title={overviewSource === "BACKEND" ? "REAL + WORKING — Authoritative AlgoFortis System State" : (overviewSource === "SAMPLE" ? "Sample System State (Demo Mode)" : "BACKEND UNAVAILABLE — Operational Authority Disconnected")}
        />
      </div>

      {/* Governance Banner */}
      <div className="dev-preview-banner" style={{ marginBottom: 18 }}>
        <span className="banner-tag">OWNER AUTHORITY</span>
        <span>
          FAIL-CLOSED GOVERNANCE ACTIVE · Owner authority cannot bypass pre-trade risk gates or alter immutable audit logs.
        </span>
      </div>

      {/* 5 Operational Summary Regions Grid */}
      <div className="v3-grid">
        {/* 1. Users Operational Summary */}
        <section className="v3-region v3-sp6" id="owner-users-summary-card">
          <div className="v3-region-head" style={{ marginBottom: 12 }}>
            <span className="v3-region-title">Users Oversight</span>
            <button className="v3-entry-link" onClick={() => go("users")} id="overview-goto-users-btn">
              Manage users <Icon name="chevron" size={14} />
            </button>
          </div>
          <div style={{ display: "flex", gap: 32, flexWrap: "wrap", alignItems: "baseline" }}>
            <div>
              <div className="v3-stat-big">{totalEnrolled}</div>
              <div className="v3-region-note">Total Enrolled</div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div className="v3-stat-line"><Dot tone="ok" /> <strong>{usersActive}</strong> Active Accounts</div>
              <div className="v3-stat-line"><Dot tone="live" /> <strong>{usersInvited}</strong> Pending Invites</div>
              <div className="v3-stat-line"><Dot tone="neg" /> <strong>{usersSuspended}</strong> Suspended Accounts</div>
            </div>
          </div>
        </section>

        {/* 2. Access IDs Operational Summary */}
        <section className="v3-region v3-sp6" id="owner-access-summary-card">
          <div className="v3-region-head" style={{ marginBottom: 12 }}>
            <span className="v3-region-title">Access Registry</span>
            <button className="v3-entry-link" onClick={() => go("access-registry")} id="overview-goto-access-btn">
              Registry table <Icon name="chevron" size={14} />
            </button>
          </div>
          <div style={{ display: "flex", gap: 32, flexWrap: "wrap", alignItems: "baseline" }}>
            <div>
              <div className="v3-stat-big">{accessRecords.length}</div>
              <div className="v3-region-note">Total Access IDs</div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div className="v3-stat-line"><Dot tone="live" /> <strong>{accessPending}</strong> Pending Token{accessPending === 1 ? "" : "s"}</div>
              <div className="v3-stat-line"><Dot tone="ok" /> <strong>{accessRedeemed}</strong> Redeemed / Active</div>
              <div className="v3-stat-line"><Dot tone="warn" /> <strong>{accessExpired}</strong> Expired · <Dot tone="neg" /> <strong>{accessRevoked}</strong> Revoked</div>
            </div>
          </div>
        </section>

        {/* 3. Strategies Oversight */}
        <section className="v3-region v3-sp6" id="owner-strategies-summary-card">
          <div className="v3-region-head" style={{ marginBottom: 12 }}>
            <span className="v3-region-title">Strategies Governance</span>
            <button className="v3-entry-link" onClick={() => go("strategies")} id="overview-goto-strategies-btn">
              Strategy desk <Icon name="chevron" size={14} />
            </button>
          </div>
          <div style={{ display: "flex", gap: 32, flexWrap: "wrap", alignItems: "baseline" }}>
            <div>
              <div className="v3-stat-big">{stratsRegistered}</div>
              <div className="v3-region-note">Registered Strategies</div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div className="v3-stat-line"><Dot tone="ok" /> <strong>{stratsPaperEligible}</strong> Paper Eligible / Live</div>
              <div className="v3-stat-line"><Dot tone="warn" /> <strong>{stratsBacktestEligible}</strong> Backtest Eligible</div>
              <div className="v3-stat-line">
                <Dot tone={stratsNeedsAttention > 0 ? "warn" : "ok"} />
                <strong>{stratsNeedsAttention}</strong> {stratsNeedsAttention === 0 ? "All conformant" : "Needs Attention"}
              </div>
            </div>
          </div>
        </section>

        {/* 4. Connections & Plugins Fleet */}
        <section className="v3-region v3-sp6" id="owner-connections-summary-card">
          <div className="v3-region-head" style={{ marginBottom: 12 }}>
            <span className="v3-region-title">Broker Connections &amp; Plugins</span>
            <button className="v3-entry-link" onClick={() => go("plugins")} id="overview-goto-plugins-btn">
              Plugin fleet <Icon name="chevron" size={14} />
            </button>
          </div>
          <div style={{ display: "flex", gap: 32, flexWrap: "wrap", alignItems: "baseline" }}>
            <div>
              <div className="v3-stat-big">{connsList.length}</div>
              <div className="v3-region-note">Gateway Connectors</div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {connsList.length === 0 ? (
                <div className="v3-stat-line"><Dot tone="dim" /> <strong>0</strong> Broker connections configured</div>
              ) : (
                <>
                  <div className="v3-stat-line"><Dot tone="ok" /> <strong>{connHealthy}</strong> Healthy</div>
                  {connNeedsAttention > 0 && <div className="v3-stat-line"><Dot tone="warn" /> <strong>{connNeedsAttention}</strong> Needs Attention</div>}
                  {connOffline > 0 && <div className="v3-stat-line"><Dot tone="neg" /> <strong>{connOffline}</strong> Offline</div>}
                </>
              )}
            </div>
          </div>
        </section>

        {/* 5. System Health & Security Stream */}
        <section className="v3-region v3-sp12" id="owner-system-summary-card">
          <div className="v3-region-head" style={{ marginBottom: 12 }}>
            <span className="v3-region-title">System Health &amp; Security Authority</span>
            <button className="v3-entry-link" onClick={() => go("system")} id="overview-goto-system-btn">
              System health <Icon name="chevron" size={14} />
            </button>
          </div>
          <div style={{ display: "flex", gap: 48, flexWrap: "wrap", alignItems: "center", justifyContent: "space-between" }}>
            <div>
              <div className="v3-hero-label">System State</div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginTop: 4 }}>
                {overviewSource === "UNAVAILABLE" || !liveHealth ? (
                  <>
                    <span className="v3-hero-value" id="control-system-state" style={{ fontSize: 32, color: "var(--v3-ink-dim)" }}>
                      OFFLINE
                    </span>
                    <span className="v3-hero-delta">
                      <Dot tone="neg" />
                      Backend Authority Unavailable
                    </span>
                  </>
                ) : (
                  <>
                    <span className="v3-hero-value" id="control-system-state" style={{ fontSize: 32 }}>
                      {operationalSubsystemsCount}/{subsystemsList.length > 0 ? subsystemsList.length : (liveHealth.databaseConnected ? 1 : 0)}
                    </span>
                    <span className="v3-hero-delta">
                      <Dot tone={systemState === "Healthy" ? "ok" : "warn"} />
                      {systemState === "Healthy" ? "All Subsystems Nominal" : "Subsystem Attention Required"}
                    </span>
                  </>
                )}
              </div>
            </div>

            <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
              <div className="v3-stat-line">
                <Dot tone={liveHealth?.databaseConnected ? "ok" : "neg"} /> Persistence: {liveHealth?.databaseConnected ? `Connected (${liveHealth.journalMode || "WAL"})` : "Disconnected"}
              </div>
              <div className="v3-stat-line">
                <Dot tone={liveHealth?.auditStoreOperational ? "ok" : "warn"} /> Audit Ledger: {liveHealth?.auditStoreOperational ? `${liveHealth.auditEventCount} sealed events` : "Unavailable"}
              </div>
              <div className="v3-stat-line">
                <Dot tone={liveHealth?.subsystems?.backend_api === "OPERATIONAL" ? "ok" : (liveHealth?.adapterReachable ? "ok" : "neg")} /> Backend API: {liveHealth?.subsystems?.backend_api || (liveHealth?.adapterReachable ? "Operational" : "Disconnected")}
              </div>
              <div className="v3-stat-line">
                <Dot tone={liveHealth?.subsystems?.risk_runtime ? "ok" : "dim"} /> Risk Sentinel: {liveHealth?.subsystems?.risk_runtime || "ENFORCED"}
              </div>
            </div>
          </div>
        </section>
      </div>
    </>
  );
};

