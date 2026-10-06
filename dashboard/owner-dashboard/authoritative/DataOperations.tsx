import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Panel } from "../../shared/utilities/V3Chrome";
import { AsyncActionButton, AuthorityBadge, SimpleTable } from "./components";
import { useAsyncResource, useOwnerAuthority } from "./hooks";
import {
  configureHistoricalProvider,
  configureHistoricalSchedule,
  listHistoricalProviders,
  listHistoricalSyncJobs,
  repairHistoricalGaps,
  runHistoricalSync,
  toggleHistoricalProvider,
} from "./dataOps";
import { ownerCapabilityAllowance, ownerConnectionAllowance, ownerDatasetApproval, ownerDatasetReplace, ownerDatasetRetire } from "./mutations";
import { queryOwnerConnections } from "./api";

const rowsFrom = (payload: any, key: string): any[] => Array.isArray(payload) ? payload : Array.isArray(payload?.[key]) ? payload[key] : [];

export const DataOperations: React.FC = () => {
  const load = useCallback(async () => {
    const [providers, jobs] = await Promise.all([listHistoricalProviders(), listHistoricalSyncJobs()]);
    return { providers, jobs };
  }, []);
  const { data, loading, error, refresh } = useAsyncResource(load);
  const authority = useOwnerAuthority();
  const [providerId, setProviderId] = useState("");
  const [providerName, setProviderName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [instrument, setInstrument] = useState("NIFTY");
  const [timeframe, setTimeframe] = useState("1m");
  const [startDate, setStartDate] = useState("2026-01-01");
  const [endDate, setEndDate] = useState("2026-01-31");
  const [frequency, setFrequency] = useState("DAILY");
  const [lookbackDays, setLookbackDays] = useState(7);
  const [replacement, setReplacement] = useState("");
  const [capability, setCapability] = useState("");
  const [connectionData, setConnectionData] = useState<any[] | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const providers = useMemo(() => rowsFrom(data?.providers, "providers"), [data]);
  const jobs = useMemo(() => rowsFrom(data?.jobs, "jobs"), [data]);
  const datasetSurface: any = authority.snapshot?.surfaces.datasets;
  const datasetState = datasetSurface?.authority_state || "UNAVAILABLE";
  const datasets = datasetState === "AVAILABLE" ? rowsFrom(datasetSurface, "datasets") : [];
  const loadConnections = async () => {
    try {
      const result = await queryOwnerConnections();
      setConnectionData(rowsFrom(result, "connections"));
      setConnectionError(null);
    } catch (error) {
      setConnectionData(null);
      setConnectionError(error instanceof Error ? error.message : "CONNECTION_AUTHORITY_UNAVAILABLE");
    }
  };
  useEffect(() => { void loadConnections(); }, []);
  const refreshAll = () => { void refresh(); void authority.refresh(); void loadConnections(); };

  if (loading && !data) return <Panel>Loading data authority…</Panel>;
  return <>
    <div className="v3-screen-head"><div><h2 className="v3-screen-title">Connections & Data</h2><p className="v3-screen-sub">Historical provider credentials are write-only. Dataset and sync authority remains backend-owned.</p></div></div>
    {error && <div className="owner-authority-message unavailable"><strong>UNAVAILABLE</strong><div>{error}</div></div>}

    <Panel>
      <div className="v3-region-head"><span className="v3-region-title">Connection Allowance</span><span className="v3-region-note">Owner governance · step-up protected</span></div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
        <input className="v3-input" value={capability} onChange={(e) => setCapability(e.target.value)} placeholder="Capability (for example MARKET_DATA)" />
      </div>
      {connectionError && <div className="owner-authority-message unavailable"><strong>UNAVAILABLE</strong><div>{connectionError}</div></div>}
      {!connectionError && connectionData && connectionData.length === 0 && <div className="v3-region-note">No authoritative Owner connections recorded.</div>}
      {connectionData && connectionData.length > 0 && <SimpleTable rows={connectionData} columns={[
        { key: "connection_id", label: "Connection" }, { key: "provider", label: "Provider" }, { key: "status", label: "Status" }, { key: "owner_allowance", label: "Allowance" },
        { key: "actions", label: "Governance", render: (row) => {
          const id = String(row.connection_id || row.id || "");
          return <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <AsyncActionButton label="ALLOW" onRun={() => ownerConnectionAllowance(id, "ALLOWED", "Owner allow")} onDone={loadConnections} disabled={!id} />
            <AsyncActionButton label="HOLD" tone="warn" onRun={() => ownerConnectionAllowance(id, "HOLD", "Owner hold")} onDone={loadConnections} disabled={!id} />
            <AsyncActionButton label="REVOKE" tone="danger" onRun={() => ownerConnectionAllowance(id, "REVOKED", "Owner revoke")} onDone={loadConnections} disabled={!id} />
            <AsyncActionButton label="Capability ALLOW" onRun={() => ownerCapabilityAllowance(id, capability.trim(), "ALLOWED", "Owner capability allow")} onDone={loadConnections} disabled={!id || !capability.trim()} />
            <AsyncActionButton label="Capability HOLD" tone="warn" onRun={() => ownerCapabilityAllowance(id, capability.trim(), "HOLD", "Owner capability hold")} onDone={loadConnections} disabled={!id || !capability.trim()} />
          </div>;
        } },
      ]} />}
    </Panel>

    <Panel>
      <div className="v3-region-head"><span className="v3-region-title">Providers</span></div>
      <div className="v3-region-note" style={{ marginBottom: 8 }}>Credential input is write-only and is never rendered back after submission.</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(170px,1fr))", gap: 8 }}>
        <input className="v3-input" value={providerId} onChange={(e) => setProviderId(e.target.value)} placeholder="Provider ID" />
        <input className="v3-input" value={providerName} onChange={(e) => setProviderName(e.target.value)} placeholder="Provider name" />
        <input className="v3-input" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="Base URL (optional)" />
        <input className="v3-input" type="password" value={apiSecret} onChange={(e) => setApiSecret(e.target.value)} placeholder="Credential (write-only)" autoComplete="new-password" />
      </div>
      <div style={{ marginTop: 10 }}><AsyncActionButton label="Save Provider" disabled={!providerId.trim() || !providerName.trim()} onRun={async () => {
        await configureHistoricalProvider({ provider_id: providerId.trim(), name: providerName.trim(), base_url: baseUrl.trim() || null, api_key: apiSecret || null, is_enabled: true });
        setApiSecret("");
      }} onDone={refresh} /></div>
      <SimpleTable rows={providers} columns={[
        { key: "provider_id", label: "Provider" }, { key: "provider_name", label: "Name" }, { key: "is_enabled", label: "Enabled" },
        { key: "actions", label: "Control", render: (row) => {
          const id = String(row.provider_id || row.id || "");
          return <div style={{ display: "flex", gap: 6 }}><AsyncActionButton label="Enable" disabled={!id} onRun={() => toggleHistoricalProvider(id, true)} onDone={refresh} /><AsyncActionButton label="Disable" tone="warn" disabled={!id} onRun={() => toggleHistoricalProvider(id, false)} onDone={refresh} /></div>;
        } },
      ]} />
    </Panel>

    <div className="v3-grid">
      <section className="v3-region v3-sp6">
        <div className="v3-region-head"><span className="v3-region-title">Manual Sync</span></div>
        <div style={{ display: "grid", gap: 8 }}>
          <input className="v3-input" value={instrument} onChange={(e) => setInstrument(e.target.value)} placeholder="Instrument" />
          <input className="v3-input" value={timeframe} onChange={(e) => setTimeframe(e.target.value)} placeholder="Timeframe" />
          <input className="v3-input" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          <input className="v3-input" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
          <AsyncActionButton label="Run Manual Sync" onRun={() => runHistoricalSync({ instrument, timeframe, start_date: startDate, end_date: endDate, provider_id: providerId.trim() || null })} onDone={refresh} />
        </div>
      </section>
      <section className="v3-region v3-sp6">
        <div className="v3-region-head"><span className="v3-region-title">Schedule</span></div>
        <div style={{ display: "grid", gap: 8 }}>
          <input className="v3-input" value={frequency} onChange={(e) => setFrequency(e.target.value)} placeholder="Frequency" />
          <input className="v3-input" type="number" value={lookbackDays} onChange={(e) => setLookbackDays(Number(e.target.value) || 1)} />
          <AsyncActionButton label="Save Schedule" onRun={() => configureHistoricalSchedule({ instrument, timeframe, frequency, lookback_days: lookbackDays, provider_id: providerId.trim() || null, is_enabled: true })} onDone={refresh} />
          <AsyncActionButton label="Gap Repair" tone="warn" onRun={() => repairHistoricalGaps({ instrument, timeframe, provider_id: providerId.trim() || null })} onDone={refresh} />
        </div>
      </section>
    </div>

    <Panel><div className="v3-region-head"><span className="v3-region-title">Sync Jobs</span></div><SimpleTable rows={jobs} columns={[{ key: "job_id", label: "Job" }, { key: "instrument", label: "Instrument" }, { key: "status", label: "Status" }, { key: "error", label: "Failure" }]} /></Panel>

    <Panel>
      <div className="v3-region-head"><span className="v3-region-title">Datasets</span><AuthorityBadge state={datasetState} /></div>
      {datasetState !== "AVAILABLE" ? <div className="owner-authority-message unavailable"><strong>UNAVAILABLE</strong><div>Dataset authority is not current.</div></div> : <>
        <input className="v3-input" value={replacement} onChange={(e) => setReplacement(e.target.value)} placeholder="Replacement dataset ID" style={{ marginBottom: 8 }} />
        <SimpleTable rows={datasets} columns={[
          { key: "dataset_id", label: "Dataset" }, { key: "instrument", label: "Instrument" }, { key: "timeframe", label: "Timeframe" }, { key: "readiness", label: "Readiness" },
          { key: "actions", label: "Governance", render: (row) => {
            const id = String(row.dataset_id || row.id || "");
            return <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <AsyncActionButton label="Approve" onRun={() => ownerDatasetApproval(id, "APPROVED", "Owner approval")} onDone={refreshAll} />
              <AsyncActionButton label="Hold" tone="warn" onRun={() => ownerDatasetApproval(id, "HOLD", "Owner hold")} onDone={refreshAll} />
              <AsyncActionButton label="Retire" tone="danger" onRun={() => ownerDatasetRetire(id, "Owner retirement")} onDone={refreshAll} />
              <AsyncActionButton label="Replace" tone="warn" disabled={!replacement.trim()} onRun={() => ownerDatasetReplace(id, replacement.trim(), "Owner replacement")} onDone={refreshAll} />
            </div>;
          } },
        ]} />
      </>}
    </Panel>
  </>;
};
