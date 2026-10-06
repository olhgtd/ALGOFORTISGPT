import React, { useMemo, useState } from "react";
import { Panel, Dot } from "../../shared/utilities/V3Chrome";
import type { AuthorityState } from "../authority";
import {
  bindAIAgent,
  cancelAIJob,
  configureAIModel,
  configureAIProvider,
  createAIJob,
  createOwnerAccess,
  ownerAccountAction,
  ownerStrategyAction,
  queryOwnerAI,
  queryOwnerAudit,
  queryOwnerBacktests,
  queryOwnerDevices,
  queryOwnerOrdersPortfolio,
  queryOwnerPaperSessions,
  queryOwnerReports,
  queryOwnerSessions,
  queryServerSettings,
  setAIAgentPolicy,
} from "./api";
import {
  confirmOwnerSetting,
  ownerCapabilityAllowance,
  ownerConnectionAllowance,
  ownerDatasetApproval,
  ownerDatasetReplace,
  ownerDatasetRetire,
  ownerStrategyAssignment,
  proposeOwnerSetting,
  revokeOwnerDevice,
  revokeOwnerSession,
} from "./mutations";
import { useAsyncResource, useOwnerAuthority } from "./hooks";
import { AuthorityBadge, AuthorityPanel, AsyncActionButton, SafeMetric, SimpleTable } from "./components";

const asState = (value: unknown): AuthorityState => (
  value === "AVAILABLE" || value === "STALE" || value === "UNKNOWN" || value === "UNAVAILABLE"
    ? value
    : "UNKNOWN"
);
const asRows = (value: unknown): any[] => Array.isArray(value) ? value : [];
const screenHead = (title: string, subtitle: string) => (
  <div className="v3-screen-head">
    <div><h2 className="v3-screen-title">{title}</h2><p className="v3-screen-sub">{subtitle}</p></div>
  </div>
);

export const OwnerOverviewScreen: React.FC<{ go: (id: string) => void }> = ({ go }) => {
  const { snapshot, loading, error, refresh } = useOwnerAuthority();
  if (loading) return <Panel>Loading authoritative Owner state…</Panel>;
  if (!snapshot) return <AuthorityPanel title="Owner Control Center" state="UNAVAILABLE" reason={error} onRefresh={refresh} />;
  const { health, access, strategies, connections, datasets, security, ai } = snapshot.surfaces;
  const cards = [
    ["Users & Access", access, "records", "users"],
    ["Strategies", strategies, "strategies", "strategies"],
    ["Connections", connections, "connections", "plugins"],
    ["Datasets", datasets, "datasets", "plugins"],
  ] as const;
  return <>
    {screenHead("Owner Overview", "Backend-authoritative governance. Missing authority is never rendered as zero, healthy, PASS, or safe.")}
    <div className="dev-preview-banner" style={{ marginBottom: 18 }}>
      <span className="banner-tag">SAFETY</span>
      <span>LIVE {snapshot.live_state} · Owner broker mutation {snapshot.broker_mutation} · destructive actions require fresh WebAuthn step-up.</span>
    </div>
    <div className="v3-grid">
      {cards.map(([title, surface, key, target]) => {
        const state = asState(surface.authority_state);
        const rows = asRows(surface[key]);
        return <section key={title} className="v3-region v3-sp6">
          <div className="v3-region-head"><span className="v3-region-title">{title}</span><AuthorityBadge state={state} /></div>
          <div style={{ display: "flex", gap: 24, alignItems: "end", marginTop: 12 }}>
            <SafeMetric state={state} label="Authoritative records" value={rows.length} />
            <button className="v3-btn ghost mini" onClick={() => go(target)}>Open</button>
          </div>
          {state !== "AVAILABLE" && <div className="v3-region-note" style={{ marginTop: 10 }}>{String(surface.error || "Authority not current")}</div>}
        </section>;
      })}
      <section className="v3-region v3-sp6">
        <div className="v3-region-head"><span className="v3-region-title">System / Audit</span><AuthorityBadge state={asState(health.authority_state)} /></div>
        <div style={{ marginTop: 12 }}>
          <div className="v3-stat-line"><Dot tone={health.database_connected ? "ok" : "neg"} /> Database {health.database_connected ? "connected" : "not verified"}</div>
          <div className="v3-stat-line"><Dot tone={health.audit_store_operational ? "ok" : "neg"} /> Core audit {health.audit_store_operational ? "operational" : "not verified"}</div>
        </div>
      </section>
      <section className="v3-region v3-sp6">
        <div className="v3-region-head"><span className="v3-region-title">Security Authority</span><AuthorityBadge state={asState(security.authority_state)} /></div>
        <div style={{ marginTop: 12 }}>
          <div className="v3-stat-line">WebAuthn: <strong>{String(security.webauthn || "UNKNOWN")}</strong></div>
          <div className="v3-stat-line">Owner authenticators: <strong>{security.owner_authenticators_ready === true ? "READY" : "NOT VERIFIED"}</strong></div>
        </div>
      </section>
      <section className="v3-region v3-sp12">
        <div className="v3-region-head"><span className="v3-region-title">AI Control Plane</span><AuthorityBadge state={asState(ai.authority_state)} /></div>
        <div style={{ display: "flex", gap: 28, flexWrap: "wrap", marginTop: 12 }}>
          <div><strong>Routing owner:</strong> {String(ai.routing_owner || "PRIME")}</div>
          <div><strong>Agents:</strong> {asRows(ai.agents).length}</div>
          <div><strong>Providers:</strong> {asRows(ai.providers).length}</div>
          <div><strong>Recent jobs:</strong> {asRows(ai.jobs).length}</div>
          <button className="v3-btn ghost mini" onClick={() => go("ai-control")}>Open AI Control Center</button>
        </div>
      </section>
    </div>
  </>;
};

