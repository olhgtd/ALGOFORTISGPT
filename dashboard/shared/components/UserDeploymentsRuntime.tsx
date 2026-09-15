import React, { useCallback, useEffect, useState } from "react";
import { Panel, TruthChip } from "../utilities/V3Chrome";
import {
  listUserDeployments,
  createUserDeployment,
  pauseUserDeployment,
  resumeUserDeployment,
  stopUserDeployment,
  getUserDeploymentsRecovery,
  queryUserStrategyRegistry,
  listUserConnections,
  isBackendEnabled,
  type UserDeployment,
} from "../services/integrationClient";

function modeOf(d: UserDeployment): string {
  return String(d.executionMode || d.execution_mode || "LIVE_PAPER");
}

function versionOf(d: UserDeployment): string {
  return String(d.strategyVersionId || (d as any).strategy_version_id || "—");
}

/** Authoritative per-user deployments. Backend responses are the only truth. */
export const UserDeploymentsRuntime: React.FC = () => {
  const [deployments, setDeployments] = useState<UserDeployment[]>([]);
  const [source, setSource] = useState<string>("UNAVAILABLE");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [recovery, setRecovery] = useState<any>(null);
  const [strategies, setStrategies] = useState<{ id: string; version: string }[]>([]);
  const [connections, setConnections] = useState<{ id: string; status: string }[]>([]);

  const [strategyId, setStrategyId] = useState("");
  const [connectionId, setConnectionId] = useState("");
  const [instrument, setInstrument] = useState("NIFTY");
  const [timeframe, setTimeframe] = useState("1m");
  const [executionMode, setExecutionMode] = useState("LIVE_PAPER");

  const refresh = useCallback(async () => {
    if (!isBackendEnabled()) {
      setDeployments([]);
      setSource("UNAVAILABLE");
      setError("BACKEND_AUTHORITY_UNAVAILABLE");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await listUserDeployments();
      setDeployments(res.data || []);
      setSource(res.source);
      if (res.error) setError(res.error);
      const rec = await getUserDeploymentsRecovery();
      if (rec.source === "BACKEND") setRecovery(rec.data);
    } catch (e: any) {
      setError(e?.message || "Network error");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    queryUserStrategyRegistry().then((r) => {
      if (r.source === "BACKEND") {
        setStrategies((r.data || []).map((s) => ({ id: s.strategy_id, version: s.version_id })));
      }
    }).catch(() => {});
    listUserConnections().then((r) => {
      if (r.source === "BACKEND") {
        setConnections((r.data || []).map((c) => ({ id: c.connectionId, status: c.status })));
      }
    }).catch(() => {});
  }, [refresh]);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 4000);
  };

  const handleCreate = async () => {
    if (!strategyId) {
      showToast("Select a strategy.");
      return;
    }
    const strat = strategies.find((s) => s.id === strategyId);
    const res = await createUserDeployment({
      strategy_id: strategyId,
      strategy_version_id: strat?.version,
      connection_id: connectionId || undefined,
      instrument,
      timeframe,
      execution_mode: executionMode,
    });
    if (res.success) {
      showToast(`Deployment created: ${(res.data as any)?.deploymentId || "ok"} (backend-confirmed).`);
      void refresh();
    } else {
      showToast(res.error || "Create failed");
    }
  };

  const act = async (id: string, fn: (x: string) => Promise<{ success: boolean; error?: string }>, label: string) => {
    const res = await fn(id);
    showToast(res.success ? `Deployment ${id} → ${label} (backend-confirmed).` : (res.error || `${label} failed`));
    void refresh();
  };

  return (
    <div id="user-deployments-runtime" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="v3-screen-head">
        <div>
          <h2 className="v3-screen-title">Deployments</h2>
          <p className="v3-screen-sub">
            Persistent deployment lifecycle · backend-authoritative status only · state management, no execution
          </p>
        </div>
        <TruthChip
          kind={source === "BACKEND" ? "REAL" : "DISABLED"}
          title={source === "BACKEND" ? "Backend deployment authority" : "Deployment authority unavailable"}
        />
      </div>

      {toast && <div className="v3-toast" role="status">{toast}</div>}
      {error && <div role="alert" className="auth-error-alert">DEPLOYMENT AUTHORITY: {error}</div>}

      <Panel label="Your Deployments (Authoritative)" meta={`${deployments.length} records`} className="v3-sp12">
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <button className="v3-btn ghost mini" onClick={() => void refresh()} disabled={busy} id="deployments-refresh-btn">
            Refresh from backend
          </button>
        </div>
        {deployments.length === 0 ? (
          <div style={{ padding: "20px 12px", textAlign: "center", color: "var(--v3-ink-3)" }} role="status">
            {source === "BACKEND" ? "No deployments recorded for this user." : "Deployment authority unavailable."}
          </div>
        ) : (
          <div className="v3-table-wrap">
            <table className="v3-table" id="user-deployments-table">
              <thead>
                <tr>
                  <th>DEPLOYMENT</th>
                  <th>STRATEGY</th>
                  <th>VERSION</th>
                  <th>MODE</th>
                  <th>STATUS</th>
                  <th>BLOCK REASON</th>
                  <th>ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {deployments.map((d) => (
                  <tr key={d.deploymentId}>
                    <td className="v3-mono font-bold">{d.deploymentId}</td>
                    <td className="v3-mono">{d.strategyId}</td>
                    <td className="v3-mono" style={{ fontSize: 11 }}>{versionOf(d).slice(0, 13)}</td>
                    <td>{modeOf(d)}</td>
                    <td><span className="v3-tag">{d.status}</span></td>
                    <td style={{ fontSize: 11 }}>{d.blockReason || "—"}</td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <button className="v3-btn ghost mini" onClick={() => void act(d.deploymentId, pauseUserDeployment, "PAUSED")} id={`deployment-pause-${d.deploymentId}`}>Pause</button>
                      <button className="v3-btn ghost mini" onClick={() => void act(d.deploymentId, resumeUserDeployment, "RESUMED")} id={`deployment-resume-${d.deploymentId}`}>Resume</button>
                      <button className="v3-btn ghost mini" onClick={() => void act(d.deploymentId, stopUserDeployment, "STOPPED")} id={`deployment-stop-${d.deploymentId}`}>Stop</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel label="New Deployment (State Only)" className="v3-sp12">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr 1fr auto", gap: 10, alignItems: "end" }}>
          <div>
            <label className="v3-field-label" htmlFor="new-deployment-strategy">Strategy</label>
            <select id="new-deployment-strategy" className="v3-input" value={strategyId} onChange={(e) => setStrategyId(e.target.value)}>
              <option value="">Select</option>
              {strategies.map((s) => (
                <option key={s.id} value={s.id}>{s.id}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="v3-field-label" htmlFor="new-deployment-connection">Connection (optional)</label>
            <select id="new-deployment-connection" className="v3-input" value={connectionId} onChange={(e) => setConnectionId(e.target.value)}>
              <option value="">None</option>
              {connections.map((c) => (
                <option key={c.id} value={c.id}>{c.id} · {c.status}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="v3-field-label" htmlFor="new-deployment-instrument">Instrument</label>
            <select id="new-deployment-instrument" className="v3-input" value={instrument} onChange={(e) => setInstrument(e.target.value)}>
              <option value="NIFTY">NIFTY</option>
              <option value="BANKNIFTY">BANKNIFTY</option>
            </select>
          </div>
          <div>
            <label className="v3-field-label" htmlFor="new-deployment-timeframe">Timeframe</label>
            <select id="new-deployment-timeframe" className="v3-input" value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
              <option value="1m">1m</option>
              <option value="5m">5m</option>
              <option value="15m">15m</option>
            </select>
          </div>
          <div>
            <label className="v3-field-label" htmlFor="new-deployment-mode">Mode</label>
            <select id="new-deployment-mode" className="v3-input" value={executionMode} onChange={(e) => setExecutionMode(e.target.value)}>
              <option value="LIVE_PAPER">LIVE_PAPER</option>
              <option value="LIVE">LIVE</option>
            </select>
          </div>
          <button className="v3-btn primary" onClick={() => void handleCreate()} id="create-deployment-btn">Create</button>
        </div>
      </Panel>

      <Panel label="Recovery Snapshot (Authoritative)" className="v3-sp12">
        {recovery ? (
          <pre className="v3-mono" style={{ fontSize: 11, whiteSpace: "pre-wrap", margin: 0 }} id="deployments-recovery-view">
            {JSON.stringify(recovery, null, 2)}
          </pre>
        ) : (
          <div style={{ fontSize: 12, color: "var(--v3-ink-3)" }}>Recovery snapshot unavailable — backend authority only.</div>
        )}
      </Panel>
    </div>
  );
};
