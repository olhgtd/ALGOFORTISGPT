import React, { useCallback, useEffect, useState } from "react";
import { Panel, TruthChip } from "../utilities/V3Chrome";
import {
  listAllUserConnections,
  setUserConnectionStatus,
  listAllDeployments,
  blockDeployment,
  getOwnerDeploymentsRecovery,
  isBackendEnabled,
  type UserConnection,
  type UserDeployment,
} from "../services/integrationClient";

function maskAccount(ref: string): string {
  if (!ref) return "—";
  if (ref.length <= 6) return `${ref.slice(0, 2)}••••`;
  return `${ref.slice(0, 3)}••••${ref.slice(-2)}`;
}

/** Owner oversight: per-user connections (no secrets) + deployments with block/suspend. */
export const OwnerConnectionsDeployments: React.FC = () => {
  const [connections, setConnections] = useState<UserConnection[]>([]);
  const [deployments, setDeployments] = useState<UserDeployment[]>([]);
  const [connSource, setConnSource] = useState("UNAVAILABLE");
  const [depSource, setDepSource] = useState("UNAVAILABLE");
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [recovery, setRecovery] = useState<any>(null);
  const [blockReason, setBlockReason] = useState<Record<string, string>>({});
  const [statusReason, setStatusReason] = useState<Record<string, string>>({});

  const refresh = useCallback(async () => {
    if (!isBackendEnabled()) {
      setError("BACKEND_AUTHORITY_UNAVAILABLE");
      return;
    }
    setError(null);
    try {
      const [cRes, dRes, rRes] = await Promise.all([
        listAllUserConnections(),
        listAllDeployments(),
        getOwnerDeploymentsRecovery(),
      ]);
      setConnections(cRes.data || []);
      setConnSource(cRes.source);
      setDeployments(dRes.data || []);
      setDepSource(dRes.source);
      if (rRes.source === "BACKEND") setRecovery(rRes.data);
      if (cRes.error || dRes.error) setError(cRes.error || dRes.error || null);
    } catch (e: any) {
      setError(e?.message || "Network error");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 4000);
  };

  const handleConnStatus = async (id: string, status: string) => {
    const reason = statusReason[id] || "Owner governance action";
    const res = await setUserConnectionStatus(id, { status, reason });
    showToast(res.success ? `Connection ${id} → ${status} (backend-confirmed).` : (res.error || "Update failed"));
    void refresh();
  };

  const handleBlock = async (id: string) => {
    const reason = blockReason[id] || "Owner governance block";
    const res = await blockDeployment(id, reason);
    showToast(res.success ? `Deployment ${id} BLOCKED (backend-confirmed).` : (res.error || "Block failed"));
    void refresh();
  };

  return (
    <div id="owner-connections-deployments" style={{ display: "flex", flexDirection: "column", gap: 16, marginTop: 16 }}>
      <div className="v3-screen-head">
        <div>
          <h2 className="v3-screen-title">User Connections & Deployments Oversight</h2>
          <p className="v3-screen-sub">Owner governance · status only, secrets never projected · backend-authoritative</p>
        </div>
        <TruthChip
          kind={connSource === "BACKEND" && depSource === "BACKEND" ? "REAL" : "DISABLED"}
          title="Owner oversight authority"
        />
      </div>

      {toast && <div className="v3-toast" role="status">{toast}</div>}
      {error && <div role="alert" className="auth-error-alert">OVERSIGHT AUTHORITY: {error}</div>}

      <Panel label="Per-User Connections (No Secrets)" meta={`${connections.length} records`} className="v3-sp12">
        {connections.length === 0 ? (
          <div style={{ padding: "20px 12px", textAlign: "center", color: "var(--v3-ink-3)" }} role="status">
            {connSource === "BACKEND" ? "No user connections recorded." : "Oversight authority unavailable."}
          </div>
        ) : (
          <div className="v3-table-wrap">
            <table className="v3-table" id="owner-user-connections-table">
              <thead>
                <tr>
                  <th>USER</th>
                  <th>CONNECTION</th>
                  <th>PROVIDER</th>
                  <th>ACCOUNT (MASKED)</th>
                  <th>STATUS</th>
                  <th>CAPABILITIES</th>
                  <th>SUSPEND</th>
                </tr>
              </thead>
              <tbody>
                {connections.map((c) => (
                  <tr key={c.connectionId}>
                    <td className="v3-mono" style={{ fontSize: 11 }}>{c.userId.slice(0, 13)}…</td>
                    <td className="v3-mono font-bold" style={{ fontSize: 11 }}>{c.connectionId}</td>
                    <td>{c.provider}</td>
                    <td className="v3-mono">{maskAccount(c.accountRef)}</td>
                    <td>
                      <span className="v3-tag">{c.status}</span>
                      <div style={{ fontSize: 11, color: "var(--v3-ink-3)" }}>
                        MD: {c.marketDataCapability} · EX: {c.executionCapability}
                      </div>
                    </td>
                    <td className="v3-mono" style={{ fontSize: 11 }}>{c.healthState}</td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <input
                        className="v3-input"
                        style={{ width: 140, marginRight: 6 }}
                        placeholder="reason"
                        value={statusReason[c.connectionId] || ""}
                        onChange={(e) => setStatusReason((p) => ({ ...p, [c.connectionId]: e.target.value }))}
                        aria-label={`Suspend reason for ${c.connectionId}`}
                      />
                      <button className="v3-btn ghost mini" onClick={() => void handleConnStatus(c.connectionId, "SUSPENDED")} id={`owner-suspend-conn-${c.connectionId}`}>Suspend</button>
                      <button className="v3-btn ghost mini" onClick={() => void handleConnStatus(c.connectionId, "CONFIGURED")} id={`owner-restore-conn-${c.connectionId}`}>Restore</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel label="Deployments Oversight" meta={`${deployments.length} records`} className="v3-sp12">
        {deployments.length === 0 ? (
          <div style={{ padding: "20px 12px", textAlign: "center", color: "var(--v3-ink-3)" }} role="status">
            {depSource === "BACKEND" ? "No deployments recorded." : "Oversight authority unavailable."}
          </div>
        ) : (
          <div className="v3-table-wrap">
            <table className="v3-table" id="owner-deployments-table">
              <thead>
                <tr>
                  <th>USER</th>
                  <th>DEPLOYMENT</th>
                  <th>STRATEGY</th>
                  <th>VERSION</th>
                  <th>MODE</th>
                  <th>STATUS</th>
                  <th>BLOCK REASON</th>
                  <th>BLOCK</th>
                </tr>
              </thead>
              <tbody>
                {deployments.map((d) => (
                  <tr key={d.deploymentId}>
                    <td className="v3-mono" style={{ fontSize: 11 }}>{String(d.userId || "—").slice(0, 13)}…</td>
                    <td className="v3-mono font-bold" style={{ fontSize: 11 }}>{d.deploymentId}</td>
                    <td className="v3-mono" style={{ fontSize: 11 }}>{d.strategyId}</td>
                    <td className="v3-mono" style={{ fontSize: 11 }}>{String(d.strategyVersionId || (d as any).strategy_version_id || "—").slice(0, 13)}</td>
                    <td>{String(d.executionMode || (d as any).execution_mode || "LIVE_PAPER")}</td>
                    <td><span className="v3-tag">{d.status}</span></td>
                    <td style={{ fontSize: 11 }}>{d.blockReason || "—"}</td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <input
                        className="v3-input"
                        style={{ width: 140, marginRight: 6 }}
                        placeholder="block reason"
                        value={blockReason[d.deploymentId] || ""}
                        onChange={(e) => setBlockReason((p) => ({ ...p, [d.deploymentId]: e.target.value }))}
                        aria-label={`Block reason for ${d.deploymentId}`}
                      />
                      <button className="v3-btn danger-ghost mini" onClick={() => void handleBlock(d.deploymentId)} id={`owner-block-deployment-${d.deploymentId}`}>Block</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel label="Deployments Recovery (Authoritative)" className="v3-sp12">
        {recovery ? (
          <pre className="v3-mono" style={{ fontSize: 11, whiteSpace: "pre-wrap", margin: 0 }}>
            {JSON.stringify(recovery, null, 2)}
          </pre>
        ) : (
          <div style={{ fontSize: 12, color: "var(--v3-ink-3)" }}>Recovery snapshot unavailable — backend authority only.</div>
        )}
      </Panel>
    </div>
  );
};