export const OwnerUsersScreen: React.FC = () => {
  const { snapshot, loading, error, refresh } = useOwnerAuthority();
  if (loading) return <Panel>Loading users…</Panel>;
  const surface = snapshot?.surfaces.access;
  const state = asState(surface?.authority_state);
  const rows = state === "AVAILABLE" ? asRows(surface?.records) : [];
  return <>
    {screenHead("Users Oversight", "Authoritative account lifecycle and service status. Administrative changes require passkey step-up.")}
    <AuthorityPanel title="User Accounts" state={surface ? state : "UNAVAILABLE"} reason={error || String(surface?.error || "")} onRefresh={refresh}>
      <SimpleTable rows={rows} columns={[
        { key: "sxId", label: "SX ID" },
        { key: "displayName", label: "Name" },
        { key: "emailMasked", label: "Email" },
        { key: "accountStatus", label: "Account" },
        { key: "serviceStatus", label: "Service" },
        { key: "actions", label: "Governance", render: (row) => <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {row.accountStatus === "SUSPENDED" ?
            <AsyncActionButton label="Restore" tone="warn" onRun={() => ownerAccountAction(row.sxId, "restore", { notes: "Owner restore" })} onDone={refresh} /> :
            <AsyncActionButton label="Suspend" tone="warn" onRun={() => ownerAccountAction(row.sxId, "suspend", { notes: "Owner suspension" })} onDone={refresh} />}
          <AsyncActionButton label="Revoke" tone="danger" onRun={() => ownerAccountAction(row.sxId, "revoke", { notes: "Owner revocation" })} onDone={refresh} />
        </div> },
      ]} />
    </AuthorityPanel>
  </>;
};

