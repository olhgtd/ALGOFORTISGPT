import React, { useCallback, useEffect, useState } from "react";
import { Panel, TruthChip } from "../utilities/V3Chrome";
import {
  listUserConnections,
  createUserConnection,
  updateUserConnection,
  retireUserConnection,
  mapStrategyConnection,
  getStrategyMapping,
  queryUserStrategyRegistry,
  isBackendEnabled,
  type UserConnection,
} from "../services/integrationClient";

const TRUTHFUL_STATUS_HELP: Record<string, string> = {
  NOT_CONNECTED: "No broker session bound. Market data and execution are unavailable on this connection.",
  CONFIGURED: "Account reference stored. No live broker session is implied.",
  DISABLED: "Disabled by the user. It will not be used for market data or execution.",
  RETIRED: "Retired by the user. Record preserved for history; it is operationally dead and immutable.",
  SUSPENDED: "Suspended by Owner governance. It cannot be used until restored.",
  ERROR: "Last verification reported an error. See backend reason.",
};

function capabilityNote(c: UserConnection): string {
  const parts: string[] = [];
  parts.push(`Market data: ${c.marketDataCapability || "UNKNOWN"}`);
  parts.push(`Execution: ${c.executionCapability || "DISARMED"}`);
  if ((c.executionCapability || "").toUpperCase().includes("DISARM")) {
    parts.push("READ_ONLY/DISARMED — no real execution");
  }
  return parts.join(" · ");
}

