import React, { useCallback, useMemo, useState } from "react";
import { Panel } from "../../shared/utilities/V3Chrome";
import { AsyncActionButton, SimpleTable } from "./components";
import { useAsyncResource } from "./hooks";
import {
  createOwnerDeployment,
  getOwnerDeploymentRecovery,
  listOwnerDeployments,
  pauseOwnerDeployment,
  resumeOwnerDeployment,
  stopOwnerDeployment,
} from "./deploymentOps";

const rowsFrom = (payload: any, key: string): any[] => Array.isArray(payload) ? payload : Array.isArray(payload?.[key]) ? payload[key] : [];

export const DeploymentOperations: React.FC = () => {
  const load = useCallback(async () => {
    const [deployments, recovery] = await Promise.all([listOwnerDeployments(), getOwnerDeploymentRecovery()]);
    return { deployments, recovery };
  }, []);
  const { data, loading, error, refresh } = useAsyncResource(load);
  const rows = useMemo(() => rowsFrom(data?.deployments, "deployments"), [data]);
  const [strategyId, setStrategyId] = useState("");
  const [versionId, setVersionId] = useState("");
  const [connectionId, setConnectionId] = useState("");
  const [instrument, setInstrument] = useState("NIFTY");
  const [timeframe, setTimeframe] = useState("1m");

  if (loading && !data) return <Panel>Loading deployment authority…</Panel>;

  return <>
    <div className="v3-screen-head"><div><h2 className="v3-screen-title">Deployments</h2><p className="v3-screen-sub">Owner deployment operations are restricted to LIVE_PAPER. Real-money Live remains READ_ONLY / DISARMED.</p></div></div>
    {error && <div className="owner-authority-message unavailable"><strong>UNAVAILABLE</strong><div>{error}</div></div>}

    <Panel>
      <div className="v3-region-head"><span className="v3-region-title">Create LIVE_PAPER Deployment</span></div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))", gap: 8 }}>
        <input className="v3-input" value={strategyId} onChange={(e) => setStrategyId(e.target.value)} placeholder="Strategy ID" />
        <input className="v3-input" value={versionId} onChange={(e) => setVersionId(e.target.value)} placeholder="Version ID (optional)" />
        <input className="v3-input" value={connectionId} onChange={(e) => setConnectionId(e.target.value)} placeholder="Connection ID (optional)" />
        <input className="v3-input" value={instrument} onChange={(e) => setInstrument(e.target.value)} placeholder="Instrument" />
        <input className="v3-input" value={timeframe} onChange={(e) => setTimeframe(e.target.value)} placeholder="Timeframe" />
      </div>
      <div style={{ marginTop: 12 }}><AsyncActionButton label="Create Deployment" disabled={!strategyId.trim() || !instrument.trim()} onRun={() => createOwnerDeployment({ strategy_id: strategyId.trim(), strategy_version_id: versionId.trim() || null, connection_id: connectionId.trim() || null, instrument: instrument.trim(), timeframe: timeframe.trim() })} onDone={refresh} /></div>
    </Panel>

    <section className="v3-region v3-sp12">
      <div className="v3-region-head"><span className="v3-region-title">Installation-wide Deployments</span></div>
      <SimpleTable rows={rows} columns={[
        { key: "deploymentId", label: "Deployment" }, { key: "strategyId", label: "Strategy" }, { key: "executionMode", label: "Mode" }, { key: "status", label: "Status" },
        { key: "actions", label: "Controls", render: (row) => {
          const id = String(row.deploymentId || row.deployment_id || row.id || "");
          return <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <AsyncActionButton label="Pause" tone="warn" disabled={!id} onRun={() => pauseOwnerDeployment(id)} onDone={refresh} />
            <AsyncActionButton label="Resume" disabled={!id} onRun={() => resumeOwnerDeployment(id)} onDone={refresh} />
            <AsyncActionButton label="Stop" tone="danger" disabled={!id} onRun={() => stopOwnerDeployment(id)} onDone={refresh} />
          </div>;
        } },
      ]} />
    </section>

    <Panel>
      <div className="v3-region-head"><span className="v3-region-title">Recovery</span></div>
      <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", margin: 0 }}>{JSON.stringify(data?.recovery ?? { state: "UNAVAILABLE" }, null, 2)}</pre>
    </Panel>
  </>;
};