export const OwnerAccessRegistryScreen: React.FC = () => {
  const { snapshot, loading, error, refresh } = useOwnerAuthority();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  if (loading) return <Panel>Loading access registry…</Panel>;
  const surface = snapshot?.surfaces.access;
  const state = asState(surface?.authority_state);
  const rows = state === "AVAILABLE" ? asRows(surface?.records) : [];
  const create = async () => {
    if (!name.trim() || !email.trim()) { setMessage("Name and email are required."); return; }
    const result = await createOwnerAccess({
      display_name: name.trim(), email: email.trim(), phone: phone.trim(), role: "USER",
      plan: "Quant Professional", service_term_type: "3_MONTHS", notes: "Owner-created access record",
    });
    setMessage(result?.activation_code ? `Created. Activation code is shown once: ${result.activation_code}` : "Created and confirmed by backend.");
    setName(""); setEmail(""); setPhone(""); await refresh();
  };
  return <>
    {screenHead("Access Registry", "Backend-generated identities and activation lifecycle. No prototype IDs or locally generated activation codes.")}
    <div className="v3-grid">
      <section className="v3-region v3-sp12">
        <div className="v3-region-head"><span className="v3-region-title">Create User Access</span><AuthorityBadge state={state} /></div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 10, marginTop: 12 }}>
          <input className="v3-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Display name" />
          <input className="v3-input" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" />
          <input className="v3-input" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Phone" />
          <AsyncActionButton label="Create with passkey" onRun={create} disabled={state !== "AVAILABLE"} />
        </div>
        {message && <p className="v3-region-note">{message}</p>}
      </section>
      <section className="v3-region v3-sp12">
        <SimpleTable rows={rows} columns={[
          { key: "sxId", label: "SX ID" }, { key: "displayName", label: "User" },
          { key: "activationStatus", label: "Activation" }, { key: "accountStatus", label: "Account" },
          { key: "serviceTermLabel", label: "Term" }, { key: "serviceStatus", label: "Service" },
          { key: "actions", label: "Lifecycle & Activation", render: (row) => {
            const identifier = String(row.sxId || row.id || "");
            return <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <AsyncActionButton label="Suspend" tone="warn" disabled={!identifier} onRun={() => ownerAccountAction(identifier, "suspend", { notes: "Owner account suspension" })} onDone={refresh} />
              <AsyncActionButton label="Restore" disabled={!identifier} onRun={() => ownerAccountAction(identifier, "restore", { notes: "Owner account restoration" })} onDone={refresh} />
              <AsyncActionButton label="Revoke" tone="danger" disabled={!identifier} onRun={() => ownerAccountAction(identifier, "revoke", { notes: "Owner account revocation" })} onDone={refresh} />
              <AsyncActionButton label="Reissue" onRun={() => ownerAccountAction(identifier, "reissue-activation", { notes: "Owner reissue" })} onDone={refresh} />
              <AsyncActionButton label="Revoke invite" tone="danger" onRun={() => ownerAccountAction(identifier, "revoke-activation", { notes: "Owner activation revoke" })} onDone={refresh} />
              <AsyncActionButton label="+3 months" tone="warn" onRun={() => ownerAccountAction(identifier, "extend-service", { service_term_type: "3_MONTHS", notes: "Owner extension" })} onDone={refresh} />
              <AsyncActionButton label="Renew 3 months" tone="warn" onRun={() => ownerAccountAction(identifier, "renew-service", { service_term_type: "3_MONTHS", notes: "Owner renewal" })} onDone={refresh} />
              <AsyncActionButton label="Lifetime" tone="warn" onRun={() => ownerAccountAction(identifier, "convert-lifetime", { notes: "Owner lifetime conversion" })} onDone={refresh} />
            </div>;
          } },
        ]} />
      </section>
    </div>
  </>;
};

export const OwnerStrategiesScreen: React.FC = () => {
  const { snapshot, loading, error, refresh } = useOwnerAuthority();
  const [assignmentUserId, setAssignmentUserId] = useState("");
  if (loading) return <Panel>Loading strategy authority…</Panel>;
  const surface = snapshot?.surfaces.strategies;
  const state = asState(surface?.authority_state);
  const rows = state === "AVAILABLE" ? asRows(surface?.strategies) : [];
  const userId = assignmentUserId.trim();
  return <>
    {screenHead("Strategies Governance", "Owner restrictions never bypass readiness, deterministic validation, or RiskGate authority.")}
    <AuthorityPanel title="Strategy Registry" state={surface ? state : "UNAVAILABLE"} reason={error || String(surface?.error || "")} onRefresh={refresh}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        <input className="v3-input" value={assignmentUserId} onChange={(e) => setAssignmentUserId(e.target.value)} placeholder="User ID for assignment" />
      </div>
      <SimpleTable rows={rows} columns={[
        { key: "strategy_id", label: "Strategy" }, { key: "name", label: "Name" }, { key: "version", label: "Version" },
        { key: "stage", label: "Stage" }, { key: "admin_status", label: "Admin" },
        { key: "governance", label: "Governance", render: (row) => {
          const strategyId = row.strategy_id || row.id;
          return <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <AsyncActionButton label="Paper HOLD" tone="warn" onRun={() => ownerStrategyAction(strategyId, "allowance", { sandbox: "paper", allowance: "HOLD", reason: "Owner hold" })} onDone={refresh} />
            <AsyncActionButton label="Publish" onRun={() => ownerStrategyAction(strategyId, "visibility", { visibility: "GLOBAL" })} onDone={refresh} />
            <AsyncActionButton label="Owner private" tone="warn" onRun={() => ownerStrategyAction(strategyId, "visibility", { visibility: "OWNER_PRIVATE" })} onDone={refresh} />
            <AsyncActionButton label="Promote Paper" onRun={() => ownerStrategyAction(strategyId, "promote", { target_stage: "PAPER_ELIGIBLE", version: row.version, notes: "Owner Paper promotion" })} onDone={refresh} />
            <AsyncActionButton label="Assign user" onRun={() => ownerStrategyAssignment(strategyId, userId, false)} onDone={refresh} disabled={!userId} />
            <AsyncActionButton label="Revoke assignment" tone="warn" onRun={() => ownerStrategyAssignment(strategyId, userId, true)} onDone={refresh} disabled={!userId} />
            <AsyncActionButton label="Suspend" tone="danger" onRun={() => ownerStrategyAction(strategyId, "suspend", { reason: "Owner suspension" })} onDone={refresh} />
            <AsyncActionButton label="Restore" onRun={() => ownerStrategyAction(strategyId, "restore", { notes: "Owner restore" })} onDone={refresh} />
          </div>;
        } },
      ]} />
    </AuthorityPanel>
  </>;
};