/** Authoritative per-user connections. Renders ONLY backend states; NEVER fabricates CONNECTED. */
export const UserConnectionsRuntime: React.FC = () => {
  const [connections, setConnections] = useState<UserConnection[]>([]);
  const [source, setSource] = useState<string>("UNAVAILABLE");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [provider, setProvider] = useState("PAPER_INTERNAL");
  const [accountRef, setAccountRef] = useState("");
  const [toast, setToast] = useState<string | null>(null);
  const [strategies, setStrategies] = useState<{ id: string; version: string }[]>([]);
  const [mapStrategy, setMapStrategy] = useState("");
  const [mapConnection, setMapConnection] = useState("");
  const [mapMode, setMapMode] = useState("LIVE_PAPER");

  const refresh = useCallback(async () => {
    if (!isBackendEnabled()) {
      setConnections([]);
      setSource("UNAVAILABLE");
      setError("BACKEND_AUTHORITY_UNAVAILABLE");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await listUserConnections();
      setConnections(res.data || []);
      setSource(res.source);
      if (res.error) setError(res.error);
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
  }, [refresh]);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 4000);
  };

  const handleCreate = async () => {
    if (!accountRef.trim()) {
      showToast("Account reference is required.");
      return;
    }
    const res = await createUserConnection({ provider, accountRef: accountRef.trim() });
    if (res.success) {
      showToast(`Connection recorded: ${res.data?.connectionId || "ok"}`);
      setAccountRef("");
      void refresh();
    } else {
      showToast(res.error || "Create failed");
    }
  };

  const handleDisable = async (id: string, status: string) => {
    const next = status === "DISABLED" ? "CONFIGURED" : "DISABLED";
    const res = await updateUserConnection(id, { status: next });
    if (res.success) {
      showToast(`Connection ${id} → ${next} (backend-confirmed).`);
      void refresh();
    } else {
      showToast(res.error || "Update failed");
    }
  };

  const handleRetire = async (id: string) => {
    const res = await retireUserConnection(id);
    if (res.success) {
      showToast(`Connection ${id} retired (backend-confirmed). Record preserved; authority revoked.`);
      void refresh();
    } else {
      showToast(res.error || "Retire failed");
    }
  };

  const handleMap = async () => {
    if (!mapStrategy || !mapConnection) {
      showToast("Select a strategy and a connection to map.");
      return;
    }
    const strat = strategies.find((s) => s.id === mapStrategy);
    const res = await mapStrategyConnection(mapStrategy, {
      connection_id: mapConnection,
      execution_mode: mapMode,
      strategy_version_id: strat?.version,
    });
    if (res.success) {
      showToast(`Strategy mapped to connection (backend-confirmed).`);
    } else {
      showToast(res.error || "Mapping failed");
    }
  };

  const handleCheckMapping = async () => {
    if (!mapStrategy) return;
    const res = await getStrategyMapping(mapStrategy, mapMode);
    if (res.data) {
      showToast(`Backend mapping: ${(res.data as any).connection_id || JSON.stringify(res.data)}`);
    } else {
      showToast(res.error || "No mapping on backend.");
    }
  };

  return (
    <div id="user-connections-runtime" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="v3-screen-head">
        <div>
          <h2 className="v3-screen-title">Connections</h2>
          <p className="v3-screen-sub">
            Per-user broker/API connections · backend-authoritative states only · secrets never displayed
          </p>
        </div>
        <TruthChip
          kind={source === "BACKEND" ? "REAL" : "DISABLED"}
          title={source === "BACKEND" ? "Backend connection authority" : "Connection authority unavailable"}
        />
      </div>

      {toast && <div className="v3-toast" role="status">{toast}</div>}
      {error && <div role="alert" className="auth-error-alert">CONNECTION AUTHORITY: {error}</div>}

      <Panel label="Your Connections (Authoritative)" meta={`${connections.length} records`} className="v3-sp12">
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <button className="v3-btn ghost mini" onClick={() => void refresh()} disabled={busy} id="connections-refresh-btn">
            Refresh from backend
          </button>
        </div>
        {connections.length === 0 ? (
          <div style={{ padding: "20px 12px", textAlign: "center", color: "var(--v3-ink-3)" }} role="status">
            {source === "BACKEND" ? "No connections recorded for this user." : "Connection authority unavailable."}
          </div>
        ) : (
          <div className="v3-table-wrap">
            <table className="v3-table" id="user-connections-table">
              <thead>
                <tr>
                  <th>CONNECTION</th>
                  <th>PROVIDER</th>
                  <th>ACCOUNT REF (MASKED)</th>
                  <th>STATUS</th>
                  <th>CAPABILITIES</th>
                  <th>HEALTH</th>
                  <th>ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {connections.map((c) => (
                  <tr key={c.connectionId}>
                    <td className="v3-mono font-bold">{c.connectionId}</td>
                    <td>{c.provider}</td>
                    <td className="v3-mono">{c.accountRef}</td>
                    <td>
                      <span className="v3-tag" title={TRUTHFUL_STATUS_HELP[c.status] || c.status}>
                        {c.status}
                      </span>
                      {c.suspended && (
                        <div style={{ fontSize: 11, color: "var(--v3-loss-text)" }}>
                          Suspended: {c.suspendReason || "Owner governance"}
                        </div>
                      )}
                    </td>
                    <td style={{ fontSize: 11 }}>{capabilityNote(c)}</td>
                    <td className="v3-mono" style={{ fontSize: 11 }}>{c.healthState}</td>
                    <td>
                      <button
                        className="v3-btn ghost mini"
                        onClick={() => void handleDisable(c.connectionId, c.status)}
                        id={`connection-toggle-${c.connectionId}`}
                        disabled={c.status === "RETIRED"}
                      >
                        {c.status === "DISABLED" ? "Enable" : "Disable"}
                      </button>
                      {c.status !== "RETIRED" && (
                        <button
                          className="v3-btn ghost mini"
                          onClick={() => void handleRetire(c.connectionId)}
                          id={`connection-retire-${c.connectionId}`}
                          title="Retire: preserve history, revoke authority, clear credential reference"
                        >
                          Retire
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div style={{ fontSize: 11, color: "var(--v3-ink-3)", marginTop: 8 }}>
          Connection states are backend-authoritative (NOT_CONNECTED, CONFIGURED, DISABLED, RETIRED, SUSPENDED, ERROR).
          A live broker CONNECTED session is never implied by this surface.
        </div>
      </Panel>

      <Panel label="Record a Connection (Preparation Only)" className="v3-sp12">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", gap: 10, alignItems: "end" }}>
          <div>
            <label className="v3-field-label" htmlFor="new-connection-provider">Provider</label>
            <select id="new-connection-provider" className="v3-input" value={provider} onChange={(e) => setProvider(e.target.value)}>
              <option value="PAPER_INTERNAL">PAPER_INTERNAL</option>
              <option value="UPSTOX">UPSTOX</option>
              <option value="ZERODHA">ZERODHA (KITE)</option>
              <option value="DHAN">DHAN</option>
              <option value="ANGEL_ONE">ANGEL ONE</option>
            </select>
          </div>
          <div>
            <label className="v3-field-label" htmlFor="new-connection-account">Account reference</label>
            <input
              id="new-connection-account"
              className="v3-input v3-mono"
              value={accountRef}
              onChange={(e) => setAccountRef(e.target.value)}
              placeholder="e.g. ACC-PAPER-001"
            />
          </div>
          <button className="v3-btn primary" onClick={() => void handleCreate()} id="create-connection-btn">
            Record connection
          </button>
        </div>
        <div style={{ fontSize: 11, color: "var(--v3-ink-3)", marginTop: 8 }}>
          Recording a connection stores an account reference only. It does not establish a broker session and never handles secrets in this view.
        </div>
      </Panel>

      <Panel label="Map Strategy → Connection (Preparation Only)" className="v3-sp12">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr auto auto", gap: 10, alignItems: "end" }}>
          <div>
            <label className="v3-field-label" htmlFor="map-strategy-select">Strategy</label>
            <select id="map-strategy-select" className="v3-input" value={mapStrategy} onChange={(e) => setMapStrategy(e.target.value)}>
              <option value="">Select strategy</option>
              {strategies.map((s) => (
                <option key={s.id} value={s.id}>{s.id} ({s.version.slice(0, 8)})</option>
              ))}
            </select>
          </div>
          <div>
            <label className="v3-field-label" htmlFor="map-connection-select">Connection</label>
            <select id="map-connection-select" className="v3-input" value={mapConnection} onChange={(e) => setMapConnection(e.target.value)}>
              <option value="">Select connection</option>
              {connections.map((c) => (
                <option key={c.connectionId} value={c.connectionId}>{c.connectionId} · {c.status}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="v3-field-label" htmlFor="map-mode-select">Execution mode</label>
            <select id="map-mode-select" className="v3-input" value={mapMode} onChange={(e) => setMapMode(e.target.value)}>
              <option value="LIVE_PAPER">LIVE_PAPER</option>
              <option value="LIVE">LIVE</option>
            </select>
          </div>
          <button className="v3-btn primary" onClick={() => void handleMap()} id="map-strategy-connection-btn">Map</button>
          <button className="v3-btn ghost" onClick={() => void handleCheckMapping()} id="check-strategy-mapping-btn">Check backend mapping</button>
        </div>
      </Panel>
    </div>
  );
};