export const OwnerConnectionsScreen: React.FC = () => {
  const { snapshot, loading, error, refresh } = useOwnerAuthority();
  const [capability, setCapability] = useState("");
  const [replacementDatasetId, setReplacementDatasetId] = useState("");
  const [datasetReason, setDatasetReason] = useState("Owner governance change");
  if (loading) return <Panel>Loading connections…</Panel>;
  const connections = snapshot?.surfaces.connections;
  const datasets = snapshot?.surfaces.datasets;
  const connState = asState(connections?.authority_state);
  const dataState = asState(datasets?.authority_state);
  const connRows = connState === "AVAILABLE" ? asRows(connections?.connections) : [];
  const dataRows = dataState === "AVAILABLE" ? asRows(datasets?.datasets) : [];
  const capabilityName = capability.trim();
  const replacementId = replacementDatasetId.trim();
  const reason = datasetReason.trim() || "Owner governance change";
  return <>
    {screenHead("Connections & Datasets", "Broker/data governance only. A connected broker never implies Live armed.")}
    <div className="v3-grid">
      <section className="v3-region v3-sp12">
        <div className="v3-region-head"><span className="v3-region-title">Connections</span><AuthorityBadge state={connState} /></div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "10px 0" }}>
          <input className="v3-input" value={capability} onChange={(e) => setCapability(e.target.value)} placeholder="Capability (for example MARKET_DATA)" />
        </div>
        {connState === "AVAILABLE" ? <SimpleTable rows={connRows} columns={[
          { key: "connection_id", label: "Connection" }, { key: "provider", label: "Provider" }, { key: "status", label: "Status" },
          { key: "owner_allowance", label: "Owner allowance" },
          { key: "actions", label: "Governance", render: (row) => {
            const connectionId = row.connection_id || row.id;
            return <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <AsyncActionButton label="ALLOW" onRun={() => ownerConnectionAllowance(connectionId, "ALLOWED", "Owner allow")} onDone={refresh} />
              <AsyncActionButton label="HOLD" tone="warn" onRun={() => ownerConnectionAllowance(connectionId, "HOLD", "Owner hold")} onDone={refresh} />
              <AsyncActionButton label="REVOKE" tone="danger" onRun={() => ownerConnectionAllowance(connectionId, "REVOKED", "Owner revoke")} onDone={refresh} />
              <AsyncActionButton label="Capability ALLOW" onRun={() => ownerCapabilityAllowance(connectionId, capabilityName, "ALLOWED", "Owner capability allow")} onDone={refresh} disabled={!capabilityName} />
              <AsyncActionButton label="Capability HOLD" tone="warn" onRun={() => ownerCapabilityAllowance(connectionId, capabilityName, "HOLD", "Owner capability hold")} onDone={refresh} disabled={!capabilityName} />
            </div>;
          } },
        ]} /> : <div className="owner-authority-message unavailable">{error || String(connections?.error || "Connection authority unavailable")}</div>}
      </section>
      <section className="v3-region v3-sp12">
        <div className="v3-region-head"><span className="v3-region-title">Datasets</span><AuthorityBadge state={dataState} /></div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "10px 0" }}>
          <input className="v3-input" value={replacementDatasetId} onChange={(e) => setReplacementDatasetId(e.target.value)} placeholder="Replacement dataset ID" />
          <input className="v3-input" value={datasetReason} onChange={(e) => setDatasetReason(e.target.value)} placeholder="Governance reason" />
        </div>
        {dataState === "AVAILABLE" ? <SimpleTable rows={dataRows} columns={[
          { key: "dataset_id", label: "Dataset" }, { key: "instrument", label: "Instrument" }, { key: "timeframe", label: "Timeframe" },
          { key: "owner_approval", label: "Approval" }, { key: "readiness", label: "Readiness" },
          { key: "actions", label: "Governance", render: (row) => {
            const datasetId = row.dataset_id || row.id;
            return <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <AsyncActionButton label="Approve" onRun={() => ownerDatasetApproval(datasetId, "APPROVED", "Owner approval")} onDone={refresh} />
              <AsyncActionButton label="Hold" tone="warn" onRun={() => ownerDatasetApproval(datasetId, "HOLD", "Owner hold")} onDone={refresh} />
              <AsyncActionButton label="Reject" tone="danger" onRun={() => ownerDatasetApproval(datasetId, "REJECTED", reason)} onDone={refresh} />
              <AsyncActionButton label="Retire" tone="danger" onRun={() => ownerDatasetRetire(datasetId, reason)} onDone={refresh} />
              <AsyncActionButton label="Replace" tone="warn" onRun={() => ownerDatasetReplace(datasetId, replacementId, reason)} onDone={refresh} disabled={!replacementId} />
            </div>;
          } },
        ]} /> : <div className="owner-authority-message unavailable">{String(datasets?.error || "Dataset authority unavailable")}</div>}
      </section>
    </div>
  </>;
};

export const OwnerBacktestsScreen: React.FC = () => {
  const resource = useAsyncResource(queryOwnerBacktests);
  const rows = asRows((resource.data as any)?.runs || (resource.data as any)?.backtests || resource.data);
  return <>{screenHead("Backtests Oversight", "Deterministic research/backtest evidence; no duplicate V1 engine.")}
    <AuthorityPanel title="Backtest Runs" state={resource.error ? "UNAVAILABLE" : resource.loading ? "UNKNOWN" : "AVAILABLE"} reason={resource.error} onRefresh={resource.refresh}>
      <SimpleTable rows={rows} columns={[{ key: "run_id", label: "Run" }, { key: "strategy_id", label: "Strategy" }, { key: "status", label: "Status" }, { key: "dataset_id", label: "Dataset" }, { key: "created_at_utc", label: "Created" }]} />
    </AuthorityPanel></>;
};

export const OwnerPaperScreen: React.FC = () => {
  const resource = useAsyncResource(queryOwnerPaperSessions);
  const rows = asRows((resource.data as any)?.sessions || resource.data);
  return <>{screenHead("Paper Sessions", "Paper authority is isolated from Live. Recovery and resume remain backend-controlled.")}
    <AuthorityPanel title="Paper Sessions" state={resource.error ? "UNAVAILABLE" : resource.loading ? "UNKNOWN" : "AVAILABLE"} reason={resource.error} onRefresh={resource.refresh}>
      <SimpleTable rows={rows} columns={[{ key: "session_id", label: "Session" }, { key: "strategy_id", label: "Strategy" }, { key: "status", label: "Status" }, { key: "data_source_mode", label: "Data" }, { key: "created_at_utc", label: "Created" }]} />
    </AuthorityPanel></>;
};

export const OwnerPortfolioOrdersScreen: React.FC = () => {
  const resource = useAsyncResource(() => queryOwnerOrdersPortfolio("PAPER"));
  const payload: any = resource.data || {};
  const available = !resource.error && payload.availability !== "UNAVAILABLE";
  return <>{screenHead("Portfolio & Orders Oversight", "Read-side oversight only. Owner UI has no place/modify/cancel broker authority.")}
    <div className="v3-grid">
      <section className="v3-region v3-sp12"><div className="v3-region-head"><span className="v3-region-title">Positions</span><AuthorityBadge state={available ? "AVAILABLE" : "UNAVAILABLE"} /></div><SimpleTable rows={available ? asRows(payload.positions) : []} columns={[{ key: "session_id", label: "Session" }, { key: "strategy_name", label: "Strategy" }, { key: "instrument", label: "Instrument" }, { key: "quantity", label: "Quantity" }, { key: "status", label: "Status" }]} /></section>
      <section className="v3-region v3-sp12"><div className="v3-region-head"><span className="v3-region-title">Orders</span><AuthorityBadge state={available ? "AVAILABLE" : "UNAVAILABLE"} /></div><SimpleTable rows={available ? asRows(payload.orders) : []} columns={[{ key: "session_id", label: "Session" }, { key: "order_id", label: "Order" }, { key: "strategy_name", label: "Strategy" }, { key: "status", label: "Status" }, { key: "execution_mode", label: "Mode" }]} /></section>
    </div></>;
};

export const OwnerReportsAuditScreen: React.FC = () => {
  const reports = useAsyncResource(queryOwnerReports);
  const audit = useAsyncResource(queryOwnerAudit);
  const reportRows = asRows((reports.data as any)?.reports || reports.data);
  const auditRows = asRows((audit.data as any)?.events || audit.data);
  return <>{screenHead("Reports & Audit", "Reports are backend evidence. Core Audit is immutable authority; no simulated report success.")}
    <div className="v3-grid">
      <section className="v3-region v3-sp12"><div className="v3-region-head"><span className="v3-region-title">Reports</span><AuthorityBadge state={reports.error ? "UNAVAILABLE" : reports.loading ? "UNKNOWN" : "AVAILABLE"} /></div><SimpleTable rows={reportRows} columns={[{ key: "report_id", label: "Report" }, { key: "category", label: "Category" }, { key: "status", label: "Status" }, { key: "created_at_utc", label: "Created" }, { key: "evidence_ref", label: "Evidence" }]} /></section>
      <section className="v3-region v3-sp12"><div className="v3-region-head"><span className="v3-region-title">Core Audit</span><AuthorityBadge state={audit.error ? "UNAVAILABLE" : audit.loading ? "UNKNOWN" : "AVAILABLE"} /></div><SimpleTable rows={auditRows} columns={[{ key: "timestamp", label: "Time" }, { key: "eventFamily", label: "Family" }, { key: "eventType", label: "Event" }, { key: "status", label: "Status" }, { key: "evidenceRef", label: "Evidence" }]} /></section>
    </div></>;
};

export const OwnerSystemScreen: React.FC = () => {
  const { snapshot, loading, error, refresh } = useOwnerAuthority();
  if (loading) return <Panel>Loading system authority…</Panel>;
  const health = snapshot?.surfaces.health;
  const state = asState(health?.authority_state);
  const subsystems = health && typeof health.subsystems === "object" && health.subsystems ? Object.entries(health.subsystems as Record<string, string>) : [];
  return <>{screenHead("System Health", "Operational truth from backend persistence and subsystem authorities.")}
    <AuthorityPanel title="Runtime & Persistence" state={health ? state : "UNAVAILABLE"} reason={error || String(health?.error || "")} onRefresh={refresh}>
      <div className="v3-grid">
        <SafeMetric state={state} label="Audit events" value={health?.audit_event_count as number} />
        <SafeMetric state={state} label="Schema version" value={health?.schema_version as number} />
      </div>
      <SimpleTable rows={subsystems.map(([name, status]) => ({ name, status }))} columns={[{ key: "name", label: "Subsystem" }, { key: "status", label: "State" }]} />
    </AuthorityPanel></>;
};

export const OwnerSecurityScreen: React.FC = () => {
  const { snapshot, loading, error, refresh } = useOwnerAuthority();
  const sessions = useAsyncResource(queryOwnerSessions);
  const devices = useAsyncResource(queryOwnerDevices);
  if (loading) return <Panel>Loading security authority…</Panel>;
  const security = snapshot?.surfaces.security;
  const state = asState(security?.authority_state);
  const sessionRows = asRows((sessions.data as any)?.sessions || sessions.data);
  const deviceRows = asRows((devices.data as any)?.devices || devices.data);
  return <>{screenHead("Security Authority", "Passkeys, sessions and devices are backend authority. Revocation requires fresh WebAuthn step-up.")}
    <div className="v3-grid">
      <section className="v3-region v3-sp12"><div className="v3-region-head"><span className="v3-region-title">Security Posture</span><AuthorityBadge state={state} /></div>{state === "AVAILABLE" ? <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}><div>WebAuthn <strong>{String(security?.webauthn || "UNKNOWN")}</strong></div><div>Enrollment <strong>{String(security?.webauthn_enrollment || "UNKNOWN")}</strong></div><div>mTLS <strong>{String(security?.normal_mtls || "UNKNOWN")}</strong></div></div> : <div className="owner-authority-message unavailable">{error || "Security authority unavailable"}</div>}</section>
      <section className="v3-region v3-sp12"><div className="v3-region-head"><span className="v3-region-title">Sessions</span><AuthorityBadge state={sessions.error ? "UNAVAILABLE" : sessions.loading ? "UNKNOWN" : "AVAILABLE"} /></div><SimpleTable rows={sessions.error ? [] : sessionRows} columns={[{ key: "session_ref", label: "Session" }, { key: "sx_id", label: "User" }, { key: "risk", label: "Risk" }, { key: "expires_at_utc", label: "Expires" }, { key: "actions", label: "Action", render: (row) => <AsyncActionButton label="Revoke" tone="danger" onRun={() => revokeOwnerSession(row.session_ref || row.id)} onDone={sessions.refresh} /> }]} /></section>
      <section className="v3-region v3-sp12"><div className="v3-region-head"><span className="v3-region-title">Devices</span><AuthorityBadge state={devices.error ? "UNAVAILABLE" : devices.loading ? "UNKNOWN" : "AVAILABLE"} /></div><SimpleTable rows={devices.error ? [] : deviceRows} columns={[{ key: "credential_id", label: "Credential" }, { key: "sx_id", label: "User" }, { key: "label", label: "Label" }, { key: "status", label: "Status" }, { key: "actions", label: "Action", render: (row) => <AsyncActionButton label="Revoke" tone="danger" onRun={() => revokeOwnerDevice(row.credential_id || row.id)} onDone={devices.refresh} /> }]} /></section>
    </div></>;
};

export const OwnerSettingsScreen: React.FC = () => {
  const settings = useAsyncResource(queryServerSettings);
  const [key, setKey] = useState("stale_threshold_seconds");
  const [value, setValue] = useState("");
  const [proposal, setProposal] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const propose = async () => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) throw new Error("Numeric value required");
    const result = await proposeOwnerSetting(key, numeric);
    setProposal(result.proposal_id || result.data?.proposal_id || null);
    setMessage("Proposal staged; effective state has not changed.");
  };
  const confirm = async () => {
    if (!proposal) throw new Error("No staged proposal");
    await confirmOwnerSetting(proposal);
    setProposal(null); setMessage("Applied and backend confirmation requested."); await settings.refresh();
  };
  return <>{screenHead("Settings", "Safe settings lifecycle: PROPOSE → CONFIRM → APPLY → re-read. Protected Live/RiskGate keys remain forbidden.")}
    <div className="v3-grid">
      <section className="v3-region v3-sp12"><div className="v3-region-head"><span className="v3-region-title">Effective Settings</span><AuthorityBadge state={settings.error ? "UNAVAILABLE" : settings.loading ? "UNKNOWN" : "AVAILABLE"} /></div><pre style={{ whiteSpace: "pre-wrap" }}>{settings.error ? "Authority unavailable" : JSON.stringify(settings.data, null, 2)}</pre></section>
      <section className="v3-region v3-sp12"><div className="v3-region-head"><span className="v3-region-title">Change Proposal</span></div><div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}><select className="v3-input" value={key} onChange={(e) => setKey(e.target.value)}><option value="stale_threshold_seconds">Stale threshold</option><option value="retention_policy_days">Retention days</option></select><input className="v3-input" value={value} onChange={(e) => setValue(e.target.value)} placeholder="Value" /><AsyncActionButton label="Propose" onRun={propose} /><AsyncActionButton label="Confirm" tone="warn" onRun={confirm} disabled={!proposal} /></div>{message && <p className="v3-region-note">{message}</p>}</section>
    </div></>;
};

export const OwnerAIControlScreen: React.FC = () => {
  const ai = useAsyncResource(queryOwnerAI);
  const [providerId, setProviderId] = useState("");
  const [providerName, setProviderName] = useState("");
  const [modelId, setModelId] = useState("");
  const [modelName, setModelName] = useState("");
  const [agentId, setAgentId] = useState("laya");
  const [jobType, setJobType] = useState("MARKET_INTELLIGENCE");
  const payload: any = ai.data || {};
  const state = ai.error ? "UNAVAILABLE" : ai.loading ? "UNKNOWN" : asState(payload.authority_state);
  const providers = asRows(payload.providers);
  const models = asRows(payload.models);
  const agents = asRows(payload.agents);
  const jobs = asRows(payload.jobs);
  const selectedProvider = providerId || providers[0]?.provider_id || "";
  const selectedModel = modelId || models[0]?.model_id || "";
  return <>{screenHead("AI Control Center", "Prime orchestrates. Laya is market intelligence only. Research and Risk Challenger remain advisory. No broker mutation or Live arm authority.")}
    <div className="dev-preview-banner" style={{ marginBottom: 18 }}><span className="banner-tag">AI SAFETY</span><span>RESEARCH / SHADOW ONLY · routing owner PRIME · Live READ_ONLY/DISARMED</span></div>
    <div className="v3-grid">
      <section className="v3-region v3-sp12"><div className="v3-region-head"><span className="v3-region-title">Agents</span><AuthorityBadge state={state} /></div><SimpleTable rows={agents} columns={[{ key: "display_name", label: "Agent" }, { key: "role_type", label: "Role" }, { key: "authority_state", label: "Authority" }, { key: "provider", label: "Provider", render: (row) => row.provider?.display_name || "—" }, { key: "model", label: "Model", render: (row) => row.model?.display_name || "—" }, { key: "actions", label: "Policy", render: (row) => <AsyncActionButton label={row.enabled ? "Disable" : "Enable"} tone="warn" onRun={() => setAIAgentPolicy(row.agent_id, !row.enabled)} onDone={ai.refresh} /> }]} /></section>
      <section className="v3-region v3-sp6"><div className="v3-region-head"><span className="v3-region-title">Provider Registry</span></div><div style={{ display: "flex", flexDirection: "column", gap: 8 }}><input className="v3-input" value={providerId} onChange={(e) => setProviderId(e.target.value)} placeholder="Provider ID" /><input className="v3-input" value={providerName} onChange={(e) => setProviderName(e.target.value)} placeholder="Display name" /><AsyncActionButton label="Save provider" onRun={async () => { if (!providerId || !providerName) throw new Error("Provider ID and name required"); await configureAIProvider(providerId, { display_name: providerName, provider_type: "OPENAI_COMPATIBLE", credential_ref: null, enabled: true, authority_state: "UNKNOWN" }); await ai.refresh(); }} /></div><SimpleTable rows={providers} columns={[{ key: "provider_id", label: "ID" }, { key: "display_name", label: "Provider" }, { key: "authority_state", label: "State" }]} /></section>
      <section className="v3-region v3-sp6"><div className="v3-region-head"><span className="v3-region-title">Model Registry</span></div><div style={{ display: "flex", flexDirection: "column", gap: 8 }}><input className="v3-input" value={modelId} onChange={(e) => setModelId(e.target.value)} placeholder="Model ID" /><input className="v3-input" value={modelName} onChange={(e) => setModelName(e.target.value)} placeholder="Display name" /><AsyncActionButton label="Save model" onRun={async () => { if (!modelId || !modelName || !selectedProvider) throw new Error("Model and provider required"); await configureAIModel(modelId, { provider_id: selectedProvider, display_name: modelName, capability: "RESEARCH", enabled: true, authority_state: "UNKNOWN" }); await ai.refresh(); }} /></div><SimpleTable rows={models} columns={[{ key: "model_id", label: "ID" }, { key: "provider_id", label: "Provider" }, { key: "display_name", label: "Model" }, { key: "authority_state", label: "State" }]} /></section>
      <section className="v3-region v3-sp12"><div className="v3-region-head"><span className="v3-region-title">Agent Binding</span></div><div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}><select className="v3-input" value={agentId} onChange={(e) => setAgentId(e.target.value)}>{["prime", "laya", "research", "risk-challenger"].map((id) => <option key={id} value={id}>{id}</option>)}</select><select className="v3-input" value={selectedProvider} onChange={(e) => setProviderId(e.target.value)}>{providers.map((p) => <option key={p.provider_id} value={p.provider_id}>{p.display_name || p.provider_id}</option>)}</select><select className="v3-input" value={selectedModel} onChange={(e) => setModelId(e.target.value)}>{models.filter((m) => !selectedProvider || m.provider_id === selectedProvider).map((m) => <option key={m.model_id} value={m.model_id}>{m.display_name || m.model_id}</option>)}</select><AsyncActionButton label="Bind (fail-closed)" onRun={async () => { if (!selectedProvider || !selectedModel) throw new Error("Provider/model required"); await bindAIAgent(agentId, { provider_id: selectedProvider, model_id: selectedModel, fallback_policy: { mode: "FAIL_CLOSED" } }); await ai.refresh(); }} /></div></section>
      <section className="v3-region v3-sp12"><div className="v3-region-head"><span className="v3-region-title">Research / Shadow Jobs</span></div><div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}><select className="v3-input" value={jobType} onChange={(e) => setJobType(e.target.value)}><option value="MARKET_INTELLIGENCE">Laya · Market intelligence</option><option value="STRATEGY_RESEARCH">Research Agent</option><option value="RISK_CHALLENGE">Risk Challenger</option><option value="ORCHESTRATE">Prime orchestration</option></select><AsyncActionButton label="Create research job" onRun={async () => { await createAIJob({ job_type: jobType, scope: "RESEARCH", request: {}, auto_submit: false }); await ai.refresh(); }} /></div><SimpleTable rows={jobs} columns={[{ key: "job_id", label: "Job" }, { key: "agent_id", label: "Agent" }, { key: "job_type", label: "Type" }, { key: "scope", label: "Scope" }, { key: "status", label: "Status" }, { key: "failure_reason", label: "Reason" }, { key: "actions", label: "Action", render: (row) => <AsyncActionButton label="Cancel" tone="warn" disabled={!['QUEUED','BLOCKED'].includes(row.status)} onRun={() => cancelAIJob(row.job_id)} onDone={ai.refresh} /> }]} /></section>
    </div>
  </>;
};

export const OwnerIncidentsScreen: React.FC = () => {
  const { snapshot, loading, error, refresh } = useOwnerAuthority();
  const rows = snapshot?.incidents || [];
  return <>{screenHead("Owner Security Incidents", "Subordinate incident evidence linked to authoritative Core Audit references.")}
    <AuthorityPanel title="Failure / Rejection Incidents" state={error ? "UNAVAILABLE" : loading ? "UNKNOWN" : "AVAILABLE"} reason={error} onRefresh={refresh}>
      <SimpleTable rows={rows} columns={[{ key: "created_at_utc", label: "Time" }, { key: "action_family", label: "Action" }, { key: "resource_ref", label: "Resource" }, { key: "status", label: "Status" }, { key: "reason_code", label: "Reason" }, { key: "core_audit_ref", label: "Core Audit" }]} />
    </AuthorityPanel></>;
};
